"""Safety control-flow checks for the strict external semantic runner."""

from pathlib import Path


RUNNER = (
    Path(__file__).resolve().parents[4]
    / "scripts"
    / "release"
    / "run-agent-hub-external-semantic-e2e.ps1"
)


def _runner_text() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_backend_is_stopped_before_temporary_credential_scan() -> None:
    text = _runner_text()
    finally_block = text.split("\nfinally {", 1)[1]

    stop_index = finally_block.index("Stop-Process -Id $server.Id -Force")
    output_scan_index = finally_block.index(
        "Assert-CredentialAbsent -RootPath $resolvedOutputRoot"
    )
    temp_scan_index = finally_block.index(
        "Assert-CredentialAbsent -RootPath $taskTemp"
    )

    assert stop_index < output_scan_index < temp_scan_index


def test_scan_distinguishes_detection_from_incomplete_io() -> None:
    text = _runner_text()

    assert "CREDENTIAL_DETECTED:" in text
    assert "CREDENTIAL_SCAN_IO_ERROR:" in text
    assert "Credential material was detected;" in text
    assert "Credential scan could not complete;" in text


def test_scan_failure_does_not_mask_primary_e2e_failure() -> None:
    text = _runner_text()

    assert "$executionSucceeded = $false" in text
    assert "$executionSucceeded = $true" in text
    assert "if ($executionSucceeded)" in text
    assert "The primary E2E failure remains authoritative." in text


def test_primary_failure_persists_content_free_backend_diagnostic() -> None:
    text = _runner_text()

    assert "external_semantic_e2e_failure.json" in text
    assert 'execution_phase = $executionPhase' in text
    assert 'backend_exit_code = $backendExitCode' in text
    assert 'credential_value_recorded = $false' in text
    assert (
        'diagnostic_content_scope = "bounded_first_line_credential_redacted_error_and_stderr_tail"'
        in text
    )
    assert '$safeFailureMessage.Replace(' in text
    assert '$safeFailureMessage -split "`r?`n", 2' in text
    assert "[structured details omitted]" in text
    assert "$safeFailureMessage.Length -gt 1000" in text
    assert "$safeServerStderrTail.Length -gt 8000" in text


def test_large_artifacts_are_validated_by_python_not_winps_json_parser() -> None:
    text = _runner_text()

    assert "validate_agent_hub_external_artifacts.py" in text
    assert "$artifactValidation.valid" in text
    assert "Windows PowerShell 5.1" in text
    assert "$adversarial = Get-Content" not in text


def test_source_artifact_hashing_does_not_require_get_file_hash_cmdlet() -> None:
    text = _runner_text()

    assert "function Get-Sha256Hex" in text
    assert "[System.Security.Cryptography.SHA256]::Create()" in text
    assert "sha256 = Get-Sha256Hex -LiteralPath $path" in text
    assert "Get-FileHash" not in text
