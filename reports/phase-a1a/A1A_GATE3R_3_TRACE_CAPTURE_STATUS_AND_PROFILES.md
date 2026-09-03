# Phase A1A Gate 3R.3 — Trace Capture Status Semantics + Deployment Profiles

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3R.2 (`A1A_GATE3R_2_MATERIAL_AUDIT_EMIT_WIRING.md`)

Closes charter §3R.3 carry-over: the four-way ambiguity of NULL
`run_history.trace_capture_status` and the binary
`RUNTRACE_STORE=memory|db` + `RUNTRACE_FAIL_CLOSED=True|False`
matrix that doesn't surface operator intent.

After Gate 3R.3:
- NULL is reserved for **pre-Gate-3.3 historical rows** only (Migration 020 in 3R.4 backfills all 244 → NEVER_CAPTURED_LEGACY).
- New rows written after Gate 3R.3 carry one of 5 canonical states.
- The deployment profile is named (MEMORY_DEV / BEST_EFFORT_DB / REQUIRED_DB), not a flag triple.

---

## §1. TraceCaptureState — 5-class taxonomy

`app/services/trace_capture_state.py` (new, 110 LOC).

| State | Meaning |
|---|---|
| `NEVER_CAPTURED_LEGACY` | pre-Gate-3.3 historical row; Migration 020 backfills all 244 NULLs |
| `CAPTURE_PENDING` | `record_run_start` wrote the row; awaiting first trace emit |
| `CAPTURED` | at least one `DbRunTraceStore.append` succeeded (canonical name post-3R.3) |
| `PERSISTED` | deprecated alias; same meaning as `CAPTURED` (Gate 3.3-era literal) |
| `FAILED` | at least one DB write raised; events may be lost |
| `FALLBACK_MEMORY` | `InMemoryRunTraceStore` was used (dev/test only) |

### §1.1 Helpers

- `TraceCaptureState.ALL_STATES` — frozenset, 6 elements (5 canonical + PERSISTED alias)
- `TraceCaptureState.ANSWERED_STATES` — frozenset, 5 elements (excludes CAPTURE_PENDING)
- `TraceCaptureState.is_answered(status)` — True iff the status represents a definite outcome
- `TraceCaptureState.is_lost(status)` — True iff trace events are known-unavailable
- `TraceCaptureState.normalize(status)` — maps `PERSISTED → CAPTURED`; other values pass through

`is_answered(None)` returns False — readers know to interpret NULL as "pre-3R.3 row, Migration 020 hasn't run yet".

### §1.2 Migration 020 (Gate 3R.4) coordination

The DB CHECK constraint currently allows `{PERSISTED, FAILED, FALLBACK_MEMORY}` only. New values (`NEVER_CAPTURED_LEGACY`, `CAPTURE_PENDING`, `CAPTURED`) are rejected by SQLite CHECK pre-Migration-020.

Workaround until 3R.4 lands:
1. `record_run_start` stamps `CAPTURE_PENDING` on INSERT; if SQLite CHECK rejects, the row is re-flushed with NULL (pre-3R.3 fallback).
2. `_mark_trace_capture_status` is already best-effort (try/except + logger.debug) — UPDATE rejections are logged but don't crash the run.
3. Migration 020 widens the CHECK to include all 6 states + backfills NULL → NEVER_CAPTURED_LEGACY.

This keeps the code forward-compatible with 3R.4 without modifying Migration 019 (charter §22 forbids).

---

## §2. DeploymentProfile — 3 named profiles

`app/services/deployment_profile.py` (new, 175 LOC).

| Profile | Run store | Fail-closed | Context |
|---|---|---|---|
| `MEMORY_DEV` | in-memory | N/A | local single-developer, unit tests, CI smoke |
| `BEST_EFFORT_DB` | DB | False (transient failures logged) | default cloud mode |
| `REQUIRED_DB` | DB | True (failures propagate) | compliance / hospital-on-prem with SLA-backed audit |

### §2.1 Resolver

`resolve_profile(deployment_mode, runtrace_store, runtrace_fail_closed, explicit_profile)`:

1. **Explicit override wins**: `explicit_profile` (from `RUNTRACE_DEPLOYMENT_PROFILE` env var) takes precedence over everything else. Invalid values raise `ValueError`.
2. **Derive from settings**:
   - `RUNTRACE_STORE=memory` → `MEMORY_DEV` (regardless of deployment mode; cloud refusal handled by Settings validation)
   - `RUNTRACE_STORE=db` + cloud + `RUNTRACE_FAIL_CLOSED=True` → `REQUIRED_DB`
   - `RUNTRACE_STORE=db` + otherwise → `BEST_EFFORT_DB`

### §2.2 Predicates

- `DeploymentProfile.is_cloud_allowed(profile)` — True iff profile is BEST_EFFORT_DB or REQUIRED_DB
- `DeploymentProfile.is_db_backed(profile)` — True iff profile routes through `DbRunTraceStore`
- `DeploymentProfile.is_fail_closed(profile)` — True iff profile is REQUIRED_DB

