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

The canonical Gateway exposes the same native SSE event contract for
DeepSeek and OpenAI-compatible fallbacks such as Qwen and Azure OpenAI.
The public A2A route projects provisional content to PHI-safe progress
telemetry and publishes clinical text only after final runtime validation.
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

    def configuration_status(self) -> dict[str, str | bool]:
        """Return a secret-free configuration snapshot, never live health.

        The process gateway always contains a Mock provider, so merely having
        a gateway object (or ``gateway.is_configured``) cannot make a clinical
        Provider healthy.  This method resolves the actual selected provider,
        rejects Mock and egress-denied configurations, and reports only stable
        bounded fields suitable for Hub/runtime health projection.
        """
        gateway_get = getattr(self._gateway, "get", None)
        if not callable(gateway_get):
            return {
                "status": "unknown",
                "reason": "provider_configuration_uninspectable",
                "live_health_verified": False,
            }
        try:
            selected = gateway_get(self._provider)
        except Exception:
            return {
                "status": "unavailable",
                "reason": "provider_not_registered",
                "live_health_verified": False,
            }

        provider_name = str(getattr(selected, "name", "") or "")[:128]
        if selected.__class__.__name__ == "MockLLMProvider" or provider_name == "mock":
            return {
                "status": "unavailable",
                "reason": "mock_provider",
                "provider": "mock",
                "live_health_verified": False,
            }

        data_policy = getattr(self._gateway, "_data_policy", None)
        egress_decision = getattr(data_policy, "egress_decision", None)
        if callable(egress_decision):
            policy_name = str(
                getattr(selected, "policy_provider_name", "")
                or provider_name
            )
            try:
                decision = egress_decision(policy_name)
            except Exception:
                decision = {"decision": "deny"}
            if not isinstance(decision, dict) or decision.get("decision") != "allow":
                return {
                    "status": "unavailable",
                    "reason": "external_llm_egress_denied",
                    "provider": provider_name,
                    "live_health_verified": False,
                }

        raw_status = "unknown"
        health_check = getattr(selected, "health_check", None)
        if callable(health_check):
            try:
                raw = health_check()
                if isinstance(raw, dict):
                    raw_status = str(raw.get("status") or "unknown").lower()[:64]
            except Exception:
                raw_status = "error"
        if raw_status in {"healthy", "configured", "ok", "ready"}:
            status = "configured"
            reason = "configuration_present_not_live_verified"
        elif raw_status in {"unknown"}:
            status = "unknown"
            reason = "provider_configuration_unknown"
        else:
            status = "unavailable"
            reason = "provider_configuration_unavailable"
        return {
            "status": status,
            "reason": reason,
            "provider": provider_name,
            "provider_configuration_status": raw_status,
            "live_health_verified": False,
        }

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
        # Resolve the concrete provider before the call.  LLMGateway's mock
        # provider deliberately returns a normal-looking deterministic dict
        # for planner tests, so the response itself does not carry a
        # ``degraded`` marker.  Clinical agent execution must nevertheless
        # fail closed instead of publishing that synthetic payload.
        selected_provider_is_mock = False
        gateway_get = getattr(self._gateway, "get", None)
        if callable(gateway_get):
            try:
                selected = gateway_get(self._provider)
                selected_provider_is_mock = (
                    selected.__class__.__name__ == "MockLLMProvider"
                )
            except Exception:
                # Provider resolution/generation below remains the authority
                # for the actual error envelope.
                pass

        try:
            result = await self._gateway.generate(
                messages,
                provider=self._provider,
                tools=tools,
                context=context,
            )
        except Exception as e:
            logger.error(
                "LLMGatewayAdapter: gateway.generate raised error_type=%s",
                type(e).__name__,
            )
            return LLMResponse(
                text="",
                finish_reason=f"gateway_error:{type(e).__name__}",
                latency_ms=0,
                raw={"adapter_error": type(e).__name__},
            )

        return self._normalize_result(
            result,
            selected_provider_is_mock=selected_provider_is_mock,
        )

    @staticmethod
    def _normalize_result(
        result: Any,
        *,
        selected_provider_is_mock: bool = False,
    ) -> LLMResponse:
        """Normalize a gateway terminal result for sync and stream paths."""
        if not isinstance(result, dict):
            return LLMResponse(
                text=str(result),
                finish_reason="non_dict_response",
                latency_ms=0,
                raw={"raw_type": type(result).__name__},
            )

        text = result.get("content", "") or ""
        latency_ms = result.get("latency_ms", 0) or 0
        # A configured MockLLMProvider is suitable for deterministic tests,
        # but its synthetic content must never be treated as clinical output.
        degraded = bool(
            result.get("degraded", False)
            or result.get("is_mock", False)
            or result.get("provider") == "mock"
            or selected_provider_is_mock
        )
        finish_reason = result.get("finish_reason", "")
        if degraded:
            reason = result.get("degraded_reason") or "mock_provider"
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

    async def stream(
        self,
        *,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout_seconds: float = 60.0,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """Yield native text/tool deltas and one normalized completion."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        async for chunk in self.stream_messages(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        ):
            yield chunk

    async def stream_messages(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout_seconds: float = 60.0,
    ) -> AsyncIterator[LLMChunk]:
        """Multi-message streaming used by tool-calling providers."""
        context = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout_seconds": timeout_seconds,
        }
        stream_method = getattr(self._gateway, "generate_stream", None)
        if not callable(stream_method):
            response = await self._invoke_gateway(
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )
            yield LLMChunk(
                event_type="completed",
                finish_reason=response.finish_reason,
                response=response,
                native=False,
            )
            return

        try:
            async for event in stream_method(
                messages,
                provider=self._provider,
                tools=tools,
                context=context,
            ):
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("type") or "")
                native = bool(event.get("native", False))
                provider_name = str(event.get("provider") or "")
                if event_type == "text_delta":
                    delta = event.get("delta")
                    if isinstance(delta, str) and delta:
                        yield LLMChunk(
                            delta=delta,
                            event_type=event_type,
                            native=native,
                            provider=provider_name,
                            raw=event,
                        )
                elif event_type == "tool_call_delta":
                    delta = event.get("delta")
                    yield LLMChunk(
                        event_type=event_type,
                        tool_call_delta=(
                            delta if isinstance(delta, dict) else {}
                        ),
                        native=native,
                        provider=provider_name,
                        raw=event,
                    )
                elif event_type == "usage":
                    usage = event.get("usage")
                    yield LLMChunk(
                        event_type=event_type,
                        usage=usage if isinstance(usage, dict) else {},
                        native=native,
                        provider=provider_name,
                        raw=event,
                    )
                elif event_type == "provider_reset":
                    yield LLMChunk(
                        event_type=event_type,
                        native=native,
                        provider=provider_name,
                        raw=event,
                    )
                elif event_type == "completed":
                    response = self._normalize_result(event.get("result"))
                    yield LLMChunk(
                        event_type=event_type,
                        finish_reason=response.finish_reason,
                        response=response,
                        native=native,
                        provider=provider_name,
                        raw=event,
                    )
        except Exception as exc:
            logger.error(
                "LLMGatewayAdapter stream failed error_type=%s",
                type(exc).__name__,
            )
            response = LLMResponse(
                text="",
                finish_reason=f"gateway_error:{type(exc).__name__}",
                raw={"adapter_error": type(exc).__name__},
            )
            yield LLMChunk(
                event_type="completed",
                finish_reason=response.finish_reason,
                response=response,
                native=False,
            )


__all__ = ["LLMGatewayAdapter"]
