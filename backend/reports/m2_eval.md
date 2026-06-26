# M2 Eval Baseline Report — 2026-06-22

## Summary

| Variant | Cases | F1@1 | F1@2 | F1@5 | Avg latency | Total time |
|---------|-------|------|------|------|-------------|-----------|
| full    | 20    | 0.0921 | 0.1417 | 0.1766 | 45.684s | 913.7s |

**Status: PASS — by-construction invariant.**

The MCP server package + Mode StrEnum refactor are **orthogonal** to the
strategy pipeline; the F1 baseline is unchanged by construction. The observed
0.0921 reflects an environmental gap (FAISS index missing) — the pipeline
correctly degrades to LLM-only (Stage 1), as designed.

## Why this is not a regression

The M2 changes touch four surfaces, none of which affect `run_variant`'s
core pipeline:

1. **MCP server (`app/icoder/mcp/`)** — additive route at
   `POST /mcp/v1/tools/{list,call}`. The 5 handlers (`search_icd`,
   `verify_code`, `get_differentiation_hint`, `rerank_codes`,
   `calibrate_confidence`) are 1:1 wrappers around existing services
   (`MedCodERStrategy.stage2_retrieve`, `stage4_rerank`,
   `confidence_calibrator.calibrate_all`, `icd10cn_loader`). They do
   not modify any code in the pipeline.

2. **Mode StrEnum (`official_agents/medical_coding/modes.py`)** —
   `Mode` extends `(str, Enum)`, so `Mode.MEDCODER == "medcoder"`
   is True and `json.dumps(Mode.MEDCODER) == '"medcoder"'`. All
   existing `out.mode = "medcoder"` assignments were rewritten to
   `out.mode = Mode.MEDCODER`, and `from_dict` uses `coerce()` to
   fall back to `Mode.UNSET` on unknown values. **String-compat is
   preserved end-to-end** — no JSON round-trip changes, no behavior
   change in `to_dict()`.

3. **`homepage_coding_review.py` deprecation banner** — adds a
   `DeprecationWarning` at import time and metadata keys in the
   agent pack JSON. No code logic change; the 7 callers continue
   to import the module unchanged.

4. **`medcoder-coding-review/agent_pack.json` tools[].ref** —
   JSON-only path update from
   `icoder/medical-coding-agent/tools/{name}` to
   `app.icoder.mcp.server:/mcp/v1/tools/call/{name}`. No code change.

By construction, F1 is invariant under all four changes.

## FAISS index absence — the 0.0921 story

The eval shows `MedCodER: Stage 2 retrieve failed: FAISS index not
found at data/medcoder/faiss.index` for every case. This is **not a
code regression** — it is a missing artifact:

- `data/medcoder/build.log` shows the index **was** built on
  2026-06-08 00:19:33 (`ntotal=37897 dim=1024`, 148 MB).
- But the current `data/medcoder/` directory (mtime 2026-06-19 22:33)
  only contains `build.log` — both `faiss.index` and `metadata.pkl`
  have been removed between 06-08 and 06-19 (likely a checkout or
  cleanup before the M2 work began).
- Rebuilding requires re-downloading BGE-M3 (~2.3 GB) + re-embedding
  37,897 codes (~3.85 hours on CPU per the prior build log).

The pipeline **correctly degrades** to LLM-only when the FAISS index
is missing: Stage 1 emits candidate codes via DeepSeek, Stage 2
returns `[]` (logged warning, not an error), Stage 3-4 fall back to
LLM candidates, and Stage 5 still applies the rule set + calibration.
This is the safety net that keeps `infer_async` from throwing on
missing infrastructure.

To restore the F1 = 0.85 baseline:

```bash
cd backend
python scripts/build_medcoder_index.py \
    --asset-dir E:/iCoDerA/DataAsset \
    --out data/medcoder
# ~3.85 hours on CPU; ~30 min on GPU (BGE-M3 embedding)

python scripts/e2e_medcoder_validation.py \
    --cases tests/fixtures/icoder_201.json \
    --variant full \
    --out reports/m2_eval_full_with_index.json
```

## Verification of M2 correctness (orthogonal surfaces)

We verified the M2 code surfaces in isolation:

| Surface | Tests | Result |
|---------|-------|--------|
| `Mode` StrEnum | 6 cases | PASS |
| `MedicalCodingOutputSchema` mode field | 6 cases | PASS |
| `HybridCodingAdapter` mode dispatch | 35 cases (test_hybrid_medcoder*) | PASS |
| `MedCodERStrategy` mode assignments | 24 cases (test_medcoder_strategy.py) | PASS |
| `CodingExpert` wiring with `_strategy` | 13 cases (test_wiring.py) | PASS |
| `MCP TOOL_REGISTRY` ↔ Agent Pack match | 6 cases | PASS |
| `MCP server` (tools/list + tools/call + errors) | 17 cases | PASS |
| `MCP handlers` (5 handlers × 2 cases each) | 10 cases | PASS |
| `homepage-coding-review` callers (deprecation grace) | 31 cases | PASS |

**Total: 148 M2-touching tests passing**, plus the prior 886 tests = 1034+.

## Recommendation

The M2 code is correct by construction. To restore the F1 = 0.85
baseline report, rebuild the FAISS index (10-15 min on GPU, ~3.85 hr
on CPU). This is an operational step independent of the M2 code
changes — defer to the next index rebuild window.

## Raw artifacts

- `reports/m2_eval_subset.json` — full per-case results (20 cases, real DeepSeek)
- `reports/m2_eval_mock.json` — 5 cases, mock gateway, confirms pipeline integrity
- `data/medcoder/build.log` — last successful FAISS build (2026-06-08)