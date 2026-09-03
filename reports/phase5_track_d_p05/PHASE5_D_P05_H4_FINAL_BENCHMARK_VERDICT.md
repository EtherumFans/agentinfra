# Phase 5 Track D P0.5 — H4 Final Benchmark Verdict (Track H Closure)

**Date**: 2026-07-13
**Scope**: Track H (Corti × iCoDer CDI capability audit + calibration) comprehensive closure.
**Source artifacts**:
- `reports/track_h/h4_benchmark_candidate_rc1/` (H4.2 frozen snapshot, 44 files)
- `reports/track_h/H2_ICODER_CORTI_CAPABILITY_GAP_MATRIX.md`
- `reports/track_h/h41_quality_safety_expert_40case.json`
- `reports/phase5_track_d_p05/PHASE5_D_P05_GATE8_CALIBRATION_CLOSURE.md` (iter 1)
- `reports/phase5_track_d_p05/PHASE5_D_P05_H39_H311_CALIBRATION_ITERATION_2.md` (iter 2)
- `reports/phase5_track_d_p05/PHASE5_D_P05_H312_CALIBRATION_ITERATION_3.md` (iter 3, best)
- `reports/phase5_track_d_p05/PHASE5_D_P05_H41_QUALITY_SAFETY_EXPERT_SCORING.md` (H4.1)
- `docs/corti_parity/track_h/CORTI_CDI_CAPABILITY_ONTOLOGY.md` (H1.0, Corti baseline)

**Final verdict**: `PASS_CALIBRATION_TUNING_ITERATION_3` — Track H best tier.

Track H ships the methodology, the baseline, the calibration, and the
frozen candidate. Production-grade formal quality benchmark remains
gated on carry-forward items (H3.13 / H3.14 / H1.2-H1.4) totaling ~9-10h
of additional work, none of which blocks the current snapshot's value as
a reproducible reference point.

---

## 1. Executive summary

### What Track H delivered

Track H is the Corti × iCoDer cross-platform CDI audit + calibration track,
spanning 4 sub-tracks:

| Sub-track | Description | Status |
|---|---|---|
| **H1** | Corti CDI capability ontology (37 capabilities) + mechanism probes | ✅ H1.0 + H1.1 done; H1.2-H1.4 carry-forward |
| **H2** | iCoDer × Corti capability gap matrix | ✅ done |
| **H3** | Calibration tuning (12 sub-tasks H3.1-H3.12, 3 iterations) | ✅ iter 3 = best tier |
| **H4** | Quality + safety + expert scoring + freeze + verdict | ✅ done (this report) |

### Headline numbers (iter 3 baseline, frozen as `icoder-cdi-agent-v1.0.0-rc1`)

| Metric | Value | Reference |
|---|---|---|
| iCoDer avg queries/case | 0.875 | Corti 1.43 (38% fewer) |
| iCoDer range conformance | **28/40 (70%)** | Corti 20/40 (50%) |
| Agreement rate vs Corti (\|Δ\|≤1) | **0.57** | up from 0.42 (iter 2) |
| Avg \|Δq\| | **1.23** | down from 1.55 (iter 2) |
| multi_dim_leaked_total | **0** | structural (deterministic gate) |
| complete_chart over-query | 4/10 | target 0 (H3.13 carry-forward) |
| clear_gap under-query | **1/10** | down from 7/10 (iter 2 — main H3.12 win) |
| Quality (quote / options / non-leading) | ≥ 97% per axis | ✅ PASS |
| Expert invocation (coding + pubmed) | 82.5% + 17.5% | healthy |

### Verdict tier ladder (where we are)

```
PASS_CALIBRATION_TUNING_ITERATION_3   ← we are here (Track H best tier)
        ↑
PASS_CALIBRATION_TUNING_ITERATION_2_PARTIAL
        ↑
PASS_CALIBRATION_TUNING_ITERATION_1
        ↑
PASS_WITH_CORTE_CALIBRATION_INCOMPLETE  (Track D P0.5 Gate 8 entry)
        ↑
PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK  ← target (requires over-query=0 AND under-query=0)
        ↑
PASS_PRODUCTION_READY_FOR_PILOT          ← final production gate
```

