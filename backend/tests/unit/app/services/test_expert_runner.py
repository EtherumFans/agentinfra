"""Fail-closed and PHI-boundary tests for the legacy ExpertRunner."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import expert_runner as module
from app.services.expert_runner import (
    ExpertExecutionError,
    ExpertRunner,
    MCPToolExecutionError,
    UnsupportedMCPServiceError,
)


def _expert():
    return SimpleNamespace(
        id="expert-test",
        name="Test Expert",
        description="Test only",
        system_prompt="Return a safe test response.",
    )


def _server(name: str, url: str = ""):
    return SimpleNamespace(name=name, url=url, description="Test server")


@pytest.mark.asyncio
async def test_run_redacts_input_and_history_before_llm(monkeypatch):
    captured = {}

    async def _chat(*, messages, temperature):
        captured["messages"] = messages
        return {"content": "safe response"}

    monkeypatch.setattr(module.llm_service, "chat", _chat)
    output = await ExpertRunner().run(
        _expert(),
        "联系电话 13800138000",
        conversation_history=[{"role": "user", "content": "备用 13900139000"}],
    )

    assert output == "safe response"
    rendered = repr(captured)
    assert "13800138000" not in rendered
    assert "13900139000" not in rendered
    assert rendered.count("<REDACTED:PHONE>") == 2


@pytest.mark.asyncio
async def test_run_raises_safe_error_instead_of_error_string(monkeypatch):
    async def _chat(**_kwargs):
        raise RuntimeError("connector leaked 13800138000")

    monkeypatch.setattr(module.llm_service, "chat", _chat)
    with pytest.raises(ExpertExecutionError) as excinfo:
        await ExpertRunner().run(_expert(), "safe clinical input")

    assert str(excinfo.value) == "Expert execution failed"
    assert "13800138000" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_unknown_mcp_server_never_returns_mock_success():
    with pytest.raises(UnsupportedMCPServiceError):
        await ExpertRunner()._real_mcp_call(
            _server("Hospital Internal Mystery Service", "https://example.invalid"),
            "query",
        )


@pytest.mark.asyncio
async def test_mcp_connector_error_dict_fails_closed(monkeypatch):
    async def _call(*_args, **_kwargs):
        return {"error": "remote response included 13800138000"}

    monkeypatch.setattr(module.mcp_client, "call", _call)
    with pytest.raises(MCPToolExecutionError) as excinfo:
        await ExpertRunner()._real_mcp_call(_server("PubMed"), "query")

    assert str(excinfo.value) == "MCP connector call failed"
    assert "13800138000" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_unconfigured_llm_tool_call_fails_closed():
    tool_calls = [{
        "id": "call-1",
        "function": {"name": "unknown_tool", "arguments": '{"query":"safe"}'},
    }]
    with pytest.raises(UnsupportedMCPServiceError):
        await ExpertRunner()._handle_tool_calls(tool_calls, [], [])

