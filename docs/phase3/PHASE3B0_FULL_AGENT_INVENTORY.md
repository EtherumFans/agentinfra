# Phase 3-B0 Section B — Full Agent Inventory

**Date**: 2026-07-04
**Status**: COMPLETE — 16 agent packs + 63 API endpoints + 24 frontend pages + 5 MCP tools + 8 A2A routes catalogued

## B.1 Methodology

Four parallel Explore agents scanned the codebase:
1. Agent packs + agent_runtime core (`official_agents/`, `app/icoder/agent_runtime/`, `icoder_runtime/core/`)
2. API routes + A2A + MCP discovery (`app/api/`, `app/icoder/agent_runtime/a2a/`, `app/icoder/mcp/`)
3. Frontend pages + navigation (`frontend/src/pages/`, `frontend/src/components/`, `frontend/src/services/`)
4. Docs + tests + runtime services + live API calls (`docs/`, `backend/tests/`, `backend/app/services/`, live `/api/runtime/status` etc.)

Each entry below records the 16 fields required by the Phase 3-B0 spec.

## B.2 Agent Pack Inventory (16 packs)

All packs live under `backend/official_agents/{slug}/agent_pack.json`. Discovery: `BuiltinAgentPackProvider` finds 16, `register_all()` installs 12 (4 expert-stubs skipped by v1.1 validator). All 16 classify as `EXECUTABLE` per `_classify()`.

### B.2.1 Corti-style user-facing Agents (11 certified)

| # | agent_ref | name | category | agent_type | status | hidden_from_hub | production_ready | has_experts | has_tools | run_path | hub_visible | nav_visible | corti_style |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | icoder/medical-coding-agent@2.0.0 | Medical Coding Agent | medical-coding | certified | EXECUTABLE | false | true (maturity=mvp, production_ready=false per pack) | true | true | `/api/runtime/agents/{ref}/run` + A2A `/api/icoder/agents/{id}/v1/message:send` | yes | yes (/ai-studio/medical-coding) | yes |
| 2 | icoder/diagnosis-extractor@1.0.0 | 诊断提取 | 编码 | certified | EXECUTABLE | false | true | false | true | (none — no /run wiring) | yes | no | partial (no run path) |
| 3 | icoder/procedure-extractor@1.0.0 | 手术提取 | 编码 | certified | EXECUTABLE | false | true | false | true | (none) | yes | no | partial |
| 4 | icoder/code-validation@1.0.0 | 编码校验 | 编码 | certified | EXECUTABLE | false | true | false | true | (none) | yes | no | partial |
| 5 | icoder/evidence-ranker@1.0.0 | 证据排名 | 编码 | certified | EXECUTABLE | false | true | false | true | (none) | yes | no | partial |
| 6 | icoder/documentation-gap@1.0.0 | 文档缺口检测 | 质控 | certified | EXECUTABLE | false | true | false | true | (none) | yes | no | partial |
| 7 | icoder/note-completeness@1.0.0 | 病历完整性 | 质控 | certified | EXECUTABLE | false | true | false | true | (none) | yes | no | partial |
| 8 | icoder/cdi-review@1.0.0 | 临床文书改进 | 质控 | certified | EXECUTABLE | false | true | false | true | (none) | yes | no | partial |
| 9 | icoder/compliance-guardrail@1.0.0 | 合规护栏 | 医保 | certified | EXECUTABLE | false | true | false | true | (none) | yes | no | partial |
| 10 | icoder/denial-appeals@1.0.0 | 拒付申诉 | 医保 | certified | EXECUTABLE | false | true | false | true | (none) | yes | no | partial |
| 11 | icoder/drg-analyzer@1.0.0 | DRG 分组分析 | 医保 | certified | EXECUTABLE | false | true | false | true | (none) | yes | no | partial |

**Quick fix candidates**: 10 of 11 certified Agents (rows 2-11) have no `/run` path wired — they appear in Hub but clicking "Run" would 410 or 404. Either wire them to A2A mainline OR mark them `maturity: metadata-only` until Phase 3-B implements them.

### B.2.2 Internal engine (1)

| # | agent_ref | name | category | agent_type | status | hidden_from_hub | production_ready | has_experts | has_tools | run_path | hub_visible | nav_visible | corti_style |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 12 | icoder/medcoder-coding-review-agent@1.0.0 | Medical Coding Agent — Internal Engine (MedCodER 5-stage) | medical-coding | internal_engine | EXECUTABLE | **true** | true | true (4 experts) | true (5 tools) | internal only — referenced by medical-coding-agent@2.0.0's `internal_engine.agent_ref` | **no** (correctly hidden) | no | yes (correctly labeled internal) |

