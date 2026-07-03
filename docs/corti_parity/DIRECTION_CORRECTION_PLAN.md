# DIRECTION_CORRECTION_PLAN — 方向纠偏方案

> **阶段**: P1.3 — Corti Parity Direction Audit & Asset Consolidation / Stage 3
> **输入**: Stage 0 baseline + Stage 1 inventory + Stage 2 gap analysis (总分 65.94/100, PARTIALLY_ALIGNED)
> **日期**: 2026-07-02
> **目标**: 修正方向, 让 iCoDer 真正朝 "Corti-style 医疗 Agent Runtime 平台" 前进

---

## 1. 最大偏差识别

### 1.1 偏差 #1 — MedCodER 被当作产品本体 (根因)

**现象**: CLAUDE.md 80-130 行大段描述 MedCodER 5-stage pipeline + NAACL 2025 + 4 ablation variant. E1.x 系列 cycle 全部围绕 MedCodER 优化. HomePage 不是 4 tabs 而是 MedicalCoding 入口. Sidebar 把 Medical Coding 当首页主入口. 5 tool 不共享 layout 因为 MedicalCodingPage 760 LOC 独立实现. 文档站 90+ 文件混杂因为 MedCodER 评估系列文档占大头.

**根因**: MedCodER 被当作产品本体, 而非 Pre-built Agent #18.

**影响维度**: 维度 1 (产品定位 2.80) + 维度 3 (Sidebar IA 3.00) + 维度 4 (Home 4 tabs 1.33) + 维度 5 (工作台模式 3.29) + 维度 19 (视觉系统 2.89) + 维度 20 (文档站 1.13).

### 1.2 偏差 #2 — 三套 Agent 架构并存

**现象**: Legacy `app/agents/orchestrator.py` (引用 homepage_expert 664 LOC) + Legacy `icoder_runtime/agent_runner.py` (1047 LOC) + 新 `app/icoder/agent_runtime/` (A2A+MCP+Context+Experts+Orchestrator, spec 完整但未真实跑通). 实际运行的是 Legacy 单体, 新 Agentic Framework 是空壳.

**影响维度**: 维度 15 (A2A 3.00) + 维度 16 (MCP 3.50) + 维度 17 (Context/Memory 3.29).

### 1.3 偏差 #3 — API 路径双轨

**现象**: Legacy `app/api/icoder_*.py` 4 个大模块 (2286 LOC: icoder_coding_review 1283 + icoder_agents_hub 1029 + icoder_agents_compat 123 + icoder_registry_compat 106) vs Corti-aligned `app/api/v2_tools_*.py` 8 个 (4034 LOC). 两条路径都活着, 用户和前端可调任一.

**影响维度**: 维度 6-9 (API 契约 4.47 已对齐, 但 legacy 路径仍开放是隐患).

### 1.4 偏差 #4 — 17 个 Pre-built Agents 完全缺

**现象**: Corti 20 个 Pre-built Agents, iCoDer 仅 3 个对齐. 14 metadata-only packs 无真实 Python impl. 17 个完全缺 (ICU/Triage/Medication Reconciliation/Discharge Education/Shift Handoff/PA/Referral/Clinical Education/Clinical Guidelines/Surgical Registry/Rule Explainer 等).

**影响维度**: 维度 14 (Pre-built Agents 1.40).

### 1.5 偏差 #5 — 第三方基础设施完全缺

**现象**: PostHog 自部署 / Stripe 全套 / Intercom / Mintlify / Keycloak 全部缺. Embedded Assistant 不是独立子域 proxy 模式.

**影响维度**: 维度 2 (架构 2.25) + 维度 10 (Embedded Assistant 1.67) + 维度 13 (顶栏 PostHog session replay 缺).

---

## 2. 模块分类 — 偏向何处 + 应如何处理

### 2.1 偏向"医疗编码单点工具"的模块 (应降级或删)

