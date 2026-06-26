# M2.5 Phase 1 — INDEX_AUDIT.md (2026-06-22)

## TL;DR

| Asset | Path | Status | Size | Records | Action |
|-------|------|--------|------|---------|--------|
| ICD-10-CN code catalog | `E:/iCoDerA/DataAsset/icd10cn_code_catalog.json` | ✅ OK | 25.0 MB | 37,897 codes | rebuild FAISS |
| ICD-10-CN synonym map | `E:/iCoDerA/DataAsset/icd10cn_synonym_map.json` | ✅ OK | 14.6 MB | 56,424 term-index entries | rebuild FAISS |
| ICD-9-CM-3 code catalog | `E:/iCoDerA/DataAsset/icd9cm3_code_catalog.json` | ✅ OK | 6.3 MB | 13,617 codes | rebuild FAISS (NEW) |
| Gold disease catalog | `E:/iCoDerA/DataAsset/gold_disease_catalog.json` | ✅ OK | 27.9 MB | 37,897 entries | rebuild FAISS |
| Coding differentiation KB | `E:/iCoDerA/DataAsset/coding_differentiation_kb.json` | ✅ OK | 2.9 MB | 2,090 groups | orthogonal (Stage 3) |
| **FAISS index (ICD-10)** | `data/medcoder/faiss.index` | ❌ **MISSING** (was 148 MB, ntotal=37897) | — | — | **rebuild required** |
| **FAISS metadata** | `data/medcoder/metadata.pkl` | ❌ **MISSING** (was 6.5 MB) | — | — | **rebuild required** |
| **FAISS index (ICD-9-CM-3)** | `data/medcoder/faiss_icd9cm3.index` | ❌ **NEVER EXISTED** | — | — | **build new script** |
| **BGE-M3 model cache** | `data/medcoder/models/` | ❌ **MISSING** (was 2.3 GB) | — | — | re-download on first use |
| **BGE-M3 in HF Hub** | `~/.cache/huggingface/hub/` | ❌ **MISSING** (only `bge-large-zh-v1.5` present) | — | — | re-download on first use |

## Defect timeline

| Date (UTC+8) | Event |
|---|---|
| 2026-06-08 00:19:33 | `data/medcoder/faiss.index` (148.0 MB) + `metadata.pkl` (6.5 MB) built successfully — `ntotal=37897 dim=1024`, total build time **13898.6s ≈ 3h 51min** on CPU. BGE-M3 cache written to `data/medcoder/models/` (~2.3 GB). |
| 2026-06-19 22:33:19 | `data/medcoder/` directory mtime — `faiss.index` + `metadata.pkl` + `models/` removed. **No error logged, no audit trail.** |
| 2026-06-22 14:57:37 | M2 eval hits `Stage 2 retrieve failed: FAISS index not found at data/medcoder/faiss.index` for every case. F1@1=0.0921. |

## Detailed asset inventory

### Read-only source assets (`E:/iCoDerA/DataAsset/`) — all healthy

| File | Size | Records | Last modified | Schema |
|------|------|---------|---------------|--------|
| `icd10cn_code_catalog.json` | 25,996,500 B (24.8 MB) | 37,897 codes | 2026-05-19 00:11 | `{_meta, chapters:22, codes:[{code, name_cn, name_en, synonyms_cn, synonyms_en, chapter_range, chapter_no, chapter_name, category_code, is_extended, is_dagger_asterisk, is_generated_category, clinical_category, synonym_count_cn, synonym_count_en, is_insurance_gray}, ...]}` |
| `icd10cn_synonym_map.json` | 15,292,266 B (14.6 MB) | 56,424 term-index entries (21 categories) | 2026-05-18 23:06 | `{_meta, synonyms:{21 categories}, term_index:{56,424 entries}}` |
| `icd9cm3_code_catalog.json` | 6,641,225 B (6.3 MB) | 13,617 codes (92 v2→v3 mappings) | 2026-05-19 00:11 | `{_meta, chapters:18, v2_to_v3:{92}, codes:[...]}` |
| `gold_disease_catalog.json` | 29,231,518 B (27.9 MB) | 37,897 entries | 2026-05-27 10:23 | top-level dict (length 3) |
| `coding_differentiation_kb.json` | 3,004,588 B (2.9 MB) | 2,090 groups | 2026-05-21 14:22 | `{_meta, groups:[...]}` (orthogonal to FAISS — used by MedCodER Stage 3 Merge, in-process lookup, no index needed) |
| `icd10cn_standard_names.json` | 5,990,261 B (5.7 MB) | — | 2026-05-18 22:54 | (not used by current build script) |
| `icd9cm3_standard_names.json` | 1,629,429 B (1.6 MB) | — | 2026-05-18 23:42 | (not used by current build script) |
| `icd9cm3_enhanced/` (alt) | — | 13,617 codes | — | V2 catalog at `E:/iCoDerA/data/icd9cm3_enhanced/icd9cm3_code_catalog.json` |
| `evidence_anchoring_kb.json` | 8,533,296 B (8.1 MB) | — | 2026-05-21 14:22 | (orthogonal — pattern matching, no FAISS) |
| `cot_generation_progress_v2.json` | 10,995 B | 175 verified CoT samples | 2026-05-24 17:43 | (M3 — few-shot rerank) |

