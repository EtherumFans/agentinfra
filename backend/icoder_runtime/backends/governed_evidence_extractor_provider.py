"""Governed local exact-mention Evidence Extractor provider."""

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


class GovernedEvidenceExtractorProvider:
    provider_id = "icoder.governed-evidence-extractor.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/CodedEvidence/v11"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.evidence_extractor.agent import verify_extractor_health

            evidence = verify_extractor_health()
            asset = evidence.get("asset") or {}
            return ProviderHealth(
                state="ok",
                latency_ms=0,
                details={
                    "provider_id": self.provider_id,
                    "backend_type": self.backend_type,
                    "network_required": False,
                    "llm_required": False,
                    "clinical_support_assessed": False,
                    "integrity_verified": True,
                    "asset_id": asset.get("asset_id"),
                    "asset_version": asset.get("version"),
                    "catalog_count": evidence.get("catalog_count"),
                    "term_index_count": evidence.get("term_index_count"),
                },
            )
        except Exception as exc:
            return ProviderHealth(
                state="down",
                details={
                    "provider_id": self.provider_id,
                    "error": f"evidence_extractor_health_failed:{type(exc).__name__}",
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
            from official_agents.evidence_extractor.agent import (
                run,
                to_current_pack_candidate,
            )

            input_data = dict(req.input or {})
            text = str(input_data.get("text") or req.user_input or "")
            internal = await run(text, run_id=ctx.run_id, structured_input=input_data)
            public = to_current_pack_candidate(internal)
            state = str(public.get("extraction_status") or "")
            unavailable = state == "CATALOG_UNAVAILABLE"
            input_required = state == "INPUT_REQUIRED"
            status: ProviderStatus = (
                "fail" if unavailable else "incomplete" if input_required else "requires_review"
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._emit_backend_metadata(ctx, internal, latency_ms, status)
            return BackendResponse(
                status=status,
                summary=str(public.get("summary") or "编码候选精确证据提及定位已完成。"),
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed" if unavailable else "input-required" if input_required else "completed",
                finish_reason=(
                    "catalog_governance_unavailable" if unavailable
                    else "explicit_candidate_codes_required" if input_required
                    else None
                ),
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                fallback_used=False,
                raw_provider_response=dict(internal),
                markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
                trace_refs=[f"{ctx.run_id}:governed-evidence-extraction"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "GovernedEvidenceExtractorProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(ctx, {}, latency_ms, "fail")
            return BackendResponse(
                status="fail",
                summary="编码候选精确证据提及定位无法安全执行。",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=f"governed_evidence_extraction_error:{type(exc).__name__}",
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
                "Locates exact submitted-code literals or hash-pinned ICD-10-CN "
                "catalog terms. It does not assess clinical support or code validity."
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
                clinical_asset_ids="+".join(trace_refs.get("catalog_asset_ids") or []),
                clinical_asset_versions="+".join(trace_refs.get("catalog_asset_versions") or []),
                clinical_asset_authority_statuses="+".join(
                    trace_refs.get("catalog_authority_statuses") or []
                ),
                clinical_asset_license_statuses="+".join(
                    trace_refs.get("catalog_license_statuses") or []
                ),
                clinical_asset_integrity_verified=bool(
                    trace_refs.get("catalog_integrity_verified")
                ),
                evidence_input_codes_count=int(
                    trace_refs.get("evidence_input_codes_count") or 0
                ),
                evidence_located_mentions_count=int(
                    trace_refs.get("evidence_located_mentions_count") or 0
                ),
                evidence_unmatched_codes_count=int(
                    trace_refs.get("evidence_unmatched_codes_count") or 0
                ),
                store=get_default_store(),
            )
        except Exception as exc:
            logger.warning(
                "GovernedEvidenceExtractorProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["GovernedEvidenceExtractorProvider"]