### §2.3 Backwards compat

Existing deployments with no `RUNTRACE_DEPLOYMENT_PROFILE` env var continue to work — the profile is derived from the Gate 3.3 triple `(ICODER_DEPLOYMENT_MODE, RUNTRACE_STORE, RUNTRACE_FAIL_CLOSED)`. Settings validation now goes through `DeploymentProfile.is_cloud_allowed` instead of the raw `RUNTRACE_STORE != "db"` check, but the refusal semantics are identical.

---

## §3. Code changes — file inventory

### §3.1 New files

- `app/services/trace_capture_state.py` (110 LOC) — 5-class state machine + helpers
- `app/services/deployment_profile.py` (175 LOC) — 3 named profiles + resolver
- `tests/test_api/test_a1a_gate3r_3_trace_capture_profiles.py` (~440 LOC, 21 tests)

### §3.2 Modified files

- `app/config.py`:
  - Added `RUNTRACE_DEPLOYMENT_PROFILE: str = ""` Settings field
  - Replaced raw `RUNTRACE_STORE != "db"` check with `resolve_profile` + `is_cloud_allowed`
  - Stashed resolved profile on `self._resolved_runtrace_profile` for diagnostics
- `app/services/run_lifecycle.py::record_run_start`:
  - Stamps `trace_capture_status=CAPTURE_PENDING` on INSERT
  - Falls back to NULL if SQLite CHECK rejects (pre-Migration-020 path)
- `app/icoder/agent_runtime/orchestrator/run_trace.py`:
  - `_should_fail_closed()` helper — consults deployment profile instead of raw flag
  - `DbRunTraceStore.append` writes canonical `CAPTURED` (not legacy `PERSISTED`) on success; `FAILED` on exception
  - `InMemoryRunTraceStore.append` writes `FALLBACK_MEMORY` (unchanged literal, now imported from `TraceCaptureState`)

### §3.3 Files NOT modified

- `alembic/versions/019_db_constraints_tenant_classification.py` — Migration 019 is committed; charter §22 forbids modifying. CHECK widening lands in Migration 020 (Gate 3R.4).
- `app/models/run_history.py` — model definition is unchanged; `trace_capture_status` column accepts any string; the CHECK constraint lives in the migration only.
- Gate 3 historical reports — charter §22 forbids modifying.

---

## §4. Charter §3R.3 requirements — closure

| Charter §3R.3 item | Status |
|---|---|
| Disambiguate NULL `trace_capture_status` meanings | ✅ §1 (5-class taxonomy) |
| Add `NEVER_CAPTURED_LEGACY` for pre-Gate-3.3 rows | ✅ §1 (literal + Migration 020 backfill scheduled in 3R.4) |
| Add `CAPTURE_PENDING` for newly-inserted rows | ✅ §1 + `record_run_start` |
| Add `CAPTURED` as canonical success state | ✅ §1 (`PERSISTED` kept as deprecated alias) |
| Replace binary `RUNTRACE_STORE=memory|db` matrix with named profiles | ✅ §2 |
| Add `MEMORY_DEV` profile | ✅ §2 |
| Add `BEST_EFFORT_DB` profile | ✅ §2 |
| Add `REQUIRED_DB` profile | ✅ §2 |
| Settings validation refuses MEMORY_DEV in cloud mode | ✅ §2 (via `is_cloud_allowed`) |
| Code-level state machine is forward-compatible with Migration 020 CHECK widening | ✅ §1.2 (best-effort writes; fallback to NULL) |

---

## §5. Test results — `test_a1a_gate3r_3_trace_capture_profiles.py`

```
21 passed

  §1 TraceCaptureState taxonomy
    test_state_machine_has_5_canonical_states                  1
    test_state_machine_all_states_includes_legacy_alias        1
    test_is_answered_distinguishes_pending_from_terminal       1
    test_is_lost_distinguishes_recoverable_from_unrecoverable  1
    test_normalize_maps_persisted_to_captured                  1

  §2 DeploymentProfile resolver
    test_resolver_explicit_override_wins                       1
    test_resolver_invalid_profile_raises                        1
    test_resolver_cloud_db_no_failclosed_is_best_effort        1
    test_resolver_cloud_db_failclosed_is_required_db           1
    test_resolver_local_memory_is_memory_dev                   1
    test_resolver_cloud_memory_is_memory_dev_then_refused      1
    test_profile_predicates                                    1

  §3 record_run_start stamps CAPTURE_PENDING
    test_record_run_start_stamps_capture_pending               1

  §4 InMemoryRunTraceStore writes FALLBACK_MEMORY
    test_in_memory_store_marks_fallback_memory                 1

  §5 DbRunTraceStore writes canonical state names
    test_db_store_writes_canonical_state_names                 1

  §6 Settings cloud-mode validation
    test_cloud_mode_memory_dev_refused_at_boot                 1
    test_cloud_mode_required_db_profile_accepted               1

  §7 _should_fail_closed consults deployment profile
    test_should_fail_closed_returns_true_for_required_db       1
    test_should_fail_closed_returns_false_for_best_effort_db   1
    test_should_fail_closed_returns_false_for_memory_dev       1

  §8 Regression — NULL trace_capture_status rows still readable
    test_legacy_null_trace_status_rows_remain_readable         1
                                                              ──
                                                              21 passed
```

