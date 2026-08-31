from __future__ import annotations

import builtins

from app.services.medcoder_index_health import (
    index_health_check,
    is_icd9cm3_retriever_available,
)


def test_native_health_gate_reports_assets_without_importing_faiss(tmp_path, monkeypatch):
    (tmp_path / "faiss.index").write_bytes(b"not-loaded")
    (tmp_path / "metadata.pkl").write_bytes(b"not-loaded")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "faiss" or name.startswith("faiss."):
            raise AssertionError("FAISS must not be imported when native health is disabled")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    report = index_health_check(
        tmp_path,
        allow_native=False,
        native_disabled_reason="known unsafe host",
    )

    assert report["status"] == "degraded"
    assert report["checks"]["faiss_exists"] is True
    assert report["checks"]["metadata_exists"] is True
    assert "known unsafe host" in report["reason"]
    assert report["checks"]["faiss_loads"] is False


def test_icd9_helper_honors_native_health_gate_without_importing_faiss(
    tmp_path, monkeypatch
):
    (tmp_path / "faiss_icd9cm3.index").write_bytes(b"not-loaded")
    (tmp_path / "metadata_icd9cm3.pkl").write_bytes(b"not-loaded")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "faiss" or name.startswith("faiss."):
            raise AssertionError("FAISS must not be imported when native health is disabled")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert is_icd9cm3_retriever_available(
        tmp_path,
        allow_native=False,
        native_disabled_reason="operator disabled",
    ) is False
