from __future__ import annotations

import pytest

from app.services.connector_executor import ConnectorExecutionError
from app.services.connector_memory_semantic import (
    MEMORY_EMBEDDING_REQUEST_CONTRACT,
    MEMORY_EMBEDDING_RESPONSE_CONTRACT,
    GovernedMemoryEmbeddingProvider,
)


class _Transport:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def post_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _response(**overrides) -> dict:
    value = {
        "contract": MEMORY_EMBEDDING_RESPONSE_CONTRACT,
        "model": "test-model",
        "model_version": "v1",
        "dimensions": 16,
        "embeddings": [[1.0] + [0.0] * 15],
    }
    value.update(overrides)
    return value


def _provider(transport, **overrides) -> GovernedMemoryEmbeddingProvider:
    arguments = {
        "credential_resolver": lambda service: (
            "secret-memory-token" if service == "memory_semantic" else None
        ),
        "host_authorizer": lambda host: host == "memory.example.org",
        "endpoint": "https://memory.example.org/v1/embed",
    }
    arguments.update(overrides)
    return GovernedMemoryEmbeddingProvider(transport, **arguments)


@pytest.mark.asyncio
async def test_memory_embedding_contract_normalizes_and_sends_no_identifiers():
    transport = _Transport(_response(embeddings=[[2.0] + [0.0] * 15]))
    result = await _provider(transport).embed("糖尿病\n  用药情况")

    assert result.vector == (1.0,) + (0.0,) * 15
    assert result.model == "test-model"
    call = transport.calls[0]
    assert call["expected_host"] == "memory.example.org"
    assert call["headers"] == {"Authorization": "Bearer secret-memory-token"}
    assert call["body"] == {
        "contract": MEMORY_EMBEDDING_REQUEST_CONTRACT,
        "texts": ["糖尿病 用药情况"],
        "normalize": True,
    }
    assert all(
        token not in repr(call["body"])
        for token in ("organization", "user_id", "patient", "consent_id")
    )


@pytest.mark.asyncio
async def test_memory_embedding_rejects_phi_before_transport():
    transport = _Transport(_response())
    with pytest.raises(ConnectorExecutionError) as raised:
        await _provider(transport).embed("患者电话13800138000，糖尿病")
    assert raised.value.code == "CONNECTOR_MEMORY_SEMANTIC_DEIDENTIFICATION_REQUIRED"
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        _response(contract="wrong"),
        _response(dimensions=15, embeddings=[[1.0] * 15]),
        _response(embeddings=[[0.0] * 16]),
        _response(embeddings=[[float("nan")] + [0.0] * 15]),
        {**_response(), "raw_vendor_payload": "forbidden"},
    ],
)
async def test_memory_embedding_response_fails_closed(response):
    with pytest.raises(ConnectorExecutionError) as raised:
        await _provider(_Transport(response)).embed("safe query")
    assert raised.value.code == "CONNECTOR_MEMORY_SEMANTIC_RESPONSE_INVALID"


@pytest.mark.asyncio
async def test_memory_embedding_endpoint_and_credential_fail_closed():
    cases = [
        _provider(_Transport(_response()), endpoint="http://memory.example.org/v1/embed"),
        _provider(_Transport(_response()), endpoint="https://memory.example.org/v1/embed?q=x"),
        _provider(_Transport(_response()), credential_resolver=lambda _service: None),
        _provider(_Transport(_response()), host_authorizer=lambda _host: False),
    ]
    expected = [
        "CONNECTOR_MEMORY_SEMANTIC_NOT_CONFIGURED",
        "CONNECTOR_MEMORY_SEMANTIC_NOT_CONFIGURED",
        "CONNECTOR_MEMORY_SEMANTIC_NOT_CONFIGURED",
        "CONNECTOR_EGRESS_NOT_APPROVED",
    ]
    for provider, code in zip(cases, expected, strict=True):
        with pytest.raises(ConnectorExecutionError) as raised:
            await provider.embed("safe query")
        assert raised.value.code == code


def test_memory_embedding_status_is_secret_and_endpoint_free():
    secret = "must-not-leak"
    status = _provider(
        _Transport(_response()), credential_resolver=lambda _service: secret,
    ).status()
    assert status["configured"] is True
    assert status["identifiers_sent"] is False
    assert status["native_ml_in_api_process"] is False
    assert secret not in repr(status)
    assert "memory.example.org" not in repr(status)
