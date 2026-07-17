"""POST /api/v1/agents/{agent_id}/run — unified Agent Run API.

Phase 4-F (2026-07-09): a single facade endpoint that routes any iCoDer
built agent to its appropriate runtime, with a uniform response envelope
consumed by the Agent Detail chat UI (per prompt §9.1 + §9.4).

Routing (per architecture validated by Plan agent — no new dispatcher
class, reuse existing infrastructure):

  1. ``medical-coding-agent`` (any runtime_mode in {corti_like_fast,
     medcoder_deep}) → ``CodingRuntimeDispatcher`` (G001 fast path or
     5-stage MedCodER pipeline).
  2. Any other agent → ``ProviderRegistry.resolve_from_agent_pack()``
     returns the registered backend (PureLLMProvider /
     LLMWithToolsProvider / RuleEngineProvider) — provider.invoke() is
     called with a ``BackendRequest`` + ``AgentRunContext`` built from
     the agent_pack.json.

Failure contract (prompt §9.4): on any error — unknown agent_id,
missing LLM credential, runtime crash, timeout — returns HTTP 200 with
``error=True`` + ``error_reason`` + user-visible ``summary``. Never
raises to the caller, never silently times out.

This endpoint does NOT replace the A2A mainline
(``POST /api/icoder/agents/{id}/v1/message:send``) — agents with rich
A2A orchestration (Planner/Delegator/Aggregator state machine) continue
to be reachable via A2A. This endpoint is the Corti-style "Run"
facade: simpler response shape, easier for the Agent Detail chat UI to
render uniformly across all 8 iCoDer built agents.
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.coding_runtime import (
    CodingRequest,
    CodingResult,
    RuntimeMode,
    get_dispatcher,
)
from app.database import get_db
from app.icoder.agent_runtime.a2a_facade import (
    MEDICAL_CODING_AGENT_IDS as _FACADE_MEDICAL_CODING_AGENT_IDS,
    construct_envelope,
    dispatch_medical_coding_fast,
    persist_trace_events,
)
from app.middleware.auth import get_current_user, get_current_organization, get_current_user_or_oauth_client
from app.models.organization import Organization
from app.models.user import User
from app.services.idempotency_service import (
    IdempotencyKeyReusedError,
    acquire_or_replay,
    compute_request_hash,
    mark_completed,
    mark_failed,
    mark_in_progress,
)
from icoder_runtime.backends.contracts import (
    AgentRunContext,
    BackendRequest,
    BackendResponse,
)
from icoder_runtime.backends.registry import (
    ProviderNotRegisteredError,
    get_default_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agent-run"])


# ── Pack discovery (mirrors icoder_agents_hub._load_packs but filtered) ──

_REPO_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_AGENTS_DIR = _REPO_ROOT / "official_agents"


def _load_pack_by_agent_id(agent_id: str) -> dict[str, Any] | None:
    """Find the agent_pack.json whose short agent_id matches.

    ``agent_id`` is the URL-safe short form derived from ``agent_ref``
    (e.g. ``"medical-coding-agent"`` ← ``"icoder/medical-coding-agent@2.0.0"``).
    Returns the raw pack dict, or None if no match.
    """
    if not OFFICIAL_AGENTS_DIR.exists():
        return None
    import json

    for path in sorted(OFFICIAL_AGENTS_DIR.rglob("agent_pack.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                pack = json.load(f)
        except Exception:
            continue
        ref = pack.get("agent_ref", "")
        if _agent_id_from_ref(ref) == agent_id:
            return pack
    return None


def _agent_id_from_ref(agent_ref: str) -> str:
    """``icoder/medical-coding-agent@2.0.0`` → ``medical-coding-agent``."""
    if not agent_ref:
        return ""
    tail = agent_ref.split("/")[-1]
    return tail.split("@")[0]


# Phase 5 Track C Gate 1: contract derivation for StructuredOutputProjector.
_AGENT_CONTRACT_MAP: dict[str, str] = {
    "note-completeness-agent": "icoder/NoteCompleteness/v1",
    "compliance-guardrail-agent": "icoder/ComplianceGuardrail/v1",
    "procedure-extractor": "icoder/ProcedureExtractor/v1",
    "evidence-extractor": "icoder/EvidenceExtractor/v1",
    "principal-diagnosis-review": "icoder/PrincipalDxReview/v1",
    "discharge-summary-structuring": "icoder/DischargeSummary/v1",
    "drg-analyzer": "icoder/DrgAnalyzer/v1",
    "code-validation-agent": "icoder/CodeValidation/v1",
}


def _derive_contract(agent_id: str, backend_provider: str) -> str:
    """Derive the StructuredOutputProjector contract name.

    Medical-coding-agent uses HybridCodingAdapter (not PureLLM), so it
    returns "" and skips projection (its structured output is already
    populated by HybridCodingAdapter's MedicalCodingOutputSchema).
    """
    return _AGENT_CONTRACT_MAP.get(agent_id, "")


# ── Request / Response models ───────────────────────────────────────────


class AgentRunRequestInput(BaseModel):
    """Agent run input — ``text`` is the universal field.

    Other agent-specific input fields can be passed via the dict-like
    shape (e.g. ``{"text": "...", "codes": ["I50.9"]}`` for Coding
    Evidence agent).
    """

    text: str = Field(..., min_length=1, max_length=32000,
                      description="Clinical encounter text (Chinese or English).")
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-specific extra input fields (codes, context, etc.).",
    )


class AgentRunRequest(BaseModel):
    """POST /api/v1/agents/{agent_id}/run request body (prompt §9.1)."""

    input: AgentRunRequestInput
    runtime_mode: str | None = Field(
        None,
        description=(
            "Override the agent's default_runtime_mode. For medical-coding-agent: "
            "'corti_like_fast' (default, ~9s) or 'medcoder_deep' (5-stage, 30-60s+). "
            "Other agents ignore this field (their backend_provider determines runtime)."
        ),
    )
    api_client_id: str | None = Field(
        None,
        description="Optional API Client ID for usage attribution (placeholder).",
    )
    include_trace: bool = Field(
        True,
        description="Whether to include trace_events in the response.",
    )
    include_evidence: bool = Field(
        True,
        description="Whether to include evidence[] in the response.",
    )


class AgentRunResponse(BaseModel):
    """POST /api/v1/agents/{agent_id}/run response body (prompt §9.1)."""

    agent_id: str
    run_id: str
    trace_id: str = ""
    trace_url: str = Field(
        default="",
        description=(
            "Phase 6 Gate 5: frontend deep-link to the RunTrace viewer "
            "(/ai-studio/runs/{run_id}/trace). Embedded widgets surface this "
            "in the run.completed event payload so consumers can open the "
            "trace in a new tab. Empty when run_id is empty."
        ),
    )
    runtime_mode: str = ""
    latency_ms: int = 0
    cost: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    manual_review_required: bool = False
    trace_events: list[dict[str, Any]] = Field(default_factory=list)
    error: bool = False
    error_reason: str = ""


def _trace_url_for(
    run_id: str,
    *,
    organization_id: Optional[str] = None,
    api_client_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """Phase 6 Gate 5 / Phase 7 Gate 7 — RunTrace deep-link.

    Two modes:

    - **Console mode** (no ``organization_id`` / ``api_client_id``):
      Returns the frontend route ``/ai-studio/runs/{run_id}/trace``
      relative to baseURL. The Console SPA authenticates via JWT.

    - **Partner mode** (``organization_id`` or ``api_client_id`` set):
      Returns a full signed URL of the form::

          {base_url}/api/v1/runs/{run_id}/trace?token=<signed>

      The token is HMAC-signed (24h TTL) and bound to run_id +
      organization_id. Partners can deep-link without a Console JWT.

    Phase 7 §12: the signed partner URL is required so partners
    receive a clickable trace link they can share with their clinical
    reviewers without requiring those reviewers to log into iCoDer.
    """
    if not run_id:
        return ""
    if organization_id or api_client_id:
        from app.services.trace_token import build_trace_url
        return build_trace_url(
            base_url or "",
            run_id=run_id,
            organization_id=organization_id,
            api_client_id=api_client_id,
        )
    return f"/ai-studio/runs/{run_id}/trace"


# ── Endpoint ────────────────────────────────────────────────────────────

# Agent IDs that route to the CodingRuntimeDispatcher (G001 fast path).
_MEDICAL_CODING_AGENT_IDS: frozenset[str] = frozenset({
    "medical-coding-agent",
    "medcoder-coding-review-agent",
})


@router.post(
    "/{agent_id}/run",
    operation_id="agent_run_v1",
    response_model=AgentRunResponse,
)
async def run_agent(
    agent_id: str,
    body: AgentRunRequest,
    request: Request,
    principal: tuple = Depends(get_current_user_or_oauth_client),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AgentRunResponse:
    """Unified Agent Run facade (A2A-compatible, Phase 4-F2).

    Constructs an A2A-compatible envelope (InboundRequest with TextPart +
    metadata.runtime_mode), then dispatches through the shared A2A facade
    to the appropriate runtime (CodingRuntimeDispatcher for medical coding,
    ProviderRegistry for everything else). After the run, persists
    trace_events to RunTraceStore so the dedicated RunTrace page works.

    Phase 7 Gate 3 §8: server-side Idempotency-Key dedup. If the client
    sends an `Idempotency-Key` header, the server checks the
    `idempotency_records` table:
    - First request → run normally, save snapshot on completion.
    - Replay (same key + same hash + COMPLETED) → return saved snapshot.
    - Replay (same key + same hash + IN_PROGRESS) → return run_id + 200.
    - Mismatch (same key + different hash) → 409.

    On any error, returns HTTP 200 with ``error=True`` so the frontend
    can render a friendly retry UI (rather than catching a 5xx).
    """
    t0 = time.perf_counter()
    # Phase 7 Gate 12 — hybrid auth: principal is (user, client), exactly one set.
    current_user, current_client = principal
    api_client_id: Optional[str] = None
    if current_client is not None:
        # Partner client_credentials flow — synthesize identity from the client.
        user_id = current_client.get("client_id") or ""
        tenant_id = ""
        org_id = current_client.get("org_id") or ""
        api_client_id = current_client.get("client_id")
    else:
        user_id = str(getattr(current_user, "id", "") or "")
        tenant_id = str(getattr(current_user, "tenant_id", "") or "")
        org_id = str(getattr(current_org, "id", "") or "") or tenant_id

    # ── Phase 7 Gate 3: server-side idempotency check ───────────────
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
    dedup_record = None
    if idempotency_key:
        request_hash = compute_request_hash(
            agent_id=agent_id,
            input_text=body.input.text,
            runtime_mode=body.runtime_mode or "",
            extra=body.input.extra,
        )
        dedup_result = await acquire_or_replay(
            db,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            agent_ref=agent_id,
            organization_id=org_id or None,
            api_client_id=api_client_id,
        )
        if not dedup_result.should_run:
            if dedup_result.in_progress:
                # Same key still running — return run_id + 200 status.
                # Per §8.2: "返回相同 run_id, status = IN_PROGRESS"
                return AgentRunResponse(
                    agent_id=agent_id,
                    run_id=dedup_result.record.run_id or "",
                    trace_id="",
                    trace_url=_trace_url_for(dedup_result.record.run_id or ""),
                    runtime_mode=body.runtime_mode or "",
                    summary="(in progress)",
                    error=False,
                    error_reason="",
                )
            # COMPLETED — return the saved snapshot verbatim.
            snapshot = dedup_result.response_snapshot or {}
            await db.commit()
            return AgentRunResponse(**snapshot)
        dedup_record = dedup_result.record

    # ── Phase 4-F2 §4.1: construct A2A-compatible envelope ──────────
    # The envelope preserves A2A protocol semantics (run_id, trace_id,
    # context_id, message_id, parts, metadata) even when the dispatch
    # is a lightweight CodingRuntimeDispatcher call rather than the full
    # InboundHandler 5-stage state machine (§6.1 lightweight adapter).
    envelope, run_id, trace_id, context_id, message_id = construct_envelope(
        agent_id=agent_id,
        input_text=body.input.text,
        extra=body.input.extra or None,
        runtime_mode=body.runtime_mode,
        include_trace=body.include_trace,
        include_evidence=body.include_evidence,
        user_id=user_id,
        tenant_id=tenant_id,
    )
    logger.info(
        "agent_run: A2A envelope constructed agent_id=%s run_id=%s "
        "trace_id=%s runtime_mode=%s context_id=%s",
        agent_id, run_id, trace_id,
        body.runtime_mode or "(default)", context_id,
    )

    # ── Phase 7 Gate 3: bind run_id to the dedup record ─────────────
    if dedup_record is not None:
        try:
            await mark_in_progress(db, dedup_record, run_id=run_id)
            await db.commit()
        except Exception as e:
            logger.warning(
                "agent_run: idempotency mark_in_progress failed (run_id=%s): %s",
                run_id, e,
            )

    # ── Phase 7 Gate 4 §9.3: write a PENDING row so partners can poll ─
    # POST /api/v1/runs/{run_id}/cancel and GET /api/v1/runs/{run_id}
    # work mid-run. The row is finalized to COMPLETED/FAILED at the end.
    #
    # Phase 7 Gate 5 §10.1: capture partner attribution (api_client_id,
    # session_id, context_id, request_id, idempotency_key) so every
    # Embedded Run can be attributed to a partner + patient context.
    try:
        from app.services.run_lifecycle import record_run_start, RunStatus, set_status
        # request_id: prefer X-Request-Id header, fall back to trace_id.
        request_id_hdr = (request.headers.get("X-Request-Id") or "").strip() or None
        # session_id: read from body.input.extra (set by Phase 6 widget).
        extra = body.input.extra or {}
        session_id = (extra.get("sessionId") or extra.get("session_id") or "") or None
        await record_run_start(
            db,
            run_id=run_id,
            agent_id=agent_id,
            user_id=user_id,
            organization_id=org_id or None,
            input_text=body.input.text,
            runtime_mode=body.runtime_mode or "",
            trace_id=trace_id,
            # §10.1 attribution
            api_client_id=(body.api_client_id or "") or None,
            embedded_app_id=(extra.get("embeddedAppId") or extra.get("embedded_app_id") or "") or None,
            session_id=session_id,
            context_id=context_id,
            request_id=request_id_hdr,
            idempotency_key=idempotency_key or None,
        )
        # Promote PENDING → RUNNING now that the run is about to start.
        await set_status(db, run_id=run_id, status=RunStatus.RUNNING)
        await db.commit()
    except Exception as e:
        logger.warning(
            "agent_run: run_lifecycle record_run_start failed (run_id=%s): %s",
            run_id, e,
        )

    # ── 1. Medical coding fast path (G001) ──────────────────────────
    if agent_id in _MEDICAL_CODING_AGENT_IDS:
        response = await _run_medical_coding(
            agent_id=agent_id,
            body=body,
            run_id=run_id,
            trace_id=trace_id,
            context_id=context_id,
            t0=t0,
            user_id=user_id,
            tenant_id=tenant_id,
        )
    else:
        # ── 2. Generic provider path ───────────────────────────────
        response = await _run_via_provider_registry(
            agent_id=agent_id,
            body=body,
            run_id=run_id,
            trace_id=trace_id,
            context_id=context_id,
            t0=t0,
            current_user=current_user,
            request=request,
        )

    # ── Phase 4-F2 §4.3: persist trace_events to RunTraceStore ──────
    # So GET /api/runtime/runs/{run_id}/trace works for unified runs.
    if response.trace_events and not response.error:
        persist_trace_events(
            run_id=response.run_id or run_id,
            trace_events=response.trace_events,
            agent_id=agent_id,
            runtime_mode=response.runtime_mode,
            trace_id=response.trace_id or trace_id,
        )

    # ── Phase 4-G #3: persist run summary to run_history table ──────
    # So AgentChatPage can hydrate a history dropdown on page load.
    # Failures here are non-fatal — the run already succeeded; we just
    # log so a broken DB doesn't break the user's chat experience.
    try:
        await _persist_run_history(
            db,
            response=response,
            input_text=body.input.text,
            user_id=user_id,
            tenant_id=tenant_id,
            organization_id=org_id or None,
        )
    except Exception as e:
        logger.warning(
            "agent_run: run_history persist failed (run_id=%s): %s",
            response.run_id or run_id, e,
        )

    # ── Phase 7 Gate 3: persist completed/failed snapshot ───────────
    # COMPLETED → mark_completed so the next replay returns this snapshot
    #   verbatim (Phase 7 §8.2). FAILED → mark_failed so the next replay
    #   re-runs rather than replaying a stale error. Non-fatal: if the
    #   snapshot write fails, the partner just loses dedup-replay — the
    #   run itself already succeeded.
    if dedup_record is not None:
        try:
            if getattr(response, "error", False):
                await mark_failed(db, dedup_record)
            else:
                await mark_completed(
                    db,
                    dedup_record,
                    response_snapshot=response.model_dump(),
                )
            await db.commit()
        except Exception as e:
            logger.warning(
                "agent_run: idempotency mark_completed/failed failed (run_id=%s): %s",
                response.run_id or run_id, e,
            )

    # ── Phase 7 Gate 7 §12: upgrade trace_url to a signed partner URL ──
    # The internal helpers (_run_medical_coding / _run_via_provider_registry)
    # return a relative Console trace_url. For partner runs (invoked via
    # client_credentials token), we replace it with a signed URL that grants
    # read-only access without a Console JWT.
    #
    # Phase 7 Gate 12 narrowing: previously this fired whenever org_id was
    # truthy, but Console users also carry an org_id — so every Console-
    # mode request got a partner URL. Now we fire only when the request
    # actually came through the partner auth path (api_client_id set on
    # the principal or explicitly in the body).
    is_partner_run = current_client is not None or bool(body.api_client_id)
    if response.run_id and is_partner_run:
        try:
            signed = _trace_url_for(
                response.run_id,
                organization_id=org_id or None,
                api_client_id=(body.api_client_id or (current_client or {}).get("client_id") or "") or None,
                base_url=str(request.base_url),
            )
            if signed:
                response.trace_url = signed
        except Exception as e:
            logger.warning(
                "agent_run: trace_url sign failed (run_id=%s): %s",
                response.run_id, e,
            )

    return response


async def _persist_run_history(
    db: AsyncSession,
    *,
    response: AgentRunResponse,
    input_text: str,
    user_id: str = "",
    tenant_id: str = "",
    organization_id: Optional[str] = None,
) -> None:
    """Upsert the run_history row for this run_id.

    Phase 7 Gate 4: switched from INSERT to UPDATE-or-INSERT so the
    lifecycle (PENDING → RUNNING → COMPLETED/FAILED) works. The
    PENDING row was written by ``record_run_start`` at envelope
    construction time; this call finalizes it.

    Writes status = COMPLETED or FAILED depending on response.error.
    Other terminal states (CANCELLED, CLIENT_ABORTED, etc.) are set
    by ``run_lifecycle`` helpers and are NOT overwritten here —
    once a row is terminal, the final persist becomes a no-op for
    the status column.
    """
    from sqlalchemy import select
    from app.models.run_history import RunHistoryModel
    from app.services.run_lifecycle import RunStatus

    cost_amount = 0.0
    if isinstance(response.cost, dict):
        try:
            cost_amount = float(response.cost.get("amount") or 0.0)
        except (TypeError, ValueError):
            cost_amount = 0.0

    final_status = RunStatus.FAILED if response.error else RunStatus.COMPLETED

    # Look up the existing row (PENDING / RUNNING from record_run_start).
    stmt = select(RunHistoryModel).where(RunHistoryModel.run_id == response.run_id)
    result = await db.execute(stmt)
    row = result.scalars().one_or_none()

    if row is None:
        # No PENDING row was written (legacy path or row was deleted).
        # INSERT with all fields. Use COMPLETED/FAILED directly.
        row = RunHistoryModel(
            id=_generate_row_id(),
            organization_id=organization_id or tenant_id or None,
            user_id=user_id or None,
            agent_id=response.agent_id,
            run_id=response.run_id,
            trace_id=response.trace_id,
            runtime_mode=response.runtime_mode,
            latency_ms=response.latency_ms,
            cost_usd=cost_amount,
            input_text=(input_text or "")[:4096],
            output_summary=(response.summary or "")[:4096],
            error=bool(response.error),
            error_reason=response.error_reason or None,
            status=final_status,
        )
        db.add(row)
    else:
        # Don't downgrade a terminal cancel-state to COMPLETED — if
        # the row is already CANCELLED / CLIENT_ABORTED, keep it.
        from app.services.run_lifecycle import RunStatus as _RS
        if _RS.is_terminal(row.status) and row.status not in (
            _RS.COMPLETED, _RS.FAILED, _RS.COMPLETED_AFTER_CLIENT_ABORT,
        ):
            # Cancel-kind terminal: keep status, just fill in cost/latency.
            pass
        else:
            row.status = final_status
        row.trace_id = row.trace_id or response.trace_id
        row.runtime_mode = row.runtime_mode or response.runtime_mode
        row.latency_ms = response.latency_ms
        row.cost_usd = cost_amount
        row.input_text = row.input_text or (input_text or "")[:4096]
        row.output_summary = (response.summary or "")[:4096]
        row.error = bool(response.error)
        row.error_reason = response.error_reason or None
    await db.flush()


def _generate_row_id() -> str:
    """12-char ID matching the rest of the iCoDer schema (e.g. run_trace_events.id)."""
    import secrets
    return secrets.token_hex(6)


# ── Medical coding path ─────────────────────────────────────────────────


async def _run_medical_coding(
    *,
    agent_id: str,
    body: AgentRunRequest,
    run_id: str,
    trace_id: str,
    context_id: str,
    t0: float,
    user_id: str = "",
    tenant_id: str = "",
) -> AgentRunResponse:
    """Delegate to CodingRuntimeDispatcher via the shared A2A facade.

    Phase 4-F2: uses ``a2a_facade.dispatch_medical_coding_fast()`` so the
    unified endpoint and the A2A ``message:send`` path share one dispatch
    code path. Default mode is ``corti_like_fast`` (~6-8s); explicit
    ``medcoder_deep`` opts into the 5-stage MedCODER pipeline.
    """
    try:
        result, out_run_id, out_trace_id = await dispatch_medical_coding_fast(
            agent_id=agent_id,
            input_text=body.input.text,
            extra=body.input.extra or None,
            runtime_mode=body.runtime_mode,
            include_trace=body.include_trace,
            include_evidence=body.include_evidence,
            run_id=run_id,
            trace_id=trace_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
    except Exception as e:
        logger.exception(
            "agent_run: medical-coding dispatcher failed for agent_id=%s",
            agent_id,
        )
        mode_str = body.runtime_mode or "corti_like_fast"
        return _error_response(
            agent_id=agent_id,
            run_id=run_id,
            trace_id=trace_id,
            runtime_mode=mode_str,
            t0=t0,
            error_reason="runtime_crash",
            summary=f"Medical coding runtime crashed: {type(e).__name__}: {e}",
        )

    return _map_coding_result(
        agent_id=agent_id,
        run_id=out_run_id,
        trace_id=out_trace_id,
        result=result,
        include_trace=body.include_trace,
        include_evidence=body.include_evidence,
        t0=t0,
    )


def _map_coding_result(
    *,
    agent_id: str,
    run_id: str,
    trace_id: str,
    result: CodingResult,
    include_trace: bool,
    include_evidence: bool,
    t0: float,
) -> AgentRunResponse:
    """Project a CodingResult into the unified AgentRunResponse envelope."""
    # Prefer result.trace_id/run_id if the runtime populated them; else
    # fall back to the API-layer IDs.
    out_trace_id = result.trace_id or trace_id
    out_run_id = result.run_id or run_id

    # Evidence: pull per-code evidence into a flat list (one entry per
    # non-empty evidence string) so the frontend can render uniformly.
    evidence: list[dict[str, Any]] = []
    if include_evidence:
        for c in result.codes:
            if c.evidence:
                evidence.append({
                    "code": c.code,
                    "system": c.system,
                    "type": c.type,
                    "text": c.evidence,
                    "rationale": c.rationale,
                })

    # Warnings: flat list of per-code warnings.
    warnings: list[str] = []
    for c in result.codes:
        warnings.extend(c.warnings)

    # result: full CodingResult payload (codes[], raw_schema, etc.).
    result_payload = {
        "codes": [
            {
                "code": c.code,
                "system": c.system,
                "display": c.display,
                "type": c.type,
                "confidence": c.confidence,
                "evidence": c.evidence if include_evidence else "",
                "rationale": c.rationale,
                "warnings": list(c.warnings),
                "alternatives": list(c.alternatives),
            }
            for c in result.codes
        ],
        "raw_schema": dict(result.raw_schema) if result.raw_schema else {},
        "llm_provider": result.llm_provider,
    }

    trace_events = list(result.trace_events) if include_trace else []

    # If runtime reported an error, surface it in the envelope.
    if result.error:
        return AgentRunResponse(
            agent_id=agent_id,
            run_id=out_run_id,
            trace_id=out_trace_id,
            trace_url=_trace_url_for(out_run_id),
            runtime_mode=result.runtime_mode,
            latency_ms=result.latency_ms or int((time.perf_counter() - t0) * 1000),
            cost=dict(result.cost),
            summary=result.summary,
            result=result_payload,
            evidence=evidence,
            warnings=warnings,
            manual_review_required=True,  # medical coding always requires human review
            trace_events=trace_events,
            error=True,
            error_reason=result.error_reason or "runtime_error",
        )

    return AgentRunResponse(
        agent_id=agent_id,
        run_id=out_run_id,
        trace_id=out_trace_id,
        trace_url=_trace_url_for(out_run_id),
        runtime_mode=result.runtime_mode,
        latency_ms=result.latency_ms or int((time.perf_counter() - t0) * 1000),
        cost=dict(result.cost),
        summary=result.summary,
        result=result_payload,
        evidence=evidence,
        warnings=warnings,
        manual_review_required=True,  # medical coding always requires human review
        trace_events=trace_events,
        error=False,
        error_reason="",
    )


# ── Generic provider path ───────────────────────────────────────────────


async def _run_via_provider_registry(
    *,
    agent_id: str,
    body: AgentRunRequest,
    run_id: str,
    trace_id: str,
    context_id: str,
    t0: float,
    current_user: Optional[User],
    request: Request | None = None,
) -> AgentRunResponse:
    """Resolve the agent's backend_provider and call invoke()."""
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        RunTraceStep,
        RunTraceStatus,
        emit_trace_event,
    )

    # Emit USER_MESSAGE_RECEIVED so /runs/{run_id}/trace has content.
    emit_trace_event(
        run_id, RunTraceStep.USER_MESSAGE_RECEIVED,
        safe_metadata={
            "agent_id": agent_id,
            "input_text_len": len(body.input.text),
            "runtime_mode": body.runtime_mode or "",
            "context_id": context_id,
            "trace_id": trace_id,
            "api_client_id": body.api_client_id or "",
        },
    )

    # Load agent_pack.json by agent_id.
    pack = _load_pack_by_agent_id(agent_id)
    if pack is None:
        emit_trace_event(
            run_id, RunTraceStep.COMPLETION,
            status=RunTraceStatus.FAILED,
            safe_metadata={"error": f"unknown_agent: {agent_id}"},
        )
        return _error_response(
            agent_id=agent_id,
            run_id=run_id,
            trace_id=trace_id,
            runtime_mode=body.runtime_mode or "",
            t0=t0,
            error_reason="unknown_agent",
            summary=f"Unknown agent_id: {agent_id!r}. No matching agent_pack.json found.",
        )

    # Resolve provider via ProviderRegistry.
    registry = get_default_registry()
    try:
        provider = registry.resolve_from_agent_pack(pack)
    except ProviderNotRegisteredError as e:
        emit_trace_event(
            run_id, RunTraceStep.COMPLETION,
            status=RunTraceStatus.FAILED,
            safe_metadata={"error": f"provider_not_registered: {e}"},
        )
        return _error_response(
            agent_id=agent_id,
            run_id=run_id,
            trace_id=trace_id,
            runtime_mode=body.runtime_mode or pack.get("default_runtime_mode", ""),
            t0=t0,
            error_reason="provider_not_registered",
            summary=f"Backend provider not registered for agent {agent_id!r}: {e}",
        )

    # Build BackendRequest + AgentRunContext.
    system_prompt = pack.get("system_prompt", "") or ""
    backend_config = registry.get_backend_config(pack)
    req = BackendRequest(
        input={"text": body.input.text, **body.input.extra},
        system_prompt=system_prompt,
        user_input=body.input.text,
        tool_scope=list((backend_config.get("tools") or {}).get("scope") or []),
        mandatory_tools=list((backend_config.get("tools") or {}).get("mandatory") or []),
        forbidden_tools=list((backend_config.get("tools") or {}).get("forbidden") or []),
        placeholder_values=dict(backend_config.get("placeholder_values") or {}),
        timeout_seconds=float(backend_config.get("timeout_seconds", 60.0)),
    )

    ctx = AgentRunContext(
        run_id=run_id,
        context_id=context_id or str(uuid.uuid4()),
        agent_id=agent_id,
        tenant_id=str(getattr(current_user, "tenant_id", "") or "default"),
        redacted_input=body.input.text,  # PHI redaction happens inside provider
        agent_pack=pack,
        backend_config=backend_config,
    )

    # Determine runtime_mode label for the response.
    runtime_mode_label = (
        body.runtime_mode
        or pack.get("default_runtime_mode")
        or getattr(provider, "backend_type", "")
    )

    try:
        resp: BackendResponse = await provider.invoke(req, ctx, request=request)
    except Exception as e:
        logger.exception(
            "agent_run: provider.invoke failed for agent_id=%s provider=%s",
            agent_id, getattr(provider, "provider_id", "?"),
        )
        emit_trace_event(
            run_id, RunTraceStep.COMPLETION,
            status=RunTraceStatus.FAILED,
            safe_metadata={
                "agent_id": agent_id,
                "error": f"runtime_crash: {type(e).__name__}: {str(e)[:200]}",
            },
        )
        return _error_response(
            agent_id=agent_id,
            run_id=run_id,
            trace_id=trace_id,
            runtime_mode=runtime_mode_label,
            t0=t0,
            error_reason="runtime_crash",
            summary=f"Provider invoke crashed: {type(e).__name__}: {e}",
        )

    # Trace events for the success path are emitted by persist_trace_events()
    # at the unified-endpoint handler (line ~255), which re-emits the inline
    # trace_events built by _map_backend_response(). We deliberately do NOT
    # emit OUTPUT_GENERATED/COMPLETION directly here — that would double-count
    # (BUG-12-01). The USER_MESSAGE_RECEIVED emit above (line 538) is the
    # only direct emit on the success path because it happens before invoke()
    # and is not re-emitted by persist_trace_events (the inline trace_events
    # in _map_backend_response omits user_message_received for this reason).

    return _map_backend_response(
        agent_id=agent_id,
        run_id=run_id,
        trace_id=trace_id,
        runtime_mode=runtime_mode_label,
        resp=resp,
        include_trace=body.include_trace,
        include_evidence=body.include_evidence,
        api_client_id=body.api_client_id or "",
        t0=t0,
    )


