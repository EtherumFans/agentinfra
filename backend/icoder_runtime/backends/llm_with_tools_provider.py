"""LLMWithToolsProvider — LLM backend with MCP tool calls.

The provider is production fail-closed.  Tool dispatch only occurs when a
real LLM client (or the application-wide gateway) requests a tool call; a
missing LLM must never execute a guessed tool or manufacture a successful
clinical response.

Phase 4-C (2026-07-08): real LLM tool-calling loop. Mirrors the
Corti Code Validation Agent architecture (LLM + 4 mandatory tools
verify/guidelines/explore/search). The loop:

  1. Build OpenAI-style tool schemas from ``req.tool_scope``.
  2. Call ``llm_client.complete_messages(messages, tools)``.
  3. If response has ``tool_calls`` → for each call:
     a. ``ToolMCPCompatLayer.provider_to_mcp`` → MCP request.
     b. ``ToolMCPCompatLayer.call`` → routes through ``dispatch_tool``.
     c. ``ToolMCPCompatLayer.to_tool_call_record`` → ``ToolCallRecord``.
     d. Append ``{"role": "assistant", "tool_calls": [...]}`` and
        ``{"role": "tool", "tool_call_id": ..., "content": ...}``
        to the messages list.
  4. Re-call LLM with the extended messages.
  5. Loop until LLM stops requesting tools or ``max_tool_rounds`` hit.

Provider metadata:
  - ``provider_id = "icoder.llm-with-tools.v1"``
  - ``backend_type = "llm_with_tools"``
  - ``supports_tool_calling = True``
  - ``supports_streaming = True``
  - ``deterministic = False``
  - ``max_tool_rounds = 8`` (Corti Code Validation uses ~4-8 rounds)

Hard rules:
  1. Every tool call routes through ``ToolMCPCompatLayer.call`` →
     ``dispatch_tool`` — no direct handler invocation.
  2. ``required_scopes`` enforced by ``ToolMCPCompatLayer.validate_tool_scope``.
  3. Tool result loopback uses ``ToolCallResponse.to_provider_result()``
     (PHI-safe — only ``redacted_view`` is surfaced on ``ToolCallRecord``).
  4. RunTrace: ``_emit_backend_metadata`` fires after every invoke with
     ``tool_rounds`` populated. Per-tool ``TOOLS_CALL`` events are
     emitted by ``dispatch_tool`` itself.
  5. ``max_tool_rounds`` cap prevents infinite loops. Exceeding the
     cap returns ``status="incomplete"`` with what we have so far.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Callable

from .contracts import (
    AgentBackendProvider,
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    BackendType,
    ProviderCapability,
    ProviderHealth,
    ProviderStatus,
    ToolCallRecord,
)
from .pure_llm_provider import (
    LLMClient,
    LLMResponse,
    _append_pack_contract_instruction,
    _is_incomplete_finish_reason,
    _model_telemetry_from_raw,
    _pack_output_contract,
    _redact_untrusted_instruction_echo,
)
from .tool_mcp_compat_layer import ToolMCPCompatLayer, ToolCallResponse

logger = logging.getLogger(__name__)


def _accumulate_cost(total: float | None, incremental: float | None) -> float | None:
    """Sum billed model calls while preserving an entirely unknown total."""
    if incremental is None:
        return total
    return round((total or 0.0) + float(incremental), 12)


def _accumulate_model_telemetry(
    aggregate: dict[str, Any],
    raw: Any,
) -> None:
    """Accumulate bounded telemetry across a multi-round LLM/tool loop."""

    current = _model_telemetry_from_raw(raw)
    for key in ("model_provider", "model_system", "model_name"):
        value = current.get(key)
        if not value:
            continue
        existing = aggregate.get(key)
        if existing and existing != value:
            aggregate[key] = "mixed"
        else:
            aggregate[key] = value
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = current.get(key)
        if value is not None:
            aggregate[key] = int(aggregate.get(key) or 0) + int(value)


# ── Provider ───────────────────────────────────────────────────────────


class LLMWithToolsProvider:
    """LLM backend with MCP tool calls.

    Phase 4-C: real tool-calling loop. The provider NEVER sees raw
    PHI — ``AgentRunContext.redacted_input`` is the only user-side
    text it reads. Tool arguments are stripped of secret keys by
    ``ToolMCPCompatLayer._strip_secret_keys`` before MCP dispatch
    (defense-in-depth — ``dispatch_tool`` redacts again).
    """

    provider_id: str = "icoder.llm-with-tools.v1"
    backend_type: BackendType = "llm_with_tools"
    supports_tool_calling: bool = True
    supports_streaming: bool = True
    deterministic: bool = False

    _OUTPUT_CONTRACT_REF: str = "icoder/LLMWithToolsOutput/v1"

    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        mcp_layer: ToolMCPCompatLayer | None = None,
        default_temperature: float = 0.0,
        max_tool_rounds: int = 8,
    ) -> None:
        self._llm_client = llm_client
        self._mcp_layer = mcp_layer or ToolMCPCompatLayer()
        self._default_temperature = default_temperature
        self._max_tool_rounds = max_tool_rounds

    # ── AgentBackendProvider protocol ─────────────────────────────

    async def health(self) -> ProviderHealth:
        client = self._resolve_client()
        if client is None:
            return ProviderHealth(
                state="degraded",
                details={"note": "no application LLM gateway is configured"},
            )
        configuration_status = getattr(client, "configuration_status", None)
        if callable(configuration_status):
            snapshot = configuration_status()
            if snapshot.get("status") != "configured":
                return ProviderHealth(state="degraded", details=dict(snapshot))
            return ProviderHealth(
                state="ok",
                details={
                    "provider_id": self.provider_id,
                    "backend_type": self.backend_type,
                    "max_tool_rounds": self._max_tool_rounds,
                    **snapshot,
                },
            )
        return ProviderHealth(
            state="ok",
            details={"provider_id": self.provider_id,
                     "backend_type": self.backend_type,
                     "max_tool_rounds": self._max_tool_rounds,
                     "configuration_status": "injected_client",
                     "live_health_verified": False},
        )

    async def invoke(
        self, req: BackendRequest, ctx: AgentRunContext,
        *,
        request: Any = None,
    ) -> BackendResponse:
        """LLM completion with at most ``max_tool_rounds`` tool-call rounds.

        Phase 5 Track C Gate 1 (2026-07-11): lazy-resolve ``llm_client``
        via ``registry.get_gateway()`` (same pattern as
        ``PureLLMProvider._resolve_client``). Registry-created providers
        therefore use the application gateway without a constructor-level
        client dependency.

        If lazy resolution cannot find an LLM client, return a failed backend
        envelope.  Offline contract tests inject a mock client explicitly.

        ``request`` is the FastAPI ``Request`` (or stand-in) needed by
        ``dispatch_tool`` to read ``app.state``. In-process callers
        construct a lightweight stand-in (see
        ``app.main.py:_handle_simple`` for the established pattern).
        """
        t0 = time.perf_counter()
        system_prompt = _append_pack_contract_instruction(
            req.system_prompt or _extract_system_prompt(ctx),
            ctx.agent_pack,
        )
        user_input = req.user_input or ctx.redacted_input or _extract_user_input(req)

        # Validate tool scope config (mandatory ⊆ scope, forbidden ∩ scope = ∅).
        scope_ok, scope_errors = self._mcp_layer.validate_tool_scope(
            req.tool_scope,
            mandatory=(
                list(req.mandatory_tools)
                + [
                    str(tool)
                    for policy in req.conditional_mandatory_tools
                    for tool in (policy.get("tools") or [])
                ]
            ),
            forbidden=req.forbidden_tools,
        )
        if not scope_ok:
            return self._fail(
                f"tool_scope invalid: {scope_errors}",
                t0, ctx,
            )

        # Track C Gate 1: lazy-resolve llm_client if not explicitly wired.
        client = self._resolve_client()
        if client is None:
            return self._fail(
                "llm_unavailable: no llm_client and no application gateway wired",
                t0,
                ctx,
            )

        try:
            return await self._real_llm_pipeline(
                req=req, ctx=ctx, system_prompt=system_prompt,
                user_input=user_input, request=request, t0=t0,
            )
        except Exception as e:
            logger.error(
                "LLMWithToolsProvider.invoke failed error_type=%s",
                type(e).__name__,
            )
            return self._fail(
                f"llm_error: {type(e).__name__}",
                t0, ctx,
            )

    async def stream(
        self, req: BackendRequest, ctx: AgentRunContext,
        *,
        request: Any = None,
    ) -> AsyncIterator[Any]:
        """Streaming LLM with tools.

        Current implementation consumes provider-native text/tool/usage/reset
        events while the canonical MCP loop is running. Provisional payloads
        are internal; the final normalized response remains authoritative.

        Historical Phase 4-C behavior emitted a sequence derived from invoke
        path (real streaming with interleaved tool calls is Phase 4-D
        scope — DeepSeek SSE):

          1. ``{"step": "backend_invoked", "payload": BackendResponse}``
          2. ``{"step": "tool_calls", "payload": ToolCallRecord}`` (per call)
          3. ``{"step": "output_chunk", "payload": {"delta": str}}``
          4. ``{"step": "finished", "payload": {"state": "completed"}}``
        """
        t0 = time.perf_counter()
        system_prompt = _append_pack_contract_instruction(
            req.system_prompt or _extract_system_prompt(ctx),
            ctx.agent_pack,
        )
        user_input = req.user_input or ctx.redacted_input or _extract_user_input(req)
        scope_ok, scope_errors = self._mcp_layer.validate_tool_scope(
            req.tool_scope,
            mandatory=(
                list(req.mandatory_tools)
                + [
                    str(tool)
                    for policy in req.conditional_mandatory_tools
                    for tool in (policy.get("tools") or [])
                ]
            ),
            forbidden=req.forbidden_tools,
        )
        if not scope_ok:
            resp = self._fail(f"tool_scope invalid: {scope_errors}", t0, ctx)
            yield {"step": "backend_invoked", "payload": resp}
            yield {"step": "finished", "payload": {"state": resp.finish_state}}
            return
        if self._resolve_client() is None:
            resp = self._fail(
                "llm_unavailable: no llm_client and no application gateway wired",
                t0,
                ctx,
            )
            yield {"step": "backend_invoked", "payload": resp}
            yield {"step": "finished", "payload": {"state": resp.finish_state}}
            return

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        task = asyncio.create_task(self._real_llm_pipeline(
            req=req,
            ctx=ctx,
            system_prompt=system_prompt,
            user_input=user_input,
            request=request,
            t0=t0,
            event_sink=queue.put_nowait,
        ))
        try:
            while not task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                except TimeoutError:
                    continue
                yield event
            resp = await task
        except Exception as exc:
            if not task.done():
                task.cancel()
            logger.error(
                "LLMWithToolsProvider.stream failed error_type=%s",
                type(exc).__name__,
            )
            resp = self._fail(f"llm_error: {type(exc).__name__}", t0, ctx)

        yield {"step": "backend_invoked", "payload": resp}
        for tc in resp.tool_calls:
            yield {"step": "tool_calls", "payload": tc}
        text = resp.markdown or ""
        for i in range(0, len(text), 200):
            yield {
                "step": "output_chunk",
                "payload": {"delta": text[i:i + 200], "native": False},
            }
        yield {"step": "finished", "payload": {"state": resp.finish_state}}

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
            supported_tools=[],  # populated by ToolMCPCompatLayer.list_available_tools
            description=(
                "LLM backend with MCP tool calls. Mirrors Corti Code "
                "Validation (4 tools) and Compliance Guardrail (3 tools, "
                "search forbidden) patterns. Phase 4-C: real tool-calling."
            ),
        )

    # ── Real LLM tool-calling pipeline (Phase 4-C) ─────────────────

    async def _real_llm_pipeline(
        self,
        *,
        req: BackendRequest,
        ctx: AgentRunContext,
        system_prompt: str,
        user_input: str,
        request: Any,
        t0: float,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> BackendResponse:
        """Phase 4-C real LLM tool-calling loop.

        See module docstring for the loop structure. Never raises —
        all exceptions become a ``BackendResponse(status="fail")``
        envelope via the caller's try/except in ``invoke``.
        """
        if not user_input:
            return self._fail(
                "empty user_input — LLMWithToolsProvider needs req.user_input "
                "or ctx.redacted_input", t0, ctx,
            )

        # 1. Build OpenAI-style tool schemas from the agent's tool_scope.
        tool_schemas = self._build_tool_schemas(req, ctx)
        # 2. Initialize messages: system + user.
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        total_cost: float | None = None
        llm_call_count = 0
        model_telemetry: dict[str, Any] = {}

        # Output-dependent tool policies require a no-tool classification
        # pass before tools are exposed.  This prevents a diagnosis extractor
        # from querying codes for mentions that are all negated, ruled out or
        # historical.  If the preflight cannot be parsed, the resolver fails
        # closed and the regular tool-enabled path remains available.
        if req.conditional_mandatory_tools:
            preflight = await self._call_llm(
                messages=messages + [{
                    "role": "system",
                    "content": (
                        "This is a tool-eligibility preflight, not the final "
                        "public response. No tools are available in this "
                        "round. Return only one JSON object with this exact "
                        "shape: {\"tool_eligibility\": {\"<output_path>\": "
                        "true_or_false}}. Include every conditional output "
                        "path named by the runtime policy. Set a path to true "
                        "when the supplied input contains qualifying content "
                        "that would make that final output path non-empty; "
                        "set it to false only when confidently empty. The "
                        "absence of tools or verified codes is never a reason "
                        "to set it to false. Do not emit the public output "
                        "contract and do not invent or verify codes."
                    ),
                }],
                tools=[],
                temperature=self._default_temperature,
                max_tokens=None,
                timeout_seconds=req.timeout_seconds,
                event_sink=event_sink,
            )
            llm_call_count += 1
            total_cost = _accumulate_cost(total_cost, preflight.cost_usd)
            _accumulate_model_telemetry(model_telemetry, preflight.raw)
            preflight_finish = str(preflight.finish_reason or "")
            if _is_incomplete_finish_reason(preflight_finish):
                return self._fail(
                    f"llm_incomplete: {preflight_finish}",
                    t0,
                    ctx,
                    cost_usd=total_cost,
                    llm_call_count=llm_call_count,
                    model_routing=_model_routing_from_raw(preflight.raw),
                    model_telemetry={
                        **model_telemetry,
                        "model_cost_usd": total_cost,
                        "finish_reason": preflight_finish,
                        "llm_call_count": llm_call_count,
                    },
                )
            if preflight_finish.startswith(("degraded", "gateway_error:")):
                return self._fail(
                    (
                        f"llm_degraded: {preflight_finish}"
                        if preflight_finish.startswith("degraded:")
                        else "llm_degraded: gateway_error"
                    ),
                    t0,
                    ctx,
                    fallback_used=preflight_finish.startswith("degraded"),
                    cost_usd=total_cost,
                    llm_call_count=llm_call_count,
                    model_routing=_model_routing_from_raw(preflight.raw),
                    model_telemetry={
                        **model_telemetry,
                        "model_cost_usd": total_cost,
                        "finish_reason": preflight_finish,
                        "llm_call_count": llm_call_count,
                    },
                )
            conditional_tools = _resolve_preflight_conditional_tools(
                preflight.text,
                req.conditional_mandatory_tools,
            )
            if not conditional_tools:
                tool_schemas = []
                logger.info(
                    "LLMWithToolsProvider conditional preflight withheld "
                    "all tools agent_id=%s",
                    ctx.agent_id,
                )
        all_tool_records: list[ToolCallRecord] = []
        tool_rounds = 0
        final_text = ""
        final_finish_reason = ""
        last_raw: dict[str, Any] = {}
        incomplete = False

        # 3. Tool-calling loop.
        while tool_rounds < self._max_tool_rounds:
            llm_resp = await self._call_llm(
                messages=messages, tools=tool_schemas,
                temperature=self._default_temperature,
                max_tokens=None, timeout_seconds=req.timeout_seconds,
                event_sink=event_sink,
            )
            llm_call_count += 1
            total_cost = _accumulate_cost(total_cost, llm_resp.cost_usd)
            _accumulate_model_telemetry(model_telemetry, llm_resp.raw)
            llm_finish_reason = str(llm_resp.finish_reason or "")
            if _is_incomplete_finish_reason(llm_finish_reason):
                return self._fail(
                    f"llm_incomplete: {llm_finish_reason}",
                    t0,
                    ctx,
                    cost_usd=total_cost,
                    tool_rounds=tool_rounds,
                    llm_call_count=llm_call_count,
                    model_routing=_model_routing_from_raw(llm_resp.raw),
                    model_telemetry={
                        **model_telemetry,
                        "model_cost_usd": total_cost,
                        "finish_reason": llm_finish_reason,
                        "llm_call_count": llm_call_count,
                    },
                )
            if llm_finish_reason.startswith(("degraded", "gateway_error:")):
                return self._fail(
                    (
                        f"llm_degraded: {llm_finish_reason}"
                        if llm_finish_reason.startswith("degraded:")
                        else "llm_degraded: gateway_error"
                    ),
                    t0,
                    ctx,
                    fallback_used=llm_finish_reason.startswith("degraded"),
                    cost_usd=total_cost,
                    tool_rounds=tool_rounds,
                    llm_call_count=llm_call_count,
                    model_routing=_model_routing_from_raw(llm_resp.raw),
                    model_telemetry={
                        **model_telemetry,
                        "model_cost_usd": total_cost,
                        "finish_reason": llm_finish_reason,
                        "llm_call_count": llm_call_count,
                    },
                )
            if llm_resp.text and not llm_resp.tool_calls:
                # Final response — LLM stopped calling tools.
                final_text = llm_resp.text
                final_finish_reason = llm_resp.finish_reason
                last_raw = llm_resp.raw
                break

            if not llm_resp.tool_calls:
                # No text AND no tool_calls — LLM produced nothing.
                final_text = llm_resp.text or ""
                final_finish_reason = llm_resp.finish_reason or "empty_response"
                last_raw = llm_resp.raw
                break

            # 4. LLM requested tool calls — process each.
            # Append the assistant message (with tool_calls) to messages
            # so the next LLM round sees the full conversation.
            messages.append({
                "role": "assistant",
                "content": llm_resp.text or None,
                "tool_calls": llm_resp.tool_calls,
            })

            for tc in llm_resp.tool_calls:
                record, tool_message = await self._dispatch_one_tool_call(
                    tc, ctx, request,
                    round_index=tool_rounds, caller="llm",
                )
                all_tool_records.append(record)
                messages.append(tool_message)
                if event_sink is not None:
                    event_sink({
                        "step": "tool_call_completed",
                        "payload": record,
                    })

            tool_rounds += 1
            last_raw = llm_resp.raw
        if (
            tool_rounds >= self._max_tool_rounds
            and not final_text
        ):
            # Loop exited via while-condition (max_tool_rounds hit)
            # without a clean break. Give the model one tools-disabled
            # synthesis round: mandatory evidence may already be complete,
            # and returning an incomplete markdown placeholder would violate
            # the owning Pack's public JSON contract. This round cannot
            # dispatch another tool, so the budget remains a hard cap.
            messages.append({
                "role": "system",
                "content": (
                    "Tool budget is exhausted. Do not request or call any "
                    "more tools. Using only the supplied input and successful "
                    "tool results already present above, return the final "
                    "JSON object required by the public output contract now."
                ),
            })
            synthesis_resp = await self._call_llm(
                messages=messages,
                tools=[],
                temperature=self._default_temperature,
                max_tokens=None,
                timeout_seconds=req.timeout_seconds,
                event_sink=event_sink,
            )
            llm_call_count += 1
            total_cost = _accumulate_cost(total_cost, synthesis_resp.cost_usd)
            _accumulate_model_telemetry(model_telemetry, synthesis_resp.raw)
            synthesis_finish_reason = str(synthesis_resp.finish_reason or "")
            if _is_incomplete_finish_reason(synthesis_finish_reason):
                return self._fail(
                    f"llm_incomplete: {synthesis_finish_reason}",
                    t0,
                    ctx,
                    cost_usd=total_cost,
                    tool_rounds=tool_rounds,
                    llm_call_count=llm_call_count,
                    model_routing=_model_routing_from_raw(synthesis_resp.raw),
                    model_telemetry={
                        **model_telemetry,
                        "model_cost_usd": total_cost,
                        "finish_reason": synthesis_finish_reason,
                        "llm_call_count": llm_call_count,
                    },
                )
            if synthesis_finish_reason.startswith(("degraded", "gateway_error:")):
                return self._fail(
                    (
                        f"llm_degraded: {synthesis_finish_reason}"
                        if synthesis_finish_reason.startswith("degraded:")
                        else "llm_degraded: gateway_error"
                    ),
                    t0,
                    ctx,
                    fallback_used=synthesis_finish_reason.startswith("degraded"),
                    cost_usd=total_cost,
                    tool_rounds=tool_rounds,
                    llm_call_count=llm_call_count,
                    model_routing=_model_routing_from_raw(synthesis_resp.raw),
                    model_telemetry={
                        **model_telemetry,
                        "model_cost_usd": total_cost,
                        "finish_reason": synthesis_finish_reason,
                        "llm_call_count": llm_call_count,
                    },
                )
            if synthesis_resp.text and not synthesis_resp.tool_calls:
                final_text = synthesis_resp.text
                final_finish_reason = "tool_budget_finalized"
                last_raw = synthesis_resp.raw
            else:
                incomplete = True
                final_finish_reason = (
                    f"max_tool_rounds_exceeded:{self._max_tool_rounds}"
                )

        # A declarative mandatory tool is a runtime contract, not merely a
        # prompt hint. A model that answers without successfully calling all
        # mandatory tools has not grounded its answer and cannot succeed.
        successful_tools = {
            record.tool_name for record in all_tool_records if not record.error
        }
        effective_mandatory = set(req.mandatory_tools)
        effective_mandatory.update(
            _resolve_conditional_mandatory_tools(
                final_text,
                req.conditional_mandatory_tools,
                ctx,
            )
        )
        missing_mandatory = sorted(effective_mandatory - successful_tools)
        if missing_mandatory:
            incomplete = True
            final_finish_reason = (
                "mandatory_tools_not_completed:"
                + ",".join(missing_mandatory)
            )
            final_text = _build_missing_mandatory_markdown(
                final_text, missing_mandatory,
            )

        # 5. Normalize to BackendResponse.  A model can reject a document
        # injection yet repeat its literal marker in the explanation; remove
        # that echo before structured projection and public serialization.
        final_text, echoed_markers = _redact_untrusted_instruction_echo(
            final_text, user_input,
        )
        if echoed_markers:
            logger.warning(
                "LLMWithToolsProvider redacted %d untrusted marker echo(es)",
                len(echoed_markers),
            )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if incomplete:
            status: ProviderStatus = "incomplete"
            finish_state = "completed"
            if not final_text:
                final_text = _build_incomplete_markdown(
                    tool_rounds, all_tool_records, user_input,
                )
        else:
            status = _parse_status_from_markdown(final_text)
            finish_state = "completed"

        # Detect degraded LLM responses (gateway returned a mock fallback).
        finish_reason_str = final_finish_reason or ""
        degraded = finish_reason_str.startswith("degraded")
        model_telemetry.update({
            "model_cost_usd": total_cost,
            "finish_reason": finish_reason_str,
            "llm_call_count": llm_call_count,
        })
        self._emit_backend_metadata(
            ctx, latency_ms, status,
            tool_rounds=tool_rounds, fallback_used=degraded,
            model_routing=_model_routing_from_raw(last_raw),
            model_telemetry=model_telemetry,
        )

        return BackendResponse(
            status=status,
            summary=_extract_first_paragraph(final_text),
            markdown=final_text,
            tool_calls=all_tool_records,
            backend_provider=self.provider_id,
            backend_type=self.backend_type,
            latency_ms=latency_ms,
            cost_usd=total_cost,
            finish_state=finish_state,
            finish_reason=final_finish_reason or None,
            raw_provider_response={
                **(last_raw or {}),
                "tool_rounds": tool_rounds,
                "tool_calls_count": len(all_tool_records),
                "llm_call_count": llm_call_count,
                "cost_usd_total": total_cost,
                "max_tool_rounds": self._max_tool_rounds,
                "incomplete": incomplete,
                "missing_mandatory_tools": missing_mandatory,
            },
            evidence_refs=[tc.tool_name for tc in all_tool_records],
            trace_refs=[ctx.run_id],
        )

    async def _call_llm(
        self, *, messages: list[dict[str, Any]],
        tools: list[dict[str, Any]], temperature: float,
        max_tokens: int | None, timeout_seconds: float,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> LLMResponse:
        """Call the LLM with the full messages list.

        Uses ``complete_messages`` if the client exposes it (the
        ``LLMGatewayAdapter`` does, Phase 4-C). Falls back to
        ``complete(system_prompt, user_input, tools)`` for the first
        round if the client only implements the single-shot Protocol —
        but multi-round loops require ``complete_messages``.
        """
        client = self._llm_client
        if event_sink is not None and hasattr(client, "stream_messages"):
            terminal: LLMResponse | None = None
            async for chunk in client.stream_messages(  # type: ignore[attr-defined]
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            ):
                event_type = getattr(chunk, "event_type", "text_delta")
                if event_type == "text_delta":
                    delta = getattr(chunk, "delta", "")
                    if isinstance(delta, str) and delta:
                        event_sink({
                            "step": "provider_text_delta",
                            "payload": {
                                "delta": delta,
                                "provider": getattr(chunk, "provider", ""),
                                "native": bool(getattr(chunk, "native", False)),
                                "provisional": True,
                            },
                        })
                elif event_type == "tool_call_delta":
                    raw_delta = dict(
                        getattr(chunk, "tool_call_delta", {}) or {}
                    )
                    fn = raw_delta.get("function")
                    event_sink({
                        "step": "provider_tool_call_delta",
                        "payload": {
                            "index": int(
                                getattr(chunk, "raw", {}).get("index", 0) or 0
                            ),
                            "id_present": bool(raw_delta.get("id")),
                            "name_fragment": (
                                str(fn.get("name") or "")
                                if isinstance(fn, dict)
                                else ""
                            ),
                            "argument_characters": (
                                len(str(fn.get("arguments") or ""))
                                if isinstance(fn, dict)
                                else 0
                            ),
                            "provider": getattr(chunk, "provider", ""),
                            "native": bool(getattr(chunk, "native", False)),
                            "provisional": True,
                        },
                    })
                elif event_type == "provider_reset":
                    event_sink({
                        "step": "provider_reset",
                        "payload": {
                            "provider": getattr(chunk, "provider", ""),
                            "native": bool(getattr(chunk, "native", False)),
                        },
                    })
                elif event_type == "usage":
                    event_sink({
                        "step": "provider_usage",
                        "payload": {
                            "usage": dict(getattr(chunk, "usage", {}) or {}),
                            "provider": getattr(chunk, "provider", ""),
                        },
                    })
                elif event_type == "completed":
                    terminal = getattr(chunk, "response", None)
            if terminal is None:
                return LLMResponse(
                    text="",
                    finish_reason="gateway_error:stream_missing_completion",
                )
            return terminal
        if hasattr(client, "complete_messages"):
            return await client.complete_messages(  # type: ignore[attr-defined]
                messages=messages, tools=tools,
                temperature=temperature, max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )
        # Fallback: first-round only via complete(system_prompt, user_input).
        # Multi-round loops will not work — the LLM only sees the original
        # system+user, not the tool results. Log a warning so the operator
        # notices; downstream the loop will see no tool_calls progress.
        if len(messages) > 2:
            logger.warning(
                "LLMWithToolsProvider: client has no complete_messages(); "
                "multi-round tool calls will not see tool results. "
                "Wrap the gateway with LLMGatewayAdapter to fix."
            )
        system_prompt = ""
        user_input = ""
        for m in messages:
            if m.get("role") == "system":
                system_prompt = m.get("content", "") or ""
            elif m.get("role") == "user":
                user_input = m.get("content", "") or ""
        return await client.complete(  # type: ignore[union-attr]
            system_prompt=system_prompt, user_input=user_input,
            temperature=temperature, max_tokens=max_tokens,
            timeout_seconds=timeout_seconds, tools=tools,
        )

    async def _dispatch_one_tool_call(
        self, tc: dict[str, Any], ctx: AgentRunContext, request: Any,
        *, round_index: int | None = None, caller: str | None = "llm",
    ) -> tuple[ToolCallRecord, dict[str, Any]]:
        """Dispatch one provider-native tool call through MCP.

        Returns ``(ToolCallRecord, tool_result_message)`` where
        ``tool_result_message`` is the ``{"role": "tool", ...}`` dict
        to append to the messages list for the next LLM round.
        """
        # Provider-native shape: {"id": ..., "type": "function",
        #   "function": {"name": ..., "arguments": "<json string>"}}
        fn = tc.get("function") or {}
        name = fn.get("name") or tc.get("name") or ""
        args_str = fn.get("arguments") or ""
        if isinstance(args_str, str):
            try:
                arguments = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                arguments = {"_raw_arguments": args_str}
        elif isinstance(args_str, dict):
            arguments = args_str
        else:
            arguments = {}
        tool_call_id = tc.get("id", "") or ""

        tool_call_dict = {
            "name": name,
            "arguments": arguments,
            "run_id": ctx.run_id,
            "tool_call_id": tool_call_id,
        }
        mcp_resp: ToolCallResponse = await self._mcp_layer.call(
            tool_call_dict, ctx,
            provider_id=self.provider_id, request=request,
            round_index=round_index, caller=caller,
        )
        record = self._mcp_layer.to_tool_call_record(
            mcp_resp, arguments=arguments,
        )
        # Stamp the tool_call_id on the record so downstream consumers
        # (RunTrace, frontend ToolDispatchDetail) can correlate.
        try:
            record.scope_granted = list(record.scope_granted or [])
        except Exception:
            pass

        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": json.dumps(mcp_resp.to_provider_result(), ensure_ascii=False),
        }
        return record, tool_message

    def _build_tool_schemas(
        self, req: BackendRequest, ctx: AgentRunContext,
    ) -> list[dict[str, Any]]:
        """Build OpenAI-style tool schemas from the agent's tool_scope.

        Asks ``ToolMCPCompatLayer.list_available_tools`` for the
        provider-native descriptors, filters by ``req.tool_scope``,
        and converts each to the OpenAI function-calling shape:

            {"type": "function",
             "function": {"name": ..., "description": ...,
                          "parameters": <input_schema>}}
        """
        if not req.tool_scope:
            return []
        try:
            all_tools = self._mcp_layer.list_available_tools(
                agent_id=ctx.agent_id, provider_id=self.provider_id,
                tool_scope=req.tool_scope,
            )
        except Exception as e:
            logger.warning(
                "LLMWithToolsProvider: list_available_tools failed: %s",
                type(e).__name__,
            )
            return []
        schemas: list[dict[str, Any]] = []
        for t in all_tools:
            if not isinstance(t, dict):
                continue
            name = t.get("name", "")
            if not isinstance(name, str) or not name:
                continue
            description = t.get("description", "") or ""
            input_schema = (
                t.get("input_schema")
                or t.get("inputSchema")
                or t.get("parameters")
                or {"type": "object", "properties": {}}
            )
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": input_schema,
                },
            })
        return schemas

    def _emit_backend_metadata(
        self, ctx: AgentRunContext, latency_ms: int,
        status: ProviderStatus, *, tool_rounds: int = 0,
        fallback_used: bool = False,
        model_routing: dict[str, Any] | None = None,
        model_telemetry: dict[str, Any] | None = None,
    ) -> None:
        """Emit a ``backend_metadata`` RunTrace event.

        Phase 4-C: same pattern as ``PureLLMProvider._emit_backend_metadata``
        but with ``tool_rounds`` populated. Defensive — never breaks
        the agent run if RunTrace is unavailable (e.g., unit tests
        without a store).
        """
        try:
            from app.icoder.agent_runtime.orchestrator.run_trace import (
                emit_backend_metadata_event,
                get_default_store,
            )
            emit_backend_metadata_event(
                ctx.run_id,
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                provider_latency_ms=latency_ms,
                provider_status=status,
                provider_deterministic=self.deterministic,
                supports_tool_calling=self.supports_tool_calling,
                fallback_used=fallback_used,
                output_contract=_pack_output_contract(
                    ctx.agent_pack, fallback=self.output_contract()
                ),
                tool_rounds=tool_rounds,
                model_deployment_id=str(
                    (model_routing or {}).get("deployment_id") or ""
                ),
                model_routing_mode=str((model_routing or {}).get("mode") or ""),
                model_selection_version=int(
                    (model_routing or {}).get("selection_version") or 0
                ),
                model_routing_decision=str(
                    (model_routing or {}).get("decision") or ""
                ),
                **(model_telemetry or {}),
                store=get_default_store(),
            )
        except Exception as e:
            logger.warning(
                "LLMWithToolsProvider: emit_backend_metadata_event failed: %s",
                type(e).__name__,
            )

    # ── Internal helpers ──────────────────────────────────────────

    def _resolve_client(self) -> LLMClient | None:
        """Return the LLMClient to use, lazy-resolving via registry gateway.

        Phase 5 Track C Gate 1 (2026-07-11): mirrors
        ``PureLLMProvider._resolve_client``. Priority:
          1. ``self._llm_client`` set at construction time.
          2. Lazy-resolve via ``registry.get_gateway()`` (registered by
             ``app/main.py`` at startup). Wrap in ``LLMGatewayAdapter``.
          3. None — ``invoke`` returns a failed backend envelope.

        Caches into ``self._llm_client`` so subsequent invokes (and
        ``_call_llm`` downstream) skip the lookup.
        """
        if self._llm_client is not None:
            return self._llm_client
        try:
            from .registry import get_gateway
            gateway = get_gateway()
        except Exception:
            return None
        if gateway is None:
            return None
        from .llm_gateway_adapter import LLMGatewayAdapter
        client = LLMGatewayAdapter(gateway)
        self._llm_client = client
        return client

    def _fail(
        self,
        message: str,
        t0: float,
        ctx: AgentRunContext,
        *,
        fallback_used: bool = False,
        cost_usd: float | None = None,
        tool_rounds: int = 0,
        llm_call_count: int = 0,
        model_routing: dict[str, Any] | None = None,
        model_telemetry: dict[str, Any] | None = None,
    ) -> BackendResponse:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        # Emit metadata so the RunTrace shows the failure even on _fail path.
        self._emit_backend_metadata(
            ctx, latency_ms, "fail",
            tool_rounds=tool_rounds, fallback_used=fallback_used,
            model_routing=model_routing,
            model_telemetry=model_telemetry,
        )
        return BackendResponse(
            status="fail",
            summary=f"LLMWithToolsProvider: {message}",
            finish_state="failed",
            finish_reason=message[:300],
            backend_provider=self.provider_id,
            backend_type=self.backend_type,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            raw_provider_response={
                "error": message[:500],
                "tool_rounds": tool_rounds,
                "llm_call_count": llm_call_count,
                "cost_usd_total": cost_usd,
                **({"model_routing": model_routing} if model_routing else {}),
            },
            trace_refs=[ctx.run_id],
        )


# ── Helpers ────────────────────────────────────────────────────────────


def _model_routing_from_raw(raw: Any) -> dict[str, Any] | None:
    """Return the gateway's secret-free routing decision, if present."""
    if not isinstance(raw, dict):
        return None
    routing = raw.get("model_routing")
    return dict(routing) if isinstance(routing, dict) else None


