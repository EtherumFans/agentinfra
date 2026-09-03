# H4.2 Benchmark Candidate — `icoder-cdi-agent-v1.0.0-rc5`

**Frozen at (UTC)**: 2026-07-13T12:36:58Z
**Git commit**: `0d759e5533223594941ceb0c46c8a4df7c244f40`
**Iter**: 7
**Tier**: `PASS_CALIBRATION_TUNING_ITERATION_7`
**Case count**: 40

## What this is

A reproducible snapshot of the iCoDer CDI Agent's iter 7 calibration baseline
on the 40-case Corti × iCoDer cross-platform fixture. iter 7 = H3.19 sentence-
bounded CEA-005/CEA-006 negation look-back (closes negation_history agreement
regression 0.60 → 0.80). Preserves all iter 6 wins. iCoDer range conformance
lifted 85% → 93% (37/40). Tier 2 work (H1.2/H1.3/H1.4 Corti controlled probes)
will measure deltas against this artifact.

## Files

| Path | Purpose |
|---|---|
| `MANIFEST.json` | Self-describing manifest with sha256 + headlines |
| `gate8_icoder_40case_results.json` | iter 7 iCoDer 40-case aggregate results |
| `per_case/*.json` | 40 per-case trace files (stage_traces, gaps, queries, experts) |
| `h34_normalizer_40case.json` | §9.9 cross-platform + §9.10 safety metrics |
| `h41_quality_safety_expert_40case.json` | H4.1 quality + safety + expert scoring |
| `corti_40_summary.json` | Corti baseline reference (for delta comparison) |

## Headline metrics

| Metric | Value | Target | Status |
|---|---|---|---|
| avg queries/case | 1.000 | n/a | informational |
| iCoDer range conformance | 37/40 (93%) | ≥ 60% | ✅ PASS |
| agreement rate vs Corti (\|Δ\|≤1) | 0.75 | ≥ 0.80 | ⚠ partial |
| avg \|Δ query count\| | 1.00 | ≤ 0.50 | ⚠ partial |
| multi_dim_leaked_total | 0 | 0 | ✅ PASS (structural, 7 iters) |
| complete_chart over-query | 0/10 | 0 | ✅ PASS (7 iters) |
| clear_gap under-query | 1/10 | 0 | ⚠ partial (held from iter 6) |
| evidence_quote_verbatim | 0.975 | ≥ 0.95 | ✅ PASS (1 query drift) |
| document_conflict emit rate | 1.000 | ≥ 0.80 | ✅ PASS (held from iter 6) |
| unsupported_query_rate | 0.025 | = 0 | ⚠ 1 query drift |
| response_options_4plus | 1.000 | ≥ 0.95 | ✅ PASS (held from iter 6) |
| non_leading_query_rate | 1.000 | ≥ 0.95 | ✅ PASS (held from iter 6) |
| contradiction_risk_flag cases | 6/40 | n/a | ✅ iter 4 hold |

## Iter 7 wins (vs iter 6)

1. **negation_history agreement 0.60 → 0.80** — H3.19 sentence-bounded
   CEA-005/CEA-006 look-back. Closes the iter 4 → iter 6 regression:
   charts like NEG-026 ("否认糖尿病。家族史:父亲糖尿病。入院诊断:2型糖尿病?")
   had 否认 + 家族史 in PRIOR sentences false-trigger negation_as_support /
   PMH context → cascade to CEA-008 BLOCK → query dropped. Fix bounds
   look-back to sentence scope (delimiters 。！？；;).
2. **iCoDer range conformance 85% → 93%** (34/40 → 37/40) — same H3.19 fix
   unblocked 3 negation cases that were over-blocked by cross-sentence
   negation walkback.
3. **document_conflict agreement 0.60 → 0.80** — iter 7 co-lift.
4. **Agreement rate 0.70 → 0.75** — iter 7 WIN.

## Maintained from iter 6

- complete_chart over-query 0/10 (now 7 iters at 0 — longest sustained safety win)
- multi_dim_leaked = 0 (structural, deterministic gate)
- leading_query_rate = 0.000
- document_conflict emit_rate = 1.000 (H3.16 CEA-004 'chart' doc_id fix)
- response_options_4plus = 1.000 (H3.18 deterministic padding)
- non_leading_query_rate = 1.000
- lab_positive_uncertain emit = 4/5 (H3.16 three safety nets)
- contradiction_risk_flag = 6/40

## Carry-forward (does not block freeze)

1. **H1.2/H1.3/H1.4** — Corti controlled probes for the 3 UNKNOWN capabilities
   + EXP-005 rejection behavior (~3-4h). Requires Corti JWT.
2. **insufficient_evidence agreement 1.00 → 0.80** — 1 case LLM drift
   (INSUF-025 semantic_necessity_gate block).
3. **8 under-query cases (GAP-004 / INSUF-025 / NEG-027 / LAB-036/037/038 /
   CONFLICT-035)** — need structural fixes:
   - GAP-004: MULTI_DIM query dropped by SD gate (need rewrite instead of drop)
   - NEG-027: LLM chart_complete=True override too aggressive on negation
     cases (need override tightening)
   - LAB-036/037/038: iCoDer emits 1 query vs Corti 3 (need multi-query
     expansion for multi-axis lab findings)
   - INSUF-025: semantic gate over-blocks (need LLM gate tuning)
   - CONFLICT-035: iCoDer emits 1 vs Corti 3 (same multi-query expansion)
4. **Avg |Δq| drift 0.97 → 1.00** — symptom of negation lowering icoder_avg_q
   on negation_history category (0.40 vs corti 1.20).
5. **multi_dim "7 iters at 0" framing** — structural (deterministic gate),
   not a tuned achievement.

## How to regenerate

```bash
# Restore the snapshot from any commit:
python scripts/corti_parity/track_h/06_h4_freeze_benchmark_candidate.py

# Re-run H4.1 scoring on the snapshot:
python scripts/corti_parity/track_h/05_h4_quality_safety_expert_scoring.py

# Re-run normalizer on the snapshot:
python scripts/corti_parity/track_h/04_normalize_and_compare.py
```

To unfreeze / delete:
```bash
rm -rf reports/track_h/h4_benchmark_candidate_rc5/
```
