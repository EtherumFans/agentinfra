"""Phase 7 Gate 4 — Run lifecycle + cancel/timeout semantics.

Per Phase 7 §9.1-§9.4, this module defines:

1. ``RunStatus`` — the lifecycle states a Run can occupy:
     PENDING, RUNNING, COMPLETED, FAILED,
     CANCELLATION_REQUESTED, CANCELLED, CANCEL_NOT_SUPPORTED,
     CLIENT_ABORTED, COMPLETED_AFTER_CLIENT_ABORT

2. ``record_run_start`` / ``record_run_completion`` / ``record_run_failure``
   — write status transitions to ``run_history`` so ``GET /runs/{id}``
   can poll the real status after an SDK 90s timeout (§9.3).

3. ``request_cancel`` — the handler for ``POST /api/v1/runs/{run_id}/cancel``
   (§9.2). Records the cancel request and returns the appropriate
   response state. **We do NOT lie about cancellation**: if the run is
   already COMPLETED we return COMPLETED; if the Provider doesn't
   support mid-stream cancel (DeepSeek doesn't), we return
   CANCEL_NOT_SUPPORTED and the run continues.

4. ``mark_client_aborted`` — called when the SDK disconnects mid-run
   (FastAPI ``request.is_disconnected()``). The Run continues server-side
   (we don't kill the LLM call); if it later completes, we promote to
   COMPLETED_AFTER_CLIENT_ABORT. Cost is real (Provider was called).

5. ``get_run_status`` — reads a row for status polling.

§9.4 Cost semantics:
- cancelled before Provider call → cost stays 0 (no Provider charge)
- cancelled after Provider call → cost is whatever was actually recorded
- client-aborted → cost is real (Provider was called)
We never zero a recorded cost.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run_history import RunHistoryModel

logger = logging.getLogger(__name__)


# ── §9.1 lifecycle states ──────────────────────────────────────────


class RunStatus:
    """Run lifecycle states (Phase 7 §9.1).

    Stored as plain strings (not Python enums) so they round-trip
    through SQLite/JSON without serialization glue. Keep the string
    values stable — partners may switch on them client-side.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    # Cancel-related (§9.1)
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    CANCELLED = "CANCELLED"
    CANCEL_NOT_SUPPORTED = "CANCEL_NOT_SUPPORTED"
    CLIENT_ABORTED = "CLIENT_ABORTED"
    COMPLETED_AFTER_CLIENT_ABORT = "COMPLETED_AFTER_CLIENT_ABORT"

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        """A terminal state won't transition further — pollers can stop."""
        return status in (
            cls.COMPLETED,
            cls.FAILED,
            cls.CANCELLED,
            cls.CANCEL_NOT_SUPPORTED,
            cls.CLIENT_ABORTED,
            cls.COMPLETED_AFTER_CLIENT_ABORT,
        )

    @classmethod
    def is_cancel_kind(cls, status: str) -> bool:
        """True if the run ended due to cancel/abort (not natural complete)."""
        return status in (
            cls.CANCELLATION_REQUESTED,
            cls.CANCELLED,
            cls.CANCEL_NOT_SUPPORTED,
            cls.CLIENT_ABORTED,
        )


# ── Response shapes ────────────────────────────────────────────────


class CancelOutcome:
    """The decision a cancel request reached.

    Maps to §9.1 statuses returned by POST /api/v1/runs/{run_id}/cancel.
    The endpoint uses this to choose HTTP code + body shape.

    - ``outcome="ALREADY_COMPLETE"`` → 200 with the original status
    - ``outcome="RECORDED_ONLY"`` → 202 (we recorded the request but
      the run continues because the Provider doesn't support cancel)
    - ``outcome="CANCELLED"`` → 200 (run was PENDING/RUNNING and we
      could stop it before Provider call)
    - ``outcome="NOT_FOUND"`` → 404
    - ``outcome="FORBIDDEN"`` → 403 (org / user mismatch)
    """
    ALREADY_COMPLETE = "ALREADY_COMPLETE"
    RECORDED_ONLY = "RECORDED_ONLY"
    CANCELLED = "CANCELLED"
    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"


# ── Write helpers ──────────────────────────────────────────────────


