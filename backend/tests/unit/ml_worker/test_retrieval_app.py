from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ml_worker.retrieval_app import (
    REMOTE_RETRIEVER_SCHEMA,
    create_app,
    verify_asset_manifest,
)


TEST_TOKEN = "test-worker-token-32-characters-minimum"
MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
ASSET_NAMES = (
    "faiss.index",
    "metadata.pkl",
    "faiss_icd9cm3.index",
    "metadata_icd9cm3.pkl",
)


@pytest.fixture(autouse=True)
def configured_index_version(monkeypatch):
    monkeypatch.setenv("MEDCODER_INDEX_VERSION", "test-catalog-2026-08")


class FakeRetriever:
    def __init__(self, *, fail_startup: bool = False):
        self.fail_startup = fail_startup
        self.calls = []

    def ensure_loaded(self):
        if self.fail_startup:
            raise FileNotFoundError("missing index")

    def retrieve_sync(self, query, top_k=None, expand_synonyms=True):
        self.calls.append((query, top_k, expand_synonyms))
        return [{
            "code": "I50.900",
            "name": "心力衰竭",
            "score": 0.93,
            "chapter": "循环系统",
        }]


def write_test_asset_manifest(root: Path, *, index_version: str) -> None:
    artifacts = {}
    for position, name in enumerate(ASSET_NAMES, start=1):
        content = f"test-asset-{position}".encode()
        (root / name).write_bytes(content)
        artifacts[name] = {
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    (root / "asset_manifest.json").write_text(
        json.dumps({
            "schema_version": "icoder.medcoder-assets/v1",
            "index_version": index_version,
            "embedding_model": {
                "repository": "BAAI/bge-m3",
                "revision": MODEL_REVISION,
                "dimension": 1024,
            },
            "artifacts": artifacts,
        }),
        encoding="utf-8",
    )


def test_worker_requires_bearer_token_and_returns_versioned_contract(monkeypatch):
    monkeypatch.setenv("MEDCODER_INDEX_VERSION", "catalog-2026-08")
    diagnosis = FakeRetriever()
    procedure = FakeRetriever()
    app = create_app(
        diagnosis_retriever=diagnosis,
        procedure_retriever=procedure,
        service_token=TEST_TOKEN,
    )
    with TestClient(app) as client:
        assert client.get("/readyz").json()["ready"] is True
        assert client.post("/v1/retrieve", json={
            "query": "心衰", "top_k": 3, "code_system": "ICD-10-CN",
        }).status_code == 401
        response = client.post(
            "/v1/retrieve",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
            json={"query": "心衰", "top_k": 3, "code_system": "ICD-10-CN"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == REMOTE_RETRIEVER_SCHEMA
    assert body["index_version"] == "catalog-2026-08"
    assert body["candidates"][0]["code"] == "I50.900"
    assert diagnosis.calls == [("心衰", 3, True)]


def test_worker_fails_one_code_system_without_false_green():
    app = create_app(
        diagnosis_retriever=FakeRetriever(),
        procedure_retriever=FakeRetriever(fail_startup=True),
        service_token=TEST_TOKEN,
    )
    with TestClient(app) as client:
        ready_response = client.get("/readyz")
        ready = ready_response.json()
        response = client.post(
            "/v1/retrieve",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
            json={"query": "手术", "code_system": "ICD-9-CM-3-CN"},
        )

    assert ready_response.status_code == 503
    assert ready["ready"] is False
    assert ready["code_systems"]["ICD-10-CN"]["ready"] is True
    assert ready["code_systems"]["ICD-9-CM-3-CN"]["ready"] is False
    assert response.status_code == 503


def test_worker_contract_tests_do_not_import_native_ml():
    backend_root = Path(__file__).resolve().parents[3]
    code = (
        "import sys; import ml_worker.retrieval_app; "
        "assert not any(n == 'torch' or n.startswith('torch.') or "
        "n == 'faiss' or n.startswith('faiss.') or "
        "n == 'sentence_transformers' or n.startswith('sentence_transformers.') "
        "for n in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_asset_manifest_accepts_exact_version_model_and_hashes(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDCODER_BGE_REVISION", MODEL_REVISION)
    write_test_asset_manifest(tmp_path, index_version="catalog-2026-08")

    verify_asset_manifest(tmp_path, "catalog-2026-08")


def test_asset_manifest_rejects_tampered_index(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDCODER_BGE_REVISION", MODEL_REVISION)
    write_test_asset_manifest(tmp_path, index_version="catalog-2026-08")
    (tmp_path / "faiss.index").write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="integrity failure"):
        verify_asset_manifest(tmp_path, "catalog-2026-08")


@pytest.mark.parametrize("mismatch", ["index_version", "model_revision"])
def test_asset_manifest_rejects_provenance_mismatch(
    tmp_path,
    monkeypatch,
    mismatch,
):
    monkeypatch.setenv(
        "MEDCODER_BGE_REVISION",
        MODEL_REVISION if mismatch == "index_version" else "different-revision",
    )
    write_test_asset_manifest(tmp_path, index_version="catalog-2026-08")

    with pytest.raises(RuntimeError, match="mismatch"):
        verify_asset_manifest(
            tmp_path,
            "different-catalog" if mismatch == "index_version" else "catalog-2026-08",
        )


def test_worker_weak_token_never_reports_ready():
    app = create_app(
        diagnosis_retriever=FakeRetriever(),
        procedure_retriever=FakeRetriever(),
        service_token="weak",
    )
    with TestClient(app) as client:
        ready_response = client.get("/readyz")
        ready = ready_response.json()
        response = client.post(
            "/v1/retrieve",
            headers={"Authorization": "Bearer weak"},
            json={"query": "query", "code_system": "ICD-10-CN"},
        )

    assert ready_response.status_code == 503
    assert ready["ready"] is False
    assert ready["credential_configured"] is False
    assert response.status_code == 503


def test_worker_unversioned_index_never_reports_ready():
    app = create_app(
        diagnosis_retriever=FakeRetriever(),
        procedure_retriever=FakeRetriever(),
        service_token=TEST_TOKEN,
        index_version="unversioned",
    )
    with TestClient(app) as client:
        ready_response = client.get("/readyz")
        ready = ready_response.json()

    assert ready_response.status_code == 503
    assert ready["ready"] is False
    assert ready["index_version_configured"] is False
    assert "index_version_invalid" in ready["code_systems"]["ICD-10-CN"]["reason"]


def test_worker_rejects_invalid_queue_timeout(monkeypatch):
    monkeypatch.setenv("MEDCODER_WORKER_QUEUE_TIMEOUT_SECONDS", "0")
    app = create_app(
        diagnosis_retriever=FakeRetriever(),
        procedure_retriever=FakeRetriever(),
        service_token=TEST_TOKEN,
    )
    try:
        with TestClient(app):
            pass
    except RuntimeError as exc:
        assert "QUEUE_TIMEOUT" in str(exc)
    else:
        raise AssertionError("invalid queue timeout must fail startup")


def test_worker_warmup_exercises_both_complete_native_paths():
    diagnosis = FakeRetriever()
    procedure = FakeRetriever()
    app = create_app(
        diagnosis_retriever=diagnosis,
        procedure_retriever=procedure,
        service_token=TEST_TOKEN,
        warmup=True,
    )
    with TestClient(app) as client:
        assert client.get("/readyz").json()["ready"] is True

    assert diagnosis.calls == [("心力衰竭", 1, False)]
    assert procedure.calls == [("胆囊切除术", 1, False)]
