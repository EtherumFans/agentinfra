"""T2 — Planner (SPEC §6.1, §7.2)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.icoder.agent_runtime.orchestrator.planner import (
    LLMResponse,
    Planner,
    PlannerConfig,
    PlannerError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeAgent:
    id: str = "medical-coding-agent"
    name: str = "Medical Coding Agent"
    expert_ids: list[str] = field(default_factory=lambda: ["coding-expert", "drg-expert"])
    config: dict = field(default_factory=dict)


def _good_plan_dict() -> dict:
    return {
        "experts": [
            {
                "expert_id": "coding-expert",
                "priority": 1,
                "critical": True,
                "subtask_input": "提取主诊断并编码",
                "tool_constraints": ["icd_search"],
            }
        ],
        "reason": "纯编码审核",
    }


def _good_two_expert_plan() -> dict:
    return {
        "experts": [
            {
                "expert_id": "coding-expert",
                "priority": 1,
                "critical": True,
                "subtask_input": "编码",
                "tool_constraints": [],
            },
            {
                "expert_id": "drg-expert",
                "priority": 2,
                "critical": False,
                "subtask_input": "分组",
                "tool_constraints": [],
            },
        ],
        "reason": "编码 + DRG 分组",
    }


class _ScriptedLLM:
    """Sequence-controlled LLM stub for tests."""

    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self._idx = 0
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        if self._idx >= len(self._responses):
            raise AssertionError(f"_ScriptedLLM exhausted at call {self._idx + 1}")
        r = self._responses[self._idx]
        self._idx += 1
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, dict) else {
            "content": json.dumps(_good_plan_dict()),
            "model": "fake",
            "latency_ms": 10,
        }


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_planner_requires_llm_call():
    with pytest.raises(ValueError, match="llm_call is required"):
        Planner(llm_call=None)  # type: ignore[arg-type]


def test_planner_uses_default_prompt():
    p = Planner(llm_call=lambda s, u: {"content": "{}"})
    from app.icoder.agent_runtime.orchestrator.prompts import (
        ORCHESTRATOR_SYSTEM_PROMPT,
    )

    assert p.system_prompt == ORCHESTRATOR_SYSTEM_PROMPT


def test_planner_accepts_custom_prompt():
    p = Planner(llm_call=lambda s, u: {"content": "{}"}, system_prompt="custom")
    assert p.system_prompt == "custom"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_plan_returns_valid_plan_on_first_try():
    llm = _ScriptedLLM({"content": json.dumps(_good_plan_dict()), "model": "x"})
    p = Planner(llm_call=llm)
    plan = p.plan(redacted_input="脱敏病历", agent=_FakeAgent())
    assert len(plan.steps) == 1
    assert plan.steps[0]["expert_id"] == "coding-expert"
    assert plan.steps[0]["priority"] == 1
    assert plan.reason == "纯编码审核"
    assert plan.raw_llm_output == _good_plan_dict()
    # system prompt + user message both sent
    assert len(llm.calls) == 1
    sent_system, sent_user = llm.calls[0]
    assert "production_writeback_blocked" in sent_system
    assert "脱敏病历" in sent_user


def test_plan_strips_markdown_fences():
    bad_fence = "```json\n" + json.dumps(_good_plan_dict()) + "\n```"
    llm = _ScriptedLLM({"content": bad_fence, "model": "x"})
    p = Planner(llm_call=llm)
    plan = p.plan(redacted_input="x", agent=_FakeAgent())
    assert len(plan.steps) == 1


def test_plan_with_user_message_direct():
    llm = _ScriptedLLM({"content": json.dumps(_good_plan_dict())})
    p = Planner(llm_call=llm)
    plan = p.plan_with_user_message(
        redacted_input="x",
        agent_id="a",
        agent_name="A",
        available_experts=["coding-expert"],
    )
    assert len(plan.steps) == 1


def test_plan_preserves_two_expert_ordering_by_priority():
    llm = _ScriptedLLM({"content": json.dumps(_good_two_expert_plan())})
    p = Planner(llm_call=llm)
    plan = p.plan(redacted_input="x", agent=_FakeAgent())
    assert len(plan.steps) == 2
    # sorted by priority asc
    assert plan.steps[0]["expert_id"] == "coding-expert"
    assert plan.steps[1]["expert_id"] == "drg-expert"


# ---------------------------------------------------------------------------
# Parse failure → retry (Q-S1: 1 retry on parse)
# ---------------------------------------------------------------------------


def test_parse_failure_retries_with_hint():
    bad = "not json"
    good = {"content": json.dumps(_good_plan_dict())}
    llm = _ScriptedLLM({"content": bad}, good)
    p = Planner(llm_call=llm)
    plan = p.plan(redacted_input="x", agent=_FakeAgent())
    assert len(plan.steps) == 1
    # second call should have a parse hint appended
    assert len(llm.calls) == 2
    assert "REMINDER" in llm.calls[1][1] or "JSON" in llm.calls[1][1]


def test_parse_failure_after_retry_exhausted_bubbles():
    llm = _ScriptedLLM({"content": "not json"}, {"content": "still bad"})
    p = Planner(llm_call=llm, config=PlannerConfig(parse_retry_count=1, max_retries=1))
    with pytest.raises(PlannerError, match="parse"):
        p.plan(redacted_input="x", agent=_FakeAgent())


# ---------------------------------------------------------------------------
# LLM network/exception → retry
# ---------------------------------------------------------------------------


def test_llm_exception_retries_with_backoff():
    sleeps: list[float] = []
    llm = _ScriptedLLM(
        RuntimeError("network blip"),
        RuntimeError("again"),
        {"content": json.dumps(_good_plan_dict())},
    )
    p = Planner(
        llm_call=llm,
        config=PlannerConfig(
            max_retries=3, base_backoff_seconds=0.5, sleep_fn=sleeps.append
        ),
    )
    plan = p.plan(redacted_input="x", agent=_FakeAgent())
    assert plan.steps[0]["expert_id"] == "coding-expert"
    # 2 sleeps between 3 attempts (exp: 0.5, 1.0)
    assert sleeps == [0.5, 1.0]


def test_llm_exception_exhausts_retries():
    llm = _ScriptedLLM(RuntimeError("net"))
    p = Planner(llm_call=llm, config=PlannerConfig(max_retries=2, sleep_fn=lambda s: None))
    with pytest.raises(PlannerError, match="LLM call raised"):
        p.plan(redacted_input="x", agent=_FakeAgent())


def test_llm_retryable_false_fails_fast():
    # A non-retryable error should not retry
    class _Fatal(PlannerError):
        def __init__(self):
            super().__init__("auth failed", retryable=False)

    llm = _ScriptedLLM(_Fatal())
    p = Planner(llm_call=llm, config=PlannerConfig(max_retries=3, sleep_fn=lambda s: None))
    with pytest.raises(PlannerError, match="auth failed"):
        p.plan(redacted_input="x", agent=_FakeAgent())
    assert len(llm.calls) == 1


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------


def test_plan_must_have_nonempty_experts():
    llm = _ScriptedLLM({"content": json.dumps({"experts": [], "reason": "x"})})
    p = Planner(llm_call=llm)
    with pytest.raises(PlannerError, match="non-empty"):
        p.plan(redacted_input="x", agent=_FakeAgent())


def test_plan_expert_id_must_be_in_available_experts():
    plan = {
        "experts": [
            {"expert_id": "rogue-expert", "priority": 1, "critical": True,
             "subtask_input": "x", "tool_constraints": []}
        ],
        "reason": "x",
    }
    llm = _ScriptedLLM({"content": json.dumps(plan)})
    p = Planner(llm_call=llm)
    with pytest.raises(PlannerError, match="not in agent.available_experts"):
        p.plan(redacted_input="x", agent=_FakeAgent())


def test_plan_priority_must_be_positive_int():
    plan = {
        "experts": [
            {"expert_id": "coding-expert", "priority": 0, "critical": True,
             "subtask_input": "x", "tool_constraints": []}
        ],
        "reason": "x",
    }
    llm = _ScriptedLLM({"content": json.dumps(plan)})
    p = Planner(llm_call=llm)
    with pytest.raises(PlannerError, match="priority"):
        p.plan(redacted_input="x", agent=_FakeAgent())


def test_plan_critical_defaults_to_true_when_missing():
    plan = {
        "experts": [
            {"expert_id": "coding-expert", "priority": 1,
             "subtask_input": "x", "tool_constraints": []}
        ],
        "reason": "x",
    }
    llm = _ScriptedLLM({"content": json.dumps(plan)})
    p = Planner(llm_call=llm)
    plan_obj = p.plan(redacted_input="x", agent=_FakeAgent())
    assert plan_obj.steps[0]["critical"] is True


def test_plan_tool_constraints_must_be_list():
    plan = {
        "experts": [
            {"expert_id": "coding-expert", "priority": 1, "critical": True,
             "subtask_input": "x", "tool_constraints": "icd_search"}
        ],
        "reason": "x",
    }
    llm = _ScriptedLLM({"content": json.dumps(plan)})
    p = Planner(llm_call=llm)
    with pytest.raises(PlannerError, match="tool_constraints"):
        p.plan(redacted_input="x", agent=_FakeAgent())


def test_plan_top_level_must_be_object():
    # Two responses: parse retry reuses the bad content, then outer loop
    # tries a third LLM call — all bad, so parse_retry_count exhausted
    # bubbles a parse-failure PlannerError.
    llm = _ScriptedLLM(
        {"content": "[1,2,3]"},
        {"content": "[1,2,3]"},
        {"content": "[1,2,3]"},
    )
    p = Planner(llm_call=llm, config=PlannerConfig(sleep_fn=lambda s: None))
    with pytest.raises(PlannerError, match="object"):
        p.plan(redacted_input="x", agent=_FakeAgent())


def test_empty_llm_content_raises_retryable():
    llm = _ScriptedLLM({"content": ""}, {"content": json.dumps(_good_plan_dict())})
    p = Planner(llm_call=llm, config=PlannerConfig(sleep_fn=lambda s: None))
    plan = p.plan(redacted_input="x", agent=_FakeAgent())
    assert len(plan.steps) == 1


# ---------------------------------------------------------------------------
# LLMResponse
# ---------------------------------------------------------------------------


def test_llm_response_from_gateway_normalizes():
    payload = {
        "content": "abc",
        "model": "deepseek-v4",
        "latency_ms": 123,
        "degraded": False,
    }
    r = LLMResponse.from_gateway(payload)
    assert r.content == "abc"
    assert r.model == "deepseek-v4"
    assert r.latency_ms == 123
    assert r.is_degraded is False


def test_llm_response_detects_degraded():
    payload = {"content": "x", "is_mock": True, "degraded": True}
    r = LLMResponse.from_gateway(payload)
    assert r.is_degraded is True


def test_llm_response_handles_missing_content():
    r = LLMResponse.from_gateway({})
    assert r.content == ""
    assert r.model == "unknown"


# ---------------------------------------------------------------------------
# PlannerError shape
# ---------------------------------------------------------------------------


def test_planner_error_is_orchestrator_error():
    from app.icoder.agent_runtime.orchestrator.errors import OrchestratorError

    e = PlannerError("x")
    assert isinstance(e, OrchestratorError)
    assert e.code == "planning_failed"
    assert e.stage == "planning"
    assert e.http_status == 500