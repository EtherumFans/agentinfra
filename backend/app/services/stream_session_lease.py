"""Database-backed ownership fence for stateful Streams WebSockets.

The in-process connection map remains a fast local guard. This lease is the
authoritative cross-worker guard: only the exact current ``session_id`` may
renew or release a scoped interaction, and an expired row is reclaimed with a
single compare-and-set update.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, update
from sqlalchemy.exc import IntegrityError

from app import database
from app.config import settings
from app.models.stt_artifact import STTStreamLease


DEFAULT_LEASE_SECONDS = 30
MINIMUM_LEASE_SECONDS = 6
MAXIMUM_LEASE_SECONDS = 300


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def configured_lease_seconds() -> int:
    try:
        requested = int(
            os.environ.get(
                "ICODER_STREAM_LEASE_SECONDS",
                str(settings.ICODER_STREAM_LEASE_SECONDS),
            )
        )
    except ValueError:
        requested = DEFAULT_LEASE_SECONDS
    return max(MINIMUM_LEASE_SECONDS, min(requested, MAXIMUM_LEASE_SECONDS))


@dataclass(frozen=True, slots=True)
class StreamLeaseScope:
    organization_id: str
    owner_id: str
    interaction_id: str


def _scope_filter(scope: StreamLeaseScope):
    return and_(
        STTStreamLease.organization_id == scope.organization_id,
        STTStreamLease.owner_id == scope.owner_id,
        STTStreamLease.interaction_id == scope.interaction_id,
    )


async def acquire_stream_lease(
    scope: StreamLeaseScope,
    session_id: str,
    *,
    lease_seconds: int | None = None,
    now: datetime | None = None,
) -> bool:
    """Acquire a new row or atomically reclaim one whose lease expired."""

    current = now or utc_now()
    seconds = lease_seconds or configured_lease_seconds()
    expires = current + timedelta(seconds=seconds)
    async with database.AsyncSessionLocal() as db:
        from app.services.database_tenancy import bind_tenant_to_transaction
        await bind_tenant_to_transaction(db, scope.organization_id)
        db.add(STTStreamLease(
            organization_id=scope.organization_id,
            owner_id=scope.owner_id,
            interaction_id=scope.interaction_id,
            session_id=session_id,
            acquired_at=current,
            lease_expires_at=expires,
            updated_at=current,
        ))
        try:
            await db.commit()
            return True
        except IntegrityError:
            await db.rollback()

        reclaimed = await db.execute(
            update(STTStreamLease)
            .where(
                _scope_filter(scope),
                STTStreamLease.lease_expires_at <= current,
            )
            .values(
                session_id=session_id,
                acquired_at=current,
                lease_expires_at=expires,
                updated_at=current,
            )
        )
        await db.commit()
        return bool(reclaimed.rowcount)


async def renew_stream_lease(
    scope: StreamLeaseScope,
    session_id: str,
    *,
    lease_seconds: int | None = None,
    now: datetime | None = None,
) -> bool:
    """Renew only if the caller still owns the exact fenced row."""

    current = now or utc_now()
    seconds = lease_seconds or configured_lease_seconds()
    async with database.AsyncSessionLocal() as db:
        from app.services.database_tenancy import bind_tenant_to_transaction
        await bind_tenant_to_transaction(db, scope.organization_id)
        renewed = await db.execute(
            update(STTStreamLease)
            .where(
                _scope_filter(scope),
                STTStreamLease.session_id == session_id,
            )
            .values(
                lease_expires_at=current + timedelta(seconds=seconds),
                updated_at=current,
            )
        )
        await db.commit()
        return bool(renewed.rowcount)


async def release_stream_lease(scope: StreamLeaseScope, session_id: str) -> bool:
    """Delete only the caller's row; a stale worker cannot release a successor."""

    async with database.AsyncSessionLocal() as db:
        from app.services.database_tenancy import bind_tenant_to_transaction
        await bind_tenant_to_transaction(db, scope.organization_id)
        released = await db.execute(
            delete(STTStreamLease).where(
                _scope_filter(scope),
                STTStreamLease.session_id == session_id,
            )
        )
        await db.commit()
        return bool(released.rowcount)


__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "MAXIMUM_LEASE_SECONDS",
    "MINIMUM_LEASE_SECONDS",
    "StreamLeaseScope",
    "acquire_stream_lease",
    "configured_lease_seconds",
    "release_stream_lease",
    "renew_stream_lease",
]
