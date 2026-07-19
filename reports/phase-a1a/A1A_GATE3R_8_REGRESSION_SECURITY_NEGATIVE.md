# Phase A1A Gate 3R.8 — Cross-gate Regression + Security Negative Tests

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3R.7 (`A1A_GATE3R_7_GATE3_ADDENDUM_EVIDENCE_MANIFEST_ISSUE_LEDGER.md`)

Closes charter §3R.8: extend the Gate 3.8 negative spine (Layers
1–6) with the new defence-in-depth established by Gate 3R.1–3R.6
(Layers 7–12), and prove the full Phase A1A + Phase 7 regression
sweep still passes.

Gate 3R.8 produces one new test file plus the cross-gate regression
sweep evidence. No code changes.

---

## §1. Deliverable

| Artifact | Path | Tests |
|---|---|---|
| Cross-gate negative spine extension | `backend/tests/test_api/test_a1a_gate3r_8_regression_security_negative.py` | 20 |
| This closure report | `reports/phase-a1a/A1A_GATE3R_8_REGRESSION_SECURITY_NEGATIVE.md` | — |

---

## §2. Layered invariants under test

| Layer | Gate | Charter ref | Invariant |
|---|---|---|---|
| 1 | 2 / 3.1 | §3.1 | classify_modern_write refuses NULL org writes in cloud mode |
| 2 | 3.7 | §3.7 | DB CHECK rejects invalid tenancy_classification / trace_capture_status |
| 3 | 3.2 | §3.2 | tenant_read_policy filter excludes invisible classes from list endpoints |
| 4 | 3.2 | §3.2 | point-lookup returns exact 404 for invisible rows (no existence leak) |
| 5 | 3.4 / 3.5 | §3.4, §3.5 | SSE + Console trace denial returns exact 404 for invisible classifications |
| 6 | 3.6 | §3.6 | system_audit refuses non-allowlist actions |
| **7** | **3R.1** | **§3R.1** | **Orphan-run denial — token valid, no RunHistory row → 404 on trace + SSE** |
| **8** | **3R.2** | **§3R.2** | **Audit emit coverage — material callers fire on run lifecycle** |
| **9** | **3R.3** | **§3R.3** | **TraceCaptureState + DeploymentProfile — 6 literals + 5-case matrix** |
| **10** | **3R.4** | **§3R.4** | **Stable event identity — UUID v4 + monotonic sequence** |
| **11** | **3R.5** | **§3R.5** | **Migration 020 — fresh DB lands at 020; idempotent re-run is no-op** |
| **12** | **3R.6** | **§3R.6** | **Cross-org denial — token org != row org → 403 (trace) / 404 (SSE)** |

Layers 1–6 are tested by `test_a1a_gate3_8_security_negative_consolidated.py`
(19 cases, unchanged from Gate 3.8).

Layers 7–12 are tested by `test_a1a_gate3r_8_regression_security_negative.py`
(20 new cases).

---

## §3. New test file — 20 tests across 6 layers

### §3.1 Layer 7 — Orphan-run denial (3 tests)

```
test_L7_partner_trace_orphan_run_denied
test_L7_console_trace_orphan_run_denied
test_L7_partner_sse_orphan_run_denied
```

Each test mints a signed trace token for a run that has no
RunHistory row, then verifies the corresponding endpoint
returns HTTP 404 TRACE_NOT_FOUND (not the events that might
be lurking in the store).

### §3.2 Layer 8 — Audit emit coverage (3 tests)

```
test_L8_run_lifecycle_actions_in_allowlist
test_L8_run_lifecycle_actions_classified_correctly
test_L8_record_run_start_stamps_capture_pending
```

The first two verify the six lifecycle actions (run.cancel,
run.timeout, run.complete, run.failed, idempotency.dedup,
api_client.rotate) are in both the system_audit allowlist AND
the legacy_tenancy_attribution SYSTEM_AUDIT_ACTIONS set.
This catches a subtle regression: an action could be in one
list but not the other, and the emit caller would silently
fail at runtime.

The third verifies `record_run_start` stamps
`trace_capture_status=CAPTURE_PENDING` on INSERT (Gate 3R.3 +
3R.4 behaviour).

### §3.3 Layer 9 — TraceCaptureState + DeploymentProfile (3 tests)

