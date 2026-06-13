import os

import pytest
from fastapi.testclient import TestClient

# Phase 3: the real national catalog + FAISS index are opt-in. Pop their env vars at
# conftest import (before any test module imports icoder.experts.catalog, which reads
# ICODER_ICD_CATALOG_DIR at import time) so the unit suite always runs on the 13-code
# sample — offline + deterministic regardless of the developer's shell environment.
os.environ.pop("ICODER_ICD_CATALOG_DIR", None)
os.environ.pop("ICODER_MEDCODER_INDEX_DIR", None)


@pytest.fixture(autouse=True)
def _no_llm_key(monkeypatch):
    # force the deterministic local provider (no external model in tests)
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)


@pytest.fixture
def client(tmp_path):
    from icoder.api.app import create_app

    # Per-test sqlite file; the context manager fires shutdown -> store.close()
    # so the db handle is released (Windows tmp_path cleanup needs this).
    app = create_app(db_path=str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


AUTH = {"Authorization": "Bearer demo:coder"}
