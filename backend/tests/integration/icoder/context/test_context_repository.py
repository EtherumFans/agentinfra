"""C4 — ContextRepository isolation + round-trip."""

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
    Context,
    ContextArtifactRef,
    ContextIsolationError,
    ContextMessage,
    ContextNotFoundError,
    ContextRepository,
    ContextStatus,
    ContextTaskRef,
    generate_context_id,
)
from app.icoder.agent_runtime.context.db_models import ContextRow

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


async def _make_ctx(repo: ContextRepository, agent_id: str = "a") -> Context:
    now = _now()
    ctx = Context(
        id=generate_context_id(),
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        agent_id=agent_id,
        status=ContextStatus.ACTIVE,
    )
    await repo.create_context(ctx)
    return ctx


async def test_create_then_get_round_trip(session):
    repo = ContextRepository(session)
    ctx = await _make_ctx(repo)

    loaded = await repo.get_context(ctx.id)
    assert loaded is not None
    assert loaded.id == ctx.id
    assert loaded.agent_id == ctx.agent_id
    assert loaded.status == ContextStatus.ACTIVE
    assert loaded.metadata.production_writeback_blocked is True
    assert loaded.metadata.phi_redacted is True


async def test_get_context_invalid_id_raises_isolation_error(session):
    repo = ContextRepository(session)
    with pytest.raises(ContextIsolationError):
        await repo.get_context("not-a-uuid")


async def test_get_context_unknown_returns_none(session):
    repo = ContextRepository(session)
    cid = generate_context_id()
    assert await repo.get_context(cid) is None


async def test_add_message_requires_context_exists(session):
    repo = ContextRepository(session)
    msg = ContextMessage(
        message_id="m-1",
        role="user",
        parts=[{"type": "text", "text": "hi"}],
        timestamp=_now(),
    )
    with pytest.raises(ContextNotFoundError):
        await repo.add_message(generate_context_id(), msg)


async def test_add_message_invalid_id_raises(session):
    repo = ContextRepository(session)
    msg = ContextMessage(
        message_id="m-1",
        role="user",
        parts=[],
        timestamp=_now(),
    )
    with pytest.raises(ContextIsolationError):
        await repo.add_message("not-a-uuid", msg)


async def test_add_then_get_messages_filters_by_context(session):
    repo = ContextRepository(session)
    a = await _make_ctx(repo)
    b = await _make_ctx(repo)

    msg_a = ContextMessage(
        message_id="m-a",
        role="user",
        parts=[{"type": "text", "text": "alpha"}],
        timestamp=_now(),
    )
    msg_b = ContextMessage(
        message_id="m-b",
        role="user",
        parts=[{"type": "text", "text": "beta"}],
        timestamp=_now(),
    )
    await repo.add_message(a.id, msg_a)
    await repo.add_message(b.id, msg_b)

    a_msgs = await repo.get_messages(a.id)
    b_msgs = await repo.get_messages(b.id)

    assert [m.message_id for m in a_msgs] == ["m-a"]
    assert [m.message_id for m in b_msgs] == ["m-b"]
    assert a_msgs[0].parts[0]["text"] == "alpha"
    assert a_msgs[0].redacted is True


async def test_get_messages_message_id_filter(session):
    repo = ContextRepository(session)
    ctx = await _make_ctx(repo)
    for i in range(3):
        await repo.add_message(
            ctx.id,
            ContextMessage(
                message_id=f"m-{i}",
                role="user",
                parts=[],
                timestamp=_now(),
            ),
        )

    one = await repo.get_messages(ctx.id, message_id="m-1")
    assert [m.message_id for m in one] == ["m-1"]


async def test_get_messages_empty_for_unknown_context(session):
    repo = ContextRepository(session)
    msgs = await repo.get_messages(generate_context_id())
    assert msgs == []


async def test_tasks_isolation(session):
    repo = ContextRepository(session)
    a = await _make_ctx(repo)
    b = await _make_ctx(repo)
    await repo.add_task(
        a.id,
        ContextTaskRef(task_id="t-a", state="submitted", started_at=_now()),
    )
    await repo.add_task(
        b.id,
        ContextTaskRef(task_id="t-b", state="submitted", started_at=_now()),
    )

    assert [t.task_id for t in await repo.get_tasks(a.id)] == ["t-a"]
    assert [t.task_id for t in await repo.get_tasks(b.id)] == ["t-b"]
    assert await repo.get_tasks(generate_context_id()) == []


