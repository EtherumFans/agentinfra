"""Governed local Provider for explicitly documented referral fields."""

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


class GovernedReferralProvider:
    provider_id = "icoder.governed-referral.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/ReferralOutput/v3"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.referral_gen.agent import verify_referral_health

            return ProviderHealth(
                state="ok",
                latency_ms=0,
                details={
                    "provider_id": self.provider_id,
                    "backend_type": self.backend_type,
                    **verify_referral_health(),
                },
            )
        except Exception as exc:
            return ProviderHealth(
                state="down",
                details={
                    "provider_id": self.provider_id,
                    "error": f"referral_health_failed:{type(exc).__name__}",
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
            from official_agents.referral_gen.agent import build_referral, to_pack_output

            input_data = dict(req.input or {})
            text = str(input_data.get("text") or req.user_input or ctx.redacted_input or "")
            internal = build_referral(text, run_id=ctx.run_id)
            public = to_pack_output(internal)
            input_required = internal["referral_status"] == "INPUT_REQUIRED"
            status: ProviderStatus = "incomplete" if input_required else "requires_review"
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._emit_backend_metadata(ctx, internal, latency_ms, status)
            return BackendResponse(
                status=status,
                summary=(
                    "缺少生成转诊信所需的明确字段；请补充缺失项。"
                    if input_required
                    else (
                        f"已将 {internal['_trace']['evidence_items_count']} 条明确记录装配为转诊草案；"
                        "未推断诊断、紧急程度或新增治疗建议，须转出医师复核。"
                    )
                ),
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="input-required" if input_required else "completed",
                finish_reason=(
                    "required_labelled_referral_fields_missing" if input_required else None
                ),
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                fallback_used=False,
                raw_provider_response=dict(internal),
                markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
                evidence_refs=[],
                trace_refs=[f"{ctx.run_id}:governed-referral"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "GovernedReferralProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(ctx, {}, latency_ms, "fail")
            return BackendResponse(
                status="fail",
                summary="本地转诊草案生成无法安全执行。",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=f"governed_referral_error:{type(exc).__name__}",
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
                "Assembles explicitly headed referral fields into a fixed review-only "
                "letter with exact spans. It does not summarize unlabelled narrative, "
                "infer urgency or specialty, create diagnoses or recommendations, "
                "transmit the referral, or write to a health record."
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
                "GovernedReferralProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["GovernedReferralProvider"]
