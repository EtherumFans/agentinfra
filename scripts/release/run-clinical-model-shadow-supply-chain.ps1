param(
    [string]$PythonPath = "python",
    [string]$EvidenceDirectory = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$databasePath = Join-Path $repoRoot "backend\data\icoder.db"
$fixturePath = Join-Path $repoRoot "backend\tests\fixtures\clinical_model_bundle_v1"
if (-not $EvidenceDirectory) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDirectory = Join-Path $repoRoot "reports\deployment\clinical_model_shadow_supply_chain_$stamp"
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
$before = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
New-Item -ItemType Directory -Force -Path $EvidenceDirectory | Out-Null
$outputPath = Join-Path $EvidenceDirectory "clinical_model_shadow_supply_chain.json"
try {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
    & $PythonPath (
        Join-Path $repoRoot "backend\scripts\corti_parity\verify_clinical_model_shadow_fixture.py"
    ) --fixture $fixturePath --output $outputPath
    if ($LASTEXITCODE -ne 0) {
        throw "Synthetic clinical model supply-chain verification failed."
    }
    $after = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($before -ne $after) {
        throw "Protected database changed during the synthetic supply-chain probe."
    }
    $evidence = Get-Content -Raw -LiteralPath $outputPath | ConvertFrom-Json
    if (-not $evidence.passed -or $evidence.production_inference_enabled) {
        throw "Aggregate shadow evidence failed its release boundary."
    }
    Write-Host "Clinical model shadow supply-chain evidence passed: $outputPath"
}
finally {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
}