The remaining gap to `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK` is
**complete_chart over-query (4/10)** + **document_conflict emit rate (0.40)**
+ **lab_positive_uncertain under-query**. All three are addressable by
H3.13 (LLM-backed chart completeness + contradiction risk_flag emission)
and H3.14 (contradiction amplifier), totaling ~6h of additional work.

---

## 2. H1 — Corti CDI Capability Ontology

**Status**: H1.0 + H1.1 complete. H1.2-H1.4 carry-forward.

### H1.0 — Ontology (37 capabilities, 8 categories)

Corti's CDI agent (`agent_def_id=fa3be93e` `icoder-g8-cdi-ref`) was
reverse-engineered via authorized account access + 40-case calibration
runs. The 6238-char systemPrompt + 4 Experts (pubmed / web-search /
medical-calculator / coding) + Vercel AI SDK SSE protocol decompose into:

| Category | Capability count | Confidence breakdown |
|---|---|---|
| Encounter Understanding | 3 | 2 CONFIRMED + 1 UNKNOWN |
| CDI Knowledge | 3 | 1 CONFIRMED + 1 STRONGLY_SUPPORTED + 1 UNKNOWN |
| Query Eligibility | 3 | 1 INFERRED + 1 STRONGLY_SUPPORTED + 1 CONTRADICTED |
| Query Generation | 4 | 2 CONFIRMED + 1 STRONGLY_SUPPORTED + 1 UNKNOWN |
| Expert Orchestration | 5 | 1 CONFIRMED + 4 INFERRED/UNKNOWN |
| Safety | 7 | 1 STRONGLY_SUPPORTED + 4 INFERRED + 2 UNKNOWN |
| Audit Trace | 5 | 3 CONFIRMED + 2 STRONGLY_SUPPORTED |
| Operational | 7 | 3 CONFIRMED + 2 STRONGLY_SUPPORTED + 2 UNKNOWN |

**Total**: 37 capabilities, 11 UNKNOWN (30%) awaiting H1.2-H1.4 controlled
probes.

### H1.1 — Mechanism probe fixture

12-case mechanism probe fixture at `tests/fixtures/track_h_mechanism_probes.json`,
covering minimal-pair / routing / repeatability axes. Built but **not yet
executed on Corti** — H1.2-H1.4 will run these.

### H1.2-H1.4 — Corti controlled probes (carry-forward, ~3-4h total)

| Probe | Resolves | ETA |
|---|---|---|
| H1.2 minimal-pair | `ENC-003` timeline reconstruction (multi-day encounters) | ~1h |
| H1.3 expert-routing | `EXP-002` AMBOSS, `EXP-005` rejection behavior | ~1h |
| H1.4 repeatability | `OPS-005` token transparency, `OPS-007` failure handling | ~1h |

These need Corti JWT credentials (`scripts/corti_parity/track_h/.corti_creds.json`).
Keycloak has 5-min silent refresh — may need re-login.

---

## 3. H2 — iCoDer × Corti Capability Gap Matrix

**Status**: complete.

### Parity breakdown (37 Corti capabilities)

| Code | Meaning | Count | Rate |
|---|---|---|---|
| PARITY | Both implement, comparable behavior | 21 | 57% |
| CLOSE | Both implement, minor diff (e.g. language/format) | 5 | 13% |
| ICODER_ADVANTAGE | iCoDer implements; Corti does not or worse | 6 | 16% |
| CORTI_ADVANTAGE | Corti implements; iCoDer does not or worse | 1 | 3% |
| PARTIAL | One implements; other stub | 1 | 3% |
| UNKNOWN | Insufficient data — H1.2-H1.4 probes | 3 | 8% |

**Headline**: iCoDer has structural parity on **27/37 (73%)** of Corti's
CDI capabilities, with 6 iCoDer-only advantages concentrated in safety +
audit-trace + multi-language.

### iCoDer's 6 advantages

1. **ELG-001 explicit eligibility gate** — Corti has no chart-completeness
   check; iCoDer's H3.5 8-dimension detector is novel.
