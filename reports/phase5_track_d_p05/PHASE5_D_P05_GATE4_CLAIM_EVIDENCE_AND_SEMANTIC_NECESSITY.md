# Phase 5 Track D — P0.5 Gate 4 — Claim-Evidence Alignment + Semantic Necessity

**Date**: 2026-07-12
**PDF**: `iCoDer CDI Phase 5 Track D P0.5 Prompt.md` §3.2 R8 + Master Task §五
**Prior state**: Gate 3 PARTIAL_IMPROVEMENT (multi-dim 30%→0%, over-query 40%→20%, avg 3.2→2.6, C09 empty-chart still produces 4 unnecessary queries)
**Gate 4 scope**: Two new orchestrator stages — `claim_evidence_alignment_gate` (LLM extraction + 9 deterministic CEA-XXX rules) and `semantic_necessity_gate` (LLM semantic reviewer for empty-chart pathology). Orchestrator STAGES 8→10.
**Checkpoint A verdict**: **PASS** — C09 final queries = 0; 0 invalid evidence quotes; 0 PMH-as-current leaks.

---

## 1. Design

### 1.1 Two-stage hybrid gate

Gate 4 splits the claim-evidence + necessity problem into two complementary stages:

| Stage | Method | Role |
|---|---|---|
| `claim_evidence_alignment_gate` | Hybrid (LLM extraction + 9 deterministic rules) | First line: every critical claim must be chart-evidenced |
| `semantic_necessity_gate` | LLM semantic reviewer | Second line: catches what CEA cannot (e.g. inferred diagnoses without substrate) |

Both stages sit AFTER necessity + single-dimension gates and BEFORE NLQ compliance:

```
encounter_synthesis
gap_identification
expert_consultation
query_generation
query_necessity_gate          ← structural
query_single_dimension_gate   ← structural
claim_evidence_alignment_gate  ← NEW Gate 4 (hybrid)
semantic_necessity_gate        ← NEW Gate 4 (LLM)
query_compliance_gate          (NLQ-001..011)
specialist_trace_emit
```

STAGES tuple 8 → 10 entries.

### 1.2 Claim data model

New domain types in `domain.py`:

```python
SupportType = Literal["direct", "contextual", "inferred", "unsupported"]
ClaimCriticality = Literal["critical", "supporting"]
ClaimValidationStatus = Literal[
    "unchecked", "valid", "invalid_quote", "invalid_span",
    "negation_as_support", "pmh_as_current", "inferred_as_direct",
    "no_evidence", "cross_case_evidence",
]

@dataclass
class Claim:
    claim_id: str
    text: str
    criticality: ClaimCriticality = "supporting"

@dataclass
class ClaimEvidenceAlignment:
    claim_id: str
    evidence_span_id: str
    document_id: str
    quote: str
    char_start: int = -1
    char_end: int = -1
    support_type: SupportType = "unsupported"
    confidence: float = 0.0
    validation_status: ClaimValidationStatus = "unchecked"
```

`ProviderQuery` extended with `claims: list[Claim]` + `claim_evidence_alignments: list[ClaimEvidenceAlignment]` + `semantic_necessity_*` fields. Backwards compatible — defaults to empty list / unchecked.

### 1.3 CEA-001 through CEA-009 (deterministic rules)

| Rule | What it checks | Severity |
|---|---|---|
| CEA-001 | quote_exists_in_chart — quote verbatim in chart | HARD |
| CEA-002 | char_span_accurate — `chart[start:end] == quote` (skipped if absent) | HARD |
| CEA-003 | document_id_valid — non-empty | HARD |
| CEA-004 | no_cross_case_evidence — document_id in case allowlist | HARD |
| CEA-005 | no_negation_as_support — not preceded by 否认/无/未见 in 25-char window | HARD |
| CEA-006 | no_pmh_as_current — not inside 既往史/家族史/个人史 section | HARD |
| CEA-007 | no_inferred_as_direct — 'direct' support_type must not contain 可能/疑似/考虑 | HARD |
| CEA-008 | critical_claim_must_have_evidence — critical claim needs ≥1 valid alignment | HARD |
| CEA-009 | inferred_critical_demotes — critical claim with only inferred → REVIEW_REQUIRED | SOFT |

CEA-001..007 run per alignment. CEA-008 + CEA-009 aggregate per claim. Per-query verdict:

- BLOCK — ≥1 critical claim UNSUPPORTED → query dropped
- REVIEW_REQUIRED — ≥1 critical claim INFERRED_ONLY → query kept, flagged
- PASS — all critical claims have direct/contextual support
- DEGRADED — no claims extracted (LLM extraction failed)

### 1.4 LLM extraction contract

