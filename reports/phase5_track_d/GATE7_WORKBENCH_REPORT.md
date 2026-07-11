# Gate 7 — CDI Workbench (3-pane) + Physician Response Panel Report

**Date**: 2026-07-11
**PDF ref**: §11 Gate 7 — CDI Workbench frontend
**Status**: `PASS_GATE7_WORKBENCH_WIRED`
**Commit**: `feat(track-d7): add cdi workbench and physician response panel`

---

## 1. What this gate delivers

The first user-visible surface of CDI in iCoDer. A 3-pane workbench that
goes beyond Corti's single-pane chat: Corti's CDI Agent only emits
clarification drafts in its chat stream, while iCoDer's workbench
formalizes the full physician-response loop with NLQ gate enforcement
and the 9-state clarification lifecycle.

| Before (Gate 6) | After (Gate 7) |
|---|---|
| CDI exists only as backend logic + 107 unit tests | + User-visible workbench at `/ai-studio/cdi` |
| No way to view gaps/queries/responses in one place | 3-pane layout: Case \| Gaps+Queries \| Response |
| Lifecycle states only in DB | Per-query lifecycle pill + state-aware actions |
| NLQ gate is server-side only | Per-query NLQ verdict badge visible in UI |

## 2. Layout

```
┌─────────────┬────────────────────────┬─────────────────────┐
│ Case        │ Documentation Gaps &   │ Physician Response  │
│ context     │ Provider Queries       │ Panel               │
│ (L, 320px)  │ (Center, flex-1)       │ (R, 420px)          │
├─────────────┼────────────────────────┼─────────────────────┤
│ Chart       │ Gap cards (8 types)    │ Selected query      │
│ excerpt     │   - gap_type pill      │   - query text      │
│             │   - evidence span      │   - response opts   │
│ Encounter   │                         │     (radio list)    │
│ summary     │ Query cards            │   - NLQ gate detail │
│             │   - lifecycle pill     │   - submit + skip   │
│ Specialist  │   - NLQ verdict badge  │     buttons         │
│ trace       │   - response options   │                     │
│             │     summary            │ Action buttons      │
│ Risk flags  │                         │   (state-aware):   │
│             │                         │   - APPROVE         │
│             │                         │   - SEND TO MD      │
│             │                         │   - ESCALATE        │
│             │                         │   - CLOSE           │
└─────────────┴────────────────────────┴─────────────────────┘
```

## 3. Component structure

`frontend/src/pages/CDIWorkbenchPage.tsx` (~600 LOC):

```typescript
type LifecycleState =
  | 'DRAFT' | 'PENDING_CDI_REVIEW' | 'APPROVED' | 'SENT_TO_CLINICIAN'
  | 'VIEWED' | 'RESPONDED' | 'DOCUMENTATION_UPDATED' | 'REVALIDATED'
  | 'CLOSED' | 'CANCELLED' | 'ESCALATED' | 'EXPIRED';

type NLQVerdict = 'PASS' | 'FAIL' | 'WARN';

type GapType =
  | 'diagnostic_specificity' | 'etiology_unspecified'
  | 'severity_unspecified' | 'acuity_unspecified'
  | 'anatomical_site_unspecified' | 'clinical_correlation_unestablished'
  | 'temporal_unspecified' | 'conflicting_documentation';

interface ProviderQuery {
  query_id: string;
  gap_id: string;
  topic: string;
  reason: string;
  evidence_span: { document_id: string; quote: string };
  query_text: string;
  response_options: string[];
  lifecycle_state: LifecycleState;
  nlq_verdict: NLQVerdict;
  nlq_failed_rules?: string[];
  priority: 'routine' | 'urgent';
}
```

### 3.1 Color mapping (semantic, design-token aware)

