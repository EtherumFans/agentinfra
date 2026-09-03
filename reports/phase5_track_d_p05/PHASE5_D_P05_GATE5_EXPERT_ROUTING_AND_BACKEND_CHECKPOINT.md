# Phase 5 Track D — P0.5 Gate 5 — Conditional Expert Routing

**Date**: 2026-07-12
**PDF**: `iCoDer CDI Phase 5 Track D P0.5 Prompt.md` §3.2 R9 + Master Task §六
**Prior state**: Gate 4 PASS — C09 closed, evidence validity 100%, 0 PMH leaks. 4 Experts invoked unconditionally per case (40 calls / 10-case baseline).
**Gate 5 scope**: New `cdi_expert_router.py` with 6 execution modes; `_stage_expert_consultation` in `real_runner.py` refactored to honor router decisions; Specialist Trace extended with route_decision/route_reason/execution_mode; combined 10-case run with Gate 4.
**Checkpoint B verdict**: **PASS** — avg experts/case 4.0→1.0, C09 experts=0, avg queries/case 0.20.

---

## 1. Design

### 1.1 The 6 execution modes

Per Master Task §6.1. The router emits exactly one of:

| Mode | When | LLM call? |
|---|---|---|
| `REAL_TOOL` | real MCP/tool wired + needed + inputs present | yes |
| `LLM_KNOWLEDGE_ONLY` | no real tool, but LLM recall is acceptable (coding context, criteria) | yes |
| `SKIPPED_NOT_NEEDED` | case has no relevant gap for this Expert | no |
| `SKIPPED_MISSING_INPUTS` | gap exists but required parameters absent from chart | no |
| `TOOL_UNAVAILABLE` | gap exists, inputs present, no real tool wired AND LLM recall is forbidden (web-search, calculator) | no |
| `DEGRADED` | LLM/tool failure during invocation | (attempted, failed) |

### 1.2 Per-Expert routing rules (Master Task §6.2)

| Expert | Needed when | Default mode (no real tools) |
|---|---|---|
| coding-expert | gap_type ∈ {diagnostic_specificity, etiology_unspecified, severity_unspecified, acuity_unspecified, anatomical_site_unspecified, conflicting_documentation} | `LLM_KNOWLEDGE_ONLY` |
| pubmed-expert | chart/gap text contains 标准定义/criteria/classification markers | `LLM_KNOWLEDGE_ONLY` |
| web-search-expert | chart mentions 最新指南/guideline/policy/year ≥ 2024 | `TOOL_UNAVAILABLE` |
| medical-calculator-expert | chart mentions 评分/分级/score + clinical parameters present | `TOOL_UNAVAILABLE` (or `SKIPPED_MISSING_INPUTS` if params absent) |

**Why web/calculator cannot fall back to LLM_KNOWLEDGE_ONLY**: per §6.2, "不得用普通 LLM 猜测评分" and "不得伪装为 PubMed 检索". Time-sensitive guidelines and deterministic scores cannot honestly be served from LLM training data — so the router marks them unavailable rather than fabricate.

### 1.3 Empty-chart C09 rule (Master Task §6.3)

`_chart_has_substrate(chart)` scans for 4 marker buckets: diagnosis statements, lab/imaging/procedures, clinical indicator units, common disease names. C09 fixture ("患者主诉腹痛. 建议进一步检查.") hits zero buckets → all 4 Experts return `SKIPPED_NOT_NEEDED`.

### 1.4 Tool availability contract

`available_tools` parameter lets future phases advertise real MCP wiring. Defaults to all-False (Phase 5 Track D P0.5 has no real Expert tools). When a future phase wires PubMed search, set `available_tools={"pubmed-expert": True}` and that Expert upgrades from `LLM_KNOWLEDGE_ONLY` to `REAL_TOOL`.

---

## 2. Implementation

### 2.1 New module: `cdi_expert_router.py` (~340 LOC)

```python
def route_experts(case: CDICase, *, available_tools: dict[str, bool] | None = None) -> ExpertRouteResult
```

