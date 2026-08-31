"""LLM Gateway — model routing layer for iCoDer Runtime.

AgentRunner calls LLMGateway, not individual LLM providers.
LLMGateway routes to the configured provider based on runtime settings.

Providers:
  - MockLLMProvider: deterministic fake responses for tests
  - DeepSeekProvider: calls DeepSeek API
  - OpenAICompatibleProvider: any OpenAI-compatible endpoint
  - MedicalCodingLLMProvider: wraps iCoDer coding engine as an LLM
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Awaitable, Callable

from .errors import LLMProviderNotConfigured, ProviderError
from icoder_runtime.circuit_breaker import (
    CircuitBreaker,
    llm_circuit_breaker as gateway_circuit_breaker,
)

logger = logging.getLogger(__name__)


def _bounded_request_limits(
    context: dict[str, Any] | None,
    *,
    default_max_tokens: int,
    default_temperature: float,
    default_timeout: float,
) -> tuple[int, float, float, int]:
    """Apply per-request limits without allowing callers to widen defaults."""

    values = context if isinstance(context, dict) else {}
    try:
        requested_tokens = int(values.get("max_tokens") or default_max_tokens)
    except (TypeError, ValueError):
        requested_tokens = default_max_tokens
    max_tokens = max(1, min(requested_tokens, max(1, int(default_max_tokens))))

    try:
        requested_temperature = float(
            values.get("temperature")
            if values.get("temperature") is not None
            else default_temperature
        )
    except (TypeError, ValueError):
        requested_temperature = default_temperature
    temperature = max(0.0, min(requested_temperature, 2.0))

    try:
        requested_timeout = float(
            values.get("timeout_seconds") or default_timeout
        )
    except (TypeError, ValueError):
        requested_timeout = default_timeout
    timeout = max(0.1, min(requested_timeout, max(0.1, float(default_timeout))))

    try:
        requested_attempts = int(values.get("max_attempts") or 3)
    except (TypeError, ValueError):
        requested_attempts = 3
    max_attempts = max(1, min(requested_attempts, 3))
    return max_tokens, temperature, timeout, max_attempts


def _compute_cost_usd(usage: dict[str, Any]) -> float:
    """Phase 4-G #1 — compute cost in USD from token usage + config pricing.

    Reads `LLM_PRICE_INPUT_PER_1M` / `LLM_PRICE_OUTPUT_PER_1M` from settings
    (with sensible DeepSeek V4 flash defaults if unset). Returns 0.0 when
    usage is missing/zero so the response still serializes cleanly.
    """
    if not isinstance(usage, dict):
        return 0.0
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    if input_tokens == 0 and output_tokens == 0:
        return 0.0
    # Lazy import to avoid circular: config.py imports plenty; this module
    # is imported very early in app startup.
    try:
        from app.config import settings
        in_price = float(getattr(settings, "LLM_PRICE_INPUT_PER_1M", 0.14) or 0.14)
        out_price = float(getattr(settings, "LLM_PRICE_OUTPUT_PER_1M", 0.28) or 0.28)
    except Exception:
        in_price, out_price = 0.14, 0.28
    cost = (input_tokens / 1_000_000.0) * in_price + (output_tokens / 1_000_000.0) * out_price
    return round(cost, 6)


__all__ = [
    "BaseLLMProvider",
    "MockLLMProvider",
    "DeepSeekProvider",
    "OpenAICompatibleProvider",
    "MedicalCodingLLMProvider",
    "LLMGateway",
    "ProviderError",
    "LLMProviderNotConfigured",
    "CircuitBreaker",
    "gateway_circuit_breaker",
    "_compute_cost_usd",
]


def _check_circuit_or_raise(cb: CircuitBreaker) -> None:
    """Raise ProviderError if the circuit is open.

    Caller should fall back to a degraded path (e.g., MockLLMProvider)
    after catching this. The circuit tracks transient LLM failures
    (timeouts, 429, 503) and short-circuits requests when a provider
    is known unhealthy.
    """
    if cb.is_open:
        raise ProviderError(
            f"Circuit '{cb.name}' is open; refusing LLM call. "
            "Caller should fall back to degraded mode."
        )


def _mock_fallback_response(reason: str) -> dict[str, Any]:
    """Build a degraded response that looks like a DeepSeek API call but signals fallback.

    Used by DeepSeekProvider.generate() when the call cannot be served
    by a real LLM (no API key, circuit open, exhausted retries, 4xx
    errors, network failures). The response carries ``degraded=True``,
    ``degraded_reason``, ``is_mock=True`` and ``provider="mock"`` so
    callers can detect and route around it.
    """
    fallback = {
        "review_conclusion": "UNKNOWN",
        "primary_diagnosis": {"code": "", "description": ""},
        "issues_found": [
            {
                "severity": "warning",
                "code": "DEGRADED_MODE",
                "message": f"LLM provider unavailable: {reason}",
            }
        ],
        "confidence": 0.0,
        "notes": f"[DeepSeek degraded] {reason}. Mock response, not a real LLM call.",
    }
    return {
        "content": json.dumps(fallback, ensure_ascii=False),
        "model": "mock/1.0",
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "latency_ms": 0,
        "degraded": True,
        "degraded_reason": reason,
        "is_mock": True,
        "provider": "mock",
        "structured": fallback,
    }


logger = logging.getLogger(__name__)


# ── Abstract Provider ──


class BaseLLMProvider(ABC):
    """Abstract LLM provider. All providers implement this interface."""

    name: str = "base"

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a completion from the provider.

        Returns: {"content": str, "model": str, "usage": {"input_tokens": int, "output_tokens": int}}
        """
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Optional: embed ``texts`` to fixed-dim vectors.

        Providers don't have to support embedding — the default raises
        NotImplementedError. MedCodER uses a local BGE-M3 embedder loaded
        in-process, not the gateway; this hook exists for the
        OpenAI-compatible provider so future code can call
        ``gateway.embed([...])`` uniformly.
        """
        raise NotImplementedError(
            f"Provider {self.name} does not implement embed(); "
            "use the local BGE-M3 embedder (icoder_runtime.providers.medical_coding.embedding_bge_m3.BGEEmbedder) instead."
        )

    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield provider events and a mandatory final ``completed`` event.

        Providers without a native streaming transport retain compatibility by
        executing ``generate`` once and emitting only the completed result.
        Consumers can therefore distinguish native deltas from a projected
        final response via the ``native`` flag instead of guessing.
        """
        result = await self.generate(
            messages=messages,
            tools=tools,
            response_schema=response_schema,
            context=context,
        )
        yield {"type": "completed", "native": False, "result": result}

    def health_check(self) -> dict:
        """Return provider health status."""
        return {"provider": self.name, "status": "unknown"}


