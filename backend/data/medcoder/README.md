# MedCodER Retrieval Assets

This directory holds the **FAISS indices + metadata + BGE-M3 model cache** that back MedCodER's Stage 2 retrieval (and any other method that wants ANN over the ICD catalog).

## What lives here

| Path | Purpose | Source | Rebuild command |
|---|---|---|---|
| `faiss.index` | 37,897 × 1024 FAISS IndexFlatIP over ICD-10-CN codes | `scripts/build_medcoder_index.py` | see below |
| `metadata.pkl` | List[dict] aligned with `faiss.index` — code, name_cn, name_en, chapter_no, chapter_name, chapter_range, category_code, clinical_category | same | same |
| `faiss_icd9cm3.index` | 13,617 × 1024 FAISS IndexFlatIP over ICD-9-CM-3 procedure codes | `scripts/build_medcoder_icd9cm3_index.py` | see below |
| `metadata_icd9cm3.pkl` | List[dict] aligned with `faiss_icd9cm3.index` | same | same |
| `models/` | Local BGE-M3 (`BAAI/bge-m3`) sentence-transformers cache | `scripts/download_bge_m3.py` | see below |
| `README.md` | This file | (committed) | n/a |
| `*.log` | Build logs (gitignored) | scripts output | n/a |

## Sizes (approximate)

| Asset | Size |
|---|---|
| `faiss.index` | ~148 MB |
| `metadata.pkl` | ~6.5 MB |
| `faiss_icd9cm3.index` | ~53 MB |
| `metadata_icd9cm3.pkl` | ~1.5 MB |
| `models/` (BGE-M3 cache) | ~2.3 GB |

These are **gitignored** (see root `.gitignore`) because of size. Each developer / CI runner must rebuild them locally before running MedCodER.

## Rebuild commands

```bash
cd backend

# 1. Download BGE-M3 (one-time, ~8 min on 5 MB/s link)
HF_ENDPOINT=https://hf-mirror.com python scripts/download_bge_m3.py --out data/medcoder/models

# 2. Build ICD-10-CN FAISS index (~10-15 min CPU after model is loaded)
python scripts/build_medcoder_index.py --asset-dir E:/iCoDerA/DataAsset --out data/medcoder

# 3. Build ICD-9-CM-3 FAISS index (~5 min CPU)
python scripts/build_medcoder_icd9cm3_index.py --asset-dir E:/iCoDerA/DataAsset --out data/medcoder
```

> **Note**: CPU-only build takes ~10-15 min for ICD-10 (37,897 codes) after the model is loaded. With GPU it is roughly 10× faster.

## Verification

After rebuilding, verify with the index-health module:

```bash
cd backend
python -c "from app.services.medcoder_index_health import check_index_health; print(check_index_health())"
```

A healthy response returns:

```python
{
  "status": "ok",     # or "degraded"
  "faiss_index": {"exists": True, "ntotal": 37897, "dim": 1024},
  "metadata": {"exists": True, "len": 37897},
  "model_cache": {"exists": True, "has_pytorch_model": True},
  "errors": []
}
```

Or run the dedicated test:

```bash
pytest backend/tests/test_services/test_medcoder_index_health.py -v
```

## Why this layout

- **Single source of truth** for retrieval assets: scripts and tests reference `data/medcoder/` exclusively.
- **Rebuild is idempotent** — re-running the build scripts overwrites prior outputs; nothing is destroyed silently.
- **No silent disappearance** — the previous incident (2026-06-19) where `faiss.index` / `metadata.pkl` / `models/` vanished without an audit trail is now guarded by:
  - `.gitignore` policy (assets never enter git, so git operations cannot delete them)
  - `medcoder_index_health.py` startup check (`app.state.medcoder_index_health.status`)
  - Test gate `test_medcoder_index_health.py` (5 cases)
- **Tests run offline**: when assets are missing the index-health check reports `degraded` and the runtime / tests explicitly fail loud rather than silently degrading.

## When the assets are missing in production

The runtime surfaces an HTTP `-32002 Retriever Unavailable` error (per MCP error spec) on every retrieval call. UI shows a banner: "FAISS 索引未加载 — 请运行 scripts/build_medcoder_index.py". No silent fall-through.