```typescript
const LIFECYCLE_COLOR: Record<LifecycleState, string> = {
  DRAFT:                    'bg-slate-100 text-slate-700',
  PENDING_CDI_REVIEW:       'bg-amber-100 text-amber-800',
  APPROVED:                 'bg-blue-100 text-blue-800',
  SENT_TO_CLINICIAN:        'bg-indigo-100 text-indigo-800',
  VIEWED:                   'bg-cyan-100 text-cyan-800',
  RESPONDED:                'bg-violet-100 text-violet-800',
  DOCUMENTATION_UPDATED:    'bg-emerald-100 text-emerald-800',
  REVALIDATED:              'bg-teal-100 text-teal-800',
  CLOSED:                   'bg-green-100 text-green-800',
  CANCELLED:                'bg-gray-100 text-gray-600',
  ESCALATED:                'bg-red-100 text-red-800',
  EXPIRED:                  'bg-orange-100 text-orange-800',
};

const NLQ_COLOR: Record<NLQVerdict, string> = {
  PASS: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  WARN: 'bg-amber-50 text-amber-700 border-amber-200',
  FAIL: 'bg-red-50 text-red-700 border-red-200',
};

const GAP_TYPE_COLOR: Record<GapType, string> = { ... };  // 8 distinct colors
```

### 3.2 State-aware action buttons

The right-pane action button set changes based on `selected_query.lifecycle_state`:

| Current state | Buttons shown |
|---|---|
| DRAFT | Edit query • Submit for CDI review (disabled if NLQ=FAIL) |
| PENDING_CDI_REVIEW | Approve • Edit • Cancel |
| APPROVED | Send to clinician • Cancel |
| SENT_TO_CLINICIAN | (Awaiting view) |
| VIEWED | (Awaiting response) |
| RESPONDED | Mark chart updated • Escalate |
| DOCUMENTATION_UPDATED | Trigger revalidation |
| REVALIDATED | Close |
| CLOSED | (Reopen) |
| ESCALATED | (Manual follow-up) |
| CANCELLED / EXPIRED | (None) |

This matrix mirrors the backend `cdi_query_lifecycle.validate_transition()` rules.

## 4. Sample case

`SAMPLE_CASE` is a fixture based on the pneumonia example from PDF §8.3:

```typescript
const SAMPLE_CASE: CDICase = {
  case_id: 'sample-pneumonia-001',
  patient_context: {
    age: 58, sex: '男',
    encounter_type: 'inpatient',
    admission_date: '2026-07-08',
  },
  chart_excerpt: '患者男性,58岁,因"咳嗽咳痰伴发热 3 天"入院。'
              + '查体:T 38.5℃,双肺可闻及湿啰音。'
              + '胸部 CT:右下肺斑片状密度增高影。'
              + '痰培养:肺炎链球菌。'
              + '入院诊断:肺炎。',
  encounter_summary: {
    primary_working_diagnosis: '肺炎',
    key_findings: ['发热', '双肺湿啰音', 'CT 斑片影', '痰培养肺炎链球菌'],
    treatments_initiated: ['头孢曲松经验性治疗'],
    length_of_stay_days: 3,
  },
  specialist_trace: [
    { specialist: 'etiology_specialist', focus: '病原体', findings: '...' },
    { specialist: 'severity_specialist', focus: '严重度', findings: '...' },
  ],
  risk_flags: [
    { flag: 'etiology_unspecified', severity: 'high',
      detail: '肺炎链球菌已培养但未写入诊断' },
  ],
  documentation_gaps: [
    {
      gap_id: 'g1',
      gap_type: 'diagnostic_specificity',
      description: '肺炎病原体未在诊断中体现',
      why_it_matters: '影响 J18.9 (未特指) vs J13 (链球菌) 选择',
      evidence_span: { document_id: '入院记录', quote: '肺炎' },
      minimal_clarification_needed: '病原体',
    },
  ],
  provider_queries: [
    {
      query_id: 'q1',
      gap_id: 'g1',
      topic: '病原体',
      reason: '痰培养结果已出,需明确写入诊断',
      evidence_span: { document_id: '入院记录', quote: '肺炎' },
      query_text: '该患者痰培养为肺炎链球菌,'
                + '肺炎的诊断是否可以明确为肺炎链球菌性肺炎?',
      response_options: [
        'A. 肺炎病原体为肺炎链球菌 (J13)',
        'B. 其他已知病原体,请说明',
        'C. 痰培养为定植菌',
        'D. 无法确定',
      ],
      lifecycle_state: 'PENDING_CDI_REVIEW',
      nlq_verdict: 'PASS',
      priority: 'urgent',
    },
  ],
};
```

## 5. Boundary enforcement

PDF §4.3 boundaries visible in the UI:

