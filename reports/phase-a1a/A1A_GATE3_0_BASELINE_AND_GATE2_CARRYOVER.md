# Phase A1A Gate 3.0 — Baseline and Gate 2 Carry-over Re-audit

**Date**: 2026-07-18
**Branch**: `phase-a1a/emergency-containment`
**HEAD**: `de2feaa35fa9060a771da843e811c396624352a6`
**Predecessor**: Gate 2 commit `de2feaa` (= current HEAD)
**Mode**: READ-ONLY investigation. No business code, migration, or Gate 2
report modified during this gate.

This document is the first-round deliverable for Phase A1A Gate 3.
Per the charter §23 "第一轮执行要求" it produces all 26 required evidence
items and the interim verdict. Gates 3.1–3.9 follow.

---

## §1. Git baseline verification (items 1–6)

| # | Field | Observed | Expected | Match |
|---|---|---|---|---|
| 1 | `current_branch` | `phase-a1a/emergency-containment` | `phase-a1a/emergency-containment` | ✅ |
| 2 | `current_head` | `de2feaa35fa9060a771da843e811c396624352a6` | `de2feaa…` | ✅ |
| 3 | `de2feaa is ancestor of HEAD` | `YES_ANCESTOR` (trivially — HEAD == de2feaa) | true | ✅ |
| 4 | `master_hash` | `c147d015455017bc1d8420cbdbd813b3b8ec23ce` | `c147d01…` | ✅ |
| 5 | `phase_a0_1r_tag_hash` | `3cd1bece14a7f4564d14d630568697c48cfd8385` | `3cd1bec…` (matches memory record `project_phase_a0_1r_2026_07_17.md`) | ✅ |
| 6a | `staged_files` | (none) | (none) | ✅ |
| 6b | `modified_files` | (none) | (none) | ✅ |
| 6c | `untracked_files` | 50 pre-existing audit artifacts under `docs/audit/`, `docs/corti_parity/phase7_gate13a/`, `reports/comprehensive-audit/**`, `reports/phase6/`, `reports/phase7/`, `scripts/audit/` | unchanged from session start | ✅ |

**Result**: `BASELINE_VERIFIED`. No `PARTIAL_BLOCKED_BY_INVALID_GATE2_BASELINE`.

---

## §2. Gate 2 carry-over tests re-run (item 7)

Re-run from clean worktree at HEAD = `de2feaa`.

| Suite | File | Tests | PASS | FAIL |
|---|---|---:|---:|---:|
| Tenancy guard unit | `backend/tests/unit/app/test_tenancy_guard.py` | 11 | 11 | 0 |
| Org isolation API | `backend/tests/test_api/test_a1a_gate2_org_isolation.py` | 16 | 16 | 0 |
| **Total** | | **27** | **27** | **0** |

All 27 Gate 2 carry-over tests pass. Fail-closed policy at write time,
`MODERN` / `MODERN_SYSTEM` classification on new writes, and 16
negative org-isolation behaviors remain green.

---

## §3. Migration 016 state (item 8)

```
$ sqlite3 backend/data/icoder.db "SELECT * FROM alembic_version"
016
```

- `alembic_version = '016'` — Gate 2 migration is head.
- Migration 016 file (`backend/alembic/versions/016_tenancy_classification.py`)
  is **untouched**. Gate 3.1 will add migration **017** alongside it, per
  charter §3.1 "不得修改 Migration 016".
- The downgrade path (lines 177–189) explicitly declines to undo the
  organization_id backfill.

---

## §4. Historical NULL classification — actual counts (items 9–12)

Migration 016 docstring claims (data/icoder.db, 2026-07-17):

| | run_history | audit_logs | total |
|---|---:|---:|---:|
| Pre-Gate-2 NULL | 235 | 201 | 436 |
| → `LEGACY_TENANT_KNOWN` (backfilled) | 230 | 200 | 430 |
| → `LEGACY_TENANT_UNKNOWN` (still NULL) | 5 | 1 | 6 |

Recomputed directly from `backend/data/icoder.db` (2026-07-18):

