# Audit Gate 7 — Run / Trace / Event / Usage Audit (Tracks I1-I6)

> Per PDF §三 Track I: audits the run lifecycle, trace store, event surface, and usage metering. Determines whether the observability story is real or theater.

## I1. Run lifecycle — REAL with 5 status states

### I1.1 Status state machine

`backend/app/services/run_lifecycle.py` defines 5 states (alembic 013):

```
PENDING → RUNNING → COMPLETED | FAILED | CANCELLED | CLIENT_ABORTED
                                       (terminal)   (terminal)    (terminal)
```

`COMPLETED_AFTER_CLIENT_ABORT` is a special terminal: client gave up but server finished. Per Phase 7 §9.4: "never zero a recorded cost" — this state preserves cost even when client cancels.

DB distribution (`run_history.status`):

```
COMPLETED    239
FAILED         1
```

No CANCELLED, no CLIENT_ABORTED in the production record. The cancel endpoint exists but has never been exercised in production.

### I1.2 Lifecycle endpoints — Phase 7 Gate 4

| Method | Path | Real? |
|--------|------|-------|
| GET | `/api/v1/runs/{run_id}` | ✅ Returns status + cost + cancel info |
| POST | `/api/v1/runs/{run_id}/cancel` | ✅ Never lies — returns `CANCEL_NOT_SUPPORTED` for DeepSeek mid-call |

`record_run_start()` is called from agent_run.py:396, BEFORE the actual LLM call, so PENDING rows exist even for in-flight runs. Partners can poll `GET /api/v1/runs/{run_id}` after SDK 90s timeout.

## I2. Trace store — MEMORY MODE, real DB code is dormant (G4-002 root cause)

### I2.1 The smoking gun

`backend/app/config.py:93`:
```python
RUNTRACE_STORE: str = "memory"  # memory | db
```

Live check:
```
RUNTRACE_STORE: memory
```

`run_trace_events` table: **0 rows**. This is the root cause of G4-002.

### I2.2 Code is real but unused

`backend/app/icoder/agent_runtime/orchestrator/run_trace.py`:
- Line 178: `class RunTraceStore` (abstract base)
- Line 209: `DbRunTraceStore` — uses sync SQLAlchemy engine, org-scoped queries
- Line 342: `get_default_store()` — selects memory vs db per `settings.RUNTRACE_STORE`

The DB-backed store is fully implemented (defensive PHI scrubbing, cross-worker visibility, survives restart). It's just **disabled by default**.

### I2.3 9-step Corti-parity timeline

`RunTraceStep` class defines 9 steps:

```
1. USER_MESSAGE_RECEIVED
2. PLANNER_SELECTED_EXPERTS
3. TOOLS_LIST
4. AUTH_RESOLVED
5. SCOPE_CHECKED
6. TOOLS_CALL
7. EXPERT_RESPONSE
8. OUTPUT_GENERATED
9. COMPLETION (status="ok" | "failed")
```

But: agent_run.py:798 emits only `USER_MESSAGE_RECEIVED` directly, the provider's `emit_backend_metadata_event` emits `OUTPUT_GENERATED`, and `_map_backend_response` emits `COMPLETION`. So a typical unified-endpoint run produces **3 events**, not 9. The Corti-parity 9-step claim is **overstated** for the unified path; only the full InboundHandler (medcoder_deep) emits all 9.

### I2.4 Frontend trace page — graceful 404

`GET /api/runtime/runs/{run_id}/trace` returns 404 when no events exist. Verified live:

```
$ curl /api/runtime/runs/run-ad3ea52d.../trace
{"detail":"no trace events for run_id 'run-ad3ea52d-136f-4e3c-a12a-a187c0aa0368'"}
```

The RunTracePage (`/runs/:runId/trace`) renders this as a graceful empty state — but since **every** run_id has zero events, the page is functionally useless in production.

## I3. Event surface — 3 protocols, 1 broken

### I3.1 Inline trace_events in AgentRunResponse

Real — every successful `/api/v1/agents/{id}/run` response carries `trace_events[]` with the COMPLETION event (plus USER_MESSAGE_RECEIVED + OUTPUT_GENERATED via persist_trace_events). Frontend Agent Detail chat renders this inline.