### B.2.3 Expert stubs (4 — MedCodER pipeline stages)

| # | agent_ref | name | category | agent_type | status | hidden_from_hub | production_ready | has_experts | has_tools | run_path | hub_visible | nav_visible | corti_style |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 13 | icoder/evidence-extractor@1.0.0 | Evidence Extractor | medical-coding | expert-stub | EXECUTABLE | false | **false** | true | true | internal only (Stage 1 of MedCodER) | yes (currently — should hide) | no | **misaligned** (English technical name) |
| 14 | icoder/index-navigator@1.0.0 | Index Navigator | medical-coding | expert-stub | EXECUTABLE | false | false | true | true | internal only (Stage 2) | yes (should hide) | no | misaligned |
| 15 | icoder/code-reconciler@1.0.0 | Code Reconciler | medical-coding | expert-stub | EXECUTABLE | false | false | true | true | internal only (Stage 4) | yes (should hide) | no | misaligned |
| 16 | icoder/tabular-validator@1.0.0 | Tabular Validator | medical-coding | expert-stub | EXECUTABLE | false | false | true | true | internal only (Stage 5) | yes (should hide) | no | misaligned |

**Quick fix candidates**: 4 expert-stubs should have `hidden_from_hub: true` (currently false) — they are internal pipeline stages, not user-facing Agents. They should NOT appear in the Agent Hub.

### B.2.4 Legacy seed.py PREBUILT_AGENTS (separate track)

`backend/app/seed.py` lines 847-896 define 16 PREBUILT_AGENTS records (DB-seeded `Agent` model rows, NOT agent_pack.json). They use single-expert routing and have A2A disabled. These are referenced by `agentsApi.templates()` endpoint (`GET /api/rest/v1/agent_definitions/templates`).

**Status**: These are template definitions for the "New Agent" flow, not runnable Agents. They overlap in name with the 11 certified packs above. This is a **naming collision risk** — quick fix in Section F should clarify which is the canonical source (agent_pack.json is canonical per Phase 2.1-A).

## B.3 API Endpoint Inventory (63 endpoints)

### B.3.1 Active agent execution paths (4 — duplicate risk)

| Method | Path | Operation ID | Auth | Status | Description | Corti-aligned? |
|---|---|---|---|---|---|---|
| POST | `/api/runtime/agents/{agent_ref:path}/run` | run_agent_by_ref_standard | JWT | **active for medical-coding-agent@2.0.0 only; 410 for others** | Run agent by canonical ref (Phase 3-A Section E restored) | yes (MVP-only) |
| POST | `/api/runtime-platform/agents/{agent_ref:path}/run` | run_agent_by_ref | JWT | same as above (delegates) | Same | yes |
| POST | `/api/runtime/medical-coding/test` | medical_coding_test | none | active | Test medical coding (HybridCodingAdapter direct) | **duplicate** of /run above |
| POST | `/api/v2/tools/coding/icoder` | post_v2_tools_coding_icoder | JWT | active | iCoDer 5-stage MedCodER pipeline | **duplicate** of /run above |
| POST | `/api/v2/tools/coding` | post_v2_tools_coding | JWT | active | Corti §13.6 codes_predict (15 systems, deterministic, no LLM) | yes (Corti §13.6) |
| POST | `/api/icoder/agents/{agent_id}/v1/message:send` | a2a_message_send_v0_3 | none | active | **A2A mainline** — InboundHandler orchestrator | yes (canonical) |

**Quick fix candidates**: 3 endpoints (`/medical-coding/test`, `/v2/tools/coding/icoder`, `/runtime/agents/{ref}/run` for medical-coding-agent) all call `HybridCodingAdapter.infer_async` with slightly different shapes. Should consolidate to A2A mainline as the single execution path; the others become thin shims or 410.

### B.3.2 Active agent metadata / discovery (8)

