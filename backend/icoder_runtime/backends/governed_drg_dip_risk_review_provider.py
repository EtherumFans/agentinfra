"""Governed local Provider for explicit coded-case DRG/DIP risk review."""

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


class GovernedDRGDIPRiskReviewProvider:
    provider_id = "icoder.governed-drg-dip-risk-review.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/DRGDIPRiskReview/v8"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.drg_analyzer.agent import (
                verify_drg_dip_risk_review_health,
            )

            evidence = verify_drg_dip_risk_review_health()
            governance = evidence.get("governance") or {}
            return ProviderHealth(
                state="ok",
                latency_ms=0,
                details={
                    "provider_id": self.provider_id,
                    "backend_type": self.backend_type,
                    **evidence,
                    "integrity_verified": True,
                    "rule_pack_id": governance.get("asset_id"),
                    "rule_pack_version": governance.get("version"),
                    "authority_status": governance.get("authority_status"),
                    "license_status": governance.get("license_status"),
                    "billing_authoritative": False,
                    "official_grouping_performed": False,
                    "official_dip_scoring_performed": False,
                    "payment_calculation_performed": False,
                    "production_writeback_blocked": True,
                },
            )
        except Exception as exc:
            return ProviderHealth(
                state="down",
                details={
                    "provider_id": self.provider_id,
                    "error": f"drg_dip_risk_review_health_failed:{type(exc).__name__}",
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
            from official_agents.drg_analyzer.agent import (
                build_drg_dip_risk_review,
                to_pack_output,
            )

            input_data = dict(req.input or {})
            text = str(input_data.get("text") or req.user_input or ctx.redacted_input or "")
            internal = await build_drg_dip_risk_review(text, run_id=ctx.run_id)
            public = to_pack_output(internal)
            review_status = str(internal.get("review_status") or "RUNTIME_FAILED")
            if review_status == "INPUT_REQUIRED":
                status: ProviderStatus = "incomplete"
                finish_state = "input-required"
                finish_reason = "required_labelled_coded_case_fields_missing"
                summary = "缺少明确的编码标准、版本、主诊断编码或逐字证据；未运行 DRG/DIP 风险复核。"
            elif review_status == "RUNTIME_FAILED":
                status = "fail"
                finish_state = "failed"
                finish_reason = "governed_drg_dip_risk_review_failed_closed"
                summary = "受治理 DRG/DIP 风险复核未完成，未生成可用候选。"
            else:
                status = "requires_review"
                finish_state = "completed"
                finish_reason = None
                summary = (
                    f"已对 {internal['_trace']['diagnosis_count']} 个明确诊断编码及 "
                    f"{internal['_trace']['procedure_count']} 个明确手术编码执行开发期风险复核；"
                    "候选分组非官方结果，必须由授权引擎和编码员复核。"
                )
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
                trace_refs=[f"{ctx.run_id}:governed-drg-dip-risk-review"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "GovernedDRGDIPRiskReviewProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(ctx, {}, latency_ms, "fail")
            return BackendResponse(
                status="fail",
                summary="本地 DRG/DIP 风险复核无法安全执行。",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=f"governed_drg_dip_risk_review_error:{type(exc).__name__}",
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
                "Runs hash-pinned, development-only China DRG/DIP risk heuristics "
                "on explicit coded inputs and exact evidence. It never extracts or "
                "assigns codes and never emits official grouping, DIP scores, payment, "
                "settlement, submission, or writeback results."
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
                candidate_codes_count=int(trace.get("diagnosis_count") or 0)
                + int(trace.get("procedure_count") or 0),
                store=get_default_store(),
            )
        except Exception as exc:
            logger.warning(
                "GovernedDRGDIPRiskReviewProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["GovernedDRGDIPRiskReviewProvider"]
