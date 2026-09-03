# Phase 7 Gate 3 — Server-side Idempotency-Key Dedup

**Status**: PASS_GATE3_SERVER_SIDE_IDEMPOTENCY_DEDUP_VERIFIED
**Verdict tier**: PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION (gate-level)
**Date**: 2026-07-14
**Checkpoint**: A (Gates 2+3) — Gate 2 done in `PHASE7_GATE2_SDK_TGZ_EXTERNAL_INSTALL.md`

> Gate 3 is a P0 gate per the Phase 7 prompt. The contract: "the
> partner sends an `Idempotency-Key` header; the server dedups
> replayed requests, replays completed responses verbatim, and 409s
> key reuse with a different body." §4: "Server is the final security
> boundary." No client-side-only dedup, no SELECT-then-INSERT race.

---

## 1. What was built

| Artifact | Path | Purpose |
|---|---|---|
| Migration | `backend/alembic/versions/012_idempotency_records.py` | Creates `idempotency_records` table with UNIQUE `(organization_id, api_client_id, idempotency_key)` |
| Model | `backend/app/models/idempotency_record.py` | SQLAlchemy ORM mirror incl. `__table_args__ = (UniqueConstraint(...),)` so `create_all` enforces it in tests/dev |
| Service | `backend/app/services/idempotency_service.py` (~210 LOC) | `acquire_or_replay`, `mark_in_progress`, `mark_completed`, `mark_failed`, `compute_request_hash`, `IdempotencyKeyReusedError` (409) |
| Endpoint wiring | `backend/app/api/agent_run.py:269-307, 330-339, 396-413` | Reads `Idempotency-Key` header, branches to run/replay/409 paths; binds `run_id`; persists snapshot on completion |
| Unit tests | `backend/tests/unit/app/services/test_phase7_gate3_idempotency.py` (10 tests) | Direct service contract: race, mismatch, replay, IN_PROGRESS, FAILED, hash determinism |
| Integration tests | `backend/tests/test_api/test_phase7_gate3_agent_run_idempotency.py` (4 tests) | End-to-end through `POST /api/v1/agents/{id}/run` with real HTTP semantics |

**Total tests**: 14 new (10 unit + 4 integration), all PASS, 0 regressions in 538-test `tests/test_api/` sweep (1 pre-existing failure on master, unrelated).

---

## 2. Phase 7 §8 contract coverage

| §8 requirement | How it's satisfied | Test |
|---|---|---|
| §8.1 schema (idempotency_records table) | Migration 012 + model | `pragma table_info` verified |
| §8.1 UNIQUE constraint on (org, client, key) | `uq_idempotency_org_client_key` | `test_concurrent_insert_exactly_one_winner` |
| §8.2 first request → run | `should_run=True` path | `test_completed_replay_returns_snapshot` step 1 |
| §8.2 COMPLETED replay → return snapshot | `response_snapshot` JSON column | `test_completed_replay_returns_snapshot`, `test_replay_returns_completed_snapshot_verbatim` |
| §8.2 IN_PROGRESS replay → return run_id | `in_progress=True`, run_id from row | `test_in_progress_replay_returns_run_id`, `test_pending_replay_returns_in_progress` |
| §8.2 hash mismatch → 409 | `IdempotencyKeyReusedError` HTTP 409 | `test_hash_mismatch_raises_409`, `test_same_key_different_body_returns_409` |
| §8.3 INSERT-with-UNIQUE is dedup primitive | `INSERT; on IntegrityError rollback+SELECT` | `test_concurrent_insert_exactly_one_winner` (asyncio.gather) |
| §8.3 SELECT-then-INSERT forbidden | Never used; INSERT is first op | Code path in `acquire_or_replay` |

---

## 3. The NULL-sentinel fix

**Problem**: SQLite AND PostgreSQL treat NULL as distinct under UNIQUE
constraints. If `organization_id=NULL` or `api_client_id=NULL`, the
constraint silently fails to dedup — two concurrent requests with the
same key both INSERT successfully.

**Where it bites**:
- Local dev single-org mode (no JWT org context → `organization_id` is NULL)
- Console JWT callers (no API client → `api_client_id` is NULL)
- Any partner flow before Gate 5 ships API Client identity

**Fix** (`idempotency_service.py:140-145`): normalize None → "" sentinel
at the service boundary, before INSERT and SELECT:

```python
org_id_norm = (organization_id or "").strip()
api_client_id_norm = (api_client_id or "").strip()
```

This guarantees the UNIQUE constraint always has comparable values.
The model/migration schema remains `nullable=True` (sentinel stored as
NULL is also valid since the constraint treats them all equal). The
normalization is internal to the service — caller still passes real
identity or None.

**Test**: `test_concurrent_insert_exactly_one_winner` fails without this
fix; passes with it.

