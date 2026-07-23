# A1B-AE-RV.0 — Charter + Evidence Freeze

**Phase**: A1B-AE-RV (Terminal Evidence Repair & Reacceptance)
**Sub-gate**: RV.0
**Date**: 2026-07-23
**Predecessor**: A1B-AE-R terminal commit `8546184` (`PASS_A1B_AE_R_AGENT_RUNTIME_PRESET_MATERIALIZATION_PUBLIC_EXPERT_MCP_AND_HUMAN_WORKFLOWS_VERIFIED`)
**Execution prompt**: `C:\Users\huawei\Downloads\Claude_Code_A1B_AE_RV_Terminal_Reverification_Prompt.md`

## Phase purpose

A1B-AE-RV is **evidence repair + reacceptance**, NOT feature expansion. It challenges the A1B-AE-R PASS verdict and treats each of its 10 load-bearing claims as a hypothesis to be re-verified:

1. "10/10 HUMAN_WORKFLOW_VERIFIED"
2. "Full backend regression verified"
3. "Public Expert live integration verified"
4. "5 个 Preset 已 materialized"
5. "legacy orphan deletion completed"
6. "Context scrub completed"
7. "4 failed + 27 errors 均为 pre-existing"
8. "Migration 024/025 upgrade path safe"
9. "NEW_FAIL=0 / NEW_ERROR=0"
10. Final PASS verdict satisfies original Charter conditions

The phase must NOT default to assuming these are correct. Each claim is a hypothesis with the burden of proof on the phase.

## Engineering preservation

A1B-AE-R engineering work is preserved — Task / ThreadAuth / Context / Preset Clone / SSRF / Public Expert Adapter / Calculator / Memory / Interviewing / frontend code all stay in place. RV judges whether they actually work and whether evidence meets original Charter requirements.

## Inherited state (must NOT be mutated)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

## Prior terminal verdict status

A1B-AE-R `PASS_A1B_AE_R_AGENT_RUNTIME_PRESET_MATERIALIZATION_PUBLIC_EXPERT_MCP_AND_HUMAN_WORKFLOWS_VERIFIED` is marked at RV.0 as:

```
A1B_AE_R_PRIOR_TERMINAL_VERDICT = PENDING_REVALIDATION
```

(Alternate allowed label: `NOT_YET_SUPPORTED_BY_COMPLETE_EVIDENCE`.)

The prior verdict is NOT modified or deleted. It is treated as a claim pending revalidation. RV.7 will resolve it to `SUPERSEDED`, `RECONFIRMED`, or `NOT_VERIFIED`.

## Only permitted final verdicts (per §17)

- **Pass (all 33 acceptance conditions satisfied)**:
  `PASS_A1B_AE_RV_TERMINAL_EVIDENCE_REPAIR_FULL_REGRESSION_MIGRATION_CONTEXT_SCRUB_PUBLIC_EXPERT_LIVE_AND_HEADED_WORKFLOWS_VERIFIED`
- **Partial (any condition unmet)**:
  `PARTIAL_A1B_AE_RV_TERMINAL_EVIDENCE_REPAIR_AND_REACCEPTANCE_FILED`

## Forbidden verdicts (per §18) — 10 items

`PRODUCTION_READY` / `FULLY_VERIFIED` / `PHI_BOUNDED` / `CORTI_PARITY_VERIFIED` / `PASS_A1A_GATE4_FINAL` / `READY_FOR_HOSPITAL_DEPLOYMENT` / `CLINICAL_GRADE_VERIFIED` / `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED` / `CORTI_AGENTIC_PARITY_VERIFIED` / `READY_FOR_MVP_SHIP`.

## Git + branch setup

- **Predecessor**: `8546184` (verified, full SHA `85461848b4067100df7df40367cb49753559506f`)
- **Baseline ancestor**: `85a5c9a` (verified, full SHA `85a5c9abc40fd85648e45343de6d3e1924cdd5a2`)
- **New branch**: `phase-a1b/agent-expert-terminal-reverification` (local-only)
- **New worktree**: `E:/Corti4C-agent-expert-reverification` (from `8546184`)
- **Baseline tag** (created at RV.7 if verdict conditions met): `audit/phase-a1b-ae-rv-baseline-8546184` (annotated, local-only)

Forbidden git ops (unchanged from A1B-AE-R charter):
- No push, no PR, no deploy
- No amend of `8546184` or any ancestor
- No rebase, no squash, no reset --hard
- No branch delete, no tag delete/rewrite
- No `git add -A`, no `git add .`, no `commit -a`

## Sub-gate sequence

| # | Sub-gate | Title | Est. commits |
|---|---|---|---|
| RV.0 | Charter + evidence freeze + terminal correction notice | 1 (this commit) |
| RV.1 | Exact test collection + node-ID diff + 4/27 attribution | 1 |
| RV.2 | Migration safety + dev DB isolation + PostgreSQL | 1 |
| RV.3 | Context scrub completion + org fail-closed | 1 |
| RV.4 | PubMed + ClinicalTrials live capture | 1 |
| RV.5 | True headed-browser Playwright E2E (10 journeys × 3 runs) | 3 |
| RV.6 | Full regression + OpenAPI + SDK + Migration | 1 |
| RV.7 | Final verdict + state output | 1 |

