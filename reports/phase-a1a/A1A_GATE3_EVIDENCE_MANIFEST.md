# Phase A1A Gate 3 Evidence Manifest — Consolidated Artifact Index

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Author**: Gate 3R.7 (charter §3R.7 deliverable #2)
**Scope**: All artifacts produced by Gate 3 (commit `d1447f3`) and
Gate 3R.1–3R.6 (this branch, uncommitted as of Gate 3R.7).

This manifest is the single canonical index an auditor uses to
locate every artifact that supports the trace + audit + tenant-read
surface verdicts. Each artifact has:

- **Path** — relative to repo root
- **LOC / size** — lines of code (code files) or page count (reports)
- **Gate** — which Gate produced it
- **Charter ref** — the charter §item it satisfies
- **Verifiable claim** — what an auditor can prove by reading it

The manifest is frozen at Gate 3R.7. Gate 3R.8 may add test
artifacts; Gate 3R.9 may add a final summary. No earlier gate's
evidence is moved or renamed.

---

## §1. Source code artifacts

### §1.1 New files (Gate 3R.1–3R.6)

| Path | LOC | Gate | Charter ref | Claim |
|---|---|---|---|---|
| `backend/app/services/trace_capture_state.py` | 134 | 3R.3 | §3R.3 | 6-literal state machine + ALL_STATES frozenset as source of truth |
| `backend/app/services/deployment_profile.py` | 179 | 3R.3 | §3R.3 | MEMORY_DEV / BEST_EFFORT_DB / REQUIRED_DB resolver |
| `backend/alembic/versions/020_trace_event_identity_and_capture_state.py` | 241 | 3R.4 + 3R.5 | §3R.4 + §3R.5 | 4 new columns + 3 indexes + CHECK widen + backfill |
| `backend/tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py` | ~430 | 3R.1 | §3R.1 | 12 tests covering 3 orphan-run denial paths |
| `backend/tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py` | ~250 | 3R.2 | §3R.2 | 7 tests covering 6 audit emit call sites |
| `backend/tests/test_api/test_a1a_gate3r_3_trace_capture_profiles.py` | ~620 | 3R.3 | §3R.3 | 21 tests covering state machine + profile + Settings |
| `backend/tests/test_api/test_a1a_gate3r_4_trace_event_identity.py` | ~460 | 3R.4 | §3R.4 | 12 tests covering UUID + sequence counter + backcompat |
| `backend/tests/test_api/test_a1a_gate3r_5_migration_portability.py` | ~335 | 3R.5 | §3R.5 | 7 tests covering fresh/idempotent/round-trip/interrupted |
| **Total new code** | **~2,650** | | | |

### §1.2 Modified files (Gate 3R.1–3R.6)

| Path | ΔLOC | Gate | Charter ref | Claim |
|---|---|---|---|---|
| `backend/app/api/agent_run.py` | +~20 | 3R.2 | §3R.2 | trace_url surfacing on run.completed event |
| `backend/app/api/platform_api_clients.py` | +~25 | 3R.2 | §3R.2 | `api_client.rotate` audit emit on secret rotation |
| `backend/app/api/run_trace.py` | +~80 | 3R.1 + 3R.3 | §3R.1, §3R.3 | orphan-run guard + audit emit + scoped read |
| `backend/app/api/runs.py` | +~120 | 3R.1 + 3R.2 | §3R.1, §3R.2 | orphan-run guard in SSE + partner trace + run lifecycle emits |
| `backend/app/config.py` | +~30 | 3R.3 | §3R.3 | `RUNTRACE_DEPLOYMENT_PROFILE` field + cloud-mode validation |
| `backend/app/icoder/agent_runtime/orchestrator/run_trace.py` | +~90 | 3R.3 + 3R.4 | §3R.3, §3R.4 | `_assign_event_identity` + `_TRACE_SEQUENCE_COUNTERS` + DbRunTraceStore writes identity columns |
| `backend/app/models/run_trace.py` | +~20 | 3R.4 | §3R.4 | 4 new Mapped columns (event_id, sequence_number, trace_id, identity_source) |
| `backend/app/services/idempotency_service.py` | +~10 | 3R.2 | §3R.2 | `idempotency.dedup` audit emit on replay |
| `backend/app/services/legacy_tenancy_attribution.py` | +~5 | 3R.2 | §3R.2 | attribution audit emit on classification |
| `backend/app/services/run_lifecycle.py` | +~50 | 3R.2 + 3R.3 | §3R.2, §3R.3 | record_run_complete/failed/cancelled/timeout emits + CAPTURE_PENDING stamp on INSERT |
| `backend/app/services/system_audit.py` | +~5 | 3R.1 + 3R.2 | §3R.1, §3R.2 | allowlist widens for trace.read.denied.* + run.* lifecycle actions |
| `backend/tests/test_api/test_phase7_gate7_trace_token.py` | +~10 | 3R.1 | §3R.1 | additional orphan-run denial assertion in pre-existing test |
| `backend/tests/test_api/test_phase7_gate9_sse_run_events.py` | +~10 | 3R.1 | §3R.1 | additional orphan-run denial assertion in pre-existing test |
| **Total modifications** | **~475** | | | |

### §1.3 Files NOT modified (charter §22 forbidden)

- No `app/coding/*.py` files (Medical Coding prompts)
- No `app/icoder/cdi/**/*.py` files (CDI prompts)
- No `official_agents/**/*.py` files (pre-built Agent packs)
- No `icoder_runtime/core/*.py` files (Runtime core)
- No Phase 5 / 6 / 7 production code outside the test files listed above
- No `.env`, `pyproject.toml`, `package.json`, `alembic.ini`
- No frontend (`frontend/src/**`) — Gate 3R is backend-only

---

## §2. Report artifacts

### §2.1 Gate 3 reports (commit `d1447f3` — frozen)

| Path | Gate | Status |
|---|---|---|
| `reports/phase-a1a/A1A_GATE3_0_BASELINE_AND_GATE2_CARRYOVER.md` | 3.0 | frozen |
| `reports/phase-a1a/A1A_GATE3_1_LEGACY_TENANCY_RECONCILIATION.md` | 3.1 | frozen |
| `reports/phase-a1a/A1A_GATE3_2_QUARANTINE_AND_TENANT_READ_POLICY.md` | 3.2 | frozen |
| `reports/phase-a1a/A1A_GATE3_3_DATABASE_BACKED_TRACE_PERSISTENCE.md` | 3.3 | frozen |
| `reports/phase-a1a/A1A_GATE3_4_SSE_TENANT_ISOLATION.md` | 3.4 | frozen |
| `reports/phase-a1a/A1A_GATE3_5_CONSOLE_TRACE_TENANT_ISOLATION.md` | 3.5 | frozen |
| `reports/phase-a1a/A1A_GATE3_6_AUDIT_LOG_COVERAGE_AND_SYSTEM_TENANT_SEPARATION.md` | 3.6 | frozen |
| `reports/phase-a1a/A1A_GATE3_7_DB_CONSTRAINTS_AND_FAIL_CLOSED_POLICY.md` | 3.7 | frozen |
| `reports/phase-a1a/A1A_GATE3_8_REGRESSION_SECURITY_NEGATIVE_BROWSER_EVIDENCE.md` | 3.8 | frozen |

### §2.2 Gate 3R reports (this branch, uncommitted)

| Path | Gate | Status |
|---|---|---|
| `reports/phase-a1a/A1A_GATE3R_0_BASELINE_AND_CARRYOVER_RE_AUDIT.md` | 3R.0 | ready for 3R.9 commit |
| `reports/phase-a1a/A1A_GATE3R_1_AUTHORITATIVE_RUN_RESOLVER.md` | 3R.1 | ready for 3R.9 commit |
| `reports/phase-a1a/A1A_GATE3R_2_MATERIAL_AUDIT_EMIT_WIRING.md` | 3R.2 | ready for 3R.9 commit |
| `reports/phase-a1a/A1A_GATE3R_3_TRACE_CAPTURE_STATUS_AND_PROFILES.md` | 3R.3 | ready for 3R.9 commit |
| `reports/phase-a1a/A1A_GATE3R_4_TRACE_EVENT_IDENTITY.md` | 3R.4 | ready for 3R.9 commit |
| `reports/phase-a1a/A1A_GATE3R_5_MIGRATION_PORTABILITY.md` | 3R.5 | ready for 3R.9 commit |
| `reports/phase-a1a/A1A_GATE3R_6_RUNTRACE_SSE_BROWSER_E2E.md` | 3R.6 | ready for 3R.9 commit |
| `reports/phase-a1a/A1A_GATE3_ADDENDUM.md` | 3R.7 | this file's sibling (del #1) |
| `reports/phase-a1a/A1A_GATE3_EVIDENCE_MANIFEST.md` | 3R.7 | **this file** (del #2) |
| `reports/phase-a1a/A1A_GATE3R_ISSUE_LEDGER.md` | 3R.7 | this file's sibling (del #3) |

### §2.3 Browser evidence artifacts

| Path | Gate | Captured via |
|---|---|---|
| `reports/phase-a1a/gate3-8-browser-evidence.png` | 3.8 | Playwright MCP `evaluate` |
| `reports/phase-a1a/screenshots/gate3r6/01_runtrace_timeline.png` | 3R.6 | Playwright MCP `take_screenshot` |
| `reports/phase-a1a/screenshots/gate3r6/02_runtrace_step_expanded.png` | 3R.6 | Playwright MCP `take_screenshot` |

---

## §3. Database artifacts

### §3.1 Migrations

| File | Revision | Gate | Status |
|---|---|---|---|
| `backend/alembic/versions/019_*.py` | 019 | 3.7 | applied to dev DB |
| `backend/alembic/versions/020_trace_event_identity_and_capture_state.py` | 020 | 3R.4 | applied to dev DB |

### §3.2 Dev DB state at Gate 3R.7 close

```
data/icoder.db (SQLite, ~660 KB)

alembic_version: 020

run_history row count: 244 (unchanged from Gate 3R.0)
  trace_capture_status distribution:
    NEVER_CAPTURED_LEGACY: 244  (was NULL pre-Migration-020; backfilled)
    CAPTURED:                0
    CAPTURE_PENDING:         0
    PERSISTED:               0
    FAILED:                  0
    FALLBACK_MEMORY:         0

run_trace_events row count: 0  (test fixtures seeded + removed within each gate)

audit_logs row count: ~236 (Phase 7 baseline) +
  new emits added by Gate 3R.2 wiring (run.*, idempotency.dedup,
  api_client.rotate) on subsequent runs
```

### §3.3 Pre-release DB snapshot

```
backend/data/icoder.db.gate3-prerelease
```

Snapshot taken at Gate 3R.0 §24 to preserve the pre-Migration-020
state for audit comparison. Not loaded by any production code;
kept as evidence of pre-backfill row state.

---

## §4. Test artifacts

### §4.1 Test counts (Gate 3R)

| File | Tests | Status |
|---|---|---|
| `test_a1a_gate3r_1_orphan_run_denial.py` | 12 | ✅ pass |
| `test_a1a_gate3r_2_audit_emit_wiring.py` | 7 | ✅ pass |
| `test_a1a_gate3r_3_trace_capture_profiles.py` | 21 | ✅ pass |
| `test_a1a_gate3r_4_trace_event_identity.py` | 12 | ✅ pass |
| `test_a1a_gate3r_5_migration_portability.py` | 7 | ✅ pass |
| **Gate 3R subtotal** | **59** | all pass |

### §4.2 Regression sweep (Phase A1A + Phase 5/6/7)

| File | Tests | Status |
|---|---|---|
| `test_a1a_gate3_2_tenant_read_policy.py` | 5 | ✅ pass |
| `test_a1a_gate3_4_sse_tenant_isolation.py` | 7 | ✅ pass |
| `test_a1a_gate3_5_console_trace_isolation.py` | 11 | ✅ pass |
| `test_a1a_gate3_8_security_negative_consolidated.py` | 19 | ✅ pass |
| `test_phase7_gate3_agent_run_idempotency.py` | 14 | ✅ pass |
| `test_phase7_gate4_run_cancel.py` | 7 | ✅ pass |
| `test_phase7_gate7_trace_token.py` | 13 | ✅ pass |
| `test_phase7_gate9_sse_run_events.py` | 10 | ✅ pass |
| **Regression subtotal** | **86** | all pass |

### §4.3 Total pytest invocation (Gate 3R.6 §6.1)

```
112 tests passed
```

---

## §5. Verdict chain

| Verdict | Gate | Date | Commit |
|---|---|---|---|
| `PASS_A1A_GATE3_TENANCY_TRUTH_CONTAINMENT_AND_TRACE_ISOLATION_VERIFIED` | 3 (bundled) | 2026-07-19 | `d1447f3` |
| `IN_PROGRESS_A1A_GATE3R_BASELINE_AND_CARRYOVER_RE_AUDIT_COMPLETE` | 3R.0 | 2026-07-19 | (uncommitted) |
| `PASS_A1A_GATE3R_1_AUTHORITATIVE_RUN_RESOLVER_VERIFIED` | 3R.1 | 2026-07-19 | (uncommitted) |
| `PASS_A1A_GATE3R_2_MATERIAL_AUDIT_EMIT_WIRING_VERIFIED` | 3R.2 | 2026-07-19 | (uncommitted) |
| `PASS_A1A_GATE3R_3_TRACE_CAPTURE_STATUS_AND_PROFILES_VERIFIED` | 3R.3 | 2026-07-19 | (uncommitted) |
| `PASS_A1A_GATE3R_4_TRACE_EVENT_IDENTITY_VERIFIED` | 3R.4 | 2026-07-19 | (uncommitted) |
| `PASS_A1A_GATE3R_5_MIGRATION_PORTABILITY_VERIFIED` + `PARTIAL_BLOCKED_BY_POSTGRES_MIGRATION_NOT_VERIFIED` | 3R.5 | 2026-07-19 | (uncommitted) |
| `PASS_A1A_GATE3R_6_RUNTRACE_SSE_BROWSER_E2E_VERIFIED` | 3R.6 | 2026-07-19 | (uncommitted) |
| (pending) `PASS_A1A_GATE3R_*_VERIFIED` (cumulative) | 3R.9 | TBD | TBD |

All verdicts use the charter allowlist (§22). No forbidden verdicts
issued.

---

## §6. How to re-verify

### §6.1 Re-run the test suite

```bash
cd backend
python -m pytest tests/test_api/test_a1a_gate3r_*.py -v
# Expected: 59 passed
```

### §6.2 Re-verify migration state

```bash
cd backend
python -m alembic current
# Expected: 020 (head)

python -c "
import sqlite3
conn = sqlite3.connect('data/icoder.db')
print(conn.execute('SELECT version_num FROM alembic_version').fetchone())
print(conn.execute('PRAGMA table_info(run_trace_events)').fetchall())
print(conn.execute(
    \"SELECT trace_capture_status, COUNT(*) FROM run_history GROUP BY trace_capture_status\"
).fetchall())
"
```

### §6.3 Re-verify orphan-run denial (live)

```bash
# Mint a token for a non-existent run
python -c "
from app.services.trace_token import issue_trace_token
print(issue_trace_token(run_id='run-audit-repro-nonexistent', organization_id='org_default1'))
"
# Then curl the trace endpoint with that token — expect HTTP 404 TRACE_NOT_FOUND
```

### §6.4 Re-verify browser evidence

Open `reports/phase-a1a/screenshots/gate3r6/01_runtrace_timeline.png`
in any image viewer. Confirm:
- Header reads "RunTrace / run_id: run-3r6-browser-e2e / 7 steps · 7 ok · 1234ms total"
- Timeline shows all 7 events grouped into pre-dispatcher / dispatcher / post-dispatcher segments
- Step 4 (工具调用) shows duration 800.0ms

### §6.5 Re-verify audit emit coverage

```bash
cd backend
python -c "
import sqlite3
conn = sqlite3.connect('data/icoder.db')
for row in conn.execute(
    'SELECT action, COUNT(*) FROM audit_logs GROUP BY action ORDER BY action'
).fetchall():
    print(row)
"
# Expected: now-nonzero counts for run.start, run.complete (post-test-runs);
# api_client.rotate may still be 0 if no test exercised rotation this session.
```

---

## §7. Out-of-scope artifacts (NOT counted as Gate 3R evidence)

These artifacts exist in the repo but are NOT part of Gate 3R's
evidence chain:

- `docs/audit/` — separate audit workstream
- `docs/corti_parity/phase7_gate13a/` — Phase 7 Gate 13A work
- `reports/comprehensive-audit/` — separate comprehensive audit workstream
- `gate3-8-browser-evidence.png` (at repo root) — should be moved
  under `reports/phase-a1a/` in a future cleanup; not blocking
- `backend/data/icoder.db.gate3-prerelease` — pre-release snapshot
  referenced in §3.3 above but not load-bearing for any Gate 3R claim

---

## §8. Charter cross-reference

| Charter §item | Gate | Primary evidence |
|---|---|---|
| §3.0 baseline | 3.0 | `A1A_GATE3_0_BASELINE_AND_GATE2_CARRYOVER.md` |
| §3.1 legacy tenancy | 3.1 | `A1A_GATE3_1_LEGACY_TENANCY_RECONCILIATION.md` + 244-row classification |
| §3.2 quarantine + read policy | 3.2 | `A1A_GATE3_2_QUARANTINE_AND_TENANT_READ_POLICY.md` + `app/services/tenant_read_policy.py` |
| §3.3 DB-backed trace | 3.3 | `A1A_GATE3_3_DATABASE_BACKED_TRACE_PERSISTENCE.md` + Migration 019 |
| §3.4 SSE isolation | 3.4 | `A1A_GATE3_4_SSE_TENANT_ISOLATION.md` + `test_phase7_gate9_sse_run_events.py` |
| §3.5 console trace isolation | 3.5 | `A1A_GATE3_5_CONSOLE_TRACE_TENANT_ISOLATION.md` + `test_a1a_gate3_5_console_trace_isolation.py` |
| §3.6 audit coverage + system tenant | 3.6 | `A1A_GATE3_6_AUDIT_LOG_COVERAGE_AND_SYSTEM_TENANT_SEPARATION.md` + `system_audit.py` allowlist |
| §3.7 DB constraints + fail-closed | 3.7 | `A1A_GATE3_7_DB_CONSTRAINTS_AND_FAIL_CLOSED_POLICY.md` + Migration 019 CHECK constraints |
| §3.8 regression + security negative | 3.8 | `A1A_GATE3_8_REGRESSION_SECURITY_NEGATIVE_BROWSER_EVIDENCE.md` + 19-case negative spine |
| §3R.0 baseline re-audit | 3R.0 | `A1A_GATE3R_0_BASELINE_AND_CARRYOVER_RE_AUDIT.md` |
| §3R.1 orphan-run resolver | 3R.1 | `A1A_GATE3R_1_AUTHORITATIVE_RUN_RESOLVER.md` + 12-test suite |
| §3R.2 audit emit wiring | 3R.2 | `A1A_GATE3R_2_MATERIAL_AUDIT_EMIT_WIRING.md` + 7-test suite + 6 emit call sites |
| §3R.3 trace_capture_status + profiles | 3R.3 | `A1A_GATE3R_3_TRACE_CAPTURE_STATUS_AND_PROFILES.md` + 21-test suite + 2 new services |
| §3R.4 stable event identity | 3R.4 | `A1A_GATE3R_4_TRACE_EVENT_IDENTITY.md` + Migration 020 + 12-test suite |
| §3R.5 migration portability | 3R.5 | `A1A_GATE3R_5_MIGRATION_PORTABILITY.md` + 7-test suite (PG partial) |
| §3R.6 RunTrace + SSE browser E2E | 3R.6 | `A1A_GATE3R_6_RUNTRACE_SSE_BROWSER_E2E.md` + 2 screenshots + 9-criteria matrix |
| §3R.7 addendum + manifest + ledger | 3R.7 | `A1A_GATE3_ADDENDUM.md` + **this file** + `A1A_GATE3R_ISSUE_LEDGER.md` |
| §3R.8 regression + negative tests | 3R.8 | (next gate) |
| §3R.9 commit + final verdict | 3R.9 | (final gate) |

---

## §9. Forbidden list re-confirmation

This manifest does NOT:

- Issue a verdict (it's an index, not a closure)
- Modify any historical Gate 3 report
- Claim PostgreSQL verification (env-blocked, partial verdict)
- Push the branch or open a PR
- Add code or tests (it's documentation only)
- Reference any artifact outside the repo tree

Forbidden verdicts (charter §22) remain forbidden.
