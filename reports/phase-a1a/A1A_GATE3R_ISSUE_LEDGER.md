# Phase A1A Gate 3R Issue Ledger — Canonical Issue Status

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Author**: Gate 3R.7 (charter §3R.7 deliverable #3)
**Scope**: Every issue (defect, gap, observation, carry-over) surfaced
by Gate 3 (`d1447f3`) and Gate 3R.1–3R.6, with a canonical status.

Each issue has:

- **ID** — `GATE3_xxx_yy` or `GATE3R_xxx_yy` format
- **Severity** — P0 / P1 / P2 / P3 (rubric in §2)
- **Status** — CLOSED / OBSERVED / DEFERRED / WONTFIX
- **Surfaced by** — the gate that first raised it
- **Closed by** — the gate that produced the fix or formal disposition
- **Evidence** — primary artifact(s) that prove the status

This ledger is the single canonical answer to "is issue X open?"
Auditors consult this file, not scattered mentions across the
closure reports.

---

## §1. Severity rubric

| Severity | Definition | SLA |
|---|---|---|
| P0 | Tenant isolation or PHI boundary violated in production-shipped code | block release |
| P1 | Tenant isolation contract leak (existence / org boundary) without PHI exposure | block release |
| P2 | Narrow claim that needs widening; correctness intact for documented surface | next phase |
| P3 | Documentation gap, environment-blocked verification, or future hardening | backlog |

---

## §2. Issue table

### §2.1 Gate 3 issues (commit `d1447f3`)

| ID | Severity | Description | Status | Surfaced by | Closed by | Evidence |
|---|---|---|---|---|---|---|
| GATE3_001 | P1 | F01 — 235 `run_history` rows with NULL `organization_id` | CLOSED | A0.1R / Gate 2 | Gate 2 (commit `de2feaa`) | Migration `016_tenancy_classification` backfills 470 rows (run_history + audit_logs) |
| GATE3_002 | P1 | F02 — 201 `audit_logs` rows with NULL `organization_id` | CLOSED | A0.1R / Gate 2 | Gate 2 (commit `de2feaa`) | Migration 016 backfill + cloud-mode fail-closed guard at 4 write surfaces |
| GATE3_003 | P1 | F03 — `log_action` callers skip `org_id` | CLOSED | A0.1R / Gate 2 | Gate 2 (commit `de2feaa`) | `allow_null_org=True` parameter + `system_audit()` helper for system-scope rows |
| GATE3_004 | P1 | F04 — SSE trace lacked tenant isolation | CLOSED | Gate 3.4 | Gate 3.4 (commit `d1447f3`) | `test_phase7_gate9_sse_run_events.py` + `app/api/runs.py` SSE path |
| GATE3_005 | P1 | F05 — Console trace lacked tenant isolation | CLOSED | Gate 3.5 | Gate 3.5 (commit `d1447f3`) | `test_a1a_gate3_5_console_trace_isolation.py` + `app/api/run_trace.py` |
| GATE3_006 | P1 | F06 — boolean escape hatch in `system_audit` allowlist | CLOSED | Gate 3.6 | Gate 3.6 (commit `d1447f3`) | `allow_null_org=True` removed from `system_audit()` signature |
| GATE3_007 | P2 | Pre-Migration-019 `run_history` schema lacked CHECK on `trace_capture_status` | CLOSED | Gate 3.7 | Gate 3.7 (commit `d1447f3`) | Migration 019 adds narrow CHECK `{PERSISTED, FAILED, FALLBACK_MEMORY}` |
| GATE3_008 | P2 | Pre-Migration-019 `run_trace_events` had no composite UNIQUE | CLOSED | Gate 3.7 | Gate 3.7 (commit `d1447f3`) | Migration 019 adds `UNIQUE(run_id, step, ts)` |
| GATE3_009 | P1 | Tenancy classification taxonomy was ad-hoc strings | CLOSED | Gate 3.1 | Gate 3.1 (commit `d1447f3`) | 7-class evidence-based taxonomy in `app/services/legacy_tenancy_attribution.py` |
| GATE3_010 | P1 | Quarantine path had no formal policy | CLOSED | Gate 3.2 | Gate 3.2 (commit `d1447f3`) | `app/services/tenant_read_policy.py` `is_tenant_visible()` |
| GATE3_011 | P2 | `run_lifecycle` audit emits were allowlist-only | OBSERVED → CLOSED by 3R.2 | Gate 3.6 carry-over | Gate 3R.2 | `app/services/run_lifecycle.py` `record_run_complete/failed/cancelled/timeout` |
| GATE3_012 | P2 | `idempotency.dedup` audit emit missing | OBSERVED → CLOSED by 3R.2 | Gate 3.6 carry-over | Gate 3R.2 | `app/services/idempotency_service.py` replay-path emit |
| GATE3_013 | P2 | `api_client.rotate` audit emit missing | OBSERVED → CLOSED by 3R.2 | Gate 3.6 carry-over | Gate 3R.2 | `app/api/platform_api_clients.py` rotation endpoint emit |
| GATE3_014 | P2 | `assert_org_scope` refactor (F06 carry-over) | DEFERRED | Gate 3.6 | Gate 4 or later | F06 helper still in use; refactor would touch 17 callers, deferred |
| GATE3_015 | P3 | CHECK constraints on `encounters` / `cdi_cases` | DEFERRED | Gate 3.7 carry-over | Phase B (post-A1A) | Not on Gate 3R critical path |
| GATE3_016 | P3 | PostgreSQL migration verification | DEFERRED | Gate 3 / 3R.5 | Future gate | Env-blocked; partial verdict `PARTIAL_BLOCKED_BY_POSTGRES_MIGRATION_NOT_VERIFIED` |
| GATE3_017 | P2 | Migration interrupted-recovery not tested | OBSERVED → CLOSED by 3R.4 + 3R.5 | Gate 3.7 (manual temp-table drop) | Gate 3R.4 + 3R.5 | Migration 020 DROP IF EXISTS + `test_interrupted_recovery_completes_on_retry` |
| GATE3_018 | P3 | Browser evidence was Playwright MCP `evaluate` only (Gate 3.8) | OBSERVED → CLOSED by 3R.6 | Gate 3.8 carry-over | Gate 3R.6 | `01_runtrace_timeline.png` + `02_runtrace_step_expanded.png` screenshots |

### §2.2 Gate 3R issues

| ID | Severity | Description | Status | Surfaced by | Closed by | Evidence |
|---|---|---|---|---|---|---|
| GATE3R_001 | P0 | Orphan-run fall-through: signed token valid but no RunHistory row → trace events returned without tenancy binding | CLOSED | Gate 3R.0 §9-11 | Gate 3R.1 | Orphan-run guard in `runs.py` + `run_trace.py`; 12-test suite |
| GATE3R_002 | P2 | `trace_capture_status` had 3 literals, deployment-profile state machine needs 6 | CLOSED | Gate 3R.0 §14 | Gate 3R.3 + 3R.4 | Migration 020 widens CHECK; `TraceCaptureState.ALL_STATES` source of truth |
| GATE3R_003 | P1 | NULL `trace_capture_status` rows (244) had no canonical interpretation | CLOSED | Gate 3R.0 §15 | Gate 3R.4 | Migration 020 backfills NULL → `NEVER_CAPTURED_LEGACY` (idempotent) |
| GATE3R_004 | P2 | `(run_id, step, ts)` composite identity brittle across clock slew / microsecond collision | CLOSED | Gate 3R.0 §16-17 | Gate 3R.4 | Migration 020 adds UUID `event_id` + `sequence_number` + `trace_id` + `identity_source` |
| GATE3R_005 | P1 | `InMemoryRunTraceStore` zero on backend restart | CLOSED | Gate 3R.0 §1 / 3R.3 charter | Gate 3R.3 + 3R.4 | `DeploymentProfile` + `DbRunTraceStore` canonical for `REQUIRED_DB` profile; 3R.6 restart-recovery test |
| GATE3R_006 | P2 | Cloud-mode validation rejected all memory stores without nuance | CLOSED | Gate 3R.0 §19 | Gate 3R.3 | `resolve_profile()` + `is_cloud_allowed()` in `app/services/deployment_profile.py` |
| GATE3R_007 | P3 | `context.clear` allowlist entry with no emit caller | OBSERVED → WONTFIX | Gate 3R.0 §13 / open Q5 | Gate 3R.2 (decision: keep with N/A docstring) | Phase 6 widget postMessage-only; backend never sees it; allowlist entry retained for symmetry |
| GATE3R_008 | P3 | Browser E2E didn't cover restart recovery | CLOSED | Gate 3R.0 §20 | Gate 3R.6 | `01_runtrace_timeline.png` + curl transcript of kill+restart loop |
| GATE3R_009 | P2 | Migration 020 interrupted-recovery pattern (same class as Gate 3.7 issue) | CLOSED | Gate 3R.5 §4 | Gate 3R.5 | `op.execute("DROP TABLE IF EXISTS _alembic_tmp_*")` at top of upgrade() |
| GATE3R_010 | P3 | PG partial verdict for Migration 020 | DEFERRED | Gate 3R.5 §5 | Future gate | `test_postgresql_migration_verification_blocked` documents the gap |
| GATE3R_011 | P2 | Frontend doesn't send `Tenant-Name` header in dev mode | OBSERVED | Gate 3R.6 §5.2 | (not closed — out of 3R scope) | Cloud mode enforces `tenant_header_required` so prod is safe; dev-mode asymmetry documented in Gate 3 closure memory |
| GATE3R_012 | P3 | SSE returns 404 for org-mismatch but trace endpoint returns 403 | OBSERVED → WONTFIX | Gate 3R.6 §6.2 | (decision: intentional asymmetry) | SSE doesn't leak existence; trace endpoint's 403 is for already-URL-exposed run_id |

### §2.3 Out-of-scope (NOT Gate 3R issues, tracked elsewhere)

| ID | Severity | Description | Status | Tracked by |
|---|---|---|---|---|
| GATE4_PHI_* | P0/P1 | PHI boundary, redaction, regional data residency | (not yet opened) | Gate 4 workstream |
| GATE5_RUNTIME_* | P2 | Runtime hardening, A2A v0.3 contract | (not yet opened) | Gate 5 workstream |
| GATE6_FORK_* | P3 | Web Component 2.0 method-based API | OBSERVED | Phase 4-H audit, Phase 5 Track A closed P0+P1 |
| GATE7_PARTNER_* | P2 | Partner reference app, sandbox demo | CLOSED | Phase 7 Gate 12 / 13 |

---

## §3. Closed-by-Gate-3R summary

Gate 3R closed **8 P0/P1/P2 issues** from Gate 3's backlog:

- 4 audit emit gaps (GATE3_011/012/013 + GATE3R_005 effectively): CLOSED
- 1 interrupted-recovery test gap (GATE3_017): CLOSED
- 1 browser evidence gap (GATE3_018): CLOSED
- 3 new P1/P2 issues from Gate 3R.0 re-audit (GATE3R_001/003/004): CLOSED

Plus 2 new P3 observations (GATE3R_007 context.clear, GATE3R_012
SSE asymmetry) closed WONTFIX with explicit reasoning.

Plus 3 deferred items:
- GATE3_014 — F06 refactor (17 callers)
- GATE3_015 — CHECK on encounters/cdi_cases
- GATE3_016 / GATE3R_010 — PostgreSQL verification (env-blocked)

---

## §4. Risk acceptance

The two WONTFIX items accept specific, scoped risks:

### §4.1 GATE3R_007 — `context.clear` allowlist entry

**Risk**: Auditor grepping the allowlist sees `context.clear` and
expects an emit caller. Finding none, they may conclude the audit
pipeline is broken.

**Mitigation**: `system_audit.py` docstring on `context.clear`
entry states "Phase 6 widget postMessage-only; backend never
sees this event. Kept for symmetry with the event-name list
the widget emits." The allowlist entry exists so audit
consumers can pattern-match without needing two lists.

**Residual risk**: Documentation-only. If the widget ever emits
`context.clear` to the backend (Phase 7+ change), the allowlist
entry will accept it; no code change needed.

### §4.2 GATE3R_012 — SSE vs trace HTTP code asymmetry

**Risk**: API consumers expecting uniform HTTP codes across
`/trace` and `/events` may break when one returns 403 and the
other 404 for the same org-mismatch condition.

**Mitigation**: Documented in Gate 3R.6 §6.2 + Gate 3 closure
memory. The asymmetry is intentional: SSE denial must not leak
existence (no URL-embedded run_id), trace denial already has
the run_id in the URL so 403 is the more honest signal.

**Residual risk**: Backend-only contract. No frontend currently
depends on the uniformity; if one ever does, the contract is
documented.

---

## §5. Issue lifecycle

```
   OPEN  ─────fix──────►  CLOSED
     │
     │
   no-fix-needed
     │
     ▼
   WONTFIX  (with explicit risk acceptance)

   OPEN  ────env-blocked / scope-shift────►  DEFERRED  ──future gate──►  CLOSED

   CLOSED  ───regression-found───►  REOPENED  ──fix──►  CLOSED
```

No issue in this ledger is currently REOPENED. The DEFERRED items
each have a clearly-named future gate that owns them.

---

## §6. Audit trail for each CLOSED issue

For an auditor who needs to re-verify a specific closure:

| Issue | Re-verify command |
|---|---|
| GATE3_001-003 | `git show de2feaa -- backend/alembic/versions/016_tenancy_classification.py` |
| GATE3_004 | `pytest tests/test_api/test_phase7_gate9_sse_run_events.py -v` |
| GATE3_005 | `pytest tests/test_api/test_a1a_gate3_5_console_trace_isolation.py -v` |
| GATE3_006 | `grep -n "allow_null_org" backend/app/services/system_audit.py` |
| GATE3_007 | `grep -A5 "chk_run_history_trace_cap" backend/alembic/versions/019_*.py` |
| GATE3_008 | `grep -B1 -A5 "ux_run_trace_events_run_step_ts" backend/alembic/versions/019_*.py` |
| GATE3_009 | `grep -E "MODERN|MODERN_SYSTEM|LEGACY_TENANT" backend/app/services/legacy_tenancy_attribution.py \| head -10` |
| GATE3_010 | `pytest tests/unit/app/test_tenant_read_policy.py -v` |
| GATE3_011-013 | `pytest tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py -v` |
| GATE3_017 | `pytest tests/test_api/test_a1a_gate3r_5_migration_portability.py::test_interrupted_recovery_completes_on_retry -v` |
| GATE3_018 | Open `reports/phase-a1a/screenshots/gate3r6/01_runtrace_timeline.png` |
| GATE3R_001 | `pytest tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py -v` |
| GATE3R_002 | `pytest tests/test_api/test_a1a_gate3r_4_trace_event_identity.py::test_trace_capture_state_allowlist_unchased_post_migration -v` |
| GATE3R_003 | `python -c "import sqlite3; print(sqlite3.connect('backend/data/icoder.db').execute(\"SELECT trace_capture_status, COUNT(*) FROM run_history GROUP BY trace_capture_status\").fetchall())"` |
| GATE3R_004 | `pytest tests/test_api/test_a1a_gate3r_4_trace_event_identity.py -v` |
| GATE3R_005 | kill+restart loop in Gate 3R.6 §4 transcript |
| GATE3R_006 | `pytest tests/test_api/test_a1a_gate3r_3_trace_capture_profiles.py -v` |

---

## §7. Forbidden list re-confirmation

This ledger does NOT:

- Edit any historical Gate 3 report
- Modify any code (it's documentation only)
- Issue a verdict (it's an index)
- Close a forbidden issue (charter §22 items remain forbidden)
- Reopen a CLOSED issue without new evidence

Forbidden verdicts (charter §22) remain forbidden.

---

## §8. References

- Gate 3 Addendum: `reports/phase-a1a/A1A_GATE3_ADDENDUM.md`
- Gate 3 Evidence Manifest: `reports/phase-a1a/A1A_GATE3_EVIDENCE_MANIFEST.md`
- Gate 3R.0 baseline: `reports/phase-a1a/A1A_GATE3R_0_BASELINE_AND_CARRYOVER_RE_AUDIT.md`
- Charter (authoritative for severity rubric + forbidden list)