2. **CDI-003 DRG/DIP awareness** — Corti prompt has no DRG mention; iCoDer
   has dedicated `drg_analyzer` + DRG/DIP risk flags.
3. **SAF-005 fabricated-fact detection** — Corti relies on prompt guidance;
   iCoDer has `necessity_semantic.py` LLM-backed review.
4. **SAF-006 contradiction handling** — code exists (H3.10), but dormant
   on iter 3 (see §5 finding S-1 below).
5. **TRC-005 + OPS-005 per-stage audit** — Corti exposes aggregate cost;
   iCoDer emits per-stage provider/model/latency/tokens.
6. **OPS-006 Chinese-language support** — Corti is English-only; iCoDer
   matches China hospital reality.

### Corti's 1 advantage

- **EXP-002 AMBOSS Expert** — Corti prompt references AMBOSS clinical
  criteria. iCoDer has no AMBOSS equivalent. **Mitigation**: AMBOSS is
  EU-centric; for China market, iCoDer can substitute with local clinical
  knowledge bases without losing capability.

---

## 4. H3 — Calibration iteration history

3 iterations of LLM-prompt + gate-logic tuning. Each iteration = full
40-case rerun (~13min wall clock, ~95K tokens).

### Iteration timeline

```
iter 1 (H3.5-H3.8)   →  over-query 5/10 → 3/10,  under-query 4/10 → 4/10
iter 2 (H3.9-H3.11)  →  over-query 3/10 (hold),  under-query 4/10 → 7/10 (REGRESSION)
iter 3 (H3.12)       →  over-query 3/10 → 4/10,  under-query 7/10 → 1/10 (REGRESSION FIXED)
```

### Metric trajectory

| Metric | Iter 1 | Iter 2 | Iter 3 | Direction |
|---|---|---|---|---|
| Avg queries/case | 0.475 | 0.60 | **0.875** | ↑ better |
| iCoDer range conformance | n/a | 25/40 (62.5%) | **28/40 (70%)** | ↑ better |
| Agreement rate (\|Δ\|≤1) | 0.45 | 0.42 | **0.57** | ↑ better |
| Avg \|Δq\| | 1.55 | 1.55 | **1.23** | ↓ better |
| Over-query complete_chart | 3/10 | 3/10 | 4/10 | ↓ slightly worse |
| Under-query clear_gap | 4/10 | 7/10 | **1/10** | ↓ better (H3.12 main win) |
| Multi-dim leaked | 0 | 0 | 0 | structural |

### Per-category avg queries/case trajectory

| Category | Iter 1 | Iter 2 | Iter 3 | Corti baseline |
|---|---|---|---|---|
| `clear_gap` | n/a | 0.90 | **1.90** | 2.70 |
| `complete_chart` | n/a | 0.40 | 0.50 | 0.50 |
| `insufficient_evidence` | n/a | 0.20 | 0.60 | 1.00 |
| `negation_history` | 0.6 | 0.60 | 0.40 | 1.20 |
| `document_conflict` | 0.4 | 0.80 | 0.60 | 2.40 |
| `lab_positive_uncertain` | 0.4 | 0.60 | 0.60 | 2.20 |

### H3.x changes by sub-task

| Sub-task | File | Change |
|---|---|---|
| H3.1 | `02_run_corti_cdi_sse_40.py` | Python Corti SSE runner (dual JWT, Vercel AI SDK decode) |
| H3.2 | (Corti run) | 40-case Corti baseline executed (137K tokens, 16.7s/case) |
| H3.3 | `circuit_breaker.py` | Failure threshold 5→20 |
| H3.4 | `04_normalize_and_compare.py` | §9.9 + §9.10 normalizer |
| H3.5 | `query_eligibility_gate.py` | NEW 8-dimension chart completeness gate |
| H3.6 | `claim_evidence_gate.py` | CEA-001 fuzzy fallback (rapidfuzz ≥ 0.85) |
| H3.7 | (iCoDer rerun) | iter 1 40-case rerun |
| H3.8 | `PHASE5_D_P05_GATE8_CALIBRATION_CLOSURE.md` | iter 1 closure |
| H3.9 | `real_runner.py` | EVIDENCE-VERBATIM prompt (over-strict — iter 2 regression) |
| H3.10 | `query_eligibility_gate.py:231` | Contradiction risk_flag override (currently dormant — §5) |
| H3.11 | `necessity_semantic.py` | chart_fully_documented 7th metric |
| H3.12 | `real_runner.py` | QUOTE-ANCHOR PROCEDURE (iter 2 regression fixed — main iter 3 win) |

