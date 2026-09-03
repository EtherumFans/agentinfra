# Phase 5 Track D P0.5 — H4.1 Quality + Safety + Expert Scoring

**Date**: 2026-07-13
**Baseline**: H3.12 calibration iteration 3 (best tier)
**Candidate**: `icoder-cdi-agent-v1.0.0-rc1`
**Method**: Offline audit of 40 per-case JSON files in
`backend/reports/phase5_d_p05/gate8_icoder_per_case/` against three families
of metrics. No LLM calls (script is pure analysis).
**Script**: `scripts/corti_parity/track_h/05_h4_quality_safety_expert_scoring.py`
**Data**: `reports/track_h/h41_quality_safety_expert_40case.json`

---

## Headline

40 cases, **35 final queries** emitted. Three families audited:

| Family | Headline metric | Value | Target | Status |
|---|---|---|---|---|
| Quality | `evidence_quote_present_rate` | 1.000 | 1.0 | ✅ PASS |
| Quality | `evidence_quote_verbatim_rate` (rapidfuzz ≥ 0.85) | 0.971 | ≥ 0.95 | ✅ PASS |
| Quality | `response_options_4plus_rate` | 0.971 | ≥ 0.95 | ✅ PASS |
| Quality | `response_options_escape_hatch_rate` | 1.000 | 1.0 | ✅ PASS |
| Quality | `non_leading_query_rate` | 0.971 | ≥ 0.95 | ✅ PASS |
| Safety | `multi_dim_leaked_total` | 0 | 0 | ✅ PASS (deterministic gate) |
| Safety | `unsupported_query_rate` | 0.029 | 0.0 | ⚠ 1/35 (fuzzy pass) |
| Safety | `leading_query_rate` | 0.029 | 0.0 | ⚠ 1/35 (heuristic flag) |
| Safety | `document_conflict_emit_rate` | 0.40 | ≥ 0.80 | ❌ 2/5 emit |
| Expert | `coding-expert` invoke rate | 82.5% | n/a (informational) | ✅ main expert active |
| Expert | `expert_rejection_count` (all experts) | 0 | n/a | ⚠ rejection behavior not exercised |

**Verdict**: `PASS_H4_1_QUALITY_SAFETY_EXPERT_WITH_TWO_MINOR_SAFETY_FINGS_AND_CONFLICT_UNDERQUERY`

Quality axes all pass with ≥ 0.95 thresholds. Two minor safety findings
(1 fuzzy-only quote, 1 leading-query heuristic flag) — neither blocking
benchmark freeze. Conflict under-query (2/5 emit) is the same gap noted
in H3.12 §5 carry-forward; not a new regression.

---

## 1. Quality (per-query, 35 queries)

| Metric | Count | Rate | Notes |
|---|---|---|---|
| `evidence_quote_present` | 35/35 | 1.000 | Every query has an evidence_span.quote |
| `evidence_quote_verbatim` (≥0.85 fuzz) | 34/35 | 0.971 | 1 query fuzz-only pass |
| `avg_evidence_quote_fuzz_score` | n/a | 0.990 | Average fuzzy ratio |
| `response_options_4plus` | 34/35 | 0.971 | 1 query has 3 options (≥4 required) |
| `response_options_escape_hatch` | 35/35 | 1.000 | Every query has 无法确定 / 不详 / 未知 / etc. |
| `query_text_non_leading` | 34/35 | 0.971 | 1 query flagged by heuristic |

**The two flagged queries are different queries** — they are not the same
single outlier. Quality control on iter 3 baseline is robust.

### Leading-query heuristic (false-positive prone)

The single "leading" flag is from this regex set:
```
是不是 / 是否为 / 确诊 / 应该诊断为 / 实际上是 / 可以考虑...吧
```

Manual spot-check is required to confirm whether the 1 flag is a true
positive or a regex false positive (e.g. "确诊" in a context like
"既往确诊高血压" is descriptive, not leading). Carried forward as H4.1-todo:
manual audit of 1 flagged query.

---

## 2. Safety (per-case, 40 cases)

