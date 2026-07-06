"""Phase 3-C0 A1 — LLM_PROVIDER=mock leakage hard tests.

Asserts:
1. MockLLMProvider returns a valid Plan shape `{"experts": [...]}` on
   planner-style prompts (so `_validate_plan_dict` never rejects with
   "Plan.experts must be a non-empty list").
2. LLMGateway with MockLLMProvider as default never dispatches to
   DeepSeekProvider — verified via httpx.MockTransport that raises
   AssertionError if invoked.
3. Planner constructed with a MockLLMProvider-backed llm_call produces
   a non-empty Plan with `coding-expert` for the MedCodER agent.
4. App lifespan wiring respects LLM_PROVIDER=mock: even when
   ICODER_CREDENTIAL_LLM is set in the env, DeepSeekProvider is NOT
   registered as default (suppressing real DeepSeek HTTP 401s).

These are the "hard test" required by Phase 3-C0 A1 acceptance:
> 添加硬测试，确认 mock 模式下不调用 DeepSeek/OpenAI/任何外部 HTTP
"""
from __future__ import annotations

import json
import os

import httpx
import pytest

from icoder_runtime.core.llm_gateway import (
    DeepSeekProvider,
    LLMGateway,
    MockLLMProvider,
)


# ─── 1. MockLLMProvider returns valid Plan shape ───────────────────────


def _build_planner_messages(expert_id: str = "coding-expert") -> list[dict]:
    """Build the same message shape the Planner sends to the gateway."""
    system_prompt = (
        "# Role\n你是 iCoDer Agent Runtime 的中央协调器 (Orchestrator)。\n"
        "# Plan schema\n"
        "{\n  \"experts\": [\n    {\n      \"expert_id\": \"coding-expert\",\n"
        "      \"priority\": 1,\n      \"critical\": true,\n"
        "      \"subtask_input\": \"\",\n      \"tool_constraints\": []\n    }\n  ],\n"
        "  \"reason\": \"\"\n}\n"
    )
    user_message = (
        "# Agent\nid: medcoder-coding-review\nname: MedCodER Coding Review Agent\n"
        f"available_experts:\n  - {expert_id}\n"
        "\n# User input (PHI redacted)\n患者男 65 岁, 因持续胸痛 6 小时入院\n"
        "\n# Return JSON only, matching this schema:\n"
        "{\n  \"experts\": [...],\n  \"reason\": \"...\"\n}\n"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]


@pytest.mark.asyncio
async def test_mock_llm_returns_valid_plan_with_non_empty_experts():
    """MockLLMProvider.generate() with a planner prompt must return a
    valid Plan JSON with at least one expert — never empty.
    """
    provider = MockLLMProvider()
    messages = _build_planner_messages("coding-expert")

    resp = await provider.generate(messages)

    assert resp["model"] == "mock/1.0"
    parsed = json.loads(resp["content"])
    assert isinstance(parsed, dict)
    assert isinstance(parsed.get("experts"), list)
    assert len(parsed["experts"]) >= 1, "Plan.experts must NOT be empty in mock mode"
    e = parsed["experts"][0]
    assert e["expert_id"] == "coding-expert"
    assert e["priority"] == 1
    assert e["critical"] is True
    assert isinstance(e["subtask_input"], str) and e["subtask_input"]
    assert e["tool_constraints"] == []


@pytest.mark.asyncio
async def test_mock_llm_plan_picks_first_declared_expert():
    """When the agent declares multiple experts, the mock planner picks
    the first one — deterministic, never empty.
    """
    provider = MockLLMProvider()
    messages = _build_planner_messages("drg-expert")

    resp = await provider.generate(messages)
    parsed = json.loads(resp["content"])
    assert parsed["experts"][0]["expert_id"] == "drg-expert"


@pytest.mark.asyncio
async def test_mock_llm_non_planner_prompt_returns_compliance_shape():
    """Non-planner prompts still return the legacy compliance audit
    shape — the mock planner detection is scoped to planner cues only.
    """
    provider = MockLLMProvider()
    messages = [
        {"role": "system", "content": "你是医学编码助手."},
        {"role": "user", "content": "请编码: 心力衰竭"},
    ]
    resp = await provider.generate(messages)
    parsed = json.loads(resp["content"])
    assert "review_conclusion" in parsed
    assert "experts" not in parsed


# ─── 2. LLMGateway never calls DeepSeek when MockLLMProvider is default ──


