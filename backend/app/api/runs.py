"""Phase 7 Gate 4 — Run lifecycle endpoints.

Per Phase 7 §9:

  GET  /api/v1/runs/{run_id}
    → 200 {"run_id": "...", "status": "...", "agent_id": "...",
           "latency_ms": N, "cost": {"amount": ..., "currency": "CNY"},
           "error": bool, "error_reason": str,
           "cancelled_at": iso8601|null, "cancel_reason": str|null,
           "terminal": bool}

  POST /api/v1/runs/{run_id}/cancel
    Body: {"reason": str}  (optional)
    → 200 ALREADY_COMPLETE  — run already finished; original status returned
    → 200 CANCELLED         — run was PENDING, dropped before Provider call
    → 202 RECORDED_ONLY     — Provider mid-call (cancel not supported); recorded
    → 404 NOT_FOUND         — run_id unknown
    → 403 FORBIDDEN         — run belongs to another org

§9.3 Timeout: when the SDK 90s timeout fires, the SDK polls
``GET /api/v1/runs/{run_id}`` until ``terminal=True``. The Run
continues server-side regardless.

§9.4 Cost: never zero a recorded cost. ``GET`` returns whatever cost
was actually recorded (real Provider charges).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import (
    get_current_organization,
    get_current_user_or_oauth_client,
)
from app.models.organization import Organization
from app.services.run_lifecycle import (
    CancelOutcome,
    RunStatus,
    get_run_status,
    request_cancel,
)
from app.services.run_sse_observability import get_run_sse_metrics

logger = logging.getLogger(__name__)
_SSE_METRICS = get_run_sse_metrics()

router = APIRouter(prefix="/api/v1/runs", tags=["phase7-runs"])


# Run-event SSE tuning. Module constants keep the production contract
# explicit while allowing regression tests to use millisecond-scale waits.
_SSE_POLL_INTERVAL_SECONDS = 0.25
_SSE_HEARTBEAT_INTERVAL_SECONDS = 15.0


def _resolve_trace_token_organization(token_organization_id: str) -> str:
    """Return the authoritative tenant for a partner trace token.

    Legacy empty-org tokens are accepted only in explicitly local,
    single-tenant mode.  Cloud deployments must carry the tenant in the
    signed token and therefore fail closed before opening a database session.
    """

    normalized = (token_organization_id or "").strip()
    if normalized:
        return normalized

    from app.config import settings

    local_org = (settings.ICODER_SINGLE_TENANT_ORG_ID or "").strip()
    if settings.ICODER_DEPLOYMENT_MODE == "local" and local_org:
        return local_org
    raise HTTPException(status_code=401, detail={
        "code": "TRACE_TOKEN_MALFORMED",
        "message": "Trace token is not bound to an organization.",
    })


# ── Phase A1A Gate 3.6 — system-scope audit helper ────────────────


async def _emit_system_audit(
    *,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Best-effort MODERN_SYSTEM audit row for denials.

    Used by SSE / trace URL / Console denial paths so Security Admin
    can audit "who tried to read what" without the tenant themselves
    seeing the denial record (the row carries organization_id=NULL +
    classification=MODERN_SYSTEM, so tenant reads exclude it per
    Gate 3.2).

    Failures are logged but do not bubble up — a denial must never
    be downgraded to a 500 because the audit sink had a transient
    error.
    """
    try:
        from app.database import AsyncSessionLocal
        from app.services.system_audit import system_audit
        async with AsyncSessionLocal() as db:
            await system_audit(
                db,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
            )
            await db.commit()
    except Exception as audit_err:  # pragma: no cover — defensive
        logger.error(
            "system_audit emit failed: %s (action=%s resource=%s/%s)",
            audit_err, action, resource_type, resource_id,
        )


# ── Response models ────────────────────────────────────────────────


class RunStatusResponse(BaseModel):
    """Shape returned by GET /api/v1/runs/{run_id}.

    Partners poll this after an SDK 90s timeout (§9.3). The
    ``terminal`` flag tells them when to stop polling.
    """
    run_id: str
    status: str
    terminal: bool
    agent_id: str = ""
    trace_id: str = ""
    runtime_mode: str = ""
    latency_ms: int = 0
    cost_amount: float = 0.0
    cost_currency: str = "CNY"
    error: bool = False
    error_reason: Optional[str] = None
    cancel_reason: Optional[str] = None
    cancelled_at: Optional[str] = None
    cancelled_by_user_id: Optional[str] = None
    created_at: Optional[str] = None
    trace_retention_days: int = 90
    trace_events_purged_at: Optional[str] = None
    trace_events_purged_count: int = 0


class CancelRequest(BaseModel):
    """Body for POST /api/v1/runs/{run_id}/cancel."""
    reason: str = Field(
        default="",
        description="Free-form reason; recorded for audit (§9.2).",
    )


