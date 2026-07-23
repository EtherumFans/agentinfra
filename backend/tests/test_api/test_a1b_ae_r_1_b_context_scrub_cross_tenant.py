"""A1B-AE-R.1.b — Context scrub + cross-tenant isolation tests.

Coverage:

§1  Migration 025 — contexts.organization_id column NOT NULL with default
§2  ContextRepository.hard_delete_context — all 5 tables scrubbed
§3  ContextLifecycle.destroy_now with org filter — wrong org → ContextIsolationError
§4  DELETE /api/icoder/contexts/{id} happy path — 200 + row gone
§5  DELETE /api/icoder/contexts/{id} unknown id — 404 CONTEXT_NOT_FOUND
§6  Cross-tenant DELETE — row exists under org_A, DELETE with org_B JWT → 404 (no leak)
§7  Cross-tenant GET /tasks/{id} — task under org_A, GET with org_B JWT → 404 (no leak)
§8  Cross-tenant POST /tasks/{id}/cancel — task under org_A, POST with org_B → 404
§9  Same-org operations succeed (control for §6-§8)
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Module-level imports so context + a2a models register with Base.metadata
# before the session-scoped setup_db fixture runs init_db().
import app.icoder.agent_runtime.a2a  # noqa: F401
import app.icoder.agent_runtime.context  # noqa: F401
from app.icoder.agent_runtime.context.db_models import (  # noqa: F401
    ContextArtifactRefRow,
    ContextMessageRow,
    ContextRow,
    ContextTaskRefRow,
    OriginalInputAuditRow,
)

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


A2A_PROTOCOL_HEADER = "A2A-Protocol-Version"
A2A_PROTOCOL_VERSION = "0.3"

ORG_A = "org_default1"  # matches the test-bypass mock org
ORG_B = "org_other_tenant"


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def _db_path() -> str:
    return os.environ.get(
        "ICODER_TEST_DB_PATH",
        str(Path(__file__).resolve().parents[2] / "data" / "test.db"),
    )


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _uuid() -> str:
    return str(uuid.uuid4())


async def _seed_context(
    *,
    context_id: str,
    organization_id: str = ORG_A,
    agent_id: str = "medcoder-coding-review",
) -> None:
    """Insert a contexts row directly bypassing the lifecycle (test-only)."""
    from app.database import AsyncSessionLocal

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO contexts "
                "(id, created_at, updated_at, expires_at, agent_id, "
                " organization_id, status, metadata_json, "
                " redacted_input_hash, original_input_ref) "
                "VALUES (:id, :ca, :ua, :ea, :aid, :oid, :st, :mj, :rh, :rr)"
            ),
            {
                "id": context_id,
                "ca": now,
                "ua": now,
                "ea": now,
                "aid": agent_id,
                "oid": organization_id,
                "st": "ACTIVE",
                "mj": "{}",
                "rh": "",
                "rr": "",
            },
        )
        await db.commit()


async def _seed_message(*, context_id: str, message_id: str) -> None:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO context_messages "
                "(context_id, message_id, role, parts_json, timestamp, "
                " redacted, metadata_json) "
                "VALUES (:c, :m, :r, :p, :t, 1, :mj)"
            ),
            {
                "c": context_id,
                "m": message_id,
                "r": "user",
                "p": '[{"kind":"text","text":"hi"}]',
                "t": datetime.now(timezone.utc),
                "mj": "{}",
            },
        )
        await db.commit()


async def _seed_task(
    *,
    context_id: str,
    task_id: str,
    state: str = "submitted",
) -> None:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
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


async def _seed_artifact(*, context_id: str, artifact_id: str) -> None:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO context_artifact_refs "
                "(context_id, artifact_id, name, mime_type, url) "
                "VALUES (:c, :a, :n, :m, :u)"
            ),
            {
                "c": context_id,
                "a": artifact_id,
                "n": "result.json",
                "m": "application/json",
                "u": "https://example.com/result.json",
            },
        )
        await db.commit()


async def _seed_audit(*, context_id: str, audit_id: str) -> None:
    from app.database import AsyncSessionLocal

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO original_input_audit "
                "(id, context_id, original_input, created_at, retention_until) "
                "VALUES (:id, :c, :oi, :ca, :ru)"
            ),
            {
                "id": audit_id,
                "c": context_id,
                "oi": "raw-before-redaction",
                "ca": now,
                "ru": now,
            },
        )
        await db.commit()


async def _count_rows(table: str, where: str = "") -> int:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        q = f"SELECT COUNT(*) FROM {table}"
        if where:
            q += f" WHERE {where}"
        return (await db.execute(text(q))).scalar_one()


async def _cleanup(*, context_id: str) -> None:
    """Delete a context and all its children (defensive — keeps tests hermetic)."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM original_input_audit WHERE context_id = :c"),
            {"c": context_id},
        )
        await db.execute(
            text("DELETE FROM context_artifact_refs WHERE context_id = :c"),
            {"c": context_id},
        )
        await db.execute(
            text("DELETE FROM context_task_refs WHERE context_id = :c"),
            {"c": context_id},
        )
        await db.execute(
            text("DELETE FROM context_messages WHERE context_id = :c"),
            {"c": context_id},
        )
        await db.execute(text("DELETE FROM contexts WHERE id = :c"), {"c": context_id})
        await db.commit()


