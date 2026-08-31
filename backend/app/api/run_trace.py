"""RunTrace API — Phase 3-D1 Task 4 (in-memory) + Phase 3-D2 Task 1 (DB).

Exposes the RunTraceStore via a read-only endpoint so the frontend
RunTracePage can render the 9-step timeline.

  GET /api/runtime/runs/{run_id}/trace
    → 200 {"run_id": "...", "events": [RunTraceEvent.to_dict(), ...],
            "trace_attestation": "<tenant/run/events-bound proof>"}

  GET /api/runtime/runs/{run_id}/trace?format=timeline
    → 200 {"run_id": "...", "timeline": [{"step": ..., "status": ...,
            "duration_ms": ..., "safe_metadata": {...}, "ts": ...}, ...]}

Phase 3-D2 Task 1 changes:
  - Reads from the configured store (memory or db per settings.RUNTRACE_STORE).
  - When DB mode, the query is org-scoped: ``request.state.tenant_name``
    (set by TenantHeaderMiddleware) is passed to ``get_run_scoped``.
    A run that exists but belongs to a different org returns 404
    (don't leak cross-org run existence).
  - The endpoint never redacts — the store is ALREADY display-safe
    (DbRunTraceStore.append runs a defensive scan before insert).

Phase A1A Gate 3.2 changes:
  - ``list_run_history`` now applies ``apply_tenant_visibility_filter``
    so ``LEGACY_TENANT_UNKNOWN`` / ``LEGACY_TENANT_AMBIGUOUS`` /
    ``QUARANTINED`` / ``MODERN_SYSTEM`` rows are excluded from the
    list response. They remain in the DB for forensics but are
    invisible to normal tenant reads (charter §3.2).
  - ``_get_run_trace_impl`` (Gate 3.5) will add a point-read visibility
    guard + RunHistory.organization_id cross-check.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
from app.middleware.tenant_extractor import get_request_tenant
from app.services.trace_attestation import (
    TraceAttestationError,
    issue_trace_attestation,
)


router = APIRouter(prefix="/api/runtime", tags=["run-trace"])


def _build_run_summary(console_row: Any, events: list[Any]) -> dict[str, Any]:
    """Build a display-safe, auditable summary for the Console trace view.

    Only bounded run-envelope fields are projected from ``run_history``.  The
    review state is intentionally an event-derived *signal*, not an
    authoritative clinical review decision: older runs did not persist the
    response-level ``manual_review_required`` flag.
    """
    required_sources: list[str] = []
    explicit_not_required_sources: list[str] = []
    required_provider_statuses = {
        "requires_review", "unclear", "incomplete", "non_compliant",
    }
    for event in events:
        metadata = getattr(event, "safe_metadata", None) or {}
        step = str(getattr(event, "step", "event") or "event")
        for key in ("manual_review_required", "review_required"):
            value = metadata.get(key)
            if value is True:
                required_sources.append(f"{step}.{key}")
            elif value is False:
                explicit_not_required_sources.append(f"{step}.{key}")
        provider_status = str(metadata.get("provider_status") or "").lower()
        if provider_status in required_provider_statuses:
            required_sources.append(f"{step}.provider_status:{provider_status}")

    if required_sources:
        review_state = "required"
        review_sources = required_sources
    elif explicit_not_required_sources:
        review_state = "not_required"
        review_sources = explicit_not_required_sources
    else:
        review_state = "not_recorded"
        review_sources = []

    created_at = getattr(console_row, "created_at", None)
    return {
        "agent_id": str(getattr(console_row, "agent_id", "") or ""),
        "trace_id": str(getattr(console_row, "trace_id", "") or ""),
        "run_status": str(getattr(console_row, "status", "") or "UNKNOWN"),
        "runtime_mode": str(getattr(console_row, "runtime_mode", "") or ""),
        "latency_ms": int(getattr(console_row, "latency_ms", 0) or 0),
        # cost_usd is the historical DB column name; configured run pricing
        # and all public contracts use CNY (see app.config).
        "cost": {
            "amount": max(float(getattr(console_row, "cost_usd", 0.0) or 0.0), 0.0),
            "currency": "CNY",
        },
        "error": bool(getattr(console_row, "error", False)),
        "error_reason": str(getattr(console_row, "error_reason", "") or "") or None,
        "trace_capture_status": str(
            getattr(console_row, "trace_capture_status", "") or "NOT_RECORDED"
        ),
        "created_at": created_at.isoformat() if created_at else None,
        "review_signal": {
            "state": review_state,
            "sources": sorted(set(review_sources)),
            "authoritative": False,
        },
    }


# ── Phase A1A Gate 3.6 — system-scope audit helper ────────────────


async def _emit_console_system_audit(
    *,
    action: str,
    run_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Best-effort MODERN_SYSTEM audit row for Console trace denials."""
    try:
        from app.services.system_audit import system_audit
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await system_audit(
                db,
                action=action,
                resource_type="run_history",
                resource_id=run_id,
                details=details,
            )
            await db.commit()
    except Exception as audit_err:  # pragma: no cover — defensive
        import logging as _logging
        _logging.getLogger("app.api.run_trace.console").error(
            "system_audit emit failed: %s (action=%s run_id=%s)",
            audit_err, action, run_id,
        )


