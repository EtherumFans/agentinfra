"""C7 — context_audit: record / get / prune / verify (DB)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.icoder.agent_runtime.context import (
    ContextAudit,
    ContextIsolationError,
    hash_original_input,
)
from app.icoder.agent_runtime.context.db_models import (
    ContextRow,
    OriginalInputAuditRow,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa.event.listens_for(eng.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(ContextRow.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def test_record_writes_row_with_90d_retention(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440000"
    before = _now()
    row = await audit.record_original_input(cid, "raw PHI text")
    after = _now()

    assert row.context_id == cid
    assert row.original_input == "raw PHI text"
    expected_min = (before + timedelta(days=90)).timestamp()
    expected_max = (after + timedelta(days=90)).timestamp()
    assert expected_min <= row.retention_until.timestamp() <= expected_max + 1


async def test_record_with_custom_retention(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440001"
    row = await audit.record_original_input(cid, "x", retention_days=7)
    delta = (row.retention_until - row.created_at).total_seconds()
    assert 7 * 86400 - 5 <= delta <= 7 * 86400 + 5


async def test_record_rejects_invalid_context_id(session):
    audit = ContextAudit(session)
    with pytest.raises(ContextIsolationError):
        await audit.record_original_input("not-a-uuid", "x")


async def test_get_by_context_returns_only_matching(session):
    audit = ContextAudit(session)
    a = "550e8400-e29b-41d4-a716-446655440002"
    b = "550e8400-e29b-41d4-a716-446655440003"
    await audit.record_original_input(a, "alpha")
    await audit.record_original_input(a, "alpha 2")
    await audit.record_original_input(b, "beta")

    a_rows = await audit.get_by_context(a)
    b_rows = await audit.get_by_context(b)

    assert {r.original_input for r in a_rows} == {"alpha", "alpha 2"}
    assert {r.original_input for r in b_rows} == {"beta"}


async def test_get_by_context_rejects_invalid_id(session):
    audit = ContextAudit(session)
    with pytest.raises(ContextIsolationError):
        await audit.get_by_context("not-a-uuid")


async def test_prune_expired_deletes_only_overdue(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440004"

    old = await audit.record_original_input(
        cid, "old", retention_days=1, now=_now() - timedelta(days=2)
    )
    new = await audit.record_original_input(cid, "new", retention_days=90)

    deleted = await audit.prune_expired(now=_now())
    assert old.id in deleted
    assert new.id not in deleted

    surviving = await audit.get_by_context(cid)
    assert {r.id for r in surviving} == {new.id}


async def test_prune_expired_empty_when_nothing_overdue(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440005"
    await audit.record_original_input(cid, "fresh", retention_days=90)
    deleted = await audit.prune_expired(now=_now())
    assert deleted == []


async def test_verify_against_context_returns_true_on_match(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440006"
    raw = "病人张三 13012345678"
    await audit.record_original_input(cid, raw)

    assert await audit.verify_against_context(cid, raw) is True


async def test_verify_against_context_returns_false_on_mismatch(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440007"
    await audit.record_original_input(cid, "stored")

    assert await audit.verify_against_context(cid, "different") is False


async def test_verify_against_context_returns_false_for_unknown(session):
    audit = ContextAudit(session)
    assert (
        await audit.verify_against_context(
            "550e8400-e29b-41d4-a716-446655440099", "x"
        )
        is False
    )


async def test_audit_survives_context_deletion(session):
    """Destroying a Context does NOT touch its audit row (SPEC §5.5)."""
    from app.icoder.agent_runtime.context import (
        Context,
        ContextLifecycle,
        ContextRepository,
        ContextStatus,
    )

    repo = ContextRepository(session)
    audit = ContextAudit(session)

    now = _now()
    ctx = Context(
        id="550e8400-e29b-41d4-a716-446655440008",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        agent_id="a",
        status=ContextStatus.ACTIVE,
    )
    await repo.create_context(ctx)
    await audit.record_original_input(ctx.id, "raw PHI")

    await repo.delete_context(ctx.id)

    rows = await audit.get_by_context(ctx.id)
    assert len(rows) == 1
    assert rows[0].original_input == "raw PHI"


async def test_audit_hash_consistency_with_helper(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-44665544000a"
    raw = "hello audit"
    row = await audit.record_original_input(cid, raw)
    assert hash_original_input(raw) == hash_original_input(row.original_input)