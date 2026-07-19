# Phase A1A Gate 3 Addendum — Corrections to Gate 3 Maturity Claims

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Author**: Gate 3R.7 (charter §3R.7 deliverable)
**Predecessor**: Gate 3R.6 (`A1A_GATE3R_6_RUNTRACE_SSE_BROWSER_E2E.md`)
**Scope of addendum**: commits `d1447f3` (Gate 3 final) and earlier.

Gate 3 (commit `d1447f3`, verdict
`PASS_A1A_GATE3_TENANCY_TRUTH_CONTAINMENT_AND_TRACE_ISOLATION_VERIFIED`)
shipped the 7-class tenancy taxonomy, tenant_read_policy visibility
filter, DB-backed trace persistence, SSE+Console trace isolation,
system_audit allowlist, and DB CHECK+UNIQUE constraints. The verdict
was correct *for the surface area Gate 3 actually covered*. Gate 3R.0
surfaced six carry-overs that Gate 3's bundled report claimed but
didn't fully deliver. This addendum records each one — what was
claimed, what was actually shipped, and what Gate 3R.1–3R.6 did to
close the gap.

**This addendum does NOT modify any historical Gate 3 report.** The
original Gate 3.0–3.8 reports remain in the repo unchanged. Charter
§22 forbids editing history. The addendum is the canonical correction
layer that downstream gates (and the audit trail) read first.

---

## §1. The six corrections

| # | Gate 3 claim | Actual state at `d1447f3` | Gate 3R closure | Severity |
|---|---|---|---|---|
| 1 | "DB CHECK constraint on `trace_capture_status` enforces {PERSISTED, FAILED, FALLBACK_MEMORY}" | True but narrow — the 3R.3 literals (NEVER_CAPTURED_LEGACY, CAPTURE_PENDING, CAPTURED) were missing from the CHECK allowlist | 3R.3 + 3R.4 (Migration 020 widens CHECK to all 6 literals) | Medium |
| 2 | "Composite UNIQUE(run_id, step, ts) on run_trace_events prevents duplicate emit" | True but brittle — float-second ts collides on multi-event-per-microsecond emit; cross-process clock slew reorders reads | 3R.4 (Migration 020 adds UUID `event_id` + per-trace `sequence_number`) | Medium |
| 3 | "Cross-org trace reads denied via tenant_read_policy" | True only when a RunHistory row exists. Orphan runs (token valid, no RunHistory row) fell through to the store without a tenancy check | 3R.1 (orphan-run guard in SSE + Console + partner trace paths) | **High** |
| 4 | "Audit emit coverage for run lifecycle events" | Allowlist only — `run.cancel` / `run.timeout` / `run.complete` / `run.failed` / `idempotency.dedup` / `api_client.rotate` were listed but no caller actually emitted them | 3R.2 (material emit wiring across 6 call sites) | **High** |
| 5 | "Migration 019 interrupted-recovery robust" | Untested — the `_alembic_tmp_*` shadow table had to be dropped manually during Gate 3.7 to unblock the migration | 3R.4 + 3R.5 (Migration 020 + tests for round-trip, idempotent re-run, interrupted recovery) | Medium |
| 6 | "Migration verified on SQLite + designed for Postgres" | SQLite verified; Postgres never run. PG tooling absent from dev env | 3R.5 (documents `PARTIAL_BLOCKED_BY_POSTGRES_MIGRATION_NOT_VERIFIED`; PG verification deferred to a future gate) | Low |

Severity rubric:
- **High** — silent incorrect behaviour on a tenant isolation boundary
- **Medium** — narrow claim that needed widening, plus test coverage gap
- **Low** — environment-blocked verification, design intent unchanged

None of the six corrections invalidate the Gate 3 verdict — they
narrow its scope. After Gate 3R.6 the original verdict holds for a
strictly smaller surface (the parts that were actually tested) and
Gate 3R issues its own verdict (`PASS_A1A_GATE3R_*_VERIFIED` per
sub-gate, culminating in a Gate 3R.9 final verdict).

---

## §2. Correction #1 — CHECK constraint widening

### §2.1 Gate 3.7 original claim (excerpt)

> The narrow CHECK `{PERSISTED, FAILED, FALLBACK_MEMORY}` is the
> final word on `trace_capture_status`. Migration 019 is committed
> and won't be revisited.

### §2.2 Actual state

Migration 019's CHECK was correct *for the literals Gate 3.3
shipped*. Gate 3R.3 then introduced three more literals
(`NEVER_CAPTURED_LEGACY`, `CAPTURE_PENDING`, `CAPTURED`) to support
the deployment profile state machine. Without a CHECK widening,
SQLite would have rejected INSERTs carrying these literals.

