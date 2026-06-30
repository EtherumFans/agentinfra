# Phase 1.2 Cycle 4 — Guided Templates & Sections LIST (REST Beta)

## Context

Phase 1.2 cycle 3 (`2d33355`) shipped `POST /api/v2/tools/guided-documents/`
(templateRef + ephemeral). Cycle 4 closes the **discovery path** so a
Corti-SDK caller can find templates and sections to pass into that
generator endpoint.

Corti splits this into two URL families:

- `GET /documents/templates/` → list templates (Guided Templates)
- `GET /documents/sections/`  → list sections (Guided Sections)

There are 11 endpoints in each family (CRUD + versioning + publishing).
Phase 1.2 cycle 4 closes **only the LIST endpoint of each** for the
same one-cycle closure tractability reason as cycle 3 — full CRUD +
publish + version lands in a follow-on cycle once real storage is
designed.

## Spec sources

- `docs/corti-reverse-engineered/guided-templates-list.md` (23,529B,
  fetched 2026-07-01 from
  `https://docs.corti.ai/api-reference/guided-templates/list-templates.md`).
  Archive: `docs/phase_cycles/cycle_4_sections_templates/corti-templates-list.md`.
- `docs/corti-reverse-engineered/guided-sections-list.md` (18,630B,
  fetched 2026-07-01 from
  `https://docs.corti.ai/api-reference/guided-sections/list-sections.md`).
  Archive: `docs/phase_cycles/cycle_4_sections_templates/corti-sections-list.md`.

Both are real Corti OpenAPI 3.0.0 specs — never inferred.

## Endpoint surface

```
GET /api/v2/tools/templates/   (and /templates trailing-slash-less alias)
GET /api/v2/tools/sections/    (and /sections trailing-slash-less alias)

Authorization: Bearer <jwt or oauth>      (Phase 1.0 capability scope path)

Query params (all optional, repeatable):
  lang        BCP 47 tag       (e.g. en-US)
  region      ISO 3166-1 α-3  (e.g. USA)
  specialty   clinical specialty string
  label       key:value form (e.g. encounter_type:inpatient)
  published   true | false    (omit ⇒ both)
  source      user | corti    (omit ⇒ both; project not surfaced in Cycle 4)

→ 200 OK   Array<GuidedTemplate | GuidedSection>
→ 422      FastAPI: invalid enum value (e.g. source=invalid)
→ 503      service_unavailable (hospital-pilot gate)
```

## Files

| Path | Lines | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_sections_templates.py` | 165 | Pydantic for GuidedTemplate + GuidedSection + GuidedLabel |
| `backend/app/api/v2_tools_sections_templates.py` | 235 | LIST router with stub data + filter helpers |
| `backend/tests/test_api/test_v2_sections_templates_consistency.py` | 290 | 9 回环一致性测试 |
| `backend/app/main.py` | +2 | import + include router |

## Stub data

Cycle 4 returns 2 templates + 2 sections (one Corti-standard, one
user-created each) so SDK callers have something to discover. The
schema is wired for `publishedVersion` but the stub data doesn't
populate it (Cycle 4 is read-only discovery; publishing lands with
the CRUD cycle).

No DB writes, no LLM calls, no external storage. The router is
deterministic and tests can validate against the constant stub data.

## Filter semantics

- **Empty filter list** → return all entries (after soft-delete exclusion).
- **AND across categories, OR within a category**: a template is
  included only if every provided filter category matches; within a
  category (e.g. multiple `lang` values), any match counts.
- **Soft-deleted entries excluded**: `deletedAt` set ⇒ excluded.
  There is no `includeDeleted` query param in Cycle 4 (Corti spec
  uses GET-by-id for that).
- **`published=false`** → empty result (no unpublished stubs yet).
- **`source=user|corti`** → exact-match on the enum.

## Hospital-pilot gate

Same 503 gate as cycles 1-3:

```
ICODER_CREDENTIAL_LLM empty
  AND ICODER_ALLOW_DEGRADED_NO_KEY ≠ "1"
  → 503 service_unavailable
