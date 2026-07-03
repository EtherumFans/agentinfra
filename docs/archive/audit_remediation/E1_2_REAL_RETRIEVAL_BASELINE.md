# E1.2 — Real Retrieval Restoration & F1 Baseline (2026-06-27)

> **Verdict**: ICD-9-CM-3 index BUILT. Two wiring bugs FIXED. F1 baseline ESTABLISHED on 10-case smoke.
>
> **Headline**: F1@1=0.095, F1@5=0.107 on `full` variant. Pipeline picks correct concept ~60% of time but misses exact subcategories (e.g., R91.x02 vs R91.800).

## What was done in E1.2

### 1. Built ICD-9-CM-3 FAISS index (53 MB)

`python scripts/build_medcoder_icd9cm3_index.py --asset-dir E:/iCoDerA/DataAsset --out data/medcoder`

- Input: 13,617 ICD-9-CM-3 procedure codes from `icd9cm3_code_catalog.json`
- Embedder: BGE-M3 (BAAI/bge-m3, 1024-dim) — already cached
- Output: `data/medcoder/faiss_icd9cm3.index` (53.2 MB) + `data/medcoder/metadata_icd9cm3.pkl` (2.3 MB)
- Wall time: **35 min** (model load 7s + embed 34.9 min + FAISS write 0.7s)
- Health check: `is_icd9cm3_retriever_available() == True` ✓

### 2. Asset wiring audit (see E1_2_ASSET_WIRING_AUDIT.md)

