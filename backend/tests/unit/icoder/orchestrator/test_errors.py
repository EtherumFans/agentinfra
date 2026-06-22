"""T1 — OrchestratorError + OrchestratorStateError (SPEC §7)."""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.orchestrator.errors import (
    OrchestratorError,
    OrchestratorStateError,
)


# ---------------------------------------------------------------------------
# OrchestratorError (runtime failure value)
# ---------------------------------------------------------------------------


def test_error_default_code_and_status():
    e = OrchestratorError(message="boom")
    assert e.code == "ORCHESTRATION_FAILED"
    assert e.stage == "unknown"
    assert e.retryable is False
    assert e.http_status == 500


def test_error_from_code_maps_known_a2a_codes():
    e = OrchestratorError.from_code("INVALID_REQUEST", "bad json")
    assert e.code == "invalid_request"
    assert e.http_status == 400
    assert e.stage == "unknown"

    e = OrchestratorError.from_code("PHI_REDACTION_FAILED", "redactor crash")
    assert e.code == "phi_redaction_failed"
    assert e.http_status == 500

    e = OrchestratorError.from_code("PLANNING_FAILED", "llm 500")
    assert e.code == "planning_failed"
    assert e.http_status == 500

    e = OrchestratorError.from_code("EXPERT_FAILED", "expert oom")
    assert e.code == "expert_failed"
    assert e.http_status == 502

    e = OrchestratorError.from_code("DELEGATION_TIMEOUT", "slow expert")
    assert e.code == "delegation_timeout"
    assert e.http_status == 504

    e = OrchestratorError.from_code("AGGREGATION_FAILED", "merge crash")
    assert e.code == "aggregation_failed"
    assert e.http_status == 500

    e = OrchestratorError.from_code("ORCHESTRATION_FAILED", "misc")
    assert e.code == "orchestration_failed"
    assert e.http_status == 500


def test_error_from_code_unknown_falls_back_to_orchestration_failed():
    e = OrchestratorError.from_code("WHATEVER_NEW_THING", "x")
    assert e.code == "orchestration_failed"
    assert e.http_status == 500


def test_error_from_code_propagates_stage_and_retryable():
    e = OrchestratorError.from_code(
        "PLANNING_FAILED",
        "llm timeout",
        stage="planning",
        retryable=True,
    )
    assert e.stage == "planning"
    assert e.retryable is True


def test_error_is_exception_subclass():
    e = OrchestratorError(message="x")
    assert isinstance(e, Exception)
    with pytest.raises(OrchestratorError):
        raise OrchestratorError(message="x")


def test_error_str_includes_code_stage_message():
    e = OrchestratorError(message="bad", code="expert_failed", stage="delegating")
    s = str(e)
    assert "expert_failed" in s
    assert "delegating" in s
    assert "bad" in s


def test_error_http_status_override_is_respected():
    # from_code fills http_status from A2A table, but the field is just an int
    # — caller may override by passing http_status explicitly:
    e = OrchestratorError(
        message="x",
        code="EXPERT_FAILED",
        http_status=503,  # would normally be 502 from table
    )
    assert e.http_status == 503


# ---------------------------------------------------------------------------
# OrchestratorStateError (programmer error — bad transition)
# ---------------------------------------------------------------------------


def test_state_error_is_exception_subclass():
    assert issubclass(OrchestratorStateError, Exception)


def test_state_error_carries_state_and_event():
    e = OrchestratorStateError(
        "no transition",
        current_state="completed",
        event="plan_generated",
    )
    assert e.current_state == "completed"
    assert e.event == "plan_generated"
    assert "no transition" in str(e)


def test_state_error_state_and_event_are_optional():
    e = OrchestratorStateError("oops")
    assert e.current_state is None
    assert e.event is None


def test_state_error_distinct_from_orchestrator_error():
    # SPEC: state error is a *programmer* error, runtime error is a *value*.
    e1 = OrchestratorError(message="x")
    e2 = OrchestratorStateError("x")
    assert not isinstance(e2, OrchestratorError)
    assert not isinstance(e1, OrchestratorStateError)


def test_a2a_code_table_covers_all_spec_codes():
    expected = {
        "INVALID_REQUEST",
        "PHI_REDACTION_FAILED",
        "PLANNING_FAILED",
        "EXPERT_FAILED",
        "DELEGATION_TIMEOUT",
        "AGGREGATION_FAILED",
        "ORCHESTRATION_FAILED",
    }
    assert set(OrchestratorError.A2A_CODES.keys()) == expected


def test_a2a_code_table_status_codes_are_well_formed():
    for code, (a2a_name, http) in OrchestratorError.A2A_CODES.items():
        assert isinstance(a2a_name, str) and a2a_name
        assert 400 <= http < 600, f"{code} → bad http {http}"