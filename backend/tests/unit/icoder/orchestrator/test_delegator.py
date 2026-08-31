"""T2 — Delegator (SPEC §3.1, §7.2, §7.3)."""

from __future__ import annotations

from typing import Any

import pytest

from app.icoder.agent_runtime.orchestrator.delegator import (
    Delegator,
    DelegatorConfig,
    ExpertInvocation,
    ExpertInvocationError,
)
from app.icoder.agent_runtime.orchestrator.run_context import ExpertResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step(expert_id="coding-expert", priority=1, critical=True, subtask="do coding"):
    return {
        "expert_id": expert_id,
        "priority": priority,
        "critical": critical,
        "subtask_input": subtask,
        "tool_constraints": ["icd_search"],
    }


class _RecordingInvoker:
    """Counts calls, returns scripted results in order."""

    def __init__(self, *scripted: Any) -> None:
        self._scripted = list(scripted)
        self._idx = 0
        self.calls: list[ExpertInvocation] = []

    def __call__(self, inv: ExpertInvocation) -> dict:
        self.calls.append(inv)
        if self._idx >= len(self._scripted):
            raise AssertionError(
                f"_RecordingInvoker exhausted at call {self._idx + 1}"
            )
        r = self._scripted[self._idx]
        self._idx += 1
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, dict) else {"echo": r}


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_delegator_requires_invoker():
    with pytest.raises(ValueError, match="invoker is required"):
        Delegator(invoker=None)  # type: ignore[arg-type]


def test_default_config_critical_2_noncrit_1():
    cfg = DelegatorConfig()
    assert cfg.critical_max_retries == 2
    assert cfg.non_critical_max_retries == 1


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_delegate_returns_one_result_per_step():
    inv = _RecordingInvoker({"ok": True}, {"ok": True})
    d = Delegator(invoker=inv)
    results = d.delegate(
        plan_steps=[_step("e1"), _step("e2", priority=2, critical=False)],
    )
    assert len(results) == 2
    assert all(isinstance(r, ExpertResult) for r in results)
    assert all(not r.error for r in results)
    assert results[0].expert_id == "e1"
    assert results[1].expert_id == "e2"


def test_delegate_records_invocation_payload():
    inv = _RecordingInvoker({"ok": True})
    d = Delegator(invoker=inv)
    d.delegate(plan_steps=[_step(subtask="extract dx")], context={"ctx": 1})
    assert inv.calls[0].subtask_input == "extract dx"
    assert inv.calls[0].context == {"ctx": 1}
    assert inv.calls[0].attempt == 1


def test_delegate_succeeds_on_first_try_no_sleep():
    sleeps: list[float] = []
    inv = _RecordingInvoker({"ok": True})
    d = Delegator(
        invoker=inv,
        config=DelegatorConfig(sleep_fn=sleeps.append),
    )
    results = d.delegate(plan_steps=[_step()])
    assert len(sleeps) == 0
    assert not results[0].error


# ---------------------------------------------------------------------------
# Retry semantics
# ---------------------------------------------------------------------------


def test_critical_expert_retries_twice_then_succeeds():
    sleeps: list[float] = []
    inv = _RecordingInvoker(
        ExpertInvocationError("net"),
        ExpertInvocationError("again"),
        {"ok": True},
    )
    d = Delegator(
        invoker=inv,
        config=DelegatorConfig(
            critical_max_retries=2,
            critical_backoff_seconds=1.0,
            sleep_fn=sleeps.append,
        ),
    )
    results = d.delegate(plan_steps=[_step(critical=True)])
    assert results[0].error == ""
    assert results[0].result == {"ok": True}
    assert results[0].attempt == 3
    # 2 sleeps between 3 attempts (exp backoff: 1.0, 2.0)
    assert sleeps == [1.0, 2.0]
    assert len(inv.calls) == 3
    assert inv.calls[2].attempt == 3


def test_critical_expert_fails_after_all_retries():
    sleeps: list[float] = []
    inv = _RecordingInvoker(
        ExpertInvocationError("net 1"),
        ExpertInvocationError("net 2"),
        ExpertInvocationError("net 3"),
    )
    d = Delegator(
        invoker=inv,
        config=DelegatorConfig(
            critical_max_retries=2,
            critical_backoff_seconds=0.5,
            sleep_fn=sleeps.append,
        ),
    )
    results = d.delegate(plan_steps=[_step(critical=True)])
    assert results[0].error == "net 3"
    assert results[0].attempt == 3
    assert results[0].result is None
    assert len(inv.calls) == 3


