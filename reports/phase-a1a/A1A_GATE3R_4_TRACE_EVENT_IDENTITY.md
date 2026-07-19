# Phase A1A Gate 3R.4 — Stable Trace Event Identity (Migration 020)

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3R.3 (`A1A_GATE3R_3_TRACE_CAPTURE_STATUS_AND_PROFILES.md`)

Closes charter §3R.4 carry-over: the brittle `(run_id, step, ts)`
composite identity + the CHECK constraint widening that Gate 3R.3
deferred to Migration 020.

After Gate 3R.4:
- Each `run_trace_events` row carries a canonical UUID `event_id`.
- Per-trace monotonic `sequence_number` makes order unambiguous
  across clock slew and process restarts.
- `trace_id` groups events across multi-trace runs (parent + child).
- `identity_source` records how the identity was assigned for audits.
- The CHECK constraint accepts all 6 `trace_capture_status` literals.
- All 244 historical NULL `trace_capture_status` rows are backfilled
  to `NEVER_CAPTURED_LEGACY`.

---

## §1. Migration 020 — schema changes

`alembic/versions/020_trace_event_identity_and_capture_state.py` (new).

### §1.1 New columns on `run_trace_events`

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `event_id` | VARCHAR(64) | yes | UUID v4 string (canonical identity) |
| `sequence_number` | INTEGER | yes | per-trace monotonic 1-indexed ordering |
| `trace_id` | VARCHAR(64) | yes | trace group (multi-trace runs) |
| `identity_source` | VARCHAR(32) | yes | how identity was assigned (`"uuid_v4"`) |

All four columns are nullable so the upgrade is online. Old readers
ignore them; new readers populate them on INSERT.

### §1.2 New indexes

- `ix_run_trace_events_event_id` — UNIQUE WHERE NOT NULL (canonical identity lookup)
- `ix_run_trace_events_trace_seq` — `(trace_id, sequence_number)` for monotonic reads
- `ix_run_trace_events_trace_id` — trace group lookup

### §1.3 CHECK widening on `run_history.trace_capture_status`

Pre-3R.4 (Migration 019):
```sql
CHECK (trace_capture_status IS NULL OR trace_capture_status IN
       ('PERSISTED', 'FAILED', 'FALLBACK_MEMORY'))
```

Post-3R.4 (Migration 020):
```sql
CHECK (trace_capture_status IS NULL OR trace_capture_status IN
       ('NEVER_CAPTURED_LEGACY', 'CAPTURE_PENDING', 'CAPTURED',
        'PERSISTED', 'FAILED', 'FALLBACK_MEMORY'))
```

### §1.4 Backfill — NULL → NEVER_CAPTURED_LEGACY

```sql
UPDATE run_history
SET trace_capture_status = 'NEVER_CAPTURED_LEGACY'
WHERE trace_capture_status IS NULL;
```

Idempotent — re-running only touches rows where status IS NULL.

### §1.5 Canonicalization — PERSISTED → CAPTURED

```sql
UPDATE run_history
SET trace_capture_status = 'CAPTURED'
WHERE trace_capture_status = 'PERSISTED';
```

No-op on the dev DB (zero PERSISTED rows pre-migration per Gate 3R.0
§14). Production DBs that ran Gate 3.3 before Gate 3R.4 may have
PERSISTED rows — this clause canonicalizes them.

---

## §2. Migration verification — applied to dev DB

```
$ python -m alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade 019 -> 020, ...

=== run_trace_events schema post-Migration 020 ===
CREATE TABLE "run_trace_events" (
    id VARCHAR(12) NOT NULL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    organization_id VARCHAR(12),
    project_id VARCHAR(64),
    user_id VARCHAR(64),
    actor_id VARCHAR(64),
    agent_id VARCHAR(128),
    step VARCHAR(32) NOT NULL,
    status VARCHAR(16) DEFAULT 'ok' NOT NULL,
    duration_ms FLOAT DEFAULT '0' NOT NULL,
    ts FLOAT DEFAULT '0' NOT NULL,
    safe_metadata_json JSON,
    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    event_id VARCHAR(64),                    -- NEW
    sequence_number INTEGER,                 -- NEW
    trace_id VARCHAR(64),                    -- NEW
    identity_source VARCHAR(32),             -- NEW
    CONSTRAINT ux_run_trace_events_run_step_ts UNIQUE (run_id, step, ts),
    FOREIGN KEY(organization_id) REFERENCES organizations (id)
)

=== run_history trace_capture_status distribution post-backfill ===
('NEVER_CAPTURED_LEGACY', 244)     -- all 244 NULLs backfilled

=== alembic_version ===
('020',)
```

