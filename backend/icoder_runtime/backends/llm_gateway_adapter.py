"""LLMGatewayAdapter — bridges ``LLMGateway.generate(messages)`` to the
``LLMClient`` Protocol expected by ``PureLLMProvider`` and
``LLMWithToolsProvider``.

Phase 4-B Step 1 (2026-07-08): ``complete(system_prompt, user_input)``
single-shot path for PureLLMProvider (no tools).

Phase 4-C (2026-07-08): ``complete_messages(messages, tools)`` multi-round
path for LLMWithToolsProvider tool-calling loop. ``complete()`` also
accepts ``tools`` now (forwarded to ``gateway.generate``).

Background:
  - ``LLMGateway`` (``icoder_runtime/core/llm_gateway.py``) is the existing
    process-wide LLM router. Its ``generate()`` takes a
    ``messages: list[dict]`` argument (OpenAI chat format) and returns
    a flat dict ``{"content": str, "model": str, "usage": {...},
    "latency_ms": int, "tool_calls": list | None, ...}``.
  - ``PureLLMProvider`` (Phase 4-A) defines an ``LLMClient`` Protocol
    with ``complete(system_prompt, user_input, ...)`` and ``stream(...)``.
    The Protocol is intentional — it doesn't bind to DeepSeek, so
    future providers (OpenAI / Qwen / custom) can be injected.
  - ``LLMWithToolsProvider`` (Phase 4-C) needs a multi-round variant
    that accepts the full messages list (including assistant tool_calls
    and tool results) so it can loop. ``complete_messages()`` provides
    this without disturbing the single-shot ``complete()`` contract.

Streaming is NOT supported in Phase 4-C. ``LLMGateway`` doesn't expose
a streaming method today (``LLMService.chat_stream()`` is deprecated).
Phase 4-D may add streaming when the first agent needs it.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from .pure_llm_provider import LLMChunk, LLMResponse

logger = logging.getLogger(__name__)


class LLMGatewayAdapter:
    """Adapts ``LLMGateway`` → ``LLMClient`` Protocol.

    Usage (production):
        gateway = app.state.platform_gateway
        provider = PureLLMProvider(llm_gateway=gateway)

    Usage (test):
        gateway = LLMGateway()
        gateway.register(MockLLMProvider(), default=True)
        provider = PureLLMProvider(llm_gateway=gateway)

    The adapter is stateless — one instance can be shared across
    providers. The ``gateway`` reference is held weakly (no cleanup
    needed when the gateway is replaced).
    """

    def __init__(self, gateway: Any, *, provider: str = "") -> None:
        # ``gateway`` is typed as Any to avoid importing LLMGateway here
        # (would create a circular import: llm_gateway imports from
        # icoder_runtime.circuit_breaker, which is fine, but we want
        # the backends package to be self-contained).
        self._gateway = gateway
        self._provider = provider

    async def complete(
        self,
        *,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout_seconds: float = 60.0,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Single-shot completion via the wrapped ``LLMGateway``.

        Builds an OpenAI-style messages list, calls
        ``gateway.generate(messages, ...)`` and normalizes the result
        to ``LLMResponse``.

        Phase 4-C: ``tools`` is forwarded to ``gateway.generate`` so
        LLMWithToolsProvider can do single-round tool-calling. For
        multi-round loops (where the messages list already contains
        assistant tool_calls and tool results), use
        ``complete_messages()`` instead.

        Error handling: ``LLMGateway`` / ``DeepSeekProvider`` already
        graceful-degrade to a mock fallback response on failure (the
        ``degraded`` flag is set on the return dict). We surface that
        here as ``finish_reason="degraded"`` plus the
        ``degraded_reason`` in ``raw``. The caller (PureLLMProvider)
        decides whether to treat it as a fail or a warning.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        return await self._invoke_gateway(
            messages=messages, tools=tools,
            temperature=temperature, max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )

    async def complete_messages(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout_seconds: float = 60.0,
    ) -> LLMResponse:
        """Multi-round completion — accepts a full messages list.

        Phase 4-C: used by ``LLMWithToolsProvider`` for the tool-calling
        loop. The ``messages`` list may include:

          - ``{"role": "system", "content": str}``
          - ``{"role": "user", "content": str}``
          - ``{"role": "assistant", "content": str | None,
                 "tool_calls": [...]}``  (LLM requested tool calls)
          - ``{"role": "tool", "tool_call_id": str, "content": str}``
            (tool result fed back to the LLM)

        Same error envelope as ``complete()`` — never raises to the
        caller. ``tool_calls`` in the returned ``LLMResponse`` is empty
        when the LLM finishes (no further tool calls requested).
        """
        return await self._invoke_gateway(
            messages=messages, tools=tools,
            temperature=temperature, max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )

    async def _invoke_gateway(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int | None,
        timeout_seconds: float,
    ) -> LLMResponse:
        """Shared gateway call + result normalization for both entry points."""
        context = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout_seconds": timeout_seconds,
        }
        try:
            result = await self._gateway.generate(
                messages,
                provider=self._provider,
                tools=tools,
                context=context,
            )
        except Exception as e:
            logger.exception("LLMGatewayAdapter: gateway.generate raised")
            return LLMResponse(
                text="",
                finish_reason=f"gateway_error:{type(e).__name__}",
                latency_ms=0,
                raw={"adapter_error": str(e)[:500]},
            )

        if not isinstance(result, dict):
            return LLMResponse(
                text=str(result),
                finish_reason="non_dict_response",
                latency_ms=0,
                raw={"raw_type": type(result).__name__},
            )

        text = result.get("content", "") or ""
        latency_ms = result.get("latency_ms", 0) or 0
        degraded = bool(result.get("degraded", False))
        finish_reason = result.get("finish_reason", "")
        if degraded:
            reason = result.get("degraded_reason", "unknown")
            finish_reason = f"degraded:{reason}"

        # Phase 4-C: parse tool_calls from gateway result. DeepSeek/OpenAI
        # return ``choices[0].message.tool_calls`` — DeepSeekProvider.generate()
        # now surfaces this as ``result["tool_calls"]``. Mock gateways that
        # don't populate the key yield an empty list (no tool calls).
        tool_calls_raw = result.get("tool_calls")
        tool_calls: list[dict[str, Any]] = []
        if isinstance(tool_calls_raw, list):
            tool_calls = tool_calls_raw

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            cost_usd=result.get("cost_usd"),
            raw=result,
        )

    def stream(
        self,
        *,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout_seconds: float = 60.0,
    ) -> AsyncIterator[LLMChunk]:
        """Streaming completion — NOT supported in Phase 4-C.

        ``LLMGateway`` doesn't expose a streaming method today. Phase 4-D
        may add streaming when the first agent needs it (likely
        Code Validation with ~12s latency benefits from SSE).

        Raising ``NotImplementedError`` here is intentional — it
        satisfies the ``LLMClient`` Protocol structurally while
        signaling to callers that streaming isn't available.
        """
        raise NotImplementedError(
            "Phase 4-C: LLMGatewayAdapter.stream not yet supported — "
            "non-streaming only. Use invoke() or complete_messages() instead. "
            "Streaming lands in Phase 4-D."
        )


__all__ = ["LLMGatewayAdapter"]
