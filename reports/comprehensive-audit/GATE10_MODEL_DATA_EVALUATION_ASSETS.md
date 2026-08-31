# Audit Gate 10 — Model, Data and Evaluation Assets (Tracks M1-M5)

> Per PDF §三 Track M: audits the LLM model choice + version pinning, the data assets (ICD-10-CN catalog, KBs, FAISS indices), the evaluation fixtures and gold sets, and whether the "金标准评估 (gold standard evaluation)" claim in CLAUDE.md is backed by real numbers. Determines whether iCoDer's clinical accuracy is measurable, measured, and reproducible.

## M1. Model layer — REAL but name-drift across 4 identifiers

### M1.1 Actual model in use

`backend/app/config.py:70`:

```python
LLM_PROVIDER: str = "deepseek"
LLM_BASE_URL: str = "https://api.deepseek.com/v1"
LLM_MODEL: str = "deepseek-chat"
```

`backend/data/versions.json`:

```json
{
  "model_version": "deepseek-v4-flash (M3-0 interim, B0 prediction pending)",
  "code_dict_version": "icd10cn_code_catalog 37,897 codes (M3-0 baseline)",
  "rule_version": "medical_coding R001-R010 + MC-R-M80-001 (M3-0 baseline)",
  "agent_version": "icoder/medcoder-coding-review-agent@1.0.0",
  "data_asset_version": "iCoDerA v1.0.0"
}
```

`versions.json` claims `deepseek-v4-flash` but `config.py` ships `deepseek-chat` as the actual model identifier. **These are different identifiers** — DeepSeek's public API exposes `deepseek-chat` (the V3.x family) and `deepseek-reasoner` (R1); `deepseek-v4-flash` is not a public DeepSeek model name as of 2026-07.

### M1.2 Model name drift across the codebase

Live grep across `backend/app/` + `backend/icoder_runtime/`:

```
app/config.py:70                       LLM_MODEL: str = "deepseek-chat"
app/coding_runtime/fast_runtime.py:194 "model": ... or "deepseek-chat"
icoder_runtime/core/llm_gateway.py:288 model: str = "deepseek-chat"
icoder_runtime/providers/...           self._model = ... or "deepseek-v4"
app/icoder/agent_runtime/experts/...   model: str = "deepseek-v4"
app/icoder/agent_runtime/cdi/real_runner.py:66
                                      _PROVIDER_MODEL_ENV_DEFAULT = "deepseek-v4-flash"
app/icoder/agent_runtime/a2a/icoder_metadata.py:37
                                      "llm_model": actual model used (e.g., "deepseek-v4-flash")
data/versions.json                     "deepseek-v4-flash (M3-0 interim, B0 prediction pending)"
```

→ **4 different model identifiers** in code (`deepseek-chat`, `deepseek-v4`, `deepseek-v4-flash`, `deepseek-v4-flash (M3-0 interim...)`). Register as **G10-001 (P1)**: it is impossible to determine from the codebase alone which DeepSeek model actually runs in production. Some paths send `deepseek-v4` to DeepSeek's API which will likely 404; others send the canonical `deepseek-chat`. This drift is the kind of bug that hides accuracy regressions.

### M1.3 Embedding model — BGE-M3 (local, 1024-dim)

`backend/data/medcoder/models/` — local HuggingFace cache of `BAAI/bge-m3` (~2.3GB).

- ✅ Local inference (no API roundtrip)
- ✅ 1024-dim cosine-normalized vectors
- ✅ Used by both Stage-2 retrieval and Synonym-Expand
- ⚠️ Download is gitignored; CI runners must run `scripts/download_bge_m3.py` first

## M2. Data assets — REAL, comprehensive, single-machine dependent

### M2.1 Catalog sizes (from `E:\iCoDerA\DataAsset\`)