```

The gate is shared with cycles 1-3; tests set
`ICODER_ALLOW_DEGRADED_NO_KEY=1` to bypass.

## 回环一致性测试 pattern

Same walker as cycle 3, extended with one new skip: **`createdBy`**
(server-assigned UUID like `requestid`, must be skipped in the
walker because the stub data has it `null` for `source=corti` entries
where there is no human creator).

9 tests cover:

```
test_templates_spec_is_real_and_cached                            PASSED
test_sections_spec_is_real_and_cached                             PASSED
test_v2_templates_list_shape_matches_corti_spec                   PASSED
test_v2_sections_list_shape_matches_corti_spec                    PASSED
test_v2_templates_filter_source_corti_returns_only_corti          PASSED
test_v2_sections_filter_specialty_cardiology                      PASSED
test_v2_templates_invalid_source_422                              PASSED
test_v2_templates_reference_round_trip                            PASSED
test_v2_sections_reference_round_trip                             PASSED
9 passed in ~3s
```

Full `tests/test_api` regression: **112/112 PASS** in 3:39 (was 103
pre-cycle-4, +9 for this cycle). tsc clean.

## Design decisions

1. **LIST only, not CRUD.** Closing both full CRUD surfaces (22
   endpoints) in one cycle violates the "按复杂度排序" rule and breaks
   the回环 gate. Cycles 4.1+ will layer on create / update / delete /
   publish / version incrementally.
2. **Stub data, no DB.** iCoDer doesn't have real template/section
   storage; deferring that until the storage layer is designed is
   cleaner than faking it. The schemas are storage-agnostic so the
   real backend will plug in without changing wire contract.
3. **Legacy `/api/templates` NOT deleted.** It serves the legacy
   frontend Templates Beta page (DB-backed, iCoDer Chinese category
   enums). Cleaning it up is Phase 2 work; Cycle 4 adds the Corti
   shape alongside without touching the legacy surface.
4. **`publishedVersion` schema NOT wired.** The stub data doesn't
   include a published version. The schema will be added when a real
   publish endpoint lands. `publishedVersion` is omitted from stub
   responses, which is valid per spec (it's optional).
5. **Walker skip list extended.** `createdBy` joins `requestid` and
   `creditsConsumed` as a server-assigned dynamic field that stub
   data legitimately leaves null for Corti-source entries.

## Out of scope (explicit, future cycles)

- ❌ `GET /documents/templates/{id}` (get one) — Cycle 4.1
- ❌ `POST /documents/templates/` (create) — Cycle 4.2
- ❌ `PATCH /documents/templates/{id}` (update) — Cycle 4.2
- ❌ `DELETE /documents/templates/{id}` — Cycle 4.2
- ❌ All section CRUD — Cycle 4.3+
- ❌ `POST /documents/templates/{id}/versions/` (create-version) — Cycle 4.4
- ❌ `POST /documents/templates/{id}/versions/{versionId}/publish` — Cycle 4.5
- ❌ Real DB-backed storage design — separate Phase 2 task
- ❌ Frontend `TemplatesPage` switching from `/api/templates` to
  `/api/v2/tools/templates` — out of scope: Phase 1.2 = backend wire
  parity only

## Risk register

| Risk | Mitigation |
|---|---|
| SDK caller expects `publishedVersion` populated | Documented in spec doc; Cycle 4.4 will add publish + populate |
| Filter algorithm differs from real DB query | Cycle 4 implements subset match; real DB query will replace — wire shape unchanged |
| Stub data UUIDs collide with real ones | All stub UUIDs are deterministic, fixed (no `uuid4()` generation in stub); SDK callers should treat as read-only demo data |

## Auto-advance: Cycle 5 = Documents Classic REST (Planned deprecation)

Per the parity queue. The Documents Classic family (`/documents-classic/`)
is marked as "Planned deprecation" in the Corti docs — it's the legacy
template/document surface that the §13.4 family replaces. iCoDer has
its own legacy `documents` router that this will likely target for
deletion or deprecation-banner.