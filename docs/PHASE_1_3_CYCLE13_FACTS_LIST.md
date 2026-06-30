# Phase 1.3 Cycle 13 — Facts list-facts align Corti §13.5

## Context

Phase 1.3 STT family (cycles 6-12.2) is **COMPLETE** (9 of 9 endpoints).
Per the cycle 12.2 spec doc's "Auto-advance" section, the next family
is **Facts (Corti §13.5)**. Cycle 13 is the **first endpoint** of that
family — `GET /interactions/{id}/facts/` (operationId `facts_list`).

This is **distinct** from Phase 1.2 cycle 1's `extract-facts` (§3.2/§13.4
Text Generation family). `extract-facts` is an LLM call that *creates*
facts from text; `list-facts` is a CRUD-style read of stored facts.

## Spec source

`docs/corti-reverse-engineered/facts-list-facts.md` (6,314 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/facts/list-facts.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_13_facts_list_facts/corti-facts-list-facts.md`.

## Endpoint surface

```
GET /api/v2/tools/interactions/{interaction_id}/facts/
Authorization: Bearer <jwt or oauth>

→ 200 OK   {facts: [...]}   FactsListResponse
→ 504      RFC9457 ErrorResponse
→ 503      service_unavailable (hospital-pilot gate)
```

Note: spec only lists **200 + 504** (interesting — no 400/401/403/500).
iCoDer stub honors spec exactly — no extra sentinels for cycle 13.

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_facts.py` | MODIFIED | Added `FactsEvidence`, `FactsListItem`, `FactsListResponse` |
| `backend/app/api/v2_tools_facts.py` | MODIFIED | Added `get_v2_tools_interaction_facts` (200, no LLM) |
| `backend/tests/test_api/test_v2_facts_list_facts_consistency.py` | NEW | 7 回环一致性测试 |
| `docs/corti-reverse-engineered/facts-list-facts.md` | NEW | spec cache (6,314B) |
| `docs/phase_cycles/cycle_13_facts_list_facts/corti-facts-list-facts.md` | NEW | archive |

## Stub data

Stub does NOT hit a DB (no DB).

| interaction_id prefix | Result |
|---|---|
| `empty-{uuid}` | `facts: []` envelope (exercises empty path) |
| anything else | 2 facts: one `source=core` (LLM), one `source=system` (e.g. EHR), each with 1 evidence row |

`facts[*].id` / `facts[*].groupId` / `facts[*].evidence[*].reference` all
echo the `interaction_id` (path-echo contract) so SDK callers can verify.

## 回环一致性测试 pattern (no walker — list endpoint, simple shape)

7 tests cover:
- Spec sanity (200 + 504, `FactsListResponse` ref)
- Default returns 2 facts
- Item shape (`id/text/group/groupId/isDiscarded/source/createdAt/updatedAt/evidence`)
- Path-echo contract (id/groupId/reference all carry interaction_id)
- Source enum (exercises `core + system` per spec enum)
- Empty envelope (empty-{uuid} → `facts: []`)
- Trailing-slash optional (FastAPI dual registration)

## Hospital-pilot gate

Same 503 gate as cycles 1-12.2.

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

## Design decisions

1. **Add to existing `v2_tools_facts.py`** rather than new file. The
   existing file already has `extract-facts` (Phase 1.2 cycle 1) — both
   facts-related endpoints now live in one router, following the STT
   pattern (`v2_tools_stt.py` holds both transcripts and recordings).
2. **No LLM call** — `list-facts` is a CRUD read, not an inference.
   Stub is deterministic and path-echo based.
3. **No walker** — list endpoint with a flat envelope is simple enough
   to assert via direct JSON key inspection (no `$ref` walk).
4. **Empty envelope preserved** — `empty-{uuid}` returns `{"facts": []}`
   (not `null`, not 404) so SDK callers can iterate a known shape.
5. **Path-echo contract** — `id` / `groupId` / `evidence.reference` all
   carry the `interaction_id` prefix. This is a new SDK-affordance: a
   caller can verify the path param made it into the response without
   a second lookup call.

## Out of scope (explicit, future cycles)

- ❌ Real facts storage (no DB / no persistence)
- ❌ `add-facts` (POST), `update-fact` (PATCH), `update-facts` (PATCH),
  `list-fact-groups` (GET) — 4 more §13.5 endpoints to follow in
  future cycles
- ❌ Frontend facts list UI — out of scope: Phase 1.3 = backend wire
  parity only
- ❌ Other Corti §13 families (Codes, Languages) — separate phases

## Risk register

| Risk | Mitigation |
|---|---|
| 503 gate may fire in dev if `ICODER_CREDENTIAL_LLM` unset | Tests set `ICODER_CREDENTIAL_LLM=test-fake-key-cycle13` |
| Path-echo on `evidence.reference` makes them non-URLs (no `/v2/...` prefix) | Documented; SDK callers can parse the suffix as UUID |

## Auto-advance: Phase 1.3 Facts family in progress

Cycle 13 is **1 of 6** §13.5 endpoints. Remaining 5 to align:
- **add-facts** (POST /interactions/{id}/facts/) — add user facts
- **list-fact-groups** (GET /interactions/{id}/fact-groups/) — list group metadata
- **update-fact** (PATCH /interactions/{id}/facts/{factId}) — update single
- **update-facts** (PATCH /interactions/{id}/facts/) — batch update

**Phase 1.3 Facts parity: 1/6 endpoints (17%).** Next cycle 14 = add-facts.

## Phase 1.3 cumulative metrics (after cycle 13)

- **Cycles so far**: 6, 7, 8, 9, 10, 11, 12, 12.1, 12.2 (STT done), 13 (Facts started)
- **Test count growth**: 126 (pre-STT) → 189 (post-cycle-13) = **+63 tests**
- **Commits**: `729a2e6` → `e594dee` → `d8f852f` → `5bbb4e6` → `44219ad` → `8a37918` → `7504164` → `8805ca9` → `379646b` (cycle 12.2 STT done) → (cycle 13 incoming)
- **Spec docs archived**: 10 (`docs/corti-reverse-engineered/stt-*.md` × 9 + `facts-list-facts.md` × 1)
