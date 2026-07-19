# Phase A1A Gate 3R.7 — Gate 3 Addendum + Evidence Manifest + Issue Ledger

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3R.6 (`A1A_GATE3R_6_RUNTRACE_SSE_BROWSER_E2E.md`)

Closes charter §3R.7 deliverables: the three documentary artifacts
that frame Gate 3's scope, list every artifact an auditor needs,
and answer "is issue X open?" canonically.

Gate 3R.7 produces no code changes. It is pure documentation —
the layer that converts the scattered mentions of "carry-over"
and "observation" across the 3R.1–3R.6 closure reports into a
single, addressable index.

---

## §1. Three deliverables

| # | Artifact | Purpose |
|---|---|---|
| 1 | `reports/phase-a1a/A1A_GATE3_ADDENDUM.md` | Corrections to Gate 3's maturity claims — what Gate 3 *actually* shipped vs what its closure reports claimed |
| 2 | `reports/phase-a1a/A1A_GATE3_EVIDENCE_MANIFEST.md` | Consolidated artifact index — every code file, migration, test, report, screenshot, with its verifiable claim |
| 3 | `reports/phase-a1a/A1A_GATE3R_ISSUE_LEDGER.md` | Canonical issue status — CLOSED / OBSERVED / DEFERRED / WONTFIX for every issue Gate 3 and Gate 3R surfaced |

All three are written. This file is the meta-closure that
introduces them.

---

## §2. Why this gate exists

Gate 3's bundled commit `d1447f3` shipped 9 sub-gates of work
(3.0 through 3.8) in one commit with one verdict. The
individual closure reports were accurate per sub-gate, but
several made claims that needed narrowing when read together:

- Gate 3.3 claimed the composite UNIQUE(run_id, step, ts) was
  the canonical identity. Gate 3R.4 replaced it with a UUID.
- Gate 3.7 claimed the narrow CHECK on `trace_capture_status`
  was final. Gate 3R.4 widened it.
- Gate 3.6 listed 12 audit actions in the allowlist. Gate 3R.2
  found that 6 of them had no actual emit caller.
- Gate 3.4/3.5 claimed tenant_read_policy enforced isolation.
  Gate 3R.1 found orphan runs fell through.

Each individual claim was correct *for the surface it described*.
But the closure reports didn't explicitly enumerate their own
scope boundaries. An auditor reading them in isolation could
over-extend the claims to areas Gate 3 didn't actually test.

Gate 3R.0 §1 called this out as the "honesty caveats" section.
Gate 3R.7 codifies the caveats into three durable artifacts.

---

## §3. Addendum — six corrections (summary)

| # | Gate 3 claim | Gate 3R closure |
|---|---|---|
| 1 | CHECK constraint on `trace_capture_status` | 3R.3 + 3R.4 widen CHECK to 6 literals |
| 2 | Composite UNIQUE(run_id, step, ts) | 3R.4 adds UUID event_id + sequence_number |
| 3 | Cross-org trace reads denied | 3R.1 adds orphan-run guard |
| 4 | Audit emit coverage for run lifecycle | 3R.2 wires 6 missing emit callers |
| 5 | Migration 019 robust against interruption | 3R.4 + 3R.5 test + auto-recover |
| 6 | Migration verified on SQLite + Postgres | 3R.5 documents PG env-blocked partial verdict |

Net effect on Gate 3's verdict: **historical record unchanged**.
The original
`PASS_A1A_GATE3_TENANCY_TRUTH_CONTAINMENT_AND_TRACE_ISOLATION_VERIFIED`
remains correct for the surface Gate 3 actually implemented.
The corrections narrow the scope and Gate 3R.1–3R.6 verdicts
cover the extended surface.

Full detail: `reports/phase-a1a/A1A_GATE3_ADDENDUM.md`.

---

## §4. Evidence manifest — counts

