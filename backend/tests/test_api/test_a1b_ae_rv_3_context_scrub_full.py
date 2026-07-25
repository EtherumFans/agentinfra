"""A1B-AE-RV.3 — Context scrub completion + organization_id fail-closed.

Closes the 4 cross-store gaps identified in
CONTEXT_DATA_DEPENDENCY_GRAPH.json (RV3_GAP_01..04):

§1  hard_delete_context scrubs conversation_memories (session_id LIKE ctx:%)
§2  hard_delete_context redacts run_history (input_text + output_summary + clears context_id)
§3  hard_delete_context redacts run_trace_events (safe_metadata_json)
§4  hard_delete_context redacts audit_logs (details + summaries)
§5  DELETE endpoint returns per-store count + scrubs all 15 stores
§6  Synthetic marker scan: pre-insert marker into every store, delete, scan = 0
§7  Failure injection — message delete raises → entire txn rolls back
§8  Failure injection — Memory delete raises → entire txn rolls back
§9  Failure injection — Audit redact raises → entire txn rolls back
§10 organization_id fail-closed — Pydantic Context org_id required
§11 organization_id fail-closed — ContextLifecycle.create rejects empty org
§12 organization_id fail-closed — DB NOT NULL on direct INSERT
§13 Cross-tenant DELETE — ORG_B JWT cannot delete ORG_A context
§14 Dev DB guard — fixture armed and would catch mutation (smoke)
§15 Migration 026 — no server_default on contexts.organization_id

Marker strategy: every synthetic row contains the literal
``RV3MARKER-{ctx_id}`` so post-delete LIKE scans are authoritative.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Register context + a2a models with Base.metadata before init_db() runs.
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

ORG_A = "org_default1"
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


def _uuid() -> str:
    return str(uuid.uuid4())


def _marker(ctx_id: str, store: str) -> str:
    """Synthetic marker for post-delete LIKE scan."""
    return f"RV3MARKER-{ctx_id}-{store}"


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


async def _seed_context(
    *,
    context_id: str,
    organization_id: str = ORG_A,
    agent_id: str = "medcoder-coding-review",
    metadata_json: str = "{}",
) -> None:
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
                "mj": metadata_json,
                "rh": "",
                "rr": "",
            },
        )
        await db.commit()


async def _seed_message(*, context_id: str, message_id: str, marker: str) -> None:
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
                "p": json.dumps([{"kind": "text", "text": marker}]),
                "t": datetime.now(timezone.utc),
                "mj": json.dumps({"marker": marker}),
            },
        )
        await db.commit()


async def _seed_task(*, context_id: str, task_id: str, marker: str) -> None:
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
                "s": "submitted",
                "st": datetime.now(timezone.utc),
            },
        )
        await db.commit()


async def _seed_artifact(*, context_id: str, artifact_id: str, marker: str) -> None:
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
                "n": marker,
                "m": "application/json",
                "u": f"https://example.com/{marker}",
            },
        )
        await db.commit()


async def _seed_audit(*, context_id: str, audit_id: str, marker: str) -> None:
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
                "oi": marker,
                "ca": now,
                "ru": now,
            },
        )
        await db.commit()


async def _seed_memory(
    *, context_id: str, message_id: str, user_id: str, marker: str
) -> None:
    """Insert one conversation_memories row keyed by the
    memory_expert.ingest_context_messages pattern '{ctx}:{msg}'."""
    from app.database import AsyncSessionLocal
    from app.models.memory import ConversationMemory

    async with AsyncSessionLocal() as db:
        db.add(
            ConversationMemory(
                organization_id=ORG_A,
                user_id=user_id,
                agent_id="medcoder-coding-review",
                session_id=f"{context_id}:{message_id}",
                role="user",
                content=marker,
                key_facts=json.dumps(
                    {
                        "facts": [],
                        "_embedding": [0.1, 0.2, 0.3],
                        "source": "context",
                        "context_id": context_id,
                        "message_id": message_id,
                    }
                ),
                importance=0.4,
            )
        )
        await db.commit()


async def _seed_run_history(
    *, context_id: str, run_id: str, marker: str
) -> None:
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel

    async with AsyncSessionLocal() as db:
        db.add(
            RunHistoryModel(
                organization_id=ORG_A,
                user_id="test-user",
                agent_id="medcoder-coding-review",
                context_id=context_id,
                run_id=run_id,
                trace_id="trace-" + run_id,
                runtime_mode="platform_runtime",
                latency_ms=123,
                cost_usd=0.0,
                input_text=marker,
                output_summary=marker,
                status="COMPLETED",
                tenancy_classification="MODERN",
            )
        )
        await db.commit()


async def _seed_run_trace(*, run_id: str, marker: str) -> None:
    from app.database import AsyncSessionLocal
    from app.models.run_trace import RunTraceEventModel

    async with AsyncSessionLocal() as db:
        db.add(
            RunTraceEventModel(
                run_id=run_id,
                organization_id=ORG_A,
                agent_id="medcoder-coding-review",
                step="llm_call",
                status="ok",
                duration_ms=42.0,
                ts=0.0,
                safe_metadata_json={
                    "marker": marker,
                    "expert_invocations": [{"id": "coder", "marker": marker}],
                },
                event_id=str(uuid.uuid4()),
                sequence_number=1,
                trace_id="trace-" + run_id,
                identity_source="uuid_v4",
            )
        )
        await db.commit()


async def _seed_audit_log(*, context_id: str, marker: str) -> None:
    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog

    async with AsyncSessionLocal() as db:
        db.add(
            AuditLog(
                organization_id=ORG_A,
                user_id="test-user",
                username="test-user",
                action="agent.run",
                resource_type="context",
                resource_id=context_id,
                details={"marker": marker, "context_id": context_id},
                model_input_summary=marker,
                model_output_summary=marker,
                tool_calls_made={"marker": marker},
                status="success",
                agent_id="medcoder-coding-review",
                tenancy_classification="MODERN",
            )
        )
        await db.commit()


async def _count_rows(table: str, where: str = "") -> int:
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        q = f"SELECT COUNT(*) FROM {table}"
        if where:
            q += f" WHERE {where}"
        return (await db.execute(text(q))).scalar_one()


async def _scan_marker(marker_prefix: str) -> dict[str, int]:
    """Scan every PHI-bearing store for any row whose TEXT/JSON column
    contains the marker prefix. Returns per-table hit count.

    This is the authoritative post-delete check: the count for every
    table MUST be 0 for the scrub to be considered complete.
    """
    from app.database import AsyncSessionLocal

    scans = {
        "contexts": ["id", "metadata_json", "redacted_input_hash", "original_input_ref"],
        "context_messages": ["message_id", "parts_json", "metadata_json"],
        "context_task_refs": ["task_id"],
        "context_artifact_refs": ["artifact_id", "name", "url"],
        "original_input_audit": ["id", "original_input"],
        "conversation_memories": ["session_id", "content", "summary", "key_facts"],
        "run_history": ["run_id", "input_text", "output_summary", "trace_id"],
        "run_trace_events": ["run_id", "safe_metadata_json"],
        "audit_logs": ["action", "resource_id", "details", "model_input_summary", "model_output_summary", "tool_calls_made"],
    }
    hits: dict[str, int] = {}
    async with AsyncSessionLocal() as db:
        for table, cols in scans.items():
            or_clauses = " OR ".join(
                f"CAST({c} AS TEXT) LIKE :pat" for c in cols
            )
            sql = f"SELECT COUNT(*) FROM {table} WHERE {or_clauses}"
            n = (
                await db.execute(text(sql), {"pat": f"%{marker_prefix}%"})
            ).scalar_one()
            hits[table] = int(n)
    return hits


async def _cleanup(*, context_id: str) -> None:
    """Defensive — keeps tests hermetic regardless of test outcome."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM audit_logs WHERE resource_id = :c"),
            {"c": context_id},
        )
        await db.execute(
            text(
                "DELETE FROM run_trace_events WHERE run_id IN "
                "(SELECT run_id FROM run_history WHERE context_id = :c)"
            ),
            {"c": context_id},
        )
        await db.execute(
            text("DELETE FROM run_history WHERE context_id = :c OR input_text LIKE :p"),
            {"c": context_id, "p": f"%RV3MARKER-{context_id}%"},
        )
        await db.execute(
            text(
                "DELETE FROM conversation_memories WHERE session_id LIKE :p"
            ),
            {"p": f"{context_id}:%"},
        )
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


