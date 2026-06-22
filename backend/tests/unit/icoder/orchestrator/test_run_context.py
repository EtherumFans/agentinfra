"""T1 — RunContext + Plan + ExpertResult + OrchestratorMessage + StateTransition."""

from __future__ import annotations

from dataclasses import is_dataclass
from datetime import datetime, timezone

from app.icoder.agent_runtime.orchestrator.run_context import (
    ExpertResult,
    OrchestratorMessage,
    Plan,
    RunContext,
    StateTransition,
)


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def test_plan_default_empty_steps():
    p = Plan()
    assert p.steps == []
    assert p.raw_llm_output is None


def test_plan_with_steps_and_llm_output():
    steps = [{"expert_id": "e1", "subtask": "extract dx"}]
    raw = {"choices": [{"message": {"content": "..."}}]}
    p = Plan(steps=steps, raw_llm_output=raw)
    assert p.steps == steps
    assert p.raw_llm_output == raw


def test_plan_is_dataclass():
    assert is_dataclass(Plan)


# ---------------------------------------------------------------------------
# ExpertResult
# ---------------------------------------------------------------------------


def test_expert_result_defaults():
    r = ExpertResult(expert_id="coding_expert")
    assert r.expert_id == "coding_expert"
    assert r.subtask_input is None
    assert r.result is None
    assert r.error == ""
    assert r.latency_ms == 0
    assert r.attempt == 1


def test_expert_result_records_failure():
    r = ExpertResult(
        expert_id="drg_expert",
        subtask_input="I50.9",
        error="timeout",
        latency_ms=30000,
        attempt=2,
    )
    assert r.error == "timeout"
    assert r.latency_ms == 30000
    assert r.attempt == 2


def test_expert_result_is_dataclass():
    assert is_dataclass(ExpertResult)


# ---------------------------------------------------------------------------
# OrchestratorMessage (A2A Message body)
# ---------------------------------------------------------------------------


def test_orchestrator_message_defaults():
    m = OrchestratorMessage()
    assert m.role == "agent"
    assert m.parts == []
    assert m.message_id == ""


def test_orchestrator_message_with_text_and_data_parts():
    parts = [
        {"type": "text", "text": "result"},
        {"type": "data", "data": {"codes": ["I50.9"]}},
    ]
    m = OrchestratorMessage(role="agent", parts=parts, message_id="m-001")
    assert m.parts == parts
    assert m.message_id == "m-001"


# ---------------------------------------------------------------------------
# StateTransition
# ---------------------------------------------------------------------------


def test_state_transition_construction():
    ts = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    t = StateTransition(
        from_state="received",
        to_state="planning",
        event="phi_redacted",
        timestamp=ts,
    )
    assert t.from_state == "received"
    assert t.to_state == "planning"
    assert t.event == "phi_redacted"
    assert t.timestamp == ts


def test_state_transition_is_dataclass():
    assert is_dataclass(StateTransition)


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------


def test_run_context_minimal_construction():
    ctx = RunContext(
        run_id="r-1",
        context_id="550e8400-e29b-41d4-a716-446655440000",
        agent_id="medical-coding-agent",
    )
    assert ctx.run_id == "r-1"
    assert ctx.context_id == "550e8400-e29b-41d4-a716-446655440000"
    assert ctx.agent_id == "medical-coding-agent"
    assert ctx.agent_definition is None
    assert ctx.original_input == ""
    assert ctx.redacted_input == ""
    assert ctx.plan is None
    assert ctx.expert_results == []
    assert ctx.final_message is None
    assert ctx.error is None
    assert ctx.state_history == []


def test_run_context_holds_redacted_input_separately():
    ctx = RunContext(
        run_id="r-2",
        context_id="c2",
        agent_id="a",
        original_input="Patient: 张三, ID 110101199001011234",
        redacted_input="Patient: [REDACTED], ID [REDACTED]",
    )
    assert ctx.original_input != ctx.redacted_input
    assert "[REDACTED]" in ctx.redacted_input
    assert "110101" in ctx.original_input


def test_run_context_collects_expert_results():
    ctx = RunContext(run_id="r-3", context_id="c3", agent_id="a")
    ctx.expert_results.append(ExpertResult(expert_id="e1", result={"x": 1}))
    ctx.expert_results.append(ExpertResult(expert_id="e2", error="boom"))
    assert len(ctx.expert_results) == 2
    assert ctx.expert_results[0].result == {"x": 1}
    assert ctx.expert_results[1].error == "boom"


def test_run_context_holds_plan():
    ctx = RunContext(run_id="r-4", context_id="c4", agent_id="a")
    plan = Plan(steps=[{"expert_id": "e1"}])
    ctx.plan = plan
    assert ctx.plan is plan


def test_run_context_state_history_appended_externally():
    ctx = RunContext(run_id="r-5", context_id="c5", agent_id="a")
    ctx.state_history.append(
        StateTransition("received", "planning", "phi_redacted", datetime.now(timezone.utc))
    )
    assert len(ctx.state_history) == 1


def test_run_context_is_dataclass():
    assert is_dataclass(RunContext)


def test_run_context_final_message_carries_a2a_parts():
    ctx = RunContext(run_id="r-6", context_id="c6", agent_id="a")
    msg = OrchestratorMessage(
        parts=[{"type": "data", "data": {"diagnosis": ["I50.9"]}}],
        message_id="m-final",
    )
    ctx.final_message = msg
    assert ctx.final_message.message_id == "m-final"


def test_run_context_error_carries_orchestrator_error_value():
    from app.icoder.agent_runtime.orchestrator.errors import OrchestratorError

    ctx = RunContext(run_id="r-7", context_id="c7", agent_id="a")
    err = OrchestratorError.from_code("EXPERT_FAILED", "crash", stage="delegating")
    ctx.error = err
    assert ctx.error is err
    assert ctx.error.http_status == 502