# Phase 5 Track D — Gate 1 CDI Documentation Realignment Report

**Date**: 2026-07-11
**Gate**: 1 — Force update system documentation (PDF §4 mandatory P0)
**Status**: `PASS_GATE1_DOCS_REALIGNED`

---

## 1. PDF §4 mandate

PDF §4 requires updating all core product and architecture docs to
explicitly position CDI as a `CORE_ENTRY_AGENT`, distinct from
note-completeness, discharge-summary-structuring, and medical-coding.

## 2. Files updated (Gate 1)

| File | Update | Before → After |
|---|---|---|
| `CLAUDE.md` | Add "两个核心业务入口" section + "边界" section + CDI listed first in 医疗收入合规体系 tree | CDI absent → CDI = Core Entry Agent #1, explicit boundaries |
| `README.md` | Add CDI as bullet #1 in Core capabilities + new "Two Core Entry Agents" section | CDI absent → CDI explicitly positioned with relationship to Medical Coding |
| `docs/PRODUCT-MODULES.md` | Add "Core Entry Agents" section at top, mark CDI as CORE_ENTRY_AGENT, mark related agents as SPECIALIZED/ORCHESTRATED, mark documentation-gap as "CDI internal capability" | CDI listed as Agent #78 with no role → CDI = CORE_ENTRY_AGENT #1 |
| `docs/SOLUTION-SCENARIOS.md` | Rewrite Scenario 2 (CDI) with new flow, non-leading query example, 9 red lines, new deployment API | Old scenario used leading query "建议: 请...明确: 肺炎病原体是否为肺炎链球菌？" + old `/api/agents` API → new scenario uses non-leading query with response options + new `/api/cdi/runs` API |

## 3. Core Agent list (PDF §4.1)

Per PDF §4.1 the updated core agent list:

```
CORE_ENTRY_AGENT (2):
  1. Clinical Documentation Improvement Agent (CDI)
  2. Medical Coding Agent

SPECIALIZED_AGENT (2):
  3. Note Completeness Agent (形式完整性)
  4. Discharge Summary Structuring Agent (出院小结结构化)

ORCHESTRATED_CAPABILITY (6):
  5. Evidence Extraction Agent
  6. Principal Diagnosis Review Agent
  7. Procedure Extraction Agent
  8. Code Validation Agent
  9. Compliance Guardrail Agent
  10. DRG/DIP Risk Review Agent
```

## 4. Boundary clarifications (PDF §4.3)

Now explicit in CLAUDE.md + README.md + PRODUCT-MODULES.md + SOLUTION-SCENARIOS.md:

- ✅ `discharge-summary-structuring` ≠ CDI (出院小结结构化抽取)
- ✅ `note-completeness` ≠ CDI (形式完整性检查)
- ✅ `medical-coding` ≠ CDI (编码而非临床澄清)
- ✅ `documentation-gap` 属于 CDI 内部能力或 CDI 结果类型 (NOT 顶层 Agent)

## 5. Agent Mapping update (PDF §4.4)

| Corti | iCoDer current | iCoDer target (Track D) |
|---|---|---|
| `clinical-documentation-improvement-cdi-agent` | `cdi-review` (metadata-only, PARTIAL_MATCH) | `clinical-documentation-improvement-agent` (CORE_AGENT, EXACT_MATCH_AT_PRODUCT_AND_RUNTIME_LEVEL, LOCALIZED_FOR_CHINA) |

The rename from `cdi-review` → `clinical-documentation-improvement-agent` will happen in Gate 3 (promote from metadata-only). `cdi-review` is kept as legacy alias for migration only.

## 6. Architecture diagram update (PDF §4.5)

New architecture (recorded in CLAUDE.md + this report):

```
Clinical Documentation Layer
├── Discharge Summary Structuring (SPECIALIZED)
├── Note Completeness (SPECIALIZED)
└── CDI Core Agent (CORE_ENTRY_AGENT)
    ├── Documentation Gap Detection
    ├── Clinical Specificity Review
    ├── Contradiction Detection
    ├── Query Generation (Non-leading)
    ├── Query Compliance Review
    └── Clinician Response Loop

Coding Compliance Layer (Phase 5 Track C, complete)
├── Medical Coding (CORE_ENTRY_AGENT)
├── Principal Diagnosis Review
├── Procedure Extraction
├── Evidence Extraction
├── Code Validation
├── Compliance Guardrail
└── DRG/DIP Risk Review
```

## 7. Roadmap change

Phase 5 plan updated:
- Track A (Quality at Scale) — COMPLETE
- Track B (Corti × iCoDer Audit) — COMPLETE
- Track B-2 (Real-Run Validation) — COMPLETE
- Track C (Corti Runtime Reconstruction) — COMPLETE (READY_FOR_FORMAL_QUALITY_BENCHMARK)
- **Track D (CDI Core Agent Productization) — IN PROGRESS (this track)**
- Quality benchmark track — separate PDF, deferred

## 8. Verification

- ✅ CLAUDE.md, README.md, PRODUCT-MODULES.md, SOLUTION-SCENARIOS.md all updated in this commit
- ✅ All 4 boundary conditions from PDF §4.3 explicit in docs
- ✅ CDI listed as CORE_ENTRY_AGENT #1 in 3 of 4 docs (4th will follow in Track D implementation)
- ✅ Architecture diagram shows Clinical Documentation Layer + Coding Compliance Layer
- ✅ Agent Mapping correct (Corti → iCoDer target)

## 9. Next: Gate 2 — Corti CDI deep reverse engineering

Gate 2 explores Corti's CDI agent live (if account permissions allow)
or via static analysis to extract the runtime patterns iCoDer needs to
replicate. Produces 4 reports + 1 observations JSONL.