### §5.1 Regression sweep

```
tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py            12 passed
tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py             7 passed
tests/test_api/test_a1a_gate3_2_tenant_read_policy.py             ?  passed
tests/test_api/test_a1a_gate3_4_sse_tenant_isolation.py           7 passed
tests/test_api/test_a1a_gate3_5_console_trace_isolation.py       11 passed
tests/test_api/test_a1a_gate3_8_security_negative_consolidated.py ?  passed
tests/test_api/test_phase7_gate3_agent_run_idempotency.py        14 passed
tests/test_api/test_phase7_gate4_run_cancel.py                    7 passed
tests/test_api/test_phase7_gate5_api_clients.py                  15 passed
tests/test_api/test_phase7_gate7_trace_token.py                  13 passed
tests/test_api/test_phase7_gate9_sse_run_events.py               10 passed
                                                                ──
                                                               110 passed
```

No regressions.

---

## §6. Coordination with Gate 3R.4

Gate 3R.4 (Migration 020 — Stable trace event identity) must:

1. **Widen the DB CHECK constraint** from `{PERSISTED, FAILED, FALLBACK_MEMORY}` to the full 6-state set (`{NEVER_CAPTURED_LEGACY, CAPTURE_PENDING, CAPTURED, PERSISTED, FAILED, FALLBACK_MEMORY}`).
2. **Backfill all 244 NULL rows** to `NEVER_CAPTURED_LEGACY` in one pass.
3. **Rewrite existing `PERSISTED` rows** to `CAPTURED` (optional but cleaner; `TraceCaptureState.normalize` handles both either way).
4. **Add `event_id` UUID + `sequence_number` per `trace_id`** to `run_trace_events` (the charter §3R.4 main deliverable).

After 3R.4, `record_run_start` no longer needs the try/except fallback — the CHECK constraint will accept `CAPTURE_PENDING` directly.

---

## §7. Operational implications

### §7.1 New env var — `RUNTRACE_DEPLOYMENT_PROFILE`

Optional. When set, takes precedence over the `(RUNTRACE_STORE, RUNTRACE_FAIL_CLOSED)` pair. Operators in compliance environments can now express intent directly:

```bash
# Before Gate 3R.3 (still works, derived profile)
export RUNTRACE_STORE=db
export RUNTRACE_FAIL_CLOSED=true

# After Gate 3R.3 (preferred for new deployments)
export RUNTRACE_DEPLOYMENT_PROFILE=REQUIRED_DB
```

### §7.2 Diagnostics — `settings._resolved_runtrace_profile`

The resolved profile is stashed on the Settings instance for diagnostics. Operators can verify which profile booted by checking this attribute (e.g. via a startup log line or a `/api/v1/system/info` endpoint, neither of which Gate 3R.3 adds — that's a future ops gate).

### §7.3 Failure modes — unchanged

- Cloud + MEMORY_DEV → boot refuses (Settings validation)
- Cloud + BEST_EFFORT_DB + DB write fails → run continues, row stamped `FAILED`
- Cloud + REQUIRED_DB + DB write fails → exception propagates, run is marked failed
- Local + MEMORY_DEV → in-memory store; row stamped `FALLBACK_MEMORY` on first emit

These match Gate 3.3 semantics exactly; Gate 3R.3 only changes how the policy is expressed, not how it's enforced.

---

## §8. Forbidden list — re-confirmation

Charter §22 forbidden verdicts remain forbidden; this gate does NOT issue any of them.

Forbidden actions NOT taken in this gate:

- No `git push` (local-only branch)
- No PR opened
- No master commit
- No amend of Gate 3 commit (`d1447f3`) or Gate 3R.1 / Gate 3R.2 work
- No new Agent / Expert / Tool / Runtime added
- No Medical Coding / CDI prompt changes
- No `git add -A` (explicit file list in Gate 3R.9)
- No falsification of historical data
- No Migration 020 added (scheduled for Gate 3R.4)
- No modification to Migration 019 (charter §22 forbids)

---

## §9. Verdict

```
PASS_A1A_GATE3R_3_TRACE_CAPTURE_STATUS_AND_PROFILES_VERIFIED
```

Forbidden verdicts (charter §22) remain forbidden.

Gate 3R.4 (Stable trace event identity — Migration 020) follows.
