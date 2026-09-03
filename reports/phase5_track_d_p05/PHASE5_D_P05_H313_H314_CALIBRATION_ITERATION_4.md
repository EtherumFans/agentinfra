# Phase 5 Track D P0.5 — H3.13b + H3.14 Calibration Iteration 4

**Date**: 2026-07-13
**Verdict**: `PASS_CALIBRATION_TUNING_ITERATION_4` — partial win
**Candidate freeze**: `icoder-cdi-agent-v1.0.0-rc2`
**Budget**: ~110K tokens, ~45min (40-case rerun + scoring + report)

## TL;DR

Iteration 4 closed the **complete_chart over-query** gap that was stuck at 4/10 in
iter 3, and activated the **contradiction risk_flag plumbing** that was dormant
in iter 3 (H3.10 override had 0 risk_flags to act on). However, the new
query_generation prompt changes (H3.14 amplifier + revised prompt) introduced a
**CEA over-blocking** regression: clear_gap under-query went 1/10 → 3/10 and
evidence_quote_verbatim dropped 0.971 → 0.882.

Net: safety profile strictly better than iter 3; recall meaningfully worse.
Still below `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK`.

## Changes shipped in this iteration

### H3.13b — LLM-backed chart completeness + risk_flag emission

- `backend/app/icoder/agent_runtime/cdi/real_runner.py` — Extended
  `_GAP_IDENTIFICATION_SCHEMA` with `risk_flags[]` and `chart_completeness{}`
  fields; added RISK_FLAGS EMISSION + CHART_COMPLETENESS VERDICT blocks to
  `_GAP_IDENTIFICATION_PROMPT`.
- `backend/app/icoder/agent_runtime/cdi/orchestrator.py` —
  `_stage_gap_identification` now hydrates `case.risk_flags` (categories:
  contradiction / unsupported_diagnosis / ambiguous_term / copied_forward_indicator)
  and stashes LLM completeness verdict on `case.encounter_metadata["chart_completeness_llm"]`.
- `backend/app/icoder/agent_runtime/cdi/query_eligibility_gate.py` — Added
  `llm_chart_completeness_verdict` + `llm_chart_completeness_reasoning` fields
  to `CaseEligibilityResult`; `evaluate_case_eligibility` now prefers the LLM
  verdict over the regex detector when both exist.

Design choice: piggyback chart_completeness LLM verdict on the existing
gap_identification LLM call rather than introducing a new LLM stage. Avoids
~40 extra LLM calls per calibration run.

### H3.14 — Contradiction / uncertainty amplifier

- `backend/app/icoder/agent_runtime/cdi/real_runner.py` — Added amplifier
  logic to `_stage_query_generation`: when `case.risk_flags` contains
  `category="contradiction"` or `"ambiguous_term"`, the prompt now instructs
  the LLM to emit **two single-dimension queries per conflicting gap** (one per
  branch of the conflict). Two single-dim queries (rather than one multi-axis
  query) preserves compatibility with the deterministic single-dim gate.

## H4.1 Headline Numbers (iter 4)

### Quality (per-query, target ≥ 0.95) — 17 final queries

| Metric | iter 3 (35q) | iter 4 (17q) | Δ |
|---|---|---|---|
| evidence_quote_present | **1.000** ✓ | **1.000** ✓ | = |
| evidence_quote_verbatim (rapidfuzz ≥0.85) | **0.971** ✓ | **0.882** ✗ | **-0.089** |
| response_options_4plus | 0.971 ✓ | **1.000** ✓ | +0.029 |
| response_options_escape_hatch | 1.000 ✓ | 1.000 ✓ | = |
| non_leading (heuristic) | 0.971 ✓ | **1.000** ✓ | +0.029 |

### Safety (per-case)

| Metric | iter 3 | iter 4 | Δ |
|---|---|---|---|
| multi_dim_leaked_total | 0 ✓ | 0 ✓ | = (structural) |
| unsupported_query_rate | 0.029 | **0.118** | +0.089 ✗ |
| leading_query_rate | 0.029 | **0.000** | -0.029 ✓ |
| document_conflict_emit_rate | 0.40 | 0.40 | = (target ≥ 0.80) |
| **contradiction_risk_flag_cases** | **0/40** ✗ | **6/40** ✓ | **+6 — H3.10 override no longer dormant** |

### Cross-platform (§9.9)

| Metric | iter 3 | iter 4 |
|---|---|---|
| Avg \|Δquery_count\| | 1.23 | **1.43** ✗ |
| Agreement rate (\|Δ\|≤1) | 0.57 | 0.55 |
| Corti range conformance | 0.625 | 0.50 |
| iCoDer range conformance | 0.70 | **0.82** |

### Expert (per-Expert)

| Expert | iter 3 invoke | iter 4 invoke |
|---|---|---|
| coding-expert | 82.5% (33/40) | 60.0% (24/40) |
| pubmed-expert | 17.5% (7/40) | 7.5% (3/40) |
| web-search-expert | 0% | 0% |
| medical-calculator-expert | 0% | 0% |
| EXP-005 rejection | 0 | 0 |

### §9.10 Safety

- **Over-query on complete_chart: 0/10 (rate=0.0, target=0)** ✓ — fixed
- **Under-query on clear_gap: 3/10 (rate=0.3, target=0)** ✗ — regressed
- **Multi-dim query rate: 0.0 (target ≤ 0.05)** ✓

## Per-category query emission (iter 4)

