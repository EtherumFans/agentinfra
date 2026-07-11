# Phase 5 Track D — P0.5 Gate 0 — Baseline Audit

**Date**: 2026-07-11
**PDF**: `iCoDer CDI Phase 5 Track D P0.5 Prompt.md` (1226 lines)
**Prior state**: P0 verdict `PASS_READY_FOR_REAL_CDI_QUALITY_VALIDATION` (Gates 0-7, 7 commits `0851eb6..e18efcc`)
**Gate 0 scope**: 4 audit dimensions — data consistency / query quality / Expert routing / frontend language
**Verdict**: BASELINE_COMPLETE — root causes confirmed; no fixes applied yet (fixes begin in Gate 1)

---

## 1. State inventory

### 1.1 Code HEAD

```
e292420 docs(phase4g): walkthrough report + 4 screenshots
e9a4cc9 feat(phase4g): live cost + API Client binding + RunHistory + Agent fork (PASS)
b7db84f feat(phase4f-f3): core agent smoke runs + frontend polish (PASS)
c9c1f52 feat(phase4f-f1f2): AgentChatPage unified run + A2A-compatible architecture
5f8f611 fix(phase4f-redesign): min-h-dvh iOS Safari + max-w-5xl centered layout
```

P0.5 builds on the P0 terminal commit `e18efcc` (Gate 7 final report). Working tree has Phase 4-G uncommitted changes that are out-of-scope for P0.5.

### 1.2 Backend health

```
GET /api/health →
  status: healthy
  llm_provider: deepseek
  llm_model: deepseek-chat
  medcoder_index_ready: true

GET /api/v1/cdi/health →
  status: healthy
  endpoints: [POST /runs, GET /runs/{case_id}, POST /queries/{query_id}/transition,
              GET /audit/dashboard, POST /subscriptions, GET /health]
  boundaries_enforced: [no_medical_coding_calls, no_chart_modification,
                        nlq_gate_on_draft_to_pending_review, rbac_per_role]
```

### 1.3 Existing DB state (sqlite `data/icoder.db`)

```
cdi_cases                 11
cdi_documentation_gaps    10
cdi_provider_queries      14
cdi_clinician_responses    0
cdi_document_versions      0
```

Per-case gap/query distribution:

| case_id | gaps | queries |
|---|---|---|
| CASE-5d435a133f1c | 4 | 4 |
| CASE-9e12ee517ec3 | 4 | 4 |
| CASE-c4fe3d10032d | 2 | 2 |
| **CASE-a0193e43b506** | **0** | **4** ← bug |
| (7 other cases) | 0 | 0 |

---

## 2. Audit dimension 1 — Data consistency root cause (PDF §3.1)

### 2.1 Symptom

DB inspection confirms `CASE-a0193e43b506` has **0 gaps but 4 queries** in `cdi_provider_queries`. All 4 queries reference `gap_id ∈ {GAP-001, GAP-002, GAP-003, GAP-004}`, which already exist under `CASE-9e12ee517ec3`. This is the exact "0 Gap + N Query" pathology PDF §3.1 calls out.

### 2.2 Root cause

`backend/app/services/cdi_persistence.py` — idempotent skip on placeholder IDs:

```python
for gap in case.documentation_gaps:
    existing_gap = await session.get(DocumentationGapModel, gap.gap_id)
    if existing_gap is None:
        session.add(gap_to_orm(gap, case.case_id))   # ← silently skipped when gap_id collides
```

LLM stage emits placeholder IDs `GAP-001`, `GAP-002`, `GAP-003`, `GAP-004` for every run. The first run persists them; subsequent runs see them as "already exists" and skip. The downstream `provider_query` rows still get written with the (now-orphan) `gap_id` FK because the skip only protects the `gaps` table — the `queries` table write does not check whether the parent gap was actually persisted for the current case.

### 2.3 Three derived problems

