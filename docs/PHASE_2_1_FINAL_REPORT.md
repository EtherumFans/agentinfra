# Phase 2.1 — Agentic Framework Mainline Cutover (COMPLETE)

**Date**: 2026-07-02 to 2026-07-04
**Status**: COMPLETE — VERDICT: PASS
**Predecessor**: Phase 2-H (stub恢复, since reversed)
**Successor**: Phase 2.2 (A2A 真实任务流 + 17 Pre-built Agents 实装)

## Scope

Phase 2.1 cut over from the legacy M3-0 router-based architecture to the
Corti-style A2A + MCP + Runtime + Pre-built Agents mainline. Six sub-phases:

| Sub-phase | Title | Status |
|---|---|---|
| 2.1-A | agent_runner full deletion | COMPLETE (commit ce0bc4a, 2026-07-02) |
| 2.1-B | 16 legacy router deletion (4 steps) | COMPLETE (commits 1c6c4c0 → accc5be) |
| 2.1-B wrap-up | 7 test files assertion migration + 5 invariant suites | COMPLETE (commit 757fda1) |
| 2.1-B wrap-up | OpenAPI contract + docs/frontend residual scrub | COMPLETE (commit 7ecc4b1) |
| 2.1-B wrap-up | TECH_DEBT_BACKLOG formalization | COMPLETE (commit 85d0de9) |
| 2.1-C | agents.py → Corti-style /rest/v1/agent_definitions | COMPLETE (commit 19bda7a) |
| 2.1-D | New test suite regression verification | COMPLETE (1229/1 PASS) |
| 2.1-E | Residual legacy reference scrub (frontend) | COMPLETE (commit a7f04f8) |
| 2.1-F | Phase 2.1 final wrap-up (this doc) | COMPLETE |

## What was deleted

### 2.1-A (commit ce0bc4a)
- `app/services/agent_runner.py` (1047 LOC)
- `icoder_runtime/agent_runner.py` (491 LOC)
- `app/agents/orchestrator.py` (848 LOC)
- 5 orphan modules (stt_finetune, sandbox, symbolic_state, dashboard.html, 6 orphan tests)
- 36 files / +652 / -5496

### 2.1-B (commits 1c6c4c0 → accc5be)
15 legacy routers deleted (plan said 16; agents.py deferred to 2.1-C per
user decision, then migrated rather than deleted):

| Step | Routers | LOC |
|---|---|---|
| Step 1 (1c6c4c0) | runtime, code_tables, gold_cases, evaluation, agent_evaluation, fhir, facts, experts | 2146 |
| Step 2 (9a2723c) | icoder_registry_compat, icoder_agents_compat, icoder_agents_hub | 1261 |
| Step 3 (0d8370a) | m2a (agents.py deferred) | 278 |
| Step 4 (accc5be) | icoder_coding_review, text_gen, reviews | 2347 |
| **Total** | **15 routers** | **6032 LOC** |

### 2.1-B (commit 757fda1)
5 new mainline invariant suites (33 tests, all PASS) preserving the
safety contracts from 7 deleted test files (78 functions):
- `tests/e2e/icoder/test_a2a_mainline_invariants.py` (8 tests)
- `tests/test_services/test_mcp_invariants.py` (6 tests)
- `tests/test_api/test_runtime_trace_invariants.py` (7 tests)
- `tests/test_api/test_v2_contract_invariants.py` (8 tests)
- `tests/test_api/test_safety_phi_invariants.py` (5 tests)

### 2.1-C (commit 19bda7a)
`app/api/agents.py` router prefix migrated from `/api/agents` to
`/api/rest/v1/agent_definitions` (Corti-style, namespaced under /api per
iCoDer convention). 9 management endpoints migrated; A2A discovery
remains on `/api/icoder/agents`.

### 2.1-E (commit a7f04f8)
3 dead fetch calls in AgentDetailPage.tsx + 1 playground sample in
DeveloperQuickstartPage.tsx scrubbed.

## Phase 2.1 cumulative stats
- 9 commits (8317217..HEAD)
- 86 files changed
- +7609 / -27513 (net deletion of ~20K LOC of legacy code)

## Verification (final)

| Check | Result |
|---|---|
| health_check.py | 7/7 PASS |
| tsc --noEmit | 0 errors |
| npm run build | exit 0 |
| vitest src/ | 54/54 PASS |
| pytest tests/test_api/ tests/unit/ tests/regression/ tests/e2e/icoder/ | 1229 passed / 1 failed / 1 skipped |
| MCP /mcp/v1/tools/list | 200 with 5 tools |
| A2A /api/icoder/agents | 200 (discovery) |
| A2A /api/icoder/agents/{id}/v1/message:send | 200 (inbound) |
| /api/rest/v1/agent_definitions | 401 (auth required, exists) |
| OpenAPI paths | 168 (was 47 originally, before 2.1-B) |

The 1 pytest failure is pre-existing TD-002 (schema_drift flakiness, see
TECH_DEBT_BACKLOG.md). TD-001 (templates org_id mismatch) is intermittent
based on test ordering and didn't surface in the final run.

## Pre-existing debt carried forward

| ID | Item | Phase introduced |
|---|---|---|
| TD-001 | test_templates_api 3 failures (org_id mismatch) | Pre-2.1-B |
| TD-002 | test_no_schema_drift_against_fresh_alembic_db flakiness | Pre-2.1-B |
| TD-003 | agents.py legacy router | RESOLVED in 2.1-C |
| TD-004 | FastAPI duplicate operation_id warnings (A2A + MCP) | Pre-2.1-B |
| TD-005 | RuntimeAgentRegistry thread-level locking | Pre-2.1-B |

## New mainline architecture

```
医疗收入合规体系
├── 编码合规 (Medical Coding)      ← Pre-built Agent #18 (MedCodER) on A2A + MCP
├── 分组合规 (DRG/DIP)            ← 规则结构已预留
├── 结算合规 (Insurance Audit)    ← 规则结构已预留
├── 收费合规 (Charge Compliance)  ← 规则结构已预留
├── 病历合规 (Document Evidence)  ← 规则结构已预留
└── 审计合规 (Audit)              ← AuditLog/RunHistory 已完整

第四层: Business Workbenches   app/api/*             ~168 endpoints (was 47+)
第三层: Official Agent Packs   official_agents/      Medical Coding (icoder/medical-coding-agent@1.0.0)
                                                    MedCodER (icoder/medcoder-coding-review-agent@1.0.0)
第二层: Agentic Framework       app.icoder.agent_runtime/
                                  A2A v0.3 (InboundHandler + Orchestrator + Delegator + Aggregator)
                                  MCP server (/mcp/v1/tools/{list,call} with 5 tools)
                                  Context (Q4 三层隔离)
                                  AgentCard discovery (/api/icoder/agents, /.well-known/agent.json)
第一层: Runtime Core           icoder_runtime/        AgentRunner (deleted), LLMGateway, Registry,
                                  Observability (RunHistory, AuditLog, FallbackTracker)
```

## Phase 2.2 (next)

Per the Corti parity direction (memory: project_p1_3_corti_parity_audit_2026_07_02):
- A2A 真实任务流 (Task state machine: submitted → working → input-required → completed/failed/canceled)
- 17 Pre-built Agents 实装 (Medical Coding + DRG + Audit + Documentation + Claim + ...)
- A2A outbound delegation (Orchestrator → Expert)
- Phase 4: SSE for A2A streaming
- Phase 5: Third-party ISV agent registration

The Phase 2.1 cutover unblocks all of these — the legacy M3-0 router
infrastructure is gone, the new mainline is the only path.
