from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import database
from app.models.stt_artifact import STTStreamLease
from app.services.stream_session_lease import (
    MAXIMUM_LEASE_SECONDS,
    MINIMUM_LEASE_SECONDS,
    StreamLeaseScope,
    acquire_stream_lease,
    configured_lease_seconds,
    release_stream_lease,
    renew_stream_lease,
)


@pytest_asyncio.fixture
async def isolated_lease_store(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'streams-leases.db'}",
        connect_args={"timeout": 30},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(STTStreamLease.__table__.create)
    monkeypatch.setattr(database, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


def _scope(*, organization: str = "org-a", owner: str = "owner-a"):
    return StreamLeaseScope(
        organization_id=organization,
        owner_id=owner,
        interaction_id="11111111-1111-4111-8111-111111111111",
    )


@pytest.mark.asyncio
async def test_active_lease_rejects_duplicate_but_not_other_tenant_or_owner(
    isolated_lease_store,
):
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    assert await acquire_stream_lease(_scope(), "session-a", now=now)
    assert not await acquire_stream_lease(_scope(), "session-b", now=now)
    assert await acquire_stream_lease(
        _scope(organization="org-b"), "session-c", now=now
    )
    assert await acquire_stream_lease(_scope(owner="owner-b"), "session-d", now=now)


@pytest.mark.asyncio
async def test_expired_lease_is_reclaimed_and_stale_owner_is_fenced(
    isolated_lease_store,
):
    started = datetime(2026, 8, 24, tzinfo=timezone.utc)
    recovered = started + timedelta(seconds=7)
    assert await acquire_stream_lease(
        _scope(), "stale-session", lease_seconds=6, now=started
    )
    assert await acquire_stream_lease(
        _scope(), "recovered-session", lease_seconds=6, now=recovered
    )
    assert not await renew_stream_lease(
        _scope(), "stale-session", lease_seconds=6, now=recovered
    )
    assert not await release_stream_lease(_scope(), "stale-session")
    assert await renew_stream_lease(
        _scope(), "recovered-session", lease_seconds=6, now=recovered
    )
    assert await release_stream_lease(_scope(), "recovered-session")


@pytest.mark.asyncio
async def test_concurrent_acquire_has_exactly_one_winner(isolated_lease_store):
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    outcomes = await asyncio.gather(*(
        acquire_stream_lease(_scope(), f"session-{index}", now=now)
        for index in range(8)
    ))
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 7


def test_configured_lease_duration_is_strictly_bounded(monkeypatch):
    monkeypatch.setenv("ICODER_STREAM_LEASE_SECONDS", "1")
    assert configured_lease_seconds() == MINIMUM_LEASE_SECONDS
    monkeypatch.setenv("ICODER_STREAM_LEASE_SECONDS", "9999")
    assert configured_lease_seconds() == MAXIMUM_LEASE_SECONDS
    monkeypatch.setenv("ICODER_STREAM_LEASE_SECONDS", "invalid")
    assert MINIMUM_LEASE_SECONDS <= configured_lease_seconds() <= MAXIMUM_LEASE_SECONDS
