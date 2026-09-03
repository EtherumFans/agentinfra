"""Executable retention contract for RunTrace replay and SSE cursors."""

from __future__ import annotations

import asyncio
import os
import secrets
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as value:
        yield value


def _run(coro):
    return asyncio.run(coro)


def _seed_api_run(run_id: str, *, event_count: int) -> None:
    from sqlalchemy import delete

    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        RunTraceEvent,
        get_default_store,
    )
    from app.models.run_history import RunHistoryModel

    async def _seed() -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(RunHistoryModel).where(RunHistoryModel.run_id == run_id)
            )
            now = datetime.now(UTC)
            db.add(RunHistoryModel(
                id=secrets.token_hex(6),
                run_id=run_id,
                agent_id="note-completeness-agent",
                user_id="u-test-bypass",
                organization_id="org_default1",
                tenancy_classification="MODERN",
                status="COMPLETED",
                input_text="",
                output_summary="",
                created_at=now,
                updated_at=now,
            ))
            await db.commit()

    _run(_seed())
    store = get_default_store()
    store.clear()
    for index in range(event_count):
        store.append(RunTraceEvent(
            run_id=run_id,
            step="ingest" if index == 0 else "completion",
            status="ok",
            ts=time.time() + index,
            safe_metadata={"marker": f"retained-{index}"},
        ))


def _mark_purged(run_id: str, count: int) -> None:
    from sqlalchemy import update

    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel

    async def _mark() -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(RunHistoryModel)
                .where(RunHistoryModel.run_id == run_id)
                .values(
                    trace_events_purged_at=datetime.now(UTC),
                    trace_events_purged_count=count,
                )
            )
            await db.commit()

    _run(_mark())


def _cleanup_api_run(run_id: str) -> None:
    from sqlalchemy import delete

    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
    from app.models.run_history import RunHistoryModel

    get_default_store().clear()

    async def _cleanup() -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(RunHistoryModel).where(RunHistoryModel.run_id == run_id)
            )
            await db.commit()

    _run(_cleanup())


def test_sse_distinguishes_unknown_cursor_from_retention_expiry(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings
    from app.services.trace_token import issue_trace_token

    monkeypatch.setattr(settings, "RUNTRACE_STORE", "memory")
    monkeypatch.setenv("ICODER_RUN_TRACE_EVENTS_TTL_DAYS", "37")
    run_id = "run-sse-retained-prefix"
    _seed_api_run(run_id, event_count=1)
    _mark_purged(run_id, 4)
    try:
        token = issue_trace_token(run_id=run_id)
        response = client.get(
            f"/api/v1/runs/{run_id}/events?token={token}",
            headers={"Last-Event-ID": "00000000-0000-4000-8000-000000000000"},
        )
        assert response.status_code == 410
        assert response.headers["x-icoder-trace-retention-days"] == "37"
        assert response.json()["detail"] == {
            "code": "SSE_CURSOR_EXPIRED",
            "message": (
                "The requested event cursor cannot be resolved after retention "
                "purge. Restart from the retained prefix or fetch the "
                "authoritative Run status."
            ),
            "retention_days": 37,
            "purged_at": response.json()["detail"]["purged_at"],
            "events_purged": 4,
        }
        assert response.json()["detail"]["purged_at"]
    finally:
        _cleanup_api_run(run_id)


def test_empty_retained_trace_returns_gone_and_status_exposes_tombstone(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings
    from app.services.trace_token import issue_trace_token

    monkeypatch.setattr(settings, "RUNTRACE_STORE", "memory")
    run_id = "run-sse-retained-empty"
    _seed_api_run(run_id, event_count=0)
    _mark_purged(run_id, 2)
    try:
        token = issue_trace_token(run_id=run_id)
        events = client.get(f"/api/v1/runs/{run_id}/events?token={token}")
        trace = client.get(f"/api/v1/runs/{run_id}/trace?token={token}")
        status = client.get(f"/api/v1/runs/{run_id}")

        assert events.status_code == 410
        assert events.json()["detail"]["code"] == "SSE_TRACE_EXPIRED"
        assert trace.status_code == 410
        assert trace.json()["detail"]["code"] == "TRACE_EXPIRED"
        assert status.status_code == 200
        assert status.json()["trace_retention_days"] == 90
        assert status.json()["trace_events_purged_count"] == 2
        assert status.json()["trace_events_purged_at"]
    finally:
        _cleanup_api_run(run_id)


@pytest.mark.asyncio
async def test_trace_purge_only_removes_expired_terminal_events_and_audits() -> None:
    from sqlalchemy import delete, select

    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog
    from app.models.run_history import RunHistoryModel
    from app.models.run_trace import RunTraceEventModel
    from app.services.retention import (
        RetentionPolicy,
        purge_expired_run_trace_events,
    )

    suffix = secrets.token_hex(4)
    expired_run = f"run-retention-expired-{suffix}"
    active_run = f"run-retention-active-{suffix}"
    recent_run = f"run-retention-recent-{suffix}"
    run_ids = [expired_run, active_run, recent_run]
    old = datetime.now(UTC) - timedelta(days=20)
    recent = datetime.now(UTC) - timedelta(days=1)

    async with AsyncSessionLocal() as db:
        now = datetime.now(UTC)
        for run_id, status in (
            (expired_run, "COMPLETED"),
            (active_run, "RUNNING"),
            (recent_run, "COMPLETED"),
        ):
            db.add(RunHistoryModel(
                id=secrets.token_hex(6),
                run_id=run_id,
                agent_id="note-completeness-agent",
                status=status,
                input_text="",
                output_summary="",
                created_at=now,
                updated_at=now,
            ))
        for run_id, created_at in (
            (expired_run, old),
            (active_run, old),
            (recent_run, recent),
        ):
            db.add(RunTraceEventModel(
                id=secrets.token_hex(6),
                run_id=run_id,
                step="completion",
                status="ok",
                ts=created_at.timestamp(),
                created_at=created_at,
                updated_at=created_at,
            ))
        await db.commit()

        policy = RetentionPolicy(run_trace_events_ttl_days=10)
        dry_run = await purge_expired_run_trace_events(db, policy, dry_run=True)
        assert dry_run["run_trace_events"] >= 1
        assert dry_run["runs_affected"] >= 1

        result = await purge_expired_run_trace_events(db, policy)
        assert result["run_trace_events"] >= 1

        rows = {
            row.run_id: row
            for row in (
                await db.execute(
                    select(RunHistoryModel).where(
                        RunHistoryModel.run_id.in_(run_ids)
                    )
                )
            ).scalars()
        }
        remaining = set((await db.execute(
            select(RunTraceEventModel.run_id).where(
                RunTraceEventModel.run_id.in_(run_ids)
            )
        )).scalars())
        assert expired_run not in remaining
        assert active_run in remaining
        assert recent_run in remaining
        assert rows[expired_run].trace_events_purged_at is not None
        assert rows[expired_run].trace_events_purged_count == 1
        assert rows[active_run].trace_events_purged_at is None

        audits = (await db.execute(
            select(AuditLog).where(
                AuditLog.action == "retention.purge",
                AuditLog.resource_id == "run_trace_events",
            )
        )).scalars().all()
        assert audits

        await db.execute(
            delete(RunTraceEventModel).where(
                RunTraceEventModel.run_id.in_(run_ids)
            )
        )
        await db.execute(
            delete(RunHistoryModel).where(RunHistoryModel.run_id.in_(run_ids))
        )
        await db.commit()
