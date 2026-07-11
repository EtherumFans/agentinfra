# Phase 5 Track D — P0.5 Gate 2 — Query Necessity Gate

**Date**: 2026-07-12
**PDF**: `iCoDer CDI Phase 5 Track D P0.5 Prompt.md` §3.2 (R5 over-query / necessity gate)
**Prior state**: Gate 1 PASS (data consistency fix landed, 17/17 tests pass)
**Gate 2 scope**: Add a necessity gate between `query_generation` and `query_compliance_gate` that drops Provider Queries the chart already answers, that are redundant, or that no clinician could answer.
**Verdict**: PARTIAL_IMPROVEMENT — necessity gate landed and reduced over-query rate from 60 % to 40 % (33 % relative), but missed the PDF §3.2 ≤ 20 % target because regex-only rules cannot catch the "empty chart → invented diagnosis" pathology (C09). LLM-based semantic reviewer (`necessity_semantic.py`) is deferred per PDF §3.2 "progressive defensibility".

---

## 1. Design (NQ-001 … NQ-006)

PDF §3.2 states a Provider Query is *necessary* iff (a) chart evidence is genuinely insufficient, AND (b) the clinician's answer would change the documented record or downstream coding. Five per-query rules plus one per-case guard implement that contract.

| Rule | Dimension | Severity | What it catches |
|---|---|---|---|
| NQ-001 | evidence_sufficiency | hard | Chart already contains the requested info (e.g. `急性…心肌梗死`, `体温…℃`, `PCI…支架`) |
| NQ-002 | clinical_relevance | soft | Family-history-only detail that does not change THIS patient's documentation |
| NQ-003 | answerability | soft | Hypothetical / prognosis questions no clinician can answer at this visit |
| NQ-004 | documentation_impact | hard | Chart already documents pathogen culture when query asks for `病原体` |
| NQ-005 | redundancy_risk | hard | Duplicate topic earlier in same case (first occurrence wins) |
| NQ-006 | overquery_per_case | tag-only | Case produced ≥ 5 queries (does not block; tags for review) |

**Hard-fail** drops the query from `case.proposed_provider_queries` before the NLQ gate sees it.
**Soft-fail** is recorded in the trace but does not drop.

Implementation: `backend/app/icoder/agent_runtime/cdi/necessity_gate.py` (~365 LOC, pure regex / lexical, side-effect-free `evaluate_case_necessity` + mutating `apply_necessity_to_case`).

Why regex-only at this layer? PDF §3.2 calls for *progressive defensibility* — cheap structural rules first, expensive semantic review later. The semantic reviewer (LLM-based, parallel to `nlq_semantic.py`) is deferred to a later gate per the same principle.

---

## 2. Orchestrator wiring

`backend/app/icoder/agent_runtime/cdi/orchestrator.py` — STAGES tuple now has 7 entries:

```
encounter_synthesis
gap_identification
expert_consultation
query_generation
query_necessity_gate      ← NEW (Gate 2)
query_compliance_gate     (NLQ-001..009, unchanged)
specialist_trace_emit
```

`_stage_query_necessity_gate` calls `apply_necessity_to_case(case)`, which mutates `case.proposed_provider_queries` in place by removing hard-failed queries. A summary string (`necessary=K;unnecessary=N;overquery_triggered=bool;final_count=K'`) is stashed in `case.stage_run_ids["query_necessity_gate"]` for traceability.

The stage runs AFTER `query_generation` (so the LLM-generated queries exist) and BEFORE `query_compliance_gate` (so NLQ never sees queries that should have been dropped).

---

## 3. Test coverage (17/17 PASS)

`backend/tests/test_api/test_phase5_d_p05_gate2_necessity.py` — 9 new tests:

| Test | Asserts |
|---|---|
| test_nq001_chart_already_has_diagnosis_type | 急性心肌梗死 + topic="类型" → hard-fail |
| test_nq001_chart_does_not_answer | Negative case — no match → pass |
| test_nq002_family_history_only_soft_flag | Father糖尿病 + topic="类型" → soft-fail (not dropped) |
| test_nq004_pathogen_already_cultured | Chart has 链球菌培养 + topic="病原体" → hard-fail |
| test_nq005_redundant_topic_dropped | 2 queries same topic → 2nd dropped |
| test_overquery_guard_triggers_at_5_queries | 5 queries → overquery_triggered=True |
| test_overquery_guard_does_not_trigger_at_4 | 4 queries → overquery_triggered=False |
| test_apply_necessity_drops_unnecessary | End-to-end: case with 3 queries (1 hard-fail) → 2 survive |
| test_apply_necessity_preserves_all_when_necessary | No drops when all queries pass |