# ── Mock Provider ──


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock for testing. Returns structured JSON from the last user message.

    Detects the call shape:
    - Planner prompt (system contains "# Plan schema" + user contains
      "available_experts:") → returns a valid Plan `{"experts": [...], "reason": ...}`
      picking the first declared available_expert (so `Plan.experts` is never empty).
    - Otherwise → returns a generic compliance audit result.
    """

    name = "mock"

    def __init__(self, *, name: str = "") -> None:
        # Phase A1D.4 — optional instance-level name override so tests can
        # register multiple mocks (e.g. ``MockLLMProvider(name="fb1")``) and
        # tell them apart in the fallback chain trail.
        if name:
            self.name = name

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_user = ""
        system_text = ""
        for m in messages:
            if m.get("role") == "system":
                system_text += m.get("content", "")
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        # Planner call shape — return a valid Plan with the first declared
        # available_expert so _validate_plan_dict never trips "experts must
        # be a non-empty list". Falls back to "coding-expert" if parsing fails.
        if "# Plan schema" in system_text and "available_experts:" in last_user:
            expert_id = self._extract_first_expert(last_user) or "coding-expert"
            subtask = self._extract_subtask_input(last_user) or (
                "提取病历中的疾病诊断并按 ICD-10-CN 编码"
            )
            plan = {
                "experts": [
                    {
                        "expert_id": expert_id,
                        "priority": 1,
                        "critical": True,
                        "subtask_input": subtask,
                        "tool_constraints": [],
                    }
                ],
                "reason": f"[MockLLM] deterministic plan with {expert_id}",
            }
            return {
                "content": json.dumps(plan, ensure_ascii=False),
                "model": "mock/1.0",
                "usage": {"input_tokens": len(last_user) // 3, "output_tokens": 60},
                "structured": plan,
                "provider": "mock",
                "is_mock": True,
                "degraded": True,
                "degraded_reason": "mock_provider",
            }

        # Generic compliance audit shape (used by medical-coding expert paths
        # that don't go through the planner).
        reply = {
            "review_conclusion": "PASS",
            "primary_diagnosis": {"code": "I21.0", "description": "急性前壁心肌梗死"},
            "issues_found": [],
            "confidence": 0.95,
            "notes": f"[MockLLM] Processed input ({len(last_user)} chars).",
        }

        return {
            "content": json.dumps(reply, ensure_ascii=False),
            "model": "mock/1.0",
            "usage": {"input_tokens": len(last_user) // 3, "output_tokens": 120},
            "structured": reply,
            "provider": "mock",
            "is_mock": True,
            "degraded": True,
            "degraded_reason": "mock_provider",
        }

    def health_check(self) -> dict:
        return {"provider": self.name, "status": "degraded", "mode": "mock"}

    @staticmethod
    def _extract_first_expert(user_message: str) -> str:
        """Pull the first bullet under `available_experts:`."""
        import re

        m = re.search(
            r"available_experts:\s*\n(\s*-\s*([^\n]+))",
            user_message,
        )
        if not m:
            return ""
        eid = m.group(2).strip()
        # Strip leading dashes / whitespace just in case
        eid = eid.lstrip("-").strip()
        return eid

    @staticmethod
    def _extract_subtask_input(user_message: str) -> str:
        """Pull the user input block as the subtask payload."""
        marker = "# User input (PHI redacted)\n"
        idx = user_message.find(marker)
        if idx < 0:
            return ""
        rest = user_message[idx + len(marker):]
        # Cut at the next section header if present
        next_hdr = rest.find("\n# ")
        if next_hdr >= 0:
            rest = rest[:next_hdr]
        return rest.strip()

    def health_check(self) -> dict:
        return {"provider": self.name, "status": "healthy"}


# ── DeepSeek Provider ──


class DeepSeekProvider(BaseLLMProvider):
    """Calls DeepSeek API (deepseek-chat)."""

    name = "deepseek"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        timeout: int = 120,
        _transport: Any = None,
    ):
        self.api_key = api_key or os.environ.get("ICODER_CREDENTIAL_LLM", "")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        # Private: test hook to inject a MockTransport. None in production.
        self._transport = _transport
        self._stream_include_usage = True

    def _chat_completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _request_headers(self, *, stream: bool = False) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if stream:
            headers["Accept"] = "text/event-stream"
        return headers

    def _stream_circuit_is_open(self) -> bool:
        return gateway_circuit_breaker.is_open

    def _stream_record_failure(self) -> None:
        gateway_circuit_breaker.record_failure()

    def _stream_record_success(self) -> None:
        gateway_circuit_breaker.record_success()

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Graceful degradation (C3): every error path returns a mock
        # fallback response tagged with ``degraded=True`` and
        # ``degraded_reason``. Callers can check ``response.get("degraded")``
        # to detect fallback and route around it (e.g., skip re-ranking).
        # This method never raises ProviderError to the eval loop.

        # 1. Circuit open at entry — provider known unhealthy, short-circuit.
        if gateway_circuit_breaker.is_open:
            return _mock_fallback_response("circuit_open")

        # 2. No API key — misconfiguration. Fall back without touching the circuit.
        if not self.api_key:
            return _mock_fallback_response("no_api_key")

        import httpx

        request_max_tokens, request_temperature, request_timeout, max_attempts = (
            _bounded_request_limits(
                context,
                default_max_tokens=self.max_tokens,
                default_temperature=self.temperature,
                default_timeout=self.timeout,
            )
        )
        url = self._chat_completions_url()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request_max_tokens,
            "temperature": request_temperature,
        }
        if tools:
            payload["tools"] = tools
        if response_schema:
            payload["response_format"] = {"type": "json_object", "schema": response_schema}

        headers = self._request_headers()

        t0 = time.time()
        # Retry budget: 3 attempts on transient (429 / 503) with 1s, 2s backoff.
        # Final failure returns a degraded mock response (no raise).
        for attempt in range(max_attempts):
            try:
                client_kwargs: dict[str, Any] = {"timeout": request_timeout}
                if self._transport is not None:
                    client_kwargs["transport"] = self._transport
                async with httpx.AsyncClient(**client_kwargs) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code in (429, 503):
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(1 << attempt)
                            continue
                        gateway_circuit_breaker.record_failure()
                        return _mock_fallback_response("provider_429_503")
                    # Non-retryable HTTP error (400, 401, 403, 404, 422, etc.)
                    # raise_for_status raises HTTPStatusError → caught below.
                    resp.raise_for_status()
                    data = resp.json()
                    gateway_circuit_breaker.record_success()
                    break
            except httpx.HTTPStatusError as e:
                # 4xx — caller/contract problem. No record_failure (a 401 is
                # not a sign the provider is unhealthy; it's a misconfig).
                status = e.response.status_code if e.response is not None else "?"
                return _mock_fallback_response(f"provider_http_{status}")
            except httpx.HTTPError as e:
                # Network-level (timeout, DNS, connect) — degraded fallback.
                # No record_failure: a single network blip shouldn't open the circuit.
                return _mock_fallback_response("provider_network_error")

        choice = data["choices"][0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        # Phase 4-C: parse tool_calls (OpenAI/DeepSeek function-calling shape).
        # The LLM returns ``message.tool_calls`` as a list of
        # ``{"id": str, "type": "function",
        #   "function": {"name": str, "arguments": "<json string>"}}``
        # when it wants to call a tool. We surface this so
        # ``LLMGatewayAdapter._invoke_gateway`` can populate
        # ``LLMResponse.tool_calls`` for ``LLMWithToolsProvider``.
        tool_calls = message.get("tool_calls")
        usage = {
            "input_tokens": data.get("usage", {}).get("prompt_tokens", 0),
            "output_tokens": data.get("usage", {}).get("completion_tokens", 0),
        }
        result: dict[str, Any] = {
            "content": content,
            "model": data.get("model", self.model),
            "usage": usage,
            "cost_usd": _compute_cost_usd(usage),
            "latency_ms": int((time.time() - t0) * 1000),
            "finish_reason": str(choice.get("finish_reason") or ""),
        }
        if tool_calls:
            result["tool_calls"] = tool_calls
        return result

    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream an OpenAI-compatible SSE response.

        Text and tool-call fragments are provisional provider events.  The
        mandatory final ``completed`` event contains the same normalized
        result shape as :meth:`generate`, including usage and cost.  Clinical
        transports must not publish provisional text until their own output
        safety/contract boundary permits it.
        """
        if self._stream_circuit_is_open():
            yield {
                "type": "completed",
                "native": True,
                "result": _mock_fallback_response("circuit_open"),
            }
            return
        if not self.api_key:
            yield {
                "type": "completed",
                "native": True,
                "result": _mock_fallback_response("no_api_key"),
            }
            return

        import httpx

        request_max_tokens, request_temperature, request_timeout, max_attempts = (
            _bounded_request_limits(
                context,
                default_max_tokens=self.max_tokens,
                default_temperature=self.temperature,
                default_timeout=self.timeout,
            )
        )
        url = self._chat_completions_url()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request_max_tokens,
            "temperature": request_temperature,
            "stream": True,
        }
        if self._stream_include_usage:
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = tools
        if response_schema:
            payload["response_format"] = {
                "type": "json_object",
                "schema": response_schema,
            }
        headers = self._request_headers(stream=True)

        t0 = time.time()
        content_chunks: list[str] = []
        tool_calls_by_index: dict[int, dict[str, Any]] = {}
        usage = {"input_tokens": 0, "output_tokens": 0}
        finish_reason = ""
        model = self.model
        emitted_provider_data = False
        saw_done = False
        saw_valid_chunk = False

        for attempt in range(max_attempts):
            try:
                client_kwargs: dict[str, Any] = {"timeout": request_timeout}
                if self._transport is not None:
                    client_kwargs["transport"] = self._transport
                async with httpx.AsyncClient(**client_kwargs) as client:
                    async with client.stream(
                        "POST", url, json=payload, headers=headers,
                    ) as response:
                        if response.status_code in (429, 503):
                            if attempt < max_attempts - 1 and not emitted_provider_data:
                                await response.aread()
                                await asyncio.sleep(1 << attempt)
                                continue
                            self._stream_record_failure()
                            reason = "provider_429_503"
                            yield {
                                "type": "completed",
                                "native": True,
                                "result": _mock_fallback_response(reason),
                            }
                            return
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line or line.startswith(":"):
                                continue
                            if not line.startswith("data:"):
                                continue
                            payload_text = line[5:].strip()
                            if payload_text == "[DONE]":
                                saw_done = True
                                break
                            try:
                                chunk = json.loads(payload_text)
                            except json.JSONDecodeError:
                                yield {
                                    "type": "provider_warning",
                                    "native": True,
                                    "code": "invalid_sse_json",
                                }
                                continue
                            if not isinstance(chunk, dict):
                                continue
                            saw_valid_chunk = True
                            model = str(chunk.get("model") or model)
                            raw_usage = chunk.get("usage")
                            if isinstance(raw_usage, dict):
                                usage = {
                                    "input_tokens": int(
                                        raw_usage.get("prompt_tokens", 0) or 0
                                    ),
                                    "output_tokens": int(
                                        raw_usage.get("completion_tokens", 0) or 0
                                    ),
                                }
                                yield {
                                    "type": "usage",
                                    "native": True,
                                    "usage": dict(usage),
                                }
                            choices = chunk.get("choices")
                            if not isinstance(choices, list):
                                continue
                            for choice in choices:
                                if not isinstance(choice, dict):
                                    continue
                                if choice.get("finish_reason"):
                                    finish_reason = str(choice["finish_reason"])
                                delta = choice.get("delta")
                                if not isinstance(delta, dict):
                                    continue
                                text_delta = delta.get("content")
                                if isinstance(text_delta, str) and text_delta:
                                    emitted_provider_data = True
                                    content_chunks.append(text_delta)
                                    yield {
                                        "type": "text_delta",
                                        "native": True,
                                        "delta": text_delta,
                                    }
                                reasoning_delta = delta.get("reasoning_content")
                                if (
                                    isinstance(reasoning_delta, str)
                                    and reasoning_delta
                                ):
                                    # Reasoning is accounted for but never
                                    # projected as public clinical text.
                                    emitted_provider_data = True
                                    yield {
                                        "type": "reasoning_delta",
                                        "native": True,
                                        "characters": len(reasoning_delta),
                                    }
                                tool_deltas = delta.get("tool_calls")
                                if not isinstance(tool_deltas, list):
                                    continue
                                for tool_delta in tool_deltas:
                                    if not isinstance(tool_delta, dict):
                                        continue
                                    emitted_provider_data = True
                                    index = int(tool_delta.get("index", 0) or 0)
                                    merged = tool_calls_by_index.setdefault(
                                        index,
                                        {
                                            "id": "",
                                            "type": "function",
                                            "function": {
                                                "name": "",
                                                "arguments": "",
                                            },
                                        },
                                    )
                                    if tool_delta.get("id"):
                                        merged["id"] = str(tool_delta["id"])
                                    if tool_delta.get("type"):
                                        merged["type"] = str(tool_delta["type"])
                                    fn_delta = tool_delta.get("function")
                                    if isinstance(fn_delta, dict):
                                        name_delta = fn_delta.get("name")
                                        args_delta = fn_delta.get("arguments")
                                        if isinstance(name_delta, str):
                                            merged["function"]["name"] += name_delta
                                        if isinstance(args_delta, str):
                                            merged["function"]["arguments"] += args_delta
                                    yield {
                                        "type": "tool_call_delta",
                                        "native": True,
                                        "index": index,
                                        "delta": tool_delta,
                                    }
                if not saw_done or not saw_valid_chunk:
                    yield {
                        "type": "completed",
                        "native": True,
                        "result": _mock_fallback_response(
                            "provider_stream_truncated"
                        ),
                    }
                    return
                self._stream_record_success()
                break
            except httpx.HTTPStatusError as exc:
                status = (
                    exc.response.status_code
                    if exc.response is not None
                    else "unknown"
                )
                yield {
                    "type": "completed",
                    "native": True,
                    "result": _mock_fallback_response(
                        f"provider_http_{status}"
                    ),
                }
                return
            except httpx.HTTPError:
                yield {
                    "type": "completed",
                    "native": True,
                    "result": _mock_fallback_response(
                        "provider_network_error"
                    ),
                }
                return

        tool_calls = [
            tool_calls_by_index[index]
            for index in sorted(tool_calls_by_index)
        ]
        result: dict[str, Any] = {
            "content": "".join(content_chunks),
            "model": model,
            "usage": usage,
            "cost_usd": _compute_cost_usd(usage),
            "latency_ms": int((time.time() - t0) * 1000),
            "finish_reason": finish_reason,
            "provider": self.name,
            "stream_native": True,
        }
        if tool_calls:
            result["tool_calls"] = tool_calls
        yield {"type": "completed", "native": True, "result": result}

    def health_check(self) -> dict:
        return {"provider": self.name, "model": self.model, "status": "configured" if self.api_key else "no_api_key"}


