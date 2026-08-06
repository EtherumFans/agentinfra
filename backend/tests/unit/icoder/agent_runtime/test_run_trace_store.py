"""Phase 3-D1 Task 4 — RunTrace store + API tests.

Verifies:
  - RunTraceStore append/get_run ordering
  - emit_trace_event writes to default store
  - Auth step carries redacted_view, NOT raw token
  - GET /api/runtime/runs/{run_id}/trace returns timeline
  - 404 when run_id has no events
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.run_trace import router as run_trace_router
from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceEvent,
    RunTraceStatus,
    RunTraceStep,
    RunTraceStore,
    emit_trace_event,
    get_default_store,
)


def _seed_modern_row(run_id: str, org_id: str) -> None:
    """Seed an authoritative MODERN RunHistory row so the Phase A1A
    Gate 3R.1 orphan-run guard does not deny the trace read.
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


def test_run_trace_store_append_and_get_run():
    """Events append in order; get_run returns a copy."""
    store = RunTraceStore()
    emit_trace_event("run-1", RunTraceStep.USER_MESSAGE_RECEIVED,
                     safe_metadata={"input_len": 100}, store=store, ts=1.0)
    emit_trace_event("run-1", RunTraceStep.TOOLS_LIST,
                     safe_metadata={"tool_count": 5}, store=store, ts=2.0)
    emit_trace_event("run-1", RunTraceStep.COMPLETION,
                     status=RunTraceStatus.OK, store=store, ts=3.0)

    events = store.get_run("run-1")
    assert len(events) == 3
    assert events[0].step == RunTraceStep.USER_MESSAGE_RECEIVED
    assert events[1].step == RunTraceStep.TOOLS_LIST
    assert events[2].step == RunTraceStep.COMPLETION
    assert events[0].ts == 1.0
    assert events[2].status == RunTraceStatus.OK


def test_run_trace_store_get_run_returns_copy():
    """Mutating the returned list doesn't affect the store."""
    store = RunTraceStore()
    emit_trace_event("run-1", RunTraceStep.USER_MESSAGE_RECEIVED, store=store, ts=1.0)
    events = store.get_run("run-1")
    events.clear()
    assert len(store.get_run("run-1")) == 1


def test_run_trace_store_unknown_run_returns_empty():
    store = RunTraceStore()
    assert store.get_run("unknown") == []


def test_emit_trace_event_uses_default_store():
    """emit_trace_event without explicit store writes to the singleton."""
    store = get_default_store()
    store.clear()
    emit_trace_event("run-default", RunTraceStep.TOOLS_LIST,
                     safe_metadata={"tool_count": 5})
    events = store.get_run("run-default")
    assert len(events) == 1
    assert events[0].step == RunTraceStep.TOOLS_LIST
    assert events[0].safe_metadata["tool_count"] == 5
    store.clear()


def test_run_trace_event_to_dict_round_trip():
    """to_dict returns a JSON-serializable flat dict."""
    e = RunTraceEvent(
        run_id="r1",
        step=RunTraceStep.AUTH_RESOLVED,
        status=RunTraceStatus.OK,
        ts=1234567890.0,
        duration_ms=42.0,
        safe_metadata={"redacted_view": "Bearer ••••12", "granted_scopes": ["read"]},
    )
    d = e.to_dict()
    assert d["run_id"] == "r1"
    assert d["step"] == "auth_resolved"
    assert d["status"] == "ok"
    assert d["duration_ms"] == 42.0
    assert d["safe_metadata"]["redacted_view"] == "Bearer ••••12"
    assert d["safe_metadata"]["granted_scopes"] == ["read"]


def test_auth_step_carries_redacted_view_not_raw_token():
    """When emitting an auth_resolved event, safe_metadata MUST carry
    redacted_view and MUST NOT carry the raw token. The store trusts
    the caller, so this is a contract test for the emit site (server.py).
    """
    store = RunTraceStore()
    raw_token = "tok-bearer-XYZ123abcd9876"
    redacted_view = "Bearer ••••9876"
    # The emit site would build safe_metadata from the AuthHeader, NOT
    # from the raw token. We simulate that contract here.
    emit_trace_event(
        "run-auth", RunTraceStep.AUTH_RESOLVED,
        status=RunTraceStatus.OK,
        safe_metadata={
            "auth_type": "bearer",
            "redacted_view": redacted_view,
            "granted_scopes": ["coding:verify"],
        },
        store=store,
        ts=1.0,
    )
    events = store.get_run("run-auth")
    assert len(events) == 1
    dumped = str(events[0].to_dict())
    assert redacted_view in dumped
    assert raw_token not in dumped
    assert "Bearer tok-bearer" not in dumped


# ── API tests ──────────────────────────────────────────────────────────


@pytest.fixture
def app_with_trace():
    """FastAPI app with the run_trace router mounted."""
    app = FastAPI()
    app.include_router(run_trace_router)
    return app


@pytest.fixture
def client(app_with_trace):
    return TestClient(app_with_fixture=app_with_trace) if False else TestClient(app_with_trace)


def test_get_run_trace_returns_timeline(app_with_trace):
    """GET /api/runtime/runs/{run_id}/trace returns the events as timeline."""
    store = get_default_store()
    store.clear()
    # Phase A1A Gate 3R.1 — seed authoritative MODERN row so the orphan-run
    # guard does not deny. Resolved tenant is ICODER_SINGLE_TENANT_ORG_ID.
    _seed_modern_row("run-api", "org_default1")
    try:
        emit_trace_event("run-api", RunTraceStep.USER_MESSAGE_RECEIVED,
                         safe_metadata={"input_len": 100}, ts=1.0)
        emit_trace_event("run-api", RunTraceStep.TOOLS_LIST,
                         safe_metadata={"tool_count": 5}, ts=2.0)
        emit_trace_event("run-api", RunTraceStep.COMPLETION,
                         status=RunTraceStatus.OK, ts=3.0)

        client = TestClient(app_with_trace)
        r = client.get("/api/runtime/runs/run-api/trace")
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"] == "run-api"
        assert body["step_count"] == 3
        assert len(body["timeline"]) == 3
        assert body["timeline"][0]["step"] == "user_message_received"
        assert body["timeline"][2]["step"] == "completion"
    finally:
        store.clear()
        _clear_run_history("run-api")


def test_get_run_trace_404_on_unknown_run(app_with_trace):
    """GET /api/runtime/runs/unknown/trace → 404."""
    store = get_default_store()
    store.clear()
    client = TestClient(app_with_trace)
    r = client.get("/api/runtime/runs/never-existed/trace")
    assert r.status_code == 404
    assert "no trace events" in r.json()["detail"]


def test_get_run_trace_raw_format(app_with_trace):
    """?format=raw returns the internal store dump."""
    store = get_default_store()
    store.clear()
    # Phase A1A Gate 3R.1 — seed authoritative MODERN row.
    _seed_modern_row("run-raw", "org_default1")
    try:
        emit_trace_event("run-raw", RunTraceStep.TOOLS_LIST, ts=1.0)
        client = TestClient(app_with_trace)
        r = client.get("/api/runtime/runs/run-raw/trace?format=raw")
        assert r.status_code == 200
        body = r.json()
        assert "events" in body
        assert "timeline" not in body
    finally:
        store.clear()
        _clear_run_history("run-raw")
