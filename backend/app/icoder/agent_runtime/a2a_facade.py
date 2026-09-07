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
import json
import time
import uuid
from pathlib import Path
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
    RunTraceStep,
    emit_trace_event,
)
from app.icoder.agent_runtime.specialized_telemetry import (
    build_medical_coding_telemetry_event,
)
from app.services.result_attestation import (
    ResultAttestationError,
    issue_result_attestation,
)

logger = logging.getLogger(__name__)


# Agent IDs that route to CodingRuntimeDispatcher (G001 fast path).
MEDICAL_CODING_AGENT_IDS: frozenset[str] = frozenset({
    "medical-coding-agent",
    "medcoder-coding-review-agent",
})

_SUPPORTED_CODING_SYSTEMS: tuple[str, ...] = ("icd10cn", "icd9cm3")


def _requested_coding_systems(extra: dict[str, Any] | None) -> tuple[str, ...]:
    """Return a bounded coding-system selection for the Agent Pack route.

    Medical Coding Agent advertises diagnosis and procedure coding, so its
    default is both ICD-10-CN and ICD-9-CM-3.  Callers may explicitly request
    either supported subset through ``input.extra.coding_systems``; unknown
    values are ignored and can never enter provider instructions.
    """

    raw = (extra or {}).get("coding_systems")
    if not isinstance(raw, (list, tuple)):
        return _SUPPORTED_CODING_SYSTEMS
    requested = {
        str(value).strip().lower()
        for value in raw
        if isinstance(value, str)
    }
    selected = tuple(
        system for system in _SUPPORTED_CODING_SYSTEMS if system in requested
    )
    return selected or _SUPPORTED_CODING_SYSTEMS


def medical_coding_pack() -> dict[str, Any]:
    """Load the authoritative current Medical Coding Agent Pack."""
    pack_path = (
        Path(__file__).resolve().parents[3]
        / "official_agents"
        / "medical_coding"
        / "agent_pack.json"
    )
    return json.loads(pack_path.read_text(encoding="utf-8"))


def medical_coding_schema_ref() -> str:
    """Return the schema version advertised by the current Pack."""
    schema_ref = str(
        (medical_coding_pack().get("output_contract") or {}).get("schema_ref")
        or ""
    )
    if not schema_ref:
        raise RuntimeError("medical-coding Agent Pack is missing output schema_ref")
    return schema_ref


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
    project_policy: str = "",
    project_policy_metadata: dict[str, Any] | None = None,
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
    coding_systems = _requested_coding_systems(extra)
    request = CodingRequest(
        text=input_text,
        mode=mode,
        coding_system=coding_systems[0],
        coding_systems=coding_systems,
        include_evidence=include_evidence,
        include_trace=include_trace,
        run_id=run_id,
        user_id=user_id,
        tenant_id=tenant_id,
        project_policy=project_policy,
    )

    if project_policy:
        policy_meta = project_policy_metadata or {}
        emit_trace_event(
            run_id,
            RunTraceStep.SCOPE_CHECKED,
            safe_metadata={
                "agent_id": agent_id,
                "project_policy_digest": str(
                    policy_meta.get("project_policy_digest") or ""
                ),
                "project_prompt_overridden": bool(
                    policy_meta.get("project_prompt_overridden")
                ),
                "project_expert_ids": list(
                    policy_meta.get("project_expert_ids") or []
                ),
                "dedicated_source_experts_fixed": bool(
                    policy_meta.get("dedicated_source_experts_fixed", True)
                ),
                "source_runtime_agent_id": str(
                    policy_meta.get("source_runtime_agent_id") or ""
                ),
                "_organization_id": tenant_id or None,
                "_user_id": user_id or None,
                "_actor_id": user_id or None,
                "_trace_id": trace_id or None,
            },
        )

    dispatcher = get_dispatcher()
    result = await dispatcher.dispatch(request)
    out_run_id = result.run_id or run_id
    out_trace_id = result.trace_id or trace_id
    # Dedicated coding runtimes do not pass through Provider Registry's
    # direct telemetry emitter.  Persist one normalized, PHI-free provider
    # event here so both unified Agent Run and A2A message/send share the
    # same accounting span even when the caller hides inline trace details.
    try:
        telemetry = build_medical_coding_telemetry_event(
            result,
            output_contract=medical_coding_schema_ref(),
        )
        safe_metadata = dict(telemetry.get("safe_metadata") or {})
        safe_metadata.update({
            "agent_id": agent_id,
            "source_runtime_agent_id": str(
                (project_policy_metadata or {}).get("source_runtime_agent_id")
                or ""
            ),
            "_trace_id": out_trace_id,
            "_organization_id": tenant_id or None,
            "_user_id": user_id or None,
            "_actor_id": user_id or None,
        })
        emit_trace_event(
            out_run_id,
            str(telemetry.get("step") or "output_generated"),
            status=str(telemetry.get("status") or RunTraceStatus.OK),
            duration_ms=float(telemetry.get("duration_ms") or 0),
            safe_metadata=safe_metadata,
        )
    except Exception as exc:
        logger.warning(
            "a2a_facade: medical coding telemetry emit failed "
            "run_id=%s error_type=%s",
            out_run_id,
            type(exc).__name__,
        )
    return result, out_run_id, out_trace_id


