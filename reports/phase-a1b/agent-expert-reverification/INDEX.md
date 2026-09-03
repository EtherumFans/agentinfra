# Phase A1B-AE-RV — Terminal Evidence Repair & Reacceptance — Reports Index

**Branch**: `phase-a1b/agent-expert-terminal-reverification` (local-only)
**Worktree**: `E:/Corti4C-agent-expert-reverification`
**Predecessor HEAD**: `8546184` (A1B-AE-R.6 phase terminal)
**Predecessor branch**: `phase-a1b/agent-expert-runtime-verification` (frozen, untouched)
**Baseline ancestor**: `85a5c9a` (A1B-AE.11 terminal)
**Execution prompt**: `C:\Users\huawei\Downloads\Claude_Code_A1B_AE_RV_Terminal_Reverification_Prompt.md`

## Inherited 5-tuple state (NOT mutated)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

## Prior terminal verdict (per RV.0)

```
A1B_AE_R_PRIOR_TERMINAL_VERDICT = PENDING_REVALIDATION
```

RV.7 will resolve to `RECONFIRMED` / `SUPERSEDED` / `NOT_VERIFIED`.

## Permitted final verdicts (per §17)

```
PASS_A1B_AE_RV_TERMINAL_EVIDENCE_REPAIR_FULL_REGRESSION_MIGRATION_CONTEXT_SCRUB_PUBLIC_EXPERT_LIVE_AND_HEADED_WORKFLOWS_VERIFIED
PARTIAL_A1B_AE_RV_TERMINAL_EVIDENCE_REPAIR_AND_REACCEPTANCE_FILED
```

## Forbidden verdicts (per §18 — 10 items)

`PRODUCTION_READY` / `FULLY_VERIFIED` / `PHI_BOUNDED` / `CORTI_PARITY_VERIFIED` / `PASS_A1A_GATE4_FINAL` / `READY_FOR_HOSPITAL_DEPLOYMENT` / `CLINICAL_GRADE_VERIFIED` / `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED` / `CORTI_AGENTIC_PARITY_VERIFIED` / `READY_FOR_MVP_SHIP`.

## Sub-gate sequence

| # | Sub-gate | Title | Commits | Status |
|---|---|---|---|---|
| 1 | `A1B-AE-RV.0` | Charter + evidence freeze + terminal correction notice | 1 | **COMPLETED (this commit)** |
| 2 | `A1B-AE-RV.1` | Exact test collection + node-ID diff + 4/27 attribution | 1 | pending |
| 3 | `A1B-AE-RV.2` | Migration safety + dev DB isolation + PostgreSQL | 1 | pending |
| 4 | `A1B-AE-RV.3` | Context scrub completion + org fail-closed | 1 | pending |
| 5 | `A1B-AE-RV.4` | PubMed + ClinicalTrials live capture | 1 | pending |
| 6 | `A1B-AE-RV.5` | True headed-browser Playwright E2E (10 × 3) | 3 | pending |
| 7 | `A1B-AE-RV.6` | Full regression + OpenAPI + SDK + Migration | 1 | pending |
| 8 | `A1B-AE-RV.7` | Final verdict + state output | 1 | pending |

**Estimated total**: 10 commits.

## Evidence directory layout (populated by RV.1+)

