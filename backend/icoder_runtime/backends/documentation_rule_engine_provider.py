"""Deterministic documentation-completeness provider.

This provider exposes the local Chinese medical-record documentation rules through
the same ``AgentBackendProvider`` contract used by the unified Run facade.  It
does not call an LLM or a network service.  Its scope is deliberately narrow:
it verifies presence and non-empty content for the required 7+1 sections and
performs bounded explicit-literal checks (currently spinal-level consistency).
It does not claim broad semantic consistency or clinical correctness.
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


class DocumentationRuleEngineProvider:
    """Run deterministic Chinese documentation-section checks."""

    provider_id = "icoder.documentation-rule-engine.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/NoteCompletenessOutput/v2"

    async def health(self) -> ProviderHealth:
        try:
            from official_agents.note_completeness.agent import run_deterministic

            if not callable(run_deterministic):
                raise RuntimeError("documentation_rule_entrypoint_unavailable")
            return ProviderHealth(
                state="ok",
                latency_ms=0,
                details={
                    "provider_id": self.provider_id,
                    "backend_type": self.backend_type,
                    "network_required": False,
                },
            )
        except Exception as exc:
            return ProviderHealth(
                state="down",
                details={"error": f"provider_unavailable:{type(exc).__name__}"},
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
            from official_agents.note_completeness.agent import (
                run_deterministic,
                to_current_pack_candidate,
            )

            input_data = req.input or {}
            text = str(input_data.get("text") or req.user_input or "")
            internal = await run_deterministic(text, run_id=ctx.run_id)
            public = to_current_pack_candidate(internal)
            conclusion = str(public.get("review_conclusion") or "FAIL").upper()
            status: ProviderStatus = (
                "requires_review"
                if str((ctx.agent_pack.get("manifest") or {}).get("human_review") or "")
                == "required"
                else {"PASS": "pass", "WARNING": "warning"}.get(conclusion, "fail")
            )  # type: ignore[assignment]
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._emit_backend_metadata(ctx, latency_ms, status)
            return BackendResponse(
                status=status,
                summary=(
                    f"Documentation completeness {conclusion}: "
                    f"{len(public.get('missing_sections') or [])} missing and "
                    f"{len(public.get('incomplete_sections') or [])} incomplete section(s)."
                ),
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="completed",
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                raw_provider_response=dict(internal),
                markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
                trace_refs=[f"{ctx.run_id}:documentation-rules"],
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "DocumentationRuleEngineProvider.invoke failed error_type=%s",
                type(exc).__name__,
            )
            self._emit_backend_metadata(ctx, latency_ms, "fail")
            return BackendResponse(
                status="fail",
                summary="Documentation completeness rules could not be executed.",
                latency_ms=latency_ms,
                cost_usd=0.0,
                finish_state="failed",
                finish_reason=f"documentation_rule_error:{type(exc).__name__}",
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
            supported_tools=[],
            description=(
                "Deterministic Chinese medical-record 7+1 section presence, "
                "non-empty-content, and bounded explicit-literal consistency "
                "checks; broader semantic review remains human-owned."
            ),
        )

    def _emit_backend_metadata(
        self,
        ctx: AgentRunContext,
        latency_ms: int,
        status: ProviderStatus,
    ) -> None:
        try:
            from app.icoder.agent_runtime.orchestrator.run_trace import (
                emit_backend_metadata_event,
                get_default_store,
            )

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
                store=get_default_store(),
            )
        except Exception as exc:
            logger.warning(
                "DocumentationRuleEngineProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = ["DocumentationRuleEngineProvider"]