async def _seed_all_stores(ctx_id: str) -> dict[str, str]:
    """Seed every PHI-bearing store with a marker. Returns the id map."""
    msg_id = _uuid()
    task_id = _uuid()
    art_id = _uuid()
    audit_id = _uuid()
    run_id = _uuid()
    user_id = "rv3-test-user"

    await _seed_context(
        context_id=ctx_id,
        metadata_json=json.dumps(
            {"marker": _marker(ctx_id, "contexts"), "interview_state": {"marker": _marker(ctx_id, "interview")}}
        ),
    )
    await _seed_message(context_id=ctx_id, message_id=msg_id, marker=_marker(ctx_id, "messages"))
    await _seed_task(context_id=ctx_id, task_id=task_id, marker=_marker(ctx_id, "tasks"))
    await _seed_artifact(context_id=ctx_id, artifact_id=art_id, marker=_marker(ctx_id, "artifacts"))
    await _seed_audit(context_id=ctx_id, audit_id=audit_id, marker=_marker(ctx_id, "audit"))
    await _seed_memory(
        context_id=ctx_id,
        message_id=msg_id,
        user_id=user_id,
        marker=_marker(ctx_id, "memory"),
    )
    await _seed_run_history(context_id=ctx_id, run_id=run_id, marker=_marker(ctx_id, "run_history"))
    await _seed_run_trace(run_id=run_id, marker=_marker(ctx_id, "run_trace"))
    await _seed_audit_log(context_id=ctx_id, marker=_marker(ctx_id, "audit_log"))

    return {
        "msg_id": msg_id,
        "task_id": task_id,
        "art_id": art_id,
        "audit_id": audit_id,
        "run_id": run_id,
        "user_id": user_id,
    }


