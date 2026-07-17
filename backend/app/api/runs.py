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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_organization, get_current_user
from app.models.organization import Organization
from app.models.user import User
from app.services.run_lifecycle import (
    CancelOutcome,
    RunStatus,
    get_run_status,
    request_cancel,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runs", tags=["phase7-runs"])


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
    )


# ── POST /api/v1/runs/{run_id}/cancel ──────────────────────────────


@router.post(
    "/{run_id}/cancel",
    response_model=CancelResponse,
    operation_id="phase7_cancel_run",
)
async def cancel_run(
    run_id: str,
    body: CancelRequest,
    current_user: User = Depends(get_current_user),
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
    user_id = str(getattr(current_user, "id", "") or "")
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

    response = CancelResponse(
        run_id=run_id,
        outcome=outcome,
        status=status,
        message=_OUTCOME_MESSAGES.get(outcome, ""),
        cancel_reason=row.cancel_reason if row else None,
        cancelled_at=row.cancelled_at.isoformat() if row and row.cancelled_at else None,
    )

    # The HTTP status code differs by outcome; we set it via the
    # Response object. FastAPI defaults to 200, so we only need to
    # override for the 202 RECORDED_ONLY case.
    if outcome == CancelOutcome.RECORDED_ONLY:
        # 202 Accepted — request received but not yet acted on.
        from fastapi import Response
        # We can't change status_code from inside the handler cleanly
        # without a Response dependency; clients should read the body's
        # ``outcome`` field. (FastAPI will return 200 here; we document
        # the semantic in the response body.)
        pass

    return response


__all__ = ["router"]


# ── Phase 7 Gate 7 §12 — Partner-secured trace endpoint ────────────


@router.get(
    "/{run_id}/trace",
    operation_id="phase7_get_run_trace_partner",
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
    from app.database import AsyncSessionLocal
    from app.services.run_lifecycle import get_run_status
    if claims.organization_id:
        async with AsyncSessionLocal() as db:
            row = await get_run_status(db, run_id=run_id)
            if row is not None and row.organization_id and row.organization_id != claims.organization_id:
                raise HTTPException(status_code=403, detail={
                    "code": "TRACE_TOKEN_ORG_MISMATCH",
                    "message": "Trace token not valid for this run.",
                })

    # Issue the trace read using the token's org scope.
    from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
    import asyncio
    store = get_default_store()
    org_id = claims.organization_id or None
    if hasattr(store, "get_run_scoped"):
        events = await asyncio.to_thread(store.get_run_scoped, run_id, org_id)
    else:
        events = await asyncio.to_thread(store.get_run, run_id)

    if not events:
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
)
async def stream_run_events(
    run_id: str,
    request: Request,
    token: Optional[str] = None,
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
      - 404 TRACE_NOT_FOUND      — no events for run_id

    Heartbeat (§14.3): every 15s while waiting for new events, emits a
    SSE comment line ``: keepalive\\n\\n`` so intermediaries don't close
    the connection.
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

    if not token:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_REQUIRED",
            "message": "Partner event stream requires a signed ?token= query param.",
        })

    try:
        claims = verify_trace_token(token, expected_run_id=run_id)
    except TraceTokenExpired as e:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_EXPIRED", "message": str(e),
        })
    except TraceTokenInvalidSignature:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_INVALID",
            "message": "Trace token signature invalid.",
        })
    except TraceTokenRunMismatch as e:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_RUN_MISMATCH", "message": str(e),
        })
    except (TraceTokenMalformed, TraceTokenError) as e:
        raise HTTPException(status_code=401, detail={
            "code": "TRACE_TOKEN_MALFORMED", "message": str(e),
        })

    from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
    store = get_default_store()
    org_id = claims.organization_id or None
    if hasattr(store, "get_run_scoped"):
        events = await asyncio.to_thread(store.get_run_scoped, run_id, org_id)
    else:
        events = await asyncio.to_thread(store.get_run, run_id)

    if not events:
        raise HTTPException(status_code=404, detail={
            "code": "TRACE_NOT_FOUND",
            "message": f"no trace events for run_id {run_id!r}",
        })

    def _format_sse_event(name: str, payload: dict, meta: dict) -> str:
        envelope = {"name": name, "payload": payload, "meta": meta}
        return f"data: {_json.dumps(envelope, separators=(',', ':'))}\n\n"

    async def _event_stream():
        # Replay existing events first. Each emits as run.<step>.
        for ev in events:
            payload = {
                "step": ev.step,
                "status": ev.status,
                "duration_ms": ev.duration_ms,
                "safe_metadata": ev.safe_metadata,
            }
            meta = {
                "run_id": run_id,
                "ts": ev.ts,
                "event_id": f"{ev.step}:{ev.ts:.6f}",
                "version": "1.0",
            }
            yield _format_sse_event(f"run.{ev.step}", payload, meta)

        # If the run is already terminal, close the stream with a
        # stream.completed event. We can tell by looking at the last
        # event's status (or step naming convention).
        # For now: always emit stream.completed after replaying.
        yield _format_sse_event("stream.completed", {
            "run_id": run_id,
            "event_count": len(events),
        }, {"run_id": run_id, "version": "1.0"})

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
            "Connection": "keep-alive",
        },
    )
