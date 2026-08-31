from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from scripts.corti_parity.audit_ccl2026_local_model_runtime import (
    build_report,
    validate_report,
)


def _assets(tmp_path: Path) -> Path:
    root = tmp_path / "medcoder"
    revision = "test-revision"
    snapshot = root / "models" / "models--BAAI--bge-m3" / "snapshots" / revision
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "pytorch_model.bin").write_bytes(b"embedding-only")
    artifact = root / "faiss.index"
    artifact.write_bytes(b"index")
    manifest = {
        "schema_version": "icoder.medcoder-assets/v1",
        "index_version": "test",
        "embedding_model": {
            "repository": "BAAI/bge-m3",
            "revision": revision,
            "dimension": 1024,
        },
        "artifacts": {
            "faiss.index": {
                "size_bytes": artifact.stat().st_size,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }
        },
    }
    (root / "asset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_unsafe_native_stack_and_missing_generative_model_are_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "scripts.corti_parity.audit_ccl2026_local_model_runtime.assess_bge_runtime_safety",
        lambda: SimpleNamespace(
            safe=False,
            reason="known_unsafe_windows_native_stack",
            torch_version="2.11.0",
            sentence_transformers_version="3.2.1",
        ),
    )
    monkeypatch.setattr(
        "scripts.corti_parity.audit_ccl2026_local_model_runtime.assess_pyarrow_runtime_safety",
        lambda: SimpleNamespace(
            safe=False,
            reason="known_unsafe_windows_native_stack",
            pyarrow_version="24.0.0",
        ),
    )
    report = build_report(_assets(tmp_path))
    assert validate_report(report) == []
    assert report["status"] == "blocked"
    assert report["retrieval_assets"]["integrity_verified"] is True
    assert report["capability"]["can_generate_real_local_model_prediction_packet"] is False
    assert report["claim_boundaries"]["unsafe_runtime_override_used"] is False
    assert report["claim_boundaries"]["native_model_loaded_by_audit"] is False


def test_embedding_only_assets_do_not_become_a_generative_model(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "scripts.corti_parity.audit_ccl2026_local_model_runtime.assess_bge_runtime_safety",
        lambda: SimpleNamespace(
            safe=True,
            reason="no_known_native_conflict",
            torch_version="safe",
            sentence_transformers_version="safe",
        ),
    )
    monkeypatch.setattr(
        "scripts.corti_parity.audit_ccl2026_local_model_runtime.assess_pyarrow_runtime_safety",
        lambda: SimpleNamespace(
            safe=True,
            reason="no_known_native_conflict",
            pyarrow_version="safe",
        ),
    )
    report = build_report(_assets(tmp_path))
    assert report["status"] == "blocked"
    assert report["model_inventory"]["embedding_retriever_is_generative_model"] is False
    assert report["model_inventory"][
        "approved_local_generative_clinical_coding_model_configured"
    ] is False


def test_asset_tamper_and_report_tamper_are_detected(
    tmp_path: Path, monkeypatch
) -> None:
    root = _assets(tmp_path)
    (root / "faiss.index").write_bytes(b"tampered")
    report = build_report(root)
    assert report["status"] == "blocked"
    assert report["retrieval_assets"]["integrity_verified"] is False
    tampered = copy.deepcopy(report)
    tampered["claim_boundaries"]["local_model_quality_measured"] = True
    errors = validate_report(tampered)
    assert "canonical readiness report digest mismatch" in errors
    assert any("local_model_quality_measured" in item for item in errors)