---

## 5. H4 — Quality + Safety + Expert scoring + Freeze

### H4.1 — Quality (35 final queries)

| Metric | Value | Target | Status |
|---|---|---|---|
| `evidence_quote_present_rate` | 1.000 | 1.0 | ✅ PASS |
| `evidence_quote_verbatim_rate` (rapidfuzz ≥ 0.85) | 0.971 | ≥ 0.95 | ✅ PASS |
| `avg_evidence_quote_fuzz_score` | 0.990 | ≥ 0.90 | ✅ PASS |
| `response_options_4plus_rate` | 0.971 | ≥ 0.95 | ✅ PASS |
| `response_options_escape_hatch_rate` | 1.000 | 1.0 | ✅ PASS |
| `non_leading_query_rate` (heuristic) | 0.971 | ≥ 0.95 | ✅ PASS |

### H4.1 — Safety (40 cases)

| Metric | Value | Target | Status |
|---|---|---|---|
| `multi_dim_leaked_total` | **0** | 0 | ✅ PASS (structural) |
| `multi_dim_leaked_rate` | **0.000** | 0.0 | ✅ PASS |
| `unsupported_query_rate` | 0.029 (1/35) | 0.0 | ⚠ minor |
| `leading_query_rate` | 0.029 (1/35) | 0.0 | ⚠ minor |
| `document_conflict_emit_rate` | 0.40 (2/5) | ≥ 0.80 | ❌ |
| `contradiction_risk_flag_cases` | **0** (across all 40) | n/a | **see finding S-1** |

### H4.1 — Expert invocation

| Expert | invoke_rate | avg_lat | avg_tok | rejection |
|---|---|---|---|---|
| `coding-expert` | 82.5% (33/40) | 3321ms | 277 | 0 |
| `pubmed-expert` | 17.5% (7/40) | 2634ms | 338 | 0 |
| `web-search-expert` | 0% | n/a | n/a | 0 |
| `medical-calculator-expert` | 0% | n/a | n/a | 0 |

### Finding S-1: H3.10 contradiction override is dormant on iter 3

The H3.10 code path (`_case_has_contradiction()` in
`query_eligibility_gate.py:231`) requires `case.risk_flags` to contain a
flag with `category == "contradiction"`. Inspection of all 40 per-case
JSON files reveals **0 contradiction risk_flags across the entire baseline**
— including the 5 CONFLICT fixture cases.

This means the gap_identification stage is **not emitting contradiction
risk_flags** even when the chart has internal conflicts. H3.10's override
logic exists in code but is **dead code on iter 3 baseline**.

