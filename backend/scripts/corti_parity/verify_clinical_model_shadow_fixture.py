"""Verify the repository synthetic bundle and emit aggregate-only evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.clinical_model_bundle import (  # noqa: E402
    build_canonical_zip,
    validate_verification_report,
    verify_bundle_directory,
    verify_bundle_zip_bytes,
)
from app.services.clinical_model_shadow_probe import (  # noqa: E402
    probe_verified_synthetic_bundle,
)


DEFAULT_FIXTURE = BACKEND_ROOT / "tests" / "fixtures" / "clinical_model_bundle_v1"


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def build_report(fixture: Path = DEFAULT_FIXTURE) -> dict[str, object]:
    verified_directory = verify_bundle_directory(fixture, environment="test")
    archive = build_canonical_zip(fixture)
    verified_archive = verify_bundle_zip_bytes(archive, environment="test")
    validate_verification_report(verified_directory.report)
    validate_verification_report(verified_archive.report)
    if verified_directory.report != verified_archive.report:
        raise RuntimeError("CLINICAL_MODEL_DIRECTORY_ZIP_VERIFICATION_MISMATCH")
    probe = probe_verified_synthetic_bundle(verified_archive)
    verification = verified_archive.report
    report: dict[str, object] = {
        "schema_version": "icoder.clinical-model-shadow-supply-chain-evidence/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": True,
        "artifact_class": verification["artifact_class"],
        "bundle_content_sha256": verification["bundle_content_sha256"],
        "manifest_sha256": verification["manifest_sha256"],
        "verification_report_sha256": verification["verification_report_sha256"],
        "trust_key_id": verification["trust_key_id"],
        "trust_store_sha256": verification["trust_store_sha256"],
        "sbom_sha256": verification["sbom_sha256"],
        "model_sha256": probe["model_sha256"],
        "test_vector_count": probe["test_vector_count"],
        "test_vectors_passed": probe["test_vectors_passed"],
        "signature_verified": True,
        "sbom_verified": True,
        "content_scan_status": verification["content_scan_status"],
        "directory_zip_equivalent": True,
        "bundle_stored": False,
        "case_level_artifacts_emitted": False,
        "patient_data_used": False,
        "network_used": False,
        "predictions_emitted": False,
        "production_inference_enabled": False,
        "os_sandbox_proven": False,
        "production_antivirus_proven": False,
        "real_clinical_model_validated": False,
        "corti_capability_parity_proven": False,
    }
    report["report_sha256"] = hashlib.sha256(_canonical_json(report)).hexdigest()
    return report


def validate_report(report: dict[str, object]) -> None:
    digest = report.get("report_sha256")
    unsigned = dict(report)
    unsigned.pop("report_sha256", None)
    if (
        report.get("schema_version")
        != "icoder.clinical-model-shadow-supply-chain-evidence/v1"
        or report.get("passed") is not True
        or report.get("bundle_stored") is not False
        or report.get("case_level_artifacts_emitted") is not False
        or report.get("patient_data_used") is not False
        or report.get("network_used") is not False
        or report.get("predictions_emitted") is not False
        or report.get("production_inference_enabled") is not False
        or digest != hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    ):
        raise RuntimeError("CLINICAL_MODEL_SHADOW_EVIDENCE_INVALID")


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
