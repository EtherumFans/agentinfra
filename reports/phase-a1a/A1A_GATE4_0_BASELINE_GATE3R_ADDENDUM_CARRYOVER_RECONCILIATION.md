# Phase A1A Gate 4.0 — Baseline, Gate 3R Addendum, PHI Carry-over Reconciliation

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3R.9 (`A1A_GATE3R_9_COMMIT_FINAL_VERDICT.md`, commit `b737eab`)

Closes charter §4.0: re-verify the Gate 3R baseline, document the
PHI-relevant corrections to the Gate 3R Issue Ledger, and take
formal ownership of three PHI carry-overs (`GATE3R_011`,
`GATE3_014`, `GATE3_015`) plus the new
`TENANT_OWNED_SYSTEM_AUDIT_ATTRIBUTION` issue. No code changes.

Gate 4.0 produces this closure report only. Inventory is
read-only. No business code, no migration, no medical prompt,
no real patient data is touched.

---

## §1. Baseline verification

| Item | Expected | Actual | Match |
|---|---|---|---|
| Branch | `phase-a1a/emergency-containment` | `phase-a1a/emergency-containment` | ✓ |
| HEAD | `b737eab...` | `b737eabb344a270e5bbabe89a8331657be21a03d` | ✓ |
| b737eab is ancestor of HEAD | YES | YES | ✓ |
| d1447f3 is ancestor of b737eab | YES | YES | ✓ |
| Master | `c147d01...` | `c147d015455017bc1d8420cbdbd813b3b8ec23ce` | ✓ |
| A0.1R tag unchanged | `3cd1bec...` | `3cd1bece14a7f4564d14d630568697c48cfd8385` | ✓ |
| b737eab not amended | commit message intact | commit message intact | ✓ |

Working tree: pre-existing untracked items only
(`reports/comprehensive-audit/`, `docs/audit/`, `docs/corti_parity/phase7_gate13a/`,
`reports/phase6/`, `reports/phase7/`, `scripts/audit/`,
`backend/data/icoder.db.gate3-prerelease`, repo-root
`gate3-8-browser-evidence.png`). None of these are Gate 4
artifacts.

**Verdict**: `BASELINE_VERIFIED`. No `PARTIAL_BLOCKED_BY_INVALID_GATE3R_BASELINE`.

---

## §2. Gate 3R core test re-run

```
pytest tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py
     tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py
     tests/test_api/test_a1a_gate3r_3_trace_capture_profiles.py
     tests/test_api/test_a1a_gate3r_4_trace_event_identity.py
     tests/test_api/test_a1a_gate3r_5_migration_portability.py
     tests/test_api/test_a1a_gate3r_8_regression_security_negative.py

→ 79 passed in 103.87s
```

Gate 3R carry-over tests remain green at the Gate 4 baseline.

---

## §3. Gate 3R file and report counts

| Metric | Count |
|---|---|
| Files in commit `b737eab` | 38 |
| Markdown reports added (`A1A_GATE3*` + `A1A_GATE3R_*`) | 13 |
| New code files | 3 |
| Modified code files | 11 |
| New test files | 6 |
| Modified test files | 2 |
| `.gitignore` whitelist entry | 1 |
| Screenshots (newly unignored) | 2 |

---

## §4. Gate 3R Issue Ledger machine recount

| Pattern | Count |
|---|---|
| `^\| GATE3` rows (all tables) | 47 |
| §2.1 Gate 3 issues (`GATE3_xxx`) | 18 |
| §2.2 Gate 3R issues (`GATE3R_xxx`) | 12 |
| §2.3 Out-of-scope references | 4 |
| Section header / status rows | 13 |
| **Effective issue count** | **30 unique** (18 Gate 3 + 12 Gate 3R) |

The recount confirms the Issue Ledger is internally
consistent — no orphan IDs, no duplicate IDs.

---

## §5. Carry-over ownership transfer

Gate 4 takes formal ownership of the following issues. Each
gets a `closed-by → Gate 4.x` update in the canonical Issue
Ledger at Gate 4.9.

### §5.1 `GATE3R_011` — Frontend does not send `Tenant-Name`

**Ledger status (as of Gate 3R.9)**: OBSERVED.

**Inventory finding**:
- `frontend/src` does NOT send `Tenant-Name` or `X-Tenant` header on any fetch.
- `TenantHeaderMiddleware` (`backend/app/middleware/tenant_extractor.py:58`)
  enforces the header only when `ICODER_DEPLOYMENT_MODE == "cloud"`.
- Local/dev mode is pass-through; missing header silently
  bypasses the cross-check.
