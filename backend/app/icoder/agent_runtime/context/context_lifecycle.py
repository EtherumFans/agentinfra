"""ContextLifecycle — state machine wrapping ContextRepository (SPEC §5).

Allowed transitions:
    (none)   ──create──▶  ACTIVE
    ACTIVE   ──complete─▶ COMPLETED   (terminal)
    ACTIVE   ──fail─────▶ FAILED      (terminal)
    ACTIVE   ──expire───▶ EXPIRED     (TTL elapsed)
    COMPLETED ──expire──▶ EXPIRED     (post-completion grace elapsed)
    FAILED   ──expire───▶ EXPIRED     (post-fail grace elapsed)
    EXPIRED  ──destroy─▶ (gone)

COMPLETED / FAILED / EXPIRED accept no further mutations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from .context import Context, ContextMessage
from .context_id import generate_context_id
from .context_isolation import ContextIsolationError
from .context_repository import ContextRepository
from .context_status import ContextStatus

EventSink = Callable[[str, dict], Awaitable[None]]


class ContextLifecycleError(Exception):
    """Raised when a lifecycle transition is invalid for the current state."""

    def __init__(self, message: str, *, context_id: str, current_status: ContextStatus) -> None:
        super().__init__(message)
        self.context_id = context_id
        self.current_status = current_status


class ContextLifecycle:
    """State machine wrapping ContextRepository."""

    def __init__(
        self,
        repo: ContextRepository,
        *,
        ttl_seconds: int = 24 * 3600,
        completed_ttl_seconds: int = 3600,
        grace_seconds: int = 7 * 24 * 3600,
        now_fn: Callable[[], datetime] | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self._repo = repo
        self._ttl = timedelta(seconds=ttl_seconds)
        self._completed_ttl = timedelta(seconds=completed_ttl_seconds)
        self._grace = timedelta(seconds=grace_seconds)
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._event_sink = event_sink

    async def _emit(self, stage: str, payload: dict) -> None:
        if self._event_sink is None:
            return
        await self._event_sink(stage, payload)

    def _require_status(self, ctx: Context, allowed: set[ContextStatus]) -> None:
        if ctx.status not in allowed:
            raise ContextLifecycleError(
                f"cannot transition from {ctx.status.value}; allowed: "
                f"{sorted(s.value for s in allowed)}",
                context_id=ctx.id,
                current_status=ctx.status,
            )

    async def assert_can_mutate(self, context_id: str) -> Context:
        """Raise ContextLifecycleError unless the context is ACTIVE.

        Callers adding messages / tasks must invoke this first to honour the
        append-only invariant on terminal states.
        """
        ctx = await self._repo.get_context(context_id)
        if ctx is None:
            raise ContextIsolationError(
                f"context {context_id!r} not found",
                context_id=context_id,
            )
        self._require_status(ctx, {ContextStatus.ACTIVE})
        return ctx

    async def create(
        self,
        *,
        agent_id: str,
        initial_message: ContextMessage | None = None,
        organization_id: str = "org_default1",
    ) -> Context:
        """Create active context with server-generated contextId.

        ``organization_id`` is the tenant scope (A1B-AE-R.1.b). Defaults
        to ``org_default1`` to match the test-bypass mock org and the
        dev DB default. Production callers should always pass the JWT's
        ``current_org.id`` explicitly.
        """
        now = self._now()
        ctx = Context(
            id=generate_context_id(),
            created_at=now,
            updated_at=now,
            expires_at=now + self._ttl,
            agent_id=agent_id,
            organization_id=organization_id or "org_default1",
            status=ContextStatus.ACTIVE,
        )
        await self._repo.create_context(ctx)
        await self._emit(
            "context_created",
            {
                "contextId": ctx.id,
                "agent_id": agent_id,
                "ttl_seconds": int(self._ttl.total_seconds()),
                "phi_redacted_entities": list(ctx.metadata.phi_redacted_entities),
            },
        )
        if initial_message is not None:
            await self._repo.add_message(ctx.id, initial_message)
            await self._emit(
                "context_message_added",
                {
                    "contextId": ctx.id,
                    "message_id": initial_message.message_id,
                    "role": initial_message.role,
                    "redacted": initial_message.redacted,
                },
            )
        return ctx

    async def complete(self, context_id: str) -> Context:
        ctx = await self.assert_can_mutate(context_id)
        now = self._now()
        new_expires = now + self._completed_ttl
        await self._repo.update_status(
            context_id,
            ContextStatus.COMPLETED,
            updated_at=now,
            expires_at=new_expires,
        )

        msgs = await self._repo.get_messages(context_id)
        tasks = await self._repo.get_tasks(context_id)
        await self._emit(
            "context_completed",
            {
                "contextId": context_id,
                "total_messages": len(msgs),
                "total_tasks": len(tasks),
            },
        )
        return await self._repo.get_context(context_id)  # type: ignore[return-value]

    async def fail(
        self,
        context_id: str,
        *,
        error_code: str = "",
        error_stage: str = "",
    ) -> Context:
        ctx = await self.assert_can_mutate(context_id)
        now = self._now()
        new_expires = now + self._completed_ttl
        await self._repo.update_status(
            context_id,
            ContextStatus.FAILED,
            updated_at=now,
            expires_at=new_expires,
        )

        await self._emit(
            "context_failed",
            {
                "contextId": context_id,
                "error_code": error_code,
                "error_stage": error_stage,
            },
        )
        return await self._repo.get_context(context_id)  # type: ignore[return-value]

    async def expire_if_overdue(self, context_id: str) -> Context | None:
        """Mark expired if expires_at < now and not already terminal."""
        ctx = await self._repo.get_context(context_id)
        if ctx is None:
            return None
        if ctx.status == ContextStatus.EXPIRED:
            return ctx
        if ctx.status in {ContextStatus.COMPLETED, ContextStatus.FAILED}:
            if ctx.expires_at <= self._now():
                now = self._now()
                await self._repo.update_status(
                    context_id, ContextStatus.EXPIRED, updated_at=now
                )
                age = (now - ctx.created_at).total_seconds()
                await self._emit(
                    "context_expired",
                    {"contextId": context_id, "age_seconds": int(age)},
                )
                return await self._repo.get_context(context_id)
            return ctx
        if ctx.expires_at <= self._now():
            now = self._now()
            await self._repo.update_status(
                context_id, ContextStatus.EXPIRED, updated_at=now
            )
            age = (now - ctx.created_at).total_seconds()
            await self._emit(
                "context_expired",
                {"contextId": context_id, "age_seconds": int(age)},
            )
            return await self._repo.get_context(context_id)
        return ctx

    async def sweep_expired(self) -> list[str]:
        """Batch transition overdue contexts to EXPIRED. Returns expired IDs."""
        now = self._now()
        active = await self._repo.list_all(status=ContextStatus.ACTIVE)
        completed = await self._repo.list_all(status=ContextStatus.COMPLETED)
        failed = await self._repo.list_all(status=ContextStatus.FAILED)
        overdue_ids: list[str] = []
        for ctx in (*active, *completed, *failed):
            if ctx.expires_at <= now:
                await self._repo.update_status(
                    ctx.id, ContextStatus.EXPIRED, updated_at=now
                )
                age = (now - ctx.created_at).total_seconds()
                await self._emit(
                    "context_expired",
                    {"contextId": ctx.id, "age_seconds": int(age)},
                )
                overdue_ids.append(ctx.id)
        return overdue_ids

    async def destroy_expired(self, *, older_than_seconds: int | None = None) -> list[str]:
        """Physically delete contexts that have been EXPIRED for >= grace period.

        Children are removed via FK CASCADE; original_input_audit is left
        intact (independent retention).
        """
        grace = (
            timedelta(seconds=older_than_seconds)
            if older_than_seconds is not None
            else self._grace
        )
        now = self._now()
        threshold = now - grace
        expired = await self._repo.list_all(status=ContextStatus.EXPIRED)
        destroyed: list[str] = []
        for ctx in expired:
            if ctx.updated_at <= threshold:
                await self._repo.delete_context(ctx.id)
                await self._emit(
                    "context_destroyed",
                    {"contextId": ctx.id, "reason": "grace_elapsed"},
                )
                destroyed.append(ctx.id)
        return destroyed

    async def destroy_now(
        self,
        context_id: str,
        *,
        organization_id: str | None = None,
        reason: str = "user_requested",
    ) -> None:
        """A1B-AE-R.1.b — physical scrub, no grace period.

        Differs from ``destroy_expired`` in two ways:

        * No EXPIRED precondition — any context state can be scrubbed
          on explicit user request (DELETE endpoint).
        * ``original_input_audit`` rows are also scrubbed. Retention
          policies that require the audit trail to survive user-initiated
          delete must be enforced at a higher layer (e.g. deny DELETE
          while a compliance hold is active).

        If ``organization_id`` is supplied and the context does not
        belong to that org, ``ContextNotFoundError`` is raised — the
        caller MUST translate this to a 404 (never leak tenant
        existence).
        """
        if organization_id is not None:
            row = await self._repo.get_for_org(context_id, organization_id)
            if row is None:
                raise ContextIsolationError(
                    f"context {context_id!r} not found for "
                    f"organization {organization_id!r}",
                    context_id=context_id,
                )
        await self._repo.hard_delete_context(context_id)
        await self._emit(
            "context_destroyed",
            {
                "contextId": context_id,
                "reason": reason,
                "initiated_by": "user",
            },
        )