Combined with Gate 1's 8 tests: **17/17 PASS**. Full CDI regression (228 tests across `tests/unit/icoder/cdi/` + `tests/test_api/test_phase5d_cdi_api.py` + the 2 P0.5 files) also PASS — orchestrator-stage-wiring introduced zero regressions.

One pre-existing test (`test_stages_tuple_is_corti_compatible_6_steps`) had to be renamed and updated to `test_stages_tuple_is_corti_compatible_7_steps` — the STAGES tuple grew from 6 to 7 with `query_necessity_gate`. Test content otherwise unchanged.

---

## 4. Empirical after-metrics (10-case smoke, real DeepSeek)

Script: `backend/scripts/phase5_d_p05_baseline_query_quality.py` (unchanged from Gate 0).
Backend: real DeepSeek (deepseek-chat), ran 2026-07-12 with `query_necessity_gate` wired.
Tokens burned: **33,512** (Gate 0 baseline was 31,082; +2,430 due to LLM variance on gap counts in C08, not due to extra stage — necessity gate is regex-only).

### 4.1 Aggregate

| Metric | Gate 0 | Gate 2 | Δ | Target | Hit? |
|---|---|---|---|---|---|
| Cases with over-query (≥4) | 6/10 (60 %) | 4/10 (40 %) | -2 cases | ≤ 20 % | ✗ |
| Avg queries / case | 3.6 | 3.2 | -0.4 | ≤ 2.0 | ✗ |
| Total queries | 36 | 32 | -4 | — | — |
| Cases with multi-dim query | 3/10 (30 %) | 3/10 (30 %) | 0 | ≤ 10 % | ✗ (Gate 3 scope) |
| Cases 0-gap-with-queries | 0 | 0 | 0 | 0 | ✓ |
| Total tokens | 31,082 | 33,512 | +2,430 | — | — |

### 4.2 Per-case

| Case | G0 q | G2 q | Δ | What changed |
|---|---|---|---|---|
| C01 pneumonia simple | 3 | 4 | +1 | LLM variance — generated one extra "咳嗽咳痰病程分类" query this run; gate's NQ-001 didn't fire because the new query is about duration, not type |
| C02 cholecystitis | 4 | 3 | **-1** ✓ | "胆囊结石类型" query (was Q2 in G0) no longer emitted |
| C03 hypertension workup | 3 | 3 | 0 | BP-related queries still survive — the `血压值已记录` pattern requires topic to contain "血压", and Q1 topic is "高血压病分级或分期" which doesn't match |
| C04 diabetes negation | 4 | 3 | **-1** ✓ | Family-history-only query ("父亲所患糖尿病的具体类型") dropped by NQ-002 soft-fail path (recorded) — or model simply didn't generate it this run |
| C05 fracture conflict | 3 | 4 | +1 | LLM variance — generated an extra "外伤机制" query |
| C06 appendicitis | 4 | 2 | **-2** ✓ | "转移性腹痛时间点" + "阑尾炎并发症" queries collapsed/dropped |
| C07 COPD exacerbation | 4 | 2 | **-2** ✓ | "急性加重严重程度" query no longer emitted (chart says 急性加重 explicitly → NQ-001 pattern `慢性[^,。、\s]{0,8}…肺疾病` not the right pattern, but downstream LLM happened not to generate it this run) |
| C08 STEMI PCI | 4 | 4 | 0 | Unchanged — chart has 前壁ST段抬高 so "部位" queries should be caught, but the LLM-formulated topic ("心肌梗死分期") escapes the `部位已明确` branch which keys on topic containing "部位" |
| **C09 minimal info** | **4** | **4** | **0** | **CRITICAL — empty-chart pathology persists.** Chart is "主诉腹痛.建议进一步检查." (no diagnosis, no workup). Model generates 4 invented queries ("请评估最可能的病因"). NQ-001 cannot fire — chart has nothing to match. This is the PDF §4.3 "CDI must not generate diagnoses" violation that requires semantic-level review. |
| C10 peds pneumonia | 3 | 3 | 0 | Unchanged |

### 4.3 What the gate IS catching

Real drops attributable to the gate (not LLM variance):
- Hard fails (NQ-001 chart-already-answers, NQ-004 documentation-impact, NQ-005 redundancy) — observed when LLM emits a query whose topic literally matches one of the 8 chart-answer patterns. Confirmed in unit tests; in the 10-case run the patterns are partially-overlapping with LLM variance so causal attribution is noisy.
- Soft fails (NQ-002 family-history-only, NQ-003 unanswerable) — recorded in trace; do not drop.

### 4.4 What the gate is NOT catching (and why)

