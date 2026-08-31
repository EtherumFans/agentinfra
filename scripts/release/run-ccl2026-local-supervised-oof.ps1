[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$AuthorizedRoot = "E:\iCoDerA\data",
    [string]$SourceWorkbook = "E:\iCoDerA\data\train.xlsx",
    [string]$AuditReport = "reports\agent_hub\ccl2026_local_dataset_audit_20260827_v2\ccl2026_local_dataset_audit.json",
    [string]$Fixture = "backend\tests\fixtures\ccl2026_train_gold.json",
    [string]$OutputDirectory = "reports\agent_hub\ccl2026_local_supervised_oof_latest"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$authorized = [System.IO.Path]::GetFullPath($AuthorizedRoot)
$source = [System.IO.Path]::GetFullPath($SourceWorkbook)
$auditPath = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $AuditReport))
$fixturePath = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $Fixture))
$outputRoot = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $OutputDirectory))
$reportPath = Join-Path $outputRoot "ccl2026_local_supervised_oof.json"
$databasePath = Join-Path $repositoryRoot "backend\data\icoder.db"

if (-not $source.StartsWith(
        $authorized.TrimEnd('\') + '\',
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    throw "Source workbook is outside the explicitly authorized root."
}
if (-not $outputRoot.StartsWith(
        (Join-Path $repositoryRoot "reports\agent_hub").TrimEnd('\') + '\',
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    throw "Aggregate output must remain below reports\agent_hub."
}
foreach ($path in @($source, $auditPath, $fixturePath, $databasePath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required governed input is missing."
    }
}

$audit = Get-Content -LiteralPath $auditPath -Raw | ConvertFrom-Json
$sourceSha = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sourceSha -cne [string]$audit.source_workbook.sha256) {
    throw "Authorized workbook no longer matches the governed audit."
}
$databaseBefore = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

try {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
    [Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", $null, "Process")
    [Environment]::SetEnvironmentVariable("LLM_API_KEY", $null, "Process")
    [Environment]::SetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", "1", "Process")
    & $PythonPath (
        Join-Path $repositoryRoot (
            "backend\scripts\corti_parity\" +
            "evaluate_ccl2026_local_supervised_oof.py"
        )
    ) `
        --audit-report $auditPath `
        --fixture $fixturePath `
        --output $reportPath `
        --expected-case-count 1800 `
        --folds 5 `
        --assert-valid
    if ($LASTEXITCODE -ne 0) {
        throw "Local supervised OOF evaluation failed."
    }
}
finally {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
    [Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", $null, "Process")
    [Environment]::SetEnvironmentVariable("LLM_API_KEY", $null, "Process")
    [Environment]::SetEnvironmentVariable("PYTHONDONTWRITEBYTECODE", $null, "Process")
}

$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
if ($report.status -cne "valid_local_supervised_oof_measurement") {
    throw "Aggregate report is not valid."
}
if (
    -not $report.claim_boundaries.all_predictions_out_of_fold -or
    $report.integrity.training_row_self_exposure_count -ne 0 -or
    $report.claim_boundaries.independent_clinical_gold_proven -or
    $report.claim_boundaries.external_generalization_proven -or
    $report.claim_boundaries.corti_capability_parity_proven -or
    $report.claim_boundaries.clinical_production_readiness_proven
) {
    throw "Aggregate report violates conservative claim boundaries."
}
$serialized = Get-Content -LiteralPath $reportPath -Raw
foreach ($pattern in @(
        '"predictions"\s*:',
        '"per_case"\s*:',
        '"encounter_id"\s*:',
        '"clinical_text"\s*:',
        '"text"\s*:',
        '"case_digest"\s*:',
        '"neighbors"\s*:',
        '"error_examples"\s*:'
    )) {
    if ($serialized -match $pattern) {
        throw "Aggregate report contains a forbidden case-level field."
    }
}
$databaseAfter = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash
if ($databaseBefore -cne $databaseAfter) {
    throw "Protected development database changed during local evaluation."
}

[pscustomobject]@{
    status = "passed"
    report = $reportPath
    case_count = $report.evaluation.evaluated_case_count
    fold_count = $report.evaluation.fold_count
    report_sha256 = (Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash.ToLowerInvariant()
    protected_database_unchanged = $true
    external_network_used = $false
    case_level_artifacts_emitted = $false
} | ConvertTo-Json -Compress
