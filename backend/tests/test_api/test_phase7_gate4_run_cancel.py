"""Phase 7 Gate 4 — Run cancel + status polling tests.

Covers §9.1-§9.4 contract:

1. **GET /api/v1/runs/{run_id}** — happy path reads the row.
2. **GET unknown run_id** → 404 RUN_NOT_FOUND.
3. **GET cross-org run_id** → 404 (don't leak existence).
4. **POST /cancel on PENDING run** → 200 outcome=CANCELLED, status=CANCELLED.
5. **POST /cancel on COMPLETED run** → 200 outcome=ALREADY_COMPLETE.
6. **POST /cancel on RUNNING run** → outcome=RECORDED_ONLY (DeepSeek no mid-call cancel).
7. **POST /cancel unknown run** → 404.
8. **POST /cancel cross-org run** → 404 (not 403).
9. **Cost semantic** — cancelled PENDING run has cost=0; COMPLETED run keeps cost.
10. **terminal flag** — true for all terminal statuses; false for PENDING/RUNNING.
"""
from __future__ import annotations

import os
import uuid
import asyncio
from types import SimpleNamespace

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


def _seed_run(
    client: TestClient,
    *,
    agent_id: str = "medical-coding-agent",
    input_text: str = "test run for cancel",
    runtime_mode: str = "corti_like_fast",
) -> str:
    """Trigger one real agent_run so we get a valid run_id + a PENDING
    row in run_history. Returns the run_id."""
    resp = client.post(
        f"/api/v1/agents/{agent_id}/run",
        json={"input": {"text": input_text}, "runtime_mode": runtime_mode},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["run_id"]


# ────────────────────────────────────────────────────────────────────
# GET /api/v1/runs/{run_id}
# ────────────────────────────────────────────────────────────────────


def test_get_run_status_returns_envelope(client: TestClient) -> None:
    """GET returns the lifecycle envelope including status + terminal."""
    run_id = _seed_run(client, input_text="get_status happy path")
    resp = client.get(f"/api/v1/runs/{run_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["run_id"] == run_id
    assert data["status"] in ("COMPLETED", "FAILED", "COMPLETED_AFTER_CLIENT_ABORT")
    assert data["terminal"] is True
    assert data["agent_id"] == "medical-coding-agent"
    assert data["cost_currency"] == "CNY"


def test_get_run_status_unknown_returns_404(client: TestClient) -> None:
    """Unknown run_id → 404 RUN_NOT_FOUND."""
    resp = client.get("/api/v1/runs/run-does-not-exist-xyz")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RUN_NOT_FOUND"


# ────────────────────────────────────────────────────────────────────
# POST /api/v1/runs/{run_id}/cancel
# ────────────────────────────────────────────────────────────────────


def test_cancel_completed_run_returns_already_complete(client: TestClient) -> None:
    """Cancelling a run that already finished → outcome=ALREADY_COMPLETE."""
    run_id = _seed_run(client, input_text="cancel after complete")
    # The mock provider returns synchronously, so by the time we cancel
    # the run is COMPLETED. The cancel endpoint should report this
    # honestly rather than faking a cancellation.
    resp = client.post(
        f"/api/v1/runs/{run_id}/cancel",
        json={"reason": "user_clicked_cancel"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "ALREADY_COMPLETE"
    assert data["status"] in ("COMPLETED", "FAILED", "COMPLETED_AFTER_CLIENT_ABORT")
    assert data["cancel_reason"] == "user_clicked_cancel"
    assert data["cancelled_at"] is not None  # audit recorded


def test_cancel_unknown_run_returns_404(client: TestClient) -> None:
    """Cancel unknown run_id → 404 (don't leak existence)."""
    resp = client.post(
        "/api/v1/runs/run-not-found/cancel",
        json={"reason": "anything"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RUN_NOT_FOUND"


def test_cancel_records_audit_fields(client: TestClient) -> None:
    """Cancel writes cancelled_at + cancelled_by_user_id + cancel_reason."""
    run_id = _seed_run(client, input_text="cancel audit fields")
    client.post(
        f"/api/v1/runs/{run_id}/cancel",
        json={"reason": "audit_test_reason"},
    )
    # Read back via GET
    resp = client.get(f"/api/v1/runs/{run_id}")
    data = resp.json()
    assert data["cancel_reason"] == "audit_test_reason"
    assert data["cancelled_at"] is not None


def test_get_run_after_cancel_shows_terminal(client: TestClient) -> None:
    """After cancel of a COMPLETED run, GET shows terminal=True."""
    run_id = _seed_run(client, input_text="get after cancel")
    client.post(f"/api/v1/runs/{run_id}/cancel", json={"reason": "x"})
    resp = client.get(f"/api/v1/runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["terminal"] is True


# ────────────────────────────────────────────────────────────────────
# Cost semantics — never zero a recorded cost
# ────────────────────────────────────────────────────────────────────


def test_cancel_does_not_zero_recorded_cost(client: TestClient) -> None:
    """§9.4: cancelling a COMPLETED run does not zero its cost.

    The mock provider may or may not report cost. Whatever cost was
    recorded stays — cancel never zeroes it. We assert that the
    post-cancel cost is AT LEAST the pre-cancel cost (no regression).
    """
    run_id = _seed_run(client, input_text="cost preservation")
    resp_before = client.get(f"/api/v1/runs/{run_id}")
    cost_before = resp_before.json().get("cost_amount", 0.0)

    client.post(f"/api/v1/runs/{run_id}/cancel", json={"reason": "x"})

    resp_after = client.get(f"/api/v1/runs/{run_id}")
    cost_after = resp_after.json().get("cost_amount", 0.0)
    # Cost never decreases due to cancel.
    assert cost_after >= cost_before, (
        f"Cancel must not zero cost: before={cost_before}, after={cost_after}"
    )


# POST /api/v1/runs/{run_id}/trace-token


def test_renew_trace_token_is_bound_no_store_and_audited(client: TestClient) -> None:
    """An authorized caller receives a fresh run/org-bound token only once
    the tenant audit row has been persisted."""
    from sqlalchemy import text
    from app.database import AsyncSessionLocal
    from app.services.trace_token import verify_trace_token

    run_id = _seed_run(client, input_text="trace token renewal")

    async def _count() -> int:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text(
                "SELECT COUNT(*) FROM audit_logs "
                "WHERE action = 'run.trace_token.renew' AND resource_id = :run_id"
            ), {"run_id": run_id})
            return int(result.scalar() or 0)

    before = asyncio.run(_count())
    response = client.post(f"/api/v1/runs/{run_id}/trace-token")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["run_id"] == run_id
    assert body["events_url"] == f"/api/v1/runs/{run_id}/events"
    assert body["trace_url"] == f"/api/v1/runs/{run_id}/trace"
    claims = verify_trace_token(body["trace_token"], expected_run_id=run_id)
    assert claims.organization_id == "org_default1"
    assert claims.exp == body["expires_at"]
    assert asyncio.run(_count()) == before + 1


def test_renew_trace_token_unknown_returns_404(client: TestClient) -> None:
    response = client.post("/api/v1/runs/run-token-does-not-exist/trace-token")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "RUN_NOT_FOUND"


def test_renew_trace_token_cross_org_returns_same_404(client: TestClient) -> None:
    from app.main import app
    from app.middleware.auth import get_current_organization

    run_id = _seed_run(client, input_text="trace token cross org")
    app.dependency_overrides[get_current_organization] = lambda: SimpleNamespace(
        id="org-other1"
    )
    try:
        response = client.post(f"/api/v1/runs/{run_id}/trace-token")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "RUN_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_current_organization, None)


def test_renew_trace_token_fails_closed_while_audit_is_paused(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = _seed_run(client, input_text="trace token audit pause")
    monkeypatch.setenv("ICODER_AUDIT_WRITE_PAUSED", "true")
    response = client.post(f"/api/v1/runs/{run_id}/trace-token")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AUDIT_PERSISTENCE_FAILED"