def _map_backend_response(
    *,
    agent_id: str,
    run_id: str,
    trace_id: str,
    runtime_mode: str,
    resp: BackendResponse,
    include_trace: bool,
    include_evidence: bool,
    api_client_id: str = "",
    t0: float,
) -> AgentRunResponse:
    """Project a BackendResponse into the unified AgentRunResponse envelope."""
    # Pull evidence from the response's evidence_refs + per-issue evidence.
    evidence: list[dict[str, Any]] = []
    if include_evidence:
        for ref in resp.evidence_refs:
            evidence.append({"text": ref})
        for issue in resp.issues:
            for ev in issue.evidence:
                evidence.append({
                    "code": issue.code,
                    "severity": issue.severity,
                    "text": ev,
                })

    warnings: list[str] = []
    for issue in resp.issues:
        if issue.severity in ("warning", "error", "critical"):
            warnings.append(f"[{issue.code}] {issue.message}")

    result_payload = {
        "status": resp.status,
        "markdown": resp.markdown,
        "issues": [issue.model_dump() for issue in resp.issues],
        "corrected_draft": resp.corrected_draft,
        "risk_flags": list(resp.risk_flags),
        "tool_calls": [tc.model_dump() for tc in resp.tool_calls],
        "finish_state": resp.finish_state,
        "finish_reason": resp.finish_reason,
        "backend_provider": resp.backend_provider,
        "backend_type": resp.backend_type,
        "raw_provider_response": dict(resp.raw_provider_response),
    }

    # Phase 5 Track C Gate 1: StructuredOutputProjector.
    # Closes B-2 P1 gap "unified API 不解析 JSON-in-markdown" for the 8
    # PureLLM agents (note-completeness, compliance-guardrail, procedure,
    # evidence, principal-dx, discharge, drg, code-validation). When the
    # provider emitted markdown only, project structured fields from the
    # markdown so the unified /api/v1/agents/{id}/run response is
    # directly consumable (no client-side JSON-in-markdown parsing).
    try:
        from icoder_runtime.backends.structured_output_projector import (
            project as _project_structured,
        )
        # Normalize agent_id — _map_backend_response may receive either
        # short id ("drg-analyzer") or full ref ("icoder/drg-analyzer@1.0.0").
        short_agent_id = _agent_id_from_ref(agent_id)
        contract = _derive_contract(short_agent_id, resp.backend_provider)
        logger.info(
            "StructuredOutputProjector: agent_id=%s short=%s contract=%s md_len=%d",
            agent_id, short_agent_id, contract, len(resp.markdown or ""),
        )
        if contract and resp.markdown:
            projection = _project_structured(
                markdown=resp.markdown,
                contract=contract,
                agent_id=short_agent_id,
            )
            logger.info(
                "StructuredOutputProjector: result_keys=%s method=%s warnings=%s",
                list(projection.result.keys()), projection.extraction_method,
                projection.parse_warnings,
            )
            if projection.result:
                for key, value in projection.result.items():
                    result_payload.setdefault(key, value)
                result_payload["structured_extraction"] = {
                    "contract": contract,
                    "method": projection.extraction_method,
                    "warnings": projection.parse_warnings,
                }
    except Exception as e:
        logger.warning("StructuredOutputProjector failed for %s: %s", agent_id, e)

    trace_events: list[dict[str, Any]] = []
    if include_trace:
        # Phase 4-F2 + Phase 5 A1 fix: inline trace_events carry only
        # COMPLETION. USER_MESSAGE_RECEIVED is emitted directly by
        # _run_via_provider_registry() (line 538). OUTPUT_GENERATED is
        # emitted by the provider's emit_backend_metadata_event() (with
        # rich backend metadata: provider_id, backend_type, latency,
        # tool_rounds, etc.). Re-emitting either here would double-count
        # (BUG-12-01). persist_trace_events() at the unified-endpoint
        # handler re-emits this single COMPLETION event to RunTraceStore.
        # Total for a success-path run: 3 events (USER_MESSAGE_RECEIVED
        # + OUTPUT_GENERATED + COMPLETION), each appearing exactly once.
        latency_ms_val = resp.latency_ms or int((time.perf_counter() - t0) * 1000)
        completion_status = (
            "failed"
            if (resp.finish_state == "failed" or resp.status == "fail")
            else "ok"
        )
        trace_events = [
            {
                "step": "completion",
                "status": completion_status,
                "duration_ms": latency_ms_val,
                "metadata": {
                    "agent_id": agent_id,
                    "runtime_mode": runtime_mode,
                    "latency_ms": latency_ms_val,
                },
            },
        ]

    # manual_review_required: True if status is requires_review / unclear /
    # incomplete, or if any issue severity is warning/error/critical.
    manual_review = resp.status in ("requires_review", "unclear", "incomplete")
    if not manual_review:
        manual_review = any(
            issue.severity in ("warning", "error", "critical")
            for issue in resp.issues
        )

    is_error = resp.finish_state == "failed" or resp.status == "fail"
    error_reason = resp.finish_reason or "" if is_error else ""

    return AgentRunResponse(
        agent_id=agent_id,
        run_id=run_id,
        trace_id=trace_id,
        trace_url=_trace_url_for(run_id),
        runtime_mode=runtime_mode,
        latency_ms=resp.latency_ms or int((time.perf_counter() - t0) * 1000),
        cost={"amount": resp.cost_usd or 0.0, "currency": "CNY"} if resp.cost_usd else {},
        summary=resp.summary,
        result=result_payload,
        evidence=evidence,
        warnings=warnings,
        manual_review_required=manual_review,
        trace_events=trace_events,
        error=is_error,
        error_reason=error_reason,
    )


# ── Failure contract helper ─────────────────────────────────────────────


def _error_response(
    *,
    agent_id: str,
    run_id: str,
    trace_id: str,
    runtime_mode: str,
    t0: float,
    error_reason: str,
    summary: str,
) -> AgentRunResponse:
    """Build a structured error response (prompt §9.4 — never raises)."""
    return AgentRunResponse(
        agent_id=agent_id,
        run_id=run_id,
        trace_id=trace_id,
        trace_url=_trace_url_for(run_id),
        runtime_mode=runtime_mode,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        cost={},
        summary=summary,
        result={},
        evidence=[],
        warnings=[],
        manual_review_required=False,
        trace_events=[],
        error=True,
        error_reason=error_reason,
    )


__all__ = [
    "AgentRunRequest",
    "AgentRunRequestInput",
    "AgentRunResponse",
    "router",
]
