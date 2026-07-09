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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.coding_runtime import (
    CodingRequest,
    CodingResult,
    RuntimeMode,
    get_dispatcher,
)
from app.middleware.auth import get_current_user
from app.models.user import User
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
    current_user: User = Depends(get_current_user),
) -> AgentRunResponse:
    """Unified Agent Run facade.

    Routes ``agent_id`` to the appropriate runtime (CodingRuntimeDispatcher
    for medical coding, ProviderRegistry for everything else) and wraps
    the response in a uniform envelope.

    On any error, returns HTTP 200 with ``error=True`` so the frontend
    can render a friendly retry UI (rather than catching a 5xx).
    """
    t0 = time.perf_counter()
    run_id = f"run-{uuid.uuid4()}"
    trace_id = f"trace-{uuid.uuid4()}"

    # ── 1. Medical coding fast path (G001) ──────────────────────────
    if agent_id in _MEDICAL_CODING_AGENT_IDS:
        return await _run_medical_coding(
            agent_id=agent_id,
            body=body,
            run_id=run_id,
            trace_id=trace_id,
            t0=t0,
            current_user=current_user,
        )

    # ── 2. Generic provider path ────────────────────────────────────
    return await _run_via_provider_registry(
        agent_id=agent_id,
        body=body,
        run_id=run_id,
        trace_id=trace_id,
        t0=t0,
        current_user=current_user,
    )


# ── Medical coding path ─────────────────────────────────────────────────


async def _run_medical_coding(
    *,
    agent_id: str,
    body: AgentRunRequest,
    run_id: str,
    trace_id: str,
    t0: float,
    current_user: User,
) -> AgentRunResponse:
    """Delegate to CodingRuntimeDispatcher (G001 fast path or medcoder_deep)."""
    # Build CodingRequest — mode overrides default if provided.
    mode_str = body.runtime_mode or "corti_like_fast"
    mode = RuntimeMode.coerce(mode_str)
    request = CodingRequest(
        text=body.input.text,
        mode=mode,
        coding_system="icd10cn",
        include_evidence=body.include_evidence,
        include_trace=body.include_trace,
        run_id=run_id,
        user_id=str(getattr(current_user, "id", "") or ""),
        tenant_id=str(getattr(current_user, "tenant_id", "") or ""),
    )

    try:
        dispatcher = get_dispatcher()
        result: CodingResult = await dispatcher.dispatch(request)
    except Exception as e:
        logger.exception(
            "agent_run: medical-coding dispatcher failed for agent_id=%s mode=%s",
            agent_id, mode.value,
        )
        return _error_response(
            agent_id=agent_id,
            run_id=run_id,
            trace_id=trace_id,
            runtime_mode=mode.value,
            t0=t0,
            error_reason="runtime_crash",
            summary=f"Medical coding runtime crashed: {type(e).__name__}: {e}",
        )

    return _map_coding_result(
        agent_id=agent_id,
        run_id=run_id,
        trace_id=trace_id,
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
    t0: float,
    current_user: User,
) -> AgentRunResponse:
    """Resolve the agent's backend_provider and call invoke()."""
    # Load agent_pack.json by agent_id.
    pack = _load_pack_by_agent_id(agent_id)
    if pack is None:
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
        context_id=str(uuid.uuid4()),
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
        resp: BackendResponse = await provider.invoke(req, ctx)
    except Exception as e:
        logger.exception(
            "agent_run: provider.invoke failed for agent_id=%s provider=%s",
            agent_id, getattr(provider, "provider_id", "?"),
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

    return _map_backend_response(
        agent_id=agent_id,
        run_id=run_id,
        trace_id=trace_id,
        runtime_mode=runtime_mode_label,
        resp=resp,
        include_trace=body.include_trace,
        include_evidence=body.include_evidence,
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

    trace_events: list[dict[str, Any]] = []
    if include_trace and resp.trace_refs:
        trace_events = [{"run_id": rid} for rid in resp.trace_refs]

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
        runtime_mode=runtime_mode,
        latency_ms=resp.latency_ms or int((time.perf_counter() - t0) * 1000),
        cost={"amount": resp.cost_usd or 0.0, "currency": "USD"} if resp.cost_usd else {},
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
