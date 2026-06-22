"""Original-input audit repository (SPEC §8).

Stores the raw PHI separately from the Context lifecycle so that:
- Context can be physically deleted after 7d grace (SPEC §5.5)
- Audit row persists for the compliance retention window (default 90d)
- Every audit row is keyed by contextId for forensic lookup
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .context_id import is_valid_context_id
from .context_isolation import ContextIsolationError
from .db_models import OriginalInputAuditRow


def hash_original_input(raw: str) -> str:
    """SHA-256 of the raw input — for ``Context.redacted_input_hash`` cross-check."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ContextAudit:
    """CRUD + retention-prune for original_input_audit table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    async def record_original_input(
        self,
        context_id: str,
        original_input: str,
        *,
        retention_days: int = 90,
        audit_id: str | None = None,
        now: datetime | None = None,
    ) -> OriginalInputAuditRow:
        """Write a new audit row keyed by contextId.

        Raises ContextIsolationError if context_id is not a canonical UUID v4.
        Returns the persisted row (with the assigned audit_id).
        """
        if not is_valid_context_id(context_id):
            raise ContextIsolationError(
                f"context_id must be canonical UUID v4: {context_id!r}",
                context_id=context_id,
            )
        now = now or datetime.now(timezone.utc)
        row = OriginalInputAuditRow(
            id=audit_id or hash_original_input(f"{context_id}:{now.isoformat()}"),
            context_id=context_id,
            original_input=original_input,
            created_at=now,
            retention_until=now + timedelta(days=retention_days),
        )
        self._session.add(row)
        await self._session.commit()
        return row

    async def get_by_context(self, context_id: str) -> list[OriginalInputAuditRow]:
        """All audit rows for one contextId. Empty if none."""
        if not is_valid_context_id(context_id):
            raise ContextIsolationError(
                f"context_id must be canonical UUID v4: {context_id!r}",
                context_id=context_id,
            )
        stmt = select(OriginalInputAuditRow).where(
            OriginalInputAuditRow.context_id == context_id
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def prune_expired(self, *, now: datetime | None = None) -> list[str]:
        """Delete audit rows past their retention_until. Returns deleted IDs."""
        now = self._as_utc(now or datetime.now(timezone.utc))
        stmt = select(OriginalInputAuditRow).where(
            OriginalInputAuditRow.retention_until <= now
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        deleted: list[str] = []
        for row in rows:
            await self._session.delete(row)
            deleted.append(row.id)
        if deleted:
            await self._session.commit()
        return deleted

    async def verify_against_context(
        self,
        context_id: str,
        original_input: str,
    ) -> bool:
        """Forensic check: does the supplied input hash-match a stored audit row?

        Returns True if a row for context_id exists and the SHA-256 of
        original_input matches. Used during incident response — never by
        the runtime hot path.
        """
        rows = await self.get_by_context(context_id)
        target = hash_original_input(original_input)
        return any(
            hash_original_input(r.original_input) == target for r in rows
        )