async def _get_run_trace_impl(
    run_id: str,
    format: str,
    request: Request,
) -> dict[str, Any]:
    store = get_default_store()
    org_id: Optional[str] = get_request_tenant(request)

    # ── Phase A1A Gate 3.5 (F05 carry-over) — defence-in-depth ──
    # Before reading any trace events, cross-check RunHistory's
    # organization_id and tenancy_classification. Two scenarios:
    #
    #   1. Run belongs to a different org than the requesting tenant.
    #      Even though trace events are filtered by get_run_scoped
    #      with org_id, the run_history row carries the authoritative
    #      org. Stale trace events with NULL org_id on the event row
    #      could otherwise sneak through.
    #   2. Run is QUARANTINED / UNKNOWN / AMBIGUOUS / MODERN_SYSTEM.
    #      Per charter §3.2 these are invisible to tenant reads;
    #      Console trace reads are tenant reads.
    #
    # Both paths return the same 404 shape as "no events" so no
    # existence leaks. Denials route through the system_audit sink
    # (Gate 3.6).
    #
    # ── Phase A1A Gate 3R.1 — orphan-run guard ──
    # If ``console_row is None`` there is no authoritative RunHistory
    # row. Trace events may exist in the store (e.g. in-memory writes
    # before the run record was committed) but without an
    # authoritative row the run has no tenant ownership. Deny
    # (charter §3R.1).
    import logging as _logging
    _log = _logging.getLogger("app.api.run_trace.console")
    from app.database import AsyncSessionLocal
    from app.services.run_lifecycle import get_run_status
    from app.services.tenant_read_policy import is_tenant_visible

    async with AsyncSessionLocal() as db:
        console_row = await get_run_status(db, run_id=run_id)
    if console_row is None:
        # Phase A1A Gate 3R.1 — orphan-run denial. No authoritative
        # RunHistory row means no tenant-owned run; refuse even if
        # trace events exist in the store.
        _log.warning(
            "console.trace.denied orphan_run run_id=%s request_org=%s",
            run_id, org_id,
        )
        await _emit_console_system_audit(
            action="trace.read.denied.orphan_run",
            run_id=run_id,
            details={"request_org": org_id, "path": "console"},
        )
        raise HTTPException(
            status_code=404,
            detail=f"no trace events for run_id {run_id!r}",
        )
    if (
        console_row.organization_id is not None
        and org_id is not None
        and console_row.organization_id != org_id
    ):
        _log.warning(
            "console.trace.denied org_mismatch run_id=%s request_org=%s row_org=%s",
            run_id, org_id, console_row.organization_id,
        )
        await _emit_console_system_audit(
            action="trace.read.denied.org_mismatch",
            run_id=run_id,
            details={"request_org": org_id, "row_org": console_row.organization_id},
        )
        raise HTTPException(
            status_code=404,
            detail=f"no trace events for run_id {run_id!r}",
        )
    if not is_tenant_visible(
        getattr(console_row, "tenancy_classification", None)
    ):
        _log.warning(
            "console.trace.denied invisible_classification run_id=%s classification=%s",
            run_id, getattr(console_row, "tenancy_classification", None),
        )
        await _emit_console_system_audit(
            action="trace.read.denied.invisible_classification",
            run_id=run_id,
            details={
                "classification": getattr(console_row, "tenancy_classification", None),
                "path": "console",
            },
        )
        raise HTTPException(
            status_code=404,
            detail=f"no trace events for run_id {run_id!r}",
        )

    # DB store may block the event loop briefly; run in threadpool.
    if hasattr(store, "get_run_scoped"):
        events = await asyncio.to_thread(store.get_run_scoped, run_id, org_id)
    else:
        events = await asyncio.to_thread(store.get_run, run_id)

    if not events:
        if getattr(console_row, "trace_events_purged_at", None):
            from app.services.retention import RetentionPolicy

            retention_days = RetentionPolicy.from_env().run_trace_events_ttl_days
            purged_at = console_row.trace_events_purged_at
            raise HTTPException(
                status_code=410,
                detail={
                    "code": "TRACE_EXPIRED",
                    "message": "The Run trace is no longer available after retention purge.",
                    "retention_days": retention_days,
                    "purged_at": purged_at.isoformat() if purged_at else None,
                    "events_purged": int(
                        getattr(console_row, "trace_events_purged_count", 0) or 0
                    ),
                },
                headers={"X-iCoDer-Trace-Retention-Days": str(retention_days)},
            )
        raise HTTPException(
            status_code=404,
            detail=f"no trace events for run_id {run_id!r}",
        )

    serialized_events = [event.to_dict() for event in events]
    attestation_org = str(getattr(console_row, "organization_id", None) or org_id or "")
    try:
        trace_attestation = issue_trace_attestation(
            run_id=run_id,
            organization_id=attestation_org,
            events=serialized_events,
        )
    except TraceAttestationError as exc:
        _log.error(
            "console.trace.attestation_failed run_id=%s error_type=%s",
            run_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="trace authenticity proof could not be created",
        ) from exc

    if format == "raw":
        return {
            "run_id": run_id,
            "events": serialized_events,
            "trace_attestation": trace_attestation,
            "summary": _build_run_summary(console_row, events),
        }

    # Default: timeline format — already display-safe.
    return {
        "run_id": run_id,
        "timeline": serialized_events,
        "step_count": len(events),
        "trace_attestation": trace_attestation,
        "summary": _build_run_summary(console_row, events),
    }


