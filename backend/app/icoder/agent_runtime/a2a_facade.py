"""A2A-compatible facade — Phase 4-F2 (2026-07-10).

Provides the shared "A2A-compatible adapter" used by BOTH:

  - ``POST /api/v1/agents/{agent_id}/run`` (unified endpoint,
    ``app/api/agent_run.py``)
  - ``POST /api/icoder/agents/{agent_id}/v1/message:send`` (A2A mainline,
    via ``_MedicalCodingV2ProjectingHandler`` in ``app/main.py``)

Per Phase 4-F2 prompt §6.1:
  "如现有 A2A handler 过重，可先做一层轻量 A2A-compatible adapter，
   但必须保留 A2A envelope 语义，不允许继续形成完全独立路径。"

Three-layer architecture (§2):
  A2A = protocol layer       (InboundRequest / InboundResponse envelope)
  endpoint = entry/facade    (/api/v1/agents/{id}/run)
  runtime = execution layer  (corti_like_fast / medcoder_deep / ...)

This module owns the **envelope construction + runtime dispatch** so both
entry points share one A2A-compatible code path. The envelope preserves
A2A semantics (run_id, trace_id, context_id, message_id, parts, metadata)
even when the underlying dispatch is a lightweight CodingRuntimeDispatcher
call rather than the full InboundHandler 5-stage state machine.

Medical Coding Agent default routing (§4.2):
  - ``medical-coding-agent`` + runtime_mode in (None, "corti_like_fast")
    → CodingRuntimeDispatcher (FastCodingRuntime, ~6-8s)
  - ``medical-coding-agent`` + runtime_mode == "medcoder_deep"
    → InboundHandler 5-stage MedCODER pipeline (30-60s+, opt-in only)

Trace persistence (§4.3):
  - ``persist_trace_events()`` emits each trace_event to RunTraceStore
    so ``GET /api/runtime/runs/{run_id}/trace`` returns the events for
    unified-endpoint runs (not just A2A-persisted runs).
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.icoder.agent_runtime.orchestrator.inbound_handler import (
    InboundMessage,
    InboundRequest,
    InboundResponse,
    extract_text_from_parts,
    make_context_id,
    make_message_id,
    make_run_id,
)
from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceStatus,
    emit_trace_event,
)

logger = logging.getLogger(__name__)


# Agent IDs that route to CodingRuntimeDispatcher (G001 fast path).
MEDICAL_CODING_AGENT_IDS: frozenset[str] = frozenset({
    "medical-coding-agent",
    "medcoder-coding-review-agent",
})


# ── Envelope construction ────────────────────────────────────────────────


def construct_envelope(
    *,
    agent_id: str,
    input_text: str,
    extra: dict[str, Any] | None = None,
    runtime_mode: str | None = None,
    include_trace: bool = True,
    include_evidence: bool = True,
    run_id: str | None = None,
    trace_id: str | None = None,
    user_id: str = "",
    tenant_id: str = "",
) -> tuple[InboundRequest, str, str, str, str]:
    """Build an A2A-compatible InboundRequest envelope (§4.1).

    The envelope preserves A2A protocol semantics:
      - ``message.role`` = "user"
      - ``message.parts`` = [TextPart(input_text), DataPart(extra)?]
      - ``message.interaction_id`` = trace_id (for cross-reference)
      - ``metadata`` carries runtime_mode / include_trace / include_evidence
        / run_id / trace_id / agent_id / user_id / tenant_id

    Returns ``(envelope, run_id, trace_id, context_id, message_id)`` so
    the caller can thread these IDs through the response + trace persistence.
    """
    out_run_id = run_id or f"run-{uuid.uuid4()}"
    out_trace_id = trace_id or f"trace-{uuid.uuid4().hex[:16]}"
    context_id = make_context_id()
    message_id = make_message_id()

    parts: list[dict[str, Any]] = [
        {"kind": "text", "text": input_text},
    ]
    if extra:
        parts.append({
            "kind": "data",
            "data": {
                "schema": "icoder/AgentRunInputExtra/v1",
                "value": dict(extra),
            },
        })

    metadata: dict[str, Any] = {
        "agent_id": agent_id,
        "run_id": out_run_id,
        "trace_id": out_trace_id,
        "context_id": context_id,
        "message_id": message_id,
        "runtime_mode": runtime_mode or "",
        "include_trace": include_trace,
        "include_evidence": include_evidence,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "phi_redacted": True,
        "production_writeback_blocked": True,
    }

    envelope = InboundRequest(
        message=InboundMessage(
            role="user",
            parts=parts,
            interaction_id=out_trace_id,
        ),
        metadata=metadata,
    )
    return envelope, out_run_id, out_trace_id, context_id, message_id


# ── Medical Coding fast-path dispatch (shared by both entry points) ────


async def dispatch_medical_coding_fast(
    *,
    agent_id: str,
    input_text: str,
    extra: dict[str, Any] | None,
    runtime_mode: str | None,
    include_trace: bool,
    include_evidence: bool,
    run_id: str,
    trace_id: str,
    user_id: str = "",
    tenant_id: str = "",
) -> tuple[Any, str, str]:
    """Dispatch medical-coding-agent to CodingRuntimeDispatcher.

    Routes to FastCodingRuntime for ``corti_like_fast`` (default) or
    MedCoderRuntime for ``medcoder_deep``. Returns ``(CodingResult,
    out_run_id, out_trace_id)``.

    This is the shared fast-path used by:
      - unified endpoint ``_run_medical_coding()`` in agent_run.py
      - ``_MedicalCodingV2ProjectingHandler`` when runtime_mode is None or
        "corti_like_fast" (so A2A ``message:send`` also defaults to fast)
    """
    from app.coding_runtime import (
        CodingRequest,
        RuntimeMode,
        get_dispatcher,
    )

    mode_str = runtime_mode or "corti_like_fast"
    mode = RuntimeMode.coerce(mode_str)
    request = CodingRequest(
        text=input_text,
        mode=mode,
        coding_system="icd10cn",
        include_evidence=include_evidence,
        include_trace=include_trace,
        run_id=run_id,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    dispatcher = get_dispatcher()
    result = await dispatcher.dispatch(request)
    out_run_id = result.run_id or run_id
    out_trace_id = result.trace_id or trace_id
    return result, out_run_id, out_trace_id


def build_medical_coding_inbound_response(
    *,
    result: Any,
    run_id: str,
    trace_id: str,
    context_id: str,
    interaction_id: str = "",
) -> InboundResponse:
    """Project a CodingResult into an A2A InboundResponse with v2 parts.

    Used by ``_MedicalCodingV2ProjectingHandler`` so the A2A ``message:send``
    path returns the same v2 contract as the unified endpoint.
    """
    try:
        from official_agents.medical_coding.schema import (
            MedicalCodingOutputSchema,
            MedicalCodingAgentOutputV2,
        )
    except Exception:
        return InboundResponse(
            kind="error",
            context_id=context_id,
            metadata={
                "run_id": run_id,
                "trace_id": trace_id,
                "agent_id": "medical-coding-agent",
                "phi_redacted": True,
            },
            error={"code": "INTERNAL_ERROR", "message": "medical_coding schema unavailable"},
            http_status=500,
        )

    raw = dict(result.raw_schema) if result.raw_schema else {}
    try:
        v1 = MedicalCodingOutputSchema.from_dict(raw)
        v2 = MedicalCodingAgentOutputV2.from_legacy_v1(v1, run_id=run_id)
        v2_dict = v2.to_dict()
        try:
            from app.icoder.markdown_generator import generate_markdown
            v2_dict["markdown"] = generate_markdown(v2_dict)
        except Exception as _me:
            logger.warning("Markdown generation failed (non-fatal): %s", _me)
    except Exception as _pe:
        logger.warning("A2A v1→v2 projection failed: %s; passing through v1", _pe)
        v2_dict = raw

    v2_dict["_runtime"] = {
        "runtime_mode": result.runtime_mode,
        "latency_ms": result.latency_ms,
        "llm_provider": result.llm_provider,
        "trace_id": trace_id,
        "run_id": run_id,
        "cost": dict(result.cost),
        "trace_events": list(result.trace_events),
        "error": result.error,
        "error_reason": result.error_reason,
    }

    return InboundResponse(
        kind="message",
        message_id=make_message_id(),
        context_id=context_id,
        role="agent",
        parts=[{
            "kind": "data",
            "data": v2_dict,
            "metadata": {
                "schema_ref": "icoder/MedicalCodingAgentOutputV2/v1",
                "projected_from": "MedicalCodingOutputSchema/v1",
                "phi_redacted": True,
                "production_writeback_blocked": True,
                "runtime_mode": result.runtime_mode,
                "latency_ms": result.latency_ms,
                "trace_id": trace_id,
            },
        }],
        metadata={
            "run_id": run_id,
            "trace_id": trace_id,
            "agent_id": "medical-coding-agent",
            "interaction_id": interaction_id,
            "phi_redacted": True,
            "production_writeback_blocked": True,
            "output_contract": "icoder/MedicalCodingAgentOutputV2/v1",
            "v1_to_v2_projected": True,
            "runtime_mode": result.runtime_mode,
            "latency_ms": result.latency_ms,
        },
        http_status=200,
    )


# ── Trace persistence ────────────────────────────────────────────────────


def persist_trace_events(
    *,
    run_id: str,
    trace_events: list[dict[str, Any]],
    agent_id: str = "",
    runtime_mode: str = "",
    trace_id: str = "",
) -> None:
    """Emit each trace_event to RunTraceStore (§4.3).

    After a unified-endpoint run completes, this writes the inline
    ``trace_events`` from the CodingResult / BackendResponse into the
    process-wide RunTraceStore so ``GET /api/runtime/runs/{run_id}/trace``
    returns the events (not just the inline response body).

    Defensive — never raises: if the store write fails, we log and continue
    (the response still carries trace_events inline).
    """
    if not trace_events:
        return
    for ev in trace_events:
        if not isinstance(ev, dict):
            continue
        step = str(ev.get("step", "unknown"))
        status = str(ev.get("status", "ok")) or RunTraceStatus.OK
        duration_ms = float(ev.get("duration_ms", 0) or 0)
        meta = ev.get("metadata") or ev.get("safe_metadata") or {}
        safe_meta: dict[str, Any] = {
            "agent_id": agent_id,
            "runtime_mode": runtime_mode,
            "trace_id": trace_id,
        }
        if isinstance(meta, dict):
            for k, v in meta.items():
                if k in ("agent_id", "runtime_mode", "trace_id"):
                    continue
                safe_meta[k] = v
        try:
            emit_trace_event(
                run_id,
                step,
                status=status,
                duration_ms=duration_ms,
                safe_metadata=safe_meta,
            )
        except Exception as e:
            logger.warning(
                "a2a_facade: emit_trace_event failed for run_id=%s step=%s: %s",
                run_id, step, e,
            )


__all__ = [
    "MEDICAL_CODING_AGENT_IDS",
    "construct_envelope",
    "dispatch_medical_coding_fast",
    "build_medical_coding_inbound_response",
    "persist_trace_events",
]
