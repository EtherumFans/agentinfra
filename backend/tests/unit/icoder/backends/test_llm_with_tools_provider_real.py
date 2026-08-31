"""Tests for ``LLMWithToolsProvider._real_llm_pipeline()`` — Phase 4-C.

Phase 4-C adds the real LLM tool-calling loop. These tests verify the
loop behavior with a mock LLM client that can be configured to:

  - return ``tool_calls`` for N rounds, then return a final text answer
  - always return ``tool_calls`` (to exercise the ``max_tool_rounds`` cap)
  - raise an exception (to exercise the ``_fail`` fallback path)

The LLM client mock exposes ``complete_messages()`` (the multi-round
entry point that ``LLMGatewayAdapter`` ships in production). Tool
dispatch is stubbed via ``mcp_layer._dispatch_tool_fn`` — the test
asserts the loop routes each tool call through it (Task 7 requirement
#2: "never bypass dispatch_tool").

We also verify:
  - ``backend_metadata`` RunTrace event is emitted with ``tool_rounds``
    populated (Phase 4-C metadata contract).
  - Final text is parsed to a ``ProviderStatus`` via
    ``_parse_status_from_markdown`` (heuristic status scan).
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from icoder_runtime.backends import (
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    ToolCallRecord,
)
from icoder_runtime.backends.llm_with_tools_provider import LLMWithToolsProvider
from icoder_runtime.backends.pure_llm_provider import LLMChunk, LLMResponse


# ── Fixtures ─────────────────────────────────────────────────────────


def _ctx(agent_id: str = "code-validation-agent") -> AgentRunContext:
    return AgentRunContext(
        run_id="run-real-1",
        context_id="ctx-real-1",
        agent_id=agent_id,
        redacted_input="patient with STEMI",
        agent_pack={"agent": {"system_prompt": "You are Code Validation."}},
    )


class _FakeRequest:
    """Stand-in for FastAPI Request — ``dispatch_tool`` reads
    ``request.app.state`` and ``request.state`` for context."""

    class _State:
        def __init__(self):
            self.context_id = "ctx-real-1"
            self.run_id = "run-real-1"
            self.mcp_run_auth_context = None

    class _App:
        def __init__(self):
            self.state = type("state", (), {})()

    def __init__(self):
        self.app = self._App()
        self.state = self._State()


def _make_openai_tool_call(name: str, args: dict[str, Any], call_id: str = "") -> dict:
    """Build a provider-native (OpenAI shape) tool_call dict."""
    return {
        "id": call_id or f"call_{name}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }


class _ScriptedLLMClient:
    """Mock LLM client that returns a scripted sequence of LLMResponses.

    Each item in ``script`` is either:
      - ``LLMResponse`` — returned as-is for that call.
      - ``Exception`` — raised when ``complete_messages`` is called
        (used to exercise the fallback path).

    Once the script is exhausted, raises ``AssertionError`` — tests
    should consume exactly the scripted rounds.
    """

    def __init__(self, script: list[Any]):
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def complete_messages(
        self, *, messages, tools=None, temperature=0.0,
        max_tokens=None, timeout_seconds=60.0,
    ) -> LLMResponse:
        self.calls.append({
            "messages": list(messages),
            "tools": tools,
            "temperature": temperature,
        })
        if not self._script:
            raise AssertionError(
                "_ScriptedLLMClient: script exhausted — "
                f"unexpected call #{len(self.calls)}"
            )
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        if not isinstance(item, LLMResponse):
            raise TypeError(
                f"_ScriptedLLMClient: script item must be LLMResponse or Exception, "
                f"got {type(item).__name__}"
            )
        return item


class _StreamingScriptedLLMClient:
    def __init__(self, rounds: list[list[LLMChunk]]) -> None:
        self.rounds = list(rounds)

    async def stream_messages(self, **kwargs):
        if not self.rounds:
            raise AssertionError("streaming script exhausted")
        for chunk in self.rounds.pop(0):
            yield chunk

    async def complete_messages(self, **kwargs):
        raise AssertionError("native stream path must not call complete_messages")


def _make_provider(
    *,
    llm_script: list[Any],
    tool_scope: list[str] | None = None,
    max_tool_rounds: int = 8,
) -> tuple[LLMWithToolsProvider, _ScriptedLLMClient, list[tuple[str, dict]], list[dict]]:
    """Construct an LLMWithToolsProvider with a scripted LLM + stub dispatch.

    Returns ``(provider, llm_client, dispatch_calls, dispatch_kwargs)``
    where ``dispatch_calls`` is a list of ``(tool_name, arguments)``
    tuples and ``dispatch_kwargs`` is a list of the extra kwargs
    (``run_id``, ``round_index``, ``caller``) the stub ``dispatch_tool``
    was called with — Phase 4-C uses these to assert round/caller
    propagation.
    """
    llm_client = _ScriptedLLMClient(llm_script)
    dispatch_calls: list[tuple[str, dict]] = []
    dispatch_kwargs: list[dict] = []

    async def fake_dispatch(tool_name, args, request, *, run_id=None, **kwargs):
        dispatch_calls.append((tool_name, dict(args or {})))
        dispatch_kwargs.append({"run_id": run_id, **kwargs})
        return {
            "content": {"ok": True, "tool_name": tool_name, "args": args},
            "isError": False,
            "tool_name": tool_name,
            "duration_ms": 3,
        }

    tool_list = [
        {"name": name, "description": f"{name} tool", "input_schema": {"type": "object"}}
        for name in (tool_scope or ["verify_code"])
    ]

    p = LLMWithToolsProvider(
        llm_client=llm_client,
        max_tool_rounds=max_tool_rounds,
    )
    p._mcp_layer._dispatch_tool_fn = fake_dispatch
    p._mcp_layer._list_tools_fn = lambda: tool_list
    return p, llm_client, dispatch_calls, dispatch_kwargs


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_real_pipeline_one_tool_round():
    """LLM requests one tool call, then on the next round returns final text."""
    tool_call = _make_openai_tool_call("verify_code", {"code": "I25.10"}, "call_1")
    llm_script = [
        LLMResponse(text="", tool_calls=[tool_call], cost_usd=0.01),
        LLMResponse(
            text="# Status: pass\n\nAll checks passed.",
            finish_reason="stop",
            cost_usd=0.02,
        ),
    ]
    p, llm_client, dispatch_calls, dispatch_kwargs = _make_provider(llm_script=llm_script)

    req = BackendRequest(
        system_prompt="You are Code Validation.",
        user_input="validate I25.10",
        tool_scope=["verify_code"],
    )
    resp = await p.invoke(req, _ctx(), request=_FakeRequest())

    assert resp.backend_provider == "icoder.llm-with-tools.v1"
    assert resp.backend_type == "llm_with_tools"
    assert resp.finish_state == "completed"
    # Final text had "# Status: pass" → status="pass"
    assert resp.status == "pass"
    assert "All checks passed" in resp.markdown
    # 1 tool call recorded
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].tool_name == "verify_code"
    assert resp.tool_calls[0].arguments == {"code": "I25.10"}
    # dispatch_tool was called exactly once
    assert len(dispatch_calls) == 1
    assert dispatch_calls[0] == ("verify_code", {"code": "I25.10"})
    # LLM was called exactly twice (round 1: tool_call, round 2: final text)
    assert len(llm_client.calls) == 2
    # raw_provider_response tracks tool_rounds
    assert resp.raw_provider_response.get("tool_rounds") == 1
    assert resp.raw_provider_response.get("tool_calls_count") == 1
    assert resp.raw_provider_response.get("llm_call_count") == 2
    assert resp.raw_provider_response.get("cost_usd_total") == 0.03
    assert resp.cost_usd == 0.03
    assert resp.raw_provider_response.get("incomplete") is False
    # Phase 4-C: dispatch_tool received round_index + caller="llm"
    assert len(dispatch_kwargs) == 1
    assert dispatch_kwargs[0].get("round_index") == 0
    assert dispatch_kwargs[0].get("caller") == "llm"


@pytest.mark.asyncio
async def test_native_stream_interleaves_tool_fragments_dispatch_and_final_text():
    tool_call = _make_openai_tool_call(
        "verify_code", {"code": "I25.10"}, "call_stream_1",
    )
    client = _StreamingScriptedLLMClient([
        [
            LLMChunk(
                event_type="tool_call_delta",
                tool_call_delta={
                    "index": 0,
                    "id": "call_stream_1",
                    "function": {
                        "name": "verify_code",
                        "arguments": '{"code":"I25.10"}',
                    },
                },
                native=True,
                provider="deepseek",
                raw={"index": 0},
            ),
            LLMChunk(
                event_type="completed",
                response=LLMResponse(
                    text="",
                    tool_calls=[tool_call],
                    finish_reason="tool_calls",
                    cost_usd=0.01,
                ),
                native=True,
                provider="deepseek",
            ),
        ],
        [
            LLMChunk(
                event_type="text_delta",
                delta="# Status: pass\n\n",
                native=True,
                provider="deepseek",
            ),
            LLMChunk(
                event_type="text_delta",
                delta="All checks passed.",
                native=True,
                provider="deepseek",
            ),
            LLMChunk(
                event_type="completed",
                response=LLMResponse(
                    text="# Status: pass\n\nAll checks passed.",
                    finish_reason="stop",
                    cost_usd=0.02,
                ),
                native=True,
                provider="deepseek",
            ),
        ],
    ])
    dispatches: list[str] = []

    async def fake_dispatch(tool_name, args, request, *, run_id=None, **kwargs):
        dispatches.append(tool_name)
        return {
            "content": {"valid": True},
            "isError": False,
            "tool_name": tool_name,
            "duration_ms": 2,
        }

    provider = LLMWithToolsProvider(llm_client=client)
    provider._mcp_layer._dispatch_tool_fn = fake_dispatch
    provider._mcp_layer._list_tools_fn = lambda: [{
        "name": "verify_code",
        "description": "Validate one code",
        "input_schema": {"type": "object"},
    }]
    request = BackendRequest(
        system_prompt="Validate codes.",
        user_input="validate I25.10",
        tool_scope=["verify_code"],
    )

    events = [
        event
        async for event in provider.stream(
            request, _ctx(), request=_FakeRequest(),
        )
    ]
    steps = [event["step"] for event in events]

    assert dispatches == ["verify_code"]
    assert steps.index("provider_tool_call_delta") < steps.index(
        "tool_call_completed"
    )
    assert steps.index("tool_call_completed") < steps.index(
        "provider_text_delta"
    )
    assert steps.index("provider_text_delta") < steps.index("backend_invoked")
    response = next(
        event["payload"]
        for event in events
        if event["step"] == "backend_invoked"
    )
    assert response.markdown.endswith("All checks passed.")
    assert response.cost_usd == 0.03


@pytest.mark.asyncio
async def test_conditional_preflight_withholds_tools_for_negated_only_output():
    preflight_text = '{"tool_eligibility":{"diagnoses":false}}'
    final_text = (
        '```json\n{"diagnoses":[],"non_codable_mentions":'
        '[{"text":"已排除肺炎"}],"issues_found":[],"status":"REQUIRES_REVIEW",'
        '"manual_review_required":true,"trace_refs":{}}\n```'
    )
    p, llm_client, dispatch_calls, _ = _make_provider(
        llm_script=[
            LLMResponse(
                text=preflight_text,
                finish_reason="stop",
                cost_usd=0.005,
            ),
            LLMResponse(
                text=final_text,
                finish_reason="stop",
                cost_usd=0.01,
            ),
        ],
        tool_scope=["search_icd", "verify_code"],
    )
    req = BackendRequest(
        system_prompt="Extract confirmed diagnoses only.",
        user_input="考虑肺炎，复查后已排除。",
        tool_scope=["search_icd", "verify_code"],
        conditional_mandatory_tools=[{
            "output_path": "diagnoses",
            "when": "nonempty",
            "tools": ["search_icd", "verify_code"],
        }],
    )
    ctx = AgentRunContext(
        run_id="run-negated",
        context_id="ctx-negated",
        agent_id="diagnosis-extractor",
        redacted_input=req.user_input,
        agent_pack={
            "output_contract": {
                "schema_ref": "icoder/DiagnosisExtractionOutput/v1",
                "required_fields": ["diagnoses", "non_codable_mentions"],
            }
        },
    )

    resp = await p.invoke(req, ctx, request=_FakeRequest())

    assert resp.finish_state == "completed"
    assert resp.tool_calls == []
    assert dispatch_calls == []
    assert len(llm_client.calls) == 2
    assert llm_client.calls[0]["tools"] == []
    assert llm_client.calls[1]["tools"] == []
    assert "tool_eligibility" in llm_client.calls[0]["messages"][-1]["content"]
    assert '"diagnoses":[]' in resp.markdown
    assert resp.cost_usd == 0.015
    assert resp.raw_provider_response["llm_call_count"] == 2


@pytest.mark.asyncio
async def test_real_pipeline_cannot_skip_mandatory_grounding_tools():
    """A fluent answer without mandatory tool evidence is incomplete."""
    p, _, dispatch_calls, _ = _make_provider(
        llm_script=[LLMResponse(text="# Status: pass\n\nLooks valid.")],
        tool_scope=["verify_code", "get_guidelines"],
    )
    req = BackendRequest(
        system_prompt="sys",
        user_input="Explain I50.9",
        tool_scope=["verify_code", "get_guidelines"],
        mandatory_tools=["verify_code", "get_guidelines"],
    )

    resp = await p.invoke(req, _ctx("rule-explainer"), request=_FakeRequest())

    assert resp.status == "incomplete"
    assert resp.finish_reason == "mandatory_tools_not_completed:get_guidelines,verify_code"
    assert resp.raw_provider_response["missing_mandatory_tools"] == [
        "get_guidelines", "verify_code",
    ]
    assert "Unverified model draft" in resp.markdown
    assert dispatch_calls == []


@pytest.mark.asyncio
async def test_real_pipeline_multi_round():
    """LLM requests 3 tool calls across 3 rounds, then returns final text."""
    script = [
        LLMResponse(text="", tool_calls=[_make_openai_tool_call(
            "verify_code", {"code": "I25.10"}, "c1")], cost_usd=0.01),
        LLMResponse(text="", tool_calls=[_make_openai_tool_call(
            "verify_code", {"code": "R07.9"}, "c2")], cost_usd=0.02),
        LLMResponse(text="", tool_calls=[_make_openai_tool_call(
            "verify_code", {"code": "I25.5"}, "c3")], cost_usd=0.03),
        LLMResponse(
            text="# Status: warning\n\nSome issues found.",
            finish_reason="stop",
            cost_usd=0.04,
        ),
    ]
    p, llm_client, dispatch_calls, dispatch_kwargs = _make_provider(llm_script=script)

    req = BackendRequest(
        system_prompt="sys", user_input="validate 3 codes",
        tool_scope=["verify_code"],
    )
    resp = await p.invoke(req, _ctx(), request=_FakeRequest())

    assert resp.status == "warning"
    assert len(resp.tool_calls) == 3
    assert [tc.tool_name for tc in resp.tool_calls] == ["verify_code"] * 3
    assert [tc.arguments.get("code") for tc in resp.tool_calls] == [
        "I25.10", "R07.9", "I25.5",
    ]
    assert len(dispatch_calls) == 3
    assert resp.raw_provider_response.get("tool_rounds") == 3
    assert resp.raw_provider_response.get("tool_calls_count") == 3
    assert resp.raw_provider_response.get("incomplete") is False
    assert resp.raw_provider_response.get("llm_call_count") == 4
    assert resp.raw_provider_response.get("cost_usd_total") == 0.1
    assert resp.cost_usd == 0.1
    # LLM called 4 times (3 tool rounds + 1 final)
    assert len(llm_client.calls) == 4
    # Phase 4-C: round_index increments 0→1→2 across 3 rounds
    assert [kw.get("round_index") for kw in dispatch_kwargs] == [0, 1, 2]
    assert all(kw.get("caller") == "llm" for kw in dispatch_kwargs)


@pytest.mark.asyncio
async def test_real_pipeline_max_rounds_exceeded():
    """LLM keeps requesting tool calls → ``max_tool_rounds`` cap → status='incomplete'."""
    # LLM ALWAYS returns a tool call, never a final text.
    infinite_tool_call = LLMResponse(text="", tool_calls=[_make_openai_tool_call(
        "verify_code", {"code": "I25.10"}, "c")])
    # Need at least max_tool_rounds+1 responses because the loop checks
    # tool_rounds < max_tool_rounds BEFORE incrementing.
    script = [infinite_tool_call] * 10
    p, _, dispatch_calls, _ = _make_provider(
        llm_script=script, max_tool_rounds=3,
    )

    req = BackendRequest(
        system_prompt="sys", user_input="loop test",
        tool_scope=["verify_code"],
    )
    resp = await p.invoke(req, _ctx(), request=_FakeRequest())

    assert resp.status == "incomplete"
    assert resp.finish_state == "completed"  # task completed, but content incomplete
    assert "max_tool_rounds_exceeded" in (resp.finish_reason or "")
    assert resp.raw_provider_response.get("incomplete") is True
    assert resp.raw_provider_response.get("max_tool_rounds") == 3
    # 3 tool-call rounds were dispatched
    assert resp.raw_provider_response.get("tool_rounds") == 3
    assert len(dispatch_calls) == 3
    # Markdown should mention incomplete
    assert "incomplete" in resp.markdown.lower() or "incomplete" in resp.summary.lower()


@pytest.mark.asyncio
async def test_real_pipeline_tool_budget_forces_tools_disabled_final_json():
    tool_call = LLMResponse(
        text="",
        tool_calls=[_make_openai_tool_call(
            "verify_code", {"code": "I25.10"}, "c"
        )],
        cost_usd=0.01,
    )
    final_json = LLMResponse(
        text='{"review_conclusion":"PASS","validated_codes":[],"cross_code_issues":[],"manual_review_required":false,"summary":"done","markdown":"done"}',
        finish_reason="stop",
        cost_usd=0.02,
    )
    p, llm_client, dispatch_calls, _ = _make_provider(
        llm_script=[tool_call, tool_call, final_json], max_tool_rounds=2,
    )

    req = BackendRequest(
        system_prompt="sys", user_input="validate",
        tool_scope=["verify_code"], mandatory_tools=["verify_code"],
    )
    resp = await p.invoke(req, _ctx(), request=_FakeRequest())

    assert resp.status != "incomplete"
    assert resp.finish_reason == "tool_budget_finalized"
    assert resp.raw_provider_response.get("incomplete") is False
    assert len(dispatch_calls) == 2
    assert llm_client.calls[-1]["tools"] == []
    assert resp.raw_provider_response["llm_call_count"] == 3
    assert resp.cost_usd == 0.04


@pytest.mark.asyncio
async def test_real_pipeline_llm_exception_fallback():
    """LLM raises → invoke catches → returns ``status='fail'`` envelope."""
    script = [RuntimeError("deepseek 503 service unavailable")]
    p, _, _, _ = _make_provider(llm_script=script)

    req = BackendRequest(
        system_prompt="sys", user_input="hello",
        tool_scope=["verify_code"],
    )
    resp = await p.invoke(req, _ctx(), request=_FakeRequest())

    assert resp.status == "fail"
    assert resp.finish_state == "failed"
    assert "RuntimeError" in (resp.finish_reason or "")
    assert "deepseek 503" not in (resp.finish_reason or "")
    assert "deepseek 503" not in repr(resp.raw_provider_response)
    assert resp.backend_provider == "icoder.llm-with-tools.v1"
    # No tool calls issued because LLM raised on first call
    assert resp.tool_calls == []


@pytest.mark.asyncio
async def test_real_pipeline_degraded_gateway_response_fails_closed():
    """A gateway mock fallback is an error, never a grounded answer."""
    p, _, dispatch_calls, _ = _make_provider(
        llm_script=[LLMResponse(
            text="# Status: pass\n\nSynthetic fallback.",
            finish_reason="degraded:no_api_key",
            cost_usd=0.01,
        )],
    )
    resp = await p.invoke(
        BackendRequest(
            system_prompt="sys", user_input="explain I50.9",
            tool_scope=["verify_code"],
        ),
        _ctx("rule-explainer"),
        request=_FakeRequest(),
    )
    assert resp.status == "fail"
    assert resp.finish_state == "failed"
    assert resp.markdown == ""
    assert resp.finish_reason == "llm_degraded: degraded:no_api_key"
    assert resp.cost_usd == 0.01
    assert resp.raw_provider_response["llm_call_count"] == 1
    assert resp.raw_provider_response["cost_usd_total"] == 0.01
    assert dispatch_calls == []


@pytest.mark.asyncio
async def test_real_pipeline_emits_backend_metadata_with_tool_rounds(monkeypatch):
    """``_emit_backend_metadata`` fires with ``tool_rounds`` populated."""
    emitted: list[dict[str, Any]] = []

    def fake_emit(
        run_id, *, backend_provider, backend_type, provider_latency_ms,
        provider_status, provider_deterministic, supports_tool_calling,
        fallback_used, output_contract, tool_rounds,
        model_deployment_id="", model_routing_mode="",
        model_selection_version=0, model_routing_decision="", store=None,
        **model_telemetry,
    ):
        emitted.append({
            "run_id": run_id,
            "backend_provider": backend_provider,
            "backend_type": backend_type,
            "provider_latency_ms": provider_latency_ms,
            "provider_status": provider_status,
            "tool_rounds": tool_rounds,
            "fallback_used": fallback_used,
            "output_contract": output_contract,
            "model_deployment_id": model_deployment_id,
            "model_routing_mode": model_routing_mode,
            "model_selection_version": model_selection_version,
            "model_routing_decision": model_routing_decision,
            **model_telemetry,
        })

    # Patch the import inside _emit_backend_metadata.
    import sys
    from app.icoder.agent_runtime.orchestrator import run_trace as rt_module
    monkeypatch.setattr(rt_module, "emit_backend_metadata_event", fake_emit)

    tool_call = _make_openai_tool_call("verify_code", {"code": "I25.10"}, "c1")
    script = [
        LLMResponse(
            text="", tool_calls=[tool_call],
            raw={
                "provider": "qwen",
                "model": "qwen-plus",
                "usage": {"input_tokens": 10, "output_tokens": 2},
            },
        ),
        LLMResponse(
            text="# Status: pass\n\nDone.",
            finish_reason="stop",
            raw={
                "provider": "qwen",
                "model": "qwen-plus",
                "usage": {"input_tokens": 20, "output_tokens": 8},
                "model_routing": {
                    "mode": "pinned",
                    "deployment_id": "hospital-qwen-a",
                    "selection_version": 7,
                    "decision": "tenant_pinned",
                }
            },
        ),
    ]
    p, _, _, _ = _make_provider(llm_script=script)

    req = BackendRequest(
        system_prompt="sys", user_input="hello",
        tool_scope=["verify_code"],
    )
    await p.invoke(req, _ctx(), request=_FakeRequest())

    assert len(emitted) == 1
    meta = emitted[0]
    assert meta["backend_provider"] == "icoder.llm-with-tools.v1"
    assert meta["backend_type"] == "llm_with_tools"
    assert meta["tool_rounds"] == 1
    assert meta["fallback_used"] is False
    assert meta["output_contract"] == "icoder/LLMWithToolsOutput/v1"
    assert meta["provider_status"] == "pass"
    assert meta["model_deployment_id"] == "hospital-qwen-a"
    assert meta["model_routing_mode"] == "pinned"
    assert meta["model_selection_version"] == 7
    assert meta["model_routing_decision"] == "tenant_pinned"
    assert meta["model_provider"] == "qwen"
    assert meta["model_name"] == "qwen-plus"
    assert meta["input_tokens"] == 30
    assert meta["output_tokens"] == 10
    assert meta["total_tokens"] == 40
    assert meta["finish_reason"] == "stop"
    assert meta["llm_call_count"] == 2


@pytest.mark.asyncio
async def test_real_pipeline_final_output_parsing():
    """LLM final text is parsed to ``ProviderStatus`` via heuristic scan.

    Verifies the provider correctly maps LLM-emitted status keywords to
    the 9-state ``ProviderStatus`` enum. Same logic as
    ``PureLLMProvider._parse_status_from_markdown``.
    """
    test_cases = [
        ("# Status: pass\n\nAll good.", "pass"),
        ("# Status: warning\n\nCheck this.", "warning"),
        ("# Status: fail\n\nBroken.", "fail"),
        ("# Status: incomplete\n\nNeed more data.", "incomplete"),
        ("# Status: requires_review\n\nSend to doctor.", "requires_review"),
        ("# Status: compliant\n\nOK.", "compliant"),
        ("# Status: non_compliant\n\nNot OK.", "non_compliant"),
        ("No explicit keyword here", "complete"),  # default
    ]
    for markdown, expected_status in test_cases:
        script = [LLMResponse(text=markdown, finish_reason="stop")]
        p, _, _, _ = _make_provider(llm_script=script)
        req = BackendRequest(
            system_prompt="sys", user_input="hello",
            tool_scope=["verify_code"],
        )
        resp = await p.invoke(req, _ctx(), request=_FakeRequest())
        assert resp.status == expected_status, (
            f"status for markdown {markdown!r} was {resp.status!r}, "
            f"expected {expected_status!r}"
        )