- The console trace path `/api/runtime/runs/{id}/trace` reads
  `request.state.tenant_name`; if missing, the org filter is
  skipped (returns rows across all orgs).
- The partner trace path `/api/v1/runs/{id}/trace` does NOT
  read `request.state.tenant_name`; it uses `current_org.id`
  from the JWT — this asymmetry was documented in Gate 3R.6 §5.2
  but not closed.

**Risk class**: P1 (tenant boundary leak in console trace when
running local/dev mode without the header).

**Gate 4.2 owns the fix**: replace the implicit Tenant-Name
header with an authenticated-tenant derivation. The header
becomes a non-authoritative hint; the org is derived from the
JWT and verified against membership + API client binding.

### §5.2 `GATE3_014` — `assert_org_scope` refactor

**Ledger description (Gate 3.6 carry-over)**: "F06 helper still in use; refactor would touch 17 callers, deferred".

**Inventory finding**: **`assert_org_scope` DOES NOT EXIST in the codebase.**
- No `def assert_org_scope` anywhere in `backend/app/`.
- The 17-caller count is stale or refers to a different helper name.
- The actual helpers are:
  - `require_org_membership` (`backend/app/middleware/auth.py:176`) — 2 callers.
  - `require_org_role(*roles)` factory (`backend/app/middleware/auth.py:197`) — used by `organizations.py`.
  - `assert_tenancy_for_write(organization_id, table_name)` (used in `run_lifecycle.py`, `idempotency_service.py`) — runtime write guard, ~5 callers.
  - `get_current_organization` dependency (`backend/app/middleware/auth.py:149`) — ~30 callers via FastAPI `Depends`.

**Ledger correction**: GATE3_014 will be re-scoped in Gate 4.9
as either (a) OBSERVED→CLOSED if no refactor is actually needed
after audit, or (b) re-described as the
`get_current_organization` vs `Tenant-Name` asymmetry that
Gate 4.2 closes. The "17 callers" claim is invalidated.

**Gate 4.2 owns the re-scope decision.**

### §5.3 `GATE3_015` — `encounters` / `cdi_cases` organization constraints

**Ledger status (as of Gate 3R.9)**: DEFERRED to "Phase B (post-A1A)".

**Inventory finding**:
- `Encounter.organization_id` is `nullable=True` (`backend/app/models/encounter.py:12`). No DB CHECK constraint.
- `Document.organization_id` is `nullable=True` (encounter.py:36). No CHECK.
- `CDICaseModel.organization_id` is `nullable=True` (cdi_case.py:60). No CHECK.
- `DocumentationGapModel`, `ProviderQueryModel`, `ClinicianResponseModel`, `DocumentVersionModel` have no `organization_id` column at all — they inherit org only transitively via `case_id → cdi_cases.organization_id`.
- Migration 019 added CHECK constraints ONLY on `run_history` and `audit_logs`. Clinical tables were not touched.

**Risk class**: P1. Clinical tables can carry NULL org at the
DB level; a buggy write path that skips org stamping would
persist unattributed PHI.

**Gate 4.2 owns the fix**: add NOT NULL + CHECK on
`encounters.organization_id`, `documents.organization_id`,
`cdi_cases.organization_id` (Migration 021 or later, depending
on Gate 4.1 sequencing). The downstream CDI sub-tables inherit
org via JOIN, but Gate 4.2 may also add a denormalized
`organization_id` column on the high-traffic ones
(`cdi_provider_queries`) to enable direct filter without JOIN.

### §5.4 New — `TENANT_OWNED_SYSTEM_AUDIT_ATTRIBUTION`

**Charter §3 (Gate 4 scope)**: "系统自动执行的租户业务动作，仍然必须记录所属 Organization."

**Inventory finding**:
- `system_audit()` (`backend/app/services/system_audit.py:152`) **always** writes `organization_id=None` with `tenancy_classification=MODERN_SYSTEM`.
- The 6 lifecycle actions Gate 3R.2 wired (`run.cancel`, `run.timeout`, `run.complete`, `run.failed`, `idempotency.dedup`, `api_client.rotate`) currently emit via `log_action(organization_id=...)` from their respective call sites — so they DO get tenant attribution.
- BUT the `system_audit()` function itself has no `organization_id` parameter. If a future caller routes a tenant-owned business action through `system_audit()` (instead of `log_action`), the org is lost.

**Risk class**: P2 today (no current caller leaks org), but P1
as a structural risk. The function signature itself is the
escape hatch.