1. **Referential integrity**: 4 queries point at gaps from a *different* case. Front-end reads back `caseData.documentation_gaps = []` and `caseData.proposed_provider_queries.length === 4`.
2. **GET/readback inconsistency**: `GET /api/v1/cdi/runs/{case_id}` returns gaps=0 / queries=4 for the affected case — no assertion catches this.
3. **Case state derivation**: derived `case_state` (e.g., "PENDING_CDI_REVIEW" vs "AUTO_PASS") depends on `len(gaps)`. With gaps=0, the state machine thinks the case auto-passed, but queries still get emitted, contradicting the auto-pass semantics.

### 2.4 Existing-data repair scope

11 cases need repair:
- `CASE-a0193e43b506` — needs its 4 queries either deleted or repointed at newly-created gaps
- (no other case has the inconsistency, but `gap_id` collision risk affects all 11)

---

## 3. Audit dimension 2 — Query quality baseline (PDF §3.2)

### 3.1 Method

10-case smoke through real DeepSeek (`scripts/phase5_d_p05_baseline_query_quality.py`). Heuristic multi-dimension detector:

```python
MULTI_DIM_PATTERNS = [
    r"类型.{0,4}(严重|部位|解剖)",
    r"严重.{0,4}(部位|解剖|并发症)",
    r"侧.{0,4}(肺叶|部位)",
    r"急性.{0,4}病程",
    r"(及|和|与).{0,15}(及|和|与)",
    r"both\s+the\s+\w+\s+and",
]
```

### 3.2 Aggregate results (10 cases, 31,082 real DeepSeek tokens)

| Metric | Value |
|---|---|
| Cases with queries | 10/10 (100%) |
| Cases with over-query (≥4 queries) | **6/10 (60%)** |
| Cases with multi-dimension query | **3/10 (30%)** |
| Cases with 0 gap but N query | 0 (in fresh data) |
| Avg queries / case | **3.6** (PDF §3.2 target: ≤ 2.0 for simple cases) |
| Avg gaps / case | 3.6 |
| Multi-dim query rate | 0.083 |
| Total tokens consumed | 31,082 |
| Avg tokens / case | 3,108 |
| Est. CNY cost / case | ~¥0.031 |

### 3.3 Per-case findings (red flags)

| Case | n_q | Multi-dim? | Red flag |
|---|---|---|---|
| C01 pneumonia simple | 3 | ✓ ("类型和部位") | Simple community pneumonia triggers severity+pathogen+site queries |
| C02 cholecystitis (clean surgical) | 4 | – | Clean Murphy+/B超/诊断 case still produces 4 queries |
| C03 hypertension workup | 3 | ✓ ("分级或分期") | Severity graded from BP 160/95 alone — should need end-organ evidence |
| C04 diabetes negation | 4 | – | Queries include family-history detail — borderline clinical relevance |
| C05 fracture conflict | 3 | – | Correctly surfaces left↔right conflict; well-targeted |
| C06 appendicitis (clean) | 4 | – | Includes "转移性腹痛时间点" — over-detailed for clean appendectomy |
| C07 COPD exacerbation | 4 | – | Q1 asks "严重程度" of explicit "急性加重" — severity grading needs GOLD criteria, not query |
| C08 STEMI PCI (clean) | 4 | – | Q4 asks "胸痛详细特征" when STEMI already explicit |
| **C09 minimal info** | **4** | **–** | **CRITICAL: chart is "主诉腹痛.建议进一步检查." — model generates "请评估最可能的病因" — this is asking the clinician to invent a diagnosis. Direct violation of PDF §4.3 "CDI must not generate diagnoses"** |
| C10 peds pneumonia | 3 | ✓ ("具体部位...左/右, 上/中/下叶, 是否对称") | Multi-dim via 3-axis option list |

### 3.4 Query-Necessity violations

PDF §3.2 says: *"a query is necessary if and only if (a) the gap is real (chart evidence insufficient) and (b) the answer would change documentation."* Baseline shows:

- **C09**: 4/4 queries unnecessary — chart contains no diagnosis to begin with; the gap is "no workup" not "ambiguous documentation"
- **C02/C06/C08**: ≥2/4 queries are over-detailed follow-ups that won't change coding or care
- **C07**: 1/4 queries is severity-grading that should come from GOLD criteria via Medical-Calculator Expert, not from a query

### 3.5 Single-dimension violation