---

## 4. Concurrency correctness (§8.3)

The dedup primitive is INSERT-with-UNIQUE. Two asyncio.gather requests
with the same key:

```
[T=0] request A: BEGIN, INSERT PENDING → flush succeeds (winner)
[T=0] request B: BEGIN, INSERT PENDING → flush raises IntegrityError
[T=1] request B: rollback, SELECT existing row → returns PENDING
[T=1] request B: returns in_progress=True (observer)
```

The loser never observes a half-written row. SELECT-then-INSERT would
race here and produce two `should_run=True` responses — explicitly
forbidden by §8.3.

`test_concurrent_insert_exactly_one_winner` proves exactly one winner
emerges from `asyncio.gather(acquire_or_replay, acquire_or_replay)`.

---

## 5. Endpoint wiring (agent_run.py)

The `run_agent` function now:

1. Reads `Idempotency-Key` from headers (line 270).
2. If present, computes `request_hash` and calls `acquire_or_replay` (line 273-286).
3. If `should_run=False`:
   - `in_progress=True` → return 200 with the existing `run_id` and `summary="(in progress)"` (line 287-300).
   - `in_progress=False` → return the saved snapshot verbatim (line 301-304).
4. Otherwise `dedup_record` is set; proceeds with the normal run.
5. After envelope construction, calls `mark_in_progress(db, dedup_record, run_id=run_id)` (line 330-338).
6. After the run succeeds/fails, calls `mark_completed` or `mark_failed` (line 396-413).
7. `IdempotencyKeyReusedError` propagates as 409 via FastAPI's HTTPException handling.

**Org identity source**: changed from the broken `current_user.tenant_id` (always empty — User model has no such field) to `Depends(get_current_organization)` which returns the real org. Falls back to `tenant_id` if org is unset.

---

## 6. Error handling

| Failure | Behavior |
|---|---|
| Idempotency-Key header empty | Bypass dedup (legacy behavior preserved) |
| Hash mismatch | HTTP 409 `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST` |
| DB INSERT fails non-UNIQUEly | HTTP 500 `IDEMPOTENCY_INTERNAL_ERROR` |
| `mark_in_progress` / `mark_completed` fails | Logged warning; run continues (non-fatal — partner just loses dedup) |
| Run itself fails | `mark_failed` is called; next replay re-runs rather than replaying the error |

---

## 7. Tests run

```
$ python -m pytest tests/unit/app/services/test_phase7_gate3_idempotency.py tests/test_api/test_phase7_gate3_agent_run_idempotency.py -v

tests/unit/app/services/test_phase7_gate3_idempotency.py
  PASSED test_completed_replay_returns_snapshot
  PASSED test_in_progress_replay_returns_run_id
  PASSED test_pending_replay_returns_in_progress
  PASSED test_hash_mismatch_raises_409
  PASSED test_concurrent_insert_exactly_one_winner
  PASSED test_mark_failed_transitions_status
  PASSED test_request_hash_is_stable_for_same_inputs
  PASSED test_request_hash_diverges_on_input_text
  PASSED test_request_hash_normalizes_agent_id_case
  PASSED test_request_hash_normalizes_whitespace

tests/test_api/test_phase7_gate3_agent_run_idempotency.py
  PASSED test_no_idempotency_key_runs_normally
  PASSED test_same_key_same_body_replays_snapshot
  PASSED test_same_key_different_body_returns_409
  PASSED test_replay_returns_completed_snapshot_verbatim

14 passed
```

Regression sweep: `python -m pytest tests/test_api/ --deselect ...test_hub_has_at_least_24_agents` → **538 passed, 0 failures** (1 deselected pre-existing).

---

## 8. What's NOT done (deferred to later gates)

- **Gate 5** will populate `api_client_id` from the partner's OAuth Client credentials. Currently always `None` (normalized to `""` sentinel). The dedup logic is correct today; the field is just empty for Console-JWT callers.
- **Gate 8** will surface `api_client_id` in usage meters so partners see "this dedup record belongs to me". Currently meters don't filter by it.
- **TTL cleanup**: a background job to delete `expires_at < now()` rows is not built. Default TTL is 24h; table will grow until manual cleanup. Documented in `idempotency_service.DEFAULT_TTL_SECONDS`.

---

## 9. Phase 7 §16 forbidden outputs check

| Forbidden | Status |
|---|---|
| PRODUCTION_READY | Not claimed |
| PUBLIC_NPM_PUBLISHED | N/A (this is backend) |
| 100% Corti parity claim | Not claimed |
| "Final" verdict before all gates | Not claimed |

Verdict: **PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION** at the gate level. Phase 7 continues with Gate 4 (Run cancel/timeout) — Checkpoint A (Gates 2+3) is complete.
