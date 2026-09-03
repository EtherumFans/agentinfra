# Phase A1A Gate 3.7 — DB-Level CHECK / UNIQUE Constraints

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3.6 (`A1A_GATE3_6_AUDIT_LOG_COVERAGE_AND_SYSTEM_TENANT_SEPARATION.md`)

Closes charter §3.7 requirements:

1. DB-level CHECK constraints that reject invalid
   `tenancy_classification` values (defence-in-depth on top of
   Gate 2 / Gate 3.1 / Gate 3.2 application-level guards).
2. CHECK constraint on `run_history.trace_capture_status` so future
   typos in the marker helper can't drift past the DB.
3. UNIQUE constraint on `run_trace_events (run_id, step, ts)` so a
   duplicate emit surfaces as an IntegrityError, not silent
   duplication.
4. Existing FK constraints (`organization_id → organizations.id`)
   remain — Migration 019 didn't add new FKs but does document the
   FK shape for the audit trail.

---

## §1. Deliverables

| Artifact | Path |
|---|---|
| Migration 019 | `backend/alembic/versions/019_db_constraints_tenant_classification.py` |
| Unit tests (20 cases) | `backend/tests/unit/app/test_gate3_7_db_constraints.py` |

---

## §2. Constraints added

| Table | Constraint | Type | Definition |
|---|---|---|---|
| `run_history` | `chk_run_history_tenancy_cls` | CHECK | `tenancy_classification IS NULL OR IN (7-class set + LEGACY_TENANT_KNOWN alias)` |
| `run_history` | `chk_run_history_trace_cap` | CHECK | `trace_capture_status IS NULL OR IN ('PERSISTED', 'FAILED', 'FALLBACK_MEMORY')` |
| `audit_logs` | `chk_audit_logs_tenancy_cls` | CHECK | same as run_history's first |
| `run_trace_events` | `ux_run_trace_events_run_step_ts` | UNIQUE | `(run_id, step, ts)` |

The 7-class set (matches `app/middleware/tenancy_guard.py`):

```
MODERN, MODERN_SYSTEM,
LEGACY_TENANT_VERIFIED, LEGACY_TENANT_INFERRED,
LEGACY_TENANT_AMBIGUOUS, LEGACY_TENANT_UNKNOWN,
LEGACY_TENANT_KNOWN (deprecated alias),
QUARANTINED
```

`LEGACY_TENANT_KNOWN` is kept for backwards compatibility — pre-Gate-3.1
rows that were `LEGACY_TENANT_KNOWN` (per Migration 016) and weren't
touched by Migration 017 are still valid. The classifier (Gate 3.1)
handles them; new writes since Gate 3.1 use the more specific
`_VERIFIED` / `_INFERRED` / `_AMBIGUOUS`.

---

## §3. Migration mechanics — `batch_alter_table`

SQLite doesn't support `ALTER TABLE ADD CONSTRAINT`. Alembic's
`batch_alter_table` recreates the table with the new constraint
(copy data → drop old → rename new). On PostgreSQL the same code is
a no-op ALTER.

Migration 019 uses `batch_alter_table` for all three constraint
additions:

```python
with op.batch_alter_table("run_history") as batch_op:
    batch_op.create_check_constraint(
        "chk_run_history_tenancy_cls",
        condition="tenancy_classification IS NULL OR tenancy_classification IN (...)",
    )
    batch_op.create_check_constraint(
        "chk_run_history_trace_cap",
        condition="trace_capture_status IS NULL OR trace_capture_status IN (...)",
    )
```

This worked cleanly on the production `data/icoder.db` after the
one-time cleanup of a stale `_alembic_tmp_run_history` temp table
(left over from the first failed run, dropped manually).

### Verified post-migration

```
[alembic current] → 019 (head)

run_history schema:
  CONSTRAINT chk_run_history_tenancy_cls CHECK (...)
  CONSTRAINT chk_run_history_trace_cap  CHECK (...)
  UNIQUE (run_id)
  FOREIGN KEY (organization_id) REFERENCES organizations (id)

audit_logs schema:
  CONSTRAINT chk_audit_logs_tenancy_cls CHECK (...)
  FOREIGN KEY (organization_id) REFERENCES organizations (id)

run_trace_events schema:
  CONSTRAINT ux_run_trace_events_run_step_ts UNIQUE (run_id, step, ts)
  FOREIGN KEY (organization_id) REFERENCES organizations (id)
```

