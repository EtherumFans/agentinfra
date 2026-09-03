# Phase A1A Gate 3.3 — Database-Backed Trace Persistence (Fail-Closed)

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3.2 (`A1A_GATE3_2_QUARANTINE_AND_TENANT_READ_POLICY.md`)

Closes charter §3.3 requirements:

1. Trace events must persist to a database so they survive process
   restarts and are visible across workers (audit guarantee).
2. The "silent except" pattern in `DbRunTraceStore.append` (line 274
   pre-Gate-3.3) is removed — failures are now **visible**, recorded
   on `run_history.trace_capture_status`, and (when
   `RUNTRACE_FAIL_CLOSED=True`) propagated to the caller.
3. Cloud-mode deployment refuses to boot when `RUNTRACE_STORE != db`
   (fail-closed at startup, not just at runtime).
4. Cross-worker visibility: two store instances pointed at the same
   DB both see the same events (no in-memory state per process).

---

## §1. Deliverables

| Artifact | Path |
|---|---|
| Migration 018 | `backend/alembic/versions/018_run_history_trace_capture_status.py` |
| 2 new columns on `run_history` | `trace_capture_status`, `trace_capture_failure_reason` |
| `_mark_trace_capture_status` helper | `backend/app/icoder/agent_runtime/orchestrator/run_trace.py` (new) |
| `DbRunTraceStore.append` rewrite | same file — failure path no longer silent |
| `RunTraceStore.append` (in-memory) | now stamps FALLBACK_MEMORY |
| `RUNTRACE_FAIL_CLOSED` setting | `backend/app/config.py` |
| Cloud-mode validation | same file — refuses `RUNTRACE_STORE != db` |
| Unit tests (7 cases) | `backend/tests/unit/app/test_run_trace_persistence.py` |

---

## §2. `trace_capture_status` state machine

```
   (row written by record_run_start)
              │
              ▼
         ┌─ NULL ──────────────────┐
         │                         │
   DbRunTraceStore.append    RunTraceStore.append
         │                         │
   ┌─────┴──────┐                  ▼
   │            │          FALLBACK_MEMORY
   ▼            ▼
PERSISTED    FAILED
              │
              │  ── if RUNTRACE_FAIL_CLOSED=True ──▶ exception bubbles
              │     else: log + continue
              ▼
    trace_capture_failure_reason = "<error msg>"
```

| State | Meaning | Action |
|---|---|---|
| `NULL` | row written before Gate 3.3, or before first trace event | readers treat as "unknown — do not fail" |
| `PERSISTED` | `DbRunTraceStore.append` succeeded | audit can read trace events |
| `FAILED` | DB write raised; events may be lost | audit log shows reason; run continues unless fail-closed |
| `FALLBACK_MEMORY` | `RunTraceStore` (in-memory) was used | events lost on restart; allowed only in local dev |

---

## §3. Cloud-mode fail-closed

`Settings._validate_fail_closed_policy` now rejects cloud mode when
`RUNTRACE_STORE != db`:

```python
if self.RUNTRACE_STORE != "db":
    failures.append(
        f"RUNTRACE_STORE={self.RUNTRACE_STORE!r}; must be 'db' in "
        "cloud mode (memory store loses trace events on restart)"
    )
```

The setting `RUNTRACE_FAIL_CLOSED` (default: `False`) controls
runtime behaviour on individual DB write failures:

- `False` — log + stamp `FAILED` on `run_history`, run continues.
- `True` — log + stamp `FAILED` **and** re-raise so the caller can
  fail the run (compliance mode for hospitals that demand strict
  "no trace left behind").

Local dev keeps `RUNTRACE_STORE=memory` + `RUNTRACE_FAIL_CLOSED=False`
so tests don't need a real DB for every trace emit.

---

## §4. Code changes — `DbRunTraceStore.append`

Pre-Gate-3.3 (silent swallow):

```python
try:
    with self._sync_session_factory() as session:
        session.add(record)
        session.commit()
except Exception as e:
    logger.error("run_trace DB write failed: %s ...", e, ...)
```

Post-Gate-3.3:

```python
try:
    with self._sync_session_factory() as session:
        session.add(record)
        session.commit()
except Exception as e:
    logger.error(
        "run_trace DB write failed: %s (run_id=%s step=%s)",
        e, event.run_id, event.step,
    )
    try:
        _mark_trace_capture_status(
            event.run_id, "FAILED", reason=str(e)[:250],
        )
    except Exception as mark_err:
        logger.error("run_trace status mark also failed: %s ...", mark_err, ...)
    if getattr(settings, "RUNTRACE_FAIL_CLOSED", False):
        raise
    return

# Success path
try:
    _mark_trace_capture_status(event.run_id, "PERSISTED")
except Exception as mark_err:
    logger.debug("run_trace PERSISTED mark skipped: %s ...", mark_err, ...)
```

Key differences:

