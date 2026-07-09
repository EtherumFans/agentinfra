"""LLMWithToolsProvider — LLM backend with MCP tool calls.

Phase 4-A Task 6 (2026-07-07): skeleton — implemented the
``AgentBackendProvider`` interface and routed tool calls through
``ToolMCPCompatLayer`` → ``app.icoder.mcp.server.dispatch_tool``,
but did NOT wire a real LLM.

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
    ToolCallRecord,
)
from .pure_llm_provider import LLMClient, LLMResponse
from .tool_mcp_compat_layer import ToolMCPCompatLayer, ToolCallResponse

logger = logging.getLogger(__name__)


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
        if self._llm_client is None:
            return ProviderHealth(
                state="degraded",
                details={"note": "no llm_client wired (Phase 4-C production needs one)"},
            )
        return ProviderHealth(
            state="ok",
            details={"provider_id": self.provider_id,
                     "backend_type": self.backend_type,
                     "max_tool_rounds": self._max_tool_rounds},
        )

    async def invoke(
        self, req: BackendRequest, ctx: AgentRunContext,
        *,
        request: Any = None,
    ) -> BackendResponse:
        """LLM completion with at most ``max_tool_rounds`` tool-call rounds.

        Phase 4-C: real LLM tool-calling loop. If no ``llm_client`` is
        wired, runs the ``_skeleton_pipeline`` (one simulated tool
        call + placeholder markdown) so the contract is still
        verifiable in unit tests without an LLM.

        ``request`` is the FastAPI ``Request`` (or stand-in) needed by
        ``dispatch_tool`` to read ``app.state``. In-process callers
        construct a lightweight stand-in (see
        ``app.main.py:_handle_simple`` for the established pattern).
        """
        t0 = time.perf_counter()
        system_prompt = req.system_prompt or _extract_system_prompt(ctx)
        user_input = req.user_input or ctx.redacted_input or _extract_user_input(req)

        # Validate tool scope config (mandatory ⊆ scope, forbidden ∩ scope = ∅).
        scope_ok, scope_errors = self._mcp_layer.validate_tool_scope(
            req.tool_scope,
            mandatory=req.mandatory_tools,
            forbidden=req.forbidden_tools,
        )
        if not scope_ok:
            return self._fail(
                f"tool_scope invalid: {scope_errors}",
                t0, ctx,
            )

        if self._llm_client is None:
            return await self._skeleton_pipeline(
                req=req, ctx=ctx, system_prompt=system_prompt,
                user_input=user_input, request=request, t0=t0,
            )

        try:
            return await self._real_llm_pipeline(
                req=req, ctx=ctx, system_prompt=system_prompt,
                user_input=user_input, request=request, t0=t0,
            )
        except Exception as e:
            logger.exception("LLMWithToolsProvider.invoke failed")
            return self._fail(
                f"llm error: {type(e).__name__}: {e}",
                t0, ctx,
            )

    async def stream(
        self, req: BackendRequest, ctx: AgentRunContext,
        *,
        request: Any = None,
    ) -> AsyncIterator[Any]:
        """Streaming LLM with tools.

        Phase 4-C: emits a 4-event sequence derived from the invoke
        path (real streaming with interleaved tool calls is Phase 4-D
        scope — DeepSeek SSE):

          1. ``{"step": "backend_invoked", "payload": BackendResponse}``
          2. ``{"step": "tool_calls", "payload": ToolCallRecord}`` (per call)
          3. ``{"step": "output_chunk", "payload": {"delta": str}}``
          4. ``{"step": "finished", "payload": {"state": "completed"}}``
        """
        resp = await self.invoke(req, ctx, request=request)
        yield {"step": "backend_invoked", "payload": resp}
        for tc in resp.tool_calls:
            yield {"step": "tool_calls", "payload": tc}
        text = resp.markdown or ""
        for i in range(0, len(text), 200):
            yield {"step": "output_chunk", "payload": {"delta": text[i:i + 200]}}
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

    # ── Skeleton pipeline (no llm_client) ──────────────────────────

    async def _skeleton_pipeline(
        self,
        *,
        req: BackendRequest,
        ctx: AgentRunContext,
        system_prompt: str,
        user_input: str,
        request: Any,
        t0: float,
    ) -> BackendResponse:
        """Skeleton fallback: simulate one tool call + placeholder LLM.

        Used when no ``llm_client`` is wired (unit tests, dev startup
        before LLM gateway is registered). Picks the first tool in
        ``req.tool_scope`` and routes it through
        ``ToolMCPCompatLayer.call`` so the dispatch_tool contract is
        verified.
        """
        tool_calls: list[ToolCallRecord] = []
        scope = list(req.tool_scope or [])
        if not scope:
            all_tools = self._mcp_layer.list_available_tools(
                agent_id=ctx.agent_id, provider_id=self.provider_id,
            )
            if all_tools:
                first = all_tools[0]
                if isinstance(first, dict):
                    name = first.get("name", "")
                    if isinstance(name, str) and name:
                        scope = [name]

        if scope and request is not None:
            tool_name = scope[0]
            tool_args = _build_skeleton_tool_args(
                tool_name, user_input, req.input,
            )
            tool_call = {"name": tool_name, "arguments": tool_args,
                         "run_id": ctx.run_id}
            mcp_resp: ToolCallResponse = await self._mcp_layer.call(
                tool_call, ctx, provider_id=self.provider_id, request=request,
            )
            tool_calls.append(self._mcp_layer.to_tool_call_record(
                mcp_resp, arguments=tool_args,
            ))
        elif scope and request is None:
            tool_calls.append(ToolCallRecord(
                tool_name=scope[0],
                arguments={},
                error=("ToolMCPCompatLayer.call requires `request` — "
                       "pass it via invoke(..., request=...)"),
            ))

        placeholder_text = _placeholder_markdown(
            user_input, system_prompt, tool_calls,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        status: ProviderStatus = "complete"
        self._emit_backend_metadata(
            ctx, latency_ms, status,
            tool_rounds=len(tool_calls), fallback_used=False,
        )
        return BackendResponse(
            status=status,
            summary="LLMWithToolsProvider skeleton: placeholder response (no llm_client wired).",
            markdown=placeholder_text,
            tool_calls=tool_calls,
            backend_provider=self.provider_id,
            backend_type=self.backend_type,
            latency_ms=latency_ms,
            cost_usd=0.0,
            finish_state="completed",
            raw_provider_response={
                "skeleton": True,
                "tool_rounds": len(tool_calls),
                "system_prompt_chars": len(system_prompt),
                "user_input_chars": len(user_input),
            },
            evidence_refs=[tc.tool_name for tc in tool_calls],
            trace_refs=[ctx.run_id],
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
        all_tool_records: list[ToolCallRecord] = []
        tool_rounds = 0
        final_text = ""
        final_finish_reason = ""
        last_cost: float | None = None
        last_raw: dict[str, Any] = {}
        incomplete = False

        # 3. Tool-calling loop.
        while tool_rounds < self._max_tool_rounds:
            llm_resp = await self._call_llm(
                messages=messages, tools=tool_schemas,
                temperature=self._default_temperature,
                max_tokens=None, timeout_seconds=req.timeout_seconds,
            )
            if llm_resp.text and not llm_resp.tool_calls:
                # Final response — LLM stopped calling tools.
                final_text = llm_resp.text
                final_finish_reason = llm_resp.finish_reason
                last_cost = llm_resp.cost_usd
                last_raw = llm_resp.raw
                break

            if not llm_resp.tool_calls:
                # No text AND no tool_calls — LLM produced nothing.
                final_text = llm_resp.text or ""
                final_finish_reason = llm_resp.finish_reason or "empty_response"
                last_cost = llm_resp.cost_usd
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

            tool_rounds += 1
            last_cost = llm_resp.cost_usd
            last_raw = llm_resp.raw
        else:
            # Loop exited via while-condition (max_tool_rounds hit)
            # without a clean break — mark as incomplete.
            incomplete = True
            final_finish_reason = (
                f"max_tool_rounds_exceeded:{self._max_tool_rounds}"
            )

        # 5. Normalize to BackendResponse.
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
        self._emit_backend_metadata(
            ctx, latency_ms, status,
            tool_rounds=tool_rounds, fallback_used=degraded,
        )

        return BackendResponse(
            status=status,
            summary=_extract_first_paragraph(final_text),
            markdown=final_text,
            tool_calls=all_tool_records,
            backend_provider=self.provider_id,
            backend_type=self.backend_type,
            latency_ms=latency_ms,
            cost_usd=last_cost,
            finish_state=finish_state,
            finish_reason=final_finish_reason or None,
            raw_provider_response={
                **(last_raw or {}),
                "tool_rounds": tool_rounds,
                "tool_calls_count": len(all_tool_records),
                "max_tool_rounds": self._max_tool_rounds,
                "incomplete": incomplete,
            },
            evidence_refs=[tc.tool_name for tc in all_tool_records],
            trace_refs=[ctx.run_id],
        )

    async def _call_llm(
        self, *, messages: list[dict[str, Any]],
        tools: list[dict[str, Any]], temperature: float,
        max_tokens: int | None, timeout_seconds: float,
    ) -> LLMResponse:
        """Call the LLM with the full messages list.

        Uses ``complete_messages`` if the client exposes it (the
        ``LLMGatewayAdapter`` does, Phase 4-C). Falls back to
        ``complete(system_prompt, user_input, tools)`` for the first
        round if the client only implements the single-shot Protocol —
        but multi-round loops require ``complete_messages``.
        """
        client = self._llm_client
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
                "LLMWithToolsProvider: list_available_tools failed: %s", e,
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
                output_contract=self.output_contract(),
                tool_rounds=tool_rounds,
                store=get_default_store(),
            )
        except Exception as e:
            logger.warning(
                "LLMWithToolsProvider: emit_backend_metadata_event failed: %s", e,
            )

    # ── Internal helpers ──────────────────────────────────────────

    def _fail(self, message: str, t0: float, ctx: AgentRunContext) -> BackendResponse:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        # Emit metadata so the RunTrace shows the failure even on _fail path.
        self._emit_backend_metadata(
            ctx, latency_ms, "fail",
            tool_rounds=0, fallback_used=False,
        )
        return BackendResponse(
            status="fail",
            summary=f"LLMWithToolsProvider: {message}",
            finish_state="failed",
            finish_reason=message[:300],
            backend_provider=self.provider_id,
            backend_type=self.backend_type,
            latency_ms=latency_ms,
            raw_provider_response={"error": message[:500]},
            trace_refs=[ctx.run_id],
        )


# ── Helpers ────────────────────────────────────────────────────────────


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


def _build_skeleton_tool_args(
    tool_name: str, user_input: str, input_data: dict[str, Any],
) -> dict[str, Any]:
    """Build plausible tool args for the skeleton pipeline."""
    if not isinstance(input_data, dict):
        input_data = {}
    if tool_name in ("search_icd", "verify_code", "get_differentiation_hint"):
        if tool_name == "verify_code":
            return {"code": (user_input or "I50.900")[:20]}
        return {"query": user_input[:200]}
    if tool_name in ("rerank_codes", "calibrate_confidence"):
        return {
            "disease_text": user_input[:200],
            "candidates": input_data.get("candidates", []),
        }
    return {"query": user_input[:200]}


def _placeholder_markdown(
    user_input: str, system_prompt: str, tool_calls: list[ToolCallRecord],
) -> str:
    """Deterministic placeholder so tests can verify the contract."""
    tool_lines = "\n".join(
        f"- {tc.tool_name} ({tc.duration_ms}ms"
        f"{', error=' + tc.error if tc.error else ''})"
        for tc in tool_calls
    ) or "(no tool calls in skeleton pipeline)"
    return (
        "# LLMWithToolsProvider — Skeleton Response\n\n"
        f"## User Input (truncated)\n\n> {user_input[:200]}\n\n"
        f"## System Prompt (truncated)\n\n> {system_prompt[:200]}\n\n"
        f"## Tool Calls\n\n{tool_lines}\n\n"
        "## Status\n\ncomplete (skeleton — no real LLM call)\n\n"
        "## Note\n\nPhase 4-A skeleton. Wire `llm_client` to enable real LLM calls.\n"
    )


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
