# Gate 8 — Roles + Notifications + SLA + Audit Dashboard Report

**Date**: 2026-07-11
**PDF ref**: §12 Gate 8 — CDI roles + notifications + SLA + audit
**Status**: `PASS_GATE8_ROLES_NOTIFICATIONS_SLA_AUDIT_WIRED`
**Commit**: `feat(track-d8): add cdi roles notifications sla and audit dashboard`

---

## 1. What this gate delivers

The operational layer for CDI workflows. Until Gate 7, CDI was a state
machine + UI mock. Gate 8 adds:

| Layer | Before (Gate 7) | After (Gate 8) |
|---|---|---|
| Access control | Any user could drive any transition | 4 CDI roles (cdi_specialist/clinician/auditor/admin) with scoped permissions |
| Notifications | None | Subscription-based events for state changes + SLA breaches |
| SLA tracking | Static `compute_sla_due_at()` helper | Runtime breach detection (warning at 80%, critical past due) |
| Audit dashboard | None | Aggregated metrics: cases/queries/breaches/escalation/top gap types |

## 2. Role-based access control

`platform_role_to_cdi_role()` maps the existing `UserRole` enum to CDI
roles:

| Platform `UserRole` | CDI role | Why |
|---|---|---|
| `ADMIN` | `admin` | Full control |
| `QC` (质控科) | `cdi_specialist` | Drives CDI workflow |
| `CLINICIAN` (临床医生) | `clinician` | Responds to queries |
| `INSURANCE` (医保办) | `auditor` | Read-only oversight |
| `DEPT_HEAD` (科室负责人) | `auditor` | Read-only oversight |
| `CODER` (编码员) | `auditor` | Read-only (medical-coding side, not CDI) |
| `IT` (信息科) | `auditor` | Read-only oversight |
| unknown | `auditor` | Default = least privilege |

### 2.1 Transition matrix per role

| Transition | cdi_specialist | clinician | auditor | admin |
|---|---|---|---|---|
| DRAFT → PENDING_CDI_REVIEW | ✓ | × | × | ✓ |
| PENDING_CDI_REVIEW → APPROVED | ✓ | × | × | ✓ |
| PENDING_CDI_REVIEW → DRAFT | ✓ | × | × | ✓ |
| PENDING_CDI_REVIEW → CANCELLED | ✓ | × | × | ✓ |
| APPROVED → SENT_TO_CLINICIAN | ✓ | × | × | ✓ |
| SENT_TO_CLINICIAN → VIEWED | × | ✓ | × | ✓ |
| VIEWED → RESPONDED | × | ✓ | × | ✓ |
| VIEWED → ESCALATED | × | ✓ | × | ✓ |
| RESPONDED → DOCUMENTATION_UPDATED | ✓ | ✓ | × | ✓ |
| DOCUMENTATION_UPDATED → REVALIDATED | ✓ | × | × | ✓ |
| REVALIDATED → CLOSED | ✓ | × | × | ✓ |

Auditor has zero allowed transitions — pure read-only. This enforces
the PDF §1 boundary: "auditor cannot influence clinical workflow".

### 2.2 Public API

```python
can_drive_transition(role, from_state, to_state) -> RolePermissionCheck
get_role_permissions(role) -> set[tuple[str, str]]
platform_role_to_cdi_role(platform_role) -> CdiRole
```

## 3. Notifications

### 3.1 Notification events

7 event types (all post-transition):

| Event | Trigger |
|---|---|
| `QUERY_SENT_TO_CLINICIAN` | After APPROVED → SENT_TO_CLINICIAN |
| `QUERY_VIEWED_BY_CLINICIAN` | After SENT_TO_CLINICIAN → VIEWED |
| `QUERY_RESPONDED` | After VIEWED → RESPONDED |
| `QUERY_ESCALATED` | After VIEWED → ESCALATED (escape hatch) |
| `QUERY_CLOSED` | After REVALIDATED → CLOSED |
| `SLA_BREACH_WARNING` | Query past 80% of SLA window |
| `SLA_BREACH_CRITICAL` | Query past SLA due_at |

### 3.2 Subscription channels