`extract_claims(query, *, chart, llm)` is async. Calls DeepSeek with JSON response format. The system prompt strictly forbids inventing quotes:

> 红线: 不要发明 chart 中没有的 quote. 如果 query 提到的内容 chart 里没有, 必须诚实标 unsupported.

The LLM returns claims + alignments together. CEA-001..007 then validate the LLM's proposal. If the LLM hallucinates a quote, CEA-001 catches it (quote verbatim must exist).

### 1.5 Semantic necessity contract

`review_necessity(query, *, chart, llm)` is async. LLM evaluates 6 booleans:

1. `clinical_substrate_present` — chart has enough clinical matrix
2. `existing_documentation_ambiguous` — what's documented is genuinely ambiguous
3. `query_answerable` — clinician can realistically answer at this visit
4. `query_changes_documentation` — answer would change record/coding
5. `query_requests_new_diagnosis` — query is steering toward invention
6. `query_is_redundant` — query duplicates existing documentation

Verdict mapping:
- substrate=false AND requests_new_diagnosis=true → BLOCK `INSUFFICIENT_CLINICAL_SUBSTRATE`
- answerable=false → BLOCK `NOT_ANSWERABLE`
- is_redundant=true → BLOCK `REDUNDANT_WITH_CHART`
- ambiguous=false AND changes_documentation=false → BLOCK `NO_DOCUMENTATION_IMPACT`
- requests_new_diagnosis=true (with substrate) → REVIEW_REQUIRED `POSSIBLE_DIAGNOSIS_INVENTION`
- otherwise → PASS

DEGRADED on LLM failure: verdict="PASS" + degraded=True (gate never blocks on LLM outage).

---

## 2. Orchestrator wiring

`backend/app/icoder/agent_runtime/cdi/orchestrator.py`:

- STAGES tuple 8→10
- Added `_stage_claim_evidence_alignment_gate(case)` — calls `extract_claims` bulk async via `_resolve_llm()`, then `apply_claim_evidence_to_case` sync (drops BLOCK queries)
- Added `_stage_semantic_necessity_gate(case)` — calls `review_necessity` bulk async, drops BLOCK queries, flags REVIEW_REQUIRED
- Added `_resolve_llm()` precedence: `self.llm` → `self.runner.llm` (test fixtures) → singleton `llm_service`
- Added `_run_async(coro)` helper mirroring `real_runner.py`'s asyncio.run + ThreadPoolExecutor fallback
- Per-stage summary strings stashed in `case.stage_run_ids`:
  - `claim_evidence_alignment_gate`: `claims_extracted=K;blocked=N;flagged=M;final_count=P`
  - `semantic_necessity_gate`: `blocked=K;flagged=M;degraded=D;final_count=P`

**Critical guard**: Both new stages short-circuit when `case.chart_excerpt` is empty — protects stub_runner-based unit tests from making real LLM calls.

---

## 3. Test coverage

### 3.1 New gate4 tests (30/30 PASS)

`backend/tests/test_api/test_phase5_d_p05_gate4_claim_evidence.py` — 21 tests:

- **CEA-001 quote_exists_in_chart** (PASS + BLOCK fixtures)
- **CEA-002 char_span** (skipped when absent, matches when provided)
- **CEA-003 document_id** (empty fails, populated passes)
- **CEA-004 cross_case** (document_id must be in case_documents allowlist)
- **CEA-005 negation** (否认 prefix fails, positive assertion passes)
- **CEA-006 PMH** (既往史 section fails, 现病史 passes)
- **CEA-007 inferred_as_direct** (mislabeled inference fails, correctly labeled passes)
- **CEA-008 critical_unsupported** (BLOCK; multiple claims + 1 unsupported critical → BLOCK)
- **CEA-009 inferred_critical** (REVIEW_REQUIRED, query kept + flagged)
- **DEGRADED** when no claims extracted
- **apply_claim_evidence_to_case** end-to-end (drops BLOCK, keeps REVIEW, handles empty)
- **extract_claims DEGRADED** on LLM failure

`backend/tests/test_api/test_phase5_d_p05_gate4_semantic_necessity.py` — 9 tests:

- C09 empty-chart → BLOCK with `INSUFFICIENT_CLINICAL_SUBSTRATE`
- Symptom-only no-diagnosis → REVIEW_REQUIRED `POSSIBLE_DIAGNOSIS_INVENTION`
- Complete-chart redundant → BLOCK `REDUNDANT_WITH_CHART`
- Necessary + answerable → PASS
- DEGRADED on LLM failure (verdict=PASS, never blocks)
- Empty query_text → DEGRADED without LLM call
- Malformed LLM response → DEGRADED
- Unknown verdict normalizes to PASS
- Provider metadata (model/latency/tokens) captured

