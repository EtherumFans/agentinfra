# Cycle 12.1 — Transcripts (STT) Get-Status — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 7/7 回环一致性测试 + 177/177 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/transcripts/get-transcript-status.md`
(5,477 bytes) → `docs/corti-reverse-engineered/stt-get-transcript-status.md`
→ archive `docs/phase_cycles/cycle_12_1_stt_get_transcript_status/corti-stt-get-transcript-status.md`.

Path: `GET /interactions/{id}/transcripts/{transcriptId}/status` → operationId
`transcripts_get_status`. Response: `TranscriptsStatusResponse {status: enum}`.

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | MODIFIED | +25 (TranscriptsStatusLiteral + TranscriptsStatusResponse) |
| `backend/app/api/v2_tools_stt.py` | MODIFIED | +75 (GET endpoint + 4 sentinels) |
| `backend/tests/test_api/test_v2_stt_get_transcript_status_consistency.py` | NEW | 235 |
| `docs/PHASE_1_3_CYCLE12_1_STT_GET_TRANSCRIPT_STATUS.md` | NEW | 165 |
| `docs/phase_cycles/cycle_12_1_stt_get_transcript_status/corti-stt-get-transcript-status.md` | archive | 5,477B |

## Test results

```
tests/test_api/test_v2_stt_get_transcript_status_consistency.py:
  test_stt_get_status_spec_is_real_and_cached                  PASSED
  test_stt_get_status_enum_matches_spec                        PASSED
  test_v2_stt_get_status_default_returns_completed             PASSED
  test_v2_stt_get_status_processing_sentinel                   PASSED
  test_v2_stt_get_status_failed_sentinel                       PASSED
  test_v2_stt_get_status_missing_sentinel_returns_404          PASSED
  test_v2_stt_get_status_reference_round_trip                  PASSED
7 passed in 1.12s

tests/test_api/ (full regression):
177 passed in 206.65s (3:26)
- All prior cycles (170) ✓
- Phase 1.3 cycle 12.1 Transcripts Get-Status (7) ✓

frontend tsc --noEmit: exit 0
```

## 回环一致性测试 strategy

Cycle 6/7 walker (with `$ref + parent-level metadata` fix) reused
verbatim. Cycle 12.1 response envelope is trivial (`{status: enum}`)
— no walker changes needed.

Notable cycle-12.1 specifics:
- 4 sentinels total (default / processing- / failed- / missing-)
- missing- is NEW for cycle 12.1; cycles 11/12 also use it (for missing recordings) so the pattern is consistent across the family
- 7 tests cover all sentinel paths + reference round-trip for all 3 status values

## STT family progress

**8/9 endpoints complete (89%).** Final endpoint remaining:
- Cycle 12.2: DELETE /interactions/{id}/transcripts/{transcriptId} (last)