3/10 cases mix dimensions in a single query (C01, C03, C10). Example:
> C01 Q1: "请明确肺炎的**类型和部位**" — should split into "类型" + "部位" (two queries, each single-dim)

---

## 4. Audit dimension 3 — Expert routing baseline (PDF §3.3)

### 4.1 Observation

All 10 cases invoke **all 4 Experts** unconditionally:

| Expert | Invocations / 10 cases |
|---|---|
| coding-expert | 10 |
| pubmed-expert | 10 |
| web-search-expert | 10 |
| medical-calculator-expert | 10 |

### 4.2 Conditional-routing opportunities (PDF §3.3)

| Case | coding | pubmed | web | calculator | Should skip? |
|---|---|---|---|---|---|
| C01 pneumonia | ✓ useful | borderline | borderline | ✓ CURB-65 | web-search unnecessary for routine CAP |
| C02 cholecystitis | ✓ useful | skip | skip | skip | PubMed/Web/Calculator all unnecessary |
| C03 hypertension | ✓ useful | skip | skip | ✓ risk stratify | PubMed unnecessary |
| C04 diabetes negation | ✓ useful | skip | skip | ✓ HbA1c calc | PubMed/Web unnecessary |
| C05 fracture conflict | ✓ useful | skip | skip | skip | Only coding-expert relevant |
| C06 appendicitis | ✓ useful | skip | skip | skip | Only coding-expert relevant |
| C07 COPD | ✓ useful | ✓ GOLD guide | skip | ✓ GOLD grade | Web unnecessary |
| C08 STEMI PCI | ✓ useful | skip | skip | ✓Killip | PubMed/Web unnecessary |
| **C09 minimal info** | skip | skip | skip | skip | **ALL 4 EXPERTS SHOULD SKIP — no clinical substrate to reason about** |
| C10 peds pneumonia | ✓ useful | skip | skip | skip | PubMed/Web/Calculator unnecessary |

**Estimated conditional routing**: ~50% of expert calls are unnecessary. Conservative cost savings ~30-40% per case.

### 4.3 Expert trace evidence

Real per-case trace confirms each expert was called with its own systemPrompt and chart context (`trace_events` with `expert_id`). The issue is not "configured but not invoked" (PDF §A2 red line held) — it is "always invoked even when conditionally unnecessary".

---

## 5. Audit dimension 4 — Frontend language baseline (PDF §3.4)

### 5.1 User-visible developer/audit terminology

Locations exposing internal/PDF terminology in business UI (`CDIWorkbenchPage.tsx`):

| Location | Current text | PDF §3.4 violation |
|---|---|---|
| L2 (file header) | "Phase 5 Track D P0 Gate 5" | Internal phase label — should not appear in source comments or rendered text |
| L243 (sub-header) | "Clinical Documentation Improvement · Core Entry Agent #1" | "Core Entry Agent #1" is internal product-taxonomy language; PDF §3.4 forbids exposing "Core Entry Agent" to clinicians |
| L353 (empty state) | "Phase 5 Track D P0 · 真实 LLM · NLQ-001..010 gate · 9-state lifecycle" | Phase label + NLQ rule IDs + state count — all internal |
| L457 (trace card) | "{latency_ms}ms · {total_tokens}tok" | "tok" abbreviation and raw token count visible in specialist trace |
| L461 (trace card) | "{run_id}" | Raw run_id UUID visible in specialist trace |
| L480 (gap section header) | "PDF §6.2 — 9 gap types (incl. unknown)" | PDF section reference in business UI |

### 5.2 Empty / placeholder states

`caseData.documentation_gaps.length === 0` block (L486):
```tsx
<div>无文档缺口 (auto_pass 或 LLM 阶段降级)</div>
```
The text "auto_pass" / "LLM 阶段降级" exposes internal lifecycle terminology.

### 5.3 Raw enum exposure

| Field | Currently rendered | Should be |
|---|---|---|
| gap.gap_type | raw enum string ("diagnostic_specificity", "etiology", ...) | Chinese human-readable label |
| query.lifecycle_state | raw enum ("DRAFT", "PENDING_CDI_REVIEW", "VIEWED", ...) | Chinese status label |
| query.nlq_verdict | raw ("PASS", "REVIEW_REQUIRED") | Chinese verdict |
| query.outcome | raw ("APPROVED", "SEND_TO_CLINICIAN", "RESPONDED", ...) | Chinese |

