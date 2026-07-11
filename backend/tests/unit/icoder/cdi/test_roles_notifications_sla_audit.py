"""Unit tests for CDI Roles + Notifications + SLA + Audit Dashboard (Gate 8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.cdi_roles_notifications import (
    AuditDashboardSnapshot,
    NotificationPayload,
    NotificationSubscription,
    SLABreachRecord,
    build_audit_dashboard,
    can_drive_transition,
    find_sla_breaches,
    get_role_permissions,
    platform_role_to_cdi_role,
    select_subscriptions_for_event,
    should_dispatch,
)


# ---------------------------------------------------------------------------
# Role mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "platform_role,expected_cdi",
    [
        ("admin", "admin"),
        ("qc", "cdi_specialist"),
        ("clinician", "clinician"),
        ("insurance", "auditor"),
        ("dept_head", "auditor"),
        ("coder", "auditor"),
        ("it", "auditor"),
        ("unknown_role", "auditor"),  # default = read-only
    ],
)
def test_platform_role_to_cdi_role(platform_role: str, expected_cdi: str) -> None:
    assert platform_role_to_cdi_role(platform_role) == expected_cdi


# ---------------------------------------------------------------------------
# RBAC: who can drive which transitions
# ---------------------------------------------------------------------------


def test_cdi_specialist_can_approve_query() -> None:
    r = can_drive_transition("cdi_specialist", "PENDING_CDI_REVIEW", "APPROVED")
    assert r.allowed is True
    assert r.role == "cdi_specialist"


def test_clinician_cannot_approve_query() -> None:
    """Only CDI specialist can approve — clinician is the queried party."""

    r = can_drive_transition("clinician", "PENDING_CDI_REVIEW", "APPROVED")
    assert r.allowed is False
    assert "clinician" in r.reason


def test_clinician_can_respond() -> None:
    r = can_drive_transition("clinician", "VIEWED", "RESPONDED")
    assert r.allowed is True


def test_cdi_specialist_cannot_respond() -> None:
    """CDI specialist cannot submit a clinician response."""

    r = can_drive_transition("cdi_specialist", "VIEWED", "RESPONDED")
    assert r.allowed is False


def test_auditor_is_read_only() -> None:
    """Auditor can drive zero transitions."""

    for from_state in ["DRAFT", "PENDING_CDI_REVIEW", "APPROVED", "RESPONDED"]:
        for to_state in ["APPROVED", "SENT_TO_CLINICIAN", "CLOSED"]:
            r = can_drive_transition("auditor", from_state, to_state)
            assert r.allowed is False, (
                f"auditor should not drive {from_state} -> {to_state}"
            )


def test_admin_can_drive_anything() -> None:
    r = can_drive_transition("admin", "PENDING_CDI_REVIEW", "APPROVED")
    assert r.allowed is True


def test_cdi_specialist_can_send_to_clinician() -> None:
    r = can_drive_transition("cdi_specialist", "APPROVED", "SENT_TO_CLINICIAN")
    assert r.allowed is True


def test_cdi_specialist_can_close_after_revalidation() -> None:
    r = can_drive_transition("cdi_specialist", "REVALIDATED", "CLOSED")
    assert r.allowed is True


def test_clinician_can_escalate_escape_hatch() -> None:
    """Clinician selecting 'unable to determine' escalates."""

    r = can_drive_transition("clinician", "VIEWED", "ESCALATED")
    assert r.allowed is True


def test_cdi_specialist_cannot_escalate_viewed() -> None:
    """Escalation is the clinician's call, not specialist's."""

    r = can_drive_transition("cdi_specialist", "VIEWED", "ESCALATED")
    assert r.allowed is False


def test_unknown_role_rejected_cleanly() -> None:
    r = can_drive_transition("intern", "DRAFT", "PENDING_CDI_REVIEW")
    assert r.allowed is False
    assert "unknown role" in r.reason


def test_get_role_permissions_returns_set() -> None:
    perms = get_role_permissions("cdi_specialist")
    assert isinstance(perms, set)
    assert ("PENDING_CDI_REVIEW", "APPROVED") in perms
    assert len(perms) >= 5


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def _make_sub(
    sub_id: str = "s1",
    role: str = "cdi_specialist",
    events: list[str] | None = None,
    channel: str = "in_app",
    target_url: str = "",
) -> NotificationSubscription:
    return NotificationSubscription(
        subscription_id=sub_id,
        user_role=role,  # type: ignore[arg-type]
        events=events or ["QUERY_RESPONDED"],
        channel=channel,  # type: ignore[arg-type]
        target_url=target_url,
    )


def _make_payload(
    event: str = "QUERY_RESPONDED",
    query_id: str = "q1",
) -> NotificationPayload:
    return NotificationPayload(
        event=event,  # type: ignore[arg-type]
        query_id=query_id,
        case_id="c1",
        timestamp=datetime.now(timezone.utc),
    )


def test_should_dispatch_matching_event() -> None:
    sub = _make_sub(events=["QUERY_RESPONDED"])
    payload = _make_payload("QUERY_RESPONDED")
    assert should_dispatch(sub, payload) is True


def test_should_dispatch_non_matching_event() -> None:
    sub = _make_sub(events=["QUERY_CLOSED"])
    payload = _make_payload("QUERY_RESPONDED")
    assert should_dispatch(sub, payload) is False


def test_should_dispatch_webhook_requires_url() -> None:
    sub = _make_sub(channel="webhook", target_url="")
    payload = _make_payload()
    assert should_dispatch(sub, payload) is False


def test_should_dispatch_webhook_with_url() -> None:
    sub = _make_sub(channel="webhook", target_url="https://emr.example.com/cdi")
    payload = _make_payload()
    assert should_dispatch(sub, payload) is True


def test_select_subscriptions_filters_correctly() -> None:
    subs = [
        _make_sub("s1", events=["QUERY_RESPONDED"]),
        _make_sub("s2", events=["QUERY_CLOSED"]),
        _make_sub("s3", events=["QUERY_RESPONDED", "QUERY_ESCALATED"]),
    ]
    payload = _make_payload("QUERY_RESPONDED")
    selected = select_subscriptions_for_event(subs, payload)
    sub_ids = {s.subscription_id for s in selected}
    assert sub_ids == {"s1", "s3"}


# ---------------------------------------------------------------------------
# SLA breaches
# ---------------------------------------------------------------------------


def test_find_sla_breaches_empty() -> None:
    breaches = find_sla_breaches([])
    assert breaches == []


def test_find_sla_breaches_ignores_closed() -> None:
    """Closed queries are not subject to SLA tracking."""

    closed_query = {
        "query_id": "q1",
        "case_id": "c1",
        "priority": "routine",
        "approved_at": datetime.now(timezone.utc) - timedelta(hours=100),
        "lifecycle_state": "CLOSED",
    }
    breaches = find_sla_breaches([closed_query])
    assert breaches == []


def test_find_sla_breaches_critical() -> None:
    """Query past SLA due_at = critical breach."""

    approved_long_ago = datetime.now(timezone.utc) - timedelta(hours=100)
    query = {
        "query_id": "q1",
        "case_id": "c1",
        "priority": "routine",  # 72h SLA
        "approved_at": approved_long_ago,
        "lifecycle_state": "SENT_TO_CLINICIAN",
    }
    breaches = find_sla_breaches([query])
    assert len(breaches) == 1
    assert breaches[0].severity == "critical"
    assert breaches[0].hours_overdue > 0


def test_find_sla_breaches_warning_at_80pct() -> None:
    """Query past 80% of SLA window but not yet due = warning."""

    # routine SLA = 72h; 80% = 57.6h
    approved = datetime.now(timezone.utc) - timedelta(hours=60)
    query = {
        "query_id": "q1",
        "case_id": "c1",
        "priority": "routine",
        "approved_at": approved,
        "lifecycle_state": "SENT_TO_CLINICIAN",
    }
    breaches = find_sla_breaches([query])
    assert len(breaches) == 1
    assert breaches[0].severity == "warning"
    assert breaches[0].hours_overdue == 0  # not yet overdue


def test_find_sla_breaches_urgent_priority() -> None:
    """Urgent queries have 24h SLA, breach sooner."""

    approved = datetime.now(timezone.utc) - timedelta(hours=30)
    query = {
        "query_id": "q1",
        "case_id": "c1",
        "priority": "urgent",
        "approved_at": approved,
        "lifecycle_state": "VIEWED",
    }
    breaches = find_sla_breaches([query])
    assert len(breaches) == 1
    assert breaches[0].priority == "urgent"
    assert breaches[0].severity == "critical"


def test_find_sla_breaches_sorts_by_overdue_desc() -> None:
    """Most overdue first."""

    now = datetime.now(timezone.utc)
    queries = [
        {
            "query_id": "q1",
            "case_id": "c1",
            "priority": "routine",
            "approved_at": now - timedelta(hours=80),  # 8h overdue
            "lifecycle_state": "SENT_TO_CLINICIAN",
        },
        {
            "query_id": "q2",
            "case_id": "c1",
            "priority": "routine",
            "approved_at": now - timedelta(hours=100),  # 28h overdue
            "lifecycle_state": "VIEWED",
        },
    ]
    breaches = find_sla_breaches(queries, now=now)
    assert len(breaches) == 2
    assert breaches[0].query_id == "q2"
    assert breaches[0].hours_overdue > breaches[1].hours_overdue


def test_find_sla_breaches_ignores_unapproved() -> None:
    """Queries that haven't been approved yet have no SLA."""

    query = {
        "query_id": "q1",
        "case_id": "c1",
        "priority": "routine",
        "approved_at": None,
        "lifecycle_state": "DRAFT",
    }
    breaches = find_sla_breaches([query])
    assert breaches == []


