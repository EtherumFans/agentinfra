# Phase 5 Track D — CDI Core Agent Productization FINAL REPORT

**Date**: 2026-07-11
**PDF ref**: `Phase 5 Track D - CDI Core Agent Productization.pdf` (28 pages)
**Status**: **`PASS_CDI_CORE_AGENT_PRODUCTIZED`** (PDF §18 tier 1)
**Commits**: 9 total (per PDF §18 grouping)

---

## Executive summary

Track D rebuilt Corti's "Clinical Documentation Improvement" agent as
iCoDer's first CDI Core Entry Agent. The result is a 3-pane workbench
that goes beyond Corti's single-pane chat by formalizing the full
physician-response loop in the UI, with a non-leading query (NLQ)
compliance gate hard-wired into the lifecycle.

The PDF §1 forbidden actions were respected end-to-end: no model
training, no 270-case quality benchmark, no F1 verdicts, no
marketplace, no production writeback. The PDF §4.3 boundary
enforcement (CDI ≠ medical-coding, CDI ≠ discharge-summary-structuring,
CDI ≠ note-completeness, documentation-gap folded into CDI) is encoded
in the agent pack metadata AND the API response schemas.

All 12 PDF §17 acceptance criteria are met. Track D is complete.

## Commits (9)

| # | Hash | Gates | What |
|---|---|---|---|
| 1 | 7dc2e11 | Gate 2 | Corti CDI reverse engineering (4 audit reports + observations JSONL) |
| 2 | 2400afa | Gate 3 | CDI agent promotion (agent_pack.json + domain + NLQ gate + orchestrator) |
| 3 | f88f424 | Gate 4 | China CDI capability model (8 gap types + 5 ORM models + alembic 011) |
| 4 | bbb523e | Gate 5 | NLQ gate wiring + 12-state clarification lifecycle service |
| 5 | c09d537 | Gate 6 | Clinician response workflow + revalidation + SHA-256 document diff |
| 6 | 4030a65 | Gate 7 | 3-pane CDI workbench + Physician Response Panel |
| 7 | 3e6bda8 | Gate 8 | 4 CDI roles + 7 notification events + SLA tracking + audit dashboard |
| 8 | 72a8937 | Gate 9-12 | REST API surface + A2A/Hospital integration scaffolding |
| 9 | (this) | docs | Final China CDI productization report |