### I3.2 SSE stream — Phase 7 Gate 9

`GET /api/v1/runs/{run_id}/events?token=<signed>` emits `text/event-stream` with unified envelope `{name, payload, meta}`:

```
data: {"name": "run.user_message_received", "payload": {...}, "meta": {...}}\n\n
```

- HMAC-signed 24h token (same as Gate 7 trace_url)
- `X-Accel-Buffering: no` disables proxy buffering
- Replays RunTraceEvents + terminal `stream.completed`
- Code-complete, integration-verified

But — since `RUNTRACE_STORE=memory` and traces are essentially inline-only, the SSE endpoint has the same coverage gap as the trace page.

### I3.3 Persisted events (DB) — DORMANT

`run_trace_events` table is empty. emit_trace_event is called in production, but writes go to InMemoryRunTraceStore (process-local dict). Cross-worker visibility + restart durability are theoretically present but practically off.

## I4. Usage metering — REAL aggregation, with caveats

### I4.1 Endpoints — Phase 5 A3 + Phase 6 Gate 8 + Phase 7 Gate 8

| Endpoint | Purpose | Real? |
|-----------|---------|-------|
| GET `/api/usage/tokens` | Real-time LLM token tracker (in-memory) | ✅ |
| GET `/api/usage/summary?days=N` | Aggregated requests + cost | ✅ reads run_history.cost_usd |
| GET `/api/usage/by-agent?days=N` | Per-agent cost breakdown | ✅ |
| GET `/api/usage/by-client?days=N` | Per-API-client cost (partner attribution) | ✅ |
| GET `/api/usage/history?days=N` | Recent activity stream | ✅ |

### I4.2 Aggregation correctness — verified via DB

`/api/usage/summary` SQL (usage.py:99-110):
```python
cost_query = (
    select(func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0))
    .where(RunHistoryModel.user_id == str(user.id))
    .where(RunHistoryModel.created_at >= since)
)
```

DB confirms: total cost_usd across all run_history = **¥0.049392** (CNY column mislabeled as USD).

For admin@icoder.ai (`f237e192bbd5`), expected `/api/usage/summary?days=30` to surface ~¥0.014714 from the 83 audit-log requests + ¥0.030678 from run_history.

### I4.3 Cost attribution is broken on the largest agent

| Agent | Runs | Total Cost (¥) |
|-------|------|----------------|
| medical-coding-agent (corti_like_fast) | 35 | **0.0000** ← G5-001 |
| drg-analyzer (a2a_pure_llm) | 24 | 0.0139 |
| discharge-summary-structuring | 19+9 | 0.0043 |
| evidence-extractor | 17+8 | 0.0088 |
| All others | various | various |

**42 of 240 runs (17.5%) have zero cost**, all because medical-coding-agent runs the broken FastCodingRuntime path. This means `/api/usage/by-agent` under-reports medical coding cost by **100%** for the core product agent.

### I4.4 Audit log coverage — LIMITED

`audit_logs.action` distribution:

```
user.login              160   (51%)
user.register            40   (13%)
preview_session.create   17   (5%)
preview_session.exchange  6
preview_session.revoke    5
```

**NOT audited**: agent runs, CDI runs, billing transactions, OAuth token issuance, MCP tool calls. The audit log covers auth + preview sessions only.

## I5. Phase 7 hard-checkpoint attribution — REAL but never exercised

### I5.1 Idempotency (Gate 3)

`idempotency_records`: **11 rows**. Phase 7 Gate 3 is live and exercised. Breakdown by status:

```
COMPLETED    10
FAILED        1
```

All from medical-coding-agent (Phase 7 testing) + 1 CDI failure + 1 drg-analyzer. Idempotency-Key dedup works.

### I5.2 API Client attribution (Gate 5)

`run_history.api_client_id` distribution:

```
NULL        240   (100%)
```

**Only 1 OAuth client exists** in the system (`partner-ref-07ef23d306cf`, Phase 7 Gate 12 reference app). Most runs are Console-initiated (api_client_id IS NULL, which is the correct Console sentinel). The Phase 7 Gate 12 reference app run IS attributed correctly to `partner-ref-07ef23d306cf` (visible in idempotency_records).

### I5.3 Run cancel (Gate 4)

0 cancel records in production. The endpoint is real but untested in production usage.

