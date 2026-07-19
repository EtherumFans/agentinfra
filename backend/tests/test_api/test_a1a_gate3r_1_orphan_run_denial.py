"""Phase A1A Gate 3R.1 — Authoritative tenant-owned run resolver.

Charter §3R.1 carry-over:

> SSE、Console Trace 和 Partner Trace 在缺少权威 ``RunHistory`` 行时
> 可能继续访问 Event/Trace Store。

This file is the consolidated negative-path coverage for the orphan-run
defence. Each test proves one of three trace-read endpoints refuses to
serve events when there is no authoritative ``run_history`` row — even
when the trace token is valid, even when trace events are present in
the store, and even when the request appears to come from a tenant.

Endpoints covered:

  GET /api/runtime/runs/{run_id}/trace        — Console path
  GET /api/v1/runs/{run_id}/trace?token=…     — Partner path
  GET /api/v1/runs/{run_id}/events?token=…    — SSE partner path

Each denial:

  - Returns HTTP 404 with a body identical to the "no events" response
    (no existence leak)
  - emits a system_audit row with action ``trace.read.denied.orphan_run``
    (Console / partner) or ``sse.denied.orphan_run`` (SSE) for Security
    Admin forensic visibility (Gate 3.6 sink)
"""
from __future__ import annotations

import asyncio
import os
import secrets
import time

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


# ── Helpers ────────────────────────────────────────────────────────


def _seed_trace_events(run_id: str, *, org_id: str | None = None) -> None:
    """Drop events straight into the trace store WITHOUT seeding a
    run_history row. This is the orphan-run state: events exist but no
    authoritative row does.
    """
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
        safe_metadata={
            "agent_id": "medical-coding-agent",
            **({"_organization_id": org_id} if org_id else {}),
        },
    ))


def _clear_trace() -> None:
    from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
    get_default_store().clear()


def _clear_run_history(run_id: str) -> None:
    from app.database import AsyncSessionLocal
    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            await db.commit()
    asyncio.run(_go())


def _delete_audit_emits(action: str, resource_id: str) -> None:
    from app.database import AsyncSessionLocal
    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM audit_logs WHERE action = :a AND resource_id = :rid"
            ), {"a": action, "rid": resource_id})
            await db.commit()
    asyncio.run(_go())


def _count_audit_emits(action: str, resource_id: str) -> int:
    from app.database import AsyncSessionLocal
    async def _go() -> int:
        async with AsyncSessionLocal() as db:
            r = await db.execute(text(
                "SELECT COUNT(*) FROM audit_logs "
                "WHERE action = :a AND resource_id = :rid"
            ), {"a": action, "rid": resource_id})
            return int(r.scalar() or 0)
    return asyncio.run(_go())


# ── §1 Console path: orphan-run denied ────────────────────────────


def test_console_trace_orphan_run_returns_404(client: TestClient) -> None:
    """Console trace path refuses events when no run_history row.

    Before Gate 3R.1: events would have been served because the
    ``console_row is None`` branch fell through to read the store.
    After Gate 3R.1: refusal is the authoritative behaviour.
    """
    run_id = f"run-3r1-unauth-console-{secrets.token_hex(4)}"
    _clear_trace()
    _clear_run_history(run_id)
    _seed_trace_events(run_id, org_id="org-A")
    _delete_audit_emits("trace.read.denied.orphan_run", run_id)
    try:
        resp = client.get(
            f"/api/runtime/runs/{run_id}/trace",
            headers={"Tenant-Name": "org-A"},
        )
        assert resp.status_code == 404
        # The body must NOT leak that the run exists in the trace
        # store without an authoritative row. Generic phrases only.
        body_text = resp.text.lower()
        assert "orphan" not in body_text
        assert "classification" not in body_text
        assert "trace events" in body_text  # the generic "no events" message
    finally:
        _clear_trace()
        _clear_run_history(run_id)
        _delete_audit_emits("trace.read.denied.orphan_run", run_id)


