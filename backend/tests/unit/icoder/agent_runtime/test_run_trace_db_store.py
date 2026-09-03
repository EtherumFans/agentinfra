"""Phase 3-D2 Task 1 — DbRunTraceStore persistence + org-scoped reads
+ redaction-before-write tests.

Verifies:
  - DbRunTraceStore append/get_run round-trip
  - Unknown run_id returns []
  - Org-scoped read filters by organization_id (no cross-org leak)
  - Redaction defensive scan blanks secret keys + token blobs before persist
  - GET /api/runtime/runs/{run_id}/trace reads from DB store
  - 404 when run belongs to a different org (no leak)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.run_trace import router as run_trace_router
from app.icoder.agent_runtime.orchestrator.run_trace import (
    DbRunTraceStore,
    RunTraceStatus,
    RunTraceStep,
    emit_trace_event,
)
from app.models.run_trace import RunTraceEventModel
from app.middleware.tenant_extractor import TenantHeaderMiddleware


# Use a per-test sqlite DB so DB tests don't collide with the dev DB.
_DB_PATH_TEMPLATE = "./data/test_run_trace_{uid}.db"


def _seed_modern_row(run_id: str, org_id: str) -> None:
    """Seed an authoritative MODERN RunHistory row so the Phase A1A
    Gate 3R.1 orphan-run guard does not deny the trace read. The row
    is inserted into the application database (the same database the
    guard queries via AsyncSessionLocal), not the per-test tmp DB
    that the DbRunTraceStore fixture patches.
    """
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel

    async def _go() -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("DELETE FROM run_history WHERE run_id = :rid"),
                {"rid": run_id},
            )
            db.add(
                RunHistoryModel(
                    run_id=run_id,
                    agent_id="medical-coding-agent",
                    user_id="u-test-bypass",
                    cost_usd=0.0,
                    latency_ms=0,
                    runtime_mode="a2a_pure_llm",
                    status="COMPLETED",
                    organization_id=org_id,
                    tenancy_classification="MODERN",
                )
            )
            await db.commit()

    asyncio.run(_go())


def _clear_run_history(run_id: str) -> None:
    """Remove the seeded RunHistory row to keep tests hermetic."""
    from app.database import AsyncSessionLocal

    async def _go() -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("DELETE FROM run_history WHERE run_id = :rid"),
                {"rid": run_id},
            )
            await db.commit()

    asyncio.run(_go())


@pytest.fixture
def db_store(tmp_path, monkeypatch):
    """Fresh DbRunTraceStore with an isolated sqlite DB."""
    db_file = tmp_path / "run_trace.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    # Patch settings.DATABASE_URL so DbRunTraceStore picks up the test DB.
    from app.config import settings
    monkeypatch.setattr(settings, "DATABASE_URL", db_url)
    # Also patch the async engine URL setting (already imported by other modules).
    monkeypatch.setattr(settings, "RUNTRACE_STORE", "db")

    store = DbRunTraceStore()
    # Force engine creation against the test DB.
    store._ensure_engine()
    # Create the table directly (no alembic in tests).
    from sqlalchemy import create_engine
    from app.database import Base
    # Re-bind Base metadata to include our model.
    Base.metadata.create_all(store._sync_engine, tables=[RunTraceEventModel.__table__])
    yield store

    store.clear()
    if store._sync_engine is not None:
        store._sync_engine.dispose()


def test_db_store_append_and_get_run(db_store):
    """Events append to DB; get_run returns them in order."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    emit_trace_event(run_id, RunTraceStep.USER_MESSAGE_RECEIVED,
                     safe_metadata={"input_len": 100}, store=db_store, ts=1.0)
    emit_trace_event(run_id, RunTraceStep.TOOLS_LIST,
                     safe_metadata={"tool_count": 5}, store=db_store, ts=2.0)
    emit_trace_event(run_id, RunTraceStep.COMPLETION,
                     status=RunTraceStatus.OK, store=db_store, ts=3.0)

    events = db_store.get_run(run_id)
    assert len(events) == 3
    assert events[0].step == RunTraceStep.USER_MESSAGE_RECEIVED
    assert events[1].step == RunTraceStep.TOOLS_LIST
    assert events[2].step == RunTraceStep.COMPLETION
    assert events[0].ts == 1.0
    assert events[2].status == RunTraceStatus.OK


def test_db_store_unknown_run_returns_empty(db_store):
    """Unknown run_id returns [] (not 404 — the store returns empty)."""
    assert db_store.get_run("never-existed") == []


