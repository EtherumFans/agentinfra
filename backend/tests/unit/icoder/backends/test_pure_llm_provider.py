"""Tests for ``icoder_runtime.backends.pure_llm_provider`` — Phase 4-A Task 5.

Verifies the SKELETON (no real LLM wired):
  - Without llm_client, returns a deterministic placeholder.
  - Placeholder markdown contains user input + system prompt excerpts.
  - Status is parsed from markdown via _parse_status_from_markdown.
  - stream() yields backend_invoked → output_chunk* → finished.
  - With a mock LLMClient, the real LLM path returns the mock's text.
  - LLM timeout / error produces a fail envelope (never raises).
  - Provider metadata + output_contract + capabilities.
"""
from __future__ import annotations

import pytest

from icoder_runtime.backends import (
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    ProviderHealth,
)
from icoder_runtime.backends.pure_llm_provider import (
    LLMChunk,
    LLMResponse,
    PureLLMProvider,
)


def _ctx(agent_id: str = "note-completeness-agent") -> AgentRunContext:
    return AgentRunContext(
        run_id="run-test-1",
        context_id="ctx-test-1",
        agent_id=agent_id,
        redacted_input="patient with severe COPD and right heart failure",
        agent_pack={
            "agent": {"system_prompt": "You are the Note Completeness Agent."},
        },
    )


# ── Provider metadata ───────────────────────────────────────────────


def test_pure_llm_provider_metadata():
    p = PureLLMProvider()
    assert p.provider_id == "icoder.pure-llm.v1"
    assert p.backend_type == "pure_llm"
    assert p.deterministic is False
    assert p.supports_tool_calling is False
    assert p.supports_streaming is True


def test_pure_llm_provider_output_contract():
    p = PureLLMProvider()
    assert p.output_contract() == "icoder/PureLLMOutput/v1"


def test_pure_llm_provider_capabilities():
    p = PureLLMProvider()
    cap = p.capabilities()
    assert cap.provider_id == "icoder.pure-llm.v1"
    assert cap.backend_type == "pure_llm"


# ── LLMResponse Phase 4-C: tool_calls field ────────────────────────


def test_llm_response_defaults_to_empty_tool_calls():
    """LLMResponse without tool_calls arg has ``tool_calls == []``."""
    resp = LLMResponse(text="hello")
    assert resp.tool_calls == []


def test_llm_response_carries_tool_calls_list():
    """LLMResponse.tool_calls stores the provider-native tool call list."""
    fake_calls = [{
        "id": "call_1", "type": "function",
        "function": {"name": "verify_code", "arguments": '{"code": "I25.10"}'},
    }]
    resp = LLMResponse(text="", tool_calls=fake_calls)
    assert resp.tool_calls == fake_calls


def test_llm_response_tool_calls_none_becomes_empty_list():
    """Passing ``tool_calls=None`` explicitly still yields an empty list."""
    resp = LLMResponse(text="hi", tool_calls=None)
    assert resp.tool_calls == []


# ── health ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_degraded_without_llm_client():
    p = PureLLMProvider()
    h = await p.health()
    assert h.state == "degraded"
    assert "no llm_client" in h.details.get("note", "")


# ── invoke without llm_client (skeleton path) ─────────────────────


@pytest.mark.asyncio
async def test_invoke_skeleton_returns_placeholder_markdown():
    """Without llm_client, provider returns a deterministic placeholder."""
    p = PureLLMProvider()
    req = BackendRequest(
        system_prompt="You are Note Completeness.",
        user_input="patient with COPD",
    )
    resp = await p.invoke(req, _ctx())
    assert isinstance(resp, BackendResponse)
    assert resp.backend_provider == "icoder.pure-llm.v1"
    assert resp.backend_type == "pure_llm"
    assert resp.finish_state == "completed"
    assert resp.markdown  # non-empty
    assert "Skeleton Response" in resp.markdown
    assert "patient with COPD" in resp.markdown
    assert "You are Note Completeness" in resp.markdown
    assert resp.raw_provider_response.get("skeleton") is True


@pytest.mark.asyncio
async def test_invoke_uses_redacted_input_when_user_input_empty():
    """When req.user_input is empty, falls back to ctx.redacted_input."""
    p = PureLLMProvider()
    req = BackendRequest(system_prompt="sys")
    resp = await p.invoke(req, _ctx())
    assert "patient with severe COPD" in resp.markdown