async def run_medical_coding_a2a(
    *,
    dispatch_input: dict[str, Any],
    context_id: str,
    interaction_id: str = "",
    source_text: str = "",
    source_documents: list[dict[str, Any]] | None = None,
    upstream_results: list[dict[str, Any]] | None = None,
) -> InboundResponse:
    """Own the A2A fast-path audit lifecycle before publishing any result.

    The unified Agent Run endpoint owns its own lifecycle and continues to
    call dispatch_medical_coding_fast directly. Trace events alone cannot
    authorize a trace read: a committed tenant-owned RunHistory is required.
    """
    from app import database
    from app.services.run_lifecycle import RunStatus, record_run_start, set_status
    from app.services.database_tenancy import bind_tenant_to_transaction

    dispatch_input = dict(dispatch_input)
    run_id = dispatch_input["run_id"] = dispatch_input.get("run_id") or make_run_id()
    trace_id = dispatch_input["trace_id"] = (
        dispatch_input.get("trace_id") or f"trace-{uuid.uuid4().hex[:16]}"
    )
    agent_id = str(dispatch_input["agent_id"])
    organization_id = str(dispatch_input.get("tenant_id") or "")
    user_id = str(dispatch_input.get("user_id") or "")
    started_at = time.monotonic()

    def failure(code: str, message: str) -> InboundResponse:
        return InboundResponse(
            kind="error", context_id=context_id, http_status=503,
            metadata={
                "run_id": run_id, "trace_id": trace_id, "agent_id": agent_id,
                "phi_redacted": True, "production_writeback_blocked": True,
                "manual_review_required": True,
            },
            error={"code": code, "message": message},
        )

    try:
        if not organization_id:
            raise ValueError("A2A run requires server-established tenant identity")
        async with database.AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db, organization_id)
            await record_run_start(
                db, run_id=run_id, trace_id=trace_id, agent_id=agent_id,
                organization_id=organization_id, user_id=user_id,
                context_id=context_id, input_text=source_text,
                runtime_mode=dispatch_input.get("runtime_mode") or "corti_like_fast",
            )
            await set_status(db, run_id=run_id, status=RunStatus.RUNNING)
            await db.commit()
    except Exception as exc:
        logger.error("Medical A2A audit start failed error_type=%s", type(exc).__name__)
        return failure("RUN_AUDIT_UNAVAILABLE", "Agent execution could not establish its audit record.")

    result = None
    try:
        result, out_run_id, trace_id = await dispatch_medical_coding_fast(**dispatch_input)
        if out_run_id != run_id:
            raise ValueError("Runtime changed the authoritative run identity")
        persist_trace_events(
            run_id=run_id, trace_events=list(result.trace_events or []),
            agent_id=agent_id, runtime_mode=result.runtime_mode,
            trace_id=trace_id, organization_id=organization_id,
            user_id=user_id, actor_id=user_id,
        )
        response = build_medical_coding_inbound_response(
            result=result, run_id=run_id, trace_id=trace_id,
            context_id=context_id, interaction_id=interaction_id,
            source_text=source_text, source_documents=source_documents,
            upstream_results=upstream_results, organization_id=organization_id,
        )
    except Exception as exc:
        logger.error("Medical A2A execution failed error_type=%s", type(exc).__name__)
        response = failure("INTERNAL_ERROR", "Medical coding execution failed.")

    failed = response.kind != "message"
    reason = str((response.error or {}).get("code") or "") if failed else ""
    emit_trace_event(
        run_id, RunTraceStep.COMPLETION,
        status=RunTraceStatus.FAILED if failed else RunTraceStatus.OK,
        safe_metadata={
            "agent_id": agent_id, "error_reason": reason,
            "_trace_id": trace_id, "_organization_id": organization_id,
            "_user_id": user_id or None, "_actor_id": user_id or None,
        },
    )
    try:
        async with database.AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db, organization_id)
            row = await set_status(
                db, run_id=run_id,
                status=RunStatus.FAILED if failed else RunStatus.COMPLETED,
                extra_fields={
                    "trace_id": trace_id,
                    "latency_ms": int((time.monotonic() - started_at) * 1000),
                    "cost_usd": float((getattr(result, "cost", None) or {}).get("amount") or 0),
                    "error": failed, "error_reason": reason[:128] or None,
                },
            )
            if row is None:
                raise RuntimeError("Run audit record disappeared before finalization")
            await db.commit()
    except Exception as exc:
        logger.error("Medical A2A audit finalization failed error_type=%s", type(exc).__name__)
        return failure("RUN_AUDIT_UNAVAILABLE", "Agent result was withheld because its audit record could not be finalized.")
    return response


