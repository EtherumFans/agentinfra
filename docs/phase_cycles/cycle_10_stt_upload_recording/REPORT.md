# Cycle 10 — Recordings (STT) Upload — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 7/7 回环一致性测试 + 159/159 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/recordings/upload-recording.md`
(6,386 bytes) → `docs/corti-reverse-engineered/stt-upload-recording.md`
→ archive `docs/phase_cycles/cycle_10_stt_upload_recording/corti-stt-upload-recording.md`.

Path: `POST /interactions/{id}/recordings/` → operationId
`recordings_upload`. Body: `application/octet-stream` (raw binary).
Response 201: `RecordingsCreateResponse {recordingId: UUID}`.

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | MODIFIED | +15 (RecordingsCreateResponse) |
| `backend/app/api/v2_tools_stt.py` | MODIFIED | +85 (POST endpoint + Request body + 150 MB cap) |
| `backend/tests/test_api/test_v2_stt_upload_recording_consistency.py` | NEW | 252 |
| `docs/PHASE_1_3_CYCLE10_STT_UPLOAD_RECORDING.md` | NEW | 145 |
| `docs/phase_cycles/cycle_10_stt_upload_recording/corti-stt-upload-recording.md` | archive | 6,386B |

## Test results

```
tests/test_api/test_v2_stt_upload_recording_consistency.py:
  test_stt_upload_spec_is_real_and_cached                       PASSED
  test_stt_upload_response_required_field                       PASSED
  test_v2_stt_upload_binary_body_returns_201                    PASSED
  test_v2_stt_upload_empty_body_rejected                        PASSED
  test_v2_stt_upload_path_echoes_interaction_id                 PASSED
  test_v2_stt_upload_trailing_slash_alias                       PASSED
  test_v2_stt_upload_reference_round_trip                       PASSED
7 passed in 1.16s

tests/test_api/ (full regression):
159 passed in 234.11s (3:54)
- All prior cycles (152) ✓
- Phase 1.3 cycle 10 Recordings Upload (7) ✓

frontend tsc --noEmit: exit 0
```

## 回环一致性测试 strategy

Cycle 6/7/8/9 walker (with `$ref + parent-level metadata` fix) reused
verbatim. Cycle 10 response envelope is trivial
(`{recordingId: UUID}`) — no walker changes needed.

**Notable cycle-10 milestone:** First **non-JSON content-type**
endpoint in iCoDer's v2 surface. Body read via `await request.body()`
(raw binary), stub does NOT persist (real audio storage is separate
Phase 1.3 task). 150 MB cap enforced per spec; 120-minute audio
duration cap not enforced (would require audio parsing).

Cycle 10 makes create-transcript (cycle 8) a real wire: callers can
now chain upload-recording → create-transcript referencing the returned
recordingId.