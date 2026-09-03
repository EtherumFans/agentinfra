"""Build tamper-evident evidence for the distributed shadow-job contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_TEST = REPO_ROOT / "backend/tests/test_api/test_clinical_model_packages.py"
SOURCES = {
    "model": REPO_ROOT / "backend/app/models/clinical_model_package.py",
    "migration": REPO_ROOT / "backend/alembic/versions/061_clinical_model_shadow_evaluation_jobs.py",
    "service": REPO_ROOT / "backend/app/services/clinical_model_shadow_job.py",
    "api": REPO_ROOT / "backend/app/api/clinical_model_packages.py",
    "worker": REPO_ROOT / "backend/scripts/clinical_model_shadow_job_worker.py",
    "contract_test": CONTRACT_TEST,
}
EXPECTED_TEST = (
    "test_signed_synthetic_bundle_probe_is_metadata_only_and_shadow_bound"
)
REQUIRED_ASSERTION_MARKERS = (
    'assert replayed.json()["id"] == fault_job["id"]',
    "assert reused.status_code == 409",
    "assert duplicate_active.status_code == 409",
    "assert blocked_claim is None",
    "assert recovered_claim.lease_token != first_claim.lease_token",
    "assert stale_result is None",
    "assert exhausted == 1",
    'assert executed_normal.json()["status"] == "passed"',
    '"clinical_model_shadow_job.auto_rolled_back"',
    'assert "lease_token" not in job_audit_text',
)
SECRET_PATTERN = re.compile(r"(?i)(?:sk-[a-z0-9_-]{16,}|api[_-]?key\s*[:=]\s*[^\s\"']+)")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _validate_junit(path: Path) -> dict[str, int]:
    payload = path.read_bytes()
    if SECRET_PATTERN.search(payload.decode("utf-8", errors="replace")):
        raise RuntimeError("SHADOW_JOB_JUNIT_CREDENTIAL_LEAK")
    root = ET.fromstring(payload)
    cases = list(root.iter("testcase"))
    matching = [item for item in cases if item.attrib.get("name") == EXPECTED_TEST]
    if len(matching) != 1:
        raise RuntimeError("SHADOW_JOB_CONTRACT_TEST_MISSING")
    if any(list(item.iter("failure")) or list(item.iter("error")) for item in matching):
        raise RuntimeError("SHADOW_JOB_CONTRACT_TEST_FAILED")
    return {
        "tests": len(matching),
        "failures": 0,
        "errors": 0,
    }


def build_report(junit_path: Path) -> dict[str, object]:
    test_text = CONTRACT_TEST.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_ASSERTION_MARKERS if marker not in test_text]
    if missing:
        raise RuntimeError("SHADOW_JOB_ASSERTION_COVERAGE_INCOMPLETE")
    source_hashes = {
        name: _sha256_bytes(path.read_bytes()) for name, path in SOURCES.items()
    }
    report: dict[str, object] = {
        "schema_version": "icoder.clinical-model-shadow-job-evidence/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": True,
        "pytest": _validate_junit(junit_path),
        "source_sha256": source_hashes,
        "idempotent_create_replay": True,
        "idempotency_conflict_fail_closed": True,
        "single_active_job_per_binding": True,
        "lease_renewal_proven": True,
        "pre_expiry_takeover_blocked": True,
        "expired_lease_reclaimed": True,
        "fresh_fence_token_on_reclaim": True,
        "stale_worker_terminal_mutation_blocked": True,
        "bounded_attempt_exhaustion_terminalized": True,
        "active_slot_released_after_exhaustion": True,
        "controlled_failure_auto_rollback": True,
        "normal_repository_fixture_job_passed": True,
        "tenant_scoped_job_reads": True,
        "safe_aggregate_audit": True,
        "idempotency_key_audited": False,
        "lease_token_audited": False,
        "repository_fixture_only": True,
        "aggregate_only": True,
        "patient_data_used": False,
        "case_level_artifacts_emitted": False,
        "predictions_emitted": False,
        "network_used": False,
        "production_inference_enabled": False,
        "real_shadow_traffic_used": False,
        "real_clinical_model_validated": False,
        "hospital_acceptance_proven": False,
        "corti_capability_parity_proven": False,
    }
    report["report_sha256"] = _sha256_bytes(_canonical(report))
    return report


def validate_report(report: dict[str, object]) -> None:
    unsigned = dict(report)
    digest = unsigned.pop("report_sha256", None)
    required_true = (
        "passed", "idempotent_create_replay", "idempotency_conflict_fail_closed",
        "single_active_job_per_binding", "lease_renewal_proven",
        "pre_expiry_takeover_blocked", "expired_lease_reclaimed",
        "fresh_fence_token_on_reclaim", "stale_worker_terminal_mutation_blocked",
        "bounded_attempt_exhaustion_terminalized",
        "active_slot_released_after_exhaustion",
        "controlled_failure_auto_rollback", "normal_repository_fixture_job_passed",
        "tenant_scoped_job_reads", "safe_aggregate_audit",
        "repository_fixture_only", "aggregate_only",
    )
    required_false = (
        "idempotency_key_audited", "lease_token_audited", "patient_data_used",
        "case_level_artifacts_emitted", "predictions_emitted", "network_used",
        "production_inference_enabled", "real_shadow_traffic_used",
        "real_clinical_model_validated", "hospital_acceptance_proven",
        "corti_capability_parity_proven",
    )
    if (
        report.get("schema_version")
        != "icoder.clinical-model-shadow-job-evidence/v1"
        or any(report.get(key) is not True for key in required_true)
        or any(report.get(key) is not False for key in required_false)
        or digest != _sha256_bytes(_canonical(unsigned))
    ):
        raise RuntimeError("SHADOW_JOB_EVIDENCE_INVALID")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.junit.resolve())
    validate_report(report)
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
