# H4.2 Benchmark Candidate — `icoder-cdi-agent-v1.0.0-rc1`

**Frozen at (UTC)**: 2026-07-12T23:41:31Z
**Git commit**: `01c8448bda8b5bf2239365adbccbebfe149f9315`
**Iter**: 3
**Tier**: `PASS_CALIBRATION_TUNING_ITERATION_3`
**Case count**: 40

## What this is

A reproducible snapshot of the iCoDer CDI Agent's iter 3 calibration baseline
on the 40-case Corti × iCoDer cross-platform fixture. Future Track H work
(H3.13 LLM-backed chart completeness, H3.14 contradiction amplifier,
H1.2-H1.4 Corti controlled probes) will measure deltas against this artifact.

## Files

| Path | Purpose |
|---|---|
| `MANIFEST.json` | Self-describing manifest with sha256 + headlines |
| `gate8_icoder_40case_results.json` | iter 3 iCoDer 40-case aggregate results |
| `per_case/*.json` | 40 per-case trace files (stage_traces, gaps, queries, experts) |
| `h34_normalizer_40case.json` | §9.9 cross-platform + §9.10 safety metrics |
| `h41_quality_safety_expert_40case.json` | H4.1 quality + safety + expert scoring |
| `corti_40_summary.json` | Corti baseline reference (for delta comparison) |

## Headline metrics

| Metric | Value | Target | Status |
|---|---|---|---|
| avg queries/case | 0.875 | n/a | informational |
| iCoDer range conformance | 28/40 (70%) | ≥ 60% | ✅ PASS |
| agreement rate vs Corti (\|Δ\|≤1) | 0.57 | ≥ 0.50 | ✅ PASS |
| avg \|Δ query count\| | 1.23 | ≤ 1.50 | ✅ PASS |
| multi_dim_leaked_total | 0 | 0 | ✅ PASS (structural) |
| complete_chart over-query | 4/10 | 0 | ❌ carry-forward H3.13 |
| clear_gap under-query | 1/10 | 0 | ⚠ near-pass |
| document_conflict emit rate | 0.40 | ≥ 0.80 | ❌ carry-forward H3.10/H3.13 |

## Carry-forward (does not block freeze)

1. **H3.13b** — LLM-backed chart completeness detection + contradiction risk_flag
   emission prompt update (~3h). Will close complete_chart over-query 4/10 and
   document_conflict emit 0.40 simultaneously.
2. **H3.14** — lab_positive_uncertain / document_conflict volume lift (~3h).
3. **H1.2/H1.3/H1.4** — Corti controlled probes for the 3 UNKNOWN + EXP-005
   rejection behavior (~3-4h).
4. **multi_dim "3 iters at 0" framing** — clarify in H4.3 final report that
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
rm -rf reports/track_h/h4_benchmark_candidate_rc1/
```
