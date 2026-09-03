[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [string]$OutputRoot = "reports/agent_hub/external_semantic_e2e_phase_20260825",
    [ValidateRange(90, 900)]
    [int]$StartupTimeoutSeconds = 240,
    [switch]$IncludeClinicalCalibration,
    [string]$BlindReviewPacketPath = "",
    [string]$ReviewerAResponsePath = "",
    [string]$ReviewerBResponsePath = "",
    [string]$GoldAdjudicationPath = ""
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
$reviewInputValues = @(
    $BlindReviewPacketPath,
    $ReviewerAResponsePath,
    $ReviewerBResponsePath,
    $GoldAdjudicationPath
)
$reviewInputCount = @($reviewInputValues | Where-Object {
    -not [string]::IsNullOrWhiteSpace($_)
}).Count
if ($reviewInputCount -notin @(0, 4)) {
    throw "All four independent gold review paths must be supplied together."
}
if ($reviewInputCount -eq 4 -and -not $IncludeClinicalCalibration) {
    throw "Independent gold review paths require -IncludeClinicalCalibration."
}
$resolvedReviewInputs = @{}
if ($reviewInputCount -eq 4) {
    $reviewInputMap = @{
        packet = $BlindReviewPacketPath
        review_a = $ReviewerAResponsePath
        review_b = $ReviewerBResponsePath
        adjudication = $GoldAdjudicationPath
    }
    foreach ($name in $reviewInputMap.Keys) {
        $value = [string]$reviewInputMap[$name]
        $resolved = if ([System.IO.Path]::IsPathRooted($value)) {
            [System.IO.Path]::GetFullPath($value)
        } else {
            [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $value))
        }
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "Independent gold review artifact not found: ${name}."
        }
        $resolvedReviewInputs[$name] = $resolved
    }
}
$credential = [Environment]::GetEnvironmentVariable("ICODER_CREDENTIAL_LLM", "Process")
if ([string]::IsNullOrWhiteSpace($credential)) {
    throw "ICODER_CREDENTIAL_LLM is not set in this PowerShell process."
}
if ($credential -match '<新密钥>|test-fake|placeholder|changeme') {
    throw "ICODER_CREDENTIAL_LLM contains a placeholder or test credential."
}

$tempRoot = [System.IO.Path]::GetFullPath("C:\Temp")
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$taskTemp = Join-Path $tempRoot ("icoder-agent-external-e2e-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $taskTemp | Out-Null
$databasePath = Join-Path $taskTemp "agent-external-e2e.db"
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
        throw "Python command failed with exit code ${LASTEXITCODE}."
    }
}

