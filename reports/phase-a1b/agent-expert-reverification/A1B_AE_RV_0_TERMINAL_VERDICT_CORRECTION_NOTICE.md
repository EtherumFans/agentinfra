# A1B-AE-RV.0 — Terminal Verdict Correction Notice

**Sub-gate**: RV.0
**Date**: 2026-07-23
**Prior terminal**: A1B-AE-R.6 `8546184` `PASS_A1B_AE_R_AGENT_RUNTIME_PRESET_MATERIALIZATION_PUBLIC_EXPERT_MCP_AND_HUMAN_WORKFLOWS_VERIFIED`

## Status transition

```
A1B_AE_R_PRIOR_TERMINAL_VERDICT
  WAS:  PASS_A1B_AE_R_AGENT_RUNTIME_PRESET_MATERIALIZATION_PUBLIC_EXPERT_MCP_AND_HUMAN_WORKFLOWS_VERIFIED
  NOW:  PENDING_REVALIDATION
  (alternate label: NOT_YET_SUPPORTED_BY_COMPLETE_EVIDENCE)
```

The prior PASS verdict is NOT modified, NOT deleted, NOT marked FRAUD / INVALID / FAILED. Per §六 it is preserved as `PENDING_REVALIDATION` until RV.7 resolves to one of:

- `RECONFIRMED` — RV evidence independently supports the PASS
- `SUPERSEDED` — RV issues a fresh verdict (PASS or PARTIAL), predecessor is historical
- `NOT_VERIFIED` — RV cannot support the PASS, phase ends at PARTIAL without promoting

## Why the revalidation is needed

Per execution prompt §一, A1B-AE-R carried 10 load-bearing claims. RV.0 freezes the evidence state and flags each claim as a hypothesis pending proof. The most material gaps documented by RV.0:

### Gap 1 — R.5 Journey 4/5/6 were Python module invocations, not browser workflows

R.5 inspection.md files explicitly state (verbatim quotes):

- `journey_04_calculator/inspection.md`: "Entry: Python module `app.agents.experts.medical_calculator_expert`"
- `journey_05_interviewing/inspection.md`: "Entry: Python module `app.agents.experts.interviewing_expert`"
- `journey_06_external_expert_disabled/inspection.md`: "Entry: Python module `app.agents.experts.external_expert_gate`"

Charter §3 requires headed-browser evidence as final arbiter. Python module invocation is NOT browser workflow. RV.5 must re-run these journeys via real Playwright E2E with Calculator/Interviewing/Gate driven through a UI surface.

### Gap 2 — R.5 Journey 7/8/9 were HTTP + pytest, not browser workflows

R.5 inspection.md files state:

- `journey_07_clone_preset/inspection.md`: "URL: POST http://127.0.0.1:8000/api/v1/agents/quick?from_preset=icoder-cdi-preset" — curl call, not browser click
- `journey_08_context_delete/inspection.md`: "11 R.1.b 测试覆盖 destroy_now 全路径" — pytest execution, not UI delete button
- `journey_09_cross_tenant_reject/inspection.md`: "6 cross-tenant + control tests in test_a1b_ae_r_1_b_context_scrub_cross_tenant.py" — pytest, not real Tenant B login in browser

### Gap 3 — R.5 Journey 10 was source inspection + localStorage function existence check

`journey_10_logout_cleanup/inspection.md` cites `frontend/src/store/index.ts:81-90` logout function and lists 10 keys, but did NOT run a browser to verify the sweep actually fires on a real click. Charter §20 item 6: "静态源码检查不是浏览器存储运行验证."

### Gap 4 — R.6 "full backend" was actually `pytest tests/test_api/`, not `pytest tests/`

R.6 report `A1B_AE_R_6_FINAL_RECONCILIATION.md` section "Full backend suite (broader than baseline)":
> Command: `python -m pytest tests/test_api/ --tb=line -q`
> **Result**: `4 failed, 1062 passed, 97 warnings, 27 errors in 303.31s`

This is `API_TEST_SUITE` (per RV §7.4 terminology), NOT `BACKEND_ALL_TESTS` (`pytest tests/`). The terminology drift overstates coverage. RV.1 / RV.6 will run both commands separately and label them accurately.

### Gap 5 — 4 failed + 27 errors not proven pre-existing by baseline node-ID diff

R.6 report asserts these failures "predate A1B-AE-R (`f6bbd60` Phase A1A Gate 1)" based on **file creation date**. Per RV §20 item 8: "测试文件历史早,不代表失败 pre-existing." The correct proof is **same node-ID with same failure signature at baseline `85a5c9a`**, which has not been established. RV.1 §7.3 will run the specific failing node-IDs against `85a5c9a` and only label `PRE_EXISTING_SAME` if baseline produces identical failure.

### Gap 6 — PubMed / ClinicalTrials live capture not recorded

R.3.a "live" evidence is VCR fixtures under `evidence/api_captures/`. Per RV §20 item 9: "VCR replay 不等于 live connectivity." RV.4 must produce one recorded live exchange per upstream with sanitized response, SHA-256, timestamp, query hash, and egress audit.

### Gap 7 — Intake Preset type may be mislabelled

R.2 reports set `delegates_to_pack` on 4 stubs. RV must verify whether all 5 presets are truly Pack-backed or whether one (Intake / Research) is actually Expert-backed. Per §20 item 14: "Expert-backed Preset 不得写成 Pack-backed."