| Channel | Use case |
|---|---|
| `in_app` | Surface in /notifications badge (default for cdi_specialist) |
| `webhook` | POST to EMR for SENT_TO_CLINICIAN (default for hospital integration) |
| `email` | Daily digest for auditor (deferred to Gate 9+) |

### 3.3 Subscription filtering

```python
should_dispatch(sub, payload) -> bool
select_subscriptions_for_event(subs, payload) -> list[NotificationSubscription]
```

Webhooks require `target_url` to be set; otherwise filtered out.

## 4. SLA tracking

`find_sla_breaches(open_queries, now=None)`:

- Ignores queries in CLOSED/CANCELLED/EXPIRED
- Ignores queries without `approved_at`
- Computes SLA window from `compute_sla_due_at(approved_at, priority)`:
  - routine = 72h
  - urgent = 24h
- Warning threshold: 80% of SLA elapsed (configurable via `SLA_WARNING_RATIO`)
- Severity:
  - `warning` if past 80% but not yet due
  - `critical` if past `sla_due_at`
- Returns sorted by `hours_overdue` descending

### 4.1 Public API

```python
@dataclass
class SLABreachRecord:
    query_id: str
    case_id: str
    priority: Literal["routine", "urgent"]
    approved_at: datetime
    sla_due_at: datetime
    breached_at: datetime
    hours_overdue: float
    severity: Literal["warning", "critical"]

find_sla_breaches(open_queries, now=None) -> list[SLABreachRecord]
```

### 4.2 Cron integration

Gate 9 will wire a periodic task (every 5 min) that:
1. Fetches open queries via `SELECT FROM provider_queries WHERE lifecycle_state NOT IN ('CLOSED','CANCELLED','EXPIRED') AND approved_at IS NOT NULL`
2. Calls `find_sla_breaches(rows)`
3. For each record, dispatches `SLA_BREACH_WARNING` or `SLA_BREACH_CRITICAL` notifications
4. Records to AuditLog

The cron logic itself is in this service (pure function); Gate 9 adds the scheduler wiring.

## 5. Audit dashboard

`build_audit_dashboard(cases, queries, responses, now=None) -> AuditDashboardSnapshot`

Pure computation — no DB queries inside. Gate 9 REST endpoint fetches
rows and passes them in.

### 5.1 Metrics computed

| Metric | Source |
|---|---|
| `total_cases` | len(cases) |
| `total_queries` | len(queries) |
| `queries_by_state` | counter over lifecycle_state |
| `queries_by_priority` | counter over priority |
| `breaches_critical` | count of SLABreachRecord with severity=critical |
| `breaches_warning` | count of SLABreachRecord with severity=warning |
| `response_category_distribution` | counter over response.category |
| `average_hours_to_response` | mean(response.submitted_at - query.created_at) |
| `average_hours_to_close` | mean(query.closed_at - query.created_at) for CLOSED |
| `top_gap_types` | top 5 gap_type by frequency |
| `escalation_rate` | ESCALATED / total |

### 5.2 Auditor role integration

The auditor role gets read-only access to:
- `GET /api/v1/cdi/audit/dashboard` (Gate 9 endpoint)
- Returns the full `AuditDashboardSnapshot` JSON
- Frontend (Gate 8 frontend not in this commit) renders it as a grid of stat cards + breach table

## 6. Circular import fix

Gate 8 surfaced a latent circular import:

```
cdi_roles_notifications.py
  → cdi_query_lifecycle.py
    → app.icoder.agent_runtime.cdi/__init__.py
      → clinician_response.py
        → cdi_query_lifecycle.py (partially loaded — ImportError)
```

Fixed by changing `clinician_response.py` to lazy-import
`attempt_transition` inside `process_clinician_response()` instead of
at module top. TYPE_CHECKING import keeps type hints intact.

This was a latent bug that would have surfaced in Gate 9 anyway
(REST API would have hit the same cycle).

## 7. Tests (41 new)

`backend/tests/unit/icoder/cdi/test_roles_notifications_sla_audit.py`:

### 7.1 Role mapping (8 tests)
- 8-way parametrized platform_role → cdi_role mapping