def test_non_critical_expert_retries_once_only():
    sleeps: list[float] = []
    inv = _RecordingInvoker(
        ExpertInvocationError("net"),
        {"ok": True},
    )
    d = Delegator(
        invoker=inv,
        config=DelegatorConfig(
            non_critical_max_retries=1,
            non_critical_backoff_seconds=1.0,
            sleep_fn=sleeps.append,
        ),
    )
    results = d.delegate(plan_steps=[_step(critical=False)])
    assert results[0].error == ""
    assert results[0].attempt == 2
    assert sleeps == [1.0]


def test_non_critical_expert_fails_after_one_retry():
    sleeps: list[float] = []
    inv = _RecordingInvoker(
        ExpertInvocationError("net"),
        ExpertInvocationError("again"),
    )
    d = Delegator(
        invoker=inv,
        config=DelegatorConfig(
            non_critical_max_retries=1,
            non_critical_backoff_seconds=1.0,
            sleep_fn=sleeps.append,
        ),
    )
    results = d.delegate(plan_steps=[_step(critical=False)])
    assert results[0].error == "again"
    assert results[0].attempt == 2


def test_generic_exception_treated_as_retryable():
    sleeps: list[float] = []
    inv = _RecordingInvoker(RuntimeError("boom"), {"ok": True})
    d = Delegator(
        invoker=inv,
        config=DelegatorConfig(
            critical_max_retries=2,
            critical_backoff_seconds=0.5,
            sleep_fn=sleeps.append,
        ),
    )
    results = d.delegate(plan_steps=[_step()])
    assert not results[0].error
    assert "RuntimeError: boom" in (results[0].result and "" or "") or results[0].attempt == 2


def test_non_retryable_invocation_error_fails_fast():
    sleeps: list[float] = []
    inv = _RecordingInvoker(
        ExpertInvocationError("4xx", retryable=False),
    )
    d = Delegator(
        invoker=inv,
        config=DelegatorConfig(
            critical_max_retries=2,
            critical_backoff_seconds=1.0,
            sleep_fn=sleeps.append,
        ),
    )
    results = d.delegate(plan_steps=[_step()])
    assert results[0].error == "4xx"
    assert len(inv.calls) == 1
    assert sleeps == []


# ---------------------------------------------------------------------------
# Sequential ordering
# ---------------------------------------------------------------------------


def test_experts_invoked_in_plan_order():
    inv = _RecordingInvoker({"ok": 1}, {"ok": 2}, {"ok": 3})
    d = Delegator(invoker=inv)
    d.delegate(
        plan_steps=[
            _step("a", priority=1),
            _step("b", priority=2),
            _step("c", priority=3),
        ]
    )
    assert [c.expert_id for c in inv.calls] == ["a", "b", "c"]


def test_failed_expert_does_not_abort_subsequent():
    inv = _RecordingInvoker(
        ExpertInvocationError("e1 fail"),
        ExpertInvocationError("e1 fail 2"),
        ExpertInvocationError("e1 fail 3"),  # e1 critical, exhausts retries
        {"ok": "e2"},
    )
    d = Delegator(invoker=inv, config=DelegatorConfig(sleep_fn=lambda s: None))
    results = d.delegate(plan_steps=[_step("e1"), _step("e2", priority=2, critical=False)])
    assert len(results) == 2
    assert results[0].error != ""
    assert results[1].result == {"ok": "e2"}


# ---------------------------------------------------------------------------
# Latency tracking
# ---------------------------------------------------------------------------


def test_latency_recorded_per_expert():
    inv = _RecordingInvoker({"ok": True})
    d = Delegator(invoker=inv)
    results = d.delegate(plan_steps=[_step()])
    assert results[0].latency_ms >= 0


# ---------------------------------------------------------------------------
# ExpertInvocationError
# ---------------------------------------------------------------------------


def test_invocation_error_is_orchestrator_error():
    from app.icoder.agent_runtime.orchestrator.errors import OrchestratorError

    e = ExpertInvocationError("net", retryable=True)
    assert isinstance(e, OrchestratorError)
    assert e.code == "expert_failed"
    assert e.http_status == 502
    assert e.retryable is True


def test_invocation_error_retryable_default():
    e = ExpertInvocationError("x")
    assert e.retryable is True