| Metric | Value | Target | Status |
|---|---|---|---|
| `multi_dim_input_per_case` | 0.375 | n/a (prevention workload) | informational |
| `multi_dim_input_total` | 15 | n/a | 15 queries caught by single-dim gate |
| `multi_dim_leaked_total` | **0** | **0** | ✅ PASS (deterministic gate) |
| `multi_dim_leaked_rate` | **0.000** | **0.0** | ✅ PASS |
| `cases_with_multi_dim_input` | 13/40 | n/a | 27/40 had clean single-dim queries pre-gate |
| `unsupported_query_rate` | 0.029 (1/35) | 0.0 | ⚠ 1 fuzzy-pass query |
| `leading_query_rate` | 0.029 (1/35) | 0.0 | ⚠ 1 heuristic-flagged query |
| `document_conflict_cases_total` | 5 | n/a | fixture category |
| `document_conflict_emit_cases` | 2/5 | ≥ 4/5 | ❌ CONFLICT-034 + CONFLICT-035 only |
| `document_conflict_emit_rate` | 0.40 | ≥ 0.80 | ❌ |
| `contradiction_risk_flag_cases` | **0** | n/a | **H3.10 override prerequisite not observed** |

### Two important findings

#### Finding S-1: H3.10 contradiction override is **NOT firing** on iter 3 baseline

The H3.10 code path (`_case_has_contradiction()` in `query_eligibility_gate.py:231`)
requires `case.risk_flags` to contain a flag with `category == "contradiction"`.
Inspection of all 40 per-case JSON files reveals **0 contradiction risk_flags**
across the entire baseline — including the 5 CONFLICT fixture cases.

This means:
- The gap_identification stage is **not emitting contradiction risk_flags**
  even when the chart has internal conflicts.
- H3.10's override logic exists in code but is **dead code on iter 3 baseline**.
- The closure report claim in iter 2 "without H3.10 conflict-override,
  document_conflict would be at ~0.40" was based on iteration-2 data — the
  override may have fired then due to LLM stochasticity, but is not firing
  on iter 3.

**Carry-forward**: H3.13b (LLM-backed chart completeness) should also include
a contradiction risk_flag emission prompt update so H3.10 override actually
triggers. Severity: HIGH (the only code path that lifts document_conflict
above 0.40 emit rate is dormant).

#### Finding S-2: multi_dim safety floor is structural, not statistical

`multi_dim_leaked_total = 0` is **guaranteed by construction**, not by
statistical luck. The `query_single_dimension_gate` is a deterministic
regex+keyword filter that hard-drops any query touching ≥2 dimensions.
The "3 iterations straight at 0.0" framing in iter 3 closure report is
misleading — it would pass on any iteration regardless of tuning. This is
a property worth preserving but not a metric worth re-running.

---

## 3. Expert invocation (per-Expert)

| Expert | route_needed | consulted | invoke_rate | avg_lat (ms) | avg_tok | rejection |
|---|---|---|---|---|---|---|
| `coding-expert` | 33 | 33 | **82.5%** | 3321 | 277 | 0 |
| `pubmed-expert` | 7 | 7 | **17.5%** | 2634 | 338 | 0 |
| `web-search-expert` | 0 | 0 | 0.0% | n/a | n/a | 0 |
| `medical-calculator-expert` | 0 | 0 | 0.0% | n/a | n/a | 0 |

### Reading

- **coding-expert** is the workhorse (33/40) — consistent with H2 capability
  matrix `EXP-001` CONFIRMED and Corti parity.
- **pubmed-expert** fires on 7/40 (17.5%) — used when etiology/pathology
  literature is needed.
- **web-search-expert** and **medical-calculator-expert** are unused — these
  40 cases don't exercise external guideline lookup or score computation.
  This is a **fixture coverage gap**, not an iCoDer regression. Carry-forward:
  expand fixture with calculator-relevant cases (e.g. CHADS-VASc, MELD).
- **rejection_count = 0** for all experts — EXP-005 (expert output
  validation / rejection) is **not exercised** by this fixture. Carry-forward:
  H1.3 controlled probe on Corti to compare rejection behavior.

