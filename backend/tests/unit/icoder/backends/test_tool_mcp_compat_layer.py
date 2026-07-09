"""Tests for ``icoder_runtime.backends.tool_mcp_compat_layer`` — Phase 4-A Task 7.

Verifies:
  - provider_to_mcp accepts OpenAI-style and MCP-native shapes.
  - provider_to_mcp strips secret keys (defense-in-depth).
  - provider_to_mcp raises on missing name / non-dict args.
  - mcp_to_provider projects dispatch_tool result to ToolCallResponse.
  - list_available_tools filters by tool_scope.
  - validate_tool_scope enforces mandatory ⊆ scope, forbidden ∩ scope = ∅.
  - call() routes through dispatch_tool (not handler directly).
  - call() with no request returns NO_REQUEST error envelope.
  - to_tool_call_record projects to ToolCallRecord for OutputContract.
"""
from __future__ import annotations

import pytest

from icoder_runtime.backends import (
    AgentRunContext,
    ToolCallRecord,
)
from icoder_runtime.backends.tool_mcp_compat_layer import (
    ToolCallRequest,
    ToolCallResponse,
    ToolMCPCompatLayer,
)


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        run_id="run-mcp-1",
        context_id="ctx-mcp-1",
        agent_id="code-validation-agent",
    )


# ── provider_to_mcp ────────────────────────────────────────────────


def test_provider_to_mcp_openai_function_calling_shape():
    """OpenAI shape: {"name": "...", "arguments": {...}}."""
    layer = ToolMCPCompatLayer()
    req = layer.provider_to_mcp(
        {"name": "verify_code", "arguments": {"code": "I50.900"}},
        provider_id="icoder.llm-with-tools.v1",
    )
    assert isinstance(req, ToolCallRequest)
    assert req.tool_name == "verify_code"
    assert req.arguments == {"code": "I50.900"}


def test_provider_to_mcp_mcp_native_shape():
    """MCP-native shape: {"tool": "...", "input": {...}}."""
    layer = ToolMCPCompatLayer()
    req = layer.provider_to_mcp(
        {"tool": "search_icd", "input": {"query": "heart failure"}},
    )
    assert req.tool_name == "search_icd"
    assert req.arguments == {"query": "heart failure"}


def test_provider_to_mcp_strips_secret_keys():
    """Defense-in-depth: token / secret / api_key args are blanked."""
    layer = ToolMCPCompatLayer()
    req = layer.provider_to_mcp({
        "name": "search_icd",
        "arguments": {
            "query": "ok",
            "token": "Bearer abc.def.ghi",
            "api_key": "sk-1234567890",
            "normal_arg": "fine",
        },
    })
    assert req.arguments["token"] == "[REDACTED]"
    assert req.arguments["api_key"] == "[REDACTED]"
    assert req.arguments["query"] == "ok"
    assert req.arguments["normal_arg"] == "fine"


def test_provider_to_mcp_raises_on_missing_name():
    layer = ToolMCPCompatLayer()
    with pytest.raises(ValueError, match="missing 'name'"):
        layer.provider_to_mcp({"arguments": {}})


def test_provider_to_mcp_raises_on_non_dict_args():
    layer = ToolMCPCompatLayer()
    with pytest.raises(ValueError, match="arguments must be a dict"):
        layer.provider_to_mcp({"name": "x", "arguments": "not a dict"})


def test_provider_to_mcp_raises_on_non_dict_input():
    layer = ToolMCPCompatLayer()
    with pytest.raises(ValueError, match="must be a dict"):
        layer.provider_to_mcp(["not", "a", "dict"])  # type: ignore[arg-type]


def test_provider_to_mcp_propagates_run_id():
    layer = ToolMCPCompatLayer()
    req = layer.provider_to_mcp({
        "name": "verify_code", "arguments": {}, "run_id": "run-xyz",
    })
    assert req.run_id == "run-xyz"


# ── mcp_to_provider ────────────────────────────────────────────────


def test_mcp_to_provider_success_envelope():
    layer = ToolMCPCompatLayer()
    mcp_resp = {
        "content": {"in_catalog": True, "code": "I50.900"},
        "isError": False,
        "tool_name": "verify_code",
        "duration_ms": 42,
    }
    resp = layer.mcp_to_provider(mcp_resp)
    assert isinstance(resp, ToolCallResponse)
    assert resp.tool_name == "verify_code"
    assert resp.is_error is False
    assert resp.content == {"in_catalog": True, "code": "I50.900"}
    assert resp.duration_ms == 42


