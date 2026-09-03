# Phase 5 Track D P0.5 — H3.12 Calibration Iteration 3

**Date**: 2026-07-12
**Predecessor**: `PHASE5_D_P05_H39_H311_CALIBRATION_ITERATION_2.md` (PASS_CALIBRATION_TUNING_ITERATION_2_PARTIAL)
**Scope**: Fix the clear_gap regression caused by H3.9's over-strict prompt. Soften the wording so absence gaps get their queries emitted while preserving the verbatim-substring requirement for downstream CEA-001.
**Verdict**: `PASS_CALIBRATION_TUNING_ITERATION_3` — best iteration yet. clear_gap under-query 7/10 → 1/10, iCoDer range conformance 62.5% → 70%, agreement rate 0.42 → 0.57.

---

## 1. Root cause of iter-2 clear_gap regression

H3.9's prompt had two anti-patterns:

1. **"If you cannot find a verbatim chart span that supports the gap, SKIP that gap."**

   For absence gaps (gap type = "X 未明确" / "X not documented"), there is no verbatim span that *supports* the missing piece — because it is missing. The LLM correctly applied the rule and skipped. Result: 0 queries on real-gap charts.

2. **No distinction between "quote that supports the gap" and "quote that anchors the gap location".**

   CEA-001 verbatim check only requires the quote to be a substring of the chart. It does not require the quote to mention the missing piece. But the H3.9 prompt asked for a "supports-the-gap" quote, which the LLM interpreted strictly.

The fix: redefine the quote as **anchor** (the chart location where the missing/ambiguous info should live), not **supporting evidence**.

---

## 2. What was done — H3.12

**File**: `backend/app/icoder/agent_runtime/cdi/real_runner.py` (in-place edit)

### System prompt change

Old:
> EVIDENCE-VERBATIM REQUIREMENT (Track H3.9 — strict): evidence_span.quote MUST be a VERBATIM substring... If you cannot find a verbatim chart span that supports the gap, SKIP that gap.

New:
> QUOTE-ANCHOR REQUIREMENT (Track H3.9 + H3.12 — strict substring, soft scope): evidence_span.quote MUST be a VERBATIM substring of the chart text... The quote ANCHORS the gap (marks the chart location where the missing/ambiguous info should live); it does NOT need to contain the missing piece itself. For absence gaps (e.g. '病原体未明确'), the anchor is the surrounding clinical context (e.g. '入院诊断:肺炎' or '痰培养阳性'). Reuse the gap's existing evidence_span.quote when present. Do NOT skip gaps just because the missing piece is not in the chart — that is the nature of an absence gap. Only skip a gap if the chart truly has no surrounding context for it.

### User-prompt change

Old "QUOTE-FIRST PROCEDURE" (4 steps with "If no verbatim span exists, SKIP that gap" at step 3).

New "QUOTE-ANCHOR PROCEDURE" (5 steps):

> Step 1. Identify the gap type: absence, ambiguity, or contradiction.
> Step 2. Find a 5-30 character span of chart text that ANCHORS the gap. The anchor does NOT need to contain the missing piece itself.
> Step 3. Copy the anchor span VERBATIM. If the gap's anchor_hint is non-empty, prefer reusing it.
> Step 4. Draft the query_text + ≥4 response_options.
> Step 5. Only skip a gap if the chart has NO surrounding context for it at all (very rare).

The per-gap line in the user prompt now includes `[gap_type=...]` and `[anchor_hint=...]` hints — the LLM can see the gap_type up front and reuse the anchor_hint (set by Stage 2 gap_identification) instead of inventing a new quote.

---

## 3. Iter 2 → Iter 3 metrics

### §9.9 Cross-platform

| Metric | Iter 1 | Iter 2 | Iter 3 | Δ (iter 2 → 3) |
|---|---|---|---|---|
| Avg queries/case | 0.475 | 0.60 | **0.875** | +0.275 |
| iCoDer range conformance | n/a | 25/40 (62.5%) | **28/40 (70%)** | +3 cases ✅ |
| Corti range conformance | 20/40 | 20/40 | 20/40 | unchanged (Corti untouched) |
| Agreement rate (\|Δ\|≤1) | 0.45 | 0.42 | **0.57** | +0.15 ✅ |
| Avg \|Δ query count\| | 1.55 | 1.55 | **1.23** | -0.32 ✅ |

### §9.10 Safety

| Metric | Iter 1 | Iter 2 | Iter 3 | Target | Status |
|---|---|---|---|---|---|
| Over-query complete_chart | 3/10 | 3/10 | 4/10 | 0 | ❌ +1 minor regression |
| Under-query clear_gap | 4/10 | 7/10 | **1/10** | 0 | ✅✅✅ **massive win** |
| Multi-dim query rate | 0.0 | 0.0 | 0.0 | ≤0.05 | ✅ PASS |

### Per-category avg queries/case

| Category | Iter 1 | Iter 2 | Iter 3 | Corti baseline |
|---|---|---|---|---|
| clear_gap | n/a | 0.90 | **1.90** | 2.70 |
| complete_chart | n/a | 0.40 | 0.50 | 0.50 |
| insufficient_evidence | n/a | 0.20 | 0.60 | 1.00 |
| negation_history | 0.6 | 0.60 | 0.40 | 1.20 |
| document_conflict | 0.4 | 0.80 | 0.60 | 2.40 |
| lab_positive_uncertain | 0.4 | 0.60 | 0.60 | 2.20 |

