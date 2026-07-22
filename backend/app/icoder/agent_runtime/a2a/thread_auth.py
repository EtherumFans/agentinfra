"""Thread auth registration — A1B-AE-R.1.a DB-backed rewrite.

Corti public §9 rule 6:

    MCP tools are registered when a new thread is created (the
    first message). Auth DataParts MUST be on that first message.
    Later messages on the same thread do NOT re-register tools;
    auth DataParts are ignored for MCP registration on subsequent
    messages.

A1B-AE.5 shipped an in-memory tracker; A1B-AE-R.1.a swaps it for a
DB-derived source of truth: a thread is "first message" iff the
``context_messages`` row count for that ``context_id`` is 0. This
survives process restart, works across replicas, and needs no
auxiliary state column.

The registry is now async + session-aware. The previous module-level
``thread_auth_registry`` singleton is removed; callers construct a
registry per unit-of-work with an ``AsyncSession`` they already hold.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..context.db_models import ContextMessageRow
from .mcp_auth_extractor import ExtractedMcpAuth


class ThreadAuthRegistry:
    """DB-backed per-thread registration state.

    Construct with the caller's existing ``AsyncSession``; the registry
    does not open its own session. All methods are coroutines.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_first_message(self, context_id: str) -> bool:
        """True iff no message row exists for ``context_id`` yet."""
        stmt = (
            select(ContextMessageRow.message_id)
            .where(ContextMessageRow.context_id == context_id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.first() is None

    async def register_first_message(
        self,
        context_id: str,
        auth_entries: list[ExtractedMcpAuth],
    ) -> None:
        """Record MCP tool registrations for ``context_id``.

        Per Corti §9 rule 6 this is a per-context-idempotent operation:
        if a row already exists for ``context_id``, this is a no-op.
        The actual persistence is the ``ContextMessageRow`` written by
        the caller; this method exists only so legacy callers compile.
        """
        if not await self.is_first_message(context_id):
            return
        _ = auth_entries

    async def get_state(self, context_id: str) -> dict[str, Any]:
        """Snapshot of the thread's registration state (DB-derived)."""
        stmt = select(ContextMessageRow.message_id).where(
            ContextMessageRow.context_id == context_id
        )
        rows = (await self._session.execute(stmt)).all()
        message_count = len(rows)
        return {
            "has_registered": message_count > 0,
            "registered_mcp_names": [],
            "message_count": message_count,
        }


__all__ = ["ThreadAuthRegistry"]
