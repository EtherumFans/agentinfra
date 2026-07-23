# Phase A1B-AE-R — Agent Runtime Verification & Human-Workflow Closure — Reports Index

**Branch**: `phase-a1b/agent-expert-runtime-verification` (local-only)
**Worktree**: `E:/Corti4C-agent-expert-runtime`
**Baseline HEAD**: `85a5c9a` (verified full SHA: `85a5c9abc40fd85648e45343de6d3e1924cdd5a2`)
**Inherited from**: `phase-a1b/agent-expert-clean-room` A1B-AE.11 phase terminal (`85a5c9a`)
**Charter**: [A1B_AE_R_0_CHARTER_AND_BASELINE.md](A1B_AE_R_0_CHARTER_AND_BASELINE.md) — v1.0 (2026-07-22)

## Inherited state (NOT mutated by this phase)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

Full detail: [A1B_AE_R_0_BASELINE_STATE_5_TUPLE.json](A1B_AE_R_0_BASELINE_STATE_5_TUPLE.json)

## Only permitted final verdicts

```
PASS_A1B_AE_R_AGENT_RUNTIME_PRESET_MATERIALIZATION_PUBLIC_EXPERT_MCP_AND_HUMAN_WORKFLOWS_VERIFIED
PARTIAL_A1B_AE_R_RUNTIME_AND_HUMAN_WORKFLOW_RECONCILIATION_FILED
```

Forbidden (8 — unchanged from A1B-AE): `PRODUCTION_READY` / `FULLY_VERIFIED` / `PHI_BOUNDED` / `CORTI_PARITY_VERIFIED` / `PASS_A1A_GATE4_FINAL` / `READY_FOR_HOSPITAL_DEPLOYMENT` / `CLINICAL_GRADE_VERIFIED` / `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED`.

## Sub-gate sequence

| # | Sub-gate | Title | Commits | Status |
|---|---|---|---|---|
| 1 | `A1B-AE-R.0` | Charter + baseline + Journey 7 evidence correction | 1 | **COMPLETED** |
| 2 | `A1B-AE-R.1` | Agent Runtime closure (Task state machine + ThreadAuth DB + Context scrub) | 2 | **COMPLETED** (R.1.a `1b7c750` + R.1.b `5332cc3`) |
| 3 | `A1B-AE-R.2` | Preset Agent materialization (cdi/drg-dip/claim-check Packs + Journey 7 fix) | 1 | **COMPLETED** (`8eb7d60`) |
| 4 | `A1B-AE-R.3` | Public Expert + MCP (PubMed + ClinicalTrials + VCR + SSRF) | 1 | **COMPLETED** (`3a06543`) |
| 5 | `A1B-AE-R.4` | Local Expert completion (Calculator / Memory / Interviewing) | 1 | **COMPLETED** (`48cae71`) |
| 6 | `A1B-AE-R.5` | Frontend + 10 browser journeys (ExpertsPage + NewAgentPage extend + 10 Playwright headed) | 2-3 | **COMPLETED (this commit)** |
| 7 | `A1B-AE-R.6` | Regression + final verdict | 1 | pending |

## Documents (R.0)

