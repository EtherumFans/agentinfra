"""Tests for ``icoder_runtime.backends.llm_with_tools_provider``.

Covers:
  - SKELETON path (no llm_client): runs ONE tool call through
    ToolMCPCompatLayer and returns placeholder markdown.
  - REAL LLM path (Phase 4-C implemented): llm_client returns text →
    status='complete' (full multi-round tool-calling loop is tested
    in ``test_llm_with_tools_provider_real.py``).
  - validate_tool_scope rejects bad tool scope config.
  - stream() yields backend_invoked → tool_calls → output_chunk+ → finished.
  - ToolCallRecord is populated on the response.
  - Provider metadata + output_contract + capabilities.
"""
from __future__ import annotations

import pytest

from icoder_runtime.backends import (
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    ProviderHealth,
    ToolCallRecord,
)
from icoder_runtime.backends.llm_with_tools_provider import LLMWithToolsProvider
from icoder_runtime.backends.tool_mcp_compat_layer import (
    ToolCallResponse,
    ToolMCPCompatLayer,
)


def _ctx(agent_id: str = "code-validation-agent") -> AgentRunContext:
    return AgentRunContext(
        run_id="run-cv-1",
        context_id="ctx-cv-1",
        agent_id=agent_id,
        redacted_input="patient with STEMI",
        agent_pack={"agent": {"system_prompt": "You are Code Validation."}},
    )


class _FakeRequest:
    class _State:
        def __init__(self):
            self.context_id = "ctx-cv-1"
            self.run_id = "run-cv-1"
            self.mcp_run_auth_context = None

    class _App:
        def __init__(self):
            self.state = type("state", (), {})()

    def __init__(self):
        self.app = self._App()
        self.state = self._State()


# ── Provider metadata ───────────────────────────────────────────────


def test_llm_with_tools_provider_metadata():
    p = LLMWithToolsProvider()
    assert p.provider_id == "icoder.llm-with-tools.v1"
    assert p.backend_type == "llm_with_tools"
    assert p.deterministic is False
    assert p.supports_tool_calling is True
    assert p.supports_streaming is True


def test_llm_with_tools_provider_output_contract():
    p = LLMWithToolsProvider()
    assert p.output_contract() == "icoder/LLMWithToolsOutput/v1"


def test_llm_with_tools_provider_capabilities():
    p = LLMWithToolsProvider()
    cap = p.capabilities()
    assert cap.provider_id == "icoder.llm-with-tools.v1"
    assert cap.backend_type == "llm_with_tools"
    assert cap.supports_tool_calling is True


# ── health ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_degraded_without_llm_client():
    p = LLMWithToolsProvider()
    h = await p.health()
    assert h.state == "degraded"


# ── invoke: tool scope validation ─────────────────────────────────


@pytest.mark.asyncio
async def test_invoke_rejects_bad_tool_scope_with_mandatory_missing():
    """mandatory must be subset of scope — Code Validation requires verify+guidelines."""
    p = LLMWithToolsProvider()
    req = BackendRequest(
        system_prompt="sys", user_input="hello",
        tool_scope=["verify"],  # missing 'guidelines'
        mandatory_tools=["verify", "guidelines"],
    )
    resp = await p.invoke(req, _ctx(), request=_FakeRequest())
    assert resp.status == "fail"
    assert "tool_scope" in resp.summary
    assert resp.finish_state == "failed"


@pytest.mark.asyncio
async def test_invoke_rejects_forbidden_tool_in_scope():
    """forbidden ∩ scope must be empty — Compliance Guardrail forbids search."""
    p = LLMWithToolsProvider()
    req = BackendRequest(
        system_prompt="sys", user_input="hello",
        tool_scope=["verify", "guidelines", "search"],
        forbidden_tools=["search"],
    )
    resp = await p.invoke(req, _ctx(), request=_FakeRequest())
    assert resp.status == "fail"
    assert "forbidden" in resp.summary


# ── invoke: skeleton pipeline (no llm_client) ────────────────────