@pytest.mark.asyncio
async def test_invoke_uses_agent_pack_system_prompt_when_empty():
    """When req.system_prompt is empty, pulls from ctx.agent_pack."""
    p = PureLLMProvider()
    req = BackendRequest(user_input="hello")
    resp = await p.invoke(req, _ctx())
    assert "Note Completeness Agent" in resp.markdown


@pytest.mark.asyncio
async def test_invoke_empty_input_returns_fail_envelope():
    """Both req.user_input AND ctx.redacted_input empty → fail envelope."""
    p = PureLLMProvider()
    req = BackendRequest(system_prompt="sys")
    ctx = AgentRunContext(
        run_id="r1", context_id="c1", agent_id="ag",
        redacted_input="",  # empty
    )
    resp = await p.invoke(req, ctx)
    assert resp.status == "fail"
    assert resp.finish_state == "failed"
    assert "empty user_input" in resp.summary


# ── invoke with mock LLMClient ─────────────────────────────────────


class _MockLLMClient:
    """Mock LLM client for the real-LLM path test."""

    def __init__(
        self, *, text: str = "mock response", finish_reason: str = "stop",
        latency_ms: int = 5, raise_exc: Exception | None = None,
    ) -> None:
        self._text = text
        self._finish_reason = finish_reason
        self._latency_ms = latency_ms
        self._raise = raise_exc

    async def complete(
        self, *, system_prompt, user_input, temperature=0.0,
        max_tokens=None, timeout_seconds=60.0,
    ) -> LLMResponse:
        if self._raise is not None:
            raise self._raise
        return LLMResponse(
            text=self._text, finish_reason=self._finish_reason,
            latency_ms=self._latency_ms,
        )

    def stream(self, *, system_prompt, user_input, **kwargs):
        raise NotImplementedError("stream not implemented in mock")


@pytest.mark.asyncio
async def test_invoke_with_mock_llm_returns_mock_text():
    """With a mock LLMClient, the real LLM path returns the mock's text."""
    mock = _MockLLMClient(text="# Status: complete\n\nAll checks passed.")
    p = PureLLMProvider(llm_client=mock)
    req = BackendRequest(system_prompt="sys", user_input="hello")
    resp = await p.invoke(req, _ctx())
    assert resp.status == "complete"  # parsed from markdown
    assert "All checks passed" in resp.markdown
    assert resp.raw_provider_response == {}  # LLMResponse.raw default


@pytest.mark.asyncio
async def test_invoke_llm_timeout_returns_fail_envelope():
    """LLM timeout never raises — returns fail envelope."""
    mock = _MockLLMClient(raise_exc=TimeoutError("LLM timed out"))
    p = PureLLMProvider(llm_client=mock)
    req = BackendRequest(user_input="hello", system_prompt="sys")
    resp = await p.invoke(req, _ctx())
    assert resp.status == "fail"
    assert resp.finish_state == "failed"
    assert "timeout" in resp.finish_reason.lower()


@pytest.mark.asyncio
async def test_invoke_llm_generic_error_returns_fail_envelope():
    """Generic LLM errors also become fail envelopes."""
    mock = _MockLLMClient(raise_exc=RuntimeError("internal LLM error"))
    p = PureLLMProvider(llm_client=mock)
    req = BackendRequest(user_input="hello", system_prompt="sys")
    resp = await p.invoke(req, _ctx())
    assert resp.status == "fail"
    assert "RuntimeError" in resp.finish_reason


# ── stream ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_skeleton_yields_three_event_kinds():
    """stream() yields backend_invoked → output_chunk+ → finished."""
    p = PureLLMProvider()
    req = BackendRequest(system_prompt="sys", user_input="hello world")
    events = []
    async for ev in p.stream(req, _ctx()):
        events.append(ev)
    steps = [e["step"] for e in events]
    assert steps[0] == "backend_invoked"
    assert steps[-1] == "finished"
    assert "output_chunk" in steps
    # Chunks concatenate to the original markdown.
    chunks = "".join(
        e["payload"]["delta"] for e in events
        if e["step"] == "output_chunk"
    )
    assert chunks == events[0]["payload"].markdown


# ── _parse_status_from_markdown ─────────────────────────────────────


