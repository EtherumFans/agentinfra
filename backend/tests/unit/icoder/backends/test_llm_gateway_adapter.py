"""Tests for ``icoder_runtime.backends.llm_gateway_adapter`` — Phase 4-B Step 1.

Verifies the adapter bridges ``LLMGateway.generate(messages: list[dict])``
to the ``LLMClient.complete(system_prompt, user_input)`` Protocol that
``PureLLMProvider`` expects.

Phase 4-C additions:
  - ``complete()`` threads ``tools`` param to gateway
  - ``complete_messages()`` multi-round variant accepts full messages list
  - ``LLMResponse.tool_calls`` populated from gateway result

Covers:
  - ``complete()`` builds the right messages list (system + user)
  - ``complete()`` returns ``LLMResponse`` with text/latency_ms/raw populated
  - ``complete()`` detects ``degraded`` flag from gateway fallback response
  - ``complete()`` surfaces gateway exceptions as ``LLMResponse`` with
    ``finish_reason="gateway_error:..."`` (never raises to caller)
  - ``complete()`` forwards ``tools`` to ``gateway.generate(tools=...)``
  - ``complete_messages()`` accepts a full messages list (Phase 4-C)
  - ``LLMResponse.tool_calls`` populated from gateway result (Phase 4-C)
  - ``stream()`` raises ``NotImplementedError`` (Phase 4-D scope)
  - Adapter is reusable across providers (stateless)
"""
from __future__ import annotations

import pytest

from icoder_runtime.backends.llm_gateway_adapter import LLMGatewayAdapter
from icoder_runtime.backends.pure_llm_provider import LLMResponse


# ── Mock gateway (stand-in for LLMGateway) ─────────────────────────


class _MockGateway:
    """Minimal stand-in for ``LLMGateway``. Captures calls for assertions.

    Phase 4-C: ``response_tool_calls`` lets a test simulate the LLM
    requesting tool calls (the adapter should surface them on
    ``LLMResponse.tool_calls``).
    """

    def __init__(self, *, response_text: str = "mock", latency_ms: int = 5,
                 degraded: bool = False, degraded_reason: str = "",
                 response_tool_calls: list[dict] | None = None,
                 raise_exc: Exception | None = None) -> None:
        self._response_text = response_text
        self._latency_ms = latency_ms
        self._degraded = degraded
        self._degraded_reason = degraded_reason
        self._response_tool_calls = response_tool_calls
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def generate(self, messages, *, provider: str = "",
                       tools=None, response_schema=None, context=None):
        if self._raise is not None:
            raise self._raise
        self.calls.append({
            "messages": messages,
            "provider": provider,
            "tools": tools,
            "response_schema": response_schema,
            "context": context,
        })
        result = {
            "content": self._response_text,
            "model": "mock/1.0",
            "usage": {"input_tokens": 10, "output_tokens": 20},
            "latency_ms": self._latency_ms,
        }
        if self._degraded:
            result["degraded"] = True
            result["degraded_reason"] = self._degraded_reason or "test"
            result["is_mock"] = True
            result["provider"] = "mock"
        if self._response_tool_calls:
            result["tool_calls"] = self._response_tool_calls
        return result


# ── complete() builds the right messages ───────────────────────────


@pytest.mark.asyncio
async def test_complete_builds_system_plus_user_messages():
    """complete() must construct [{system}, {user}] for LLMGateway.generate."""
    gw = _MockGateway(response_text='{"review_conclusion":"PASS"}')
    adapter = LLMGatewayAdapter(gw)
    resp = await adapter.complete(
        system_prompt="You are Note Completeness.",
        user_input="主诉：心悸3年...",
    )
    assert len(gw.calls) == 1
    messages = gw.calls[0]["messages"]
    assert len(messages) == 2
    assert messages[0] == {"role": "system", "content": "You are Note Completeness."}
    assert messages[0]["role"] == "system"
    assert "心悸" in messages[1]["content"]
    assert messages[1]["role"] == "user"


@pytest.mark.asyncio
async def test_complete_passes_context_with_temperature_max_tokens_timeout():
    """context dict carries temperature/max_tokens/timeout_seconds."""
    gw = _MockGateway(response_text="ok")
    adapter = LLMGatewayAdapter(gw)
    await adapter.complete(
        system_prompt="sys", user_input="hi",
        temperature=0.3, max_tokens=2048, timeout_seconds=30.0,
    )
    ctx = gw.calls[0]["context"]
    assert ctx["temperature"] == 0.3
    assert ctx["max_tokens"] == 2048
    assert ctx["timeout_seconds"] == 30.0


