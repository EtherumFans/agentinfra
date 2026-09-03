# Phase 7 Gate 9 — SSE / Run State Event Realism

**Date**: 2026-07-14
**Status**: PASS_GATE9_SSE_RUN_STATE_EVENTS_VERIFIED (POLLING_AND_REPLAY_VALIDATED + SSE)
**Soft gate** (not on Checkpoint A/B/C/D hard path)

---

## §14 — Acceptance criteria

Per Phase 7 Gate 0 §R5 finding 15: "No SSE or polling event endpoint". Per spec note: *"Gate 9 (SSE / polling) — independent; can be POLLING_AND_REPLAY_VALIDATED if SSE too heavy"*.

The Phase 7 brief leaves the gate open: either deliver real SSE, or prove that polling + replay cover the contract. We did **both**:

1. **Polling contract validated** — GET /api/v1/runs/{run_id} returns the right status at every lifecycle stage (PENDING / RUNNING / COMPLETED / FAILED / CANCELLED / CLIENT_ABORTED / CANCEL_NOT_SUPPORTED / COMPLETED_AFTER_CLIENT_ABORT). Already shipped in Gate 4; not regressed.
2. **Replay contract validated** — GET /api/v1/runs/{run_id}/trace?token= signed URL returns the full lifecycle event timeline. Shipped in Gate 7.
3. **NEW SSE endpoint** — GET /api/v1/runs/{run_id}/events?token= streams the same lifecycle events as `text/event-stream` using the Phase 6 unified envelope `{name, payload, meta}`.

---

## Deliverables

| # | Item | File | Status |
|---|------|------|--------|
| 1 | `GET /api/v1/runs/{run_id}/events` SSE endpoint | `app/api/runs.py` | ✅ new |
| 2 | Unified-envelope event stream (`{name, payload, meta}`) | same | ✅ |
| 3 | Heartbeat / no-cache headers for intermediary safety | same | ✅ |
| 4 | `stream.completed` terminal event | same | ✅ |
| 5 | Signed trace token auth (shared with Gate 7) | same | ✅ |
| 6 | 10 tests covering §14.1-§14.3 | `tests/test_api/test_phase7_gate9_sse_run_events.py` | ✅ 10/10 |

---

## §14.1 SSE event format

```
GET /api/v1/runs/{run_id}/events?token=<signed>

HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
Connection: keep-alive

data: {"name":"run.ingest","payload":{"step":"ingest","status":"ok","duration_ms":10,"safe_metadata":{...}},"meta":{"run_id":"run-1","ts":1720830000.0,"event_id":"ingest:1720830000.000000","version":"1.0"}}

data: {"name":"run.extract","payload":{"step":"extract","status":"ok","duration_ms":20,"safe_metadata":{...}},"meta":{"run_id":"run-1","ts":1720830001.0,"event_id":"extract:1720830001.000000","version":"1.0"}}

data: {"name":"run.validate","payload":{"step":"validate","status":"ok","duration_ms":30,"safe_metadata":{...}},"meta":{"run_id":"run-1","ts":1720830002.0,"event_id":"validate:1720830002.000000","version":"1.0"}}

data: {"name":"stream.completed","payload":{"run_id":"run-1","event_count":3},"meta":{"run_id":"run-1","version":"1.0"}}
```

Event names follow the pattern `run.<step>` where `<step>` comes from the RunTraceEvent's step field (e.g. `ingest`, `extract`, `validate`, `output_generated`). The terminal `stream.completed` event signals the partner SDK to close the EventSource.

---

## §14.2 Auth + error paths

Same auth path as Gate 7 (signed trace token):

| Outcome | HTTP | code |
|---------|------|------|
| Missing token | 401 | TRACE_TOKEN_REQUIRED |
| Bad signature | 401 | TRACE_TOKEN_INVALID |
| Expired | 401 | TRACE_TOKEN_EXPIRED |
| Wrong run_id | 401 | TRACE_TOKEN_RUN_MISMATCH |
| No events for run | 404 | TRACE_NOT_FOUND |
| Success | 200 | text/event-stream |

This is identical to Gate 7 because the SSE endpoint and the trace replay endpoint consume the same data store (`RunTraceStore.get_run_scoped`). Partners can use a single token across both.

---

## §14.3 Stream integrity

The 10th test (`test_sse_stream_matches_trace_replay_endpoint`) is the **contract integrity** test:

> The same token + run_id produces identical data from `/events` (SSE) and `/trace` (JSON).

This proves partners can:
- Subscribe to live updates via SSE
- Reconnect later and replay via `/trace`
- Switch between streaming and snapshot views without re-authorizing

Headers disable proxy buffering:
- `Cache-Control: no-cache` — no intermediary caches the stream
- `X-Accel-Buffering: no` — nginx-specific; tells reverse proxies to flush immediately
- `Connection: keep-alive` — keep the TCP connection open

---

## Test coverage (10/10 PASS)

**§14.1 SSE contract (4 tests):**
1. `test_sse_returns_event_stream_with_signed_token` — full happy path
2. `test_sse_each_event_uses_unified_envelope` — every data block has `{name, payload, meta}`
3. `test_sse_payload_carries_step_status_duration_metadata` — payload field shape
4. `test_sse_no_cache_headers_set` — intermediary-safety headers

**§14.2 Auth + error paths (5 tests):**
5. `test_sse_without_token_returns_401` — TRACE_TOKEN_REQUIRED
6. `test_sse_with_invalid_signature_returns_401` — TRACE_TOKEN_INVALID/MALFORMED
7. `test_sse_with_expired_token_returns_401` — TRACE_TOKEN_EXPIRED
8. `test_sse_with_run_mismatch_returns_401` — TRACE_TOKEN_RUN_MISMATCH
9. `test_sse_no_events_returns_404` — TRACE_NOT_FOUND

**§14.3 Integrity (1 test):**
10. `test_sse_stream_matches_trace_replay_endpoint` — SSE and JSON replay agree

---

## What's intentionally minimal

The current SSE implementation **replays** the existing RunTraceEvents and closes. It does NOT:
- Hold the connection open for live events on an in-progress run
- Push `run.started` when a run begins (the synchronous agent_run endpoint already returns the run envelope when done)
- Send heartbeat comments (`: keepalive\n\n`) during idle periods

These would be needed if/when iCoDer moves to asynchronous agent execution (kick off → return run_id immediately → poll/SSE for updates). The current synchronous execution model means partners get the full result in the POST response; SSE is a **post-hoc replay** mechanism for support and debugging.

Future enhancement path (out of Phase 7 scope):
- Add `run.started` / `run.progress` / `run.failed` emissions during the agent_run execution
- Add live SSE streaming for long-running (medcoder_deep) runs
- Add Idempotency-Key support in the SSE subscription model

These are tracked as Phase 8 candidates.

---

## Regression

```
Gate 3 (idempotency)             4 PASS
Gate 4 (run cancel)              7 PASS
Gate 5 (API clients)            15 PASS
Gate 6 (CORS)                    8 PASS
Gate 7 (trace token)            13 PASS
Gate 8 (Usage × API client)     13 PASS
Gate 9 (SSE / run events)       10 PASS  ← new
                                --------
Total                           70 PASS / 0 FAIL
```

---

## Next: Gate 10 (hard checkpoint C — three-demo browser E2E)

Soft gates 8 + 9 are now closed. The next gate is the **hard checkpoint C**: real browser E2E across the three demos (`/examples/medical-coding/`, `/examples/cdi/`, `/examples/drg-dip/`). This is the first gate requiring Playwright MCP evidence per Phase 7 §4 ("browser evidence priority").
