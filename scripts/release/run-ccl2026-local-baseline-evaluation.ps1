[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$AuditReport = "reports/agent_hub/ccl2026_local_dataset_audit_20260827_v2/ccl2026_local_dataset_audit.json",
    [string]$Fixture = "backend/tests/fixtures/ccl2026_train_gold.json",
    [string]$OutputRoot = "reports/agent_hub/ccl2026_local_baseline_evaluation_20260827_v1"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$backendRoot = Join-Path $repositoryRoot "backend"

function Resolve-RepositoryPath {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ([System.IO.Path]::IsPathRooted($Value)) {
        return [System.IO.Path]::GetFullPath($Value)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $Value))
}

function Invoke-PythonChecked {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & $PythonPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code ${LASTEXITCODE}."
    }
}

$resolvedAudit = Resolve-RepositoryPath -Value $AuditReport
$resolvedFixture = Resolve-RepositoryPath -Value $Fixture
$resolvedOutput = Resolve-RepositoryPath -Value $OutputRoot
$tempBase = [System.IO.Path]::GetFullPath("C:\Temp")
New-Item -ItemType Directory -Path $tempBase -Force | Out-Null
$tempRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $tempBase ("icoder-ccl-baseline-" + [guid]::NewGuid().ToString("N")))
)
if (-not $tempRoot.StartsWith($tempBase + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Resolved baseline temporary root is outside C:\Temp."
}
$predictionPacket = Join-Path $tempRoot "local-baseline-predictions.json"
$aggregateReport = Join-Path $resolvedOutput "ccl2026_local_baseline_evaluation.json"
$environmentNames = @(
    "ICODER_CREDENTIAL_LLM", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
    "ICODER_ALLOW_EXTERNAL_LLM", "LLM_PROVIDER", "PYTHONPATH",
    "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    New-Item -ItemType Directory -Path $resolvedOutput -Force | Out-Null
    foreach ($name in @("ICODER_CREDENTIAL_LLM", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    $env:ICODER_ALLOW_EXTERNAL_LLM = "false"
    $env:LLM_PROVIDER = "mock"
    $env:HF_HUB_OFFLINE = "1"
    $env:TRANSFORMERS_OFFLINE = "1"
    $env:PYTHONPATH = $backendRoot

    Push-Location $backendRoot
    try {
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/generate_ccl2026_local_baseline_predictions.py",
            "--audit-report", $resolvedAudit,
            "--fixture", $resolvedFixture,
            "--predictions", $predictionPacket,
            "--isolated-root", $tempRoot,
            "--expected-case-count", "1800"
        )
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/evaluate_ccl2026_local_predictions.py",
            "--audit-report", $resolvedAudit,
            "--fixture", $resolvedFixture,
            "--predictions", $predictionPacket,
            "--isolated-root", $tempRoot,
            "--expected-case-count", "1800",
            "--output", $aggregateReport,
            "--assert-valid"
        )
    }
    finally {
        Pop-Location
    }

    $report = Get-Content -LiteralPath $aggregateReport -Raw | ConvertFrom-Json
    if ($report.status -ne "valid_local_training_set_measurement") {
        throw "Local deterministic baseline did not produce a valid measurement."
    }
    if (-not $report.claim_boundaries.local_deterministic_training_set_baseline_measured) {
        throw "Aggregate report lost its deterministic baseline boundary."
    }
    if (
        $report.claim_boundaries.model_capability_proven -or
        $report.claim_boundaries.local_model_training_set_metrics_measured -or
        $report.claim_boundaries.production_readiness_proven
    ) {
        throw "Deterministic baseline report contains an invalid capability claim."
    }
    $serialized = Get-Content -LiteralPath $aggregateReport -Raw
    foreach ($forbidden in @(
        '"predictions"', '"per_case"', '"encounter_id"',
        '"case_digest"', '"admission_reason"', '"text"'
    )) {
        if ($serialized.Contains($forbidden)) {
            throw "Aggregate report contains a prohibited case-level field."
        }
    }
    Write-Host "CCL 2026 local deterministic baseline completed."
    Write-Host "Aggregate evidence: $aggregateReport"
}
finally {
    foreach ($name in $environmentNames) {
        $value = $previousEnvironment[$name]
        if ($null -eq $value) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
        else {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
    $resolvedTemp = [System.IO.Path]::GetFullPath($tempRoot)
    if (
        $resolvedTemp.StartsWith($tempBase + [System.IO.Path]::DirectorySeparatorChar) -and
        [System.IO.Path]::GetFileName($resolvedTemp).StartsWith("icoder-ccl-baseline-") -and
        (Test-Path -LiteralPath $resolvedTemp)
    ) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}
