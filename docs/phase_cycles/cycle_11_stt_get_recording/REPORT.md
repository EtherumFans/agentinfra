# Cycle 11 — Recordings (STT) Get — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 6/6 回环一致性测试 + 165/165 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/recordings/get-recording.md`
(7,160 bytes) → `docs/corti-reverse-engineered/stt-get-recording.md`
→ archive `docs/phase_cycles/cycle_11_stt_get_recording/corti-stt-get-recording.md`.

Path: `GET /interactions/{id}/recordings/{recordingId}` → operationId
`recordings_get`. Response: raw binary (`text/plain` + `format: binary`).

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/api/v2_tools_stt.py` | MODIFIED | +60 (GET endpoint + Response + X-Stub headers) |
| `backend/tests/test_api/test_v2_stt_get_recording_consistency.py` | NEW | 175 |
| `docs/PHASE_1_3_CYCLE11_STT_GET_RECORDING.md` | NEW | 145 |
| `docs/phase_cycles/cycle_11_stt_get_recording/corti-stt-get-recording.md` | archive | 7,160B |

## Test results

```
tests/test_api/test_v2_stt_get_recording_consistency.py:
  test_stt_get_recording_spec_is_real_and_cached                           PASSED
  test_v2_stt_get_recording_default_returns_binary                         PASSED
  test_v2_stt_get_recording_missing_sentinel_returns_404                   PASSED
  test_v2_stt_get_recording_path_echo_via_headers                          PASSED
  test_v2_stt_get_recording_interaction_id_missing_returns_400             PASSED
  test_v2_stt_get_recording_content_type_is_text_plain                     PASSED
6 passed in 1.15s

tests/test_api/ (full regression):
165 passed in 229.06s (3:49)
- All prior cycles (159) ✓
- Phase 1.3 cycle 11 Recordings Get (6) ✓

frontend tsc --noEmit: exit 0
```

## 回环一致性测试 strategy

**Walker not used** — cycle 11 response is opaque binary bytes, not a
structured shape. Tests focus on:
- Spec sanity (correct paths/schemas + 404 presence)
- Content-type assertion (`text/plain` per spec)
- Body is opaque bytes (NOT a JSON envelope)
- 404 sentinel for missing recordingId
- Path-echo via `X-Stub-*` headers (since body is binary)
- 400 for empty path IDs

Cycle 11 also adds a **404 error code** (new for the recordings family;
cycles 9-10 did not have 404 in their spec). Sentinel `missing-{uuid}`
exercises this path.

**Test fixup**: First run failed on the 404 detail assertion because
FastAPI wraps HTTPException detail in `{"detail": {...}}`. Fixed by
reading `body["detail"]["status"]` instead of `body["status"]`. Cycles
1-10 hit the same wrap pattern but didn't trip on it (their error paths
weren't deeply inspected).