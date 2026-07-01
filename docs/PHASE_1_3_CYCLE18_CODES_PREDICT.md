# Phase 1.3 Cycle 18 — Codes predict align Corti §13.6

## Context

Phase 1.3 cycle 17 (`1d5404b`) closed the §13.5 Facts family at 5/5
endpoints. Cycle 18 opens the **§13.6 Codes family** with its first
endpoint: `POST /tools/coding/` (predict-codes per Corti OpenAPI spec).

**Path split (the load-bearing change):**
- Before cycle 18: `POST /api/v2/tools/coding/` was Phase 1.1's
  Chinese-only MedCodER 5-stage pipeline (`HybridCodingAdapter(mode="medcoder")`).
- After cycle 18:
  - `POST /api/v2/tools/coding/` = **Corti §13.6 spec predictor** —
    accepts all 15 `CommonCodingSystemEnum` values, returns
    `{codes, candidates, usageInfo}` per spec, no LLM dependency in
    the stub.
  - `POST /api/v2/tools/coding/icoder/` = **Phase 1.1 iCoDer MedCodER
    pipeline** — relocated, Chinese ICD-10-CN / ICD-9-CM-3 only,
    LLM-backed.

The two endpoints share the *evidence* and *alternative* inner shapes
(`CodingEvidence`, `CodingAlternative`) but differ on envelope, system
vocabulary, and stub strategy.

## Spec source

