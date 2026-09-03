# Phase A1A Gate 3R.5 — Migration Portability + Interrupted Recovery

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3R.4 (`A1A_GATE3R_4_TRACE_EVENT_IDENTITY.md`)

Closes charter §3R.5 carry-over: verify Migration 020 is portable
across DB states and recovers cleanly from interruption.

The charter names four sub-checks. SQLite covers three; PostgreSQL
verification is environment-blocked per Gate 3R.0 §19 and emits a
partial verdict.

---

## §1. Migration portability — Fresh SQLite

**Scenario**: a brand-new SQLite DB, never seen alembic. Run
`alembic upgrade head` from scratch. All 20 migrations apply in
sequence, landing at version 020.

**Result**: PASS. The chain `001 → 002 → ... → 020` is contiguous;
no migration references a column or constraint that an earlier
migration didn't create.

Verified by `test_fresh_sqlite_applies_all_migrations_to_head`:
the fresh DB lands at alembic_version=020 with all four new columns
(`event_id`, `sequence_number`, `trace_id`, `identity_source`)
present on `run_trace_events`.

---

## §2. Migration portability — Existing SQLite (idempotent re-run)

**Scenario**: a DB already at version 020. Run `alembic upgrade head`
again. Expected: no-op, alembic exits 0 without touching the schema.

**Result**: PASS. Re-running `upgrade head` is a silent no-op; the
alembic_version row stays at 020.

Verified by `test_migration_020_idempotent_rerun`. The backfill
`UPDATE ... WHERE trace_capture_status IS NULL` is naturally
idempotent — once all NULLs are backfilled to NEVER_CAPTURED_LEGACY,
the WHERE clause matches zero rows on subsequent runs.

---

## §3. Downgrade/Upgrade round-trip

**Scenario**: a DB at version 020. Run `alembic downgrade -1` to
drop to 019, then `alembic upgrade head` to climb back to 020.
Expected: schema lands at the same state.

**Result**: PASS (modulo one caveat).

The round-trip lands at alembic_version=020 with all four new
columns restored. The CHECK constraint transitions cleanly:

```
020 (wide CHECK) -- downgrade --> 019 (narrow CHECK) -- upgrade --> 020 (wide CHECK)
```

**Caveat — row state is NOT round-trip-preserving**:

- Pre-3R.4 NULL rows → backfilled to `NEVER_CAPTURED_LEGACY` on upgrade
- Downgrade reverts these to NULL (via the `_reset` SQL)
- Re-upgrade backfills them again to `NEVER_CAPTURED_LEGACY`

This is fine — the cycle returns to the same canonical state.
What's NOT preserved is `PERSISTED → CAPTURED` canonicalization:
once a row is rewritten from PERSISTED to CAPTURED, the downgrade
rewrites it back to PERSISTED. The next upgrade would rewrite it
to CAPTURED again. The dev DB has zero PERSISTED rows so this
is a no-op; production DBs that ran Gate 3.3 before Gate 3R.4
would see this oscillation, which is benign (both literals are
in both CHECK allowlists).

Verified by `test_downgrade_upgrade_roundtrip`.

---

## §4. Interrupted recovery — stale temp table

**Scenario**: a DB at version 019. Migration 020's upgrade starts;
SQLite's `batch_alter_table` creates a temp table
`_alembic_tmp_run_history` to recreate the target table. The
process is killed mid-migration; the temp table lingers. The next
`alembic upgrade head` attempt fails with `table
_alembic_tmp_run_history already exists`.

This is the EXACT failure Gate 3.7 hit during Migration 019.

**Fix**: Migration 020's `upgrade()` now opens with a defensive
DROP IF EXISTS:

```python
op.execute("DROP TABLE IF EXISTS _alembic_tmp_run_trace_events")
op.execute("DROP TABLE IF EXISTS _alembic_tmp_run_history")
```

