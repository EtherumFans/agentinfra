# Cycle 3 — Guided Documents (templateRef + ephemeral) — REPORT

**Date:** 2026-06-30 → 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 6/6 回环一致性测试 + 103/103 test_api regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/guided-documents/generate-a-structured-document.md`
(35,728 bytes) → `docs/corti-reverse-engineered/guided-documents-generate.md`
→ archive `docs/phase_cycles/cycle_3_guided_doc/corti-guided-generate.md`.

Embedded OpenAPI 3.0.0 YAML contains 14 schemas, 1 path (`/documents/` POST).
Cycle 3 closes the **simplest path**: `templateRef` (no overrides) +
`X-Corti-Retention-Policy: none` → 200 ephemeral.

## Files

| File | Lines | Status |
|---|---|---|
| `backend/app/schemas/v2_tools_guided_document.py` | 165 | NEW |
| `backend/app/api/v2_tools_guided_document.py` | 225 | NEW |
| `backend/tests/test_api/test_v2_guided_document_consistency.py` | 310 | NEW |
| `backend/app/main.py` | +2 | include + import |
| `docs/PHASE_1_2_CYCLE3_GUIDED_DOCUMENTS.md` | 168 | NEW |
| `docs/phase_cycles/cycle_3_guided_doc/corti-guided-generate.md` | 35,728B | archive |

## Test results

```
tests/test_api/test_v2_guided_document_consistency.py:
  test_openapi_spec_is_real_and_cached                       PASSED
  test_v2_guided_document_ephemeral_shape_matches_corti_spec  PASSED
  test_v2_guided_document_error_envelope_matches_corti_spec  PASSED
  test_v2_guided_document_empty_context_rejected             PASSED
  test_v2_guided_document_no_llm_credential_returns_503      PASSED
  test_v2_guided_document_reference_round_trip               PASSED
6 passed in 1.57s

tests/test_api/ (full regression):
103 passed in 322.84s (5:22)
- Phase 1.0 OAuth (14) ✓
- Phase 1.1 Medical Coding v2 (8) ✓
- Phase 1.2 cycle 1 FactsR (8) ✓
- Phase 1.2 cycle 2 Streams (5) ✓
- Phase 1.2 cycle 3 Guided Doc (6) ✓
- M3-0 legacy surfaces (62) ✓

frontend tsc --noEmit: exit 0, 0 errors
```

## 回环一致性测试 strategy

Spec loader uses regex `r"````yaml[^\n]*\n(.*?)````"` against the captured
markdown (the fence opener line is
`` ````yaml /api-reference/auto-generated-openapi.yml post /documents/ ```` — non-empty
header line, so `\s*\n` is wrong).

The recursive `_check_shape` walker:

- Walks `$ref` to resolve `components/schemas/*` references.
- **Skips dynamic leaves**: `requestid`, `creditsConsumed`.
- **Honors `nullable: true`** (Corti spec marks `interactionId` and
  `structuredDocument` nullable — first pass wrongly flagged `None`,
  fixed by checking `schema.get("nullable", False)` before type-check).
- Asserts type equality (`number` accepts `integer`).
- Asserts required-field presence.
- Asserts enum/const membership.

The error envelope test caught a separate contract violation:
`ErrorResponse.validationErrors` is `type: array` with no
`nullable: true`. First pass set it to `None` — fixed in `_err()` to
omit the key entirely when no per-field errors exist.

## Auto-advance: Cycle 4 = Sections & Templates REST (Beta)

Per the Phase 1.2 cycle queue: Sections & Templates CRUD lets iCoDer
host its own templates so the cycle-3 endpoint can reference real
template IDs. Cycle 5 = Documents Classic.