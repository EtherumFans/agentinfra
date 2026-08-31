from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from icoder_runtime.providers.medical_coding.remote_retriever import (
    REMOTE_RETRIEVER_SCHEMA,
    RemoteMedCodERRetriever,
    RemoteRetrieverError,
)


TEST_TOKEN = "test-retriever-token-32-characters-minimum"


@pytest.mark.asyncio
async def test_remote_retriever_projects_strict_candidate_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TEST_TOKEN}"
        body = json.loads(request.content)
        assert body == {
            "query": "心力衰竭",
            "top_k": 2,
            "expand_synonyms": True,
            "code_system": "ICD-10-CN",
        }
        return httpx.Response(200, json={
            "schema_version": REMOTE_RETRIEVER_SCHEMA,
            "worker_version": "1.0.0",
            "index_version": "2026-08-cn",
            "code_system": "ICD-10-CN",
            "candidates": [
                {"code": "I50.900", "name": "心力衰竭", "score": 0.91,
                 "chapter": "循环系统", "source": "retrieve"},
            ],
        })

    retriever = RemoteMedCodERRetriever(
        "https://retriever.internal",
        token=TEST_TOKEN,
        transport=httpx.MockTransport(handler),
    )
    candidates = await retriever.retrieve_async("心力衰竭", top_k=2)

    assert len(candidates) == 1
    assert candidates[0].code == "I50.900"
    assert candidates[0].source == "retrieve"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": "wrong", "code_system": "ICD-10-CN", "candidates": []},
        {"schema_version": REMOTE_RETRIEVER_SCHEMA,
         "code_system": "ICD-9-CM-3-CN", "candidates": []},
        {"schema_version": REMOTE_RETRIEVER_SCHEMA,
         "code_system": "ICD-10-CN", "candidates": [
             {"code": "I50", "name": "x", "score": float("nan"), "chapter": ""}
         ]},
    ],
)
async def test_remote_retriever_fails_closed_on_contract_violation(payload) -> None:
    retriever = RemoteMedCodERRetriever(
        "https://retriever.internal",
        token=TEST_TOKEN,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        ),
    )
    with pytest.raises(RemoteRetrieverError):
        await retriever.retrieve_async("心衰")


def test_remote_retriever_requires_token_and_secure_transport() -> None:
    with pytest.raises(RemoteRetrieverError, match="TOKEN"):
        RemoteMedCodERRetriever("https://retriever.internal", token="")
    with pytest.raises(RemoteRetrieverError, match="plain HTTP"):
        RemoteMedCodERRetriever(
            "http://retriever.internal", token=TEST_TOKEN, allow_http=False
        )
    assert RemoteMedCodERRetriever(
        "http://127.0.0.1:8100", token=TEST_TOKEN
    ).base_url == "http://127.0.0.1:8100"
    with pytest.raises(RemoteRetrieverError, match="32 to 512"):
        RemoteMedCodERRetriever(
            "https://retriever.internal", token="too-short"
        )


@pytest.mark.asyncio
async def test_remote_retriever_rejects_zero_top_k() -> None:
    retriever = RemoteMedCodERRetriever(
        "https://retriever.internal",
        token=TEST_TOKEN,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500)
        ),
    )
    with pytest.raises(RemoteRetrieverError, match="top_k"):
        await retriever.retrieve_async("query", top_k=0)


@pytest.mark.asyncio
async def test_health_probe_is_code_system_specific() -> None:
    payload = {
        "schema_version": REMOTE_RETRIEVER_SCHEMA,
        "worker_version": "1.0.0",
        "index_version": "catalog-v3",
        "ready": False,
        "code_systems": {
            "ICD-10-CN": {"ready": True, "reason": ""},
            "ICD-9-CM-3-CN": {"ready": False, "reason": "index_missing"},
        },
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)
    )
    diagnosis = RemoteMedCodERRetriever(
        "https://retriever.internal", token=TEST_TOKEN, transport=transport
    )
    health = await diagnosis.health_async()

    # Overall readiness is deliberately false until both configured indices
    # are ready, preventing a partially initialized worker from looking green.
    assert health.ready is False
    assert health.index_version == "catalog-v3"


def test_importing_remote_client_never_loads_native_ml_modules() -> None:
    backend_root = Path(__file__).resolve().parents[4]
    code = (
        "import sys; "
        "import icoder_runtime.providers.medical_coding.remote_retriever; "
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