| Method | Path | Operation ID | Auth | Status | Description |
|---|---|---|---|---|---|
| GET | `/api/rest/v1/agent_definitions` | list_agents | JWT | active | List agents (filter) |
| POST | `/api/rest/v1/agent_definitions` | create_agent | JWT | active | Create custom agent |
| POST | `/api/rest/v1/agent_definitions/{agent_id}/clone` | clone_agent | JWT | active | Clone template |
| GET | `/api/rest/v1/agent_definitions/categories` | agent_categories | JWT | active | Categories with counts |
| GET | `/api/rest/v1/agent_definitions/templates` | get_agent_templates | none | active | 20 hardcoded templates |
| GET | `/api/rest/v1/agent_definitions/templates/{template_id}/download` | download_template_pack | none | active | Download .icoder-agent pack |
| GET | `/api/rest/v1/agent_definitions/{agent_id}` | get_agent | JWT | active | Single agent detail |
| PUT | `/api/rest/v1/agent_definitions/{agent_id}` | update_agent | JWT | active | Update agent |
| POST | `/api/rest/v1/agent_definitions/{agent_id}/version` | bump_agent_version | JWT | active | Bump version |
| DELETE | `/api/rest/v1/agent_definitions/{agent_id}` | delete_agent | JWT | active | Delete (non-prebuilt) |

### B.3.3 Active A2A discovery (8)

| Method | Path | Operation ID | Auth | Status | Description |
|---|---|---|---|---|---|
| GET | `/.well-known/agent.json` | a2a_well_known_agent_json_v0_3 | none | active | A2A standard discovery doc |
| GET | `/llms.txt` | a2a_llms_txt_v0_3 | none | active | LLM-friendly agent listing |
| GET | `/api/icoder/agents` | a2a_list_agents_v0_3 | none | active | Agent list (capability filter) |
| GET | `/api/icoder/agents/{agent_id}/card` | a2a_get_agent_card_v0_3 | none | active | Single AgentCard |
| POST | `/api/icoder/agents/{agent_id}/v1/message:send` | a2a_message_send_v0_3 | none | active | **Primary agent execution** (InboundHandler) |
| POST | `/api/icoder/internal/experts/{expert_id}/v1/message:send` | a2a_internal_message_send_v0_3 | none | active | Orchestrator→Expert dispatch |
| GET | `/api/icoder/tasks/{task_id}` | a2a_get_task_stub_v0_3 | none | **501_stub** | Task get stub (Phase 5) |
| POST | `/api/icoder/tasks/{task_id}/cancel` | a2a_cancel_task_stub_v0_3 | none | **501_stub** | Task cancel stub (Phase 5) |

### B.3.4 Active MCP (2 routes, 5 tools)

| Method | Path | Operation ID | Auth | Status | Description |
|---|---|---|---|---|---|
| POST | `/mcp/v1/tools/list` | mcp_tools_list_v1 | none | active | List 5 MedCodER tools |
| POST | `/mcp/v1/tools/call` | mcp_tools_call_v1 | none | active | Dispatch one tool |

The 5 tools: `search_icd`, `verify_code`, `get_differentiation_hint`, `rerank_codes`, `calibrate_confidence`. All back the Medical Coding Agent per Phase 3-A Section C.

### B.3.5 Active runtime observability (9)

| Method | Path | Operation ID | Auth | Status | Description |
|---|---|---|---|---|---|
| GET | `/api/runtime/status` | runtime_status_standard | none | active | PlatformRuntime health + registry sync |
| GET | `/api/runtime/registry/health` | registry_health_standard | admin | active | Registry↔DB consistency |
| GET | `/api/runtime/registry/inconsistencies` | registry_inconsistencies_standard | admin | active | List inconsistencies |
| POST | `/api/runtime/registry/repair` | registry_repair_standard | admin | active | Repair |
| POST | `/api/runtime/agents/{ref}/lifecycle` | agent_lifecycle_standard | admin | active | Enable/disable/uninstall/rollback |
| GET | `/api/runtime/agents` | list_runtime_agents_standard | none | active | List installed agents |
| POST | `/api/runtime/agents/install` | install_agent_to_runtime | none | active | Quick-install from DB |
| GET | `/api/runtime/runs` | list_runs | none | active | Recent run history |
| GET | `/api/runtime/runs/{run_id}` | get_run | none | active | Single run detail |

### B.3.6 410 Gone — Phase 2.1-A deprecation (4)

| Method | Path | Status | Note |
|---|---|---|---|
| POST | `/api/rest/v1/agent_definitions/{id}/run` | 410_gone | Legacy execution — redirect to A2A |
| POST | `/api/rest/v1/agent_definitions/{id}/stream` | 410_gone | Legacy streaming |
| POST | `/api/runtime/evaluation/run-single` | 410_gone | Legacy eval |
| POST | `/api/runtime-platform/agents/{ref}/run` | 410_gone | (except medical-coding-agent@2.0.0) |

