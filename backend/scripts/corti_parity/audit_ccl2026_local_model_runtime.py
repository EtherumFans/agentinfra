"""Audit local CCL coding-model readiness without importing native ML stacks."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from icoder_runtime.providers.medical_coding.runtime_safety import (  # noqa: E402
    assess_bge_runtime_safety,
    assess_pyarrow_runtime_safety,
)
from scripts.corti_parity.audit_ccl2026_local_dataset import (  # noqa: E402
    _canonical_sha256,
    _sha256_file,
)


SCHEMA_VERSION = "icoder.ccl2026-local-model-runtime-readiness/v1"


def _validate_retrieval_assets(asset_dir: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    manifest_path = asset_dir / "asset_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"integrity_verified": False}, ["retrieval asset manifest is unreadable"]
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return {"integrity_verified": False}, ["retrieval asset manifest has no artifacts"]
    verified = 0
    total_size = 0
    for name, expected in artifacts.items():
        path = asset_dir / str(name)
        if not path.is_file():
            errors.append("retrieval asset is missing")
            continue
        size = path.stat().st_size
        total_size += size
        if size != int((expected or {}).get("size_bytes") or -1):
            errors.append("retrieval asset size mismatch")
            continue
        if _sha256_file(path) != str((expected or {}).get("sha256") or ""):
            errors.append("retrieval asset digest mismatch")
            continue
        verified += 1
    embedding = manifest.get("embedding_model") or {}
    revision = str(embedding.get("revision") or "")
    snapshot = asset_dir / "models" / "models--BAAI--bge-m3" / "snapshots" / revision
    weight = snapshot / "pytorch_model.bin"
    model_cache_present = bool(
        revision and (snapshot / "config.json").is_file() and weight.is_file()
    )
    if not model_cache_present:
        errors.append("declared embedding model cache is incomplete")
    return {
        "manifest_schema_version": manifest.get("schema_version", ""),
        "index_version": manifest.get("index_version", ""),
        "embedding_repository": embedding.get("repository", ""),
        "embedding_revision": revision,
        "embedding_dimension": int(embedding.get("dimension") or 0),
        "artifact_count": len(artifacts),
        "verified_artifact_count": verified,
        "artifact_size_bytes": total_size,
        "embedding_model_cache_present": model_cache_present,
        "embedding_model_weight_size_bytes": weight.stat().st_size
        if weight.is_file()
        else 0,
        "integrity_verified": not errors,
    }, sorted(set(errors))


def build_report(asset_dir: Path) -> dict[str, Any]:
    assets, errors = _validate_retrieval_assets(asset_dir.resolve())
    bge = assess_bge_runtime_safety()
    pyarrow = assess_pyarrow_runtime_safety()
    blockers = list(errors)
    if not bge.safe:
        blockers.append("native embedding runtime is blocked by the host safety policy")
    # The governed manifest declares BAAI/bge-m3 only.  It is an embedding
    # retriever and cannot perform clinical chart-to-code generation itself.
    blockers.append("no approved local generative clinical coding model is configured")
    ready = not blockers
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ready else "blocked",
        "host": {
            "platform": platform.system(),
            "python_version": platform.python_version(),
        },
        "native_runtime_safety": {
            "bge_safe": bge.safe,
            "bge_reason": bge.reason,
            "torch_version": bge.torch_version,
            "sentence_transformers_version": bge.sentence_transformers_version,
            "pyarrow_safe": pyarrow.safe,
            "pyarrow_reason": pyarrow.reason,
            "pyarrow_version": pyarrow.pyarrow_version,
        },
        "retrieval_assets": assets,
        "model_inventory": {
            "embedding_retriever_configured": assets.get(
                "embedding_model_cache_present"
            ) is True,
            "embedding_retriever_is_generative_model": False,
            "approved_local_generative_clinical_coding_model_configured": False,
        },
        "capability": {
            "can_generate_real_local_model_prediction_packet": ready,
            "deterministic_catalog_baseline_available": True,
        },
        "claim_boundaries": {
            "native_model_loaded_by_audit": False,
            "network_used_by_audit": False,
            "unsafe_runtime_override_used": False,
            "local_model_quality_measured": False,
            "clinical_accuracy_proven": False,
            "production_readiness_proven": False,
        },
        "blockers": sorted(set(blockers)),
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported readiness report schema_version")
    supplied = str(report.get("report_sha256") or "")
    payload = copy.deepcopy(report)
    payload.pop("report_sha256", None)
    if supplied != _canonical_sha256(payload):
        errors.append("canonical readiness report digest mismatch")
    boundaries = report.get("claim_boundaries") or {}
    for key in (
        "native_model_loaded_by_audit",
        "network_used_by_audit",
        "unsafe_runtime_override_used",
        "local_model_quality_measured",
        "clinical_accuracy_proven",
        "production_readiness_proven",
    ):
        if boundaries.get(key) is not False:
            errors.append(f"readiness claim boundary must remain false: {key}")
    if report.get("status") == "ready" and report.get("blockers"):
        errors.append("ready report contains blockers")
    if report.get("status") == "blocked" and not report.get("blockers"):
        errors.append("blocked report has no blockers")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.asset_dir)
    validation_errors = validate_report(report)
    if validation_errors:
        report["status"] = "invalid"
        report["blockers"] = sorted(set(report["blockers"] + validation_errors))
        report.pop("report_sha256", None)
        report["report_sha256"] = _canonical_sha256(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "bge_safe": report["native_runtime_safety"]["bge_safe"],
        "retrieval_assets_verified": report["retrieval_assets"].get(
            "integrity_verified", False
        ),
        "local_generative_model_configured": report["model_inventory"][
            "approved_local_generative_clinical_coding_model_configured"
        ],
    }))
    return 1 if validation_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