| 模块 | 当前角色 | 应处理 | 理由 |
|---|---|---|---|
| `backend/app/api/icoder_coding_review.py` (1283 LOC) | Legacy 14-stage coding review 主路径 | deprecate → 后续 delete | Corti 用 `POST /v2/tools/coding/`, 14-stage 是 iCoDer 自创 |
| `backend/app/services/agent_runner.py` (1047 LOC) | Legacy AgentRunner | deprecate → 后续 delete | 被新 `app/icoder/agent_runtime/orchestrator/` 取代 |
| `backend/app/agents/orchestrator.py` | Legacy 单体 orchestrator | deprecate → 后续 delete | 引用 homepage_expert, 非 A2A |
| `backend/app/agents/experts/homepage_expert.py` (664 LOC) | P1.2 应删但残留 | deprecate → 后续 delete | homepage_coding_review 概念 P1.2 已删 |
| `backend/app/agents/experts/` 其余 10 个 | Legacy expert library | deprecate → 后续 delete | 被 `app/icoder/agent_runtime/experts/` 取代 |
| `backend/app/services/review_coding_service.py` (326) | MedCodER review 服务 | deprecate | 非 Corti 方向 |
| `backend/app/services/gold_case_*.py` (324+231) | Gold case 评估 | deprecate | CLAUDE.md 不做 F1 实验 |
| `backend/app/services/inter_rater.py` (193) | Inter-rater 评估 | deprecate | 同 |
| `backend/app/services/pilot_report_builder.py` (176) | Pilot 报告 | deprecate | 同 |
| `backend/app/services/ccl2026_importer.py` (221) | CCL2026 数据集导入 | deprecate | 评估专用 |
| `backend/app/services/stt_finetune.py` (323) | STT 微调 | deprecate | CLAUDE.md 不训练模型 |
| `backend/app/api/evaluation.py` (104) + `agent_evaluation.py` (152) | F1 评估端点 | deprecate | 非 Corti 方向 |
| `backend/app/api/gold_cases.py` (144) | Gold case 管理 | deprecate | 同 |
| `backend/app/api/code_tables.py` (169) + `m2a.py` (277) | iCoDer 内部概念 | deprecate | 无 Corti 等价 |
| `backend/app/api/icoder_agents_compat.py` (123) + `icoder_registry_compat.py` (106) | 兼容层 | deprecate → delete | 迁移完成后删 |
| `frontend/src/pages/EvaluationPage.tsx` (265) | F1 评估页 | deprecate | 非 Corti 方向 |
| `frontend/src/pages/GoldCasesPage.tsx` (272) | Gold case 管理 | deprecate | 同 |
| `frontend/src/pages/ExpertLibraryPage.tsx` (604) | Expert Library | deprecate | Corti 用 Pre-built Agents + MCP |
| `frontend/src/pages/OrchestrationPage.tsx` (266) | Orchestration 控制台 | deprecate | Corti 无此独立页 |
| `frontend/src/pages/EmbedDemoCodingReviewPage.tsx` (225) + `.bak` | Demo 页 | deprecate → delete | 整合到 EmbeddedAssistantPage |
| `frontend/src/components/orchestration/` (7 components) | Legacy Doctor/MethodCompare/RunTrace UI | deprecate → 后续 delete | P1.2 概念已删 |
| `frontend/src/components/icoder/RunTraceTimeline.tsx` | RunTrace 概念 | deprecate → delete | P1.2 应删 |
| `frontend/src/components/medical-coding/MethodTraceViewer.tsx` | Method trace | deprecate → delete | P1.2 概念已删 |
| `frontend/src/services/icoderCodingReviewApi.ts` | Legacy coding review API client | deprecate | 同 |
| `frontend/src/hooks/useReviewPipeline.ts` | Review pipeline hook | deprecate | 同 |
| `icoder_runtime/agent_runner.py` (重复) | 与 app/services/agent_runner.py 重复 | deprecate → delete | 二选一 |
| `icoder_runtime/dashboard.html` | Standalone HTML dashboard | delete_candidate | 无 Corti 等价 |
| `icoder_runtime/sandbox.py` + `symbolic_state.py` | 实验性 | deprecate | 无 Corti 等价 |
| `icoder_runtime/m2a/` (空) + `methods/` (空) | 空目录 | delete_candidate | 概念已弃 |

