# ICODER_ASSET_INVENTORY — iCoDer 当前项目资产总盘点

> **阶段**: P1.3 — Corti Parity Direction Audit & Asset Consolidation / Stage 1
> **审计日期**: 2026-07-02
> **审计基准**: `docs/corti_parity/CORTI_REFERENCE_BASELINE.md` (Stage 0 输出)
> **审计方法**: 文件树列举 + 行数统计 + grep 引用核查 + 与 Corti baseline 逐项对比
> **标签集**: keep_mainline / keep_experimental / archive_docs / deprecate / delete_candidate / migrate / rename / unclear

---

## 0. 总览

| 类别 | 项数 | 总 LOC / 文件数 |
|---|---|---|
| Backend API modules (`app/api/`) | 38 | ~9,500 LOC |
| Backend services (`app/services/`) | 50+ | ~13,000 LOC |
| Backend models (`app/models/`) | 22 | ~3,000 LOC |
| Backend schemas (`app/schemas/`) | 26 | ~3,500 LOC |
| Backend legacy experts (`app/agents/experts/`) | 11 | ~2,400 LOC |
| Backend new experts (`app/icoder/agent_runtime/experts/`) | 5 | ~1,200 LOC |
| Backend A2A protocol (`app/icoder/agent_runtime/a2a/`) | 13 | ~2,500 LOC |
| Backend MCP (`app/icoder/mcp/`) | 7 | ~1,000 LOC |
| Backend icoder_runtime (legacy + core) | 30+ | ~10,000 LOC |
| Backend compliance_services | 5 | ~2,000 LOC |
| Backend official_agents (16 dirs) | 16 packs | 2 real + 14 metadata_only |
| Frontend pages (`frontend/src/pages/`) | 30 | ~10,962 LOC |
| Frontend components | 28 | ~5,000 LOC |
| Frontend services / hooks / store / utils | 9 | ~1,500 LOC |
| Documentation (`docs/`) | 90+ files | ~50,000 LOC |
| Scripts (`scripts/`) | 10 | ~3,000 LOC |
| Packages (SDK) | 5 packages | ~5,000 LOC |
| Repo-root extras | 7 dirs | (Corti/, corti-crawl/, corti_contracts/, corti_ui_contracts/, icoder-next/, .corti-user-data/, web-components/) |

**审计结论速览**: iCoDer 仓库存在**三套并行的 Agent 架构**和**两套并行的 API 路径**:
1. **Legacy 单体 Agent** (`app/agents/orchestrator.py` + 11 `app/agents/experts/`) — 主线已弃用但代码仍在
2. **Legacy MedCodER pipeline** (`icoder_runtime/agent_runner.py` + `medcoder-coding-review/` pack) — 当前 medical-coding 主线
3. **新 Agentic Framework** (`app/icoder/agent_runtime/` + A2A + MCP + 5 atomic experts) — Corti-aligned 方向, 但只部分 wired

API 路径双轨:
- Legacy `app/api/icoder_*.py` (4 个大模块: icoder_coding_review 1283 LOC, icoder_agents_hub 1029 LOC, icoder_agents_compat, icoder_registry_compat) — iCoDer 内部路径
- Corti-aligned `app/api/v2_tools_*.py` (8 个: coding/facts/streams/stt/guided_document/sections_templates/documents_classic) — `/api/v2/tools/*` 路径

---

## 1. Backend API Modules (`backend/app/api/`)

### 1.1 Corti-aligned v2 tools (keep_mainline)

| 模块 | LOC | 标签 | 理由 |
|---|---|---|---|
| `v2_tools_coding.py` | 559 | keep_mainline | `POST /api/v2/tools/coding/` Corti §13.6 主线, Phase 1.1 已对齐 |
| `v2_tools_facts.py` | 619 | keep_mainline | `POST /api/v2/tools/extract-facts` + `GET /api/v2/factgroups/` §13.5 |
| `v2_tools_stt.py` | 866 | keep_mainline | `POST /api/v2/interactions/` + transcripts/recordings §13.3 (9 cycles CLOSED) |
| `v2_tools_streams.py` | 382 | keep_mainline | WSS Streams §13.3 |
| `v2_tools_guided_document.py` | 277 | keep_mainline | Guided Document Synthesis §13.4 (Beta) |
| `v2_tools_sections_templates.py` | 262 | keep_mainline | Sections & Templates LIST §13.4 (Beta) |
| `v2_tools_documents_classic.py` | 196 | keep_mainline | Documents Classic LIST §13.4 (Planned deprecation — Corti 也标 deprecated, 跟随) |
| `oauth.py` | 449 | keep_mainline | OAuth 2.0 client_credentials + tenant + scope (Phase 1.0 已对齐) |
| `runtime_platform.py` | 673 | keep_mainline | `/api/runtime/*` + `registry_sync` + `/health` (Cycle 25 已加固) |

### 1.2 Corti-aligned business APIs (keep_mainline)

| 模块 | LOC | 标签 | 理由 |
|---|---|---|---|
| `customers.py` | 217 | keep_mainline | Corti `/functions/v1/public/projects/<id>/customers` 对齐 (Loop 1) |
| `templates.py` | 195 | keep_mainline | Corti Templates Beta 对齐 (Loop 2) |
| `tickets.py` | 216 | keep_mainline | Corti Intercom Tickets 等价 in-app (Loop 9) |
| `billing.py` | 80 | keep_mainline | Corti `/functions/v1/projects/<id>/billing/balance` 对齐 (Loop 4) |
| `platform_api_clients.py` | 102 | keep_mainline | API Client CRUD |
| `platform_environments.py` | 68 | keep_mainline | EU/US/CN environment |
| `platform_tenants.py` | 74 | keep_mainline | Tenant CRUD |
| `auth.py` | 435 | keep_mainline | Register + Login + JWT (Corti 走 Keycloak, iCoDer 自实现但等价) |
| `team.py` | 141 | keep_mainline | Team members + invitations |
| `organizations.py` | 363 | keep_mainline | Org/Tenant 层 |
| `keys.py` | 98 | keep_mainline | API key management |

### 1.3 iCoDer-specific (无 Corti 等价) — deprecate or unclear

| 模块 | LOC | 标签 | 理由 |
|---|---|---|---|
| `icoder_coding_review.py` | 1283 | deprecate | iCoDer 内部 14-stage coding review, P1.2 已删概念但 API 还在, 应迁移到 `/v2/tools/coding/` 并删 |
| `icoder_agents_hub.py` | 1029 | migrate | Agent Hub 是 P1.1 临时实现, 应迁到 Corti 风格 `/rest/v1/agent_definitions` + `/functions/v1/external/agents` |
| `icoder_agents_compat.py` | 123 | deprecate | 兼容层, 应在迁移完成后删 |
| `icoder_registry_compat.py` | 106 | deprecate | 兼容层, 应在迁移完成后删 |
| `agents.py` | 736 | migrate | 当前 Agent CRUD, 应迁到 `agent_definitions` 命名 |
| `reviews.py` | 921 | unclear | 人工审核 review workflow, Corti 是 Pre-built Agent (Note Completeness + CDI), 此模块可能应降级为 Agent |
| `experts.py` | 551 | deprecate | iCoDer Expert Library 概念, Corti 用 Pre-built Agents + MCP, 应降级或重写 |
| `evaluation.py` | 104 | deprecate | F1 评估端点, 非 Corti 方向 (CLAUDE.md 已降级为非主线) |
| `agent_evaluation.py` | 152 | deprecate | 同上 |
| `gold_cases.py` | 144 | deprecate | Gold case 管理, MedCodER 评估专用, 非 Corti 方向 |
| `encounters.py` | 200 | unclear | Encounter CRUD, Corti 用 interaction 概念, 需判断保留 |
| `medical_docs.py` | 192 | unclear | Medical document CRUD, 无 Corti 等价 |
| `fhir.py` | 429 | keep_experimental | FHIR 集成, Corti docs 提 run-time context 用 FHIR, 保留实验 |
| `code_tables.py` | 169 | deprecate | Code table CRUD, iCoDer 内部概念 |
| `codes.py` | 67 | unclear | Code CRUD |
| `drg.py` | 148 | keep_experimental | DRG 分组, Corti 没有但中国医院需要 (CN-DRG/DIP), 实验性保留 |
| `m2a.py` | 277 | deprecate | "M2A" iCoDer 内部概念, 无 Corti 等价 |
| `compliance.py` | 74 | keep_mainline | Compliance 规则, 保留 |
| `tools.py` | 278 | unclear | Tool registry CRUD, 可能与 MCP tool_registry 重复 |
| `admin.py` | 232 | keep_mainline | Admin 端点 |
| `usage.py` | 97 | keep_mainline | Usage tracking |
| `runtime.py` | 386 | migrate | Runtime status + runs, 部分已被 `runtime_platform.py` 取代, 应合并 |
| `websocket.py` | 521 | keep_mainline | WS 连接 (Corti 也用 WSS for Streams/Transcribe) |
| `text_gen.py` | 131 | migrate | Text Generation 端点, 应合并到 `v2_tools_guided_document.py` |
| `facts.py` | 204 | migrate | Facts CRUD, 应合并到 `v2_tools_facts.py` |
| `embedded.py` | 95 | keep_mainline | Embedded Assistant session init |
| `experts.py` | 551 | deprecate | 见上 |

