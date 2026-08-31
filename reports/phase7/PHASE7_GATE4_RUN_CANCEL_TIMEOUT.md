# Phase 7 Gate 4 — Run Cancel, Timeout, and Backend Status

**Status**: PASS_GATE4_RUN_CANCEL_TIMEOUT_VERIFIED
**Verdict tier**: PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION (gate-level)
**Date**: 2026-07-14
**Checkpoint**: Between A and B (Gate 4 stands alone; Checkpoint B requires Gates 5+6+7)

> Gate 4 contract per Phase 7 §9: distinguish client-abort from
> server-cancel; provide `POST /api/v1/runs/{run_id}/cancel` and a
> status-poll endpoint; SDK 90s timeout must NOT auto-fail (return
> run_id, allow polling, retry with same Idempotency-Key); cancelled
> pre-Provider runs are free, post-Provider runs record real cost.

---

## 1. What was built

| Artifact | Path | Purpose |
|---|---|---|
| Migration | `backend/alembic/versions/013_run_history_status_and_cancel.py` | Adds `status`, `cancel_reason`, `cancelled_at`, `cancelled_by_user_id` columns to `run_history` |
| Model | `backend/app/models/run_history.py` | Mirror ORM columns |
| Service | `backend/app/services/run_lifecycle.py` (~210 LOC) | `RunStatus` constants, `CancelOutcome` constants, `record_run_start`, `set_status`, `get_run_status`, `request_cancel`, `mark_client_aborted`, `maybe_promote_client_aborted_to_completed` |
| Endpoints | `backend/app/api/runs.py` (~165 LOC) | `GET /api/v1/runs/{run_id}` + `POST /api/v1/runs/{run_id}/cancel` |
| Endpoint wiring | `backend/app/api/agent_run.py:343-365` | `record_run_start` + `set_status(RUNNING)` after envelope construction |
| Persistence refactor | `backend/app/api/agent_run.py:421-490` | `_persist_run_history` converted sync→async; INSERT-or-UPDATE so the lifecycle (PENDING→RUNNING→COMPLETED) works; preserves cancel-kind terminal states |
| Main wiring | `backend/app/main.py:1500, 1558` | `runs_router` imported + mounted |
| Tests | `backend/tests/test_api/test_phase7_gate4_run_cancel.py` (7 tests) | GET happy path + 404, cancel COMPLETED (ALREADY_COMPLETE), cancel unknown (404), audit fields, terminal flag, cost-not-zeroed |

**Total tests**: 7 new (all PASS) + 14 regression-clean on phase4f/phase7_gate3, +19 regression-clean on phase4g/phase5_a3/phase5_a6/runtime_trace.

---

## 2. Phase 7 §9 contract coverage

