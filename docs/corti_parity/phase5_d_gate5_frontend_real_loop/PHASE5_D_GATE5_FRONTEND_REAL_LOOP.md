# Phase 5 Track D P0 Gate 5 — Frontend Real Closed Loop

**Date**: 2026-07-11
**Verdict**: PASS — real DeepSeek-backed CDI run rendered end-to-end, no SAMPLE_CASE, no mock
**Commit scope**: `frontend/src/pages/CDIWorkbenchPage.tsx` + `frontend/src/services/cdiApi.ts` (new) + `backend/app/api/cdi.py`

## What Gate 5 closes (PDF §A8)

PDF Task A8 requires the frontend to:
1. Remove the hard-coded `SAMPLE_CASE` constant
2. Wire the real `/api/v1/cdi/runs` endpoint
3. Surface loading / error / empty / degraded states explicitly (no fake "success")
4. Drive lifecycle transitions through `/api/v1/cdi/queries/{id}/transition`

All four are now real.

## Files changed

| File | Lines | Purpose |
|---|---|---|
| `frontend/src/services/cdiApi.ts` (new) | 178 | Axios-based CDI client: `runCDI`, `getCDICase`, `transitionQuery`, `cdiHealth` + TS types mirroring backend schemas |
| `frontend/src/pages/CDIWorkbenchPage.tsx` | 815 (rewrite) | Removed SAMPLE_CASE; real chart input + Load case bar; LoadState union (idle/loading/success/error); degraded banner; role-aware action matrix |
| `backend/app/api/cdi.py` | +45 / -3 | `CDIRunResponse` gains `patient_ref`, `encounter_ref`, `encounter_summary`, `risk_flags`, `specialist_trace`; GET `/runs/{case_id}` returns same shape; transition endpoint reads `verdict` (not the non-existent `.passed`) |

## Browser walkthrough — empirical evidence

### Step 1 — empty state (`/ai-studio/cdi`, no case loaded)
- Title: `CDI 工作台` + subtitle `Clinical Documentation Improvement · Core Entry Agent #1`
- Role pill: `admin`
- Chart textarea with `DEFAULT_CHART_HINT` (pneumonia sample) — placeholder, NOT a fake result
- "运行 CDI 分析" button (primary)
- "或加载已有 Case:" input + disabled "加载" button
- Empty-state hint: "输入病历文本, 运行 CDI 分析"

### Step 2 — run real CDI analysis (POST `/api/v1/cdi/runs`)
- 200 OK
- Latency: ~20s end-to-end (7 real DeepSeek calls)
- Top banner shows Case ID `CASE-a0193e43b506` + completion_state `REVIEW_REQUIRED`
- Chart preview pane: full chart text
- Encounter summary pane: 4 bullet key points (咳嗽咳痰伴发热3天 / 体温38.5℃ / 痰培养肺炎链球菌 / 肺炎) — real LLM extraction
- Stage Traces pane: 7 real DeepSeek runs with per-stage latency + token count + run_id:
  - `encounter_synthesis` 1603ms · 272 tok · run-eeb3ca844ab9
  - `gap_identification` 5259ms · 692 tok · run-41b93337b777
  - `query_generation` 6087ms · 1028 tok · run-d5911b1164a7
  - `coding-expert` 3070ms · 204 tok (real Expert invocation)
  - `pubmed-expert` 2249ms · 230 tok
  - `web-search-expert` 1876ms · 222 tok
  - `medical-calculator-expert` 2130ms · 243 tok
- 文档缺口 (4): real gaps with `diagnostic_specificity` type + evidence quote `入院诊断:肺炎`
- 临床澄清任务 (4): real non-leading queries, each with 4-5 response options
- Selected query detail panel: query text + radio options + "提交 CDI 审核" button (admin/cdi_specialist only)

### Step 3 — lifecycle transition (POST `/api/v1/cdi/queries/Q-001/transition`)
- Body: `{to_state: "PENDING_CDI_REVIEW", query_text, response_options, evidence_quote, topic, priority}`
- 200 OK — backend ran NLQ-001..010 gate (lexical + structural), gate verdict returned
- Case reloaded via GET `/runs/{case_id}` to reflect new state

## Architectural changes

### `cdiApi.ts` (new)
Axios instance with `/api/v1/cdi` base URL + Bearer token interceptor. Exports:
- `runCDI(params)` → `CDIRunResponse`
- `getCDICase(caseId)` → `CDIRunResponse`
- `transitionQuery(queryId, params)` → `TransitionResult`
- `cdiHealth()` → `CDIHealthResponse`

Types mirror backend Pydantic schemas exactly: `LifecycleState` (12 states), `NLQVerdict`, `StageTrace`, `EvidenceSpan`, `DocumentationGapDTO`, `ProviderQueryDTO`, `CDIRunResponse`.

### `CDIWorkbenchPage.tsx` rewrite
- **Removed**: `SAMPLE_CASE` constant (~80 lines of fake data)
- **Added**: `LoadState = 'idle' | 'loading' | 'success' | 'error'` state machine
- **Added**: `normalizeCase()` helper that defends against any missing optional field so a partial backend response never crashes the renderer (the actual `Cannot read properties of undefined (reading 'length')` we hit during walkthrough)
- **Added**: `mapCDIRole(appRole)` — maps admin → admin, qc → cdi_specialist, clinician → clinician, insurance → auditor, others → read_only
- **Added**: `ActionButtons` component implementing the role-aware action matrix per PDF §B2
- **Added**: auto-load case from URL `?case_id=` query param
- **Added**: degraded banner (`caseData.degraded === true` — falls back gracefully on LLM provider failure)
- **Added**: explicit error banner with `errorMsg`

### Backend `cdi.py`
- `CDIRunResponse` schema expanded to include all 11 fields the frontend renders (was 6)
- `run_cdi` handler now populates `patient_ref`, `encounter_ref`, `encounter_summary`, `risk_flags`, `specialist_trace` from the domain `CDICase`
- `get_case` (GET `/runs/{case_id}`) now returns the same shape so post-transition reload renders correctly
- `transition_query` endpoint: fixed `gate_result.passed` → `gate_result.verdict == "PASS"` (the `NLQGateResult` dataclass never had a `.passed` field — only `verdict`)

## Verification

### Backend
```
tests/unit/icoder/cdi/  191 passed
```

### Frontend
```
tsc --noEmit  0 errors
vitest run    77/77 passed
```

### Browser evidence (Playwright MCP)
- `phase5_d_cdi_gate5_real_run.png` — initial run with 7 stage traces + 3 gaps + 3 queries
- `phase5_d_gate5_real_run_with_queries.png` — full 4-query case with selected query detail panel

## PDF §17 acceptance

- ✓ Frontend uses real API (no SAMPLE_CASE)
- ✓ Loading state surfaces explicitly
- ✓ Error state surfaces explicitly
- ✓ Empty state surfaces explicitly
- ✓ Degraded state surfaces explicitly
- ✓ Lifecycle transitions wired through real endpoint
- ✓ Role-aware action matrix enforced (admin sees all actions; read_only sees none)
- ✓ Real DeepSeek runs (latency > 1500ms + token cost > 0 per stage)

## What's still deferred (per PDF §18)

- Real per-stage system prompts (Gate 6 closes this)
- 5-scenario browser E2E matrix (Gate 6)
- Final report (Gate 7)