**Estimated total**: 10 commits.

## Evidence inventory (RV.0)

`reports/phase-a1b/agent-expert-reverification/evidence/rv0/`:

- `PRE_CHANGE_GIT_STATE.txt` — git status, branch, HEAD, log, show-ref, fsck
- `PRE_CHANGE_WORKTREE_STATE.txt` — worktree list, branch list, audit tags
- `PRE_CHANGE_FILE_MANIFEST.csv` — 2882 git-tracked files with SHA-256 + size
- `PRE_CHANGE_ENVIRONMENT_MANIFEST.json` — Python/platform/git HEAD/branch/remote/ICODER env keys
- `PRE_CHANGE_TEST_COLLECTION.txt` — pytest --collect-only at 8546184 (3925/3935 tests, 10 deselected)
- `PRE_CHANGE_OPENAPI.json` — pre-change scope manifest (files RV will touch vs files RV will NOT touch)
- `PRE_CHANGE_SHA256SUMS.txt` — SHA-256 for A1B-AE-R.0..R.6 reports + journey evidence + Migration 024/025 (31 entries)

## Critical corrections (must be documented in RV.0 notice)

Per §六, RV.0 must explicitly document that the following R.5/R.6 claims are **pending revalidation**, not confirmed facts:

1. **Journey 4/5/6 in R.5 were Python module invocations** — not real browser journeys. Charter §3 requires headed-browser as final arbiter.
2. **Journey 7/8/9 were HTTP + pytest** — not real browser journeys.
3. **Journey 10 was source inspection + local runtime check** — not real browser verification.
4. **10/10 HUMAN_WORKFLOW_VERIFIED needs re-verification.**
5. **R.6's "full backend" command was actually `pytest tests/test_api/`** — this is API_TEST_SUITE, not BACKEND_ALL_TESTS (`pytest tests/`).
6. **4 failed + 27 errors have NOT been proven pre-existing by baseline node-ID diff** — file age is not proof.
7. **PubMed / ClinicalTrials live capture is NOT proven** — R.3 has adapter + VCR replay but no recorded live exchange.
8. **Intake Preset is Expert-backed, not Pack-backed** — must be correctly labelled.
9. **3 underscore legacy dirs are RETAINED, not DELETED** — R.2 may have retained renamed/aliased dirs.
10. **Context direct-child scrub is implemented, but ConversationMemory / vector / MCP temp scrub need proof.**
11. **Dev DB migration incident must enter formal evidence ledger.**
12. **Prior PASS verdict is NOT modified or deleted — status transitions to PENDING_REVALIDATION.**

## Acceptance gate (33 conditions, per §十三)

RV.7 will only sign PASS if ALL 33 conditions are met. Any single unmet condition forces PARTIAL. Conditions span: prior notice filed, node-ID diff complete, NEW_FAIL=0, NEW_ERROR=0, removed baseline tests=0, 4/27 attributed by node-ID, BACKEND_ALL_TESTS executed, API_TEST_SUITE executed, frontend unit + ESLint, 10 journeys real headed-browser, Journeys 4-6 not Python module, Journey 8 real Context scrub incl. ConversationMemory, Journey 9 real Tenant B negative, Journey 10 real browser storage, Context delete covers vector/MCP/temp (or proven N/A), organization_id fail-closed on new writes, Migration 024 partial-schema verified, Migration 025 no permanent org_default1, no dev DB for migration tests, SQLite old-schema upgrade, PostgreSQL migration, PubMed live, ClinicalTrials live, VCR replay matches live, Intake Preset correctly labelled, legacy underscore dirs correctly labelled, `tests/test_api/` not called "full backend", terminology consistent, no PHI, no secret leak, no security weakening.

## Execution discipline (§二十)

Key: 保留 8546184 原样不 amend; 先纠正证据再改代码; 不混淆工程问题与证据问题; Python 模块调用 ≠ 浏览器人工工作流; HTTP/pytest 负向 ≠ 浏览器; 源码 grep ≠ 运行时验证; `tests/test_api/` ≠ backend full suite; 测试文件早不代表 pre-existing fail; VCR replay ≠ live connectivity; 重建空 DB ≠ 旧 DB upgrade 成功; 删直接子表 ≠ 全 Memory 清除; 永久 org_default1 默认 ≠ fail-closed; retained legacy 不得写 deleted; Expert-backed Preset 不得写 Pack-backed; 所有结论必须能由 Git history + node-ID diff + JUnit + 完整 logs + migration snapshots + PostgreSQL evidence + DB marker scan + live public API capture + real headed-browser + screenshot + trace + video + sanitized HAR + audit records + SHA-256 独立重建。

Charter §20 item 16: 不要在每个子门之间等待人工确认,在 Charter 授权范围内连续执行. RV.0 starts execution; RV.7 closes.
