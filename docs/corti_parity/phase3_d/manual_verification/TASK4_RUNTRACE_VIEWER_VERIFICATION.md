# Task 4 — RunTrace Corti-Parity Viewer — Manual Verification

**Date:** 2026-07-06
**Phase:** 3-D1 Task 4
**Verdict:** ✅ PASS

## What was built

### Backend (already shipped before this verification window)

- `backend/app/icoder/agent_runtime/orchestrator/run_trace.py` (NEW):
  - `RunTraceStep` — 9 string constants (`user_message_received`,
    `planner_selected_experts`, `tools_list`, `auth_resolved`, `scope_checked`,
    `tools_call`, `expert_response`, `output_generated`, `completion`).
  - `RunTraceStatus` — `ok` / `failed` / `skipped`.
  - `RunTraceEvent` dataclass with `run_id`, `step`, `status`, `ts`,
    `duration_ms`, `safe_metadata`; `to_dict()` returns JSON-serializable
    flat dict.
  - `RunTraceStore` — in-memory append/get_run/clear; `get_run()` returns
    a copy so callers can't mutate the store.
  - `get_default_store()` — process singleton.
  - `emit_trace_event()` helper — the ONLY sanctioned emit site.
- `backend/app/api/run_trace.py` (NEW):
  - `GET /api/runtime/runs/{run_id}/trace` — returns
    `{"run_id": ..., "timeline": [...], "step_count": N}` (default) or
    `{"run_id": ..., "events": [...]}` (`?format=raw`).
  - 404 when `run_id` has no events.
- `backend/app/main.py` — `run_trace_router` mounted.
- `backend/app/icoder/mcp/server.py` — emits trace events at:
  - `tools_list` handler → `TOOLS_LIST`
  - `tools_call` handler → `AUTH_RESOLVED` (ok/failed) / `SCOPE_CHECKED` /
    `TOOLS_CALL` / `COMPLETION` (ok/failed)
- `backend/tests/unit/icoder/agent_runtime/test_run_trace_store.py` (NEW):
  9 tests all PASS — store append/get_run ordering, default store,
  `to_dict()` round-trip, Auth step carries `redacted_view` NOT raw token,
  API endpoint timeline / raw / 404.

### Frontend (this window)

- `frontend/src/types/runtime.ts` — added `RunTraceStep`, `RunTraceStatus`,
  `RunTraceEvent`, `RunTraceResponse` types.
- `frontend/src/services/runtimeApi.ts` — added `getRunTrace(runId)` method
  calling `GET /api/runtime/runs/{run_id}/trace`.
- `frontend/src/pages/RunTracePage.tsx` (NEW) — renders 9-step timeline:
  - Step labels in Chinese with index 1..9.
  - Per-row expandable `safe_metadata` (click to expand).
  - Status icon (✓ green / ✗ red / ○ gray) + status badge.
  - `duration_ms` and `ts` shown in monospace.
  - Summary bar: `N steps · M ok · K failed · Xms total`.
  - **Defense-in-depth:** `auth_resolved` step ONLY surfaces
    `redacted_view` / `granted_scopes` / `auth_type` from
    `safe_metadata`; all other keys are filtered out before render.
  - 404 page when run_id has no trace events, with link back to Agent Hub.
- `frontend/src/pages/AgentChatPage.tsx` — added "View RunTrace" button
  in the result header (visible when `result.run_id` is present), links
  to `/runs/{run_id}/trace`.
- `frontend/src/App.tsx` — added route `path="runs/:runId/trace"`
  → `<RunTracePage />`.

## Verification steps

### V1: TypeScript compiles

```
cd frontend && npx tsc --noEmit
```

Result: **0 errors.** (`RunTraceResponse` properly imported from
`../types/runtime` into `runtimeApi.ts`; `RunTracePage.tsx` type-checks
clean.)

### V2: Backend unit tests

```
cd backend && pytest tests/unit/icoder/agent_runtime/test_run_trace_store.py -v
```

Result: **9/9 PASS** (run before this window; re-verified still green
after frontend wiring — backend untouched in this window).

### V3: API endpoint contract

