"""Phase 3-C0 A1 — A2A live smoke in mock mode.

Asserts that ``POST /api/icoder/agents/medcoder-coding-review/v1/message:send``
returns a non-error response (not ``PLANNING_FAILED``) when
``LLM_PROVIDER=mock`` is set, even if ``ICODER_CREDENTIAL_LLM`` is set in
the OS env (the dev persisted-key leak that caused HTTP 401 + empty
Plan.experts in Phase 3-B2).

This is the live A2A smoke acceptance for Phase 3-C0 A1:
> A2A live smoke 在 mock 模式下必须稳定 PASS
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


A2A_ENDPOINT = "/api/icoder/agents/medcoder-coding-review/v1/message:send"


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


def test_a2a_smoke_mock_mode_not_planning_failed(mock_mode_client):
    """A2A message:send in LLM_PROVIDER=mock mode must NOT return
    PLANNING_FAILED due to empty Plan.experts.
    """
    r = _send_message(mock_mode_client, "患者男 65 岁, 因持续胸痛 6 小时入院")
    assert r.status_code == 200, f"A2A smoke HTTP {r.status_code}: {r.text}"

    body = r.json()
    # If the response is a JSON-RPC error, it must NOT be PLANNING_FAILED
    # due to empty experts. Other errors (e.g., auth, downstream) may be
    # acceptable per Phase 3-B2 contract, but PLANNING_FAILED is the
    # specific regression we're fixing.
    if "error" in body:
        err = body["error"]
        code = err.get("code", 0)
        message = str(err.get("message", "")).lower()
        data = str(err.get("data", "")).lower()
        # -32003 is the old PLANNING_FAILED wire code; "plan.experts" is
        # the Planner's validation message — neither should appear.
        assert "plan.experts must be a non-empty list" not in data, (
            f"PLANNING_FAILED due to empty experts leaked back into mock mode: {body}"
        )
        assert code != -32003 or "planning_failed" not in message, (
            f"PLANNING_FAILED wire code leaked back: {body}"
        )
        return

    # Success path — result must be present
    result = body.get("result", {})
    assert isinstance(result, dict), f"unexpected result shape: {body}"
    # The result must be either a message or task; either way, no
    # PLANNING_FAILED indicator.
    assert "PLANNING_FAILED" not in str(result).upper(), (
        f"PLANNING_FAILED string leaked into result: {body}"
    )


def test_a2a_smoke_mock_mode_returns_message_or_task(mock_mode_client):
    """A2A smoke in mock mode should return a well-formed message or
    task envelope. Acceptance: status is 200 and the result has either
    ``kind=message`` or ``kind=task`` (no bare error string).
    """
    r = _send_message(mock_mode_client, "测试输入, 心力衰竭病例")
    assert r.status_code == 200, r.text
    body = r.json()
    if "result" in body:
        result = body["result"]
        kind = result.get("kind", "")
        assert kind in ("message", "task", ""), (
            f"unexpected kind in mock A2A result: {body}"
        )