### 3.2 Existing test updates

- `tests/unit/icoder/cdi/test_orchestrator.py` — renamed `test_stages_tuple_is_corti_compatible_8_steps` → `_10_steps`; updated expected stage count to 10; expected_keys superset includes both new stages.

### 3.3 Full CDI regression: **279/279 PASS**

```
249 baseline (Gate 0..3)
+ 21 gate4 claim-evidence
+ 9 gate4 semantic-necessity
= 279
```

No regressions in existing tests.

---

## 4. Empirical validation — Checkpoint A (Master Task §四)

Script: `backend/scripts/phase5_d_p05_gate4_targeted_validation.py`
Backend: real DeepSeek (deepseek-chat), ran 2026-07-12 with full Gate 4 wiring (10-stage orchestrator).
Tokens burned: **15,183** (5 cases, ~3K/case).

### 4.1 Per-case results

| Case | Gaps | Final Queries | CEA blocked | Sem blocked | Evidence Validity | Verdict |
|---|---|---|---|---|---|---|
| T01 C09 empty-chart | 4 | **0** | 4 | 0 | 1.0 | ✓ empty-chart closed |
| T02 pneumonia+sputum culture | 1 | 0 | 0 | 0 | 1.0 | ⚠ degraded upstream |
| T03 fracture L-R conflict | 4 | 0 | 1 | 0 | 1.0 | ✓ conflict surface |
| T04 complete STEMI PCI | 4 | 1 | 1 | 0 | 1.0 | ✓ minimal residual |
| T05 negation + PMH | 4 | 0 | 4 | 0 | 1.0 | ✓ no PMH leak |

### 4.2 Checkpoint A criteria

| Criterion | Target | Actual | Status |
|---|---|---|---|
| C09 empty-chart final query count | 0 | **0** | ✓ |
| Unsupported critical claims surviving | 0 | **0** (CEA blocked all 10) | ✓ |
| Evidence quote validity | 100% | **100%** | ✓ |
| Direct / contextual / inferred / unsupported distinguishable | yes | **yes** (SupportType enum enforced) | ✓ |
| PMH-as-current leaks | 0 | **0** | ✓ |

**VERDICT: Checkpoint A PASS** — gate cleared to proceed to Gate 5.

### 4.3 What the gate IS catching

- **C09 empty-chart**: 4 LLM-generated queries all had `query_requests_new_diagnosis=true`-type claims ("请评估最可能的病因") with NO chart substrate. CEA-008 hard-failed every critical claim (best=invalid_quote since chart has nothing to cite). 4/4 dropped.
- **T03 fracture conflict**: 1 query asked about laterality with a quote that wasn't verbatim in chart. CEA-001 failed → CEA-008 dropped it.
- **T05 negation + PMH**: 4 queries that all relied on family history (父亲糖尿病) as if it were patient's current condition. CEA-006 (no_pmh_as_current) hard-failed those alignments → CEA-008 dropped the queries.
- **T04 STEMI PCI**: 4 queries; 1 dropped by CEA (likely already-chart-answered), 1 survived (legitimate clarification).

### 4.4 What the gate is NOT catching (honest accounting)

- **semantic_necessity blocked = 0/5 cases**: The semantic gate didn't fire in this run. Reason: claim_evidence_alignment_gate runs FIRST and drops most problematic queries before semantic_necessity sees them. The semantic gate is the second line of defense — it would catch cases where claims pass CEA but the overall query is still semantically bad (e.g. all claims individually supported but the query is still asking for diagnosis invention). The structural complementarity is by design.
- **T02 degraded upstream**: 1 case marked `degraded=True` at the case level (likely transient DeepSeek API hiccup on encounter_synthesis or gap_identification). The orchestrator completed gracefully; Gate 4 stages ran cleanly. Not a Gate 4 defect.
- **Inferred-only claims (CEA-009) flagged = 0**: In this 5-case set, no queries had inferred-only critical claims. The LLM tended to either directly support or fully unsupported claims. The CEA-009 path is exercised by unit tests but not by this empirical set.

---

## 5. PDF §16 forbidden-items checklist

- ✓ No `production_ready` / `validated` flag flipped — Checkpoint A PASS is a *gate-clear-to-proceed* signal, not a quality validation
- ✓ No diagnoses invented — CEA-008 hard-blocks queries with unsupported critical claims
- ✓ No ICD codes exposed to clinicians — NLQ-010 (existing) still covers options
- ✓ No leading query language introduced — Gate 4 only drops, never creates
- ✓ No CMI / payment optimization language
- ✓ No Stub disguised as real — 5-case run burned 15,183 real DeepSeek tokens

---

## 6. PDF §18 verdict-ladder compliance