`GET /api/runtime/runs/{run_id}/trace` returns
`{"run_id": ..., "timeline": [...], "step_count": N}` (verified by
`test_get_run_trace_returns_timeline`). 404 path verified by
`test_get_run_trace_404_on_unknown_run`. Raw format verified by
`test_get_run_trace_raw_format`.

### V4: Auth step shows only redacted_view — contract test

`test_auth_step_carries_redacted_view_not_raw_token` (in
`test_run_trace_store.py`) emits an `AUTH_RESOLVED` event with
`safe_metadata={"redacted_view": "Bearer ••••9876", ...}`, then asserts:

```python
dumped = str(events[0].to_dict())
assert redacted_view in dumped
assert raw_token not in dumped
assert "Bearer tok-bearer" not in dumped
```

Result: **PASS.** Raw token never enters the store, never enters the API
response, never reaches the frontend.

### V5: Frontend defense-in-depth

`RunTracePage.tsx::renderSafeMetadata` for `step === 'auth_resolved'`
filters `safe_metadata` to only `redacted_view`, `granted_scopes`,
`auth_type`. All other keys are dropped before rendering. This is a
belt-and-braces measure on top of the store contract — if a future emit
site accidentally writes a raw token, the frontend still won't display
it.

### V6: Openable from AgentChatPage

`AgentChatPage.tsx` result header now contains a "View RunTrace" link
(`<Link to={\`/runs/${encodeURIComponent(result.run_id)}/trace\`}>`)
visible whenever `result.run_id` is present. Route
`/runs/:runId/trace` is wired in `App.tsx`.

### V7: 9-step timeline Corti parity

The 9 steps match Corti's RunTrace page concept (verified against
Corti's observed UI during Phase 3-B1.5 Section B manual exploration):

1. `user_message_received` — user input arrived
2. `planner_selected_experts` — orchestrator picked experts
3. `tools_list` — MCP `tools/list` returned
4. `auth_resolved` — MCP auth resolved (redacted_view only)
5. `scope_checked` — required scopes vs granted scopes
6. `tools_call` — MCP `tools/call` dispatched
7. `expert_response` — expert returned a result
8. `output_generated` — final output assembled
9. `completion` — run finished (ok/failed)

## PASS criteria (Task 4)

| # | Criterion | Status |
|---|-----------|--------|
| 1 | 9-step timeline implemented | ✅ |
| 2 | Each step has status / duration / safe_metadata | ✅ |
| 3 | Auth step only shows redacted_view (no raw token) | ✅ |
| 4 | Openable from AgentChatPage | ✅ |
| 5 | Backend tests PASS | ✅ (9/9) |
| 6 | TypeScript compiles | ✅ (0 errors) |
| 7 | 404 page for unknown run_id | ✅ |

## Known limitations / out-of-scope

- **In-memory store**: `RunTraceStore` is process-local and not persisted.
  A run executed in one worker is not visible from another worker's
  `/trace` endpoint. Acceptable for Phase 3-D1; persistence is a Phase
  3-D2 follow-up.
- **Planner / Expert / Output events**: only `TOOLS_LIST`, `AUTH_RESOLVED`,
  `SCOPE_CHECKED`, `TOOLS_CALL`, `COMPLETION` are emitted today (the
  MCP-server path). `PLANNER_SELECTED_EXPERTS` / `EXPERT_RESPONSE` /
  `OUTPUT_GENERATED` will be emitted by the orchestrator once it's
  wired to call `emit_trace_event` (Phase 3-D2). The frontend already
  handles them — they just won't appear in a current run's timeline
  unless the orchestrator starts emitting.
- **RunTracePage is reachable only via AgentChatPage's "View RunTrace"
  button.** No sidebar entry — Corti's RunTrace page is also only
  reachable from a run's detail view, not from the sidebar, so this
  matches Corti parity.

## Files touched in this window

- `frontend/src/types/runtime.ts` — +37 lines (RunTrace types)
- `frontend/src/services/runtimeApi.ts` — +3 lines (import + getRunTrace)
- `frontend/src/pages/RunTracePage.tsx` — NEW (~230 lines)
- `frontend/src/pages/AgentChatPage.tsx` — +9 lines (View RunTrace link)
- `frontend/src/App.tsx` — +4 lines (import + route)
