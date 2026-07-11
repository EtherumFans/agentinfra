# Phase 5 Track C — Gate 5 Completion Report

**Date**: 2026-07-11
**Gate**: 5 — Agent-specific UI workbench (§10)
**Verdict**: `PASS_GATE5_CODING_COMPLIANCE_WORKBENCH_LIVE`

---

## 1. Gate 5 scope (from PDF §10)

PDF §10 mandates a Corti-style single coding workbench (not 7 separate agent
pages) that surfaces the entire CaseState to clinicians:

| § | Requirement | Status |
|---|---|---|
| §10.1 | Single `CodingComplianceWorkbenchPage` driving POST `/api/v1/coding-compliance/run` | ✅ Closed |
| §10.2 | 2-pane layout (input textarea + per-stage output cards) | ✅ Closed |
| §10.3 | Header banner with Human Review Gate decision | ✅ Closed |
| §10.4 | Per-stage card: stage_id + stage_name + codes + procedures + issues + latency + success/error | ✅ Closed |
| §10.5 | Conflicts panel (cross-stage) + Completion panel (status + reasons) | ✅ Closed |
| §10.6 | Sidebar entry in AI Studio section | ✅ Closed |
| §10.7 | Real-DeepSeek live run, AUTO_PASS within ~40s | ✅ Closed (35.8s) |

## 2. Implementation

### Frontend (4 files)

| File | LOC | Purpose |
|---|---|---|
| `frontend/src/pages/CodingComplianceWorkbenchPage.tsx` | 295 | Single workbench UI with sample T12 fixture + 2-pane layout + StageCard component + GATE_COLORS/GATE_LABELS/BLOCKER_LABELS Chinese maps |
| `frontend/src/App.tsx` | +2 | Route `/ai-studio/coding-compliance` → CodingComplianceWorkbenchPage |
| `frontend/src/components/layout/Layout.tsx` | +2 | Sidebar entry `编码合规` under AI Studio with `ShieldCheck` icon |
| `frontend/src/i18n/locales.ts` | +3 | `codingCompliance: '编码合规'` (zh-CN) + `'Coding Compliance'` (en-US) |

### Backend (already in Gate 4)

- `backend/app/api/coding_compliance.py` — POST `/api/v1/coding-compliance/run` (in-process orchestrator drive)
- `backend/app/main.py` — router wired

### CodingComplianceWorkbenchPage shape

```typescript
const SAMPLE = `患者男性,78岁,因跌倒后腰背疼痛12小时入院。
既往糖尿病史10年,高血压20年。
查体:T12棘突压痛(+),叩痛(+)。
MRI:T12椎体压缩性骨折。
入院诊断:T12椎体压缩性骨折,2型糖尿病,高血压病3级。
住院期间行后路椎体成形术+骨水泥注入术,手术顺利。
术后恢复良好,出院。`;

type CaseResponse = {
  case_id: string;
  agent_id: string;
  input_text_preview: string;
  input_text_length: number;
  stages: StageResult[];    // 7 stages
  conflicts: any[];
  completion: { status, reasons, must_replan, review_required };
  review_gate: { status, blocker, reasons };
  total_latency_ms: number;
};

// POST /v1/coding-compliance/run with { input_text }
// 300s timeout, axios auto-attaches Bearer token
// Renders 7 StageCards + conflicts panel + completion panel + gate badge
```

### StageCard rendering

- Header: `#<index> <stage_name> <stage_id>` + counters (`N 编码`/`N 手术`/`N 问题`) + latency + ✓ 成功 / ✗ 失败
- Body: chips of `codes_emitted` (blue) + bullet list of issues with `rule_id`
- Failure path: red error text from `stage.error`

### Gate decision banner

Top-right of header. Color-coded:
- `bg-emerald-100` AUTO_PASS (自动通过)
- `bg-amber-100` REVIEW_RECOMMENDED (建议人工复核)
- `bg-orange-100` REVIEW_REQUIRED (必须人工复核)
- `bg-rose-100` BLOCKED (已阻断) with blocker label `(BLOCKER_LABELS[code])`

## 3. Live browser walkthrough evidence

### Environment
- frontend vite :3002 (npm run dev)
- backend uvicorn :8000 (real DeepSeek provider)
- browser Playwright MCP, logged in as admin