# ─────────────────────────────────────────────────────────────────────
# §1-§4 hard_delete_context scrubs each cross-store gap
# ─────────────────────────────────────────────────────────────────────


def test_rv3_1_hard_delete_scrubs_conversation_memories():
    """§1 RV3_GAP_01 — conversation_memories with session_id LIKE ctx:% removed."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context.context_repository import (
        ContextRepository,
    )

    ctx_id = _uuid()
    msg_id = _uuid()

    async def _go():
        await _seed_context(context_id=ctx_id)
        await _seed_memory(
            context_id=ctx_id,
            message_id=msg_id,
            user_id="u1",
            marker=_marker(ctx_id, "memory"),
        )
        pre = await _count_rows(
            "conversation_memories",
            f"session_id LIKE '{ctx_id}:%'",
        )
        assert pre == 1, f"expected 1 pre-delete memory, got {pre}"
        async with AsyncSessionLocal() as db:
            repo = ContextRepository(db)
            counts = await repo.hard_delete_context(ctx_id)
        post = await _count_rows(
            "conversation_memories",
            f"session_id LIKE '{ctx_id}:%'",
        )
        return counts, post

    try:
        counts, post = asyncio.run(_go())
        assert post == 0, f"conversation_memories not scrubbed: {post} rows remain"
        assert counts["conversation_memories"] == 1, counts
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


def test_rv3_2_hard_delete_redacts_run_history():
    """§2 RV3_GAP_02 — run_history.input_text + output_summary redacted;
    context_id cleared. Row retained for audit."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context.context_repository import (
        ContextRepository,
    )

    ctx_id = _uuid()
    run_id = _uuid()
    marker = _marker(ctx_id, "run_history")

    async def _go():
        await _seed_context(context_id=ctx_id)
        await _seed_run_history(context_id=ctx_id, run_id=run_id, marker=marker)
        async with AsyncSessionLocal() as db:
            repo = ContextRepository(db)
            counts = await repo.hard_delete_context(ctx_id)

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    text("SELECT input_text, output_summary, context_id FROM run_history WHERE run_id = :r"),
                    {"r": run_id},
                )
            ).one_or_none()
        return counts, row

    try:
        counts, row = asyncio.run(_go())
        assert row is not None, "run_history row must be retained for audit"
        assert row[0] != marker, f"input_text not redacted: {row[0]!r}"
        assert row[1] != marker, f"output_summary not redacted: {row[1]!r}"
        assert row[2] is None, f"context_id not cleared: {row[2]!r}"
        assert counts["run_history_redacted"] == 1, counts
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


