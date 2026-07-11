"""Unit tests for CDI Query Lifecycle Service (Phase 5 Track D Gate 5).

Tests:
    - State machine: allowed + disallowed transitions
    - NLQ gate integration: DRAFT → PENDING_CDI_REVIEW requires PASS verdict
    - SLA computation: routine=72h, urgent=24h
    - Audit event emission per transition
    - Terminal states cannot transition
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.cdi_query_lifecycle import (
    NlqGateBlockError,
    attempt_transition,
    compute_sla_due_at,
    gate_draft_to_pending_review,
    validate_transition,
)


# ---------------------------------------------------------------------------
# Compliant + non-compliant query fixtures
# ---------------------------------------------------------------------------


COMPLIANT_QUERY = {
    "query_text": "入院记录诊断为'肺炎', 痰培养为'肺炎链球菌'. 请根据您的临床判断回答:",
    "response_options": [
        "A. 肺炎病原体为肺炎链球菌 (J13)",
        "B. 其他病原体",
        "C. 痰培养为定植菌",
        "D. 无法确定",
    ],
    "evidence_quote": "诊断: 肺炎",
    "topic": "肺炎病原体",
}

LEADING_QUERY = {
    "query_text": "是否为肺炎链球菌性肺炎?",
    "response_options": ["A. 是", "B. 否"],
    "evidence_quote": "肺炎",
    "topic": "病原体",
}


# ---------------------------------------------------------------------------
# validate_transition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_state,to_state,expected_allowed",
    [
        ("DRAFT", "PENDING_CDI_REVIEW", True),
        ("DRAFT", "APPROVED", False),  # must go through CDI review first
        ("DRAFT", "CANCELLED", True),
        ("PENDING_CDI_REVIEW", "APPROVED", True),
        ("PENDING_CDI_REVIEW", "DRAFT", True),  # send back for revision
        ("PENDING_CDI_REVIEW", "SENT_TO_CLINICIAN", False),
        ("APPROVED", "SENT_TO_CLINICIAN", True),
        ("APPROVED", "DRAFT", False),  # cannot reverse to draft
        ("SENT_TO_CLINICIAN", "VIEWED", True),
        ("SENT_TO_CLINICIAN", "RESPONDED", False),  # must be viewed first
        ("VIEWED", "RESPONDED", True),
        ("RESPONDED", "DOCUMENTATION_UPDATED", True),
        ("DOCUMENTATION_UPDATED", "REVALIDATED", True),
        ("REVALIDATED", "CLOSED", True),
        ("REVALIDATED", "DOCUMENTATION_UPDATED", True),  # can re-document
        ("CLOSED", "REVALIDATED", False),  # terminal
        ("CANCELLED", "DRAFT", False),  # terminal
        ("EXPIRED", "DRAFT", False),  # terminal
    ],
)
def test_state_machine_transition_matrix(
    from_state: str, to_state: str, expected_allowed: bool
) -> None:
    allowed, _ = validate_transition(from_state, to_state)  # type: ignore[arg-type]
    assert allowed is expected_allowed


def test_validate_transition_returns_human_readable_reason() -> None:
    _, reason = validate_transition("DRAFT", "SENT_TO_CLINICIAN")
    assert "DRAFT" in reason and "SENT_TO_CLINICIAN" in reason
    assert "PENDING_CDI_REVIEW" in reason  # suggests correct path


# ---------------------------------------------------------------------------
# gate_draft_to_pending_review (NLQ gate)
# ---------------------------------------------------------------------------


def test_gate_draft_to_pending_review_passes_compliant_query() -> None:
    result = gate_draft_to_pending_review(**COMPLIANT_QUERY)
    assert result.verdict == "PASS"
    assert result.rules_passed == 9


def test_gate_draft_to_pending_review_blocks_leading_query() -> None:
    result = gate_draft_to_pending_review(**LEADING_QUERY)
    assert result.verdict == "BLOCK"
    failed_ids = [r.rule_id for r in result.rules_failed]
    assert "NLQ-001" in failed_ids  # yes/no opening
    assert "NLQ-004" in failed_ids  # only 2 options
    assert "NLQ-005" in failed_ids  # no escape hatch


# ---------------------------------------------------------------------------
# attempt_transition (full integration)
# ---------------------------------------------------------------------------


def test_attempt_transition_draft_to_pending_with_compliant_query_accepted() -> None:
    result = attempt_transition(
        from_state="DRAFT",
        to_state="PENDING_CDI_REVIEW",
        **COMPLIANT_QUERY,
    )
    assert result.accepted is True
    assert result.nlq_gate_result is not None
    assert result.nlq_gate_result.verdict == "PASS"
    # 2 audit events: nlq_gate.passed + transition
    events = [e["event"] for e in result.audit_events]
    assert "query.nlq_gate.passed" in events
    assert "query.transition" in events


def test_attempt_transition_draft_to_pending_with_leading_query_rejected() -> None:
    result = attempt_transition(
        from_state="DRAFT",
        to_state="PENDING_CDI_REVIEW",
        **LEADING_QUERY,
    )
    assert result.accepted is False
    assert result.nlq_gate_result is not None
    assert result.nlq_gate_result.verdict == "BLOCK"
    events = [e["event"] for e in result.audit_events]
    assert "query.nlq_gate.blocked" in events
    # blocked query does NOT emit query.transition event
    assert "query.transition" not in events


def test_attempt_transition_to_approved_sets_sla() -> None:
    fixed_now = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)
    result = attempt_transition(
        from_state="PENDING_CDI_REVIEW",
        to_state="APPROVED",
        priority="routine",
        now=fixed_now,
    )
    assert result.accepted is True
    assert result.sla_due_at is not None
    expected = fixed_now + timedelta(hours=72)
    assert result.sla_due_at == expected


def test_attempt_transition_to_approved_urgent_priority_sla_24h() -> None:
    fixed_now = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)
    result = attempt_transition(
        from_state="PENDING_CDI_REVIEW",
        to_state="APPROVED",
        priority="urgent",
        now=fixed_now,
    )
    assert result.accepted is True
    expected = fixed_now + timedelta(hours=24)
    assert result.sla_due_at == expected


def test_attempt_transition_illegal_path_rejected() -> None:
    result = attempt_transition(
        from_state="DRAFT",
        to_state="SENT_TO_CLINICIAN",  # illegal: must go through PENDING_CDI_REVIEW + APPROVED
    )
    assert result.accepted is False
    assert "not allowed" in result.reason.lower() or "cannot" in result.reason.lower()
    # No NLQ gate run because transition is structurally illegal
    assert result.nlq_gate_result is None


def test_attempt_transition_emits_transition_audit_event() -> None:
    result = attempt_transition(
        from_state="APPROVED",
        to_state="SENT_TO_CLINICIAN",
    )
    assert result.accepted is True
    transition_events = [e for e in result.audit_events if e["event"] == "query.transition"]
    assert len(transition_events) == 1
    assert transition_events[0]["from"] == "APPROVED"
    assert transition_events[0]["to"] == "SENT_TO_CLINICIAN"
    assert "ts" in transition_events[0]


# ---------------------------------------------------------------------------
# Terminal state protection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("terminal_state", ["CLOSED", "CANCELLED", "EXPIRED"])
def test_terminal_states_cannot_transition_out(terminal_state: str) -> None:
    for target in ["DRAFT", "PENDING_CDI_REVIEW", "APPROVED", "REVALIDATED"]:
        allowed, reason = validate_transition(terminal_state, target)  # type: ignore[arg-type]
        assert allowed is False
        assert "terminal" in reason.lower()


# ---------------------------------------------------------------------------
# SLA computation
# ---------------------------------------------------------------------------


def test_compute_sla_due_at_routine_72h() -> None:
    approved = datetime(2026, 7, 11, 9, 0, 0, tzinfo=timezone.utc)
    due = compute_sla_due_at(approved, "routine")
    assert due == datetime(2026, 7, 14, 9, 0, 0, tzinfo=timezone.utc)  # +3 days


def test_compute_sla_due_at_urgent_24h() -> None:
    approved = datetime(2026, 7, 11, 9, 0, 0, tzinfo=timezone.utc)
    due = compute_sla_due_at(approved, "urgent")
    assert due == datetime(2026, 7, 12, 9, 0, 0, tzinfo=timezone.utc)


def test_compute_sla_due_at_unknown_priority_defaults_routine() -> None:
    approved = datetime(2026, 7, 11, 9, 0, 0, tzinfo=timezone.utc)
    # type: ignore — testing runtime safety
    due = compute_sla_due_at(approved, "unknown_priority")  # type: ignore[arg-type]
    assert due == approved + timedelta(hours=72)


# ---------------------------------------------------------------------------
# Exceptions (exported but only raised manually; service returns result)
# ---------------------------------------------------------------------------


def test_exported_exceptions_are_value_error_subclasses() -> None:
    """Both exception classes inherit from ValueError so callers can catch
    with a single except clause if desired."""

    assert issubclass(NlqGateBlockError, ValueError)
    from app.services.cdi_query_lifecycle import IllegalTransitionError

    assert issubclass(IllegalTransitionError, ValueError)


# ---------------------------------------------------------------------------
# Full lifecycle happy path (integration)
# ---------------------------------------------------------------------------


def test_full_compliant_lifecycle_draft_to_closed() -> None:
    """Walk one query through the entire happy-path lifecycle."""

    base_time = datetime(2026, 7, 11, 9, 0, 0, tzinfo=timezone.utc)
    current_state = "DRAFT"
    visited = [current_state]
    sla_due_at = None

    # 1. DRAFT → PENDING_CDI_REVIEW (NLQ gate must pass)
    r1 = attempt_transition(
        from_state="DRAFT",
        to_state="PENDING_CDI_REVIEW",
        now=base_time,
        **COMPLIANT_QUERY,
    )
    assert r1.accepted
    current_state = "PENDING_CDI_REVIEW"
    visited.append(current_state)

    # 2. PENDING_CDI_REVIEW → APPROVED (CDI specialist approves, SLA set)
    r2 = attempt_transition(
        from_state="PENDING_CDI_REVIEW",
        to_state="APPROVED",
        priority="routine",
        now=base_time + timedelta(hours=1),
    )
    assert r2.accepted
    assert r2.sla_due_at is not None
    sla_due_at = r2.sla_due_at
    current_state = "APPROVED"
    visited.append(current_state)

    # 3. APPROVED → SENT_TO_CLINICIAN
    r3 = attempt_transition(
        from_state="APPROVED",
        to_state="SENT_TO_CLINICIAN",
        now=base_time + timedelta(hours=2),
    )
    assert r3.accepted
    current_state = "SENT_TO_CLINICIAN"
    visited.append(current_state)

    # 4. SENT_TO_CLINICIAN → VIEWED
    r4 = attempt_transition(
        from_state="SENT_TO_CLINICIAN",
        to_state="VIEWED",
        now=base_time + timedelta(hours=4),
    )
    assert r4.accepted
    current_state = "VIEWED"
    visited.append(current_state)

    # 5. VIEWED → RESPONDED
    r5 = attempt_transition(
        from_state="VIEWED",
        to_state="RESPONDED",
        now=base_time + timedelta(hours=8),
    )
    assert r5.accepted
    current_state = "RESPONDED"
    visited.append(current_state)

    # 6. RESPONDED → DOCUMENTATION_UPDATED
    r6 = attempt_transition(
        from_state="RESPONDED",
        to_state="DOCUMENTATION_UPDATED",
        now=base_time + timedelta(hours=12),
    )
    assert r6.accepted
    current_state = "DOCUMENTATION_UPDATED"
    visited.append(current_state)

    # 7. DOCUMENTATION_UPDATED → REVALIDATED
    r7 = attempt_transition(
        from_state="DOCUMENTATION_UPDATED",
        to_state="REVALIDATED",
        now=base_time + timedelta(hours=14),
    )
    assert r7.accepted
    current_state = "REVALIDATED"
    visited.append(current_state)

    # 8. REVALIDATED → CLOSED
    r8 = attempt_transition(
        from_state="REVALIDATED",
        to_state="CLOSED",
        now=base_time + timedelta(hours=16),
    )
    assert r8.accepted
    current_state = "CLOSED"
    visited.append(current_state)

    assert visited == [
        "DRAFT",
        "PENDING_CDI_REVIEW",
        "APPROVED",
        "SENT_TO_CLINICIAN",
        "VIEWED",
        "RESPONDED",
        "DOCUMENTATION_UPDATED",
        "REVALIDATED",
        "CLOSED",
    ]
    # SLA was set and respected (closed before due)
    assert sla_due_at is not None
    assert base_time + timedelta(hours=16) < sla_due_at
