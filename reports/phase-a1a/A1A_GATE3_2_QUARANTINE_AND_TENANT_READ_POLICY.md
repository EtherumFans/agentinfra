# Phase A1A Gate 3.2 — Quarantine & Tenant Read Policy

**Date**: 2026-07-18
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3.1 (`A1A_GATE3_1_LEGACY_TENANCY_RECONCILIATION.md`)

Closes charter §3.2 requirements:

1. Rows classified as `LEGACY_TENANT_UNKNOWN`,
   `LEGACY_TENANT_AMBIGUOUS`, `QUARANTINED`, or `MODERN_SYSTEM` are
   **invisible to normal tenant reads** — not returned with a deny
   flag, simply absent.
2. Point-reads of invisible rows return **exact 404, not 403** — no
   existence leak (charter §3.2 §4).
3. A separate **Security Admin** authorization path can read
   quarantined rows for forensics; every access is audited.

---

## §1. Deliverables

| Artifact | Path |
|---|---|
| Tenant read policy service | `backend/app/services/tenant_read_policy.py` (new, ~250 LOC) |
| Visibility filter wired into list/aggregate paths | `backend/app/api/usage.py`, `backend/app/api/run_trace.py` |
| Visibility guard on point-read | `backend/app/api/runs.py` (GET `/api/v1/runs/{id}`) |
| Unit tests (24 cases) | `backend/tests/unit/app/test_tenant_read_policy.py` |
| API integration tests (5 cases) | `backend/tests/test_api/test_a1a_gate3_2_tenant_read_policy.py` |
| Legacy test fixtures updated | `test_phase5_a3_usage_run_history_cost.py`, `test_phase5_a6_run_history_days_filter.py`, `test_phase7_gate8_usage_api_client.py` |

---

## §2. Visibility sets

### 2.1 Visible to tenant reads

```python
TENANT_VISIBLE_CLASSIFICATIONS = frozenset({
    "MODERN",                          # modern write path
    "LEGACY_TENANT_VERIFIED",          # request-level evidence pins to 1 org
    "LEGACY_TENANT_INFERRED",          # single-membership inference
})
```

### 2.2 Invisible to tenant reads

```python
TENANT_INVISIBLE_CLASSIFICATIONS = frozenset({
    "LEGACY_TENANT_UNKNOWN",           # no candidate org
    "LEGACY_TENANT_AMBIGUOUS",         # multiple candidate orgs
    "QUARANTINED",                     # operator-flagged
    "MODERN_SYSTEM",                   # system-scope; no owning tenant
})
```

### 2.3 NULL classification

`NULL` is **invisible** (fail-closed). This matters for tables not yet
migrated (e.g. `encounters`, `cdi_cases`) where the column exists but
rows were written before Gate 2.

---

## §3. Helpers

### 3.1 `is_tenant_visible(classification)`

Predicate. `None` → `False`. Unknown strings → `False` (fail-closed
defence against future classifications not yet in the allowlist).

### 3.2 `apply_tenant_visibility_filter(stmt, column, *, also_exclude_null=True)`

SQLAlchemy helper that adds:

```sql
WHERE column IN ('MODERN', 'LEGACY_TENANT_VERIFIED', 'LEGACY_TENANT_INFERRED')
  AND column IS NOT NULL    -- when also_exclude_null=True (default)
```

`also_exclude_null=False` is an opt-out for tables that genuinely have
no classification column (the legacy `cdi_cases` table pre-Phase 7).

### 3.3 `enforce_tenant_visible_or_404(*, classification, run_id=None, resource="resource")`

Point-read guard. Raises `HTTPException(404)` with detail
`"no {resource} found"` — the same message used for genuinely absent
rows. Internal log captures `run_id` and `classification` but the
client never sees them.

### 3.4 `assert_security_admin_access(user, db, *, action, resource_type, resource_id, reason)`

Authorisation gate for forensic reads. Allowlist:

```python
SECURITY_ADMIN_ROLES = frozenset({
    "security_admin",
    "platform_security_admin",
    "platform_auditor",
})
```