### 2.2 偏向"普通 SaaS 后台"的模块 (保留但不上主线)

| 模块 | 当前角色 | 应处理 | 理由 |
|---|---|---|---|
| `backend/app/api/organizations.py` (363) | Org CRUD | keep_mainline (rename) | Corti 用 projects, 可改名 |
| `backend/app/api/team.py` (141) | Team CRUD | keep_mainline | Corti 有 team |
| `backend/app/api/billing.py` (80) | Billing | keep_mainline | Corti 有 billing |
| `backend/app/api/usage.py` (97) | Usage | keep_mainline | Corti 有 usage |
| `backend/app/api/customers.py` (217) | Customer CRUD | keep_mainline | Corti 有 customers |
| `backend/app/api/templates.py` (195) | Template CRUD | keep_mainline | Corti 有 templates (Beta) |
| `backend/app/api/settings.py` (in organizations.py) | Settings | keep_mainline | Corti 有 settings |

**判断**: 这 7 项是 Corti Manage 段的标准 SaaS 后台, **保留**但不上主线 (主线 = Agent Runtime). 与 Corti 对齐即可, 不需额外开发.

### 2.3 符合 Corti 方向的模块 (保留 + 加固)

| 模块 | 当前角色 | 应处理 |
|---|---|---|
| `backend/app/api/v2_tools_*.py` (8 模块 4034 LOC) | Corti-aligned Studio tools | keep_mainline + 加固 |
| `backend/app/api/oauth.py` (449) + `auth.py` (435) | OAuth 2.0 + JWT | keep_mainline |
| `backend/app/api/runtime_platform.py` (673) | Runtime status + health | keep_mainline |
| `backend/app/icoder/agent_runtime/a2a/` (13) | A2A 协议 | keep_mainline + 真实跑通 (Phase 2) |
| `backend/app/icoder/agent_runtime/context/` (11) | Context/Memory | keep_mainline + 真实跑通 (Phase 2) |
| `backend/app/icoder/agent_runtime/experts/` (5) | 5 atomic experts (MedCodER Stage 1-5) | keep_mainline |
| `backend/app/icoder/agent_runtime/orchestrator/` (13) | Orchestrator | keep_mainline + 真实跑通 (Phase 2) |
| `backend/app/icoder/mcp/handlers/` (5) | MCP 5 tool handlers | keep_mainline + Resources/Prompts (Phase 2) |
| `backend/app/services/expert_registry.py` + `expert_runner.py` + `mcp_client.py` + `mcp_wrapper.py` + `memory_expert.py` + `phi_redactor.py` + `sse_manager.py` + `task_manager.py` + `tool_registry.py` + `agent_registry_sync_service.py` + `schema_drift_service.py` + `runtime_state_sync.py` + `permissions.py` + `guardrails.py` + `contract_engine.py` + `evidence_pack.py` + `context_scoper.py` + `tenant_scoper.py` + `thread_state.py` + `token_tracker.py` + `credential_vault.py` + `circuit_breaker.py` | Agentic Framework 服务 | keep_mainline |
| `backend/app/services/icd10cn_loader.py` + `icd9cm3_loader.py` + `medcoder_index_health.py` + `code_dictionary.py` + `rule_engine.py` + `llm_service.py` + `llm_adapter.py` + `llm_planner.py` | 中国编码 + LLM 服务 | keep_mainline |
| `backend/compliance_services/` (5) | RuleEngine + medical_coding_rules + medcoder_retrieval_rules | keep_mainline (drg_dip/insurance 实验性) |
| `backend/official_agents/medical_coding/` + `medcoder-coding-review/` + 4 atomic expert packs | 2 real + 4 atomic Agent packs | keep_mainline |
| `backend/icoder_runtime/core/` + `constants/` + `observability/` + `providers/` + `embedded/` + pack loader | icoder_runtime 核心 | keep_mainline |
| `frontend/src/pages/` 24 Corti-aligned pages | 主线前端 | keep_mainline |
| `frontend/src/components/common/` + `medical-coding/` + `layout/` + `agents/` + `embed/` | 主线组件 | keep_mainline |
| `frontend/src/services/api.ts` + `runtimeApi.ts` + `agentHubApi.ts` | 主线 API client | keep_mainline (agentHubApi 待 migrate) |
| `docs/corti_parity/` + `corti-reverse-engineered/` + `cloud/` + `openapi/` + `dev/` + `specs/` + `phase_cycles/` + `operation-manual/` + `sdk/` | 主线文档 | keep_mainline |
| 5 SDK packages | 主线 SDK | keep_mainline |

