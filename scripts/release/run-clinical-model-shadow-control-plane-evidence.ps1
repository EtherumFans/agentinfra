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
    $EvidenceDirectory = Join-Path $repoRoot "reports\deployment\clinical_shadow_control_plane_$stamp"
}
$EvidenceDirectory = [System.IO.Path]::GetFullPath($EvidenceDirectory)
$reportsRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot "reports"))
$reportsPrefix = $reportsRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
if ($EvidenceDirectory -ne $reportsRoot -and -not $EvidenceDirectory.StartsWith(
    $reportsPrefix, [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "EvidenceDirectory must remain under the repository reports directory."
}

$databaseBefore = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
$workbookBefore = (Get-FileHash -LiteralPath $workbookPath -Algorithm SHA256).Hash.ToLowerInvariant()
New-Item -ItemType Directory -Force -Path $EvidenceDirectory | Out-Null
$junitPath = Join-Path $EvidenceDirectory "pytest-shadow-control-plane.xml"
$outputPath = Join-Path $EvidenceDirectory "clinical_shadow_control_plane.json"
try {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
    Push-Location $repoRoot
    try {
        & $PythonPath -m pytest -q `
            "backend/tests/test_api/test_clinical_model_packages.py::test_signed_synthetic_bundle_probe_is_metadata_only_and_shadow_bound" `
            "backend/tests/unit/app/services/test_clinical_model_shadow_operations.py" `
            "backend/tests/test_api/test_metrics_security.py" `
            --junitxml $junitPath
        if ($LASTEXITCODE -ne 0) {
            throw "Clinical shadow control-plane tests failed."
        }
        & $PythonPath (
            Join-Path $repoRoot "backend\scripts\corti_parity\verify_clinical_model_shadow_control_plane_evidence.py"
        ) --junit $junitPath --output $outputPath
        if ($LASTEXITCODE -ne 0) {
            throw "Clinical shadow control-plane evidence validation failed."
        }
    }
    finally {
        Pop-Location
    }
    $databaseAfter = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $workbookAfter = (Get-FileHash -LiteralPath $workbookPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($databaseBefore -ne $databaseAfter) {
        throw "Protected database changed during shadow control-plane validation."
    }
    if ($workbookBefore -ne $workbookAfter) {
        throw "Authorized workbook changed during shadow control-plane validation."
    }
    $evidence = Get-Content -Raw -LiteralPath $outputPath | ConvertFrom-Json
    if (-not $evidence.passed -or $evidence.production_inference_enabled) {
        throw "Clinical shadow control-plane evidence failed its release boundary."
    }
    Write-Host "Clinical shadow control-plane evidence passed: $outputPath"
}
finally {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
}