Org-level `admin` (a hospital administrator scoped to one tenant)
**does NOT pass** — only platform-level security roles. On success,
emits a `security_admin.access` audit event via `system_audit` (Gate
3.6 will provide the real sink; today the helper falls back to
`logger.warning`).

---

## §4. Endpoints wired

| Endpoint | Filter type | Where |
|---|---|---|
| `GET /api/usage/summary` | list+aggregate (cost_query, daily_query) | `usage.py:105, 134` |
| `GET /api/usage/by-agent` | list+aggregate | `usage.py:224` |
| `GET /api/usage/by-client` | list+aggregate (partner_stmt + console_stmt) | `usage.py:301, 316` |
| `GET /api/usage/history` | list (audit_logs) | `usage.py:361` |
| `GET /api/runtime/runs/history` | list | `run_trace.py:163` |
| `GET /api/v1/runs/{run_id}` | point-read 404 guard | `runs.py:140` |

Each of these was an F02/F03-style leak vector (the surface area
already org-scoped by Gate 2 — Gate 3.2 adds the orthogonal
classification visibility filter on top).

---

## §5. Test results

### 5.1 Unit tests (24 cases)

```
tests/unit/app/test_tenant_read_policy.py
  24 passed in 1.85s
```

Coverage matrix:

| Charter §3.2 item | Test |
|---|---|
| Visible classes pass | `test_visible_classifications_pass[MODERN/VERIFIED/INFERRED]` |
| Invisible classes fail | `test_invisible_classifications_fail[UNKNOWN/AMBIGUOUS/QUARANTINED/MODERN_SYSTEM]` |
| NULL = invisible (§2) | `test_null_classification_is_invisible` |
| Unknown string = invisible (fail-closed) | `test_unknown_string_is_invisible` |
| Point-read 404 (§4) | `test_enforce_guard_404_on_invisible[...]` ×4 |
| Point-read 404 detail doesn't leak run_id | `test_enforce_guard_404_on_invisible` |
| Point-read 404 detail doesn't leak classification | `test_enforce_guard_404_on_invisible` |
| Point-read passes visible | `test_enforce_guard_passes_visible[...]` ×3 |
| Point-read 404 on NULL | `test_enforce_guard_404_on_null` |
| SQL filter contains visible classes | `test_apply_filter_excludes_invisible` |
| SQL filter excludes NULL by default | `test_apply_filter_excludes_invisible` |
| SQL filter opt-out for NULL | `test_apply_filter_optional_null_inclusion` |
| Security Admin allows platform_security_admin | `test_security_admin_allows_platform_security_admin` |
| Security Admin denies member | `test_security_admin_denies_normal_user` |
| Security Admin denies NULL role | `test_security_admin_denies_null_role` |
| Security Admin denies tenant-level admin (§"Security Admin 路径需要专用权限") | `test_security_admin_denies_org_admin` |
| SECURITY_ADMIN_ROLES allowlist excludes member/admin | `test_security_admin_roles_allowlist_is_restrictive` |

### 5.2 API integration tests (5 cases)

```
tests/test_api/test_a1a_gate3_2_tenant_read_policy.py
  5 passed in 15.35s
```

These tests seed one row in each visibility class and verify the
HTTP response excludes invisible rows:

| Test | What it proves |
|---|---|
| `test_summary_excludes_invisible_classifications` | `/api/usage/summary?days=1` credits_used = 0.10 (MODERN) not 2.10 (MODERN + 4×0.50 invisible) |
| `test_summary_daily_breakdown_excludes_invisible` | daily_breakdown today = 0.10 only |
| `test_by_agent_excludes_invisible` | `/api/usage/by-agent` shows only 1 run, 0.10 |
| `test_runs_history_excludes_invisible` | `/api/runtime/runs/history` returned_ids contains MODERN, none of the 4 invisible prefixes |
| `test_usage_history_excludes_invisible` | `/api/usage/history` (audit_logs) returns only the MODERN action |

### 5.3 Regression (Phase A1A + Gate 2)

```
tests/unit/app/test_tenant_read_policy.py              24 passed
tests/unit/app/test_legacy_tenancy_attribution.py      17 passed
tests/unit/app/test_tenancy_guard.py                   11 passed
tests/test_api/test_a1a_gate2_org_isolation.py         16 passed
tests/test_api/test_a1a_gate3_2_tenant_read_policy.py  5  passed
                                                       73 passed
```

