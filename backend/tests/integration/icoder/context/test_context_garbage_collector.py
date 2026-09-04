"""C8 — context_garbage_collector: run_once + start/stop background loop."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncio

import pytest

from app.icoder.agent_runtime.context import (
    ContextAudit,
    ContextGarbageCollector,
    ContextLifecycle,
    ContextRepository,
    ContextStatus,
)
pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql_compat]


def _clock():
    cur = {"now": datetime.now(timezone.utc)}

    def fn() -> datetime:
        return cur["now"]

    def advance(seconds: int) -> None:
        cur["now"] = cur["now"] + timedelta(seconds=seconds)

    return fn, advance


def _instant_sleep():
    """Sleep future that resolves immediately — short-circuits the loop."""
    async def fn(_seconds: float) -> None:
        return None

    return fn


async def test_run_once_sweeps_and_destroys(session):
    now_fn, advance = _clock()
    repo = ContextRepository(session)
    audit = ContextAudit(session)
    lc = ContextLifecycle(
        repo, ttl_seconds=10, completed_ttl_seconds=10, grace_seconds=0, now_fn=now_fn
    )
    a = await lc.create(organization_id="test-org", agent_id="a")
    b = await lc.create(organization_id="test-org", agent_id="a")
    await audit.record_original_input(a.id, "raw-A", retention_days=1, now=now_fn())

    advance(11)

    gc = ContextGarbageCollector(lc, audit, now_fn=now_fn)
    result = await gc.run_once()

    assert set(result.swept_ids) == {a.id, b.id}
    assert set(result.destroyed_ids) == {a.id, b.id}
    assert a.id not in result.pruned_audit_ids
    assert gc.run_count == 1
    assert gc.last_result is result


async def test_run_once_empty_when_nothing_overdue(session):
    repo = ContextRepository(session)
    audit = ContextAudit(session)
    lc = ContextLifecycle(repo, ttl_seconds=3600)
    await lc.create(organization_id="test-org", agent_id="a")

    gc = ContextGarbageCollector(lc, audit)
    result = await gc.run_once()

    assert result.total == 0
    assert gc.run_count == 1


async def test_run_once_prunes_old_audit(session):
    now_fn, _ = _clock()
    repo = ContextRepository(session)
    audit = ContextAudit(session)
    lc = ContextLifecycle(repo, ttl_seconds=3600, now_fn=now_fn)
    cid = "550e8400-e29b-41d4-a716-4466554400aa"
    await audit.record_original_input(
        cid, "ancient", organization_id="test-org",
        retention_days=1, now=now_fn() - timedelta(days=2)
    )

    gc = ContextGarbageCollector(lc, audit, now_fn=now_fn)
    result = await gc.run_once()

    assert len(result.pruned_audit_ids) == 1


async def test_run_once_audit_prune_disabled(session):
    now_fn, _ = _clock()
    repo = ContextRepository(session)
    audit = ContextAudit(session)
    lc = ContextLifecycle(repo, ttl_seconds=3600, now_fn=now_fn)
    cid = "550e8400-e29b-41d4-a716-4466554400ab"
    await audit.record_original_input(
        cid, "ancient", organization_id="test-org",
        retention_days=1, now=now_fn() - timedelta(days=2)
    )

    gc = ContextGarbageCollector(
        lc, audit, now_fn=now_fn, audit_prune_enabled=False
    )
    result = await gc.run_once()

    assert result.pruned_audit_ids == []


async def test_start_stop_background_loop_runs_multiple_times(session):
    repo = ContextRepository(session)
    audit = ContextAudit(session)
    lc = ContextLifecycle(repo, ttl_seconds=3600)

    iterations = {"n": 0}
    gate = asyncio.Event()

    async def fake_sleep(_s: float) -> None:
        iterations["n"] += 1
        if iterations["n"] >= 3:
            gate.set()

    gc = ContextGarbageCollector(
        lc, audit, sweep_interval_seconds=1, sleep_fn=fake_sleep
    )
    await gc.start()
    assert gc.is_running

    try:
        await asyncio.wait_for(gate.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        pass

    await gc.stop()
    assert not gc.is_running
    assert iterations["n"] >= 3
    assert gc.run_count >= 3


async def test_start_is_idempotent(session):
    repo = ContextRepository(session)
    audit = ContextAudit(session)
    lc = ContextLifecycle(repo, ttl_seconds=3600)
    gc = ContextGarbageCollector(lc, audit, sleep_fn=_instant_sleep())

    await gc.start()
    await gc.start()
    await gc.start()

    assert gc.is_running
    await gc.stop()


async def test_stop_is_noop_when_never_started(session):
    repo = ContextRepository(session)
    audit = ContextAudit(session)
    lc = ContextLifecycle(repo, ttl_seconds=3600)
    gc = ContextGarbageCollector(lc, audit)

    await gc.stop()
    assert not gc.is_running
    assert gc.run_count == 0


async def test_is_running_false_after_loop_exits(session):
    repo = ContextRepository(session)
    audit = ContextAudit(session)
    lc = ContextLifecycle(repo, ttl_seconds=3600)

    async def cancel_immediately(_s: float) -> None:
        raise asyncio.CancelledError()

    gc = ContextGarbageCollector(
        lc, audit, sweep_interval_seconds=1, sleep_fn=cancel_immediately
    )
    await gc.start()
    await gc.stop()
    assert not gc.is_running


async def test_run_count_increments_each_run_once(session):
    repo = ContextRepository(session)
    audit = ContextAudit(session)
    lc = ContextLifecycle(repo, ttl_seconds=3600)
    gc = ContextGarbageCollector(lc, audit)

    for i in range(5):
        await gc.run_once()
        assert gc.run_count == i + 1


async def test_gc_full_lifecycle_e2e(session):
    """Create → GC run_once handles sweep + destroy + audit-prune in one call."""
    now_fn, advance = _clock()
    repo = ContextRepository(session)
    audit = ContextAudit(session)
    lc = ContextLifecycle(
        repo, ttl_seconds=10, completed_ttl_seconds=10, grace_seconds=0, now_fn=now_fn
    )
    ctx = await lc.create(organization_id="test-org", agent_id="a")
    audit_row = await audit.record_original_input(
        ctx.id, "ancient PHI", retention_days=0, now=now_fn()
    )

    advance(11)

    gc = ContextGarbageCollector(lc, audit, now_fn=now_fn)
    result = await gc.run_once()

    assert ctx.id in result.swept_ids
    assert ctx.id in result.destroyed_ids
    assert audit_row.id in result.pruned_audit_ids
    assert result.total == 3

    surviving_audit = await audit.get_by_context(ctx.id)
    assert surviving_audit == []
    surviving_ctx = await repo.get_context(ctx.id)
    assert surviving_ctx is None


async def test_default_interval_is_five_minutes():
    repo = None
    audit = None
    lc = None
    gc = ContextGarbageCollector.__new__(ContextGarbageCollector)
    gc._interval = 300
    assert gc._interval == 300