def test_db_store_org_scoped_filters_cross_org(db_store):
    """get_run_scoped returns [] for runs that belong to another org."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    emit_trace_event(
        run_id, RunTraceStep.USER_MESSAGE_RECEIVED,
        safe_metadata={
            "input_len": 100,
            "_organization_id": "org-A",
        },
        store=db_store, ts=1.0,
    )
    # Same org → returns the event.
    events_same = db_store.get_run_scoped(run_id, "org-A")
    assert len(events_same) == 1
    # Different org → returns [] (no leak).
    events_cross = db_store.get_run_scoped(run_id, "org-B")
    assert events_cross == []
    # No org filter → returns all (dev mode).
    events_all = db_store.get_run_scoped(run_id, None)
    assert len(events_all) == 1


def test_db_store_redaction_blanks_secret_keys(db_store, caplog):
    """Secret keys are blanked before DB insert."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    emit_trace_event(
        run_id, RunTraceStep.AUTH_RESOLVED,
        safe_metadata={
            "redacted_view": "Bearer ••••12",
            "granted_scopes": ["coding:validate"],
            # Secret keys that should NEVER slip through — defensive scan blanks them.
            "token": "tok-bearer-XYZ123abcd9876",
            "client_secret": "secret-abc",
        },
        store=db_store, ts=1.0,
    )

    events = db_store.get_run(run_id)
    assert len(events) == 1
    persisted_meta = events[0].safe_metadata
    # redacted_view + granted_scopes survive (these are display-safe by contract).
    assert persisted_meta["redacted_view"] == "Bearer ••••12"
    assert persisted_meta["granted_scopes"] == ["coding:validate"]
    # Secret keys are blanked.
    assert persisted_meta["token"] == "[REDACTED]"
    assert persisted_meta["client_secret"] == "[REDACTED]"


def test_db_store_redaction_blanks_token_blob(db_store):
    """Token-blob values are blanked before DB insert."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.signaturehash1234567890"
    emit_trace_event(
        run_id, RunTraceStep.AUTH_RESOLVED,
        safe_metadata={
            "redacted_view": "Bearer ••••12",
            # Token blob leaked under a non-secret key — defensive scan catches it.
            "auth_value": jwt_token,
        },
        store=db_store, ts=1.0,
    )

    events = db_store.get_run(run_id)
    assert len(events) == 1
    persisted_meta = events[0].safe_metadata
    assert persisted_meta["auth_value"] == "[REDACTED]"


# ── API integration tests (org-scoped 404) ─────────────────────────────


@pytest.fixture
def app_with_db_store(db_store):
    """FastAPI app + TenantHeaderMiddleware, with DbRunTraceStore as default."""
    from app.api import run_trace as api_module
    from app.icoder.agent_runtime.orchestrator import run_trace as rt_module

    # Patch BOTH the run_trace module AND the api module's already-imported
    # reference. The API does ``from ...run_trace import get_default_store``
    # at import time, so patching rt_module alone doesn't reach it.
    original_api_get = api_module.get_default_store
    original_rt_get = rt_module.get_default_store
    api_module.get_default_store = lambda: db_store
    rt_module.get_default_store = lambda: db_store
    try:
        app = FastAPI()
        app.add_middleware(TenantHeaderMiddleware)
        app.include_router(run_trace_router)
        yield app
    finally:
        api_module.get_default_store = original_api_get
        rt_module.get_default_store = original_rt_get


def test_api_returns_404_for_cross_org_run(app_with_db_store, db_store):
    """GET /trace returns 404 when run belongs to a different org (no leak)."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    emit_trace_event(
        run_id, RunTraceStep.USER_MESSAGE_RECEIVED,
        safe_metadata={
            "input_len": 100,
            "_organization_id": "org-A",
        },
        store=db_store, ts=1.0,
    )

    client = TestClient(app_with_db_store)
    # Request as org-B — should get 404 (run belongs to org-A).
    r = client.get(
        f"/api/runtime/runs/{run_id}/trace",
        headers={"X-Tenant": "org-B"},
    )
    assert r.status_code == 404
    assert "no trace events" in r.json()["detail"]


def test_api_returns_200_for_same_org_run(app_with_db_store, db_store):
    """GET /trace returns 200 when run belongs to the requesting org."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    # Phase A1A Gate 3R.1 — seed authoritative MODERN row so the orphan-run
    # guard does not deny. Tenant-Name header resolves to
    # ICODER_SINGLE_TENANT_ORG_ID (org_default1); seed + request under
    # org_default1 so the resolved tenant matches.
    _seed_modern_row(run_id, "org_default1")
    try:
        emit_trace_event(
            run_id, RunTraceStep.USER_MESSAGE_RECEIVED,
            safe_metadata={
                "input_len": 100,
                "_organization_id": "org_default1",
            },
            store=db_store, ts=1.0,
        )

        client = TestClient(app_with_db_store)
        r = client.get(
            f"/api/runtime/runs/{run_id}/trace",
            headers={"X-Tenant": "org_default1"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"] == run_id
        assert body["step_count"] == 1
    finally:
        _clear_run_history(run_id)