### 1.4 推荐操作汇总

- **删 (deprecate → delete in Stage 5)**: `icoder_coding_review.py`, `icoder_agents_compat.py`, `icoder_registry_compat.py`, `evaluation.py`, `agent_evaluation.py`, `gold_cases.py`, `code_tables.py`, `m2a.py`
- **迁 (migrate)**: `icoder_agents_hub.py` → `/rest/v1/agent_definitions`; `agents.py` → 同; `runtime.py` → 合并 `runtime_platform.py`; `text_gen.py` → 合并 `v2_tools_guided_document.py`; `facts.py` → 合并 `v2_tools_facts.py`
- **保 (keep_mainline)**: 全部 v2_tools_* + oauth + runtime_platform + 主业务 API

---

## 2. Backend Services (`backend/app/services/`)

### 2.1 Corti-aligned Agentic Framework services (keep_mainline)

| 服务 | LOC | 标签 | 理由 |
|---|---|---|---|
| `expert_registry.py` | 173 | keep_mainline | Expert 注册表 (Corti Expert Registry 对齐) |
| `expert_runner.py` | 142 | keep_mainline | Expert 执行器 |
| `mcp_client.py` | 176 | keep_mainline | MCP client (Corti Expert 用 MCP) |
| `mcp_wrapper.py` | 169 | keep_mainline | MCP server 包装 |
| `memory_expert.py` | 271 | keep_mainline | Memory expert (Corti Memory 概念) |
| `phi_redactor.py` | 72 | keep_mainline | PHI 脱敏 (Corti data residency 对齐) |
| `sse_manager.py` | 105 | keep_mainline | SSE 流 (Corti 交互模式 §11.7) |
| `task_manager.py` | 156 | keep_mainline | Task 管理 (Corti A2A Task 5 态) |
| `tool_registry.py` | 147 | keep_mainline | Tool 注册表 (Corti MCP tools) |
| `agent_registry_sync_service.py` | 279 | keep_mainline | Registry → DB sync (Cycle 25 已加固 SyncState) |
| `schema_drift_service.py` | 239 | keep_mainline | Schema drift checker (Cycle 25 已加) |
| `runtime_state_sync.py` | 201 | keep_mainline | Runtime 状态同步 |
| `permissions.py` | 244 | keep_mainline | 权限策略 (Corti safety boundaries) |
| `guardrails.py` | 149 | keep_mainline | Guardrails (Corti Safety First 原则) |
| `contract_engine.py` | 241 | keep_mainline | Contract engine (类型校验) |
| `evidence_pack.py` | 221 | keep_mainline | Evidence 打包 (Corti evidence char span) |
| `context_scoper.py` | 138 | keep_mainline | Context scope (Corti Memory scoped context) |
| `tenant_scoper.py` | 56 | keep_mainline | Tenant scope |
| `thread_state.py` | 128 | keep_mainline | Thread 状态 (Corti multi-context threads) |
| `token_tracker.py` | 49 | keep_mainline | Token 计数 (cost tracking) |
| `credential_vault.py` | 124 | keep_mainline | 凭证保险库 |
| `circuit_breaker.py` | 80 | keep_mainline | 断路器 |

### 2.2 MedCodER / 中国编码体系资产 (keep_mainline 或 keep_experimental)

| 服务 | LOC | 标签 | 理由 |
|---|---|---|---|
| `icd10cn_loader.py` | 290 | keep_mainline | ICD-10-CN catalog loader (中国编码替换) |
| `icd9cm3_loader.py` | 233 | keep_mainline | ICD-9-CM-3-CN loader (中国手术码) |
| `medcoder_index_health.py` | 260 | keep_mainline | FAISS index 健康检查 (E1.10 加固) |
| `code_dictionary.py` | 472 | keep_mainline | Code dictionary (coding_differentiation_kb) |
| `rule_engine.py` | 246 | keep_mainline | RuleEngine (Corti Compliance Guardrail 对应) |
| `llm_service.py` | 265 | keep_mainline | LLM 服务 (DeepSeek 默认, env 可配) |
| `llm_adapter.py` | 209 | keep_mainline | LLM 适配器 |
| `llm_planner.py` | 209 | keep_mainline | LLM planner (Corti Orchestrator 推理) |

### 2.3 MedCodER 专用 / 评估资产 (deprecate or keep_experimental)