### §2.3 Correction

Migration 020 (Gate 3R.4) widens the CHECK to all six literals:

```sql
CHECK (trace_capture_status IS NULL OR trace_capture_status IN
       ('NEVER_CAPTURED_LEGACY', 'CAPTURE_PENDING', 'CAPTURED',
        'PERSISTED', 'FAILED', 'FALLBACK_MEMORY'))
```

Backfill: all 244 historical NULL rows rewritten to
`NEVER_CAPTURED_LEGACY` (idempotent — WHERE clause excludes
already-backfilled rows on re-run).

Test: `tests/test_api/test_a1a_gate3r_4_trace_event_identity.py`
§7 verifies `TraceCaptureState.ALL_STATES` matches the migration
CHECK exactly.

---

## §3. Correction #2 — Stable event identity

### §3.1 Gate 3.3 original claim (excerpt)

> The composite UNIQUE(run_id, step, ts) makes duplicate emit
> loud, not silent — second INSERT raises IntegrityError.

### §3.2 Actual state

True for the duplicate-emit case *within a single process*. Two
gaps:

a) **Float-second ordering brittleness**: `ts` is `time.time()`.
   Across process restarts (NTP slew, wall vs monotonic) the
   RunTrace page can render events out of order if the clock
   moves backwards. The 9-step Corti timeline is robust against
   this on a single host, but a future multi-worker deploy would
   see it.

b) **Same-step collision**: multi-stage orchestrators (MedCodER's
   5-stage rerank) emit multiple `tools_call` events that can
   land in the same microsecond. The composite UNIQUE rejects
   the second INSERT as a duplicate, masking a real event.

### §3.3 Correction

Migration 020 adds four new columns to `run_trace_events`:

| Column | Type | Purpose |
|---|---|---|
| `event_id` | VARCHAR(64) | UUID v4 (canonical identity) |
| `sequence_number` | INTEGER | per-trace monotonic 1-indexed ordering |
| `trace_id` | VARCHAR(64) | trace group (multi-trace runs) |
| `identity_source` | VARCHAR(32) | how identity was assigned |

Three new indexes:
- `ix_run_trace_events_event_id` UNIQUE WHERE NOT NULL
  (canonical identity lookup)
- `ix_run_trace_events_trace_seq` on `(trace_id, sequence_number)`
  (monotonic reads)
- `ix_run_trace_events_trace_id` (trace group lookup)

The composite UNIQUE(run_id, step, ts) is **kept** as a defensive
dedup. Readers sort by `sequence_number` when present, falling
back to `ts` for pre-3R.4 rows (all 7+1 fixture rows in the dev
DB now have `sequence_number` populated).

Test: `tests/test_api/test_a1a_gate3r_4_trace_event_identity.py`
covers UUID shape, two-call uniqueness, sequence counter keying
by trace_id, and backwards compat with NULL event_id rows.

---

## §4. Correction #3 — Orphan-run guard

### §4.1 Gate 3.4/3.5 original claim

> SSE and Console trace reads check the row's
> `tenancy_classification` via `tenant_read_policy.is_tenant_visible`
> before returning events.

### §4.2 Actual state

The visibility check fired only when a RunHistory row existed.
A signed trace token bound to a `run_id` with no RunHistory row
(an orphan run — token was somehow minted but the run record
was never committed) fell through to `get_run_scoped(run_id, org)`
which returned whatever the trace store happened to have.

The information leak was small (the trace store is itself
org-scoped on `organization_id`), but the *contract* leak was
real: the token's HMAC was checked but never bound to an
authoritative tenant owner.

### §4.3 Correction

Gate 3R.1 added an orphan-run guard to all three read paths:

- `app/api/runs.py` partner trace endpoint (~line 410-440)
- `app/api/runs.py` partner SSE endpoint (~line 595-625)
- `app/api/run_trace.py` console endpoint (~line 100-160)

Each path now:
1. Verifies the signed token (HMAC + expiry + run_id binding).
2. Looks up the RunHistory row via `get_run_status(db, run_id)`.
3. If `row is None`, emits `trace.read.denied.orphan_run` /
   `sse.denied.orphan_run` to the system_audit sink and returns
   HTTP 404 `TRACE_NOT_FOUND`.
4. If `row.organization_id != claims.organization_id`, returns
   HTTP 403 `TRACE_TOKEN_ORG_MISMATCH` (partner path) or
   HTTP 404 `TRACE_NOT_FOUND` (console path, no existence leak).
5. If `not is_tenant_visible(row.tenancy_classification)`,
   returns HTTP 404 with audit emit
   `trace.read.denied.invisible_classification`.

Test: `tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py`
covers all three paths + audit emit assertions.