```
test_L9_trace_capture_state_only_six_literals
test_L9_normalize_persisted_to_captured
test_L9_deployment_profile_matrix
```

The matrix test covers 6 derivation cases:

| Mode | Store | Fail-closed | Expected profile |
|---|---|---|---|
| cloud | memory | False | MEMORY_DEV (Settings validation will refuse boot) |
| cloud | db | True | REQUIRED_DB |
| local | db | True | BEST_EFFORT_DB |
| local | db | False | BEST_EFFORT_DB |
| local | memory | False | MEMORY_DEV |
| (any) | (any) | (any) + explicit override | the override |

### §3.4 Layer 10 — Stable event identity (2 tests)

```
test_L10_event_id_is_uuid_v4_shaped
test_L10_sequence_counter_monotonic_per_trace
```

Verifies every `event_id` is a 36-char UUID v4 string and
the per-trace `sequence_number` is strictly monotonic from 1.

### §3.5 Layer 11 — Migration 020 idempotency (2 tests)

```
test_L11_migration_head_is_020_on_fresh_db
test_L11_migration_idempotent_rerun
```

Runs `alembic upgrade head` against a fresh temp DB and
verifies the version lands at 020 with the 4 new columns
present. The second test re-runs `upgrade head` and verifies
it's a silent no-op.

### §3.6 Layer 12 — Cross-org denial matrix (2 tests)

```
test_L12_partner_trace_cross_org_denied     → 403 TRACE_TOKEN_ORG_MISMATCH
test_L12_partner_trace_valid_org_accepted   → 404 TRACE_NOT_FOUND (no events)
```

The positive case (`_valid_org_accepted`) is the regression
guard: it proves the cross-org check doesn't accidentally
reject same-org tokens.

### §3.7 Layer 13 — Module import sweep (5 parametrized)

```
test_L13_module_imports_clean[gate3r_1]
test_L13_module_imports_clean[gate3r_2]
test_L13_module_imports_clean[gate3r_3]
test_L13_module_imports_clean[gate3r_4]
test_L13_module_imports_clean[gate3r_5]
```

Each test imports one of the per-gate test modules and
asserts it has ≥5 test functions. Catches import-time
regressions (removed helper, renamed constant) that would
only surface when pytest collects the file in a fresh run.

---

## §4. Test results — `test_a1a_gate3r_8_regression_security_negative.py`

```
20 passed

  Layer 7 — Orphan-run denial                                     3
  Layer 8 — Audit emit coverage                                   3
  Layer 9 — TraceCaptureState + DeploymentProfile                 3
  Layer 10 — Stable event identity                                2
  Layer 11 — Migration 020 idempotency                            2
  Layer 12 — Cross-org denial matrix                              2
  Layer 13 — Module import sweep                                  5
                                                                  ──
                                                                  20 passed
```

Wall time: 42.14s. The L11 migration tests dominate (~25s)
because each spawns a subprocess to invoke alembic.

---

## §5. Full Phase A1A + Phase 7 regression sweep

```
tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py            12 passed
tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py             7 passed
tests/test_api/test_a1a_gate3r_3_trace_capture_profiles.py       21 passed
tests/test_api/test_a1a_gate3r_4_trace_event_identity.py         12 passed
tests/test_api/test_a1a_gate3r_5_migration_portability.py         7 passed
tests/test_api/test_a1a_gate3r_8_regression_security_negative.py 20 passed
tests/test_api/test_a1a_gate3_8_security_negative_consolidated.py 19 passed
tests/test_api/test_phase7_gate3_agent_run_idempotency.py        14 passed
tests/test_api/test_phase7_gate4_run_cancel.py                    7 passed
tests/test_api/test_phase7_gate7_trace_token.py                  13 passed
tests/test_api/test_phase7_gate9_sse_run_events.py               10 passed
                                                                  ──
                                                                 132 passed
```

Wall time: 231.82s (~3m52s). No regressions, no skipped tests.

### §5.1 Coverage delta from Gate 3R.6

| Test count | Before 3R.8 | After 3R.8 | Δ |
|---|---|---|---|
| Gate 3R dedicated tests | 59 | 59 | 0 |
| Gate 3R.8 cross-gate spine | 0 | 20 | +20 |
| **Total** | **59** | **79** | **+20** |

The cross-gate spine tests are not redundant with the per-gate
suites — they cover scenarios that span 2+ gates:

