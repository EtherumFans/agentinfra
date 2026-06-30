# Phase 1.3 Cycle 17 — Facts update-facts (batch) align Corti §13.5

## Context

Phase 1.3 cycle 16 (`123f3e7`) shipped `PATCH /interactions/{id}/facts/{factId}`
(update-fact single). Cycle 17 adds the **fifth endpoint of the §13.5
Facts family** — `PATCH /interactions/{id}/facts/` (update-facts batch).

**Notable differences from update-fact (cycle 16):**
- Path is **trailing-slash collection** `/interactions/{id}/facts/`
  (vs single-resource PATCH `/interactions/{id}/facts/{factId}`).
- Request wraps in `{facts: [...]}` (vs bare object for single).
- **NO `source` field in batch request** (per spec — only factId, text,
  group, isDiscarded are updateable via batch). The single update-fact
  (cycle 16) does support source updates.

## Spec source

`docs/corti-reverse-engineered/facts-update-facts.md` (7,424 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/facts/update-facts.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_17_facts_update_facts_batch/corti-facts-update-facts.md`.

## Endpoint surface

```
PATCH /api/v2/tools/interactions/{interaction_id}/facts/
Authorization: Bearer <jwt or oauth>
Content-Type: application/json

Body: {facts: [{factId, text?, group?, isDiscarded?}, ...]}

→ 200 OK   {facts: [{id, text, group, groupId, source, isDiscarded, createdAt, updatedAt}, ...]}
→ 504      RFC9457 ErrorResponse
→ 503      service_unavailable (hospital-pilot gate)
```

Note: spec only lists **200 + 504** (same as update-fact cycle 16).
All 8 response fields per item are required.

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_facts.py` | MODIFIED | Added `FactsBatchUpdateInput`, `FactsBatchUpdateRequest`, `FactsBatchUpdateItem`, `FactsBatchUpdateResponse` |
| `backend/app/api/v2_tools_facts.py` | MODIFIED | Added `patch_v2_tools_interaction_facts_batch` (200, no DB) |
| `backend/tests/test_api/test_v2_facts_update_facts_batch_consistency.py` | NEW | 12 回环一致性测试 |
| `docs/corti-reverse-engineered/facts-update-facts.md` | NEW | spec cache (7,424B) |
| `docs/phase_cycles/cycle_17_facts_update_facts_batch/corti-facts-update-facts.md` | NEW | archive |

## Stub data

Stub does NOT persist (no DB). For each input fact in `body.facts[]`:
- `id` = input `factId` (path-echo)
- `groupId` = `f"{interaction_id}-grp-{short_tag}"` (echo + deterministic)
- `text` = input.text or `"(unchanged)"` if omitted
- `group` = input.group or `"other"` if omitted
- `source` = always `"user"` (not in request per spec)
- `isDiscarded` = input.isDiscarded or `False` if omitted
- `createdAt` = `"2026-07-01T12:00:00Z"` (deterministic)
- `updatedAt` = `"2026-07-01T12:00:01Z"` (1s after createdAt, deterministic)

## 回环一致性测试 pattern (no walker — flat envelope)

12 tests cover:
- Spec sanity (200 + 504, `FactsBatchUpdateResponse` ref)
- Spec invariant: NO `source` field in `FactsBatchUpdateInput` (distinct from cycle 16)
- Minimal request (1 fact with factId) → 200 + echo
- Path-echo: `id` == input `factId`
- Path-echo: `groupId` carries `interaction_id` prefix
- PATCH semantics: omitted fields use stub defaults
- All 3 batch-updateable fields updated (text, group, isDiscarded)
- `isDiscarded=True` honored
- Multiple facts (preserved order, path-echo per fact)
- Empty `facts: []` accepted (not 400)
- Trailing-slash optional
- Timestamps: `updatedAt > createdAt`

## Hospital-pilot gate

Same 503 gate as cycles 1-17.

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

tests/test_api/ (full regression): 230 expected (218 + 12)
- All prior cycles (218) ✓
- Phase 1.3 cycle 17 Facts update-facts batch (12) ✓

frontend tsc --noEmit: exit 0
```

## Design decisions

1. **NO `source` field in request** (per spec). Spec is strict about
   this — single-resource update-fact (cycle 16) supports source
   updates, batch does not. iCoDer honors spec exactly.
2. **`source` always in response** with default `"user"`. Since
   `source` is not in the request, the stub uses a deterministic
   default. When source is in a real DB, the response would reflect
   the actual stored value.
3. **All 8 response fields per item REQUIRED** (per spec, same as
   cycle 16).
4. **No 404 sentinel** — spec only lists 200 + 504.
5. **Empty `facts: []` accepted** (spec does not require non-empty).
6. **No walker** — flat envelope, direct JSON key inspection.

## Out of scope (explicit, future cycles)

- ❌ Real fact persistence (no DB / no update stored)
- ❌ 1 more §13.5 endpoint to follow (likely the 6th endpoint — could
  be a future spec or `extract-facts` re-spec)
- ❌ Frontend fact batch update UI — out of scope: Phase 1.3 = backend
  wire parity only
- ❌ Other Corti §13 families (Codes, Languages) — separate phases

## Risk register

| Risk | Mitigation |
|---|---|
| `source` always defaults to "user" (not in request) | Documented; real persistence would expose actual stored source |
| `updatedAt - createdAt = 1s` is hardcoded | Documented; real timestamps require DB |

## Auto-advance: Phase 1.3 Facts family 5/6 done

Cycle 17 is **5 of 6** §13.5 endpoints. 1 more to align.

**Phase 1.3 Facts parity: 5/6 endpoints (83%).** Next cycle 18 = last
§13.5 endpoint (likely extract-facts re-spec or another).

## Phase 1.3 cumulative metrics (after cycle 17)

- **Cycles so far**: 6-12.2 (STT done), 13, 14, 15, 16, 17 (Facts 5/6)
- **Test count growth**: 126 (pre-STT) → 230 (post-cycle-17) = **+104 tests**
- **Commits**: `729a2e6` → ... → `123f3e7` (cycle 16) → (cycle 17 incoming)
- **Spec docs archived**: 14 (`docs/corti-reverse-engineered/stt-*.md` × 9 + `facts-*.md` × 5)