async def test_artifacts_isolation(session):
    repo = ContextRepository(session)
    a = await _make_ctx(repo)
    b = await _make_ctx(repo)
    await repo.add_artifact(
        a.id,
        ContextArtifactRef(
            artifact_id="ar-a",
            name="x",
            mime_type="application/json",
            url="https://x/ar-a",
        ),
    )

    assert len(await repo.get_artifacts(a.id)) == 1
    assert await repo.get_artifacts(b.id) == []


async def test_add_task_to_unknown_context_raises(session):
    repo = ContextRepository(session)
    with pytest.raises(ContextNotFoundError):
        await repo.add_task(
            generate_context_id(),
            ContextTaskRef(task_id="t-x", state="x", started_at=_now()),
        )


async def test_add_artifact_to_unknown_context_raises(session):
    repo = ContextRepository(session)
    with pytest.raises(ContextNotFoundError):
        await repo.add_artifact(
            generate_context_id(),
            ContextArtifactRef(
                artifact_id="ar-x",
                name="x",
                mime_type="x",
                url="https://x",
            ),
        )


async def test_update_status_changes_status(session):
    repo = ContextRepository(session)
    ctx = await _make_ctx(repo)
    await repo.update_status(ctx.id, ContextStatus.COMPLETED)
    reloaded = await repo.get_context(ctx.id)
    assert reloaded.status == ContextStatus.COMPLETED
    assert reloaded.updated_at >= ctx.updated_at


async def test_update_status_unknown_context_raises(session):
    repo = ContextRepository(session)
    with pytest.raises(ContextNotFoundError):
        await repo.update_status(generate_context_id(), ContextStatus.FAILED)


async def test_delete_context_cascades_children(session):
    repo = ContextRepository(session)
    ctx = await _make_ctx(repo)
    await repo.add_message(
        ctx.id,
        ContextMessage(
            message_id="m-1",
            role="user",
            parts=[],
            timestamp=_now(),
        ),
    )
    await repo.add_task(
        ctx.id,
        ContextTaskRef(task_id="t-1", state="x", started_at=_now()),
    )

    await repo.delete_context(ctx.id)

    assert await repo.get_context(ctx.id) is None
    assert await repo.get_messages(ctx.id) == []
    assert await repo.get_tasks(ctx.id) == []


async def test_delete_unknown_context_raises(session):
    repo = ContextRepository(session)
    with pytest.raises(ContextNotFoundError):
        await repo.delete_context(generate_context_id())


async def test_list_by_agent_returns_only_matching(session):
    repo = ContextRepository(session)
    await _make_ctx(repo, agent_id="homepage-coding-review")
    await _make_ctx(repo, agent_id="homepage-coding-review")
    await _make_ctx(repo, agent_id="other-agent")

    rows = await repo.list_by_agent("homepage-coding-review")
    assert len(rows) == 2
    assert all(r.agent_id == "homepage-coding-review" for r in rows)


async def test_list_by_agent_status_filter(session):
    repo = ContextRepository(session)
    a = await _make_ctx(repo, agent_id="a")
    await _make_ctx(repo, agent_id="a")
    await repo.update_status(a.id, ContextStatus.COMPLETED)

    completed = await repo.list_by_agent("a", status=ContextStatus.COMPLETED)
    active = await repo.list_by_agent("a", status=ContextStatus.ACTIVE)
    assert len(completed) == 1
    assert len(active) == 1


async def test_cross_context_isolation_concurrent(session):
    """Two contexts, no data leak even under interleaved writes."""
    repo = ContextRepository(session)
    a = await _make_ctx(repo)
    b = await _make_ctx(repo)

    for i in range(5):
        await repo.add_message(
            a.id,
            ContextMessage(
                message_id=f"a-{i}",
                role="user",
                parts=[{"k": "alpha"}],
                timestamp=_now(),
            ),
        )
        await repo.add_message(
            b.id,
            ContextMessage(
                message_id=f"b-{i}",
                role="user",
                parts=[{"k": "beta"}],
                timestamp=_now(),
            ),
        )

    a_msgs = await repo.get_messages(a.id)
    b_msgs = await repo.get_messages(b.id)
    assert {m.message_id for m in a_msgs} == {f"a-{i}" for i in range(5)}
    assert {m.message_id for m in b_msgs} == {f"b-{i}" for i in range(5)}
    assert all(m.parts[0]["k"] == "alpha" for m in a_msgs)
    assert all(m.parts[0]["k"] == "beta" for m in b_msgs)