The closure report claim in iter 2 ("without H3.10 conflict-override,
document_conflict would be at ~0.40") was based on iteration-2 data —
the override may have fired then due to LLM stochasticity, but is not
firing on iter 3 (where document_conflict emit is also at 0.40, the
"without override" baseline).

**Severity**: HIGH. The only code path that lifts document_conflict above
0.40 emit rate is dormant. Must be addressed in H3.13b by updating the
gap_identification prompt to emit contradiction risk_flags on conflict
charts.

### Finding S-2: multi_dim safety floor is structural

`multi_dim_leaked_total = 0` is guaranteed by construction, not by
statistical luck. The `query_single_dimension_gate` is a deterministic
regex+keyword filter that hard-drops any query touching ≥2 dimensions.
The "3 iterations straight at 0.0" framing in iter 3 closure report is
misleading — it would pass on any iteration regardless of tuning. This is
a property worth preserving but not a metric worth re-running.

### H4.2 — Frozen benchmark candidate

Snapshot at `reports/track_h/h4_benchmark_candidate_rc1/`:

| Path | Purpose |
|---|---|
| `MANIFEST.json` | Self-describing manifest with sha256 + headlines + carry-forward |
| `H4_BENCHMARK_CANDIDATE_README.md` | Reproduce instructions |
| `gate8_icoder_40case_results.json` | iter 3 40-case aggregate |
| `per_case/*.json` | 40 per-case trace files |
| `h34_normalizer_40case.json` | §9.9 + §9.10 metrics |
| `h41_quality_safety_expert_40case.json` | H4.1 quality + safety + expert scoring |
| `corti_40_summary.json` | Corti baseline reference |

44 files total. Git commit `01c8448`. Candidate label
`icoder-cdi-agent-v1.0.0-rc1`. Frozen at 2026-07-12T23:41:31Z.

---

## 6. Final verdict — `PASS_CALIBRATION_TUNING_ITERATION_3`

This is the **highest tier reached** in Track H. The calibration is:

- ✅ Methodology shipped (H1.0 ontology + H2 matrix + H3.x iter framework
  + H4.1 scoring script + H4.2 freeze).
- ✅ Safety floor solid (`multi_dim_leaked = 0` structurally; quality axes
  all pass at ≥ 0.95 thresholds).
- ✅ Cross-platform agreement at 57% (up from 42% at iter 2).
- ✅ Clear_gap under-query nearly closed (1/10, down from 7/10 at iter 2 —
  the headline iter 3 win).
- ✅ Frozen as `icoder-cdi-agent-v1.0.0-rc1` for reproducibility.
- ❌ Complete_chart over-query stuck at 4/10 (target 0).
- ❌ Document_conflict emit rate 0.40 (target ≥ 0.80).
- ❌ Lab_positive_uncertain under-query.

Still below `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK` (which requires
over-query=0 AND under-query=0 simultaneously). The remaining gap is
concentrated in:
1. **complete_chart over-query** — needs H3.13 (LLM-backed chart completeness).
2. **document_conflict under-emit** — needs H3.13b (fix contradiction
   risk_flag emission so H3.10 override actually triggers).
3. **lab_positive_uncertain under-query** — needs H3.14 (contradiction /
   uncertainty amplifier).

---

## 7. Carry-forward

### Tier 1 — closes `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK`

| Item | ETA | What it closes |
|---|---|---|
| **H3.13b** LLM-backed chart completeness + contradiction risk_flag emission | ~3h | complete_chart over-query 4/10 → 0; document_conflict emit 0.40 → ≥0.80; activates H3.10 override |
| **H3.14** Contradiction / uncertainty amplifier in query_generation | ~3h | lab_positive_uncertain + document_conflict volume lift |

Combined: ~6h. Brings baseline to `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK`.

### Tier 2 — closes H1 UNKNOWN capabilities

| Item | ETA | What it closes |
|---|---|---|
| H1.2 minimal-pair probe (Corti JWT required) | ~1h | `ENC-003` timeline reconstruction |
| H1.3 expert-routing probe (Corti JWT required) | ~1h | `EXP-002` AMBOSS + `EXP-005` rejection behavior |
| H1.4 repeatability probe (Corti JWT required) | ~1h | `OPS-005` token + `OPS-007` failure handling |

Combined: ~3-4h. Closes the 3 UNKNOWN capabilities in H2 matrix.

### Tier 3 — minor H4.1 findings

| Item | ETA | What it closes |
|---|---|---|
| Manual audit of 1 leading-query heuristic flag | ~10min | Confirm true positive vs false positive |
| Inspect 1 fuzzy-only evidence quote | ~10min | Verify ≥ 0.85 fuzz threshold is appropriate |
| Fixture coverage: add calculator + web-search cases | ~1h | `web-search-expert` + `medical-calculator-expert` 0% invoke is fixture gap, not regression |
| Doc-only: clarify multi_dim structural framing | (bundled in this report) | Done |

---

## 8. Cumulative Track H budget

| Phase | Tokens | Wall clock |
|---|---|---|
| H1.0-H3.4 (ontology + initial calibration) | ~250K | ~3h |
| H3.5-H3.8 (iter 1) | ~180K | ~5h |
| H3.9-H3.11 (iter 2) | ~120K | ~3h |
| H3.12 (iter 3) | ~140K | ~3h |
| H2 (capability matrix) | ~30K | ~1h |
| H4.1 + H4.2 + H4.3 (this report) | ~80K | ~3h |
| **Cumulative** | **~800K** | **~18h** |

Estimated remaining:
- Tier 1 (H3.13 + H3.14): ~6h, ~200K tokens
- Tier 2 (H1.2-H1.4): ~3-4h, ~120K tokens
- Tier 3 (minor): ~1.5h, ~30K tokens

**Total to `PASS_PRODUCTION_READY_FOR_PILOT`**: ~10-12h, ~350K tokens.

---

## 9. Reproduce

```bash
# 1. Re-run the 40-case calibration (requires backend on :8000 + real DeepSeek)
cd backend && python scripts/phase5_d_p05_gate8_icoder_40case_run.py
# ~13min wall clock, ~95K tokens

# 2. Normalize §9.9 + §9.10 metrics
python scripts/corti_parity/track_h/04_normalize_and_compare.py

# 3. H4.1 quality + safety + expert scoring
python scripts/corti_parity/track_h/05_h4_quality_safety_expert_scoring.py

# 4. H4.2 freeze benchmark candidate
python scripts/corti_parity/track_h/06_h4_freeze_benchmark_candidate.py

# Outputs land in:
#   backend/reports/phase5_d_p05/gate8_icoder_40case_results.json
#   backend/reports/phase5_d_p05/gate8_icoder_per_case/*.json
#   reports/track_h/h34_normalizer_40case.json
#   reports/track_h/h41_quality_safety_expert_40case.json
#   reports/track_h/h4_benchmark_candidate_rc1/  (frozen snapshot)
```

To verify the frozen snapshot's integrity:

```bash
python -c "
import json, hashlib
from pathlib import Path
m = json.loads(Path('reports/track_h/h4_benchmark_candidate_rc1/MANIFEST.json').read_text(encoding='utf-8'))
for f in m['files'] + m['per_case_files']:
    p = Path('reports/track_h/h4_benchmark_candidate_rc1') / f['path']
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    assert actual == f['sha256'], f'CHECKSUM FAIL: {f[\"path\"]}'
print(f'{m[\"file_count_total\"]} files verified, candidate={m[\"candidate_version\"]}')
"
```

---

## 10. References

- **Corti baseline ontology**: `docs/corti_parity/track_h/CORTI_CDI_CAPABILITY_ONTOLOGY.md`
- **H2 gap matrix**: `reports/track_h/H2_ICODER_CORTI_CAPABILITY_GAP_MATRIX.md`
- **Iter 1 closure**: `reports/phase5_track_d_p05/PHASE5_D_P05_GATE8_CALIBRATION_CLOSURE.md`
- **Iter 2 closure**: `reports/phase5_track_d_p05/PHASE5_D_P05_H39_H311_CALIBRATION_ITERATION_2.md`
- **Iter 3 closure**: `reports/phase5_track_d_p05/PHASE5_D_P05_H312_CALIBRATION_ITERATION_3.md`
- **H4.1 scoring**: `reports/phase5_track_d_p05/PHASE5_D_P05_H41_QUALITY_SAFETY_EXPERT_SCORING.md`
- **Frozen snapshot**: `reports/track_h/h4_benchmark_candidate_rc1/MANIFEST.json`
- **Orchestrator code**: `backend/app/icoder/agent_runtime/cdi/orchestrator.py` (11-stage mainline)
- **Calibration gates**: `backend/app/icoder/agent_runtime/cdi/{query_eligibility_gate,claim_evidence_gate,necessity_semantic,real_runner}.py`

---

**Track H**: CLOSED at `PASS_CALIBRATION_TUNING_ITERATION_3` tier.
**Next**: Tier 1 carry-forward (H3.13 + H3.14, ~6h) to reach
`PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK`.