class CancelResponse(BaseModel):
    """Outcome of a cancel request (§9.1)."""
    run_id: str
    outcome: str  # ALREADY_COMPLETE | CANCELLED | RECORDED_ONLY | NOT_FOUND | FORBIDDEN
    status: str   # current RunStatus
    message: str
    cancel_reason: Optional[str] = None
    cancelled_at: Optional[str] = None


class TraceTokenRenewResponse(BaseModel):
    """Fresh run-bound trace authorization for resilient SDK streams."""

    run_id: str
    trace_token: str
    expires_at: int
    events_url: str
    trace_url: str
    trace_retention_days: int


class TraceRetentionErrorDetail(BaseModel):
    code: Literal["SSE_CURSOR_EXPIRED", "SSE_TRACE_EXPIRED", "TRACE_EXPIRED"]
    message: str
    retention_days: int
    purged_at: Optional[str] = None
    events_purged: int = 0


class TraceRetentionErrorResponse(BaseModel):
    detail: TraceRetentionErrorDetail


def _trace_retention_days() -> int:
    from app.services.retention import RetentionPolicy

    return RetentionPolicy.from_env().run_trace_events_ttl_days


def _raise_trace_retention_error(
    row,
    *,
    code: Literal["SSE_CURSOR_EXPIRED", "SSE_TRACE_EXPIRED", "TRACE_EXPIRED"],
    message: str,
) -> None:
    retention_days = _trace_retention_days()
    purged_at = getattr(row, "trace_events_purged_at", None)
    raise HTTPException(
        status_code=410,
        detail={
            "code": code,
            "message": message,
            "retention_days": retention_days,
            "purged_at": purged_at.isoformat() if purged_at else None,
            "events_purged": int(
                getattr(row, "trace_events_purged_count", 0) or 0
            ),
        },
        headers={"X-iCoDer-Trace-Retention-Days": str(retention_days)},
    )


# ── GET /api/v1/runs/{run_id} ──────────────────────────────────────


_OUTCOME_MESSAGES = {
    CancelOutcome.ALREADY_COMPLETE: (
        "Run is already terminal; cancel request recorded for audit only."
    ),
    CancelOutcome.RECORDED_ONLY: (
        "Run is mid-Provider-call and Provider does not support "
        "mid-stream cancel (DeepSeek). Request recorded; run will "
        "complete and the result will be available via GET."
    ),
    CancelOutcome.CANCELLED: (
        "Run was PENDING (pre-Provider-call); cancelled. No Provider "
        "charge incurred."
    ),
    CancelOutcome.NOT_FOUND: "Run not found.",
    CancelOutcome.FORBIDDEN: "Run belongs to a different organization.",
}


