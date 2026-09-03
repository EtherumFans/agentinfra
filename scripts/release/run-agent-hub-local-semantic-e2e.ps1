[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$OutputRoot = "reports/agent_hub/local_semantic_e2e_phase_20260824"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$backendRoot = Join-Path $repositoryRoot "backend"
$agentsDir = Join-Path $backendRoot "official_agents"
$resolvedOutputRoot = if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $OutputRoot))
}
$tempRoot = [System.IO.Path]::GetFullPath("C:\Temp")
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$taskTemp = Join-Path $tempRoot ("icoder-agent-local-e2e-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $taskTemp | Out-Null
$databasePath = Join-Path $taskTemp "agent-local-e2e.db"
$serverOut = Join-Path $taskTemp "uvicorn.out.log"
$serverErr = Join-Path $taskTemp "uvicorn.err.log"

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        0
    )
    $listener.Start()
    try { return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function Invoke-PythonChecked {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & $PythonPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}

$serverPort = Get-FreePort
$baseUrl = "http://127.0.0.1:$serverPort"
$server = $null
$localAgentIds = @(
    "claim-check",
    "clinical-education",
    "clinical-guidelines",
    "code-validation-agent",
    "compliance-guardrail-agent",
    "denial-appeals",
    "diagnosis-extractor",
    "discharge-edu",
    "discharge-summary-structuring",
    "drg-analyzer",
    "evidence-extractor",
    "evidence-ranker",
    "icd10-navigator",
    "icu-summary",
    "med-reconciliation",
    "note-completeness-agent",
    "nursing-handoff",
    "principal-diagnosis-review",
    "prior-auth",
    "procedure-extractor",
    "referral-gen",
    "rule-explainer",
    "surgical-registry",
    "triage"
)
$localAgentIdsArgument = $localAgentIds -join ","
$localAgentCount = $localAgentIds.Count
$externalAgentCount = 26 - $localAgentCount
$stabilityExpected = $localAgentCount * 2 * 3
$environmentNames = @(
    "DATABASE_URL", "ICODER_DATABASE_URL", "APP_ENV", "SEED_ON_STARTUP",
    "ICODER_CREDENTIAL_LLM", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
    "LLM_PROVIDER", "ICODER_ALLOW_EXTERNAL_LLM",
    "ICODER_DISABLE_NATIVE_MEDCODER", "ICODER_ENABLE_LOCAL_STT",
    "ICODER_MODEL_LIVE_CANARY_ENABLED", "ICODER_ALLOW_DEGRADED_NO_KEY",
    "ICODER_SECRET_KEY", "ICODER_ENVIRONMENT", "ICODER_REGION",
    "ICODER_E2E_BEARER", "ICODER_E2E_USERNAME", "ICODER_E2E_PASSWORD",
    "ICODER_DISABLE_AUTH_FOR_TESTS", "PYTHONPATH", "NO_PROXY", "no_proxy"
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

$examplesDir = Join-Path $resolvedOutputRoot "examples"
$adversarialDir = Join-Path $resolvedOutputRoot "adversarial"
$referenceDir = Join-Path $resolvedOutputRoot "reference"
$stabilityDir = Join-Path $resolvedOutputRoot "stability"
$bundleDir = Join-Path $resolvedOutputRoot "bundle"
$matrixDir = Join-Path $resolvedOutputRoot "runtime-matrix"

try {
    New-Item -ItemType Directory -Path $resolvedOutputRoot -Force | Out-Null
    $databaseUrl = "sqlite+aiosqlite:///" + $databasePath.Replace("\", "/")
    $env:DATABASE_URL = $databaseUrl
    $env:ICODER_DATABASE_URL = $databaseUrl
    $env:APP_ENV = "local"
    $env:SEED_ON_STARTUP = "0"
    foreach ($name in @(
        "ICODER_CREDENTIAL_LLM", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
        "ICODER_E2E_BEARER", "ICODER_E2E_USERNAME", "ICODER_E2E_PASSWORD",
        "ICODER_DISABLE_AUTH_FOR_TESTS"
    )) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    $env:LLM_PROVIDER = "mock"
    $env:ICODER_ALLOW_EXTERNAL_LLM = "false"
    $env:ICODER_DISABLE_NATIVE_MEDCODER = "true"
    $env:ICODER_ENABLE_LOCAL_STT = "false"
    $env:ICODER_MODEL_LIVE_CANARY_ENABLED = "false"
    $env:ICODER_ALLOW_DEGRADED_NO_KEY = "1"
    $env:ICODER_ENVIRONMENT = "cn"
    $env:ICODER_REGION = "cn-local-agent-e2e"
    $env:ICODER_SECRET_KEY = (
        [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    )
    $env:PYTHONPATH = $backendRoot
    $env:NO_PROXY = "127.0.0.1,localhost"
    $env:no_proxy = $env:NO_PROXY

    Push-Location $backendRoot
    try {
        Invoke-PythonChecked -Arguments @("-m", "alembic", "upgrade", "head")
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
        if (Test-Path -LiteralPath $serverErr) { Get-Content $serverErr -Tail 80 }
        throw "Temporary Agent Hub Uvicorn did not become ready."
    }

    Push-Location $backendRoot
    try {
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/run_agent_hub_examples_e2e.py",
            "--base-url", $baseUrl,
            "--agents-dir", $agentsDir,
            "--out-dir", $examplesDir,
            "--agent-ids", $localAgentIdsArgument,
            "--delay", "0", "--force", "--allow-self-register"
        )
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/run_agent_hub_adversarial_e2e.py",
            "--base-url", $baseUrl,
            "--agents-dir", $agentsDir,
            "--out-dir", $adversarialDir,
            "--agent-ids", $localAgentIdsArgument,
            "--delay", "0", "--force", "--allow-self-register"
        )
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/run_agent_hub_reference_quality_replay.py",
            "--agents-dir", $agentsDir,
            "--responses-dir", (Join-Path $examplesDir "responses"),
            "--source-report", (Join-Path $examplesDir "agent_hub_examples_e2e.json"),
            "--out-dir", $referenceDir,
            "--agent-ids", $localAgentIdsArgument
        )
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/run_agent_hub_stability_benchmark.py",
            "--base-url", $baseUrl,
            "--agents-dir", $agentsDir,
            "--out-dir", $stabilityDir,
            "--agent-ids", $localAgentIdsArgument,
            "--repetitions", "3", "--delay", "0", "--force",
            "--allow-self-register",
            "--happy-seed-dir", $examplesDir,
            "--adversarial-seed-dir", $adversarialDir
        )
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/build_agent_hub_local_semantic_evidence_bundle.py",
            "--examples", (Join-Path $examplesDir "agent_hub_examples_e2e.json"),
            "--adversarial", (Join-Path $adversarialDir "agent_hub_adversarial_e2e.json"),
            "--reference", (Join-Path $referenceDir "agent_hub_reference_quality_replay.json"),
            "--stability", (Join-Path $stabilityDir "agent_hub_stability_benchmark.json"),
            "--agents-dir", $agentsDir,
            "--out-dir", $bundleDir
        )
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/build_agent_hub_runtime_matrix.py",
            "--agents-dir", $agentsDir,
            "--output-dir", $matrixDir,
            "--assert-visible-ready",
            "--local-semantic-evidence",
            (Join-Path $bundleDir "agent_hub_local_semantic_evidence_bundle.json")
        )
    }
    finally { Pop-Location }

    $examplesPath = Join-Path $examplesDir "agent_hub_examples_e2e.json"
    $adversarialPath = Join-Path $adversarialDir "agent_hub_adversarial_e2e.json"
    $referencePath = Join-Path $referenceDir "agent_hub_reference_quality_replay.json"
    $stabilityPath = Join-Path $stabilityDir "agent_hub_stability_benchmark.json"
    $bundlePath = Join-Path $bundleDir "agent_hub_local_semantic_evidence_bundle.json"
    $matrixPath = Join-Path $matrixDir "agent_hub_runtime_matrix.json"
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    $examples = [System.IO.File]::ReadAllText($examplesPath, $utf8) | ConvertFrom-Json
    $adversarial = [System.IO.File]::ReadAllText($adversarialPath, $utf8) | ConvertFrom-Json
    $reference = [System.IO.File]::ReadAllText($referencePath, $utf8) | ConvertFrom-Json
    $stability = [System.IO.File]::ReadAllText($stabilityPath, $utf8) | ConvertFrom-Json
    $bundle = [System.IO.File]::ReadAllText($bundlePath, $utf8) | ConvertFrom-Json
    $matrix = [System.IO.File]::ReadAllText($matrixPath, $utf8) | ConvertFrom-Json

    if (
        $examples.total -ne $localAgentCount -or
        $examples.passed -ne $localAgentCount -or
        $examples.capability_passed -ne $localAgentCount -or
        $examples.failed -ne 0 -or
        $examples.safe_fail_closed -ne 0
    ) { throw "Local Agent happy-path evidence is incomplete." }
    if (
        $adversarial.expected -ne $localAgentCount -or
        $adversarial.completed -ne $localAgentCount -or
        $adversarial.passed -ne $localAgentCount -or
        $adversarial.semantic_capability_passed -ne $localAgentCount -or
        $adversarial.failed -ne 0 -or $adversarial.safe_fail_closed -ne 0
    ) { throw "Local Agent adversarial evidence is incomplete." }
    if (
        $reference.expected -ne $localAgentCount -or
        $reference.passed -ne $localAgentCount -or
        $reference.failed -ne 0 -or -not $reference.all_passed
    ) { throw "Local Agent reference replay evidence is incomplete." }
    if (
        $stability.repetitions -ne 3 -or
        $stability.expected -ne $stabilityExpected -or
        $stability.completed -ne $stabilityExpected -or
        $stability.passed -ne $stabilityExpected -or
        $stability.failed -ne 0 -or -not $stability.complete -or
        -not $stability.gates.all_passed
    ) { throw "Local Agent stability evidence is incomplete." }
    if (
        -not $bundle.valid -or
        $bundle.summary.local_agents_expected -ne $localAgentCount -or
        $bundle.summary.local_semantic_e2e_verified -ne $localAgentCount -or
        $bundle.summary.external_model_agents_not_evaluated -ne $externalAgentCount
    ) { throw "Local semantic evidence bundle is invalid or over-broad." }
    if (
        -not $matrix.local_semantic_evidence.valid -or
        $matrix.summary.visible_local_semantic_e2e_verified -ne $localAgentCount -or
        $matrix.summary.visible_local_semantic_e2e_pending.Count -ne 0 -or
        $matrix.summary.visible_semantic_live_e2e_verified -ne 0 -or
        $matrix.summary.visible_semantic_live_e2e_pending.Count -ne 26 -or
        $matrix.summary.visible_external_semantic_live_e2e_pending.Count -ne $externalAgentCount
    ) { throw "Runtime matrix blurred local evidence into the strict 26-Agent gate." }
    if ($server.HasExited) { throw "Backend exited during local Agent Hub E2E." }

    $sourceArtifacts = [ordered]@{}
    foreach ($path in @(
        $examplesPath, $adversarialPath, $referencePath,
        $stabilityPath, $bundlePath, $matrixPath
    )) {
        $sourceArtifacts[[System.IO.Path]::GetFileName($path)] = @{
            path = $path
            sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    $evidence = [ordered]@{
        schema_version = "icoder.agent-hub-local-semantic-e2e-phase/v1"
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        status = "passed"
        transport = "real_loopback_http"
        local_agent_ids = $localAgentIds
        happy = @{ passed = $localAgentCount; failed = 0; safe_fail_closed = 0 }
        adversarial = @{ passed = $localAgentCount; failed = 0; safe_fail_closed = 0 }
        reference = @{ passed = $localAgentCount; failed = 0 }
        stability = @{
            passed = $stabilityExpected
            failed = 0
            repetitions = 3
            seeded = [int]$stability.execution_provenance.seeded_artifacts
            fresh = [int]$stability.execution_provenance.fresh_http_runs
        }
        runtime_matrix = @{
            local_semantic_verified = $localAgentCount
            strict_26_agent_semantic_verified = 0
            external_model_agents_pending = $externalAgentCount
        }
        source_artifacts = $sourceArtifacts
        temporary_database = "created_migrated_removed"
        real_llm_used = $false
        external_network_used = $false
        synthetic_pack_owned_cases_only = $true
        independent_clinical_gold_used = $false
        corti_parity_proven = $false
        hospital_acceptance_proven = $false
    }
    $evidencePath = Join-Path $resolvedOutputRoot "local_semantic_e2e_evidence.json"
    [System.IO.File]::WriteAllText(
        $evidencePath,
        ($evidence | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
    $evidence | ConvertTo-Json -Depth 8
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
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
    $resolvedTemp = [System.IO.Path]::GetFullPath($taskTemp)
    $tempLeaf = Split-Path $resolvedTemp -Leaf
    if (
        $resolvedTemp.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        $tempLeaf -like "icoder-agent-local-e2e-*"
    ) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    } else {
        throw "Refusing to clean unexpected Agent Hub E2E temp path: $resolvedTemp"
    }
}
