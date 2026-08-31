param(
    [string]$PythonPath = "python",
    [string]$EvidenceDirectory = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$databasePath = Join-Path $repoRoot "backend\data\icoder.db"
$workbookPath = "E:\iCoDerA\data\train.xlsx"
if (-not $EvidenceDirectory) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDirectory = Join-Path $repoRoot "reports\deployment\clinical_model_shadow_job_$stamp"
}
$EvidenceDirectory = [System.IO.Path]::GetFullPath($EvidenceDirectory)
$reportsRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot "reports"))
$reportsPrefix = $reportsRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
if ($EvidenceDirectory -ne $reportsRoot -and -not $EvidenceDirectory.StartsWith(
    $reportsPrefix,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "EvidenceDirectory must remain under the repository reports directory."
}

$databaseBefore = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
$workbookBefore = (Get-FileHash -LiteralPath $workbookPath -Algorithm SHA256).Hash.ToLowerInvariant()
New-Item -ItemType Directory -Force -Path $EvidenceDirectory | Out-Null
$junitPath = Join-Path $EvidenceDirectory "pytest-shadow-job.xml"
$outputPath = Join-Path $EvidenceDirectory "clinical_model_shadow_job.json"
try {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
    Push-Location $repoRoot
    try {
        & $PythonPath -m pytest -q (
            "backend/tests/test_api/test_clinical_model_packages.py::" +
            "test_signed_synthetic_bundle_probe_is_metadata_only_and_shadow_bound"
        ) --junitxml $junitPath
        if ($LASTEXITCODE -ne 0) {
            throw "Distributed clinical shadow job contract test failed."
        }
        & $PythonPath (
            Join-Path $repoRoot "backend\scripts\corti_parity\verify_clinical_model_shadow_job_evidence.py"
        ) --junit $junitPath --output $outputPath
        if ($LASTEXITCODE -ne 0) {
            throw "Distributed clinical shadow job evidence validation failed."
        }
    }
    finally {
        Pop-Location
    }
    $databaseAfter = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $workbookAfter = (Get-FileHash -LiteralPath $workbookPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($databaseBefore -ne $databaseAfter) {
        throw "Protected database changed during distributed shadow job validation."
    }
    if ($workbookBefore -ne $workbookAfter) {
        throw "Authorized workbook changed during distributed shadow job validation."
    }
    $evidence = Get-Content -Raw -LiteralPath $outputPath | ConvertFrom-Json
    if (-not $evidence.passed -or $evidence.production_inference_enabled) {
        throw "Distributed shadow job evidence failed its release boundary."
    }
    Write-Host "Distributed clinical shadow job evidence passed: $outputPath"
}
finally {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
}