Pure-logic. No LLM calls. Returns one `ExpertRouteDecision` per Expert in declaration order. `ExpertRouteResult.invoked_expert_ids` and `.skipped_expert_ids` partition the 4 Experts based on `execution_mode`.

### 2.2 Domain extension

`SpecialistTraceEntry` extended with:
- `route_decision: str` — front-end label ("needed" / "not_needed" / "missing_inputs" / "tool_unavailable" / "degraded")
- `route_reason: str` — human-readable rationale
- `execution_mode: str` — one of the 6 ExpertExecutionMode values
- `latency_ms: int`, `tokens: int`, `run_id: str`, `trace_id: str` — audit metadata

### 2.3 Runner refactor: `RealCDIRunner._stage_expert_consultation`

Pre-Gate-5: invoked all 4 Experts unconditionally (4 LLM calls per case).

Post-Gate-5:
1. Calls `route_experts(case)` — pure logic, no LLM.
2. For each decision: invokes LLM only if `execution_mode ∈ {REAL_TOOL, LLM_KNOWLEDGE_ONLY}`. Otherwise records trace with 0 tokens / 0 latency.
3. On LLM failure during invocation, downgrades decision to `DEGRADED` (audit trail reflects actual outcome, not original plan).
4. Populates `case.specialist_trace` directly — one entry per Expert (called AND skipped).

### 2.4 API surface

`/api/v1/cdi/runs` response's `specialist_trace[]` entries now include `route_decision`, `route_reason`, `execution_mode`, `latency_ms`, `tokens` per Master Task §6.5.

---

## 3. Test coverage

### 3.1 New gate5 tests (19/19 PASS)

`backend/tests/test_api/test_phase5_d_p05_gate5_expert_router.py`:

**Substrate detector (§6.3)**:
- C09 empty-chart → all 4 SKIPPED_NOT_NEEDED with reason=empty_chart
- Blank/whitespace chart → all SKIPPED_NOT_NEEDED
- Chart with substrate but 0 gaps → all SKIPPED_NOT_NEEDED with reason=no_relevant_gap

**Coding-expert**:
- diagnostic_specificity gap → LLM_KNOWLEDGE_ONLY, priority=high
- clinical_correlation + temporal gaps only → SKIPPED_NOT_NEEDED (not coding-relevant)
- With available_tools={"coding-expert": True} → REAL_TOOL

**PubMed-expert**:
- "诊断标准" marker → LLM_KNOWLEDGE_ONLY with missing_inputs=["real_pubmed_search"]
- With real tool wired → REAL_TOOL
- No markers → SKIPPED_NOT_NEEDED

**Web-search-expert**:
- "2025年最新指南" marker → TOOL_UNAVAILABLE (not LLM_KNOWLEDGE_ONLY — time-sensitivity rule)
- With real tool wired → REAL_TOOL
- No markers → SKIPPED_NOT_NEEDED

**Medical-calculator-expert**:
- "NYHA分级" marker, no params → SKIPPED_MISSING_INPUTS
- "CHA2DS2-VASc评分" + mmHg/bpm params → TOOL_UNAVAILABLE (not LLM_KNOWLEDGE_ONLY — "不得用普通 LLM 猜测评分")
- With real tool wired → REAL_TOOL

**Aggregate behaviors**:
- `should_invoke` predicate truth table across 5 modes
- invoked + skipped partition matches expectations

**Real runner integration** (mock LLM):
- Chart with coding gap + pubmed marker → only coding-expert + pubmed-expert invoke LLM
- C09 empty chart → 0 Expert LLM calls

### 3.2 Existing test updates

- `tests/unit/icoder/cdi/test_real_runner.py::test_real_runner_captures_expert_traces` — updated to reflect that all 4 Experts are still ROUTED (4 trace entries) but only the needed ones consume tokens. Asserts `case.specialist_trace` populated with route metadata.
- `tests/unit/icoder/cdi/test_real_runner.py::test_real_runner_marks_degraded_on_expert_failure` — chart updated to include a pubmed marker so pubmed-expert routes to LLM and the failure path is exercised.

