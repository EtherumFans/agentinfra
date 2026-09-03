# H4.2 Benchmark Candidate — `icoder-cdi-agent-v1.0.0-rc3`

**Frozen at (UTC)**: 2026-07-13T03:08:35Z
**Git commit**: `5ea70fd912125846405409837a0f5f88eaa45674`
**Iter**: 5
**Tier**: `PASS_CALIBRATION_TUNING_ITERATION_5`
**Case count**: 40

## What this is

A reproducible snapshot of the iCoDer CDI Agent's iter 5 calibration baseline
on the 40-case Corti × iCoDer cross-platform fixture. iter 5 = H3.15 quote-snap
+ extract_claims prompt fix. Closes 3 of 5 iter 4 stuck points. Tier 2 work
(H1.2/H1.3/H1.4 Corti controlled probes) will measure deltas against this artifact.

## Files

| Path | Purpose |
|---|---|
| `MANIFEST.json` | Self-describing manifest with sha256 + headlines |
| `gate8_icoder_40case_results.json` | iter 5 iCoDer 40-case aggregate results |
| `per_case/*.json` | 40 per-case trace files (stage_traces, gaps, queries, experts) |
| `h34_normalizer_40case.json` | §9.9 cross-platform + §9.10 safety metrics |
| `h41_quality_safety_expert_40case.json` | H4.1 quality + safety + expert scoring |
| `corti_40_summary.json` | Corti baseline reference (for delta comparison) |

## Headline metrics

| Metric | Value | Target | Status |
|---|---|---|---|
| avg queries/case | 0.75 | n/a | informational |
| iCoDer range conformance | 31/40 (78%) | ≥ 60% | ✅ PASS |
| agreement rate vs Corti (\|Δ\|≤1) | 0.57 | ≥ 0.80 | ⚠ partial |
| avg \|Δ query count\| | 1.30 | ≤ 0.50 | ⚠ partial |
| multi_dim_leaked_total | 0 | 0 | ✅ PASS (structural) |
| complete_chart over-query | 0/10 | 0 | ✅ PASS (iter 4 hold) |
| clear_gap under-query | 4/10 | 0 | ⚠ partial |
| evidence_quote_verbatim | 1.000 | ≥ 0.95 | ✅ PASS (iter 5 closed) |
| document_conflict emit rate | 0.80 | ≥ 0.80 | ✅ PASS (iter 5 closed) |
| unsupported_query_rate | 0.000 | = 0 | ✅ PASS (iter 5 closed) |
| contradiction_risk_flag cases | 6/40 | n/a | ✅ iter 4 hold |

## Iter 5 wins (vs iter 4)

1. **evidence_quote_verbatim 0.882 → 1.000** — H3.15 quote-snap (deterministic
   correction to chart substring) + extract_claims prompt (critical claim must
   be chart-evidenced, not response_option hypothesis).
2. **document_conflict emit_rate 0.40 → 0.80** — H3.14 amplifier now generates
   queries that survive CEA (because critical claims are chart-evidenced).
3. **unsupported_query_rate 0.118 → 0.000** — same root cause as above.
4. **Avg |Δq| 1.43 → 1.30** — closer to Corti baseline.
5. **clear_gap agreement_rate 0.30 → 0.70** — major lift.

## Carry-forward (does not block freeze)

1. **H3.16** — lab_positive_uncertain emit 0/5 unchanged. Needs Corti-style
   lab-normal low-target clarification flow (~3h).
2. **H1.2/H1.3/H1.4** — Corti controlled probes for the 3 UNKNOWN capabilities
   + EXP-005 rejection behavior (~3-4h). Requires Corti JWT.
3. **clear_gap over-query 2/10 (new in iter 5)** — GAP-002 (q=3), GAP-010 (q=4).
   Investigate response_options extraction; may need cap at 2 queries/gap.
4. **response_options_4plus 1.000 → 0.900** — 3 queries with <4 options.
   Likely a regression in H3.14 amplifier prompt.
5. **multi_dim "5 iters at 0" framing** — clarify in H4.3 final report that
   this is structural (deterministic gate), not a tuned achievement.

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
rm -rf reports/track_h/h4_benchmark_candidate_rc3/
```
