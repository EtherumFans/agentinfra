# Cycle 8 — Transcripts (STT) Create — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 11/11 回环一致性测试 + 145/145 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/transcripts/create-transcript.md`
(14,078 bytes) → `docs/corti-reverse-engineered/stt-create-transcript.md`
→ archive `docs/phase_cycles/cycle_8_stt_create_transcript/corti-stt-create-transcript.md`.

Path: `POST /interactions/{id}/transcripts/` → operationId
`transcripts_create`. Request `TranscriptsCreateRequest` with required
`recordingId/primaryLanguage` + 9 optional knobs. Response 201 =
`TranscriptsResponse` (re-used from cycle 7 verbatim).

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | MODIFIED | +80 (4 new schemas) |
| `backend/app/api/v2_tools_stt.py` | MODIFIED | +105 (POST endpoint + stub) |
| `backend/tests/test_api/test_v2_stt_create_transcript_consistency.py` | NEW | 312 |
| `docs/PHASE_1_3_CYCLE8_STT_CREATE_TRANSCRIPT.md` | NEW | 175 |
| `docs/phase_cycles/cycle_8_stt_create_transcript/corti-stt-create-transcript.md` | archive | 14,078B |

## Test results

```
tests/test_api/test_v2_stt_create_transcript_consistency.py:
  test_stt_create_spec_is_real_and_cached                       PASSED
  test_stt_create_required_fields_match_spec                    PASSED
  test_v2_stt_create_minimal_shape_matches_corti_spec           PASSED
  test_v2_stt_create_missing_recording_id_rejected              PASSED
  test_v2_stt_create_missing_primary_language_rejected          PASSED
  test_v2_stt_create_body_echoes_recording_id                   PASSED
  test_v2_stt_create_path_echoes_interaction_id                 PASSED
  test_v2_stt_create_optional_fields_accepted                   PASSED
  test_v2_stt_create_async_flag_accepted                        PASSED
  test_v2_stt_create_reference_round_trip                       PASSED
  test_v2_stt_create_request_reference_round_trip               PASSED
11 passed in 1.17s

tests/test_api/ (full regression):
145 passed in 220.26s (3:40)
- All prior cycles (134) ✓
- Phase 1.3 cycle 8 STT Create (11) ✓

frontend tsc --noEmit: exit 0
```

## 回环一致性测试 strategy

Cycle 6/7 walker (with `$ref + parent-level metadata` fix) reused
verbatim. Cycle 8's response envelope is identical to cycle-7's
`TranscriptsResponse`, so no walker changes needed.

3 new test categories introduced for cycle 8:
1. **Required-field validation** (Pydantic 422 contract): missing
   `recordingId` or `primaryLanguage` → 4xx.
2. **Body-echo invariant**: `response.recordingId == body.recordingId`.
3. **Optional-fields acceptance**: full-body variant with all 9 optional
   knobs (spokenPunctuation, automaticPunctuation, isMultichannel,
   diarize, participants[], replacements[], keyterms, async) validates
   against spec's TranscriptsResponse schema.

Reference round-trips for **both** request and response schemas
(separately validated against their own OpenAPI definitions).

Cycle 8 is the first STT mutation endpoint — but no walker changes
were needed since response shape is unchanged from cycle 7.