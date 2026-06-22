"""Orchestrator event names (SPEC §4.4)."""

from __future__ import annotations

from enum import Enum


class OrchestratorEvent(str, Enum):
    INBOUND_REQUEST_VALIDATED = "inbound_request_validated"
    PHI_REDACTED = "phi_redacted"
    INBOUND_INVALID = "inbound_invalid"

    PLAN_GENERATED = "plan_generated"
    PLAN_FAILED = "plan_failed"
    PLANNING_TIMEOUT = "planning_timeout"

    ALL_EXPERTS_RETURNED = "all_experts_returned"
    CRITICAL_EXPERT_FAILED = "critical_expert_failed"
    DELEGATING_TIMEOUT = "delegating_timeout"

    AGGREGATED = "aggregated"
    AGGREGATION_FAILED = "aggregation_failed"