### 5.4 Regression (affected APIs — Phase 5/7)

```
tests/test_api/test_phase5_a3_usage_run_history_cost.py    2 passed
tests/test_api/test_phase5_a6_run_history_days_filter.py   1 passed
tests/test_api/test_phase7_gate8_usage_api_client.py      14 passed
tests/test_api/test_phase7_gate4_run_cancel.py             7 passed
                                                           24 passed
```

---

## §6. Fixture updates

Three legacy test fixtures seeded `run_history` rows without
`tenancy_classification`. In production this never happens (Gate 2's
fail-closed write guard stamps every row), but the test helpers
bypassed the write path via direct INSERT. Updated:

- `test_phase5_a3_usage_run_history_cost.py:67-76` — added
  `tenancy_classification='MODERN'` to the INSERT column list.
- `test_phase5_a6_run_history_days_filter.py:57-66` — same.
- `test_phase7_gate8_usage_api_client.py:81-92, 315-325` — added
  `tenancy_classification="MODERN"` to the two `RunHistoryModel(...)`
  constructor sites.

No production code was modified to make these tests pass — the
fixtures now mirror production's invariant.

---

## §7. Charter requirements — closure

| Charter §3.2 item | Status |
|---|---|
| §1 Normal tenant read of UNKNOWN → 404 | ✅ `enforce_tenant_visible_or_404` + filter |
| §1 Normal tenant read of AMBIGUOUS → 404 | ✅ same |
| §1 Normal tenant read of QUARANTINED → 404 | ✅ same |
| §1 Normal tenant read of MODERN_SYSTEM → 404 | ✅ same |
| §1 Normal tenant read of NULL classification → 404 | ✅ NULL is invisible |
| §2 NULL classification NOT visible by default | ✅ `is_tenant_visible(None) is False`; `also_exclude_null=True` default |
| §3 Security Admin role separate from tenant admin | ✅ `SECURITY_ADMIN_ROLES` excludes `admin` |
| §4 Exact 404, no existence leak | ✅ detail = `"no {resource} found"`, no run_id/classification echo |
| §5 List/aggregate excludes invisible | ✅ 6 endpoints wired |
| (Forensic audit of Security Admin reads) | 🟡 Stub — `system_audit` import is lazy and falls back to logger.warning today; Gate 3.6 will provide the real sink |

---

## §8. Open carry-over

- **Gate 3.4** (F04 carry-over): SSE event endpoint must add the same
  visibility filter + RunHistory cross-check before streaming events.
  F04 is still open; this gate doesn't close it.
- **Gate 3.5** (F05 carry-over): The signed-token trace URL endpoint
  (`GET /api/v1/runs/{run_id}/trace?token=...`) currently authorises
  by token signature + org cross-check but does NOT yet call
  `enforce_tenant_visible_or_404`. Partner tokens don't carry
  classification context today. Gate 3.5 will close this.
- **Gate 3.6**: Real `system_audit` sink for Security Admin access
  events. The stub emits `logger.warning` only.
- **Gate 3.7**: DB-level CHECK constraint that
  `tenancy_classification` ∈ the 7-class set on every row, so future
  writes can't silently introduce a typo that escapes the allowlist.
- **Other tables**: The filter is wired into `run_history`,
  `audit_logs`. Tables still pending column migration (`encounters`,
  `cdi_cases`, `coding_reviews`) inherit `NULL` and are excluded by
  `also_exclude_null=True`. Gate 3.7 will discuss whether to migrate
  them.

---

## §9. Verdict

```
PASS_A1A_GATE3_2_QUARANTINE_AND_TENANT_READ_POLICY_ENFORCED
```

Forbidden verdicts (charter §22) remain forbidden: this gate does NOT
certify production readiness, hospital deployment, partner production
readiness, security certification, clinical validation, "all tenant
isolation complete", "all audit gaps resolved", or "zero defects".
F04 (SSE) and F05 (signed-token trace URL) remain open until Gates
3.4 and 3.5 close.

Gate 3.3 (Database-backed trace persistence) follows.