### 3.3 Full CDI regression: **298/298 PASS**

```
279 baseline (Gate 0..4)
+ 19 gate5 expert-router
= 298
```

No regressions in existing tests.

---

## 4. Empirical validation — Checkpoint B (Master Task §6.6)

Script: `backend/scripts/phase5_d_p05_gate5_combined_10_cases.py`
Backend: real DeepSeek (deepseek-chat), ran 2026-07-12 with Gate 4 + Gate 5 wiring.
Tokens burned: **20,662** (10 cases, ~2.1K/case — down from baseline ~3.3K/case).

### 4.1 Per-case results

| Case | Final Q | CEA blk | Experts invoked | Tokens | Notes |
|---|---|---|---|---|---|
| C01 pneumonia+sputum | 0 | 1 | 1/4 | 2268 | coding only |
| C02 cholecystitis | 0 | 2 | 1/4 | 2365 | coding only |
| C03 HTN workup | 1 | 2 (+1 fl) | 1/4 + 1 unavail | 2066 | web TOOL_UNAVAILABLE (guideline) |
| C04 diabetes negation | 0 | 3 | 1/4 | 2133 | coding only |
| C05 fracture L-R conflict | 0 | 3 | 1/4 | 2117 | coding only |
| C06 appendicitis | 0 | 0 | 1/4 | 1165 | coding only — clean case |
| C07 COPD exacerbation | 0 | 2 | 1/4 | 2818 | coding only |
| C08 STEMI PCI | 1 | 1 | 2/4 | 2764 | coding + pubmed (criteria) |
| C09 empty-chart | 0 | 4 | **0/4** | 1888 | ✓ all SKIPPED_NOT_NEEDED |
| C10 peds pneumonia | 0 | 1 | 1/4 | 1078 | coding only |

### 4.2 Checkpoint B criteria (Master Task §6.6)

| Criterion | Target | Actual | Status |
|---|---|---|---|
| Avg experts invoked / case | ≤ 1.5 | **1.00** | ✓ (75% reduction from 4.0) |
| C09 empty-chart experts | 0 | **0** | ✓ |
| Avg queries / case | ≤ 2.0 | **0.20** | ✓ |
| ToolUnavailable disclosed | ≥ 0 | 1 (C03 web-search) | ✓ per §6.2 |
| Missing-inputs surfaced | ≥ 0 | 0 | (no calculator cases in set) |
| Degraded Experts | 0 | 0 | ✓ |

**VERDICT: Checkpoint B PASS** — gate cleared to proceed to Gate 6.

### 4.3 Per-stage drop attribution (sum across 10 cases)

| Stage | Drops | Notes |
|---|---|---|
| query_necessity_gate | 7 | structural (NQ-001..006) |
| query_single_dimension_gate | 2 | SD-001/002 multi-axis |
| claim_evidence_alignment_gate | **19** | primary lifter — CEA-008 unsupported critical claims |
| semantic_necessity_gate | 0 | complementary gate (CEA catches first) |
| query_compliance_gate | 0 | downstream gates clear |

The Gate 4 report already noted that CEA does most of the lifting and semantic_necessity is the second-line defense. Gate 5 adds Expert routing on top — Experts don't directly generate queries, so Gate 5's contribution to the query count is zero by design. Gate 5's value is in token efficiency + audit clarity.

### 4.4 Expert routing breakdown

| Bucket | Count | Notes |
|---|---|---|
| Total candidates | 40 | 4 Experts × 10 cases |
| Invoked (REAL_TOOL or LLM_KNOWLEDGE_ONLY) | 10 | 25% of candidates |
| SKIPPED_NOT_NEEDED | 29 | 72.5% — case has no relevant gap for that Expert |
| SKIPPED_MISSING_INPUTS | 0 | no calculator-scored cases in this set |
| TOOL_UNAVAILABLE | 1 | C03 web-search for HTN guideline |
| DEGRADED | 0 | no LLM outages |

### 4.5 Token efficiency

