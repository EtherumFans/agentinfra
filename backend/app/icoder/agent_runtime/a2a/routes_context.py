"""Context endpoints (SPEC §7.4) — A1B-AE-R.1.b.

``DELETE /api/icoder/contexts/{context_id}`` performs a real scrub:

* ``contexts`` row removed
* ``context_messages`` / ``context_task_refs`` / ``context_artifact_refs``
  cascade via FK ON DELETE CASCADE (migration 024)
* ``original_input_audit`` rows scrubbed manually (no FK)

Cross-tenant: the endpoint depends on ``get_current_organization``
and only deletes the row if ``contexts.organization_id`` matches the
JWT's ``current_org.id``. Mismatch returns 404 CONTEXT_NOT_FOUND —
never leak that the context exists under a different tenant.

Other Context verbs (GET, PATCH state) are intentionally NOT added
in R.1.b — they belong in a later sub-gate once the inbound handler
starts persisting Context rows from real Message:send traffic. For
now Context rows exist for the lifecycle/GC tests and for future
expansion; the only user-facing verb is DELETE.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_organization
from app.models.organization import Organization

from ..context.context_isolation import ContextIsolationError
from ..context.context_lifecycle import ContextLifecycle
from ..context.context_repository import ContextRepository
from .envelope import make_error_response, make_success_response
from .errors import context_not_found
from .version import A2A_PROTOCOL_HEADER, A2A_PROTOCOL_VERSION


def build_context_router() -> APIRouter:
    """Build the Context router (mounted at ``/api/icoder/contexts``)."""
    router = APIRouter(prefix="/api/icoder/contexts", tags=["a2a-context"])

    @router.delete(
        "/{context_id}",
        operation_id="a2a_delete_context_v0_3",
    )
    async def delete_context(
        context_id: str,
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ) -> JSONResponse:
        repo = ContextRepository(db)
        lifecycle = ContextLifecycle(repo)
        try:
            await lifecycle.destroy_now(
                context_id,
                organization_id=current_org.id,
                reason="user_requested",
            )
        except ContextIsolationError:
            err = context_not_found(context_id)
            body = make_error_response(None, err)
            return JSONResponse(
                status_code=err.http_status,
                headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
                content=body,
            )
        body = make_success_response(
            None,
            {
                "kind": "context",
                "contextId": context_id,
                "deleted": True,
                "reason": "user_requested",
            },
        )
        return JSONResponse(
            status_code=200,
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            content=body,
        )

    return router


__all__ = ["build_context_router"]