def _override_org(org_id: str):
    """Swap the mock org's id for one test, then restore."""
    from app.middleware.auth import get_current_organization
    from app.main import app

    class _MockOrg:
        id = org_id
        name = f"Test Org {org_id}"
        slug = org_id
        is_active = True

    saved = app.dependency_overrides.get(get_current_organization)
    app.dependency_overrides[get_current_organization] = lambda: _MockOrg()
    try:
        yield
    finally:
        if saved is not None:
            app.dependency_overrides[get_current_organization] = saved
        else:
            del app.dependency_overrides[get_current_organization]


# ─────────────────────────────────────────────────────────────────────
# §1 Migration 025 schema
# ─────────────────────────────────────────────────────────────────────


def test_migration_025_organization_id_column_present():
    """contexts.organization_id column exists (NOT NULL with default)."""
    db = _db_path()
    if not os.path.exists(db):
        pytest.skip(f"test DB not present at {db}")
    conn = sqlite3.connect(db)
    try:
        cols = {
            row[1]: (row[3], row[4])
            for row in conn.execute("PRAGMA table_info(contexts)")
        }
    finally:
        conn.close()
    assert "organization_id" in cols, "contexts.organization_id missing — Migration 025 not applied"
    notnull, dflt = cols["organization_id"]
    assert notnull == 1, "contexts.organization_id must be NOT NULL"
    # A1B-AE-RV.2 fail-closed: Migration 026 dropped the permanent
    # server_default. New writes must supply organization_id explicitly
    # (DB NOT NULL + no default = fail-closed at the DB layer).
    assert dflt is None, (
        f"A1B-AE-RV.2: contexts.organization_id must have NO server_default "
        f"(fail-closed), got {dflt!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# §2 ContextRepository.hard_delete_context scrubs all 5 tables
# ─────────────────────────────────────────────────────────────────────


def test_hard_delete_context_scrubs_all_5_tables():
    """hard_delete_context removes: contexts, context_messages,
    context_task_refs, context_artifact_refs, original_input_audit."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context.context_repository import (
        ContextRepository,
    )

    ctx_id = _uuid()
    msg_id = _uuid()
    task_id = _uuid()
    art_id = _uuid()
    audit_id = _uuid()

    async def _seed():
        await _seed_context(context_id=ctx_id)
        await _seed_message(context_id=ctx_id, message_id=msg_id)
        await _seed_task(context_id=ctx_id, task_id=task_id)
        await _seed_artifact(context_id=ctx_id, artifact_id=art_id)
        await _seed_audit(context_id=ctx_id, audit_id=audit_id)

    async def _verify_pre():
        assert await _count_rows("contexts", f"id='{ctx_id}'") == 1
        assert await _count_rows("context_messages", f"context_id='{ctx_id}'") == 1
        assert await _count_rows("context_task_refs", f"context_id='{ctx_id}'") == 1
        assert await _count_rows("context_artifact_refs", f"context_id='{ctx_id}'") == 1
        assert await _count_rows("original_input_audit", f"context_id='{ctx_id}'") == 1

    async def _delete():
        async with AsyncSessionLocal() as db:
            repo = ContextRepository(db)
            await repo.hard_delete_context(ctx_id)

    async def _verify_post():
        assert await _count_rows("contexts", f"id='{ctx_id}'") == 0
        assert await _count_rows("context_messages", f"context_id='{ctx_id}'") == 0
        assert await _count_rows("context_task_refs", f"context_id='{ctx_id}'") == 0
        assert await _count_rows("context_artifact_refs", f"context_id='{ctx_id}'") == 0
        assert await _count_rows("original_input_audit", f"context_id='{ctx_id}'") == 0

    asyncio.run(_seed())
    asyncio.run(_verify_pre())
    asyncio.run(_delete())
    asyncio.run(_verify_post())


# ─────────────────────────────────────────────────────────────────────
# §3 ContextLifecycle.destroy_now with org filter
# ─────────────────────────────────────────────────────────────────────


def test_destroy_now_wrong_org_raises_isolation_error():
    """destroy_now(context_id, organization_id=other_org) → ContextIsolationError."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context.context_isolation import (
        ContextIsolationError,
    )
    from app.icoder.agent_runtime.context.context_lifecycle import (
        ContextLifecycle,
    )
    from app.icoder.agent_runtime.context.context_repository import (
        ContextRepository,
    )

    ctx_id = _uuid()

    async def _go():
        await _seed_context(context_id=ctx_id, organization_id=ORG_A)
        try:
            async with AsyncSessionLocal() as db:
                repo = ContextRepository(db)
                lifecycle = ContextLifecycle(repo)
                await lifecycle.destroy_now(
                    ctx_id, organization_id=ORG_B, reason="cross_tenant_test"
                )
            return False  # should have raised
        except ContextIsolationError:
            return True
        finally:
            await _cleanup(context_id=ctx_id)

    raised = asyncio.run(_go())
    assert raised, "destroy_now must raise ContextIsolationError on org mismatch"


