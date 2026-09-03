[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$AuditReport = "reports/agent_hub/ccl2026_local_dataset_audit_20260827_v2/ccl2026_local_dataset_audit.json",
    [string]$Fixture = "backend/tests/fixtures/ccl2026_train_gold.json",
    [string]$OutputRoot = "reports/agent_hub/ccl2026_local_evaluator_selftest_20260827_v1"
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
    (Join-Path $tempBase ("icoder-ccl-evaluator-" + [guid]::NewGuid().ToString("N")))
)
if (-not $tempRoot.StartsWith($tempBase + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Resolved evaluator temporary root is outside C:\Temp."
}
$predictionPacket = Join-Path $tempRoot "oracle-test-predictions.json"
$aggregateReport = Join-Path $resolvedOutput "ccl2026_local_evaluator_selftest.json"
$environmentNames = @(
    "ICODER_CREDENTIAL_LLM", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
    "ICODER_ALLOW_EXTERNAL_LLM", "LLM_PROVIDER", "PYTHONPATH"
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
    $env:PYTHONPATH = $backendRoot

    Push-Location $backendRoot
    try {
        $script = "scripts/corti_parity/evaluate_ccl2026_local_predictions.py"
        Invoke-PythonChecked -Arguments @(
            $script,
            "--audit-report", $resolvedAudit,
            "--fixture", $resolvedFixture,
            "--predictions", $predictionPacket,
            "--isolated-root", $tempRoot,
            "--expected-case-count", "1800",
            "--build-oracle-test-packet",
            "--acknowledge-oracle-test-only"
        )
        Invoke-PythonChecked -Arguments @(
            $script,
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
        throw "Aggregate evaluator self-test did not produce a valid measurement."
    }
    if (-not $report.claim_boundaries.oracle_contract_self_test_only) {
        throw "Aggregate evaluator self-test lost its oracle-only boundary."
    }
    if ($report.claim_boundaries.model_capability_proven) {
        throw "Oracle self-test must not claim model capability."
    }
    if (
        $report.metrics.case_count -ne 1800 -or
        $report.metrics.full_code_set_exact_match_rate -ne 1 -or
        $report.metrics.principal_diagnosis_exact_accuracy -ne 1 -or
        $report.metrics.all_diagnosis.f1 -ne 1 -or
        $report.metrics.all_procedure.f1 -ne 1
    ) {
        throw "Oracle metrics do not prove exact evaluator scoring."
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
    Write-Host "CCL 2026 local evaluator self-test passed: 1800/1800 oracle contract cases."
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
        [System.IO.Path]::GetFileName($resolvedTemp).StartsWith("icoder-ccl-evaluator-") -and
        (Test-Path -LiteralPath $resolvedTemp)
    ) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}