def test_mcp_to_provider_error_envelope():
    layer = ToolMCPCompatLayer()
    mcp_resp = {
        "content": None,
        "isError": True,
        "error_code": "MCP_AUTH_FORBIDDEN",
        "error_message": "scope forbidden",
        "tool_name": "search",
    }
    resp = layer.mcp_to_provider(mcp_resp)
    assert resp.is_error is True
    assert resp.error_code == "MCP_AUTH_FORBIDDEN"
    assert resp.error_message == "scope forbidden"


def test_mcp_to_provider_handles_non_dict_input():
    layer = ToolMCPCompatLayer()
    resp = layer.mcp_to_provider("not a dict")  # type: ignore[arg-type]
    assert resp.is_error is True
    assert resp.error_code == "INVALID_RESPONSE"


def test_mcp_to_provider_to_provider_result_round_trip():
    """to_provider_result() gives a JSON-serializable dict for LLM loopback."""
    layer = ToolMCPCompatLayer()
    resp = layer.mcp_to_provider({
        "content": {"x": 1},
        "isError": False,
        "tool_name": "verify",
    })
    result = resp.to_provider_result()
    assert result["tool_name"] == "verify"
    assert result["content"] == {"x": 1}
    assert result["is_error"] is False


# ── list_available_tools ──────────────────────────────────────────


def test_list_available_tools_filters_by_scope():
    """Tools not in tool_scope are omitted."""
    layer = ToolMCPCompatLayer(list_tools_fn=lambda: [
        {"name": "verify_code", "description": "verify"},
        {"name": "search_icd", "description": "search"},
        {"name": "rerank_codes", "description": "rerank"},
    ])
    visible = layer.list_available_tools(
        agent_id="ag", provider_id="icoder.llm-with-tools.v1",
        tool_scope=["verify_code", "rerank_codes"],
    )
    names = sorted(t["name"] for t in visible)
    assert names == ["rerank_codes", "verify_code"]


def test_list_available_tools_returns_all_when_no_scope():
    layer = ToolMCPCompatLayer(list_tools_fn=lambda: [
        {"name": "verify_code"},
        {"name": "search_icd"},
    ])
    visible = layer.list_available_tools()
    assert len(visible) == 2


# ── validate_tool_scope ───────────────────────────────────────────


def test_validate_tool_scope_passes_when_clean():
    layer = ToolMCPCompatLayer()
    ok, errors = layer.validate_tool_scope(
        ["verify", "guidelines", "explore"],
        mandatory=["verify", "guidelines"],
        forbidden=["search"],
    )
    assert ok is True
    assert errors == []


def test_validate_tool_scope_flags_missing_mandatory():
    """Corti Code Validation: verify+guidelines are mandatory."""
    layer = ToolMCPCompatLayer()
    ok, errors = layer.validate_tool_scope(
        ["verify"],  # missing 'guidelines'
        mandatory=["verify", "guidelines"],
    )
    assert ok is False
    assert any("mandatory" in e for e in errors)


def test_validate_tool_scope_flags_forbidden_in_scope():
    """Corti Compliance Guardrail: search is forbidden."""
    layer = ToolMCPCompatLayer()
    ok, errors = layer.validate_tool_scope(
        ["verify", "guidelines", "explore", "search"],  # search forbidden
        forbidden=["search"],
    )
    assert ok is False
    assert any("forbidden" in e for e in errors)


# ── call (routes through dispatch_tool, NOT handler directly) ────


class _FakeRequest:
    """Stand-in for FastAPI Request — has app.state + state."""

    class _State:
        def __init__(self):
            self.context_id = "ctx-1"
            self.run_id = "run-1"
            self.mcp_run_auth_context = None

    class _App:
        def __init__(self):
            self.state = type("state", (), {})()

    def __init__(self):
        self.app = self._App()
        self.state = self._State()


@pytest.mark.asyncio
async def test_call_with_no_dispatch_fn_returns_dispatch_unavailable():
    """When dispatch_tool can't be resolved, returns DISPATCH_UNAVAILABLE."""
    layer = ToolMCPCompatLayer(dispatch_tool_fn=None)
    # Force _get_dispatch_fn to return None
    layer._dispatch_tool_fn = None
    layer._get_dispatch_fn = lambda: None  # type: ignore[method-assign]
    resp = await layer.call(
        {"name": "verify_code", "arguments": {"code": "I50.900"}},
        _ctx(), request=_FakeRequest(),
    )
    assert resp.is_error is True
    assert resp.error_code == "DISPATCH_UNAVAILABLE"


@pytest.mark.asyncio
async def test_call_with_no_request_returns_no_request_error():
    """call() without request returns NO_REQUEST (Task 7 req: needs request)."""
    layer = ToolMCPCompatLayer()
    resp = await layer.call(
        {"name": "verify_code", "arguments": {}},
        _ctx(), request=None,
    )
    assert resp.is_error is True
    assert resp.error_code == "NO_REQUEST"