```
reports/phase-a1b/agent-expert-reverification/
├── INDEX.md                                (this file)
├── A1B_AE_RV_0_CHARTER_AND_EVIDENCE_FREEZE.md
├── A1B_AE_RV_0_TERMINAL_VERDICT_CORRECTION_NOTICE.md
├── A1B_AE_RV_1_EXACT_REGRESSION_RECONCILIATION.md   (RV.1)
├── A1B_AE_RV_2_MIGRATION_SAFETY_AND_DB_ISOLATION.md (RV.2)
├── A1B_AE_RV_3_CONTEXT_SCRUB_AND_TENANT_FAIL_CLOSED.md (RV.3)
├── A1B_AE_RV_4_PUBLIC_EXPERT_LIVE_CAPTURE.md        (RV.4)
├── A1B_AE_RV_5_TRUE_HEADED_BROWSER_JOURNEYS.md      (RV.5)
├── A1B_AE_RV_6_FULL_REGRESSION_AND_REACCEPTANCE.md  (RV.6)
├── A1B_AE_RV_7_FINAL_VERDICT.md                     (RV.7)
└── evidence/
    ├── rv0/                                (pre-change freeze)
    │   ├── PRE_CHANGE_GIT_STATE.txt
    │   ├── PRE_CHANGE_WORKTREE_STATE.txt
    │   ├── PRE_CHANGE_FILE_MANIFEST.csv
    │   ├── PRE_CHANGE_ENVIRONMENT_MANIFEST.json
    │   ├── PRE_CHANGE_OPENAPI.json
    │   ├── PRE_CHANGE_TEST_COLLECTION.txt
    │   └── PRE_CHANGE_SHA256SUMS.txt
    ├── git/                               (RV.1)
    ├── baseline-85a5c9a/                   (RV.1 node-ID + JUnit)
    ├── terminal-8546184/                   (RV.1 node-ID + JUnit)
    ├── repair-head/                        (RV.1 node-ID + JUnit)
    ├── node-diff/                          (RV.1 diff CSVs)
    ├── migrations/                         (RV.2 scenario evidence)
    ├── postgres/                           (RV.2 PostgreSQL evidence)
    ├── context-scrub/                      (RV.3 marker scan)
    ├── public-expert-live/                 (RV.4 live capture)
    ├── vcr/                                (RV.4 VCR replay)
    ├── frontend/                           (RV.6 frontend evidence)
    ├── journeys/                           (RV.5 journey evidence)
    ├── screenshots/                        (RV.5)
    ├── traces/                             (RV.5)
    ├── videos/                             (RV.5)
    ├── sanitized-har/                       (RV.5)
    ├── console/                            (RV.5)
    ├── junit/                              (RV.1 + RV.6)
    ├── openapi/                            (RV.6)
    ├── sdk/                                (RV.6)
    └── sha256/                             (RV.7 final SHA-256 manifest)
```

## Machine-readable state files (per §十五)

```
A1B_AE_RV_STATE.json                       (master state JSON)
PRIOR_TERMINAL_CLAIM_MATRIX.csv             (10 R claims + status)
TEST_COLLECTION_DIFF.json                   (RV.1)
NODE_TRANSITIONS_85A5C9A_TO_8546184.csv      (RV.1)
NODE_TRANSITIONS_8546184_TO_FINAL.csv        (RV.1 / RV.6)
FAILURE_CLASSIFICATION.csv                  (RV.1 4/27 attribution)
MIGRATION_SCENARIO_MATRIX.csv               (RV.2)
CONTEXT_DATA_DEPENDENCY_GRAPH.json          (RV.3)
CONTEXT_SCRUB_MATRIX.csv                    (RV.3)
PUBLIC_EXPERT_LIVE_RESULTS.json             (RV.4)
HUMAN_JOURNEY_RESULTS.json                  (RV.5)
HUMAN_JOURNEY_STEP_LOGS.json                (RV.5)
BROWSER_STORAGE_RESULTS.json                (RV.5 Journey 10)
TEST_COMMAND_LOG.txt                        (RV.6)
EVIDENCE_SHA256SUMS.txt                     (RV.7)
FINAL_COMMIT_MANIFEST.json                  (RV.7)
```

## Predecessor references

- A1B-AE-R phase: `reports/phase-a1b-runtime/INDEX.md` (R.0..R.6, terminal `8546184`)
- A1B-AE phase: `reports/phase-a1b/INDEX.md` (12/12 sub-gates, terminal `85a5c9a`)
- A1A Gate 4R-I phase: `reports/phase-a1a/gate4r-integration/INDEX.md`
- A1A Gate 4 phase: `reports/phase-a1a/gate4/INDEX.md`
- A0.1R freeze: `reports/phase-a0.1r-freeze/INDEX.md`

## Charter discipline

Per §20 item 16: "不要在每个子门之间等待人工确认,在 Charter 授权范围内连续执行." RV.0 starts execution; RV.7 closes. No inter-sub-gate user confirmation unless external hard blocker.