# ── OpenAI-Compatible Provider ──


class OpenAICompatibleProvider(DeepSeekProvider):
    """Any OpenAI-compatible API endpoint (vLLM, Ollama, etc.)."""

    name = "openai_compat"

    def __init__(
        self,
        api_key: str = "not-needed",
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        timeout: int = 120,
        *,
        _name_override: str = "",
        auth_header: str = "Authorization",
        stream_include_usage: bool = True,
        _transport: Any = None,
    ):
        self.api_key = api_key
        # Phase A1D.4 — Azure OpenAI uses deployment-scoped URLs that already
        # contain the full path + query string; don't strip the query.
        if "?" in base_url:
            self.base_url = base_url.rstrip("/")
        else:
            self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        # Phase A1D.4 — instance-level name override so multiple fallbacks
        # of the same class can coexist (azure_openai_fallback, qwen_fallback, ...).
        if _name_override:
            self.name = _name_override
        # Phase A1D.4 — Azure uses ``api-key: <key>`` instead of
        # ``Authorization: Bearer <key>``. Default to Authorization for
        # OpenAI / Qwen / Moonshot compatibility.
        self._auth_header = auth_header
        self._stream_include_usage = stream_include_usage
        # Private deterministic test hook; production leaves this unset.
        self._transport = _transport

    def _chat_completions_url(self) -> str:
        if "?" in self.base_url and "/chat/completions" in self.base_url:
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _request_headers(self, *, stream: bool = False) -> dict[str, str]:
        if self._auth_header.lower() == "api-key":
            headers = {
                "api-key": self.api_key,
                "Content-Type": "application/json",
            }
        else:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        if stream:
            headers["Accept"] = "text/event-stream"
        return headers

    def _stream_circuit_is_open(self) -> bool:
        # Fallback providers must remain callable when the DeepSeek primary's
        # process-wide breaker is open.
        return False

    def _stream_record_failure(self) -> None:
        return None

    def _stream_record_success(self) -> None:
        return None

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Phase A1D.4 (A1C-B-007) — graceful degradation matches DeepSeekProvider.
        # Returns _mock_fallback_response on every error path so the gateway's
        # auto-failover logic can detect degraded responses uniformly.
        # Note: only treat EMPTY api_key as missing. The literal "not-needed"
        # is a documented placeholder for local providers (Ollama, vLLM) that
        # don't require auth — those should still attempt the call.
        if not self.api_key:
            return _mock_fallback_response("no_api_key")

        import httpx

        # Azure OpenAI URLs already include /chat/completions in the base_url.
        # Honor the contract: when base_url contains "?api-version=", treat
        # it as fully-qualified (no /chat/completions append).
        url = self._chat_completions_url()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
        if response_schema:
            payload["response_format"] = {"type": "json_object", "schema": response_schema}

        headers = self._request_headers()

        t0 = time.time()
        try:
            client_kwargs: dict[str, Any] = {"timeout": self.timeout}
            if self._transport is not None:
                client_kwargs["transport"] = self._transport
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else "?"
            return _mock_fallback_response(f"provider_http_{status}")
        except httpx.HTTPError:
            return _mock_fallback_response("provider_network_error")

        choice = data["choices"][0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        # Phase 4-C: parse tool_calls (OpenAI function-calling shape).
        tool_calls = message.get("tool_calls")
        usage = {
            "input_tokens": data.get("usage", {}).get("prompt_tokens", 0),
            "output_tokens": data.get("usage", {}).get("completion_tokens", 0),
        }
        result: dict[str, Any] = {
            "content": content,
            "model": data.get("model", self.model),
            "provider": self.name,
            "usage": usage,
            "cost_usd": _compute_cost_usd(usage),
            "latency_ms": int((time.time() - t0) * 1000),
            "finish_reason": str(choice.get("finish_reason") or ""),
        }
        if tool_calls:
            result["tool_calls"] = tool_calls
        return result

    def health_check(self) -> dict:
        # Phase A1D.5 — only treat EMPTY api_key as missing. The literal
        # "not-needed" is a valid placeholder for local no-auth providers.
        if not self.api_key:
            return {"provider": self.name, "model": self.model, "status": "missing"}
        return {"provider": self.name, "model": self.model, "status": "configured"}


# ── Medical Coding LLM Provider ──
# Wraps the iCoDer coding engine as an LLM provider.
# Does NOT contain Reviews/Encounters business logic — that lives in ReviewCodingService.


class MedicalCodingLLMProvider(BaseLLMProvider):
    """Adapter that exposes the iCoDer coding engine as an LLM Provider.

    Supports three modes:
    - unavailable: No engine configured, returns an empty failed schema
    - prompt_llm: Uses PromptLLMAdapter (LLM via prompt engineering) to get coding output
    - real: Uses a CodingEngineAdapter-compatible coding inference service

    All output is normalized through MedicalCodingOutputSchema.
    """

    name = "medical_coding"

    def __init__(self, coding_engine: Any = None, gateway: Any = None):
        """coding_engine: CodingEngineAdapter or compatible object.
        If None and gateway is provided, uses PromptLLMAdapter.
        If both None, uses mock mode.
        """
        from official_agents.medical_coding.schema import CodingEngineAdapter
        if coding_engine is not None and isinstance(coding_engine, CodingEngineAdapter):
            self._engine = coding_engine
        elif gateway is not None:
            # Use the runtime adapter rather than the older schema-local bridge.
            # The runtime adapter preserves gateway ``is_mock``/``degraded``
            # provenance; the legacy bridge hard-coded the parsed schema as a
            # real result and caused clinical false-success under MockLLM.
            from icoder_runtime.providers.medical_coding.prompt_llm_adapter import (
                PromptLLMAdapter,
            )
            self._engine = PromptLLMAdapter(gateway)
        else:
            self._engine = None

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from official_agents.medical_coding.schema import MedicalCodingOutputSchema

        if self._engine is not None:
            return await self._generate_real(messages, tools, response_schema, context)

        schema = MedicalCodingOutputSchema.failure_result(
            self.name, reason="coding_engine_unavailable"
        )
        return self._pack_response(schema)

    async def _generate_real(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None,
        response_schema: dict | None,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        from official_agents.medical_coding.schema import MedicalCodingOutputSchema

        result = await self._engine.infer_async(
            messages=messages, tools=tools, response_schema=response_schema, context=context
        )

        if isinstance(result, MedicalCodingOutputSchema):
            return self._pack_response(result)

        # Coerce to schema
        if isinstance(result, dict):
            schema = MedicalCodingOutputSchema.from_dict(result, provider=self._engine.name)
        else:
            schema = MedicalCodingOutputSchema.failure_result(
                self.name, reason="invalid_coding_engine_response"
            )
        return self._pack_response(schema)

    def _pack_response(self, schema) -> dict[str, Any]:
        """Pack a MedicalCodingOutputSchema into the standard provider response."""
        d = schema.to_dict()
        is_mock = bool(getattr(schema, "is_mock", False))
        response = {
            "content": json.dumps(d, ensure_ascii=False),
            "model": f"medical-coding/{schema.model}" if schema.model else "medical-coding/mock",
            "usage": {"input_tokens": 0, "output_tokens": len(json.dumps(d)) // 3},
            "structured": d,
        }
        # Do not lose the clinical-safety marker while adapting the structured
        # schema to the generic gateway envelope.  FastCodingRuntime checks the
        # top-level flags before projecting codes; without them mock_result()
        # was indistinguishable from a real model response and produced a
        # false-success coding result.
        if is_mock:
            response.update({
                "is_mock": True,
                "degraded": True,
                "degraded_reason": (
                    getattr(schema, "degraded_reason", "") or "mock_provider"
                ),
                "provider": "mock",
            })
        return response

    def health_check(self) -> dict:
        from official_agents.medical_coding.schema import CodingEngineAdapter
        if self._engine is None:
            return {"provider": self.name, "mode": "mock", "status": "degraded", "engine_type": "none"}
        if isinstance(self._engine, CodingEngineAdapter):
            eng_health = self._engine.health_check()
            engine_status = eng_health.get("status", "healthy")
            return {
                "provider": self.name,
                "mode": "real" if engine_status != "degraded" else "degraded",
                "status": "healthy" if engine_status == "configured" else engine_status,
                "engine": eng_health,
            }
        return {"provider": self.name, "mode": "real", "status": "healthy", "engine_type": type(self._engine).__name__}


# ── LLM Gateway ──


class LLMGateway:
    """Routes agent LLM requests to configured providers.

    Usage:
        gateway = LLMGateway()
        gateway.register(MockLLMProvider(), default=True)
        gateway.register(MedicalCodingLLMProvider(), alias="medical-coding")

        result = await gateway.generate(messages, provider="default")
    """

    def __init__(
        self,
        *,
        data_policy: Any | None = None,
        tenant_provider_resolver: Callable[
            [dict[str, Any] | None],
            Awaitable[dict[str, Any] | None] | dict[str, Any] | None,
        ] | None = None,
    ):
        self._providers: dict[str, BaseLLMProvider] = {}
        self._default: str | None = None
        self._aliases: dict[str, str] = {}
        self._data_policy = data_policy
        self._tenant_provider_resolver = tenant_provider_resolver
        # Phase A1D.4 (A1C-B-007) — ordered fallback chain.
        # When the primary returns a degraded response, the gateway walks
        # this chain in order until a healthy response is found.
        self.fallback_chain: list[BaseLLMProvider] = []

    def _egress_denial(self, provider: BaseLLMProvider) -> dict[str, Any] | None:
        """Return a structured denial without invoking the provider."""

        if self._data_policy is None:
            return None
        provider_name = str(
            getattr(provider, "policy_provider_name", "")
            or getattr(provider, "name", "")
            or ""
        )
        decision = self._data_policy.egress_decision(provider_name)
        if decision.get("decision") == "allow":
            return None
        result = _mock_fallback_response("provider_egress_denied")
        result["egress_decision"] = decision
        result["blocked_provider"] = provider_name
        return result

    async def _generate_with_policy(
        self,
        provider: BaseLLMProvider,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict] | None,
        response_schema: dict | None,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        denied = self._egress_denial(provider)
        if denied is not None:
            return denied
        return await provider.generate(
            messages=messages,
            tools=tools,
            response_schema=response_schema,
            context=context,
        )

    def register(self, provider: BaseLLMProvider, *, default: bool = False, alias: str = "") -> "LLMGateway":
        """Register a provider. If default=True, set as the default provider."""
        self._providers[provider.name] = provider
        if alias:
            self._aliases[alias] = provider.name
        if default:
            self._default = provider.name
        return self

    def register_fallback(self, provider: BaseLLMProvider) -> "LLMGateway":
        """Phase A1D.4 (A1C-B-007) — append a fallback provider.

        Fallbacks form an ordered chain. When the primary returns a
        response with ``degraded=True``, ``generate()`` walks the chain
        in order until a healthy response is found. If every fallback
        is also degraded, the last degraded response is returned with a
        ``failover_trail`` recording every provider that was tried.
        """
        self.fallback_chain.append(provider)
        return self

    def get(self, name: str = "") -> BaseLLMProvider:
        """Get a provider by name, alias, or the default.

        Raises LLMProviderNotConfigured if no provider is available.
        """
        key = self._aliases.get(name, name)
        if key and key in self._providers:
            return self._providers[key]
        if name and name != "default":
            raise LLMProviderNotConfigured(
                f"LLM provider or deployment '{name}' is not registered"
            )
        if self._default and self._default in self._providers:
            return self._providers[self._default]
        # Return any available provider as last resort
        if self._providers:
            return next(iter(self._providers.values()))
        raise LLMProviderNotConfigured()

    def get_exact(self, name: str) -> BaseLLMProvider:
        """Resolve a named deployment without falling back to the default."""

        key = self._aliases.get(name, name)
        if key and key in self._providers:
            return self._providers[key]
        raise LLMProviderNotConfigured(
            f"LLM deployment '{name}' is not registered"
        )

    async def _resolve_primary(
        self,
        provider: str,
        context: dict[str, Any] | None,
    ) -> tuple[BaseLLMProvider | None, dict[str, Any] | None, dict[str, Any] | None]:
        """Return provider, routing metadata, or a fail-closed result."""

        route: dict[str, Any] | None = None
        if self._tenant_provider_resolver is not None:
            try:
                candidate = self._tenant_provider_resolver(context)
                route = await candidate if asyncio.iscoroutine(candidate) else candidate
            except Exception as exc:
                logger.warning(
                    "Tenant model policy resolution failed error_type=%s",
                    type(exc).__name__,
                )
                failure = _mock_fallback_response(
                    "tenant_model_policy_resolution_failed"
                )
                failure["model_routing"] = {
                    "mode": "unknown",
                    "decision": "deny",
                    "reason": "policy_resolution_failed",
                }
                return None, None, failure

        if isinstance(route, dict) and route.get("mode") == "pinned":
            deployment_id = str(route.get("deployment_id") or "").strip().lower()
            routing = {
                "mode": "pinned",
                "deployment_id": deployment_id,
                "selection_version": int(route.get("version") or 0),
                "decision": "allow",
            }
            if not deployment_id:
                failure = _mock_fallback_response(
                    "tenant_model_deployment_unavailable"
                )
                routing.update({"decision": "deny", "reason": "empty_deployment_id"})
                failure["model_routing"] = routing
                return None, routing, failure
            if provider and provider != "default":
                requested_key = self._aliases.get(provider, provider)
                selected_key = self._aliases.get(deployment_id, deployment_id)
                if requested_key != selected_key:
                    failure = _mock_fallback_response(
                        "tenant_model_deployment_conflict"
                    )
                    routing.update({
                        "decision": "deny",
                        "reason": "explicit_provider_conflicts_with_tenant_selection",
                    })
                    failure["model_routing"] = routing
                    return None, routing, failure
            try:
                return self.get_exact(deployment_id), routing, None
            except LLMProviderNotConfigured:
                failure = _mock_fallback_response(
                    "tenant_model_deployment_unavailable"
                )
                routing.update({"decision": "deny", "reason": "deployment_not_registered"})
                failure["model_routing"] = routing
                return None, routing, failure

        routing = None
        if isinstance(route, dict):
            routing = {
                "mode": "inherit",
                "deployment_id": self._default or "",
                "selection_version": int(route.get("version") or 0),
                "decision": "allow",
            }
        return self.get(provider), routing, None

    @staticmethod
    def _stamp_model_routing(
        result: dict[str, Any],
        routing: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if routing is not None:
            result.setdefault("model_routing", routing)
        return result

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        provider: str = "",
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Route a generation request to the appropriate provider.

        Phase A1D.4 (A1C-B-007) — auto-failover. When the primary
        returns a degraded response, walk ``fallback_chain`` in order
        until a healthy response is found. Provenance is stamped:

          - ``fallback_from`` — name of the original (degraded) primary
          - ``fallback_reason`` — degraded_reason returned by the primary
          - ``failover_trail`` — list of ``{provider, reason}`` for every
            provider tried (only present when failover occurred)
        """
        primary, routing, routing_failure = await self._resolve_primary(
            provider, context,
        )
        if routing_failure is not None:
            return routing_failure
        assert primary is not None
        primary_name = getattr(primary, "name", provider or "primary")
        result = await self._generate_with_policy(
            primary,
            messages=messages,
            tools=tools,
            response_schema=response_schema,
            context=context,
        )

        # Healthy primary — short-circuit.
        if not (isinstance(result, dict) and result.get("degraded") is True):
            result.setdefault("provider", primary_name)
            return self._stamp_model_routing(result, routing)

        # A pinned tenant deployment must never silently fail over to another
        # model. The administrator explicitly approved this exact deployment.
        if routing is not None and routing.get("mode") == "pinned":
            result.setdefault("provider", primary_name)
            return self._stamp_model_routing(result, routing)

        # Primary degraded — record trail and walk fallback chain.
        primary_reason = result.get("degraded_reason", "degraded")
        trail: list[dict[str, str]] = [
            {"provider": primary_name, "reason": primary_reason},
        ]

        for fb in self.fallback_chain:
            fb_result = await self._generate_with_policy(
                fb,
                messages=messages,
                tools=tools,
                response_schema=response_schema,
                context=context,
            )
            fb_name = getattr(fb, "name", "fallback")
            if isinstance(fb_result, dict) and fb_result.get("degraded") is not True:
                # Healthy fallback — stamp provenance and return.
                fb_result.setdefault("provider", fb_name)
                fb_result.setdefault("fallback_from", primary_name)
                fb_result.setdefault("fallback_reason", primary_reason)
                fb_result.setdefault("failover_trail", trail)
                return self._stamp_model_routing(fb_result, routing)
            # Fallback also degraded — record and continue.
            trail.append({
                "provider": fb_name,
                "reason": fb_result.get("degraded_reason", "degraded") if isinstance(fb_result, dict) else "degraded",
            })

        # Every provider degraded — return last response with full trail.
        result.setdefault("fallback_from", primary_name)
        result.setdefault("provider", trail[-1]["provider"] if trail else primary_name)
        result.setdefault("fallback_reason", primary_reason)
        result["failover_trail"] = trail
        return self._stamp_model_routing(result, routing)

    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        provider: str = "",
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Route provider-native events while preserving failover semantics.

        Delta events are provisional.  A degraded provider is followed by a
        ``provider_reset`` event before the fallback starts, so downstream
        buffers can discard partial text/tool arguments.  Only one terminal
        ``completed`` event is emitted, and it uses the same provenance fields
        as :meth:`generate`.
        """
        primary, routing, routing_failure = await self._resolve_primary(
            provider, context,
        )
        if routing_failure is not None:
            yield {
                "type": "completed",
                "native": False,
                "provider": "tenant_policy",
                "result": routing_failure,
            }
            return
        assert primary is not None
        candidates = [primary]
        if not (routing is not None and routing.get("mode") == "pinned"):
            candidates.extend(self.fallback_chain)
        primary_name = getattr(primary, "name", provider or "primary")
        primary_reason = ""
        trail: list[dict[str, str]] = []
        last_result: dict[str, Any] | None = None

        for index, candidate in enumerate(candidates):
            candidate_name = getattr(candidate, "name", f"provider_{index}")
            completed: dict[str, Any] | None = None
            denied = self._egress_denial(candidate)
            if denied is not None:
                completed = denied
            else:
                async for event in candidate.generate_stream(
                    messages=messages,
                    tools=tools,
                    response_schema=response_schema,
                    context=context,
                ):
                    if not isinstance(event, dict):
                        continue
                    if event.get("type") == "completed":
                        result = event.get("result")
                        completed = result if isinstance(result, dict) else {
                            "content": str(result or ""),
                            "degraded": True,
                            "degraded_reason": "invalid_stream_result",
                        }
                        continue
                    yield {**event, "provider": candidate_name}

            if completed is None:
                completed = _mock_fallback_response(
                    "provider_stream_missing_completion"
                )
            last_result = completed
            degraded = completed.get("degraded") is True
            if not degraded:
                if index > 0:
                    completed.setdefault("fallback_from", primary_name)
                    completed.setdefault("fallback_reason", primary_reason)
                    completed.setdefault("failover_trail", list(trail))
                completed = self._stamp_model_routing(completed, routing)
                yield {
                    "type": "completed",
                    "native": bool(completed.get("stream_native", False)),
                    "provider": candidate_name,
                    "result": completed,
                }
                return

            reason = str(completed.get("degraded_reason") or "degraded")
            if index == 0:
                primary_reason = reason
            trail.append({"provider": candidate_name, "reason": reason})
            if index < len(candidates) - 1:
                yield {
                    "type": "provider_reset",
                    "native": True,
                    "provider": candidate_name,
                    "reason": reason,
                    "next_provider": getattr(
                        candidates[index + 1], "name", f"provider_{index + 1}"
                    ),
                }

        assert last_result is not None
        last_result.setdefault("fallback_from", primary_name)
        last_result.setdefault("fallback_reason", primary_reason or "degraded")
        last_result["failover_trail"] = trail
        last_result = self._stamp_model_routing(last_result, routing)
        yield {
            "type": "completed",
            "native": bool(last_result.get("stream_native", False)),
            "provider": trail[-1]["provider"] if trail else primary_name,
            "result": last_result,
        }

    def list_providers(self) -> dict[str, dict]:
        """Return health status of all registered providers."""
        return {name: p.health_check() for name, p in self._providers.items()}

    @property
    def registered_deployments(self) -> tuple[str, ...]:
        return tuple(self._providers)

    @property
    def is_configured(self) -> bool:
        return len(self._providers) > 0

    @property
    def default_provider(self) -> str | None:
        return self._default