### 2.4 应归档的模块 (historical, 不删但移到 archive)

| 模块 | 应处理 |
|---|---|
| `docs/Corti_*.md` (10 文件) + `2026-05-08_Corti*.md` | archive_docs → `docs/archive/corti_analysis_2026_05/` |
| `docs/PHASE5/6/10/11*.md` + `SPRINT*.md` + `PILOT*.md` + `M3*.md` (20+ 文件) | archive_docs → `docs/archive/phase_history/` |
| `docs/CASE_REASONING_REPORT.md` + `CODING_REVIEW_WORKFLOW_DELIVERY.md` + `EVALUATION_BASELINE_REPORT.md` + `E2E_TEST_*.md` | archive_docs → `docs/archive/phase_history/` |
| `docs/iCoDer_Convergence_Audit_*.md` + `iCoDer_Governance_Blueprint_*.md` + `iCoDer_vs_Corti_*.md` | archive_docs → `docs/archive/convergence/` |
| `docs/audit_remediation/` (5 E1.x 报告) | archive_docs → `docs/archive/audit_remediation/` |
| `docs/productization/` (P1.0 + P1.1 baseline) | archive_docs → `docs/archive/productization/` |
| `docs/experiments/E2_0_NEGATIVE_SIGNAL_ARCHIVE.md` | archive_docs (留原位, 已在 archive 子目录) |
| `Corti/` (repo root PDF + llms) | archive_docs → `docs/archive/corti_reference_early/` |
| `corti-crawl/` + `corti_contracts/` + `corti_ui_contracts/` | archive_docs → `docs/archive/corti_crawl_early/` |
| `docs/corti-screens/` | archive_docs → 同上 |
| `screenshots/` (repo root 早期截图) | archive_docs → 同上 |
| `icoder-next/` (整个子项目) | archive_docs → `archive/icoder-next/` (repo root) |
| `iCoDer_Medical_Coding_Agent_PRD_V1.0.md` + `icoder-mockup-variant-A.html` + `train(2).xlsx` | archive_docs → `docs/archive/early_design/` |
| `docs/Figma_Design_Prompt_CodeTable_Manager.md` | archive_docs → 同上 |
| `docs/FRONTEND_FAKE_FEATURES_AUDIT.md` | archive_docs → 同上 |
| `docs/ICODER_CAPABILITY_MAP.md` | archive_docs → 同上 |
| `docs/P0_Gap_Closure_Plan.md` + `P0_QUALITY_GATE_REPORT.md` | archive_docs → `docs/archive/phase_history/` |
| `docs/Runtime_Discipline_Delivery_2026-05-12.md` + `Runtime_Persistence_Delivery_2026-05-12.md` | archive_docs → 同上 |

### 2.5 应立即删的模块 (无引用 / 备份 / 误入仓库)

| 模块 | 应处理 | 证据 |
|---|---|---|
| `.corti-user-data/` | delete_candidate + .gitignore | Chrome 浏览器 profile 误入仓库 |
| `backend/data/icoder.db.bak2` | delete_candidate | stale alembic=002 (cycle 23 已识别) |
| `backend/data/icoder.db.bak20260701` | delete_candidate | 全 DROP 0 表 (cycle 23 已识别) |
| `backend/data/icoder.db.broken-20260702` | delete_candidate | 损坏 DB |
| `backend/data/test.db` | delete_candidate | CI 应 in-memory |
| `.tmp_run.json` / `.tmp_agent_run.json` / `backend/.tmp_run.json` | delete_candidate + .gitignore | 临时运行文件 |
| `frontend/src/pages/EmbedDemoCodingReviewPage.tsx.bak` | delete_candidate | 备份文件 |
| `icoder_runtime/methods/` (空 + __pycache__) | delete_candidate | P1.2 已删概念 |
| `icoder_runtime/m2a/` (空) | delete_candidate | 概念已弃 |
| `icoder_runtime/dashboard.html` | delete_candidate | 无 Corti 等价, 前端 AgentsPage 替代 |

