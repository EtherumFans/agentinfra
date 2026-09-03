"""Emit development-only aggregate shadow observation and rollback evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.clinical_model_bundle import (  # noqa: E402
    build_canonical_zip,
    verify_bundle_zip_bytes,
)
from app.services.clinical_model_shadow_observation import (  # noqa: E402
    FAULT_MODES,
    build_fault_observation,
    run_verified_shadow_suite,
    validate_shadow_observation,
)


DEFAULT_FIXTURE = BACKEND_ROOT / "tests" / "fixtures" / "clinical_model_bundle_v1"


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_report(fixture: Path = DEFAULT_FIXTURE) -> dict[str, object]:
    archive = build_canonical_zip(fixture)
    verified = verify_bundle_zip_bytes(archive, environment="test")
    passed = run_verified_shadow_suite(verified)
    validate_shadow_observation(passed)
    faults = [
        build_fault_observation(
            fault_mode,
            artifact_sha256=passed["artifact_sha256"],
            model_sha256=passed["model_sha256"],
        )
        for fault_mode in sorted(FAULT_MODES)
    ]
    for observation in faults:
        validate_shadow_observation(observation)
    failed_binding = {
        "package_sha256": passed["artifact_sha256"],
        "model_sha256": passed["model_sha256"],
    }
    previous_binding = {
        "package_sha256": "f" * 64,
        "model_sha256": "e" * 64,
    }
    restored_binding, quarantined_binding = previous_binding, failed_binding
    report: dict[str, object] = {
        "schema_version": "icoder.clinical-model-shadow-observation-evidence/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": True,
        "normal_observation": passed,
        "fault_observations": faults,
        "fault_modes_exercised": sorted(FAULT_MODES),
        "stop_policy_fail_closed": all(item["result"] == "stopped" for item in faults),
        "automatic_rollback_simulated": True,
        "rollback_restored_previous_binding": restored_binding == previous_binding,
        "rollback_quarantined_failed_binding": quarantined_binding == failed_binding,
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
    report["report_sha256"] = _sha256(_canonical_json(report))
    return report


def validate_report(report: dict[str, object]) -> None:
    unsigned = dict(report)
    digest = unsigned.pop("report_sha256", None)
    observations = [report.get("normal_observation"), *(report.get("fault_observations") or [])]
    if (
        report.get("schema_version")
        != "icoder.clinical-model-shadow-observation-evidence/v1"
        or report.get("passed") is not True
        or report.get("stop_policy_fail_closed") is not True
        or report.get("automatic_rollback_simulated") is not True
        or report.get("rollback_restored_previous_binding") is not True
        or report.get("aggregate_only") is not True
        or report.get("patient_data_used") is not False
        or report.get("case_level_artifacts_emitted") is not False
        or report.get("predictions_emitted") is not False
        or report.get("network_used") is not False
        or report.get("production_inference_enabled") is not False
        or report.get("real_shadow_traffic_used") is not False
        or not all(isinstance(item, dict) for item in observations)
        or digest != _sha256(_canonical_json(unsigned))
    ):
        raise RuntimeError("CLINICAL_MODEL_SHADOW_OBSERVATION_EVIDENCE_INVALID")
    for observation in observations:
        validate_shadow_observation(observation)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.fixture.resolve())
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