def _extract_system_prompt(ctx: AgentRunContext) -> str:
    pack = ctx.agent_pack or {}
    agent_node = pack.get("agent") if isinstance(pack, dict) else None
    if isinstance(agent_node, dict):
        sp = agent_node.get("system_prompt")
        if isinstance(sp, str) and sp:
            return sp
    if isinstance(pack, dict):
        sp = pack.get("system_prompt")
        if isinstance(sp, str) and sp:
            return sp
    return ""


def _extract_user_input(req: BackendRequest) -> str:
    if req.input and isinstance(req.input, dict):
        text = req.input.get("text") or req.input.get("user_input")
        if isinstance(text, str):
            return text
    return ""


def _extract_preflight_json(model_text: str) -> dict[str, Any]:
    """Extract a small eligibility object without applying the public schema."""
    text = str(model_text or "").strip()
    candidates = [text]
    if "```" in text:
        for block in text.split("```"):
            candidate = block.strip()
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            if candidate:
                candidates.append(candidate)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _resolve_preflight_conditional_tools(
    model_text: str,
    policies: list[dict[str, Any]],
) -> set[str]:
    """Resolve a preflight decision; malformed/missing decisions expose tools.

    The preflight has a deliberately separate contract from the public Agent
    Pack output. This avoids a deadlock where an evidence-first agent refuses
    to populate its public diagnoses before tools are available, and the
    runtime then interprets the empty diagnoses list as a reason to hide those
    same tools.
    """
    all_tools = {
        str(tool)
        for policy in policies
        for tool in (policy.get("tools") or [])
        if str(tool)
    }
    if not policies:
        return set()
    parsed = _extract_preflight_json(model_text)
    eligibility = parsed.get("tool_eligibility")
    if not isinstance(eligibility, dict):
        return all_tools

    resolved: set[str] = set()
    for policy in policies:
        tools = {str(tool) for tool in (policy.get("tools") or []) if str(tool)}
        path = str(policy.get("output_path") or "")
        decision = eligibility.get(path)
        # Only an explicit JSON boolean false may withhold a policy's tools.
        # Missing paths, strings such as "false", or malformed values fail
        # closed by exposing tools to the model-controlled MCP boundary.
        if decision is not False:
            resolved.update(tools)
    return resolved


