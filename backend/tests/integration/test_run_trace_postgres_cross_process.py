"""PostgreSQL process-boundary contract for durable Run SSE cursors.

This test is collected by the existing integration job, which provides a
PostgreSQL 16 service.  Local SQLite runs skip explicitly; they are covered by
the separate two-process live SDK E2E.
"""
from __future__ import annotations

import multiprocessing
import os
import secrets
from typing import Any

import pytest


def _trace_worker(
    database_url: str,
    run_id: str,
    organization_id: str,
    operation: str,
    result_queue: Any,
) -> None:
    from app.config import settings

    settings.DATABASE_URL = database_url
    settings.RUNTRACE_STORE = "db"
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        DbRunTraceStore,
        RunTraceEvent,
    )

    store = DbRunTraceStore()
    if operation == "append-first":
        event = RunTraceEvent(
            run_id=run_id,
            trace_id=f"trace-{run_id}",
            step="ingest",
            status="ok",
            ts=1.0,
            safe_metadata={"_organization_id": organization_id},
        )
        store.append(event)
        result_queue.put({"event_id": event.event_id})
        return

    before = store.get_run_scoped(run_id, organization_id)
    event = RunTraceEvent(
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        step="completion",
        status="ok",
        ts=2.0,
        safe_metadata={"_organization_id": organization_id},
    )
    store.append(event)
    result_queue.put({
        "before_steps": [item.step for item in before],
        "event_id": event.event_id,
    })


def _run_worker(
    context, database_url: str, run_id: str, organization_id: str, operation: str
) -> dict:
    queue = context.Queue()
    process = context.Process(
        target=_trace_worker,
        args=(database_url, run_id, organization_id, operation, queue),
    )
    process.start()
    process.join(timeout=30)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        pytest.fail(f"PostgreSQL trace worker hung during {operation}")
    assert process.exitcode == 0
    return queue.get(timeout=5)


def test_postgres_trace_is_visible_and_ordered_across_processes() -> None:
    database_url = os.environ.get("ICODER_DATABASE_URL", "")
    if not database_url.startswith(("postgresql://", "postgresql+")):
        pytest.skip("requires the PostgreSQL integration service")

    from sqlalchemy import create_engine, delete, insert
    from app.config import settings
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        DbRunTraceStore,
        to_sync_database_url,
    )
    from app.models.organization import Organization
    from app.models.run_trace import RunTraceEventModel

    settings.DATABASE_URL = database_url
    run_id = f"run-pg-process-{secrets.token_hex(6)}"
    organization_id = f"rt{secrets.token_hex(5)}"
    context = multiprocessing.get_context("spawn")
    engine = create_engine(to_sync_database_url(database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                insert(Organization).values(
                    id=organization_id,
                    name=f"Run trace integration {organization_id}",
                    slug=f"run-trace-{organization_id}",
                    plan="free",
                    settings={},
                    is_active=True,
                )
            )

        first = _run_worker(
            context, database_url, run_id, organization_id, "append-first"
        )
        second = _run_worker(
            context, database_url, run_id, organization_id, "read-then-append"
        )

        reader = DbRunTraceStore()
        events = reader.get_run_scoped(run_id, organization_id)
        assert second["before_steps"] == ["ingest"]
        assert [event.step for event in events] == ["ingest", "completion"]
        assert [event.event_id for event in events] == [
            first["event_id"], second["event_id"]
        ]
        assert first["event_id"] != second["event_id"]
        assert reader.get_run_scoped(run_id, "org-other1") == []
    finally:
        try:
            with engine.begin() as connection:
                connection.execute(
                    delete(RunTraceEventModel).where(
                        RunTraceEventModel.run_id == run_id
                    )
                )
                connection.execute(
                    delete(Organization).where(Organization.id == organization_id)
                )
        finally:
            engine.dispose()
