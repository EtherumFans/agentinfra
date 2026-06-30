# Phase 1.3 Cycle 15 — Facts list-fact-groups align Corti §13.5

## Context

Phase 1.3 cycle 14 (`0d3d6a2`) shipped `POST /interactions/{id}/facts/`
(add-facts). Cycle 15 adds the **third endpoint of the §13.5 Facts
family** — `GET /factgroups/` (list-fact-groups).

**Notable difference**: this is a **GLOBAL endpoint, NOT path-scoped
to an interaction**. The path is `GET /factgroups/` (not
`/interactions/{id}/fact-groups/`). In iCoDer:
`GET /api/v2/tools/factgroups/`.

This is also the **first §13.5 endpoint with error code 500** (not 504
like list-facts/add-facts).

## Spec source

`docs/corti-reverse-engineered/facts-list-fact-groups.md` (4,552 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/facts/list-fact-groups.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_15_facts_list_fact_groups/corti-facts-list-fact-groups.md`.

## Endpoint surface

```
GET /api/v2/tools/factgroups/
Authorization: Bearer <jwt or oauth>

→ 200 OK   {data: [{id, key, translations: [{id, languages_id, name}]}, ...]}
→ 500      RFC9457 ErrorResponse
→ 503      service_unavailable (hospital-pilot gate)
```

**No interaction_id path param** — the catalog is global to the tenant.

Note: spec only lists **200 + 500** (no 504). First §13.5 endpoint with
500 instead of 504.

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_facts.py` | MODIFIED | Added `FactsFactGroupsItemTranslation`, `FactsFactGroupsItem`, `FactsFactGroupsListResponse` |
| `backend/app/api/v2_tools_facts.py` | MODIFIED | Added `get_v2_tools_fact_groups` (200, no DB) + `_stub_fact_groups` |
| `backend/tests/test_api/test_v2_facts_list_fact_groups_consistency.py` | NEW | 10 回环一致性测试 |
| `docs/corti-reverse-engineered/facts-list-fact-groups.md` | NEW | spec cache (4,552B) |
| `docs/phase_cycles/cycle_15_facts_list_fact_groups/corti-facts-list-fact-groups.md` | NEW | archive |

## Stub data

Stub does NOT hit a DB. Reuses the canonical `CORTI_FACT_GROUPS`
frozenset already defined in `app.schemas.v2_tools_facts` (17 kebab-case
keys: `demographics`, `chief-complaint`, `history-of-present-illness`,
`past-medical-history`, `medications-prior-to-visit`, `family-history`,
`allergies`, `social-history`, `vital-signs`, `abnormal-physical-findings`,
`imaging-results`, `lab-results`, `assessment`, `actions`,
`instructions`, `plan`, `follow-up`).

For each group:
- `id = uuid5(NAMESPACE, "icoder.factgroup." + key)` — stable across calls
- `key = the kebab-case string`
- `translations = [{id: 1, languages_id: "en-US", name: key}]`

`NAMESPACE = 5b3d4f7e-1c2a-4b8d-9e6f-0a1b2c3d4e5f` (fixed UUID, same
across all iCoDer deployments).

## 回环一致性测试 pattern (no walker — flat envelope)

10 tests cover:
- Spec sanity (200 + 500, `FactsFactGroupsListResponse` ref)
- GLOBAL path (not path-scoped to interaction_id)
- Envelope shape (data[] items have id/key/translations, translations have id/languages_id/name)
- Keys match canonical `CORTI_FACT_GROUPS` set
- UUIDs stable across calls (deterministic catalog)
- UUIDs are valid (parseable via `uuid.UUID`)
- UUIDs are unique
- Default translation: 1 en-US row per group
- Trailing-slash optional
- Canonical sample (demographics, vital-signs, plan all present)

## Hospital-pilot gate

Same 503 gate as cycles 1-15.

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

tests/test_api/ (full regression): 208 expected (198 + 10)
- All prior cycles (198) ✓
- Phase 1.3 cycle 15 Facts list-fact-groups (10) ✓

frontend tsc --noEmit: exit 0
```

## Design decisions

1. **GLOBAL endpoint** — path is `/api/v2/tools/factgroups/`, not
   `/api/v2/tools/interactions/{id}/fact-groups/`. Mirrors Corti
   exactly; the catalog is tenant-scoped, not interaction-scoped.
2. **Reuse `CORTI_FACT_GROUPS` frozenset** — same canonical 17 keys
   already used by Phase 1.2 cycle 1's `extract-facts` prompt. Single
   source of truth.
3. **uuid5 from fixed namespace** — every call returns the same
   UUIDs, so SDK callers can cache them across requests (and across
   iCoDer deployments, since the namespace is constant).
4. **Single en-US translation row per group** — minimal stub; future
   cycles can extend with zh-CN, etc., but spec doesn't require it.
5. **No walker** — flat envelope, direct JSON key inspection.

## Out of scope (explicit, future cycles)

- ❌ Real fact-group catalog (no DB / no admin UI to add custom groups)
- ❌ `update-fact` (PATCH), `update-facts` (PATCH) — 2 more §13.5
  endpoints to follow
- ❌ Frontend fact-groups UI — out of scope: Phase 1.3 = backend wire
  parity only
- ❌ Other Corti §13 families (Codes, Languages) — separate phases

## Risk register

| Risk | Mitigation |
|---|---|
| `CORTI_FACT_GROUPS` frozenset drift between cycle 1 and cycle 15 | Single source of truth in `app.schemas.v2_tools_facts`; import same constant |
| UUID5 namespace constant could clash if it matches a real UUID | 5b3d4f7e-1c2a-4b8d-9e6f-0a1b2c3d4e5f is a fabricated UUID; no real-world collision expected |
| 500 vs 504 (spec inconsistency) | Documented; iCoDer honors spec exactly (500 not 504) |

## Auto-advance: Phase 1.3 Facts family in progress

Cycle 15 is **3 of 6** §13.5 endpoints. Remaining 3 to align:
- **update-fact** (PATCH /interactions/{id}/facts/{factId}) — update single
- **update-facts** (PATCH /interactions/{id}/facts/) — batch update
- (one more — likely `extract-facts` re-spec or another)

**Phase 1.3 Facts parity: 3/6 endpoints (50%).** Next cycle 16 = update-fact.

## Phase 1.3 cumulative metrics (after cycle 15)

- **Cycles so far**: 6-12.2 (STT done), 13, 14, 15 (Facts 3/6)
- **Test count growth**: 126 (pre-STT) → 208 (post-cycle-15) = **+82 tests**
- **Commits**: `729a2e6` → ... → `0d3d6a2` (cycle 14, push pending) → (cycle 15 incoming)
- **Spec docs archived**: 12 (`docs/corti-reverse-engineered/stt-*.md` × 9 + `facts-*.md` × 3)
