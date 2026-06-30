# Cycle 13 — Facts list-facts — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 7/7 回环一致性测试 + 189/189 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/facts/list-facts.md`
(6,314 bytes) → `docs/corti-reverse-engineered/facts-list-facts.md`
→ archive `docs/phase_cycles/cycle_13_facts_list_facts/corti-facts-list-facts.md`.

Path: `GET /interactions/{id}/facts/` → operationId `facts_list`.
Response: **200 OK** with `{facts: [...]}`. Errors: only **504** per spec.

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_facts.py` | MODIFIED | +93 (FactsEvidence + FactsListItem + FactsListResponse) |
| `backend/app/api/v2_tools_facts.py` | MODIFIED | +98 (list-facts endpoint + _stub_facts_for_interaction) |
| `backend/tests/test_api/test_v2_facts_list_facts_consistency.py` | NEW | 196 |
| `docs/corti-reverse-engineered/facts-list-facts.md` | NEW | 6,314B |
| `docs/PHASE_1_3_CYCLE13_FACTS_LIST.md` | NEW | 178 |
| `docs/phase_cycles/cycle_13_facts_list_facts/corti-facts-list-facts.md` | archive | 6,314B |

## Test results

```
tests/test_api/test_v2_facts_list_facts_consistency.py:
  test_facts_list_spec_is_real_and_cached                       PASSED
  test_v2_facts_list_default_returns_2                          PASSED
  test_v2_facts_list_item_shape                                 PASSED
  test_v2_facts_list_path_echo                                  PASSED
  test_v2_facts_list_source_enum                                PASSED
  test_v2_facts_list_empty_envelope                             PASSED
  test_v2_facts_list_trailing_slash_optional                    PASSED
7 passed in 1.25s

tests/test_api/ (full regression):
189 passed in 222.45s (3:42)
- All prior cycles (182) ✓
- Phase 1.3 cycle 13 Facts list-facts (7) ✓

frontend tsc --noEmit: exit 0
```

## Phase 1.3 Facts parity — status (1/6)

| Cycle | Method | Path | Status code |
|---|---|---|---|
| **13** | GET | /interactions/{id}/facts/ | 200 (LIST) ← this cycle |
| (next) | POST | /interactions/{id}/facts/ | TBD (add-facts) |
| (next) | GET | /interactions/{id}/fact-groups/ | TBD (list-fact-groups) |
| (next) | PATCH | /interactions/{id}/facts/{factId} | TBD (update-fact) |
| (next) | PATCH | /interactions/{id}/facts/ | TBD (update-facts) |
| (next) | TBD | TBD | TBD (TBD) |

## 回环一致性测试 strategy

**Walker not used** — list endpoint with flat envelope. Tests focus on:
- Spec sanity (200 + 504, `FactsListResponse` ref)
- Default returns 2 facts
- Item shape (`id/text/group/groupId/isDiscarded/source/createdAt/updatedAt/evidence`)
- Path-echo contract (id/groupId/reference all carry interaction_id)
- Source enum (exercises `core + system` per spec enum)
- Empty envelope (empty-{uuid} → `facts: []`)
- Trailing-slash optional (FastAPI dual registration)

7 tests cover all invariants.
