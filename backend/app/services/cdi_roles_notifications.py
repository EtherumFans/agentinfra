"""CDI Roles + Notifications + SLA + Audit Dashboard service.

Phase 5 Track D Gate 8.

This module adds the operational layer for CDI workflows:

  1. **Role-based access control** — CDI specialist, clinician, auditor
     roles mapped to permission scopes (which lifecycle transitions they
     can drive).
  2. **Notifications** — In-app + webhook subscription for state changes
     (SENT_TO_CLINICIAN, RESPONDED, ESCALATED, SLA_BREACH).
  3. **SLA tracking** — Compare APPROVED timestamps against now to detect
     breaches; cron job calls `find_sla_breaches()` periodically.
  4. **Audit dashboard** — Aggregated metrics for the auditor role:
     open queries by state, breach counts, response category
     distribution, etc.

Pure logic — no FastAPI/HTTP layer here. Gate 9 wires this to REST API
endpoints. The existing `cdi_query_lifecycle.attempt_transition()`
emits audit events that this module reads back for the dashboard.

PDF §12 Gate 8 reference:
    reports/phase5_track_d/GATE8_ROLES_NOTIFICATIONS_SLA_AUDIT_REPORT.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal

from app.services.cdi_query_lifecycle import (
    LifecycleState,
    compute_sla_due_at,
)


# ---------------------------------------------------------------------------
# 1. Role-based access control
# ---------------------------------------------------------------------------


CdiRole = Literal[
    "cdi_specialist",
    "clinician",
    "auditor",
    "admin",
]


# Map platform UserRole (admin/coder/qc/clinician/insurance) to CDI role
_PLATFORM_ROLE_MAP: dict[str, CdiRole] = {
    "admin": "admin",
    "qc": "cdi_specialist",  # 质控科 drives CDI workflow
    "clinician": "clinician",
    "insurance": "auditor",  # 医保办 audits
    "dept_head": "auditor",  # 科室负责人 can audit
    "coder": "auditor",  # 编码员 read-only audit
    "it": "auditor",  # 信息科 read-only audit
}


def platform_role_to_cdi_role(platform_role: str) -> CdiRole:
    """Map a platform UserRole string to a CDI role."""

    return _PLATFORM_ROLE_MAP.get(platform_role, "auditor")


# Per-role allowed lifecycle transitions
# (from_state, to_state) pairs that this role can drive
_ALLOWED_TRANSITIONS: dict[CdiRole, set[tuple[str, str]]] = {
    "cdi_specialist": {
        # Author + review side
        ("DRAFT", "PENDING_CDI_REVIEW"),
        ("PENDING_CDI_REVIEW", "APPROVED"),
        ("PENDING_CDI_REVIEW", "DRAFT"),  # send back for revision
        ("PENDING_CDI_REVIEW", "CANCELLED"),
        # Send to clinician
        ("APPROVED", "SENT_TO_CLINICIAN"),
        ("APPROVED", "CANCELLED"),
        # Revalidation after clinician response + chart update
        ("DOCUMENTATION_UPDATED", "REVALIDATED"),
        ("REVALIDATED", "CLOSED"),
        # Close directly if no clinician response needed
        ("RESPONDED", "DOCUMENTATION_UPDATED"),
    },
    "clinician": {
        # Receive + respond side
        ("SENT_TO_CLINICIAN", "VIEWED"),
        ("VIEWED", "RESPONDED"),
        # Escape hatch: clinician cannot answer
        ("VIEWED", "ESCALATED"),
        # Chart updated signal from clinician (manual or via EMR integration)
        ("RESPONDED", "DOCUMENTATION_UPDATED"),
    },
    "auditor": {
        # Read-only — no transitions; can only view
    },
    "admin": {
        # All transitions allowed
        ("DRAFT", "PENDING_CDI_REVIEW"),
        ("PENDING_CDI_REVIEW", "APPROVED"),
        ("PENDING_CDI_REVIEW", "DRAFT"),
        ("PENDING_CDI_REVIEW", "CANCELLED"),
        ("APPROVED", "SENT_TO_CLINICIAN"),
        ("APPROVED", "CANCELLED"),
        ("SENT_TO_CLINICIAN", "VIEWED"),
        ("SENT_TO_CLINICIAN", "EXPIRED"),
        ("VIEWED", "RESPONDED"),
        ("VIEWED", "ESCALATED"),
        ("RESPONDED", "DOCUMENTATION_UPDATED"),
        ("RESPONDED", "ESCALATED"),
        ("DOCUMENTATION_UPDATED", "REVALIDATED"),
        ("REVALIDATED", "CLOSED"),
        ("DOCUMENTATION_UPDATED", "CLOSED"),
    },
}


@dataclass
class RolePermissionCheck:
    """Result of an RBAC check on a lifecycle transition."""

    allowed: bool
    role: CdiRole
    from_state: LifecycleState
    to_state: LifecycleState
    reason: str = ""


def can_drive_transition(
    role: CdiRole,
    from_state: LifecycleState,
    to_state: LifecycleState,
) -> RolePermissionCheck:
    """Check whether a CDI role is allowed to drive a transition."""

    if role not in _ALLOWED_TRANSITIONS:
        return RolePermissionCheck(
            allowed=False,
            role=role,
            from_state=from_state,
            to_state=to_state,
            reason=f"unknown role {role!r}",
        )

    pair = (from_state, to_state)
    if pair in _ALLOWED_TRANSITIONS[role]:
        return RolePermissionCheck(
            allowed=True,
            role=role,
            from_state=from_state,
            to_state=to_state,
            reason="allowed",
        )

    return RolePermissionCheck(
        allowed=False,
        role=role,
        from_state=from_state,
        to_state=to_state,
        reason=f"role {role} cannot drive {from_state} -> {to_state}",
    )


def get_role_permissions(role: CdiRole) -> set[tuple[str, str]]:
    """Return the full allowed transition set for a role (for UI hints)."""

    return set(_ALLOWED_TRANSITIONS.get(role, set()))


# ---------------------------------------------------------------------------
# 2. Notifications
# ---------------------------------------------------------------------------


NotificationEvent = Literal[
    "QUERY_SENT_TO_CLINICIAN",
    "QUERY_VIEWED_BY_CLINICIAN",
    "QUERY_RESPONDED",
    "QUERY_ESCALATED",
    "QUERY_CLOSED",
    "SLA_BREACH_WARNING",
    "SLA_BREACH_CRITICAL",
]


@dataclass
class NotificationSubscription:
    """A subscription to CDI notification events.

    `channel`:
        - "in_app"  → record to DB, surface in /notifications badge
        - "webhook" → POST to `target_url` with JSON payload
        - "email"   → send via email service (deferred to Gate 9+)
    """

    subscription_id: str
    user_role: CdiRole
    events: list[NotificationEvent]
    channel: Literal["in_app", "webhook", "email"]
    target_url: str = ""
    secret: str = ""  # for webhook HMAC verification


@dataclass
class NotificationPayload:
    """Payload dispatched to a subscription."""

    event: NotificationEvent
    query_id: str
    case_id: str
    timestamp: datetime
    details: dict = field(default_factory=dict)


def should_dispatch(
    sub: NotificationSubscription, payload: NotificationPayload
) -> bool:
    """Decide whether a subscription should receive a payload."""

    if payload.event not in sub.events:
        return False

    if sub.channel == "webhook" and not sub.target_url:
        return False

    return True


def select_subscriptions_for_event(
    subs: Iterable[NotificationSubscription],
    payload: NotificationPayload,
) -> list[NotificationSubscription]:
    """Filter subscriptions to those that should receive a payload."""

    return [s for s in subs if should_dispatch(s, payload)]


# ---------------------------------------------------------------------------
# 3. SLA tracking
# ---------------------------------------------------------------------------


@dataclass
class SLABreachRecord:
    """One SLA breach detected by `find_sla_breaches`."""

    query_id: str
    case_id: str
    priority: Literal["routine", "urgent"]
    approved_at: datetime
    sla_due_at: datetime
    breached_at: datetime
    hours_overdue: float
    severity: Literal["warning", "critical"]


# Warning threshold: 80% of SLA elapsed
SLA_WARNING_RATIO = 0.8


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normalize database timestamps for portable SLA arithmetic.

    SQLite drops timezone metadata for persisted UTC datetimes, while
    PostgreSQL returns aware values.  Treat naive persisted values as UTC and
    convert aware values to UTC so both backends use the same SLA semantics.
    """

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def find_sla_breaches(
    open_queries: Iterable[dict],
    *,
    now: datetime | None = None,
) -> list[SLABreachRecord]:
    """Find queries whose SLA is breached or near-breaching.

    Each entry in `open_queries` should be a dict with keys:
        - query_id: str
        - case_id: str
        - priority: "routine" | "urgent"
        - approved_at: datetime
        - lifecycle_state: str (one of the post-APPROVED states)

    Queries in CLOSED/CANCELLED/EXPIRED are ignored.

    Returns a list of SLABreachRecord sorted by hours_overdue descending.
    """

    if now is None:
        now = _now_utc()
    else:
        now = _as_utc(now)

    TERMINAL_STATES = {"CLOSED", "CANCELLED", "EXPIRED"}
    records: list[SLABreachRecord] = []

    for q in open_queries:
        state = q.get("lifecycle_state", "")
        if state in TERMINAL_STATES:
            continue

        approved_at = q.get("approved_at")
        if approved_at is None:
            continue
        approved_at = _as_utc(approved_at)

        priority = q.get("priority", "routine")
        sla_due_at = compute_sla_due_at(approved_at, priority)
        sla_window = (sla_due_at - approved_at).total_seconds()
        elapsed = (now - approved_at).total_seconds()
        ratio = elapsed / sla_window if sla_window > 0 else 1.0

        if ratio < SLA_WARNING_RATIO:
            continue  # Still within healthy window

        hours_overdue = max(0.0, (now - sla_due_at).total_seconds() / 3600.0)
        severity: Literal["warning", "critical"] = (
            "critical" if now >= sla_due_at else "warning"
        )

        records.append(
            SLABreachRecord(
                query_id=q["query_id"],
                case_id=q.get("case_id", ""),
                priority=priority,
                approved_at=approved_at,
                sla_due_at=sla_due_at,
                breached_at=now,
                hours_overdue=hours_overdue,
                severity=severity,
            )
        )

    records.sort(key=lambda r: r.hours_overdue, reverse=True)
    return records


