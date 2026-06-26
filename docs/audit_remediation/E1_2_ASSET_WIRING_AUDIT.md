# E1.2 — MedCodER Asset Wiring Audit (2026-06-26)

> **Status**: AUDIT COMPLETE, gaps identified. Build in progress (Step 1 of 6).
>
> **Verdict**: 3/7 priority assets are wired, 4/7 are paper artifacts.

## Why this audit matters

E1.1 (Real Boot Gate) confirmed the app boots and tests are green. But "green
tests" don't mean "real coding capability". Before running F1 eval against
201 gold cases, we need to know **which knowledge assets actually reach the
runtime**, so we can interpret the F1 numbers correctly and triage failures
to the right layer (model limit vs asset gap vs wiring bug).

## Scope

7 iCoDerA DataAsset files marked as "priority" by the Phase A audit:

| # | Asset | Size | Role |
|---|-------|------|------|
| 1 | `icd10cn_code_catalog.json` | 26 MB | ICD-10 diagnosis code master (37,897 codes) |
| 2 | `icd10cn_synonym_map.json` | 15 MB | Disease name → code reverse index (75,968 synonyms) |
| 3 | `icd9cm3_code_catalog.json` | 6.6 MB | ICD-9-CM-3 procedure code master (13,617 codes) |
| 3a | `faiss_icd9cm3.index` | ~53 MB | FAISS vector index over ICD-9-CM-3 (newly built, see Step 1) |
| 4 | `coding_differentiation_kb.json` | 2.9 MB | P0/P1 code-pair differentiation rules (2,090 groups) |
| 5 | `evidence_anchoring_kb.json` | 8.5 MB | Code → evidence pattern anchors (972 × 6,490) |
| 6 | `cot_generation_progress_v2.json` | 11 KB | Verified rerank CoT few-shot examples (175) |
| 7 | `gold_disease_catalog.json` | 29 MB | Canonical disease names (37,897 codes) |

## Wiring status matrix

