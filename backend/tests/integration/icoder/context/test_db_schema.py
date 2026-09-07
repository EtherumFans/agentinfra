"""C3 — DB schema migration + ORM round-trip (SPEC §4.3, §10)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from app.icoder.agent_runtime.context.db_models import (
    ContextArtifactRefRow,
    ContextMessageRow,
    ContextRow,
    ContextTaskRefRow,
    OriginalInputAuditRow,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql_compat]


def _now() -> datetime:
    # The legacy Context schema stores UTC in TIMESTAMP WITHOUT TIME ZONE.
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def test_all_five_tables_created(engine):
    async with engine.begin() as conn:
        rows = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_table_names()
        )
    expected = {
        "contexts",
        "context_messages",
        "context_task_refs",
        "context_artifact_refs",
        "original_input_audit",
    }
    assert expected.issubset(set(rows)), f"missing tables: {expected - set(rows)}"


async def test_context_round_trip(session):
    now = _now()
    row = ContextRow(
        id="550e8400-e29b-41d4-a716-446655440000",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        agent_id="homepage-coding-review",
        organization_id="test-org",
        status="active",
        metadata_json='{"production_writeback_blocked": true, "phi_redacted": true}',
        redacted_input_hash="abc123",
        original_input_ref="audit-1",
    )
    session.add(row)
    await session.commit()

    session.expunge_all()
    loaded = await session.get(ContextRow, row.id)
    assert loaded is not None
    assert loaded.agent_id == "homepage-coding-review"
    assert loaded.status == "active"
    assert loaded.metadata_json.startswith("{")


async def test_redacted_default_is_true(session):
    now = _now()
    ctx = ContextRow(
        id="550e8400-e29b-41d4-a716-446655440000",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        agent_id="a",
        organization_id="test-org",
        status="active",
        metadata_json="{}",
    )
    session.add(ctx)
    await session.commit()

    msg = ContextMessageRow(
        context_id=ctx.id,
        organization_id="test-org",
        message_id="m-1",
        role="user",
        parts_json="[]",
        timestamp=now,
    )
    session.add(msg)
    await session.commit()

    session.expunge_all()
    loaded = await session.get(ContextMessageRow, (ctx.id, "m-1"))
    assert loaded.redacted is True
    assert loaded.metadata_json == "{}"


async def test_cascade_delete_removes_child_rows(session):
    now = _now()
    cid = "550e8400-e29b-41d4-a716-446655440001"
    ctx = ContextRow(
        id=cid,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        agent_id="a",
        organization_id="test-org",
        status="active",
        metadata_json="{}",
    )
    session.add(ctx)
    session.add(
        ContextMessageRow(
            context_id=cid,
            organization_id="test-org",
            message_id="m-1",
            role="user",
            parts_json="[]",
            timestamp=now,
        )
    )
    session.add(
        ContextTaskRefRow(
            context_id=cid,
            organization_id="test-org",
            task_id="t-1",
            state="submitted",
            started_at=now,
        )
    )
    session.add(
        ContextArtifactRefRow(
            context_id=cid,
            organization_id="test-org",
            artifact_id="a-1",
            name="x.json",
            mime_type="application/json",
            url="https://x/a-1",
        )
    )
    await session.commit()

    await session.delete(ctx)
    await session.commit()

    msg = await session.get(
        ContextMessageRow, (cid, "m-1")
    )
    task = await session.get(
        ContextTaskRefRow, (cid, "t-1")
    )
    art = await session.get(
        ContextArtifactRefRow, (cid, "a-1")
    )
    assert msg is None
    assert task is None
    assert art is None


async def test_original_input_audit_does_not_cascade(session):
    now = _now()
    cid = "550e8400-e29b-41d4-a716-446655440002"
    ctx = ContextRow(
        id=cid,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        agent_id="a",
        organization_id="test-org",
        status="active",
        metadata_json="{}",
    )
    audit = OriginalInputAuditRow(
        id="audit-1",
        context_id=cid,
        organization_id="test-org",
        original_input="病人张三 130...",
        created_at=now,
        retention_until=now + timedelta(days=90),
    )
    session.add_all([ctx, audit])
    await session.commit()

    await session.delete(ctx)
    await session.commit()

    session.expunge_all()
    surviving = await session.get(OriginalInputAuditRow, "audit-1")
    assert surviving is not None
    assert surviving.context_id == cid


async def test_contexts_indexes_present(engine):
    async with engine.begin() as conn:
        indexes = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_indexes("contexts")
        )
    names = {ix["name"] for ix in indexes}
    assert "idx_contexts_expires_at" in names
    assert "idx_contexts_agent_id" in names
    assert "idx_contexts_status" in names


async def test_audit_indexes_present(engine):
    async with engine.begin() as conn:
        indexes = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_indexes("original_input_audit")
        )
    names = {ix["name"] for ix in indexes}
    assert "idx_original_input_audit_context_id" in names
    assert "idx_original_input_audit_retention" in names


async def test_context_status_column_is_text_not_enum(engine):
    async with engine.begin() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_columns("contexts")
        )
    status_col = next(c for c in cols if c["name"] == "status")
    assert "VARCHAR" in status_col["type"].__class__.__name__.upper() or status_col["type"].__class__.__name__ == "String"


async def test_messages_primary_key_is_composite(engine):
    async with engine.begin() as conn:
        pk = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_pk_constraint("context_messages")
        )
    assert "context_id" in pk["constrained_columns"]
    assert "message_id" in pk["constrained_columns"]


async def _seed_context(session, context_id="550e8400-e29b-41d4-a716-446655440004"):
    now = _now()
    session.add(ContextRow(
        id=context_id, organization_id="test-org", agent_id="schema-contract",
        created_at=now, updated_at=now, expires_at=now + timedelta(hours=24),
        status="active", metadata_json="{}",
    ))
    await session.commit()
    return context_id


async def test_database_server_defaults_without_orm(session):
    cid = "550e8400-e29b-41d4-a716-446655440004"
    # Raw SQL deliberately bypasses ORM defaults so Alembic defaults are tested.
    await session.execute(sa.text(
        "INSERT INTO contexts "
        "(id, organization_id, agent_id, created_at, updated_at, expires_at, status, metadata_json) "
        "VALUES (:cid, 'test-org', 'schema-contract', :now, :now, :now, 'active', '{}')"
    ), {"cid": cid, "now": _now()})
    await session.execute(sa.text(
        "INSERT INTO context_messages "
        "(context_id, organization_id, message_id, role, parts_json, timestamp) "
        "VALUES (:cid, 'test-org', 'server-default', 'user', '[]', :now)"
    ), {"cid": cid, "now": _now()})
    await session.commit()
    session.expunge_all()
    row = await session.get(ContextMessageRow, (cid, "server-default"))
    assert row.redacted is True
    assert row.metadata_json == "{}"
    ctx = await session.get(ContextRow, cid)
    assert ctx.redacted_input_hash == ctx.original_input_ref == ""


async def test_orphan_message_rejected_by_foreign_key(session):
    session.add(ContextMessageRow(
        context_id="550e8400-e29b-41d4-a716-446655440099",
        organization_id="test-org", message_id="orphan", role="user",
        parts_json="[]", timestamp=_now(),
    ))
    with pytest.raises(sa.exc.IntegrityError):
        await session.commit()
    await session.rollback()
    assert (await session.scalar(sa.select(sa.func.count()).select_from(ContextMessageRow))) == 0


async def test_invalid_task_state_rejected_by_database(session):
    cid = await _seed_context(session)
    session.add(ContextTaskRefRow(
        context_id=cid, organization_id="test-org", task_id="bad-state",
        state="unknown-state", started_at=_now(),
    ))
    with pytest.raises(sa.exc.IntegrityError):
        await session.commit()
    await session.rollback()
    assert await session.get(ContextRow, cid) is not None


async def test_duplicate_message_rejected_and_transaction_recovers(session):
    cid = await _seed_context(session)
    values = dict(context_id=cid, organization_id="test-org", message_id="duplicate",
                  role="user", parts_json="[]", timestamp=_now())
    session.add(ContextMessageRow(**values))
    await session.commit()
    session.expunge_all()
    session.add(ContextMessageRow(**values))
    with pytest.raises(sa.exc.IntegrityError):
        await session.commit()
    await session.rollback()
    assert await session.get(ContextMessageRow, (cid, "duplicate")) is not None
    assert (await session.scalar(sa.select(sa.func.count()).select_from(ContextMessageRow))) == 1
