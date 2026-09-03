param(
    [string]$DotnetPath = "dotnet",
    [string]$PythonPath = "python",
    [string]$NodePath = "node",
    [string]$NpmPath = "npm",
    [string]$BackendPath = "",
    [string]$OutputPath = "",
    [switch]$CrossWorkerSse,
    [switch]$SkipDotNet
)

$ErrorActionPreference = "Stop"

# Windows PowerShell can resolve `npm` to npm.ps1 and misparse arguments when
# that wrapper is invoked indirectly. Prefer the native command shim unless
# the caller supplied an explicit executable path.
if ($env:OS -eq "Windows_NT" -and $NpmPath -eq "npm") {
    $npmCommand = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($null -ne $npmCommand) {
        $NpmPath = $npmCommand.Source
    }
}

$packageRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $packageRoot "..\.."))
if ([string]::IsNullOrWhiteSpace($BackendPath)) {
    $BackendPath = [System.IO.Path]::GetFullPath((Join-Path $packageRoot "..\..\backend"))
}

$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$taskTemp = Join-Path $tempRoot ("icoder-dotnet-e2e-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $taskTemp | Out-Null
$stdoutPath = Join-Path $taskTemp "uvicorn.out.log"
$stderrPath = Join-Path $taskTemp "uvicorn.err.log"
$databasePath = Join-Path $taskTemp "sdk-e2e.db"

$listener = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback,
    0
)
$listener.Start()
$port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()
$baseUrl = "http://127.0.0.1:$port"
$proxyListener = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback,
    0
)
$proxyListener.Start()
$proxyPort = ([System.Net.IPEndPoint]$proxyListener.LocalEndpoint).Port
$proxyListener.Stop()
$sseBaseUrl = "http://127.0.0.1:$proxyPort"
$secondaryPort = $null
$secondaryBaseUrl = $null
if ($CrossWorkerSse) {
    $secondaryListener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        0
    )
    $secondaryListener.Start()
    $secondaryPort = ([System.Net.IPEndPoint]$secondaryListener.LocalEndpoint).Port
    $secondaryListener.Stop()
    $secondaryBaseUrl = "http://127.0.0.1:$secondaryPort"
}
$server = $null
$secondaryServer = $null
$faultProxy = $null
$fixtureFinishers = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$previousPythonPath = $env:PYTHONPATH
$previousSecretKey = $env:ICODER_SECRET_KEY
$previousMetricsToken = $env:ICODER_METRICS_BEARER_TOKEN
$previousLlmCredential = $env:ICODER_CREDENTIAL_LLM
$previousDeepSeekKey = $env:DEEPSEEK_API_KEY
$previousExternalLlm = $env:ICODER_ALLOW_EXTERNAL_LLM
$previousDisableNativeMedcoder = $env:ICODER_DISABLE_NATIVE_MEDCODER
$previousLocalStt = $env:ICODER_ENABLE_LOCAL_STT
$previousLiveCanary = $env:ICODER_MODEL_LIVE_CANARY_ENABLED

