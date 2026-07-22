# Phase A1B-AE — Agent & Expert Clean-Room Replication — Reports Index

**Branch**: `phase-a1b/agent-expert-clean-room` (local-only)
**Worktree**: `E:/Corti4C-agent-expert`
**Baseline HEAD**: `3d50b11` (verified full SHA: `3d50b116597c992ac92de189fad70def11349dcb`)
**Inherited from**: `phase-a1a/emergency-containment` Gate 4R-I.11 (3d50b11)
**Charter**: [A1B_AE_0_CHARTER_AND_BASELINE.md](A1B_AE_0_CHARTER_AND_BASELINE.md) — v1.0 (2026-07-22) → **v1.1 (2026-07-22 mid-phase)**; see [Charter Amendment 1](A1B_AE_0_CHARTER_AMENDMENT_1_REVERSE_ENGINEERING_PERMITTED.md)

## Inherited state (NOT mutated by this phase)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

Full detail: [A1B_AE_0_BASELINE_STATE_5_TUPLE.json](A1B_AE_0_BASELINE_STATE_5_TUPLE.json)

## Only permitted final verdict

```
PARTIAL_A1B_AE_AGENT_EXPERT_CAPABILITY_AND_TECH_DEBT_RECONCILIATION_FILED
```

Forbidden: PRODUCTION_READY / FULLY_VERIFIED / PHI_BOUNDED / CORTI_PARITY_VERIFIED /
PASS_A1A_GATE4_FINAL / READY_FOR_HOSPITAL_DEPLOYMENT / CLINICAL_GRADE_VERIFIED /
CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED.

## Commit sequence

| # | Sub-gate | Title | Status | Commit |
|---|---|---|---|---|
| 1 | `A1B-AE.0` | Charter + baseline + human-operation protocol | **COMPLETED** | `37e4848` |
| 2 | `A1B-AE.1` | Corti official Agentic manual observation + clean-room contracts | **COMPLETED (partial reconstruction)** | `558cfce` |
| 3 | `A1B-AE.2` | Agent / Expert taxonomy + canonical catalogs | **COMPLETED (filed, not verified)** | `b23c69a` |
| 4 | `A1B-AE.3` | Expert Registry (model + alembic + API) | **COMPLETED (filed, not verified)** | `f5839ca` |
| 5 | `A1B-AE.4` | Agent CRUD + Agent Card + alias / version resolution | **COMPLETED (filed, not verified)** | `154484b` |
| 6 | `A1B-AE.5` | Message → Task → Context + Memory Expert | **COMPLETED (filed, not verified)** | `b253388` |
| 7 | `A1B-AE.6` | Calculator + PubMed + Clinical Trials Experts | **COMPLETED (filed, not verified)** | _(this commit)_ |
| 8 | `A1B-AE.7` | Interviewing Expert + Coding wrapper + external-Expert gates | pending | — |
| 9 | `A1B-AE.8` | iCoder Preset Agents (5 clean-room agents) | pending | — |
| 10 | `A1B-AE.9` | Agent/Expert tech-debt liquidation | pending | — |
| 11 | `A1B-AE.10` | 10 headed-browser journeys + evidence | pending | — |
| 12 | `A1B-AE.11` | Final reconciliation report + verdict | pending | — |

## Documents