def _resolve_conditional_mandatory_tools(
    model_text: str,
    policies: list[dict[str, Any]],
    ctx: AgentRunContext,
) -> set[str]:
    """Resolve output-dependent tool requirements, failing closed on parse.

    Inspect the model's raw structured candidate rather than its public-output
    projection. Diagnosis projection intentionally removes entries whose code
    has not yet been verified; using that projected list here would hide the
    very search/verification tools required to make those entries codable.
    """
    if not policies:
        return set()
    del ctx  # The raw candidate is deliberately independent of public projection.
    parsed = _extract_preflight_json(model_text)
    resolved: set[str] = set()
    for policy in policies:
        tools = {str(tool) for tool in (policy.get("tools") or []) if str(tool)}
        path = str(policy.get("output_path") or "")
        when = str(policy.get("when") or "nonempty")
        if not parsed or not path:
            resolved.update(tools)
            continue
        value: Any = parsed
        exists = True
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                exists = False
                break
            value = value[part]
        if not exists:
            resolved.update(tools)
        elif when == "nonempty" and bool(value):
            resolved.update(tools)
        elif when == "truthy" and bool(value):
            resolved.update(tools)
        elif when not in {"nonempty", "truthy"}:
            resolved.update(tools)
    return resolved


def _build_incomplete_markdown(
    tool_rounds: int, tool_calls: list[ToolCallRecord], user_input: str,
) -> str:
    """Markdown to return when ``max_tool_rounds`` is exceeded.

    The LLM didn't produce a final answer — we synthesize a
    WARNING-grade summary so downstream consumers still get a
    parseable markdown response.
    """
    tool_lines = "\n".join(
        f"- {tc.tool_name} (duration={tc.duration_ms}ms"
        f"{', error=' + tc.error if tc.error else ''})"
        for tc in tool_calls
    ) or "(no tool calls recorded)"
    return (
        "# Code Validation — Incomplete (max_tool_rounds exceeded)\n\n"
        f"## Status\n\nWARNING — LLM did not produce a final answer "
        f"after {tool_rounds} tool-call rounds. "
        "Manual review required.\n\n"
        f"## Tool Calls ({len(tool_calls)} total)\n\n{tool_lines}\n\n"
        f"## User Input (truncated)\n\n> {user_input[:200]}\n"
    )