| # | Asset | Status |
|---|-------|--------|
| 1 | icd10cn_code_catalog | ✅ WIRED |
| 2 | icd10cn_synonym_map | ✅ WIRED |
| 3 | icd9cm3_code_catalog | ⚠️ no loader; only consumed via FAISS (which doesn't load it) |
| 3a | faiss_icd9cm3.index | ⚠️ file exists, **NO retriever reads it** — `MedCodERRetriever` hard-codes ICD-10 filenames |
| 4 | coding_differentiation_kb | ✅ WIRED (Stage 4 prompt injection) |
| 5 | evidence_anchoring_kb | ❌ NOT WIRED |
| 6 | cot_generation_progress_v2 | ❌ NOT WIRED (M2 explicitly skipped) |
| 7 | gold_disease_catalog | ❌ NOT WIRED |

### 3. Two wiring bugs found and fixed

#### Bug A: e2e_medcoder_validation.py segfaults on Windows

**Root cause**: Script passed an in-process `MedCodERRetriever` to `HybridCodingAdapter`, which forwarded it to `MedCodERStrategy`. Strategy uses passed-in retriever directly, skipping its own lazy-create logic that would have picked `SubprocessMedCodERRetriever` on Windows. Result: BGE-M3 + httpx segfault.

**Fix** (scripts/e2e_medcoder_validation.py:495): For `full` variant, do NOT pass `retriever` to `HybridCodingAdapter`. Let strategy choose the subprocess wrapper via its default sentinel.

#### Bug B: HybridCodingAdapter defeats lazy-create (pre-existing, masked)

**Root cause** (E1.1 missed): `HybridCodingAdapter.__init__` passed `retriever=retriever` (could be `None`) to `MedCodERStrategy`. E1.1 introduced `_NO_RETRIEVER` sentinel to distinguish "not provided" from "explicit None", but the adapter wasn't updated. So `HybridCodingAdapter(mode="medcoder")` → strategy sees `retriever=None` → `_retriever_lazy=False` → `_create_default_retriever` never called → all Stage 2 calls return degraded.

**Evidence**: `tests/test_services/test_hybrid_medcoder_subprocess.py::test_get_retriever_uses_subprocess_when_env_var_set` was failing (the only E1.1 known pre-existing failure).

**Fix** (icoder_runtime/providers/medical_coding/hybrid_adapter.py:128-141): Use `_NO_RETRIEVER` sentinel when caller passed `None` (or didn't pass) retriever. Preserves "explicit None = degraded" semantics.

### 4. F1 baseline (10-case smoke, full variant)

```
=== full ===
  cases:        10
  F1@1:         0.0950
  F1@2:         0.0986
  F1@5:         0.1074
  avg latency:  45.282s
  total time:   452.8s
```

Per-case (top-1 only):

| case | gold (first 3) | top-5 | F1@5 | concept match? |
|------|----------------|-------|------|----------------|
| 179651 | J40/R91.x02/S22.300 | R91.800/C34.x/C34.x/C34.x/D86.000 | 0.000 | partial (lung imaging) |
| 171833 | I63.900 +6 | I63.900/I63.902/... | 0.167 | ✓ (cerebral infarction) |
| 420477 | M81.900/S32.000x002/Z98.800x302 | S32.000x002/... | 0.286 | ✓ (lumbar fracture) |
| 412872 | O34.201 +7 | N85.801/O34.200/O34.201/... | 0.154 | ✓ (obstetric) |
| 505763 | O34.201 +8 | N85.801/O34.201/... | 0.143 | ✓ (obstetric) |
| 182397 | 45.2302/A49.809/I84.201/K29.400/K92.901/Z98.x | R14.x (flatulence) | 0.000 | ❌ (wrong concept) |
| 972538 | O26.x/O34.201/O35.817/O82.000/Z37.000x001 | O34.201/... | 0.182 | ✓ |
| 198691 | 31.4201/C73.x00/E06.304/Z87.x/Z98.x | E04.x (goiter) | 0.000 | partial (thyroid) |
| 176932 | 45.2302/A49.809/E04.101/E78.500/K29.400 +4 | K29.400/... | 0.143 | ✓ (gastritis) |
| 198643 | R91.x02/Z85.101 | C34.300x004/C34.x/C34.x/C34.x/C34.x | 0.000 | ❌ (lung ca vs finding) |

**Pattern**: 6/10 cases have a correct top-1 concept; 4/10 miss the concept entirely. Subcategory precision is the main weakness (R91.x02 vs R91.800).

## Why F1 is lower than the paper's reported numbers

The MedCodER paper (Baksi et al., NAACL 2025) reports F1@1 ~0.6-0.7 on the MIMIC dataset. Our baseline of 0.095 is much lower. Likely causes:

1. **Fixture granularity**: iCoDer 201 fixture uses Chinese-extended ICD-10 codes (e.g., `R91.x02`, `O26.900x505`). These subcodes don't exist in the standard ICD-10-CN catalog, so even correct concept-level retrieval scores 0.
2. **No CoT few-shot**: `cot_generation_progress_v2.json` (175 verified examples) is NOT wired into Stage 4 rerank. Paper used CoT.
3. **No evidence anchoring**: Stage 1 uses rapidfuzz for char-span snapping; `evidence_anchoring_kb.json` (972 × 6,490 patterns) is not consulted.
4. **Single-pass retrieval**: Top-K=20 with no query expansion or re-retrieval on weak matches.

## What's next (recommended priority)

| # | Action | Effort | Expected F1 gain |
|---|--------|--------|-----------------|
| 1 | Wire `MedCodERICD9CM3Retriever` (use the 53 MB index for procedure RAG) | 2-3 hr | medium (53% of cases have procedure gold) |
| 2 | Wire `cot_generation_progress_v2.json` into Stage 4 prompt (few-shot) | 1-2 hr | high (Stage 4 is the rerank bottleneck) |
| 3 | Wire `evidence_anchoring_kb.json` into Stage 1 evidence anchoring | 2-3 hr | medium |
| 4 | Tune top-K (currently 20→5 for rerank) on a calibration set | 1 hr | low-medium |
| 5 | Run full 201-case eval (4.7 hr wall time) | passive | — (baseline measurement) |

The wiring fix from Bug B is the highest-ROI immediate next step — it unblocks the lazy-create path so all subsequent wiring (1-3 above) automatically benefits on Windows.

## Files changed in E1.2

| File | Change |
|------|--------|
| `icoder_runtime/providers/medical_coding/hybrid_adapter.py` | Use `_NO_RETRIEVER` sentinel instead of `None` (Bug B fix) |
| `scripts/e2e_medcoder_validation.py` | Don't pass in-process retriever on Windows (Bug A fix) |
| `data/medcoder/faiss_icd9cm3.index` | NEW: 53 MB FAISS index over 13,617 ICD-9-CM-3 codes |
| `data/medcoder/metadata_icd9cm3.pkl` | NEW: 2.3 MB metadata for the above |
| `.gitignore` | NEW: exclude `data/medcoder/{faiss*,metadata*,models/,eval_smoke*}` + runtime noise |
| `docs/audit_remediation/E1_2_ASSET_WIRING_AUDIT.md` | NEW: asset wiring status |
| `docs/audit_remediation/E1_2_REAL_RETRIEVAL_BASELINE.md` | NEW: this file |

## Test status

- `tests/test_services/test_hybrid_medcoder_subprocess.py` — **6 passed, 1 skipped** (was: 1 failed, 6 passed)
- `tests/test_services/test_hybrid_medcoder.py` — passed (16/16)
- `tests/test_services/test_hybrid_medcoder_variants.py` — 1 pre-existing failure unrelated (`code_like_humans` mode constant, M2c test gap)
- `tests/test_services/test_e2e_medcoder_eval.py` — passed

## Notes

- The eval fixture icoder_201.json (201 cases) is heavy — full run takes ~4.7 hr wall time on this machine. The 10-case smoke (~7.5 min) is enough to confirm the pipeline works end-to-end. The 201-case run is a follow-up task.
- `is_icd9cm3_retriever_available()` returns True, but the retriever code path still uses only ICD-10. This is the **#1 wiring gap** to close in the next session.
- `os.name == 'nt'` path uses SubprocessMedCodERRetriever; probe_timeout default is 10s but BGE-M3 model load can take 30-90s on first run, leading to probe-timeout and "retriever not ready" status. First call still works (worker is alive, finishes load), but `is_ready` is misleadingly False. Consider bumping default probe_timeout to 60s.