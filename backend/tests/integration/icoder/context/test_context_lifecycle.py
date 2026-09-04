"""C6 — ContextLifecycle integration: create / complete / fail / expire / sweep / destroy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.icoder.agent_runtime.context import (
    Context,
    ContextAudit,
    ContextLifecycle,
    ContextLifecycleError,
    ContextMessage,
    ContextRepository,
    ContextStatus,
)
pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql_compat]


@pytest_asyncio.fixture
async def repo(session) -> ContextRepository:
    return ContextRepository(session)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clock():
    cur = {"now": _now()}

    def fn() -> datetime:
        return cur["now"]

    def advance(seconds: int) -> None:
        cur["now"] = cur["now"] + timedelta(seconds=seconds)

    return fn, advance


async def test_create_emits_event_and_returns_active_context(repo):
    events: list[tuple[str, dict]] = []

    async def sink(stage: str, payload: dict) -> None:
        events.append((stage, payload))

    lc = ContextLifecycle(repo, event_sink=sink)
    ctx = await lc.create(organization_id="test-org", agent_id="homepage-coding-review")

    assert ctx.status == ContextStatus.ACTIVE
    assert ctx.agent_id == "homepage-coding-review"
    assert ctx.expires_at > ctx.created_at
    assert events and events[0][0] == "context_created"
    assert events[0][1]["agent_id"] == "homepage-coding-review"


async def test_create_with_initial_message_appends(repo):
    events: list[tuple[str, dict]] = []

    async def sink(stage, payload):
        events.append((stage, payload))

    lc = ContextLifecycle(repo, event_sink=sink)
    msg = ContextMessage(
        message_id="m-1",
        role="user",
        parts=[{"type": "text", "text": "hi"}],
        timestamp=_now(),
    )
    ctx = await lc.create(organization_id="test-org", agent_id="a", initial_message=msg)

    msgs = await repo.get_messages(ctx.id)
    assert len(msgs) == 1
    assert msgs[0].message_id == "m-1"
    assert any(e[0] == "context_message_added" for e in events)


async def test_complete_transitions_active_to_completed(repo):
    lc = ContextLifecycle(
        repo,
        completed_ttl_seconds=3600,
    )
    ctx = await lc.create(organization_id="test-org", agent_id="a")

    completed = await lc.complete(ctx.id)

    assert completed.status == ContextStatus.COMPLETED
    assert completed.expires_at < ctx.expires_at
    reloaded = await repo.get_context(ctx.id)
    assert reloaded.status == ContextStatus.COMPLETED


async def test_complete_emits_event_with_counts(repo):
    events: list[tuple[str, dict]] = []

    async def sink(stage, payload):
        events.append((stage, payload))

    lc = ContextLifecycle(repo, event_sink=sink)
    ctx = await lc.create(organization_id="test-org", agent_id="a")
    await repo.add_message(
        ctx.id,
        ContextMessage(
            message_id="m-1", role="user", parts=[], timestamp=_now()
        ),
    )

    await lc.complete(ctx.id)

    completed_event = next(e for e in events if e[0] == "context_completed")
    assert completed_event[1]["total_messages"] == 1
    assert completed_event[1]["total_tasks"] == 0


async def test_complete_on_completed_raises(repo):
    lc = ContextLifecycle(repo)
    ctx = await lc.create(organization_id="test-org", agent_id="a")
    await lc.complete(ctx.id)
    with pytest.raises(ContextLifecycleError):
        await lc.complete(ctx.id)


async def test_fail_transitions_active_to_failed(repo):
    lc = ContextLifecycle(repo)
    ctx = await lc.create(organization_id="test-org", agent_id="a")

    failed = await lc.fail(ctx.id, error_code="E1", error_stage="planning")

    assert failed.status == ContextStatus.FAILED
    reloaded = await repo.get_context(ctx.id)
    assert reloaded.status == ContextStatus.FAILED


async def test_fail_emits_event_with_error_codes(repo):
    events: list[tuple[str, dict]] = []

    async def sink(stage, payload):
        events.append((stage, payload))

    lc = ContextLifecycle(repo, event_sink=sink)
    ctx = await lc.create(organization_id="test-org", agent_id="a")

    await lc.fail(ctx.id, error_code="E_PLAN", error_stage="planner")

    fail_event = next(e for e in events if e[0] == "context_failed")
    assert fail_event[1]["error_code"] == "E_PLAN"
    assert fail_event[1]["error_stage"] == "planner"


async def test_fail_on_failed_raises(repo):
    lc = ContextLifecycle(repo)
    ctx = await lc.create(organization_id="test-org", agent_id="a")
    await lc.fail(ctx.id, error_code="x", error_stage="y")
    with pytest.raises(ContextLifecycleError):
        await lc.fail(ctx.id, error_code="x", error_stage="y")


async def test_assert_can_mutate_blocks_terminal_states(repo):
    lc = ContextLifecycle(repo)
    ctx = await lc.create(organization_id="test-org", agent_id="a")
    await lc.complete(ctx.id)

    with pytest.raises(ContextLifecycleError):
        await lc.assert_can_mutate(ctx.id)


async def test_assert_can_mutate_blocks_unknown_context(repo):
    from app.icoder.agent_runtime.context.context_isolation import (
        ContextIsolationError,
    )

    lc = ContextLifecycle(repo)
    with pytest.raises(ContextIsolationError):
        await lc.assert_can_mutate("550e8400-e29b-41d4-a716-446655449999")


async def test_expire_if_overdue_marks_active_expired(repo):
    now_fn, advance = _clock()
    lc = ContextLifecycle(repo, ttl_seconds=10, now_fn=now_fn)
    ctx = await lc.create(organization_id="test-org", agent_id="a")
    advance(11)

    expired = await lc.expire_if_overdue(ctx.id)

    assert expired is not None
    assert expired.status == ContextStatus.EXPIRED


async def test_expire_if_overdue_no_op_for_active_not_yet_overdue(repo):
    lc = ContextLifecycle(repo, ttl_seconds=3600)
    ctx = await lc.create(organization_id="test-org", agent_id="a")
    result = await lc.expire_if_overdue(ctx.id)
    assert result is not None
    assert result.status == ContextStatus.ACTIVE


async def test_expire_if_overdue_returns_none_for_unknown(repo):
    lc = ContextLifecycle(repo)
    assert await lc.expire_if_overdue("550e8400-e29b-41d4-a716-446655449998") is None


async def test_sweep_expired_marks_multiple_overdue(repo):
    now_fn, advance = _clock()
    lc = ContextLifecycle(
        repo, ttl_seconds=10, completed_ttl_seconds=10, now_fn=now_fn
    )
    a = await lc.create(organization_id="test-org", agent_id="a")
    b = await lc.create(organization_id="test-org", agent_id="a")
    await lc.complete(b.id)
    advance(11)

    expired_ids = await lc.sweep_expired()

    assert set(expired_ids) == {a.id, b.id}
    for cid in (a.id, b.id):
        reloaded = await repo.get_context(cid)
        assert reloaded.status == ContextStatus.EXPIRED


async def test_sweep_expired_skips_fresh_contexts(repo):
    now_fn, advance = _clock()
    lc = ContextLifecycle(repo, ttl_seconds=3600, now_fn=now_fn)
    fresh = await lc.create(organization_id="test-org", agent_id="a")
    advance(0)

    expired_ids = await lc.sweep_expired()

    assert expired_ids == []
    reloaded = await repo.get_context(fresh.id)
    assert reloaded.status == ContextStatus.ACTIVE


async def test_destroy_expired_deletes_after_grace(repo):
    now_fn, advance = _clock()
    lc = ContextLifecycle(repo, ttl_seconds=10, grace_seconds=60, now_fn=now_fn)
    a = await lc.create(organization_id="test-org", agent_id="a")
    advance(11)
    await lc.expire_if_overdue(a.id)

    advance(50)
    destroyed = await lc.destroy_expired()
    assert destroyed == []
    assert await repo.get_context(a.id) is not None

    advance(11)
    destroyed = await lc.destroy_expired()
    assert destroyed == [a.id]
    assert await repo.get_context(a.id) is None


async def test_destroy_expired_cascades_children_but_keeps_audit(repo):
    now_fn, advance = _clock()
    lc = ContextLifecycle(repo, ttl_seconds=10, grace_seconds=10, now_fn=now_fn)
    ctx = await lc.create(organization_id="test-org", agent_id="a")
    await repo.add_message(
        ctx.id,
        ContextMessage(
            message_id="m-1", role="user", parts=[], timestamp=_now()
        ),
    )

    from app.icoder.agent_runtime.context.db_models import OriginalInputAuditRow

    await ContextAudit(lc._repo._session).record_original_input(
        ctx.id,
        "raw PHI",
        audit_id="audit-1",
        now=now_fn(),
    )

    advance(11)
    await lc.expire_if_overdue(ctx.id)
    advance(11)

    destroyed = await lc.destroy_expired()
    assert destroyed == [ctx.id]

    msgs = await repo.get_messages(ctx.id)
    assert msgs == []

    surviving = await lc._repo._session.get(OriginalInputAuditRow, "audit-1")
    assert surviving is not None
    assert surviving.context_id == ctx.id


async def test_destroy_expired_emits_event(repo):
    events: list[tuple[str, dict]] = []

    async def sink(stage, payload):
        events.append((stage, payload))

    now_fn, advance = _clock()
    lc = ContextLifecycle(
        repo, ttl_seconds=10, grace_seconds=10, now_fn=now_fn, event_sink=sink
    )
    a = await lc.create(organization_id="test-org", agent_id="a")
    advance(11)
    await lc.expire_if_overdue(a.id)
    advance(11)

    await lc.destroy_expired()

    destroyed = next(e for e in events if e[0] == "context_destroyed")
    assert destroyed[1]["contextId"] == a.id
    assert destroyed[1]["reason"] == "grace_elapsed"
