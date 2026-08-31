[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$NodePath = "node",
    [string]$NpmPath = "npm.cmd",
    [string]$DotnetPath = "C:\codex-tools\dotnet\dotnet.exe",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$backendRoot = Join-Path $repositoryRoot "backend"
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$taskTemp = Join-Path $tempRoot ("icoder-stt-recovery-e2e-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $taskTemp | Out-Null
$databasePath = Join-Path $taskTemp "stt-recovery.db"
$serverOut = Join-Path $taskTemp "uvicorn.out.log"
$serverErr = Join-Path $taskTemp "uvicorn.err.log"
$secondaryServerOut = Join-Path $taskTemp "uvicorn-secondary.out.log"
$secondaryServerErr = Join-Path $taskTemp "uvicorn-secondary.err.log"
$proxyOut = Join-Path $taskTemp "proxy.out.log"
$proxyErr = Join-Path $taskTemp "proxy.err.log"
$proxyMetrics = Join-Path $taskTemp "proxy.metrics.json"

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        0
    )
    $listener.Start()
    try { return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function Wait-TcpPort([int]$Port, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $task = $client.ConnectAsync("127.0.0.1", $Port)
            if ($task.Wait(500) -and $client.Connected) { return $true }
        }
        catch { }
        finally { $client.Dispose() }
        Start-Sleep -Milliseconds 100
    }
    return $false
}

