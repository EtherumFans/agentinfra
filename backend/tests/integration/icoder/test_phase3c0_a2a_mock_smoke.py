"""A2A public medical-coding safety checks in mock mode.

Asserts that ``POST /api/icoder/agents/medical-coding-agent/v1/message:send``
fails closed without a fabricated clinical result when ``LLM_PROVIDER=mock``
is set, even if ``ICODER_CREDENTIAL_LLM`` is present in the OS environment.
It also proves that the internal MedCodER execution engine is not restored as
a public Agent endpoint.

Mock mode is suitable for protocol and safety tests, not clinical success.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_mode_client(monkeypatch):
    """Start the FastAPI app in mock mode with a fake ICODER_CREDENTIAL_LLM
    set — the leak scenario from Phase 3-B2."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "fake-key-must-be-ignored")
    monkeypatch.setenv("ICODER_DISABLE_AUTH_FOR_TESTS", "1")

    from app.main import app
    with TestClient(app) as c:
        yield c


# ``medcoder-coding-review`` is an internal execution engine and is no longer
# a public Agent route. Exercise the canonical public facade instead.
A2A_ENDPOINT = "/api/icoder/agents/medical-coding-agent/v1/message:send"


def _send_message(client, text: str):
    envelope = {
        "jsonrpc": "2.0",
        "id": "smoke-1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
                "messageId": "client-msg-smoke",
            }
        },
    }
    return client.post(
        A2A_ENDPOINT,
        json=envelope,
        headers={"A2A-Protocol-Version": "0.3"},
    )


def test_public_medical_coding_mock_mode_fails_closed_without_result(
    mock_mode_client,
):
    """A model-dependent public Agent must not fabricate mock clinical output."""
    r = _send_message(mock_mode_client, "患者男 65 岁, 因持续胸痛 6 小时入院")
    assert r.status_code == 503, f"A2A mock safety HTTP {r.status_code}: {r.text}"

    body = r.json()
    assert "result" not in body
    assert body["error"]["data"]["a2a_error_code"] == "INTERNAL_ERROR"
    assert "did not produce a valid result" in body["error"]["data"]["details"]


def test_internal_medcoder_engine_is_not_a_public_agent_route(mock_mode_client):
    """The implementation engine stays hidden behind the public facade."""
    endpoint = "/api/icoder/agents/medcoder-coding-review/v1/message:send"
    envelope = {
        "jsonrpc": "2.0",
        "id": "internal-engine-check",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "测试输入"}],
                "messageId": "client-msg-internal-engine-check",
            }
        },
    }
    response = mock_mode_client.post(
        endpoint,
        json=envelope,
        headers={"A2A-Protocol-Version": "0.3"},
    )

    assert response.status_code == 404
    body = response.json()
    assert "result" not in body
    assert body["error"]["data"]["a2a_error_code"] == "AGENT_NOT_FOUND"