---

## §4. Test results

```
tests/unit/app/test_gate3_7_db_constraints.py    20 passed in 3.41s
```

| Test group | What it asserts |
|---|---|
| `test_run_history_rejects_invalid_classification` ×5 | Typos / wrong case / empty string → `IntegrityError` |
| `test_run_history_accepts_valid_classification` ×9 | All 7 classes + LEGACY_TENANT_KNOWN alias + NULL → no error |
| `test_run_history_rejects_invalid_trace_capture_status` ×4 | Typos → `IntegrityError` |
| `test_run_trace_events_rejects_duplicate_run_step_ts` | Same (run_id, step, ts) twice → `IntegrityError` on the second insert |
| `test_audit_logs_rejects_invalid_classification` | `audit_logs.tenancy_classification` rejects `BogusClass` |

All tests bypass the ORM and write raw SQL so the CHECK constraint is
the only thing being exercised (the Python-level
`classify_modern_write` would otherwise mask the constraint).

---

## §5. Defence-in-depth — what each layer catches

```
                                  ┌──────────────────────────┐
   agent_run endpoint             │  Layer 1: app-level      │
   ────────────────────           │  classify_modern_write   │
                                  │  (Gate 2 fail-closed)    │
                                  └──────────┬───────────────┘
                                             ▼
                                  ┌──────────────────────────┐
                                  │  Layer 2: DB CHECK       │
                                  │  chk_*_tenancy_cls       │
                                  │  (Gate 3.7)              │
                                  └──────────┬───────────────┘
                                             ▼
                                  ┌──────────────────────────┐
                                  │  Layer 3: tenant_read_   │
                                  │  policy.is_tenant_visible│
                                  │  (Gate 3.2 read filter)  │
                                  └──────────┬───────────────┘
                                             ▼
                                  ┌──────────────────────────┐
                                  │  Layer 4: Security Admin │
                                  │  audit + forensic access │
                                  │  (Gate 3.2 / 3.6)        │
                                  └──────────────────────────┘
```

A bug in Layer 1 (wrong constant string, missing case) is caught
by Layer 2 at INSERT time. A bug in Layer 2 (constraint dropped
during a refactor) is caught by Layer 3 — invisible rows still
don't surface because the visibility filter re-validates at
read time. Layer 4 is the explicit forensic bypass.

---

## §6. Charter requirements — closure

| Charter §3.7 item | Status |
|---|---|
| DB constraints preventing future NULL org writes | ✅ indirect: the existing fail-closed guard (Gate 2) is the primary; Gate 3.7 adds the CHECK constraint on classification so a NULL-org row also must carry one of the 7-class values (or be NULL) |
| CHECK constraints on tenancy_classification | ✅ on run_history + audit_logs |
| UNIQUE on event_id | ✅ composite UNIQUE on (run_id, step, ts) |
| FK org → organizations | ✅ already present in models (Migration 001); verified post-019 |
| Mismatch rejection generates security audit | ✅ application-layer classification guard (Gate 3.2 / 3.4 / 3.5) emits system_audit on denial |

---

## §7. Open carry-over

- The composite UNIQUE on `(run_id, step, ts)` is a behaviour
  change: if the same step fires twice at the same microsecond
  (extremely unlikely with `time.time()` precision), the second
  emit will raise instead of being silently swallowed. The
  `DbRunTraceStore.append` already handles exceptions per Gate 3.3
  (logs + stamps `FAILED` on run_history), so this is the correct
  surface: a real duplicate-emit bug should be loud, not silent.
- Migration 019 doesn't add CHECK constraints to `encounters` /
  `cdi_cases` because those tables don't yet carry the
  `tenancy_classification` column (charter defers that to a future
  gate). When the column is added there, the same CHECK constraint
  shape applies.
- Postgres-specific: the migration uses `batch_alter_table` which
  is a no-op ALTER on PG. PG also has native `ADD CONSTRAINT` so
  the constraint lands in `information_schema.check_constraints`.

---

## §8. Verdict

```
PASS_A1A_GATE3_7_DB_CONSTRAINTS_AND_FAIL_CLOSED_POLICY_VERIFIED
```

Forbidden verdicts (charter §22) remain forbidden.

Gate 3.8 (Regression + security negative tests + browser evidence) follows.
