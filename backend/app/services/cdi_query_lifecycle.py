"""CDI Provider Query Lifecycle Service (Phase 5 Track D Gate 5).

This service drives Provider Query state transitions in the DB, enforcing:

  1. Non-leading Query gate (NLQ-001..009) runs on every DRAFT query
     before it can transition to PENDING_CDI_REVIEW.
  2. State machine invariants (e.g. SENT_TO_CLINICIAN cannot directly
     transition to CLOSED; must pass through RESPONDED or CANCELLED).
  3. SLA computation (routine=72h, urgent=24h) on APPROVED transition.
  4. Audit event emission for every state change.

Pure logic — no FastAPI/HTTP layer here. Gate 9 wires this service to
the REST API. Gate 6 wires it to the CDI Orchestrator's
query_generation stage.

PDF §7 Gate 5 reference:
    reports/phase5_track_d/GATE5_NLQ_GATE_WIRING_REPORT.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.icoder.agent_runtime.cdi import (
    NLQGateResult,
    ProviderQueryForGate,
    evaluate_nlq,
)


# ---------------------------------------------------------------------------
# Lifecycle states (mirrors agent_pack.json clarification_lifecycle)
# ---------------------------------------------------------------------------


LifecycleState = Literal[
    "DRAFT",
    "PENDING_CDI_REVIEW",
    "APPROVED",
    "SENT_TO_CLINICIAN",
    "VIEWED",
    "RESPONDED",
    "DOCUMENTATION_UPDATED",
    "REVALIDATED",
    "CLOSED",
    "CANCELLED",
    "ESCALATED",
    "EXPIRED",
]


_TERMINAL_STATES: frozenset[LifecycleState] = frozenset(
    {"CLOSED", "CANCELLED", "EXPIRED"}
)


# ---------------------------------------------------------------------------
# Allowed transitions (PDF §7 + Gate 2 audit §6)
# ---------------------------------------------------------------------------


_ALLOWED_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    "DRAFT": frozenset({"PENDING_CDI_REVIEW", "CANCELLED"}),
    "PENDING_CDI_REVIEW": frozenset({"APPROVED", "DRAFT", "CANCELLED", "ESCALATED"}),
    "APPROVED": frozenset({"SENT_TO_CLINICIAN", "CANCELLED"}),
    "SENT_TO_CLINICIAN": frozenset({"VIEWED", "CANCELLED", "EXPIRED"}),
    "VIEWED": frozenset({"RESPONDED", "EXPIRED", "ESCALATED"}),
    "RESPONDED": frozenset({"DOCUMENTATION_UPDATED", "ESCALATED", "EXPIRED"}),
    "DOCUMENTATION_UPDATED": frozenset({"REVALIDATED", "ESCALATED"}),
    "REVALIDATED": frozenset({"CLOSED", "DOCUMENTATION_UPDATED"}),
    "CLOSED": frozenset(),  # terminal
    "CANCELLED": frozenset(),  # terminal
    "ESCALATED": frozenset({"PENDING_CDI_REVIEW", "CANCELLED", "EXPIRED"}),
    "EXPIRED": frozenset(),  # terminal
}


# ---------------------------------------------------------------------------
# SLA policy
# ---------------------------------------------------------------------------


_SLA_HOURS: dict[str, int] = {
    "routine": 72,
    "urgent": 24,
}


def compute_sla_due_at(
    approved_at: datetime, priority: Literal["routine", "urgent"] = "routine"
) -> datetime:
    """Compute SLA due_at timestamp from approval moment."""

    hours = _SLA_HOURS.get(priority, _SLA_HOURS["routine"])
    return approved_at + timedelta(hours=hours)


# ---------------------------------------------------------------------------
# Transition result
# ---------------------------------------------------------------------------


@dataclass
class TransitionResult:
    """Outcome of a single state transition attempt."""

    from_state: LifecycleState
    to_state: LifecycleState
    accepted: bool
    reason: str = ""
    nlq_gate_result: NLQGateResult | None = None
    audit_events: list[dict] = field(default_factory=list)
    sla_due_at: datetime | None = None


class IllegalTransitionError(ValueError):
    """Raised when a transition violates the state machine."""


class NlqGateBlockError(ValueError):
    """Raised when DRAFT → PENDING_CDI_REVIEW is attempted on a query that
    fails the Non-leading gate."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def validate_transition(
    from_state: LifecycleState, to_state: LifecycleState
) -> tuple[bool, str]:
    """Return ``(allowed, reason)``. Does NOT mutate state."""

    if from_state in _TERMINAL_STATES:
        return False, f"cannot transition from terminal state {from_state}"
    allowed = _ALLOWED_TRANSITIONS.get(from_state, frozenset())
    if to_state not in allowed:
        return False, (
            f"transition {from_state} → {to_state} not allowed; "
            f"allowed targets from {from_state}: {sorted(allowed)}"
        )
    return True, ""