| Asset | Size | Records | Coverage |
|-------|------|---------|----------|
| `icd10cn_code_catalog.json` | 25 MB | 37,897 codes | Full ICD-10-CN Clinical Edition 2.0 |
| `icd10cn_synonym_map.json` | 15 MB | 75,968 synonyms + 21 term_index categories | 35,468 CN + 5,560 EN synonyms |
| `icd10cn_standard_names.json` | 5.8 MB | (standardized names dict) | — |
| `gold_disease_catalog.json` | 28 MB | 37,897 codes unified | WHO ICD-10 (1,586) + CN Clinical 2.0 (15,013 extended) + 2,430 WHO-enriched |
| `icd9cm3_code_catalog.json` | 6.4 MB | 13,617 codes | ICD-9-CM-3 procedure vol 2 (note: CLAUDE.md claims 23,165 — mismatch) |
| `icd9cm3_standard_names.json` | 1.6 MB | (standardized) | — |
| `evidence_anchoring_kb.json` | 8.2 MB | 972 codes × 6,490 patterns | **972 / 37,897 = 2.5% code coverage** |
| `coding_differentiation_kb.json` | 2.9 MB | 1,666 code-pair groups | P0/P1/P2 decision hints; only 80 clinician-verified (5%) |
| `clinical_knowledge_index.json` | 2.0 MB | (knowledge graph) | — |
| `drg_grouper.json` | 1.5 MB | CHS-DRG 1.1 | bundled into `app/services/drg_grouper.py` |
| `cot_generation_progress_v2.json` | 12 KB | 175 verified / 500 target | rerank few-shot CoT |
| `insurance_*` (gray_codes, clinical_to_insurance_map) | 200 KB | (insurance rules) | — |

### M2.2 Catalog integrity — verified via direct read

```
$ python -c "import pickle; m=pickle.load(open('data/medcoder/metadata.pkl','rb')); print(len(m), m[0])"
37897 {'code': 'A00', 'name_cn': '霍乱(由于01群霍乱弧菌引起)', 'name_en': 'Cholera',
       'chapter_no': '第1章', 'chapter_name': '某些传染病和寄生虫病',
       'chapter_range': 'A00-B99', 'category_code': 'A00',
       'clinical_category': '感染性疾病'}

$ python -c "import pickle; m=pickle.load(open('data/medcoder/metadata_icd9cm3.pkl','rb')); print(len(m), m[0])"
13617 {'code': '00.0100', 'name_cn': '头颈部血管治疗性超声',
       'category': '治疗性操作', 'chapter_no': '第00章', 'is_extended': False,
       'insurance_code': '00.0100', 'is_insurance_gray': True}
```

Both catalogs are populated, schema-valid, and load fast. This is **real data work**, not stubs.

### M2.3 KB quality — verified via `_meta` headers

`coding_differentiation_kb.json` `_meta`:

```json
{
  "name": "iCoDer Coding Differentiation Knowledge Base",
  "version": "2.5",
  "build_date": "2026-05-20",
  "total_groups": 1666,
  "source": "Auto-generated from CCL 1800-case rule evaluation error matrix",
  "baseline": {"acc_main": 0.646, "m_total": 0.599},
  "expansion": {
    "source_b_textbook": 908,
    "source_a_icd_hierarchy": 500,
    "source_c_ccl_lowfreq": 23,
    "verified": 20,
    "accepted": 0,
    "no_effect": 1411
  },
  "cc_validation": {
    "total_rules": 1496,
    "verified": 80,
    "no_ccl_data": 1408,
    "prev_high_confidence": 80,
    "new_high_confidence": 80
  }
}
```

⚠️ **1,666 differentiation rules; only 80 clinician-verified (5%)**. 1,408 have "no CCL data". Register as **G10-007 (P3)**: differentiation KB coverage is broad but shallow — most rules are auto-generated from error matrices, not clinically validated.

### M2.4 Location risk — single Windows path dependency

`backend/data/medcoder/README.md`:

```
Rebuild commands:
  cd backend
  HF_ENDPOINT=https://hf-mirror.com python scripts/download_bge_m3.py --out data/medcoder/models
  python scripts/build_medcoder_index.py --asset-dir E:/iCoDerA/DataAsset --out data/medcoder
```

The default `--asset-dir E:/iCoDerA/DataAsset` is a **Windows absolute path on the lead developer's C: drive**. CLAUDE.md §Runtime Core promises cloud asset bucket support (`ICODER_ASSET_BUCKET=icoder-assets-{region}`), but:

```python
# backend/app/config.py:102
ICODER_ASSET_BUCKET: str = ""  # S3-compatible; empty = use local DATA_DIR
```

Default empty → falls back to local DATA_DIR. No automated cloud sync; no documented bucket provisioning. Register as **G10-003 (P1)**: data assets are gitignored, single-machine dependent. A second developer, CI runner, or cloud deploy cannot reconstruct the asset state without manual `E:/iCoDerA/` access. The cloud SaaS claim is not backed by a real cloud asset store.

## M3. FAISS indices — REAL, total 2.5GB, all gitignored

### M3.1 Index files

