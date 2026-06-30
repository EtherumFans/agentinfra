# Cycle 9 — Recordings (STT) LIST — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 7/7 回环一致性测试 + 152/152 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/recordings/list-recordings.md`
(4,897 bytes) → `docs/corti-reverse-engineered/stt-list-recordings.md`
→ archive `docs/phase_cycles/cycle_9_stt_list_recordings/corti-stt-list-recordings.md`.

Path: `GET /interactions/{id}/recordings/` → operationId
`recordings_list`. Response `RecordingsListResponse {recordings: UUID[]}`.

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | MODIFIED | +15 (RecordingsListResponse) |
| `backend/app/api/v2_tools_stt.py` | MODIFIED | +85 (GET endpoint + stub) |
| `backend/tests/test_api/test_v2_stt_list_recordings_consistency.py` | NEW | 245 |
| `docs/PHASE_1_3_CYCLE9_STT_LIST_RECORDINGS.md` | NEW | 145 |
| `docs/phase_cycles/cycle_9_stt_list_recordings/corti-stt-list-recordings.md` | archive | 4,897B |

## Test results

```
tests/test_api/test_v2_stt_list_recordings_consistency.py:
  test_stt_recordings_list_spec_is_real_and_cached                              PASSED
  test_stt_recordings_list_response_required_field                              PASSED
  test_v2_stt_recordings_list_default_shape_matches_corti_spec                  PASSED
  test_v2_stt_recordings_list_empty_sentinel                                    PASSED
  test_v2_stt_recordings_list_path_echoes_interaction_id                        PASSED
  test_v2_stt_recordings_list_different_interactions_different_recordings       PASSED
  test_v2_stt_recordings_list_reference_round_trip                              PASSED
7 passed in 1.23s

tests/test_api/ (full regression):
152 passed in 219.28s (3:39)
- All prior cycles (145) ✓
- Phase 1.3 cycle 9 Recordings LIST (7) ✓

frontend tsc --noEmit: exit 0
```

## 回环一致性测试 strategy

Cycle 6/7/8 walker (with `$ref + parent-level metadata` fix) reused
verbatim. Cycle 9 response envelope is trivial (`{recordings: [uuid]}`)
— no walker changes needed.

Notable: cycle 9's `empty-{uuid}` sentinel returns `{recordings: []}`
(empty array, NOT null). This exercises the **non-nullable** contract
the spec mandates (unlike cycle-6 transcripts list where the same
sentinel returned `null` because transcripts envelope WAS nullable).
The walker correctly accepts both: empty array (passes) AND would
reject null (per spec).

First endpoint of the **recordings family** (cycle 9 = recording #1 of 4).
4 recordings endpoints remain: upload-recording (POST, multipart),
get-recording, delete-recording.