| Document | Purpose |
|---|---|
| [A1B_AE_R_0_CHARTER_AND_BASELINE.md](A1B_AE_R_0_CHARTER_AND_BASELINE.md) | Charter v1.0, scope, forbidden verdicts, acceptance conditions, baseline state |
| [A1B_AE_R_0_BASELINE_STATE_5_TUPLE.json](A1B_AE_R_0_BASELINE_STATE_5_TUPLE.json) | Inherited 5-tuple with provenance; `mutated_by_a1b_ae_r=false`; baseline test inventory |
| [A1B_AE_R_0_ENVIRONMENT_MANIFEST.json](A1B_AE_R_0_ENVIRONMENT_MANIFEST.json) | Host, git, worktree path, baseline counts, execution mode, external API strategy, commit granularity |
| [A1B_AE_R_0_PRE_CHANGE_SHA256SUMS.txt](A1B_AE_R_0_PRE_CHANGE_SHA256SUMS.txt) | SHA-256 sums for 15 files R.1..R.5 will touch |
| [A1B_AE_R_0_EXPERT_KEY_MAPPING.md](A1B_AE_R_0_EXPERT_KEY_MAPPING.md) | Corti §3.2 9-key ↔ iCoDer canonical_key ↔ Pack ↔ Preset Agent mapping |
| [A1B_AE_R_0_JOURNEY7_EVIDENCE_CORRECTION.md](A1B_AE_R_0_JOURNEY7_EVIDENCE_CORRECTION.md) | Regrade Journey 7 from `API_WORKFLOW_VERIFIED` to `EVIDENCE_MISJUDGMENT_CORRECTED` |
| [A1B_AE_R_0_BASELINE_TEST_RESULTS.txt](A1B_AE_R_0_BASELINE_TEST_RESULTS.txt) | Baseline test run: 258 passed / 1 failed (pre-existing) / 2 skipped in 76.21s |

## Audit anchors preserved

| Tag | Tag SHA | Commit |
|---|---|---|
| `audit/phase-a0.1r-baseline` | `3cd1bec` | `64590fa` |
| `audit/phase-a1a-gate4-pre4r-b3ea064` | `fa0d461` | `b3ea064` |
| `audit/phase-a1a-gate4r-closure-24967da` | `43c2395` | `24967da` |

New tags planned at end of phase (local-only, never pushed):

- `audit/phase-a1b-agent-expert-runtime-verification-baseline-85a5c9a` on `85a5c9a`
- `audit/phase-a1b-agent-expert-runtime-verification-final-<SHA>` on final commit (conditional on §10 acceptance)

## Evidence directory layout (populated by R.1 onwards)

```
reports/phase-a1b-runtime/
├── INDEX.md                                  (this file)
├── A1B_AE_R_0_*.md / .json / .txt            (R.0 charter + baseline)
├── A1B_AE_R_1_*.md                           (R.1 runtime closure, planned)
├── A1B_AE_R_2_*.md                           (R.2 preset materialization, planned)
├── A1B_AE_R_3_*.md                           (R.3 public expert + MCP, planned)
├── A1B_AE_R_4_*.md                           (R.4 local expert, planned)
├── A1B_AE_R_5_*.md                           (R.5 frontend + journeys, planned)
├── A1B_AE_R_6_FINAL_RECONCILIATION.md        (R.6 terminal, planned)
└── evidence/                                 (populated by R.1+)
    ├── api_captures/                         (R.3 PubMed/ClinicalTrials VCR fixtures)
    ├── journey_01_registry_browse/           (R.5 headed-browser journeys)
    ├── journey_02_research_agent_create/
    ├── journey_03_research_agent_run/
    ├── journey_04_calculator/
    ├── journey_05_interviewing/
    ├── journey_06_external_expert_disabled/
    ├── journey_07_clone_preset_replay/       (R.5 re-run, target HUMAN_WORKFLOW_VERIFIED)
    ├── journey_08_context_delete/
    ├── journey_09_cross_tenant/
    ├── journey_10_logout_cleanup/
    └── journey_manifest.json
```

## Journey 7 status

```
A1B-AE.10 verdict    = API_WORKFLOW_VERIFIED    [MISJUDGED — see A1B_AE_R_0_JOURNEY7_EVIDENCE_CORRECTION.md]
A1B-AE-R.0 regrade   = EVIDENCE_MISJUDGMENT_CORRECTED
A1B-AE-R.5 target    = HUMAN_WORKFLOW_VERIFIED  (with DB row evidence)
```

## Predecessor references

- A1B-AE phase: `reports/phase-a1b/INDEX.md` (12/12 sub-gates filed, terminal `85a5c9a`)
- A1A Gate 4R-I phase: `reports/phase-a1a/gate4r-integration/INDEX.md` (12-sub-gate, terminal `3d50b11`)
- A1A Gate 4 phase: `reports/phase-a1a/gate4/INDEX.md`
- A0.1R freeze: `reports/phase-a0.1r-freeze/INDEX.md`