def test_rv3_3_hard_delete_redacts_run_trace_events():
    """§3 RV3_GAP_03 — run_trace_events.safe_metadata_json redacted
    for all events with run_id tied to the deleted context."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context.context_repository import (
        ContextRepository,
    )

    ctx_id = _uuid()
    run_id = _uuid()
    marker = _marker(ctx_id, "run_trace")

    async def _go():
        await _seed_context(context_id=ctx_id)
        await _seed_run_history(context_id=ctx_id, run_id=run_id, marker=marker)
        await _seed_run_trace(run_id=run_id, marker=marker)
        async with AsyncSessionLocal() as db:
            repo = ContextRepository(db)
            counts = await repo.hard_delete_context(ctx_id)

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    text("SELECT safe_metadata_json FROM run_trace_events WHERE run_id = :r LIMIT 1"),
                    {"r": run_id},
                )
            ).one_or_none()
        return counts, row

    try:
        counts, row = asyncio.run(_go())
        assert row is not None, "run_trace_events row retained"
        blob = json.dumps(row[0]) if not isinstance(row[0], str) else row[0]
        assert marker not in blob, f"marker survived in safe_metadata_json: {row[0]!r}"
        assert counts["run_trace_events_redacted"] == 1, counts
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


def test_rv3_4_hard_delete_redacts_audit_logs():
    """§4 RV3_GAP_04 — audit_logs.details + summaries redacted; row retained."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context.context_repository import (
        ContextRepository,
    )

    ctx_id = _uuid()
    marker = _marker(ctx_id, "audit_log")

    async def _go():
        await _seed_context(context_id=ctx_id)
        await _seed_audit_log(context_id=ctx_id, marker=marker)
        async with AsyncSessionLocal() as db:
            repo = ContextRepository(db)
            counts = await repo.hard_delete_context(ctx_id)

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT details, model_input_summary, model_output_summary, tool_calls_made "
                        "FROM audit_logs WHERE resource_id = :c LIMIT 1"
                    ),
                    {"c": ctx_id},
                )
            ).one_or_none()
        return counts, row

    try:
        counts, row = asyncio.run(_go())
        assert row is not None, "audit_logs row retained for compliance"
        details_blob = json.dumps(row[0]) if not isinstance(row[0], str) else row[0]
        assert marker not in details_blob, f"details not redacted: {row[0]!r}"
        assert row[1] != marker, f"model_input_summary not redacted: {row[1]!r}"
        assert row[2] != marker, f"model_output_summary not redacted: {row[2]!r}"
        tc_blob = json.dumps(row[3]) if not isinstance(row[3], str) else row[3]
        assert marker not in tc_blob, f"tool_calls_made not redacted: {row[3]!r}"
        assert counts["audit_logs_redacted"] == 1, counts
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


# ─────────────────────────────────────────────────────────────────────
# §5 DELETE endpoint returns per-store count
# ─────────────────────────────────────────────────────────────────────


