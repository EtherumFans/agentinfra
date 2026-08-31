param(
    [string]$PythonPath = "python",
    [string]$EvidenceDirectory = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$databasePath = Join-Path $repoRoot "backend\data\icoder.db"
$workbookPath = "E:\iCoDerA\data\train.xlsx"
$fixturePath = Join-Path $repoRoot "backend\tests\fixtures\clinical_model_bundle_v1"
if (-not $EvidenceDirectory) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDirectory = Join-Path $repoRoot "reports\deployment\clinical_model_shadow_observation_$stamp"
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
$outputPath = Join-Path $EvidenceDirectory "clinical_model_shadow_observation.json"
try {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
    & $PythonPath (
        Join-Path $repoRoot "backend\scripts\corti_parity\verify_clinical_model_shadow_observation.py"
    ) --fixture $fixturePath --output $outputPath
    if ($LASTEXITCODE -ne 0) {
        throw "Synthetic clinical model shadow observation failed."
    }
    $databaseAfter = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $workbookAfter = (Get-FileHash -LiteralPath $workbookPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($databaseBefore -ne $databaseAfter) {
        throw "Protected database changed during shadow observation."
    }
    if ($workbookBefore -ne $workbookAfter) {
        throw "Authorized workbook changed during shadow observation."
    }
    $evidence = Get-Content -Raw -LiteralPath $outputPath | ConvertFrom-Json
    if (-not $evidence.passed -or $evidence.production_inference_enabled) {
        throw "Aggregate shadow observation evidence failed its release boundary."
    }
    Write-Host "Clinical model aggregate shadow observation passed: $outputPath"
}
finally {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
}