def build_medical_coding_inbound_response(
    *,
    result: Any,
    run_id: str,
    trace_id: str,
    context_id: str,
    interaction_id: str = "",
    source_text: str | None = None,
    source_documents: list[dict[str, Any]] | None = None,
    upstream_results: list[dict[str, Any]] | None = None,
    organization_id: str = "default",
) -> InboundResponse:
    """Project a CodingResult into an A2A InboundResponse with v2 parts.

    Used by ``_MedicalCodingV2ProjectingHandler`` so the A2A ``message:send``
    path returns the same v2 contract as the unified endpoint.
    """
    pack = medical_coding_pack()
    output_contract = pack.get("output_contract") or {}
    schema_ref = medical_coding_schema_ref()
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
    rendered_markdown = ""
    try:
        v1 = MedicalCodingOutputSchema.from_dict(raw)
        v2 = MedicalCodingAgentOutputV2.from_legacy_v1(v1, run_id=run_id)
        v2_dict = v2.to_dict()
        try:
            from app.icoder.markdown_generator import generate_markdown
            rendered_markdown = generate_markdown(v2_dict)
        except Exception as _me:
            logger.warning("Markdown generation failed (non-fatal): %s", _me)
    except Exception as _pe:
        logger.error("A2A v1→v2 projection failed: %s", _pe)
        return InboundResponse(
            kind="error",
            context_id=context_id,
            metadata={
                "run_id": run_id,
                "trace_id": trace_id,
                "agent_id": "medical-coding-agent",
                "phi_redacted": True,
                "production_writeback_blocked": True,
                "manual_review_required": True,
            },
            error={
                "code": "OUTPUT_PROJECTION_FAILED",
                "message": "Medical coding output could not be projected safely.",
            },
            http_status=503,
            redacted_input=source_text or "",
        )

    if result.error:
        return InboundResponse(
            kind="error",
            context_id=context_id,
            metadata={
                "run_id": run_id,
                "trace_id": trace_id,
                "agent_id": "medical-coding-agent",
                "runtime_mode": result.runtime_mode,
                "phi_redacted": True,
                "production_writeback_blocked": True,
                "manual_review_required": True,
            },
            error={
                "code": "PROVIDER_EXECUTION_FAILED",
                "message": "Medical coding provider did not produce a valid result.",
            },
            http_status=503,
            redacted_input=source_text or "",
        )

    try:
        from icoder_runtime.backends.output_contract_validation import (
            declared_optional_fields,
            validate_cross_agent_relations,
            validate_declared_field_schemas,
            validate_evidence_bindings,
            validate_required_field_types,
        )
        required_fields = list(output_contract.get("required_fields") or [])
        allowed_fields = set(required_fields) | set(
            declared_optional_fields(output_contract)
        )
        missing_required_fields = [
            field for field in required_fields if field not in v2_dict
        ]
        undeclared_output_fields = sorted(
            field for field in v2_dict if field not in allowed_fields
        )
        invalid_field_types = [
            item.to_dict()
            for item in validate_required_field_types(v2_dict, output_contract)
        ]
        invalid_field_schemas = [
            item.to_dict()
            for item in validate_declared_field_schemas(v2_dict, output_contract)
        ]
        if source_text is not None or source_documents:
            invalid_field_schemas.extend(
                item.to_dict()
                for item in validate_evidence_bindings(
                    v2_dict,
                    output_contract,
                    source_text,
                    source_documents=source_documents,
                )
            )
        invalid_cross_agent_relations = [
            item.to_dict()
            for item in validate_cross_agent_relations(
                v2_dict,
                output_contract,
                upstream_results,
            )
        ]
    except Exception as exc:
        logger.error(
            "Medical coding A2A output validation failed error_type=%s",
            type(exc).__name__,
        )
        missing_required_fields = []
        undeclared_output_fields = []
        invalid_field_types = []
        invalid_field_schemas = [{
            "path": "$",
            "keyword": "outputContract",
            "expected": "available_validator",
            "actual": "validation_unavailable",
        }]
        invalid_cross_agent_relations = []
    if (
        missing_required_fields
        or undeclared_output_fields
        or invalid_field_types
        or invalid_field_schemas
        or invalid_cross_agent_relations
    ):
        return InboundResponse(
            kind="error",
            context_id=context_id,
            metadata={
                "run_id": run_id,
                "trace_id": trace_id,
                "agent_id": "medical-coding-agent",
                "phi_redacted": True,
                "production_writeback_blocked": True,
                "manual_review_required": True,
                "missing_required_fields": missing_required_fields,
                "undeclared_output_field_count": len(undeclared_output_fields),
                "invalid_field_types": invalid_field_types,
                "invalid_field_schemas": invalid_field_schemas,
                "invalid_cross_agent_relations": invalid_cross_agent_relations,
            },
            error={
                "code": "OUTPUT_CONTRACT_VIOLATION",
                "message": "Medical coding output did not match its source contract.",
            },
            http_status=503,
            redacted_input=source_text or "",
        )

    runtime_metadata = {
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

    try:
        result_attestation = issue_result_attestation(
            run_id=run_id,
            agent_id="medical-coding-agent",
            schema_ref=schema_ref,
            organization_id=organization_id,
            result=v2_dict,
        )
    except ResultAttestationError as exc:
        logger.error(
            "Medical coding A2A result attestation failed error_type=%s",
            type(exc).__name__,
        )
        return InboundResponse(
            kind="error",
            context_id=context_id,
            metadata={
                "run_id": run_id,
                "trace_id": trace_id,
                "agent_id": "medical-coding-agent",
                "phi_redacted": True,
                "production_writeback_blocked": True,
            },
            error={
                "code": "RESULT_ATTESTATION_FAILED",
                "message": "The Agent result authenticity proof could not be created.",
            },
            http_status=503,
            redacted_input=source_text or "",
        )

    return InboundResponse(
        kind="message",
        message_id=make_message_id(),
        context_id=context_id,
        role="agent",
        parts=[{
            "kind": "data",
            "data": v2_dict,
            "metadata": {
                "schema_ref": schema_ref,
                "result_attestation": result_attestation,
                "projected_from": "MedicalCodingOutputSchema/v1",
                "phi_redacted": True,
                "production_writeback_blocked": True,
                "runtime_mode": result.runtime_mode,
                "latency_ms": result.latency_ms,
                "trace_id": trace_id,
                "rendered_markdown": rendered_markdown,
                "runtime": runtime_metadata,
            },
        }],
        metadata={
            "run_id": run_id,
            "trace_id": trace_id,
            "agent_id": "medical-coding-agent",
            "interaction_id": interaction_id,
            "phi_redacted": True,
            "production_writeback_blocked": True,
            "output_contract": schema_ref,
            "result_attestation": result_attestation,
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
    organization_id: str = "",
    user_id: str = "",
    actor_id: str = "",
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
            "_trace_id": trace_id,
            "_organization_id": organization_id or None,
            "_user_id": user_id or None,
            "_actor_id": actor_id or user_id or None,
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
    "medical_coding_pack",
    "medical_coding_schema_ref",
    "persist_trace_events",
]