@router.get(
    "/{run_id}",
    response_model=RunStatusResponse,
    operation_id="phase7_get_run_status",
)
async def get_run(
    run_id: str,
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> RunStatusResponse:
    """Read the current status of a Run (§9.3 polling endpoint).

    Returns 404 if the run doesn't exist OR belongs to a different
    org (don't leak cross-org run existence).
    """
    row = await get_run_status(db, run_id=run_id)
    if row is None:
        raise HTTPException(status_code=404, detail={
            "code": "RUN_NOT_FOUND",
            "message": f"Run {run_id} not found.",
        })
    # Org scope: if both orgs are known and they differ, 404 (not 403 —
    # we don't leak existence).
    if (
        row.organization_id is not None
        and current_org.id is not None
        and row.organization_id != current_org.id
    ):
        raise HTTPException(status_code=404, detail={
            "code": "RUN_NOT_FOUND",
            "message": f"Run {run_id} not found.",
        })
    # Phase A1A Gate 3.2 §2 — point-read visibility guard. If the row
    # is QUARANTINED / LEGACY_TENANT_UNKNOWN / LEGACY_TENANT_AMBIGUOUS
    # / MODERN_SYSTEM, return the same 404 as if it didn't exist.
    # No existence leak.
    from app.services.tenant_read_policy import enforce_tenant_visible_or_404
    enforce_tenant_visible_or_404(
        classification=getattr(row, "tenancy_classification", None),
        run_id=run_id,
        resource="run",
    )
    return RunStatusResponse(
        run_id=row.run_id,
        status=row.status,
        terminal=RunStatus.is_terminal(row.status),
        agent_id=row.agent_id,
        trace_id=row.trace_id,
        runtime_mode=row.runtime_mode,
        latency_ms=row.latency_ms,
        cost_amount=row.cost_usd or 0.0,
        cost_currency="CNY",
        error=bool(row.error),
        error_reason=row.error_reason,
        cancel_reason=row.cancel_reason,
        cancelled_at=row.cancelled_at.isoformat() if row.cancelled_at else None,
        cancelled_by_user_id=row.cancelled_by_user_id,
        created_at=row.created_at.isoformat() if row.created_at else None,
        trace_retention_days=_trace_retention_days(),
        trace_events_purged_at=(
            row.trace_events_purged_at.isoformat()
            if getattr(row, "trace_events_purged_at", None)
            else None
        ),
        trace_events_purged_count=int(
            getattr(row, "trace_events_purged_count", 0) or 0
        ),
    )


# ── POST /api/v1/runs/{run_id}/cancel ──────────────────────────────


@router.post(
    "/{run_id}/cancel",
    response_model=CancelResponse,
    responses={
        202: {
            "model": CancelResponse,
            "description": "Cancellation recorded, but the provider call continues.",
        },
    },
    operation_id="phase7_cancel_run",
)
async def cancel_run(
    run_id: str,
    body: CancelRequest,
    http_response: Response,
    principal: tuple = Depends(get_current_user_or_oauth_client),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> CancelResponse:
    """Request cancellation of a Run (§9.2).

    Never lies about cancellation. If the Provider doesn't support
    mid-stream cancel (DeepSeek doesn't), returns 202 RECORDED_ONLY
    and the run continues. Partners should poll GET for the real
    final status.

    Status code mapping (HTTPException for the error cases):
    - 200 + ALREADY_COMPLETE — run already terminal
    - 200 + CANCELLED        — pre-Provider-call PENDING run was dropped
    - 202 + RECORDED_ONLY    — Provider mid-call, cancel not supported
    - 404 + NOT_FOUND        — run_id unknown (or other org)
    """
    current_user, current_client = principal
    user_id = (
        str((current_client or {}).get("client_id") or "")
        if current_client is not None
        else str(getattr(current_user, "id", "") or "")
    )
    outcome, status, row = await request_cancel(
        db,
        run_id=run_id,
        cancelled_by_user_id=user_id,
        expected_organization_id=current_org.id,
        cancel_reason=body.reason or "",
    )

    if outcome == CancelOutcome.NOT_FOUND:
        raise HTTPException(status_code=404, detail={
            "code": "RUN_NOT_FOUND",
            "message": f"Run {run_id} not found.",
        })
    if outcome == CancelOutcome.FORBIDDEN:
        # Return 404 not 403 to avoid leaking cross-org run existence.
        raise HTTPException(status_code=404, detail={
            "code": "RUN_NOT_FOUND",
            "message": f"Run {run_id} not found.",
        })

    await db.commit()

    # Phase A1A Gate 3R.2 — emit ``run.cancel`` audit row so the tenant
    # audit dashboard has a record of who cancelled what when. Emitted
    # for all non-error outcomes (CANCELLED / RECORDED_ONLY /
    # ALREADY_COMPLETE) — NOT_FOUND and FORBIDDEN already raised above.
    try:
        from app.middleware.audit import log_action
        username = (
            f"oauth:{(current_client or {}).get('client_id') or 'unknown'}"
            if current_client is not None
            else getattr(current_user, "username", None) or getattr(current_user, "email", None)
        )
        await log_action(
            db,
            user_id=user_id or None,
            username=username,
            action="run.cancel",
            resource_type="run_history",
            resource_id=run_id,
            details={
                "outcome": outcome,
                "status": status,
                "cancel_reason": (body.reason or "") or None,
            },
            organization_id=current_org.id,
        )
        await db.commit()
    except Exception as audit_err:  # pragma: no cover — defensive
        logger.error(
            "run.cancel audit emit failed: %s (run_id=%s)",
            audit_err, run_id,
        )

    response = CancelResponse(
        run_id=run_id,
        outcome=outcome,
        status=status,
        message=_OUTCOME_MESSAGES.get(outcome, ""),
        cancel_reason=row.cancel_reason if row else None,
        cancelled_at=row.cancelled_at.isoformat() if row and row.cancelled_at else None,
    )

    # The HTTP status is part of the public contract. RECORDED_ONLY is
    # accepted for audit but did not stop the provider, so it must not look
    # like a synchronous 200 cancellation success.
    if outcome == CancelOutcome.RECORDED_ONLY:
        http_response.status_code = 202

    return response


@router.post(
    "/{run_id}/trace-token",
    response_model=TraceTokenRenewResponse,
    responses={
        200: {
            "description": "Fresh run-bound trace authorization.",
            "headers": {
                "Cache-Control": {
                    "description": "Credential responses are never cacheable.",
                    "schema": {"type": "string", "example": "no-store"},
                },
            },
        },
        401: {"description": "Bearer identity is missing or expired."},
        404: {"description": "Run is absent or not visible to this organization."},
        503: {"description": "The authorization audit could not be persisted."},
    },
    operation_id="phase9_renew_run_trace_token",
)
async def renew_run_trace_token(
    run_id: str,
    http_response: Response,
    principal: tuple = Depends(get_current_user_or_oauth_client),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TraceTokenRenewResponse:
    """Issue a fresh signed trace token for an authorized Run principal.

    The bearer principal must still belong to the Run's organization. Unknown,
    cross-organization and non-tenant-visible rows share the same 404 response.
    The token response is never cacheable.
    """
    row = await get_run_status(db, run_id=run_id)
    if (
        row is None
        or (
            row.organization_id is not None
            and current_org.id is not None
            and row.organization_id != current_org.id
        )
    ):
        _SSE_METRICS.token_renewed("run_not_found")
        raise HTTPException(status_code=404, detail={
            "code": "RUN_NOT_FOUND",
            "message": f"Run {run_id} not found.",
        })

    from app.services.tenant_read_policy import enforce_tenant_visible_or_404
    try:
        enforce_tenant_visible_or_404(
            classification=getattr(row, "tenancy_classification", None),
            run_id=run_id,
            resource="run",
        )
    except HTTPException:
        _SSE_METRICS.token_renewed("visibility_denied")
        raise

    from app.services.trace_token import (
        DEFAULT_TTL_SECONDS,
        issue_trace_token,
        verify_trace_token,
    )

    if os.environ.get("ICODER_AUDIT_WRITE_PAUSED", "false").lower() == "true":
        _SSE_METRICS.token_renewed("audit_paused")
        raise HTTPException(status_code=503, detail={
            "code": "AUDIT_PERSISTENCE_FAILED",
            "message": "Trace authorization cannot be renewed while audit writes are paused.",
        })

    current_user, current_client = principal
    api_client_id = (
        str((current_client or {}).get("client_id") or "")
        if current_client is not None
        else ""
    )
    actor_id = (
        api_client_id
        if current_client is not None
        else str(getattr(current_user, "id", "") or "")
    )
    try:
        token = issue_trace_token(
            run_id=run_id,
            organization_id=row.organization_id or current_org.id,
            api_client_id=api_client_id or None,
            ttl_seconds=DEFAULT_TTL_SECONDS,
        )
        claims = verify_trace_token(token, expected_run_id=run_id)
    except Exception:
        _SSE_METRICS.token_renewed("other_failure")
        raise

    try:
        from app.middleware.audit import log_action
        username = (
            f"oauth:{api_client_id or 'unknown'}"
            if current_client is not None
            else getattr(current_user, "username", None)
            or getattr(current_user, "email", None)
        )
        await log_action(
            db,
            user_id=actor_id or None,
            username=username,
            action="run.trace_token.renew",
            resource_type="run_history",
            resource_id=run_id,
            details={
                "expires_at": claims.exp,
                "principal_type": "oauth_client" if current_client is not None else "user",
            },
            organization_id=row.organization_id or current_org.id,
        )
        await db.commit()
    except Exception as audit_err:  # pragma: no cover - defensive
        await db.rollback()
        logger.error(
            "run.trace_token renew audit failed: %s (run_id=%s)",
            audit_err,
            run_id,
        )
        _SSE_METRICS.token_renewed("audit_failed")
        # Credential issuance must remain auditable.  The fresh token only
        # exists in this process at this point, so failing before the response
        # prevents an unrecorded authorization from escaping to the caller.
        raise HTTPException(status_code=503, detail={
            "code": "AUDIT_PERSISTENCE_FAILED",
            "message": "Trace authorization could not be renewed safely.",
        }) from audit_err

    http_response.headers["Cache-Control"] = "no-store"
    _SSE_METRICS.token_renewed("success")
    return TraceTokenRenewResponse(
        run_id=run_id,
        trace_token=token,
        expires_at=claims.exp,
        events_url=f"/api/v1/runs/{run_id}/events",
        trace_url=f"/api/v1/runs/{run_id}/trace",
        trace_retention_days=_trace_retention_days(),
    )


__all__ = ["router"]


# ── Phase 7 Gate 7 §12 — Partner-secured trace endpoint ────────────


@router.get(
    "/{run_id}/trace",
    operation_id="phase7_get_run_trace_partner",
    responses={
        410: {
            "model": TraceRetentionErrorResponse,
            "description": "The authorized Run trace was removed by retention.",
        },
    },
)
async def get_run_trace_partner(
    run_id: str,
    request: Request,
    token: Optional[str] = None,
):
    """Partner-accessible trace view (§12.1).

    Partners can deep-link to a Run's trace without a Console JWT. The
    ``?token=`` query param is an HMAC-signed token issued by
    ``app.services.trace_token.issue_trace_token`` and embedded in the
    ``trace_url`` returned by POST /api/v1/agents/{id}/run.

    Token verification:
    - Signature must match (HMAC-SHA256 of payload, constant-time compare)
    - Token must not be past ``exp``
    - Token's ``run_id`` must equal the URL's ``{run_id}``
    - Token's ``organization_id`` (if set) must match the run's org
      (we read the run_history row to verify)

    On success, returns the same JSON the internal RunTrace endpoint
    returns (timeline format) — the data is already display-safe.

    Auth path precedence:
    1. ``?token=`` signed trace token (partner path) — this endpoint
    2. Console JWT via Authorization header (internal path) —
       ``/api/runtime/runs/{run_id}/trace`` (separate router)
    """
    from app.services.trace_token import (
        TraceTokenError,
        TraceTokenExpired,
        TraceTokenInvalidSignature,
        TraceTokenMalformed,
        TraceTokenOrgMismatch,
        TraceTokenRunMismatch,
        verify_trace_token,
    )

    if not token:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_REQUIRED",
            "message": "Partner trace access requires a signed ?token= query param.",
        })

    try:
        claims = verify_trace_token(token, expected_run_id=run_id)
    except TraceTokenExpired as e:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_EXPIRED",
            "message": str(e),
        })
    except TraceTokenInvalidSignature as e:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_INVALID",
            "message": "Trace token signature invalid.",
        })
    except TraceTokenRunMismatch as e:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_RUN_MISMATCH",
            "message": str(e),
        })
    except TraceTokenMalformed as e:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_MALFORMED",
            "message": str(e),
        })
    except TraceTokenError as e:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_INVALID",
            "message": str(e),
        })

    # Cross-check the run's org (if both the token and the DB specify one).
    # We don't 404 if the org doesn't match — that would leak existence.
    # Instead we return 403 with a generic message.
    #
    # Phase A1A Gate 3R.1 — orphan-run guard. The trace token may be
    # valid but if no authoritative RunHistory row exists, the run has
    # no tenant ownership and trace reads MUST refuse (charter §3R.1).
    from app.database import AsyncSessionLocal
    from app.services.database_tenancy import bind_tenant_to_transaction
    from app.services.run_lifecycle import get_run_status
    from app.services.tenant_read_policy import is_tenant_visible
    import logging as _logging
    _log = _logging.getLogger("app.api.runs.trace_url")

    org_id = _resolve_trace_token_organization(claims.organization_id)
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, org_id)
        row = await get_run_status(db, run_id=run_id)
    if row is None:
        # Orphan run: no authoritative RunHistory row. Refuse even if
        # the trace token is valid and trace events exist.
        _log.warning(
            "trace_url.denied orphan_run run_id=%s token_org=%s",
            run_id, claims.organization_id,
        )
        await _emit_system_audit(
            action="trace.read.denied.orphan_run",
            resource_type="run_history",
            resource_id=run_id,
            details={
                "token_org": claims.organization_id,
                "path": "partner_trace_url",
            },
        )
        raise HTTPException(status_code=404, detail={
            "code": "TRACE_NOT_FOUND",
            "message": f"no trace events for run_id {run_id!r}",
        })
    if row.organization_id and row.organization_id != org_id:
        raise HTTPException(status_code=403, detail={
            "code": "TRACE_TOKEN_ORG_MISMATCH",
            "message": "Trace token not valid for this run.",
        })
    # Phase A1A Gate 3.5 — visibility classification guard.
    # Token is valid + org matches, but if the run was
    # retroactively quarantined, deny. Return 404 (not 403)
    # to avoid leaking that the run exists at all.
    if not is_tenant_visible(
        getattr(row, "tenancy_classification", None)
    ):
        _log.warning(
            "trace_url.denied invisible_classification run_id=%s classification=%s",
            run_id, getattr(row, "tenancy_classification", None),
        )
        await _emit_system_audit(
            action="trace.read.denied.invisible_classification",
            resource_type="run_history",
            resource_id=run_id,
            details={
                "classification": getattr(row, "tenancy_classification", None),
                "path": "partner_trace_url",
            },
        )
        raise HTTPException(status_code=404, detail={
            "code": "TRACE_NOT_FOUND",
            "message": f"no trace events for run_id {run_id!r}",
        })

    # Issue the trace read using the token's org scope.
    from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
    import asyncio
    store = get_default_store()
    if hasattr(store, "get_run_scoped"):
        events = await asyncio.to_thread(store.get_run_scoped, run_id, org_id)
    else:
        events = await asyncio.to_thread(store.get_run, run_id)

    if not events:
        if getattr(row, "trace_events_purged_at", None):
            _raise_trace_retention_error(
                row,
                code="TRACE_EXPIRED",
                message="The Run trace is no longer available after retention purge.",
            )
        raise HTTPException(status_code=404, detail={
            "code": "TRACE_NOT_FOUND",
            "message": f"no trace events for run_id {run_id!r}",
        })

    return {
        "run_id": run_id,
        "timeline": [e.to_dict() for e in events],
        "step_count": len(events),
        "trace_token": {
            "api_client_id": claims.api_client_id or None,
            "exp": claims.exp,
            "organization_id": claims.organization_id or None,
        },
    }


