param(
    [string]$PythonPath = "python",
    [string]$EvidenceDirectory = "",
    [double]$SoakSeconds = 30,
    [int]$MinimumCycles = 100,
    [int]$DuplicateDeliveries = 16
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$databasePath = Join-Path $repoRoot "backend\data\icoder.db"
$workbookPath = "E:\iCoDerA\data\train.xlsx"
if (-not $EvidenceDirectory) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDirectory = Join-Path $repoRoot "reports\deployment\clinical_shadow_resilience_$stamp"
}
$EvidenceDirectory = [System.IO.Path]::GetFullPath($EvidenceDirectory)
$reportsRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot "reports"))
$reportsPrefix = $reportsRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
if ($EvidenceDirectory -ne $reportsRoot -and -not $EvidenceDirectory.StartsWith(
    $reportsPrefix, [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "EvidenceDirectory must remain under the repository reports directory."
}
if ($SoakSeconds -lt 1 -or $MinimumCycles -lt 1) {
    throw "SoakSeconds and MinimumCycles must both be positive."
}

$databaseBefore = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
$workbookBefore = (Get-FileHash -LiteralPath $workbookPath -Algorithm SHA256).Hash.ToLowerInvariant()
New-Item -ItemType Directory -Force -Path $EvidenceDirectory | Out-Null
$outputPath = Join-Path $EvidenceDirectory "clinical_shadow_resilience.json"
try {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
    Push-Location (Join-Path $repoRoot "backend")
    try {
        & $PythonPath "scripts\corti_parity\run_clinical_shadow_resilience.py" `
            --report $outputPath `
            --soak-seconds $SoakSeconds `
            --minimum-cycles $MinimumCycles `
            --duplicate-deliveries $DuplicateDeliveries
        if ($LASTEXITCODE -ne 0) {
            throw "Clinical shadow resilience run failed."
        }
    }
    finally {
        Pop-Location
    }
    & $PythonPath (
        Join-Path $repoRoot "backend\scripts\corti_parity\verify_clinical_shadow_resilience_evidence.py"
    ) --report $outputPath --minimum-cycles $MinimumCycles --minimum-seconds $SoakSeconds
    if ($LASTEXITCODE -ne 0) {
        throw "Clinical shadow resilience evidence validation failed."
    }
    $databaseAfter = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $workbookAfter = (Get-FileHash -LiteralPath $workbookPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($databaseBefore -ne $databaseAfter) {
        throw "Protected database changed during resilience validation."
    }
    if ($workbookBefore -ne $workbookAfter) {
        throw "Authorized workbook changed during resilience validation."
    }
    Write-Host "Clinical shadow resilience evidence passed: $outputPath"
}
finally {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
}
