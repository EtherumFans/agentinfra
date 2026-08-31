"""Build tamper-evident evidence for the shadow operations control plane."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_TEST = ROOT / "backend/tests/test_api/test_clinical_model_packages.py"
UNIT_TEST = ROOT / "backend/tests/unit/app/services/test_clinical_model_shadow_operations.py"
SOURCES = {
    "model": ROOT / "backend/app/models/clinical_model_package.py",
    "migration": ROOT / "backend/alembic/versions/063_clinical_model_shadow_operations_control_plane.py",
    "job_service": ROOT / "backend/app/services/clinical_model_shadow_job.py",
    "queue_adapter": ROOT / "backend/app/services/clinical_model_shadow_queue.py",
    "scheduler": ROOT / "backend/app/services/clinical_model_shadow_scheduler.py",
    "metrics": ROOT / "backend/app/services/clinical_model_shadow_observability.py",
    "api": ROOT / "backend/app/api/clinical_model_packages.py",
    "worker": ROOT / "backend/scripts/clinical_model_shadow_job_worker.py",
    "scheduler_cli": ROOT / "backend/scripts/clinical_model_shadow_scheduler.py",
    "contract_test": CONTRACT_TEST,
    "unit_test": UNIT_TEST,
}
EXPECTED_TESTS = {
    "test_signed_synthetic_bundle_probe_is_metadata_only_and_shadow_bound",
    "test_database_queue_is_phi_free_durable_fallback",
    "test_queue_configuration_fails_closed",
    "test_shadow_metrics_are_bounded_and_low_cardinality",
    "test_process_metrics_requires_authentication",
    "test_process_metrics_rejects_tenant_coder",
    "test_process_metrics_accepts_rotatable_monitoring_token",
}
MARKERS = (
    'assert dead_letter["status"] == "available"',
    'assert cross_tenant_replay.status_code == 404',
    'assert stale_snapshot_replay.status_code == 409',
    'assert replay_idempotent.json()["id"] == replay_job["id"]',
    'assert replay_conflict.status_code == 409',
    'assert stale_scheduler_completion is False',
    'assert scheduler_completed is True',
    'assert {item["state"] for item in alerts.json()["items"]} == {"resolved"}',
    '"clinical_model_shadow_job.dead_lettered"',
    '"clinical_model_shadow_job.dead_letter_replayed"',
)
SECRET = re.compile(r"(?i)(?:sk-[a-z0-9_-]{16,}|api[_-]?key\s*[:=]\s*[^\s\"']+)")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _junit(path: Path) -> dict[str, int]:
    payload = path.read_bytes()
    if SECRET.search(payload.decode("utf-8", errors="replace")):
        raise RuntimeError("SHADOW_CONTROL_PLANE_JUNIT_CREDENTIAL_LEAK")
    root = ET.fromstring(payload)
    cases = list(root.iter("testcase"))
    names = {case.attrib.get("name", "") for case in cases}
    if not EXPECTED_TESTS <= names:
        raise RuntimeError("SHADOW_CONTROL_PLANE_TEST_COVERAGE_INCOMPLETE")
    failures = sum(1 for case in cases if list(case.iter("failure")))
    errors = sum(1 for case in cases if list(case.iter("error")))
    if failures or errors:
        raise RuntimeError("SHADOW_CONTROL_PLANE_TEST_FAILED")
    return {"tests": len(cases), "failures": failures, "errors": errors}


def build_report(junit: Path) -> dict[str, object]:
    text = CONTRACT_TEST.read_text(encoding="utf-8")
    if any(marker not in text for marker in MARKERS):
        raise RuntimeError("SHADOW_CONTROL_PLANE_ASSERTION_COVERAGE_INCOMPLETE")
    report: dict[str, object] = {
        "schema_version": "icoder.clinical-shadow-control-plane-evidence/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": True,
        "pytest": _junit(junit),
        "source_sha256": {name: _sha(path.read_bytes()) for name, path in SOURCES.items()},
        "database_is_durable_queue_authority": True,
        "queue_signal_loss_tolerated": True,
        "queue_adapter_fails_closed": True,
        "dead_letter_creation_proven": True,
        "dead_letter_replay_idempotent": True,
        "dead_letter_cross_tenant_hidden": True,
        "dead_letter_snapshot_drift_blocked": True,
        "scheduler_generation_fencing_proven": True,
        "persistent_alert_fire_and_resolution_proven": True,
        "process_metrics_low_cardinality": True,
        "aggregate_only": True,
        "patient_data_used": False,
        "patient_metric_labels_present": False,
        "production_broker_exercised": False,
        "external_alert_delivery_exercised": False,
        "real_shadow_traffic_used": False,
        "production_inference_enabled": False,
        "corti_capability_parity_proven": False,
    }
    report["report_sha256"] = _sha(_canonical(report))
    return report


def validate(report: dict[str, object]) -> None:
    unsigned = dict(report)
    digest = unsigned.pop("report_sha256", None)
    true_keys = (
        "passed", "database_is_durable_queue_authority", "queue_signal_loss_tolerated",
        "queue_adapter_fails_closed", "dead_letter_creation_proven",
        "dead_letter_replay_idempotent", "dead_letter_cross_tenant_hidden",
        "dead_letter_snapshot_drift_blocked", "scheduler_generation_fencing_proven",
        "persistent_alert_fire_and_resolution_proven", "process_metrics_low_cardinality",
        "aggregate_only",
    )
    false_keys = (
        "patient_data_used", "patient_metric_labels_present",
        "production_broker_exercised", "external_alert_delivery_exercised",
        "real_shadow_traffic_used", "production_inference_enabled",
        "corti_capability_parity_proven",
    )
    if (
        report.get("schema_version") != "icoder.clinical-shadow-control-plane-evidence/v1"
        or any(report.get(key) is not True for key in true_keys)
        or any(report.get(key) is not False for key in false_keys)
        or digest != _sha(_canonical(unsigned))
    ):
        raise RuntimeError("SHADOW_CONTROL_PLANE_EVIDENCE_INVALID")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.junit.resolve())
    validate(report)
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