def test_find_sla_breaches_within_healthy_window() -> None:
    """Query at 50% of SLA = no breach."""

    approved = datetime.now(timezone.utc) - timedelta(hours=36)
    query = {
        "query_id": "q1",
        "case_id": "c1",
        "priority": "routine",  # 72h SLA
        "approved_at": approved,
        "lifecycle_state": "SENT_TO_CLINICIAN",
    }
    breaches = find_sla_breaches([query])
    assert breaches == []


# ---------------------------------------------------------------------------
# Audit dashboard
# ---------------------------------------------------------------------------


def test_build_audit_dashboard_empty() -> None:
    snap = build_audit_dashboard([], [], [])
    assert isinstance(snap, AuditDashboardSnapshot)
    assert snap.total_cases == 0
    assert snap.total_queries == 0
    assert snap.breaches_critical == 0


def test_build_audit_dashboard_counts_states() -> None:
    queries = [
        {"query_id": "q1", "lifecycle_state": "PENDING_CDI_REVIEW",
         "priority": "routine", "case_id": "c1", "gap_type": "diagnostic_specificity"},
        {"query_id": "q2", "lifecycle_state": "APPROVED",
         "priority": "urgent", "case_id": "c1", "gap_type": "etiology_unspecified"},
        {"query_id": "q3", "lifecycle_state": "CLOSED",
         "priority": "routine", "case_id": "c2", "gap_type": "diagnostic_specificity"},
    ]
    snap = build_audit_dashboard([{"case_id": "c1"}, {"case_id": "c2"}], queries, [])
    assert snap.total_cases == 2
    assert snap.total_queries == 3
    assert snap.queries_by_state["PENDING_CDI_REVIEW"] == 1
    assert snap.queries_by_state["APPROVED"] == 1
    assert snap.queries_by_state["CLOSED"] == 1
    assert snap.queries_by_priority["routine"] == 2
    assert snap.queries_by_priority["urgent"] == 1


