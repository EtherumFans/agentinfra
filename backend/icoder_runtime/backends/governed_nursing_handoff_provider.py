"""Governed local Provider for documented nursing shift handoff extraction."""

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


class GovernedNursingHandoffProvider:
    provider_id = "icoder.governed-nursing-handoff.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/NursingHandoffOutput/v4"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.nursing_handoff.agent import (
                verify_nursing_handoff_health,
            )

            evidence = verify_nursing_handoff_health()
            return ProviderHealth(
                state="ok",
                latency_ms=0,
                details={
                    "provider_id": self.provider_id,
                    "backend_type": self.backend_type,
                    **evidence,
                },
            )
        except Exception as exc:
            return ProviderHealth(
                state="down",
                details={
                    "provider_id": self.provider_id,
                    "error": f"nursing_handoff_health_failed:{type(exc).__name__}",
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
            from official_agents.nursing_handoff.agent import (
                build_nursing_handoff,
                to_pack_output,
            )

            input_data = dict(req.input or {})
            text = str(input_data.get("text") or req.user_input or ctx.redacted_input or "")
            internal = build_nursing_handoff(text, run_id=ctx.run_id)
            public = to_pack_output(internal)
            input_required = internal.get("handoff_status") == "INPUT_REQUIRED"
            status: ProviderStatus = "incomplete" if input_required else "requires_review"
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._emit_backend_metadata(ctx, internal, latency_ms, status)
            return BackendResponse(
                status=status,
                summary=(
                    "请按患者分区并明确标注护理交班字段。"
                    if input_required
                    else (
                        f"已整理 {internal['_trace']['patient_count']} 个明确患者分区、"
                        f"{internal['_trace']['evidence_items_count']} 条原文证据；"
                        "未评估病情优先级或生成新护理措施，须接班护士复核。"
                    )
                ),
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="input-required" if input_required else "completed",
                finish_reason="labelled_handoff_sections_required" if input_required else None,
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                fallback_used=False,
                raw_provider_response=dict(internal),
                markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
                evidence_refs=[],
                trace_refs=[f"{ctx.run_id}:governed-nursing-handoff"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "GovernedNursingHandoffProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(ctx, {}, latency_ms, "fail")
            return BackendResponse(
                status="fail",
                summary="本地护理交班无法安全执行。",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=f"governed_nursing_handoff_error:{type(exc).__name__}",
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
                "Extracts up to ten explicitly labelled patient handoff sections "
                "with exact spans and stable SBAR-shaped presentation. It does not "
                "infer acuity, priority, device condition, orders or escalation thresholds."
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
                evidence_items_count=int(trace.get("evidence_items_count") or 0),
                valid_evidence_spans_count=int(trace.get("valid_spans_count") or 0),
                invalid_evidence_spans_count=max(
                    int(trace.get("evidence_items_count") or 0)
                    - int(trace.get("valid_spans_count") or 0),
                    0,
                ),
                candidate_codes_count=0,
                store=get_default_store(),
            )
        except Exception as exc:
            logger.warning(
                "GovernedNursingHandoffProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["GovernedNursingHandoffProvider"]