async def record_run_start(
    db: AsyncSession,
    *,
    run_id: str,
    agent_id: str,
    user_id: str = "",
    organization_id: Optional[str] = None,
    input_text: str = "",
    runtime_mode: str = "",
    trace_id: str = "",
    # ── Phase 7 Gate 5 §10.1: partner attribution ──────────────────
    api_client_id: Optional[str] = None,
    embedded_app_id: Optional[str] = None,
    session_id: Optional[str] = None,
    context_id: Optional[str] = None,
    request_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> RunHistoryModel:
    """Insert a PENDING row at the start of a Run.

    The agent_run endpoint will update this row to RUNNING once the
    envelope is built, then to COMPLETED/FAILED/CANCELLED at the end.
    """
    row = RunHistoryModel(
        run_id=run_id,
        agent_id=agent_id,
        user_id=user_id or None,
        organization_id=organization_id,
        input_text=(input_text or "")[:4096],
        runtime_mode=runtime_mode or "",
        trace_id=trace_id or "",
        status=RunStatus.PENDING,
        latency_ms=0,
        cost_usd=0.0,
        output_summary="",
        error=False,
        # Partner attribution (§10.1)
        api_client_id=api_client_id,
        embedded_app_id=embedded_app_id,
        session_id=session_id,
        context_id=context_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        # Python-side timestamp with microsecond precision so two runs
        # landing in the same second still order deterministically by
        # created_at DESC (SQLite's CURRENT_TIMESTAMP is 1-second res).
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return row


async def set_status(
    db: AsyncSession,
    *,
    run_id: str,
    status: str,
    extra_fields: Optional[dict] = None,
) -> Optional[RunHistoryModel]:
    """Update the status of a Run row.

    Returns the refreshed row, or None if no row matched ``run_id``.
    """
    values: dict = {"status": status}
    if extra_fields:
        values.update(extra_fields)
    stmt = (
        update(RunHistoryModel)
        .where(RunHistoryModel.run_id == run_id)
        .values(**values)
        .returning(RunHistoryModel)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    await db.flush()
    return row


async def get_run_status(
    db: AsyncSession,
    *,
    run_id: str,
) -> Optional[RunHistoryModel]:
    """Read a single run_history row by run_id."""
    stmt = select(RunHistoryModel).where(RunHistoryModel.run_id == run_id)
    result = await db.execute(stmt)
    return result.scalars().one_or_none()


# ── §9.2 cancel request handler ────────────────────────────────────


async def request_cancel(
    db: AsyncSession,
    *,
    run_id: str,
    cancelled_by_user_id: str = "",
    expected_organization_id: Optional[str] = None,
    cancel_reason: str = "",
) -> tuple[str, RunStatus, Optional[RunHistoryModel]]:
    """Apply a cancel request per Phase 7 §9.2.

    Returns ``(outcome, current_status, row)``. The caller (the HTTP
    handler) maps the outcome to HTTP code + body.

    Validation (§9.2):
    - 404 if the run doesn't exist
    - 403 if the run belongs to a different org
    - 200 + ALREADY_COMPLETE if the run is already terminal
    - 200 + CANCELLED if the run was PENDING and we can stop it
    - 202 + RECORDED_ONLY if Provider can't be cancelled (we record
      the request but the run continues — never lie about cancellation)

    Cost (§9.4): we never zero a recorded cost. If the Provider was
    already called, the existing cost stays.
    """
    row = await get_run_status(db, run_id=run_id)
    if row is None:
        return (CancelOutcome.NOT_FOUND, "", None)

    # Org scope check — Phase 7 §9.2 "校验 Organization".
    if (
        expected_organization_id is not None
        and row.organization_id is not None
        and row.organization_id != expected_organization_id
    ):
        return (CancelOutcome.FORBIDDEN, row.status, row)

    now = datetime.now(timezone.utc)
    update_fields = {
        "cancel_reason": cancel_reason or "client_requested",
        "cancelled_at": now,
        "cancelled_by_user_id": cancelled_by_user_id or None,
    }

    if RunStatus.is_terminal(row.status) and row.status != RunStatus.RUNNING:
        # Already done — record the (now-inert) cancel request for audit
        # but tell the caller nothing changed.
        update_fields["status"] = row.status  # unchanged
        await set_status(db, run_id=run_id, status=row.status, extra_fields=update_fields)
        return (CancelOutcome.ALREADY_COMPLETE, row.status, row)

    if row.status == RunStatus.PENDING:
        # Pre-Provider cancel: the run hadn't started yet — safe to drop.
        update_fields["status"] = RunStatus.CANCELLED
        await set_status(
            db, run_id=run_id, status=RunStatus.CANCELLED, extra_fields=update_fields,
        )
        return (CancelOutcome.CANCELLED, RunStatus.CANCELLED, row)

    # RUNNING — the Provider is mid-call. DeepSeek doesn't support
    # mid-stream cancel; we record the request and let the run finish.
    # The agent_run loop will observe the recorded cancel and may
    # short-circuit post-Provider stages (repair loop, etc.).
    update_fields["status"] = RunStatus.CANCEL_NOT_SUPPORTED
    await set_status(
        db, run_id=run_id,
        status=RunStatus.CANCEL_NOT_SUPPORTED,
        extra_fields=update_fields,
    )
    logger.info(
        "run_lifecycle: cancel requested for run_id=%s but Provider mid-call "
        "(deepseek does not support cancel) — recorded only",
        run_id,
    )
    return (CancelOutcome.RECORDED_ONLY, RunStatus.CANCEL_NOT_SUPPORTED, row)


# ── §9.1 client-abort detection ────────────────────────────────────


async def mark_client_aborted(
    db: AsyncSession,
    *,
    run_id: str,
) -> None:
    """Mark that the SDK disconnected mid-run (§9.1 CLIENT_ABORTED).

    Called when ``request.is_disconnected()`` becomes True. The Run
    continues server-side; if it later completes, the agent_run loop
    promotes the status to COMPLETED_AFTER_CLIENT_ABORT.
    """
    row = await get_run_status(db, run_id=run_id)
    if row is None:
        return
    if RunStatus.is_terminal(row.status):
        # Already done — leave the more-specific terminal state intact.
        return
    await set_status(db, run_id=run_id, status=RunStatus.CLIENT_ABORTED)


async def maybe_promote_client_aborted_to_completed(
    db: AsyncSession,
    *,
    run_id: str,
) -> None:
    """If a Run was CLIENT_ABORTED but the underlying call finished
    successfully, promote to COMPLETED_AFTER_CLIENT_ABORT so the
    partner polling for status sees the truth (§9.1)."""
    row = await get_run_status(db, run_id=run_id)
    if row is None or row.status != RunStatus.CLIENT_ABORTED:
        return
    await set_status(
        db, run_id=run_id, status=RunStatus.COMPLETED_AFTER_CLIENT_ABORT,
    )