| Document | Purpose |
|---|---|
| [A1B_AE_0_CHARTER_AND_BASELINE.md](A1B_AE_0_CHARTER_AND_BASELINE.md) | Charter v1.0 → v1.1, scope, forbidden verdicts, acceptance conditions, baseline state |
| [A1B_AE_0_CHARTER_AMENDMENT_1_REVERSE_ENGINEERING_PERMITTED.md](A1B_AE_0_CHARTER_AMENDMENT_1_REVERSE_ENGINEERING_PERMITTED.md) | **v1.1 Amendment** — adds `REVERSE_ENGINEERED` provenance tier (Corti Console observation + behavioural RE permitted under developer account). CLEAN_ROOM_PUBLIC tier unchanged. Forbidden verdicts unchanged. |
| [A1B_AE_0_HUMAN_OPERATION_PROTOCOL.md](A1B_AE_0_HUMAN_OPERATION_PROTOCOL.md) | Headed-browser protocol, evidence archive layout, 11 conditions for HUMAN_WORKFLOW_VERIFIED |
| [A1B_AE_0_ENVIRONMENT_MANIFEST.json](A1B_AE_0_ENVIRONMENT_MANIFEST.json) | Host, git, baseline counts, pack classification, clean-room sources |
| [A1B_AE_0_PRE_CHANGE_SHA256SUMS.txt](A1B_AE_0_PRE_CHANGE_SHA256SUMS.txt) | SHA-256 sums for 15 key Agent/Expert files at baseline |
| [A1B_AE_0_BASELINE_STATE_5_TUPLE.json](A1B_AE_0_BASELINE_STATE_5_TUPLE.json) | Inherited 5-tuple with provenance; mutated_by_a1b_ae=false |
| [A1B_AE_1_CORTI_PUBLIC_CONTRACTS_CLEAN_ROOM_RECONSTRUCTION.md](A1B_AE_1_CORTI_PUBLIC_CONTRACTS_CLEAN_ROOM_RECONSTRUCTION.md) | 8 Corti public pages observed via headed browser; clean-room Agent/Expert/MCP/Task/Context/Memory contracts; UNKNOWN list |
| [A1B_AE_2_TAXONOMY.md](A1B_AE_2_TAXONOMY.md) | A1B-AE.2 unified 8-kind taxonomy (Agent / Expert / Pack / Preset Agent / Tool / MCP Server / Agent Card / Runtime elements); 4-value Pack classification; 3-value Agent classification; 3-value Expert classification; source-of-truth hierarchy |
| [A1B_AE_2_AGENT_ARCHITECTURE_RECONCILIATION.md](A1B_AE_2_AGENT_ARCHITECTURE_RECONCILIATION.md) | A1B-AE.2 answers the 10 §9 architecture questions (source of truth, dual-naming, version shadowing, clone-404 root cause, seed-vs-Pack drift, Agent Card field drift, metadata-only mislabeling, expert-stub vestige); machine-derived counts (29 canonical Agents, 40 Experts, 32 Packs); carry-forward table to A1B-AE.3..A1B-AE.9 |
| [A1B_AE_3_EXPERT_REGISTRY.md](A1B_AE_3_EXPERT_REGISTRY.md) | A1B-AE.3 Expert Registry provenance layer — Migration 022 schema, `/api/v1/experts` REST surface, charter Amendment 1 §7 provenance discipline, evidence sources from both CLEAN_ROOM_PUBLIC + REVERSE_ENGINEERED tiers |
| [A1B_AE_4_AGENT_CRUD.md](A1B_AE_4_AGENT_CRUD.md) | A1B-AE.4 Agent canonical_key + agent_type + aliases (Migration 023), Corti §6 Agent Card surface, Corti Console create-then-customize `/api/v1/agents/quick`, AliasResolver service, clone-404 fix |
| [A1B_AE_5_MESSAGE_TASK_CONTEXT.md](A1B_AE_5_MESSAGE_TASK_CONTEXT.md) | A1B-AE.5 4 mcp_auth_* error codes + auth DataPart extractor + thread-first-message registration rule + Memory Expert stub (Corti §3.2 key 1/9, lexical-only, no parity claim) |
| [A1B_AE_6_EXTERNAL_EXPERTS.md](A1B_AE_6_EXTERNAL_EXPERTS.md) | A1B-AE.6 Medical Calculator Expert (BMI + Cockcroft-Gault, CORTI_ADAPTED) + PubMed stub (CORTI_REFERENCE) + Clinical Trials stub (CORTI_REFERENCE); Corti §3.2 keys 3/7/8 of 9; 17 tests PASS |
| [evidence/](evidence/) | Per-page Corti observation + per-journey iCoDer browser evidence + sanitized HAR + SHA-256 manifest (populated from A1B-AE.1 onwards) |

## Audit anchors preserved

| Tag | Tag SHA | Commit |
|---|---|---|
| `audit/phase-a0.1r-baseline` | `3cd1bec` | `64590fa` |
| `audit/phase-a1a-gate4-pre4r-b3ea064` | `fa0d461` | `b3ea064` |
| `audit/phase-a1a-gate4r-closure-24967da` | `43c2395` | `24967da` |

New tags planned at end of phase (local-only, never pushed):

- `audit/phase-a1b-agent-expert-clean-room-baseline-3d50b11`
- `audit/phase-a1b-agent-expert-clean-room-final-<SHA>` (only if §10 acceptance met)

## Forbidden operations in this phase

```
git merge --ff-only        # fast-forward forbidden (no-ff if ever merged; not in scope)
git push                   # not pushed
git rebase                 # not rebased
git commit --amend         # not amended
git reset --hard           # not hard-reset
git add -A / git add .     # explicit file list only
git commit -a              # explicit staging only
```

Direct DB writes to fake user operations are forbidden as primary evidence
(headed-browser / curl-per-command only).