### 2.6 应迁移的模块 (migrate, 高代价可放缓)

| 模块 | 当前 | 目标 | 优先级 |
|---|---|---|---|
| `app/api/icoder_agents_hub.py` (1029) + `agents.py` (736) | Legacy Agent Hub | `/rest/v1/agent_definitions` Corti 风格 | P2 (Phase 2) |
| `app/api/runtime.py` (386) | Legacy runtime | 合并到 `runtime_platform.py` | P2 |
| `app/api/text_gen.py` (131) | Legacy text gen | 合并到 `v2_tools_guided_document.py` | P2 |
| `app/api/facts.py` (204) | Legacy facts | 合并到 `v2_tools_facts.py` | P2 |
| `app/services/runtime.py` (702) | Legacy runtime service | 合并到 runtime_platform service | P2 |
| `web-components/` (repo root) | 与 packages/web-components/ 重复 | 合并到 `packages/web-components/` | P2 |
| `frontend/src/services/agentHubApi.ts` | Legacy 命名 | 改名对齐 Corti agent_definitions | P2 |
| `app/models/organization.py` | iCoDer 命名 | 评估改名 project (高代价, 可放缓) | P3 |
| `app/models/agent.py` | iCoDer 命名 | 评估改名 agent_definition (高代价, 可放缓) | P3 |

---

## 3. 新的主线定义

### 3.1 一句话定位