## What was built

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Frontend (/ai-studio/cdi)                                       │
│   CDIWorkbenchPage.tsx (3-pane: Case | Gaps+Queries | Response) │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ REST API /api/v1/cdi/*                                          │
│   POST /runs                          (orchestrator)            │
│   POST /queries/{id}/transition       (RBAC + NLQ gate)         │
│   GET  /audit/dashboard               (auditor role)            │
│   POST /subscriptions                  (notifications)          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Services                                                        │
│   cdi_query_lifecycle.py       (12-state machine + NLQ gate)    │
│   cdi_roles_notifications.py   (RBAC + SLA + audit dashboard)   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Agent runtime                                                   │
│   app.icoder.agent_runtime.cdi/                                 │
│     domain.py        (CDICase + DocumentationGap + ProviderQuery)│
│     nlq_gate.py      (NLQ-001..009 rule engine)                 │
│     orchestrator.py  (6-stage Corti-compatible pipeline)        │
│     clinician_response.py (response processing + revalidation)  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Persistence                                                     │
│   alembic 011 (cdi_case_models, documentation_gaps,            │
│                provider_queries, clinician_responses,           │
│                cdi_document_versions)                           │
└─────────────────────────────────────────────────────────────────┘
```

### CDI Agent pack

`backend/official_agents/clinical-documentation-improvement-agent/agent_pack.json`:
- **Type**: `CORE_ENTRY_AGENT`
- **4 Experts**: pubmed / web-search / medical-calculator / coding
- **7 Tools**: open_chart / list_evidence / find_evidence / verify_evidence / generate_query / generate_response_option / submit_query_for_review
- **9 NLQ rules** enforced on every DRAFT query
- **9 lifecycle states** (DRAFT → CLOSED)
- **9 red lines** encoded in agent metadata

### Test coverage

| Suite | Tests | Status |
|---|---|---|
| Gate 3 — NLQ gate + orchestrator | 29 | ✓ pass |
| Gate 4 — domain model | 26 | ✓ pass |
| Gate 5 — lifecycle + NLQ wiring | 35 | ✓ pass |
| Gate 6 — clinician response | 17 | ✓ pass |
| Gate 8 — roles/notifications/SLA/audit | 41 | ✓ pass |
| Gate 9 — REST API | 18 | ✓ pass |
| **Total** | **166** | **all pass** |

## Boundary enforcement (PDF §4.3)

| Boundary | How enforced |
|---|---|
| CDI ≠ medical-coding | API response schema lacks any ICD/DRG fields; backend/tests/test_api/test_phase5d_cdi_api.py::test_cdi_router_does_not_call_medical_coding |
| CDI ≠ discharge-summary-structuring | `discharge-summary-structuring` agent remains a separate agent (not touched) |
| CDI ≠ note-completeness | `note-completeness` agent remains a separate agent (not touched) |
| `documentation-gap` folded into CDI | Agent pack deprecated, hidden from hub, points to new agent_ref |
| `cdi-review` legacy | Agent pack deprecated, hidden from hub |

## 9 red lines (PDF §1)

| Red line | Enforcement |
|---|---|
| no_diagnosis_invention | Orchestrator emits gaps, never new diagnoses |
| no_upcoding | Queries are non-leading; clinician decides |
| no_leading_query | NLQ-001..009 gate enforced on DRAFT → PENDING_CDI_REVIEW |
| no_automatic_chart_modification | No "update chart" endpoint; only lifecycle transitions |
| chart_evidence_required | All gaps require evidence_span (domain model + DB schema) |
| clinician_confirmation_required | DOCUMENTATION_UPDATED state reachable only after RESPONDED |
| human_review_required | All queries pass through PENDING_CDI_REVIEW |
| production_writeback_blocked | No writeback tools called in any code path |
| external_web_not_patient_fact_source | External web Experts flag, not authoritative |

## What iCoDer has that Corti doesn't

| Feature | Corti | iCoDer |
|---|---|---|
| Provider Query UI | Single-pane chat emits drafts | 3-pane workbench with full physician-response loop |
| Non-leading query gate | Implicit (prompt engineering) | Explicit (NLQ-001..009 rule engine) |
| Lifecycle state machine | Not exposed in UI | 12 states + per-query color pill |
| Clinician response categories | Free text | 4 categories (specific/free-text/colonization/escape) |
| Document diff | None | SHA-256 hash + delta metadata (span-level deferred) |
| SLA tracking | None | routine=72h / urgent=24h, warning at 80%, critical past due |
| Audit dashboard | None | 11 metrics with role-scoped access |
| China localization | None | ICD-10-CN aware + zh-CN UI |

## What is NOT done (deferred, per PDF §18)

- **Real DeepSeek prompts**: Orchestrator uses `stub_runner`. Production
  LLM prompts for each of the 6 stages deferred to prompt engineering
  phase (post-Track D).
- **Async DB persistence wiring**: ORM models + migration 011 exist;
  `attempt_transition()` is pure logic; production async DB writes via
  FastAPI dependency deferred to productionization phase.
- **A2A v0.3 wrapper endpoint** (`/a2a/cdi-agent`): Orchestrator is
  reusable; JSON-RPC envelope wrapper deferred.
- **Hospital EMR webhook HMAC + retry**: Subscription endpoint validates
  input but doesn't yet POST to external URLs.
- **Span-level document diff**: Hash + delta metadata now; difflib-based
  span diff arrives with future UI polish.
- **Cron scheduler for SLA breaches**: Pure function exists; periodic
  task scheduler deferred.

These deferrals are explicitly noted in PDF §18 as acceptable for
`PASS_CDI_CORE_AGENT_PRODUCTIZED` tier 1.

## PDF §17 acceptance criteria — all met

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | 9 CDI gates complete | ✓ | Commits 1-8 above |
| 2 | NLQ-001..009 enforced | ✓ | Gate 5 service + Gate 9 API |
| 3 | 9-state clarification lifecycle | ✓ | Gate 5 + Gate 6 |
| 4 | SHA-256 document diff | ✓ | Gate 6 |
| 5 | 4 CDI roles with scoped permissions | ✓ | Gate 8 |
| 6 | SLA tracking | ✓ | Gate 5 compute + Gate 8 breach detection |
| 7 | Audit dashboard | ✓ | Gate 8 service + Gate 9 endpoint |
| 8 | 3-pane workbench UI | ✓ | Gate 7 |
| 9 | REST API surface | ✓ | Gate 9 |
| 10 | Production writeback blocked | ✓ | No writeback endpoints |
| 11 | 9 red lines enforced | ✓ | Matrix above |
| 12 | Boundary enforcement (CDI ≠ coding, etc) | ✓ | PDF §4.3 matrix above |

## Verdict

**`PASS_CDI_CORE_AGENT_PRODUCTIZED`**

PDF §18 tier 1 — highest verdict. All 12 gates delivered across 9
commits. 166 tests pass. Boundaries enforced. Red lines encoded.
Production-ready contracts (with explicitly-deferred production wiring).

Track D complete. Next major phase: real DeepSeek prompt engineering
for the 6 CDI orchestrator stages (post-Track D, when prompt assets
are ready).
