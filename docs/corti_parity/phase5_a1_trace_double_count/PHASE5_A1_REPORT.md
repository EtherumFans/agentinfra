# Phase 5 A1 — Trace Step Duration Double-Count Fix (BUG-12-01)

**Date:** 2026-07-10
**Gap closed:** BUG-12-01 (Phase 4-H §12 audit, P0 critical)
**Status:** PASS

## The bug

Phase 4-H §12 audit found that a 3-step success-path run produced 7 entries in `RunTraceStore.timeline` instead of 3. Each step (USER_MESSAGE_RECEIVED, OUTPUT_GENERATED, COMPLETION) appeared 2× — once without `duration_ms` from the direct `emit_trace_event` call, once with `duration_ms` from `persist_trace_events` re-emitting the inline `trace_events` list.

Symptom: 3-step run on `Medical Coding Agent` showed total `7 × 3020ms = 9060ms` phantom duration, making the trace page misleading.

## Root cause

`backend/app/api/agent_run.py` `_run_via_provider_registry()` did two things on the success path:

1. **Direct emits** at lines 537 (USER_MESSAGE_RECEIVED), 644 (OUTPUT_GENERATED), and 658 (COMPLETION) — wrote 3 events to `RunTraceStore`.
2. Then `_map_backend_response()` (called at the end of the function) built an inline `trace_events` list with the same 3 steps.
3. The unified-endpoint handler then called `persist_trace_events()` which **re-emitted** those 3 inline events to `RunTraceStore`.

Result: 6 events in store for a 3-step run. (Audit reported 7 because of the test fixture's specific timing — there was an extra inline event in one path.)

## The fix

Remove the duplicates. Three coordinated changes:

### Change 1 — `_run_via_provider_registry()` direct emits

**Removed:** OUTPUT_GENERATED + COMPLETION direct emits (lines 644-658 in old code).
**Kept:** USER_MESSAGE_RECEIVED direct emit (line 537) — happens before `invoke()` so it can't be in the inline list.

Reasoning: USER_MESSAGE_RECEIVED must be in `RunTraceStore` even if the provider call crashes before `_map_backend_response()` runs. The direct emit is the safety net.

### Change 2 — `_map_backend_response()` inline `trace_events`

**Removed:** inline `user_message_received` and `output_generated` entries.
**Kept:** inline `completion` entry only.

Reasoning: `persist_trace_events()` re-emits the inline list. Keeping only COMPLETION there means COMPLETION ends up in store 1× (from re-emit). USER_MESSAGE_RECEIVED is in store 1× (from direct emit). OUTPUT_GENERATED is in store 1× (from the provider's `emit_backend_metadata_event`, which fires inside `invoke()` and writes a richer event with backend metadata like `provider_id`, `backend_type`, `tool_rounds`).

### Change 3 — Error path unchanged

Error paths (unknown_agent at line 553, provider crash at line 574/626) keep their direct COMPLETION-failed emit. `persist_trace_events` is skipped on error path, so no double-count.

## Final event counts

| Path | Before | After |
|------|--------|-------|
| Success | 6-7 events (each step × 2) | **3 events** (USER_MESSAGE_RECEIVED + OUTPUT_GENERATED + COMPLETION, each × 1) |
| Error (unknown_agent) | 2 events | **2 events** (unchanged — error path already had no double-emit) |
| Error (provider crash) | 2 events | **2 events** (unchanged) |

## Test

`backend/tests/test_api/test_phase5_a1_trace_double_count.py` — 2 tests:

1. `test_a1_success_path_has_exactly_3_trace_events_no_double_count` — POSTs a real coding_evidence_case.json fixture through `/api/v1/agents/{id}/run`, then GETs `/api/runtime/runs/{run_id}/trace` and asserts `len(timeline) == 3` with each step appearing exactly once.
2. `test_a1_error_path_has_exactly_2_trace_events_no_double_count` — POSTs to a nonexistent agent, asserts error envelope `{error: true}`, then asserts trace has 2 events (USER_MESSAGE_RECEIVED + COMPLETION failed).

```
$ python -m pytest tests/test_api/test_phase5_a1_trace_double_count.py -v
tests/test_api/test_phase5_a1_trace_double_count.py::test_a1_success_path_has_exactly_3_trace_events_no_double_count PASSED
tests/test_api/test_phase5_a1_trace_double_count.py::test_a1_error_path_has_exactly_2_trace_events_no_double_count PASSED
======================== 2 passed, 2 warnings in 2.04s ========================
```

## Files changed

- `backend/app/api/agent_run.py` — -71 / +18 lines (removed duplicate emits + duplicate inline entries; added explanatory comment block)

## Bonus

While fixing, also flipped `cost.currency` from `"USD"` to `"CNY"` on the same file (line 760) per Phase 5 A2 currency unification. See A2 report.
