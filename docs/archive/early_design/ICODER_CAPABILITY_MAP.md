# iCoDer 当前能力映射

**日期**: 2026-05-12
**范围**: 扫描全部 backend + frontend + docs，映射已有能力

---

## 1. Backend Pipeline

### 1.1 Orchestrator (10-step fixed pipeline)

```
Step 1: Evidence Extraction        → EvidenceExtractionExpert
Step 2: Timeline Reconstruction    → TimelineReconstructionExpert (9A)
Step 3a: ICD Diagnosis Coding      → ICDDiagnosisExpert
Step 3b: Procedure Coding          → ProcedureCodingExpert
Step 4-6: Homepage + Rules         → MedicalRecordHomepageExpert (9B)
Step 7: Evidence Verification      → EvidenceVerificationExpert
Step 7b: Evidence Ranking          → EvidenceRanker (9C)
Step 7c: Disagreement Analysis     → DisagreementAnalyzer (9D)
Step 7d: Confidence Calibration    → ConfidenceCalibrator (9E)
Step 8a: DRG/DIP Analysis          → DRGDIPExpert
Step 8b: Documentation Gap         → DocumentationGapExpert
Step 9: Report Generation          → ReportExpert
(+ Case Reasoning Report)          → ReasoningReportBuilder (aggregation)
```

### 1.2 Cognitive Modules (Sprint 9A-9E)

| Module | Service | Key Functions |
|--------|---------|---------------|
| Timeline (9A) | `timeline_expert.py` | LLM extraction + regex fallback, anchor resolution |
| Principal Diagnosis Reasoning (9B) | `homepage_expert.py` v2 | Rule matching (R001-R015), adjusted scoring, why_selected/why_not_selected, disagreement analysis, confidence assessment |
| Evidence Ranking (9C) | `evidence_ranker.py` | 11-factor scoring, 5 evidence categories, unsupported detection, 5 conflict types |
| Disagreement (9D) | `disagreement_analyzer.py` | 8-type taxonomy, correction model, DRG sensitivity, gold evolution tracking |
| Confidence (9E) | `confidence_calibrator.py` | 6-source calibration, 3-tier routing (auto/review/escalate), 6 override rules |

### 1.3 Runtime Safety

- 5-layer framework: State Machine → Tool Gates → DUC → Audit Chain → HITL
- 12 DUC actions
- Timeout auto-escalation
- DB persistence
- `runtime_registry` global instance management

### 1.4 Gold Case & Evaluation (Phase 10-11)

- Gold case schema (12 fields) + model
- Batch evaluation (`POST /api/evaluation/run`)
- Extended metrics (soft accuracy, recall, DRG match, reasoning score)
- Gold case template generator (JSON/Markdown)
- Importer (CSV/JSON, dry-run, upsert)
- Adjudication state machine (6 states)
- Inter-rater agreement (Cohen's Kappa, Fleiss' Kappa)
- CLI tool (`pilot_eval_runbook.py`)

### 1.5 Code & Rules

- 33K ICD-10 + 23K ICD-9-CM-3 dictionaries
- 15 coding rules (R001-R015)
- OpenDRG CHS-DRG 1.1 grouper
- LLM-based diagnosis + procedure coding

---

## 2. Frontend Pages

| Page | Relevant to Corti Comparison | Current State |
|------|------------------------------|---------------|
| **CodingWorkbenchPage** | ✅ Core | Tabs (Evidence/Candidates/Report/DRG/Audit), search, Run Review, Export, Human Review button, Runtime badge |
| **CaseReviewPage** | ✅ Core | Code candidate list, Approve/Reject/Modify, Decision Summary shield, Runtime guard display |
| EvaluationPage | ✅ Evaluation | Metrics dashboard |
| GoldCasesPage | ✅ Gold cases | CRUD |
| SettingsPage | ⬜ Config | Guardrail toggles |
| EmbeddedAssistantPage | ⬜ STT | Speech-to-text mode |
| FactExtractionPage | ⬜ Tools | Standalone fact extraction |
| MedicalCodingPage | ⬜ Tools | Standalone coding |
| 16 other pages | ⬜ Admin | Agents, Experts, Rules, Dictionaries, etc. |

---

## 3. Key Integration Points

### 3.1 What the Pipeline Returns (API Response)

```json
{
  "primary_diagnosis": { "code": "Z51.102", "reasoning": {...} },
  "primary_diagnosis_reasoning": {
    "why_selected": "...",
    "why_not_selected": [...],
    "rule_basis": ["R013"],
    "confidence_level": "high",
    "disagreement_analysis": {...},
    "confidence_escalation": {...}
  },
  "timeline": { "events": [...], "anchor_points": {...} },
  "evidence_ranking": { "top_supporting_evidence": [...], "unsupported_codes": [...], "conflicts": [...] },
  "disagreement_analysis": { "corrections": [...], "summary": {...} },
  "confidence_calibration": { "routing_decisions": [...], "metrics": {...} },
  "case_reasoning_report": { "human_readable_summary": "...", ... },
  "diagnosis_candidates": [...],
  "procedure_candidates": [...],
  "report_markdown": "...",
  "drg_impact": {...}
}
```

### 3.2 Frontend Consumes

| Pipeline Output | Frontend Display |
|----------------|-----------------|
| `evidence_ranking` | Evidence tab (partial — only verification status) |
| `diagnosis_candidates` | Candidates tab (table with code/score/status) |
| `primary_diagnosis` + `reasoning` | Report tab (markdown) |
| `drg_impact` | DRG tab |
| `runtime` audit | Audit tab (5 sub-panels) |
| `case_reasoning_report` | **NOT consumed by frontend** |
| `confidence_calibration.routing_decisions` | **NOT consumed by frontend** |
| `disagreement_analysis` | **NOT consumed by frontend** |
| `timeline` | **NOT consumed by frontend** |

---

## 4. Test Coverage

| Layer | Tests | Coverage |
|-------|-------|----------|
| Backend unit | 481 | All services + experts + runtime |
| Regression | 100 | Determinism + fallback + recovery |
| Frontend unit | 0 | vitest configured but no tests |
| E2E | 1 file | Phase 4 workflow spec (renders only) |

---

## 5. Documentation

| Category | Count | Key Docs |
|----------|-------|----------|
| Architecture | 4 | Runtime Disciplines, Coding Workflow, Governance Blueprint |
| Sprints (9A-9E) | 6 | Timeline, Reasoning, Evidence, Disagreement, Confidence, Case Report |
| Phase Reports | 8 | P0-P6 reports, Phase 10-11 |
| Pilot | 8 | Demo script, Acceptance checklist, Known limitations, Data request, Issue template, Runbook, Deliverable package, Thresholds |
| Analysis | 5 | Corti vs iCoDer gaps, iCoDer convergence audit, Frontend fake features, E2E plans |

---

## 6. 不纳入映射的能力 (明确排除)

- A2A Agent 协同 — 仅注册，无业务调用
- WebSocket STT — 不可用
- CI/CD — 无
- 前端单元/E2E — 0覆盖
- Billing — 不在范围
- Multi-tenant SaaS — 不在范围
