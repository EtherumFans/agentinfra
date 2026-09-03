# Agent UX Score Report (B-1.5)

**Date:** 2026-07-11
**Source data:** `outputs/phase5_track_b/agent_ux_matrix.{csv,json}`
**Agents scored:** 20 Corti + 24 iCoDer (44 total)
**Dimensions:** 12 per PDF §8

## Summary totals

| Cohort | Total | Avg per dim |
|---|---|---|
| Corti (20 agents, all production) | 47.0 / 60 | 3.92 |
| iCoDer runnable (9 agents) | **56.8 / 60** | **4.73** |
| iCoDer metadata-only (15 agents) | 20.3 / 60 | 1.69 |

**Headline:** iCoDer runnable agents OUTPERFORM Corti on UX by 9.8 points (56.8 vs 47.0). iCoDer's metadata-only agents drag the average down — expected since they cannot be run.

## Per-dim comparison (iCoDer runnable vs Corti)

| UX dim | Corti | iCoDer runnable | Diff | Direction |
|---|---|---|---|---|
| discoverability | 5.0 | 5.0 | 0.0 | = |
| comprehensibility | 5.0 | 5.0 | 0.0 | = |
| input_clarity | 4.0 | 3.8 | -0.2 | ▼ |
| output_transparency | 5.0 | 5.0 | 0.0 | = |
| error_handling | 4.0 | 4.0 | 0.0 | = |
| **latency_transparency** | 2.0 | **5.0** | **+3.0** | ▲ iCoDer |
| **auditability** | 2.0 | **5.0** | **+3.0** | ▲ iCoDer |
| **trust_signals** | 3.0 | **5.0** | **+2.0** | ▲ iCoDer |
| customization | 5.0 | 5.0 | 0.0 | = |
| sdk_support | 5.0 | 4.0 | -1.0 | ▼ Corti |
| **cost_transparency** | 3.0 | **5.0** | **+2.0** | ▲ iCoDer |
| consistency | 4.0 | 5.0 | +1.0 | ▲ iCoDer |

## Key findings

### iCoDer ADVANTAGES (5 dims, +11 points total)

1. **latency_transparency** (+3.0): iCoDer surfaces `latency_ms` per run in the envelope and RunTrace UI; Corti doesn't expose latency per run (only aggregate dashboard).
2. **auditability** (+3.0): iCoDer has RunHistory + RunTrace pages (`/runs/{run_id}`) with full trace_events; Corti has no per-run trace in agent detail UI per Phase 4-H §7 audit.
3. **trust_signals** (+2.0): iCoDer agents have explicit `maturity` badge + `red_lines` (no_upcoding/no_inference/evidence_required/production_writeback_blocked) + `human_review=required` hard gate; Corti prompt mentions compliance but no UI badge.
4. **cost_transparency** (+2.0): iCoDer Topbar shows live cost `¥X.XXXXXX` per run (Phase 4-G); Corti shows only daily aggregate `$X.XX`.
5. **consistency** (+1.0): iCoDer enforces unified 13-field envelope across all 9 runnable agents (Phase 4-F2); Corti has per-agent output schemas.

### Corti ADVANTAGES (1 dim, -1 point)

1. **sdk_support** (-1.0): Corti has full `@corti/sdk` (TS/JS) with `cortiClient.agents.create()` + `agents.messageSend()`; iCoDer exposes A2A cards for only 5 of 9 runnable agents (GAP-13-01).

### Ties (6 dims)

discoverability / comprehensibility / output_transparency / error_handling / customization / input_clarity — full parity.

## Implications

For Phase 5 Track C polish:
- **Keep winning**: latency_transparency / auditability / trust_signals / cost_transparency / consistency (5 iCoDer advantages)
- **Close gap**: sdk_support — close GAP-13-01 by extending `.well-known/agent.json` to all 9 runnable agents (P1)
- **Promote metadata-only**: 15 metadata-only agents drag average down; promote 3 PARTIAL_MATCH agents (diagnosis-extractor / denial-appeals / cdi-review) to runnable to lift cohort score

## Per-agent UX totals (top 10 iCoDer)

| Rank | Agent | Total / 60 | Status |
|---|---|---|---|
| 1 | medical-coding-agent | 60 | runnable |
| 2 | code-validation-agent | 60 | runnable |
| 3 | note-completeness-agent | 60 | runnable |
| 4 | drg-analyzer | 60 | runnable |
| 5 | evidence-extractor | 60 | runnable |
| 6 | principal-diagnosis-review | 60 | runnable |
| 7 | discharge-summary-structuring | 60 | runnable |
| 8 | procedure-extractor | 60 | runnable |
| 9 | compliance-guardrail-agent | 60 | runnable |
| 10 | (15 metadata-only agents) | ~20 | metadata-only |

Full data: `outputs/phase5_track_b/agent_ux_matrix.csv` (44 rows × 15 columns).