$serverPort = Get-FreePort
$secondaryServerPort = Get-FreePort
$proxyPort = Get-FreePort
$baseUrl = "http://127.0.0.1:$serverPort"
$proxyBaseUrl = "http://127.0.0.1:$proxyPort"
$server = $null
$secondaryServer = $null
$proxy = $null
$environmentNames = @(
    "DATABASE_URL", "APP_ENV", "SEED_ON_STARTUP", "ICODER_CREDENTIAL_LLM",
    "DEEPSEEK_API_KEY", "LLM_PROVIDER", "ICODER_ALLOW_EXTERNAL_LLM",
    "ICODER_DISABLE_NATIVE_MEDCODER", "ICODER_ENABLE_LOCAL_STT",
    "ICODER_MODEL_LIVE_CANARY_ENABLED", "ICODER_ALLOW_DEGRADED_NO_KEY",
    "ICODER_SECRET_KEY", "ICODER_E2E_STT_BASE_URL", "ICODER_E2E_ACCESS_TOKEN",
    "PYTHONPATH", "NO_PROXY", "no_proxy", "NUGET_PACKAGES"
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
    $env:DATABASE_URL = "sqlite+aiosqlite:///" + $databasePath.Replace("\", "/")
    $env:APP_ENV = "local"
    $env:SEED_ON_STARTUP = "0"
    Remove-Item Env:ICODER_CREDENTIAL_LLM -ErrorAction SilentlyContinue
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    $env:LLM_PROVIDER = "mock"
    $env:ICODER_ALLOW_EXTERNAL_LLM = "false"
    $env:ICODER_DISABLE_NATIVE_MEDCODER = "true"
    $env:ICODER_ENABLE_LOCAL_STT = "false"
    $env:ICODER_MODEL_LIVE_CANARY_ENABLED = "false"
    $env:ICODER_ALLOW_DEGRADED_NO_KEY = "1"
    $env:ICODER_SECRET_KEY = (
        [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    )
    $env:NO_PROXY = "127.0.0.1,localhost"
    $env:no_proxy = $env:NO_PROXY
    $env:NUGET_PACKAGES = "C:\codex-tools\nuget-packages"

    Push-Location $backendRoot
    try {
        & $PythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Alembic failed for temporary STT database." }
    }
    finally { Pop-Location }

    $server = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @(
            "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", [string]$serverPort, "--log-level", "warning"
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
        if (Test-Path $serverErr) { Get-Content $serverErr -Tail 80 }
        throw "Temporary Uvicorn did not become ready."
    }

    $secondaryServer = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @(
            "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", [string]$secondaryServerPort, "--log-level", "warning"
        ) `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $secondaryServerOut `
        -RedirectStandardError $secondaryServerErr `
        -PassThru
    $secondaryReady = $false
    $secondaryDeadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $secondaryDeadline) {
        if ($secondaryServer.HasExited) { break }
        try {
            $secondaryHealth = Invoke-RestMethod `
                -Uri "http://127.0.0.1:$secondaryServerPort/api/health" `
                -TimeoutSec 2
            if ($secondaryHealth.status -eq "healthy") {
                $secondaryReady = $true
                break
            }
        }
        catch { }
        Start-Sleep -Milliseconds 250
    }
    if (-not $secondaryReady) {
        if (Test-Path $secondaryServerErr) { Get-Content $secondaryServerErr -Tail 80 }
        throw "Secondary temporary Uvicorn did not become ready."
    }

    $suffix = [guid]::NewGuid().ToString("N")
    $registration = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/api/auth/register" `
        -ContentType "application/json" `
        -Body (@{
            username = "stt_$suffix"
            email = "stt-$suffix@icoder.ai"
            password = "Stt-$suffix!"
            full_name = "STT Recovery E2E"
            organization_name = "STT Recovery $suffix"
        } | ConvertTo-Json -Compress) `
        -TimeoutSec 15
    if ([string]::IsNullOrWhiteSpace($registration.access_token)) {
        throw "Registration did not return a tenant-bound access token."
    }

    $proxy = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @(
            "-m", "scripts.sdk_stt_fault_proxy",
            "--upstream", "ws://127.0.0.1:$serverPort",
            "--upstream", "ws://127.0.0.1:$secondaryServerPort",
            "--port", [string]$proxyPort,
            "--metrics-file", $proxyMetrics
        ) `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $proxyOut `
        -RedirectStandardError $proxyErr `
        -PassThru
    if (-not (Wait-TcpPort -Port $proxyPort -Seconds 20)) {
        if (Test-Path $proxyErr) { Get-Content $proxyErr -Tail 80 }
        throw "STT fault proxy did not start."
    }

    $env:ICODER_E2E_STT_BASE_URL = $proxyBaseUrl
    $env:ICODER_E2E_ACCESS_TOKEN = $registration.access_token

    $javascriptRoot = Join-Path $repositoryRoot "packages\icoder-sdk"
    & $NpmPath --prefix $javascriptRoot run build
    if ($LASTEXITCODE -ne 0) { throw "JavaScript SDK build failed." }
    $javascriptResult = & $NodePath (
        Join-Path $javascriptRoot "examples\realtime-stt-recovery-smoke.mjs"
    )
    if ($LASTEXITCODE -ne 0) { throw "JavaScript STT recovery smoke failed." }

    $pythonRoot = Join-Path $repositoryRoot "packages\icoder-python"
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($previousEnvironment["PYTHONPATH"])) {
        $pythonRoot
    } else {
        "$pythonRoot$([System.IO.Path]::PathSeparator)$($previousEnvironment['PYTHONPATH'])"
    }
    $pythonResult = & $PythonPath (
        Join-Path $pythonRoot "examples\realtime_stt_recovery_smoke.py"
    )
    if ($LASTEXITCODE -ne 0) { throw "Python STT recovery smoke failed." }

    $dotnetProject = Join-Path $repositoryRoot (
        "packages\icoder-dotnet\examples\Icoder.Sdk.SttRecoverySmoke\" +
        "Icoder.Sdk.SttRecoverySmoke.csproj"
    )
    $dotnetOutput = & $DotnetPath run --project $dotnetProject -c Release
    if ($LASTEXITCODE -ne 0) { throw ".NET STT recovery smoke failed." }
    $dotnetResult = $dotnetOutput | Select-Object -Last 1

    $metricsDeadline = (Get-Date).AddSeconds(5)
    do {
        if (Test-Path $proxyMetrics) {
            $metrics = Get-Content -LiteralPath $proxyMetrics -Raw | ConvertFrom-Json
            if ($metrics.unique_sessions -ge 3 -and $metrics.forced_disconnects -ge 3) { break }
        }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $metricsDeadline)
    if (
        $metrics.unique_sessions -ne 3 -or
        $metrics.forced_disconnects -ne 3 -or
        $metrics.sessions_with_reconnect -ne 3 -or
        $metrics.total_resume_connections -ne 6
    ) {
        throw "Fault proxy metrics did not prove all three SDK smoke executions."
    }
    if ($server.HasExited -or $secondaryServer.HasExited -or $proxy.HasExited) {
        throw "Backend or fault proxy exited during recovery testing."
    }

    $evidence = [ordered]@{
        schema_version = "icoder.sdk-stt-recovery-e2e/v1"
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        status = "passed"
        transport = "real_loopback_websocket"
        api_processes = 2
        proxy_upstream_policy = "round_robin_across_independent_api_processes"
        fault = "close_after_sequence_1_ack"
        resume_protocol = "icoder.stt-resume.v1"
        resume_mode = "client_replay"
        sdk_executions = @(
            ($javascriptResult | Select-Object -Last 1 | ConvertFrom-Json),
            ($pythonResult | Select-Object -Last 1 | ConvertFrom-Json),
            ($dotnetResult | ConvertFrom-Json)
        )
        proxy = $metrics
        authenticated_tenant_token = $true
        temporary_database = "created_migrated_removed"
        synthetic_non_audio_bytes_only = $true
        real_stt_engine_used = $false
        real_llm_used = $false
        clinical_payload_captured = $false
    }
    $evidenceJson = $evidence | ConvertTo-Json -Depth 8
    if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
        $resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
        $outputParent = Split-Path $resolvedOutput -Parent
        New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
        [System.IO.File]::WriteAllText(
            $resolvedOutput,
            $evidenceJson + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
    $evidenceJson
}
finally {
    foreach ($process in @($proxy, $secondaryServer, $server)) {
        if ($null -ne $process) {
            $process.Refresh()
            if (-not $process.HasExited) {
                Stop-Process -Id $process.Id -Force
                Wait-Process -Id $process.Id -Timeout 10 -ErrorAction SilentlyContinue
            }
        }
    }
    foreach ($name in $environmentNames) {
        $value = $previousEnvironment[$name]
        if ($null -eq $value) {
            [Environment]::SetEnvironmentVariable($name, $null, "Process")
        } else {
            [Environment]::SetEnvironmentVariable($name, [string]$value, "Process")
        }
    }
    $resolvedTemp = [System.IO.Path]::GetFullPath($taskTemp)
    $tempLeaf = Split-Path $resolvedTemp -Leaf
    if (
        $resolvedTemp.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        $tempLeaf -like "icoder-stt-recovery-e2e-*"
    ) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    } else {
        throw "Refusing to clean unexpected STT E2E temp path: $resolvedTemp"
    }
}
