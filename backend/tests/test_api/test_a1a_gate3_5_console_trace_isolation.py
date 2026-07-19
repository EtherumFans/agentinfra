"""Phase A1A Gate 3.5 — Console RunTrace tenant isolation (F05 carry-over).

Charter §3.5 coverage:

1. Console RunTrace endpoint ``GET /api/runtime/runs/{run_id}/trace``
   cross-checks RunHistory.organization_id against the requesting
   tenant. Mismatch → 404 (no leak).
2. Console endpoint enforces tenant visibility classification —
   QUARANTINED / UNKNOWN / AMBIGUOUS / MODERN_SYSTEM rows return
   404 TRACE_NOT_FOUND.
3. Partner trace URL endpoint ``GET /api/v1/runs/{run_id}/trace?token=``
   also enforces visibility classification (the org check was already
   there).
4. Denials emit ``logger.warning("console.trace.denied ...")`` /
   ``"trace_url.denied ..."`` for the audit trail.
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


def _seed_trace_events(run_id: str, *, org_id: str | None = None) -> None:
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
        safe_metadata={
            "agent_id": "medical-coding-agent",
            **({"_organization_id": org_id} if org_id else {}),
        },
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


# ── §1 Console endpoint org mismatch ──────────────────────────────


def test_console_trace_denied_on_org_mismatch(client: TestClient) -> None:
    """Requesting tenant=org-A but run belongs to org=B → 404."""
    run_id = f"run-g35-org-{secrets.token_hex(4)}"
    _seed_run_row(run_id=run_id, org_id="org-B", classification="MODERN")
    _seed_trace_events(run_id, org_id="org-B")
    try:
        # The TenantHeaderMiddleware cross-checks header vs JWT, but
        # in test mode auth is disabled and request.state.tenant_name
        # is whatever the header says. So we set Tenant-Name=org-A
        # to simulate a different tenant.
        resp = client.get(
            f"/api/runtime/runs/{run_id}/trace",
            headers={"Tenant-Name": "org-A"},
        )
        assert resp.status_code == 404
        assert "org-A" not in resp.text
        assert "org-B" not in resp.text
    finally:
        _clear(run_id)


# ── §2 Console endpoint invisible classification ──────────────────


@pytest.mark.parametrize("cls", [
    "QUARANTINED",
    "LEGACY_TENANT_UNKNOWN",
    "LEGACY_TENANT_AMBIGUOUS",
    "MODERN_SYSTEM",
])
def test_console_trace_denied_on_invisible_classification(
    client: TestClient, cls: str,
):
    """Run with invisible classification → 404 TRACE_NOT_FOUND,
    no leak of which classification triggered the deny."""
    run_id = f"run-g35-{cls[:6]}-{secrets.token_hex(4)}"
    _seed_run_row(run_id=run_id, org_id="org-A", classification=cls)
    _seed_trace_events(run_id, org_id="org-A")
    try:
        resp = client.get(
            f"/api/runtime/runs/{run_id}/trace",
            headers={"Tenant-Name": "org-A"},
        )
        assert resp.status_code == 404
        assert cls not in resp.text
    finally:
        _clear(run_id)


# ── §3 Console endpoint NULL classification denied ─────────────────


def test_console_trace_denied_on_null_classification(
    client: TestClient,
):
    """Pre-Gate-2 rows with NULL classification must not surface
    their trace via Console."""
    run_id = f"run-g35-null-{secrets.token_hex(4)}"
    _seed_run_row(run_id=run_id, org_id="org-A", classification=None)
    _seed_trace_events(run_id, org_id="org-A")
    try:
        resp = client.get(
            f"/api/runtime/runs/{run_id}/trace",
            headers={"Tenant-Name": "org-A"},
        )
        assert resp.status_code == 404
    finally:
        _clear(run_id)


# ── §4 Console endpoint MODERN + matching org passes ───────────────


def test_console_trace_passes_for_visible_modern(client: TestClient) -> None:
    """MODERN row + matching tenant → 200 + timeline."""
    run_id = f"run-g35-modern-{secrets.token_hex(4)}"
    _seed_run_row(run_id=run_id, org_id="org-A", classification="MODERN")
    _seed_trace_events(run_id, org_id="org-A")
    try:
        resp = client.get(
            f"/api/runtime/runs/{run_id}/trace",
            headers={"Tenant-Name": "org-A"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
        assert len(body["timeline"]) >= 1
    finally:
        _clear(run_id)


# ── §5 Partner trace URL — invisible classification denied ────────


@pytest.mark.parametrize("cls", [
    "QUARANTINED",
    "LEGACY_TENANT_UNKNOWN",
    "MODERN_SYSTEM",
])
def test_partner_trace_url_denied_on_invisible_classification(
    client: TestClient, cls: str,
):
    """Signed token + matching org, but row is invisible → 404."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-g35-p-{cls[:6]}-{secrets.token_hex(4)}"
    _seed_run_row(run_id=run_id, org_id="org-A", classification=cls)
    _seed_trace_events(run_id, org_id="org-A")
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        resp = client.get(f"/api/v1/runs/{run_id}/trace?token={token}")
        assert resp.status_code == 404
        assert cls not in resp.text
    finally:
        _clear(run_id)


# ── §6 Partner trace URL — MODERN + matching org passes ───────────


def test_partner_trace_url_passes_for_modern(client: TestClient) -> None:
    from app.services.trace_token import issue_trace_token
    run_id = f"run-g35-p-modern-{secrets.token_hex(4)}"
    _seed_run_row(run_id=run_id, org_id="org-A", classification="MODERN")
    _seed_trace_events(run_id, org_id="org-A")
    try:
        token = issue_trace_token(run_id=run_id, organization_id="org-A")
        resp = client.get(f"/api/v1/runs/{run_id}/trace?token={token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
        assert len(body["timeline"]) >= 1
    finally:
        _clear(run_id)