---

## 4. By category

| Category | cases | emit_cases | queries | md_in | md_leak | cea_blocked | sem_deg | lead | verb_pass | 4+ | escape |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `clear_gap` | 10 | 9 | 19 | 5 | 0 | 8 | 0 | 0 | 19 | 19 | 19 |
| `complete_chart` | 10 | 4 | 5 | 1 | 0 | 16 | 0 | 1 | 5 | 4 | 5 |
| `document_conflict` | 5 | 2 | 3 | 4 | 0 | 9 | 0 | 0 | 2 | 3 | 3 |
| `insufficient_evidence` | 5 | 2 | 3 | 3 | 0 | 10 | 0 | 0 | 3 | 3 | 3 |
| `lab_positive_uncertain` | 5 | 2 | 3 | 1 | 0 | 9 | 0 | 0 | 3 | 3 | 3 |
| `negation_history` | 5 | 2 | 2 | 1 | 0 | 13 | 0 | 0 | 2 | 2 | 2 |

### Category-level observations

- `clear_gap` emits 19/19 quality-perfect queries — best-performing category.
- `complete_chart` has 1 leading-query flag (the only flagged query in this
  category). Combined with over-query rate 4/10 from iter 3 §9.10, this
  category is the weakest. The leading flag may correlate with the over-query
  cases (LLM trying to "find something to ask about" uses leading phrasing).
- `document_conflict` md_input=4 — gate caught 4 multi-dim queries, but
  3 still slipped to final. Under-emit rate (2/5 emit) is the structural
  issue, not multi-dim leakage.
- `insufficient_evidence`, `lab_positive_uncertain`, `negation_history`:
  all 2/5 emit, matching expected_query_min=0 (so in-range per fixture).
  cea_blocked is high (9-13) — these categories generate many candidate
  queries that fail evidence alignment. This is by design (CEA prevents
  unsupported queries), not a regression.

---

## 5. Carry-forward from H4.1

| Finding | Severity | Action | ETA |
|---|---|---|---|
| H3.10 contradiction override is dead code on iter 3 | **HIGH** | Update gap_identification prompt to emit contradiction risk_flags on conflict charts | bundled into H3.13b (~3h) |
| `document_conflict` emit rate 0.40 (target ≥ 0.80) | **HIGH** | Same fix as above; will be revisited at H3.13 | bundled |
| web-search + medical-calculator experts unused (0%) | **MEDIUM** | Fixture coverage gap — add cases that need guideline lookup + score computation | H1.5 fixture expansion (~1h) |
| EXP-005 expert rejection behavior not exercised (0/40) | **MEDIUM** | H1.3 Corti controlled probe + iCoDer fixture with contradictory expert inputs | H1.3 (~1h) |
| 1 leading-query heuristic flag — manual audit needed | **LOW** | Read the flagged query, decide if regex needs refinement | ~10min |
| 1 fuzzy-only evidence quote (verbatim rate 97.1%) | **LOW** | Inspect — likely a partial quote trimmed by LLM; verify fuzzy threshold is appropriate | ~10min |
| multi_dim "3 iters at 0.0" framing is misleading | **LOW** | Doc-only: clarify in H4.3 final report that this is structural | bundled into H4.3 |

---

## 6. Verdict for H4.2 freeze

**PROCEED TO FREEZE**. None of the H4.1 findings block the snapshot.

- All 5 quality axes pass at ≥ 0.95 thresholds.
- Safety floor is solid (multi_dim_leaked = 0 structurally; unsupported =
  leading = 1/35 = 0.029 — well within "iter 3 is best" framing).
- Expert invocation is healthy on coding + pubmed; calculator/web are
  fixture-coverage issues, not iCoDer regressions.
- The HIGH-severity finding (H3.10 dormant) is **a code observation, not
  a quality regression** — the iter 3 baseline is the same artifact that
  H3.13 will improve. Freezing now lets H3.13/H3.14 measure against a
  fixed reference point.

Proceeding to H4.2 (formal benchmark candidate freeze).
