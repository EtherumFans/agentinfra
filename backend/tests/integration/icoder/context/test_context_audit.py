"""C7 — context_audit: record / get / prune / verify (DB)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.icoder.agent_runtime.context import (
    ContextAudit,
    ContextIsolationError,
    hash_original_input,
)
from app.icoder.agent_runtime.context.db_models import (
    ContextRow,
    OriginalInputAuditRow,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql_compat]

AUDIT_ORG = "test-org"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def test_record_writes_row_with_90d_retention(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440000"
    before = _now()
    row = await audit.record_original_input(
        cid, "raw PHI text", organization_id=AUDIT_ORG
    )
    after = _now()

    assert row.context_id == cid
    assert row.original_input == "raw PHI text"
    expected_min = (before + timedelta(days=90)).timestamp()
    expected_max = (after + timedelta(days=90)).timestamp()
    assert expected_min <= row.retention_until.timestamp() <= expected_max + 1


async def test_record_with_custom_retention(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440001"
    row = await audit.record_original_input(
        cid, "x", organization_id=AUDIT_ORG, retention_days=7
    )
    delta = (row.retention_until - row.created_at).total_seconds()
    assert 7 * 86400 - 5 <= delta <= 7 * 86400 + 5


async def test_record_rejects_invalid_context_id(session):
    audit = ContextAudit(session)
    with pytest.raises(ContextIsolationError):
        await audit.record_original_input("not-a-uuid", "x")


async def test_record_without_context_requires_explicit_organization(session):
    audit = ContextAudit(session)
    with pytest.raises(ValueError, match="organization_id is required"):
        await audit.record_original_input(
            "550e8400-e29b-41d4-a716-446655440011", "orphan"
        )


async def test_get_by_context_returns_only_matching(session):
    audit = ContextAudit(session)
    a = "550e8400-e29b-41d4-a716-446655440002"
    b = "550e8400-e29b-41d4-a716-446655440003"
    await audit.record_original_input(a, "alpha", organization_id=AUDIT_ORG)
    await audit.record_original_input(a, "alpha 2", organization_id=AUDIT_ORG)
    await audit.record_original_input(b, "beta", organization_id=AUDIT_ORG)

    a_rows = await audit.get_by_context(a)
    b_rows = await audit.get_by_context(b)

    assert {r.original_input for r in a_rows} == {"alpha", "alpha 2"}
    assert {r.original_input for r in b_rows} == {"beta"}


async def test_same_timestamp_writes_receive_distinct_audit_ids(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440010"
    fixed_now = _now()

    first = await audit.record_original_input(
        cid, "first", organization_id=AUDIT_ORG, now=fixed_now
    )
    second = await audit.record_original_input(
        cid, "second", organization_id=AUDIT_ORG, now=fixed_now
    )

    assert first.id != second.id
    assert {row.original_input for row in await audit.get_by_context(cid)} == {
        "first",
        "second",
    }


async def test_get_by_context_rejects_invalid_id(session):
    audit = ContextAudit(session)
    with pytest.raises(ContextIsolationError):
        await audit.get_by_context("not-a-uuid")


async def test_prune_expired_deletes_only_overdue(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440004"

    old = await audit.record_original_input(
        cid, "old", organization_id=AUDIT_ORG,
        retention_days=1, now=_now() - timedelta(days=2)
    )
    new = await audit.record_original_input(
        cid, "new", organization_id=AUDIT_ORG, retention_days=90
    )

    deleted = await audit.prune_expired(now=_now())
    assert old.id in deleted
    assert new.id not in deleted

    surviving = await audit.get_by_context(cid)
    assert {r.id for r in surviving} == {new.id}


async def test_prune_expired_empty_when_nothing_overdue(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440005"
    await audit.record_original_input(
        cid, "fresh", organization_id=AUDIT_ORG, retention_days=90
    )
    deleted = await audit.prune_expired(now=_now())
    assert deleted == []


async def test_verify_against_context_returns_true_on_match(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440006"
    raw = "病人张三 13012345678"
    await audit.record_original_input(cid, raw, organization_id=AUDIT_ORG)

    assert await audit.verify_against_context(cid, raw) is True


async def test_verify_against_context_returns_false_on_mismatch(session):
    audit = ContextAudit(session)
    cid = "550e8400-e29b-41d4-a716-446655440007"
    await audit.record_original_input(cid, "stored", organization_id=AUDIT_ORG)

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
        organization_id="test-org",
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
    row = await audit.record_original_input(cid, raw, organization_id=AUDIT_ORG)
    assert hash_original_input(raw) == hash_original_input(row.original_input)