def test_console_trace_orphan_run_emits_system_audit(client: TestClient) -> None:
    """Orphan-run denial emits a Security Admin-visible audit row
    with action ``trace.read.denied.orphan_run`` (Gate 3.6 sink)."""
    run_id = f"run-3r1-unauth-console-audit-{secrets.token_hex(4)}"
    _clear_trace()
    _clear_run_history(run_id)
    _seed_trace_events(run_id, org_id="org-A")
    _delete_audit_emits("trace.read.denied.orphan_run", run_id)
    before = _count_audit_emits("trace.read.denied.orphan_run", run_id)
    try:
        client.get(
            f"/api/runtime/runs/{run_id}/trace",
            headers={"Tenant-Name": "org-A"},
        )
        after = _count_audit_emits("trace.read.denied.orphan_run", run_id)
        assert after == before + 1, (
            f"orphan_run audit emit missing: before={before} after={after}"
        )
    finally:
        _clear_trace()
        _clear_run_history(run_id)
        _delete_audit_emits("trace.read.denied.orphan_run", run_id)


# ── §2 Partner path: orphan-run denied (token with org) ──────────


def test_partner_trace_orphan_run_returns_404_with_org_token(
    client: TestClient,
) -> None:
    """Partner trace path refuses events when no run_history row, even
    when the trace token carries a valid organization_id claim."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-3r1-unauth-partner-org-{secrets.token_hex(4)}"
    _clear_trace()
    _clear_run_history(run_id)
    _seed_trace_events(run_id, org_id="org-A")
    _delete_audit_emits("trace.read.denied.orphan_run", run_id)
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        resp = client.get(f"/api/v1/runs/{run_id}/trace?token={token}")
        assert resp.status_code == 404
        body = resp.json()
        # FastAPI wraps HTTPException detail under "detail".
        detail = body.get("detail") or {}
        assert detail.get("code") == "TRACE_NOT_FOUND"
        body_text = resp.text.lower()
        assert "orphan" not in body_text
    finally:
        _clear_trace()
        _clear_run_history(run_id)
        _delete_audit_emits("trace.read.denied.orphan_run", run_id)


def test_partner_trace_orphan_run_returns_404_with_no_org_token(
    client: TestClient,
) -> None:
    """Partner trace path refuses events when no run_history row, even
    when the trace token carries no org claim (system / diagnostic
    token shape)."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-3r1-unauth-partner-noorg-{secrets.token_hex(4)}"
    _clear_trace()
    _clear_run_history(run_id)
    _seed_trace_events(run_id, org_id=None)
    _delete_audit_emits("trace.read.denied.orphan_run", run_id)
    try:
        token = issue_trace_token(run_id=run_id, organization_id=None)
        resp = client.get(f"/api/v1/runs/{run_id}/trace?token={token}")
        assert resp.status_code == 404
        body = resp.json()
        detail = body.get("detail") or {}
        assert detail.get("code") == "TRACE_NOT_FOUND"
        body_text = resp.text.lower()
        assert "orphan" not in body_text
    finally:
        _clear_trace()
        _clear_run_history(run_id)
        _delete_audit_emits("trace.read.denied.orphan_run", run_id)


# ── §3 SSE path: orphan-run denied ────────────────────────────────


def test_sse_orphan_run_returns_404_with_org_token(client: TestClient) -> None:
    """SSE event stream refuses to open when no run_history row."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-3r1-unauth-sse-org-{secrets.token_hex(4)}"
    _clear_trace()
    _clear_run_history(run_id)
    _seed_trace_events(run_id, org_id="org-A")
    _delete_audit_emits("sse.denied.orphan_run", run_id)
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        resp = client.get(f"/api/v1/runs/{run_id}/events?token={token}")
        assert resp.status_code == 404
        body = resp.json()
        detail = body.get("detail") or {}
        assert detail.get("code") == "TRACE_NOT_FOUND"
        body_text = resp.text.lower()
        assert "orphan" not in body_text
    finally:
        _clear_trace()
        _clear_run_history(run_id)
        _delete_audit_emits("sse.denied.orphan_run", run_id)


def test_sse_orphan_run_returns_404_with_no_org_token(client: TestClient) -> None:
    """SSE event stream refuses even when token has no org claim."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-3r1-unauth-sse-noorg-{secrets.token_hex(4)}"
    _clear_trace()
    _clear_run_history(run_id)
    _seed_trace_events(run_id, org_id=None)
    _delete_audit_emits("sse.denied.orphan_run", run_id)
    try:
        token = issue_trace_token(run_id=run_id, organization_id=None)
        resp = client.get(f"/api/v1/runs/{run_id}/events?token={token}")
        assert resp.status_code == 404
        body_text = resp.text.lower()
        assert "orphan" not in body_text
    finally:
        _clear_trace()
        _clear_run_history(run_id)
        _delete_audit_emits("sse.denied.orphan_run", run_id)


