"""Governed local Provider for documented discharge-summary sections."""

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


class GovernedDischargeSummaryProvider:
    provider_id = "icoder.governed-discharge-summary.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/DischargeSummaryStructured/v5"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.discharge_summary_structuring.agent import (
                verify_discharge_summary_health,
            )

            evidence = verify_discharge_summary_health()
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
                    "error": (
                        "discharge_summary_health_failed:"
                        f"{type(exc).__name__}"
                    ),
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
            from official_agents.discharge_summary_structuring.agent import (
                build_discharge_summary,
                to_pack_output,
            )

            input_data = dict(req.input or {})
            text = str(
                input_data.get("text")
                or req.user_input
                or ctx.redacted_input
                or ""
            )
            internal = build_discharge_summary(text, run_id=ctx.run_id)
            public = to_pack_output(internal)
            input_required = internal.get("structuring_status") == "INPUT_REQUIRED"
            status: ProviderStatus = "incomplete" if input_required else "requires_review"
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._emit_backend_metadata(ctx, internal, latency_ms, status)
            return BackendResponse(
                status=status,
                summary=(
                    "请提供带明确章节标题的出院小结。"
                    if input_required
                    else (
                        f"已整理 {internal['_trace']['evidence_items_count']} 条出院小结原文证据；"
                        "未推断临床事实、分配编码、重整用药或新增医嘱，须临床人员复核。"
                    )
                ),
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="input-required" if input_required else "completed",
                finish_reason=(
                    "labelled_discharge_summary_sections_required"
                    if input_required
                    else None
                ),
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                fallback_used=False,
                raw_provider_response=dict(internal),
                markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
                evidence_refs=[],
                trace_refs=[f"{ctx.run_id}:governed-discharge-summary"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "GovernedDischargeSummaryProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(ctx, {}, latency_ms, "fail")
            return BackendResponse(
                status="fail",
                summary="本地出院小结结构化无法安全执行。",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=(
                    "governed_discharge_summary_error:"
                    f"{type(exc).__name__}"
                ),
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
                "Reorganizes explicitly headed, possibly multi-line discharge-summary "
                "sections with exact spans. It does not summarize unlabelled narrative, "
                "infer diagnoses, assign codes, reconcile medications, add instructions, "
                "or write to the health record."
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
                "GovernedDischargeSummaryProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["GovernedDischargeSummaryProvider"]