def gate_draft_to_pending_review(
    query_text: str,
    response_options: list[str],
    evidence_quote: str,
    topic: str = "",
) -> NLQGateResult:
    """Run the Non-leading Query gate on a DRAFT query.

    The orchestrator MUST call this before transitioning to
    PENDING_CDI_REVIEW. If verdict is BLOCK, the query stays in DRAFT
    and the block_reasons are stored on the row.

    Returns the gate result for the caller to persist + audit.
    """

    gate_input = ProviderQueryForGate(
        query_text=query_text,
        response_options=list(response_options),
        topic=topic,
        evidence_quote=evidence_quote,
    )
    return evaluate_nlq(gate_input)


def attempt_transition(
    from_state: LifecycleState,
    to_state: LifecycleState,
    *,
    query_text: str = "",
    response_options: list[str] | None = None,
    evidence_quote: str = "",
    topic: str = "",
    priority: Literal["routine", "urgent"] = "routine",
    now: datetime | None = None,
) -> TransitionResult:
    """Attempt a state transition with all policy checks.

    For DRAFT → PENDING_CDI_REVIEW: runs NLQ gate. BLOCK → transition rejected.
    For APPROVED transition: computes SLA due_at.
    For all transitions: emits audit_event.

    Returns TransitionResult. Caller persists state + audit_events.
    """

    if now is None:
        now = datetime.now(timezone.utc)

    audit_events: list[dict] = []

    # 1. State machine check
    allowed, reason = validate_transition(from_state, to_state)
    if not allowed:
        return TransitionResult(
            from_state=from_state,
            to_state=to_state,
            accepted=False,
            reason=reason,
            audit_events=audit_events,
        )

    nlq_result: NLQGateResult | None = None

    # 2. NLQ gate check on DRAFT → PENDING_CDI_REVIEW
    if from_state == "DRAFT" and to_state == "PENDING_CDI_REVIEW":
        nlq_result = gate_draft_to_pending_review(
            query_text=query_text,
            response_options=response_options or [],
            evidence_quote=evidence_quote,
            topic=topic,
        )
        if nlq_result.verdict == "BLOCK":
            audit_events.append({
                "event": "query.nlq_gate.blocked",
                "from": from_state,
                "to": to_state,
                "reason": "NLQ gate BLOCK verdict",
                "rules_failed": [r.rule_id for r in nlq_result.rules_failed],
                "ts": now.isoformat(),
            })
            return TransitionResult(
                from_state=from_state,
                to_state=to_state,
                accepted=False,
                reason=f"NLQ gate BLOCK: {len(nlq_result.rules_failed)} rules failed",
                nlq_gate_result=nlq_result,
                audit_events=audit_events,
            )
        audit_events.append({
            "event": "query.nlq_gate.passed",
            "from": from_state,
            "to": to_state,
            "rules_evaluated": nlq_result.rules_evaluated,
            "rules_passed": nlq_result.rules_passed,
            "ts": now.isoformat(),
        })

    # 3. SLA computation on APPROVED transition
    sla_due_at: datetime | None = None
    if to_state == "APPROVED":
        sla_due_at = compute_sla_due_at(now, priority)
        audit_events.append({
            "event": "query.sla.set",
            "from": from_state,
            "to": to_state,
            "priority": priority,
            "sla_due_at": sla_due_at.isoformat(),
            "ts": now.isoformat(),
        })

    # 4. Generic transition audit event
    audit_events.append({
        "event": "query.transition",
        "from": from_state,
        "to": to_state,
        "ts": now.isoformat(),
    })

    return TransitionResult(
        from_state=from_state,
        to_state=to_state,
        accepted=True,
        nlq_gate_result=nlq_result,
        audit_events=audit_events,
        sla_due_at=sla_due_at,
    )


__all__ = [
    "LifecycleState",
    "TransitionResult",
    "IllegalTransitionError",
    "NlqGateBlockError",
    "validate_transition",
    "gate_draft_to_pending_review",
    "attempt_transition",
    "compute_sla_due_at",
]