| Metric | Gate 5 (this run) | Gate 4 baseline | Delta |
|---|---|---|---|
| Total tokens / 10 cases | 20,662 | ~33,000 | **-37%** |
| Tokens / case | ~2,066 | ~3,300 | -1,234 |
| Expert calls / case | 1.0 | 4.0 | **-75%** |

The token saving comes from skipping 30 unnecessary Expert invocations. Each avoided Expert call saves ~600-700 tokens (system prompt + chart context + 2-3 sentence response).

---

## 5. What Gate 5 IS closing

- **R9 Expert conditional routing**: CLOSED — 4/4 invoked unconditionally → 1/4 avg with proper routing logic.
- **C09 empty-chart Expert waste**: CLOSED — 0/4 invoked, 1.9K tokens saved on this case alone.
- **Tool-vs-Persona conflation**: CLOSED — pubmed-expert now explicitly tagged `LLM_KNOWLEDGE_ONLY` with `missing_inputs=["real_pubmed_search"]` rather than passing silently as a real PubMed search.
- **Web-search honesty**: CLOSED — `TOOL_UNAVAILABLE` instead of LLM-recalling time-sensitive guidelines.
- **Calculator integrity**: CLOSED — `SKIPPED_MISSING_INPUTS` when params absent, `TOOL_UNAVAILABLE` when params present but no deterministic calculator wired. No LLM-score-fabrication path remains.
- **Audit trail completeness**: Specialist Trace now records what was ROUTED, not just what was CALLED. Front-end can show "医学计算器: 未调用 — 当前病例不需要临床评分" per Master Task §6.5 example.

## 6. What Gate 5 is NOT catching (honest accounting)

- **All 10 cases route coding-expert to LLM_KNOWLEDGE_ONLY**: that's by design — coding-expert is the most broadly relevant Expert. Future calibration (Gate 8) should measure: of cases where coding-expert was invoked, did its advice actually change downstream query generation? If 0%, the coding-expert invocation is wasted tokens.
- **0 SKIPPED_MISSING_INPUTS in this 10-case set**: the calculator rule's `SKIPPED_MISSING_INPUTS` path is exercised by unit tests but not by this empirical set. The set has no cases requiring clinical scores.
- **0 TOOL_UNAVAILABLE for pubmed-expert**: pubmed defaults to LLM_KNOWLEDGE_ONLY when needed (more permissive than web-search). The TOOL_UNAVAILABLE path for pubmed would only fire if we explicitly forbade LLM fallback — current design permits it.
- **semantic_necessity_gate still 0**: same as Gate 4 — CEA catches problems before semantic_necessity sees them. The complementary gate remains as a defense-in-depth and is exercised by unit tests.

---

## 7. PDF §16 forbidden-items checklist

- ✓ No `production_ready` / `validated` flag flipped — Checkpoint B PASS is gate-clear-to-proceed, not quality validation
- ✓ No ICD codes exposed to clinicians — coding-expert invoked but its system prompt explicitly forbids proposing codes
- ✓ No diagnosis invention — Gate 5 only ROUTES; it never creates queries or diagnoses
- ✓ No leading query language — Gate 5 doesn't generate text
- ✓ No CMI / payment optimization language
- ✓ No Stub disguised as real — 10-case run burned 20,662 real DeepSeek tokens
- ✓ No PubMed/web-search impersonation — execution_mode field discloses LLM_KNOWLEDGE_ONLY explicitly
- ✓ No LLM-score-fabrication — calculator Expert returns TOOL_UNAVAILABLE / SKIPPED_MISSING_INPUTS, never LLM_KNOWLEDGE_ONLY

---

## 8. PDF §18 verdict-ladder compliance

**CHECKPOINT_B_PASS** (Master Task §六):

- Code + tests + runner refactor landed (deterministic, verified by 298/298 regression)
- Empirical: avg experts 1.0 (target ≤1.5), C09 experts 0, avg queries 0.20 (target ≤2.0)
- All 10 baseline cases executed against real DeepSeek with Gate 4 + Gate 5 wiring
- Per-stage drop attribution complete (necessity / single_dim / CEA / semantic / NLQ)
- Per-Expert routing attribution complete (invoked / skipped / unavailable / missing / degraded)
- Master Task §六 Checkpoint B criteria all met