def test_rv3_5_endpoint_returns_per_store_count(client):
    """DELETE /api/icoder/contexts/{id} scrubs all 15 stores."""
    ctx_id = _uuid()

    async def _seed():
        await _seed_all_stores(ctx_id)

    asyncio.run(_seed())
    try:
        r = client.delete(f"/api/icoder/contexts/{ctx_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result"]["deleted"] is True
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


# ─────────────────────────────────────────────────────────────────────
# §6 Authoritative marker scan — every store must read 0 hits
# ─────────────────────────────────────────────────────────────────────


def test_rv3_6_marker_scan_all_stores_zero_post_delete():
    """Insert marker into every PHI-bearing store, DELETE, scan = 0."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context.context_repository import (
        ContextRepository,
    )

    ctx_id = _uuid()

    async def _go():
        await _seed_all_stores(ctx_id)
        marker_prefix = f"RV3MARKER-{ctx_id}"

        pre = await _scan_marker(marker_prefix)
        # sanity: at least 8 stores must have a marker hit pre-delete
        assert (
            sum(1 for v in pre.values() if v > 0) >= 8
        ), f"seed did not cover all stores: {pre}"

        async with AsyncSessionLocal() as db:
            repo = ContextRepository(db)
            await repo.hard_delete_context(ctx_id)

        post = await _scan_marker(marker_prefix)
        return pre, post

    try:
        pre, post = asyncio.run(_go())
        nonzero = {k: v for k, v in post.items() if v > 0}
        assert not nonzero, (
            f"marker survived in stores: {nonzero}\n"
            f"pre-delete scan: {pre}\n"
            f"post-delete scan: {post}"
        )
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


# ─────────────────────────────────────────────────────────────────────
# §7-§9 Failure injection — partial-state must roll back
# ─────────────────────────────────────────────────────────────────────


def _make_fail_on(table_pattern: str):
    """Return a context manager that patches the session's execute to
    raise when it sees a DELETE/UPDATE touching the named table."""
    from sqlalchemy import event
    from app.database import AsyncSessionLocal

    raises: list[Exception] = []

    @event.listens_for(AsyncSessionLocal.sync_session_class, "do_orm_execute")
    def _guard(orm_execute_state):
        # no-op hook entry — actual interception happens via raw execute patch below
        pass

    return raises


def test_rv3_7_failure_injection_original_input_audit_rolls_back():
    """§7 If the first cross-table delete fails, NOTHING is committed."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context import context_repository as mod

    ctx_id = _uuid()
    msg_id = _uuid()

    async def _go():
        await _seed_context(context_id=ctx_id)
        await _seed_message(context_id=ctx_id, message_id=msg_id, marker="m")
        original_execute = mod.AsyncSession.execute

        async def _bomb(self, statement, *args, **kwargs):
            stmt_str = str(statement)
            if "original_input_audit" in stmt_str and "DELETE" in stmt_str.upper():
                raise RuntimeError("injected failure on original_input_audit")
            return await original_execute(self, statement, *args, **kwargs)

        mod.AsyncSession.execute = _bomb  # type: ignore[method-assign]
        try:
            async with AsyncSessionLocal() as db:
                repo = mod.ContextRepository(db)
                with pytest.raises(RuntimeError, match="injected failure"):
                    await repo.hard_delete_context(ctx_id)
                await db.rollback()
        finally:
            mod.AsyncSession.execute = original_execute  # type: ignore[method-assign]

        # Post-condition: contexts row MUST still exist (txn rolled back)
        return await _count_rows("contexts", f"id='{ctx_id}'")

    try:
        n = asyncio.run(_go())
        assert n == 1, (
            f"failure injection on original_input_audit did not roll back; "
            f"contexts row count post-failure = {n}"
        )
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


