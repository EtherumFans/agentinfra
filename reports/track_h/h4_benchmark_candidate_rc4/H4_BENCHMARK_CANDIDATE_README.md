# H4.2 Benchmark Candidate — `icoder-cdi-agent-v1.0.0-rc4`

**Frozen at (UTC)**: 2026-07-13T06:56:04Z
**Git commit**: `f316cffaca81a6ad7d2d80309d3e83a3244794b4`
**Iter**: 6
**Tier**: `PASS_CALIBRATION_TUNING_ITERATION_6`
**Case count**: 40

## What this is

A reproducible snapshot of the iCoDer CDI Agent's iter 6 calibration baseline
on the 40-case Corti × iCoDer cross-platform fixture. iter 6 = H3.16 lab-positive-
uncertain safety net (3 deterministic fixes in extract_claims + CEA-004 + gap
prompt) + H3.18 response_options padding. Closes 4 of 5 iter 5 stuck points.
Tier 2 work (H1.2/H1.3/H1.4 Corti controlled probes) will measure deltas against
this artifact.

## Files

| Path | Purpose |
|---|---|
| `MANIFEST.json` | Self-describing manifest with sha256 + headlines |
| `gate8_icoder_40case_results.json` | iter 6 iCoDer 40-case aggregate results |
| `per_case/*.json` | 40 per-case trace files (stage_traces, gaps, queries, experts) |
| `h34_normalizer_40case.json` | §9.9 cross-platform + §9.10 safety metrics |
| `h41_quality_safety_expert_40case.json` | H4.1 quality + safety + expert scoring |
| `corti_40_summary.json` | Corti baseline reference (for delta comparison) |

## Headline metrics

| Metric | Value | Target | Status |
|---|---|---|---|
| avg queries/case | 0.925 | n/a | informational |
| iCoDer range conformance | 34/40 (85%) | ≥ 60% | ✅ PASS |
| agreement rate vs Corti (\|Δ\|≤1) | 0.70 | ≥ 0.80 | ⚠ partial |
| avg \|Δ query count\| | 0.97 | ≤ 0.50 | ⚠ partial |
| multi_dim_leaked_total | 0 | 0 | ✅ PASS (structural) |
| complete_chart over-query | 0/10 | 0 | ✅ PASS (6 iters) |
| clear_gap under-query | 1/10 | 0 | ⚠ partial (iter 6 BIG WIN: 4→1) |
| evidence_quote_verbatim | 0.973 | ≥ 0.95 | ✅ PASS (1 query drift) |
| document_conflict emit rate | 1.000 | ≥ 0.80 | ✅ PASS (iter 6 fully closed) |
| unsupported_query_rate | 0.027 | = 0 | ⚠ 1 query drift |
| response_options_4plus | 1.000 | ≥ 0.95 | ✅ PASS (iter 6 closed) |
| non_leading_query_rate | 1.000 | ≥ 0.95 | ✅ PASS (iter 6 closed) |
| contradiction_risk_flag cases | 6/40 | n/a | ✅ iter 4 hold |

## Iter 6 wins (vs iter 5)

1. **document_conflict emit_rate 0.60 → 1.000** — H3.16 CEA-004 'chart' doc_id
   acceptance unblocked every LLM-extracted alignment (was failing because
   'chart' ∉ DOC-001).
2. **response_options_4plus 0.900 → 1.000** — H3.18 deterministic padding.
3. **non_leading_query_rate 0.968 → 1.000** — LLM drift resolved.
4. **lab_positive_uncertain emit 0/5 → 2/5** — H3.16 three safety nets
   (critical+empty quote demote, critical+fuzzy mismatch demote, CEA-004
   'chart' accept, gap_identification lab-positive prompt rule).
5. **clear_gap under-query 4/10 → 1/10** — same H3.16 fixes.
6. **Avg |Δq| 1.30 → 0.97** — closer to Corti baseline.
7. **Agreement rate 0.57 → 0.70** — insufficient_evidence 0.40 → 1.00.
8. **iCoDer range conformance 78% → 85%** (34/40).

## Carry-forward (does not block freeze)

1. **H3.19** — negation_history agreement 0.60 (was 0.80 iter 4). ~2h.
2. **H1.2/H1.3/H1.4** — Corti controlled probes for the 3 UNKNOWN capabilities
   + EXP-005 rejection behavior (~3-4h). Requires Corti JWT.
3. **clear_gap over-query 1/10 (GAP-010)** — LLM emits 3 gaps for a max=2
   case. Defer prompt tuning to iter 7.
4. **evidence_quote_verbatim 1.000 → 0.973** — 1 query LLM drift.
5. **unsupported_query_rate 0.000 → 0.027** — 1 query LLM drift.
6. **multi_dim "6 iters at 0" framing** — structural (deterministic gate),
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
rm -rf reports/track_h/h4_benchmark_candidate_rc4/
```