```
data/medcoder/
├── faiss.index              149 MB   37,897 × 1024 IndexFlatIP (ICD-10-CN)
├── faiss_icd9cm3.index       54 MB   13,617 × 1024 IndexFlatIP (ICD-9-CM-3)
├── metadata.pkl              6.5 MB  aligned with faiss.index
├── metadata_icd9cm3.pkl      2.4 MB  aligned with faiss_icd9cm3.index
└── models/                   2.3 GB  BGE-M3 sentence-transformers cache
```

### M3.2 IndexFlatIP — exact inner-product, no ANN compression

Per `data/medcoder/README.md`:

> faiss.index — 37,897 × 1024 FAISS IndexFlatIP over ICD-10-CN codes

`IndexFlatIP` is the exact / brute-force variant. No quantization (IVF, HNSW, PQ). Search is O(N) per query but exact. For 37,897 codes × 1024 dims, single-query latency is sub-10ms on CPU. This is the right choice for accuracy-first retrieval at this scale.

⚠️ Register as **G10-004 (P2)**: total ~2.5GB local cache. Each new developer / CI runner must rebuild. Build time = ~8min BGE-M3 download + ~15min ICD-10 index + ~5min ICD-9-CM-3 index ≈ 30min one-time. Not a P1 — but a real friction for onboarding.

## M4. Evaluation fixtures — REAL but monoculture, no held-out test set

### M4.1 Fixture inventory (`backend/tests/fixtures/`)

| File | Count | Purpose | Source |
|------|-------|---------|--------|
| `ccl2026_train_gold.json` | 1,800 cases | CCL 2026 train, public | CCL 2026 official train split |
| `ccl2026_val_100.json` | 100 cases | CI smoke | random sample of train, seed=42 |
| `icoder_201.json` | 201 cases | Regression baseline | sample of train, seed=42, `source: icoder_201_subset` |
| `cdi_gate8_40cases.json` | 40 cases | Phase 5 Track D P0.5 calibration | 6 categories × 5-10 cases |
| `cdi_gap8_smoke10.json` | 10 cases | Smoke | subset of 40-case |
| `cdi_gate8_corti3.json` | 3 cases | Corti cross-platform subset | subset of 40-case |

### M4.2 CDI gate8_40 categories

`cdi_gate8_40cases.json` `_meta`:

```json
{
  "purpose": "Phase 5 Track D P0.5 Gate 8 — 40-case Corti Teacher Calibration",
  "spec": "Master Task §9.4",
  "categories": {
    "clear_gap": 10, "complete_chart": 10, "insufficient_evidence": 5,
    "negation_history": 5, "document_conflict": 5, "lab_positive_uncertain": 5
  },
  "dimensions_covered": ["type","etiology","severity","acuity","site","course",
                         "complication","count","correlation","unknown"],
  "language_constraint": "Bilingual — chart_zh for iCoDer, chart_en for Corti",
  "deidentification": "Per §9.3 — no names, IDs, phones, addresses"
}
```

- ✅ 6 categories, 10 dimensions, bilingual, deidentified
- ⚠️ All 40 cases are synthetic-derived from the same CCL 2026 train corpus

### M4.3 F1 numbers actually in the repo

`backend/data/medcoder/eval_e20_smoke.json` (5-case smoke):

```json
{
  "summary": {
    "variant": "full",
    "n_cases": 5,
    "total_elapsed_s": 295.1,
    "avg_latency_s": 59.025,
    "f1_at_1": 0.15,
    "f1_at_2": 0.1644,
    "f1_at_5": 0.1498
  }
}
```

`backend/data/medcoder/e2e_regression_check.json` (5-case regression):

```json
{
  "summary": {
    "variant": "full",
    "n_cases": 5,
    "f1_at_1": 0.15,
    "f1_at_2": 0.1608,
    "f1_at_5": 0.1734
  }
}
```

**These are the only quantitative medical-coding accuracy numbers in the entire repo.**

- F1@1 = **0.15** — i.e., the full MedCodER 5-stage pipeline produces the correct primary code as top-1 in only **15% of 5 smoke cases**.
- F1@5 = **0.15-0.17** — the gold code appears anywhere in top-5 in only 15-17% of cases.
- This is **catastrophically low** for a production medical-coding product. Even random guess over 37,897 codes ≈ 0.00003; 0.15 is meaningful but far below the >0.85 F1 industry baseline for ICD coding assistants.

Register as **G10-002 (P0)**: the only persisted F1 numbers in the repo are 5-case smoke results showing F1@1 = 0.15. The 201-case baseline the CLAUDE.md "金标准评估" section promises is documented as a script but **its results are not persisted anywhere**. There is no production-scale F1 number for the medical-coding product.