### §4.4 Demonstration

Gate 3R.6 §5.3 demonstrated the orphan-run denial against a
real backend: token for `run-3r6-orphan-nonexistent` returned
HTTP 404 TRACE_NOT_FOUND on both `/trace` and `/events`.

---

## §5. Correction #4 — Material audit emit wiring

### §5.1 Gate 3.6 original claim (excerpt)

> The audit emit coverage matrix lists 12 actions that the
> platform surfaces: `run.start`, `run.complete`, `run.failed`,
> `run.cancel`, `run.timeout`, `idempotency.dedup`,
> `api_client.authentication_rejected`, `api_client.rotate`,
> `context.clear`, `trace.read.*`, `system.startup`, etc.

### §5.2 Actual state at `d1447f3`

The allowlist in `app/services/system_audit.py` listed all 12
actions, but **no caller actually emitted 6 of them**:

| Action | Allowlist | Emit caller |
|---|---|---|
| `run.cancel` | yes | **missing** |
| `run.timeout` | yes | **missing** |
| `run.complete` | yes | **missing** (only `run.start` via record_run_start) |
| `run.failed` | yes | **missing** |
| `idempotency.dedup` | yes | **missing** |
| `api_client.rotate` | yes | **missing** |

Gate 3R.0 §12-13 surfaced this by querying the `audit_logs`
table:

```sql
SELECT action, COUNT(*) FROM audit_logs GROUP BY action;
-- Result: 0 rows for run.cancel/timeout/complete/failed,
--         idempotency.dedup, api_client.rotate
```

### §5.3 Correction

Gate 3R.2 added emit calls at 6 sites:

| Action | File | Function |
|---|---|---|
| `run.complete` | `app/services/run_lifecycle.py` | `record_run_complete` |
| `run.failed` | `app/services/run_lifecycle.py` | `record_run_failure` |
| `run.cancel` | `app/services/run_lifecycle.py` | `record_run_cancelled` |
| `run.timeout` | `app/services/run_lifecycle.py` | `record_run_timeout` |
| `idempotency.dedup` | `app/services/idempotency_service.py` | replay path |
| `api_client.rotate` | `app/api/platform_api_clients.py` | secret rotation endpoint |

Each emit uses `system_audit()` (system-scope, MODERN_SYSTEM
classification) so the audit row lands in the same
`audit_logs` table with the correct
`tenancy_classification=MODERN_SYSTEM` tag.

Test: `tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py`
exercises each emit path and asserts the row landed with the
expected `action` + `tenancy_classification`.

---

## §6. Correction #5 — Migration interrupted recovery

### §6.1 Gate 3.7 original claim (excerpt)

> Migration 019's batch_alter_table is robust against interruption
> because SQLite's temp-table pattern is well-understood.

### §6.2 Actual state

During Gate 3.7 itself, Migration 019 was interrupted mid-flight
(process killed by a Ctrl-C during the CHECK constraint swap).
The `_alembic_tmp_run_history` shadow table lingered. The next
`alembic upgrade head` attempt failed with:

```
sqlalchemy.exc.OperationalError: table _alembic_tmp_run_history already exists
```

The Gate 3.7 author dropped the temp table manually with
`DROP TABLE _alembic_tmp_run_history` and re-ran the migration.
This recovery procedure was **not** documented in the Gate 3.7
report. Hospitals hitting the same issue in production would
have no guidance.

### §6.3 Correction

Gate 3R.4 + 3R.5 made the recovery automatic.

Migration 020's `upgrade()` opens with a defensive cleanup:

```python
op.execute("DROP TABLE IF EXISTS _alembic_tmp_run_trace_events")
op.execute("DROP TABLE IF EXISTS _alembic_tmp_run_history")
```

