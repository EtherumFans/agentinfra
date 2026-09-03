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
$taskTemp = Join-Path $tempRoot ("icoder-streams-e2e-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $taskTemp | Out-Null
$databasePath = Join-Path $taskTemp "streams.db"
$serverOut = Join-Path $taskTemp "uvicorn.out.log"
$serverErr = Join-Path $taskTemp "uvicorn.err.log"
$audioPath = Join-Path $taskTemp "synthetic-silence.ogg"

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

$serverPort = Get-FreePort
$baseUrl = "http://127.0.0.1:$serverPort"
$server = $null
$environmentNames = @(
    "DATABASE_URL", "ICODER_DATABASE_URL", "APP_ENV", "SEED_ON_STARTUP", "ICODER_CREDENTIAL_LLM",
    "DEEPSEEK_API_KEY", "LLM_PROVIDER", "ICODER_ALLOW_EXTERNAL_LLM",
    "ICODER_DISABLE_NATIVE_MEDCODER", "ICODER_ENABLE_LOCAL_STT",
    "ICODER_STREAM_MEDIA_VALIDATION_MODE", "ICODER_STREAM_MEDIA_DECODER_PATH",
    "ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS",
    "ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY",
    "ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS",
    "ICODER_MODEL_LIVE_CANARY_ENABLED", "ICODER_ALLOW_DEGRADED_NO_KEY",
    "ICODER_SECRET_KEY", "ICODER_ENVIRONMENT", "ICODER_REGION",
    "ICODER_PHI_ENCRYPTION_KEY",
    "ICODER_E2E_STREAMS_BASE_URL", "ICODER_E2E_ACCESS_TOKEN",
    "ICODER_E2E_TENANT_NAME", "ICODER_E2E_STREAMS_AUDIO_PATH",
    "PYTHONPATH", "NO_PROXY", "no_proxy",
    "NUGET_PACKAGES", "ICODER_DISABLE_AUTH_FOR_TESTS"
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
    $env:DATABASE_URL = "sqlite+aiosqlite:///" + $databasePath.Replace("\", "/")
    $env:ICODER_DATABASE_URL = $env:DATABASE_URL
    $env:APP_ENV = "local"
    $env:SEED_ON_STARTUP = "0"
    Remove-Item Env:ICODER_CREDENTIAL_LLM -ErrorAction SilentlyContinue
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:ICODER_DISABLE_AUTH_FOR_TESTS -ErrorAction SilentlyContinue
    $env:LLM_PROVIDER = "mock"
    $env:ICODER_ALLOW_EXTERNAL_LLM = "false"
    $env:ICODER_DISABLE_NATIVE_MEDCODER = "true"
    $env:ICODER_ENABLE_LOCAL_STT = "false"
    $env:ICODER_MODEL_LIVE_CANARY_ENABLED = "false"
    $env:ICODER_ALLOW_DEGRADED_NO_KEY = "1"
    $env:ICODER_ENVIRONMENT = "cn"
    $env:ICODER_REGION = "cn-local-e2e"
    $env:ICODER_SECRET_KEY = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    $keyBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($keyBytes)
    $env:ICODER_PHI_ENCRYPTION_KEY = [Convert]::ToBase64String($keyBytes).Replace("+", "-").Replace("/", "_")
    $env:NO_PROXY = "127.0.0.1,localhost"
    $env:no_proxy = $env:NO_PROXY
    $env:NUGET_PACKAGES = "C:\codex-tools\nuget-packages"

    $ffmpegPath = (& $PythonPath -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" | Select-Object -Last 1).Trim()
    if ([string]::IsNullOrWhiteSpace($ffmpegPath) -or -not (Test-Path -LiteralPath $ffmpegPath)) {
        throw "Bundled ffmpeg executable was not found."
    }
    & $ffmpegPath -hide_banner -loglevel error -f lavfi -i "anullsrc=r=16000:cl=mono" `
        -t 0.25 -c:a libopus -f ogg -y $audioPath
    if ($LASTEXITCODE -ne 0) { throw "Synthetic silent Ogg/Opus generation failed." }
    $audioBytes = [System.IO.File]::ReadAllBytes($audioPath)
    if (
        $audioBytes.Length -lt 64 -or $audioBytes.Length -gt 64000 -or
        [System.Text.Encoding]::ASCII.GetString($audioBytes, 0, 4) -ne "OggS"
    ) {
        throw "Generated Streams fixture is not a bounded Ogg container."
    }
    $env:ICODER_STREAM_MEDIA_VALIDATION_MODE = "decoder"
    $env:ICODER_STREAM_MEDIA_DECODER_PATH = $ffmpegPath
    $env:ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS = "3"
    $env:ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY = "2"
    $env:ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS = "0.5"

    Push-Location $backendRoot
    try {
        & $PythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Alembic failed for temporary Streams database." }
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
        throw "Temporary Streams Uvicorn did not become ready."
    }

    $suffix = [guid]::NewGuid().ToString("N")
    $registration = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/api/auth/register" `
        -ContentType "application/json" `
        -Body (@{
            username = "streams_$suffix"
            email = "streams-$suffix@icoder.ai"
            password = "Streams-$suffix!"
            full_name = "Streams E2E"
            organization_name = "Streams E2E $suffix"
        } | ConvertTo-Json -Compress) `
        -TimeoutSec 15
    if ([string]::IsNullOrWhiteSpace($registration.access_token)) {
        throw "Registration did not return a tenant-bound access token."
    }
    if ($registration.organizations.Count -ne 1) {
        throw "Registration did not return exactly one organization."
    }

    $env:ICODER_E2E_STREAMS_BASE_URL = $baseUrl
    $env:ICODER_E2E_ACCESS_TOKEN = $registration.access_token
    $env:ICODER_E2E_TENANT_NAME = $registration.organizations[0].slug
    $env:ICODER_E2E_STREAMS_AUDIO_PATH = $audioPath

    $javascriptRoot = Join-Path $repositoryRoot "packages\icoder-sdk"
    & $NpmPath --prefix $javascriptRoot run build
    if ($LASTEXITCODE -ne 0) { throw "JavaScript SDK build failed." }
    $javascriptOutput = & $NodePath (Join-Path $javascriptRoot "examples\streams-smoke.mjs")
    if ($LASTEXITCODE -ne 0) { throw "JavaScript Streams smoke failed." }
    $javascriptResult = $javascriptOutput | Select-Object -Last 1 | ConvertFrom-Json

    $pythonRoot = Join-Path $repositoryRoot "packages\icoder-python"
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($previousEnvironment["PYTHONPATH"])) {
        $pythonRoot
    } else {
        "$pythonRoot$([System.IO.Path]::PathSeparator)$($previousEnvironment['PYTHONPATH'])"
    }
    $pythonOutput = & $PythonPath (Join-Path $pythonRoot "examples\streams_smoke.py")
    if ($LASTEXITCODE -ne 0) { throw "Python Streams smoke failed." }
    $pythonResult = $pythonOutput | Select-Object -Last 1 | ConvertFrom-Json

    $dotnetProject = Join-Path $repositoryRoot (
        "packages\icoder-dotnet\examples\Icoder.Sdk.StreamsSmoke\" +
        "Icoder.Sdk.StreamsSmoke.csproj"
    )
    $dotnetOutput = & $DotnetPath run --project $dotnetProject -c Release
    if ($LASTEXITCODE -ne 0) { throw ".NET Streams smoke failed." }
    $dotnetResult = $dotnetOutput | Select-Object -Last 1 | ConvertFrom-Json

    $malformedClient = Join-Path $backendRoot "scripts\streams_malformed_media_e2e_client.py"
    $malformedOutput = & $PythonPath $malformedClient
    if ($LASTEXITCODE -ne 0) { throw "Malformed Streams media E2E failed." }
    $malformedResult = $malformedOutput | Select-Object -Last 1 | ConvertFrom-Json

    $audioEventsClient = Join-Path $backendRoot "scripts\streams_pcm_audio_events_e2e_client.py"
    $audioEventsOutput = & $PythonPath $audioEventsClient
    if ($LASTEXITCODE -ne 0) { throw "PCM audio events Streams E2E failed." }
    $audioEventsResult = $audioEventsOutput | Select-Object -Last 1 | ConvertFrom-Json

    $multichannelClient = Join-Path $backendRoot "scripts\streams_multichannel_e2e_client.py"
    $multichannelOutput = & $PythonPath $multichannelClient
    if ($LASTEXITCODE -ne 0) { throw "Multichannel Streams E2E failed." }
    $multichannelResult = $multichannelOutput | Select-Object -Last 1 | ConvertFrom-Json

    $decoderHealth = (Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 15).stream_media_decoder
    if (
        $decoderHealth.schema -ne "icoder/stream-media-decoder-health/v1" -or
        $decoderHealth.attempts -ne 6 -or
        $decoderHealth.valid -ne 5 -or
        $decoderHealth.invalid -ne 1 -or
        $decoderHealth.active -ne 0 -or
        $decoderHealth.busy -ne 0 -or
        $decoderHealth.timeout -ne 0 -or
        $decoderHealth.unavailable -ne 0
    ) {
        throw "Streams decoder health counters do not match the six E2E decode attempts."
    }

    $headers = @{ Authorization = "Bearer $($registration.access_token)" }
    $recordings = Invoke-RestMethod `
        -Headers $headers `
        -Uri "$baseUrl/api/v2/tools/interactions/$($javascriptResult.interaction_id)/recordings" `
        -TimeoutSec 15
    if ($recordings.recordings.Count -ne 1) {
        throw "Retain-mode Streams session did not persist exactly one encrypted recording."
    }

    $countScript = @'
import json, os, sqlite3
path = os.environ["ICODER_E2E_STREAMS_DB"]
db = sqlite3.connect(path)
try:
    result = {
        "stt_interactions": db.execute("select count(*) from stt_interactions").fetchone()[0],
        "stt_recordings": db.execute("select count(*) from stt_recordings").fetchone()[0],
        "stt_transcripts": db.execute("select count(*) from stt_transcripts").fetchone()[0],
        "clinical_facts": db.execute("select count(*) from clinical_facts").fetchone()[0],
        "remaining_stream_leases": db.execute("select count(*) from stt_stream_leases").fetchone()[0],
        "configured_audits": db.execute("select count(*) from audit_logs where action='stt.stream.configured'").fetchone()[0],
        "ended_audits": db.execute("select count(*) from audit_logs where action='stt.stream.ended'").fetchone()[0],
        "audio_event_audits": db.execute("select count(*) from audit_logs where action='stt.stream.audio_event'").fetchone()[0],
    }
    rows = db.execute("select details from audit_logs where action='stt.stream.audio_event'").fetchall()
    allowed = {
        "session_id", "token_type", "audio_bytes", "audio_chunks", "event",
        "channel", "start_time_ms", "audio_event_count",
    }
    result["audio_event_audits_content_free"] = len(rows) == 5 and all(
        set(json.loads(row[0] or "{}")).issubset(allowed) for row in rows
    )
    print(json.dumps(result, sort_keys=True))
finally:
    db.close()
'@
    $env:ICODER_E2E_STREAMS_DB = $databasePath
    $databaseEvidence = & $PythonPath -c $countScript | Select-Object -Last 1 | ConvertFrom-Json
    Remove-Item Env:ICODER_E2E_STREAMS_DB -ErrorAction SilentlyContinue
    if (
        $databaseEvidence.stt_interactions -ne 2 -or
        $databaseEvidence.stt_recordings -ne 1 -or
        $databaseEvidence.stt_transcripts -ne 0 -or
        $databaseEvidence.clinical_facts -ne 0 -or
        $databaseEvidence.remaining_stream_leases -ne 0 -or
        $databaseEvidence.configured_audits -ne 6 -or
        $databaseEvidence.ended_audits -ne 5 -or
        $databaseEvidence.audio_event_audits -ne 5 -or
        -not $databaseEvidence.audio_event_audits_content_free
    ) {
        $observedEvidence = $databaseEvidence | ConvertTo-Json -Compress
        throw "Streams persistence or audit evidence did not match the expected fail-closed run: $observedEvidence"
    }
    if ($server.HasExited) { throw "Backend exited during Streams E2E." }

    $evidence = [ordered]@{
        schema_version = "icoder.sdk-streams-e2e/v1"
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        status = "passed"
        transport = "real_loopback_websocket"
        api_processes = 1
        sdk_executions = @($javascriptResult, $pythonResult, $dotnetResult)
        malformed_media_execution = $malformedResult
        pcm_audio_events_execution = $audioEventsResult
        multichannel_execution = $multichannelResult
        decoder_health = $decoderHealth
        authenticated_tenant_token = $true
        environment = "cn"
        persistence = $databaseEvidence
        retained_recording_retrieved_through_tenant_api = $true
        temporary_database = "created_migrated_removed"
        synthetic_generated_silence_ogg_opus = $true
        audio_container_validated = $true
        isolated_decoder_validation = $true
        decoder_audio_frames = 1
        decoder_output_discarded = $true
        real_patient_audio_used = $false
        real_stt_engine_used = $false
        real_llm_used = $false
        clinical_payload_captured = $false
        invented_credits = $false
    }
    $evidenceJson = $evidence | ConvertTo-Json -Depth 8
    if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
        $resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
        New-Item -ItemType Directory -Path (Split-Path $resolvedOutput -Parent) -Force | Out-Null
        [System.IO.File]::WriteAllText(
            $resolvedOutput,
            $evidenceJson + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
    $evidenceJson
}
finally {
    if ($null -ne $server) {
        $server.Refresh()
        if (-not $server.HasExited) {
            Stop-Process -Id $server.Id -Force
            Wait-Process -Id $server.Id -Timeout 10 -ErrorAction SilentlyContinue
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
    Remove-Item Env:ICODER_E2E_STREAMS_DB -ErrorAction SilentlyContinue
    $resolvedTemp = [System.IO.Path]::GetFullPath($taskTemp)
    $tempLeaf = Split-Path $resolvedTemp -Leaf
    if (
        $resolvedTemp.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        $tempLeaf -like "icoder-streams-e2e-*"
    ) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    } else {
        throw "Refusing to clean unexpected Streams E2E temp path: $resolvedTemp"
    }
}
