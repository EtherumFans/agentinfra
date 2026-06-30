# Cycle 12.2 — Transcripts (STT) Delete — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 5/5 回环一致性测试 + 182/182 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/transcripts/delete-transcript.md`
(5,061 bytes) → `docs/corti-reverse-engineered/stt-delete-transcript.md`
→ archive `docs/phase_cycles/cycle_12_2_stt_delete_transcript/corti-stt-delete-transcript.md`.

Path: `DELETE /interactions/{id}/transcripts/{transcriptId}` → operationId
`transcripts_delete`. Response: **204 No Content** (empty body).

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/api/v2_tools_stt.py` | MODIFIED | +50 (DELETE endpoint) |
| `backend/tests/test_api/test_v2_stt_delete_transcript_consistency.py` | NEW | 175 |
| `docs/PHASE_1_3_CYCLE12_2_STT_DELETE_TRANSCRIPT.md` | NEW | 195 |
| `docs/phase_cycles/cycle_12_2_stt_delete_transcript/corti-stt-delete-transcript.md` | archive | 5,061B |

## Test results

```
tests/test_api/test_v2_stt_delete_transcript_consistency.py:
  test_stt_delete_transcript_spec_is_real_and_cached                  PASSED
  test_v2_stt_delete_transcript_default_returns_204                   PASSED
  test_v2_stt_delete_transcript_status_sentinels_still_deletable      PASSED
  test_v2_stt_delete_transcript_empty_path_rejected                   PASSED
  test_v2_stt_delete_transcript_completes_stt_family                 PASSED
5 passed in 1.22s

tests/test_api/ (full regression):
182 passed in 222.82s (3:42)
- All prior cycles (177) ✓
- Phase 1.3 cycle 12.2 Transcripts Delete (5) ✓

frontend tsc --noEmit: exit 0
```

## Phase 1.3 STT parity — FINAL COMPLETION

After cycle 12.2, **Phase 1.3 STT parity is COMPLETE**:

**Transcripts family (5 of 5):**
- Cycle 6: GET /interactions/{id}/transcripts/ (LIST)
- Cycle 7: GET /interactions/{id}/transcripts/{transcriptId} (single)
- Cycle 8: POST /interactions/{id}/transcripts/ (create)
- Cycle 12.1: GET /interactions/{id}/transcripts/{transcriptId}/status
- Cycle 12.2: DELETE /interactions/{id}/transcripts/{transcriptId}

**Recordings family (4 of 4):**
- Cycle 9: GET /interactions/{id}/recordings/ (LIST)
- Cycle 10: POST /interactions/{id}/recordings/ (upload, octet-stream)
- Cycle 11: GET /interactions/{id}/recordings/{recordingId} (text/plain binary)
- Cycle 12: DELETE /interactions/{id}/recordings/{recordingId}

**9 of 9 STT endpoints complete (100%).**

## 回环一致性测试 strategy

**Walker not used** — DELETE returns no body. The closing test
(`test_v2_stt_delete_transcript_completes_stt_family`) exercises ALL 9
STT endpoints (5 transcripts + 4 recordings) in sequence, verifying
each returns its canonical status code. This is the definitive close
test for Phase 1.3 STT parity — if any of the 9 endpoints regress,
this test catches it.

Cycle 12.2 also notably does NOT include 404 (unlike cycles 11/12 for
delete-recording). The spec lists only 400/401/403/500/504 for
delete-transcript. iCoDer stub honors spec exactly — no missing-
sentinel for cycle 12.2.