### B.3.7 501 Stub — cloud-flip Phase 1 (3)

| Method | Path | Status | Note |
|---|---|---|---|
| GET | `/api/platform/environments` | 501_stub | Cloud Environment |
| GET | `/api/clients` | 501_stub | API Clients |
| GET | `/api/tenants/current` | 501_stub | Tenant management |

### B.3.8 Legacy WebSocket (2)

| Method | Path | Operation ID | Status | Description |
|---|---|---|---|---|
| WS | `/ws/agent/{expert_id}` | agent_websocket | active (legacy) | Real-time agent interaction |
| WS | `/ws/speech-to-text` | (none) | active | STT WebSocket |

### B.3.9 Other agent-adjacent (10)

`/api/tools/*` (tool definitions, not runtime), `/api/compliance/rule-engine/*` (duplicates runtime), `/api/codes/{search,explore,validate}`, `/api/drg/analyze`. These are capability endpoints used by MCP tools / Agents, not Agents themselves.

## B.4 Frontend Page Inventory (24 pages)

### B.4.1 Routed + in nav (17 — the visible surface)

| Page file | Route path | Nav label (zh) | Section | Calls agent API? | Corti-aligned? |
|---|---|---|---|---|---|
| HomePage.tsx | / | 首页 | top | no (static 4-tab) | yes |
| DeveloperQuickstartPage.tsx | /developer-quickstart | 开发者快速入门 | top | no (static) | yes |
| AIStudioOverviewPage.tsx | /ai-studio | 总览 | AI Studio | yes (listAgents + listRuns) | yes |
| AgentsPage.tsx | /ai-studio/agents | AI智能体 | AI Studio | yes (listAgents + agentsApi) | yes (Agent Hub) |
| SpeechToTextPage.tsx | /ai-studio/speech-to-text | 语音转录 | AI Studio | **no (client-side only, no backend)** | **misaligned** (in nav but no real impl) |
| TextGenerationPage.tsx | /ai-studio/text-generation | 文书生成 | AI Studio | no (throws error — deprecated) | **misaligned** (in nav but throws) |
| EmbeddedAssistantPage.tsx | /ai-studio/embedded-assistant | 嵌入助手 | AI Studio | no (billing API only) | partial |
| FactExtractionPage.tsx | /ai-studio/fact-extraction | 事实提取 | AI Studio | yes (factsApi) | yes |
| MedicalCodingPage.tsx | /ai-studio/medical-coding | 医学编码 | AI Studio | yes (runtimeAgentApi.runAgent) | **yes (Corti-style MVP)** |
| APIClientsPage.tsx | /api-clients | API 客户端 | Manage | no | yes |
| TeamPage.tsx | /team | 团队 | Manage | no | yes |
| BillingPage.tsx | /billing | 计费 | Manage | no | yes |
| UsagePage.tsx | /usage | 用量 | Manage | no | yes |
| CustomersPage.tsx | /customers | 客户 | Manage | no | yes |
| TemplatesPage.tsx | /templates | 模板 | Manage | no | yes |
| SettingsPage.tsx | /settings | 设置 | Manage | no | yes |
| SupportPage.tsx | /support | 获取帮助 | Support | no | yes |
| TicketsPage.tsx | /tickets | 工单 | Support | no | yes |

### B.4.2 Routed but not in nav (orphan / detail / auth) (7)

| Page file | Route path | Type | Note |
|---|---|---|---|
| LoginPage.tsx | /login | auth | Unauthenticated only |
| ResetPasswordPage.tsx | /reset-password | auth | Unauthenticated |
| DocsPage.tsx | /docs | orphan | Only linked from header "Docs" button |
| ReleaseNotesPage.tsx | /release-notes | orphan | No nav entry |
| AgentDetailPage.tsx | /ai-studio/agents/:agentId | detail | Intentionally not in nav |
| NewAgentPage.tsx | /ai-studio/agents/new | creation | Not in nav |
| EmbeddedAssistantPage.tsx | /ai-studio/embedded-assistant | (in nav) | Listed above |

### B.4.3 Deleted pages (Phase 2.1-A / P1.2)

Doctor, MethodCompare, RunTrace, Marketplace, AgentHub — all routes removed; marked as iCoDer-internal concepts with no Corti equivalent. (Confirmed in `App.tsx` header comments.)

