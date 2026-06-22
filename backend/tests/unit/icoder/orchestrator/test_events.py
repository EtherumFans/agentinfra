"""T1 — OrchestratorEvent enum (SPEC §4.4)."""

from __future__ import annotations

from app.icoder.agent_runtime.orchestrator.events import OrchestratorEvent


def test_event_has_eleven_members():
    assert len(list(OrchestratorEvent)) == 11


def test_event_string_values_match_spec():
    assert OrchestratorEvent.INBOUND_REQUEST_VALIDATED.value == "inbound_request_validated"
    assert OrchestratorEvent.PHI_REDACTED.value == "phi_redacted"
    assert OrchestratorEvent.INBOUND_INVALID.value == "inbound_invalid"
    assert OrchestratorEvent.PLAN_GENERATED.value == "plan_generated"
    assert OrchestratorEvent.PLAN_FAILED.value == "plan_failed"
    assert OrchestratorEvent.PLANNING_TIMEOUT.value == "planning_timeout"
    assert OrchestratorEvent.ALL_EXPERTS_RETURNED.value == "all_experts_returned"
    assert OrchestratorEvent.CRITICAL_EXPERT_FAILED.value == "critical_expert_failed"
    assert OrchestratorEvent.DELEGATING_TIMEOUT.value == "delegating_timeout"
    assert OrchestratorEvent.AGGREGATED.value == "aggregated"
    assert OrchestratorEvent.AGGREGATION_FAILED.value == "aggregation_failed"


def test_event_is_str_subclass():
    assert isinstance(OrchestratorEvent.PLAN_GENERATED, str)
    assert OrchestratorEvent.PLAN_GENERATED == "plan_generated"


def test_event_distinct_names_no_collision():
    values = [e.value for e in OrchestratorEvent]
    assert len(values) == len(set(values)), "duplicate event string values"


def test_event_by_value_lookup_works():
    assert OrchestratorEvent("plan_generated") is OrchestratorEvent.PLAN_GENERATED
    assert OrchestratorEvent("phi_redacted") is OrchestratorEvent.PHI_REDACTED