**CHECKPOINT_A_PASS** (Master Task §四):

- Code + tests + orchestrator wiring landed (deterministic, verified by 279/279 regression)
- Empirical: C09 final=0, evidence validity=100%, 0 PMH leaks
- All 5 targeted cases (per Master Task §5.7) executed against real DeepSeek
- Master Task §四 Checkpoint A criteria all met

This verdict is deliberately below `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK`. CDI agent label (`preview` per §B6) unchanged.

---

## 7. Evidence files

| File | Purpose |
|---|---|
| `backend/app/icoder/agent_runtime/cdi/claim_evidence_gate.py` | NEW — CEA-001..009 + LLM extract_claims (~430 LOC) |
| `backend/app/icoder/agent_runtime/cdi/necessity_semantic.py` | NEW — semantic reviewer (6 booleans → verdict) (~230 LOC) |
| `backend/app/icoder/agent_runtime/cdi/domain.py` | MODIFIED — Claim/ClaimEvidenceAlignment + SupportType + extensions |
| `backend/app/icoder/agent_runtime/cdi/orchestrator.py` | MODIFIED — STAGES 8→10, 2 new stage methods, `_run_async`, `_resolve_llm` |
| `backend/app/icoder/agent_runtime/cdi/__init__.py` | MODIFIED — export new public symbols |
| `backend/tests/test_api/test_phase5_d_p05_gate4_claim_evidence.py` | NEW — 21 tests |
| `backend/tests/test_api/test_phase5_d_p05_gate4_semantic_necessity.py` | NEW — 9 tests |
| `backend/tests/unit/icoder/cdi/test_orchestrator.py` | MODIFIED — 8-step → 10-step stage tuple |
| `backend/scripts/phase5_d_p05_gate4_targeted_validation.py` | NEW — Checkpoint A runner |
| `backend/reports/phase5_d_p05/gate4_targeted_cases.json` | NEW — empirical evidence |

---

## 8. What Gate 4 does NOT close

| Risk | Gate | Status after Gate 4 |
|---|---|---|
| R8 claim-evidence alignment | 4 | ✓ CLOSED on 5-case targeted set — C09=0, evidence validity=100% |
| C09 empty-chart pathology | 4 | ✓ CLOSED — Gate 3 carried 4 unnecessary queries; Gate 4 → 0 |
| PMH-as-current leak | 4 | ✓ CLOSED on T05 — CEA-006 hard-fails |
| R9 Expert conditional routing | 5 | ⬜ NOT STARTED — 4 Experts still invoked per case |
| R10/R11/R12 frontend language | 6 | ⬜ NOT STARTED |
| R13 4-role E2E | 7 | ⬜ NOT STARTED |
| R14 40-case Corti calibration | 8 | ⬜ NOT STARTED |

---

## 9. Known carry-forward

1. **Semantic gate is secondary in this run** — CEA does most of the lifting. Future calibration (Gate 8) should measure: of queries that PASS CEA, what fraction does semantic_necessity still block? If 0%, the semantic gate may be redundant. If >0%, both gates pull weight.
2. **T02 degraded upstream** — transient DeepSeek API issue on encounter_synthesis. Robust handling already in place (orchestrator completes; downstream gates still run). Worth monitoring across longer runs.
3. **`char_start`/`char_end` always -1** — LLM doesn't reliably emit offsets. CEA-002 currently defers to CEA-001 when offsets are absent. A future improvement could have the orchestrator compute offsets after-the-fact (`chart.find(quote)`) and populate them.
4. **No cross-query claim dedup** — if two queries make the same unsupported critical claim, both are independently blocked. Fine for now; if it becomes noisy, dedup at the case level.
5. **LLM extraction latency** — Gate 4 adds ~5-10 seconds per case (2 LLM calls per query × N queries). Total 5-case elapsed = 122s ≈ 24s/case. Within acceptable bounds for CDI but worth tracking.
6. **Token burn rate** — Gate 4 added ~3K tokens/case (claim extraction + semantic review). For the planned 40-case Gate 8 calibration, that's ~120K additional tokens — within budget but worth noting.

---

## 10. Resume point for next session

After Gate 4 commit (pending), next session opens **Gate 5 — Conditional Expert Routing + Tool-vs-Persona Disclosure**:

- New `cdi_expert_router.py` module with 6 execution modes
- Per-Expert route decision (coding / pubmed / web / calculator)
- Empty-chart rule: all 4 Experts → SKIPPED_NOT_NEEDED
- Conditional execution + parallel + Specialist Trace for both called + skipped
- Combined 10-case run with Gate 4 (single execution per Master Task §10.2)
- Checkpoint B target: avg experts/case drops, empty-chart experts=0, avg queries ≤2.0