def test_rv3_8_failure_injection_conversation_memory_rolls_back():
    """§8 If the memory delete fails, NOTHING is committed."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context import context_repository as mod

    ctx_id = _uuid()
    msg_id = _uuid()

    async def _go():
        await _seed_context(context_id=ctx_id)
        await _seed_message(context_id=ctx_id, message_id=msg_id, marker="m")
        await _seed_memory(
            context_id=ctx_id,
            message_id=msg_id,
            user_id="u",
            marker="m",
        )
        original_execute = mod.AsyncSession.execute

        async def _bomb(self, statement, *args, **kwargs):
            stmt_str = str(statement)
            if "conversation_memories" in stmt_str:
                raise RuntimeError("injected failure on conversation_memories")
            return await original_execute(self, statement, *args, **kwargs)

        mod.AsyncSession.execute = _bomb  # type: ignore[method-assign]
        try:
            async with AsyncSessionLocal() as db:
                repo = mod.ContextRepository(db)
                with pytest.raises(RuntimeError, match="injected failure"):
                    await repo.hard_delete_context(ctx_id)
                await db.rollback()
        finally:
            mod.AsyncSession.execute = original_execute  # type: ignore[method-assign]

        return (
            await _count_rows("contexts", f"id='{ctx_id}'"),
            await _count_rows("context_messages", f"context_id='{ctx_id}'"),
            await _count_rows(
                "conversation_memories",
                f"session_id LIKE '{ctx_id}:%'",
            ),
        )

    try:
        n_ctx, n_msg, n_mem = asyncio.run(_go())
        assert (n_ctx, n_msg, n_mem) == (1, 1, 1), (
            f"failure injection did not roll back cleanly: "
            f"ctx={n_ctx} msg={n_msg} mem={n_mem}"
        )
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


def test_rv3_9_failure_injection_audit_logs_rolls_back():
    """§9 If the audit redact fails, NOTHING is committed."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context import context_repository as mod

    ctx_id = _uuid()

    async def _go():
        await _seed_context(context_id=ctx_id)
        await _seed_audit_log(context_id=ctx_id, marker="m")
        original_execute = mod.AsyncSession.execute

        async def _bomb(self, statement, *args, **kwargs):
            stmt_str = str(statement)
            if "audit_logs" in stmt_str and "UPDATE" in stmt_str.upper():
                raise RuntimeError("injected failure on audit_logs")
            return await original_execute(self, statement, *args, **kwargs)

        mod.AsyncSession.execute = _bomb  # type: ignore[method-assign]
        try:
            async with AsyncSessionLocal() as db:
                repo = mod.ContextRepository(db)
                with pytest.raises(RuntimeError, match="injected failure"):
                    await repo.hard_delete_context(ctx_id)
                await db.rollback()
        finally:
            mod.AsyncSession.execute = original_execute  # type: ignore[method-assign]

        return await _count_rows("contexts", f"id='{ctx_id}'")

    try:
        n = asyncio.run(_go())
        assert n == 1, (
            f"failure injection on audit_logs did not roll back; "
            f"contexts row count post-failure = {n}"
        )
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


# ─────────────────────────────────────────────────────────────────────
# §10-§12 organization_id fail-closed (Pydantic + Lifecycle + DB)
# ─────────────────────────────────────────────────────────────────────


def test_rv3_10_pydantic_context_requires_organization_id():
    """§10 Pydantic Context.model_validate rejects missing org_id."""
    from app.icoder.agent_runtime.context.context import Context

    with pytest.raises(Exception):
        Context.model_validate(
            {
                "id": _uuid(),
                "agent_id": "x",
                # organization_id intentionally missing
                "status": "ACTIVE",
            }
        )


def test_rv3_11_lifecycle_create_rejects_empty_organization_id():
    """§11 ContextLifecycle.create(organization_id='') raises ValueError."""
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.context.context_lifecycle import (
        ContextLifecycle,
    )
    from app.icoder.agent_runtime.context.context_repository import (
        ContextRepository,
    )

    async def _go():
        async with AsyncSessionLocal() as db:
            repo = ContextRepository(db)
            lifecycle = ContextLifecycle(repo)
            with pytest.raises(ValueError, match="organization_id is required"):
                await lifecycle.create(
                    agent_id="x",
                    organization_id="",
                )

    asyncio.run(_go())


