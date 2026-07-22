"""Task endpoints (SPEC §7.5) — A1B-AE-R.1.a real implementation.

Replaces the A1B-AE ``routes_task_stub.py`` 501 placeholder with real
``GET /api/icoder/tasks/{task_id}`` and ``POST /api/icoder/tasks/{task_id}/cancel``
endpoints backed by ``context_task_refs``.

State machine (per ``task_state.py``):

    submitted → working → {completed | failed | canceled}

``POST /tasks/{id}/cancel`` is only valid from ``submitted`` or
``working``. Calling it on a terminal state returns ``409
TASK_NOT_CANCELABLE``. Looking up an unknown ``task_id`` returns
``404 TASK_NOT_FOUND``.

A1B-AE-R.1.a does NOT yet filter by ``org_id`` — cross-tenant
hardening is R.1.b. The route signature already takes ``org_id``
in preparation, but the column does not yet exist on
``context_task_refs``; R.1.b adds the column + the filter.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from ..context.db_models import ContextTaskRefRow
from .envelope import make_error_response, make_success_response
from .errors import A2AError, task_not_cancelable, task_not_found
from .task_state import InvalidTaskTransition, TaskState, next_state
from .version import A2A_PROTOCOL_HEADER, A2A_PROTOCOL_VERSION


def build_task_router() -> APIRouter:
    """Build the real Task router (mounted at ``/api/icoder/tasks``)."""
    router = APIRouter(prefix="/api/icoder/tasks", tags=["a2a-task"])

    @router.get("/{task_id}", operation_id="a2a_get_task_v0_3")
    async def get_task(
        task_id: str,
        db: AsyncSession = Depends(get_db),
    ) -> JSONResponse:
        row = await _load_task(db, task_id)
        if row is None:
            return _task_not_found_response(task_id)
        return _task_response(row)

    @router.post("/{task_id}/cancel", operation_id="a2a_cancel_task_v0_3")
    async def cancel_task(
        task_id: str,
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> JSONResponse:
        body = await _safe_body(request)
        row = await _load_task(db, task_id)
        if row is None:
            return _task_not_found_response(task_id)
        current = TaskState(row.state)
        try:
            new_state = next_state(current, TaskState.CANCELED)
        except InvalidTaskTransition:
            err = task_not_cancelable(task_id)
            return _error_response(err)

        now = datetime.now(timezone.utc)
        await db.execute(
            update(ContextTaskRefRow)
            .where(ContextTaskRefRow.task_id == task_id)
            .values(state=new_state.value, completed_at=now)
        )
        await db.commit()
        row = await _load_task(db, task_id)
        return _task_response(row, cancelled_reason=body.get("reason", ""))

    return router


async def _load_task(db: AsyncSession, task_id: str) -> ContextTaskRefRow | None:
    stmt = select(ContextTaskRefRow).where(ContextTaskRefRow.task_id == task_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _safe_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _task_response(row: ContextTaskRefRow, *, cancelled_reason: str = "") -> JSONResponse:
    body = make_success_response(
        None,
        {
            "kind": "task",
            "id": row.task_id,
            "contextId": row.context_id,
            "status": {
                "state": row.state,
                "message": cancelled_reason or None,
                "timestamp": (row.completed_at or row.started_at).isoformat(),
            },
            "artifacts": [],
            "history": [],
        },
    )
    return JSONResponse(
        status_code=200,
        headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
        content=body,
    )


def _task_not_found_response(task_id: str) -> JSONResponse:
    return _error_response(task_not_found(task_id))


def _error_response(err: A2AError) -> JSONResponse:
    body = make_error_response(None, err)
    return JSONResponse(
        status_code=err.http_status,
        headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
        content=body,
    )


__all__ = ["build_task_router"]
