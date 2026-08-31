"""Governed local Provider for explicit procedure extraction."""

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


class GovernedProcedureExtractorProvider:
    provider_id = "icoder.governed-procedure-extractor.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/ProcedureCodingOutput/v8"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.procedure_extractor.agent import (
                verify_procedure_extractor_health,
            )

            evidence = verify_procedure_extractor_health()
            asset = evidence.get("asset") or {}
            return ProviderHealth(
                state="ok",
                latency_ms=0,
                details={
                    "provider_id": self.provider_id,
                    "backend_type": self.backend_type,
                    "network_required": False,
                    "llm_required": False,
                    "integrity_verified": True,
                    "asset_id": asset.get("asset_id"),
                    "asset_version": asset.get("version"),
                    "authority_status": asset.get("authority_status"),
                    "license_status": asset.get("license_status"),
                    "billing_authoritative": False,
                    "catalog_count": evidence.get("catalog_count"),
                    "term_index_count": evidence.get("term_index_count"),
                    "clinical_appropriateness_assessed": False,
                    "production_writeback_blocked": True,
                },
            )
        except Exception as exc:
            return ProviderHealth(
                state="down",
                details={
                    "provider_id": self.provider_id,
                    "error": f"procedure_extractor_health_failed:{type(exc).__name__}",
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
            from official_agents.procedure_extractor.agent import (
                extract_procedures,
                to_pack_output,
            )

            input_data = dict(req.input or {})
            text = str(input_data.get("text") or req.user_input or ctx.redacted_input or "")
            internal = extract_procedures(text)
            public = to_pack_output(internal)
            input_required = not bool(text.strip())
            status: ProviderStatus = "incomplete" if input_required else "requires_review"
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._emit_backend_metadata(
                ctx,
                internal=internal,
                latency_ms=latency_ms,
                status=status,
            )
            return BackendResponse(
                status=status,
                summary=(
                    "请提供已脱敏的手术或操作记录。"
                    if input_required
                    else (
                        f"已定位 {len(public['procedures'])} 个已实施术式和 "
                        f"{len(public['non_billable_mentions'])} 个非计费状态提及；"
                        "所有结果须编码员复核。"
                    )
                ),
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="input-required" if input_required else "completed",
                finish_reason="procedure_source_required" if input_required else None,
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                fallback_used=False,
                raw_provider_response=dict(internal),
                markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
                evidence_refs=[],
                trace_refs=[f"{ctx.run_id}:governed-procedure-extraction"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "GovernedProcedureExtractorProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(
                ctx,
                internal={},
                latency_ms=latency_ms,
                status="fail",
            )
            return BackendResponse(
                status="fail",
                summary="本地手术操作提取无法安全执行。",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=f"governed_procedure_extraction_error:{type(exc).__name__}",
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
                "Extracts explicit procedure mentions and statuses with exact source "
                "spans. Codes are emitted only for unique governed ICD-9-CM-3 catalog "
                "matches; clinical appropriateness and billing authority are not assessed."
            ),
        )

    def _emit_backend_metadata(
        self,
        ctx: AgentRunContext,
        *,
        internal: dict[str, Any],
        latency_ms: int,
        status: ProviderStatus,
    ) -> None:
        try:
            from app.icoder.agent_runtime.orchestrator.run_trace import (
                emit_backend_metadata_event,
                get_default_store,
            )

            governance = internal.get("_catalog_governance") or {}
            procedures = internal.get("procedures") or []
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
                clinical_asset_ids=str(governance.get("asset_id") or ""),
                clinical_asset_versions=str(governance.get("version") or ""),
                clinical_asset_authority_statuses=str(
                    governance.get("authority_status") or ""
                ),
                clinical_asset_license_statuses=str(
                    governance.get("license_status") or ""
                ),
                clinical_asset_integrity_verified=bool(governance),
                candidate_codes_count=sum(
                    1 for item in procedures if str(item.get("code") or "")
                ),
                evidence_items_count=len(procedures)
                + len(internal.get("non_billable_mentions") or []),
                store=get_default_store(),
            )
        except Exception as exc:
            logger.warning(
                "GovernedProcedureExtractorProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["GovernedProcedureExtractorProvider"]
