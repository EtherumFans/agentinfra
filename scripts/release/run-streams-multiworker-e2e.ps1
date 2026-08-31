[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$backendRoot = Join-Path $repositoryRoot "backend"
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$taskTemp = Join-Path $tempRoot ("icoder-streams-multiworker-e2e-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $taskTemp | Out-Null
$databasePath = Join-Path $taskTemp "streams-multiworker.db"
$readyMarker = Join-Path $taskTemp "client.ready"
$resumeMarker = Join-Path $taskTemp "client.resume"
$clientResultPath = Join-Path $taskTemp "client-result.json"
$clientOut = Join-Path $taskTemp "client.out.log"
$clientErr = Join-Path $taskTemp "client.err.log"

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function Wait-Healthy([string]$BaseUrl, [System.Diagnostics.Process]$Process) {
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        $Process.Refresh()
        if ($Process.HasExited) { return $false }
        try {
            $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 2
            if ($health.status -eq "healthy") { return $true }
        }
        catch { }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

$primaryPort = Get-FreePort
$secondaryPort = Get-FreePort
$primaryBase = "http://127.0.0.1:$primaryPort"
$secondaryBase = "http://127.0.0.1:$secondaryPort"
$primary = $null
$secondary = $null
$client = $null
$environmentNames = @(
    "DATABASE_URL", "ICODER_DATABASE_URL", "APP_ENV", "SEED_ON_STARTUP", "ICODER_CREDENTIAL_LLM",
    "DEEPSEEK_API_KEY", "LLM_PROVIDER", "ICODER_ALLOW_EXTERNAL_LLM",
    "ICODER_DISABLE_NATIVE_MEDCODER", "ICODER_ENABLE_LOCAL_STT",
    "ICODER_MODEL_LIVE_CANARY_ENABLED", "ICODER_ALLOW_DEGRADED_NO_KEY",
    "ICODER_SECRET_KEY", "ICODER_ENVIRONMENT", "ICODER_REGION",
    "ICODER_PHI_ENCRYPTION_KEY",
    "ICODER_STREAM_LEASE_SECONDS", "ICODER_DISABLE_AUTH_FOR_TESTS",
    "ICODER_E2E_STREAMS_TENANT", "ICODER_E2E_STREAMS_TOKEN",
    "PYTHONPATH", "NO_PROXY", "no_proxy"
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
    $env:ICODER_STREAM_LEASE_SECONDS = "6"
    $env:ICODER_SECRET_KEY = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    $keyBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($keyBytes)
    $env:ICODER_PHI_ENCRYPTION_KEY = [Convert]::ToBase64String($keyBytes).Replace("+", "-").Replace("/", "_")
    $env:NO_PROXY = "127.0.0.1,localhost"
    $env:no_proxy = $env:NO_PROXY
    $env:PYTHONPATH = $backendRoot

    Push-Location $backendRoot
    try {
        & $PythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Alembic failed for temporary Streams lease database." }
    }
    finally { Pop-Location }

    $primary = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @(
            "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", [string]$primaryPort, "--log-level", "warning"
        ) `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $taskTemp "primary.out.log") `
        -RedirectStandardError (Join-Path $taskTemp "primary.err.log") `
        -PassThru
    if (-not (Wait-Healthy -BaseUrl $primaryBase -Process $primary)) {
        throw "Primary Streams worker did not become ready."
    }

    $secondary = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @(
            "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", [string]$secondaryPort, "--log-level", "warning"
        ) `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $taskTemp "secondary.out.log") `
        -RedirectStandardError (Join-Path $taskTemp "secondary.err.log") `
        -PassThru
    if (-not (Wait-Healthy -BaseUrl $secondaryBase -Process $secondary)) {
        throw "Secondary Streams worker did not become ready."
    }

    $suffix = [guid]::NewGuid().ToString("N")
    $registration = Invoke-RestMethod `
        -Method Post `
        -Uri "$primaryBase/api/auth/register" `
        -ContentType "application/json" `
        -Body (@{
            username = "streams_lease_$suffix"
            email = "streams-lease-$suffix@icoder.ai"
            password = "Streams-Lease-$suffix!"
            full_name = "Streams Lease E2E"
            organization_name = "Streams Lease $suffix"
        } | ConvertTo-Json -Compress) `
        -TimeoutSec 15
    if ([string]::IsNullOrWhiteSpace($registration.access_token)) {
        throw "Registration did not return an access token."
    }
    $interactionId = [guid]::NewGuid().ToString()
    $env:ICODER_E2E_STREAMS_TENANT = $registration.organizations[0].slug
    $env:ICODER_E2E_STREAMS_TOKEN = $registration.access_token

    $client = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @(
            (Join-Path $backendRoot "scripts\streams_lease_e2e_client.py"),
            "--primary", $primaryBase,
            "--secondary", $secondaryBase,
            "--interaction-id", $interactionId,
            "--ready", $readyMarker,
            "--resume", $resumeMarker,
            "--output", $clientResultPath
        ) `
        -WorkingDirectory $backendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $clientOut `
        -RedirectStandardError $clientErr `
        -PassThru

    $readyDeadline = (Get-Date).AddSeconds(30)
    while (-not (Test-Path -LiteralPath $readyMarker) -and (Get-Date) -lt $readyDeadline) {
        $client.Refresh()
        if ($client.HasExited) { break }
        Start-Sleep -Milliseconds 100
    }
    if (-not (Test-Path -LiteralPath $readyMarker)) {
        if (Test-Path $clientErr) { Get-Content $clientErr -Tail 60 }
        throw "Streams lease client did not establish the conflict scenario."
    }

    $leaseCountBeforeCrash = & $PythonPath -c (
        "import sqlite3; db=sqlite3.connect(r'$databasePath'); " +
        "print(db.execute('select count(*) from stt_stream_leases').fetchone()[0]); db.close()"
    )
    if ([int]$leaseCountBeforeCrash -ne 1) {
        throw "Expected exactly one active lease before crash."
    }

    Stop-Process -Id $primary.Id -Force
    Wait-Process -Id $primary.Id -Timeout 10 -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 8
    [System.IO.File]::WriteAllText($resumeMarker, "resume`n")

    if (-not $client.WaitForExit(30000)) {
        throw "Streams lease recovery client timed out."
    }
    if ($client.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $clientResultPath)) {
        if (Test-Path $clientErr) { Get-Content $clientErr -Tail 60 }
        throw "Streams lease recovery client failed."
    }
    $clientEvidence = Get-Content -LiteralPath $clientResultPath -Raw | ConvertFrom-Json
    if (
        -not $clientEvidence.conflict_rejected -or
        -not $clientEvidence.crash_recovered -or
        -not $clientEvidence.session_fence_rotated -or
        $clientEvidence.checkpointed_audio_bytes -ne 640
    ) {
        throw "Streams cross-worker lease evidence was incomplete."
    }

    $databaseScript = @'
import json, os, sqlite3
db = sqlite3.connect(os.environ["ICODER_STREAMS_LEASE_E2E_DB"])
try:
    print(json.dumps({
        "remaining_leases": db.execute("select count(*) from stt_stream_leases").fetchone()[0],
        "remaining_checkpoints": db.execute("select count(*) from stt_stream_checkpoints").fetchone()[0],
        "remaining_checkpoint_chunks": db.execute("select count(*) from stt_stream_checkpoint_chunks").fetchone()[0],
        "recording_count": db.execute("select count(*) from stt_recordings").fetchone()[0],
        "recording_bytes": db.execute("select coalesce(sum(byte_length), 0) from stt_recordings").fetchone()[0],
        "configured_audits": db.execute("select count(*) from audit_logs where action='stt.stream.configured'").fetchone()[0],
        "ended_audits": db.execute("select count(*) from audit_logs where action='stt.stream.ended'").fetchone()[0],
    }, sort_keys=True))
finally:
    db.close()
'@
    $env:ICODER_STREAMS_LEASE_E2E_DB = $databasePath
    $databaseEvidence = & $PythonPath -c $databaseScript | Select-Object -Last 1 | ConvertFrom-Json
    Remove-Item Env:ICODER_STREAMS_LEASE_E2E_DB -ErrorAction SilentlyContinue
    if (
        $databaseEvidence.remaining_leases -ne 0 -or
        $databaseEvidence.remaining_checkpoints -ne 0 -or
        $databaseEvidence.remaining_checkpoint_chunks -ne 0 -or
        $databaseEvidence.recording_count -ne 1 -or
        $databaseEvidence.recording_bytes -ne 640 -or
        $databaseEvidence.configured_audits -ne 2 -or
        $databaseEvidence.ended_audits -ne 1
    ) {
        throw "Streams lease persistence evidence did not match crash recovery semantics."
    }
    $secondary.Refresh()
    if ($secondary.HasExited) { throw "Secondary worker exited during recovery." }

    $evidence = [ordered]@{
        schema_version = "icoder.streams-multiworker-e2e/v2"
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        status = "passed"
        transport = "real_loopback_websocket"
        api_processes = 2
        shared_database = "temporary_sqlite_wal"
        lease_seconds = 6
        duplicate_rejected_across_workers = $true
        primary_worker_crashed_forcefully = $true
        stale_lease_recovered_by_secondary = $true
        session_fence_rotated = $true
        retained_audio_checkpoint_recovered = $true
        checkpoint_configuration_fenced = $true
        checkpoint_encryption_required = $true
        checkpoint_rows_removed_after_end = $true
        database = $databaseEvidence
        authenticated_tenant_token = $true
        real_audio_used = $false
        real_stt_engine_used = $false
        real_llm_used = $false
        clinical_payload_captured = $false
        temporary_database = "created_migrated_removed"
    }
    $evidenceJson = $evidence | ConvertTo-Json -Depth 6
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
    foreach ($process in @($client, $primary, $secondary)) {
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
    Remove-Item Env:ICODER_STREAMS_LEASE_E2E_DB -ErrorAction SilentlyContinue
    $resolvedTemp = [System.IO.Path]::GetFullPath($taskTemp)
    $tempLeaf = Split-Path $resolvedTemp -Leaf
    if (
        $resolvedTemp.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        $tempLeaf -like "icoder-streams-multiworker-e2e-*"
    ) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    } else {
        throw "Refusing to clean unexpected Streams lease E2E temp path: $resolvedTemp"
    }
}