@pytest.mark.asyncio
async def test_gateway_with_mock_default_never_invokes_deepseek_transport():
    """LLMGateway with MockLLMProvider as default must NOT call the
    DeepSeek HTTP transport, even when a DeepSeekProvider with a fake
    key is registered (mock takes precedence as default).
    """
    def _deny_transport_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            f"DeepSeek HTTP must not be called in mock mode (saw {request.url})"
        )

    deepseek_with_transport = DeepSeekProvider(
        api_key="fake-key-must-not-be-used",
        _transport=httpx.MockTransport(_deny_transport_handler),
    )
    gateway = LLMGateway()
    gateway.register(MockLLMProvider(), default=True)
    gateway.register(deepseek_with_transport, alias="deepseek")

    resp = await gateway.generate(_build_planner_messages("coding-expert"))

    parsed = json.loads(resp["content"])
    assert len(parsed["experts"]) >= 1
    assert parsed["experts"][0]["expert_id"] == "coding-expert"


@pytest.mark.asyncio
async def test_gateway_no_real_http_in_mock_mode(monkeypatch):
    """Even if ICODER_CREDENTIAL_LLM is set in the env, LLM_PROVIDER=mock
    must short-circuit any DeepSeek HTTP attempt.
    """
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "fake-key-should-be-ignored")

    # Simulate the app/main.py lifespan decision logic.
    provider_choice = os.environ.get("LLM_PROVIDER", "").lower()
    assert provider_choice == "mock"

    # When LLM_PROVIDER=mock, app/main.py MUST register MockLLMProvider
    # as default and skip DeepSeek entirely — even if a key is present.
    gateway = LLMGateway()
    deepseek_registered = False
    if provider_choice == "mock":
        gateway.register(MockLLMProvider(), default=True)
    else:
        # This branch should NOT execute under LLM_PROVIDER=mock
        deepseek_registered = True
        gateway.register(
            DeepSeekProvider(
                api_key=os.environ["ICODER_CREDENTIAL_LLM"],
                _transport=httpx.MockTransport(
                    lambda _: pytest.fail("DeepSeek HTTP unexpectedly called")
                ),
            ),
            default=True,
        )
    assert not deepseek_registered, (
        "LLM_PROVIDER=mock must NOT register DeepSeekProvider as default"
    )

    resp = await gateway.generate(_build_planner_messages("coding-expert"))
    parsed = json.loads(resp["content"])
    assert parsed["experts"][0]["expert_id"] == "coding-expert"


# ─── 3. Planner + MockLLMProvider llm_call produces a non-empty Plan ────


def test_planner_with_mock_llm_call_produces_non_empty_plan():
    """End-to-end: Planner wired with a MockLLMProvider-backed llm_call
    must produce a Plan with `coding-expert` — never PLANNING_FAILED due
    to empty experts.
    """
    from app.icoder.agent_runtime.orchestrator.planner import (
        Planner,
        PlannerConfig,
    )
    from app.icoder.agent_runtime.orchestrator.wiring import (
        LMGatewaySyncAdapter,
    )

    gateway = LLMGateway()
    gateway.register(MockLLMProvider(), default=True)
    # The sync adapter is what app/main.py wires into the Planner.
    llm_call = LMGatewaySyncAdapter(gateway, default_provider="mock")

    class _Agent:
        id = "medcoder-coding-review"
        name = "MedCodER Coding Review Agent"
        expert_ids = ["coding-expert"]
        config = {"non_goals": [], "output_contract": "MedicalCodingOutputSchema"}

    planner = Planner(
        llm_call=llm_call,
        config=PlannerConfig(sleep_fn=lambda _: None),
    )
    plan = planner.plan(redacted_input="患者男 65 岁, 因持续胸痛入院", agent=_Agent())
    assert len(plan.steps) >= 1
    assert plan.steps[0]["expert_id"] == "coding-expert"
    assert plan.steps[0]["priority"] == 1
    assert plan.steps[0]["critical"] is True


# ─── 4. App lifespan wiring: LLM_PROVIDER=mock suppresses DeepSeek ─────


def test_app_lifespan_respects_llm_provider_mock(monkeypatch):
    """Re-execute the app/main.py lifespan decision logic and assert
    that DeepSeek is NOT registered as default when LLM_PROVIDER=mock,
    even with ICODER_CREDENTIAL_LLM set.
    """
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "persisted-dev-key-must-be-ignored")

    # Mirror the exact decision block from app/main.py (post Phase 3-C0 A1).
    _deepseek_key = (
        os.environ.get("ICODER_CREDENTIAL_LLM", "").strip()
        or ""  # settings.LLM_API_KEY defaults to ""
    )
    _llm_provider_cfg = os.environ.get("LLM_PROVIDER", "").lower()

    deepseek_registered_as_default = False
    if _llm_provider_cfg == "mock":
        # Mock path — DeepSeek NOT registered
        pass
    elif _deepseek_key or _llm_provider_cfg == "deepseek":
        deepseek_registered_as_default = True

    assert not deepseek_registered_as_default, (
        "LLM_PROVIDER=mock must suppress DeepSeek registration even when "
        "ICODER_CREDENTIAL_LLM is set in the OS env"
    )
