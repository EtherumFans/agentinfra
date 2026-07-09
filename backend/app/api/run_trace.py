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


__all__ = ["router"]