> **iCoDer 是面向中国医院场景的 Corti-style 医疗 Agent Runtime 平台**, 以托管云 SaaS 形式交付 (Environments: EU/US/CN; 医院 = Tenant; HIS/EMR = API Client).
> **Runtime 是 iCoDer Server 的内核执行引擎**, 不是独立 pip 包. **MedCodER 是第一个官方 Agent 应用** (Pre-built Agent #18), 不是产品本体.

### 3.2 平台 = Runtime + Agentic Framework + Pre-built Agents

```
iCoDer Platform
├── Runtime Core (icoder_runtime/)
│   ├── AgentPackageV1 (.icoder-agent 包格式)
│   ├── RuntimeAgentRegistry (持久化 Agent 注册表)
│   ├── AgentRunner (执行引擎, Corti Orchestrator 风格)
│   ├── LLMGateway (Provider 路由, DeepSeek 默认 env 可配)
│   ├── DataPolicy (PHI 脱敏 + 区域数据驻留)
│   └── Observability (RunHistory, AuditLog, FallbackTracker)
├── Agentic Framework (app/icoder/agent_runtime/)
│   ├── A2A Protocol (Agent-to-Agent, JSON-RPC 2.0)
│   ├── Context/Memory (短期 SQLite + 长期 BGE-M3+FAISS)
│   ├── MCP Server (tools/list + tools/call, 5 handlers)
│   ├── Orchestrator (state_machine + planner + delegator + aggregator)
│   └── 5 Atomic Experts (evidence_extractor + index_navigator + code_reconciler + tabular_validator + coding_expert)
├── Compliance Services (compliance_services/)
│   ├── RuleEngine (multi rule_set)
│   ├── MedicalCodingRuleSet (ICD-10-CN + ICD-9-CM-3-CN, R001-R010 + MC-R-M80-001)
│   ├── MedCodERRetrievalRuleSet (catalog + similarity)
│   ├── DRG_DIP_RuleSet (CN-DRG/DIP, 实验性)
│   └── InsuranceRuleSet (医保审核, 实验性)
├── Pre-built Agents (official_agents/, 目标 20 个)
│   ├── Medical Coding Agent (#18, 已对齐)
│   ├── MedCodER Coding Review Agent (5-stage NAACL 2025, 已对齐)
│   ├── 4 Atomic Expert Packs (evidence_extractor + index_navigator + code_reconciler + tabular_validator, 已对齐)
│   └── 14 待实装 (Rule Explainer / Compliance Guardrail / Code Validation / Procedure Extractor / Diagnostic Extractor / Surgical Registry / ICU / Triage / Note Completeness / Medication Reconciliation / Denial Appeals / Discharge Education / Nursing Shift Handoff / PA / Referral / Clinical Education / Clinical Guidelines / CDI)
└── Studio Tools (app/api/v2_tools_*, 8 endpoints)
    ├── Medical Coding (POST /api/v2/tools/coding/icoder/)
    ├── Fact Extraction (POST /api/v2/tools/extract-facts + GET /api/v2/factgroups/)
    ├── Text Generation 5 endpoints (Streams + FactsR + Guided Doc + Sections/Templates + Documents Classic)
    └── STT 3 endpoints (Transcribe WSS + Streams WSS + Transcripts REST)
```

### 3.3 MedCodER 降级声明

**MedCodER 不再是产品本体**, 而是:
- Pre-built Agent #18 (Medical Coding Agent) 的 5-stage pipeline 实现选项
- 通过 `medcoder-coding-review/agent_pack.json` 注册
- 由 4 atomic expert packs (evidence_extractor + index_navigator + code_reconciler + tabular_validator) 组成
- 触发方式: `POST /api/v2/tools/coding/icoder/` (用户调 Medical Coding Agent, Agent 内部走 MedCodER 5-stage)

**MedCodER 评估资产 (F1 / Gold case / Pilot / 4 ablation variant)** 降级为:
- **实验性保留** (keep_experimental), 不上线, 不在主线文档描述
- 评估脚本 + fixtures 保留在 `backend/scripts/` + `backend/tests/fixtures/` + `backend/tests/regression/`
- 但 CLAUDE.md / PRODUCT_DIRECTION 不再描述 4 ablation variant 为主线

### 3.4 主线 vs 实验性 vs Legacy 三层

| 层 | 内容 | 文档态度 |
|---|---|---|
| **主线 (Mainline)** | v2_tools API + oauth + runtime_platform + app/icoder/agent_runtime/ + compliance_services + 2 real Agent packs + 4 atomic expert packs + 24 Corti-aligned frontend pages | CLAUDE.md / PRODUCT_DIRECTION 主描述 |
| **实验性 (Experimental)** | MedCodER 评估资产 + DRG/DIP 系列 + F1 regression tests + Phase 1.x 文档 | 文档明确标 "experimental, 非主线" |
| **Legacy (Deprecated)** | app/agents/ + icoder_runtime/agent_runner.py + app/api/icoder_*.py + Doctor/MethodCompare/RunTrace 残留 + 90+ 历史文档 | 文档明确标 "deprecated, 待删" |

---

## 4. 主导航建议

### 4.1 Sidebar 段顺序 (对齐 Corti)

```
Top
├── Home (4 tabs: Transcribe/Document/Chat/Code NEW)
└── Developer quickstart

AI Studio
├── Overview
├── Agents (Pre-built + My agents)
├── Speech to Text (Dictation / Ambient / Pre-recorded)
├── Text Generation
├── Embedded Assistant
├── Fact Extraction
└── Medical Coding  ← 降为 AI Studio 第 7 子页 (不再是首页主入口)

Manage
├── API Clients
├── Team
├── Billing
├── Usage
├── Customers
├── Templates (Beta)
└── Settings

Support
├── Get Help
└── Tickets Portal
```

### 4.2 Project Home 4 tabs (对齐 Corti)

`/` (Home) 重写为 4 tabs:
- **Transcribe** → promo 跳 `/ai-studio/speech-to-text`
- **Document** → promo 跳 `/ai-studio/text-generation`
- **Chat** → promo 跳 `/ai-studio/embedded-assistant`
- **Code NEW** → promo 跳 `/ai-studio/medical-coding`

### 4.3 工作台通用 Layout (对齐 Corti)

5 个 Studio tool 共享 layout 组件:
- 左 Input / 右 Output 50/50 split
- Input 控件: Samples + Clear + Copy
- Output 控件: Rendered/JSON toggle + Clear + Copy + Download
- 右侧 Settings panel (Settings/Code tabs + Template dropdown + Output language)
- 底部 Event Inspector 可折叠
- Empty state microcopy

### 4.4 顶栏元素 (对齐 Corti)

- Breadcrumb (已有)
- Live cost (6 位小数, 已有)
- **Reset live cost (新增)**
- API Client dropdown (已有)
- $credits 余额 (已有)
- Docs link (已有)
- **Theme toggle 深/浅 (新增)**
- PostHog session replay (Phase 4, 不在 P1.3 范围)

---

## 5. P1.3 范围内行动项

### 5.1 Stage 4 — 文档重写 (7 份)

| 文档 | 路径 | 内容 |
|---|---|---|
| 1 | `docs/product/PRODUCT_DIRECTION.md` | 新主线声明 (Corti-style 医疗 Agent Runtime 平台) |
| 2 | `docs/architecture/CURRENT_ARCHITECTURE.md` | 当前架构 (4 层: Studio Tools / Agentic Framework / Compliance Services / Runtime Core) |
| 3 | `docs/architecture/MAINLINE_VS_LEGACY.md` | 主线 vs 实验性 vs Legacy 三层分类清单 |
| 4 | `docs/product/CORTI_PARITY_ROADMAP.md` | Corti 对齐 roadmap (Phase 1-4, P1.3 范围 + Phase 2-4 后续) |
| 5 | `docs/backlog/PRODUCT_BACKLOG.md` | 产品 backlog (Pre-built Agents 17 个缺 + Theme toggle + 工作台 layout 等) |
| 6 | `docs/backlog/TECH_DEBT_BACKLOG.md` | 技术债 backlog (legacy 删除清单 + 命名分散 + 三套架构合并) |
| 7 | `docs/README_INDEX.md` | 文档索引 (新人 5 分钟了解全局) |

### 5.2 Stage 5 — 资产清理 (P0 立即删 + 归档 + deprecate 标记)

**P0 立即删** (10 项, Stage 1 已列):
1. `.corti-user-data/` + .gitignore
2. `backend/data/icoder.db.bak2` + `icoder.db.bak20260701` + `icoder.db.broken-20260702`
3. `backend/data/test.db`
4. `.tmp_run.json` + `.tmp_agent_run.json` + `backend/.tmp_run.json` + .gitignore
5. `frontend/src/pages/EmbedDemoCodingReviewPage.tsx.bak`
6. `icoder_runtime/methods/` (空)
7. `icoder_runtime/m2a/` (空)
8. `icoder_runtime/dashboard.html`

**归档** (移到 `docs/archive/` 或 `archive/`):
1. 90+ 历史文档 → `docs/archive/`
2. `Corti/` + `corti-crawl/` + `corti_contracts/` + `corti_ui_contracts/` + `screenshots/` → `docs/archive/corti_reference_early/`
3. `icoder-next/` → `archive/icoder-next/`
4. `iCoDer_Medical_Coding_Agent_PRD_V1.0.md` + `icoder-mockup-variant-A.html` + `train(2).xlsx` → `docs/archive/early_design/`

**Deprecate 标记** (代码不动, 加 `# DEPRECATED` 注释 + 在 MAINLINE_VS_LEGACY.md 标记):
1. `app/agents/` 整套 (orchestrator + 11 experts)
2. `app/services/agent_runner.py` + `icoder_runtime/agent_runner.py`
3. `app/api/icoder_coding_review.py` + `icoder_agents_hub.py` + `icoder_agents_compat.py` + `icoder_registry_compat.py`
4. `app/api/evaluation.py` + `agent_evaluation.py` + `gold_cases.py` + `code_tables.py` + `m2a.py`
5. `app/services/review_coding_service.py` + `gold_case_*.py` + `inter_rater.py` + `pilot_report_builder.py` + `ccl2026_importer.py` + `stt_finetune.py`
6. `frontend/src/pages/EvaluationPage.tsx` + `GoldCasesPage.tsx` + `ExpertLibraryPage.tsx` + `OrchestrationPage.tsx` + `EmbedDemoCodingReviewPage.tsx`
7. `frontend/src/components/orchestration/` (7 components) + `icoder/RunTraceTimeline.tsx` + `medical-coding/MethodTraceViewer.tsx`
8. `frontend/src/services/icoderCodingReviewApi.ts` + `hooks/useReviewPipeline.ts`
9. `icoder_runtime/sandbox.py` + `symbolic_state.py`

### 5.3 Stage 6 — UI IA 最小纠偏

**最小纠偏** (低风险, 高 ROI):
1. Sidebar 段顺序对齐 Corti (Layout.tsx 改 nav 顺序)
2. Medical Coding 在 sidebar 降为 AI Studio 第 7 子页 (而非首页主入口)
3. Project Home 加 4 tabs 雏形 (Transcribe/Document/Chat/Code, 即使是 promo 卡片)
4. 顶栏加 Theme toggle (深/浅) + Reset live cost
5. 工作台 5 tool 抽离共享 layout 组件 (Layout 壳子, 不动各页内部)

**不上主线** (P1.3 范围外):
- 5 tool 内部重写
- 20 Pre-built Agents 实装
- Embedded Assistant 子域 proxy
- PostHog/Stripe/Intercom/Mintlify 第三方基础设施

### 5.4 Stage 7 — 测试验证 (4 轮)

1. **Asset/Docs/Direction Audit**: 验证 Stage 1-6 输出文档完整 + 一致
2. **Backend/Runtime Regression**: `health_check.py` + `check_schema_drift.py` + `export_openapi.py` + 关键 API 测试
3. **Frontend Product Flow**: `npx tsc --noEmit` + `npx vitest run` + 关键 page render
4. **Browser QA** (可选): 主流程 e2e (register → home → settings → medical-coding)

### 5.5 Stage 8 — 最终报告

`docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md` 含 18 项 + PASS/FAIL.

---

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| MedCodER 降级影响现有用户 | MedCodER 仍可用 (Pre-built Agent #18), 仅文档降级, 不删代码 |
| Legacy 代码删早了引用断 | Stage 5 只标 deprecate, 不实际删 (除 P0 无引用项); 实际删放在 Phase 2 迁移后 |
| UI IA 改 Sidebar 影响导航 | Stage 6 最小纠偏, 不动路由, 仅改 nav 顺序 |
| 文档重写覆盖历史 | Stage 4 全部新建, 旧文档归档不删 |
| 测试失败 | Stage 7 不允许 skip/xfail/delete, 必须修复 |

---

## 7. 成功标准 (对齐原 Prompt 20 项)

1. ✅ 已建立 Corti reference baseline (Stage 0)
2. ✅ 已完成 iCoDer 全资产盘点 (Stage 1)
3. ✅ 已输出 Corti parity gap analysis (Stage 2)
4. ✅ 已明确当前偏离 Corti-style 方向 (PARTIALLY_ALIGNED, 65.94/100)
5. ⏳ 已更新产品方向文档 (Stage 4)
6. ⏳ 已更新架构主线文档 (Stage 4)
7. ⏳ 已更新 mainline vs legacy 文档 (Stage 4)
8. ⏳ 已建立文档索引 (Stage 4)
9. ⏳ 已清理或归档不需要的资产 (Stage 5)
10. ⏳ 已标记 deprecated / experimental / historical (Stage 4 + 5)
11. ⏳ 主导航和 IA 更接近 Corti-style (Stage 6)
12. ⏳ MedCodER 降级为官方 Agent 应用 (Stage 4 + 6)
13. ⏳ 编码质量优化移出主线 (Stage 4)
14. ⏳ 不再堆 SaaS 后台功能 (Stage 4 — 明确 Manage 段不上主线)
15. ⏳ 后端测试通过 (Stage 7)
16. ⏳ 前端构建通过 (Stage 7)
17. ⏳ OpenAPI contract 通过 (Stage 7)
18. ⏳ schema drift 为 0 (Stage 7)
19. ⏳ doctor / health 通过 (Stage 7)
20. ⏳ 最终报告清楚说明下一步 (Stage 8)

---

## Stage 3 完成, 进入 Stage 4。
