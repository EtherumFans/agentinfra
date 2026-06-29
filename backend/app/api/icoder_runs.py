"""iCoDer Run Trace API — discoverable surface for execution history.

P1.0-E: Thin aliases over the existing ``/api/runtime/runs*`` endpoints so
the frontend ``/runtime/runs`` page has a stable, discoverable URL.

Endpoints
---------
* ``GET /api/icoder/runs``         — list runs (filter by agent_ref, paginate)
* ``GET /api/icoder/runs/{run_id}`` — get one run by id (404 if unknown)

Design rules
------------
* Reuses ``app.state.run_history`` (RunHistoryStore) exactly like
  ``/api/runtime/runs`` does. No new persistence.
* No fake data. Empty history → ``{runs: [], total: 0}`` + header note.
* Unknown run_id → HTTP 404 with ``error_code: RUN_NOT_FOUND``.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/icoder/runs", tags=["agent-hub"])


def _get_history():
    """Return ``app.state.run_history`` or None.

    Lazy import avoids a circular dep on app.main.
    """
    try:
        from app.main import app as _app

        return getattr(_app.state, "run_history", None)
    except Exception:
        return None


@router.get("")
async def list_runs(
    agent_ref: str = Query("", description="Filter by agent_ref (e.g. icoder/medcoder-coding-review-agent@1.0.0)"),
    limit: int = Query(50, le=200, description="Max runs to return (default 50, max 200)"),
) -> dict[str, Any]:
    """List recent run history entries.

    Returns ``{runs, total, history_available}`` so the frontend can
    distinguish "no runs yet" from "history store not initialized".
    """
    history = _get_history()
    if not history:
        return {"runs": [], "total": 0, "history_available": False}
    runs = history.query(agent_ref=agent_ref, limit=limit)
    return {
        "runs": runs,
        "total": len(runs),
        "history_available": True,
    }


@router.get("/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    """Fetch one run by its ``run_id``.

    404 (with error_code RUN_NOT_FOUND) if the run is not in history.
    """
    history = _get_history()
    if not history:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "RUN_HISTORY_UNAVAILABLE",
                "message": "Run history store not initialized on this runtime.",
            },
        )
    entry = history.get(run_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "RUN_NOT_FOUND",
                "run_id": run_id,
                "message": f"Run not found: {run_id}",
            },
        )
    return entry


__all__ = ["router"]