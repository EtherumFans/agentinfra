# Phase A1A Gate 4.2 — Clinical Data Tenant + Context Boundary

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 4.1 (`A1A_GATE4_1_PHI_INVENTORY_CLASSIFICATION_THREAT_MODEL.md`)
**Successor**: Gate 4.3 (Live-path redaction + minimum necessary data)

Charter §4.2: close three PHI carry-overs and one new structural
risk on the clinical data surface.

| Carry-over | Origin | Gate 4.2 fix |
|---|---|---|
| `GATE3R_011` | Gate 3R — frontend did not send `Tenant-Name` | Make JWT `org_id` authoritative; `Tenant-Name` becomes hint-only. Frontend axios interceptor attaches the header from `useAuthStore.currentOrgId`. |
| `GATE3_014` | Gate 3.6 — `assert_org_scope` refactor (17 callers) | Ledger correction: the function **does not exist**. Re-scoped OBSERVED → CLOSED with no refactor. Actual helpers verified present. |
| `GATE3_015` | Gate 3.7 — encounters/documents/cdi_cases CHECK constraints deferred | Migration 021 backfills NULL/empty organization_id and adds NOT NULL + CHECK on all three tables. SQLAlchemy models updated to `nullable=False`. |

---

## §1. GATE3R_011 — Frontend did not send `Tenant-Name`

### §1.1 Inventory recap (from Gate 4.0 §5.1)

The original `TenantHeaderMiddleware` derived the tenant from the
`Tenant-Name` (or `X-Tenant`) header. In cloud mode the header was
mandatory; in local-dev mode it was optional, and a missing header
silently bypassed the cross-check. The console trace path
`/api/runtime/runs/{id}/trace` reads `request.state.tenant_name`;
when it was missing, the org filter was skipped and rows from
other tenants could leak. The partner trace path
`/api/v1/runs/{id}/trace` used `current_org.id` from the JWT,
creating an asymmetry the Gate 3R.6 addendum flagged but did not
close.

### §1.2 Authoritative-source fix

`backend/app/middleware/tenant_extractor.py` now derives
`request.state.tenant_name` from the JWT `org_id` claim, never
from the header. The header is recorded separately on
`request.state.tenant_header_hint` for audit-log scoping.

Behaviour matrix:

| State | Resolved org | Rejection |
|---|---|---|
| JWT present + header matches JWT | `jwt_org_id` | — |
| JWT present + header mismatches JWT | — | `400 tenant_header_mismatch` |
| JWT absent + cloud mode | — | `400 tenant_header_required` |
| JWT absent + local mode + `ICODER_SINGLE_TENANT_ORG_ID` set | configured org (header disagreement logged as warning) | — |
| JWT absent + local mode + `ICODER_SINGLE_TENANT_ORG_ID` empty | — | `400 tenant_context_required` |
| Tenant-exempt path (`/api/health`, `/docs`, `/api/oauth/`) | header hint or `None` | — |

The console trace path now reads the JWT-derived
`request.state.tenant_name`, so the asymmetry with the partner
path is closed: both paths use the JWT org.

### §1.3 Frontend wiring

`frontend/src/services/api.ts` axios request interceptor now
attaches `Tenant-Name: <orgId>` from `useAuthStore.currentOrgId`
on every request. The header is a non-authoritative hint; the
backend still validates it against the JWT and rejects with
`tenant_header_mismatch` if they disagree.

This wiring exists for two reasons:

1. **Audit log scoping** — backend logs the header alongside the
   JWT value so cross-claim mismatches are visible in forensics.
2. **Local-dev single-tenant mode** — when no JWT is present
   (e.g. unauthenticated health pings), the backend uses the
   header to record which tenant the caller *thought* they were
   hitting.

### §1.4 Tests

`tests/test_api/test_a1a_gate4_2_clinical_tenant_boundary.py`
exercises the new behaviour matrix:

- `test_cloud_mode_rejects_unauthenticated_request` — monkeypatches
  `ICODER_DEPLOYMENT_MODE=cloud` and asserts 400
  `tenant_header_required` on a request with no JWT.
- `test_jwt_authoritative_when_header_mismatches` — sends a JWT
  with `org_id=org_default1` plus `Tenant-Name: org-different`,
  asserts 400 `tenant_header_mismatch`.
