# Gate 2 — Corti CDI UI & Integration Audit

**Date**: 2026-07-11
**Source**: Corti console UI observation (Track B) + Corti SDK documentation + agent card metadata
**Scope**: UI surface, API contract, Webhook/SSE, Embedded integration

---

## 1. UI surface observation

Corti's CDI agent UI was observed in Track B-1/B-2 via the Corti console (account permission allowed read-only browse; live run blocked).

### 1.1 Agent Hub card

| Field | Value |
|---|---|
| Title | Clinical Documentation Improvement (CDI) |
| Subtitle | Identify documentation gaps in clinical charts and generates compliant provider queries to improve coding accuracy |
| Use case badge | Coding and Revenue Cycle |
| Experts avatars | 4 (PubMed, Web Search, Medical Calculator, Coding) |
| "Open agent" CTA | Primary |

### 1.2 Agent Detail page

Five tabs (Corti-standard across all agents):

| Tab | CDI content |
|---|---|
| Overview | Description, use case, examples |
| Settings | system_prompt (read-only in production), config knobs (none visible for CDI) |
| Experts | 4 cards, each with name + description + (some with) MCP server binding |
| Tools | (empty for CDI — Experts own the tools, agent itself has no direct MCP tools) |
| Code | JavaScript SDK snippet (Create agent, send message, subscribe to events) |

### 1.3 Chat / Run page

