"""T2 — Orchestrator system prompt + Plan schema (SPEC §6.1, §6.2)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.icoder.agent_runtime.orchestrator.prompts import (
    NON_GOALS_NOTICE,
    ORCHESTRATOR_SYSTEM_PROMPT,
    PHI_REDACTION_NOTICE,
    PLAN_SCHEMA_DESCRIPTION,
    PRODUCTION_WRITEBACK_BLOCKED,
    assert_prompt_invariants,
    build_planner_user_message,
    build_planner_user_message_from_agent,
)


# ---------------------------------------------------------------------------
# Hard invariants — spec §6.1 red lines
# ---------------------------------------------------------------------------


def test_prompt_contains_production_writeback_blocked():
    assert PRODUCTION_WRITEBACK_BLOCKED in ORCHESTRATOR_SYSTEM_PROMPT


def test_prompt_mentions_phi_redaction():
    assert PHI_REDACTION_NOTICE in ORCHESTRATOR_SYSTEM_PROMPT


def test_prompt_marks_orchestrator_as_dispatcher_only():
    # Must explicitly NOT do the work itself
    assert "不做具体业务" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "不编码" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "不调用任何工具" in ORCHESTRATOR_SYSTEM_PROMPT


def test_prompt_specifies_plan_schema():
    assert "Plan schema" in ORCHESTRATOR_SYSTEM_PROMPT
    assert '"experts"' in ORCHESTRATOR_SYSTEM_PROMPT
    assert '"subtask_input"' in ORCHESTRATOR_SYSTEM_PROMPT


def test_prompt_invariants_passes_default():
    assert_prompt_invariants()  # does not raise


def test_assert_invariants_catches_missing_writeback_line():
    bad = ORCHESTRATOR_SYSTEM_PROMPT.replace(PRODUCTION_WRITEBACK_BLOCKED, "")
    with pytest.raises(ValueError, match="production_writeback_blocked"):
        assert_prompt_invariants(bad)


def test_assert_invariants_catches_missing_phi_notice():
    bad = ORCHESTRATOR_SYSTEM_PROMPT.replace(PHI_REDACTION_NOTICE, "")
    with pytest.raises(ValueError, match="PHI"):
        assert_prompt_invariants(bad)


def test_assert_invariants_catches_missing_plan_schema():
    bad = ORCHESTRATOR_SYSTEM_PROMPT.replace("Plan schema", "PLAN SCHEMA")
    with pytest.raises(ValueError, match="Plan schema"):
        assert_prompt_invariants(bad)


# ---------------------------------------------------------------------------
# build_planner_user_message
# ---------------------------------------------------------------------------


def test_user_message_includes_agent_id_name():
    msg = build_planner_user_message(
        redacted_input="病历已脱敏",
        agent_id="coding-agent",
        agent_name="Coding Agent",
        available_experts=["coding-expert"],
    )
    assert "coding-agent" in msg
    assert "Coding Agent" in msg
    assert "coding-expert" in msg
    assert "病历已脱敏" in msg


def test_user_message_includes_schema_grouding():
    msg = build_planner_user_message(
        redacted_input="x",
        agent_id="a",
        agent_name="A",
        available_experts=["e1"],
    )
    assert "priority" in msg
    assert "critical" in msg
    assert "subtask_input" in msg
    assert "tool_constraints" in msg


def test_user_message_optional_fields_omitted_when_blank():
    msg = build_planner_user_message(
        redacted_input="x",
        agent_id="a",
        agent_name="A",
        available_experts=[],
    )
    assert "non_goals" not in msg
    assert "output_contract" not in msg


def test_user_message_includes_optional_fields_when_present():
    msg = build_planner_user_message(
        redacted_input="x",
        agent_id="a",
        agent_name="A",
        available_experts=[],
        non_goals="不写回 EMR",
        output_contract="MedicalCodingOutputSchema",
    )
    assert "不写回 EMR" in msg
    assert "MedicalCodingOutputSchema" in msg


def test_user_message_marks_input_as_redacted():
    msg = build_planner_user_message(
        redacted_input="x",
        agent_id="a",
        agent_name="A",
        available_experts=[],
    )
    assert "PHI redacted" in msg or "脱敏" in msg


# ---------------------------------------------------------------------------
# build_planner_user_message_from_agent
# ---------------------------------------------------------------------------


@dataclass
class _FakeAgent:
    id: str = "agent-x"
    name: str = "Agent X"
    expert_ids: list[str] = field(default_factory=lambda: ["e1", "e2"])
    config: dict = field(default_factory=dict)


def test_from_agent_uses_id_and_expert_ids():
    msg = build_planner_user_message_from_agent(
        redacted_input="x",
        agent=_FakeAgent(),
    )
    assert "agent-x" in msg
    assert "Agent X" in msg
    assert "e1" in msg
    assert "e2" in msg


def test_from_agent_falls_back_to_name_when_id_blank():
    agent = _FakeAgent(id="", name="Fallback Name")
    msg = build_planner_user_message_from_agent(redacted_input="x", agent=agent)
    assert "Fallback Name" in msg


def test_from_agent_propagates_non_goals_from_config():
    agent = _FakeAgent(config={"non_goals": ["a", "b"]})
    msg = build_planner_user_message_from_agent(redacted_input="x", agent=agent)
    assert "a" in msg and "b" in msg


def test_plan_schema_description_documents_required_fields():
    assert "experts" in PLAN_SCHEMA_DESCRIPTION
    assert "non-empty" in PLAN_SCHEMA_DESCRIPTION
    assert "priority" in PLAN_SCHEMA_DESCRIPTION
    assert "critical" in PLAN_SCHEMA_DESCRIPTION