def test_sse_orphan_run_emits_system_audit(client: TestClient) -> None:
    """SSE orphan-run denial emits a system_audit row with action
    ``sse.denied.orphan_run`` for Security Admin."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-3r1-unauth-sse-audit-{secrets.token_hex(4)}"
    _clear_trace()
    _clear_run_history(run_id)
    _seed_trace_events(run_id, org_id="org-A")
    _delete_audit_emits("sse.denied.orphan_run", run_id)
    before = _count_audit_emits("sse.denied.orphan_run", run_id)
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        client.get(f"/api/v1/runs/{run_id}/events?token={token}")
        after = _count_audit_emits("sse.denied.orphan_run", run_id)
        assert after == before + 1, (
            f"sse orphan_run audit emit missing: before={before} after={after}"
        )
    finally:
        _clear_trace()
        _clear_run_history(run_id)
        _delete_audit_emits("sse.denied.orphan_run", run_id)


# ── §4 Regression: authoritative MODERN row still served ──────────


def _seed_modern_row(run_id: str, org_id: str) -> None:
    """Seed an authoritative MODERN row so the orphan-run guard
    DOES NOT fire. Used to prove the guard is precise, not
    over-restrictive.
    """
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
                tenancy_classification="MODERN",
            ))
            await db.commit()
    asyncio.run(_go())


def test_console_trace_modern_row_still_served(client: TestClient) -> None:
    """Regression: Console trace path still serves an authoritative
    MODERN row (orphan-run guard is precise)."""
    run_id = f"run-3r1-modern-console-{secrets.token_hex(4)}"
    _clear_trace()
    _clear_run_history(run_id)
    _seed_modern_row(run_id, "org-A")
    _seed_trace_events(run_id, org_id="org-A")
    try:
        resp = client.get(
            f"/api/runtime/runs/{run_id}/trace",
            headers={"Tenant-Name": "org-A"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
    finally:
        _clear_trace()
        _clear_run_history(run_id)


def test_partner_trace_modern_row_still_served(client: TestClient) -> None:
    """Regression: Partner trace path still serves an authoritative
    MODERN row."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-3r1-modern-partner-{secrets.token_hex(4)}"
    _clear_trace()
    _clear_run_history(run_id)
    _seed_modern_row(run_id, "org-A")
    _seed_trace_events(run_id, org_id="org-A")
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        resp = client.get(f"/api/v1/runs/{run_id}/trace?token={token}")
        assert resp.status_code == 200
    finally:
        _clear_trace()
        _clear_run_history(run_id)


def test_sse_modern_row_still_served(client: TestClient) -> None:
    """Regression: SSE path still serves an authoritative MODERN row."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-3r1-modern-sse-{secrets.token_hex(4)}"
    _clear_trace()
    _clear_run_history(run_id)
    _seed_modern_row(run_id, "org-A")
    _seed_trace_events(run_id, org_id="org-A")
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        resp = client.get(f"/api/v1/runs/{run_id}/events?token={token}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
    finally:
        _clear_trace()
        _clear_run_history(run_id)


# ── §5 Allowlist regression: orphan-run actions are recognized ────


def test_orphan_run_actions_in_system_audit_allowlist() -> None:
    """Gate 3R.1 added two new actions to the system_audit allowlist.
    Asserting they're present prevents accidental removal in future
    refactors."""
    from app.services.system_audit import ALL_SYSTEM_AUDIT_ACTIONS
    assert "trace.read.denied.orphan_run" in ALL_SYSTEM_AUDIT_ACTIONS
    assert "sse.denied.orphan_run" in ALL_SYSTEM_AUDIT_ACTIONS


def test_legacy_classifier_recognizes_orphan_run_actions() -> None:
    """The legacy_tenancy_attribution classifier must also recognise
    the new actions so future rows with these actions classify as
    MODERN_SYSTEM (Gate 3.6 invariants)."""
    from app.services.legacy_tenancy_attribution import SYSTEM_AUDIT_ACTIONS
    assert "trace.read.denied.orphan_run" in SYSTEM_AUDIT_ACTIONS
    assert "sse.denied.orphan_run" in SYSTEM_AUDIT_ACTIONS
