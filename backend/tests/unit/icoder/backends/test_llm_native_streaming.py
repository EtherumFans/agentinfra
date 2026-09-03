from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx
import pytest

from icoder_runtime.backends.llm_gateway_adapter import LLMGatewayAdapter
from icoder_runtime.circuit_breaker import CircuitState, llm_circuit_breaker
from icoder_runtime.core.llm_gateway import (
    BaseLLMProvider,
    DeepSeekProvider,
    LLMGateway,
    OpenAICompatibleProvider,
)
from icoder_runtime.core.fallback_provider import (
    make_azure_openai_fallback,
    make_qwen_fallback,
)


@pytest.fixture(autouse=True)
def _closed_gateway_circuit() -> None:
    llm_circuit_breaker.state = CircuitState.CLOSED
    llm_circuit_breaker._failures = 0


def _deepseek_stream_transport(captured: dict[str, Any]) -> httpx.MockTransport:
    chunks = [
        {
            "id": "stream-1",
            "model": "deepseek-chat",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": "Hello "},
                "finish_reason": None,
            }],
            "usage": None,
        },
        {
            "id": "stream-1",
            "model": "deepseek-chat",
            "choices": [{
                "index": 0,
                "delta": {"content": "world"},
                "finish_reason": None,
            }],
            "usage": None,
        },
        {
            "id": "stream-1",
            "model": "deepseek-chat",
            "choices": [{
                "index": 0,
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "verify_code",
                            "arguments": '{"code":',
                        },
                    }],
                },
                "finish_reason": None,
            }],
            "usage": None,
        },
        {
            "id": "stream-1",
            "model": "deepseek-chat",
            "choices": [{
                "index": 0,
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {"arguments": '"I21.0"}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": None,
        },
        {
            "id": "stream-1",
            "model": "deepseek-chat",
            "choices": [],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 7,
                "total_tokens": 19,
            },
        },
    ]
    body = "".join(
        f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        for chunk in chunks
    ) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        captured["accept"] = request.headers.get("accept")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=body.encode("utf-8"),
        )

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_deepseek_native_stream_accumulates_text_tools_and_usage() -> None:
    captured: dict[str, Any] = {}
    provider = DeepSeekProvider(
        api_key="test-only",
        _transport=_deepseek_stream_transport(captured),
    )

    events = [
        event
        async for event in provider.generate_stream(
            messages=[{"role": "user", "content": "validate"}],
            tools=[{
                "type": "function",
                "function": {"name": "verify_code", "parameters": {}},
            }],
        )
    ]

    assert captured["payload"]["stream"] is True
    assert captured["payload"]["stream_options"] == {"include_usage": True}
    assert captured["accept"] == "text/event-stream"
    assert [event["delta"] for event in events if event["type"] == "text_delta"] == [
        "Hello ",
        "world",
    ]
    assert len([event for event in events if event["type"] == "tool_call_delta"]) == 2
    completed = events[-1]
    assert completed["type"] == "completed"
    assert completed["native"] is True
    result = completed["result"]
    assert result["content"] == "Hello world"
    assert result["finish_reason"] == "tool_calls"
    assert result["usage"] == {"input_tokens": 12, "output_tokens": 7}
    assert result["tool_calls"] == [{
        "id": "call_1",
        "type": "function",
        "function": {
            "name": "verify_code",
            "arguments": '{"code":"I21.0"}',
        },
    }]


class _ScriptedStreamProvider(BaseLLMProvider):
    def __init__(self, name: str, events: list[dict[str, Any]]) -> None:
        self.name = name
        self.events = events

    async def generate(self, messages, tools=None, response_schema=None, context=None):
        return self.events[-1]["result"]

    async def generate_stream(
        self, messages, tools=None, response_schema=None, context=None,
    ) -> AsyncIterator[dict[str, Any]]:
        for event in self.events:
            yield event


