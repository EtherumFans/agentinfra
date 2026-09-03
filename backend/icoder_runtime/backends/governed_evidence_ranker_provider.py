"""Deterministic evidence documentation-grounding provider."""

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


class GovernedEvidenceRankerProvider:
    provider_id = "icoder.governed-evidence-ranker.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/EvidenceRankerOutput/v4"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.evidence_ranker.agent import verify_ranker_health

            evidence = verify_ranker_health()
            return ProviderHealth(
                state="ok",
                latency_ms=0,
                details={
                    "provider_id": self.provider_id,
                    "backend_type": self.backend_type,
                    "policy_id": evidence["policy_id"],
                    "policy_version": evidence["policy_version"],
                    "network_required": False,
                    "llm_required": False,
                    "clinical_support_assessed": False,
                },
            )
        except Exception as exc:
            return ProviderHealth(
                state="down",
                details={
                    "provider_id": self.provider_id,
                    "error": f"evidence_ranker_health_failed:{type(exc).__name__}",
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
            from official_agents.evidence_ranker.agent import (
                run,
                to_current_pack_candidate,
            )

            input_data = dict(req.input or {})
            text = str(input_data.get("text") or req.user_input or "")
            internal = await run(text, run_id=ctx.run_id, structured_input=input_data)
            public = to_current_pack_candidate(internal)
            input_required = public.get("ranking_status") == "INPUT_REQUIRED"
            status: ProviderStatus = "incomplete" if input_required else "requires_review"
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._emit_backend_metadata(ctx, internal, latency_ms, status)
            return BackendResponse(
                status=status,
                summary=str(public.get("summary") or "证据文档可追溯性排序已完成。"),
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="input-required" if input_required else "completed",
                finish_reason="explicit_evidence_items_required" if input_required else None,
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                fallback_used=False,
                raw_provider_response=dict(internal),
                markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
                trace_refs=[f"{ctx.run_id}:governed-evidence-ranking"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "GovernedEvidenceRankerProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(ctx, {}, latency_ms, "fail")
            return BackendResponse(
                status="fail",
                summary="证据文档可追溯性排序无法安全执行。",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=f"governed_evidence_ranking_error:{type(exc).__name__}",
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
            )

    async def stream(self, req: BackendRequest, ctx: AgentRunContext) -> AsyncIterator[Any]:
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
                "Ranks explicit evidence by source/span traceability only. It does "
                "not assess clinical support, diagnosis validity, or coding correctness."
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

            trace_refs = internal.get("trace_refs") or {}
            output_contract = str(
                (ctx.agent_pack.get("output_contract") or {}).get("schema_ref")
                or self.output_contract()
            )
            emit_backend_metadata_event(
                ctx.run_id,
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                provider_latency_ms=latency_ms,
                provider_status=status,
                provider_deterministic=True,
                supports_tool_calling=False,
                fallback_used=False,
                output_contract=output_contract,
                tool_rounds=0,
                model_cost_usd=0.0,
                llm_call_count=0,
                evidence_items_count=int(trace_refs.get("evidence_items_count") or 0),
                valid_evidence_spans_count=int(
                    trace_refs.get("valid_evidence_spans_count") or 0
                ),
                invalid_evidence_spans_count=int(
                    trace_refs.get("invalid_evidence_spans_count") or 0
                ),
                evidence_source_coverage_ratio=float(
                    trace_refs.get("evidence_source_coverage_ratio") or 0.0
                ),
                store=get_default_store(),
            )
        except Exception as exc:
            logger.warning(
                "GovernedEvidenceRankerProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["GovernedEvidenceRankerProvider"]