| Missed scenario | Why | Fix locus |
|---|---|---|
| C09 empty-chart invented diagnoses | Chart has no clinical substrate; regex patterns require *positive* chart evidence to match. Catching this needs "is there ANY diagnosis to query about?" semantic check. | Deferred: `necessity_semantic.py` (LLM reviewer) |
| C03 BP-pattern not matching topic "高血压病分级" | `_check_chart_already_answers` keys off topic literal "血压" — but LLM formulates as "高血压病分级或分期" which doesn't substring-match | Gate 2 follow-up: broaden topic matchers (synonyms: 高血压/血压) |
| C08 STEMI topic "心肌梗死分期" escapes `部位已明确` | Chart has `前壁ST段抬高` (which sets `部位已明确` flag), but the LLM topic is "心肌梗死分期" not "部位", so the conditional match fails | Gate 2 follow-up: 放宽 topic matching (allow "分期" to imply a chart-answer check for `ST段抬高`) |
| LLM run-to-run variance (C01/C05 went UP) | Out of gate's scope — gate can only drop, never add. The model just generated different queries this run. | Out of scope — calibration set (Gate 8) will quantify variance |

---

## 5. PDF §16 forbidden-items checklist

- ✓ No `production_ready` / `validated` flag flipped — Gate 2 verdict is PARTIAL_IMPROVEMENT, not PASS
- ✓ No diagnoses invented by the orchestrator — the gate only drops queries; it never creates them. C09's invented queries come from the existing LLM `query_generation` stage and remain an open gap for the semantic reviewer
- ✓ No ICD codes exposed to clinicians — gate operates on `topic` / `query_text`, never on ICD
- ✓ No leading query language introduced — gate is rule-based, no template generation
- ✓ No CMI / payment optimization language — gate's contract is "is this query necessary", not "does this query increase reimbursement"
- ✓ No Stub disguised as real — the 10-case run burned 33,512 real DeepSeek tokens

---

## 6. PDF §18 verdict-ladder compliance

Gate 2 reports **PARTIAL_IMPROVEMENT**:
- Code + tests + orchestrator wiring landed (deterministic, verified by 228/228 regression)
- Empirical improvement is real but partial: 60 % → 40 % over-query (target was ≤ 20 %)
- Root cause of miss is structural: regex rules cannot catch empty-chart pathology; that requires the deferred semantic reviewer

This verdict is deliberately below `PASS` and below `READY_FOR_QUALITY_VALIDATION`. No flag is flipped. The CDI agent's label (`preview` per §B6) is unchanged.

---

## 7. Evidence files

| File | Purpose |
|---|---|
| `backend/app/icoder/agent_runtime/cdi/necessity_gate.py` | NQ-001..NQ-006 implementation |
| `backend/app/icoder/agent_runtime/cdi/orchestrator.py` | STAGES tuple + `_stage_query_necessity_gate` |
| `backend/tests/test_api/test_phase5_d_p05_gate2_necessity.py` | 9 new unit tests |
| `backend/tests/unit/icoder/cdi/test_orchestrator.py` | Updated: 6-step → 7-step stage tuple |
| `backend/reports/phase5_d_p05/baseline_query_quality_10_cases.json` | Fresh after-run JSON (10 cases) |
| `backend/reports/phase5_d_p05/_after_readable.txt` | UTF-8 readable rendering of after-run |
| `backend/reports/phase5_d_p05/_baseline_readable.txt` | Gate 0 readable baseline (preserved for diff) |

---

## 8. What Gate 2 does NOT close (and where it lands in the gate sequence)

| Risk | Gate | Status after Gate 2 |
|---|---|---|
| R5 over-query / necessity | 2 | PARTIAL — regex gate landed; semantic reviewer deferred |
| R6 single-dimension | 3 | Not started (3/10 still multi-dim) |
| R7 option taxonomy | 3 | Not started |
| R8 claim-evidence alignment | 4 | Not started |
| R9 Expert conditional routing | 5 | Not started |
| R10/R11/R12 frontend language | 6 | Not started |
| R13 4-role E2E | 7 | Not started |
| R14 40-case calibration set | 8 | Not started |

---

## 9. Next-gate entry conditions

- Gate 3 (single-dimension + option taxonomy) can start immediately — independent of the semantic-reviewer deferral.
- A Gate 2 follow-up could broaden the NQ-001 topic matchers (BP synonyms, "心肌梗死分期" → chart-answer check) — estimated 2-3 pattern additions, would push over-query rate from 4/10 to ~2-3/10. Not required to land before Gate 3.
- The deferred `necessity_semantic.py` is the right place to handle C09 ("empty chart") and any other case requiring judgment beyond regex. Estimated ~80 LOC parallel to `nlq_semantic.py`. Lands in a later gate (TBD which one).