@pytest.mark.asyncio
async def test_complete_passes_provider_to_gateway():
    """gateway_provider constructor arg flows through to gateway.generate(provider=...)."""
    gw = _MockGateway(response_text="ok")
    adapter = LLMGatewayAdapter(gw, provider="mock")
    await adapter.complete(system_prompt="sys", user_input="hi")
    assert gw.calls[0]["provider"] == "mock"


# ── complete() returns LLMResponse ─────────────────────────────────


@pytest.mark.asyncio
async def test_complete_returns_llm_response_with_text():
    gw = _MockGateway(response_text='{"review_conclusion":"PASS"}', latency_ms=42)
    adapter = LLMGatewayAdapter(gw)
    resp = await adapter.complete(system_prompt="sys", user_input="hi")
    assert isinstance(resp, LLMResponse)
    assert resp.text == '{"review_conclusion":"PASS"}'
    assert resp.latency_ms == 42


@pytest.mark.asyncio
async def test_complete_returns_raw_gateway_result():
    """raw_provider_response carries the full gateway result dict for trace."""
    gw = _MockGateway(response_text="ok", latency_ms=7)
    adapter = LLMGatewayAdapter(gw)
    resp = await adapter.complete(system_prompt="sys", user_input="hi")
    assert resp.raw["model"] == "mock/1.0"
    assert resp.raw["usage"]["input_tokens"] == 10
    assert resp.raw["latency_ms"] == 7


# ── degraded detection ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_detects_degraded_fallback_response():
    """When gateway returns degraded=True, adapter sets finish_reason='degraded:...'."""
    gw = _MockGateway(
        response_text="degraded fallback",
        degraded=True,
        degraded_reason="no_api_key",
    )
    adapter = LLMGatewayAdapter(gw)
    resp = await adapter.complete(system_prompt="sys", user_input="hi")
    assert resp.finish_reason == "degraded:no_api_key"
    assert resp.raw.get("degraded") is True


# ── error handling ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_swallows_gateway_exceptions():
    """If gateway.generate raises, adapter returns LLMResponse with error reason — never raises."""
    gw = _MockGateway(raise_exc=RuntimeError("gateway exploded"))
    adapter = LLMGatewayAdapter(gw)
    resp = await adapter.complete(system_prompt="sys", user_input="hi")
    assert isinstance(resp, LLMResponse)
    assert resp.text == ""
    assert "gateway_error" in resp.finish_reason
    assert "RuntimeError" in resp.finish_reason
    assert "gateway exploded" in resp.raw.get("adapter_error", "")


@pytest.mark.asyncio
async def test_complete_handles_non_dict_gateway_result():
    """Defensive — if gateway returns non-dict, adapter doesn't crash."""
    class _BadGateway:
        async def generate(self, messages, **kwargs):
            return "not a dict"
    adapter = LLMGatewayAdapter(_BadGateway())
    resp = await adapter.complete(system_prompt="sys", user_input="hi")
    assert resp.text == "not a dict"
    assert resp.finish_reason == "non_dict_response"


# ── stream() ───────────────────────────────────────────────────────


def test_stream_raises_not_implemented():
    """Phase 4-C: streaming still not supported — NotImplementedError is intentional."""
    adapter = LLMGatewayAdapter(_MockGateway())
    with pytest.raises(NotImplementedError, match="Phase 4-C"):
        adapter.stream(system_prompt="sys", user_input="hi")


# ── adapter is stateless / reusable ────────────────────────────────


@pytest.mark.asyncio
async def test_adapter_reusable_across_invokes():
    """One adapter instance can serve multiple complete() calls."""
    gw = _MockGateway(response_text="ok")
    adapter = LLMGatewayAdapter(gw)
    await adapter.complete(system_prompt="sys1", user_input="hi1")
    await adapter.complete(system_prompt="sys2", user_input="hi2")
    assert len(gw.calls) == 2
    assert gw.calls[0]["messages"][0]["content"] == "sys1"
    assert gw.calls[1]["messages"][0]["content"] == "sys2"


# ── Phase 4-C: tools threading + complete_messages + tool_calls ──