### M4.4 CDI Track H iter 7 metrics — better-documented but no F1

`reports/track_h/h4_benchmark_candidate_rc5/MANIFEST.json`:

```json
{
  "candidate_version": "icoder-cdi-agent-v1.0.0-rc5",
  "frozen_at_utc": "2026-07-13T12:36:58Z",
  "git_commit": "0d759e5533223594941ceb0c46c8a4df7c244f40",
  "iter": 7,
  "tier": "PASS_CALIBRATION_TUNING_ITERATION_7",
  "case_count": 40,
  "headline_metrics": {
    "iter_7_avg_queries_per_case": 1.0,
    "iter_7_icoder_range_conformance": "37/40 (93%)",
    "iter_7_agreement_rate_vs_corti": 0.75,
    "iter_7_avg_abs_query_count_delta": 1.0,
    "iter_7_multi_dim_leaked_total": 0,
    "iter_7_complete_chart_over_query": "0/10",
    "iter_7_clear_gap_under_query": "1/10",
    "iter_7_evidence_quote_verbatim": 0.975,
    "iter_7_unsupported_query_rate": ...
  }
}
```

CDI agent on 40-case fixture:
- range_conformance 93% (37/40 cases within Corti-teacher query-count range)
- agreement_rate vs Corti 0.75
- avg |Δqueries| 1.0
- multi_dim_leaked 0 (safety)
- evidence verbatim 0.975
- complete_chart over-query 0/10 (no false alarms)

This is real, methodologically honest calibration work — **but it is CDI calibration, not medical-coding accuracy**. The CDI agent generates clarification queries; it does not produce ICD codes. The medical-coding F1 problem (G10-002) is unsolved.

### M4.5 Track H tier ceiling — explicitly below formal quality benchmark

Per Track H Tier 2 closure memory: `verdict tier = PASS_CALIBRATION_TUNING_ITERATION_7` which is explicitly **below** `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK`. The repo's own audit conclusion is that CDI accuracy is not yet ready for formal quality benchmark. Medical-coding accuracy is in worse shape (no benchmark exists at all).

Register as **G10-005 (P2)**: evaluation is monoculture — every fixture (smoke10, val_100, icoder_201, gate8_40, corti3) is derived from CCL 2026 train. **No held-out test set. No real hospital data.** Cross-validation against the same train set the differentiations KB was generated from will systematically overstate accuracy.

## M5. Provenance & licensing — opaque

### M5.1 CCL 2026 train corpus

`ccl2026_train_gold.json` 1,800 cases is from CCL 2026 (China Computational Linguistics conference) — public, but **license terms for hospital deployment are not documented** in the repo. Is commercial use allowed? Is redistribution to hospital partners allowed? Unknown.

### M5.2 iCoDerA DataAsset

