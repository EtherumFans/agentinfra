"""Agent-run endpoint Idempotency-Key integration tests.

Successful replay cases use the deterministic compliance rule engine. The
medical-coding smoke case uses ``LLM_PROVIDER=mock`` and asserts an explicit
safe failure instead of treating mock output as clinical success.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def _compliance_body(text: str) -> dict:
    return {
        "input": {
            "text": text,
            "extra": {"codes": ["E11.21", "N18.3"]},
        },
        "runtime_mode": "rule_engine",
    }


def test_no_idempotency_key_runs_normally(client: TestClient) -> None:
    """Without a key, execution bypasses dedup and mock fails closed."""
    response = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json={
            "input": {"text": "无 idempotency-key 时正常执行。"},
            "runtime_mode": "corti_like_fast",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "medical-coding-agent"
    assert data["run_id"].startswith("run-")
    assert data["error"] is True
    assert data["error_reason"] == "llm_degraded"


def test_same_key_same_body_replays_snapshot(client: TestClient) -> None:
    """A completed response is replayed with the original run identity."""
    headers = {"Idempotency-Key": f"pytest-{uuid.uuid4()}"}
    body = _compliance_body("出院诊断：2型糖尿病伴肾病。待校验编码 E11.21、N18.3。")

    first = client.post(
        "/api/v1/agents/compliance-guardrail-agent/run",
        json=body,
        headers=headers,
    )
    assert first.status_code == 200
    data1 = first.json()
    assert data1["error"] is False
    assert data1["run_id"].startswith("run-")

    second = client.post(
        "/api/v1/agents/compliance-guardrail-agent/run",
        json=body,
        headers=headers,
    )
    assert second.status_code == 200
    data2 = second.json()
    assert data2["run_id"] == data1["run_id"]
    assert data2["agent_id"] == "compliance-guardrail-agent"


def test_same_key_different_body_returns_409(client: TestClient) -> None:
    """Reusing a key for a different request body returns HTTP 409."""
    idempotency_key = f"pytest-mismatch-{uuid.uuid4()}"
    headers = {"Idempotency-Key": idempotency_key}

    first = client.post(
        "/api/v1/agents/compliance-guardrail-agent/run",
        json=_compliance_body("第一段临床文本。"),
        headers=headers,
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/agents/compliance-guardrail-agent/run",
        json=_compliance_body("完全不同的临床文本。"),
        headers=headers,
    )
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"
    assert detail["idempotency_key"] == idempotency_key


def test_replay_returns_completed_snapshot_verbatim(client: TestClient) -> None:
    """Replay preserves all required envelope fields and identities."""
    headers = {"Idempotency-Key": f"pytest-snapshot-{uuid.uuid4()}"}
    body = _compliance_body("出院诊断：高血压。待审核编码 I10。")

    first = client.post(
        "/api/v1/agents/compliance-guardrail-agent/run",
        json=body,
        headers=headers,
    )
    assert first.status_code == 200
    data1 = first.json()
    assert data1["error"] is False

    second = client.post(
        "/api/v1/agents/compliance-guardrail-agent/run",
        json=body,
        headers=headers,
    )
    assert second.status_code == 200
    data2 = second.json()

    for field in (
        "agent_id",
        "run_id",
        "trace_id",
        "runtime_mode",
        "summary",
        "error",
        "error_reason",
    ):
        assert field in data2, f"replay snapshot missing field: {field}"

    assert data2 == data1
