# Cycle 18 — Codes predict — REPORT

**Date:** 2026-07-01
**Branch:** master
**Verdict:** ✅ PASS — 19/19 回环一致性测试 (new) + 8/8 Phase 1.1 regression + tsc clean

## Spec ground truth

Captured `https://docs.corti.ai/api-reference/codes/predict-codes.md`
(17,173 bytes) → `docs/corti-reverse-engineered/codes-predict-codes.md`
→ archive `docs/phase_cycles/cycle_18_codes_predict/corti-codes-predict-codes.md`.

Path: `POST /tools/coding/` → operationId `codes_predict`.
Response: **200 OK** with `{codes, candidates, usageInfo}` envelope
(3 fields REQUIRED). Per-code: 5 fields REQUIRED. Per-evidence: 4 fields
REQUIRED. Errors per spec: 400, 401, 403, 500, 504.

## Files

| File | Status | Lines |
|---|---|---|
| `backend/app/schemas/v2_tools_coding.py` | MODIFIED | +230 (CORTI_COMMON_CODING_SYSTEMS × 15 + CommonText/DocumentID/AIContext + CodesFilter/Request/Response/ReadResponse/CommonUsageInfo + default_corti_coding_system) |
| `backend/app/api/v2_tools_coding.py` | MODIFIED | +276/-12 (relocate Phase 1.1 → /coding/icoder + new /coding handler + 2 helpers) |
| `backend/tests/test_api/test_v2_tools_coding.py` | MODIFIED | 3 test path updates (Phase 1.1 → /coding/icoder) |
| `backend/tests/test_api/test_v2_codes_predict_consistency.py` | NEW | 442 |
| `docs/corti-reverse-engineered/codes-predict-codes.md` | NEW | 17,173B |
| `docs/PHASE_1_3_CYCLE18_CODES_PREDICT.md` | NEW | this report's parent spec |
| `docs/phase_cycles/cycle_18_codes_predict/corti-codes-predict-codes.md` | archive | 17,173B |

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
  8/8 PASSED (path-relocation to /coding/icoder)

TOTAL: 27/27 PASSED in 2.26s
```

## Path split (load-bearing change)

| Path | Before cycle 18 | After cycle 18 |
|---|---|---|
| `POST /api/v2/tools/coding/` | Phase 1.1 Chinese-only MedCodER | **Cycle 18** Corti §13.6 spec predictor (15 systems) |
| `POST /api/v2/tools/coding/icoder/` | (did not exist) | Phase 1.1 Chinese-only MedCodER (relocated) |
| `POST /api/v2/tools/coding/icoder` (no slash) | (did not exist) | Phase 1.1 Chinese-only MedCodER (relocated) |

**No back-compat alias** at `/coding` for Phase 1.1 (hard break).
Rationale: canonical Corti path needs to be reserved for the §13.6
endpoint.

## Stub strategy

- **No LLM dependency** in cycle 18 (avoids hospital-pilot gate).
- Deterministic: `code = f"EXAMPLE-{system.split('-')[0].upper()}-001"` (primary) + `-002` (candidate).
- `usageInfo.creditsConsumed` = `len(context) + max(1, len(system))` (deterministic).
- No DB, no persistence.

## Verdict

✅ **PASS** — Cycle 18 ready for commit. Phase 1.3 §13.6 Codes family
opens at 1/2-3 endpoints.
