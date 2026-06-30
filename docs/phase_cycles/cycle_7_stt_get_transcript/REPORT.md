# Cycle 7 — Transcripts (STT) GET single — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 8/8 回环一致性测试 + 134/134 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/transcripts/get-transcript.md`
(9,859 bytes) → `docs/corti-reverse-engineered/stt-get-transcript.md`
→ archive `docs/phase_cycles/cycle_7_stt_get_transcript/corti-stt-get-transcript.md`.

Path: `GET /interactions/{id}/transcripts/{transcriptId}` → operationId
`transcripts_get`. Response `TranscriptsResponse` with required
`id/metadata/transcripts(nullable)/usageInfo/recordingId/status`.

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | MODIFIED | +30 (CommonUsageInfo + TranscriptsResponse) |
| `backend/app/api/v2_tools_stt.py` | MODIFIED | +130 (single-transcript endpoint + stub) |
| `backend/tests/test_api/test_v2_stt_get_transcript_consistency.py` | NEW | 290 |
| `docs/PHASE_1_3_CYCLE7_STT_GET_TRANSCRIPT.md` | NEW | 175 |
| `docs/phase_cycles/cycle_7_stt_get_transcript/corti-stt-get-transcript.md` | archive | 9,859B |

## Test results

```
tests/test_api/test_v2_stt_get_transcript_consistency.py:
  test_stt_get_spec_is_real_and_cached                              PASSED
  test_stt_get_status_enum_matches_spec                             PASSED
  test_v2_stt_get_completed_shape_matches_corti_spec                PASSED
  test_v2_stt_get_processing_shape_with_nullable_transcripts        PASSED
  test_v2_stt_get_failed_shape_with_nullable_transcripts            PASSED
  test_v2_stt_get_path_echoes_ids                                   PASSED
  test_v2_stt_get_completed_has_populated_transcripts               PASSED
  test_v2_stt_get_reference_round_trip                              PASSED
8 passed in <1s

tests/test_api/ (full regression):
134 passed in 217.46s (3:37)
- All prior cycles (126) ✓
- Phase 1.3 cycle 7 STT GET single (8) ✓

frontend tsc --noEmit: exit 0
```

## 回环一致性测试 strategy

Cycle 6 walker (with `$ref + parent-level metadata` fix) reused
verbatim. Cycle 7's two nullable cases (processing + failed) passed
without further walker changes — confirming the fix is generic and
backward-compatible.

Three transcript_id sentinels (default / `processing-{uuid}` /
`failed-{uuid}`) exercise the full status enum without needing real
async processing.