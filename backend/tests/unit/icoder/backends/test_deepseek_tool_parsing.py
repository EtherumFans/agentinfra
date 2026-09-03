"""Tests for ``DeepSeekProvider.generate()`` tool_calls parsing — Phase 4-C.

Phase 4-C adds tool-calling support to the LLMGateway chain.
``DeepSeekProvider.generate()`` already sends ``tools`` in the API
payload, but until Phase 4-C the response parser only read
``choice["message"]["content"]`` and silently dropped
``choice["message"]["tool_calls"]``. These tests verify the fix.

We mock ``httpx.AsyncClient`` via ``unittest.mock.patch`` so no real
network call is made. The mock returns a canned
``choices[0].message`` dict — we verify the gateway result surfaces
``tool_calls`` correctly.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest


# ── Stub httpx response / client ──────────────────────────────────


class _StubResponse:
    """Stand-in for ``httpx.Response`` returned by ``AsyncClient.post``."""

    def __init__(self, message: dict, model: str = "deepseek-chat",
                 usage: dict | None = None) -> None:
        self._body = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": model,
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
            }],
            "usage": usage or {"prompt_tokens": 50, "completion_tokens": 30},
        }
        self.status_code = 200
        self.text = json.dumps(self._body)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class _StubAsyncClient:
    """Context-manager async client that captures the request and returns a canned response.

    Replaces ``httpx.AsyncClient`` inside ``DeepSeekProvider.generate()``.
    The stub records every ``post()`` call into ``captured`` so tests can
    assert on the payload.
    """

    def __init__(self, message: dict, captured: dict[str, Any], **kwargs) -> None:
        self._message = message
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url: str, json=None, headers=None) -> _StubResponse:
        self._captured["url"] = url
        self._captured["json"] = json
        self._captured["headers"] = headers
        return _StubResponse(self._message)


def _make_provider(message: dict) -> tuple[Any, dict[str, Any]]:
    """Construct a DeepSeekProvider with stubbed httpx.

    Returns the provider and a ``captured`` dict that the stub writes
    the outgoing request payload into.

    ``DeepSeekProvider.generate()`` does ``import httpx`` inside the
    function body and then uses ``httpx.AsyncClient(...)``. Patching
    the global ``httpx.AsyncClient`` attribute via ``patch('httpx.AsyncClient', ...)``
    intercepts the lookup regardless of where the import happened.
    """
    from icoder_runtime.core.llm_gateway import DeepSeekProvider

    provider = DeepSeekProvider(
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
    )
    captured: dict[str, Any] = {}

    def _client_factory(**kwargs):
        return _StubAsyncClient(message, captured, **kwargs)

    patcher = patch("httpx.AsyncClient", side_effect=_client_factory)
    patcher.start()
    provider._patcher = patcher  # type: ignore[attr-defined]
    return provider, captured


@pytest.fixture
def cleanup_patcher():
    """Stop any patcher attached to providers created during the test."""
    yield
    # Cleanup happens per-test via the _make_provider patcher; this
    # fixture exists to make addfinalizer-style cleanup explicit.


# ── Tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deepseek_parses_tool_calls_from_response(cleanup_patcher):
    """DeepSeek response with ``message.tool_calls`` is surfaced on the result dict."""
    fake_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "verify_code",
                "arguments": json.dumps({"code": "I25.10"}, ensure_ascii=False),
            },
        }],
    }
    provider, _ = _make_provider(fake_message)
    try:
        result = await provider.generate(
            messages=[{"role": "user", "content": "validate I25.10"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "verify_code",
                    "parameters": {"type": "object", "properties": {"code": {"type": "string"}}},
                },
            }],
        )
    finally:
        provider._patcher.stop()  # type: ignore[attr-defined]

    assert isinstance(result, dict)
    assert result["content"] is None or result["content"] == ""
    assert "tool_calls" in result
    assert result["tool_calls"] == fake_message["tool_calls"]


@pytest.mark.asyncio
async def test_deepseek_no_tool_calls_returns_no_tool_calls_key(cleanup_patcher):
    """When LLM finishes normally (no tool_calls), the result dict omits the key."""
    fake_message = {
        "role": "assistant",
        "content": "All codes passed validation.",
    }
    provider, _ = _make_provider(fake_message)
    try:
        result = await provider.generate(
            messages=[{"role": "user", "content": "validate"}],
        )
    finally:
        provider._patcher.stop()  # type: ignore[attr-defined]

    assert result["content"] == "All codes passed validation."
    assert "tool_calls" not in result


@pytest.mark.asyncio
async def test_deepseek_payload_includes_tools_when_provided(cleanup_patcher):
    """DeepSeekProvider sends ``tools`` in the API payload when given."""
    fake_message = {"role": "assistant", "content": "ok"}
    provider, captured = _make_provider(fake_message)
    try:
        tool_schemas = [{
            "type": "function",
            "function": {"name": "verify_code", "parameters": {}},
        }]
        await provider.generate(
            messages=[{"role": "user", "content": "hi"}],
            tools=tool_schemas,
        )
    finally:
        provider._patcher.stop()  # type: ignore[attr-defined]

    assert captured["json"]["tools"] == tool_schemas


@pytest.mark.asyncio
async def test_deepseek_payload_omits_tools_when_none(cleanup_patcher):
    """When ``tools=None``, the payload does not include the ``tools`` key."""
    fake_message = {"role": "assistant", "content": "ok"}
    provider, captured = _make_provider(fake_message)
    try:
        await provider.generate(
            messages=[{"role": "user", "content": "hi"}],
        )
    finally:
        provider._patcher.stop()  # type: ignore[attr-defined]

    assert "tools" not in captured["json"]