def test_build_audit_dashboard_top_gap_types() -> None:
    queries = [
        {"query_id": "q1", "lifecycle_state": "CLOSED", "priority": "routine",
         "case_id": "c1", "gap_type": "diagnostic_specificity"},
        {"query_id": "q2", "lifecycle_state": "CLOSED", "priority": "routine",
         "case_id": "c1", "gap_type": "diagnostic_specificity"},
        {"query_id": "q3", "lifecycle_state": "CLOSED", "priority": "routine",
         "case_id": "c1", "gap_type": "etiology_unspecified"},
    ]
    snap = build_audit_dashboard([], queries, [])
    assert snap.top_gap_types[0] == ("diagnostic_specificity", 2)
    assert snap.top_gap_types[1] == ("etiology_unspecified", 1)


def test_build_audit_dashboard_response_category_distribution() -> None:
    responses = [
        {"query_id": "q1", "category": "specific_clinical_answer"},
        {"query_id": "q2", "category": "specific_clinical_answer"},
        {"query_id": "q3", "category": "escape_hatch"},
    ]
    snap = build_audit_dashboard([], [], responses)
    assert snap.response_category_distribution["specific_clinical_answer"] == 2
    assert snap.response_category_distribution["escape_hatch"] == 1


def test_build_audit_dashboard_escalation_rate() -> None:
    queries = [
        {"query_id": "q1", "lifecycle_state": "ESCALATED", "priority": "routine",
         "case_id": "c1", "gap_type": "x"},
        {"query_id": "q2", "lifecycle_state": "CLOSED", "priority": "routine",
         "case_id": "c1", "gap_type": "x"},
    ]
    snap = build_audit_dashboard([], queries, [])
    assert snap.escalation_rate == 0.5


