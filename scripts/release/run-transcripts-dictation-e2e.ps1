[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$FfmpegPath = "ffmpeg",
    [string]$FfprobePath = "ffprobe",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$backendRoot = Join-Path $repositoryRoot "backend"
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$taskTemp = Join-Path $tempRoot ("icoder-transcripts-dictation-e2e-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $taskTemp | Out-Null
$databasePath = Join-Path $taskTemp "dictation.db"
$serverOut = Join-Path $taskTemp "uvicorn.out.log"
$serverErr = Join-Path $taskTemp "uvicorn.err.log"

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

$environmentNames = @(
    "DATABASE_URL", "ICODER_DATABASE_URL", "APP_ENV", "SEED_ON_STARTUP",
    "ICODER_CREDENTIAL_LLM", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
    "ICODER_ENABLE_EXTERNAL_LLM", "ICODER_ALLOW_EXTERNAL_LLM",
    "ICODER_DISABLE_NATIVE_MEDCODER", "ICODER_ENABLE_LOCAL_STT",
    "ICODER_E2E_ALLOW_SYNTHETIC_STT", "ICODER_E2E_BASE_URL",
    "ICODER_E2E_FFMPEG_PATH", "ICODER_TRANSCRIPTS_MEDIA_DECODER_PATH",
    "ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH",
    "ICODER_SECRET_KEY", "ICODER_PHI_ENCRYPTION_KEY", "ICODER_ENVIRONMENT",
    "ICODER_REGION", "NO_PROXY", "no_proxy", "PYTHONPATH"
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

$server = $null
try {
    $env:DATABASE_URL = "sqlite+aiosqlite:///" + $databasePath.Replace("\", "/")
    $env:ICODER_DATABASE_URL = $env:DATABASE_URL
    $env:APP_ENV = "local"
    $env:SEED_ON_STARTUP = "0"
    $env:ICODER_CREDENTIAL_LLM = ""
    $env:DEEPSEEK_API_KEY = ""
    $env:OPENAI_API_KEY = ""
    $env:ICODER_ENABLE_EXTERNAL_LLM = "false"
    $env:ICODER_ALLOW_EXTERNAL_LLM = "false"
    $env:ICODER_DISABLE_NATIVE_MEDCODER = "true"
    $env:ICODER_ENABLE_LOCAL_STT = "false"
    $env:ICODER_E2E_ALLOW_SYNTHETIC_STT = "1"
    $resolvedFfmpeg = (Get-Command $FfmpegPath -ErrorAction Stop).Source
    $resolvedFfprobe = (Get-Command $FfprobePath -ErrorAction Stop).Source
    $env:ICODER_E2E_FFMPEG_PATH = $resolvedFfmpeg
    $env:ICODER_TRANSCRIPTS_MEDIA_DECODER_PATH = $resolvedFfmpeg
    $env:ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH = $resolvedFfprobe
    $env:ICODER_ENVIRONMENT = "cn"
    $env:ICODER_REGION = "cn-local-e2e"
    $env:ICODER_SECRET_KEY = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    $keyBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($keyBytes)
    $env:ICODER_PHI_ENCRYPTION_KEY = [Convert]::ToBase64String($keyBytes).Replace("+", "-").Replace("/", "_")
    $env:NO_PROXY = "127.0.0.1,localhost"
    $env:no_proxy = $env:NO_PROXY

    Push-Location $backendRoot
    try {
        & $PythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Alembic failed for temporary dictation database." }
    }
    finally { Pop-Location }

    $port = Get-FreePort
    $baseUrl = "http://127.0.0.1:$port"
    $env:ICODER_E2E_BASE_URL = $baseUrl
    $server = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @(
            "-m", "uvicorn", "scripts.transcripts_dictation_e2e_app:app",
            "--host", "127.0.0.1", "--port", [string]$port, "--log-level", "warning"
        ) `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $serverOut `
        -RedirectStandardError $serverErr `
        -PassThru

    $ready = $false
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        if ($server.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 2
            if ($health.status -eq "healthy") { $ready = $true; break }
        }
        catch { }
        Start-Sleep -Milliseconds 250
    }
    if (-not $ready) {
        if (Test-Path -LiteralPath $serverErr) { Get-Content -LiteralPath $serverErr -Tail 80 }
        throw "Temporary dictation Uvicorn did not become ready."
    }

    $clientOutput = & $PythonPath (Join-Path $backendRoot "scripts\transcripts_dictation_e2e_client.py")
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path -LiteralPath $serverOut) {
            Write-Warning "Temporary Uvicorn stdout tail:"
            Get-Content -LiteralPath $serverOut -Tail 120
        }
        if (Test-Path -LiteralPath $serverErr) {
            Write-Warning "Temporary Uvicorn stderr tail:"
            Get-Content -LiteralPath $serverErr -Tail 120
        }
        throw "Dictation E2E client failed."
    }
    $result = $clientOutput | Select-Object -Last 1 | ConvertFrom-Json
    if ($result.status -ne "passed") { throw "Dictation E2E result was not passed." }

    $result | Add-Member -NotePropertyName "temporary_database" -NotePropertyValue $true
    $result | Add-Member -NotePropertyName "native_models_loaded" -NotePropertyValue $false
    $json = $result | ConvertTo-Json -Depth 8
    if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
        $resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
        $outputDirectory = Split-Path -Parent $resolvedOutput
        if (-not (Test-Path -LiteralPath $outputDirectory)) {
            New-Item -ItemType Directory -Path $outputDirectory | Out-Null
        }
        [System.IO.File]::WriteAllText($resolvedOutput, $json + [Environment]::NewLine)
    }
    Write-Output $json
}
finally {
    if ($server -ne $null -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
        $server.WaitForExit(10000) | Out-Null
    }
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], "Process")
    }
    $resolvedTaskTemp = [System.IO.Path]::GetFullPath($taskTemp)
    $requiredPrefix = $tempRoot.TrimEnd("\") + "\icoder-transcripts-dictation-e2e-"
    if ($resolvedTaskTemp.StartsWith($requiredPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedTaskTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