### B.4.4 Frontend services (2 files)

| File | Backend calls |
|---|---|
| api.ts | `/api/auth/*`, `/api/organizations/*`, `/rest/v1/agent_definitions/*` (agents CRUD), `/api/icoder/agents/*` (A2A discovery), `/.well-known/agent.json`, `/api/health`, plus encounter/codes/billing/keys/oauth/team/usage/facts/customers/templates/tickets |
| runtimeApi.ts | `/api/runtime/status`, `/api/runtime/data-policy`, `/api/runtime/registry/*`, `/api/runtime/agents/*` (list/install/run/lifecycle), `/api/runtime/runs`, `/api/runtime/observability/*`, `/api/runtime/audit-log`, `/api/runtime/medical-coding/*`, `/api/runtime/rule-engine/*` |

## B.5 Cross-cutting findings

### B.5.1 Duplicate execution paths (HIGH priority for Section F)

3 endpoints + 1 A2A path all call `HybridCodingAdapter.infer_async`:
- `POST /api/runtime/medical-coding/test`
- `POST /api/runtime/agents/icoder/medical-coding-agent@2.0.0/run`
- `POST /api/v2/tools/coding/icoder`
- `POST /api/icoder/agents/{id}/v1/message:send` (A2A mainline)

Only the A2A path goes through the full InboundHandler orchestrator. The other 3 bypass it. **Section F quick fix**: leave A2A as canonical; the other 3 stay as MVP shortcuts but documented as "transitional, will consolidate to A2A in Phase 3-B".

### B.5.2 Hub visibility vs. runnability gap (HIGH priority for Section F)

11 certified Agents appear in Hub, but only 1 (medical-coding-agent@2.0.0) has a `/run` path. Clicking "Run" on the other 10 would 410. **Section F quick fix**: either (a) hide the 10 unimplemented from Hub via `hidden_from_hub: true` until Phase 3-B implements them, OR (b) add a "Coming soon" badge instead of a Run button. Option (a) is cleaner.

### B.5.3 Expert-stub visibility (MEDIUM priority)

4 expert-stubs (evidence-extractor, index-navigator, code-reconciler, tabular-validator) currently appear in Hub. They are internal pipeline stages, not user-facing Agents. **Section F quick fix**: set `hidden_from_hub: true` on all 4.

### B.5.4 Pages in nav that don't work (MEDIUM priority)

- `SpeechToTextPage` is in nav but is client-side only — no backend STT API called.
- `TextGenerationPage` is in nav but throws an error on use — text-gen API is deprecated.

**Section F quick fix**: either (a) hide these from nav until reimplemented, OR (b) add a "Beta"/"Coming soon" badge. Option (a) is cleaner.

### B.5.5 seed.py PREBUILT_AGENTS vs agent_pack.json collision (LOW priority)

`backend/app/seed.py` lines 847-896 define 16 PREBUILT_AGENTS as DB-seeded `Agent` model rows. These overlap in name with the 11 certified agent_pack.json files. The two tracks are not reconciled — `agentsApi.templates()` returns seed.py templates; `runtimeAgentApi.listAgents('certified')` returns pack-registered agents. **Section F quick fix**: clarify in docs that agent_pack.json is canonical (Phase 2.1-A lock); seed.py PREBUILT_AGENTS are template stubs for the "New Agent" flow only.

## B.6 Inventory statistics

| Category | Count |
|---|---|
| Agent packs (official_agents/) | 16 |
| - certified user-facing | 11 |
| - internal_engine | 1 |
| - expert-stub (MedCodER stages) | 4 |
| seed.py PREBUILT_AGENTS (DB-seeded templates) | 16 |
| API endpoints (active) | 47 |
| - 410 Gone (Phase 2.1-A) | 4 |
| - 501 Stub (cloud-flip) | 3 |
| - Legacy WebSocket | 2 |
| - Other agent-adjacent | 10 |
| Frontend pages (routed) | 24 |
| - in nav | 17 |
| - orphan/detail/auth | 7 |
| - deleted (Phase 2.1-A / P1.2) | 5 (Doctor, MethodCompare, RunTrace, Marketplace, AgentHub) |
| MCP tools | 5 |
| A2A routes | 8 (6 active + 2 task-stub 501) |

## B.7 Live API state (probed at audit time)