| tenancy_classification | run_history | audit_logs | total |
|---|---:|---:|---:|
| `MODERN` | 5 | 32 | 37 |
| `LEGACY_TENANT_KNOWN` | 230 | 200 | 430 |
| `LEGACY_TENANT_UNKNOWN` | 5 | 1 | 6 |
| `QUARANTINED` | 0 | 0 | 0 |
| **Total rows** | **240** | **233** | **473** |

| Metric | Migration 016 claim | Recomputed | Match |
|---|---:|---:|---|
| 9. Total classified records | 473 | 473 | ✅ |
| 10. Historical NULLs (pre-Gate-2) | 436 (235+201) | 436 (235+201) | ✅ |
| 11. Backfilled as `LEGACY_TENANT_KNOWN` | 430 (230+200) | 430 (230+200) | ✅ |
| 12. Remaining `LEGACY_TENANT_UNKNOWN` | 6 (5+1) | 6 (5+1) | ✅ |

Numbers are coherent. **However**, §5 below shows that the 430
"LEGACY_TENANT_KNOWN" rows are **inferred, not verified** — the
classification name overstates the evidence.

---

## §5. Attribution evidence strength (items 13–17)

### 13. Multi-org users

```sql
SELECT user_id, COUNT(DISTINCT organization_id)
FROM organization_members
GROUP BY user_id
HAVING COUNT(DISTINCT organization_id) > 1
```

**Result: 0 multi-org users.** All 45 users currently have exactly 1
membership each (45 memberships / 45 distinct users / 42 orgs).

### 14. Records backfilled via "latest membership" heuristic only

Per Migration 016 §3b/4b, the backfill picks
`organization_members.organization_id` ordered by
`organization_members.created_at DESC LIMIT 1`.