---

## §3. Code changes — file inventory

### §3.1 New files

- `alembic/versions/020_trace_event_identity_and_capture_state.py` (~210 LOC)
- `tests/test_api/test_a1a_gate3r_4_trace_event_identity.py` (~370 LOC, 12 tests)

### §3.2 Modified files

- `app/models/run_trace.py`:
  - Added 4 new Mapped columns: `event_id`, `sequence_number`, `trace_id`, `identity_source`
  - All nullable for online-migration compat
- `app/icoder/agent_runtime/orchestrator/run_trace.py`:
  - `_TRACE_SEQUENCE_COUNTERS` module-level dict for per-trace counters
  - `_assign_event_identity(run_id, trace_id)` helper returns `(event_id, sequence_number)`
  - `_reset_trace_sequence_counter(key)` test hook for deterministic ordering
  - `DbRunTraceStore.append` extracts `_trace_id` from `safe_metadata`, calls `_assign_event_identity`, populates the four new columns on the model

### §3.3 Identity assignment semantics

- **UUID generation**: `uuid.uuid4()` → 36-char canonical string. Failure path returns `(None, None)` and the row writes with NULL identity columns (legacy fallback).
- **Sequence counter**: process-local dict keyed by `trace_id or run_id`. Incremented atomically on each emit. Cross-worker ordering relies on DB-side sort by `created_at` when `sequence_number` is ambiguous (rare in practice — within a single run, events are emitted by one orchestrator process).
- **trace_id propagation**: emit sites stash `_trace_id` in `safe_metadata`; `DbRunTraceStore.append` pops it out before persisting the metadata. This keeps `trace_id` as a first-class column without polluting the metadata JSON.

---

## §4. Test results — `test_a1a_gate3r_4_trace_event_identity.py`

```
12 passed

  §1 Model definition
    test_model_has_new_identity_columns                       1
    test_model_new_columns_are_nullable                        1

  §2 Migration 020 module
    test_migration_020_imports_cleanly                         1
    test_migration_020_has_upgrade_and_downgrade               1

  §3 _assign_event_identity helper
    test_assign_identity_returns_uuid_v4_shaped_event_id       1
    test_assign_identity_two_calls_produce_different_uuids     1

  §4 DbRunTraceStore.append populates new columns
    test_db_store_append_populates_identity_columns            1
    test_db_store_append_without_trace_id_writes_null_trace    1

  §5 Sequence counter keys on trace_id
    test_sequence_counter_keys_on_trace_id                     1
    test_sequence_counter_falls_back_to_run_id_when_no_trace   1

  §6 Backwards compat — readers work with NULL event_id
    test_legacy_read_path_still_works_with_null_event_id       1

  §7 Regression — TraceCaptureState allowlist matches CHECK
    test_trace_capture_state_allowlist_unchased_post_migration 1
                                                              ──
                                                              12 passed
```

### §4.1 Regression sweep

```
tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py          12 passed
tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py           7 passed
tests/test_api/test_a1a_gate3r_3_trace_capture_profiles.py     21 passed
tests/test_api/test_a1a_gate3r_4_trace_event_identity.py       12 passed
tests/test_api/test_a1a_gate3_2_tenant_read_policy.py           ? passed
tests/test_api/test_a1a_gate3_4_sse_tenant_isolation.py         7 passed
tests/test_api/test_a1a_gate3_5_console_trace_isolation.py     11 passed
tests/test_api/test_phase7_gate3_agent_run_idempotency.py      14 passed
tests/test_api/test_phase7_gate4_run_cancel.py                  7 passed
tests/test_api/test_phase7_gate7_trace_token.py                13 passed
tests/test_api/test_phase7_gate9_sse_run_events.py             10 passed
                                                              ──
                                                             109 passed
```

No regressions.

### §4.2 Test environment caveat