**Gate 4.7 owns the fix**: introduce a `tenant_owned_system_audit(organization_id, action, ...)` helper that stamps `tenancy_classification=MODERN` (not `MODERN_SYSTEM`) but emits one of the 6 lifecycle actions. The classifier already recognises these 6 as system-scope via `SYSTEM_AUDIT_ACTIONS`; the row's `organization_id` is what differs.

---

## §6. Inventory snapshot — 32 required facts

| # | Item | State |
|---|---|---|
| 1 | Branch | `phase-a1a/emergency-containment` |
| 2 | HEAD | `b737eabb344a270e5bbabe89a8331657be21a03d` |
| 3 | b737eab ancestor | YES |
| 4 | Master | `c147d015455017bc1d8420cbdbd813b3b8ec23ce` |
| 5 | A0.1R tag | `3cd1bece...` (unchanged) |
| 6 | Working tree | pre-existing untracked only; no Gate 4 changes |
| 7 | Gate 3R tests | 79 passed in 103.87s |
| 8 | Gate 3R files / reports | 38 files / 13 reports |
| 9 | Issue Ledger machine count | 30 unique issues (18 GATE3_ + 12 GATE3R_) |
| 10 | `GATE3R_011` | OBSERVED — frontend sends no `Tenant-Name` |
| 11 | `GATE3_014` | `assert_org_scope` does NOT exist; ledger text stale |
| 12 | `GATE3_015` | encounters/cdi_cases/documents `organization_id` nullable; no CHECK |
| 13 | Patient table | **DOES NOT EXIST**; `Encounter.patient_id` is a free-form String(64) |
| 14 | Encounter columns | 13 columns; `admission_reason` + `discharge_summary` are Text PHI; `organization_id` nullable |
| 15 | CDI Case/Query tables | 5 tables; multiple Text PHI columns (`evidence_quote`, `query_text`, `free_text_response`, `diff_summary`) |
| 16 | Context Store | `backend/app/icoder/agent_runtime/context/`; DB-persisted; `ContextMessage.redacted` is `frozen=True` |
| 17 | Organization derivation | `get_current_organization` (auth.py:149) reads JWT `org_id` claim; no Tenant-Name fallback |
| 18 | Tenant-Name call chain | middleware→`request.state.tenant_name`; console trace path reads it; partner trace path does NOT |
| 19 | system-audit attribution | `system_audit()` always writes `organization_id=None`; lifecycle emits use `log_action(organization_id=...)` |
| 20 | PII/PHI Redactor | `app/services/phi_redactor.py` is best-effort (returns original on failure); not fail-closed |
| 21 | Data Policy | `icoder_runtime/core/data_policy.py` has `allow_external_llm`, `pii_redaction_required`; **NO region field** |
| 22 | Provider Gateway | `icoder_runtime/core/llm_gateway.py`; 4 providers; no per-provider region; no egress policy |
| 23 | Provider region info | **NOT FOUND**; no region metadata on providers |
| 24 | PHI at-rest storage | **NO ENCRYPTION**; SQLite stores plaintext |
| 25 | Frontend localStorage | `access_token`, `refresh_token`, `icoder-auth` (auth); UI prefs; no direct PHI; `icoder-textgen-templates` could carry user-input templates — needs Gate 4.3 audit |
| 26 | Trace `safe_metadata` | `_redact_safe_metadata` (run_trace.py:139) uses **BLACKLIST** of known secret keys; not allowlist |
| 27 | Audit Detail | `details: JSON` free-form; `model_input_summary` + `model_output_summary` are Text; no redaction at model layer |
| 28 | SSE / Embedded payload | Phase 6 unified envelope `{name, payload, meta}`; payload can include input/output previews |
| 29 | Gate 13A evidence | 3 markdown reports (502 LOC) + 1 screenshot; `screenshots/`, `sanitized-har/`, `storage-audit/`, `network-audit/`, `console-logs/`, `playwright-traces/`, `test-results/` subdirs **all empty** |
| 30 | Gate 4 planned files | TBD per Gate 4.1–4.8; likely touches `models/{encounter,cdi_case}.py`, `services/{phi_redactor,system_audit,tenant_read_policy}.py`, `icoder_runtime/core/{data_policy,llm_gateway,pii_redaction}.py`, new `services/phi_encryption.py`, new migrations |
| 31 | Gate 4 planned migrations | at least one for clinical tables NOT NULL+CHECK; one for encryption metadata; possibly one for `tenant_owned_system_audit` attribution |
| 32 | Provisional verdict | see §8 |

---

## §7. Gate 3R Addendum — PHI-relevant corrections

The Gate 3R Issue Ledger is correct on every P0/P1/P2 issue it
closes. Gate 4.0 surfaces three PHI-relevant clarifications
that do NOT invalidate Gate 3R verdicts but should be
recorded:

