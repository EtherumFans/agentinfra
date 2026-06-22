"""Task endpoints (SPEC §7.5) — Phase 1 STUB.

Phase 5 will replace these stubs with the full task state machine.
For now both endpoints return 501 UNSUPPORTED_OPERATION.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .envelope import make_error_response
from .errors import (
    A2AError,
    A2AErrorCode,
    task_not_cancelable,
    task_not_found,
    unsupported_operation,
)
from .version import A2A_PROTOCOL_HEADER, A2A_PROTOCOL_VERSION


def build_task_stub_router() -> APIRouter:
    """Build the stub task router.

    Returns 501 for both ``GET /tasks/{id}`` and ``POST /tasks/{id}/cancel``.
    """
    router = APIRouter(prefix="/api/icoder/tasks", tags=["a2a-task-stub"])

    @router.get("/{task_id}")
    async def get_task(request: Request, task_id: str) -> JSONResponse:
        """Phase 1 stub — return 501 UNSUPPORTED_OPERATION."""
        err = unsupported_operation(
            details="tasks/get will be implemented in Phase 5"
        )
        return _error(err)

    @router.post("/{task_id}/cancel")
    async def cancel_task(request: Request, task_id: str) -> JSONResponse:
        """Phase 1 stub — return 501 UNSUPPORTED_OPERATION."""
        err = unsupported_operation(
            details="tasks/cancel will be implemented in Phase 5"
        )
        return _error(err)

    return router


def _error(err: A2AError) -> JSONResponse:
    body = make_error_response(None, err)
    return JSONResponse(
        status_code=err.http_status,
        headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
        content=body,
    )


__all__ = ["build_task_stub_router"]