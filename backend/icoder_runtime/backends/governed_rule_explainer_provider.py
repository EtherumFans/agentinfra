"""Governed local Provider for catalog-only ICD-10-CN rule explanation."""

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


class GovernedRuleExplainerProvider:
    provider_id = "icoder.governed-rule-explainer.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/RuleExplanationOutput/v4"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.rule_explainer.agent import (
                verify_rule_explainer_health,
            )

            evidence = verify_rule_explainer_health()
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
                    "governed_instructional_notes_available": False,
                    "production_writeback_blocked": True,
                },
            )
        except Exception as exc:
            return ProviderHealth(
                state="down",
                details={
                    "provider_id": self.provider_id,
                    "error": f"rule_explainer_health_failed:{type(exc).__name__}",
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
            from official_agents.rule_explainer.agent import explain_code, to_pack_output

            input_data = dict(req.input or {})
            text = str(input_data.get("text") or req.user_input or ctx.redacted_input or "")
            internal = explain_code(
                text,
                run_id=ctx.run_id,
                structured_input=input_data,
            )
            public = to_pack_output(internal)
            unavailable = internal.get("runtime_mode") == "catalog_governance_unavailable"
            input_required = internal.get("catalog_status") == "INPUT_REQUIRED"
            status: ProviderStatus = (
                "fail" if unavailable else "incomplete" if input_required else "requires_review"
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._emit_backend_metadata(ctx, internal, latency_ms, status)
            return BackendResponse(
                status=status,
                summary=str(public.get("explanation_summary") or "目录事实解释已完成。"),
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state=(
                    "failed" if unavailable else "input-required" if input_required else "completed"
                ),
                finish_reason=(
                    "catalog_governance_unavailable"
                    if unavailable
                    else "code_required" if input_required else None
                ),
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                fallback_used=False,
                raw_provider_response=dict(internal),
                markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
                evidence_refs=list(public.get("evidence_refs") or []),
                trace_refs=[f"{ctx.run_id}:governed-rule-explanation"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "GovernedRuleExplainerProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(ctx, {}, latency_ms, "fail")
            return BackendResponse(
                status="fail",
                summary="本地规则解释无法安全执行。",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=f"governed_rule_explanation_error:{type(exc).__name__}",
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
                "Explains only hash-pinned ICD-10-CN catalog membership, name, "
                "chapter, hierarchy, and assignable-leaf facts. Governed rule "
                "notes are unavailable and are never guessed."
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
                clinical_asset_ids="+".join(
                    str(item) for item in (trace_refs.get("catalog_asset_ids") or []) if item
                ),
                clinical_asset_versions="+".join(
                    str(item) for item in (trace_refs.get("catalog_asset_versions") or []) if item
                ),
                clinical_asset_authority_statuses="+".join(
                    str(item)
                    for item in (trace_refs.get("catalog_authority_statuses") or [])
                    if item
                ),
                clinical_asset_license_statuses="+".join(
                    str(item)
                    for item in (trace_refs.get("catalog_license_statuses") or [])
                    if item
                ),
                clinical_asset_integrity_verified=bool(
                    trace_refs.get("catalog_integrity_verified")
                ),
                evidence_items_count=int(trace_refs.get("catalog_facts_count") or 0),
                store=get_default_store(),
            )
        except Exception as exc:
            logger.warning(
                "GovernedRuleExplainerProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["GovernedRuleExplainerProvider"]