| Table | Rows backfilled this way | Rows with stronger evidence (api_client / session / context / request) |
|---|---:|---:|
| `run_history` (`LEGACY_TENANT_KNOWN`) | 230 | **0** |
| `audit_logs` (`LEGACY_TENANT_KNOWN`) | 200 | n/a (audit rows don't carry these columns) |
| **Total** | **430** | **0** |

**Every one of the 430 backfilled rows has ZERO strong evidence.** All
of them rest solely on the "user's most recent membership" heuristic.
None of the 230 legacy runs carries an `api_client_id`,
`embedded_app_id`, `session_id`, `context_id`, or `request_id` that
could confirm or refute the inferred org.

### 15. Membership created_at later than Run/Audit created_at

```sql
SELECT COUNT(*)
FROM run_history rh
JOIN organization_members om ON om.user_id = rh.user_id
WHERE rh.tenancy_classification = 'LEGACY_TENANT_KNOWN'
  AND om.created_at > rh.created_at
```

**Result: 0 runs, 0 audits.** No current row has a temporal conflict.
This is comforting for the *current* dataset but says nothing about
future state: if a user is invited to a second org tomorrow, every
historical run will silently re-attribute to that new org on the next
re-migration, with no audit trail.

### 16. Strong-evidence count (api_client / embedded_app / session / context / request)

| Classification | api_client_id | embedded_app_id | session_id | context_id | request_id |
|---|---:|---:|---:|---:|---:|
| `LEGACY_TENANT_KNOWN` (230) | 0 | 0 | 0 | 0 | 0 |
| `LEGACY_TENANT_UNKNOWN` (5)  | 0 | 0 | 0 | 0 | 0 |
| `MODERN` (5)                 | 0 | 0 | 0 | **5** | 0 |

Only the 5 MODERN runs carry any correlation id at all (`context_id`),
and those rows already have a non-null `organization_id` set at write
time. The 235 legacy runs have **no request-level evidence** that
survives.

### 17. Ambiguous candidates

**Result: 0** — but only because the current dataset has zero
multi-org users (item 13). The Migration 016 heuristic
(`ORDER BY created_at DESC LIMIT 1`) returns a single deterministic
org per user even when the user has multiple memberships, so under the
current implementation, "ambiguous" is a state that **cannot be
recorded** — it would be silently resolved to the latest membership.

This is the core defect Gate 3.1 must close: the schema has no way
to express "this row's org is uncertain", and the migration has no
way to express "I guessed between two candidates".

---

## §6. The 5 UNKNOWN runs and 1 UNKNOWN audit

```sql
-- run_history LEGACY_TENANT_UNKNOWN (5 rows)
c92cdaca124b  user_id=NULL  agent_id=medical-coding-agent     2026-07-11T00:24:10.387409+00:00
a9c4683dda63  user_id=NULL  agent_id=code-validation-agent    2026-07-11T00:24:10.418829+00:00
fea5cb40b53d  user_id=NULL  agent_id=note-completeness-agent  2026-07-11T00:24:10.452096+00:00
f09a286a784a  user_id=NULL  agent_id=drg-analyzer             2026-07-11T00:24:10.475552+00:00
e4efaf6241fb  user_id=NULL  agent_id=evidence-extractor       2026-07-11T00:24:10.495716+00:00

-- audit_logs LEGACY_TENANT_UNKNOWN (1 row)
b78a1119b536  user_id=NULL  username=NULL  action=api_client.authentication_rejected
                                              resource_type=api_client
                                              2026-07-17 14:17:23
```

All 5 runs have **NULL `user_id`** and NULL every other correlation
field — there is no candidate org to attribute them to. All 5 were
seeded in the same ~100 ms window on 2026-07-11 and look like smoke-test
artifacts. The single UNKNOWN audit is a security event
(`api_client.authentication_rejected`) which by nature has no
authenticated user — it should be `MODERN_SYSTEM`, not
`LEGACY_TENANT_UNKNOWN`. Gate 3.1 will need to reclassify this row.

---

## §7. SSE Event Endpoint auth chain (item 18)

File: `backend/app/api/runs.py:369–497` (`stream_run_events`).

```
Client → GET /api/v1/runs/{run_id}/events?token=<signed>
       ↓
[1] ?token required → else 401 TRACE_TOKEN_REQUIRED
       ↓
[2] verify_trace_token(token, expected_run_id=run_id)
       • HMAC-SHA256 signature
       • exp check
       • TraceTokenRunMismatch if token.r != URL.run_id
       • TraceTokenOrgMismatch ONLY if BOTH token.o AND
         expected_organization_id are non-empty
       ↓ returns TraceTokenClaims{run_id, organization_id, api_client_id, exp}
[3] store = get_default_store()  ← settings.RUNTRACE_STORE
       ↓
[4] IF hasattr(store, "get_run_scoped"):
       events = store.get_run_scoped(run_id, claims.organization_id or None)
    ELSE:
       events = store.get_run(run_id)  ← org-blind fallback
       ↓
[5] IF not events: 404 TRACE_NOT_FOUND
       ↓
[6] StreamingResponse(text/event-stream)  ← emits to client
```

**A1A-G2-F04 (carry-over, OPEN)**: the SSE handler does NOT cross-check
`claims.organization_id` against `RunHistory.organization_id` for that
run_id. Compare with the partner `/trace` handler at runs.py:329–336,
which **does** perform this cross-check (returning 403 on mismatch).

Concretely:
- Token issuance (`_trace_url_for` → `build_trace_url` at agent_run.py:215)
  binds the token to the *issuer's* org, which the issuer reads from
  auth context at run start.
- If that org is wrong at issuance time (e.g., a Console user without
  `org_id` in JWT, or a partner client_credentials token with empty
  `org_id`), the token is HMAC-valid but bound to the wrong org.
- The SSE handler trusts `claims.organization_id` and asks
  `get_run_scoped` to filter by it. `DbRunTraceStore.get_run_scoped`
  (run_trace.py:305–321) returns `[]` if the run's events all have a
  different `organization_id`, which yields 404 — but the run *does*
  exist, and the empty result might also mean "no trace captured",
  which is a different condition with different operational meaning.
- Worse: if the run's trace events have NULL `organization_id`
  (historical rows; see §8), `get_run_scoped` returns them when the
  caller passes `organization_id=None`. The InMemoryRunTraceStore
  (run_trace.py:199–201) returns all events regardless of the
  `organization_id` argument.

Fix target at Gate 3.4: add a `RunHistory.organization_id` cross-check
**before** the StreamingResponse is constructed, mirroring the
partner /trace path. On mismatch return 404 (not 403) to avoid
existence leak.

---

## §8. Console RunTrace auth chain (item 19)

Files:
- Endpoint: `backend/app/api/run_trace.py:42–94` (`_get_run_trace_impl`)
- Middleware: `backend/app/middleware/tenant_extractor.py:58–116`
  (`TenantHeaderMiddleware`)
- Store query: `DbRunTraceStore.get_run_scoped` at
  `run_trace.py:305–321`.

```
Console SPA → GET /api/runtime/runs/{run_id}/trace (no ?token=)
            ↓
[1] TenantHeaderMiddleware.dispatch
       • reads Tenant-Name or X-Tenant header → request.state.tenant_name
       • IF header AND bearer JWT both present:
           header must equal JWT.org_id else 400 tenant_header_mismatch
       • IF cloud mode AND no header: 400 tenant_header_required
       ↓
[2] get_run_trace handler
       • org_id = get_request_tenant(request)  ← FROM HEADER, not JWT sub
       • store = get_default_store()
       ↓
[3] IF hasattr(store, "get_run_scoped"):
       events = store.get_run_scoped(run_id, org_id_from_header)
    ELSE:
       events = store.get_run(run_id)  ← org-blind fallback
       ↓
[4] IF not events: 404
       ↓
[5] Return timeline
```

**A1A-G2-F05 (carry-over, OPEN)**. Three issues:

1. The handler reads org from `request.state.tenant_name` (set by
   middleware from the Tenant-Name header), NOT from the authenticated
   user's JWT `org_id` claim. The middleware cross-checks header vs
   JWT only when **both** are present; in local mode without a JWT,
   the header is trusted as-is.
2. There is no `RunHistory.organization_id` cross-check. The handler
   trusts the header-derived org and asks the store to filter by it.
   A run that exists cross-org simply returns 404 — which is correct
   for isolation but conflates "wrong org" with "no trace captured".
3. If `request.state.tenant_name` is None (e.g., local mode without
   header) and the store implements `get_run_scoped`,
   `DbRunTraceStore.get_run_scoped` treats `organization_id=None` as
   "no filter" (run_trace.py:318 — `if organization_id is not None`)
   and returns ALL events for that run_id regardless of owning org.

Fix target at Gate 3.5: store query interface must require an
`AuthenticatedTenantContext` (not a raw string); endpoint reads org
from the authenticated principal, not from a header; add
`RunHistory.organization_id` cross-check; on mismatch return 404 with
no existence leak.

---

## §9. Trace Store configuration and defaults (item 20)

- `backend/app/config.py:156`:
  `RUNTRACE_STORE: str = "memory"`  ← **default is memory**.
- `get_default_store` (`run_trace.py:339–354`) returns
  `InMemoryRunTraceStore` unless `settings.RUNTRACE_STORE == "db"`.
- `DbRunTraceStore.append` (`run_trace.py:243–276`) wraps the
  SQLAlchemy insert in `try / except Exception: logger.error(...)`.
  **Persistence failures are silently swallowed.** Charter Gate 3.3
  §6 explicitly forbids this: "Trace 写入失败时,不得静默忽略".
- `InMemoryRunTraceStore.get_run_scoped` (run_trace.py:199–201)
  ignores its `organization_id` argument and returns all events —
  "treat as dev mode". This is a tenant-isolation hole if the memory
  store is ever used outside dev.
- No `RunHistory.trace_capture_status` field exists. Charter Gate 3.3
  §5 requires `CAPTURED | PARTIAL | TRACE_NOT_CAPTURED |
  PERSISTENCE_FAILED | NOT_APPLICABLE`. Historical runs with no
  trace (i.e., all 240 current rows — see item 21) cannot be marked.

**Charter Gate 3.3 fail-closed policy (target state)**:
- `development`: memory allowed
- `test`: memory or DB fixture
- `staging`: DB required
- `production`: DB required

Current code allows memory in all four modes with no env-based gate.

---

## §10. run_trace_events table state (item 21)

```sql
SELECT COUNT(*), SUM(CASE WHEN organization_id IS NULL THEN 1 ELSE 0 END)
FROM run_trace_events
→ 0, 0
```

**The `run_trace_events` table is empty.** Every one of the 240
historical `run_history` rows has **no persisted trace events**.

Charter Gate 3.3 §5 is explicit: historical runs without original
trace data must be marked `TRACE_NOT_CAPTURED`. Gate 3 must NOT
fabricate synthetic stage events from `RunHistory.output_summary`
or similar to make the timeline render. The current state — empty
trace table — is the cleanest possible starting point for that rule:
no fabrication has happened yet, and we add the `trace_capture_status`
column to record why.

Schema gaps in `run_trace_events` relative to Charter Gate 3.3 §3:
- No `event_id` (uniqueness)
- No `sequence_number` (per-trace ordering)
- No `event_type` / `stage_name` distinction
- No `started_at` / `completed_at` (only `ts` + `duration_ms`)
- No `provider` / `model` / `runtime_mode` columns (currently stashed
  inside `safe_metadata_json`)
- No `payload_classification` / `payload_redaction_status`
- `organization_id` is nullable; no FK or check constraint enforcing
  that it matches the owning `run_history.organization_id`.

---

## §11. Audit Log action coverage matrix (item 22)

Observed actions in `audit_logs` (233 rows):

| Action | Count |
|---|---:|
| `user.login` | 160 |
| `user.register` | 40 |
| `preview_session.create` | 19 |
| `preview_session.exchange` | 7 |
| `preview_session.revoke` | 6 |
| `api_client.authentication_rejected` | 1 |
| **(other user.* / org.* / encounter.* actions exist as code paths but not as rows in this DB)** | |

Source code declares additional actions (not yet exercised in this DB):
`user.login_failed`, `user.password_reset`, `user.password_change`,
`user.revoke_tokens`, `org.create`, `org.invite`, `org.remove_member`,
`org.update_role`, `org.switch`, `encounter.create`,
`encounter.create_text`, `encounter.delete`.

**Material actions NOT audited at all** (Gate 3.6 §1 carry-over):

| Missing action | Source | Why it matters |
|---|---|---|
| `trace.read.success` | partner /trace + Console /trace | Detects mass-scraping of run traces |
| `trace.read.denied` | partner /trace + Console /trace | Cross-org attempt indicator |
| `sse.denied` | /api/v1/runs/{id}/events | Cross-org stream attempt |
| `api_client.rotate` | /api/clients/{id}/rotate | Secret lifecycle |
| `run.cancel` | /api/v1/runs/{id} (POST cancel) | Lifecycle forensics |
| `run.timeout` | run_lifecycle.py | Distinguish from cancel |
| `run.complete` / `run.failed` | run_lifecycle.record_run_final | Today only `run_history` row records completion — no audit |
| `idempotency.dedup` | idempotency_service replay path | Replay detection forensics |
| `context.clear` (patient.context.cleared / session.cleared) | embedded.py | Phase 6 Gate 2 events — never audited |
| `api_client.authentication_rejected` in cloud mode | oauth._emit_auth_rejection | Currently swallows the tenancy violation via except → silent miss |

---

## §12. allow_null_org=True call sites (item 23)

Production call sites passing `allow_null_org=True`:

| File | Line | Caller | Production? |
|---|---|---|---|
| `app/middleware/tenancy_guard.py` | 84, 129 | function default param | (definition) |
| `app/middleware/audit.py` | 32, 45, 66 | `log_action` passthrough | (definition) |
| `tests/test_api/test_a1a_gate2_org_isolation.py` | 499 | test fixture | ❌ test |
| `tests/unit/app/test_tenancy_guard.py` | 72, 98, 99 | test fixture | ❌ test |

**Zero production callers pass `allow_null_org=True`.** This means
`MODERN_SYSTEM` classification is reachable in theory
(tenancy_guard.py:148) but no production audit event is currently
written as `MODERN_SYSTEM`. The 1 row that *should* be `MODERN_SYSTEM`
(`api_client.authentication_rejected` on 2026-07-17) was written
**before** Gate 2 and got classified as `LEGACY_TENANT_UNKNOWN`
because its `user_id` is NULL and Migration 016's last-membership
heuristic found no candidate.

Charter Gate 3.6 §3 requires that "System Event 不能通过通用布尔参数任意绕过
组织门禁". The current `allow_null_org` boolean IS exactly such a
generic bypass. Gate 3.6 will need to either (a) replace it with an
`AuditScope = tenant | system` enum that requires an out-of-band
`system_audit()` entry point, or (b) enumerate the allowed
`action ∈ {SYSTEM_ACTIONS}` allowlist at the `log_action` boundary.

---

## §13. Patient / Encounter / CDI — actually verified in Gate 2? (item 24)

**Answer: NO — not verified by Gate 2.**

The Gate 2 closure report (`A1A_GATE2_CLOSURE.md` lines 24–27 and
260–261) explicitly **defers** Patient / Encounter / CDI org-scoping
to Phase 5 Track D:

> 3. Patient A and Patient B do not cross-reference (PHI isolation).
>    ✅ Already enforced at the encounter / patient layer via the
>    `current_org` dependency (out of Gate 2 scope per survey §7.2;
>    Phase 5 Track D owns the encounter layer).
>
> …
>
> - CDI table org-scoping (Phase 5 Track D).
> - Patient/Encounter org scoping (Phase 5 Track D).

Direct DB inspection contradicts the "already enforced" claim:

| Table | Rows | NULL org_id | Has org_id column? |
|---|---:|---:|---|
| `encounters` | 10 | **10 (100%)** | Yes (nullable) |
| `cdi_cases` | 718 | **718 (100%)** | Yes (nullable) |
| `cdi_documentation_gaps` | 1310 | n/a | **No org_id column** (must join via `case_id → cdi_cases.organization_id`) |
| `cdi_provider_queries` | 443 | n/a | **No org_id column** (same) |
| `cdi_clinician_responses` | 0 | n/a | n/a |
| `cdi_document_versions` | 0 | n/a | n/a |
| `clinical_evidences` | 0 | n/a | n/a |

Every populated row in `encounters` and `cdi_cases` has NULL
`organization_id` — not because isolation is enforced, but because no
write path stamps org_id onto these rows. The `current_org` dependency
exists (`app/middleware/auth.py:149`) and is used by `tickets.py`,
but the CDI / encounter write paths evidently do not propagate
`current_org.id` into the row.

Gate 3.0 takes this as **confirmed scope deferral, not verified
isolation**. Gate 3 itself does not need to close it (per the charter's
"边界" list, CDI/Patient/Encounter org-scoping remains Phase 5 Track
D's responsibility), but Gate 3's final verdict must not inherit
Gate 2's "✅ already enforced" claim — it isn't.

---

## §14. Files Gate 3 needs to modify (item 25)

(Indicative list — finalized per gate. Forbidden zones per charter §3
are NOT in this list: no Agent / Expert / Tool / Runtime / prompt /
medical coding output / CDI output / new master commits / Gate 2
reports / Phase A0.1R tag.)

### Backend — code

| File | Why |
|---|---|
| `backend/app/middleware/tenancy_guard.py` | Add `AuditScope` enum or system-action allowlist to replace free-form `allow_null_org` (Gate 3.6) |
| `backend/app/middleware/audit.py` | Add `trace.read.success/denied`, `sse.denied`, `run.cancel/timeout/complete/failed`, `idempotency.dedup`, `context.clear`, `api_client.rotate` actions; require `AuditScope` (Gate 3.6) |
| `backend/app/api/runs.py` | SSE handler adds `RunHistory.organization_id` cross-check + audit on denial (Gate 3.4); partner /trace returns 404 not 403 on cross-org (Gate 3.5) |
| `backend/app/api/run_trace.py` | Console /trace reads org from authenticated principal; adds `RunHistory.organization_id` cross-check (Gate 3.5) |
| `backend/app/icoder/agent_runtime/orchestrator/run_trace.py` | `get_default_store` env-gated (memory only in development); fail-closed if DB store misconfigured; remove silent except in `DbRunTraceStore.append` (Gate 3.3) |
| `backend/app/models/run_trace.py` | Add `event_id`, `sequence_number`, `event_type`, `stage_name`, `started_at`, `completed_at`, `provider`, `model`, `runtime_mode`, `payload_classification`, `payload_redaction_status`; add UNIQUE constraint (Gate 3.3 / 3.7) |
| `backend/app/models/run_history.py` | Add `trace_capture_status` column (Gate 3.3) |
| `backend/app/models/audit_log.py` | Add `audit_scope` (`tenant | system`), `tenancy_attribution_source`, `tenancy_attribution_confidence` (Gates 3.1 / 3.6) |
| `backend/app/services/run_lifecycle.py` | Stamp `trace_capture_status = CAPTURED / PARTIAL / PERSISTENCE_FAILED / TRACE_NOT_CAPTURED` (Gate 3.3) |
| `backend/app/services/idempotency_service.py` | Emit `idempotency.dedup` audit on replay (Gate 3.6) |
| `backend/app/services/trace_token.py` | Tighten `TraceTokenOrgMismatch` to enforce whenever `claims.organization_id` is set, not only when caller also sets `expected_organization_id` (Gate 3.4) |
| `backend/app/api/oauth.py` | `_emit_auth_rejection` route through `system_audit` not `log_action` (Gate 3.6) |
| `backend/app/api/agent_run.py` | Token issuance asserts run_history.organization_id ↔ issuer org match (Gate 3.4) |
| New: `backend/app/services/legacy_tenancy_attribution.py` | Evidence-based attribution engine used by migration 017 + runtime (Gate 3.1) |
| New: `backend/app/services/tenant_read_policy.py` | Quarantine + 404-without-leak helper (Gate 3.2) |
| New: `backend/app/services/system_audit.py` | Distinct entry point for `MODERN_SYSTEM` writes (Gate 3.6) |

### Backend — migrations

| File | Why |
|---|---|
| New: `backend/alembic/versions/017_legacy_tenancy_reconciliation.py` | Re-classify 430 `LEGACY_TENANT_KNOWN` rows into `VERIFIED | INFERRED | AMBIGUOUS | UNKNOWN | QUARANTINED`; add attribution source/confidence fields; reclassify the 1 audit security event to `MODERN_SYSTEM` (Gate 3.1) |
| New: `backend/alembic/versions/018_run_trace_capture_status.py` | Add `run_history.trace_capture_status`; backfill existing rows to `TRACE_NOT_CAPTURED` (no synthetic events) (Gate 3.3) |
| New: `backend/alembic/versions/019_run_trace_events_rich_schema.py` | Add new columns + UNIQUE(event_id) + FK(org → organizations) + CHECK(org == owning RunHistory.organization_id where reproducible) (Gate 3.3 / 3.7) |
| New: `backend/alembic/versions/020_audit_log_scope_and_attribution.py` | Add `audit_scope`, `tenancy_attribution_source`, `tenancy_attribution_confidence` (Gates 3.1 / 3.6) |

(Migration 016 stays untouched. Charter §3.1.)

### Backend — tests

| File | Why |
|---|---|
| New: `backend/tests/unit/app/test_legacy_tenancy_attribution.py` | 15-case attribution test matrix (Gate 3.8 A) |
| New: `backend/tests/test_api/test_a1a_gate3_quarantine.py` | Quarantine read-policy tests (Gate 3.8 B) |
| New: `backend/tests/test_api/test_a1a_gate3_trace_persistence.py` | DB persistence + restart + cross-worker (Gate 3.8 C) |
| New: `backend/tests/test_api/test_a1a_gate3_tenant_isolation.py` | SSE + Console /trace negative tests (Gate 3.8 D) |
| New: `backend/tests/test_api/test_a1a_gate3_audit_coverage.py` | Material action coverage tests (Gate 3.8 F) |
| Existing: extend Gate 2 fixtures | Verify no regression |

### Reports

| File | Why |
|---|---|
| New: `reports/phase-a1a/A1A_GATE3_1_LEGACY_TENANCY_RECONCILIATION.md` | Pre-migration + post-migration report (Gate 3.1 §5) |
| New: `reports/phase-a1a/A1A_GATE3_FINAL_REPORT.md` | Gate 3 consolidated report (Gate 3.9) |
| New: `reports/phase-a1a/A1A_GATE3_EVIDENCE_MANIFEST.json` | Evidence manifest update |
| New: `reports/phase-a1a/A1A_GATE3_BROWSER_EVIDENCE/` | Playwright screenshots, console log, sanitized HAR |
| (Existing Gate 2 reports are NOT modified — charter §3 禁止) |

### Frontend

None. Charter §10.3 "Frontend only submits run_id; org from session".
The Console RunTrace page already submits only `run_id`; no change
needed. (Verification: grep frontend for `tenant_name` injection.)

---

## §15. Interim verdict (item 26)

```
INTERIM_VERDICT_A1A_GATE_3_0 =
  PARTIAL_BASELINE_VERIFIED_CARRYOVER_OPEN
```

**What is verified**:
- Git baseline (branch / HEAD / master / A0.1R tag) matches the
  charter's entry contract.
- All 27 Gate 2 carry-over tests pass from clean worktree at HEAD.
- Migration 016 is head; backfill counts (473 / 436 / 430 / 6) match
  the migration docstring and the Gate 2 closure report.
- F04 (SSE) and F05 (Console RunTrace) carry-over defects are
  reproduced and localized to specific files / line ranges.

**What is NOT verified**:
- The 430 rows classified `LEGACY_TENANT_KNOWN` are inferred via
  "latest membership" only. **Zero** of them carry request-level
  evidence (`api_client_id` / `session_id` / `context_id` /
  `request_id`). The classification name (`_KNOWN`) overstates the
  evidence and must be split into `_VERIFIED` / `_INFERRED` /
  `_AMBIGUOUS` at Gate 3.1.
- The 1 security audit row (`api_client.authentication_rejected`)
  is mis-classified as `LEGACY_TENANT_UNKNOWN`. It is actually a
  system-scope event (`MODERN_SYSTEM`) with no owning tenant.
- Patient / Encounter / CDI org-scoping is **not** verified by
  Gate 2 — it is explicitly deferred to Phase 5 Track D, and 100%
  of populated `encounters` + `cdi_cases` rows have NULL org_id.
  The Gate 2 closure's "✅ already enforced via current_org" claim
  is contradicted by the data.
- `run_trace_events` is empty. Every historical run is effectively
  `TRACE_NOT_CAPTURED`. No fabrication has happened yet — Gate 3.3
  must add the `trace_capture_status` field so it stays that way.
- `RUNTRACE_STORE` defaults to `"memory"`; `DbRunTraceStore.append`
  silently swallows persistence errors. Charter Gate 3.3 fail-closed
  policy is not yet implemented.
- The `allow_null_org=True` boolean is a free-form bypass; zero
  production callers use it today, but it remains available as a
  future regression vector.

**Hard checkpoints status**:
- Checkpoint A (Gate 2 carry-over truth): **OPEN** — Gate 2 numbers
  verified, but the "LEGACY_TENANT_KNOWN" naming + Patient/Encounter/
  CDI "✅ already enforced" claim both need addendum or Gate 3 fix.
- Checkpoint B (Historical tenant attribution): **NOT STARTED** —
  Gate 3.1.
- Checkpoint C (Tenant read isolation): **NOT STARTED** — Gates 3.2
  + 3.4 + 3.5.
- Checkpoint D (Trace persistence): **NOT STARTED** — Gate 3.3.

**Permitted verdicts remaining in scope for Gate 3 final**:
- `PASS_A1A_GATE3_TENANT_READ_ISOLATION_AND_TRACE_PERSISTENCE_VERIFIED`
- `PASS_WITH_*` (with explicit open-item list)
- `PARTIAL_BLOCKED_*`

**Forbidden verdicts** (charter §22):
`PRODUCTION_READY`, `HOSPITAL_DEPLOYMENT_READY`,
`HOSPITAL_PILOT_READY`, `PARTNER_PRODUCTION_READY`,
`SECURITY_CERTIFIED`, `CLINICALLY_VALIDATED`,
`ALL_TENANT_ISOLATION_COMPLETE`, `ALL_AUDIT_GAPS_RESOLVED`,
`ZERO_DEFECTS`.

---

## §16. Pre-Gate-3.1 guardrails (acknowledged)

Per charter §23 "Gate 3.0 完成前", Gate 3.0 has NOT:
- Modified business code ✅
- Executed Migration 017 ✅ (does not yet exist)
- Modified Gate 2 historical reports ✅
- Started Trace data backfill ✅
- Marked historical inferred attribution as Verified ✅
- Inherited Gate 2's unconditional platform-wide isolation conclusion ✅
  (item 24 above explicitly contradicts part of it)

Gate 3.1 begins next.