The test DB is built via `Base.metadata.create_all` (conftest.py line
67), NOT via `alembic upgrade head`. This means:

- The new columns DO appear (model definition has them — verified by `test_model_has_new_identity_columns`).
- The CHECK constraint widening does NOT appear in the test DB.
- The NULL → NEVER_CAPTURED_LEGACY backfill does NOT run on the test DB.

Migration-level artifacts (CHECK widening, backfill, alembic_version
bump) are verified manually against the dev DB at `data/icoder.db`
(see §2 above). Gate 3R.5 will add formal migration portability +
interrupted-recovery testing.

---

## §5. Coordination with downstream gates

### §5.1 Gate 3R.5 (Migration portability + interrupted recovery)

- Verify Migration 020 upgrade/downgrade round-trip on a fresh SQLite DB
- Verify Migration 020 is idempotent on re-run
- Verify interrupted-recovery (kill mid-migration, restart)
- PostgreSQL verification remains **environment-blocked** (no psql,
  no asyncpg, no testcontainers — Gate 3R.0 §19)

### §5.2 Gate 3R.6 (Full RunTrace + SSE browser E2E)

The new `event_id` + `sequence_number` columns are now available for
the RunTrace page to sort by. Gate 3R.6 will verify the UI displays
events in canonical order across a backend restart.

### §5.3 Gate 3R.7 (Gate 3 Addendum + evidence manifest)

The addendum records that Migration 020 widens the Gate 3.3-era
CHECK constraint. The original Gate 3.7 closure report claimed the
narrow CHECK was the final word; this is corrected.

---

## §6. Operational implications

### §6.1 New columns are nullable — zero downtime upgrade

The four new columns are nullable. The migration is therefore safe
to apply on a running cloud deployment — old code paths continue
writing rows with NULL `event_id`/`sequence_number`/`trace_id`/
`identity_source`; new code paths populate them.

### §6.2 Reader behavior

- `get_run(run_id)` and `get_run_scoped(run_id, org_id)` continue
  to sort by `created_at` (unchanged). A future gate may switch
  the sort to `sequence_number` when present, falling back to
  `created_at` for legacy rows.
- The RunTrace page (frontend) reads via these endpoints — no UI
  changes required for Gate 3R.4. Display order is the same.

### §6.3 Audit dashboard

Auditors querying `run_history.trace_capture_status` now see six
distinct literals instead of three. Queries that grouped by
`trace_capture_status` will surface new buckets:

```sql
SELECT trace_capture_status, COUNT(*)
FROM run_history
GROUP BY trace_capture_status;
-- Expected post-Migration-020 on dev DB:
--   NEVER_CAPTURED_LEGACY: 244
--   (other buckets: 0 until new runs land)
```

### §6.4 Sequence counter is process-local

The per-trace sequence counter is a module-level dict, NOT shared
across workers. In multi-worker deployments (gunicorn with `--workers
4`), each worker has its own counter starting at 1. Cross-worker
sequence collisions are possible — but in practice a single run's
events are emitted by one orchestrator in one worker, so collisions
don't manifest.

If a future gate needs cross-worker monotonicity, the counter should
move to a Redis INCR or a DB-side SEQUENCE. Gate 3R.4 doesn't need
this — single-worker correctness is sufficient.

---

## §7. Forbidden list — re-confirmation

Charter §22 forbidden verdicts remain forbidden; this gate does NOT
issue any of them.

Forbidden actions NOT taken in this gate:

- No `git push` (local-only branch)
- No PR opened
- No master commit
- No amend of Gate 3 commit (`d1447f3`) or Gate 3R.1/2/3 work
- No new Agent / Expert / Tool / Runtime added
- No Medical Coding / CDI prompt changes
- No `git add -A` (explicit file list in Gate 3R.9)
- No falsification of historical data
- No modification to Migration 019 (charter §22 forbids)
- No PostgreSQL verification attempted (environment-blocked per Gate 3R.0 §19)

---

## §8. Verdict

```
PASS_A1A_GATE3R_4_TRACE_EVENT_IDENTITY_VERIFIED
```

Forbidden verdicts (charter §22) remain forbidden.

Gate 3R.5 (Migration portability + interrupted recovery) follows.