# ── Phase 7 Gate 9 §14 — SSE / run-state event stream ──────────────


@router.get(
    "/{run_id}/events",
    operation_id="phase9_stream_run_events",
    responses={
        400: {"description": "Malformed Last-Event-ID cursor"},
        409: {"description": "Last-Event-ID is not part of this run trace"},
        410: {
            "model": TraceRetentionErrorResponse,
            "description": "The trace or requested cursor is outside the retention window.",
        },
    },
)
async def stream_run_events(
    run_id: str,
    request: Request,
    token: Optional[str] = None,
    last_event_id_header: Optional[str] = Header(
        default=None,
        alias="Last-Event-ID",
        description="Resume strictly after this previously received SSE event ID.",
    ),
):
    """Partner-accessible SSE stream of run-state events (§14.1).

    Emits the run's lifecycle events as ``text/event-stream`` using the
    Phase 6 unified envelope ``{name, payload, meta}``. Each event in the
    stream corresponds to one ``RunTraceEvent`` row, normalized as:

        data: {"name": "run.<step>", "payload": {...}, "meta": {...}}\n\n

    After all events have been emitted, sends a terminal
    ``stream.completed`` event and closes the connection. For an
    in-progress run, the stream stays open with periodic heartbeats
    (``: keepalive\\n\\n``) and emits new events as they land.

    Auth path is the same signed trace token from Gate 7 — partners
    don't need a Console JWT to subscribe.

    Contract (§14.2):
      - 200 + text/event-stream on success
      - 401 TRACE_TOKEN_REQUIRED — missing ?token=
      - 401 TRACE_TOKEN_INVALID  — bad signature
      - 401 TRACE_TOKEN_EXPIRED  — past exp
      - 401 TRACE_TOKEN_RUN_MISMATCH — token bound to a different run_id
      - 404 TRACE_NOT_FOUND      — unknown/inaccessible run, or a terminal
                                   run with no captured trace

    Heartbeat (§14.3): every 15s while waiting for new events, emits a
    SSE comment line ``: keepalive\\n\\n`` so intermediaries don't close
    the connection.

    Resume: clients may send the standard ``Last-Event-ID`` header. The
    stream resumes strictly after that stable trace event ID. Unknown or
    malformed cursors fail before response streaming begins.
    """
    import asyncio
    import json as _json
    from fastapi.responses import StreamingResponse

    from app.services.trace_token import (
        TraceTokenError,
        TraceTokenExpired,
        TraceTokenInvalidSignature,
        TraceTokenMalformed,
        TraceTokenRunMismatch,
        verify_trace_token,
    )

    request_started_at = time.monotonic()
    _SSE_METRICS.connection_attempted()

    if not token:
        _SSE_METRICS.rejected("token_required")
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_REQUIRED",
            "message": "Partner event stream requires a signed ?token= query param.",
        })

    try:
        claims = verify_trace_token(token, expected_run_id=run_id)
    except TraceTokenExpired as e:
        _SSE_METRICS.rejected("token_expired")
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_EXPIRED", "message": str(e),
        })
    except TraceTokenInvalidSignature:
        _SSE_METRICS.rejected("token_invalid")
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_INVALID",
            "message": "Trace token signature invalid.",
        })
    except TraceTokenRunMismatch as e:
        _SSE_METRICS.rejected("token_run_mismatch")
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_RUN_MISMATCH", "message": str(e),
        })
    except (TraceTokenMalformed, TraceTokenError) as e:
        _SSE_METRICS.rejected("token_malformed")
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_MALFORMED", "message": str(e),
        })

    from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
    store = get_default_store()
    org_id = _resolve_trace_token_organization(claims.organization_id)

    # ── Phase A1A Gate 3.4 (F04 carry-over) — defence-in-depth ──
    # The signed trace token already pins (run_id, org_id). But we
    # ALSO cross-check RunHistory.organization_id and the row's
    # visibility classification. Two scenarios this catches:
    #
    #   1. Token was issued for a run that has since been
    #      re-attributed to a different org (operator action). The
    #      stale token would otherwise still stream events.
    #   2. Run was retroactively classified QUARANTINED / UNKNOWN /
    #      AMBIGUOUS / MODERN_SYSTEM. Per charter §3.2 these rows are
    #      invisible to tenant reads, and SSE is a tenant read.
    #
    # Both paths return the same 404 TRACE_NOT_FOUND shape (no
    # existence leak). Denials are routed through the system_audit
    # sink (Gate 3.6).
    #
    # ── Phase A1A Gate 3R.1 — orphan-run guard ──
    # If ``sse_row is None`` there is no authoritative RunHistory row.
    # The signed trace token may be valid and trace events may exist
    # in the store, but without an authoritative row the run has no
    # tenant ownership. Deny (charter §3R.1).
    from app.database import AsyncSessionLocal
    from app.services.database_tenancy import bind_tenant_to_transaction
    from app.services.run_lifecycle import get_run_status
    from app.services.tenant_read_policy import enforce_tenant_visible_or_404, is_tenant_visible
    import logging as _logging
    _log = _logging.getLogger("app.api.runs.sse")

    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, org_id)
        sse_row = await get_run_status(db, run_id=run_id)
    if sse_row is None:
        _SSE_METRICS.rejected("run_not_found")
        # Phase A1A Gate 3R.1 — orphan-run denial. No authoritative
        # RunHistory row means no tenant-owned run; refuse even if
        # trace events exist in the store.
        _log.warning(
            "sse.denied orphan_run run_id=%s token_org=%s",
            run_id, org_id,
        )
        await _emit_system_audit(
            action="sse.denied.orphan_run",
            resource_type="run_history",
            resource_id=run_id,
            details={
                "token_org": org_id,
                "path": "sse",
            },
        )
        raise HTTPException(status_code=404, detail={
            "code": "TRACE_NOT_FOUND",
            "message": f"no trace events for run_id {run_id!r}",
        })
    # Org cross-check — if both orgs are known and differ, deny.
    if (
        sse_row.organization_id is not None
        and org_id is not None
        and sse_row.organization_id != org_id
    ):
        _SSE_METRICS.rejected("org_mismatch")
        _log.warning(
            "sse.denied org_mismatch run_id=%s token_org=%s row_org=%s",
            run_id, org_id, sse_row.organization_id,
        )
        await _emit_system_audit(
            action="sse.denied.org_mismatch",
            resource_type="run_history",
            resource_id=run_id,
            details={
                "token_org": org_id,
                "row_org": sse_row.organization_id,
            },
        )
        raise HTTPException(status_code=404, detail={
            "code": "TRACE_NOT_FOUND",
            "message": f"no trace events for run_id {run_id!r}",
        })
    # Visibility classification guard.
    if not is_tenant_visible(getattr(sse_row, "tenancy_classification", None)):
        _SSE_METRICS.rejected("visibility_denied")
        _log.warning(
            "sse.denied invisible_classification run_id=%s classification=%s",
            run_id, getattr(sse_row, "tenancy_classification", None),
        )
        await _emit_system_audit(
            action="sse.denied.invisible_classification",
            resource_type="run_history",
            resource_id=run_id,
            details={
                "classification": getattr(sse_row, "tenancy_classification", None),
            },
        )
        raise HTTPException(status_code=404, detail={
            "code": "TRACE_NOT_FOUND",
            "message": f"no trace events for run_id {run_id!r}",
        })

    if hasattr(store, "get_run_scoped"):
        events = await asyncio.to_thread(store.get_run_scoped, run_id, org_id)
    else:
        events = await asyncio.to_thread(store.get_run, run_id)

    # A newly-started run may legitimately have no trace event yet. Keep the
    # subscription open instead of forcing partners to race the first trace
    # write. A terminal run with no captured trace remains TRACE_NOT_FOUND.
    if not events and RunStatus.is_terminal(sse_row.status):
        if getattr(sse_row, "trace_events_purged_at", None):
            _SSE_METRICS.rejected("trace_expired")
            _raise_trace_retention_error(
                sse_row,
                code="SSE_TRACE_EXPIRED",
                message="The Run event stream is no longer available after retention purge.",
            )
        _SSE_METRICS.rejected("trace_not_found")
        raise HTTPException(status_code=404, detail={
            "code": "TRACE_NOT_FOUND",
            "message": f"no trace events for run_id {run_id!r}",
        })

    def _event_id_for(ev) -> str:
        return str(
            getattr(ev, "event_id", None)
            or f"legacy-ts:{ev.step}:{ev.ts:.6f}"
        )

    last_event_id = (last_event_id_header or "").strip()
    if last_event_id and (
        len(last_event_id) > 128
        or "\r" in last_event_id
        or "\n" in last_event_id
        or "\x00" in last_event_id
    ):
        _SSE_METRICS.rejected("cursor_invalid")
        raise HTTPException(status_code=400, detail={
            "code": "SSE_CURSOR_INVALID",
            "message": "Last-Event-ID is malformed.",
        })

    resume_index = 0
    if last_event_id:
        event_ids = [_event_id_for(ev) for ev in events]
        try:
            resume_index = event_ids.index(last_event_id) + 1
        except ValueError:
            if getattr(sse_row, "trace_events_purged_at", None):
                _SSE_METRICS.rejected("cursor_expired")
                _raise_trace_retention_error(
                    sse_row,
                    code="SSE_CURSOR_EXPIRED",
                    message=(
                        "The requested event cursor cannot be resolved after "
                        "retention purge. Restart from the retained prefix or "
                        "fetch the authoritative Run status."
                    ),
                )
            _SSE_METRICS.rejected("cursor_not_found")
            raise HTTPException(status_code=409, detail={
                "code": "SSE_CURSOR_NOT_FOUND",
                "message": "Last-Event-ID does not belong to this run trace.",
            })

    def _format_sse_event(
        name: str,
        payload: dict,
        meta: dict,
        *,
        event_id: str | None = None,
    ) -> str:
        envelope = {"name": name, "payload": payload, "meta": meta}
        lines = []
        if event_id:
            lines.append(f"id: {event_id}")
        lines.append(f"event: {name}")
        lines.append(f"data: {_json.dumps(envelope, separators=(',', ':'))}")
        return "\n".join(lines) + "\n\n"

    def _format_trace_event(ev) -> str:
        event_id = _event_id_for(ev)
        payload = {
            "step": ev.step,
            "status": ev.status,
            "duration_ms": ev.duration_ms,
            "safe_metadata": ev.safe_metadata,
        }
        meta = {
            "run_id": run_id,
            "ts": ev.ts,
            "event_id": event_id,
            "sequence_number": getattr(ev, "sequence_number", None),
            "version": "1.0",
        }
        return _format_sse_event(
            f"run.{ev.step}", payload, meta, event_id=event_id
        )

    async def _read_events():
        if hasattr(store, "get_run_scoped"):
            return await asyncio.to_thread(store.get_run_scoped, run_id, org_id)
        return await asyncio.to_thread(store.get_run, run_id)

    async def _read_status():
        async with AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db, org_id)
            return await get_run_status(db, run_id=run_id)

    resume_recovery_seconds = time.monotonic() - request_started_at

    async def _event_stream():
        """Replay then tail an append-only trace until its Run is terminal."""
        import time as _time

        emitted_count = resume_index
        current_events = events
        current_row = sse_row
        first_pass = True
        last_output_at = _time.monotonic()
        stream_started_at = _time.monotonic()
        close_reason = "other"
        _SSE_METRICS.stream_started(
            resumed=bool(last_event_id),
            recovery_seconds=(resume_recovery_seconds if last_event_id else None),
        )

        try:
            while True:
                if await request.is_disconnected():
                    close_reason = "client_disconnected"
                    _log.info("sse.disconnected run_id=%s", run_id)
                    return

                if not first_pass:
                    # Status and trace are separate durable records. If status
                    # turns terminal between the two reads, the terminal branch
                    # below performs one final trace refresh before closing.
                    current_events = await _read_events()
                    current_row = await _read_status()
                first_pass = False

                # Ownership/visibility can change while a long stream is open.
                # Once response headers are sent we cannot return a fresh 404,
                # so fail closed by ending the connection without another event.
                if current_row is None:
                    close_reason = "run_missing"
                    _log.warning("sse.closed missing_run run_id=%s", run_id)
                    return
                if (
                    current_row.organization_id is not None
                    and org_id is not None
                    and current_row.organization_id != org_id
                ):
                    close_reason = "org_changed"
                    _log.warning(
                        "sse.closed org_changed run_id=%s token_org=%s row_org=%s",
                        run_id, org_id, current_row.organization_id,
                    )
                    return
                if not is_tenant_visible(
                    getattr(current_row, "tenancy_classification", None)
                ):
                    close_reason = "visibility_changed"
                    _log.warning(
                        "sse.closed visibility_changed run_id=%s classification=%s",
                        run_id,
                        getattr(current_row, "tenancy_classification", None),
                    )
                    return

                # Both stores are append-only and return insertion order, so the
                # emitted prefix length is a stable incremental cursor.
                for ev in current_events[emitted_count:]:
                    _SSE_METRICS.event_emitted()
                    yield _format_trace_event(ev)
                    emitted_count += 1
                    last_output_at = _time.monotonic()

                if RunStatus.is_terminal(current_row.status):
                    # Close the trace/status commit race with one last read.
                    final_events = await _read_events()
                    for ev in final_events[emitted_count:]:
                        _SSE_METRICS.event_emitted()
                        yield _format_trace_event(ev)
                        emitted_count += 1
                    _SSE_METRICS.event_emitted()
                    yield _format_sse_event("stream.completed", {
                        "run_id": run_id,
                        "status": current_row.status,
                        "event_count": emitted_count,
                    }, {
                        "run_id": run_id,
                        "version": "1.0",
                    })
                    close_reason = "terminal"
                    return

                now = _time.monotonic()
                if now - last_output_at >= _SSE_HEARTBEAT_INTERVAL_SECONDS:
                    _SSE_METRICS.heartbeat_emitted()
                    yield ": keepalive\n\n"
                    last_output_at = now

                await asyncio.sleep(_SSE_POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            close_reason = "cancelled"
            raise
        except Exception:
            close_reason = "stream_error"
            raise
        finally:
            _SSE_METRICS.stream_closed(
                reason=close_reason,
                duration_seconds=_time.monotonic() - stream_started_at,
            )

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
            "Connection": "keep-alive",
            "X-iCoDer-Trace-Retention-Days": str(_trace_retention_days()),
            "X-iCoDer-SSE-Resumed": "true" if last_event_id else "false",
        },
    )