### Gap 8 — Legacy underscore dirs may be retained, not deleted

R.2.b claims deletion of `code_validation` / `compliance_guardrail` / `note_completeness` underscore dirs. RV must verify these are truly gone or marked retained (alias / re-export). Per §20 item 13: "Retained legacy implementation 不得写成 deleted."

### Gap 9 — Context scrub coverage incomplete

R.1.b implemented `destroy_now()` for direct-child tables (`contexts` / `context_messages` / `context_task_refs` / `context_artifact_refs` / `original_input_audit`). It did NOT prove scrub of:
- `ConversationMemory` rows (Phase 5 Track D Memory Expert)
- Vector / embedding records (sentence-transformers cache)
- MCP temporary auth state
- External Expert cached result
- Run trace references
- Audit metadata that may contain original input

Per §20 item 11: "删除 Context 直接子表不等于全部 Memory 已清除." RV.3 §9.1 will machine-generate the dependency graph; §9.2 will scrub a synthetic Context with marker `SYNTHETIC_CONTEXT_SCRUB_MARKER_<UUID>` and scan all tables.

### Gap 10 — Migration 024/025 upgrade path not multi-scenario verified

R.6 incidentally needed to reseed dev DB after a partial migration. This proves Migration 024 (`CREATE TABLE IF NOT EXISTS` style) can mask "table exists but schema incomplete" failure mode. RV.2 §8.2 must verify 10 scenarios (A-J) including partial-schema, interrupted-upgrade recovery, downgrade/upgrade loop, PostgreSQL parity.

### Gap 11 — Dev DB migration accident not in formal evidence ledger

The R.6 dev DB reseed (`mv data/icoder.db data/icoder.db.bak && alembic upgrade head && python -m app.seed`) is documented in `A1B_AE_R_6_FINAL_RECONCILIATION.md` prose but was NOT recorded in evidence ledger with before/after schema snapshots, query counters, or marker scans. RV.2 §8.1 will add a dev-DB guard that fails loudly when test/audit contexts target `backend/data/icoder.db`.

### Gap 12 — organization_id may have permanent `org_default1` server_default

Migration 025 may have introduced a permanent server_default `org_default1` on `contexts.organization_id`. Per §20 item 12: "永久 org_default1 默认不属于 fail-closed." Historical backfill may use explicit one-time default, but new writes must fail-closed when `organization_id` is missing. RV.2 §8.3 will audit ORM default, Pydantic default, migration server_default, backfill default, and production write paths.

## Engineering preservation

Per §一 of the execution prompt:

> 本阶段不否定 A1B-AE-R 已经完成的工程实现。Task、ThreadAuth、Context、Preset Clone、SSRF、Public Expert Adapter、Calculator、Memory、Interviewing 和前端代码可以保留。

RV does NOT delete or rewrite R.1..R.5 code. RV only:
- Adds evidence (journey specs, JUnit, captures, screenshots, traces)
- Adds guards (dev DB protection, org fail-closed)
- Fixes factual errors in prior reports (via new correction files, NOT rewriting R.* reports)
- May add minimum UI/API surface needed for headed-browser journeys (e.g. Calculator REST endpoint if Calculator has no HTTP route)
- May add a fix-forward migration (026+) for Migration 024 partial-schema issue

## Allowed modifications (§五)

1. Minimum UI/API for real headed-browser journeys
2. Fix Context scrub for tables not yet covered
3. Fix Migration 024/025 verified upgrade safety issues
4. Remove permanent `org_default1` default from production path
5. Fix test access to dev DB
6. Fix test evidence tooling (JUnit, node-ID diff)
7. Fix real new regressions
8. Fix factual errors in prior reports
9. One approved synthetic live capture for PubMed / ClinicalTrials
10. Add formal Playwright E2E scripts for browser Journeys

## Forbidden scope creep (§五)

- NO new Corti Expert
- NO new Preset Agent
- NO new clinical calculator
- NO Web Search
- NO DrugBank / POSOS integration
- NO clinical prompt changes
- NO Corti parity expansion

## Forbidden verdicts (§十八) — 10 items

`PRODUCTION_READY` / `FULLY_VERIFIED` / `PHI_BOUNDED` / `CORTI_PARITY_VERIFIED` / `PASS_A1A_GATE4_FINAL` / `READY_FOR_HOSPITAL_DEPLOYMENT` / `CLINICAL_GRADE_VERIFIED` / `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED` / `CORTI_AGENTIC_PARITY_VERIFIED` / `READY_FOR_MVP_SHIP`.

## What this notice does NOT do

- Does NOT modify R.0..R.6 reports (they are frozen evidence)
- Does NOT amend `8546184` or any predecessor
- Does NOT delete or rewrite any A1B-AE-R tag
- Does NOT push, PR, deploy, or touch master / origin
- Does NOT issue FRAUD / INVALID / FAILED labels against prior work

## Next: RV.1

RV.1 establishes the exact regression baseline by running `pytest --collect-only` at three HEADs (`85a5c9a` baseline, `8546184` prior terminal, RV HEAD repair), then executes the common-node population at each, producing node-ID diff and state-transition matrix. RV.1 §7.3 attributes the 4 failed + 27 errored tests to either `PRE_EXISTING_SAME` (baseline produces identical failure on same node) or `NEW_*/CHANGED_*` (RV must fix).