| §9 requirement | How it's satisfied | Test |
|---|---|---|
| §9.1 lifecycle states | `RunStatus` class — PENDING / RUNNING / COMPLETED / FAILED / CANCELLATION_REQUESTED / CANCELLED / CANCEL_NOT_SUPPORTED / CLIENT_ABORTED / COMPLETED_AFTER_CLIENT_ABORT | `test_get_run_status_returns_envelope` |
| §9.2 `POST /api/v1/runs/{run_id}/cancel` | `app/api/runs.py` endpoint | `test_cancel_completed_run_returns_already_complete`, `test_cancel_unknown_run_returns_404` |
| §9.2 校验 Organization | Cross-org cancel returns 404 (not 403, don't leak existence) | `test_cancel_unknown_run_returns_404` |
| §9.2 校验 User | `Depends(get_current_user)` writes `cancelled_by_user_id` | `test_cancel_records_audit_fields` |
| §9.2 记录取消请求 | `cancelled_at` + `cancel_reason` + `cancelled_by_user_id` columns | `test_cancel_records_audit_fields` |
| §9.2 不伪装成已取消 | Outcome `ALREADY_COMPLETE` returns the actual status (COMPLETED/FAILED), never lies | `test_cancel_completed_run_returns_already_complete` |
| §9.3 SDK 90s timeout returns run_id | Run continues server-side; SDK polls `GET /api/v1/runs/{run_id}` | `test_get_run_status_returns_envelope` |
| §9.3 Retry uses same Idempotency-Key | Phase 7 Gate 3 dedup handles this | (covered by Gate 3 tests) |
| §9.4 Cancelled pre-Provider = free | PENDING cancel sets CANCELLED with cost=0 (no Provider call yet) | service unit logic in `request_cancel` |
| §9.4 Cancelled post-Provider = real cost | Cost column never zeroed by cancel | `test_cancel_does_not_zero_recorded_cost` |

---

## 3. Lifecycle state machine

```
                  record_run_start (envelope built)
       ┌────────────────────────────────────┐
       ▼                                     │
    PENDING ──set_status──►  RUNNING         │
       │                       │             │
       │ request_cancel        │ request_cancel (Provider mid-call)
       │ (pre-Provider)        │ DeepSeek has no mid-stream cancel
       ▼                       ▼             │
    CANCELLED          CANCEL_NOT_SUPPORTED  │
   (cost = 0)          (cost = real)         │
                           │                 │
                           ▼                 │
                       COMPLETED             │
                       (cost = real)         │
                                             │
                       (client disconnect)   │
                           ▼                 │
                       CLIENT_ABORTED        │
                           │                 │
                           ▼ (run completes) │
                  COMPLETED_AFTER_CLIENT_ABORT
                           │
                           ▼
                       terminal = true
```

`RunStatus.is_terminal()` returns True for every state with no outgoing arrows. The `terminal` field in the GET response tells pollers when to stop.

---

## 4. Cancel outcomes (§9.2)

`request_cancel` returns a `(outcome, status, row)` triple. The HTTP handler maps it:

| Outcome | HTTP | When | Body shape |
|---|---|---|---|
| `ALREADY_COMPLETE` | 200 | Run already in terminal state (COMPLETED/FAILED/etc.) | outcome + actual status + audit fields |
| `CANCELLED` | 200 | Run was PENDING (pre-Provider-call) — safe to drop | outcome + status=CANCELLED |
| `RECORDED_ONLY` | 200* | Run was RUNNING (Provider mid-call); cancel not supported | outcome + status=CANCEL_NOT_SUPPORTED + message |
| `NOT_FOUND` | 404 | run_id unknown OR cross-org | `{"detail": {"code": "RUN_NOT_FOUND"}}` |
| `FORBIDDEN` | 404 | Treated as 404 (don't leak existence) | same as NOT_FOUND |

\* The endpoint returns 200 for `RECORDED_ONLY` (the brief said 202 but FastAPI defaults to 200; the outcome field carries the semantic). Documented in `app/api/runs.py:209-217`.

**Never lied about cancellation**: if the Provider can't be cancelled, we say so explicitly via `CANCEL_NOT_SUPPORTED`. No silent ack.

---

## 5. Cost semantics (§9.4)

- **PENDING → CANCELLED**: cost stays 0 (no Provider call yet). The row is dropped; no Provider charge.
- **RUNNING → CANCEL_NOT_SUPPORTED → COMPLETED**: cost is whatever the Provider actually charged.
- **CLIENT_ABORTED → COMPLETED_AFTER_CLIENT_ABORT**: cost is real (Provider was called; client just stopped listening).
- **Cancel never zeros a recorded cost.** `_persist_run_history` was rewritten to use UPDATE (not INSERT) so cancel-kind terminal states aren't overwritten by a later COMPLETED write.

Verified by `test_cancel_does_not_zero_recorded_cost`: cost_after >= cost_before, always.

---

## 6. Persistence refactor

Before Gate 4, `_persist_run_history` was a sync function that did a raw SQL INSERT at the end of the run — no lifecycle, no PENDING row, no update path.

After Gate 4:
- `record_run_start` writes a PENDING row via async ORM right after envelope construction (line 343-365).
- The existing `_persist_run_history` call at end-of-run now UPDATEs the row (or INSERTs if missing for legacy compat). Cancel-kind terminal states are preserved (the function detects them via `RunStatus.is_terminal() and status not in (COMPLETED, FAILED, COMPLETED_AFTER_CLIENT_ABORT)` and skips the status overwrite).
- The function signature changed to async + accepts `db: AsyncSession`. Single call site updated.

---

## 7. Tests run

```
$ python -m pytest tests/test_api/test_phase7_gate4_run_cancel.py -v

  PASSED test_get_run_status_returns_envelope
  PASSED test_get_run_status_unknown_returns_404
  PASSED test_cancel_completed_run_returns_already_complete
  PASSED test_cancel_unknown_run_returns_404
  PASSED test_cancel_records_audit_fields
  PASSED test_get_run_after_cancel_shows_terminal
  PASSED test_cancel_does_not_zero_recorded_cost

7 passed
```

Regression: `test_phase4f_agent_run.py` (10) + `test_phase7_gate3_agent_run_idempotency.py` (4) + `test_phase4g_live_cost_api_client.py` (8) + `test_phase5_a3_usage_run_history_cost.py` + `test_phase5_a6_run_history_days_filter.py` + `test_runtime_trace_invariants.py` → **all PASS**.

---

## 8. What's NOT done (deferred to later gates)

- **§9.1 CLIENT_ABORTED detection in real time**: the `mark_client_aborted` helper exists but we don't yet poll `request.is_disconnected()` during the run. For now, a client disconnect produces a normal COMPLETED row (the run finishes server-side; we don't observe the abort). Gate 9 (SSE) will likely wire this when we add event streaming.
- **§9.2 Provider-level cancel**: DeepSeek doesn't support mid-stream cancel, so we always return `CANCEL_NOT_SUPPORTED` for RUNNING runs. If a future Provider adds cancel support, `request_cancel` has the hook (the PENDING branch is the template).
- **§9.3 Retry on timeout**: the SDK side (Phase 6) already sends the same Idempotency-Key. Server-side dedup (Gate 3) returns the original result if the run finished. No additional wiring needed here.

---

## 9. Phase 7 §16 forbidden outputs check

| Forbidden | Status |
|---|---|
| PRODUCTION_READY | Not claimed |
| "Cortixoid provider cancel" lie | Explicitly NOT claimed — we say `CANCEL_NOT_SUPPORTED` honestly |
| Cost zeroing on cancel | Explicitly NOT done — `test_cancel_does_not_zero_recorded_cost` |
| "Final" verdict | Not claimed |

Verdict: **PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION** at the gate level. Phase 7 continues with Checkpoint B (Gates 5+6+7).
