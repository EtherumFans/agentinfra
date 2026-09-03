"""Phase A1A Gate 3.4 — SSE event tenant isolation (F04 carry-over).

Charter §3.4 coverage:

1. SSE endpoint cross-checks RunHistory.organization_id against the
   signed-token claim's org_id. A run re-attributed to a different
   org must NOT stream to a stale token.
2. SSE endpoint enforces tenant visibility classification —
   QUARANTINED / UNKNOWN / AMBIGUOUS / MODERN_SYSTEM rows return
   404 TRACE_NOT_FOUND (same shape as "no events") so no existence
   leaks.
3. Denials emit ``logger.warning("sse.denied ...")`` so the audit
   trail survives in app logs (Gate 3.6 will route to system_audit).

Pre-Gate-3.4 the endpoint only validated the token signature + used
``store.get_run_scoped`` which is fine in steady state but blind to
post-issuance re-attribution / quarantine.
"""
from __future__ import annotations

import asyncio
import os
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def _seed_run_row(
    *, run_id: str, org_id: str | None, classification: str | None,
) -> None:
    """Insert one run_history row to back the SSE cross-check."""
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel

    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            db.add(RunHistoryModel(
                run_id=run_id,
                agent_id="medical-coding-agent",
                user_id="u-test-bypass",
                cost_usd=0.0,
                latency_ms=0,
                runtime_mode="a2a_pure_llm",
                status="COMPLETED",
                organization_id=org_id,
                tenancy_classification=classification,
            ))
            await db.commit()
    asyncio.run(_go())


def _seed_trace_events(run_id: str) -> None:
    """Append one trace event for the given run_id (in-memory store)."""
    import time
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        RunTraceEvent, get_default_store,
    )
    store = get_default_store()
    store.append(RunTraceEvent(
        run_id=run_id,
        step="ingest",
        status="ok",
        ts=time.time(),
        duration_ms=10.0,
        safe_metadata={"agent_id": "medical-coding-agent"},
    ))


def _clear(run_id: str) -> None:
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
    get_default_store().clear()
    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            await db.commit()
    asyncio.run(_go())


# ── §1 Org mismatch denied ─────────────────────────────────────────


def test_sse_denied_on_org_mismatch(client: TestClient) -> None:
    """Token claims org=A but run_history row says org=B → 404."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-g34-org-{secrets.token_hex(4)}"
    _seed_run_row(run_id=run_id, org_id="org-B", classification="MODERN")
    _seed_trace_events(run_id)
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        resp = client.get(f"/api/v1/runs/{run_id}/events?token={token}")
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["code"] == "TRACE_NOT_FOUND"
        # No leak of which org "won" — generic message.
        assert "org-A" not in resp.text
        assert "org-B" not in resp.text
    finally:
        _clear(run_id)


# ── §2 Invisible classification denied ─────────────────────────────


@pytest.mark.parametrize("cls", [
    "QUARANTINED",
    "LEGACY_TENANT_UNKNOWN",
    "LEGACY_TENANT_AMBIGUOUS",
    "MODERN_SYSTEM",
])
def test_sse_denied_on_invisible_classification(
    client: TestClient, cls: str,
):
    """Token valid, org matches, but row classification is invisible
    → 404 TRACE_NOT_FOUND (no leak)."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-g34-{cls[:6]}-{secrets.token_hex(4)}"
    _seed_run_row(run_id=run_id, org_id="org-A", classification=cls)
    _seed_trace_events(run_id)
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        resp = client.get(f"/api/v1/runs/{run_id}/events?token={token}")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "TRACE_NOT_FOUND"
        assert cls not in resp.text
    finally:
        _clear(run_id)


# ── §3 NULL classification denied ──────────────────────────────────


def test_sse_denied_on_null_classification(client: TestClient) -> None:
    """Pre-Gate-2 rows with NULL classification must not stream."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-g34-null-{secrets.token_hex(4)}"
    _seed_run_row(run_id=run_id, org_id="org-A", classification=None)
    _seed_trace_events(run_id)
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        resp = client.get(f"/api/v1/runs/{run_id}/events?token={token}")
        assert resp.status_code == 404
    finally:
        _clear(run_id)


# ── §4 Visible classification + matching org passes ────────────────


def test_sse_passes_for_visible_classification(client: TestClient) -> None:
    """MODERN row with matching org should stream normally."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-g34-modern-{secrets.token_hex(4)}"
    _seed_run_row(run_id=run_id, org_id="org-A", classification="MODERN")
    _seed_trace_events(run_id)
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        resp = client.get(f"/api/v1/runs/{run_id}/events?token={token}")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        # Should have at least 2 data blocks: 1 event + stream.completed
        data_blocks = [ln for ln in resp.text.split("\n") if ln.startswith("data: ")]
        assert len(data_blocks) >= 2
    finally:
        _clear(run_id)