def test_destroy_now_correct_org_deletes():
    """destroy_now(context_id, organization_id=correct_org) deletes the row."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context.context_lifecycle import (
        ContextLifecycle,
    )
    from app.icoder.agent_runtime.context.context_repository import (
        ContextRepository,
    )

    ctx_id = _uuid()

    async def _go():
        await _seed_context(context_id=ctx_id, organization_id=ORG_A)
        async with AsyncSessionLocal() as db:
            repo = ContextRepository(db)
            lifecycle = ContextLifecycle(repo)
            await lifecycle.destroy_now(
                ctx_id, organization_id=ORG_A, reason="same_tenant_test"
            )
        return await _count_rows("contexts", f"id='{ctx_id}'")

    count = asyncio.run(_go())
    assert count == 0


# ─────────────────────────────────────────────────────────────────────
# §4 DELETE /api/icoder/contexts/{id} happy path
# ─────────────────────────────────────────────────────────────────────


def test_delete_context_endpoint_happy_path(client):
    """DELETE /api/icoder/contexts/{id} returns 200 + envelope + row gone."""
    ctx_id = _uuid()

    async def _seed():
        await _seed_context(context_id=ctx_id)
        await _seed_message(context_id=ctx_id, message_id=_uuid())

    async def _verify_gone():
        assert await _count_rows("contexts", f"id='{ctx_id}'") == 0
        assert await _count_rows("context_messages", f"context_id='{ctx_id}'") == 0

    asyncio.run(_seed())
    try:
        r = client.delete(f"/api/icoder/contexts/{ctx_id}")
        assert r.status_code == 200, r.text
        assert r.headers[A2A_PROTOCOL_HEADER] == A2A_PROTOCOL_VERSION
        body = r.json()
        assert body["result"]["kind"] == "context"
        assert body["result"]["contextId"] == ctx_id
        assert body["result"]["deleted"] is True
        asyncio.run(_verify_gone())
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


# ─────────────────────────────────────────────────────────────────────
# §5 DELETE unknown id → 404 CONTEXT_NOT_FOUND
# ─────────────────────────────────────────────────────────────────────


def test_delete_context_unknown_returns_404(client):
    """DELETE /api/icoder/contexts/{unknown} → 404 CONTEXT_NOT_FOUND."""
    r = client.delete(f"/api/icoder/contexts/{_uuid()}")
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["error"]["data"]["a2a_error_code"] == "CONTEXT_NOT_FOUND"
    assert A2A_PROTOCOL_HEADER in r.headers


# ─────────────────────────────────────────────────────────────────────
# §6 Cross-tenant DELETE — 404 no leak
# ─────────────────────────────────────────────────────────────────────


def test_delete_context_cross_tenant_returns_404_no_leak(client):
    """Context under ORG_A; DELETE with ORG_B JWT → 404 CONTEXT_NOT_FOUND.
    Row must still exist under ORG_A afterwards (not deleted by the ORG_B call)."""
    ctx_id = _uuid()

    async def _seed():
        await _seed_context(context_id=ctx_id, organization_id=ORG_A)

    async def _verify_survives():
        assert await _count_rows("contexts", f"id='{ctx_id}'") == 1

    asyncio.run(_seed())
    try:
        # Swap mock org to ORG_B for this request only
        for _ in _override_org(ORG_B):
            r = client.delete(f"/api/icoder/contexts/{ctx_id}")
            assert r.status_code == 404, r.text
            body = r.json()
            assert body["error"]["data"]["a2a_error_code"] == "CONTEXT_NOT_FOUND"
        asyncio.run(_verify_survives())
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


# ─────────────────────────────────────────────────────────────────────
# §7 Cross-tenant GET /tasks/{id} → 404 no leak
# ─────────────────────────────────────────────────────────────────────


def test_get_task_cross_tenant_returns_404_no_leak(client):
    """Task under context in ORG_A; GET with ORG_B JWT → 404 TASK_NOT_FOUND."""
    ctx_id = _uuid()
    task_id = _uuid()

    async def _seed():
        await _seed_context(context_id=ctx_id, organization_id=ORG_A)
        await _seed_task(context_id=ctx_id, task_id=task_id)

    asyncio.run(_seed())
    try:
        # Sanity: same-org GET works
        r1 = client.get(f"/api/icoder/tasks/{task_id}")
        assert r1.status_code == 200, r1.text

        # Cross-tenant GET → 404 (no leak)
        for _ in _override_org(ORG_B):
            r2 = client.get(f"/api/icoder/tasks/{task_id}")
            assert r2.status_code == 404, r2.text
            body = r2.json()
            assert body["error"]["data"]["a2a_error_code"] == "TASK_NOT_FOUND"
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


# ─────────────────────────────────────────────────────────────────────
# §8 Cross-tenant POST /tasks/{id}/cancel → 404 no leak
# ─────────────────────────────────────────────────────────────────────


def test_cancel_task_cross_tenant_returns_404_no_leak(client):
    """Task under context in ORG_A; POST cancel with ORG_B JWT → 404.
    Task state must NOT change (no leak-driven mutation)."""
    ctx_id = _uuid()
    task_id = _uuid()

    async def _seed():
        await _seed_context(context_id=ctx_id, organization_id=ORG_A)
        await _seed_task(context_id=ctx_id, task_id=task_id, state="working")

    async def _state() -> str:
        return str(
            (await _count_rows(
                "context_task_refs",
                f"task_id='{task_id}' AND state='working'",
            ))
        )

    asyncio.run(_seed())
    try:
        for _ in _override_org(ORG_B):
            r = client.post(
                f"/api/icoder/tasks/{task_id}/cancel",
                json={"reason": "cross-tenant attempt"},
            )
            assert r.status_code == 404, r.text
            body = r.json()
            assert body["error"]["data"]["a2a_error_code"] == "TASK_NOT_FOUND"
        # Task should still be in 'working' state
        assert asyncio.run(_state()) == "1"
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


# ─────────────────────────────────────────────────────────────────────
# §9 Same-org control — sanity
# ─────────────────────────────────────────────────────────────────────


def test_same_org_cancel_succeeds_control(client):
    """Control: same-org POST cancel moves working → canceled."""
    ctx_id = _uuid()
    task_id = _uuid()

    async def _seed():
        await _seed_context(context_id=ctx_id, organization_id=ORG_A)
        await _seed_task(context_id=ctx_id, task_id=task_id, state="working")

    asyncio.run(_seed())
    try:
        r = client.post(
            f"/api/icoder/tasks/{task_id}/cancel",
            json={"reason": "user control test"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result"]["status"]["state"] == "canceled"
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


def test_same_org_get_succeeds_control(client):
    """Control: same-org GET returns the task with correct state."""
    ctx_id = _uuid()
    task_id = _uuid()

    async def _seed():
        await _seed_context(context_id=ctx_id, organization_id=ORG_A)
        await _seed_task(context_id=ctx_id, task_id=task_id, state="submitted")

    asyncio.run(_seed())
    try:
        r = client.get(f"/api/icoder/tasks/{task_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result"]["id"] == task_id
        assert body["result"]["status"]["state"] == "submitted"
        assert body["result"]["contextId"] == ctx_id
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))