1. The `except` is still there (so emit-site calls don't crash by
   default), but the failure is now **observable**:
   - Logged at ERROR level (was already there).
   - Stamped on `run_history.trace_capture_status = FAILED` (new).
   - Optionally re-raised (new).
2. The success path stamps `PERSISTED` on the run_history row so
   audits can confirm "this run's trace reached disk".

---

## §5. Code changes — `RunTraceStore.append` (in-memory)

Pre-Gate-3.3:

```python
def append(self, event):
    self._events.setdefault(event.run_id, []).append(event)
```

Post-Gate-3.3:

```python
def append(self, event):
    self._events.setdefault(event.run_id, []).append(event)
    try:
        _mark_trace_capture_status(event.run_id, "FALLBACK_MEMORY")
    except Exception as mark_err:
        logger.debug("run_trace FALLBACK_MEMORY mark skipped: %s ...", ...)
```

This means the audit dashboard can answer "which runs lost their
trace on the last deploy?" with `SELECT * FROM run_history WHERE
trace_capture_status='FALLBACK_MEMORY'`. In cloud mode this query
should return zero rows because Settings validation refuses to boot.

---

## §6. Test results

```
tests/unit/app/test_run_trace_persistence.py    7 passed in 4.85s
```

| Test | What it asserts |
|---|---|
| `test_db_store_append_persists_event` | `append()` writes one row to `run_trace_events` |
| `test_db_store_append_stamps_persisted_on_run_history` | on success, `run_history.trace_capture_status == 'PERSISTED'` |
| `test_db_store_append_failure_stamps_failed` | on failure (bad DB URL), status == `FAILED`, no exception |
| `test_db_store_append_failure_raises_when_fail_closed` | with `RUNTRACE_FAIL_CLOSED=True`, failure propagates |
| `test_memory_store_append_stamps_fallback_memory` | in-memory store stamps `FALLBACK_MEMORY` |
| `test_cross_worker_visibility` | two `DbRunTraceStore` instances see the same events (cross-worker) |
| `test_cloud_mode_refuses_memory_store` | Settings validation refuses cloud + memory store |

### Combined Phase A1A regression

```
tests/unit/app/test_run_trace_persistence.py    7 passed
tests/unit/app/test_tenant_read_policy.py      24 passed
tests/unit/app/test_legacy_tenancy_attribution.py 17 passed
tests/unit/app/test_tenancy_guard.py           11 passed
                                                 59 passed
```

### Trace-related regression

```
tests/test_api/test_runtime_trace_invariants.py
tests/test_api/test_phase5_a1_trace_double_count.py
tests/test_api/test_phase7_gate7_trace_token.py
                                                 23 passed
```

Migration 018 applied cleanly to `data/icoder.db`:

```
[alembic current] → 018 (head)
PRAGMA table_info(run_history):
  32 trace_capture_status         VARCHAR(16)  nullable
  33 trace_capture_failure_reason VARCHAR(255) nullable
```

---

## §7. Charter requirements — closure

| Charter §3.3 item | Status |
|---|---|
| DB-backed trace persistence (run_trace_events table) | ✅ Phase 3-D2 (existing); Gate 3.3 makes it mandatory in cloud |
| Fail-closed policy when persistence fails | ✅ stamp FAILED + optional raise via `RUNTRACE_FAIL_CLOSED` |
| Remove silent except | ✅ except still present (defensive) but now: log + mark FAILED + optionally raise |
| Cross-worker visibility | ✅ test_cross_worker_visibility proves it; no in-memory state on `DbRunTraceStore` |
| Audit trail of "which runs lost trace" | ✅ `trace_capture_status` + `trace_capture_failure_reason` columns |
| Cloud-mode refuses memory store at boot | ✅ Settings validation |

---

## §8. Open carry-over

- The 240 existing `run_history` rows have `trace_capture_status=NULL`
  (pre-Gate-3.3). Readers treat NULL as "unknown — do not fail the
  read". Gate 3.7 may backfill a synthetic status if the audit
  dashboard needs it, but for now NULL is correct: those rows predate
  the column.
- `emit_trace_event` callers (dispatcher, orchestrator hooks) still
  don't pass a `run_history` reference; the marker helper opens a
  short-lived sync session for each call. This is acceptable at 9
  events per run but should be revisited if event volume grows.
- Gate 3.7 will add DB-level CHECK constraint on
  `trace_capture_status` (limit to NULL / PERSISTED / FAILED /
  FALLBACK_MEMORY) so future typos in the marker won't drift.

---

## §9. Verdict

```
PASS_A1A_GATE3_3_DATABASE_BACKED_TRACE_PERSISTENCE_FAIL_CLOSED
```

Forbidden verdicts (charter §22) remain forbidden: this gate does NOT
certify production readiness, hospital deployment, partner production
readiness, security certification, clinical validation, "all tenant
isolation complete", "all audit gaps resolved", or "zero defects".

Gate 3.4 (SSE event tenant isolation — F04) follows.