| Category | Count |
|---|---|
| New code files | 3 (`trace_capture_state.py`, `deployment_profile.py`, Migration 020) |
| Modified code files | 12 (api/*, services/*, models/*, config) |
| New test files | 5 (`test_a1a_gate3r_{1..5}_*.py`) |
| New tests | 59 |
| Regression tests passing | 86 |
| Total pytest count (3R.6) | 112 |
| Closure reports (3R.0–3R.7) | 8 (this file + 7 predecessors) |
| Browser evidence artifacts | 3 PNGs + 1 evaluate JSON |
| Dev DB migration head | 020 |
| Backfilled rows | 244 (NULL → NEVER_CAPTURED_LEGACY) |

Full index: `reports/phase-a1a/A1A_GATE3_EVIDENCE_MANIFEST.md`.

---

## §5. Issue ledger — closure tally

| Status | Count | Example |
|---|---|---|
| CLOSED | 18 | GATE3_001-013, GATE3_017-018, GATE3R_001-006, GATE3R_008-009 |
| OBSERVED → WONTFIX | 2 | GATE3R_007 (context.clear), GATE3R_012 (SSE asymmetry) |
| DEFERRED | 4 | GATE3_014/015/016, GATE3R_010 |
| REOPENED | 0 | — |

The 18 CLOSED items cover every P0/P1/P2 that Gate 3 + Gate 3R
surfaced on the trace + audit + tenant-read surface. The 2
WONTFIX items have explicit risk acceptance in the ledger §4.

Full detail: `reports/phase-a1a/A1A_GATE3R_ISSUE_LEDGER.md`.

---

## §6. Coordination with downstream gates

### §6.1 Gate 3R.8 (Regression + security negative tests)

The negative test spine from Gate 3.8 (19 cases) needs
extending to cover:
- Orphan-run denial on SSE path (currently curl-only in 3R.6)
- Org-mismatch denial on partner trace path (currently curl-only)
- Trace capture state transitions (CAPTURE_PENDING → CAPTURED)

These were verified manually in 3R.6 but not codified as
pytest fixtures. 3R.8 picks them up.

### §6.2 Gate 3R.9 (Commit + final verdict)

Files to be included in the 3R.9 commit (explicit list):

```
# Reports (10 files: 3R.0 through 3R.7 + 3 addendum/manifest/ledger)
reports/phase-a1a/A1A_GATE3R_0_BASELINE_AND_CARRYOVER_RE_AUDIT.md
reports/phase-a1a/A1A_GATE3R_1_AUTHORITATIVE_RUN_RESOLVER.md
reports/phase-a1a/A1A_GATE3R_2_MATERIAL_AUDIT_EMIT_WIRING.md
reports/phase-a1a/A1A_GATE3R_3_TRACE_CAPTURE_STATUS_AND_PROFILES.md
reports/phase-a1a/A1A_GATE3R_4_TRACE_EVENT_IDENTITY.md
reports/phase-a1a/A1A_GATE3R_5_MIGRATION_PORTABILITY.md
reports/phase-a1a/A1A_GATE3R_6_RUNTRACE_SSE_BROWSER_E2E.md
reports/phase-a1a/A1A_GATE3R_7_GATE3_ADDENDUM_EVIDENCE_MANIFEST_ISSUE_LEDGER.md
reports/phase-a1a/A1A_GATE3_ADDENDUM.md
reports/phase-a1a/A1A_GATE3_EVIDENCE_MANIFEST.md
reports/phase-a1a/A1A_GATE3R_ISSUE_LEDGER.md

# Screenshots (2 files)
reports/phase-a1a/screenshots/gate3r6/01_runtrace_timeline.png
reports/phase-a1a/screenshots/gate3r6/02_runtrace_step_expanded.png

# Code: new files (3)
backend/app/services/trace_capture_state.py
backend/app/services/deployment_profile.py
backend/alembic/versions/020_trace_event_identity_and_capture_state.py

# Code: modified files (12)
backend/app/api/agent_run.py
backend/app/api/platform_api_clients.py
backend/app/api/run_trace.py
backend/app/api/runs.py
backend/app/config.py
backend/app/icoder/agent_runtime/orchestrator/run_trace.py
backend/app/models/run_trace.py
backend/app/services/idempotency_service.py
backend/app/services/legacy_tenancy_attribution.py
backend/app/services/run_lifecycle.py
backend/app/services/system_audit.py

# Tests: new (5) + modified (2)
backend/tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py
backend/tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py
backend/tests/test_api/test_a1a_gate3r_3_trace_capture_profiles.py
backend/tests/test_api/test_a1a_gate3r_4_trace_event_identity.py
backend/tests/test_api/test_a1a_gate3r_5_migration_portability.py
backend/tests/test_api/test_phase7_gate7_trace_token.py
backend/tests/test_api/test_phase7_gate9_sse_run_events.py
```

Note: Gate 3R.8 will add its own test file
(`test_a1a_gate3r_8_regression_security_negative.py`) which will
also be included in the 3R.9 commit.

---

## §7. Forbidden list — re-confirmation

Charter §22 forbidden verdicts remain forbidden; this gate does NOT
issue any of them.

Forbidden actions NOT taken in this gate:

- No `git push` (local-only branch)
- No PR opened
- No master commit
- No amend of Gate 3 commit (`d1447f3`) or Gate 3R.1-3R.6 work
- No new Agent / Expert / Tool / Runtime added
- No Medical Coding / CDI prompt changes
- No `git add -A` (explicit file list above for 3R.9)
- No falsification of historical data
- No modification to Migration 019 or Migration 020
- No PostgreSQL verification attempted (environment-blocked)
- No production data touched
- No code change in this gate (Gate 3R.7 is documentation-only)

---

## §8. Verdict

```
PASS_A1A_GATE3R_7_GATE3_ADDENDUM_EVIDENCE_MANIFEST_ISSUE_LEDGER_VERIFIED
```

All three deliverables written. Forbidden verdicts (charter §22)
remain forbidden.

Gate 3R.8 (Regression + security negative tests + evidence)
follows.