def _build_missing_mandatory_markdown(
    model_text: str,
    missing_tools: list[str],
) -> str:
    """Preserve model text as an unverified draft and expose the failure."""
    missing = ", ".join(missing_tools)
    draft = model_text.strip()
    suffix = f"\n\n## Unverified model draft\n\n{draft}" if draft else ""
    return (
        "# Status: incomplete\n\n"
        "The response was not grounded by all mandatory tools.\n\n"
        f"Missing successful tool calls: `{missing}`."
        f"{suffix}"
    )


def _parse_status_from_markdown(text: str) -> ProviderStatus:
    """Heuristic: scan the LLM output for an explicit status keyword.

    Same logic as ``PureLLMProvider._parse_status_from_markdown`` —
    the LLM may emit a status keyword (``pass``/``warning``/``fail``/
    ``incomplete``) in its markdown. We case-insensitively scan.
    Defaults to ``complete`` when no keyword matches.
    """
    if not text:
        return "incomplete"
    lowered = text.lower()
    for keyword in (
        "requires_review",
        "non_compliant",
        "compliant",
        "incomplete",
        "unclear",
        "warning",
        "fail",
        "complete",
        "pass",
    ):
        if keyword in lowered:
            return keyword  # type: ignore[return-value]
    return "complete"


def _extract_first_paragraph(text: str) -> str:
    """Pull the first non-empty paragraph from markdown as summary."""
    if not text:
        return ""
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s[:300]
    return text[:300]


__all__ = ["LLMWithToolsProvider"]