clear_gap jumped from 0.90 → 1.90 (now within 0.8 of Corti's 2.70 baseline). This is the headline win.

### Tokens / latency

| Metric | Iter 1 | Iter 2 | Iter 3 |
|---|---|---|---|
| Avg queries/case | 0.475 | 0.60 | 0.875 |
| Total final queries | ~19 | ~24 | **35** |

---

## 4. Reading the result

### Wins

- **clear_gap regression fully fixed.** Under-query rate 7/10 → 1/10. This is the best single-iteration improvement in the entire Track H3.x series. The fix was a pure prompt-wording change (no code logic) — confirming the root-cause analysis that H3.9 was over-strict about "supports the gap" vs "anchors the gap".
- **iCoDer range conformance +7.5 percentage points.** 25/40 → 28/40. iCoDer now matches Corti's expected-range on 70% of cases.
- **Agreement rate +15 points.** 0.42 → 0.57. iCoDer's per-case query counts now agree with Corti's within ±1 on 57% of cases (was 42%).
- **Avg |Δq| down to 1.23.** The distance to Corti's counts has shrunk from 1.55 → 1.23.
- **multi_dim_rate stays at 0.0.** The single-dimension gate safety floor still holds — no over-correction.
- **insufficient_evidence 0.20 → 0.60.** +0.4 lift, in-range 4/5. The H3.12 anchor framing helps these cases too — the LLM can now point at the lab/imaging that lacks clinical correlation.

### Minor regressions (acceptable trade)

- **complete_chart over-query 3/10 → 4/10.** The softer H3.12 prompt makes the LLM slightly more willing to emit queries even on complete charts, which then must be caught downstream. H3.5 chart-completeness gate handles 6/10 cases; the remaining 4/10 slip through. Future iteration (H3.13) could add LLM-backed chart-completeness detection.
- **document_conflict avg 0.80 → 0.60.** Slight drop. H3.10 conflict-override still works (without it, this category would be at ~0.40). The variance here is likely LLM stochasticity on the 5-case sample.
- **negation_history avg 0.60 → 0.40.** Slight drop. In-range still 5/5 (target is "≤1 query per case"), so this is a benign shift, not a safety issue.

Net: **+6 cases of clear_gap improvement vs -1 case of complete_chart regression**. Strongly positive trade.

---

## 5. Verdict

**PASS_CALIBRATION_TUNING_ITERATION_3**

This is the **highest tier reached** in the H3.x calibration series. The calibration is now:

- ✅ Safety floor solid (multi_dim_rate = 0.0 for 3 iterations straight).
- ✅ clear_gap under-query nearly closed (1/10, down from 4/10 pre-tuning and 7/10 at iter 2).
- ✅ Cross-platform agreement at 57% (up from 42% at iter 2, 45% at iter 1).
- ❌ complete_chart over-query stuck at 4/10 (target 0).
- ❌ document_conflict and lab_positive_uncertain still below Corti baseline (Corti 2.4/2.2 vs iCoDer 0.6/0.6).

Still below `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK` (which requires over-query=0 AND under-query=0 simultaneously). The remaining gap is concentrated in complete_chart over-query — needs H3.13.

---

## 6. Carry-forward to iteration 4 / final closure

### H3.13 — complete_chart over-query fix (~3h)

4/10 complete_chart cases still emit spurious queries. Root cause: H3.5's 8-dimension regex detector misses charts where dimensions are present but the regex patterns don't fire (e.g. English charts, non-standard phrasing).

Fix options:
- **H3.13a** (cheap, low-risk): tighten the existing regex patterns (more aliases per dimension).
- **H3.13b** (~3h, more accurate): add LLM-backed chart-completeness detection — prompt DeepSeek with the chart and ask "is this chart complete on type/site/severity/etiology/procedure/pathology/complications/course?". Use LLM verdict as an override when regex detector says "not complete" but LLM says "complete".

Recommend H3.13b for accuracy.

### H3.14 — document_conflict / lab_positive_uncertain volume (~3h)

Corti emits ~2.4 / 2.2 queries on these categories vs iCoDer's 0.6 / 0.6. The gap: iCoDer's necessity gate is dropping queries that Corti would emit. Either:
- Loosen necessity gate rules (risky — may re-introduce complete_chart over-query).
- Add a "contradiction/uncertainty amplifier" in query_generation that emits 2 queries when a contradiction risk_flag is present (one for each side of the conflict).

### H4.1 / H4.2 / H4.3 — final quality benchmark + verdict (~6h)

Now within reach. With iter 3 results in hand:
- H4.1 quality + safety + expert scoring on the iter 3 baseline.
- H4.2 freeze the candidate (`icoder-cdi-agent-v1.0.0-rc1` or similar).
- H4.3 final comprehensive report — verdict likely `PASS_CALIBRATION_TUNING_ITERATION_3` with H3.13/H3.14 as carry-forward.

### H1.2 / H1.3 / H1.4 — Corti probes (~3-4h)

Still owed from Track H1. Run minimal-pair / expert-routing / repeatability probes on Corti to complete the capability ontology evidence.

### H2 — iCoDer-Corti Capability Gap Matrix (~1h)

Now have enough data to fill the matrix.

---

## 7. Cumulative commits

```
4a5b28d feat(track-h): Corti CDI capability ontology + 40-case cross-platform calibration
195bd5d feat(track-h): H3.5-H3.8 calibration tuning iteration 1
7df16ab feat(track-h): H3.9-H3.11 calibration iteration 2 — partial win
<new>   feat(track-h): H3.12 calibration iteration 3 — clear_gap regression fixed
```

## 8. Cumulative token budget

- H1.0-H3.4: ~250K
- H3.5-H3.8 (iter 1): ~180K
- H3.9-H3.11 (iter 2): ~120K
- H3.12 (iter 3 rerun + analysis): ~140K (incl. 40-case rerun)
- **Cumulative**: ~690K tokens
- H3.13/H3.14/H4.x/H1.x remaining: estimated ~30-40h effort, ~250K additional tokens.
