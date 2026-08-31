"""A2A adapter for the user-facing Clinical Documentation Improvement Agent."""

from __future__ import annotations

import uuid
import json
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.icoder.agent_runtime.cdi import CDICase, CDIOrchestrator, RealCDIRunner
from app.icoder.agent_runtime.orchestrator.inbound_handler import (
    InboundRequest,
    InboundResponse,
    extract_text_from_parts,
    make_message_id,
    make_run_id,
)
from app.icoder.agent_runtime.orchestrator.phi_redactor import (
    PHIRedactionError,
    redact_payload,
)
from app.services.result_attestation import (
    ResultAttestationError,
    issue_result_attestation,
)
from app.services.dedicated_project_policy import (
    DedicatedProjectPolicy,
    ProjectPolicyLLM,
)
from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceStatus,
    RunTraceStep,
    emit_trace_event,
)
from app.icoder.agent_runtime.specialized_telemetry import (
    build_configured_cny_cost,
    build_cdi_telemetry_event,
)
from icoder_runtime.backends.output_contract_validation import (
    PreparedSourceDocument,
    declared_optional_fields,
    prepare_source_documents,
    validate_cross_agent_relations,
    validate_declared_field_schemas,
    validate_evidence_bindings,
    validate_required_field_types,
)


class CDIA2AHandler:
    """Run the existing CDI orchestrator behind A2A message/send."""

    AGENT_ID = "clinical-documentation-improvement-agent"

    def handle(self, agent_id: str, request: InboundRequest) -> InboundResponse:
        context_id = request.message.context_id
        # Preserve the facade-owned run id so lifecycle persistence, trace
        # lookup and the A2A projection all refer to the same execution.
        run_id = str(request.metadata.get("run_id") or make_run_id())
        try:
            safe_parts = redact_payload(request.message.parts).value
        except PHIRedactionError:
            return InboundResponse(
                kind="error",
                context_id=context_id,
                metadata={"run_id": run_id, "agent_id": agent_id, "phi_redacted": True},
                error={
                    "code": "PHI_REDACTION_FAILED",
                    "message": "The request could not be safely de-identified.",
                },
                http_status=500,
                redacted_input="",
            )
        safe_text = self._text_input(safe_parts) or extract_text_from_parts(safe_parts)
        data_input = self._data_input(safe_parts)
        source_documents, document_errors = prepare_source_documents(
            data_input.get("documents"),
            fallback_text=safe_text,
            fallback_document_id="chart-001",
            require_unique_document_ids=True,
        )
        if document_errors:
            return InboundResponse(
                kind="error",
                context_id=context_id,
                metadata={"run_id": run_id, "agent_id": agent_id, "phi_redacted": True},
                error={
                    "code": "INVALID_SOURCE_DOCUMENTS",
                    "message": "Source documents were ambiguous or exceeded safety limits.",
                },
                http_status=400,
                redacted_input=safe_text,
            )
        chart_text, document_segments = self._document_bundle(source_documents)
        if agent_id != self.AGENT_ID:
            return InboundResponse(
                kind="error",
                context_id=context_id,
                metadata={"run_id": run_id, "agent_id": agent_id, "phi_redacted": True},
                error={"code": "AGENT_NOT_FOUND", "message": "CDI Agent not found."},
                http_status=404,
                redacted_input=safe_text,
            )

        trace_identity = {
            "agent_id": agent_id,
            "input_parts": len(safe_parts),
            "_trace_id": str(request.metadata.get("trace_id") or "") or None,
            "_organization_id": str(
                request.metadata.get("organization_id")
                or request.metadata.get("tenant_id")
                or ""
            ) or None,
            "_user_id": str(request.metadata.get("user_id") or "") or None,
            "_actor_id": str(request.metadata.get("user_id") or "") or None,
        }
        emit_trace_event(
            run_id,
            RunTraceStep.USER_MESSAGE_RECEIVED,
            safe_metadata=trace_identity,
        )
        project_policy = request.metadata.get(
            "_dedicated_project_policy_token"
        )
        if isinstance(project_policy, DedicatedProjectPolicy):
            emit_trace_event(
                run_id,
                RunTraceStep.SCOPE_CHECKED,
                safe_metadata={
                    **trace_identity,
                    **project_policy.safe_metadata(),
                },
            )

        # CDI still uses the legacy LLMService internally. Never let an A2A
        # clinical request bypass the application's fail-closed mock setting
        # and reach that client with development credentials.
        if str(settings.LLM_PROVIDER or "").lower() == "mock":
            emit_trace_event(
                run_id,
                RunTraceStep.COMPLETION,
                status=RunTraceStatus.FAILED,
                safe_metadata={
                    **trace_identity,
                    "error_code": "PROVIDER_UNAVAILABLE",
                },
            )
            return InboundResponse(
                kind="error",
                context_id=context_id,
                metadata={
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "runtime_mode": "cdi_real_orchestrator",
                    "degraded": True,
                    "manual_review_required": True,
                    "phi_redacted": True,
                    "production_writeback_blocked": True,
                },
                error={
                    "code": "PROVIDER_UNAVAILABLE",
                    "message": "CDI LLM provider is unavailable; no clinical result was produced.",
                },
                http_status=503,
                redacted_input=safe_text,
            )

        if isinstance(project_policy, DedicatedProjectPolicy):
            from app.services.llm_service import llm_service

            governed_llm = ProjectPolicyLLM(llm_service, project_policy)
            runner = RealCDIRunner(llm=governed_llm)
            orchestrator = CDIOrchestrator(
                runner=runner,
                llm=governed_llm,
            )
        else:
            runner = RealCDIRunner()
            orchestrator = CDIOrchestrator(runner=runner)
        orchestration_started = time.perf_counter()
        case = orchestrator.run(CDICase(
            case_id=f"CASE-{uuid.uuid4().hex[:12]}",
            chart_excerpt=chart_text,
            patient_ref="DEID",
            encounter_ref="DEID",
        ))
        orchestration_latency_ms = max(
            int((time.perf_counter() - orchestration_started) * 1000),
            0,
        )
        traces = [
            self._trace_dict(trace)
            for trace in list(runner.stage_traces.values()) + list(runner.expert_traces)
        ]
        degraded_safety_gates = dict(case.degraded_safety_gates)
        degraded = bool(degraded_safety_gates) or any(
            trace.get("degraded") for trace in traces
        )
        telemetry = self._emit_runtime_telemetry(
            request=request,
            run_id=run_id,
            runner=runner,
            case=case,
            degraded_safety_gates=degraded_safety_gates,
            orchestration_latency_ms=orchestration_latency_ms,
        )
        configured_cost = dict((telemetry or {}).get("cost") or {})
        accounting_metadata = {"cost": configured_cost} if configured_cost else {}
        if degraded:
            return InboundResponse(
                kind="error",
                context_id=context_id,
                metadata={
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "runtime_mode": "cdi_real_orchestrator",
                    "degraded": True,
                    "manual_review_required": True,
                    "phi_redacted": True,
                    "production_writeback_blocked": True,
                    "stage_traces": traces,
                    "degraded_safety_gates": sorted(degraded_safety_gates),
                    **accounting_metadata,
                },
                error={
                    "code": "PROVIDER_EXECUTION_FAILED",
                    "message": "CDI execution degraded; no clinical result was published.",
                },
                http_status=503,
                redacted_input=safe_text,
            )
        contract_preview = self._output_contract()
        trace_schema = (
            ((contract_preview.get("field_schemas") or {}).get("trace_refs") or {})
            if isinstance(contract_preview, dict)
            else {}
        )
        gate_schema = (
            ((trace_schema.get("properties") or {}).get("gate_results") or {})
            if isinstance(trace_schema, dict)
            else {}
        )
        declared_gate_keys = set((gate_schema.get("properties") or {}).keys())
        public_gate_results = {
            key: value
            for key, value in case.stage_run_ids.items()
            if not declared_gate_keys or key in declared_gate_keys
        }
        result = {
            "case_id": case.case_id,
            "completion_state": case.completion_state,
            "encounter_summary": self._encounter_summary_dict(
                case.encounter_summary
            ),
            "documentation_gaps": [
                self._gap_dict(gap, document_segments)
                for gap in case.documentation_gaps
            ],
            "proposed_provider_queries": [
                self._query_dict(query, document_segments)
                for query in case.proposed_provider_queries
            ],
            "query_gate_summary": self._query_gate_summary(
                case.query_rewrite_queue,
                provider_query_count=len(case.proposed_provider_queries),
            ),
            "coding_specificity_checklist": [
                {
                    "condition": item.condition,
                    "elements_to_address": list(item.elements_to_address),
                }
                for item in case.coding_specificity_checklist
            ],
            "risk_flags": [
                {"category": flag.category, "description": flag.description}
                for flag in case.risk_flags
            ],
            "specialist_trace": [
                {
                    "expert_id": entry.expert_id,
                    "consulted": entry.consulted,
                    "requested": entry.requested,
                    "accepted": list(entry.accepted),
                    "rejected": list(entry.rejected),
                    "rationale": entry.rationale,
                    "route_decision": entry.route_decision,
                    "route_reason": entry.route_reason,
                    "execution_mode": entry.execution_mode,
                    "latency_ms": entry.latency_ms,
                    "tokens": entry.tokens,
                    "run_id": entry.run_id,
                    "trace_id": entry.trace_id,
                }
                for entry in case.specialist_trace
            ],
            "stage_run_ids": dict(case.stage_run_ids),
            "stage_trace_ids": dict(case.stage_trace_ids),
            "stage_traces": traces,
            "human_review": {
                "cdi_specialist_review_required": True,
                # The current public Pack requires a clinician response even
                # for an auto-pass/no-query case; CDI never writes back or
                # closes documentation review autonomously.
                "clinician_response_required": True,
                "review_priority": (
                    "urgent"
                    if any(query.priority == "urgent" for query in case.proposed_provider_queries)
                    else "routine"
                ),
            },
            "trace_refs": {
                "run_id": run_id,
                "stage_trace": dict(case.stage_trace_ids),
                "experts_consulted": [
                    entry.expert_id for entry in case.specialist_trace if entry.consulted
                ],
                # stage_run_ids also contains internal privacy-remediation
                # counters.  Keep those in internal telemetry, but never let
                # undeclared dynamic keys break the strict public Pack.
                "gate_results": public_gate_results,
            },
            "degraded": degraded,
            "manual_review_required": True,
            "phi_redacted": True,
            "production_writeback_blocked": True,
        }
        contract = self._output_contract()
        if not contract:
            return InboundResponse(
                kind="error",
                context_id=context_id,
                metadata={
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "runtime_mode": "cdi_real_orchestrator",
                    "phi_redacted": True,
                    "production_writeback_blocked": True,
                    "manual_review_required": True,
                    **accounting_metadata,
                },
                error={
                    "code": "OUTPUT_CONTRACT_UNAVAILABLE",
                    "message": "CDI output contract could not be loaded.",
                },
                http_status=503,
                redacted_input=safe_text,
            )
        schema_ref = str(contract.get("schema_ref") or "")
        if not schema_ref:
            return InboundResponse(
                kind="error",
                context_id=context_id,
                metadata={
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "runtime_mode": "cdi_real_orchestrator",
                    "phi_redacted": True,
                    "production_writeback_blocked": True,
                    "manual_review_required": True,
                    **accounting_metadata,
                },
                error={
                    "code": "OUTPUT_CONTRACT_UNAVAILABLE",
                    "message": "CDI output schema reference could not be loaded.",
                },
                http_status=503,
                redacted_input=safe_text,
            )
        required_fields = list(contract.get("required_fields") or [])
        allowed_fields = set(required_fields) | set(
            declared_optional_fields(contract)
        )
        public_result = {
            key: value for key, value in result.items() if key in allowed_fields
        }
        missing_required_fields = [
            field for field in required_fields if field not in public_result
        ]
        invalid_field_types = [
            item.to_dict()
            for item in validate_required_field_types(public_result, contract)
        ]
        invalid_field_schemas = [
            item.to_dict()
            for item in validate_declared_field_schemas(public_result, contract)
        ]
        invalid_field_schemas.extend(
            item.to_dict()
            for item in validate_evidence_bindings(
                public_result,
                contract,
                safe_text,
                source_documents=source_documents,
            )
        )
        invalid_cross_agent_relations = [
            item.to_dict()
            for item in validate_cross_agent_relations(
                public_result,
                contract,
                data_input.get("upstream_results")
                if isinstance(data_input.get("upstream_results"), list)
                else [],
            )
        ]
        if (
            missing_required_fields
            or invalid_field_types
            or invalid_field_schemas
            or invalid_cross_agent_relations
        ):
            all_violations = (
                invalid_field_types
                + invalid_field_schemas
                + invalid_cross_agent_relations
            )
            emit_trace_event(
                run_id,
                "contract_validation",
                status=RunTraceStatus.FAILED,
                safe_metadata={
                    **trace_identity,
                    "error_code": "OUTPUT_CONTRACT_VIOLATION",
                    "missing_required_fields": sorted(missing_required_fields),
                    "invalid_field_type_count": len(invalid_field_types),
                    "invalid_field_schema_count": len(invalid_field_schemas),
                    "invalid_cross_agent_relation_count": len(
                        invalid_cross_agent_relations
                    ),
                    "invalid_paths": sorted({
                        str(item.get("field") or item.get("path") or "")
                        for item in all_violations
                        if item.get("field") or item.get("path")
                    })[:32],
                    "invalid_keywords": sorted({
                        str(item.get("keyword") or "type")
                        for item in all_violations
                    })[:16],
                },
            )
            return InboundResponse(
                kind="error",
                context_id=context_id,
                metadata={
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "runtime_mode": "cdi_real_orchestrator",
                    "phi_redacted": True,
                    "production_writeback_blocked": True,
                    "manual_review_required": True,
                    "missing_required_fields": missing_required_fields,
                    "invalid_field_types": invalid_field_types,
                    "invalid_field_schemas": invalid_field_schemas,
                    "invalid_cross_agent_relations": invalid_cross_agent_relations,
                    **accounting_metadata,
                },
                error={
                    "code": "OUTPUT_CONTRACT_VIOLATION",
                    "message": "CDI output did not match the current Agent Pack contract.",
                },
                http_status=503,
                redacted_input=safe_text,
            )

        try:
            result_attestation = issue_result_attestation(
                run_id=run_id,
                agent_id=agent_id,
                schema_ref=schema_ref,
                organization_id=str(
                    request.metadata.get("organization_id")
                    or request.metadata.get("tenant_id")
                    or "default"
                ),
                result=public_result,
            )
        except ResultAttestationError:
            return InboundResponse(
                kind="error",
                context_id=context_id,
                metadata={
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "runtime_mode": "cdi_real_orchestrator",
                    "phi_redacted": True,
                    "production_writeback_blocked": True,
                    "manual_review_required": True,
                    **accounting_metadata,
                },
                error={
                    "code": "RESULT_ATTESTATION_FAILED",
                    "message": "The CDI result authenticity proof could not be created.",
                },
                http_status=503,
                redacted_input=safe_text,
            )

        return InboundResponse(
            kind="message",
            message_id=make_message_id(),
            context_id=context_id,
            role="agent",
            parts=[{
                "kind": "data",
                "data": public_result,
                "metadata": {
                    "schema_ref": schema_ref,
                    "result_attestation": result_attestation,
                    "phi_redacted": True,
                    "production_writeback_blocked": True,
                },
            }],
            metadata={
                "run_id": run_id,
                "agent_id": agent_id,
                "interaction_id": request.message.interaction_id,
                "output_contract": schema_ref,
                "result_attestation": result_attestation,
                "runtime_mode": "cdi_real_orchestrator",
                "degraded": degraded,
                "phi_redacted": True,
                "production_writeback_blocked": True,
                "manual_review_required": True,
                **accounting_metadata,
            },
            redacted_input=safe_text,
        )

    @staticmethod
    def _emit_runtime_telemetry(
        *,
        request: InboundRequest,
        run_id: str,
        runner: Any,
        case: Any,
        degraded_safety_gates: dict[str, Any],
        orchestration_latency_ms: int,
    ) -> dict[str, Any] | None:
        """Persist aggregate CDI model accounting without clinical content."""
        try:
            contract = CDIA2AHandler._output_contract()
            telemetry = build_cdi_telemetry_event(
                stage_traces=list(runner.stage_traces.values()),
                expert_traces=list(runner.expert_traces),
                specialist_trace=list(case.specialist_trace),
                safety_gate_traces=list(
                    getattr(case, "safety_gate_model_traces", [])
                ),
                stage_duration_ms=dict(getattr(case, "stage_duration_ms", {})),
                orchestration_latency_ms=orchestration_latency_ms,
                latency_budget_ms=settings.ICODER_CDI_LATENCY_BUDGET_MS,
                gate_max_concurrency=settings.ICODER_CDI_GATE_MAX_CONCURRENCY,
                output_contract=str(contract.get("schema_ref") or ""),
                degraded_safety_gates=degraded_safety_gates,
            )
            safe_metadata = dict(telemetry.get("safe_metadata") or {})
            configured_cost = build_configured_cny_cost(
                telemetry,
                input_price_per_1m=settings.LLM_PRICE_INPUT_PER_1M,
                output_price_per_1m=settings.LLM_PRICE_OUTPUT_PER_1M,
            )
            if configured_cost:
                safe_metadata.update({
                    "cost_amount": configured_cost["amount"],
                    "cost_currency": configured_cost["currency"],
                    "cost_source": configured_cost["source"],
                    "billing_authoritative": configured_cost[
                        "billing_authoritative"
                    ],
                })
                telemetry = {**telemetry, "cost": configured_cost}
            safe_metadata.update({
                "_trace_id": str(request.metadata.get("trace_id") or "") or None,
                "_organization_id": str(
                    request.metadata.get("organization_id")
                    or request.metadata.get("tenant_id")
                    or ""
                ) or None,
                "_user_id": str(request.metadata.get("user_id") or "") or None,
                "_actor_id": str(request.metadata.get("user_id") or "") or None,
            })
            emit_trace_event(
                run_id,
                str(telemetry.get("step") or "output_generated"),
                status=str(telemetry.get("status") or "ok"),
                duration_ms=float(telemetry.get("duration_ms") or 0),
                safe_metadata=safe_metadata,
            )
            return telemetry
        except Exception:
            # Clinical fail-closed semantics remain authoritative; a best-effort
            # local profile must not publish prompt/output merely to explain a
            # telemetry failure. Required DB profiles still record their
            # capture state at the RunTrace persistence boundary.
            import logging
            logging.getLogger(__name__).warning(
                "CDI runtime telemetry emit failed run_id=%s", run_id,
                exc_info=True,
            )
            return None

    @staticmethod
    def _text_input(parts: list[dict[str, Any]]) -> str:
        return "\n".join(
            str(part.get("text"))
            for part in parts
            if isinstance(part, dict)
            and (part.get("kind") or part.get("type")) == "text"
            and part.get("text")
        ).strip()

    @staticmethod
    def _data_input(parts: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for part in parts:
            if not isinstance(part, dict) or part.get("kind") != "data":
                continue
            data = part.get("data")
            if not isinstance(data, dict):
                continue
            value = data.get("value")
            if isinstance(value, dict):
                merged.update(value)
        return merged

    @staticmethod
    def _document_bundle(
        documents: list[PreparedSourceDocument],
    ) -> tuple[str, list[tuple[PreparedSourceDocument, int, int]]]:
        chunks: list[str] = []
        segments: list[tuple[PreparedSourceDocument, int, int]] = []
        cursor = 0
        for document in documents:
            if chunks:
                chunks.append("\n\n")
                cursor += 2
            start = cursor
            chunks.append(document.text)
            cursor += len(document.text)
            segments.append((document, start, cursor))
        return "".join(chunks), segments

    @staticmethod
    def _output_contract() -> dict[str, Any]:
        pack_path = (
            Path(__file__).resolve().parents[3]
            / "official_agents"
            / "clinical-documentation-improvement-agent"
            / "agent_pack.json"
        )
        try:
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        contract = pack.get("output_contract")
        return contract if isinstance(contract, dict) else {}

    @staticmethod
    def _encounter_summary_dict(summary: Any) -> dict[str, Any]:
        """Project model metadata onto the exact public Pack shape.

        DeepSeek correctly omits demographics that are absent from a chart,
        but the public CDI contract requires all three metadata keys. Publish
        an explicit ``unknown`` sentinel for absent facts and discard any
        model-added metadata keys; neither behavior invents a clinical fact.
        """
        raw_metadata = (
            dict(getattr(summary, "encounter_metadata", {}) or {})
            if summary is not None
            else {}
        )

        def _documented_or_unknown(name: str) -> str:
            value = raw_metadata.get(name)
            normalized = str(value).strip() if value is not None else ""
            return normalized or "unknown"

        return {
            "key_points": [
                str(item) for item in list(getattr(summary, "key_points", []) or [])
            ],
            "encounter_metadata": {
                "patient_age": _documented_or_unknown("patient_age"),
                "patient_sex": _documented_or_unknown("patient_sex"),
                "encounter_type": _documented_or_unknown("encounter_type"),
            },
        }

    @staticmethod
    def _span(
        span: Any,
        segments: list[tuple[PreparedSourceDocument, int, int]] | tuple = (),
    ) -> dict[str, Any] | None:
        if span is None:
            return None
        quote = str(span.quote or "")
        start = int(span.char_start)
        end = int(span.char_end)
        document_id = str(span.document_id or "")
        for document, _, _ in segments:
            if (
                document.document_id == document_id
                and 0 <= start < end <= len(document.text)
                and document.text[start:end] == quote
            ):
                break
        else:
            rebound: tuple[PreparedSourceDocument, int, int] | None = None
            for document, segment_start, segment_end in segments:
                if (
                    segment_start <= start < end <= segment_end
                    and document.text[
                        start - segment_start:end - segment_start
                    ] == quote
                ):
                    rebound = (
                        document,
                        start - segment_start,
                        end - segment_start,
                    )
                    break
            if rebound is None and quote:
                matches = []
                for document, _, _ in segments:
                    position = document.text.find(quote)
                    if position >= 0 and document.text.find(quote, position + 1) < 0:
                        matches.append((document, position, position + len(quote)))
                if len(matches) == 1:
                    rebound = matches[0]
            if rebound is not None:
                document, start, end = rebound
                document_id = document.document_id
        return {
            "document_id": document_id,
            "quote": quote,
            "char_start": start,
            "char_end": end,
            "documented_at": span.documented_at,
        }

    @classmethod
    def _gap_dict(
        cls,
        gap: Any,
        segments: list[tuple[PreparedSourceDocument, int, int]] | tuple = (),
    ) -> dict[str, Any]:
        return {
            "gap_id": gap.gap_id,
            "gap_type": gap.gap_type,
            "description": gap.description,
            "why_it_matters": gap.why_it_matters,
            "evidence_span": cls._span(gap.evidence_span, segments),
            "minimal_clarification_needed": gap.minimal_clarification_needed,
            "priority": gap.priority,
        }

    @classmethod
    def _query_dict(
        cls,
        query: Any,
        segments: list[tuple[PreparedSourceDocument, int, int]] | tuple = (),
    ) -> dict[str, Any]:
        return {
            "query_id": query.query_id,
            "gap_id": query.gap_id,
            "topic": query.topic,
            "reason": query.reason,
            "evidence_span": cls._span(query.evidence_span, segments),
            "evidence_spans": [
                cls._span(span, segments) for span in query.all_evidence_spans()
            ],
            "query_text": query.query_text,
            "response_options": list(query.response_options),
            "lifecycle_state": query.lifecycle_state,
            "priority": query.priority,
            "nlq_gate_verdict": query.nlq_gate_verdict,
            "nlq_gate_block_reasons": list(query.nlq_gate_block_reasons),
        }

    @staticmethod
    def _query_gate_summary(
        queue: list[dict[str, Any]],
        *,
        provider_query_count: int = 0,
    ) -> dict[str, Any]:
        # The current public Pack intentionally exposes only the number of
        # safe rewrite candidates. Internal rejection/defer statuses remain
        # in the protected audit trail and must not widen the public schema.
        generated_count = sum(
            1
            for item in queue
            if str(item.get("status") or "")
            == "REWRITE_CANDIDATE_GENERATED"
        )
        return {
            "withheld_count": len(queue),
            "status_counts": {
                "REWRITE_CANDIDATE_GENERATED": generated_count,
            },
            # Published DRAFT queries still require CDI specialist approval;
            # an empty rewrite queue does not mean that no human action is
            # required before clinician delivery.
            "manual_cdi_action_required": bool(queue or provider_query_count),
        }

    @staticmethod
    def _trace_dict(trace: Any) -> dict[str, Any]:
        return {
            "stage": trace.stage,
            "provider": trace.provider,
            "model": trace.model,
            "latency_ms": trace.latency_ms,
            "prompt_tokens": trace.prompt_tokens,
            "completion_tokens": trace.completion_tokens,
            "total_tokens": trace.total_tokens,
            "run_id": trace.run_id,
            "trace_id": trace.trace_id,
            "degraded": trace.degraded,
            "error_reason": trace.error_reason,
            "expert_id": trace.expert_id,
        }


__all__ = ["CDIA2AHandler"]