- `test_tenant_header_hint_only_when_jwt_absent_local_mode` —
  local mode, no JWT, hits exempt path `/api/health`, asserts 200.
- `test_frontend_api_ts_attaches_tenant_name_header` — static
  source check that `api.ts` references `Tenant-Name`,
  `useAuthStore`, and `currentOrgId`.

---

## §2. GATE3_014 — `assert_org_scope` ledger correction

### §2.1 Inventory finding (from Gate 4.0 §5.2)

Gate 3 and Gate 3R closure reports reference `assert_org_scope`
as a refactor target with 17 callers. **The function does not
exist anywhere in `backend/app/`.** The 17-caller count is stale.

The actual tenant-scope helpers are:

| Helper | Location | Callers |
|---|---|---|
| `require_org_membership` | `app/middleware/auth.py:176` | 2 |
| `require_org_role(*roles)` factory | `app/middleware/auth.py:197` | 1 (organizations.py) |
| `assert_tenancy_for_write(organization_id, table_name)` | `app/services/run_lifecycle.py` | ~5 |
| `get_current_organization` (FastAPI Depends) | `app/middleware/auth.py:149` | ~30 |

### §2.2 Re-scope decision

`GATE3_014` is **re-scoped OBSERVED → CLOSED** with no code
change. The "17 callers" claim is invalidated. The actual
asymmetry the original ledger text pointed at (console trace path
vs partner trace path) is closed by GATE3R_011's fix (§1 above):
both paths now read the JWT-derived org.

### §2.3 Test

`test_assert_org_scope_does_not_exist` walks `backend/app/**/*.py`
via `ast` and asserts zero `def assert_org_scope` definitions.

`test_actual_tenant_helpers_exist` confirms the real helpers are
present and callable.

---

## §3. GATE3_015 — Clinical tables organization constraints

### §3.1 Inventory finding (from Gate 4.0 §5.3)

| Model | Column | Was nullable? | Had CHECK? |
|---|---|---|---|
| `Encounter.organization_id` | `app/models/encounter.py:12` | YES | no |
| `Document.organization_id` | `app/models/encounter.py:36` | YES | no |
| `CDICaseModel.organization_id` | `app/models/cdi_case.py:60` | YES | no |

Pre-migration row counts on `data/icoder.db` (2026-07-19):

```
encounters  10 NULL → backfilled to org_default1
documents   22 NULL → backfilled to org_default1
cdi_cases  718 NULL → backfilled to org_default1
```

### §3.2 Migration 021

`backend/alembic/versions/021_clinical_tables_tenant_not_null.py`:

1. **§1 Backfill** — for each of encounters/documents/cdi_cases,
   update rows where `organization_id IS NULL OR = ''` to the
   configured default org (env var
   `ICODER_BACKFILL_DEFAULT_ORG`, default `org_default1`).
2. **§2 NOT NULL + CHECK** — via `batch_alter_table` (SQLite-safe
   pattern): `alter_column nullable=False` plus
   `create_check_constraint` `chk_{table}_org_not_null`. The
   CHECK is structurally redundant with NOT NULL but exists as a
   second defence — NOT NULL can be silently dropped by a future
   `batch_alter_table` pass that forgets to re-add it; the CHECK
   is harder to remove accidentally.
3. **§3 Composite index** — `ix_{table}_org_created` on
   `(organization_id, created_at)` for the list-page access
   pattern. Defensive `try/except` skips the index if it already
   exists (true for `cdi_cases` post-Gate 2).

### §3.3 SQLAlchemy model update

The model declarations are updated to `nullable=False` so future
`alembic autogenerate` does not propose dropping the constraint:

- `Encounter.organization_id` (`app/models/encounter.py:12`)
- `Document.organization_id` (`app/models/encounter.py:36`)
- `CDICaseModel.organization_id` (`app/models/cdi_case.py:60`)

### §3.4 Local-mode configuration

`backend/app/config.py` adds `ICODER_SINGLE_TENANT_ORG_ID`
(default `org_default1`). Local-dev workflow unchanged.

### §3.5 Tests

- `test_migration_021_left_no_null_organization_id_in_clinical_tables`
  — asserts zero NULL/empty organization_id rows on the dev DB.