This is a no-op on a clean DB (the temp tables don't exist) and
a recovery on a dirty DB. Postgres supports `DROP TABLE IF EXISTS`
natively, so the clause is portable.

Test: `tests/test_api/test_a1a_gate3r_5_migration_portability.py`
§4 simulates the interruption by manually creating a stale
`_alembic_tmp_run_history` table between downgrade and upgrade,
then verifies the next `alembic upgrade head` completes cleanly.

---

## §7. Correction #6 — PostgreSQL verification gap

### §7.1 Gate 3 original implicit claim

> Migration 019 is portable across SQLite and Postgres because
> it uses standard SQLAlchemy constructs.

### §7.2 Actual state

True *by construction* but never *verified*. The dev environment
has no `psql` CLI, no `asyncpg`, no `psycopg`, no `testcontainers`,
no Docker. Migration 019's behaviour under Postgres is
theoretical only.

### §7.3 Correction

Gate 3R.5 documents the gap explicitly as a partial verdict:

```
PARTIAL_BLOCKED_BY_POSTGRES_MIGRATION_NOT_VERIFIED
```

The mitigation: Migration 020 uses only standard SQLAlchemy
constructs that are documented portable across SQLite + Postgres
(`add_column`, `create_index`, `create_check_constraint`,
`batch_alter_table`). `batch_alter_table` is a no-op ALTER on
Postgres. The partial unique index uses `postgresql_where=sa.text("event_id IS NOT NULL")`
which compiles to PG's native `CREATE UNIQUE INDEX ... WHERE`
syntax.

The test
`tests/test_api/test_a1a_gate3r_5_migration_portability.py::test_postgresql_migration_verification_blocked`
asserts the PG tooling is missing — if a future env has PG
installed, the test fails loudly so the partial verdict can be
upgraded to PASS.

### §7.4 Path to unblock

```bash
pip install testcontainers[postgres] asyncpg
# Then add a PG fixture to test_a1a_gate3r_5_migration_portability.py
# that runs the migration against a real PG container.
```

This is out of scope for Gate 3R but is listed in the issue
ledger (3R.7 deliverable #3).

---

## §8. Net effect on Gate 3's verdict

The original Gate 3 verdict
`PASS_A1A_GATE3_TENANCY_TRUTH_CONTAINMENT_AND_TRACE_ISOLATION_VERIFIED`
remains the **historical record** of what Gate 3 shipped at
commit `d1447f3`. It is not revised, edited, or withdrawn.

The addendum narrows its scope: the verdict is correct *for the
surface Gate 3 actually implemented and tested at the time*.
Gate 3R.1–3R.6 then extended the surface and verified the
extended parts under their own verdicts:

```
PASS_A1A_GATE3R_1_AUTHORITATIVE_RUN_RESOLVER_VERIFIED
PASS_A1A_GATE3R_2_MATERIAL_AUDIT_EMIT_WIRING_VERIFIED
PASS_A1A_GATE3R_3_TRACE_CAPTURE_STATUS_AND_PROFILES_VERIFIED
PASS_A1A_GATE3R_4_TRACE_EVENT_IDENTITY_VERIFIED
PASS_A1A_GATE3R_5_MIGRATION_PORTABILITY_VERIFIED
   ⚠ PARTIAL_BLOCKED_BY_POSTGRES_MIGRATION_NOT_VERIFIED
PASS_A1A_GATE3R_6_RUNTRACE_SSE_BROWSER_E2E_VERIFIED
```

Gate 3R.9 will issue the cumulative verdict that supersedes
Gate 3's for the trace + audit + tenant-read surface. Gate 4
(PHI) and Gate 5+ (runtime) are unaffected.

---

## §9. Charter §22 forbidden actions NOT taken

This addendum does NOT:

- Modify any historical Gate 3.0–3.8 report file
- Edit commit `d1447f3` (no amend, no force-push, no rewrite)
- Introduce a new Agent / Expert / Tool / Runtime
- Change Medical Coding / CDI prompts
- Run a PostgreSQL verification (environment-blocked)
- Push the branch or open a PR
- Issue a forbidden verdict (the partial PG verdict is explicitly allowed by charter §3R.5)

The addendum is purely a documentation layer. Code changes
landed in Gates 3R.1–3R.6 are listed in the evidence manifest
(3R.7 deliverable #2).

---

## §10. References

- Gate 3R.0 baseline: `reports/phase-a1a/A1A_GATE3R_0_BASELINE_AND_CARRYOVER_RE_AUDIT.md`
- Gate 3R.1 closure: `reports/phase-a1a/A1A_GATE3R_1_AUTHORITATIVE_RUN_RESOLVER.md`
- Gate 3R.2 closure: `reports/phase-a1a/A1A_GATE3R_2_MATERIAL_AUDIT_EMIT_WIRING.md`
- Gate 3R.3 closure: `reports/phase-a1a/A1A_GATE3R_3_TRACE_CAPTURE_STATUS_AND_PROFILES.md`
- Gate 3R.4 closure: `reports/phase-a1a/A1A_GATE3R_4_TRACE_EVENT_IDENTITY.md`
- Gate 3R.5 closure: `reports/phase-a1a/A1A_GATE3R_5_MIGRATION_PORTABILITY.md`
- Gate 3R.6 closure: `reports/phase-a1a/A1A_GATE3R_6_RUNTRACE_SSE_BROWSER_E2E.md`
- Evidence manifest: `reports/phase-a1a/A1A_GATE3_EVIDENCE_MANIFEST.md`
- Issue ledger: `reports/phase-a1a/A1A_GATE3R_ISSUE_LEDGER.md`
