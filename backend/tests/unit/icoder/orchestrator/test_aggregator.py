"""T2 — Aggregator (SPEC §7.4)."""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.orchestrator.aggregator import (
    Aggregator,
    AggregatorConfig,
    AggregatorError,
)
from app.icoder.agent_runtime.orchestrator.run_context import (
    ExpertResult,
    OrchestratorMessage,
)


def _step(expert_id="coding-expert", priority=1, critical=True):
    return {
        "expert_id": expert_id,
        "priority": priority,
        "critical": critical,
        "subtask_input": "x",
        "tool_constraints": [],
    }


def _ok(expert_id, result, latency_ms=10, attempt=1):
    return ExpertResult(
        expert_id=expert_id,
        subtask_input="x",
        result=result,
        latency_ms=latency_ms,
        attempt=attempt,
    )


def _err(expert_id, error="boom"):
    return ExpertResult(
        expert_id=expert_id,
        subtask_input="x",
        error=error,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_default_config():
    cfg = AggregatorConfig()
    assert cfg.fail_on_critical_missing is True
    assert cfg.include_failed_experts is True


def test_aggregator_uses_default_config():
    a = Aggregator()
    assert a._config.fail_on_critical_missing is True


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_single_expert_returns_message():
    a = Aggregator()
    msg = a.aggregate(
        plan_steps=[_step("coding-expert")],
        expert_results=[_ok("coding-expert", {"primary_diagnosis": {"code": "I50.9"}})],
        reason="编码审核",
    )
    assert isinstance(msg, OrchestratorMessage)
    assert msg.role == "agent"
    # expect at least one data part per expert + summary + text
    assert len(msg.parts) >= 2


def test_two_experts_ordered_by_priority():
    a = Aggregator()
    plan = [_step("coding", priority=1), _step("drg", priority=2, critical=False)]
    results = [
        _ok("coding", {"primary_diagnosis": {"code": "I50.9"}}),
        _ok("drg", {"drg_code": "FR13"}),
    ]
    msg = a.aggregate(plan_steps=plan, expert_results=results)
    # first data part is the highest-priority expert
    first_data = msg.parts[0]
    assert first_data["kind"] == "data"
    assert first_data["data"]["expert_id"] == "coding"


def test_message_summary_part_counts_successes_and_failures():
    a = Aggregator()
    plan = [_step("coding", priority=1), _step("drg", priority=2, critical=False)]
    results = [
        _ok("coding", {"x": 1}),
        _err("drg"),
    ]
    msg = a.aggregate(plan_steps=plan, expert_results=results)
    summary_part = next(
        p for p in msg.parts if p.get("kind") == "data" and "summary" in p["data"]
    )
    assert summary_part["data"]["summary"]["expert_count"] == 2
    assert summary_part["data"]["summary"]["succeeded"] == 1
    assert summary_part["data"]["summary"]["failed"] == 1


# ---------------------------------------------------------------------------
# Critical expert missing → fail (default)
# ---------------------------------------------------------------------------


def test_critical_expert_failed_raises_by_default():
    a = Aggregator()
    plan = [_step("coding", critical=True)]
    results = [_err("coding", error="net")]
    with pytest.raises(AggregatorError, match="critical"):
        a.aggregate(plan_steps=plan, expert_results=results)


def test_critical_expert_missing_raises():
    a = Aggregator()
    plan = [_step("coding", critical=True), _step("drg", priority=2, critical=False)]
    results = [_ok("drg", {"x": 1})]
    with pytest.raises(AggregatorError, match="coding"):
        a.aggregate(plan_steps=plan, expert_results=results)


def test_non_critical_failure_does_not_raise():
    a = Aggregator()
    plan = [_step("coding", critical=True), _step("drg", priority=2, critical=False)]
    results = [_ok("coding", {"x": 1}), _err("drg", error="net")]
    msg = a.aggregate(plan_steps=plan, expert_results=results)
    # succeeded=1, failed=1
    summary = next(
        p for p in msg.parts if p.get("kind") == "data" and "summary" in p["data"]
    )
    assert summary["data"]["summary"]["succeeded"] == 1


def test_fail_on_critical_missing_disabled_does_not_raise():
    a = Aggregator(config=AggregatorConfig(fail_on_critical_missing=False))
    plan = [_step("coding", critical=True)]
    results = [_err("coding", error="net")]
    msg = a.aggregate(plan_steps=plan, expert_results=results)
    # failed expert is included as a part with error
    expert_parts = [
        p for p in msg.parts
        if p.get("kind") == "data" and "expert_id" in p["data"]
    ]
    assert expert_parts[0]["data"]["ok"] is False
    assert expert_parts[0]["data"]["error"] == "net"


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def test_conflict_detected_on_diverging_codes():
    a = Aggregator()
    plan = [_step("coding"), _step("drg", priority=2, critical=False)]
    results = [
        _ok("coding", {"primary_diagnosis": {"code": "I50.9"}}),
        _ok("drg", {"primary_diagnosis": {"code": "I50.1"}}),
    ]
    msg = a.aggregate(plan_steps=plan, expert_results=results)
    summary = next(
        p for p in msg.parts if p.get("kind") == "data" and "summary" in p["data"]
    )
    assert summary["data"]["summary"]["conflicted"] is True
    assert "primary_diagnosis.code" in summary["data"]["summary"]["conflicts"]


def test_no_conflict_when_values_agree():
    a = Aggregator()
    plan = [_step("coding"), _step("drg", priority=2, critical=False)]
    results = [
        _ok("coding", {"primary_diagnosis": {"code": "I50.9"}}),
        _ok("drg", {"primary_diagnosis": {"code": "I50.9"}}),
    ]
    msg = a.aggregate(plan_steps=plan, expert_results=results)
    summary = next(
        p for p in msg.parts if p.get("kind") == "data" and "summary" in p["data"]
    )
    assert summary["data"]["summary"]["conflicted"] is False


def test_conflict_ignores_failed_experts():
    a = Aggregator()
    plan = [_step("coding"), _step("drg", priority=2, critical=False)]
    results = [
        _ok("coding", {"primary_diagnosis": {"code": "I50.9"}}),
        _err("drg"),
    ]
    msg = a.aggregate(plan_steps=plan, expert_results=results)
    summary = next(
        p for p in msg.parts if p.get("kind") == "data" and "summary" in p["data"]
    )
    assert summary["data"]["summary"]["conflicted"] is False


# ---------------------------------------------------------------------------
# Configurable: skip failed experts entirely
# ---------------------------------------------------------------------------


def test_include_failed_experts_false_drops_failed():
    a = Aggregator(config=AggregatorConfig(include_failed_experts=False))
    plan = [_step("coding", critical=True), _step("drg", priority=2, critical=False)]
    results = [_ok("coding", {"x": 1}), _err("drg")]
    msg = a.aggregate(plan_steps=plan, expert_results=results)
    expert_parts = [
        p for p in msg.parts
        if p.get("kind") == "data" and "expert_id" in p["data"]
    ]
    assert len(expert_parts) == 1
    assert expert_parts[0]["data"]["expert_id"] == "coding"


# ---------------------------------------------------------------------------
# Text summary
# ---------------------------------------------------------------------------


def test_text_summary_mentions_success_and_failure_counts():
    a = Aggregator()
    plan = [_step("coding", critical=True), _step("drg", priority=2, critical=False)]
    results = [_ok("coding", {"x": 1}), _err("drg")]
    msg = a.aggregate(plan_steps=plan, expert_results=results)
    text_part = next(p for p in msg.parts if p.get("kind") == "text")
    assert "1/2" in text_part["text"]
    assert "1 failed" in text_part["text"]


def test_text_summary_includes_conflict_marker():
    a = Aggregator()
    plan = [_step("coding"), _step("drg", priority=2, critical=False)]
    results = [
        _ok("coding", {"drg_code": "FR13"}),
        _ok("drg", {"drg_code": "FR21"}),
    ]
    msg = a.aggregate(plan_steps=plan, expert_results=results)
    text_part = next(p for p in msg.parts if p.get("kind") == "text")
    assert "conflict" in text_part["text"].lower()


# ---------------------------------------------------------------------------
# AggregatorError
# ---------------------------------------------------------------------------


def test_aggregator_error_is_orchestrator_error():
    from app.icoder.agent_runtime.orchestrator.errors import OrchestratorError

    e = AggregatorError("x")
    assert isinstance(e, OrchestratorError)
    assert e.code == "aggregation_failed"
    assert e.http_status == 500
    assert e.retryable is False


# ---------------------------------------------------------------------------
# Determinism + empty input
# ---------------------------------------------------------------------------


def test_no_experts_returns_minimal_message():
    a = Aggregator(config=AggregatorConfig(fail_on_critical_missing=False))
    msg = a.aggregate(plan_steps=[], expert_results=[])
    summary = next(
        p for p in msg.parts if p.get("kind") == "data" and "summary" in p["data"]
    )
    assert summary["data"]["summary"]["expert_count"] == 0


def test_aggregate_is_deterministic():
    a = Aggregator(config=AggregatorConfig(fail_on_critical_missing=False))
    plan = [_step("coding"), _step("drg", priority=2, critical=False)]
    results = [
        _ok("coding", {"primary_diagnosis": {"code": "I50.9"}}),
        _ok("drg", {"primary_diagnosis": {"code": "I50.1"}}),
    ]
    msg1 = a.aggregate(plan_steps=plan, expert_results=results, reason="r")
    msg2 = a.aggregate(plan_steps=plan, expert_results=results, reason="r")
    assert msg1.parts == msg2.parts


def test_reason_propagates_to_summary():
    a = Aggregator(config=AggregatorConfig(fail_on_critical_missing=False))
    msg = a.aggregate(
        plan_steps=[_step("coding")],
        expert_results=[_ok("coding", {"x": 1})],
        reason="编码审核",
    )
    summary = next(
        p for p in msg.parts if p.get("kind") == "data" and "summary" in p["data"]
    )
    assert summary["data"]["summary"]["reason"] == "编码审核"