function Start-LongSseFixture([string]$label, [string]$organizationId) {
    $runId = "sdk-sse-$label-$([guid]::NewGuid().ToString('N'))"
    Push-Location $BackendPath
    try {
        $seedOutput = & $PythonPath -m scripts.sdk_sse_fixture seed `
            --run-id $runId `
            --organization-id $organizationId `
            --expired
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to seed the $label long SSE fixture."
        }
    }
    finally {
        Pop-Location
    }
    $fixture = ($seedOutput | Select-Object -Last 1) | ConvertFrom-Json
    $finishStdout = Join-Path $taskTemp "$label-sse-finish.out.log"
    $finishStderr = Join-Path $taskTemp "$label-sse-finish.err.log"
    $finisher = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @(
            "-m", "scripts.sdk_sse_fixture", "finish",
            "--run-id", $runId,
            "--organization-id", $organizationId,
            "--delay-seconds", "1.25"
        ) `
        -WorkingDirectory $BackendPath `
        -WindowStyle Hidden `
        -RedirectStandardOutput $finishStdout `
        -RedirectStandardError $finishStderr `
        -PassThru
    $fixtureFinishers.Add($finisher)
    $env:ICODER_E2E_SSE_RUN_ID = $fixture.run_id
    $env:ICODER_E2E_SSE_TRACE_TOKEN = $fixture.trace_token
    return [pscustomobject]@{
        Process = $finisher
        OutputLog = $finishStdout
        ErrorLog = $finishStderr
    }
}

function Complete-LongSseFixture($fixture, [string]$label) {
    $exited = $fixture.Process.WaitForExit(30000)
    $fixture.Process.Refresh()
    $exitCode = $fixture.Process.ExitCode
    # Windows PowerShell can expose a blank ExitCode for an already-exited
    # Start-Process object with redirected streams. Treat blank as unknown;
    # the SDK has independently verified the fixture's terminal DB effect.
    if (-not $exited -or (
        -not [string]::IsNullOrWhiteSpace([string]$exitCode) -and
        [int]$exitCode -ne 0
    )) {
        Write-Output "$label SSE fixture exited=$exited code=$exitCode"
        if (Test-Path $fixture.OutputLog) {
            Get-Content $fixture.OutputLog -Tail 40
        }
        if (Test-Path $fixture.ErrorLog) {
            Get-Content $fixture.ErrorLog -Tail 40
        }
        throw "The $label long SSE fixture did not finish successfully."
    }
}

try {
    $env:DATABASE_URL = "sqlite+aiosqlite:///" + $databasePath.Replace("\", "/")
    $env:APP_ENV = "local"
    $env:SEED_ON_STARTUP = "0"
    Remove-Item Env:ICODER_CREDENTIAL_LLM -ErrorAction SilentlyContinue
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    $env:ICODER_ALLOW_EXTERNAL_LLM = "false"
    $env:ICODER_DISABLE_NATIVE_MEDCODER = "true"
    $env:ICODER_ENABLE_LOCAL_STT = "false"
    $env:ICODER_MODEL_LIVE_CANARY_ENABLED = "false"
    $env:ICODER_ALLOW_DEGRADED_NO_KEY = "1"
    $env:MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE = ""
    $env:ICODER_ALLOW_UNSAFE_WINDOWS_SENTENCE_TRANSFORMERS = ""
    $env:LLM_PROVIDER = "mock"
    $env:RUNTRACE_STORE = "db"
    # Independent API processes must share signing material. This value is
    # ephemeral to the child processes and is restored in finally.
    $env:ICODER_SECRET_KEY = (
        [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    )
    $env:ICODER_METRICS_BEARER_TOKEN = (
        [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    )
    $env:DOTNET_CLI_TELEMETRY_OPTOUT = "1"
    $env:DOTNET_NOLOGO = "1"

    Push-Location $BackendPath
    try {
        & $PythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "Alembic failed to prepare the temporary SDK E2E database."
        }
    }
    finally {
        Pop-Location
    }

    $server = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @(
            "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1",
            "--port", [string]$port,
            "--log-level", "warning"
        ) `
        -WorkingDirectory $BackendPath `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    $ready = $false
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        if ($server.HasExited) {
            break
        }
        try {
            $health = Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 2
            if ($health.status -eq "healthy") {
                $ready = $true
                break
            }
        }
        catch {
            # Expected while uvicorn is still starting.
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $ready) {
        if (Test-Path $stderrPath) {
            Get-Content $stderrPath -Tail 80
        }
        throw "uvicorn did not become ready on $baseUrl"
    }

    if ($CrossWorkerSse) {
        $secondaryStdout = Join-Path $taskTemp "uvicorn-secondary.out.log"
        $secondaryStderr = Join-Path $taskTemp "uvicorn-secondary.err.log"
        $secondaryServer = Start-Process `
            -FilePath $PythonPath `
            -ArgumentList @(
                "-m", "uvicorn", "app.main:app",
                "--host", "127.0.0.1",
                "--port", [string]$secondaryPort,
                "--log-level", "warning"
            ) `
            -WorkingDirectory $BackendPath `
            -WindowStyle Hidden `
            -RedirectStandardOutput $secondaryStdout `
            -RedirectStandardError $secondaryStderr `
            -PassThru
        $secondaryReady = $false
        $secondaryDeadline = (Get-Date).AddSeconds(90)
        while ((Get-Date) -lt $secondaryDeadline) {
            if ($secondaryServer.HasExited) { break }
            try {
                $secondaryHealth = Invoke-RestMethod `
                    -Uri "$secondaryBaseUrl/api/health" -TimeoutSec 2
                if ($secondaryHealth.status -eq "healthy") {
                    $secondaryReady = $true
                    break
                }
            }
            catch {
                # Expected while the second independent worker starts.
            }
            Start-Sleep -Milliseconds 500
        }
        if (-not $secondaryReady) {
            if (Test-Path $secondaryStderr) { Get-Content $secondaryStderr -Tail 80 }
            throw "Secondary uvicorn worker did not become ready on $secondaryBaseUrl"
        }
    }

    $proxyStdout = Join-Path $taskTemp "sse-fault-proxy.out.log"
    $proxyStderr = Join-Path $taskTemp "sse-fault-proxy.err.log"
    $proxyArguments = @(
        "-m", "scripts.sdk_sse_fault_proxy",
        "--upstream", $baseUrl
    )
    if ($CrossWorkerSse) {
        $proxyArguments += @("--upstream", $secondaryBaseUrl)
    }
    $proxyArguments += @(
        "--port", [string]$proxyPort,
        "--disconnects-per-run", "2"
    )
    $faultProxy = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList $proxyArguments `
        -WorkingDirectory $BackendPath `
        -WindowStyle Hidden `
        -RedirectStandardOutput $proxyStdout `
        -RedirectStandardError $proxyStderr `
        -PassThru
    $proxyReady = $false
    $proxyDeadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $proxyDeadline) {
        if ($faultProxy.HasExited) { break }
        try {
            $proxyHealth = Invoke-RestMethod -Uri "$sseBaseUrl/__health" -TimeoutSec 2
            if ($proxyHealth.status -eq "healthy") {
                $proxyReady = $true
                break
            }
        }
        catch {
            # Expected while the loopback proxy is starting.
        }
        Start-Sleep -Milliseconds 200
    }
    if (-not $proxyReady) {
        if (Test-Path $proxyStderr) { Get-Content $proxyStderr -Tail 80 }
        throw "SSE fault proxy did not become ready on $sseBaseUrl"
    }

    # Register an ephemeral user so the returned JWT carries an authoritative
    # org_id claim. Tenant-Name/X-Tenant must never manufacture tenant scope.
    $suffix = [guid]::NewGuid().ToString("N")
    $registrationBody = @{
        username = "sdk_$suffix"
        email = "sdk-e2e-$suffix@icoder.ai"
        password = "E2e-$suffix!"
        full_name = "SDK E2E"
        organization_name = "SDK E2E $suffix"
    } | ConvertTo-Json -Compress
    $registration = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/api/auth/register" `
        -ContentType "application/json" `
        -Body $registrationBody `
        -TimeoutSec 15
    if ([string]::IsNullOrWhiteSpace($registration.access_token) -or
        [string]::IsNullOrWhiteSpace($registration.current_org_id)) {
        throw "Local registration returned no tenant-bound access token."
    }

    # Provision one ephemeral OAuth client through the real form endpoint.
    # Its secret is passed only through child-process environment variables
    # and disappears with the temporary database.
    $oauthClient = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/api/oauth/clients" `
        -Headers @{ Authorization = "Bearer $($registration.access_token)" } `
        -ContentType "application/x-www-form-urlencoded" `
        -Body @{
            name = "SDK E2E OAuth"
            description = "Temporary local SDK contract"
            scopes = "api:read api:write"
            allowed_agent_ids = "note-completeness-agent"
            allowed_purposes = "treatment"
        } `
        -TimeoutSec 15
    if ([string]::IsNullOrWhiteSpace($oauthClient.client_id) -or
        [string]::IsNullOrWhiteSpace($oauthClient.client_secret)) {
        throw "Local OAuth client creation returned incomplete credentials."
    }

    $env:ICODER_E2E_BASE_URL = $baseUrl
    $env:ICODER_E2E_SSE_BASE_URL = $sseBaseUrl
    $env:ICODER_E2E_ACCESS_TOKEN = $registration.access_token
    $env:ICODER_E2E_CLIENT_ID = $oauthClient.client_id
    $env:ICODER_E2E_CLIENT_SECRET = $oauthClient.client_secret
    if (-not $SkipDotNet) {
        & $DotnetPath build `
            (Join-Path $packageRoot "examples\Icoder.Sdk.Smoke\Icoder.Sdk.Smoke.csproj") `
            -c Release `
            --nologo
        if ($LASTEXITCODE -ne 0) {
            throw "The .NET smoke consumer build failed with exit code $LASTEXITCODE."
        }
        $dotnetSse = Start-LongSseFixture "dotnet" $registration.current_org_id
        & $DotnetPath run `
            --project (Join-Path $packageRoot "examples\Icoder.Sdk.Smoke\Icoder.Sdk.Smoke.csproj") `
            -c Release `
            --no-build `
            --nologo
        if ($LASTEXITCODE -ne 0) {
            throw "The .NET smoke consumer failed with exit code $LASTEXITCODE."
        }
        Complete-LongSseFixture $dotnetSse "dotnet"
    }

    $javascriptSdk = Join-Path $repositoryRoot "packages\icoder-sdk"
    & $NpmPath --prefix $javascriptSdk run build
    if ($LASTEXITCODE -ne 0) {
        throw "The JavaScript SDK build failed with exit code $LASTEXITCODE."
    }
    $javascriptSse = Start-LongSseFixture "javascript" $registration.current_org_id
    & $NodePath (Join-Path $javascriptSdk "examples\real-api-smoke.mjs")
    if ($LASTEXITCODE -ne 0) {
        throw "The JavaScript smoke consumer failed with exit code $LASTEXITCODE."
    }
    Complete-LongSseFixture $javascriptSse "javascript"

    $pythonSdk = Join-Path $repositoryRoot "packages\icoder-python"
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
        $pythonSdk
    }
    else {
        "$pythonSdk$([System.IO.Path]::PathSeparator)$previousPythonPath"
    }
    $pythonSse = Start-LongSseFixture "python" $registration.current_org_id
    & $PythonPath (Join-Path $pythonSdk "examples\real_api_smoke.py")
    if ($LASTEXITCODE -ne 0) {
        throw "The Python smoke consumer failed with exit code $LASTEXITCODE."
    }
    Complete-LongSseFixture $pythonSse "python"

    # Scrape every independent API process directly. Metrics are deliberately
    # process-scoped and low-cardinality, so production collectors must do the
    # same aggregation rather than querying through the round-robin proxy.
    $metricsHeaders = @{
        Authorization = "Bearer $($env:ICODER_METRICS_BEARER_TOKEN)"
    }
    $metricSnapshots = @(
        Invoke-RestMethod -Uri "$baseUrl/api/metrics" `
            -Headers $metricsHeaders -TimeoutSec 5
    )
    if ($CrossWorkerSse) {
        $metricSnapshots += @(
            Invoke-RestMethod -Uri "$secondaryBaseUrl/api/metrics" `
                -Headers $metricsHeaders -TimeoutSec 5
        )
    }
    $sseConnectionAttempts = [int](
        ($metricSnapshots | ForEach-Object { $_.run_sse.connection_attempts_total } |
            Measure-Object -Sum).Sum
    )
    $sseConnectionsAccepted = [int](
        ($metricSnapshots | ForEach-Object { $_.run_sse.connections_accepted_total } |
            Measure-Object -Sum).Sum
    )
    $sseResumedConnections = [int](
        ($metricSnapshots | ForEach-Object { $_.run_sse.resumed_connections_total } |
            Measure-Object -Sum).Sum
    )
    $sseEventsEmitted = [int](
        ($metricSnapshots | ForEach-Object { $_.run_sse.events_emitted_total } |
            Measure-Object -Sum).Sum
    )
    $sseRenewSuccess = [int](
        ($metricSnapshots | ForEach-Object {
            [int]$_.run_sse.token_renewals_by_outcome.success
        } | Measure-Object -Sum).Sum
    )
    if (
        $sseConnectionAttempts -lt 12 -or
        $sseConnectionsAccepted -lt 9 -or
        $sseResumedConnections -lt 6 -or
        $sseEventsEmitted -lt 9 -or
        $sseRenewSuccess -lt 3
    ) {
        throw (
            "Run SSE metrics did not capture the fault E2E contract: " +
            "attempts=$sseConnectionAttempts accepted=$sseConnectionsAccepted " +
            "resumed=$sseResumedConnections events=$sseEventsEmitted " +
            "renew_success=$sseRenewSuccess"
        )
    }

    $health = Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 5
    $summary = [pscustomobject]@{
        schema_version = "icoder.sdk-local-e2e/v1"
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        status = "passed"
        base_url = $baseUrl
        base_url_lifecycle = "ephemeral_loopback_closed_after_run"
        sse_api_processes = if ($CrossWorkerSse) { 2 } else { 1 }
        sse_proxy_upstream_policy = if ($CrossWorkerSse) {
            "round_robin_across_independent_api_processes"
        }
        else {
            "single_api_process"
        }
        dotnet_smoke = if ($SkipDotNet) { "skipped" } else { "passed" }
        javascript_smoke = "passed"
        python_smoke = "passed"
        agent_hub_visible_verified = 26
        agent_run_without_real_llm = "deterministic_local_rule_completed"
        agent_run_lifecycle = if ($SkipDotNet) {
            "javascript,python:status-terminal,cancel-already-complete,sse-token-renew-two-disconnects-resume-terminal"
        }
        else {
            "dotnet,javascript,python:status-terminal,cancel-already-complete,sse-token-renew-two-disconnects-resume-terminal"
        }
        facts_without_real_llm = "failed_closed"
        coding_multi_system_filter_transport = if ($SkipDotNet) {
            "javascript,python:accepted_and_degraded_without_llm"
        }
        else {
            "dotnet,javascript,python:accepted_and_degraded_without_llm"
        }
        real_llm_used = $false
        realtime_stt = if ($SkipDotNet) {
            "javascript,python:authenticated-start-ready-close"
        }
        else {
            "dotnet,javascript,python:authenticated-start-ready-close"
        }
        realtime_audio_sent = $false
        oauth_client_credentials = if ($SkipDotNet) {
            "javascript,python:form-token-hub"
        }
        else {
            "dotnet,javascript,python:form-token-hub"
        }
        run_sse_metrics_process_snapshots = $metricSnapshots.Count
        run_sse_connection_attempts_total = $sseConnectionAttempts
        run_sse_connections_accepted_total = $sseConnectionsAccepted
        run_sse_resumed_connections_total = $sseResumedConnections
        run_sse_events_emitted_total = $sseEventsEmitted
        run_sse_token_renew_success_total = $sseRenewSuccess
        run_sse_metrics_labels = "fixed-enum-only:no-run-org-user-cursor-token-clinical-labels"
        medcoder_index_ready = $health.medcoder_index_ready
        medcoder_index_error = $health.medcoder_index_error
    }
    $summaryJson = $summary | ConvertTo-Json -Compress
    if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
        $resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
        $outputParent = Split-Path $resolvedOutput -Parent
        if (-not [string]::IsNullOrWhiteSpace($outputParent)) {
            New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
        }
        [System.IO.File]::WriteAllText(
            $resolvedOutput,
            $summaryJson + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
    $summaryJson
}
finally {
    Remove-Item Env:ICODER_E2E_ACCESS_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:ICODER_E2E_SSE_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:ICODER_E2E_CLIENT_ID -ErrorAction SilentlyContinue
    Remove-Item Env:ICODER_E2E_CLIENT_SECRET -ErrorAction SilentlyContinue
    Remove-Item Env:ICODER_E2E_SSE_RUN_ID -ErrorAction SilentlyContinue
    Remove-Item Env:ICODER_E2E_SSE_TRACE_TOKEN -ErrorAction SilentlyContinue
    if ($null -eq $previousMetricsToken) {
        Remove-Item Env:ICODER_METRICS_BEARER_TOKEN -ErrorAction SilentlyContinue
    }
    else {
        $env:ICODER_METRICS_BEARER_TOKEN = $previousMetricsToken
    }
    if ($null -eq $previousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONPATH = $previousPythonPath
    }
    if ($null -eq $previousSecretKey) {
        Remove-Item Env:ICODER_SECRET_KEY -ErrorAction SilentlyContinue
    }
    else {
        $env:ICODER_SECRET_KEY = $previousSecretKey
    }
    foreach ($item in @(
        @("ICODER_CREDENTIAL_LLM", $previousLlmCredential),
        @("DEEPSEEK_API_KEY", $previousDeepSeekKey),
        @("ICODER_ALLOW_EXTERNAL_LLM", $previousExternalLlm),
        @("ICODER_DISABLE_NATIVE_MEDCODER", $previousDisableNativeMedcoder),
        @("ICODER_ENABLE_LOCAL_STT", $previousLocalStt),
        @("ICODER_MODEL_LIVE_CANARY_ENABLED", $previousLiveCanary)
    )) {
        $name = [string]$item[0]
        $value = $item[1]
        if ($null -eq $value) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item "Env:$name" ([string]$value)
        }
    }
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force
        Wait-Process -Id $server.Id -Timeout 10 -ErrorAction SilentlyContinue
    }
    if ($secondaryServer -and -not $secondaryServer.HasExited) {
        Stop-Process -Id $secondaryServer.Id -Force
        Wait-Process -Id $secondaryServer.Id -Timeout 10 -ErrorAction SilentlyContinue
    }
    if ($faultProxy -and -not $faultProxy.HasExited) {
        Stop-Process -Id $faultProxy.Id -Force
        Wait-Process -Id $faultProxy.Id -Timeout 10 -ErrorAction SilentlyContinue
    }

    foreach ($finisher in $fixtureFinishers) {
        $finisher.Refresh()
        if (-not $finisher.HasExited) {
            Stop-Process -Id $finisher.Id -Force
            Wait-Process -Id $finisher.Id -Timeout 5 -ErrorAction SilentlyContinue
        }
    }

    $resolvedTemp = [System.IO.Path]::GetFullPath($taskTemp)
    $tempLeaf = Split-Path $resolvedTemp -Leaf
    if ($resolvedTemp.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        $tempLeaf -like "icoder-dotnet-e2e-*") {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
    else {
        throw "Refusing to clean unexpected temp path: $resolvedTemp"
    }
}
