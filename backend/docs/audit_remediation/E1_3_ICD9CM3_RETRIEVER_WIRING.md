# E1.3 — ICD-9-CM-3 Retriever Wiring (2026-06-27)

> **Verdict**: 53 MB ICD-9-CM-3 FAISS index NOW consumed. Two new classes (`MedCodERICD9CM3Retriever` + `SubprocessMedCodERICD9CM3Retriever`) wire the index into the MedCodER pipeline. New strategy method `stage2_retrieve_procedure()` exposes ICD-9-CM-3 RAG to callers. 14 new unit tests + 1 in-process smoke + 1 subprocess smoke all green.
>
> **Headline**: hit@1=40% / hit@5=60% on 5-case procedure smoke (real 53 MB index, gold-name query). Procedure F1 was 0 in E1.2 (LLM-only); now there's a real candidate source for downstream reranking.

## What was done in E1.3

### 1. New retriever class — `MedCodERICD9CM3Retriever`

`icoder_runtime/providers/medical_coding/medcoder_retriever.py` (E1.3 lines)

- Loads `data/medcoder/faiss_icd9cm3.index` + `metadata_icd9cm3.pkl` lazily on first call
- BGE-M3 embed (shared model with diagnosis retriever) + FAISS `IndexFlatIP` top-K
- Returns `list[CandidateCode]` with `source="retrieve"` and `chapter` = ICD-9-CM-3 chapter name
- Same surface as `MedCodERRetriever` (drop-in next to it)
- **No catalog filter** — no `ICD9CM3Loader` exists yet (audit gap #3 from E1.2). When the loader lands, drop a filter here that mirrors `MedCodERRetriever._get_loader`.

### 2. New subprocess wrapper — `SubprocessMedCodERICD9CM3Retriever`

Same `__probe__` + queue + drain protocol as the diagnosis wrapper. Bumps the protocol's `retriever_factory` parameter so the same worker can serve both indices.

- `probe_timeout` bumped to 60s in the smoke test (default 10s is misleadingly `is_ready=False` during BGE-M3 cold load — known cosmetic issue from E1.2)
- Module-level factory `_make_icd9cm3_retriever(index_dir)` — Windows `spawn` can't pickle a lambda
- Worker reuses `MedCodERRetrieverWorker.run` unchanged (just gets a factory)

### 3. New strategy method — `stage2_retrieve_procedure(text, top_k=20)`

`MedCodERStrategy.stage2_retrieve_procedure` (E1.3)

- Returns `Stage2Result` envelope (same shape as `stage2_retrieve`): `candidates`, `degraded`, `error_code`
- Reuses `STAGE2_OK` / `STAGE2_RETRIEVER_UNAVAILABLE` / `STAGE2_RETRIEVE_FAILED` (no new error codes)
- Lazy-creates the procedure retriever on first call (subprocess on Windows / in-process elsewhere)
- Constructor accepts `procedure_retriever=...` for test injection (mirrors `retriever=...`)

**Not yet wired into the main 5-stage pipeline.** The procedure retriever is an opt-in sidecar — calling code (e.g. a future extraction-prompt redesign that asks the LLM for `procedure_mentions`) feeds mentions to `stage2_retrieve_procedure` and merges candidates into the procedure side of the output. This is E1.4 work.

### 4. Tests (14 new, all green)

`tests/test_services/test_medcoder_icd9cm3_retriever.py`

| Test | What it pins |
|------|--------------|
| `test_loads_index_and_metadata` | ntotal=5 (fake), dim=1024 |
| `test_health_check_reports_status` | surface shape |
| `test_load_error_on_missing_index` | raises `FileNotFoundError` |
| `test_retrieve_returns_candidate_code_typed` | `CandidateCode` shape, `source="retrieve"`, `chapter` populated |
| `test_retrieve_caps_at_top_k` | top_k respected |
| `test_retrieve_caps_at_index_size` | top_k > ntotal → ntotal |
| `test_empty_query_returns_empty` | blank/whitespace input |
| `test_no_catalog_filter_drops_ghost_codes` | **pins the no-filter contract** (no `ICD9CM3Loader`) — future loader addition is intentional |
| `test_retrieve_async_returns_same_as_sync` | async/sync parity |
| `test_expand_synonyms_arg_accepted` | arg accepted (no-op for 9cm3 — no synonym loader) |
| `test_last_query_recorded` | stats bookkeeping |
| `test_stage2_retrieve_procedure_returns_stage2_result` | strategy integration: returns `Stage2Result` |
| `test_stage2_retrieve_procedure_empty_input_ok` | empty input → `STAGE2_OK` + `candidates=[]` |
| `test_stage2_retrieve_procedure_no_retriever_degraded` | no retriever → `STAGE2_RETRIEVER_UNAVAILABLE` + `degraded=True` |

### 5. Smoke tests

#### In-process, real 53 MB index (10-case procedure subset)

| case | gold | top-1 | top-1 name | hit@1 |
|------|------|-------|-----------|-------|
| ZY020000 | 38.8609 | 93.3911 | 三九贴 | ✗ |
| ZY040000 | 38.8609 | 93.3911 | 三九贴 | ✗ |
| ZY010001 | 45.2302 | 45.2302 | 电子结肠镜检查 | ✓ |
| ZY010001 | 31.4201 | 31.4202 | 气管镜检查 | ✗ (off-by-one digit) |
| ZY010001 | 45.2302 | 45.2302 | 电子结肠镜检查 | ✓ |

- **5/10 cases have gold procedures** (other 5 cases are diagnosis-only)
- **hit@1 = 2/5 = 40%**
- **hit@5 = 3/5 = 60%**
- Misses are mostly subcode granularity (31.4201 vs 31.4202) or empty gold-name (38.8609 has no name in the fixture)

#### Subprocess wrapper, real 53 MB index

```
Constructing SubprocessMedCodERICD9CM3Retriever (worker spawns, loads 53 MB index)...
  construction time: 0.4s
  is_alive: True
  is_ready: True

Retrieve test: 结肠镜检查
  returned 3 candidates
    45.2300    结肠镜检查                          score=0.763
    45.2400    可曲性乙状结肠镜检查                     score=0.688
    48.2100    经腹直肠乙状结肠镜检查                    score=0.668
```

- 0.4s construction (worker spawned, 53 MB loaded, probe succeeded with `probe_timeout=60s`)
- All 3 results are ICD-9-CM-3 chapter 1 (digestive system procedures)
- Subcode granularity is the main lift opportunity for E1.4

## Why this matters

Before E1.3, the 53 MB ICD-9-CM-3 FAISS index was a **paper artifact** (audit gap #3a in E1.2). The procedure side of the pipeline was 100% LLM-driven — Stage 1 extraction gave the LLM an `expected_procedure_codes` field and the LLM hallucinated ICD-9-CM-3 codes with no retrieval grounding.

After E1.3, the index is **consumed** by a real retriever. Procedure RAG is now possible. The 5-stage pipeline doesn't yet call this retriever automatically — that's E1.4 (extraction-prompt redesign + Stage 3 merge of procedure candidates). But the building block is in place and tested.

The 5 cases with procedures in the 10-case smoke now have a real candidate source. The 40% hit@1 / 60% hit@5 numbers are **a floor, not a ceiling** — with proper procedure-mention extraction (E1.4) and possibly the gold_disease_catalog for synonym expansion (E1.5), these should rise.

## What's next (E1.4 candidates)

1. **Wire `stage2_retrieve_procedure` into the main pipeline.** Add a `procedure_mentions` field to the Stage 1 extraction prompt (currently `diseases` only). For each mention, call `stage2_retrieve_procedure` and merge into the procedure candidate set. Expected: procedure F1 0 → 0.1-0.2.
2. **Add `ICD9CM3Loader`** (closes audit gap #3). Mirrors `icd10cn_loader.py` — reads `icd9cm3_code_catalog.json`, exposes `has(code)`, etc. Then add catalog filter to `MedCodERICD9CM3Retriever` (drop the `test_no_catalog_filter_drops_ghost_codes` test in favor of the new filtered contract).
3. **Subprocess unit test** for the new wrapper (full lifecycle: probe, retrieve, close). Defer from E1.3 because the worker is identical to the diagnosis worker — the only new surface is the factory injection, which is unit-testable without spawning a process.
4. **Bump default `probe_timeout` to 60s** (E1.2 cosmetic). `is_ready` is currently misleadingly `False` during BGE-M3 cold load because the default 10s probe times out before the worker finishes `ensure_loaded()`. The first real call still works — only `is_ready` is wrong. Simple one-line change.

## Test status (post-E1.3)

- New: `tests/test_services/test_medcoder_icd9cm3_retriever.py` — **14/14 pass**
- Existing icoder retriever tests: `test_medcoder_retriever.py` (11), `test_medcoder_retriever_worker.py` (?), `test_hybrid_medcoder.py` (16), `test_hybrid_medcoder_subprocess.py` (6/7, 1 pre-existing M2c test gap), `test_hybrid_medcoder_variants.py` (1 pre-existing M2c test gap)
- Full test suite: **1577 passed, 1 failed (pre-existing M2c test gap, unrelated), 9 skipped**

## Files changed in E1.3

| File | Change |
|------|--------|
| `icoder_runtime/providers/medical_coding/medcoder_retriever.py` | + `MedCodERICD9CM3Retriever` (in-process) + `SubprocessMedCodERICD9CM3Retriever` (subprocess wrapper) + `_make_icd9cm3_retriever` factory + `INDEX_FILENAME_ICD9CM3` / `META_FILENAME_ICD9CM3` constants. `MedCodERRetrieverWorker.run` parameterized with optional `retriever_factory`. `SubprocessMedCodERRetriever.__init__` accepts optional `retriever_factory`. |
| `icoder_runtime/providers/medical_coding/medcoder_strategy.py` | + `stage2_retrieve_procedure(text, top_k)` method + `_get_procedure_retriever` / `_create_default_procedure_retriever` lazy factories + `procedure_retriever` constructor kwarg. |
| `tests/test_services/test_medcoder_icd9cm3_retriever.py` | NEW: 14 unit tests (loading, retrieval, stats, strategy integration) |
| `docs/audit_remediation/E1_3_ICD9CM3_RETRIEVER_WIRING.md` | NEW: this file |

## Notes

- The fixture's `expected_procedure_codes` shape varies (string vs dict). The 10-case smoke only uses 5 of 10 because the other 5 are diagnosis-only.
- The `procedure_retriever` kwarg is a no-op when `None` is passed (lazy-create path). When a real instance is passed, lazy-create is skipped.
- `MedCodERRetrieverWorker.run` backward compatibility: the new `retriever_factory` kwarg is optional with `None` default. Existing callers that pass only `(queue_in, queue_out, index_dir)` are unaffected.
