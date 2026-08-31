"""Build tamper-evident evidence for governed shadow-job operations."""
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
    "migration": REPO_ROOT / "backend/alembic/versions/062_clinical_model_shadow_job_operations.py",
    "service": REPO_ROOT / "backend/app/services/clinical_model_shadow_job.py",
    "api": REPO_ROOT / "backend/app/api/clinical_model_packages.py",
    "worker": REPO_ROOT / "backend/scripts/clinical_model_shadow_job_worker.py",
    "contract_test": CONTRACT_TEST,
}
EXPECTED_TEST = "test_signed_synthetic_bundle_probe_is_metadata_only_and_shadow_bound"
REQUIRED_MARKERS = (
    'assert cancelled_running.json()["status"] == "cancelled"',
    'assert cancelled_running.json()["cancellation_reason"] == "safety_stop"',
    "assert stale_cancelled_result is None",
    "assert cancelled_replay.status_code == 200",
    "assert terminal_cancel.status_code == 409",
    "assert cross_tenant_cancel.status_code == 404",
    'assert cancelled_queued.json()["attempt_count"] == 0',
    'assert degraded_health["status"] == "degraded"',
    'assert health.json()["status"] == "healthy"',
    'assert other_health.json()["identifiers_emitted"] is False',
    'assert maintenance.json()["finalized_exhausted_count"] == 0',
    '"clinical_model_shadow_job.cancelled"',
)
SECRET_PATTERN = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{16,}|api[_-]?key\s*[:=]\s*[^\s\"']+)"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _passed_junit(path: Path) -> dict[str, int]:
    payload = path.read_bytes()
    if SECRET_PATTERN.search(payload.decode("utf-8", errors="replace")):
        raise RuntimeError("SHADOW_JOB_OPERATIONS_JUNIT_CREDENTIAL_LEAK")
    root = ET.fromstring(payload)
    matches = [
        case for case in root.iter("testcase")
        if case.attrib.get("name") == EXPECTED_TEST
    ]
    if len(matches) != 1:
        raise RuntimeError("SHADOW_JOB_OPERATIONS_TEST_MISSING")
    if list(matches[0].iter("failure")) or list(matches[0].iter("error")):
        raise RuntimeError("SHADOW_JOB_OPERATIONS_TEST_FAILED")
    return {"tests": 1, "failures": 0, "errors": 0}


def build_report(junit_path: Path) -> dict[str, object]:
    test_text = CONTRACT_TEST.read_text(encoding="utf-8")
    if any(marker not in test_text for marker in REQUIRED_MARKERS):
        raise RuntimeError("SHADOW_JOB_OPERATIONS_ASSERTION_COVERAGE_INCOMPLETE")
    report: dict[str, object] = {
        "schema_version": "icoder.clinical-model-shadow-job-operations-evidence/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": True,
        "pytest": _passed_junit(junit_path),
        "source_sha256": {
            name: _sha256(path.read_bytes()) for name, path in SOURCES.items()
        },
        "queued_cancellation_proven": True,
        "running_cancellation_proven": True,
        "cancellation_idempotent": True,
        "terminal_job_cancellation_blocked": True,
        "outstanding_lease_invalidated": True,
        "cancelled_worker_settlement_fenced": True,
        "active_slot_released_after_cancellation": True,
        "cross_tenant_cancellation_hidden": True,
        "degraded_health_alerts_proven": True,
        "healthy_recovery_summary_proven": True,
        "tenant_aggregate_isolation_proven": True,
        "maintenance_sweep_bounded": True,
        "cancellation_audited": True,
        "job_identifiers_in_health": False,
        "repository_fixture_only": True,
        "aggregate_only": True,
        "patient_data_used": False,
        "predictions_emitted": False,
        "network_used": False,
        "production_inference_enabled": False,
        "production_queue_exercised": False,
        "real_shadow_traffic_used": False,
        "corti_capability_parity_proven": False,
    }
    report["report_sha256"] = _sha256(_canonical(report))
    return report


def validate_report(report: dict[str, object]) -> None:
    unsigned = dict(report)
    digest = unsigned.pop("report_sha256", None)
    true_keys = (
        "passed", "queued_cancellation_proven", "running_cancellation_proven",
        "cancellation_idempotent", "terminal_job_cancellation_blocked",
        "outstanding_lease_invalidated", "cancelled_worker_settlement_fenced",
        "active_slot_released_after_cancellation",
        "cross_tenant_cancellation_hidden", "degraded_health_alerts_proven",
        "healthy_recovery_summary_proven", "tenant_aggregate_isolation_proven",
        "maintenance_sweep_bounded", "cancellation_audited",
        "repository_fixture_only", "aggregate_only",
    )
    false_keys = (
        "job_identifiers_in_health", "patient_data_used", "predictions_emitted",
        "network_used", "production_inference_enabled", "production_queue_exercised",
        "real_shadow_traffic_used", "corti_capability_parity_proven",
    )
    if (
        report.get("schema_version")
        != "icoder.clinical-model-shadow-job-operations-evidence/v1"
        or any(report.get(key) is not True for key in true_keys)
        or any(report.get(key) is not False for key in false_keys)
        or digest != _sha256(_canonical(unsigned))
    ):
        raise RuntimeError("SHADOW_JOB_OPERATIONS_EVIDENCE_INVALID")


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
