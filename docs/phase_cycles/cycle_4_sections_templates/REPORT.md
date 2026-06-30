# Cycle 4 — Sections & Templates LIST — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 9/9 回环一致性测试 + 112/112 test_api regression + tsc clean

## Spec ground truth

Captured two real Corti OpenAPI 3.0.0 specs:

- `https://docs.corti.ai/api-reference/guided-templates/list-templates.md`
  (23,529B) → `docs/corti-reverse-engineered/guided-templates-list.md`
  → archive `docs/phase_cycles/cycle_4_sections_templates/corti-templates-list.md`.
  Path: `GET /documents/templates/` → operationId `guided_templates_list`.
- `https://docs.corti.ai/api-reference/guided-sections/list-sections.md`
  (18,630B) → `docs/corti-reverse-engineered/guided-sections-list.md`
  → archive `docs/phase_cycles/cycle_4_sections_templates/corti-sections-list.md`.
  Path: `GET /documents/sections/` → operationId `guided_sections_list`.

## Files

| File | Lines | Status |
|---|---|---|
| `backend/app/schemas/v2_tools_sections_templates.py` | 165 | NEW |
| `backend/app/api/v2_tools_sections_templates.py` | 235 | NEW |
| `backend/tests/test_api/test_v2_sections_templates_consistency.py` | 290 | NEW |
| `backend/app/main.py` | +2 | include + import |
| `docs/PHASE_1_2_CYCLE4_SECTIONS_TEMPLATES_LIST.md` | 168 | NEW |
| `docs/phase_cycles/cycle_4_sections_templates/{corti-templates-list.md, corti-sections-list.md}` | 23,529B + 18,630B | archive |
| `docs/corti-reverse-engineered/{guided-templates-list.md, guided-sections-list.md}` | archive copies | source |

## Test results

```
tests/test_api/test_v2_sections_templates_consistency.py:
  test_templates_spec_is_real_and_cached                          PASSED
  test_sections_spec_is_real_and_cached                           PASSED
  test_v2_templates_list_shape_matches_corti_spec                 PASSED
  test_v2_sections_list_shape_matches_corti_spec                  PASSED
  test_v2_templates_filter_source_corti_returns_only_corti        PASSED
  test_v2_sections_filter_specialty_cardiology                    PASSED
  test_v2_templates_invalid_source_422                            PASSED
  test_v2_templates_reference_round_trip                          PASSED
  test_v2_sections_reference_round_trip                           PASSED
9 passed in ~3s

tests/test_api/ (full regression):
112 passed in 219.92s (3:39)
- Phase 1.0 OAuth (14) ✓
- Phase 1.1 Medical Coding v2 (8) ✓
- Phase 1.2 cycle 1 FactsR (8) ✓
- Phase 1.2 cycle 2 Streams (5) ✓
- Phase 1.2 cycle 3 Guided Doc (6) ✓
- Phase 1.2 cycle 4 Sections + Templates LIST (9) ✓
- M3-0 legacy surfaces (62) ✓

frontend tsc --noEmit: exit 0, 0 errors
```

## 回环一致性测试 strategy

Cycle 3 walker (`_check_shape` in
`tests/test_api/test_v2_guided_document_consistency.py`) was re-used
with one extension: **`createdBy` added to the dynamic-field skip
list** alongside `requestid` and `creditsConsumed`. Reason: `createdBy`
is a server-assigned UUID that the stub data legitimately leaves `null`
for `source=corti` entries (no human creator), but the Corti spec
declares it `type: string` (not nullable) — so the walker must skip
it the same way it skips `requestid`.

Two distinct OpenAPI specs (templates + sections) are loaded from
their captured markdown files. Each has its own `_check_shape` invocation
so the walker validates against the correct schema.

## Bug fixes during cycle 4

1. **`class GuidedSource(str, Literal)` invalid** — `typing.Literal`
   cannot be subclassed. Fix: removed the unused class; the inline
   `Literal["user", "corti", "project"]` annotation in the field
   definition is the only usage.
2. **`createdBy: null` triggered type error** — walker incorrectly
   flagged `null` as type-mismatch. Fix: added `createdBy` to walker
   skip list.

## Auto-advance: Cycle 5 = Documents Classic REST (Planned deprecation)

Per the parity queue. The Documents Classic family is the legacy
template/document surface that §13.4 replaces; iCoDer has its own
legacy `documents` router that Cycle 5 will likely delete or banner.