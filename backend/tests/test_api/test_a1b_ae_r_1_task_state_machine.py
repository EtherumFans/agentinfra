"""A1B-AE-R.1.a — Task state machine + ThreadAuthRegistry DB migration.

Coverage:

§1  Migration 055 — eight-state context_task_refs CHECK constraint active
§2  TaskState enum — A2A v1 terminal and interrupted states
§3  next_state transitions — allowed + rejected
§4  GET /api/icoder/tasks/{task_id} — happy path + 404
§5  POST /api/icoder/tasks/{task_id}/cancel — submitted/working OK, terminal 409
§6  ThreadAuthRegistry — DB-backed is_first_message (0 rows → True)
§7  ThreadAuthRegistry — register_first_message idempotent
§8  A1B-AE.5 backwards-compat — sync singleton removed
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Module-level imports so context + a2a models register with Base.metadata
# before the session-scoped setup_db fixture runs init_db(). Without this,
# collection-time module loading happens too late and Base.metadata is missing
# context_task_refs / context_messages / contexts.
import app.icoder.agent_runtime.a2a  # noqa: F401
import app.icoder.agent_runtime.context  # noqa: F401
from app.icoder.agent_runtime.context.db_models import (  # noqa: F401
    ContextArtifactRefRow,
    ContextMessageRow,
    ContextRow,
    ContextTaskRefRow,
)

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


A2A_PROTOCOL_HEADER = "A2A-Protocol-Version"
A2A_PROTOCOL_VERSION = "0.3"


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────
# §1 Migration 055 schema
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_migration_055_state_check_constraint_present():
    """Inspect the active test engine, never a stale fixed SQLite filename."""

    import app.database as database
    from sqlalchemy import inspect

    async with database.engine.connect() as connection:
        constraints = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_check_constraints(
                "context_task_refs"
            )
        )
    names = {
        str(item.get("name"))
        for item in constraints
        if item.get("name") is not None
    }

    assert "ck_context_task_refs_state" in names, (
        "context_task_refs.state CHECK constraint missing on the active test engine"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_migration_055_rejects_invalid_state_value():
    """CHECK constraint must reject any state outside the eight-state enum."""
    from app.database import AsyncSessionLocal

    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM context_task_refs"))
            await db.execute(
                text(
                    "INSERT INTO context_task_refs "
                    "(context_id, task_id, state, started_at, completed_at) "
                    "VALUES (:c, :t, :s, :st, NULL)"
                ),
                {
                    "c": "00000000-0000-4000-8000-000000000001",
                    "t": "bad-state-task",
                    "s": "rolling",
                    "st": datetime.now(timezone.utc),
                },
            )
            await db.commit()

    with pytest.raises(Exception):
        await _go()


# ─────────────────────────────────────────────────────────────────────
# §2 TaskState enum
# ─────────────────────────────────────────────────────────────────────


def test_task_state_enum_has_v1_values():
    from app.icoder.agent_runtime.a2a.task_state import TaskState
    assert {s.value for s in TaskState} == {
        "submitted", "working", "completed", "failed", "canceled",
        "rejected", "input-required", "auth-required",
    }


def test_task_state_terminal_set():
    from app.icoder.agent_runtime.a2a.task_state import (
        INTERRUPTED_STATES, SETTLED_STATES, TERMINAL_STATES,
        TaskState, is_settled, is_terminal,
    )
    assert TERMINAL_STATES == frozenset(
        {
            TaskState.COMPLETED, TaskState.FAILED,
            TaskState.CANCELED, TaskState.REJECTED,
        }
    )
    assert INTERRUPTED_STATES == frozenset(
        {TaskState.INPUT_REQUIRED, TaskState.AUTH_REQUIRED}
    )
    assert SETTLED_STATES == TERMINAL_STATES | INTERRUPTED_STATES
    assert is_terminal(TaskState.COMPLETED)
    assert not is_terminal(TaskState.INPUT_REQUIRED)
    assert is_settled(TaskState.INPUT_REQUIRED)
    assert not is_terminal(TaskState.SUBMITTED)


# ─────────────────────────────────────────────────────────────────────
# §3 next_state transitions
# ─────────────────────────────────────────────────────────────────────


def test_next_state_allows_valid_transitions():
    from app.icoder.agent_runtime.a2a.task_state import (
        InvalidTaskTransition, TaskState, next_state,
    )
    assert next_state(TaskState.SUBMITTED, TaskState.WORKING) == TaskState.WORKING
    assert next_state(TaskState.SUBMITTED, TaskState.CANCELED) == TaskState.CANCELED
    assert next_state(TaskState.WORKING, TaskState.COMPLETED) == TaskState.COMPLETED
    assert next_state(TaskState.WORKING, TaskState.FAILED) == TaskState.FAILED
    assert next_state(TaskState.WORKING, TaskState.CANCELED) == TaskState.CANCELED
    assert next_state(TaskState.WORKING, TaskState.REJECTED) == TaskState.REJECTED
    assert next_state(TaskState.WORKING, TaskState.INPUT_REQUIRED) == TaskState.INPUT_REQUIRED
    assert next_state(TaskState.WORKING, TaskState.AUTH_REQUIRED) == TaskState.AUTH_REQUIRED
    assert next_state(TaskState.INPUT_REQUIRED, TaskState.WORKING) == TaskState.WORKING
    assert next_state(TaskState.AUTH_REQUIRED, TaskState.WORKING) == TaskState.WORKING


def test_next_state_rejects_invalid_transitions():
    from app.icoder.agent_runtime.a2a.task_state import (
        InvalidTaskTransition, TaskState, next_state,
    )
    # submitted cannot jump to completed/failed
    for bad in (TaskState.COMPLETED, TaskState.FAILED):
        with pytest.raises(InvalidTaskTransition):
            next_state(TaskState.SUBMITTED, bad)
    # terminal states reject everything
    for terminal in (
        TaskState.COMPLETED, TaskState.FAILED,
        TaskState.CANCELED, TaskState.REJECTED,
    ):
        for target in TaskState:
            with pytest.raises(InvalidTaskTransition):
                next_state(terminal, target)


# ─────────────────────────────────────────────────────────────────────
# §4-§5 GET/POST /api/icoder/tasks/{id} (state machine route tests)
# ─────────────────────────────────────────────────────────────────────


def _seed_task(task_id: str, state: str) -> str:
    """Insert a task row directly into context_task_refs. Returns context_id."""
    context_id = f"ctx-{uuid.uuid4()}"
    from app.database import AsyncSessionLocal

    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM context_task_refs WHERE task_id = :t"), {"t": task_id})
            await db.execute(text("DELETE FROM contexts WHERE id = :c"), {"c": context_id})
            await db.execute(
                text(
                    "INSERT INTO contexts "
                    "(id, created_at, updated_at, expires_at, agent_id, organization_id, status, "
                    " metadata_json, redacted_input_hash, original_input_ref) "
                    "VALUES (:c, :n, :n, :n, :a, 'org_default1', 'active', '{}', '', '')"
                ),
                {
                    "c": context_id,
                    "n": datetime.now(timezone.utc),
                    "a": "test-agent",
                },
            )
            await db.execute(
                text(
                    "INSERT INTO context_task_refs "
                    "(context_id, task_id, state, started_at, completed_at) "
                    "VALUES (:c, :t, :s, :st, NULL)"
                ),
                {
                    "c": context_id,
                    "t": task_id,
                    "s": state,
                    "st": datetime.now(timezone.utc),
                },
            )
            await db.commit()

    asyncio.run(_go())
    return context_id


def _cleanup_task(task_id: str, context_id: str) -> None:
    from app.database import AsyncSessionLocal

    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM context_task_refs WHERE task_id = :t"), {"t": task_id})
            await db.execute(text("DELETE FROM contexts WHERE id = :c"), {"c": context_id})
            await db.commit()

    asyncio.run(_go())


def test_get_task_returns_envelope(client):
    task_id = f"task-{uuid.uuid4()}"
    context_id = _seed_task(task_id, "submitted")
    try:
        r = client.get(
            f"/api/icoder/tasks/{task_id}",
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result"]["kind"] == "task"
        assert body["result"]["id"] == task_id
        assert body["result"]["contextId"] == context_id
        assert body["result"]["status"]["state"] == "submitted"
    finally:
        _cleanup_task(task_id, context_id)


def test_cancel_task_from_submitted(client):
    task_id = f"task-{uuid.uuid4()}"
    context_id = _seed_task(task_id, "submitted")
    try:
        r = client.post(
            f"/api/icoder/tasks/{task_id}/cancel",
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            json={"reason": "user requested"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result"]["status"]["state"] == "canceled"
        assert body["result"]["status"]["message"] == "user requested"
    finally:
        _cleanup_task(task_id, context_id)


def test_cancel_task_from_working(client):
    task_id = f"task-{uuid.uuid4()}"
    context_id = _seed_task(task_id, "working")
    try:
        r = client.post(
            f"/api/icoder/tasks/{task_id}/cancel",
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            json={"reason": "mid-run cancel"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["result"]["status"]["state"] == "canceled"
    finally:
        _cleanup_task(task_id, context_id)


def test_cancel_task_from_completed_returns_409(client):
    task_id = f"task-{uuid.uuid4()}"
    context_id = _seed_task(task_id, "completed")
    try:
        r = client.post(
            f"/api/icoder/tasks/{task_id}/cancel",
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            json={"reason": "too late"},
        )
        assert r.status_code == 409, r.text
        body = r.json()
        assert body["error"]["data"]["a2a_error_code"] == "TASK_NOT_CANCELABLE"
    finally:
        _cleanup_task(task_id, context_id)


def test_cancel_task_from_canceled_returns_409(client):
    task_id = f"task-{uuid.uuid4()}"
    context_id = _seed_task(task_id, "canceled")
    try:
        r = client.post(
            f"/api/icoder/tasks/{task_id}/cancel",
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            json={"reason": "already canceled"},
        )
        assert r.status_code == 409, r.text
        assert r.json()["error"]["data"]["a2a_error_code"] == "TASK_NOT_CANCELABLE"
    finally:
        _cleanup_task(task_id, context_id)


# ─────────────────────────────────────────────────────────────────────
# §6-§7 ThreadAuthRegistry DB-backed
# ─────────────────────────────────────────────────────────────────────


def _seed_context_with_message(context_id: str, message_id: str) -> None:
    from app.database import AsyncSessionLocal

    async def _go():
        async with AsyncSessionLocal() as db:
            existing = await db.execute(
                text("SELECT id FROM contexts WHERE id = :c"), {"c": context_id}
            )
            if existing.first() is None:
                await db.execute(
                    text(
                        "INSERT INTO contexts "
                        "(id, created_at, updated_at, expires_at, agent_id, organization_id, status, "
                        " metadata_json, redacted_input_hash, original_input_ref) "
                        "VALUES (:c, :n, :n, :n, :a, 'org_default1', 'active', '{}', '', '')"
                    ),
                    {"c": context_id, "n": datetime.now(timezone.utc), "a": "test-agent"},
                )
            await db.execute(
                text(
                    "INSERT INTO context_messages "
                    "(context_id, message_id, role, parts_json, timestamp, redacted, metadata_json) "
                    "VALUES (:c, :m, 'user', '[]', :n, 1, '{}')"
                ),
                {"c": context_id, "m": message_id, "n": datetime.now(timezone.utc)},
            )
            await db.commit()

    asyncio.run(_go())


def _cleanup_context(context_id: str) -> None:
    from app.database import AsyncSessionLocal

    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM context_messages WHERE context_id = :c"), {"c": context_id})
            await db.execute(text("DELETE FROM contexts WHERE id = :c"), {"c": context_id})
            await db.commit()

    asyncio.run(_go())


def test_thread_auth_is_first_message_when_no_rows():
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.a2a.thread_auth import ThreadAuthRegistry

    context_id = f"ctx-{uuid.uuid4()}"

    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM context_messages WHERE context_id = :c"), {"c": context_id})
            await db.execute(text("DELETE FROM contexts WHERE id = :c"), {"c": context_id})
            await db.commit()
            reg = ThreadAuthRegistry(db)
            return await reg.is_first_message(context_id)

    try:
        assert asyncio.run(_go()) is True
    finally:
        _cleanup_context(context_id)


def test_thread_auth_not_first_message_when_rows_exist():
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.a2a.thread_auth import ThreadAuthRegistry

    context_id = f"ctx-{uuid.uuid4()}"
    _seed_context_with_message(context_id, f"msg-{uuid.uuid4()}")

    async def _go():
        async with AsyncSessionLocal() as db:
            reg = ThreadAuthRegistry(db)
            return await reg.is_first_message(context_id)

    try:
        assert asyncio.run(_go()) is False
    finally:
        _cleanup_context(context_id)


def test_thread_auth_get_state_reports_message_count():
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.a2a.thread_auth import ThreadAuthRegistry

    context_id = f"ctx-{uuid.uuid4()}"
    _seed_context_with_message(context_id, f"msg-{uuid.uuid4()}")
    _seed_context_with_message(context_id, f"msg-{uuid.uuid4()}")

    async def _go():
        async with AsyncSessionLocal() as db:
            reg = ThreadAuthRegistry(db)
            return await reg.get_state(context_id)

    try:
        state = asyncio.run(_go())
        assert state["has_registered"] is True
        assert state["message_count"] == 2
    finally:
        _cleanup_context(context_id)


# ─────────────────────────────────────────────────────────────────────
# §8 A1B-AE.5 backwards-compat
# ─────────────────────────────────────────────────────────────────────


def test_thread_auth_registry_no_longer_has_module_singleton():
    """A1B-AE-R.1.a removed the ``thread_auth_registry`` singleton."""
    import app.icoder.agent_runtime.a2a.thread_auth as mod
    assert not hasattr(mod, "thread_auth_registry"), (
        "thread_auth_registry module singleton must be removed (DB-backed now)"
    )


def test_thread_auth_registry_requires_session():
    """ThreadAuthRegistry.__init__ must require a DB session argument."""
    from app.icoder.agent_runtime.a2a.thread_auth import ThreadAuthRegistry
    with pytest.raises(TypeError):
        ThreadAuthRegistry()