@pytest.mark.asyncio
async def test_gateway_resets_provisional_buffer_before_streaming_fallback() -> None:
    primary = _ScriptedStreamProvider("primary", [
        {"type": "text_delta", "native": True, "delta": "discard me"},
        {
            "type": "completed",
            "native": True,
            "result": {
                "content": "discard me",
                "degraded": True,
                "degraded_reason": "upstream_reset",
            },
        },
    ])
    fallback = _ScriptedStreamProvider("fallback", [
        {"type": "text_delta", "native": True, "delta": "safe result"},
        {
            "type": "completed",
            "native": True,
            "result": {"content": "safe result", "stream_native": True},
        },
    ])
    gateway = LLMGateway().register(primary, default=True)
    gateway.register_fallback(fallback)

    events = [
        event
        async for event in gateway.generate_stream(
            [{"role": "user", "content": "test"}],
        )
    ]

    assert [event["type"] for event in events] == [
        "text_delta",
        "provider_reset",
        "text_delta",
        "completed",
    ]
    assert events[1]["next_provider"] == "fallback"
    assert events[-1]["result"]["fallback_from"] == "primary"
    assert events[-1]["result"]["fallback_reason"] == "upstream_reset"


@pytest.mark.asyncio
async def test_adapter_preserves_native_delta_and_terminal_response() -> None:
    captured: dict[str, Any] = {}
    gateway = LLMGateway().register(
        DeepSeekProvider(
            api_key="test-only",
            _transport=_deepseek_stream_transport(captured),
        ),
        default=True,
    )
    adapter = LLMGatewayAdapter(gateway)

    chunks = [
        chunk
        async for chunk in adapter.stream(
            system_prompt="system",
            user_input="validate",
            tools=[{
                "type": "function",
                "function": {"name": "verify_code", "parameters": {}},
            }],
        )
    ]

    assert "".join(chunk.delta for chunk in chunks) == "Hello world"
    assert len([chunk for chunk in chunks if chunk.event_type == "tool_call_delta"]) == 2
    terminal = chunks[-1]
    assert terminal.event_type == "completed"
    assert terminal.native is True
    assert terminal.response.text == "Hello world"
    assert terminal.response.tool_calls[0]["function"]["name"] == "verify_code"
    assert terminal.response.cost_usd is not None


@pytest.mark.asyncio
async def test_deepseek_stream_without_done_fails_closed() -> None:
    chunk = {
        "id": "truncated",
        "model": "deepseek-chat",
        "choices": [{
            "index": 0,
            "delta": {"content": "partial unsafe result"},
            "finish_reason": None,
        }],
        "usage": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(f"data: {json.dumps(chunk)}\n\n").encode("utf-8"),
        )

    provider = DeepSeekProvider(
        api_key="test-only",
        _transport=httpx.MockTransport(handler),
    )
    events = [
        event
        async for event in provider.generate_stream(
            messages=[{"role": "user", "content": "test"}],
        )
    ]

    assert events[0]["type"] == "text_delta"
    terminal = events[-1]
    assert terminal["type"] == "completed"
    assert terminal["result"]["degraded"] is True
    assert terminal["result"]["degraded_reason"] == "provider_stream_truncated"


def _compatible_text_stream_transport(
    captured: dict[str, Any],
    *,
    model: str,
) -> httpx.MockTransport:
    chunks = [
        {
            "id": "compat-stream-1",
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": "safe "},
                "finish_reason": None,
            }],
            "usage": None,
        },
        {
            "id": "compat-stream-1",
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": "answer"},
                "finish_reason": "stop",
            }],
            "usage": None,
        },
        {
            "id": "compat-stream-1",
            "model": model,
            "choices": [],
            "usage": {
                "prompt_tokens": 8,
                "completion_tokens": 2,
                "total_tokens": 10,
            },
        },
    ]
    body = "".join(
        f"data: {json.dumps(chunk)}\n\n" for chunk in chunks
    ) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        captured["authorization"] = request.headers.get("authorization")
        captured["api_key"] = request.headers.get("api-key")
        captured["accept"] = request.headers.get("accept")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=body.encode("utf-8"),
        )

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_qwen_fallback_uses_native_openai_compatible_stream() -> None:
    captured: dict[str, Any] = {}
    provider = make_qwen_fallback(api_key="test-only", model="qwen-plus")
    provider._transport = _compatible_text_stream_transport(
        captured,
        model="qwen-plus",
    )

    events = [
        event
        async for event in provider.generate_stream(
            messages=[{"role": "user", "content": "test"}],
        )
    ]

    assert captured["url"].endswith("/compatible-mode/v1/chat/completions")
    assert captured["authorization"] == "Bearer test-only"
    assert captured["api_key"] is None
    assert captured["accept"] == "text/event-stream"
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["stream_options"] == {"include_usage": True}
    assert [event["delta"] for event in events if event["type"] == "text_delta"] == [
        "safe ",
        "answer",
    ]
    result = events[-1]["result"]
    assert result["content"] == "safe answer"
    assert result["provider"] == "qwen_fallback"
    assert result["finish_reason"] == "stop"
    assert result["usage"] == {"input_tokens": 8, "output_tokens": 2}
    assert result["stream_native"] is True


