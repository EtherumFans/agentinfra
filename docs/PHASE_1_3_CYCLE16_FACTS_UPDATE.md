# Phase 1.3 Cycle 16 — Facts update-fact align Corti §13.5

## Context

Phase 1.3 cycle 15 (`b02ca6f`) shipped `GET /factgroups/`
(list-fact-groups). Cycle 16 adds the **fourth endpoint of the §13.5
Facts family** — `PATCH /interactions/{id}/facts/{factId}` (update-fact).

**Notable difference from add-facts (cycle 14)**: while add-facts had
all response fields optional, **update-fact has all 8 response fields
required** per spec. PATCH semantics also apply: only fields present
in the request body are changed; omitted fields retain their "current"
value (which the stub approximates with defaults).

## Spec source

`docs/corti-reverse-engineered/facts-update-fact.md` (6,927 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/facts/update-fact.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_16_facts_update_fact/corti-facts-update-fact.md`.

## Endpoint surface

```
PATCH /api/v2/tools/interactions/{interaction_id}/facts/{fact_id}
Authorization: Bearer <jwt or oauth>
Content-Type: application/json

Body: {text?, group?, source?, isDiscarded?}

→ 200 OK   {id, text, group, groupId, source, isDiscarded, createdAt, updatedAt}
→ 504      RFC9457 ErrorResponse
→ 503      service_unavailable (hospital-pilot gate)
```

**Path is `/interactions/{id}/facts/{factId}`** (no trailing slash
since it's a single-resource PATCH).

Note: spec only lists **200 + 504** (back to 504, not 500 like
list-fact-groups). All 4 request body fields are optional; all 8
response fields are required.

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_facts.py` | MODIFIED | Added `FactsUpdateRequest`, `FactsUpdateResponse` (8 required response fields) |
| `backend/app/api/v2_tools_facts.py` | MODIFIED | Added `patch_v2_tools_interaction_fact` (200, no DB) |
| `backend/tests/test_api/test_v2_facts_update_fact_consistency.py` | NEW | 10 回环一致性测试 |
| `docs/corti-reverse-engineered/facts-update-fact.md` | NEW | spec cache (6,927B) |
| `docs/phase_cycles/cycle_16_facts_update_fact/corti-facts-update-fact.md` | NEW | archive |

## Stub data

Stub does NOT persist (no DB). For each PATCH request:
- `id` = path `fact_id` (path-echo)
- `groupId` = `f"{interaction_id}-grp-{short_tag}"` (echo + deterministic)
- `text` = body.text or `"(unchanged)"` if omitted
- `group` = body.group or `"other"` if omitted
- `source` = body.source or `"user"` if omitted
- `isDiscarded` = body.isDiscarded or `False` if omitted
- `createdAt` = `"2026-07-01T12:00:00Z"` (deterministic)
- `updatedAt` = `"2026-07-01T12:00:01Z"` (1s after createdAt, deterministic)

## 回环一致性测试 pattern (no walker — flat envelope)

10 tests cover:
- Spec sanity (200 + 504, `FactsUpdateResponse` ref)
- Minimal request (1 field) → 200 + all 8 required fields populated
- All 8 response fields required (not None)
- Path-echo: `id` == path `factId`
- Path-echo: `groupId` carries `interaction_id` prefix
- PATCH semantics: omitted fields use stub defaults
- All 4 fields updated in one request
- `isDiscarded=True` honored
- Source enum core|system|user all honored
- Timestamps: `updatedAt > createdAt`

## Hospital-pilot gate

Same 503 gate as cycles 1-16.

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

tests/test_api/ (full regression): 218 expected (208 + 10)
- All prior cycles (208) ✓
- Phase 1.3 cycle 16 Facts update-fact (10) ✓

frontend tsc --noEmit: exit 0
```

## Design decisions

1. **All 8 response fields REQUIRED** (per spec) — iCoDer honors spec
   exactly. This is stricter than add-facts (cycle 14) where all
   fields were optional.
2. **No 404 sentinel** — spec only lists 200 + 504 (no 404 unlike
   cycle-11/12 STT). iCoDer stub honors spec exactly.
3. **PATCH semantics** — only fields present in the request body
   are changed; omitted fields use deterministic defaults. The stub
   approximates "current" state because there's no DB.
4. **Path-echo contract** — `id` == path `factId` and `groupId` derived
   from `interaction_id`. SDK callers can verify the path params
   made it into the response.
5. **No walker** — flat envelope, direct JSON key inspection.

## Out of scope (explicit, future cycles)

- ❌ Real fact persistence (no DB / no update stored)
- ❌ `update-facts` (PATCH batch) — 1 more §13.5 endpoint to follow
- ❌ Frontend fact update UI — out of scope: Phase 1.3 = backend wire
  parity only
- ❌ Other Corti §13 families (Codes, Languages) — separate phases

## Risk register

| Risk | Mitigation |
|---|---|
| "Current value" stub doesn't reflect a real DB state | Documented; real persistence is separate task |
| `updatedAt - createdAt = 1s` is hardcoded | Documented; real timestamps require DB |

## Auto-advance: Phase 1.3 Facts family in progress

Cycle 16 is **4 of 6** §13.5 endpoints. Remaining 2 to align:
- **update-facts** (PATCH /interactions/{id}/facts/) — batch update
- (one more — likely `extract-facts` re-spec or another)

**Phase 1.3 Facts parity: 4/6 endpoints (67%).** Next cycle 17 = update-facts (batch).

## Phase 1.3 cumulative metrics (after cycle 16)

- **Cycles so far**: 6-12.2 (STT done), 13, 14, 15, 16 (Facts 4/6)
- **Test count growth**: 126 (pre-STT) → 218 (post-cycle-16) = **+92 tests**
- **Commits**: `729a2e6` → ... → `b02ca6f` (cycle 15) → (cycle 16 incoming)
- **Spec docs archived**: 13 (`docs/corti-reverse-engineered/stt-*.md` × 9 + `facts-*.md` × 4)