| 服务 | LOC | 标签 | 理由 |
|---|---|---|---|
| `agent_runner.py` | 1047 | deprecate | Legacy AgentRunner, 被新 `app/icoder/agent_runtime/orchestrator/` 取代, 但仍被引用 |
| `runtime.py` | 702 | migrate | Legacy runtime, 部分被 `runtime_platform.py` 取代 |
| `drg_kb.py` | 727 | keep_experimental | DRG 知识库, CN-DRG 实验性 |
| `evidence_ranker.py` | 562 | keep_experimental | Evidence 排序, MedCodER Stage 4 rerank |
| `drg_analyzer_service.py` | 430 | keep_experimental | DRG 分析, 实验性 |
| `stt_service.py` | 415 | keep_mainline | STT 服务 (Corti STT 对齐) |
| `drg_grouper.py` | 381 | keep_experimental | DRG 分组器 |
| `speaker_diarizer.py` | 363 | keep_experimental | 说话人分离, Corti Streams 也用 |
| `confidence_calibrator.py` | 360 | keep_experimental | 置信度校准 (MedCodER Stage 5) |
| `review_coding_service.py` | 326 | deprecate | Review coding 服务, 应迁到 v2_tools |
| `gold_case_importer.py` | 324 | deprecate | Gold case 导入, MedCodER 评估专用 |
| `stt_finetune.py` | 323 | deprecate | STT 微调, 非主线 (CLAUDE.md 不做模型训练) |
| `disagreement_analyzer.py` | 319 | keep_experimental | 分歧分析, MedCodER Stage 4 |
| `reasoning_report_builder.py` | 302 | keep_experimental | 推理报告, MedCodER CoT |
| `ccl2026_importer.py` | 221 | deprecate | CCL2026 数据集导入, 评估专用 |
| `gold_case_template.py` | 231 | deprecate | Gold case 模板 |
| `inter_rater.py` | 193 | deprecate | Inter-rater 评估 |
| `pilot_report_builder.py` | 176 | deprecate | Pilot 报告 |
| `clinical_triage.py` | 195 | keep_experimental | 临床分诊, 对应 Corti Triage Agent (Pre-built #9) |
| `punctuation_service.py` | 154 | keep_mainline | STT 标点 |
| `agent_analytics.py` | 92 | keep_mainline | Agent 分析 |

### 2.4 推荐操作

- **删 (deprecate)**: `agent_runner.py` (1047 LOC, 最大单体, 被新 orchestrator 取代), `review_coding_service.py`, `gold_case_importer.py`, `gold_case_template.py`, `inter_rater.py`, `pilot_report_builder.py`, `ccl2026_importer.py`, `stt_finetune.py`
- **迁 (migrate)**: `runtime.py` → 合并 `runtime_platform.py`
- **保 (keep_mainline)**: Agentic Framework + MedCodER 主线 + 中国编码
- **保 (keep_experimental)**: DRG 系列 + 评估相关 (但不在主线)

---

## 3. Backend Agent Architecture (三套并存)

### 3.1 新 Agentic Framework (`app/icoder/agent_runtime/`) — keep_mainline

| 子目录 | 文件数 | 标签 | 理由 |
|---|---|---|---|
| `a2a/` | 13 | keep_mainline | A2A 协议 (envelope/agent_card/messages/parts/routes_inbound/outbound/discovery/task_stub) — Corti §11 A2A 完整对齐 |
| `context/` | 11 | keep_mainline | Context/Memory (context_id/lifecycle/isolation/garbage_collector/repository/audit) — Corti §11 Memory 对齐 |
| `experts/` | 5 | keep_mainline | 5 atomic experts (coding_expert, code_reconciler, evidence_extractor, index_navigator, tabular_validator) — MedCodER Stage 1-5 真实 impl |
| `orchestrator/` | 13 | keep_mainline | Orchestrator (state_machine/planner/delegator/aggregator/events/metrics/phi_redactor/recorder_adapter/run_context/wiring) — Corti §11.4 对齐 |
| `mcp/handlers/` | 5 | keep_mainline | MCP tool handlers (search_icd/verify_code/get_differentiation_hint/rerank_codes/calibrate_confidence) — Corti MCP 对齐 |

### 3.2 Legacy 单体 Agent (`app/agents/`) — deprecate / migrate

| 文件 | LOC | 标签 | 理由 |
|---|---|---|---|
| `app/agents/orchestrator.py` | (大) | deprecate | Legacy 单体 orchestrator, 引用 `homepage_expert`, 应被 `app/icoder/agent_runtime/orchestrator/` 取代 |
| `app/agents/base.py` | (小) | deprecate | Legacy BaseExpert 抽象 |
| `app/agents/experts/homepage_expert.py` | 664 | deprecate | 最大 legacy expert (MedicalRecordHomepageExpert), P1.2 应删但被 orchestrator 引用, 需先迁 |
| `app/agents/experts/diagnosis_expert.py` | 267 | deprecate | Legacy diagnosis expert |
| `app/agents/experts/procedure_expert.py` | 229 | deprecate | Legacy procedure expert |
| `app/agents/experts/timeline_expert.py` | 228 | deprecate | Legacy timeline expert |
| `app/agents/experts/drg_expert.py` | 205 | deprecate | Legacy DRG expert |
| `app/agents/experts/evidence_expert.py` | 126 | deprecate | Legacy evidence expert |
| `app/agents/experts/audit_expert.py` | 110 | deprecate | Legacy audit expert |
| `app/agents/experts/hcc_expert.py` | 85 | deprecate | Legacy HCC expert |
| `app/agents/experts/cdi_expert.py` | 84 | deprecate | Legacy CDI expert |
| `app/agents/experts/denial_expert.py` | 83 | deprecate | Legacy denial expert |
| `app/agents/experts/report_expert.py` | 342 | deprecate | Legacy report expert |

**关键问题**: `app/agents/orchestrator.py` 仍引用 `homepage_expert`, 而 `homepage_expert` 是 P1.2 已删概念 (homepage_coding_review) 的核心, **必须先断引用再删**.

### 3.3 Legacy icoder_runtime/ — deprecate or migrate

| 路径 | LOC | 标签 | 理由 |
|---|---|---|---|
| `icoder_runtime/agent_runner.py` | 1047 | deprecate | 与 `app/services/agent_runner.py` 重复, 都是被新 orchestrator 取代 |
| `icoder_runtime/agent_pack.py` | (中) | keep_mainline | AgentPackageV1 pack 格式, 保留 |
| `icoder_runtime/agent_pack_v1.py` | (中) | keep_mainline | 同 |
| `icoder_runtime/contract_engine.py` | (中) | keep_mainline | Contract engine (与 app/services/contract_engine.py 重复, 需合并) |
| `icoder_runtime/guardrails.py` | (中) | keep_mainline | 同 (与 app/services/guardrails.py 重复) |
| `icoder_runtime/permissions.py` | (中) | keep_mainline | 同 (与 app/services/permissions.py 重复) |
| `icoder_runtime/tool_registry.py` | (中) | keep_mainline | 同 (与 app/services/tool_registry.py 重复) |
| `icoder_runtime/core/` | 15 files | keep_mainline | Pack loader / registry / runtime_result / llm_gateway / data_policy / evidence_parser / pii_redaction — Corti 对齐 |
| `icoder_runtime/constants/` | (小) | keep_mainline | 常量提升 (D3 阶段) |
| `icoder_runtime/observability/` | (小) | keep_mainline | 可观测性 |
| `icoder_runtime/providers/` | (小) | keep_mainline | LLM provider 路由 |
| `icoder_runtime/reports/` | (小) | keep_experimental | 报告 |
| `icoder_runtime/embedded/` | (小) | keep_mainline | Embedded assistant |
| `icoder_runtime/serve.py` | (中) | keep_mainline | CLI serve |
| `icoder_runtime/cli.py` | (中) | keep_mainline | CLI 入口 |
| `icoder_runtime/sandbox.py` | (中) | deprecate | Sandbox 概念, 无 Corti 等价 |
| `icoder_runtime/symbolic_state.py` | (中) | deprecate | Symbolic state, 实验性 |
| `icoder_runtime/dashboard.html` | (小) | delete_candidate | Standalone HTML dashboard, 无 Corti 等价, 前端有 AgentsPage 替代 |
| `icoder_runtime/m2a/` | (空) | delete_candidate | 空目录, 概念已弃 |
| `icoder_runtime/methods/` | (空) | delete_candidate | P1.2 已删 10 builtin methods, 仅剩 __pycache__ |
| `icoder_runtime/types.py` | (小) | keep_mainline | 类型定义 |
| `icoder_runtime/ISV-GUIDE.md` | (doc) | keep_mainline | ISV 指南 |
| `icoder_runtime/pyproject.toml` | (config) | keep_mainline | Python 包配置 |
| `icoder_runtime/tests/` | (tests) | keep_mainline | 测试 |

### 3.4 compliance_services/ — keep_mainline

| 文件 | LOC | 标签 | 理由 |
|---|---|---|---|
| `rule_engine.py` | (中) | keep_mainline | RuleEngine 主体 |
| `medical_coding_rules.py` | (中) | keep_mainline | ICD-10/ICD-9-CM-3 编码规则 (R001-R010 + MC-R-M80-001) |
| `drg_dip_rules.py` | (中) | keep_experimental | CN-DRG/DIP 规则 (中国医院需要) |
| `insurance_rules.py` | (中) | keep_experimental | 医保审核规则 |
| `medcoder_retrieval_rules.py` | (中) | keep_mainline | MedCodER retrieval 规则 |

---

## 4. Official Agent Packs (`backend/official_agents/`)

16 个 agent pack 目录, 但只有 2 个是真实 Agent 实现:

### 4.1 真实 Agent (keep_mainline)

| Pack | 文件数 | 标签 | 理由 |
|---|---|---|---|
| `medical_coding/` | 5 (agent_pack.json + modes.py + schema.py + __init__.py) | keep_mainline | Medical Coding Agent 主线 (Corti Pre-built #18) |
| `medcoder-coding-review/` | 1 (agent_pack.json) | keep_mainline | MedCodER Coding Review Agent (5-stage NAACL 2025 pipeline) |

### 4.2 Metadata-only packs (4 expert-stub packs from D2)

| Pack | 文件数 | 标签 | 理由 |
|---|---|---|---|
| `evidence_extractor/` | 1 (agent_pack.json) | keep_mainline | MedCodER Stage 1 atomic expert, format_version=1.2, experts[] 引用 `evidence_extractor_expert.py` |
| `index_navigator/` | 1 (agent_pack.json) | keep_mainline | MedCodER Stage 2 atomic expert |
| `code_reconciler/` | 1 (agent_pack.json) | keep_mainline | MedCodER Stage 4 atomic expert |
| `tabular_validator/` | 1 (agent_pack.json) | keep_mainline | MedCodER Stage 5 atomic expert |

### 4.3 Reference / 规划中 packs (unclear or delete_candidate)

| Pack | 文件数 | 标签 | 理由 |
|---|---|---|---|
| `cdi-review/` | 1 | keep_mainline | 对应 Corti Pre-built #20 CDI Agent |
| `code-validation/` | 1 | keep_mainline | 对应 Corti Pre-built #4 Code Validation Agent |
| `compliance-guardrail/` | 1 | keep_mainline | 对应 Corti Pre-built #3 Compliance Guardrail Agent |
| `denial-appeals/` | 1 | keep_mainline | 对应 Corti Pre-built #12 Denial Appeals Agent |
| `diagnosis-extractor/` | 1 | keep_mainline | 对应 Corti Pre-built #6 Diagnostic Entity Extractor Agent |
| `documentation-gap/` | 1 | keep_mainline | 对应 Corti Pre-built #10 Note Completeness Agent (gap detection) |
| `evidence-ranker/` | 1 | keep_mainline | MedCodER Stage 4 rerank |
| `note-completeness/` | 1 | keep_mainline | 对应 Corti Pre-built #10 Note Completeness Agent |
| `procedure-extractor/` | 1 | keep_mainline | 对应 Corti Pre-built #5 Procedure Entity Extractor Agent |
| `drg-analyzer/` | 3 | keep_experimental | DRG 分析, 中国医院需要 |

**关键判断**: 16 packs 中 10 个对应 Corti Pre-built Agents, 但只是 metadata (agent_pack.json), 需要在 Phase 3 实装真实 Python impl. 当前**没有任何 pack 对应 Corti 17 个缺失 Pre-built Agents** (ICU Admission/Triage/Medication Reconciliation/Patient Discharge Education/Nursing Shift Handoff/Prior Authorization/Referral Generator/Clinical Education/Clinical Guidelines/Surgical Registry/Rule Explainer/Index Navigator 等).

---

## 5. Frontend Pages (`frontend/src/pages/`)

### 5.1 Corti-aligned 主线 (keep_mainline)

| 页面 | LOC | 标签 | 理由 |
|---|---|---|---|
| `HomePage.tsx` | 181 | keep_mainline | Corti Project Home 4 tabs (Transcribe/Document/Chat/Code) |
| `AIStudioOverviewPage.tsx` | 76 | keep_mainline | Corti AI Studio Overview |
| `AgentsPage.tsx` | 686 | keep_mainline | Corti `/ai-studio/agents` (Pre-built + My agents) |
| `AgentDetailPage.tsx` | 1286 | keep_mainline | Corti agent preview + Customize |
| `NewAgentPage.tsx` | 337 | keep_mainline | Corti `/ai-studio/agents/new` (Start from scratch + Use a template) |
| `MedicalCodingPage.tsx` | 760 | keep_mainline | Corti `/ai-studio/medical-coding` (Input/Output/Event Inspector) |
| `FactExtractionPage.tsx` | 468 | keep_mainline | Corti `/ai-studio/fact-extraction` |
| `TextGenerationPage.tsx` | 570 | keep_mainline | Corti `/ai-studio/text-generation` |
| `SpeechToTextPage.tsx` | 557 | keep_mainline | Corti `/ai-studio/speech-to-text` (3 子 tab) |
| `EmbeddedAssistantPage.tsx` | 714 | keep_mainline | Corti `/ai-studio/embedded-assistant` |
| `APIClientsPage.tsx` | 205 | keep_mainline | Corti `/api-clients` |
| `TeamPage.tsx` | 211 | keep_mainline | Corti `/team` |
| `BillingPage.tsx` | 383 | keep_mainline | Corti `/billing` |
| `UsagePage.tsx` | 244 | keep_mainline | Corti `/usage` |
| `CustomersPage.tsx` | 422 | keep_mainline | Corti `/customers` (Loop 1) |
| `TemplatesPage.tsx` | 420 | keep_mainline | Corti `/templates` Beta (Loop 2) |
| `SettingsPage.tsx` | 513 | keep_mainline | Corti `/settings` |
| `TicketsPage.tsx` | 416 | keep_mainline | Corti Tickets Portal (Loop 9 in-app 等价) |
| `DeveloperQuickstartPage.tsx` | 331 | keep_mainline | Corti `/developer-quickstart` |
| `DocsPage.tsx` | 153 | keep_mainline | Corti Docs link |
| `ReleaseNotesPage.tsx` | 97 | keep_mainline | Release notes |
| `LoginPage.tsx` | 168 | keep_mainline | Login |
| `ResetPasswordPage.tsx` | 73 | keep_mainline | Reset password |
| `SupportPage.tsx` | 59 | keep_mainline | Corti Get Help |

### 5.2 iCoDer-specific 无 Corti 等价 (deprecate or unclear)

| 页面 | LOC | 标签 | 理由 |
|---|---|---|---|
| `EvaluationPage.tsx` | 265 | deprecate | F1 评估页, 非 Corti 方向, 应降级或删 |
| `GoldCasesPage.tsx` | 272 | deprecate | Gold case 管理, MedCodER 评估专用 |
| `ExpertLibraryPage.tsx` | 604 | deprecate | iCoDer Expert Library, Corti 用 Pre-built Agents + MCP, 概念已被取代 |
| `OrchestrationPage.tsx` | 266 | deprecate | Orchestration 控制台, Corti 无此独立页 (orchestration 是内核, 不是 UI) |
| `EmbedDemoCodingReviewPage.tsx` | 225 | deprecate | Demo 页, 应整合到 `EmbeddedAssistantPage` |
| `EmbedDemoCodingReviewPage.tsx.bak` | — | delete_candidate | 备份文件, 直接删 |

---

## 6. Frontend Components

### 6.1 Corti-aligned 主线 (keep_mainline)

| 路径 | 标签 | 理由 |
|---|---|---|
| `components/layout/Layout.tsx` | keep_mainline | Sidebar + Topbar 布局 |
| `components/layout/OrgSwitcher.tsx` | keep_mainline | 项目切换 (Corti "Your Projects") |
| `components/common/CodeSnippet.tsx` | keep_mainline | 代码块 (Corti style) |
| `components/common/ErrorBoundary.tsx` | keep_mainline | 错误边界 |
| `components/common/EventInspector.tsx` | keep_mainline | Event Inspector (Corti 工作台底部日志面板, 已对齐) |
| `components/common/SettingsCodeTab.tsx` | keep_mainline | Settings/Code tab 切换 (Corti 工作台右侧) |
| `components/common/Toast.tsx` | keep_mainline | Toast 通知 (Corti 右下浮动) |
| `components/medical-coding/DiagnosisCard.tsx` | keep_mainline | Per-disease 卡片 (MedCodER Stage 1 输出) |
| `components/medical-coding/EvidenceHighlighter.tsx` | keep_mainline | Evidence char span 高亮 |
| `components/medical-coding/HighlightedTextarea.tsx` | keep_mainline | Overlay 高亮 textarea (cycle 19) |
| `components/medical-coding/TopKChips.tsx` | keep_mainline | Top-K 候选 chips |
| `components/agents/ToolSelector.tsx` | keep_mainline | Tool 选择器 |
| `components/A2ACollaboration.tsx` | keep_mainline | A2A 协作可视化 |
| `components/AddExpertModal.tsx` | keep_mainline | 添加 Expert modal |
| `components/EditSystemPromptModal.tsx` | keep_mainline | 编辑 system prompt modal |
| `components/ExpertLibraryModal.tsx` | deprecate | Expert Library modal (与 ExpertLibraryPage 同命运) |
| `components/embed/IcoderEvidenceViewer.tsx` | keep_mainline | 嵌入第三方页用 |
| `components/embed/IcoderReviewPanel.tsx` | keep_mainline | 同 |
| `components/embed/IcoderTraceViewer.tsx` | deprecate | 包装 RunTraceTimeline, 与 RunTrace 同命运 |

### 6.2 Legacy components (deprecate or delete_candidate)

| 路径 | 标签 | 理由 |
|---|---|---|
| `components/icoder/RunTraceTimeline.tsx` | deprecate | RunTrace 概念 P1.2 应删, 仍被 embed 包装引用 |
| `components/icoder/EvidenceViewer.tsx` | unclear | 与 medical-coding/EvidenceHighlighter 重复, 需合并 |
| `components/icoder/HighRiskCodingPointPanel.tsx` | unclear | 高风险编码点面板, MedCodER 内部概念 |
| `components/medical-coding/MethodTraceViewer.tsx` | deprecate | Method trace 概念 P1.2 已删, 但 component 还在 |
| `components/orchestration/AgentTraceViewer.tsx` | deprecate | Legacy orchestration UI |
| `components/orchestration/AuditTrailViewer.tsx` | deprecate | Legacy audit trail (Corti 用 Event Inspector) |
| `components/orchestration/EncounterSelector.tsx` | deprecate | Encounter 选择器, 概念无 Corti 等价 |
| `components/orchestration/HumanReviewGate.tsx` | deprecate | Human review gate, 应降级为 Pre-built Agent |
| `components/orchestration/PipelineProgress.tsx` | deprecate | Pipeline 进度, MedCodER 14-stage 概念 |
| `components/orchestration/ReviewResults.tsx` | deprecate | Review 结果展示 |
| `components/orchestration/RuntimeMonitor.tsx` | deprecate | Runtime 监控, Corti 用 Event Inspector |

---

## 7. Frontend Services / Hooks / Store / Utils

| 路径 | 标签 | 理由 |
|---|---|---|
| `services/api.ts` (`runtimeStatusApi` + others) | keep_mainline | 主 API 客户端 (Cycle 25 已 rename) |
| `services/runtimeApi.ts` (`runtimeAgentApi`) | keep_mainline | Runtime agent API (Cycle 25 已 rename) |
| `services/agentHubApi.ts` | migrate | Agent Hub API, 应迁到 agent_definitions 命名 |
| `services/icoderCodingReviewApi.ts` | deprecate | Legacy coding review API |
| `services/__tests__/apiContract.test.ts` | keep_mainline | Cycle 25 加的 OpenAPI contract test |
| `hooks/useReviewPipeline.ts` | deprecate | Review pipeline hook, MedCodER 内部 |
| `store/index.ts` | keep_mainline | Zustand store |
| `utils/errors.ts` | keep_mainline | 错误码定义 (含 MARKETPLACE_ERROR 但 Marketplace 已删, 需清理) |
| `utils/stt-punctuation.ts` | keep_mainline | STT 标点 |
| `config.ts` | keep_mainline | 配置 |
| `i18n/` | keep_mainline | 国际化 |
| `types/` | keep_mainline | 类型定义 |

---

## 8. Documentation Assets

### 8.1 Corti-parity 主线 (keep_mainline)

| 路径 | 标签 | 理由 |
|---|---|---|
| `docs/corti_parity/` (含本 inventory + baseline) | keep_mainline | P1.3 输出目录 |
| `docs/corti-reverse-engineered/` (含 SUMMARY.md + api-contracts-v2.json + 49 截图 + 15 feature summary + docs-site 提取) | keep_mainline | Corti 参考基准 (Stage 0 来源) |
| `docs/corti-feature-inventory.md` | keep_mainline | 20 Pre-built Agents 清单 + 15 页面走查 |
| `docs/cloud/` (4 文件: CLOUD_DEPLOYMENT/API_CLIENT_MODEL/MULTI_REGION/CLOUD_INTAKE_TEMPLATE) | keep_mainline | 托管云 SaaS 主线 (cloud flip) |
| `docs/openapi/` (openapi.json + path_whitelist + reasons) | keep_mainline | Cycle 25 加的 OpenAPI 契约 |
| `docs/dev/BACKEND_RECOVERY.md` | keep_mainline | Cycle 23 backend recovery runbook |
| `docs/specs/AGENT_PACK_SPEC_V1_2.md` | keep_mainline | Agent pack 1.2 spec |
| `docs/phase_cycles/` (cycle_2 → cycle_24, 24 cycle 报告) | keep_mainline | Phase 1.2/1.3/2 实施记录 (闭环) |
| `docs/sdk/` (js.md + python.md) | keep_mainline | SDK 文档 |
| `docs/CLAUDE.md` (项目根) | keep_mainline | 项目说明 (本文件) |
| `docs/README.md` | keep_mainline | 文档入口 |
| `docs/VERSION` + `docs/CHANGELOG.md` | keep_mainline | 版本 |

### 8.2 Corti-parity 历史 / 应归档 (archive_docs)

| 路径 | 标签 | 理由 |
|---|---|---|
| `docs/Corti_Console_Complete_Analysis_2026-05-15.md` | archive_docs | 旧 Corti 分析 (corti-reverse-engineered 已替代) |
| `docs/Corti_Console_Page_Inventory_2026-05-18.md` | archive_docs | 同 |
| `docs/Corti_Console_Redesign_2026-05-16_Analysis.md` | archive_docs | 同 |
| `docs/Corti_Embedded_Assistant_vs_iCoDer_Analysis.md` | archive_docs | 同 |
| `docs/Corti_Feature_List_Complete.md` | archive_docs | 同 |
| `docs/Corti_vs_iCoDer_Complete_Comparison.md` | archive_docs | 同 |
| `docs/Corti_vs_iCoDer_Gap_Analysis_2026-05-19.md` | archive_docs | 同 |
| `docs/Corti_vs_iCoDer_Gap_Analysis_and_Roadmap.md` (2026-05-08) | archive_docs | 同 |
| `docs/Corti_vs_iCoDer_MedicalCoding_Comparison.md` | archive_docs | 同 |
| `docs/2026-05-08_Corti_vs_iCoDer_Gap_Analysis_and_Roadmap.md` | archive_docs | 同 |
| `docs/corti-screens/` (AI Studio 等截图 _analysis.txt) | archive_docs | 早期截图分析, 已被 corti-reverse-engineered/feature-flows 替代 |

### 8.3 iCoDer 历史阶段报告 (archive_docs)

| 路径 | 标签 | 理由 |
|---|---|---|
| `docs/PHASE5_LOCAL_DEV_CI_REPORT.md` | archive_docs | Phase 5 历史 |
| `docs/PHASE6_PILOT_DATA_EVALUATION_REPORT.md` | archive_docs | Phase 6 pilot |
| `docs/PHASE10_GOLD_CASE_VALIDATION.md` | archive_docs | Phase 10 |
| `docs/PHASE11A_REGRESSION_STABILIZATION.md` | archive_docs | Phase 11A |
| `docs/PHASE11B_GOLD_CASE_QUALITY.md` | archive_docs | Phase 11B |
| `docs/PHASE11C_GOLD_CASE_IMPORTER.md` | archive_docs | Phase 11C |
| `docs/PHASE11D_PILOT_EVALUATION_RUNBOOK.md` | archive_docs | Phase 11D |
| `docs/SPRINT9B_PRINCIPAL_DIAGNOSIS_REASONING.md` | archive_docs | Sprint 9B |
| `docs/SPRINT9C_EVIDENCE_RANKING.md` | archive_docs | Sprint 9C |
| `docs/SPRINT9D_DISAGREEMENT_REASONING.md` | archive_docs | Sprint 9D |
| `docs/SPRINT9E_CONFIDENCE_CALIBRATION.md` | archive_docs | Sprint 9E |
| `docs/SPRINT_A_CODING_WORKBENCH_ERGONOMICS.md` | archive_docs | Sprint A |
| `docs/SPRINT_B_HUMAN_REVIEW_COCKPIT.md` | archive_docs | Sprint B |
| `docs/SPRINT_C_CASE_REASONING_PRESENTATION.md` | archive_docs | Sprint C |
| `docs/SPRINT_D_PILOT_EVALUATION_EXPERIENCE.md` | archive_docs | Sprint D |
| `docs/PILOT_ACCEPTANCE_CHECKLIST.md` | archive_docs | Pilot |
| `docs/PILOT_DELIVERABLE_PACKAGE.md` | archive_docs | Pilot |
| `docs/PILOT_DEMO_SCRIPT.md` | archive_docs | Pilot |
| `docs/PILOT_EVALUATION_ACCEPTANCE_THRESHOLDS.md` | archive_docs | Pilot |
| `docs/PILOT_ISSUE_TEMPLATE.md` | archive_docs | Pilot |
| `docs/PILOT_KNOWN_LIMITATIONS.md` | archive_docs | Pilot |
| `docs/M3_HOMEPAGE_CODING_REVIEW_AGENT_SPEC.md` | archive_docs | M3 (homepage_coding_review P1.2 已删) |
| `docs/M3_PRODUCT_E2E_VALIDATION_REPORT.md` | archive_docs | M3 |
| `docs/ICODER_M3_SECURITY_AND_AUDIT_SPEC.md` | archive_docs | M3 |
| `docs/P0_Gap_Closure_Plan.md` | archive_docs | P0 |
| `docs/P0_QUALITY_GATE_REPORT.md` | archive_docs | P0 |
| `docs/EVALUATION_BASELINE_REPORT.md` | archive_docs | F1 baseline (CLAUDE.md 已降级非主线) |
| `docs/E2E_TEST_DISCOVERY.md` | archive_docs | E2E test |
| `docs/E2E_TEST_MATRIX.md` | archive_docs | E2E test |
| `docs/E2E_TEST_PLAN.md` | archive_docs | E2E test |
| `docs/CASE_REASONING_REPORT.md` | archive_docs | Case reasoning |
| `docs/CODING_REVIEW_WORKFLOW_DELIVERY.md` | archive_docs | Coding review workflow (P1.2 已删概念) |
| `docs/FRONTEND_FAKE_FEATURES_AUDIT.md` | archive_docs | Frontend fake features audit |
| `docs/ICODER_CAPABILITY_MAP.md` | archive_docs | Capability map |
| `docs/iCoDer_Convergence_Audit_2026-05-11.md` | archive_docs | Convergence audit |
| `docs/iCoDer_Convergence_Audit_2026-05-15.md` | archive_docs | 同 |
| `docs/iCoDer_Convergence_Audit_2026-05-16.md` | archive_docs | 同 |
| `docs/iCoDer_Governance_Blueprint_2026-05-11.md` | archive_docs | Governance blueprint |
| `docs/iCoDer_vs_Corti_Complete_Comparison_2026-05-18.md` | archive_docs | Convergence |
| `docs/audit_remediation/` (5 E1.x 报告) | archive_docs | E1.x 历史 (MedCodER Stage 1-5 wiring) |
| `docs/experiments/E2_0_NEGATIVE_SIGNAL_ARCHIVE.md` | archive_docs | E2.0 few-shot 负信号存档 |
| `docs/productization/` (P1.0 + P1.1 baseline) | archive_docs | P1.0/P1.1 历史 |

### 8.4 规格文档 (keep_mainline 或 keep_experimental)

| 路径 | 标签 | 理由 |
|---|---|---|
| `docs/ICODER_V1_A2A_SPEC.md` | keep_mainline | A2A spec (Corti §11 对齐) |
| `docs/ICODER_V1_AGENT_CARD_SPEC.md` | keep_mainline | Agent Card spec |
| `docs/ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` | keep_mainline | Runtime architecture RFC |
| `docs/ICODER_V1_CONTEXT_SPEC.md` | keep_mainline | Context spec |
| `docs/ICODER_V1_MCP_SPEC.md` | keep_mainline | MCP spec |
| `docs/ICODER_V1_ORCHESTRATOR_SPEC.md` | keep_mainline | Orchestrator spec |
| `docs/ICODER_V1_TASK_SPEC.md` | keep_mainline | Task spec |
| `docs/CORTI_STYLE_GAP_ANALYSIS.md` | keep_mainline | Corti-style gap analysis (本 P1.3 前置) |
| `docs/CORTI_STYLE_PRODUCT_MODEL.md` | keep_mainline | Corti-style 产品模型 |
| `docs/CORTI_STYLE_REMEDIATION_ROADMAP.md` | keep_mainline | Corti-style remediation |
| `docs/PHASE_1_1_MEDICAL_CODING_PATH_SCHEMA.md` | keep_mainline | Phase 1.1 实施记录 |
| `docs/PHASE_1_2_*.md` (5 个 cycle 报告) | keep_mainline | Phase 1.2 实施记录 |
| `docs/PHASE_1_3_*.md` (13 个 cycle 报告) | keep_mainline | Phase 1.3 实施记录 |
| `docs/PHASE_2_CYCLE*.md` (6 个) | keep_mainline | Phase 2 实施记录 |
| `docs/PRODUCT-MODULES.md` | keep_mainline | 产品模块 |
| `docs/PRODUCT-ROADMAP.md` | keep_mainline | 产品路线图 |
| `docs/ARCHITECTURE.md` | keep_mainline | 架构 |
| `docs/TECHNICAL-DESIGN.md` | keep_mainline | 技术设计 |
| `docs/DESIGN.md` | keep_mainline | 设计 |
| `docs/runtime.md` | keep_mainline | Runtime |
| `docs/agent-pack.md` | keep_mainline | Agent pack |
| `docs/SDK-TUTORIAL.md` | keep_mainline | SDK 教程 |
| `docs/QUICKSTART.md` | keep_mainline | Quickstart |
| `docs/SOLUTION-SCENARIOS.md` | keep_mainline | 解决方案场景 |
| `docs/operation-manual/` (22 文件 + SUMMARY) | keep_mainline | 操作手册 (15+ 页面) |
| `docs/backlog/CODING_QUALITY_BACKLOG.md` | keep_experimental | Coding quality backlog (非主线) |
| `docs/Figma_Design_Prompt_CodeTable_Manager.md` | archive_docs | Figma 设计 prompt |
| `docs/document-aggregation-agent-design.md` | keep_experimental | Document aggregation agent 设计 |
| `docs/knowledge-base-product-design.md` | keep_experimental | Knowledge base 设计 |
| `docs/icoder-signit-integration-blueprint.md` | keep_experimental | 易企签集成蓝图 |
| `docs/Runtime_Discipline_Delivery_2026-05-12.md` | archive_docs | Runtime discipline |
| `docs/Runtime_Persistence_Delivery_2026-05-12.md` | archive_docs | Runtime persistence |

### 8.5 Repo-root extras (deprecate / delete_candidate / archive_docs)

| 路径 | 标签 | 理由 |
|---|---|---|
| `Corti/` (含 `Corti.ai 核心竞争力调研报告.pdf` + `llms-full.txt`) | archive_docs | 早期 Corti 调研, 已被 corti-reverse-engineered 替代 |
| `corti-crawl/` (content/ + cookies.json + index.json + screenshots/) | archive_docs | 早期 crawler 输出, 已被 corti-reverse-engineered 替代 |
| `corti_contracts/` (coding_icoder_request.json + coding_icoder_response.json) | archive_docs | 早期契约, 已被 corti-reverse-engineered/api-contracts-v2.json 替代 |
| `corti_ui_contracts/` (medical-coding.VERIFIED_OK + medical-coding.json) | archive_docs | 早期 UI 契约, 已被 phase_cycles/cycle_19_ui_medical_coding 替代 |
| `icoder-next/` (整个子项目: backend/ + frontend/ + docs/ + README.md) | deprecate | Pivot memory 2026-06-17 已逆转: icoder-next 切片不再是开发载体, 应归档或删 |
| `.corti-user-data/` (Chrome browser profile: BrowserMetrics/Crashpad/Default/...) | delete_candidate | 浏览器用户数据误入仓库, 应立即 .gitignore + 删 |
| `iCoDer_Medical_Coding_Agent_PRD_V1.0.md` (repo root) | archive_docs | 早期 PRD |
| `icoder-mockup-variant-A.html` (repo root) | archive_docs | 早期 mockup |
| `train(2).xlsx` (repo root) | archive_docs | 训练数据 |
| `postman/` (iCoDer_API_Collection.json + iCoDer.postman_collection.json + README.md) | keep_experimental | Postman 集合, 保留 |
| `deploy/cloud/` | keep_mainline | 云部署 |
| `reports/` | keep_experimental | 报告 |
| `golden_captures/` | archive_docs | Golden captures |
| `public/` | keep_mainline | 前端 public |
| `screenshots/` (20 Corti 截图 _analysis.txt + Agentsample.jpg) | archive_docs | 早期截图, 已被 corti-reverse-engineered/feature-flows 替代 |
| `.tmp_run.json` / `.tmp_agent_run.json` / `backend/.tmp_run.json` | delete_candidate | 临时运行文件, 应 .gitignore + 删 |

### 8.6 Data files (`backend/data/`)

| 路径 | 标签 | 理由 |
|---|---|---|
| `backend/data/icoder.db` | keep_mainline | 主 SQLite DB |
| `backend/data/icoder.db.bak2` | delete_candidate | 备份 (cycle 23 已识别为 stale alembic=002) |
| `backend/data/icoder.db.bak20260701` | delete_candidate | 备份 (cycle 23 已识别为全 DROP 0 表) |
| `backend/data/icoder.db.broken-20260702` | delete_candidate | 损坏 DB |
| `backend/data/test.db` | delete_candidate | 测试 DB (应 CI 用 in-memory) |
| `backend/data/medcoder/` | keep_mainline | BGE-M3 + FAISS index + metadata |
| `backend/data/code_dicts/` | keep_mainline | Code dictionary 数据 |
| `backend/data/medical_hotwords.txt` | keep_mainline | STT hotwords |
| `backend/data/versions.json` | keep_mainline | 版本记录 |

---

## 9. Scripts

| 路径 | 标签 | 理由 |
|---|---|---|
| `scripts/corti_deep_crawler.py` | keep_mainline | Corti 深度 crawler (Stage 0 来源) |
| `scripts/corti_docs_crawler.py` | keep_mainline | Corti 文档站 crawler |
| `scripts/corti_reverse_engineer.py` | keep_mainline | Corti 逆向工程主脚本 |
| `scripts/corti_reverse_engineer_interact.py` | keep_mainline | Corti 逆向交互版 |
| `scripts/corti_deep_scan.py` | keep_mainline | Corti 深度扫描 (Phase 2 baseline) |
| `scripts/icoder_compare.py` | keep_mainline | iCoDer vs Corti 对比 (Phase 2 baseline) |
| `scripts/icoder_ui_diff.py` | keep_mainline | UI diff (Phase 2 cycle 19+) |
| `scripts/chrome-connect.skill.md` | keep_mainline | Chrome 连接 skill 文档 |
| `scripts/connect-cdp.py` | keep_mainline | CDP 连接脚本 |
| `scripts/launch-chrome-debug.ps1` | keep_mainline | Chrome 调试启动 |
| `scripts/generate-certs.sh` | keep_mainline | 证书生成 |
| `backend/scripts/health_check.py` | keep_mainline | Cycle 25 backend health check |
| `backend/scripts/check_schema_drift.py` | keep_mainline | Cycle 25 schema drift checker |
| `backend/scripts/export_openapi.py` | keep_mainline | Cycle 25 OpenAPI exporter |
| `backend/scripts/build_medcoder_index.py` | keep_mainline | FAISS index 构建 |
| `backend/scripts/e2e_runtime_validation.py` | keep_experimental | E2E runtime 验证 (F1 baseline, CLAUDE.md 已降级非主线) |
| `backend/scripts/e2e_medcoder_validation.py` | keep_experimental | MedCodER 4-variant ablation 验证 |
| `backend/scripts/build_icoder_201_fixture.py` | keep_experimental | iCoDer 201 fixture 构建 |

---

## 10. Packages & SDKs

| 路径 | 标签 | 理由 |
|---|---|---|
| `packages/icoder-sdk/` (TypeScript SDK, src/client.ts + resources + types) | keep_mainline | JS SDK (Corti 有 JS SDK) |
| `packages/icoder-python/` (Python SDK, icoder_sdk/client.py + resources + types) | keep_mainline | Python SDK (Corti 有 .NET SDK, Python 等价) |
| `packages/icoder-embedded/` (src/icoder-assistant.ts) | keep_mainline | Embedded assistant SDK (Corti Embedded Web Components) |
| `packages/icoder-web/` (src + examples + dist) | keep_mainline | Web components (Corti SDKs) |
| `packages/web-components/` (src/icoder-assistant.ts + icoder-speech-to-text.ts + index.ts) | keep_mainline | Web components (Dictation + Ambient) |
| `packages/examples/` (README + 2 postman collection) | keep_mainline | 示例 |
| `web-components/` (repo root, src/icoder-assistant.ts + icoder-speech-to-text.ts) | rename | 与 `packages/web-components/` 重复, 需合并 |

---

## 11. Tests (`backend/tests/`)

| 路径 | 标签 | 理由 |
|---|---|---|
| `tests/unit/` (app/icoder/icoder_runtime/medical_coding/scripts 子目录) | keep_mainline | 单元测试 |
| `tests/test_api/` | keep_mainline | API 测试 |
| `tests/test_services/` | keep_mainline | Service 测试 |
| `tests/test_models/` | keep_mainline | Model 测试 |
| `tests/test_compliance/` | keep_mainline | Compliance 测试 |
| `tests/integration/` | keep_mainline | 集成测试 |
| `tests/e2e/` | keep_mainline | E2E 测试 |
| `tests/e2e_product/` | keep_mainline | 产品 E2E 测试 |
| `tests/regression/` (8 文件: F1/confidence/disagreement/evidence/reasoning/fallback/runtime_recovery) | keep_experimental | 回归测试 (F1 baseline CLAUDE.md 已降级非主线, 但测试保留) |
| `tests/review/` | deprecate | Review 测试, MedCodER 内部 |
| `tests/fixtures/` | keep_experimental | 测试 fixtures (ccl2026_val_100 + icoder_201) |
| `tests/conftest.py` | keep_mainline | pytest 配置 (Cycle 25 已加固) |

---

## 11. 推荐清理优先级 (供 Stage 5 执行)

### P0 — 立即删 (无引用 / 误入仓库 / 备份文件)

1. `.corti-user-data/` (Chrome 浏览器 profile, 误入仓库)
2. `backend/data/icoder.db.bak2` / `icoder.db.bak20260701` / `icoder.db.broken-20260702` (stale 备份)
3. `backend/data/test.db` (CI 用 in-memory 即可)
4. `.tmp_run.json` / `.tmp_agent_run.json` / `backend/.tmp_run.json` (临时文件)
5. `frontend/src/pages/EmbedDemoCodingReviewPage.tsx.bak` (备份文件)
6. `icoder_runtime/methods/` (空目录 + __pycache__)
7. `icoder_runtime/m2a/` (空目录)

### P1 — 归档 (historical docs, 不删但移到 archive/)

1. `docs/Corti_*.md` + `docs/2026-05-08_Corti*.md` (10 个旧 Corti 分析)
2. `docs/PHASE5/6/10/11*.md` + `docs/SPRINT*.md` + `docs/PILOT*.md` + `docs/M3*.md` (20+ 历史阶段报告)
3. `docs/CASE_REASONING_REPORT.md` + `docs/CODING_REVIEW_WORKFLOW_DELIVERY.md` + `docs/EVALUATION_BASELINE_REPORT.md` + `docs/E2E_TEST_*.md`
4. `docs/iCoDer_Convergence_Audit_*.md` + `docs/iCoDer_Governance_Blueprint_*.md` + `docs/iCoDer_vs_Corti_*.md` + `docs/2026-05-08_*.md`
5. `docs/audit_remediation/` (E1.x 历史)
6. `docs/productization/` (P1.0/P1.1 baseline)
7. `Corti/` (repo root PDF + llms)
8. `corti-crawl/` + `corti_contracts/` + `corti_ui_contracts/` (早期 crawler 输出)
9. `docs/corti-screens/` (早期截图分析)
10. `screenshots/` (repo root 早期截图)
11. `icoder-next/` (整个子项目, pivot 已逆转)
12. `iCoDer_Medical_Coding_Agent_PRD_V1.0.md` + `icoder-mockup-variant-A.html` + `train(2).xlsx` (repo root 早期资料)

### P2 — 标记 deprecated (代码仍在用, 但应迁)

1. `app/agents/orchestrator.py` + `app/agents/experts/homepage_expert.py` (664 LOC, 最大 legacy) — 需先断引用
2. `app/agents/experts/` 其余 10 个 expert (diagnosis/procedure/timeline/drg/evidence/audit/hcc/cdi/denial/report)
3. `app/services/agent_runner.py` (1047 LOC) + `icoder_runtime/agent_runner.py` (重复)
4. `app/services/review_coding_service.py` + `gold_case_importer.py` + `gold_case_template.py` + `inter_rater.py` + `pilot_report_builder.py` + `ccl2026_importer.py` + `stt_finetune.py`
5. `app/api/icoder_coding_review.py` (1283 LOC) + `icoder_agents_hub.py` (1029 LOC) + `icoder_agents_compat.py` + `icoder_registry_compat.py` + `evaluation.py` + `agent_evaluation.py` + `gold_cases.py` + `code_tables.py` + `m2a.py`
6. `frontend/src/pages/EvaluationPage.tsx` + `GoldCasesPage.tsx` + `ExpertLibraryPage.tsx` + `OrchestrationPage.tsx` + `EmbedDemoCodingReviewPage.tsx`
7. `frontend/src/components/orchestration/` (7 legacy components)
8. `frontend/src/components/icoder/RunTraceTimeline.tsx` + `medical-coding/MethodTraceViewer.tsx`
9. `frontend/src/services/icoderCodingReviewApi.ts` + `hooks/useReviewPipeline.ts`
10. `icoder_runtime/dashboard.html` + `sandbox.py` + `symbolic_state.py`

### P3 — 迁移 (migrate, 需先建新再删旧)

1. `app/api/agents.py` + `icoder_agents_hub.py` → 合并迁到 `/rest/v1/agent_definitions` Corti 风格
2. `app/api/runtime.py` → 合并到 `runtime_platform.py`
3. `app/api/text_gen.py` → 合并到 `v2_tools_guided_document.py`
4. `app/api/facts.py` → 合并到 `v2_tools_facts.py`
5. `app/services/runtime.py` → 合并到 `runtime_platform` service
6. `web-components/` (repo root) → 合并到 `packages/web-components/`
7. `frontend/src/services/agentHubApi.ts` → 改名对齐 Corti agent_definitions

### P4 — 保留主线 (keep_mainline, 不动)

- 全部 v2_tools_* API + oauth + runtime_platform
- 全部 Corti-aligned 主线前端 pages (24 个) + 主线 components
- `app/icoder/agent_runtime/` (A2A + Context + Experts + Orchestrator + MCP) — Corti §11 完整对齐
- `icoder_runtime/core/` + `constants/` + `observability/` + `providers/` + `embedded/` + pack loader
- `compliance_services/` (rule_engine + medical_coding_rules + medcoder_retrieval_rules)
- 2 real Agent packs + 4 atomic expert packs + 10 metadata-only packs (对应 Corti Pre-built Agents)
- MedCodER 主线 services (icd10cn_loader/icd9cm3_loader/medcoder_index_health/code_dictionary/rule_engine/llm_*)
- `docs/corti_parity/` + `docs/corti-reverse-engineered/` + `docs/cloud/` + `docs/openapi/` + `docs/dev/` + `docs/specs/` + `docs/phase_cycles/` + `docs/operation-manual/` + `docs/sdk/`
- 全部 ICODER_V1_*_SPEC.md (7 份)
- 5 SDK packages
- 全部 Stage 0 baseline + 本 Stage 1 inventory 输出

---

## 12. 关键差距识别 (供 Stage 2 gap analysis 用)

1. **三套 Agent 架构并存** — Legacy `app/agents/` + Legacy `icoder_runtime/agent_runner` + 新 `app/icoder/agent_runtime/`. 只有第 3 套 Corti-aligned, 但实际运行的是第 1+2 套 (medical_coding pack 走 `icoder_runtime/agent_runner` + `medcoder-coding-review/agent_pack.json`).

2. **API 路径双轨** — Legacy `app/api/icoder_*.py` 4 个大模块 (2286 LOC) vs Corti-aligned `app/api/v2_tools_*.py` 8 个 (4034 LOC). Stage 5 应迁 + 删 legacy.

3. **17 个 Corti Pre-built Agents 缺失** — Corti 20 个 Pre-built Agents, iCoDer 仅有 3 个对应 pack (medical_coding + index_navigator 部分对应 + code_validation 部分对应), 其余 17 个无任何 pack (ICU/Triage/Medication Reconciliation/Discharge Education/Shift Handoff/PA/Referral/Clinical Education/Clinical Guidelines/Surgical Registry/Rule Explainer/Compliance Guardrail 完整版/Denial Appeals/CDI/Note Completeness 完整版/Diagnostic Extractor 完整版/Procedure Extractor 完整版).

4. **iCoDer 自创概念无 Corti 等价** — Doctor 自检 / MethodCompare / 10 builtin methods / MethodSwitcher / RunTrace / ExpertLibrary / OrchestrationPage / EvaluationPage / GoldCasesPage (P1.2 部分删, 但残留代码).

5. **3 套 Runtime 概念** — `app/services/runtime.py` (702 LOC) + `icoder_runtime/` (整个包) + `app/icoder/agent_runtime/` (新). 命名重叠易混.

6. **homepage_expert.py 仍被引用** — P1.2 已删 `homepage_coding_review` 概念, 但 `app/agents/orchestrator.py` 仍 `from app.agents.experts.homepage_expert import MedicalRecordHomepageExpert`, 是 P1.2 删除未闭环的残留.

7. **14 个 metadata-only packs 无真实 impl** — `evidence_extractor`/`index_navigator`/`code_reconciler`/`tabular_validator` 4 个 expert-stub packs (D2 阶段) 引用 `app/icoder/agent_runtime/experts/`, 但其余 10 个 (`cdi-review`/`code-validation`/`compliance-guardrail`/`denial-appeals`/`diagnosis-extractor`/`documentation-gap`/`evidence-ranker`/`note-completeness`/`procedure-extractor`/`drg-analyzer`) 仅 agent_pack.json, 无 Python impl.

8. **F1 评估 / Gold case / Pilot 系列** — CLAUDE.md 明确 "不做 F1 提升实验", 但 `app/services/gold_case_*.py` + `inter_rater.py` + `pilot_report_builder.py` + `ccl2026_importer.py` + `stt_finetune.py` + `frontend/EvaluationPage.tsx` + `GoldCasesPage.tsx` + 8 个回归测试 + 多份 PHASE/PILOT 历史文档, 全部应降级或归档.

---

## Stage 1 完成, 等待继续指令。