function Invoke-PythonCalibration {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & $PythonPath @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -notin @(0, 2)) {
        throw "Clinical calibration runner failed with exit code ${exitCode}."
    }
    return $exitCode
}

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    $stream = [System.IO.File]::OpenRead($LiteralPath)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash($stream)
        return ([System.BitConverter]::ToString($digest)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

function Assert-CredentialAbsent {
    param([Parameter(Mandatory = $true)][string]$RootPath)
    if (-not (Test-Path -LiteralPath $RootPath)) { return }
    foreach ($file in Get-ChildItem -LiteralPath $RootPath -Recurse -File) {
        try {
            $content = [System.IO.File]::ReadAllText($file.FullName)
        }
        catch [System.Text.DecoderFallbackException] {
            continue
        }
        catch {
            throw "CREDENTIAL_SCAN_IO_ERROR:$($file.FullName):$($_.Exception.GetType().Name)"
        }
        if ($content.Contains($credential, [System.StringComparison]::Ordinal)) {
            # Never include the credential itself in an exception or log.
            throw "CREDENTIAL_DETECTED:$($file.FullName)"
        }
    }
}

$serverPort = Get-FreePort
$baseUrl = "http://127.0.0.1:$serverPort"
$server = $null
$executionSucceeded = $false
$executionPhase = "initialization"
$credentialScanFailureKind = $null
$credentialScanFailure = $null
$agentIds = @(
    "claim-check",
    "clinical-documentation-improvement-agent",
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
    "medical-coding-agent",
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
$agentIdsArgument = $agentIds -join ","
$agentCount = $agentIds.Count
if ($agentCount -ne 26) {
    throw "Strict external semantic runner must enumerate exactly 26 visible Agents."
}
$stabilityExpected = $agentCount * 2 * 3
$environmentNames = @(
    "DATABASE_URL", "ICODER_DATABASE_URL", "APP_ENV", "SEED_ON_STARTUP",
    "ICODER_CREDENTIAL_LLM", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
    "LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL",
    "ICODER_ALLOW_EXTERNAL_LLM", "ICODER_ENABLE_EXTERNAL_LLM",
    "ICODER_DISABLE_NATIVE_MEDCODER", "ICODER_ENABLE_LOCAL_STT",
    "ICODER_MODEL_LIVE_CANARY_ENABLED", "ICODER_ALLOW_DEGRADED_NO_KEY",
    "ICODER_SECRET_KEY", "ICODER_ENVIRONMENT", "ICODER_REGION",
    "ICODER_E2E_BEARER", "ICODER_E2E_USERNAME", "ICODER_E2E_PASSWORD",
    "ICODER_DISABLE_AUTH_FOR_TESTS", "PYTHONPATH", "NO_PROXY", "no_proxy"
)
$credentialEnvironmentNames = @(
    "ICODER_CREDENTIAL_LLM", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    if ($name -in $credentialEnvironmentNames) {
        $previousEnvironment[$name] = $null
    } else {
        $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }
}

$examplesDir = Join-Path $resolvedOutputRoot "examples"
$adversarialDir = Join-Path $resolvedOutputRoot "adversarial"
$referenceDir = Join-Path $resolvedOutputRoot "reference"
$stabilityDir = Join-Path $resolvedOutputRoot "stability"
$bundleDir = Join-Path $resolvedOutputRoot "bundle"
$matrixDir = Join-Path $resolvedOutputRoot "runtime-matrix"
$clinicalCalibrationDir = Join-Path $resolvedOutputRoot "clinical-calibration"

try {
    New-Item -ItemType Directory -Path $resolvedOutputRoot -Force | Out-Null
    $databaseUrl = "sqlite+aiosqlite:///" + $databasePath.Replace("\", "/")
    $env:DATABASE_URL = $databaseUrl
    $env:ICODER_DATABASE_URL = $databaseUrl
    $env:APP_ENV = "local"
    $env:SEED_ON_STARTUP = "0"
    $env:ICODER_CREDENTIAL_LLM = $credential
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:ICODER_E2E_BEARER -ErrorAction SilentlyContinue
    Remove-Item Env:ICODER_E2E_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:ICODER_E2E_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:ICODER_DISABLE_AUTH_FOR_TESTS -ErrorAction SilentlyContinue
    $env:LLM_PROVIDER = "deepseek"
    $env:LLM_BASE_URL = "https://api.deepseek.com/v1"
    $env:LLM_MODEL = "deepseek-chat"
    $env:ICODER_ALLOW_EXTERNAL_LLM = "true"
    $env:ICODER_ENABLE_EXTERNAL_LLM = "true"
    $env:ICODER_DISABLE_NATIVE_MEDCODER = "true"
    $env:ICODER_ENABLE_LOCAL_STT = "false"
    $env:ICODER_MODEL_LIVE_CANARY_ENABLED = "false"
    $env:ICODER_ALLOW_DEGRADED_NO_KEY = "0"
    $env:ICODER_ENVIRONMENT = "cn"
    $env:ICODER_REGION = "cn-external-agent-e2e"
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
    # A cold Windows startup can legitimately spend well over 90 seconds in
    # migrations/imports when another test process is active. The regression
    # uses an isolated DB and port, so allow a bounded four-minute readiness
    # window before classifying startup as failed.
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
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
        throw "Temporary external Agent Hub Uvicorn did not become ready."
    }

    Push-Location $backendRoot
    try {
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/run_agent_hub_examples_e2e.py",
            "--base-url", $baseUrl,
            "--agents-dir", $agentsDir,
            "--out-dir", $examplesDir,
            "--agent-ids", $agentIdsArgument,
            "--delay", "1", "--force", "--allow-self-register"
        )
        $executionPhase = "happy_complete"
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/run_agent_hub_adversarial_e2e.py",
            "--base-url", $baseUrl,
            "--agents-dir", $agentsDir,
            "--out-dir", $adversarialDir,
            "--agent-ids", $agentIdsArgument,
            "--delay", "1", "--force", "--allow-self-register"
        )
        $executionPhase = "adversarial_complete"
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/run_agent_hub_reference_quality_replay.py",
            "--agents-dir", $agentsDir,
            "--responses-dir", (Join-Path $examplesDir "responses"),
            "--source-report", (Join-Path $examplesDir "agent_hub_examples_e2e.json"),
            "--out-dir", $referenceDir,
            "--agent-ids", $agentIdsArgument
        )
        $executionPhase = "reference_complete"
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/run_agent_hub_stability_benchmark.py",
            "--base-url", $baseUrl,
            "--agents-dir", $agentsDir,
            "--out-dir", $stabilityDir,
            "--agent-ids", $agentIdsArgument,
            "--repetitions", "3", "--delay", "1", "--force",
            "--agent-p95-budget", "clinical-documentation-improvement-agent=30",
            "--agent-p95-budget", "medical-coding-agent=10",
            "--allow-self-register",
            "--happy-seed-dir", $examplesDir,
            "--adversarial-seed-dir", $adversarialDir
        )
        $executionPhase = "stability_complete"
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/build_agent_hub_semantic_evidence_bundle.py",
            "--examples", (Join-Path $examplesDir "agent_hub_examples_e2e.json"),
            "--adversarial", (Join-Path $adversarialDir "agent_hub_adversarial_e2e.json"),
            "--reference", (Join-Path $referenceDir "agent_hub_reference_quality_replay.json"),
            "--stability", (Join-Path $stabilityDir "agent_hub_stability_benchmark.json"),
            "--agents-dir", $agentsDir,
            "--out-dir", $bundleDir
        )
        $executionPhase = "semantic_bundle_complete"
        Invoke-PythonChecked -Arguments @(
            "scripts/corti_parity/build_agent_hub_runtime_matrix.py",
            "--agents-dir", $agentsDir,
            "--output-dir", $matrixDir,
            "--assert-visible-ready",
            "--semantic-evidence", (Join-Path $bundleDir "agent_hub_semantic_evidence_bundle.json")
        )
        $executionPhase = "runtime_matrix_complete"
        $clinicalCalibrationExitCode = $null
        if ($IncludeClinicalCalibration) {
            $clinicalCalibrationArguments = @(
                "scripts/corti_parity/run_agent_hub_clinical_calibration_e2e.py",
                "--base-url", $baseUrl,
                "--agents-dir", $agentsDir,
                "--out-dir", $clinicalCalibrationDir,
                "--delay", "1",
                "--allow-self-register",
                "--acknowledge-external-provider-egress"
            )
            if ($reviewInputCount -eq 4) {
                $clinicalCalibrationArguments += @(
                    "--blind-review-packet", $resolvedReviewInputs.packet,
                    "--review-a", $resolvedReviewInputs.review_a,
                    "--review-b", $resolvedReviewInputs.review_b,
                    "--gold-adjudication", $resolvedReviewInputs.adjudication
                )
            }
            $clinicalCalibrationExitCode = Invoke-PythonCalibration -Arguments $clinicalCalibrationArguments
        }
    }
    finally { Pop-Location }

    $executionPhase = "artifact_validation"
    $examplesPath = Join-Path $examplesDir "agent_hub_examples_e2e.json"
    $adversarialPath = Join-Path $adversarialDir "agent_hub_adversarial_e2e.json"
    $referencePath = Join-Path $referenceDir "agent_hub_reference_quality_replay.json"
    $stabilityPath = Join-Path $stabilityDir "agent_hub_stability_benchmark.json"
    $bundlePath = Join-Path $bundleDir "agent_hub_semantic_evidence_bundle.json"
    $matrixPath = Join-Path $matrixDir "agent_hub_runtime_matrix.json"
    $clinicalCalibrationPath = Join-Path $clinicalCalibrationDir "agent_hub_clinical_calibration_e2e.json"
    $artifactValidationPath = Join-Path $resolvedOutputRoot "artifact_validation.json"
    $artifactValidationArguments = @(
        "scripts/corti_parity/validate_agent_hub_external_artifacts.py",
        "--examples", $examplesPath,
        "--adversarial", $adversarialPath,
        "--reference", $referencePath,
        "--stability", $stabilityPath,
        "--bundle", $bundlePath,
        "--matrix", $matrixPath,
        "--expected-agent-count", [string]$agentCount,
        "--stability-expected", [string]$stabilityExpected,
        "--output", $artifactValidationPath
    )
    if ($IncludeClinicalCalibration) {
        if (-not (Test-Path -LiteralPath $clinicalCalibrationPath)) {
            throw "Clinical calibration report was not generated."
        }
        $artifactValidationArguments += @(
            "--clinical-calibration", $clinicalCalibrationPath
        )
    }
    Push-Location $backendRoot
    try {
        Invoke-PythonChecked -Arguments $artifactValidationArguments
    }
    finally { Pop-Location }
    # This report is deliberately small and content-free, so Windows PowerShell 5.1
    # can parse it even when the source reports are deeply
    # nested and hundreds of kilobytes large.
    $artifactValidation = Get-Content -Raw -LiteralPath $artifactValidationPath | ConvertFrom-Json
    if (-not $artifactValidation.valid) {
        throw "Strict external Agent Hub artifact validation failed."
    }
    $clinicalCalibrationSummary = $artifactValidation.clinical_calibration
    $executionPhase = "post_artifact_backend_liveness"
    $server.Refresh()
    if ($server.HasExited) {
        throw "Backend exited during external Agent Hub E2E."
    }
    $executionPhase = "top_level_evidence"
    $sourceArtifacts = [ordered]@{}
    foreach ($path in @(
        $examplesPath, $adversarialPath, $referencePath,
        $stabilityPath, $bundlePath, $matrixPath
    )) {
        $sourceArtifacts[[System.IO.Path]::GetFileName($path)] = @{
            path = $path
            sha256 = Get-Sha256Hex -LiteralPath $path
        }
    }
    if ($IncludeClinicalCalibration) {
        $sourceArtifacts[[System.IO.Path]::GetFileName($clinicalCalibrationPath)] = @{
            path = $clinicalCalibrationPath
            sha256 = Get-Sha256Hex -LiteralPath $clinicalCalibrationPath
        }
    }
    $evidence = [ordered]@{
        schema_version = "icoder.agent-hub-external-semantic-e2e-phase/v1"
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        status = "passed"
        transport = "real_loopback_http"
        evaluated_agent_ids = $agentIds
        external_model_agent_ids = @(
            "clinical-documentation-improvement-agent",
            "medical-coding-agent"
        )
        happy = @{ passed = $agentCount; failed = 0 }
        adversarial = @{ passed = $agentCount; failed = 0 }
        reference = @{ passed = $agentCount; failed = 0 }
        stability = @{ passed = $stabilityExpected; failed = 0; repetitions = 3 }
        runtime_matrix = @{
            strict_26_agent_semantic_verified = 26
            production_ready_verified = 0
        }
        clinical_calibration = @{
            included = [bool]$IncludeClinicalCalibration
            expected_serial_invocations = 50
            execution_valid = if ($IncludeClinicalCalibration) {
                [bool]$clinicalCalibrationSummary.execution_valid
            } else { $false }
            calibration_targets_passed = if ($IncludeClinicalCalibration) {
                [bool]$clinicalCalibrationSummary.calibration_targets_passed
            } else { $false }
            failed_targets = if ($IncludeClinicalCalibration) {
                @($clinicalCalibrationSummary.failed_targets)
            } else { @() }
            independent_clinical_gold_used = if ($IncludeClinicalCalibration) {
                [bool]$clinicalCalibrationSummary.independent_gold_used
            } else { $false }
            production_ready_proven = $false
        }
        source_artifacts = $sourceArtifacts
        temporary_database = "created_migrated_removed"
        real_llm_used = $true
        credential_persisted = $false
        synthetic_pack_owned_cases_only = $true
        independent_clinical_gold_used = if ($IncludeClinicalCalibration) {
            [bool]$clinicalCalibrationSummary.independent_gold_used
        } else { $false }
        corti_parity_proven = $false
        hospital_acceptance_proven = $false
    }
    $evidencePath = Join-Path $resolvedOutputRoot "external_semantic_e2e_evidence.json"
    [System.IO.File]::WriteAllText(
        $evidencePath,
        ($evidence | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
    $evidence | ConvertTo-Json -Depth 8
    if (
        $IncludeClinicalCalibration -and
        -not $clinicalCalibrationSummary.calibration_targets_passed
    ) {
        throw "Clinical calibration completed with quality gaps; inspect the generated report."
    }
    $executionSucceeded = $true
    $executionPhase = "complete"
}
catch {
    $primaryFailure = $_
    try {
        New-Item -ItemType Directory -Path $resolvedOutputRoot -Force | Out-Null
        $backendExited = $false
        $backendExitCode = $null
        if ($null -ne $server) {
            $server.Refresh()
            $backendExited = [bool]$server.HasExited
            if ($backendExited) {
                $backendExitCode = $server.ExitCode
            }
        }
        $safeFailureMessage = [string]$primaryFailure.Exception.Message
        if (-not [string]::IsNullOrEmpty($credential)) {
            $safeFailureMessage = $safeFailureMessage.Replace(
                $credential,
                "[REDACTED_CREDENTIAL]"
            )
        }
        # Exception messages from Windows PowerShell's JSON parser can append
        # the complete source document. Persist only a bounded diagnostic
        # headline; never copy a clinical/synthetic payload into failure
        # metadata.
        $safeFailureMessage = ($safeFailureMessage -split "`r?`n", 2)[0]
        $safeFailureMessage = [regex]::Replace(
            $safeFailureMessage,
            '([:]\s*)[\{\[].*$',
            '$1[structured details omitted]'
        )
        if ($safeFailureMessage.Length -gt 1000) {
            $safeFailureMessage = $safeFailureMessage.Substring(0, 1000)
        }
        $safeServerStderrTail = $null
        if (Test-Path -LiteralPath $serverErr) {
            $safeServerStderrTail = (
                Get-Content -LiteralPath $serverErr -Tail 80 | Out-String
            )
            if (-not [string]::IsNullOrEmpty($credential)) {
                $safeServerStderrTail = $safeServerStderrTail.Replace(
                    $credential,
                    "[REDACTED_CREDENTIAL]"
                )
            }
            if ($safeServerStderrTail.Length -gt 8000) {
                $safeServerStderrTail = $safeServerStderrTail.Substring(
                    $safeServerStderrTail.Length - 8000
                )
            }
        }
        $failureEvidence = [ordered]@{
            schema_version = "icoder.agent-hub-external-semantic-e2e-failure/v1"
            generated_at = [DateTimeOffset]::UtcNow.ToString("o")
            status = "failed"
            execution_phase = $executionPhase
            error_type = $primaryFailure.Exception.GetType().Name
            error_message = $safeFailureMessage
            backend_exited = $backendExited
            backend_exit_code = $backendExitCode
            server_stdout_bytes = if (Test-Path -LiteralPath $serverOut) {
                (Get-Item -LiteralPath $serverOut).Length
            } else { $null }
            server_stderr_bytes = if (Test-Path -LiteralPath $serverErr) {
                (Get-Item -LiteralPath $serverErr).Length
            } else { $null }
            server_stderr_tail = $safeServerStderrTail
            credential_value_recorded = $false
            diagnostic_content_scope = "bounded_first_line_credential_redacted_error_and_stderr_tail"
        }
        [System.IO.File]::WriteAllText(
            (Join-Path $resolvedOutputRoot "external_semantic_e2e_failure.json"),
            ($failureEvidence | ConvertTo-Json -Depth 5) + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
    catch {
        # Preserve the primary runner failure even if diagnostic persistence
        # itself is unavailable.
    }
    throw $primaryFailure
}
finally {
    # Stop and reap Uvicorn before inspecting SQLite/WAL/log files. On
    # Windows, scanning while the backend owns those files can raise a sharing
    # violation and used to be misreported as a credential leak.
    if ($null -ne $server) {
        $server.Refresh()
        if (-not $server.HasExited) {
            Stop-Process -Id $server.Id -Force
            Wait-Process -Id $server.Id -Timeout 10 -ErrorAction SilentlyContinue
        }
    }
    try {
        Assert-CredentialAbsent -RootPath $resolvedOutputRoot
        Assert-CredentialAbsent -RootPath $taskTemp
    }
    catch {
        $credentialScanFailure = $_
        if ([string]$_.Exception.Message -like "CREDENTIAL_DETECTED:*") {
            $credentialScanFailureKind = "detected"
        } else {
            $credentialScanFailureKind = "incomplete"
        }
    }
    foreach ($name in $environmentNames) {
        if ($name -in $credentialEnvironmentNames) {
            [Environment]::SetEnvironmentVariable($name, $null, "Process")
        } else {
            [Environment]::SetEnvironmentVariable(
                $name,
                $previousEnvironment[$name],
                "Process"
            )
        }
    }
    $credential = $null
    $previousEnvironment.Clear()
    $resolvedTemp = [System.IO.Path]::GetFullPath($taskTemp)
    $tempLeaf = Split-Path $resolvedTemp -Leaf
    if (
        $resolvedTemp.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        $tempLeaf -like "icoder-agent-external-e2e-*"
    ) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    } else {
        throw "Refusing to clean unexpected Agent Hub E2E temp path: $resolvedTemp"
    }
    if ($null -ne $credentialScanFailure) {
        $scanMessage = if ($credentialScanFailureKind -eq "detected") {
            "Credential material was detected; generated evidence must not be trusted."
        } else {
            "Credential scan could not complete; generated evidence must not be trusted."
        }
        if ($executionSucceeded) {
            throw $scanMessage
        }
        # Preserve the primary E2E failure. The scan problem remains explicit,
        # but must not replace the exception that caused the run to abort.
        Write-Error `
            -Message "$scanMessage The primary E2E failure remains authoritative." `
            -ErrorAction Continue
    }
}
