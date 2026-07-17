"""Phase 7 Gate 3 — agent_run endpoint Idempotency-Key integration tests.

End-to-end coverage of §8.1-§8.3 through ``POST /api/v1/agents/{id}/run``:

1. **No Idempotency-Key header** → run proceeds normally (dedup bypassed).
2. **Same key + same body** twice → first response has its own run_id;
   second response replays the snapshot verbatim (same run_id).
3. **Same key + different body** → second response returns 409.
4. **Same key + same body, COMPLETED** → second response is identical to
   the first (the snapshot is replayed verbatim).

These use ``LLM_PROVIDER=mock`` so they don't hit DeepSeek.
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
    with TestClient(app) as c:
        yield c


# ── 1. No Idempotency-Key → runs normally ───────────────────────────


def test_no_idempotency_key_runs_normally(client: TestClient) -> None:
    """Without Idempotency-Key header, the endpoint behaves exactly as
    before — no dedup record is created, no replay path is exercised."""
    resp = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json={
            "input": {"text": "无 idempotency-key 时正常运行。"},
            "runtime_mode": "corti_like_fast",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "medical-coding-agent"
    assert data["run_id"].startswith("run-")


# ── 2. Same key + same body twice → snapshot replay ─────────────────


def test_same_key_same_body_replays_snapshot(client: TestClient) -> None:
    """Send the same request twice with the same Idempotency-Key.

    The first response carries run_id R1. The second response replays
    the COMPLETED snapshot — same run_id R1, same body verbatim.
    """
    idempotency_key = f"pytest-{uuid.uuid4()}"
    headers = {"Idempotency-Key": idempotency_key}
    body = {
        "input": {"text": "男性,60 岁,II 型糖尿病。"},
        "runtime_mode": "corti_like_fast",
    }

    resp1 = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json=body, headers=headers,
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    run_id_1 = data1["run_id"]
    assert run_id_1.startswith("run-")

    resp2 = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json=body, headers=headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    # Snapshot replay: same run_id, same agent_id.
    assert data2["run_id"] == run_id_1
    assert data2["agent_id"] == "medical-coding-agent"


# ── 3. Same key + different body → 409 ──────────────────────────────


def test_same_key_different_body_returns_409(client: TestClient) -> None:
    """Same Idempotency-Key + different request body → HTTP 409 with
    code=IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST.

    This is the §8.2 contract that protects partners from accidentally
    reusing a key for a different request.
    """
    idempotency_key = f"pytest-mismatch-{uuid.uuid4()}"
    headers = {"Idempotency-Key": idempotency_key}

    body_a = {
        "input": {"text": "第一段文本,与第二段不同。"},
        "runtime_mode": "corti_like_fast",
    }
    body_b = {
        "input": {"text": "完全不同的文本,触发 409。"},
        "runtime_mode": "corti_like_fast",
    }

    resp1 = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json=body_a, headers=headers,
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json=body_b, headers=headers,
    )
    assert resp2.status_code == 409
    detail = resp2.json()["detail"]
    assert detail["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"
    assert detail["idempotency_key"] == idempotency_key


# ── 4. Replay returns the COMPLETED snapshot verbatim ───────────────


def test_replay_returns_completed_snapshot_verbatim(client: TestClient) -> None:
    """The replay snapshot must include every field the original
    response had (run_id, agent_id, runtime_mode, summary, etc.)."""
    idempotency_key = f"pytest-snapshot-{uuid.uuid4()}"
    headers = {"Idempotency-Key": idempotency_key}
    body = {
        "input": {"text": "snapshot replay 应保持字段完整。"},
        "runtime_mode": "corti_like_fast",
    }

    resp1 = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json=body, headers=headers,
    )
    data1 = resp1.json()

    resp2 = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json=body, headers=headers,
    )
    data2 = resp2.json()

    # Required envelope fields must all be present in the snapshot.
    for field in (
        "agent_id", "run_id", "trace_id", "runtime_mode",
        "summary", "error", "error_reason",
    ):
        assert field in data2, f"replay snapshot missing field: {field}"

    # agent_id and run_id must match the original.
    assert data2["agent_id"] == data1["agent_id"]
    assert data2["run_id"] == data1["run_id"]
    assert data2["trace_id"] == data1["trace_id"]