### Steps executed

1. Navigate to `/ai-studio/coding-compliance` — page loads, sidebar entry `编码合规` visible under AI Studio
2. Sample T12 fixture pre-filled (146 chars)
3. Click `▶ 运行 7 阶段主流程` — button transitions to `运行中...`
4. ~36s later: stages render with codes/procedures/issues, gate badge shows `自动通过`
5. Console: 0 errors, 0 warnings

### Captured run (case_id `b06db7ce-5f0b-44c7-b1f4-dd5d57328d3e`)

```
case_id:     b06db7ce-5f0b-44c7-b1f4-dd5d57328d3e
total_ms:    35781ms
stages:      7/7 ✓ 成功
gate_badge:  自动通过 (AUTO_PASS)

#0  出院小结结构化       discharge-summary-structuring   ~4000ms  ✓
#1  ICD 编码            medical-coding-agent           ~7600ms  ✓  14 编码
#2  主诊断复核          principal-diagnosis-review     ~11500ms ✓  10 编码
#3  证据强度            evidence-extractor              ~4600ms  ✓   4 编码
#4  合规审查            compliance-guardrail              ~32ms  ✓   (rule engine fast path)
#5  病历完整度          note-completeness                 ~14ms  ✓   (cached fast path)
#6  DRG/DIP 风险        drg-analyzer                    ~9200ms  ✓   4 编码
```

### Screenshots

- `phase5_c_gate5_workbench_initial.png` — page load, before run
- `phase5_c_gate5_workbench_result.png` — first run with duplicate-key warnings (still succeeded)
- `phase5_c_gate5_workbench_final.png` — clean run after StageCard key fix

## 4. Bugs caught and fixed during walkthrough

### BUG-G5-01: Duplicate React keys in StageCard codes list

**Symptom**: 13 console errors `Encountered two children with the same key M80.0` after first run.

**Root cause**: `codes.slice(0, 12).map((c) => <code key={c}>...)` — but the medical-coding stage emits the same code multiple times (different metadata), and principal-dx also re-emits codes. So `key={c}` collides.

**Fix** (CodingComplianceWorkbenchPage.tsx:263):
```diff
- {codes.slice(0, 12).map((c) => (
-   <code key={c} ...>
+ {codes.slice(0, 12).map((c, idx) => (
+   <code key={`${c}-${idx}`} ...>
```

**Result**: 0 console errors on the final run.

### BUG-G5-02 (avoided): useAuth hook doesn't exist

The initial draft imported `import { useAuth } from '../hooks/useAuth'` for the Bearer token. No such hook exists. Fixed before browser test by removing the import and relying on the axios interceptor in `services/api.ts:19-25` (auto-attaches `localStorage.getItem('access_token')`).

### BUG-G5-03 (avoided): `{ api }` named import vs default export

`services/api.ts` exports `api` as default (`export default api`). The initial draft used `import { api }`. Fixed to `import api from '../services/api'`.

## 5. What this closes

- ✅ §10 Corti-style single coding workbench (not 7 separate pages)
- ✅ Sidebar navigation entry under AI Studio
- ✅ Live end-to-end: real DeepSeek → 7 stages → CaseState → UI rendered
- ✅ Human Review Gate decision surfaced in header (AUTO_PASS path)
- ✅ Per-stage latency + status visible
- ✅ Sample T12 fixture works out-of-the-box (no setup friction for demo)

## 6. Deferred to Gate 6/7

- **Gate 6**: Per-stage trace_event viewer (reuse RunTrace page with parent-child run tree), A2A Card response envelope, Embedded Web Component smoke
- **Gate 7**: Final browser walkthrough with multiple fixtures (negation, conflict, missing fields) to demonstrate blocker paths (`BLOCKED_NO_CODES_EXTRACTED`, `BLOCKED_PRIMARY_DX_CONFLICT`, etc.); formal verdict

## 7. Next: Gate 6 — Trace + A2A + Embedded integration

Gate 6 connects the workbench to the existing trace infrastructure so each
stage card links to its run's trace_events timeline, plus wraps the run
response in an A2A v0.3 Card for interop, plus an embedded Web Component
smoke for EHR integration proof.