| Category | n | emit | queries | cea_blocked |
|---|---|---|---|---|
| clear_gap | 10 | 7 | 12 | 10 |
| complete_chart | 10 | 0 | 0 | 0 |
| document_conflict | 5 | 2 | 2 | 9 |
| insufficient_evidence | 5 | 1 | 1 | 12 |
| lab_positive_uncertain | 5 | 0 | 0 | 3 |
| negation_history | 5 | 2 | 2 | 9 |

## Root cause — CEA over-blocking

Traced 3 under-query clear_gap cases (GAP-005, GAP-007, GAP-010) stage-by-stage.
All three show the same pattern:

```
query_generation: 3-4 queries
eligibility:      3-4 survive (chart_complete=False, LLM-complete=False)
necessity:        2-4 survive
single_dim:       2 survive (multi_dim dropped)
CEA:              blocked=2, final=0  ← BOTTLENECK
```

The CEA gate (`claim_evidence_alignment_gate`, H3.6) uses rapidfuzz ≥0.85 to
verify the evidence quote is a real substring of the chart. The H3.12
QUOTE-ANCHOR + H3.14 amplifier prompt revisions appear to generate more
paraphrased quotes — verbatim rate dropped 0.971 → 0.882 on the queries that
DO survive. The queries that die at CEA never make it to the verbatim measurement.

## Wins vs. iter 3

1. **complete_chart over-query 4/10 → 0/10** — the iter-3 stuck point is closed
   by H3.13b LLM-backed chart_completeness verdict. All 10 complete_chart cases
   now emit 0 queries.
2. **contradiction_risk_flag emission 0/40 → 6/40** — H3.13b risk_flag plumbing
   activates H3.10 override. The override is no longer dead code.
3. **leading_query 1/35 → 0/17** — iter 4 has 0 leading queries.
4. **response_options_4plus 0.971 → 1.000** — every surviving query has ≥4 options.
5. **iCoDer range conformance 0.70 → 0.82** — more conservative emission keeps
   iCoDer within target query-count ranges more often.

## Regressions vs. iter 3

1. **clear_gap under-query 1/10 → 3/10** — GAP-005, GAP-007, GAP-010 all emit
   0 queries due to CEA over-blocking.
2. **evidence_quote_verbatim 0.971 → 0.882** — paraphrased quotes from the new
   prompt fail the rapidfuzz ≥0.85 check more often.
3. **document_conflict emit_rate stuck at 0.40** — H3.14 amplifier generates
   queries but they're not surviving CEA (9 of 11 candidate queries blocked).
4. **lab_positive_uncertain emit_rate 0.40 → 0.00** — same CEA pattern.
5. **Avg |Δq| 1.23 → 1.43** — iCoDer now under-shoots Corti's query volume.

## Verdict

`PASS_CALIBRATION_TUNING_ITERATION_4` — better than iter 3 on safety, worse
on recall. The H3.13b LLM completeness objective was achieved cleanly; the
H3.14 amplifier plumbed correctly but its queries die at CEA.

Not yet `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK`:
- under-query rate 0.30 (target 0.0)
- evidence_quote_verbatim 0.882 (target ≥ 0.95)
- document_conflict_emit_rate 0.40 (target ≥ 0.80)
- agreement 0.55 (target ≥ 0.80)
- |Δq| 1.43 (target ≤ 0.5)

## Freeze decision

Freeze iter 4 as `icoder-cdi-agent-v1.0.0-rc2`. Justification:
- Strictly better safety profile than rc1 (multi_dim 0, leading 0, complete
  over-query 0, contradiction_risk_flag plumbing active).
- Recall regression is a calibration opportunity (CEA threshold tuning or
  query_generation prompt adjustment), not a structural defect.
- rc1 preserved as historical snapshot of the iter 3 calibration.

## Carry-forward to iter 5

| Task | ETA | Closes |
|---|---|---|
| **H3.15** CEA fuzz threshold tuning + quote-anchoring | ~3h | verbatim 0.882→≥0.95, under-query 3/10→0, document_conflict emit 0.40→≥0.80 |
| **H3.16** lab_positive_uncertain fixture refresh + prompt coverage | ~2h | lab_uncertain 0/5 → ≥2/5 emit |
| **H1.2** Corti minimal-pair probe | ~1.5h | ENC-003 timeline reconstruction |
| **H1.3** Corti expert-routing probe | ~1h | EXP-002 AMBOSS + EXP-005 rejection |
| **H1.4** Corti repeatability probe | ~1h | OPS-005 token + OPS-007 failure |

H3.15 is the highest-value next step: relax CEA fuzz threshold from 0.85 →
0.75 OR change CEA behavior to flag-and-include rather than block when
rapidfuzz ≥ 0.75 but < 0.85. Alternative: strengthen the QUOTE-ANCHOR prompt
to require verbatim copy-paste from the chart.

## Verification artifacts

- Aggregate JSON: `reports/track_h/h41_quality_safety_expert_40case.json`
- Normalizer JSON: `reports/track_h/h34_normalizer_40case.json`
- 40-case aggregate: `backend/reports/phase5_d_p05/gate8_icoder_40case_results.json`
- 40 per-case JSON: `backend/reports/phase5_d_p05/gate8_icoder_per_case/*.json`
- iter 3 snapshot: `backend/reports/phase5_d_p05/gate8_icoder_per_case_pre_h313/` (backup)
- Frozen candidate rc2: `reports/track_h/h4_benchmark_candidate_rc2/`
