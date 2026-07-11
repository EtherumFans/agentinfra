"""RunTrace API — Phase 3-D1 Task 4 (in-memory) + Phase 3-D2 Task 1 (DB).

Exposes the RunTraceStore via a read-only endpoint so the frontend
RunTracePage can render the 9-step timeline.

  GET /api/runtime/runs/{run_id}/trace
    → 200 {"run_id": "...", "events": [RunTraceEvent.to_dict(), ...]}

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
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
from app.middleware.tenant_extractor import get_request_tenant


router = APIRouter(prefix="/api/runtime", tags=["run-trace"])


async def _get_run_trace_impl(
    run_id: str,
    format: str,
    request: Request,
) -> dict[str, Any]:
    store = get_default_store()
    org_id: Optional[str] = get_request_tenant(request)

    # DB store may block the event loop briefly; run in threadpool.
    if hasattr(store, "get_run_scoped"):
        events = await asyncio.to_thread(store.get_run_scoped, run_id, org_id)
    else:
        events = await asyncio.to_thread(store.get_run, run_id)

    if not events:
        raise HTTPException(
            status_code=404,
            detail=f"no trace events for run_id {run_id!r}",
        )

    if format == "raw":
        return {
            "run_id": run_id,
            "events": [e.to_dict() for e in events],
        }

    # Default: timeline format — already display-safe.
    return {
        "run_id": run_id,
        "timeline": [e.to_dict() for e in events],
        "step_count": len(events),
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
        200 ``{"run_id": ..., "events": [...]}`` or
        ``{"run_id": ..., "timeline": [...]}`` depending on format.

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
