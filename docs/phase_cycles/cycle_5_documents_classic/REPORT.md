# Cycle 5 — Documents Classic LIST (Planned deprecation) — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 6/6 回环一致性测试 + 118/118 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/documents-classic/list-documents.md`
(7,235 bytes) → `docs/corti-reverse-engineered/documents-classic-list.md`
→ archive `docs/phase_cycles/cycle_5_documents_classic/corti-documents-classic-list.md`.

Embedded OpenAPI 3.0.0 YAML contains 5 schemas (DocumentsListResponse,
DocumentsGetResponse, DocumentsSection, CommonUsageInfo, ErrorResponse),
1 path (`GET /interactions/{id}/documents/`). Cycle 5 closes only the
LIST endpoint; the other 4 (get, generate, update, delete) land in
follow-on cycles.

## Files

| File | Lines | Status |
|---|---|---|
| `backend/app/schemas/v2_tools_documents_classic.py` | 110 | NEW |
| `backend/app/api/v2_tools_documents_classic.py` | 175 | NEW |
| `backend/tests/test_api/test_v2_documents_classic_consistency.py` | 270 | NEW |
| `backend/app/main.py` | +2 | include + import |
| `docs/PHASE_1_2_CYCLE5_DOCUMENTS_CLASSIC_LIST.md` | 165 | NEW |
| `docs/phase_cycles/cycle_5_documents_classic/corti-documents-classic-list.md` | 7,235B | archive |

## Test results

```
tests/test_api/test_v2_documents_classic_consistency.py:
  test_documents_classic_spec_is_real_and_cached               PASSED
  test_v2_documents_classic_list_shape_matches_corti_spec      PASSED
  test_v2_documents_classic_envelope_has_data_field            PASSED
  test_v2_documents_classic_path_scoping                       PASSED
  test_v2_documents_classic_isStream_field_round_trip          PASSED
  test_v2_documents_classic_reference_round_trip               PASSED
6 passed in <1s

tests/test_api/ (full regression):
118 passed in 231.05s (3:51)
- Phase 1.0 OAuth (14) ✓
- Phase 1.1 Medical Coding v2 (8) ✓
- Phase 1.2 cycle 1 FactsR (8) ✓
- Phase 1.2 cycle 2 Streams (5) ✓
- Phase 1.2 cycle 3 Guided Doc (6) ✓
- Phase 1.2 cycle 4 Sections + Templates LIST (9) ✓
- Phase 1.2 cycle 5 Documents Classic LIST (6) ✓
- M3-0 legacy surfaces (62) ✓

frontend tsc --noEmit: exit 0, 0 errors
```

## 回环一致性测试 strategy

Same walker as cycles 3-4. Cycle 5 added one **new path-scoping
invariant** (`test_v2_documents_classic_path_scoping`): different
interaction UUIDs must yield different document IDs because the stub
data echoes the UUID into the document id. This validates that the
path param is actually being read — a contract that's invisible to a
shape-only check.

`isStream` field is exercised with both `true` and `false` values in
the stub data so the walker validates the boolean type across both
branches.

## Phase 1.2 wrap-up

Phase 1.2 = 5 cycles all GREEN. Phase 1.3 (STT alignment, Corti §13.3)
is the next big family. Per the parity queue:

- Cycle 6 = list-transcripts (REST)
- Cycle 7 = get-transcript (REST)
- Cycle 8 = list-recordings (REST)
- Future = STT WSS audio-bridge (if needed)

## Push status

Note: GitHub was unreachable from the network for the cycle-4 push
(`5dfd1aa`). Cycle-5 commit will be pushed when connectivity
returns. Both commits are local on master and verified by local
regression (118/118 PASS).