@pytest.mark.asyncio
async def test_invoke_skeleton_calls_one_tool_through_mcp(monkeypatch):
    """Without llm_client, skeleton runs ONE tool via ToolMCPCompatLayer.

    Verifies Task 6 requirement #1: "provider-native tool call →
    ToolMCPCompatLayer → MCP tools/call".
    """
    p = LLMWithToolsProvider()
    # Force list_available_tools to return a known tool.
    p._mcp_layer._list_tools_fn = lambda: [
        {"name": "verify_code", "description": "verify"},
    ]
    # Stub dispatch_tool to return a canned result.
    captured = []

    async def fake_dispatch(tool_name, args, request, *, run_id=None, **kwargs):
        captured.append((tool_name, args))
        return {"content": {"in_catalog": True}, "isError": False,
                "tool_name": tool_name, "duration_ms": 5}

    p._mcp_layer._dispatch_tool_fn = fake_dispatch
    req = BackendRequest(
        system_prompt="sys", user_input="I50.900",
        tool_scope=["verify_code"],
    )
    resp = await p.invoke(req, _ctx(), request=_FakeRequest())
    assert resp.backend_provider == "icoder.llm-with-tools.v1"
    assert resp.finish_state == "completed"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].tool_name == "verify_code"
    assert resp.tool_calls[0].result == {"in_catalog": True}
    # dispatch_tool was called once (Task 7 req: routes through dispatch_tool).
    assert len(captured) == 1
    assert captured[0][0] == "verify_code"


@pytest.mark.asyncio
async def test_invoke_skeleton_without_request_records_error_in_tool_call():
    """Without request, skeleton records an error ToolCallRecord."""
    p = LLMWithToolsProvider()
    p._mcp_layer._list_tools_fn = lambda: [{"name": "verify_code"}]
    req = BackendRequest(
        system_prompt="sys", user_input="hello",
        tool_scope=["verify_code"],
    )
    resp = await p.invoke(req, _ctx(), request=None)
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].error is not None
    assert "request" in resp.tool_calls[0].error.lower()


@pytest.mark.asyncio
async def test_invoke_skeleton_markdown_contains_tool_call_summary():
    """Placeholder markdown lists tool calls for frontend rendering."""
    p = LLMWithToolsProvider()
    p._mcp_layer._list_tools_fn = lambda: [{"name": "verify_code"}]

    async def fake_dispatch(tool_name, args, request, *, run_id=None, **kwargs):
        return {"content": {"ok": True}, "isError": False, "duration_ms": 9}

    p._mcp_layer._dispatch_tool_fn = fake_dispatch
    req = BackendRequest(
        system_prompt="sys", user_input="hello",
        tool_scope=["verify_code"],
    )
    resp = await p.invoke(req, _ctx(), request=_FakeRequest())
    assert "Tool Calls" in resp.markdown
    assert "verify_code" in resp.markdown
    assert "9ms" in resp.markdown


# ── invoke: real LLM pipeline (Phase 4-C implemented) ────────────


class _MockLLMClient:
    """Single-shot mock client — returns ``text`` and no ``tool_calls``.

    Phase 4-C: LLMWithToolsProvider now runs a real tool-calling loop.
    For tests that exercise the loop (multi-round, max_tool_rounds, etc.),
    see ``test_llm_with_tools_provider_real.py``. This client is the
    simplest case — LLM returns a final answer with no tool calls.
    """

    def __init__(self, text: str = "mock"):
        self._text = text

    async def complete(self, **kwargs):
        from icoder_runtime.backends.pure_llm_provider import LLMResponse
        return LLMResponse(text=self._text)


@pytest.mark.asyncio
async def test_invoke_with_llm_client_returns_complete_envelope():
    """Phase 4-C: real pipeline runs — LLM returns text, status='complete'."""
    p = LLMWithToolsProvider(llm_client=_MockLLMClient(text="All good."))
    req = BackendRequest(
        system_prompt="sys", user_input="hello",
        tool_scope=["verify"],
    )
    resp = await p.invoke(req, _ctx(), request=_FakeRequest())
    assert resp.backend_provider == "icoder.llm-with-tools.v1"
    assert resp.finish_state == "completed"
    # Mock returned text with no tool_calls → status defaults to "complete".
    assert resp.status == "complete"
    assert "All good" in resp.markdown
    assert resp.tool_calls == []  # no tool calls issued
    assert resp.raw_provider_response.get("tool_rounds") == 0


# ── stream ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_skeleton_yields_four_event_kinds():
    """stream() yields backend_invoked → tool_calls → output_chunk+ → finished."""
    p = LLMWithToolsProvider()
    p._mcp_layer._list_tools_fn = lambda: [{"name": "verify_code"}]

    async def fake_dispatch(tool_name, args, request, *, run_id=None, **kwargs):
        return {"content": {"ok": True}, "isError": False, "duration_ms": 1}

    p._mcp_layer._dispatch_tool_fn = fake_dispatch
    req = BackendRequest(
        system_prompt="sys", user_input="hello",
        tool_scope=["verify_code"],
    )
    events = []
    async for ev in p.stream(req, _ctx(), request=_FakeRequest()):
        events.append(ev)
    steps = [e["step"] for e in events]
    assert steps[0] == "backend_invoked"
    assert "tool_calls" in steps
    assert "output_chunk" in steps
    assert steps[-1] == "finished"