### 7.2 RBAC (12 tests)
- `test_cdi_specialist_can_approve_query`
- `test_clinician_cannot_approve_query`
- `test_clinician_can_respond`
- `test_cdi_specialist_cannot_respond`
- `test_auditor_is_read_only` (no transitions allowed)
- `test_admin_can_drive_anything`
- `test_cdi_specialist_can_send_to_clinician`
- `test_cdi_specialist_can_close_after_revalidation`
- `test_clinician_can_escalate_escape_hatch`
- `test_cdi_specialist_cannot_escalate_viewed`
- `test_unknown_role_rejected_cleanly`
- `test_get_role_permissions_returns_set`

### 7.3 Notifications (5 tests)
- matching/non-matching event dispatch
- webhook requires URL
- select_subscriptions filters correctly

### 7.4 SLA breaches (8 tests)
- empty input
- ignores CLOSED
- critical breach detection
- warning at 80% threshold
- urgent priority (24h SLA)
- sort by overdue descending
- ignores unapproved queries
- within healthy window = no breach

### 7.5 Audit dashboard (8 tests)
- empty input
- counts states correctly
- top gap types
- response category distribution
- escalation rate
- average hours to close
- breach counts
- average hours to response

### 7.6 Test results

```
=================== 148 passed, 1 warning in 1.84s ===================
```

All 148 CDI tests pass (29 Gate 3 + 26 Gate 4 + 35 Gate 5 + 17 Gate 6 + 41 Gate 8).

## 8. Verification

- ✅ 4 CDI roles with scoped permissions
- ✅ 11 transition rules per role (cdi_specialist) / 4 (clinician) / 0 (auditor) / 15 (admin)
- ✅ Auditor is strictly read-only (zero transitions)
- ✅ Notifications support 7 events × 3 channels
- ✅ SLA tracking with warning (80%) + critical (past due) thresholds
- ✅ SLA priorities enforced (routine=72h, urgent=24h)
- ✅ Audit dashboard computes 11 distinct metrics
- ✅ Circular import resolved via lazy import
- ✅ 41 new tests + 107 existing tests = 148 CDI tests pass
- ✅ No regression in CDI test suite

## 9. Boundary enforcement audit

| Boundary | Gate 8 enforcement |
|---|---|
| Auditor cannot influence workflow | `_ALLOWED_TRANSITIONS["auditor"]` is empty set |
| Clinician cannot approve own query | APPROVED transition only in cdi_specialist/admin sets |
| CDI specialist cannot self-respond | RESPONDED transition only in clinician/admin sets |
| Escape hatch escalation = clinician's call | VIEWED → ESCALATED only in clinician/admin sets |
| SLA applies to all post-APPROVED queries | find_sla_breaches ignores CLOSED/CANCELLED/EXPIRED only |
| Audit dashboard read-only | build_audit_dashboard returns immutable dataclass |

## 10. What is NOT in Gate 8 (deferred)

- **REST endpoints**: Gate 9 wires `POST /api/v1/cdi/queries/{id}/transition` + `GET /api/v1/cdi/audit/dashboard` + `POST /api/v1/cdi/subscriptions`
- **Cron scheduler**: Gate 9 adds APScheduler/APQ background task calling `find_sla_breaches` every 5 min
- **Frontend dashboard**: Gate 8 frontend renders dashboard widget; backend ready now
- **Webhook HMAC signing**: `NotificationSubscription.secret` field exists; HMAC verification logic deferred to Gate 9
- **Async DB persistence**: `attempt_transition()` is pure logic still; Gate 9 wires async DB session
- **AuditLog emission on transitions**: Gate 5 service emits metadata; Gate 9 wires actual DB writes

## 11. Next: Gate 9-12 — API + A2A + Security + Hospital integration

Combined commit (PDF §13-§16, folded per PDF §18 instructions):

- REST API: `/api/v1/cdi/runs`, `/api/v1/cdi/queries/{id}/transition`, `/api/v1/cdi/audit/dashboard`
- A2A v0.3 endpoint at `/a2a/cdi-agent`
- Async DB persistence for `attempt_transition`
- Hospital EMR webhook contracts
- 9 security red lines enforcement matrix

Commit: `feat(track-d9): add cdi api a2a and hospital integration contracts`