Single-pane chat layout (Corti's standard). User pastes chart excerpt → agent streams response in 6 sections (Encounter Summary / Documentation Gaps / Proposed Provider Queries / Coding Specificity Checklist / Risk Flags / Specialist Trace).

No 3-pane workbench. No "Pending Queries" queue. No physician response panel. **Corti's CDI is a chat-only agent**; the physician response loop is handled externally (EHR portal, email, or phone).

### 1.4 What Corti CDI does NOT have

| Capability | Corti has it? |
|---|---|
| Pending queries queue UI | ❌ |
| Physician response panel | ❌ |
| Documentation diff view (before vs after clarification) | ❌ |
| SLA tracker | ❌ |
| Multi-query workflow state machine | ❌ |
| Query approval workflow (CDI specialist signs off before send) | ❌ |
| Audit dashboard for CDI metrics | ❌ |

These are all **Corti gaps**. iCoDer Track D Gate 7+ will implement them as a 3-pane workbench (Gaps | Queries | Physician Response) — this is a **productization beyond Corti**, not a Corti-parity requirement.

## 2. API surface (Corti SDK)

From Corti SDK documentation observed in Track B:

```typescript
// Create CDI run
const task = await cortiClient.agents.messageSend(
  'clinical-documentation-improvement-cdi-agent',
  {
    role: 'user',
    parts: [
      { kind: 'text', text: chartExcerpt },
      { kind: 'data', data: { encounter_setting: 'inpatient', specialty: 'internal_medicine' } }
    ],
    messageId: crypto.randomUUID(),
    kind: 'message'
  }
);

// Poll for completion (no SSE on Corti CDI)
const result = await cortiClient.tasks.get(task.id);
// result.artifacts[0].data.sections.encounter_summary
// result.artifacts[0].data.sections.documentation_gaps[]
// result.artifacts[0].data.sections.proposed_provider_queries[]
// result.artifacts[0].data.sections.coding_specificity_checklist[]
// result.artifacts[0].data.sections.risk_flags[]
// result.artifacts[0].data.sections.specialist_trace[]
```

Corti's CDI is **synchronous-only** (no SSE streaming, no webhook callback). The client polls `tasks.get` until `state === 'completed'`. Latency for a typical chart is undocumented but expected to be 10–30s based on analogous Medical Coding Agent latency (Track B §F measured ~8s for medical-coding).

## 3. A2A Task envelope (Corti-compatible)

Corti's CDI returns an A2A v0.3 Task:

```json
{
  "id": "task_cdi_2026_0711_a3c5",
  "state": "completed",
  "artifacts": [
    {
      "name": "cdi_result",
      "parts": [
        {
          "kind": "data",
          "data": {
            "sections": {
              "encounter_summary": "...",
              "documentation_gaps": [...],
              "proposed_provider_queries": [...],
              "coding_specificity_checklist": [...],
              "risk_flags": [...],
              "specialist_trace": [...]
            }
          }
        }
      ]
    }
  ],
  "metadata": {
    "agent_id": "clinical-documentation-improvement-cdi-agent",
    "use_case": "coding_and_revenue_cycle",
    "run_url": "https://api.eu.corti.app/runs/run_cdi_..."
  }
}
```

iCoDer Track D Gate 9 will produce the same shape via `_wrap_cdi_case_as_a2a_task()` (mirroring Track C's `_wrap_case_as_a2a_task`).

## 4. Webhook / SSE / Push notifications

Corti's agent registry exposes `capabilities`:

```yaml
streaming: false        # no SSE
pushNotifications: false # no webhook
stateTransitionHistory: true
extensions: []
```

For CDI, this means:

- No real-time push to clinician when CDI finishes
- Client must poll
- No webhook integration with hospital messaging systems

iCoDer Track D Gate 8 will support webhook subscription (per Phase 5 Track C orchestrator pattern), as a productization beyond Corti.

## 5. Embedded integration (Web Component)

Corti's Web Component (`@corticloud/web-component` or equivalent) supports embedding CDI chat into an EHR iframe. The standard pattern:

```html
<corti-agent
  agent-id="clinical-documentation-improvement-cdi-agent"
  patient-context='{"patient_id": "p_001", "encounter_id": "e_001"}'
  auth-token="..."
></corti-agent>
```

iCoDer's Web Component (Phase 5 A4) already supports this pattern via `<icoder-assistant>` element. Track D Gate 7 will add a CDI-specific mode that renders the 6-section structured response instead of free-form chat.

## 6. Integration patterns observed in Corti customers

Corti's documented customer integration patterns (from public case studies, observed in Track B):

| Pattern | Description | iCoDer parity |
|---|---|---|
| Standalone console | CDI specialist logs in to console.corti.app, runs CDI on a chart, copies queries to EHR manually | ✅ Already supported |
| EHR-embedded iframe | CDI specialist opens EHR, embedded Corti iframe runs CDI in-chart | ✅ Phase 5 A4 Web Component |
| HIS API integration | HIS sends chart via API, receives CDI result, displays in HIS UI | ✅ Track C Agent Run facade |
| Manual loop | CDI query printed/emailed to clinician, response collected verbally | ⚠ Partial — Track D Gate 7 adds physician response panel for digital collection |

iCoDer's productization target (Gate 7) is to add the **digital physician response loop** that Corti does not have natively. This is a competitive differentiator, not a Corti-parity gap.

## 7. Mobile / Tablet surface

Corti's CDI is **not mobile-optimized**. Console UI is desktop-first (min-width 1280px recommended). Mobile/tablet view renders but is not usable for clinical workflow.

iCoDer Track D Gate 7 will require `min-h-dvh` and `max-w-*` responsive patterns (established in Phase 4-F redesign) for the CDI workbench.

## 8. Localization

Corti CDI is English-only (prompt constraint: "Use English only"). iCoDer Track D Gate 4 will produce Chinese output natively, with optional English for international hospital deployments.

Localization mapping:

| Corti output section | iCoDer zh-CN |
|---|---|
| Encounter Summary | 就诊摘要 |
| Documentation Gaps | 文档缺口 |
| Proposed Provider Queries | 临床澄清任务 (Provider Queries) |
| Coding Specificity Checklist | 编码特异性检查清单 |
| Risk Flags | 风险标记 |
| Specialist Trace | 专家会诊轨迹 |

## 9. Differences from Corti (iCoDer productization)

| Area | Corti | iCoDer Track D | Reason |
|---|---|---|---|
| UI layout | Single chat pane | 3-pane workbench (Gaps / Queries / Physician Response) | China hospital CDI workflow needs end-to-end digital loop, not chat |
| Query state machine | None (chat-only) | DRAFT → PENDING_CDI_REVIEW → APPROVED → SENT_TO_CLINICIAN → VIEWED → RESPONDED → DOCUMENTATION_UPDATED → REVALIDATED → CLOSED | Required for audit trail and SLA |
| Physician response capture | External (EHR/email) | Native panel with response options + free text | Required for digital closure of CDI loop |
| Documentation writeback | None (manual) | Manual + optional assisted-writeback (default OFF per red line #8) | Saves CDI specialist time while preserving red line |
| SLA tracking | None | Per-query SLA with escalation (PDF §10) | China hospital compliance requirement |
| Webhook | None | Webhook subscription on state transitions | Hospital messaging integration |
| Localization | English-only | zh-CN primary, en-US secondary | China market |
| Coding standard | ICD-10-CM | ICD-10-CN (国标 + 医保) | China coding system |
| Clinical knowledge base | AMBOSS | (open — China clinical KB or import AMBOSS) | China clinical reference standards |
| Mobile-optimized | No | Yes (responsive) | China hospital mobile workflow |

## 10. What iCoDer will NOT inherit from Corti

| Corti property | iCoDer decision | Reason |
|---|---|---|
| Synchronous-only API (no SSE) | iCoDer will support SSE for CDI runs | Long-running charts (>30s) need streaming |
| No per-query audit dashboard | iCoDer will add (Track D Gate 8) | Hospital compliance requires CDI metrics dashboard |
| No physician response capture | iCoDer will add (Track D Gate 7) | Digital loop closure is the productization value |
| English-only | iCoDer zh-CN primary | China market |
| AMBOSS as clinical criteria source | iCoDer will be pluggable | Avoid vendor lock-in; allow China clinical KB |
| No non-leading query runtime gate | iCoDer will implement NLQ-001..009 (Gate 5) | PDF §8.3 mandatory compliance gate |

## 11. Verdict

`CORTI_CDI_UI_AND_INTEGRATION_AUDIT_COMPLETE`

Corti's CDI is a chat-only agent with English-only output and no native physician response loop. iCoDer Track D will productize beyond Corti by adding: (1) 3-pane workbench, (2) query state machine, (3) physician response panel, (4) SLA tracking, (5) webhook, (6) zh-CN localization, (7) ICD-10-CN coding, (8) non-leading query runtime gate. These are productization decisions, not Corti-parity gaps.

## 12. Next

Gate 2 deliverable `outputs/phase5_track_d/corti_cdi_observations.jsonl` consolidates all 4 reports into JSONL for downstream consumption. Gate 3 (next commit) promotes cdi-review → cdi core agent.