- L7 partner trace orphan-run: covers Gate 3R.1 orphan guard +
  Gate 3R.4 partner token verification path.
- L8 allowlist: covers Gate 3R.2 emit callers + Gate 3R.3
  classifier integration.
- L11 migration idempotency: covers Gate 3R.4 Migration 020 +
  Gate 3R.5 portability design.
- L12 cross-org: covers Gate 3R.1 + Gate 3R.6 token binding.

---

## §6. Errors surfaced and fixed during Gate 3R.8 development

Five tests failed on the first run and were fixed:

### §6.1 L7 partner trace orphan-run (1 fix)

**Failure**: HTTP 401 Unauthorized.

**Root cause**: The test created a fresh `TestClient(app)` inside
the test function. The autouse `_install_auth_bypass` fixture
installs dependency overrides on the app singleton, but creating
a new TestClient triggered a lifespan event that may have reset
state.

**Fix**: Use the `client` fixture instead of creating a fresh
TestClient. Mirrors the pattern in `test_a1a_gate3r_1_orphan_run_denial.py`.

### §6.2 L8 run lifecycle emits (2 fixes)

**Failure**: `ImportError: cannot import name 'record_run_completion'`.

**Root cause**: I assumed function names that don't exist. The
actual public API is `record_run_start` + `set_status` +
`request_cancel` + `mark_client_aborted`. There is no
`record_run_completion` / `record_run_failure` helper.

**Fix**: Reframe the L8 tests to verify (a) the action strings
are in the allowlist + classifier set (regression guard against
accidental removal), and (b) `record_run_start` stamps
`trace_capture_status=CAPTURE_PENDING` on INSERT. The actual
emit-path tests already live in `test_a1a_gate3r_2_audit_emit_wiring.py`
and aren't duplicated here.

### §6.3 L9 deployment profile matrix (1 fix)

**Failure**: `assert MEMORY_DEV == REQUIRED_DB`.

**Root cause**: I assumed cloud mode forces REQUIRED_DB inside
`resolve_profile()`. Actually, the resolver just reflects intent
from the triple — the cloud-vs-memory refusal is enforced later
by Settings validation. The resolver returns MEMORY_DEV for
cloud+memory and lets Settings decide.

**Fix**: Update the test expectations to match the actual
contract: cloud+memory → MEMORY_DEV (Settings will refuse boot
separately).

### §6.4 L12 partner trace (same client issue as L7)

**Failure**: HTTP 401 Unauthorized.

**Fix**: Use `client` fixture.

All five fixes are in the committed test file. No code outside
tests was modified.

---

## §7. Coordination with Gate 3R.9

### §7.1 Files added in this gate

```
backend/tests/test_api/test_a1a_gate3r_8_regression_security_negative.py  (~340 LOC, 20 tests)
reports/phase-a1a/A1A_GATE3R_8_REGRESSION_SECURITY_NEGATIVE.md            (this file)
```

### §7.2 Updated evidence manifest entry

The Gate 3 Evidence Manifest §4.1 (test counts) should add:

```
test_a1a_gate3r_8_regression_security_negative.py    20    ✅ pass
```

bringing the Gate 3R test subtotal from 59 → 79 and the full
regression sweep from 112 → 132.

The manifest file itself doesn't need to be modified — the
counts flow through to the Gate 3R.9 final summary.

---

## §8. Forbidden list — re-confirmation

Charter §22 forbidden verdicts remain forbidden; this gate does NOT
issue any of them.

Forbidden actions NOT taken in this gate:

- No `git push` (local-only branch)
- No PR opened
- No master commit
- No amend of Gate 3 commit (`d1447f3`) or Gate 3R.1-3R.7 work
- No new Agent / Expert / Tool / Runtime added
- No Medical Coding / CDI prompt changes
- No `git add -A` (explicit file list in Gate 3R.9)
- No falsification of historical data
- No modification to Migration 019 or Migration 020
- No PostgreSQL verification attempted (environment-blocked)
- No production data touched
- No production code change in this gate (test-only)

---

## §9. Verdict

```
PASS_A1A_GATE3R_8_REGRESSION_SECURITY_NEGATIVE_VERIFIED
```

20 new negative tests + 132-test regression sweep all green.
Forbidden verdicts (charter §22) remain forbidden.

Gate 3R.9 (Commit with explicit file list + final verdict)
follows.
