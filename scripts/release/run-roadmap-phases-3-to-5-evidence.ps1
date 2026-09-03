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
    $EvidenceDirectory = Join-Path $repoRoot "reports\roadmap\phases_3_to_5_$stamp"
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
$phase3Junit = Join-Path $EvidenceDirectory "phase3.xml"
$phase4Junit = Join-Path $EvidenceDirectory "phase4.xml"
$phase5Junit = Join-Path $EvidenceDirectory "phase5.xml"
$offlineReport = Join-Path $EvidenceDirectory "offline_evaluation.json"
$buildStatusPath = Join-Path $EvidenceDirectory "build_status.json"
$outputPath = Join-Path $EvidenceDirectory "roadmap_phases_3_to_5.json"

try {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
    Push-Location $repoRoot
    try {
        & $PythonPath -m pytest -q "backend/tests/unit/app/services/test_clinical_model_infrastructure.py" --junitxml $phase3Junit
        if ($LASTEXITCODE -ne 0) { throw "Phase 3 tests failed." }
        & $PythonPath -m pytest -q "backend/tests/unit/app/services/test_offline_evaluation.py" --junitxml $phase4Junit
        if ($LASTEXITCODE -ne 0) { throw "Phase 4 tests failed." }
        & $PythonPath "backend/scripts/corti_parity/run_agent_hub_offline_evaluation.py" --output $offlineReport
        if ($LASTEXITCODE -ne 0) { throw "Offline evaluation failed." }
        & $PythonPath -m pytest -q `
            "backend/tests/test_api/test_a1b_ae_3_expert_registry.py::test_expert_readiness_is_aggregate_and_secret_free" `
            "backend/tests/test_api/test_v2_stt_real_lifecycle.py::test_stt_readiness_is_scoped_and_truthful" `
            "backend/tests/integration/icoder/a2a/test_agent_connectors.py::test_persistent_memory_consent_encryption_isolation_expiry_and_revoke" `
            --junitxml $phase5Junit
        if ($LASTEXITCODE -ne 0) { throw "Phase 5 backend tests failed." }

        Push-Location "packages/icoder-sdk"
        try { & npm.cmd test; if ($LASTEXITCODE -ne 0) { throw "JavaScript SDK tests failed." } }
        finally { Pop-Location }
        Push-Location "packages/icoder-python"
        try { & $PythonPath -m pytest -q "tests/test_agents_mainline.py" "tests/test_speech_to_text.py"; if ($LASTEXITCODE -ne 0) { throw "Python SDK tests failed." } }
        finally { Pop-Location }
        Push-Location "frontend"
        try { & npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." } }
        finally { Pop-Location }

        $dotnetStatus = "toolchain_unavailable"
        if (Get-Command dotnet -ErrorAction SilentlyContinue) {
            Push-Location "packages/icoder-dotnet"
            try {
                & dotnet test "tests/Icoder.Sdk.Tests/Icoder.Sdk.Tests.csproj" -c Release --nologo
                if ($LASTEXITCODE -ne 0) { throw ".NET SDK tests failed." }
                $dotnetStatus = "passed"
            }
            finally { Pop-Location }
        }
        @{
            javascript_sdk = "passed"
            python_sdk = "passed"
            frontend = "passed"
            dotnet_sdk = $dotnetStatus
        } | ConvertTo-Json | Set-Content -LiteralPath $buildStatusPath -Encoding utf8

        & $PythonPath "backend/scripts/corti_parity/verify_roadmap_phases_3_to_5_evidence.py" `
            --phase3-junit $phase3Junit --phase4-junit $phase4Junit `
            --phase5-junit $phase5Junit --offline-report $offlineReport `
            --build-status $buildStatusPath --output $outputPath
        if ($LASTEXITCODE -ne 0) { throw "Roadmap evidence verification failed." }
    }
    finally { Pop-Location }

    $databaseAfter = (Get-FileHash -LiteralPath $databasePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $workbookAfter = (Get-FileHash -LiteralPath $workbookPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($databaseBefore -ne $databaseAfter) { throw "Protected database changed." }
    if ($workbookBefore -ne $workbookAfter) { throw "Authorized workbook changed." }
    Write-Host "Roadmap phases 3-5 evidence passed: $outputPath"
}
finally {
    [Environment]::SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null, "Process")
}