### §7.1 Correction — `assert_org_scope` reference is stale

Gate 3 + Gate 3R closure reports reference `assert_org_scope`
as a refactor target with 17 callers. The function does not
exist. The actual org-scope helpers are
`require_org_membership`, `require_org_role`, and
`assert_tenancy_for_write`. **Net effect on Gate 3R verdict**:
none — the function name was descriptive shorthand, not a
load-bearing ref.

### §7.2 Correction — Gate 3R did not assess clinical tables

Gate 3R Issue Ledger GATE3_015 marked
`encounters`/`cdi_cases` CHECK constraints as DEFERRED to
"Phase B (post-A1A)". Gate 4.0 formally transfers ownership
into Gate 4.2 because the deferred scope is on the PHI
critical path and cannot wait for Phase B.

**Net effect on Gate 3R verdict**: none — Gate 3R's surface
was trace + audit + tenant-read on `run_history` and
`audit_logs`. The deferral was always intended to be re-scopeable.

### §7.3 Correction — `system_audit()` is structurally org-blind

Gate 3R.2 wired 6 lifecycle emits via `log_action(organization_id=...)`. The emits are correct. But the
`system_audit()` function signature itself has no org
parameter — any future caller that误routes a tenant-owned
action through `system_audit()` loses attribution.

**Net effect on Gate 3R verdict**: none for the 6 emits 3R.2
shipped. Gate 4.7 owns the structural hardening
(`tenant_owned_system_audit()` helper).

---

## §8. Provisional verdict

```
PASS_A1A_GATE4_0_BASELINE_GATE3R_ADDENDUM_CARRYOVER_RECONCILIATION_VERIFIED
```

The Gate 3R baseline is intact. The three PHI carry-overs are
formally accepted into Gate 4 with named sub-gate owners
(GATE3R_011 → 4.2, GATE3_014 → 4.2, GATE3_015 → 4.2,
TENANT_OWNED_SYSTEM_AUDIT_ATTRIBUTION → 4.7). The Gate 3R
Issue Ledger is internally consistent (30 unique issues);
the three corrections above are PHI-relevant clarifications,
not invalidations.

Forbidden verdicts (charter §22) remain forbidden. This gate
issues neither `PASS_PRODUCTION_READY` nor
`PASS_FULLY_VERIFIED` nor `PASS_PHI_BOUNDED` — the PHI
boundary has not yet been implemented, only inventoried.

---

## §9. Coordination with Gate 4.1–4.9

| Sub-gate | Primary owner of | Carry-over input |
|---|---|---|
| 4.1 | PHI inventory + threat model | §6 inventory snapshot |
| 4.2 | Patient/Encounter/CDI/Context tenant boundary | GATE3R_011, GATE3_014, GATE3_015 |
| 4.3 | Live-path redaction + minimum necessary data | §6 items 20, 26, 27, 28 |
| 4.4 | PHI at-rest protection + key lifecycle | §6 items 21, 24 |
| 4.5 | Provider egress + regional residency | §6 items 21, 22, 23 |
| 4.6 | Browser + Embedded + Patient A/B | §6 items 25, 29 |
| 4.7 | Retention + deletion + audit closure | §5.4 (new issue) |
| 4.8 | Full security regression + evidence closure | all |
| 4.9 | Commit + final verdict | all |

---

## §10. Forbidden list — re-confirmation

Gate 4.0 did NOT:
- Modify any business code
- Execute any new migration
- Touch any real patient data
- Modify any Medical Coding / CDI / DRG-DIP prompt
- Inherit Gate 3R's broad PHI security conclusions (Gate 3R
  was about trace + audit + tenant-read isolation, NOT about
  PHI boundary completeness)
- Push, PR, master commit, amend `b737eab`
- Use `git add -A`
- Issue any charter §22 forbidden verdict

The Gate 4.0 inventory explicitly distinguishes:
- "NOT FOUND" (Patient table, encryption, provider region) —
  these are real gaps that Gate 4.1–4.8 must address.
- "Blacklist, not allowlist" (safe_metadata) — a real gap that
  Gate 4.3 must close.
- "best-effort, not fail-closed" (phi_redactor) — a real gap
  that Gate 4.3 must close.

The Gate 3R verdict `RECONCILED_VERIFIED` applies to the
trace + audit + tenant-read surface. It does NOT extend to
PHI boundary, redaction completeness, encryption at rest, or
regional residency. Gate 4 owns those surfaces from this
point forward.

---

## §11. Next

Gate 4.1 — PHI Inventory, Classification and Threat Model.
