# Cycle 14 — Facts add-facts — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 9/9 回环一致性测试 + 198/198 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/facts/add-facts.md`
(7,143 bytes) → `docs/corti-reverse-engineered/facts-add-facts.md`
→ archive `docs/phase_cycles/cycle_14_facts_add_facts/corti-facts-add-facts.md`.

Path: `POST /interactions/{id}/facts/` → operationId `facts_create`.
Response: **200 OK** with `{facts: [...]}`. Errors: only **504** per spec.

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_facts.py` | MODIFIED | +103 (FactsCreateInput + FactsCreateRequest + FactsCreateItem + FactsCreateResponse) |
| `backend/app/api/v2_tools_facts.py` | MODIFIED | +99 (add-facts endpoint + _stub_create_facts) |
| `backend/tests/test_api/test_v2_facts_add_facts_consistency.py` | NEW | 215 |
| `docs/corti-reverse-engineered/facts-add-facts.md` | NEW | 7,143B |
| `docs/PHASE_1_3_CYCLE14_FACTS_ADD.md` | NEW | 178 |
| `docs/phase_cycles/cycle_14_facts_add_facts/corti-facts-add-facts.md` | archive | 7,143B |

## Test results

```
tests/test_api/test_v2_facts_add_facts_consistency.py:
  test_facts_add_spec_is_real_and_cached                         PASSED
  test_v2_facts_add_minimal_request                              PASSED
  test_v2_facts_add_path_echo                                    PASSED
  test_v2_facts_add_source_optional_default_user                 PASSED
  test_v2_facts_add_source_enum_core_system_user                 PASSED
  test_v2_facts_add_is_discarded_default_false                   PASSED
  test_v2_facts_add_empty_facts_array                            PASSED
  test_v2_facts_add_trailing_slash_optional                      PASSED
  test_v2_facts_add_multiple_facts                               PASSED
9 passed in 1.23s

tests/test_api/ (full regression):
198 passed in (3:42)
- All prior cycles (189) ✓
- Phase 1.3 cycle 14 Facts add-facts (9) ✓

frontend tsc --noEmit: exit 0
```

## Phase 1.3 Facts parity — status (2/6)

| Cycle | Method | Path | Status code |
|---|---|---|---|
| 13 | GET | /interactions/{id}/facts/ | 200 (LIST) |
| **14** | POST | /interactions/{id}/facts/ | 200 (ADD) ← this cycle |
| (next) | GET | /interactions/{id}/fact-groups/ | TBD (list-fact-groups) |
| (next) | PATCH | /interactions/{id}/facts/{factId} | TBD (update-fact) |
| (next) | PATCH | /interactions/{id}/facts/ | TBD (update-facts) |
| (next) | TBD | TBD | TBD (TBD) |

## 回环一致性测试 strategy

**Walker not used** — flat envelope with simple create response. Tests
focus on:
- Spec sanity (200 + 504, `FactsCreateResponse` ref)
- Minimal request → 200 + echo
- Path-echo (id/groupId carry interaction_id)
- Source default "user" + enum core|system|user
- `isDiscarded` defaults to False
- Empty `facts: []` accepted (not 400)
- Trailing-slash optional
- Multiple facts (sequential ids, preserved order)

9 tests cover all invariants.