### Build artifacts (`data/medcoder/`) — **all missing**

| File | Last known size | Last known mtime | Current status |
|------|-----------------|------------------|----------------|
| `faiss.index` | 148.0 MB | 2026-06-08 00:19 | ❌ **MISSING** (no record) |
| `metadata.pkl` | 6.5 MB | 2026-06-08 00:19 | ❌ **MISSING** |
| `models/` (BGE-M3 cache) | ~2,300 MB | 2026-06-08 ~00:28 | ❌ **MISSING** (dir not present) |
| `build.log` | 1,979 B | 2026-06-08 00:19 | ✅ present — last successful build log |
| `faiss_icd9cm3.index` | — | never | ❌ **NEVER BUILT** (script doesn't exist) |

### HuggingFace Hub cache — `C:/Users/huawei/.cache/huggingface/hub/`

| Model dir | Status |
|-----------|--------|
| `models--BAAI--bge-m3` | ❌ **MISSING** — must re-download ~2.3 GB on first use |
| `models--BAAI--bge-large-zh-v1.5` | ✅ present (different model — 0.4 GB, not BGE-M3) |
| `models--sentence-transformers--all-MiniLM-L6-v2` | ✅ present |
| `models--Systran--faster-whisper-small.en` | ✅ present |

## Phase 2 plan preview

- **Re-build ICD-10-CN FAISS** — re-run `scripts/build_medcoder_index.py --asset-dir E:/iCoDerA/DataAsset --out data/medcoder`. Expected: ~3.85 hr on CPU, 148 MB index + 6.5 MB metadata + 2.3 GB model cache.
- **Build ICD-9-CM-3 FAISS (NEW script)** — `scripts/build_medcoder_icd9cm3_index.py`. Mirrors ICD-10 build but reads `icd9cm3_code_catalog.json`. Output: `data/medcoder/faiss_icd9cm3.index` + `metadata_icd9cm3.pkl`. 13,617 codes × 1024-dim ≈ 53 MB index + 1.5 MB metadata (estimated).

## Phase 3 plan preview

- New `app/services/medcoder_index_health.py` (NO silent continue) — checks `faiss.index` exists + loads + ntotal>0 + dim=1024 + metadata.pkl len matches ntotal.
- Wire to `app/main.py` startup; mark `app.state.medcoder_index_health.status = "degraded"` on any check failure; downstream calls return `-32002 Retriever Unavailable`.
- 5 unit tests: ok / missing faiss / missing metadata / ntotal=0 / dim mismatch.

## Phase 4 plan preview

- `tests/integration/icoder/retrieval/test_smoke_recall.py` — 5 anchors:
  - 骨质疏松 → expect M80.x family
  - 糖尿病 → expect E10/E11 family
  - 肺炎 → expect J12-J18 family
  - 剖宫产 → expect O82 / 74.x family
  - 阑尾切除术 → expect 47.0 / 47.1 family (ICD-9-CM-3)

## Risks / notes

- **R1 (BGE-M3 download)**: HuggingFace reachable? First-run download of 2.3 GB may take 5-30 min depending on bandwidth.
- **R2 (CPU-only)**: No GPU detected (`nvidia-smi` not in PATH). Rebuild will take ~3.85 hr (per prior build log: 13898.6s for ICD-10 alone). Total wall time: ~3.85 hr ICD-10 + ~1.4 hr ICD-9-CM-3 ≈ 5.25 hr.
- **R3 (Disk)**: 50 GB free on E: — 2.3 GB model + 148 MB index + 6.5 MB metadata + ~60 MB ICD-9 ≈ 2.5 GB. **No constraint.**
- **R4 (HF rate limits)**: if rate-limited, mirror to a local snapshot dir. Out of scope for M2.5.