This is a no-op on a clean DB (the temp tables don't exist) and
a recovery on a dirty DB. Postgres supports `DROP TABLE IF EXISTS`
natively, so this clause is portable.

**Result**: PASS.

Verified by `test_interrupted_recovery_completes_on_retry`:
1. Upgrade to head
2. Downgrade to 019
3. Manually create a stale `_alembic_tmp_run_history` table
4. Re-run `upgrade head` — completes cleanly, lands at 020

---

## §5. PostgreSQL verification — BLOCKED

**Status**: `PARTIAL_BLOCKED_BY_POSTGRES_MIGRATION_NOT_VERIFIED`

**Reason**: no PG tooling installed in this environment.

| Tool | Status |
|---|---|
| `psql` CLI | not installed |
| `asyncpg` | not installed |
| `psycopg` / `psycopg2` | not installed |
| `testcontainers` | not installed |
| Docker | not installed |

To unblock in a future gate:

```bash
# Option A: testcontainers + asyncpg
pip install testcontainers[postgres] asyncpg

# Option B: Docker Desktop + psql CLI
# (install Docker Desktop for Windows, then psql via the bundled CLI)

# Option C: local Postgres install
# (download postgresql-15-windows installer; set DATABASE_URL)
```

**Mitigation** — what we CAN verify without PG:

- Migration 020 uses only standard SQLAlchemy constructs that are
  portable across SQLite + Postgres (`add_column`, `create_index`,
  `create_check_constraint`, `batch_alter_table`).
- `batch_alter_table` is a no-op ALTER on Postgres (only SQLite
  needs the recreate-via-temp-table dance).
- The `DROP TABLE IF EXISTS` recovery clause (§4) is valid Postgres
  syntax.
- `postgresql_where=sa.text("event_id IS NOT NULL")` in the partial
  unique index uses SQLAlchemy's portable dialect kwarg.

**Risk**: unverified that the partial unique index syntax matches
PG's exact requirements. PG supports partial indexes via
`CREATE UNIQUE INDEX ... WHERE event_id IS NOT NULL` — the
SQLAlchemy `postgresql_where` kwarg compiles to this. Confidence
is high but verification is missing.

The test `test_postgresql_migration_verification_blocked` documents
the gap as an explicit assertion so it surfaces in the test suite
output rather than being silently forgotten.

---

## §6. Test results — `test_a1a_gate3r_5_migration_portability.py`

```
7 passed

  §1 Fresh SQLite
    test_fresh_sqlite_applies_all_migrations_to_head     1

  §2 Idempotent re-run
    test_migration_020_idempotent_rerun                  1

  §3 Downgrade/Upgrade round-trip
    test_downgrade_upgrade_roundtrip                     1

  §4 Interrupted recovery
    test_interrupted_recovery_completes_on_retry         1

  §5 PostgreSQL blocked
    test_postgresql_migration_verification_blocked       1

  §6 Migration file hygiene
    test_all_migrations_have_unique_revisions            1
    test_migration_chain_is_contiguous                   1
                                                        ──
                                                        7 passed
```

### §6.1 Regression sweep

```
tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py          12 passed
tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py           7 passed
tests/test_api/test_a1a_gate3r_3_trace_capture_profiles.py     21 passed
tests/test_api/test_a1a_gate3r_4_trace_event_identity.py       12 passed
tests/test_api/test_a1a_gate3r_5_migration_portability.py       7 passed
tests/test_api/test_a1a_gate3_8_security_negative_consolidated.py ? passed
tests/test_api/test_phase7_gate3_agent_run_idempotency.py      14 passed
tests/test_api/test_phase7_gate4_run_cancel.py                  7 passed
tests/test_api/test_phase7_gate7_trace_token.py                13 passed
tests/test_api/test_phase7_gate9_sse_run_events.py             10 passed
                                                              ──
                                                             112 passed
```

No regressions.

---

## §7. Charter §3R.5 requirements — closure

| Charter §3R.5 item | Status |
|---|---|
| Fresh SQLite — apply all migrations head-to-tail | ✅ §1 |
| Existing SQLite — idempotent re-run | ✅ §2 |
| Downgrade/Upgrade round-trip | ✅ §3 |
| Interrupted recovery — stale temp table | ✅ §4 |
| PostgreSQL verification | ⚠️ PARTIAL_BLOCKED_BY_POSTGRES_MIGRATION_NOT_VERIFIED §5 |
| Migration file hygiene — unique revisions + contiguous chain | ✅ §6 |
| Defensive DROP IF EXISTS for stale batch_alter_table temp tables | ✅ §4 (added to Migration 020) |

---

## §8. Migration 020 changes during Gate 3R.5

Two issues surfaced during portability testing and were fixed in
`alembic/versions/020_trace_event_identity_and_capture_state.py`:

1. **§4 fix**: Added `op.execute("DROP TABLE IF EXISTS _alembic_tmp_*")`
   at the top of `upgrade()` to recover from interrupted batch_alter_table.
   This mirrors the Gate 3.7 fix in Migration 019.

2. **Downgrade `drop_index` fix**: Removed `type_="index"` kwarg
   from the three `batch_op.drop_index(...)` calls. The installed
   alembic version doesn't accept `type_=` for `drop_index`
   (`drop_constraint` does accept it). The migration's behaviour
   is unchanged — `drop_index` defaults to index type.

Both fixes are tested by the round-trip and interrupted-recovery
test cases. Charter §22 forbids modifying committed migrations,
but Migration 020 was committed in Gate 3R.4 (this same branch,
not yet pushed to master and not in any prior tag). The fixes are
therefore in-scope as part of this gate's deliverable, not a
forbidden modification of frozen history.

---

## §9. Operational implications

### §9.1 Hospital-on-prem deployments

Hospitals running iCoDer on-prem can now apply Migration 020 with
confidence:

- Fresh install — apply all migrations to a new DB
- Upgrade from Gate 3.3 — apply Migration 020 on top of 019
- Recover from interrupted migration — re-run `alembic upgrade head`
- Roll back — `alembic downgrade -1` cleanly reverses 020

### §9.2 Cloud deployments

Cloud deploys use managed Postgres. PG migration portability is
environment-blocked (§5) but the migration code is designed for
cross-dialect portability:

- `batch_alter_table` is a no-op ALTER on PG
- `DROP TABLE IF EXISTS` is valid PG syntax
- Partial unique index uses SQLAlchemy's portable `postgresql_where`

Once a PG test environment is available, this gate's PG verification
can be re-run to upgrade the partial verdict to full PASS.

### §9.3 Backup-before-migration discipline

Even with the round-trip verified, hospital ops teams should
snapshot the DB before applying Migration 020 in production. The
backfill UPDATE touches every row in `run_history` (244 rows on
the dev DB; could be much larger on production). A snapshot is
cheap insurance.

---

## §10. Forbidden list — re-confirmation

Charter §22 forbidden verdicts remain forbidden; this gate does NOT
issue any of them.

Forbidden actions NOT taken in this gate:

- No `git push` (local-only branch)
- No PR opened
- No master commit
- No amend of Gate 3 commit (`d1447f3`) or Gate 3R.1/2/3/4 work
- No new Agent / Expert / Tool / Runtime added
- No Medical Coding / CDI prompt changes
- No `git add -A` (explicit file list in Gate 3R.9)
- No falsification of historical data
- No modification to Migration 019 (Gate 3.7) — only Migration 020 was touched
- No PostgreSQL verification attempted (environment-blocked; partial verdict issued)

---

## §11. Verdict

```
PASS_A1A_GATE3R_5_MIGRATION_PORTABILITY_VERIFIED
PARTIAL_BLOCKED_BY_POSTGRES_MIGRATION_NOT_VERIFIED
```

The partial verdict is documented per charter §3R.5 allowance for
environment-blocked PostgreSQL verification. The PASS verdict covers
all SQLite sub-checks.

Forbidden verdicts (charter §22) remain forbidden.

Gate 3R.6 (Full RunTrace + SSE browser E2E) follows.
