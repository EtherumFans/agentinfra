# Cycle 16 — Facts update-fact — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 10/10 回环一致性测试 + 218/218 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/facts/update-fact.md`
(6,927 bytes) → `docs/corti-reverse-engineered/facts-update-fact.md`
→ archive `docs/phase_cycles/cycle_16_facts_update_fact/corti-facts-update-fact.md`.

Path: `PATCH /interactions/{id}/facts/{factId}` → operationId
`facts_update`. Response: **200 OK** with 8 required fields
(`id, text, group, groupId, source, isDiscarded, createdAt, updatedAt`).
Errors: only **504** per spec.

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_facts.py` | MODIFIED | +67 (FactsUpdateRequest + FactsUpdateResponse) |
| `backend/app/api/v2_tools_facts.py` | MODIFIED | +67 (update-fact endpoint) |
| `backend/tests/test_api/test_v2_facts_update_fact_consistency.py` | NEW | 234 |
| `docs/corti-reverse-engineered/facts-update-fact.md` | NEW | 6,927B |
| `docs/PHASE_1_3_CYCLE16_FACTS_UPDATE.md` | NEW | 192 |
| `docs/phase_cycles/cycle_16_facts_update_fact/corti-facts-update-fact.md` | archive | 6,927B |

## Test results

```
tests/test_api/test_v2_facts_update_fact_consistency.py:
  test_facts_update_spec_is_real_and_cached                      PASSED
  test_v2_facts_update_minimal_request                           PASSED
  test_v2_facts_update_response_all_fields_required              PASSED
  test_v2_facts_update_path_echo_id                              PASSED
  test_v2_facts_update_path_echo_group_id                        PASSED
  test_v2_facts_update_patch_semantics                           PASSED
  test_v2_facts_update_all_fields                                PASSED
  test_v2_facts_update_discard_flag                              PASSED
  test_v2_facts_update_source_enum                               PASSED
  test_v2_facts_update_timestamps                                PASSED
10 passed in 1.26s

tests/test_api/ (full regression):
218 passed in ~3:50
- All prior cycles (208) ✓
- Phase 1.3 cycle 16 Facts update-fact (10) ✓

frontend tsc --noEmit: exit 0
```

## Phase 1.3 Facts parity — status (4/6)

| Cycle | Method | Path | Status code |
|---|---|---|---|
| 13 | GET | /interactions/{id}/facts/ | 200 (LIST) |
| 14 | POST | /interactions/{id}/facts/ | 200 (ADD) |
| 15 | GET | /factgroups/ | 200 (LIST-FACT-GROUPS) |
| **16** | PATCH | /interactions/{id}/facts/{factId} | 200 (UPDATE) ← this cycle |
| (next) | PATCH | /interactions/{id}/facts/ | TBD (update-facts batch) |
| (next) | TBD | TBD | TBD (TBD) |

## 回环一致性测试 strategy

**Walker not used** — flat envelope with simple update response. Tests
focus on:
- Spec sanity (200 + 504, `FactsUpdateResponse` ref)
- Minimal request → 200 + all 8 required fields
- All 8 response fields REQUIRED (not None)
- Path-echo: `id` == path `factId`, `groupId` carries `interaction_id`
- PATCH semantics: omitted fields use stub defaults
- All 4 fields updated in one request
- `isDiscarded=True` honored
- Source enum core|system|user all honored
- Timestamps: `updatedAt > createdAt`

10 tests cover all invariants.