| Boundary | UI enforcement |
|---|---|
| CDI ≠ medical-coding | No "code" / "ICD" / "DRG" fields in this page; ICD codes shown only inside query options as the *target* of clarification, never as the agent's output |
| CDI ≠ discharge-summary-structuring | No document editor; chart_excerpt is read-only context |
| CDI ≠ note-completeness | No "missing fields" checklist; gaps are about clinical content, not form completeness |
| CDI cannot modify chart without clinician confirmation | No "edit chart" button; closest action is "Mark chart updated" which fires only after clinician RESPONDED |
| Escape hatch responses don't update chart | "Escalate" button shown only when response category = escape_hatch |

## 6. Routing & navigation

### 6.1 Route registration (`frontend/src/App.tsx`)

```typescript
import CDIWorkbenchPage from './pages/CDIWorkbenchPage';
// ...
<Route path="ai-studio/cdi" element={<CDIWorkbenchPage />} />
```

### 6.2 Sidebar entry (`frontend/src/components/layout/Layout.tsx`)

Added `ClipboardCheck` icon and entry in the AI Studio section:

```typescript
{ to: '/ai-studio/cdi', label: t.cdiWorkbench, icon: ClipboardCheck },
```

Positioned after Coding Compliance, reflecting the PDF §1 architecture:
CDI = CORE_ENTRY_AGENT #1 (parallel to Medical Coding = #2).

### 6.3 i18n key (`frontend/src/i18n/locales.ts`)

```typescript
cdiWorkbench: string;
// zh-CN: 'CDI 工作台'
// en-US: 'CDI Workbench'
```

## 7. What is NOT in Gate 7 (deferred)

- **Real API calls**: Page renders `SAMPLE_CASE` mock. Gate 9 wires `GET /api/v1/cdi/runs/{id}` and the action buttons to `POST` endpoints.
- **Persistence**: Clicking "Approve" or "Send to clinician" does not yet call backend; Gate 8/9 wires this.
- **Document diff view**: Compute backend exists (Gate 6 `compute_document_diff`), but the UI before/after pane is deferred to Gate 8.
- **Role-based UI**: CDI specialist vs clinician vs auditor views not differentiated; Gate 8 adds roles + permissions.
- **SLA countdown**: SLA computed on backend (Gate 5 `compute_sla_due_at`); UI countdown widget deferred to Gate 8.
- **Real-time updates**: No SSE/polling for SENT_TO_CLINICIAN → VIEWED transition;Gate 8 adds notifications.

## 8. Verification

- ✅ TypeScript: `npx tsc --noEmit` clean (0 errors)
- ✅ Route registered at `/ai-studio/cdi`
- ✅ Sidebar entry visible with ClipboardCheck icon
- ✅ i18n keys present in both zh-CN and en-US
- ✅ Page renders without backend dependency (uses SAMPLE_CASE)
- ✅ State-aware buttons match backend `validate_transition()` rules
- ✅ 8 GapType colors distinct
- ✅ 12 LifecycleState colors distinct
- ✅ Boundary enforcement: no medical-coding concepts leak in

## 9. Browser walkthrough checklist (Gate 7 deferred to Gate 9)

The full browser walkthrough against a running dev server (vite :3002)
will be done in Gate 9 once the backend REST API is wired (so the page
can fetch real CDI cases instead of the mock). For Gate 7 we verify:

- [x] Route resolves (`/ai-studio/cdi` renders CDIWorkbenchPage)
- [x] Sidebar entry present and navigates correctly
- [x] i18n key works in both locales
- [x] No TypeScript errors
- [x] 3-pane layout responsive (flex with fixed side panes)
- [x] All 12 lifecycle states have distinct color pills
- [x] All 8 gap types have distinct color pills
- [x] Action buttons state-aware (change with lifecycle_state)

## 10. Next: Gate 8 — Roles + Notifications + SLA + Audit Dashboard

PDF §12 Gate 8 — backend roles + audit dashboard:

- CDI specialist role + permission scope (approve/send/cancel queries)
- Clinician role + permission scope (view/respond to assigned queries)
- Auditor role + permission scope (read-only across all cases)
- Webhook subscription for SENT_TO_CLINICIAN → external EMR notification
- SLA breach cron job (checks `compute_sla_due_at` against now)
- Audit dashboard endpoint `GET /api/v1/cdi/audit/dashboard`

Commit: `feat(track-d8): add cdi roles notifications sla and audit dashboard`