### I5.4 Signed trace URL (Gate 7)

`build_trace_url` is called for every partner run. The signed URL pattern:

```
{base_url}/api/v1/runs/{run_id}/trace?token=<HMAC-SHA256>
```

24h TTL, bound to `run_id` + `organization_id`. Constant-time comparison via `secrets.compare_digest`. Code-complete, integration-verified.

## I6. New findings

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G7-001** | P0 | trace-store | `RUNTRACE_STORE="memory"` is the default — `run_trace_events` DB table is empty (0 rows) despite full DbRunTraceStore implementation. RunTrace page is non-functional in production. The Phase 3-D2 "DB-backed store" is dormant code. |
| **G7-002** | P1 | audit-coverage | `audit_logs` table only records 5 action types (user.login, user.register, preview_session.*). Agent runs, CDI runs, OAuth token issuance, MCP tool calls, billing transactions — NONE are audit-logged. |
| **G7-003** | P1 | cost-attribution | `/api/usage/by-agent` under-reports medical-coding cost by 100% because 35 corti_like_fast runs have cost=0 (G5-001 propagation). The Usage page lies to operators about the cost of the core product. |
| **G7-004** | P2 | trace-coverage | The "9-step Corti-parity timeline" claim is overstated — typical unified-endpoint runs emit only 3 events (USER_MESSAGE_RECEIVED + OUTPUT_GENERATED + COMPLETION). Only medcoder_deep emits all 9, and that mode has 0 production invocations. |
| G7-005 | P2 | trace-store | `InMemoryRunTraceStore` is process-local — multi-worker uvicorn deployments lose cross-worker visibility even if RUNTRACE_STORE were left at "memory" intentionally. |
| G7-006 | P3 | token-tracker | `token_tracker.py` is in-memory only, lost on restart, not per-agent despite the docstring claim "per-agent/session tracking" (the implementation is process-wide). |

## I7. Track-level verdicts (interim)

| Sub-track | Verdict |
|-----------|---------|
| **I1 Run lifecycle** | `REAL_5_STATES_PARTNER_POLLING_LIVE` — PENDING/RUNNING/COMPLETED/FAILED/CANCELLED; cancel endpoint never lies; only 1 FAILED + 0 CANCELLED in production record |
| **I2 Trace store** | `MEMORY_MODE_DEFAULT_DB_CODE_DORMANT` — DbRunTraceStore fully implemented but disabled; run_trace_events table empty; RunTrace page is non-functional |
| **I3 Event surface** | `INLINE_REAL__SSE_REAL__DB_DORMANT` — Inline + SSE work; persisted events broken by RUNTRACE_STORE config |
| **I4 Usage metering** | `REAL_AGGREGATION_BUT_UNDERREPORTS_MEDICAL_CODING_100PCT` — 5 endpoints with real SQL aggregation; cost attribution broken for the largest agent |
| **I5 Attribution** | `GATES_3_4_5_7_LIVE_RARELY_EXERCISED` — Idempotency-Keys, api_client_id, signed trace URL all work; only 11 idempotency_records + 1 OAuth client in production record |

## I8. Gate 7 verdict

`OBSERVABILITY_THEATER__RUN_LIFECYCLE_REAL_BUT_TRACE_DB_DORMANT_AND_AUDIT_LOG_THIN`

Specifically:

- ✅ Run lifecycle is real (5 states, partner polling, never-lies cancel)
- ✅ Phase 7 hard checkpoints (3, 4, 5, 7) are live with real code + DB schema
- ❌ **G7-001 P0**: `RUNTRACE_STORE=memory` makes the entire DB trace layer dormant; RunTrace page is non-functional in production
- ❌ **G7-002 P1**: Audit log covers only auth + preview sessions; the actual product work (agent runs, CDI, billing) is unaudited
- ❌ **G7-003 P1**: Usage page silently under-reports medical coding cost by 100% — operators cannot trust the cost dashboard
- ⚠️ 9-step Corti-parity timeline is overstated (3 events typical, 9 only in medcoder_deep which has 0 production runs)
- ✅ Inline trace_events in AgentRunResponse + SSE stream both work

Gate 7 closes. Proceed to **Gate 8 — Embedded, SDK, API Client, Partner App**.