# ---------------------------------------------------------------------------
# 4. Audit dashboard
# ---------------------------------------------------------------------------


@dataclass
class AuditDashboardSnapshot:
    """Aggregated CDI workflow metrics for the auditor role."""

    total_cases: int = 0
    total_queries: int = 0
    queries_by_state: dict[str, int] = field(default_factory=dict)
    queries_by_priority: dict[str, int] = field(default_factory=dict)
    breaches_critical: int = 0
    breaches_warning: int = 0
    response_category_distribution: dict[str, int] = field(default_factory=dict)
    average_hours_to_response: float | None = None
    average_hours_to_close: float | None = None
    top_gap_types: list[tuple[str, int]] = field(default_factory=list)
    escalation_rate: float = 0.0
    generated_at: datetime = field(default_factory=_now_utc)


def build_audit_dashboard(
    cases: Iterable[dict],
    queries: Iterable[dict],
    responses: Iterable[dict],
    *,
    now: datetime | None = None,
) -> AuditDashboardSnapshot:
    """Compute the audit dashboard snapshot from raw DB rows.

    Each `case` dict should have at least: case_id, created_at.
    Each `query` dict should have: query_id, case_id, lifecycle_state,
        priority, gap_type, created_at, approved_at, closed_at (optional).
    Each `response` dict should have: query_id, category, submitted_at.

    This is a pure computation — no DB queries. Gate 9 REST endpoint
    fetches rows and passes them in.
    """

    if now is None:
        now = _now_utc()

    cases_list = list(cases)
    queries_list = list(queries)
    responses_list = list(responses)

    snap = AuditDashboardSnapshot(
        total_cases=len(cases_list),
        total_queries=len(queries_list),
    )

    # Count by state
    for q in queries_list:
        state = q.get("lifecycle_state", "UNKNOWN")
        snap.queries_by_state[state] = snap.queries_by_state.get(state, 0) + 1
        priority = q.get("priority", "routine")
        snap.queries_by_priority[priority] = (
            snap.queries_by_priority.get(priority, 0) + 1
        )

    # SLA breaches
    open_queries_for_sla = [
        q for q in queries_list
        if q.get("approved_at") and q.get("lifecycle_state") not in {
            "CLOSED", "CANCELLED", "EXPIRED"
        }
    ]
    breaches = find_sla_breaches(open_queries_for_sla, now=now)
    snap.breaches_critical = sum(1 for b in breaches if b.severity == "critical")
    snap.breaches_warning = sum(1 for b in breaches if b.severity == "warning")

    # Response category distribution
    for r in responses_list:
        cat = r.get("category", "unknown")
        snap.response_category_distribution[cat] = (
            snap.response_category_distribution.get(cat, 0) + 1
        )

    # Average time to response (RESPONDED or beyond)
    response_times: list[float] = []
    for r in responses_list:
        submitted = r.get("submitted_at")
        qid = r.get("query_id")
        if not submitted or not qid:
            continue
        # Find the matching query for created_at baseline
        match = next((q for q in queries_list if q.get("query_id") == qid), None)
        if not match:
            continue
        created = match.get("created_at")
        if created:
            delta = (submitted - created).total_seconds() / 3600.0
            if delta >= 0:
                response_times.append(delta)
    if response_times:
        snap.average_hours_to_response = sum(response_times) / len(response_times)

    # Average time to close
    close_times: list[float] = []
    for q in queries_list:
        if q.get("lifecycle_state") != "CLOSED":
            continue
        closed = q.get("closed_at")
        created = q.get("created_at")
        if closed and created:
            delta = (closed - created).total_seconds() / 3600.0
            if delta >= 0:
                close_times.append(delta)
    if close_times:
        snap.average_hours_to_close = sum(close_times) / len(close_times)

    # Top gap types
    gap_counts: dict[str, int] = {}
    for q in queries_list:
        gap_type = q.get("gap_type", "unknown")
        gap_counts[gap_type] = gap_counts.get(gap_type, 0) + 1
    snap.top_gap_types = sorted(
        gap_counts.items(), key=lambda kv: kv[1], reverse=True
    )[:5]

    # Escalation rate
    if queries_list:
        escalated = sum(
            1 for q in queries_list if q.get("lifecycle_state") == "ESCALATED"
        )
        snap.escalation_rate = escalated / len(queries_list)

    return snap


__all__ = [
    # Roles
    "CdiRole",
    "RolePermissionCheck",
    "platform_role_to_cdi_role",
    "can_drive_transition",
    "get_role_permissions",
    # Notifications
    "NotificationEvent",
    "NotificationSubscription",
    "NotificationPayload",
    "should_dispatch",
    "select_subscriptions_for_event",
    # SLA
    "SLABreachRecord",
    "SLA_WARNING_RATIO",
    "find_sla_breaches",
    # Audit dashboard
    "AuditDashboardSnapshot",
    "build_audit_dashboard",
]