@pytest.mark.asyncio
async def test_call_routes_through_dispatch_tool_not_handler_directly():
    """call() invokes dispatch_tool_fn, never the handler directly.

    This is the critical Task 7 requirement #2: "不绕过 dispatch_tool".
    """
    calls = []

    async def fake_dispatch(tool_name, args, request, *, run_id=None, **kwargs):
        calls.append((tool_name, args, run_id))
        return {"content": {"verified": True}, "isError": False,
                "tool_name": tool_name, "duration_ms": 7}

    layer = ToolMCPCompatLayer(dispatch_tool_fn=fake_dispatch)
    resp = await layer.call(
        {"name": "verify_code", "arguments": {"code": "I50.900"}},
        _ctx(), request=_FakeRequest(),
    )
    # dispatch_tool was called with the right args.
    assert len(calls) == 1
    assert calls[0][0] == "verify_code"
    assert calls[0][1] == {"code": "I50.900"}
    # Result is projected correctly.
    assert resp.is_error is False
    assert resp.content == {"verified": True}
    assert resp.duration_ms == 7


@pytest.mark.asyncio
async def test_call_dispatch_exception_returns_error_envelope():
    """If dispatch_tool raises, call() wraps it into an error envelope."""
    async def raising_dispatch(tool_name, args, request, *, run_id=None, **kwargs):
        raise RuntimeError("dispatch exploded")

    layer = ToolMCPCompatLayer(dispatch_tool_fn=raising_dispatch)
    resp = await layer.call(
        {"name": "verify_code", "arguments": {}},
        _ctx(), request=_FakeRequest(),
    )
    assert resp.is_error is True
    assert resp.error_code == "RuntimeError"
    assert "dispatch exploded" in resp.error_message


@pytest.mark.asyncio
async def test_call_strips_secrets_before_dispatch():
    """Secrets in tool args are stripped before reaching dispatch_tool."""
    captured_args = {}

    async def capturing_dispatch(tool_name, args, request, *, run_id=None, **kwargs):
        captured_args.update(args)
        return {"content": {}, "isError": False}

    layer = ToolMCPCompatLayer(dispatch_tool_fn=capturing_dispatch)
    await layer.call(
        {"name": "search", "arguments": {"q": "ok", "api_key": "sk-leaked"}},
        _ctx(), request=_FakeRequest(),
    )
    assert captured_args["api_key"] == "[REDACTED]"
    assert captured_args["q"] == "ok"


@pytest.mark.asyncio
async def test_call_forwards_round_index_and_caller_to_dispatch():
    """Phase 4-C — call() forwards round_index/caller kwargs to dispatch_tool.

    LLMWithToolsProvider stamps these on every tool call so the RunTrace
    ToolDispatchDetail panel can show which LLM round triggered the call.
    """
    captured: dict = {}

    async def capturing_dispatch(
        tool_name, args, request, *,
        run_id=None, round_index=None, caller=None, **kwargs,
    ):
        captured["round_index"] = round_index
        captured["caller"] = caller
        return {"content": {}, "isError": False}

    layer = ToolMCPCompatLayer(dispatch_tool_fn=capturing_dispatch)
    await layer.call(
        {"name": "verify_code", "arguments": {"code": "I25.10"}},
        _ctx(), request=_FakeRequest(),
        round_index=2, caller="llm",
    )
    assert captured["round_index"] == 2
    assert captured["caller"] == "llm"


# ── to_tool_call_record ───────────────────────────────────────────


def test_to_tool_call_record_projects_to_ToolCallRecord():
    layer = ToolMCPCompatLayer()
    resp = ToolCallResponse(
        tool_name="verify_code", content={"ok": True},
        duration_ms=15, scope_granted=["coding:validate"],
    )
    rec = layer.to_tool_call_record(resp, arguments={"code": "I50.900"})
    assert isinstance(rec, ToolCallRecord)
    assert rec.tool_name == "verify_code"
    assert rec.arguments == {"code": "I50.900"}
    assert rec.result == {"ok": True}
    assert rec.duration_ms == 15
    assert rec.error is None
    assert "coding:validate" in rec.scope_granted


def test_to_tool_call_record_with_error():
    layer = ToolMCPCompatLayer()
    resp = ToolCallResponse(
        tool_name="search", is_error=True, error_message="forbidden",
    )
    rec = layer.to_tool_call_record(resp, arguments={})
    assert rec.error == "forbidden"
    assert rec.result is None
