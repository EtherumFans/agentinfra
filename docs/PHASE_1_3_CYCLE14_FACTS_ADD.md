# Phase 1.3 Cycle 14 — Facts add-facts align Corti §13.5

## Context

Phase 1.3 cycle 13 (`f54a083`) shipped `GET /interactions/{id}/facts/`
(list-facts). Cycle 14 adds the **second endpoint of the §13.5 Facts
family** — `POST /interactions/{id}/facts/` (add-facts).

This is **distinct** from Phase 1.2 cycle 1's `extract-facts` (§3.2/§13.4
Text Generation family). `extract-facts` is an LLM call that *creates*
facts from text; `add-facts` is a CRUD-style create where the caller
supplies the fact text+group directly.

## Spec source

`docs/corti-reverse-engineered/facts-add-facts.md` (7,143 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/facts/add-facts.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_14_facts_add_facts/corti-facts-add-facts.md`.

## Endpoint surface

```
POST /api/v2/tools/interactions/{interaction_id}/facts/
Authorization: Bearer <jwt or oauth>
Content-Type: application/json

Body: {facts: [{text, group, source?}, ...]}

→ 200 OK   {facts: [{id, text, group, groupId, source, isDiscarded, updatedAt}, ...]}
→ 504      RFC9457 ErrorResponse
→ 503      service_unavailable (hospital-pilot gate)
```

Note: spec only lists **200 + 504** (same minimalism as list-facts, no
400/401/403/500). iCoDer stub honors spec exactly.

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_facts.py` | MODIFIED | Added `FactsCreateInput`, `FactsCreateRequest`, `FactsCreateItem`, `FactsCreateResponse` |
| `backend/app/api/v2_tools_facts.py` | MODIFIED | Added `post_v2_tools_interaction_facts` (200, no DB) + `_stub_create_facts` |
| `backend/tests/test_api/test_v2_facts_add_facts_consistency.py` | NEW | 9 回环一致性测试 |
| `docs/corti-reverse-engineered/facts-add-facts.md` | NEW | spec cache (7,143B) |
| `docs/phase_cycles/cycle_14_facts_add_facts/corti-facts-add-facts.md` | NEW | archive |

## Stub data

Stub does NOT persist (no DB).

For each input fact in `body.facts[]`:
- `id = f"{interaction_id}-fact-{short_tag}-{idx:02d}"` (echo + sequential)
- `groupId = f"{interaction_id}-grp-{short_tag}-{idx:02d}"` (echo)
- `text/group/source` → echoed from input (source defaults to "user" if omitted)
- `isDiscarded = False` (always)
- `updatedAt = "2026-07-01T12:00:00Z"` (deterministic)

## 回环一致性测试 pattern (no walker — flat envelope)

9 tests cover:
- Spec sanity (200 + 504, `FactsCreateResponse` ref)
- Minimal request (1 fact with text+group) → 200 + echo
- Path-echo contract (id/groupId carry interaction_id)
- Source optional default "user"
- Source enum core/system/user all honored
- `isDiscarded` defaults to False
- Empty `facts: []` array accepted (not 400)
- Trailing-slash optional
- Multiple facts (sequential ids, preserved order)

## Hospital-pilot gate

Same 503 gate as cycles 1-14.

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

tests/test_api/ (full regression): 198 expected (189 + 9)
- All prior cycles (189) ✓
- Phase 1.3 cycle 14 Facts add-facts (9) ✓

frontend tsc --noEmit: exit 0
```

## Design decisions

1. **Add to existing `v2_tools_facts.py`** (same file as extract-facts
   §13.4 and list-facts §13.5 from cycle 13). All facts-related
   endpoints now live in one router, following the STT pattern.
2. **No LLM call** — `add-facts` is a CRUD create where the caller
   already knows what they want. Stub is deterministic and path-echo
   based.
3. **Empty `facts: []` accepted** — spec does not require non-empty,
   so we accept empty and echo empty (200, not 400). This matches
   list-facts' `empty-{uuid}` → `[]` behavior.
4. **Source default "user"** — when caller omits `source`, the stub
   defaults to `"user"` (caller-created), not `"core"` (LLM-created)
   or `"system"` (EHR-derived). The "user" default reflects the most
   common use case (manual fact entry from a clinician UI).
5. **No walker** — flat envelope, direct JSON key inspection.

## Out of scope (explicit, future cycles)

- ❌ Real facts storage (no DB / no persistence)
- ❌ `list-fact-groups` (GET), `update-fact` (PATCH), `update-facts`
  (PATCH) — 3 more §13.5 endpoints to follow in future cycles
- ❌ Frontend facts CRUD UI — out of scope: Phase 1.3 = backend wire
  parity only
- ❌ Other Corti §13 families (Codes, Languages) — separate phases

## Risk register

| Risk | Mitigation |
|---|---|
| Stub `updatedAt` is fixed (not real timestamp) | Documented; real persistence is separate task |
| Source default "user" might surprise EHR-pipeline callers | Documented; callers should pass `source=system` explicitly when needed |

## Auto-advance: Phase 1.3 Facts family in progress

Cycle 14 is **2 of 6** §13.5 endpoints. Remaining 4 to align:
- **list-fact-groups** (GET /interactions/{id}/fact-groups/) — list group metadata
- **update-fact** (PATCH /interactions/{id}/facts/{factId}) — update single
- **update-facts** (PATCH /interactions/{id}/facts/) — batch update
- (one more — likely list-fact-groups or another)

**Phase 1.3 Facts parity: 2/6 endpoints (33%).** Next cycle 15 = list-fact-groups.

## Phase 1.3 cumulative metrics (after cycle 14)

- **Cycles so far**: 6-12.2 (STT done), 13, 14 (Facts 2/6)
- **Test count growth**: 126 (pre-STT) → 198 (post-cycle-14) = **+72 tests**
- **Commits**: `729a2e6` → ... → `f54a083` (cycle 13) → (cycle 14 incoming)
- **Spec docs archived**: 11 (`docs/corti-reverse-engineered/stt-*.md` × 9 + `facts-*.md` × 2)
