# Cycle 6 — Transcripts (STT) LIST — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 8/8 回环一致性测试 + 126/126 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/transcripts/list-transcripts.md`
(7,962 bytes) → `docs/corti-reverse-engineered/stt-list-transcripts.md`
→ archive `docs/phase_cycles/cycle_6_stt_list_transcripts/corti-stt-list-transcripts.md`.

Path: `GET /interactions/{id}/transcripts/?full=bool` → operationId
`transcripts_list`. Response envelope `{transcripts: T[] | null}` —
`transcripts` field declared nullable.

## Files

| File | Lines | Status |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | 130 | NEW |
| `backend/app/api/v2_tools_stt.py` | 175 | NEW |
| `backend/tests/test_api/test_v2_stt_consistency.py` | 310 | NEW |
| `backend/app/main.py` | +2 | include + import |
| `docs/PHASE_1_3_CYCLE6_STT_LIST_TRANSCRIPTS.md` | 170 | NEW |
| `docs/phase_cycles/cycle_6_stt_list_transcripts/corti-stt-list-transcripts.md` | 7,962B | archive |

## Test results

```
tests/test_api/test_v2_stt_consistency.py:
  test_stt_spec_is_real_and_cached                            PASSED
  test_stt_envelope_field_is_nullable_in_spec                 PASSED
  test_v2_stt_list_shape_matches_corti_spec                   PASSED
  test_v2_stt_list_full_true_includes_transcript_data         PASSED
  test_v2_stt_list_full_false_omits_transcript                PASSED
  test_v2_stt_envelope_nullable_round_trip                    PASSED
  test_v2_stt_path_scoping                                    PASSED
  test_v2_stt_reference_round_trip                            PASSED
8 passed in <1s

tests/test_api/ (full regression):
126 passed in 225.55s (3:45)
- Phase 1.0 OAuth (14) ✓
- Phase 1.1 Medical Coding v2 (8) ✓
- Phase 1.2 cycles 1-5 (8+5+6+9+6 = 34) ✓
- Phase 1.3 cycle 6 STT LIST (8) ✓
- M3-0 legacy surfaces (62) ✓

frontend tsc --noEmit: exit 0, 0 errors
```

## 回环一致性测试 strategy + walker fix

**Walker bug discovered during cycle 6**: when an OpenAPI property has
both `$ref` and parent-level metadata (`type: object, nullable: true`),
the walker was resolving `$ref` and dropping the parent's `nullable`
declaration. The fix preserves parent overrides:

```python
if "$ref" in schema:
    parent_overrides = {k: v for k, v in schema.items() if k != "$ref"}
    resolved = _resolve_ref(spec, schema["$ref"])
    schema = {**resolved, **parent_overrides}  # parent wins
```

**The fix is generic** — it applies retroactively to cycles 3-5
without regression (their nullable declarations were on resolved
schemas, not on parent properties; only cycle 6 has a parent-level
nullable on a `$ref` property).

**Schema discovery during cycle 6**: `TranscriptsParticipant` actually
requires `channel` (int) + `role` (enum `doctor|patient|multiple`) per
the captured spec — NOT my initial `participant+role` shape. Fixed in
schema + stub data + reference round-trip.

## Push status

GitHub network remained unreachable from this host throughout cycles
4-6. All commits are local on master with full regression green.