@pytest.mark.asyncio
async def test_complete_forwards_tools_to_gateway():
    """Phase 4-C: ``tools`` param threads through to gateway.generate(tools=...)."""
    gw = _MockGateway(response_text="ok")
    adapter = LLMGatewayAdapter(gw)
    tool_schemas = [{
        "type": "function",
        "function": {
            "name": "verify_code",
            "description": "Verify an ICD-10 code",
            "parameters": {"type": "object", "properties": {"code": {"type": "string"}}},
        },
    }]
    await adapter.complete(
        system_prompt="sys", user_input="hi", tools=tool_schemas,
    )
    assert gw.calls[0]["tools"] == tool_schemas


@pytest.mark.asyncio
async def test_complete_passes_none_tools_when_omitted():
    """PureLLMProvider path: ``tools`` defaults to None and is forwarded as None."""
    gw = _MockGateway(response_text="ok")
    adapter = LLMGatewayAdapter(gw)
    await adapter.complete(system_prompt="sys", user_input="hi")
    # Gateway receives tools=None (not unset) — the adapter always forwards the kwarg.
    assert "tools" in gw.calls[0]
    assert gw.calls[0]["tools"] is None


@pytest.mark.asyncio
async def test_complete_surfaces_tool_calls_from_gateway():
    """Phase 4-C: gateway result ``tool_calls`` populates ``LLMResponse.tool_calls``."""
    fake_tool_calls = [{
        "id": "call_1",
        "type": "function",
        "function": {"name": "verify_code", "arguments": '{"code": "I25.10"}'},
    }]
    gw = _MockGateway(response_text="", response_tool_calls=fake_tool_calls)
    adapter = LLMGatewayAdapter(gw)
    resp = await adapter.complete(system_prompt="sys", user_input="hi", tools=[{"type": "function"}])
    assert isinstance(resp, LLMResponse)
    assert resp.tool_calls == fake_tool_calls
    assert resp.raw.get("tool_calls") == fake_tool_calls


@pytest.mark.asyncio
async def test_complete_returns_empty_tool_calls_when_gateway_omits_key():
    """When gateway doesn't return tool_calls, ``LLMResponse.tool_calls`` is empty list."""
    gw = _MockGateway(response_text="plain text response")
    adapter = LLMGatewayAdapter(gw)
    resp = await adapter.complete(system_prompt="sys", user_input="hi")
    assert resp.tool_calls == []


@pytest.mark.asyncio
async def test_complete_messages_accepts_full_messages_list():
    """Phase 4-C: ``complete_messages()`` accepts multi-round messages (system+user+assistant+tool)."""
    gw = _MockGateway(response_text="final answer")
    adapter = LLMGatewayAdapter(gw)
    messages = [
        {"role": "system", "content": "you are a validator"},
        {"role": "user", "content": "validate I25.10"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "verify_code", "arguments": '{"code": "I25.10"}'}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "content": '{"in_catalog": true}'},
    ]
    resp = await adapter.complete_messages(messages=messages, tools=[{"type": "function"}])
    assert isinstance(resp, LLMResponse)
    assert resp.text == "final answer"
    # The full messages list (including tool result) is forwarded verbatim.
    assert gw.calls[0]["messages"] == messages
    assert gw.calls[0]["tools"] == [{"type": "function"}]


@pytest.mark.asyncio
async def test_complete_messages_surfaces_tool_calls_for_next_round():
    """``complete_messages()`` surfaces tool_calls so the loop can continue."""
    fake_tool_calls = [{
        "id": "call_2", "type": "function",
        "function": {"name": "get_guidelines", "arguments": '{"code": "I25.10"}'},
    }]
    gw = _MockGateway(response_text="", response_tool_calls=fake_tool_calls)
    adapter = LLMGatewayAdapter(gw)
    resp = await adapter.complete_messages(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}],
        tools=[{"type": "function"}],
    )
    assert resp.tool_calls == fake_tool_calls


@pytest.mark.asyncio
async def test_complete_messages_never_raises_on_gateway_error():
    """``complete_messages()`` shares the never-raise error envelope with ``complete()``."""
    gw = _MockGateway(raise_exc=ConnectionError("network down"))
    adapter = LLMGatewayAdapter(gw)
    resp = await adapter.complete_messages(
        messages=[{"role": "user", "content": "hi"}],
    )
    assert isinstance(resp, LLMResponse)
    assert resp.text == ""
    assert "gateway_error" in resp.finish_reason
    assert "ConnectionError" in resp.finish_reason