- `test_migration_021_added_check_constraint_on_clinical_tables`
  — asserts each table's CREATE TABLE statement contains the
  `chk_{table}_org_not_null` CHECK.
- `test_migration_021_blocks_null_insert_via_check` — on a temp
  DB, attempts to INSERT an Encounter row with NULL
  organization_id and asserts `sqlite3.IntegrityError`.
- `test_encounter_model_has_not_null_organization_id`,
  `test_document_model_has_not_null_organization_id`,
  `test_cdi_case_model_has_not_null_organization_id` — model-level
  nullable=False assertions.

### §3.6 Downstream CDI sub-tables

`DocumentationGapModel`, `ProviderQueryModel`,
`ClinicianResponseModel`, `DocumentVersionModel` have no direct
`organization_id` column. They inherit org transitively via
`case_id → cdi_cases.organization_id`. Gate 4.2 deliberately does
NOT denormalize org onto these sub-tables — the JOIN cost is
negligible at current scale, and the surface-area cost of
duplicating the column + re-checking consistency on every write
is higher than the benefit.

If a future hot path needs direct filter (e.g.
`cdi_provider_queries` scan under a single org), Gate 4.7 may
revisit. This deferral is recorded in the Issue Ledger.

---

## §4. New issue — `TENANT_OWNED_SYSTEM_AUDIT_ATTRIBUTION`

**Not closed by Gate 4.2.** Owned by Gate 4.7.

`system_audit()` (`app/services/system_audit.py:152`) always
writes `organization_id=None`. The 6 lifecycle emits Gate 3R.2
wired (`run.cancel`, `run.timeout`, `run.complete`, `run.failed`,
`idempotency.dedup`, `api_client.rotate`) currently emit via
`log_action(organization_id=...)` so they DO get tenant
attribution. But the `system_audit()` function itself has no
`organization_id` parameter — any future caller that routes a
tenant-owned business action through `system_audit()` loses
attribution.

Risk class: **P2 today** (no current caller leaks org), **P1
structural**. The function signature itself is the escape hatch.

Gate 4.7 will introduce a `tenant_owned_system_audit(organization_id,
action, ...)` helper that stamps
`tenancy_classification=MODERN` (not `MODERN_SYSTEM`) but emits
one of the 6 lifecycle actions. The classifier already recognises
these 6 as system-scope via `SYSTEM_AUDIT_ACTIONS`; the row's
`organization_id` is what differs.

---

## §5. Test report

```
pytest tests/test_api/test_a1a_gate4_2_clinical_tenant_boundary.py
     tests/test_api/test_a1a_gate2_org_isolation.py
     tests/test_api/test_a1a_gate3_2_tenant_read_policy.py
     tests/test_api/test_a1a_gate3_4_sse_tenant_isolation.py
     tests/test_api/test_a1a_gate3_5_console_trace_isolation.py
     tests/test_api/test_a1a_gate3_8_security_negative_consolidated.py
     tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py
     tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py
     tests/test_api/test_a1a_gate3r_3_trace_capture_profiles.py
     tests/test_api/test_a1a_gate3r_4_trace_event_identity.py
     tests/test_api/test_a1a_gate3r_5_migration_portability.py
     tests/test_api/test_a1a_gate3r_8_regression_security_negative.py

→ 150 passed in 196.30s
```

Frontend TypeScript check (`npx tsc --noEmit`) passes clean.

---

## §6. Files touched

### Code

| File | Change |
|---|---|
| `backend/app/middleware/tenant_extractor.py` | JWT-authoritative tenant derivation; `_single_tenant_org_id()` helper; new behaviour matrix docstring |
| `backend/app/config.py` | New `ICODER_SINGLE_TENANT_ORG_ID` setting (default `org_default1`) |
| `backend/app/models/encounter.py` | `Encounter.organization_id` + `Document.organization_id` → `nullable=False` |
| `backend/app/models/cdi_case.py` | `CDICaseModel.organization_id` → `nullable=False` |
| `frontend/src/services/api.ts` | Axios request interceptor attaches `Tenant-Name` from `useAuthStore.currentOrgId` |

### Migrations

| File | Change |
|---|---|
| `backend/alembic/versions/021_clinical_tables_tenant_not_null.py` | New. Backfill + NOT NULL + CHECK + composite index on encounters/documents/cdi_cases |