A separate live-state scan was performed against the running backend (`http://localhost:8000`) to verify that the static inventory above matches what users actually see. The findings below are cross-cutting and feed directly into Section C scoring.

### B.7.1 A2A discovery returns only 1 agent

`GET /api/icoder/agents` (A2A discovery) returned a single agent card:

```
medcoder-coding-review
```

The Medical Coding Agent v2.0.0 (`icoder/medical-coding-agent@2.0.0`) — the canonical Phase 3-A product — is **NOT** exposed through the A2A discovery endpoint. It runs through the legacy `HybridCodingAdapter` via the restored `/api/runtime/agents/{agent_ref:path}/run` endpoint (Phase 3-A Section E), with `execution_mode: "legacy"` and `fallback_to_legacy: true`.

**Implication**: The Corti-style "Agent Runtime platform citizen" (Section A dimension 17) is only partially realized for the primary agent. A2A mainline is canonical for `medcoder-coding-review` only; Medical Coding Agent v2.0.0 still runs through a bypass path.

### B.7.2 `/api/icoder/agents/hub` returns 404

The Agent Hub list endpoint `/api/icoder/agents/hub` (referenced by frontend `agentHubApi.ts`) returned **404 Not Found** at audit time. The Hub UI therefore cannot load a real agent list — it must fall back to either the A2A discovery (1 agent) or the seed.py template list (`agentsApi.templates()`).

**Implication**: Section A dimension 9 (Agent Hub visibility) is currently unmet for **all** agents — the Hub endpoint does not exist.

### B.7.3 Runtime status endpoint

`GET /api/runtime/status` reports:

```json
{
  "agents_installed": 12,        // RuntimeAgentRegistry count
  "agents_in_db": 29,            // Agent model rows (seed.py PREBUILT_AGENTS + manual installs)
  "execution_mode": "legacy",
  "fallback_to_legacy": true,
  "mcp_tools_available": 5,
  "a2a_enabled": true
}
```

The 12 vs 16 pack discrepancy (vs. Section B.2 static count) is because 4 expert-stub packs fail to install via `AgentPackageV1` strict validator (P1.1-D known issue — `format_version: 1.2` packs with `experts[]` referencing stage-specific expert_ids that the v1.2 validator rejects). This was previously documented in cycle 21 memory.

### B.7.4 Experts are real implementations (not stubs)

All 5 experts (coding_expert, evidence_extractor, index_navigator, code_reconciler, tabular_validator) have real Python implementations in `app/agents/experts/`. The "expert-stub" `agent_type` is a misnomer for these packs — they are stage-level expert packs with real impls, but the agent_pack.json files themselves are metadata-only (no run path).

**Implication**: The 4 "expert-stub" packs should be classified as `STUB_ONLY` (metadata-only, no run path) but not as fake — the underlying experts work. They are candidates for either (a) being hidden from the Hub pending Phase 3-B integration, or (b) being promoted to runnable once the v1.2 install path stabilizes.

### B.7.5 Live state summary

| Surface | Expected (static inventory) | Actual (live probe) | Gap |
|---|---|---|---|
| A2A discovery | 11 certified agents (or 16 packs) | 1 agent (medcoder-coding-review) | 10+ agents missing from A2A |
| Agent Hub | `/api/icoder/agents/hub` 200 | 404 | Hub endpoint not live |
| Runtime status | 16 packs installed | 12 installed | 4 expert-stubs fail v1.2 strict install |
| Execution mode | A2A mainline (Phase 2.1-A canonical) | `legacy` + `fallback_to_legacy: true` | Medical Coding Agent v2.0.0 still bypasses A2A |
| MCP tools | 5 tools advertised | 5 tools confirmed | Aligned |

These live gaps are the **most material findings** of Section B and must drive quick-fix prioritization in Section F.

## B.8 Section C uses this inventory

The next section (C) scores each of the 16 agent packs + 5 page-as-agent features (MedicalCodingPage, FactExtractionPage, SpeechToTextPage, TextGenerationPage, EmbeddedAssistantPage) on the 17 Corti parity dimensions from Section A, assigning one of 6 verdicts (ALIGNED / PARTIALLY_ALIGNED / MISALIGNED / LEGACY / STUB_ONLY / DELETE_CANDIDATE). The live API gaps from B.7 are carried forward as scoring inputs: any agent whose run path depends on the legacy bypass or whose Hub endpoint 404s cannot score above PARTIALLY_ALIGNED on dimension 9 (Hub visibility) and dimension 17 (platform alignment).