def test_build_audit_dashboard_avg_hours_to_close() -> None:
    now = datetime.now(timezone.utc)
    queries = [
        {
            "query_id": "q1",
            "lifecycle_state": "CLOSED",
            "priority": "routine",
            "case_id": "c1",
            "gap_type": "x",
            "created_at": now - timedelta(hours=48),
            "closed_at": now,
        },
        {
            "query_id": "q2",
            "lifecycle_state": "CLOSED",
            "priority": "routine",
            "case_id": "c1",
            "gap_type": "x",
            "created_at": now - timedelta(hours=24),
            "closed_at": now,
        },
    ]
    snap = build_audit_dashboard([], queries, [], now=now)
    assert snap.average_hours_to_close is not None
    assert 35 < snap.average_hours_to_close < 37  # avg of 48 and 24


def test_build_audit_dashboard_breach_counts() -> None:
    now = datetime.now(timezone.utc)
    queries = [
        # Critical: 100h elapsed, 72h SLA → 28h overdue
        {
            "query_id": "q1",
            "lifecycle_state": "SENT_TO_CLINICIAN",
            "priority": "routine",
            "case_id": "c1",
            "gap_type": "x",
            "approved_at": now - timedelta(hours=100),
        },
        # Warning: 60h elapsed, 72h SLA → 80%+
        {
            "query_id": "q2",
            "lifecycle_state": "VIEWED",
            "priority": "routine",
            "case_id": "c1",
            "gap_type": "x",
            "approved_at": now - timedelta(hours=60),
        },
    ]
    snap = build_audit_dashboard([], queries, [], now=now)
    assert snap.breaches_critical == 1
    assert snap.breaches_warning == 1


def test_build_audit_dashboard_avg_hours_to_response() -> None:
    now = datetime.now(timezone.utc)
    queries = [
        {
            "query_id": "q1",
            "lifecycle_state": "RESPONDED",
            "priority": "routine",
            "case_id": "c1",
            "gap_type": "x",
            "created_at": now - timedelta(hours=20),
        },
    ]
    responses = [
        {
            "query_id": "q1",
            "category": "specific_clinical_answer",
            "submitted_at": now,
        },
    ]
    snap = build_audit_dashboard([], queries, responses, now=now)
    assert snap.average_hours_to_response is not None
    assert 19 < snap.average_hours_to_response < 21
