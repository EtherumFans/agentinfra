"""Governed deterministic Provider for explicit triage questionnaire paths."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator

from .contracts import (
    AgentBackendProvider,
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    BackendType,
    ProviderCapability,
    ProviderHealth,
    ProviderStatus,
)


logger = logging.getLogger(__name__)


class GovernedTriageQuestionnaireProvider:
    provider_id = "icoder.governed-triage-questionnaire.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/TriageOutput/v5"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.triage.agent import verify_triage_questionnaire_health

            evidence = verify_triage_questionnaire_health()
            return ProviderHealth(
                state="ok",
                latency_ms=0,
                details={
                    "provider_id": self.provider_id,
                    "backend_type": self.backend_type,
                    **evidence,
                    "integrity_verified": True,
                    "protocol_authority_verified": False,
                    "hospital_approval_verified": False,
                    "production_action_blocked": True,
                    "production_writeback_blocked": True,
                },
            )
        except Exception as exc:
            return ProviderHealth(
                state="down",
                details={
                    "provider_id": self.provider_id,
                    "error": f"triage_questionnaire_health_failed:{type(exc).__name__}",
                },
            )

    async def invoke(
        self,
        req: BackendRequest,
        ctx: AgentRunContext,
        *,
        request: Any = None,
    ) -> BackendResponse:
        del request
        started = time.perf_counter()
        try:
            from official_agents.triage.agent import (
                build_triage_questionnaire_review,
                to_pack_output,
            )

            input_data = dict(req.input or {})
            text = str(input_data.get("text") or req.user_input or ctx.redacted_input or "")
            internal = build_triage_questionnaire_review(text, run_id=ctx.run_id)
            public = to_pack_output(internal)
            assessment_status = str(internal.get("assessment_status") or "RUNTIME_FAILED")
            if assessment_status == "READY_FOR_ONSITE_REVIEW":
                status: ProviderStatus = "requires_review"
                finish_state = "completed"
                finish_reason = None
                summary = (
                    f"已机械执行 {internal['_trace']['path_steps']} 个明确回答的问卷分支；"
                    "结果只是开发期协议候选，必须由现场分诊专业人员确认。"
                )
            elif assessment_status in {
                "INPUT_REQUIRED",
                "PROTOCOL_INVALID",
                "CONFLICT_REVIEW_REQUIRED",
            }:
                status = "incomplete"
                finish_state = "input-required"
                finish_reason = assessment_status.casefold().replace("_", "-")
                summary = "问卷、明确回答或逐字证据不足/冲突；未生成可用分诊级别。"
            else:
                status = "fail"
                finish_state = "failed"
                finish_reason = "governed_triage_questionnaire_failed_closed"
                summary = "受治理分诊问卷路径复核未完成，未生成候选。"

            latency_ms = int((time.perf_counter() - started) * 1000)
            self._emit_backend_metadata(ctx, internal, latency_ms, status)
            return BackendResponse(
                status=status,
                summary=summary,
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state=finish_state,
                finish_reason=finish_reason,
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                fallback_used=False,
                raw_provider_response=dict(internal),
                markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
                evidence_refs=[],
                trace_refs=[f"{ctx.run_id}:governed-triage-questionnaire-review"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "GovernedTriageQuestionnaireProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(ctx, {}, latency_ms, "fail")
            return BackendResponse(
                status="fail",
                summary="本地分诊问卷路径复核无法安全执行。",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=f"governed_triage_questionnaire_error:{type(exc).__name__}",
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
            )

    async def stream(
        self,
        req: BackendRequest,
        ctx: AgentRunContext,
    ) -> AsyncIterator[Any]:
        response = await self.invoke(req, ctx)
        yield {"step": "backend_invoked", "payload": response}
        yield {"step": "finished", "payload": {"state": response.finish_state}}

    def output_contract(self) -> str:
        return self._OUTPUT_CONTRACT_REF

    def fallback_chain(self) -> list[AgentBackendProvider] | None:
        return None

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            provider_id=self.provider_id,
            backend_type=self.backend_type,
            supports_tool_calling=False,
            supports_streaming=False,
            deterministic=True,
            default_output_contract=self._OUTPUT_CONTRACT_REF,
            supported_tools=[],
            description=(
                "Validates a bounded caller-supplied triage questionnaire, binds "
                "explicit structured answers to exact source spans, and mechanically "
                "follows its branches. It does not extract answers, validate clinical "
                "authority, calculate scores, assign final acuity, act, or write back."
            ),
        )

    def _emit_backend_metadata(
        self,
        ctx: AgentRunContext,
        internal: dict[str, Any],
        latency_ms: int,
        status: ProviderStatus,
    ) -> None:
        try:
            from app.icoder.agent_runtime.orchestrator.run_trace import (
                emit_backend_metadata_event,
                get_default_store,
            )

            trace = internal.get("_trace") or {}
            evidence_count = int(trace.get("evidence_items_count") or 0)
            valid_spans = int(trace.get("valid_spans_count") or 0)
            emit_backend_metadata_event(
                ctx.run_id,
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                provider_latency_ms=latency_ms,
                provider_status=status,
                provider_deterministic=True,
                supports_tool_calling=False,
                fallback_used=False,
                output_contract=str(
                    (ctx.agent_pack.get("output_contract") or {}).get("schema_ref")
                    or self.output_contract()
                ),
                tool_rounds=0,
                model_cost_usd=0.0,
                llm_call_count=0,
                evidence_items_count=evidence_count,
                valid_evidence_spans_count=valid_spans,
                invalid_evidence_spans_count=max(evidence_count - valid_spans, 0),
                candidate_codes_count=0,
                store=get_default_store(),
            )
        except Exception as exc:
            logger.warning(
                "GovernedTriageQuestionnaireProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["GovernedTriageQuestionnaireProvider"]