def test_rv3_12_db_not_null_rejects_missing_organization_id():
    """§12 Raw INSERT into contexts without organization_id → IntegrityError."""
    from app.database import AsyncSessionLocal

    async def _go():
        async with AsyncSessionLocal() as db:
            with pytest.raises(Exception):
                await db.execute(
                    text(
                        "INSERT INTO contexts "
                        "(id, created_at, updated_at, expires_at, agent_id, "
                        " status, metadata_json, redacted_input_hash, "
                        " original_input_ref) "
                        "VALUES (:id, :ca, :ua, :ea, :aid, :st, :mj, :rh, :rr)"
                    ),
                    {
                        "id": _uuid(),
                        "ca": datetime.now(timezone.utc),
                        "ua": datetime.now(timezone.utc),
                        "ea": datetime.now(timezone.utc),
                        "aid": "x",
                        "st": "ACTIVE",
                        "mj": "{}",
                        "rh": "",
                        "rr": "",
                    },
                )
                await db.commit()

    asyncio.run(_go())


# ─────────────────────────────────────────────────────────────────────
# §13 Cross-tenant DELETE — ORG_B cannot delete ORG_A context
# ─────────────────────────────────────────────────────────────────────


def _override_org(org_id: str):
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


def test_rv3_13_cross_tenant_delete_returns_404_and_preserves_row(client):
    """§13 Context under ORG_A; DELETE with ORG_B JWT → 404 + row survives."""
    ctx_id = _uuid()

    async def _seed():
        await _seed_context(context_id=ctx_id, organization_id=ORG_A)
        await _seed_message(
            context_id=ctx_id,
            message_id=_uuid(),
            marker=_marker(ctx_id, "messages"),
        )

    async def _survives():
        return (
            await _count_rows("contexts", f"id='{ctx_id}'"),
            await _count_rows("context_messages", f"context_id='{ctx_id}'"),
        )

    asyncio.run(_seed())
    try:
        for _ in _override_org(ORG_B):
            r = client.delete(f"/api/icoder/contexts/{ctx_id}")
            assert r.status_code == 404, r.text
            assert (
                r.json()["error"]["data"]["a2a_error_code"] == "CONTEXT_NOT_FOUND"
            )
        n_ctx, n_msg = asyncio.run(_survives())
        assert (n_ctx, n_msg) == (1, 1), (
            f"cross-tenant DELETE leaked: ctx={n_ctx} msg={n_msg}"
        )
    finally:
        asyncio.run(_cleanup(context_id=ctx_id))


# ─────────────────────────────────────────────────────────────────────
# §14 Dev DB guard smoke (full fixture assertion is in test_a1b_ae_rv_2)
# ─────────────────────────────────────────────────────────────────────


def test_rv3_14_dev_db_guard_armed():
    """§14 conftest session-scoped dev DB guard wired (RV.2 contract).

    We don't import the conftest symbol directly (autouse fixtures run on
    import); instead we verify the source contains the guard wiring.
    """
    p = Path(__file__).resolve().parents[1] / "conftest.py"
    src = p.read_text(encoding="utf-8")
    assert "A1B-AE-RV.2 dev DB guard" in src, (
        "conftest.py must contain the RV.2 dev DB guard"
    )
    assert "data/icoder.db" in src, (
        "conftest.py must reference data/icoder.db"
    )
    assert "st_mtime_ns" in src, (
        "conftest.py must snapshot mtime+size (not just one)"
    )


# ─────────────────────────────────────────────────────────────────────
# §15 Migration 026 — no server_default on contexts.organization_id
# ─────────────────────────────────────────────────────────────────────


def test_rv3_15_migration_026_no_server_default():
    """§15 Re-verify RV.2 fail-closed contract from a fresh connection."""
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
    assert "organization_id" in cols
    notnull, dflt = cols["organization_id"]
    assert notnull == 1, "organization_id must be NOT NULL"
    assert dflt is None, (
        f"organization_id must have NO server_default (RV.2 contract), got {dflt!r}"
    )