@pytest.mark.asyncio
async def test_gateway_streams_real_compatible_fallback_after_deepseek_degrades(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    # Integration modules may set the canonical credential during collection.
    # This no-key fallback test must never inherit it or reach the network.
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
    captured: dict[str, Any] = {}
    primary = DeepSeekProvider(api_key="")
    fallback = make_qwen_fallback(api_key="test-only", model="qwen-plus")
    fallback._transport = _compatible_text_stream_transport(
        captured,
        model="qwen-plus",
    )
    gateway = LLMGateway().register(primary, default=True)
    gateway.register_fallback(fallback)

    events = [
        event
        async for event in gateway.generate_stream(
            [{"role": "user", "content": "test"}],
        )
    ]

    assert [event["type"] for event in events] == [
        "provider_reset",
        "text_delta",
        "text_delta",
        "usage",
        "completed",
    ]
    assert events[0]["provider"] == "deepseek"
    assert events[0]["next_provider"] == "qwen_fallback"
    terminal = events[-1]
    assert terminal["provider"] == "qwen_fallback"
    assert terminal["result"]["content"] == "safe answer"
    assert terminal["result"]["fallback_from"] == "deepseek"
    assert terminal["result"]["fallback_reason"] == "no_api_key"
    assert terminal["result"]["failover_trail"] == [
        {"provider": "deepseek", "reason": "no_api_key"},
    ]


@pytest.mark.asyncio
async def test_azure_fallback_stream_uses_api_key_and_ignores_primary_circuit() -> None:
    captured: dict[str, Any] = {}
    provider = make_azure_openai_fallback(
        api_key="azure-test-only",
        endpoint="https://example.openai.azure.com",
        deployment="gpt-4o-mini",
        api_version="2024-10-21",
    )
    provider._transport = _compatible_text_stream_transport(
        captured,
        model="gpt-4o-mini",
    )
    llm_circuit_breaker.state = CircuitState.OPEN

    events = [
        event
        async for event in provider.generate_stream(
            messages=[{"role": "user", "content": "test"}],
        )
    ]

    assert captured["url"] == (
        "https://example.openai.azure.com/openai/deployments/gpt-4o-mini/"
        "chat/completions?api-version=2024-10-21"
    )
    assert captured["api_key"] == "azure-test-only"
    assert captured["authorization"] is None
    result = events[-1]["result"]
    assert result["provider"] == "azure_openai_fallback"
    assert result["content"] == "safe answer"
    assert result.get("degraded") is not True


@pytest.mark.asyncio
async def test_generic_compatible_stream_can_disable_usage_extension() -> None:
    captured: dict[str, Any] = {}
    provider = OpenAICompatibleProvider(
        api_key="not-needed",
        base_url="http://local.test/v1",
        model="local-model",
        stream_include_usage=False,
        _transport=_compatible_text_stream_transport(
            captured,
            model="local-model",
        ),
    )

    events = [
        event
        async for event in provider.generate_stream(
            messages=[{"role": "user", "content": "test"}],
        )
    ]

    assert "stream_options" not in captured["payload"]
    assert events[-1]["result"]["content"] == "safe answer"


@pytest.mark.asyncio
async def test_usage_only_completed_stream_has_defined_finish_reason() -> None:
    chunk = {
        "id": "usage-only",
        "model": "deepseek-chat",
        "choices": [],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 0,
            "total_tokens": 1,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=body.encode("utf-8"),
        )

    provider = DeepSeekProvider(
        api_key="test-only",
        _transport=httpx.MockTransport(handler),
    )
    events = [
        event
        async for event in provider.generate_stream(
            messages=[{"role": "user", "content": "test"}],
        )
    ]

    assert events[-1]["type"] == "completed"
    assert events[-1]["result"]["finish_reason"] == ""