def test_parse_status_picks_up_explicit_keywords():
    from icoder_runtime.backends.pure_llm_provider import _parse_status_from_markdown
    assert _parse_status_from_markdown("Status: requires_review") == "requires_review"
    assert _parse_status_from_markdown("Status: non_compliant") == "non_compliant"
    assert _parse_status_from_markdown("Status: compliant") == "compliant"
    assert _parse_status_from_markdown("Status: warning") == "warning"
    assert _parse_status_from_markdown("Status: fail") == "fail"
    assert _parse_status_from_markdown("Status: pass") == "pass"
    assert _parse_status_from_markdown("Status: complete") == "complete"


def test_parse_status_defaults_to_complete_when_unknown():
    from icoder_runtime.backends.pure_llm_provider import _parse_status_from_markdown
    assert _parse_status_from_markdown("no keywords here") == "complete"


def test_parse_status_incomplete_when_empty():
    from icoder_runtime.backends.pure_llm_provider import _parse_status_from_markdown
    assert _parse_status_from_markdown("") == "incomplete"


# ── Phase 4-B: llm_gateway constructor param ───────────────────────


@pytest.fixture
def fresh_registry_with_gateway():
    """Reset default registry and wire a mock gateway via set_gateway_lookup.

    Used to verify PureLLMProvider lazy-resolves the gateway via registry.get_gateway()
    when no llm_client/llm_gateway is provided at construction.
    """
    from icoder_runtime.backends.registry import (
        reset_default_registry,
        set_gateway_lookup,
    )
    reset_default_registry()

    class _MockGateway:
        async def generate(self, messages, *, provider="", tools=None,
                           response_schema=None, context=None):
            return {
                "content": "from registry gateway",
                "model": "mock",
                "usage": {"input_tokens": 5, "output_tokens": 10},
                "latency_ms": 7,
            }

    gw = _MockGateway()
    set_gateway_lookup(lambda: gw)
    try:
        yield gw
    finally:
        set_gateway_lookup(None)
        reset_default_registry()


@pytest.mark.asyncio
async def test_constructor_accepts_llm_gateway_via_adapter():
    """Phase 4-B: llm_gateway arg wraps via LLMGatewayAdapter to satisfy LLMClient."""
    class _MockGateway:
        async def generate(self, messages, *, provider="", tools=None,
                           response_schema=None, context=None):
            return {
                "content": "# Status: pass\n\nAll good.",
                "model": "mock",
                "usage": {"input_tokens": 5, "output_tokens": 10},
                "latency_ms": 12,
            }
    p = PureLLMProvider(llm_gateway=_MockGateway())
    # health() should now report ok (gateway is wired via adapter)
    h = await p.health()
    assert h.state == "ok"
    # invoke() should go through the adapter
    req = BackendRequest(system_prompt="sys", user_input="hello")
    resp = await p.invoke(req, _ctx())
    assert resp.backend_provider == "icoder.pure-llm.v1"
    assert resp.markdown == "# Status: pass\n\nAll good."
    assert resp.latency_ms == 12
    assert resp.status == "pass"  # parsed from "# Status: pass"


@pytest.mark.asyncio
async def test_constructor_priority_llm_client_over_llm_gateway():
    """If both llm_client and llm_gateway are provided, llm_client wins."""
    class _MockGateway:
        async def generate(self, messages, **kwargs):
            return {"content": "from gateway", "latency_ms": 1}
    mock_client = _MockLLMClient(text="from client", latency_ms=99)
    p = PureLLMProvider(llm_client=mock_client, llm_gateway=_MockGateway())
    req = BackendRequest(system_prompt="sys", user_input="hello")
    resp = await p.invoke(req, _ctx())
    assert resp.markdown == "from client"  # llm_client won


@pytest.mark.asyncio
async def test_constructor_no_llm_no_gateway_resolves_at_invoke(fresh_registry_with_gateway):
    """Phase 4-B: no llm_client and no llm_gateway at construction → lazy-resolve via registry.get_gateway()."""
    # fresh_registry_with_gateway fixture sets up a gateway via set_gateway_lookup
    p = PureLLMProvider()  # nothing wired at construction
    h = await p.health()
    assert h.state == "ok"  # gateway was lazy-resolved
    req = BackendRequest(system_prompt="sys", user_input="hello")
    resp = await p.invoke(req, _ctx())
    assert resp.markdown == "from registry gateway"
