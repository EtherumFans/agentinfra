# Cycle 17 — Facts update-facts (batch) — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 12/12 回环一致性测试 + 230/230 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/facts/update-facts.md`
(7,424 bytes) → `docs/corti-reverse-engineered/facts-update-facts.md`
→ archive `docs/phase_cycles/cycle_17_facts_update_facts_batch/corti-facts-update-facts.md`.

Path: `PATCH /interactions/{id}/facts/` → operationId
`facts_batch_update`. Response: **200 OK** with 8 required fields per
item. Errors: only **504** per spec.

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_facts.py` | MODIFIED | +89 (FactsBatchUpdateInput + FactsBatchUpdateRequest + FactsBatchUpdateItem + FactsBatchUpdateResponse) |
| `backend/app/api/v2_tools_facts.py` | MODIFIED | +71 (update-facts batch endpoint) |
| `backend/tests/test_api/test_v2_facts_update_facts_batch_consistency.py` | NEW | 273 |
| `docs/corti-reverse-engineered/facts-update-facts.md` | NEW | 7,424B |
| `docs/PHASE_1_3_CYCLE17_FACTS_UPDATE_BATCH.md` | NEW | 192 |
| `docs/phase_cycles/cycle_17_facts_update_facts_batch/corti-facts-update-facts.md` | archive | 7,424B |

## Test results

```
tests/test_api/test_v2_facts_update_facts_batch_consistency.py:
  test_facts_batch_update_spec_is_real_and_cached                  PASSED
  test_facts_batch_update_input_no_source_field                    PASSED
  test_v2_facts_batch_update_minimal_request                       PASSED
  test_v2_facts_batch_update_path_echo_id                          PASSED
  test_v2_facts_batch_update_path_echo_group_id                    PASSED
  test_v2_facts_batch_update_patch_semantics                       PASSED
  test_v2_facts_batch_update_all_fields                            PASSED
  test_v2_facts_batch_update_discard_flag                          PASSED
  test_v2_facts_batch_update_multiple_facts                        PASSED
  test_v2_facts_batch_update_empty_facts                           PASSED
  test_v2_facts_batch_update_trailing_slash_optional               PASSED
  test_v2_facts_batch_update_timestamps                            PASSED
12 passed in 1.19s

tests/test_api/ (full regression):
230 passed in ~4:00
- All prior cycles (218) ✓
- Phase 1.3 cycle 17 Facts update-facts batch (12) ✓

frontend tsc --noEmit: exit 0
```

## Phase 1.3 Facts parity — status (5/6)

| Cycle | Method | Path | Status code |
|---|---|---|---|
| 13 | GET | /interactions/{id}/facts/ | 200 (LIST) |
| 14 | POST | /interactions/{id}/facts/ | 200 (ADD) |
| 15 | GET | /factgroups/ | 200 (LIST-FACT-GROUPS) |
| 16 | PATCH | /interactions/{id}/facts/{factId} | 200 (UPDATE) |
| **17** | PATCH | /interactions/{id}/facts/ | 200 (BATCH UPDATE) ← this cycle |
| (next) | TBD | TBD | TBD (TBD) |

## 回环一致性测试 strategy

**Walker not used** — flat envelope with simple batch update response.
Tests focus on:
- Spec sanity (200 + 504, `FactsBatchUpdateResponse` ref)
- **Spec invariant**: NO `source` field in `FactsBatchUpdateInput`
- Minimal request (1 fact with factId) → 200 + echo
- Path-echo: `id` == input `factId`, `groupId` carries `interaction_id`
- PATCH semantics: omitted fields use stub defaults
- All 3 batch-updateable fields updated (text, group, isDiscarded)
- `isDiscarded=True` honored
- Multiple facts (preserved order, path-echo per fact)
- Empty `facts: []` accepted (not 400)
- Trailing-slash optional
- Timestamps: `updatedAt > createdAt`

12 tests cover all invariants.
