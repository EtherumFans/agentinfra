"""Tests for ``icoder_runtime.backends.llm_with_tools_provider``.

Covers:
  - Missing LLM wiring fails closed without guessing a tool call.
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
from icoder_runtime.backends.llm_with_tools_provider import (
    LLMWithToolsProvider,
    _resolve_conditional_mandatory_tools,
    _resolve_preflight_conditional_tools,
)
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


def _diagnosis_ctx() -> AgentRunContext:
    return AgentRunContext(
        run_id="run-dx-1",
        context_id="ctx-dx-1",
        agent_id="diagnosis-extractor",
        redacted_input="test",
        agent_pack={
            "output_contract": {
                "schema_ref": "icoder/DiagnosisExtractionOutput/v1",
                "required_fields": ["diagnoses", "non_codable_mentions"],
            }
        },
    )


def test_conditional_tools_required_when_diagnoses_are_emitted():
    policies = [{
        "output_path": "diagnoses",
        "when": "nonempty",
        "tools": ["search_icd", "verify_code"],
    }]
    text = '```json\n{"diagnoses":[{"text":"肺炎"}],"non_codable_mentions":[]}\n```'
    assert _resolve_conditional_mandatory_tools(text, policies, _diagnosis_ctx()) == {
        "search_icd", "verify_code",
    }


def test_conditional_tools_skipped_for_negated_only_output():
    policies = [{
        "output_path": "diagnoses",
        "when": "nonempty",
        "tools": ["search_icd", "verify_code"],
    }]
    text = '```json\n{"diagnoses":[],"non_codable_mentions":[{"text":"已排除肺炎"}]}\n```'
    assert _resolve_conditional_mandatory_tools(text, policies, _diagnosis_ctx()) == set()


def test_conditional_tools_fail_closed_when_output_is_unparseable():
    policies = [{
        "output_path": "diagnoses",
        "when": "nonempty",
        "tools": ["search_icd", "verify_code"],
    }]
    assert _resolve_conditional_mandatory_tools(
        "not-json", policies, _diagnosis_ctx()
    ) == {"search_icd", "verify_code"}


def test_preflight_eligibility_uses_separate_boolean_contract():
    policies = [{
        "output_path": "diagnoses",
        "when": "nonempty",
        "tools": ["search_icd", "verify_code"],
    }]
    assert _resolve_preflight_conditional_tools(
        '{"tool_eligibility":{"diagnoses":false}}', policies
    ) == set()
    assert _resolve_preflight_conditional_tools(
        '{"tool_eligibility":{"diagnoses":true}}', policies
    ) == {"search_icd", "verify_code"}


def test_preflight_missing_or_non_boolean_decision_exposes_tools():
    policies = [{
        "output_path": "diagnoses",
        "when": "nonempty",
        "tools": ["search_icd", "verify_code"],
    }]
    expected = {"search_icd", "verify_code"}
    assert _resolve_preflight_conditional_tools(
        '{"diagnoses":[],"issues_found":["tools unavailable"]}', policies
    ) == expected
    assert _resolve_preflight_conditional_tools(
        '{"tool_eligibility":{"diagnoses":"false"}}', policies
    ) == expected


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


@pytest.mark.asyncio
async def test_health_degraded_when_gateway_adapter_selects_mock_provider():
    from icoder_runtime.backends.llm_gateway_adapter import LLMGatewayAdapter
    from icoder_runtime.core.llm_gateway import LLMGateway, MockLLMProvider

    gateway = LLMGateway()
    gateway.register(MockLLMProvider(), default=True)
    provider = LLMWithToolsProvider(llm_client=LLMGatewayAdapter(gateway))

    health = await provider.health()

    assert health.state == "degraded"
    assert health.details["reason"] == "mock_provider"
    assert health.details["live_health_verified"] is False


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


# ── invoke without LLM client (fail-closed) ─────────────────────


@pytest.mark.asyncio
async def test_invoke_without_llm_fails_closed_and_does_not_call_tool():
    """Missing LLM wiring cannot guess a tool or report success."""
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
    assert resp.status == "fail"
    assert resp.finish_state == "failed"
    assert resp.markdown == ""
    assert resp.tool_calls == []
    assert "llm_unavailable" in resp.finish_reason
    assert captured == []


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
async def test_stream_without_llm_has_no_tool_or_output_events():
    """Fail-closed streaming emits no fabricated tools or output."""
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
    assert "tool_calls" not in steps
    assert "output_chunk" not in steps
    assert steps[-1] == "finished"
    assert events[0]["payload"].finish_state == "failed"