| # | Asset | Status | Where it actually loads | Evidence |
|---|-------|--------|--------------------------|----------|
| 1 | icd10cn_code_catalog | ✅ WIRED | `app/services/icd10cn_loader.py` singleton (`get_loader()`) → consumed by retriever's catalog-compliance filter | `medcoder_retriever.py:274` `from app.services.icd10cn_loader import get_loader` |
| 2 | icd10cn_synonym_map | ✅ WIRED | Same loader; exposes `synonyms_for()` and `codes_for_term()` | `icd10cn_loader.py:90` `_term_index: dict[str, list[str]]` |
| 3 | icd9cm3_code_catalog | ⚠️ CATALOG NOT LOADED | NO `ICD9CM3Loader` analogue exists. Only consumed implicitly via FAISS (which also doesn't load) | `grep icd9cm3_loader` → 0 hits in `app/services/` |
| 3a | faiss_icd9cm3.index | ⚠️ FILE EXISTS, NO READER | `MedCodERRetriever` hard-codes `INDEX_FILENAME = "faiss.index"` and `META_FILENAME = "metadata.pkl"` (line 40-41). `SubprocessMedCodERRetriever` worker same. `is_icd9cm3_retriever_available()` only checks file existence; does not load | `medcoder_retriever.py:40-41` |
| 4 | coding_differentiation_kb | ✅ WIRED | `medcoder_adapter.py:261-293` `get_differentiation_hints()` — inline filesystem read every Stage 4 call, injected into rerank prompt | `medcoder_strategy.py:658` `hints = get_differentiation_hints(disease_text)` → passed to `stage4_rerank(...)` |
| 5 | evidence_anchoring_kb | ❌ **NOT WIRED** | 0 `.py` files load this asset. Only mentions in `agent_pack.json` descriptions, audit docs (INDEX_AUDIT.md, PHASE_A_REPORT.md), and 1 handler docstring reference | `grep -l evidence_anchoring_kb backend/{app,icoder_runtime}/**/*.py` → 0 hits |
| 6 | cot_generation_progress_v2 | ❌ **NOT WIRED** | M2 explicitly skipped. Handler docstring (`rerank_codes.py:14`): *"M2 does NOT inject CoT few-shot (`cot_generation_progress_v2.json`)"* | `grep -r cot_generation_progress_v2 backend/{app,icoder_runtime}/**/*.py` → 0 hits |
| 7 | gold_disease_catalog | ❌ **NOT WIRED** | 0 `.py` files load this asset. Only mentioned in INDEX_AUDIT.md and PHASE_A_REPORT.md | `grep -l gold_disease_catalog backend/{app,icoder_runtime}/**/*.py` → 0 hits |

### Summary

- **3/7** are truly wired into the runtime path
- **2/7** have a partial paper trail (3 catalog file referenced in build
  script, 3a file built but never read)
- **3/7** are referenced only in docs/agent_pack descriptions, with no
  production code path consuming them

## Where each asset SHOULD go

| # | Asset | Stage that should consume it | Value add |
|---|-------|------------------------------|-----------|
| 5 | evidence_anchoring_kb | Stage 1 (LLM extraction + evidence anchoring) | Better char-span snapping; fewer false-positive evidence matches |
| 6 | cot_generation_progress_v2 | Stage 4 (rerank) | Verified few-shot CoT → much better LLM rerank accuracy |
| 7 | gold_disease_catalog | Stage 5 (compliance/calibration) | Canonical name normalization → cleaner calibration surface |
| 3a | faiss_icd9cm3.index | Stage 2 (procedure retrieval) | ICD-9-CM-3 RAG; currently LLM-only → procedure F1 ceiling very low |

## icoder_201.json fixture shape

201 gold cases. F1 eval is diagnosis-weighted:

- 201 (100%) have `expected_principal_diagnosis` (gold code)
- 196 (97.5%) have `expected_secondary_diagnoses` (avg 4.32 codes/case)
- 108 (53.8%) have `expected_procedure_codes` (avg 0.65 codes/case)

So F1@K primarily reflects diagnosis-side recall. Procedure F1 will be hurt
by missing 9cm3 RAG but contributes less to headline.

## Step 1: build ICD-9-CM-3 index (in progress)

Started `python scripts/build_medcoder_icd9cm3_index.py --asset-dir E:/iCoDerA/DataAsset --out data/medcoder` at 23:17:30 on 2026-06-26.

- Smoke test (50 codes): 20.7s end-to-end, all components functional
- Full build (13,617 codes) projected: ~25 min total (mostly BGE-M3 embed)
- Expected finish: ~23:42

## Recommended next steps (post-build)

1. **WIRE** the ICD-9-CM-3 index into a `MedCodERICD9CM3Retriever` (or extend
   `MedCodERRetriever` to dual-index). Without this, the 53 MB file is a
   paper artifact. *(This is the #1 missing piece.)*
2. Run `python scripts/e2e_medcoder_validation.py --cases tests/fixtures/icoder_201.json --variant full`
3. Triage F1 failures to: model limit vs asset gap vs wiring bug
4. Wire `cot_generation_progress_v2` into Stage 4 rerank prompt (high ROI, small file)
5. Wire `evidence_anchoring_kb` into Stage 1 evidence anchoring
6. Wire `gold_disease_catalog` into Stage 5 calibration (last; benefit unclear)

## Why the gaps exist

- `evidence_anchoring_kb` would require Stage 1 redesign (currently uses
  rapidfuzz for char-span snapping, KB would replace that with KB-driven
  patterns).
- `cot_generation_progress_v2` requires Stage 4 prompt surgery (currently
  the rerank prompt is a static template, few-shot examples would slot in).
- `gold_disease_catalog` requires Stage 5 calibration redesign (currently
  per-dx confidence is a flat mean, KB would inject prior).
- ICD-9-CM-3 retriever: no upstream ticket drove this; the build script was
  added by INDEX_AUDIT but no runtime wiring ticket.

These are real engineering tasks, not "just import the JSON". Each requires
a stage-level refactor + tests.