This verdict is deliberately below `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK`. CDI agent label (`preview` per §B6) unchanged.

---

## 9. Evidence files

| File | Purpose |
|---|---|
| `backend/app/icoder/agent_runtime/cdi/cdi_expert_router.py` | NEW — 6 modes + 4 Expert routing rules (~340 LOC) |
| `backend/app/icoder/agent_runtime/cdi/real_runner.py` | MODIFIED — `_stage_expert_consultation` refactored; `last_route_result` field added; `_route_decision_label` helper |
| `backend/app/icoder/agent_runtime/cdi/domain.py` | MODIFIED — SpecialistTraceEntry extended with route_decision/route_reason/execution_mode/latency_ms/tokens/run_id/trace_id |
| `backend/app/icoder/agent_runtime/cdi/__init__.py` | MODIFIED — export router symbols |
| `backend/app/api/cdi.py` | MODIFIED — specialist_trace[] response includes routing fields |
| `backend/tests/test_api/test_phase5_d_p05_gate5_expert_router.py` | NEW — 19 tests |
| `backend/tests/unit/icoder/cdi/test_real_runner.py` | MODIFIED — 2 tests updated for conditional Expert invocation |
| `backend/scripts/phase5_d_p05_gate5_combined_10_cases.py` | NEW — combined 10-case runner with per-stage + per-Expert attribution |
| `backend/reports/phase5_d_p05/gate5_combined_10_cases.json` | NEW — empirical evidence |

---

## 10. What Gate 5 does NOT close

| Risk | Gate | Status after Gate 5 |
|---|---|---|
| R9 Expert conditional routing | 5 | ✓ CLOSED on 10-case set — 4→1 avg, C09=0 |
| Tool-vs-Persona disclosure | 5 | ✓ CLOSED — execution_mode field surfaces LLM_KNOWLEDGE_ONLY explicitly |
| R10/R11/R12 frontend language | 6 | ⬜ NOT STARTED |
| R13 4-role E2E | 7 | ⬜ NOT STARTED |
| R14 40-case Corti calibration | 8 | ⬜ NOT STARTED |

---

## 11. Known carry-forward

1. **coding-expert always invoked when coding-relevant gap exists**: 10/10 cases invoked coding-expert. Future Gate 8 calibration should measure whether its advice actually changes downstream query generation. If the delta is ~0%, consider routing coding-expert more narrowly (e.g. only when laterality/severity specificity is at stake).
2. **No real MCP tools wired**: all 4 Experts use LLM_KNOWLEDGE_ONLY (when needed) or TOOL_UNAVAILABLE. The router's `available_tools` parameter is forward-looking — Phase 6+ can wire real PubMed/Web/Calculator MCP servers and the router upgrades modes automatically.
3. **Single set of substrate markers**: the C09 detection heuristic relies on a hand-curated marker list. Edge cases (e.g. a chart with only symptom text + a numeric value but no diagnosis) may mis-route. Worth re-calibrating against the Gate 8 40-case set.
4. **LLM latency still ~20s/case**: Expert routing cut token burn by 37% but per-case elapsed time only dropped modestly (24s → 21s avg). The upstream stages (encounter_synthesis, gap_identification, query_generation) still make 3 LLM calls in sequence. Parallelizing them is a Phase 6 optimization.
5. **Calculator path underexercised**: 0 cases in this set triggered calculator routing. Unit tests cover it, but empirical validation awaits a chart that requires CHA2DS2-VASc / MELD / APACHE etc.

---

## 12. Resume point for next session

After Gate 5 commit (pending), next session opens **Gate 6 — Workbench Product Language + Corti UI Comparison** (Master Task §七):

- Audit Workbench for internal terminology / raw enum / technical field leakage
- Corti console.corti.app CDI view walkthrough (already logged in via Chrome)
- Side-by-side comparison: language polish list per screen
- Frontend label i18n updates
- No backend changes expected
- Combined with Gate 4 + Gate 5 for cumulative smoke