`E:\iCoDerA\DataAsset\` contains 18+ JSON assets totaling >100MB. No `LICENSE`, `README.md`, or `PROVENANCE.md` at the asset root. CLAUDE.md notes "数据资产 (只读;本地开发 / CI/eval 用 E:\iCoDerA\)" but does not document:

- Where each asset came from (manual curation vs auto-generation)
- Whether hospital data was used in synthesis
- Whether deidentification is certified (HIPAA Safe Harbor / GB/T 35273-2020)
- Update frequency / data drift policy

Register as **G10-006 (P2)**: data provenance is undocumented. For a hospital-deployment product, every dataset that influences clinical output must carry a LICENSE + PROVENANCE + DEIDENTIFICATION_CERTIFICATE. The repo has none.

### M5.3 No real patient data — confirmed

Per fixture metadata: "no names, IDs, phones, addresses". All eval cases are synthetic-derived. **Zero real hospital patient data in the repo.** This is good for compliance but means the eval is testing on a distribution that may not match production traffic.

## M6. New findings

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G10-001** | P0 | model-identity | **Only persisted medical-coding F1 numbers in the repo: F1@1 = 0.15, F1@5 = 0.15-0.17 (5-case smoke).** No 201-case baseline results persisted anywhere. CLAUDE.md "金标准评估" section promises ongoing F1 tracking; not backed by evidence. |
| **G10-002** | P1 | model-drift | 4 different model identifiers in code (`deepseek-chat`, `deepseek-v4`, `deepseek-v4-flash`, `deepseek-v4-flash (M3-0 interim)`). `config.py` ships `deepseek-chat`; `versions.json` claims `deepseek-v4-flash`. Impossible to determine which model actually runs. Some paths may 404 against DeepSeek's public API. |
| **G10-003** | P1 | asset-portability | Data assets are gitignored + single-machine Windows path (`E:\iCoDerA\DataAsset`). No cloud asset bucket wired by default; CLAUDE.md's `ICODER_ASSET_BUCKET` claim is not implemented. New developers / CI / cloud deploys cannot reconstruct asset state without manual file transfer. |
| **G10-004** | P2 | asset-portability | 2.5GB local cache (FAISS indices + BGE-M3). Onboarding cost ~30min one-time rebuild per machine. |
| **G10-005** | P2 | eval-monoculture | Every evaluation fixture (smoke10, val_100, icoder_201, gate8_40, corti3) derived from CCL 2026 train. No held-out test set. Differentiation KB also derived from CCL train error matrix → systematic overstatement of accuracy. |
| **G10-006** | P2 | provenance | No LICENSE / README / PROVENANCE / DEIDENTIFICATION_CERTIFICATE for `iCoDerA/DataAsset/`. Unknown license terms for hospital deployment. CCL 2026 commercial-use terms not documented. |
| **G10-007** | P3 | kb-coverage | `evidence_anchoring_kb` covers 972 / 37,897 ICD codes (2.5%). `coding_differentiation_kb` has 1,666 rules; only 80 clinician-verified (5%). KBs are broad but shallow. |
| **G10-008** | P3 | cdi-tier-ceiling | Track H Tier 2 memory explicitly notes CDI verdict is **below** `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK`. Combined with G10-001 (no medical-coding F1), neither core product has a production-grade accuracy benchmark. |
| G10-009 | P3 | minor-count | CLAUDE.md claims 23,165 ICD-9-CM-3 codes; `icd9cm3_code_catalog.json` has 13,617 codes. Either the doc is stale or the catalog is incomplete. |

## M7. Track-level verdicts (interim)

| Sub-track | Verdict |
|-----------|---------|
| **M1 Model** | `DEEPSEEK_REAL_BUT_NAME_DRIFT_4_IDENTIFIERS` — Real DeepSeek integration; `deepseek-chat` actual; `deepseek-v4-flash` claimed; `deepseek-v4` references in expert code |
| **M2 Catalogs** | `REAL_37897_ICD10CN_+_13617_ICD9CM3` — Full ICD-10-CN Clinical Edition 2.0; BGE-M3 embedding; KBs are broad-but-shallow |
| **M3 Indices** | `REAL_INDEXFLATIP_2_5GB_GITIGNORED` — Exact ANN, sub-10ms latency, gitignored, single-machine dependent |
| **M4 Evaluation** | `F1_0_15_5CASE_SMOKE_ONLY_NO_201_BASELINE` — CDI calibration is methodologically sound (Track H iter7 rc5); medical-coding F1 is undocumented at scale |
| **M5 Provenance** | `UNDOCUMENTED_NO_LICENSE_NO_PROVENANCE` — Synthetic cases only; no real patient data; asset licensing opaque |

## M8. Gate 10 verdict

`CATALOGS_AND_INDEXES_REAL_BUT_MODEL_IDENTITY_DRIFTING_AND_F1_BASELINE_MISSING`

Specifically:

- ✅ ICD-10-CN Clinical Edition 2.0 (37,897 codes) — complete and schema-valid
- ✅ ICD-9-CM-3 (13,617 codes) — complete
- ✅ FAISS IndexFlatIP exact retrieval, ~2.5GB cache
- ✅ BGE-M3 local embeddings (no API roundtrip)
- ✅ CDI Track H iter7 rc5 has methodologically sound 40-case calibration (agreement 0.75, range_conformance 93%, multi_dim_leaked 0)
- ❌ **G10-001 P0**: medical-coding F1@1 = 0.15 on 5-case smoke; no 201-case baseline persisted; "金标准评估" claim is unbacked
- ❌ **G10-002 P1**: 4 different model identifiers in code (`deepseek-chat` / `deepseek-v4` / `deepseek-v4-flash` / `deepseek-v4-flash (M3-0 interim)`)
- ❌ **G10-003 P1**: data assets are gitignored + single Windows-path dependent; cloud asset bucket claim is unimplemented
- ⚠️ Track H CDI tier is explicitly below `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK`
- ⚠️ No held-out test set; differentiation KB derived from train error matrix
- ⚠️ No LICENSE / PROVENANCE / DEIDENTIFICATION_CERTIFICATE for the asset bundle

Gate 10 closes. Proceed to **Gate 11 — Test, Performance, Deployment and Docs**.