`docs/corti-reverse-engineered/codes-predict-codes.md` (17,173 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/codes/predict-codes.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_18_codes_predict/corti-codes-predict-codes.md`.

## Endpoint surface

```
POST /api/v2/tools/coding/             (canonical, with trailing slash)
POST /api/v2/tools/coding              (no-slash alias)
Authorization: Bearer <jwt or oauth>
Content-Type: application/json

Body: {
  "system":  ["icd10cm-outpatient", "icd10pcs"],  // 1-15 of CommonCodingSystemEnum
  "context": [
    {"type": "text", "text": "Patient presents with ..."},
    {"type": "documentId", "documentId": "abc-123"}
  ],
  "filter": {"include": ["I50.*"], "exclude": [], "expand": true}  // optional
}

→ 200 OK   {
  "codes": [
    {
      "system": "icd10cm-outpatient",
      "code": "EXAMPLE-ICD10CM-001",
      "display": "Stub icd10cm-outpatient code for context block 0",
      "evidences": [{"contextIndex": 0, "text": "...", "start": 0, "end": 256}],
      "alternatives": []
    }
  ],
  "candidates": [
    {
      "system": "icd10cm-outpatient",
      "code": "EXAMPLE-ICD10CM-002",  // OR filter.include[0] when filter is present
      "display": "Lower-confidence candidate (icd10cm-outpatient)",
      "evidences": [...],  // mirrors primary evidence in stub
      "alternatives": []
    }
  ],
  "usageInfo": {"creditsConsumed": 3.0}  // 1 per context block + 1 per system
}
→ 400 empty_context           (context[] empty)
→ 400 empty_system            (system[] empty)
→ 400 unsupported_system      (system not in 15-value enum)
→ 400 no_text_context         (no type=text block)
→ 401 / 403                   (auth — deferred)
→ 500 / 504                   (server errors — deferred)
```

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_coding.py` | MODIFIED | +230 lines: `CORTI_COMMON_CODING_SYSTEMS` (15) + `CommonTextContext/CommonDocumentIDContext/CommonAIContext` + `CodesFilter/Request/Response/ReadResponse/CommonUsageInfo` + `default_corti_coding_system()` |
| `backend/app/api/v2_tools_coding.py` | MODIFIED | +276/-12 lines: relocate Phase 1.1 to `/coding/icoder` (renamed function) + new `/coding` handler + `_stub_corti_coding` + `_resolve_evidence_text` |
| `backend/tests/test_api/test_v2_tools_coding.py` | MODIFIED | 3 test path updates (Phase 1.1 → `/coding/icoder`) |
| `backend/tests/test_api/test_v2_codes_predict_consistency.py` | NEW | 442 lines, 19 回环一致性测试 |
| `docs/corti-reverse-engineered/codes-predict-codes.md` | NEW | 17,173B spec cache |
| `docs/phase_cycles/cycle_18_codes_predict/corti-codes-predict-codes.md` | NEW | archive |
| `docs/PHASE_1_3_CYCLE18_CODES_PREDICT.md` | NEW | this spec doc |

## Stub data

Stub does NOT call any LLM (cycle 18 is a wire-contract milestone, not
a real predictor). For each request:

- **Primary code**:
  - `system` = `body.system[0]` (first valid system)
  - `code` = `f"EXAMPLE-{system.split('-')[0].upper()}-001"` (deterministic)
  - `display` = `f"Stub {system} code for context block {ctx_idx}"` (or `(no text context)` if all documentId)
  - `evidences[0]` = `(contextIndex=0, text=text[0:256], start=0, end=min(len(text), 256))` for the first non-empty text block
  - `alternatives = []`

- **Candidate code** (always 1):
  - If `body.filter.include` is non-empty: `code = filter.include[0]`, `display = "Filter-anchored candidate ({system})"`.
  - Else: `code = f"EXAMPLE-{system.split('-')[0].upper()}-002"`, `display = "Lower-confidence candidate ({system})"`.
  - Evidence: same char-span as primary (so 回环 tests can verify the invariant on both lists).

- **usageInfo.creditsConsumed**: `len(context) + max(1, len(system))` (deterministic).

- **No DB**, no persistence; pure request-shape → response-shape projection.

## Test results

```
tests/test_api/test_v2_codes_predict_consistency.py:
  test_codes_predict_spec_is_real_and_cached                PASSED
  test_codes_predict_15_systems_enum_complete               PASSED
  test_codes_predict_minimal_request                        PASSED
  test_codes_predict_path_echo_system                       PASSED
  test_codes_predict_evidence_span_roundtrip                PASSED
  test_codes_predict_all_5_response_fields_per_code         PASSED
  test_codes_predict_all_4_evidence_fields                  PASSED
  test_codes_predict_usage_info_credits_consumed            PASSED
  test_codes_predict_filter_include                         PASSED
  test_codes_predict_filter_exclude                         PASSED
  test_codes_predict_all_15_systems_accepted                PASSED
  test_codes_predict_multi_system_in_one_request            PASSED
  test_codes_predict_multi_context_contextindex             PASSED
  test_codes_predict_empty_context_rejected                 PASSED
  test_codes_predict_empty_system_rejected                  PASSED
  test_codes_predict_unknown_system_rejected                PASSED
  test_codes_predict_no_text_context_rejected               PASSED
  test_codes_predict_trailing_slash_optional                PASSED
  test_codes_predict_codes_candidates_split                 PASSED
                                                         ── 19/19 PASSED

tests/test_api/test_v2_tools_coding.py (Phase 1.1 regression):
  test_v2_coding_shape_minimal                              PASSED  (path: /coding/icoder)
  test_v2_coding_evidence_span_roundtrip                    PASSED  (path: /coding/icoder)
  test_v2_coding_alternatives_contains_rerank               PASSED  (path: /coding/icoder)
  test_v2_coding_icoder_system_accepted                     PASSED
  test_v2_coding_corti_us_system_rejected                   PASSED
  test_v2_coding_multi_context_contextindex                 PASSED
  test_v2_coding_empty_context_rejected                     PASSED
  test_v2_coding_no_llm_credential_returns_503              PASSED
                                                         ── 8/8 PASSED

TOTAL: 27/27 PASSED in 2.26s
```

## Design decisions

1. **No LLM in cycle 18 stub.** Avoids hospital-pilot gate collision
   (Phase 1.1 returns 503 without LLM key; cycle 18 stub is green
   regardless). Real predictor wiring is a future cycle (18+).

2. **No back-compat alias at `/coding` for Phase 1.1.** Hard break.
   Rationale: canonical Corti path needs to be reserved for the §13.6
   endpoint. Any iCoDer clients still pointing at `/coding` will now
   get the spec-shaped response (no Chinese-only restriction), which
   is a behaviour change but not a wire break (15-system policy is
   more permissive than Chinese-only).

3. **`usageInfo.creditsConsumed` is deterministic** from request
   shape (1 per context block + 1 per system). Spec doesn't dictate
   the formula; this gives stable snapshot tests without hiding the
   field.

4. **Discriminated `CommonAIContext`** (text OR documentId) via
   Pydantic, not enum. Spec uses oneOf; iCoDer accepts both, but only
   text yields char-span evidence in the stub.

5. **Filter is honored on candidates, not codes.** Spec says filter
   restricts what the model can predict; cycle 18 surfaces
   `include[0]` as a candidate code token. Not a faithful LLM
   implementation; just keeps the wire shape correct.

6. **No walker.** Envelope is flat (`{codes, candidates, usageInfo}`),
   not the `transcripts: T[] | null` cycle-6 nullable pattern. Direct
   JSON key inspection suffices.

7. **Function rename** `post_v2_tools_coding` →
   `post_v2_tools_coding_icoder` for grep-ability. Both endpoints
   coexist in the same file (vs splitting into a new module) because
   they share `CodingEvidence` / `CodingAlternative` shapes and the
   split-point is path-level, not module-level.

## Next

§13.6 Codes family: 1/2-3 endpoints done. Remaining per Corti
docs-content.json:
- `code-translate` (translate between systems, e.g. icd10cn ↔ icd10cm)
- `code-verify` (validate a code against the system vocabulary)

Or move to §13.7 Languages (`list-languages`).

Per the §13 family order (STT → TextGen → Facts → Codes → Languages),
the next Corti family is **§13.7 Languages** after §13.6 closes.
