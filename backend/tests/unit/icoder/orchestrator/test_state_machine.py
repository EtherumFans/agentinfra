"""T1 — OrchestratorStateMachine (SPEC §4.3).

Pure immutable transitions; covers all 10 valid (state, event) → state mappings
plus terminal-state guards, retry loop, history accumulation, immutability, and
serialization.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.icoder.agent_runtime.orchestrator.errors import OrchestratorStateError
from app.icoder.agent_runtime.orchestrator.events import OrchestratorEvent
from app.icoder.agent_runtime.orchestrator.state_machine import (
    ALL_STATES,
    ORCHESTRATOR_STATE_AGGREGATING,
    ORCHESTRATOR_STATE_COMPLETED,
    ORCHESTRATOR_STATE_DELEGATING,
    ORCHESTRATOR_STATE_FAILED,
    ORCHESTRATOR_STATE_PLANNING,
    ORCHESTRATOR_STATE_RECEIVED,
    TERMINAL_STATES,
    TRANSITIONS,
    OrchestratorStateMachine,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_all_states_frozenset_six_members():
    assert ALL_STATES == frozenset(
        {
            ORCHESTRATOR_STATE_RECEIVED,
            ORCHESTRATOR_STATE_PLANNING,
            ORCHESTRATOR_STATE_DELEGATING,
            ORCHESTRATOR_STATE_AGGREGATING,
            ORCHESTRATOR_STATE_COMPLETED,
            ORCHESTRATOR_STATE_FAILED,
        }
    )


def test_terminal_states_only_completed_and_failed():
    assert TERMINAL_STATES == frozenset(
        {ORCHESTRATOR_STATE_COMPLETED, ORCHESTRATOR_STATE_FAILED}
    )


def test_terminal_states_disjoint_from_non_terminal():
    assert TERMINAL_STATES.isdisjoint(
        ALL_STATES - TERMINAL_STATES
    )


def test_transitions_table_has_ten_entries():
    assert len(TRANSITIONS) == 10


def test_transitions_covers_happy_path():
    """received → planning → delegating → aggregating → completed."""
    assert TRANSITIONS[
        (ORCHESTRATOR_STATE_RECEIVED, OrchestratorEvent.PHI_REDACTED)
    ] == ORCHESTRATOR_STATE_PLANNING
    assert TRANSITIONS[
        (ORCHESTRATOR_STATE_PLANNING, OrchestratorEvent.PLAN_GENERATED)
    ] == ORCHESTRATOR_STATE_DELEGATING
    assert TRANSITIONS[
        (ORCHESTRATOR_STATE_DELEGATING, OrchestratorEvent.ALL_EXPERTS_RETURNED)
    ] == ORCHESTRATOR_STATE_AGGREGATING
    assert TRANSITIONS[
        (ORCHESTRATOR_STATE_AGGREGATING, OrchestratorEvent.AGGREGATED)
    ] == ORCHESTRATOR_STATE_COMPLETED


def test_transitions_failure_paths_all_lead_to_failed():
    failed_paths = [
        (ORCHESTRATOR_STATE_RECEIVED, OrchestratorEvent.INBOUND_INVALID),
        (ORCHESTRATOR_STATE_PLANNING, OrchestratorEvent.PLANNING_TIMEOUT),
        (ORCHESTRATOR_STATE_DELEGATING, OrchestratorEvent.CRITICAL_EXPERT_FAILED),
        (ORCHESTRATOR_STATE_DELEGATING, OrchestratorEvent.DELEGATING_TIMEOUT),
        (ORCHESTRATOR_STATE_AGGREGATING, OrchestratorEvent.AGGREGATION_FAILED),
    ]
    for state, event in failed_paths:
        assert TRANSITIONS[(state, event)] == ORCHESTRATOR_STATE_FAILED, (
            f"{state} + {event.value} → expected failed"
        )


def test_plan_failed_loops_back_to_planning():
    """SPEC §4.2 — plan_failed retries planning rather than failing the run."""
    assert TRANSITIONS[
        (ORCHESTRATOR_STATE_PLANNING, OrchestratorEvent.PLAN_FAILED)
    ] == ORCHESTRATOR_STATE_PLANNING


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_default_construction_starts_at_received():
    sm = OrchestratorStateMachine()
    assert sm.current_state == ORCHESTRATOR_STATE_RECEIVED
    assert sm.state_history == ()
    assert sm.is_terminal is False


def test_unknown_initial_state_raises_value_error():
    with pytest.raises(ValueError, match="unknown initial state"):
        OrchestratorStateMachine(state="bogus")


def test_now_fn_is_used_for_transition_timestamps():
    fixed = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    sm = OrchestratorStateMachine(now_fn=lambda: fixed)
    sm2 = sm.transition(OrchestratorEvent.PHI_REDACTED)
    assert sm2.state_history[-1].timestamp == fixed


def test_now_fn_default_is_utc_aware():
    sm = OrchestratorStateMachine()
    sm2 = sm.transition(OrchestratorEvent.PHI_REDACTED)
    ts = sm2.state_history[-1].timestamp
    assert ts.tzinfo is not None
    assert ts.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_is_terminal_true_only_for_completed_failed():
    assert OrchestratorStateMachine(state=ORCHESTRATOR_STATE_COMPLETED).is_terminal
    assert OrchestratorStateMachine(state=ORCHESTRATOR_STATE_FAILED).is_terminal
    assert not OrchestratorStateMachine(state=ORCHESTRATOR_STATE_RECEIVED).is_terminal
    assert not OrchestratorStateMachine(state=ORCHESTRATOR_STATE_PLANNING).is_terminal
    assert not OrchestratorStateMachine(state=ORCHESTRATOR_STATE_DELEGATING).is_terminal
    assert not OrchestratorStateMachine(state=ORCHESTRATOR_STATE_AGGREGATING).is_terminal


# ---------------------------------------------------------------------------
# Pure transitions
# ---------------------------------------------------------------------------


def _advance(sm: OrchestratorStateMachine, *events: OrchestratorEvent) -> OrchestratorStateMachine:
    """Helper — walk an event sequence to build the target SM."""
    for e in events:
        sm = sm.transition(e)
    return sm


def test_transition_returns_new_instance_does_not_mutate():
    sm = OrchestratorStateMachine()
    sm2 = sm.transition(OrchestratorEvent.PHI_REDACTED)
    assert sm is not sm2
    assert sm.current_state == ORCHESTRATOR_STATE_RECEIVED  # original untouched
    assert sm2.current_state == ORCHESTRATOR_STATE_PLANNING


def test_happy_path_full_walk():
    sm = OrchestratorStateMachine()
    sm = _advance(
        sm,
        OrchestratorEvent.PHI_REDACTED,
        OrchestratorEvent.PLAN_GENERATED,
        OrchestratorEvent.ALL_EXPERTS_RETURNED,
        OrchestratorEvent.AGGREGATED,
    )
    assert sm.current_state == ORCHESTRATOR_STATE_COMPLETED
    assert sm.is_terminal
    assert len(sm.state_history) == 4


def test_inbound_invalid_short_circuits_to_failed():
    sm = OrchestratorStateMachine()
    sm = sm.transition(OrchestratorEvent.INBOUND_INVALID)
    assert sm.current_state == ORCHESTRATOR_STATE_FAILED
    assert sm.is_terminal
    assert len(sm.state_history) == 1


def test_planning_timeout_goes_to_failed():
    sm = _advance(
        OrchestratorStateMachine(),
        OrchestratorEvent.PHI_REDACTED,
    )
    sm = sm.transition(OrchestratorEvent.PLANNING_TIMEOUT)
    assert sm.current_state == ORCHESTRATOR_STATE_FAILED


def test_delegating_critical_expert_failed_goes_to_failed():
    sm = _advance(
        OrchestratorStateMachine(),
        OrchestratorEvent.PHI_REDACTED,
        OrchestratorEvent.PLAN_GENERATED,
    )
    sm = sm.transition(OrchestratorEvent.CRITICAL_EXPERT_FAILED)
    assert sm.current_state == ORCHESTRATOR_STATE_FAILED


def test_delegating_timeout_goes_to_failed():
    sm = _advance(
        OrchestratorStateMachine(),
        OrchestratorEvent.PHI_REDACTED,
        OrchestratorEvent.PLAN_GENERATED,
    )
    sm = sm.transition(OrchestratorEvent.DELEGATING_TIMEOUT)
    assert sm.current_state == ORCHESTRATOR_STATE_FAILED


def test_aggregation_failed_goes_to_failed():
    sm = _advance(
        OrchestratorStateMachine(),
        OrchestratorEvent.PHI_REDACTED,
        OrchestratorEvent.PLAN_GENERATED,
        OrchestratorEvent.ALL_EXPERTS_RETURNED,
    )
    sm = sm.transition(OrchestratorEvent.AGGREGATION_FAILED)
    assert sm.current_state == ORCHESTRATOR_STATE_FAILED


def test_plan_failed_loops_and_then_succeeds():
    """Retry semantics: plan_failed keeps us in planning, plan_generated proceeds."""
    sm = _advance(
        OrchestratorStateMachine(),
        OrchestratorEvent.PHI_REDACTED,
    )
    sm = sm.transition(OrchestratorEvent.PLAN_FAILED)
    assert sm.current_state == ORCHESTRATOR_STATE_PLANNING
    assert sm.is_terminal is False

    sm = sm.transition(OrchestratorEvent.PLAN_GENERATED)
    assert sm.current_state == ORCHESTRATOR_STATE_DELEGATING
    assert len(sm.state_history) == 3


def test_plan_failed_can_loop_multiple_times():
    sm = _advance(
        OrchestratorStateMachine(),
        OrchestratorEvent.PHI_REDACTED,
    )
    for _ in range(3):
        sm = sm.transition(OrchestratorEvent.PLAN_FAILED)
    assert sm.current_state == ORCHESTRATOR_STATE_PLANNING
    assert len(sm.state_history) == 4  # 1 received→planning + 3 retries


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


def test_invalid_transition_raises_state_error():
    sm = OrchestratorStateMachine()  # received
    with pytest.raises(OrchestratorStateError) as excinfo:
        sm.transition(OrchestratorEvent.PLAN_GENERATED)  # no edge from received
    assert excinfo.value.current_state == ORCHESTRATOR_STATE_RECEIVED
    assert excinfo.value.event == OrchestratorEvent.PLAN_GENERATED.value


def test_terminal_state_rejects_all_events():
    for terminal in (ORCHESTRATOR_STATE_COMPLETED, ORCHESTRATOR_STATE_FAILED):
        sm = OrchestratorStateMachine(state=terminal)
        for ev in OrchestratorEvent:
            with pytest.raises(OrchestratorStateError) as excinfo:
                sm.transition(ev)
            assert excinfo.value.current_state == terminal
            assert excinfo.value.event == ev.value


def test_aggregating_rejects_delegating_only_events():
    """aggregating only accepts AGGREGATED or AGGREGATION_FAILED."""
    sm = _advance(
        OrchestratorStateMachine(),
        OrchestratorEvent.PHI_REDACTED,
        OrchestratorEvent.PLAN_GENERATED,
        OrchestratorEvent.ALL_EXPERTS_RETURNED,
    )
    assert sm.current_state == ORCHESTRATOR_STATE_AGGREGATING
    with pytest.raises(OrchestratorStateError):
        sm.transition(OrchestratorEvent.PLAN_GENERATED)
    with pytest.raises(OrchestratorStateError):
        sm.transition(OrchestratorEvent.ALL_EXPERTS_RETURNED)


def test_delegating_rejects_planning_events():
    sm = _advance(
        OrchestratorStateMachine(),
        OrchestratorEvent.PHI_REDACTED,
        OrchestratorEvent.PLAN_GENERATED,
    )
    assert sm.current_state == ORCHESTRATOR_STATE_DELEGATING
    with pytest.raises(OrchestratorStateError):
        sm.transition(OrchestratorEvent.PLAN_GENERATED)
    with pytest.raises(OrchestratorStateError):
        sm.transition(OrchestratorEvent.PLAN_FAILED)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def test_history_records_state_transition_metadata():
    fixed = datetime(2026, 6, 20, 9, 30, 0, tzinfo=timezone.utc)
    sm = OrchestratorStateMachine(now_fn=lambda: fixed)
    sm = sm.transition(OrchestratorEvent.PHI_REDACTED)
    assert len(sm.state_history) == 1
    rec = sm.state_history[0]
    assert rec.from_state == ORCHESTRATOR_STATE_RECEIVED
    assert rec.to_state == ORCHESTRATOR_STATE_PLANNING
    assert rec.event == OrchestratorEvent.PHI_REDACTED.value
    assert rec.timestamp == fixed


def test_history_is_immutable_tuple():
    sm = OrchestratorStateMachine()
    sm = sm.transition(OrchestratorEvent.PHI_REDACTED)
    assert isinstance(sm.state_history, tuple)


def test_old_history_preserved_on_new_transition():
    sm = OrchestratorStateMachine()
    sm = sm.transition(OrchestratorEvent.PHI_REDACTED)
    old_history = sm.state_history
    sm2 = sm.transition(OrchestratorEvent.PLAN_GENERATED)
    assert sm2.state_history[: len(old_history)] == old_history
    assert sm.state_history == old_history  # original unchanged


# ---------------------------------------------------------------------------
# reachable_from
# ---------------------------------------------------------------------------


def test_reachable_from_received():
    sm = OrchestratorStateMachine()
    reachable = sm.reachable_from(ORCHESTRATOR_STATE_RECEIVED)
    assert reachable == {
        OrchestratorEvent.PHI_REDACTED,
        OrchestratorEvent.INBOUND_INVALID,
    }


def test_reachable_from_planning_includes_plan_failed():
    sm = OrchestratorStateMachine(state=ORCHESTRATOR_STATE_PLANNING)
    reachable = sm.reachable_from(ORCHESTRATOR_STATE_PLANNING)
    assert OrchestratorEvent.PLAN_FAILED in reachable
    assert OrchestratorEvent.PLAN_GENERATED in reachable
    assert OrchestratorEvent.PLANNING_TIMEOUT in reachable


def test_reachable_from_terminal_is_empty():
    for terminal in (ORCHESTRATOR_STATE_COMPLETED, ORCHESTRATOR_STATE_FAILED):
        assert OrchestratorStateMachine(state=terminal).reachable_from(terminal) == set()


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


def test_to_dict_includes_state_and_history():
    sm = OrchestratorStateMachine()
    sm = sm.transition(OrchestratorEvent.PHI_REDACTED)
    d = sm.to_dict()
    assert d["current_state"] == ORCHESTRATOR_STATE_PLANNING
    assert isinstance(d["history"], list)
    assert len(d["history"]) == 1
    rec = d["history"][0]
    assert rec["from_state"] == ORCHESTRATOR_STATE_RECEIVED
    assert rec["to_state"] == ORCHESTRATOR_STATE_PLANNING
    assert rec["event"] == OrchestratorEvent.PHI_REDACTED.value
    # timestamp must be ISO 8601 string
    assert isinstance(rec["timestamp"], str)
    assert "T" in rec["timestamp"]  # datetime.isoformat() includes 'T'


def test_to_dict_at_initial_state_has_empty_history():
    sm = OrchestratorStateMachine()
    d = sm.to_dict()
    assert d["current_state"] == ORCHESTRATOR_STATE_RECEIVED
    assert d["history"] == []


# ---------------------------------------------------------------------------
# SPEC §9: every transition exercised at least once (smoke coverage)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "events",
    [
        (OrchestratorEvent.PHI_REDACTED,),
        (OrchestratorEvent.INBOUND_INVALID,),
        (
            OrchestratorEvent.PHI_REDACTED,
            OrchestratorEvent.PLAN_GENERATED,
        ),
        (
            OrchestratorEvent.PHI_REDACTED,
            OrchestratorEvent.PLAN_FAILED,
            OrchestratorEvent.PLAN_GENERATED,
        ),
        (
            OrchestratorEvent.PHI_REDACTED,
            OrchestratorEvent.PLANNING_TIMEOUT,
        ),
        (
            OrchestratorEvent.PHI_REDACTED,
            OrchestratorEvent.PLAN_GENERATED,
            OrchestratorEvent.ALL_EXPERTS_RETURNED,
        ),
        (
            OrchestratorEvent.PHI_REDACTED,
            OrchestratorEvent.PLAN_GENERATED,
            OrchestratorEvent.CRITICAL_EXPERT_FAILED,
        ),
        (
            OrchestratorEvent.PHI_REDACTED,
            OrchestratorEvent.PLAN_GENERATED,
            OrchestratorEvent.DELEGATING_TIMEOUT,
        ),
        (
            OrchestratorEvent.PHI_REDACTED,
            OrchestratorEvent.PLAN_GENERATED,
            OrchestratorEvent.ALL_EXPERTS_RETURNED,
            OrchestratorEvent.AGGREGATED,
        ),
        (
            OrchestratorEvent.PHI_REDACTED,
            OrchestratorEvent.PLAN_GENERATED,
            OrchestratorEvent.ALL_EXPERTS_RETURNED,
            OrchestratorEvent.AGGREGATION_FAILED,
        ),
    ],
)
def test_all_ten_transitions_exercised(events):
    sm = OrchestratorStateMachine()
    for ev in events:
        sm = sm.transition(ev)
    assert len(sm.state_history) == len(events)
    # paths that end in completed/failed must be terminal; mid-pipeline paths not
    terminal_ending = (
        events[-1]
        in (
            OrchestratorEvent.INBOUND_INVALID,
            OrchestratorEvent.PLANNING_TIMEOUT,
            OrchestratorEvent.CRITICAL_EXPERT_FAILED,
            OrchestratorEvent.DELEGATING_TIMEOUT,
            OrchestratorEvent.AGGREGATED,
            OrchestratorEvent.AGGREGATION_FAILED,
        )
    )
    if terminal_ending:
        assert sm.is_terminal
    else:
        assert not sm.is_terminal