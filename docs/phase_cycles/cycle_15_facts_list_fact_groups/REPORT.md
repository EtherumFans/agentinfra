# Cycle 15 — Facts list-fact-groups — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 10/10 回环一致性测试 + 208/208 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/facts/list-fact-groups.md`
(4,552 bytes) → `docs/corti-reverse-engineered/facts-list-fact-groups.md`
→ archive `docs/phase_cycles/cycle_15_facts_list_fact_groups/corti-facts-list-fact-groups.md`.

Path: `GET /factgroups/` (NOT path-scoped to interaction) → operationId
`facts_fact_groups_list`. Response: **200 OK** with `{data: [...]}`.
Errors: only **500** per spec (different from list-facts/add-facts 504).

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_facts.py` | MODIFIED | +71 (FactsFactGroupsItemTranslation + FactsFactGroupsItem + FactsFactGroupsListResponse) |
| `backend/app/api/v2_tools_facts.py` | MODIFIED | +91 (list-fact-groups endpoint + _stub_fact_groups) |
| `backend/tests/test_api/test_v2_facts_list_fact_groups_consistency.py` | NEW | 226 |
| `docs/corti-reverse-engineered/facts-list-fact-groups.md` | NEW | 4,552B |
| `docs/PHASE_1_3_CYCLE15_FACTS_LIST_FACT_GROUPS.md` | NEW | 195 |
| `docs/phase_cycles/cycle_15_facts_list_fact_groups/corti-facts-list-fact-groups.md` | archive | 4,552B |

## Test results

```
tests/test_api/test_v2_facts_list_fact_groups_consistency.py:
  test_facts_fact_groups_spec_is_real_and_cached                  PASSED
  test_v2_facts_fact_groups_global_path                          PASSED
  test_v2_facts_fact_groups_envelope_shape                       PASSED
  test_v2_facts_fact_groups_keys_match_canonical                 PASSED
  test_v2_facts_fact_groups_uuids_stable                         PASSED
  test_v2_facts_fact_groups_uuids_are_valid                      PASSED
  test_v2_facts_fact_groups_uuids_unique                         PASSED
  test_v2_facts_fact_groups_translation_default                  PASSED
  test_v2_facts_fact_groups_trailing_slash_optional              PASSED
  test_v2_facts_fact_groups_canonical_sample                     PASSED
10 passed in 1.24s

tests/test_api/ (full regression):
208 passed in ~3:50
- All prior cycles (198) ✓
- Phase 1.3 cycle 15 Facts list-fact-groups (10) ✓

frontend tsc --noEmit: exit 0
```

## Phase 1.3 Facts parity — status (3/6)

| Cycle | Method | Path | Status code |
|---|---|---|---|
| 13 | GET | /interactions/{id}/facts/ | 200 (LIST) |
| 14 | POST | /interactions/{id}/facts/ | 200 (ADD) |
| **15** | GET | /factgroups/ | 200 (LIST-FACT-GROUPS) ← this cycle |
| (next) | PATCH | /interactions/{id}/facts/{factId} | TBD (update-fact) |
| (next) | PATCH | /interactions/{id}/facts/ | TBD (update-facts) |
| (next) | TBD | TBD | TBD (TBD) |

## 回环一致性测试 strategy

**Walker not used** — flat envelope with simple list response. Tests
focus on:
- Spec sanity (200 + 500, `FactsFactGroupsListResponse` ref)
- GLOBAL path (not interaction-scoped)
- Envelope shape (data[] items + translations[])
- Keys match `CORTI_FACT_GROUPS` canonical set
- UUIDs stable + valid + unique (uuid5 deterministic)
- Default translation: 1 en-US row per group
- Trailing-slash optional
- Canonical sample (demographics, vital-signs, plan all present)

10 tests cover all invariants.