### 5.4 Status semantics not localized

The 12 lifecycle states (DRAFT, PENDING_CDI_REVIEW, APPROVED, SENT_TO_CLINICIAN, VIEWED, RESPONDED, DOCUMENTATION_UPDATED, REVALIDATED, CLOSED, CANCELLED, ESCALATED, EXPIRED) are all rendered as raw English enums.

### 5.5 Technical / audit panel placement

The "specialist trace" panel (L444-L466) is rendered in the same visual layer as case context and gap list. PDF §3.4 says it should be **collapsible / default-collapsed** so clinicians never see run_id/tokens/expert_id unless they explicitly expand the "审计/技术详情" disclosure.

---

## 6. Risk catalog → Gate mapping

| # | PDF § | Risk | Gate that fixes it |
|---|---|---|---|
| R1 | §3.1 | 0-Gap+N-Query data inconsistency | Gate 1 |
| R2 | §3.1 | Referential integrity gap↔query | Gate 1 |
| R3 | §3.1 | GET readback inconsistency | Gate 1 |
| R4 | §3.1 | Case state derivation broken by gaps=0 | Gate 1 |
| R5 | §3.2 | Query Necessity gate missing → over-query 60% | Gate 2 |
| R6 | §3.2 | Single-dimension constraint missing → 30% multi-dim | Gate 3 |
| R7 | §3.2 | Option taxonomy (3-5 options, escape hatch, no ICD) missing | Gate 3 |
| R8 | §3.2 | Claim-Evidence alignment not enforced | Gate 4 |
| R9 | §3.3 | Expert always-call-4 instead of conditional routing | Gate 5 |
| R10 | §3.4 | PDF §6.2 / Core Entry Agent / Token / run_id exposed | Gate 6 |
| R11 | §3.4 | Raw enums not Chinese-ized | Gate 6 |
| R12 | §3.4 | Specialist trace panel not collapsible | Gate 6 |
| R13 | §3.5 | 4-role (CDI specialist / clinician / auditor / admin) browser E2E missing | Gate 7 |
| R14 | §3.6 | Calibration set (40 cases, dual annotation) missing | Gate 8 |

---

## 7. What Gate 0 closes (and does NOT close)

### Closes

- Baseline metrics established (10 cases, 31,082 tokens, 60% over-query, 30% multi-dim)
- Root cause of "0 Gap + N Query" pinpointed to `cdi_persistence.py` idempotent skip
- Conditional Expert routing opportunity quantified (~50% of calls unnecessary)
- 6 frontend language exposures inventoried
- 14-risk catalog → Gate mapping

### Does NOT close (deferred to Gates 1-8)

- Any code fix (Gates 1-6)
- Any browser walkthrough (Gate 7)
- Calibration set authoring (Gate 8)

---

## 8. Gate 0 verdict

**BASELINE_AUDIT_COMPLETE** — 4 audit dimensions executed, 14 risks catalogued and mapped to Gates 1-8. Ready to open Gate 1 (data consistency fix).

**Forbidden claims in this report**: none. Gate 0 is descriptive only — no "fix", "validate", "ready", "production" claims made.

**Forbidden items respected** (PDF §16, subset relevant to Gate 0):
- ✓ No `production_ready` flip
- ✓ No Stub disguised as real (baseline used real DeepSeek, 31,082 tokens)
- ✓ No CMI/payment optimization language introduced
- ✓ No diagnosis invented by the orchestrator (only flagged as a model-output issue to be fixed in Gate 2)
- ✓ No ICD codes exposed to clinicians (UI baseline does not show ICD)

**Empirical evidence files**:
- `backend/reports/phase5_d_p05/baseline_query_quality_10_cases.json` (10 cases × full gap/query/trace data)
- `backend/reports/phase5_d_p05/_baseline_readable.txt` (UTF-8 readable query texts)
- DB snapshot `data/icoder.db` (11 cases, 10 gaps, 14 queries — CASE-a0193e43b506 shows the 0/4 split)