@router.get("/runs/{run_id}/trace")
async def get_run_trace(
    run_id: str,
    request: Request,
    format: str = Query("timeline", description="timeline | raw"),
) -> dict[str, Any]:
    """Return the ordered trace events for one run.

    Args:
        run_id: The run identifier (from the A2A envelope or
            orchestrator run context).
        format: ``timeline`` (default) returns events sorted by ts
            with display-safe field names. ``raw`` returns the
            internal store dump (for debugging).

    Returns:
        200 ``{"run_id": ..., "events": [...], "trace_attestation": ...}``
        or ``{"run_id": ..., "timeline": [...], "trace_attestation": ...}``
        depending on format.

    Raises:
        404 if run_id has no trace events OR if the run belongs to
        a different organization (don't leak cross-org existence).
    """
    return await _get_run_trace_impl(run_id, format, request)


# ── Phase 4-G #3: RunHistory list endpoint ───────────────────────────────


@router.get("/runs/history")
async def list_run_history(
    request: Request,
    agent_id: str = Query("", description="Filter by agent_id (exact match)"),
    days: int = Query(0, ge=0, le=365, description="Filter to last N days (0 = no date filter)"),
    limit: int = Query(50, ge=1, le=200, description="Max items to return"),
) -> dict[str, Any]:
    """Return recent run summaries for the current user's org.

    Used by AgentChatPage's history dropdown to hydrate on page load.
    The endpoint reads from the ``run_history`` table (Phase 4-G #3
    migration 010) which the unified ``POST /api/v1/agents/{id}/run``
    endpoint populates after each run.

    Filtering:
      - ``agent_id`` optional (exact match); omitted = all agents
      - ``days`` optional (Phase 5 A6); 0 = no date filter, otherwise only
        include rows with ``created_at >= now - days``. Default: 0 (all time)
      - ``user_id`` / ``organization_id`` derived from request state
        (set by TenantHeaderMiddleware + auth)
      - ``limit`` capped at 200 to bound response size

    Returns ``{"items": [...], "total": <int>}`` ordered by created_at desc.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import create_engine, select, desc, text as sa_text
    from sqlalchemy.orm import Session
    from app.config import settings
    from app.models.run_history import RunHistoryModel

    org_id = get_request_tenant(request) or None
    user_attr = getattr(request.state, "user", None)
    user_id = getattr(user_attr, "id", None) if user_attr else None

    db_url = getattr(settings, "DATABASE_URL", "") or "sqlite+aiosqlite:///./data/icoder.db"
    sync_url = db_url.replace("+aiosqlite", "").replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(sync_url, echo=False)
    try:
        with Session(engine) as session:
            stmt = select(RunHistoryModel).order_by(desc(RunHistoryModel.created_at)).limit(limit)
            if agent_id:
                stmt = stmt.where(RunHistoryModel.agent_id == agent_id)
            if org_id:
                stmt = stmt.where(RunHistoryModel.organization_id == org_id)
            if user_id:
                stmt = stmt.where(RunHistoryModel.user_id == str(user_id))
            if days > 0:
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                stmt = stmt.where(RunHistoryModel.created_at >= cutoff)
            # Phase A1A Gate 3.2 §1 — exclude non-tenant-visible rows
            # (LEGACY_TENANT_UNKNOWN / AMBIGUOUS / QUARANTINED /
            # MODERN_SYSTEM / NULL classification). They remain in the
            # DB for forensics but never appear in normal tenant reads.
            from app.services.tenant_read_policy import apply_tenant_visibility_filter
            stmt = apply_tenant_visibility_filter(
                stmt, RunHistoryModel.tenancy_classification,
                also_exclude_null=True,
            )
            rows = session.execute(stmt).scalars().all()
            items = [
                {
                    "run_id": row.run_id,
                    "trace_id": row.trace_id,
                    "agent_id": row.agent_id,
                    "runtime_mode": row.runtime_mode,
                    "latency_ms": row.latency_ms,
                    "cost_usd": row.cost_usd,
                    "input_preview": (row.input_text or "")[:200],
                    "output_preview": (row.output_summary or "")[:200],
                    "error": row.error,
                    "error_reason": row.error_reason,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]
            return {"items": items, "total": len(items)}
    finally:
        engine.dispose()


__all__ = ["router"]
