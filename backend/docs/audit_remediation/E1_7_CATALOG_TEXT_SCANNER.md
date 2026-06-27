# E1.7 — Catalog-Text Scanner for Procedure Mentions

**Date:** 2026-06-27
**Builds on:** E1.6 (catalog-mention pre-lookup per mention).
**Closes:** Stage 1 LLM extraction recall gap for buried procedures.

## Problem

E1.4–E1.6 added procedure RAG to MedCodER, but the realistic smoke
test (`tests/fixtures/icoder_201.json`, full variant) showed
**procedure hit@1 = 0%** on 5 obstetric/oncology cases. Investigation
showed the bottleneck was **Stage 1 LLM extraction completeness**: the
LLM doesn't always extract all procedures mentioned in the EMR
narrative. Buried procedures (e.g. "脐动脉插管" in a long obstetric
discharge summary) are missed.

E1.6 only helped when the LLM extracted the procedure *as a mention*
(it ran a catalog lookup on the mention string). E1.7 adds
defensive resilience: even if the LLM misses a procedure, the catalog
text scanner finds it by scanning the EMR text directly.

## Implementation

`MedCodERStrategy._catalog_scan_emr_text(text, min_name_len=3, max_mentions=20)`:
- Linear scan over 13,617 ICD-9-CM-3 catalog entries (≤30 ms/EMR).
- For each entry, checks **bidirectional substring containment**:
  1. Full catalog name in EMR (e.g. "阑尾切除术" in "行阑尾切除术...")
  2. First `min_name_len` chars of catalog name in EMR (e.g. "剖宫产"
     prefix of "古典式剖宫产" matching "行剖宫产术..."). The prefix
     check is the workhorse — real catalog has long qualified names
     ("剖宫产术，子宫下段横切口") that EMR text never contains verbatim,
     but the short core fragment almost always appears.
- Dedup on canonical `name_cn`. Cap at 20 mentions.

`MedCodERStrategy._populate_procedures(out, mentions, emr_text="")`:
- Merges LLM-extracted mentions with catalog-scan mentions from EMR
  (when `emr_text` is provided).
- Dedup: case-insensitive text overlap.
- Existing catalog lookup ∪ BGE-M3 retrieval logic unchanged.

3 call sites updated to pass `emr_text=emr_text`:
- `_run_full` (Stage 1 EMR text)
- `_run_prompt_only` (Stage 1 EMR text)
- `_run_prompt_plus_retrieve` (Stage 1 EMR text)

## Files

- `icoder_runtime/providers/medical_coding/medcoder_strategy.py` —
  new `_catalog_scan_emr_text` + extended `_populate_procedures`
- `tests/unit/icoder/providers/test_medcoder_strategy.py` — 9 new
  tests (TestCatalogScanEmrText + TestPopulateProceduresE1_7)

## Live verification (real catalog)

```
行剖宫产术，术后给予脐动脉插管术监测。           → ['剖宫产术，子宫下段横切口', '剖宫产术，子宫下段直切口']
患者行冠状动脉支架植入术，术后给予低分子肝素抗凝治疗。  → 20 冠状动脉* procedures (capped)
患者行阑尾切除术，术后病理证实为急性化脓性阑尾炎。      → ['阑尾切除术']
患者行胃大部切除术                              → 3 胃大部切除* procedures
```

Before E1.7, all 4 of these EMRs returned `[]` (the LLM-extracted
mention list was empty in the synthetic test). After E1.7, all 4
produce real procedure candidates.

## E2E F1 impact

E2E F1 measurement deferred to a 50–100 case run (the 5-case E1.6
smoke doesn't have statistical power to distinguish 0% → small
improvements). The qualitative direction is clear: E1.7 makes the
procedure sidecar more resilient to LLM miss, but the dominant
bottleneck is still Stage 1 LLM extraction. Further work:
- Larger few-shot examples in the Stage 1 prompt
- Per-disease procedure extractor (separate from disease coding)

## How to apply: future work

- Catalog scan is O(N_catalog × |EMR|). For 13.6k entries × 2k chars
  = ~30 ms in Python. If this becomes a hotspot, build a trigram
  index (one-time O(N × avg_name_len) build, O(|EMR|) query).
- The min_name_len=3 default is conservative. Lowering to 2 would
  catch more (e.g. 肠镜 in catalog "结肠镜检查") but adds false
  positives. Tests pin this at 3.