### Tests

| File | Change |
|---|---|
| `backend/tests/test_api/test_a1a_gate4_2_clinical_tenant_boundary.py` | New. 13 tests covering §1–§3 |
| `backend/tests/test_api/test_a1a_gate3_2_tenant_read_policy.py` | Fixture seeds `organization_id="org_default1"` on run_history + audit_logs rows |
| `backend/tests/test_api/test_a1a_gate3_5_console_trace_isolation.py` | `test_console_trace_passes_for_visible_modern` uses `org_default1` (was `org-A`) |
| `backend/tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py` | `test_console_trace_modern_row_still_served` uses `org_default1` (was `org-A`) |
| `backend/tests/test_api/test_a1a_gate3r_5_migration_portability.py` | Head assertions `020` → `021` |
| `backend/tests/test_api/test_a1a_gate3r_8_regression_security_negative.py` | Head assertion `020` → `021` |

### Docs

| File | Change |
|---|---|
| `reports/phase-a1a/A1A_GATE4_2_CLINICAL_DATA_TENANT_CONTEXT_BOUNDARY.md` | This closure report |

---

## §7. Forbidden list — re-confirmation

Gate 4.2 did NOT:

- Introduce any new Agent / Expert / Tool / Runtime
- Modify any Medical Coding / CDI / DRG-DIP prompt
- Touch real patient data (Migration 021 backfill operates on
  the dev DB only; production deploy must run the same migration
  with the deployment's actual default org)
- Verify on PostgreSQL (Migration 021 is SQLite-only-verified;
  PG syntax is identical — batch_alter_table compiles to
  `ALTER COLUMN SET NOT NULL` + `ADD CONSTRAINT` on PG)
- Push, PR, master commit, amend `b737eab`
- Use `git add -A`
- Issue any charter §22 forbidden verdict
- Close `TENANT_OWNED_SYSTEM_AUDIT_ATTRIBUTION` (deferred to 4.7)
- Add `organization_id` columns to CDI sub-tables (deferred; see §3.6)
- Remove or weaken the console trace / partner trace asymmetry
  protection — the fix preserves the existence-check distinction

---

## §8. Provisional verdict

```
PASS_A1A_GATE4_2_CLINICAL_DATA_TENANT_CONTEXT_BOUNDARY_VERIFIED
```

Three PHI carry-overs are closed (`GATE3R_011`, `GATE3_014`,
`GATE3_015`). One new structural risk
(`TENANT_OWNED_SYSTEM_AUDIT_ATTRIBUTION`) is documented and
deferred to Gate 4.7 with explicit owner. 150 A1A regression
tests pass; 13 new Gate 4.2 tests pass; frontend TypeScript clean.

Forbidden verdicts (charter §22) remain forbidden. This gate
issues neither `PASS_PRODUCTION_READY` nor `PASS_FULLY_VERIFIED`
nor `PASS_PHI_BOUNDED` — the PHI boundary has been enforced at
the tenant + clinical column level, but at-rest encryption,
live-path redaction, and regional residency are still pending
(Gates 4.3–4.5).

---

## §9. Coordination with Gate 4.3–4.9

| Sub-gate | Primary owner of | Carry-over input from 4.2 |
|---|---|---|
| 4.3 | Live-path redaction + minimum necessary data | `phi_redactor` is best-effort (not fail-closed); `safe_metadata` uses blacklist (not allowlist) |
| 4.4 | PHI at-rest protection + key lifecycle | No encryption at rest today; Migration 021 enforces org ownership but content remains plaintext |
| 4.5 | Provider egress + regional residency | `RuntimeDataPolicy` has no region field; LLMGateway has no per-provider region metadata |
| 4.6 | Browser + Embedded + Patient A/B | localStorage auth tokens; `icoder-textgen-templates` could carry user-input PHI |
| 4.7 | Retention + deletion + audit closure | `TENANT_OWNED_SYSTEM_AUDIT_ATTRIBUTION` (§4 above) |
| 4.8 | Full security regression + evidence closure | All |
| 4.9 | Commit + final verdict | All |

---

## §10. Next

Gate 4.3 — Live-path redaction + minimum necessary data.
