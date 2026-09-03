"""Hybrid Code Validation provider with a governed local catalog baseline.

The provider always executes deterministic membership/assignability checks
against hash-pinned development catalogs.  A separately gated LLM-with-tools
review may append cross-code observations, but it cannot alter catalog facts.
Unverified catalog provenance keeps every successful result human-review-only.
"""

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


class GovernedCodeValidationProvider:
    """Catalog-grounded validation with optional semantic enhancement."""

    provider_id = "icoder.governed-code-validation.v1"
    backend_type: BackendType = "hybrid"
    supports_tool_calling = True
    supports_streaming = False
    deterministic = False
    _OUTPUT_CONTRACT_REF = "icoder/CodeValidationOutput/v7"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.code_validation.catalog_validation import (
                verify_catalog_health,
            )

            evidence = verify_catalog_health()
            assets = evidence.get("assets") or []
            return ProviderHealth(
                state="ok",
                latency_ms=0,
                details={
                    "provider_id": self.provider_id,
                    "backend_type": self.backend_type,
                    "network_required_for_baseline": False,
                    "development_only": True,
                    "integrity_verified": True,
                    "asset_ids": [item.get("asset_id") for item in assets],
                    "asset_versions": [item.get("version") for item in assets],
                    "catalog_counts": evidence.get("catalog_counts") or {},
                },
            )
        except Exception as exc:
            return ProviderHealth(
                state="down",
                details={
                    "provider_id": self.provider_id,
                    "error": f"catalog_health_failed:{type(exc).__name__}",
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
            from official_agents.code_validation.agent import (
                run,
                to_current_pack_candidate,
            )

            input_data = dict(req.input or {})
            text = str(input_data.get("text") or req.user_input or "")
            internal = await run(
                text,
                run_id=ctx.run_id,
                structured_input=input_data,
            )
            public = to_current_pack_candidate(internal)
            unavailable = (
                internal.get("runtime_mode") == "catalog_governance_unavailable"
            )
            status: ProviderStatus = "fail" if unavailable else "requires_review"
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._emit_backend_metadata(ctx, internal, latency_ms, status)
            trace_refs = internal.get("trace_refs") or {}
            return BackendResponse(
                status=status,
                summary=str(public.get("summary") or "编码校验已完成。"),
                latency_ms=latency_ms,
                cost_usd=float(trace_refs.get("model_cost_usd") or 0.0),
                finish_state="failed" if unavailable else "completed",
                finish_reason=(
                    "catalog_governance_unavailable" if unavailable else None
                ),
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                fallback_used=False,
                raw_provider_response=dict(internal),
                markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
                trace_refs=[f"{ctx.run_id}:governed-code-validation"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "GovernedCodeValidationProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(ctx, {}, latency_ms, "fail")
            return BackendResponse(
                status="fail",
                summary="治理目录编码校验无法安全执行。",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=f"governed_code_validation_error:{type(exc).__name__}",
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
            supports_tool_calling=self.supports_tool_calling,
            supports_streaming=self.supports_streaming,
            deterministic=self.deterministic,
            default_output_contract=self._OUTPUT_CONTRACT_REF,
            supported_tools=[
                "verify_code",
                "get_guidelines",
                "explore_code",
                "search_codes",
            ],
            description=(
                "Hash-pinned local ICD catalog membership/assignability baseline "
                "with separately gated LLM cross-code review. Local catalog facts "
                "cannot be overridden by the model."
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
                provider_deterministic=not bool(
                    trace_refs.get("semantic_enhancement_used")
                ),
                supports_tool_calling=self.supports_tool_calling,
                fallback_used=False,
                output_contract=output_contract,
                tool_rounds=int(trace_refs.get("semantic_tool_calls_count") or 0),
                model_cost_usd=float(trace_refs.get("model_cost_usd") or 0.0),
                llm_call_count=(
                    1 if trace_refs.get("semantic_enhancement_used") else 0
                ),
                clinical_asset_ids="+".join(
                    str(item)
                    for item in (trace_refs.get("catalog_asset_ids") or [])
                    if item
                ),
                clinical_asset_versions="+".join(
                    str(item)
                    for item in (trace_refs.get("catalog_asset_versions") or [])
                    if item
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
                semantic_enhancement_used=bool(
                    trace_refs.get("semantic_enhancement_used")
                ),
                store=get_default_store(),
            )
        except Exception as exc:
            logger.warning(
                "GovernedCodeValidationProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["GovernedCodeValidationProvider"]
