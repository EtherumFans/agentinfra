# E1.4 — Procedure RAG Wireup (Stage 1 + Procedure Retriever → `output.procedures`)

**Date:** 2026-06-27
**Closes audit gap:** E1.2 audit #2 ("Stage 1 → procedures path wired but produces zero output") + #3a part 2 (ICD-9-CM-3 retrieval sidecar was built but not consumed by the main pipeline).
**Builds on:** E1.3 — `MedCodERICD9CM3Retriever` + subprocess wrapper.

## Problem

After E1.3, the ICD-9-CM-3 FAISS index (53 MB, 13,617 codes) is loaded and the
in-process retriever is tested in isolation. But the main `MedCodERStrategy.run_variant`
pipeline:

1. Did NOT extract `procedure_mentions` from EMR text (Stage 1 prompt asked
   for diseases only).
2. Did NOT populate `MedicalCodingOutputSchema.procedures` from ICD-9-CM-3
   retrieval (the `_populate_procedures` method didn't exist).

So even though the retriever existed, the user-facing output had **zero
procedure codes**. E1.2 baseline confirmed: procedure F1=0 across 10 cases.

## What changed

### 1. Stage 1 prompt + result type (`medcoder_adapter.py`)

- New `ExtractionResult` dataclass with `diseases` + `procedure_mentions`.
- Backward-compatible iteration (`for dx in extraction: ...` still works).
- `EXTRACTION_SYSTEM_PROMPT` updated to ask for object shape:
  ```json
  {
    "diseases": [{"disease_text": "...", "supporting_evidence": "...", "llm_initial_code": "..."}],
    "procedure_mentions": ["腹腔镜胆囊切除术", "结肠镜检查"]
  }
  ```
- `parse_extraction_response` accepts both legacy array shape (back-compat)
  and new object shape. First non-whitespace, non-fence character decides
  branch (fixes a regex-greediness bug where `[{...}]` was matched as
  top-level dict).

### 2. Strategy integration (`medcoder_strategy.py`)

- `stage1_extraction` now returns `ExtractionResult` (was `list[dict]`).
- New `_populate_procedures(out, mentions)` method:
  - Cap at 10 mentions (avoid runaway token cost on long admissions).
  - Dedup on code (same code → one `ProcedureEntry`).
  - Non-fatal: if procedure retriever raises, `out.procedures` stays empty.
- New `procedure_retriever` constructor kwarg with `_get_procedure_retriever`
  lazy factory (mirrors diagnosis retriever lazy pattern).
- Wired into `_run_full`, `_run_prompt_only`, `_run_prompt_plus_retrieve`.

### 3. Test updates

- `tests/test_services/test_medcoder_icd9cm3_retriever.py`:
  - New `TestPopulateProcedures` class with 5 tests
    (empty input, dedup, caps, retriever failure, success path).
  - All 19 tests green.
- `tests/unit/icoder/providers/test_medcoder_strategy.py`:
  - 3 mock Stage 1 stubs updated to return `ExtractionResult`.
  - `test_stage1_extraction_no_gateway_returns_mock` now checks
    `isinstance(out, ExtractionResult)`.
  - New tests for object shape (parses `procedure_mentions`) and legacy
    array shape (no procedure_mentions).
- `tests/test_services/test_medcoder_adapter.py`:
  - `test_empty_or_invalid_returns_empty` updated to check `.diseases`.
- `tests/test_services/test_hybrid_medcoder_variants.py`:
  - `test_medcoder_modes_constant_lists_all_supported_values` updated to
    include `code_like_humans` (stale since Phase C M2c).

## Verification

### Unit tests

```
tests/test_services/test_medcoder_icd9cm3_retriever.py ........... 19 passed
tests/test_services/test_medcoder_adapter.py ..................... passed
tests/unit/icoder/providers/test_medcoder_strategy.py ............ passed
tests/test_services/test_hybrid_medcoder_variants.py ............. passed

Full suite: 1928 passed, 4 errors (pre-existing, unrelated — auth service 502 on localhost:8765)
```

### Smoke tests (10 cases from `ccl2026_val_100.json`)

**Oracle-name smoke** (retriever given the gold procedure name directly):
```
hit@1 = 6/10 = 60%
hit@5 = 10/10 = 100%
```

The retriever itself is well-tuned: when given a clean procedure name, it
returns the correct ICD-9-CM-3 code in the top-1 60% of the time, and always
within top-5.

**Realistic full-pipeline smoke** (DeepSeek Stage 1 + ICD-9-CM-3 retriever):
```
hit@1 = 0/7 = 0%
hit@5 = 0/7 = 0%
```

5 procedure candidates per case now appear in `output.procedures` where
before E1.4 the field was empty for all cases. The 0% hit is because DeepSeek's
Stage 1 procedure mention extraction is variable on these obstetric/oncology
cases — the bottleneck moved from "no candidates" to "mentions don't match
the gold codes' Chinese names."

## Comparison to E1.2 baseline

| Metric                   | E1.2 (no proc RAG) | E1.4 (proc RAG wired) |
|--------------------------|--------------------|------------------------|
| `output.procedures` size | 0                  | 1-5                    |
| Procedure hit@1          | 0%                 | 0% (Stage 1 bottleneck)|
| Procedure hit@5          | 0%                 | 0% (Stage 1 bottleneck)|
| Retriever hit@5 (oracle) | n/a                | 100%                   |

E1.4 closes the "no candidates" gap. The remaining "candidates don't match
gold" gap requires Stage 1 prompt tuning or a synonym-aware mention
extractor (future E1.5 / audit #3).

## Files changed

- `icoder_runtime/providers/medical_coding/medcoder_adapter.py` — ExtractionResult + parser refactor
- `icoder_runtime/providers/medical_coding/medcoder_strategy.py` — procedure RAG sidecar
- `tests/test_services/test_medcoder_icd9cm3_retriever.py` — TestPopulateProcedures (5 new tests)
- `tests/test_services/test_medcoder_adapter.py` — ExtractionResult assertions
- `tests/unit/icoder/providers/test_medcoder_strategy.py` — ExtractionResult + new shape tests
- `tests/test_services/test_hybrid_medcoder_variants.py` — stale mode constant fix

## Follow-ups (next priorities)

1. **E1.5 — ICD9CM3Loader** (audit gap #3 closure): add a real catalog
   loader mirroring `icd10cn_loader.py`. Currently the ICD-9-CM-3 retriever
   does no catalog membership filter, so ghost codes can survive (test
   `test_no_catalog_filter_drops_ghost_codes` pins this contract).
2. **Stage 1 procedure mention quality**: consider adding a synonym-aware
   mention extractor that maps clinical abbreviations (e.g. "剖宫产" →
   "剖宫产术") to canonical ICD-9-CM-3 names before retrieval. The oracle
   smoke shows the retriever works; the bottleneck is upstream.
3. **End-to-end F1 eval**: re-run `scripts/e2e_medcoder_validation.py` on
   `icoder_201.json` to confirm overall F1 doesn't regress (procedure
   field is new — primary/secondary dx should be unchanged).