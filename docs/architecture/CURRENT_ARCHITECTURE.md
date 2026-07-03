# CURRENT_ARCHITECTURE — iCoDer 当前架构

> **声明**: 本文档描述 iCoDer **当前**架构 (P1.3 阶段), 含主线 + 实验性 + Legacy 三层. 不描述未来架构 (见 `CORTI_PARITY_ROADMAP.md`).
> **日期**: 2026-07-02
> **阶段**: P1.3 Corti Parity Direction Audit 后的架构梳理
> **状态**: MAINLINE — 取代 docs/ARCHITECTURE.md 中关于 MedCodER 主线的描述

---

## 1. 架构总览 (4 层)

```
┌──────────────────────────────────────────────────────────────────────┐
│  第四层: Studio Tools (app/api/v2_tools_*)                            │
│  8 endpoints — Corti §13 完整对齐                                      │
│  Medical Coding / Fact Extraction / Text Generation 5 / STT 3         │
├──────────────────────────────────────────────────────────────────────┤
│  第三层: Pre-built Agents (backend/official_agents/)                  │
│  2 real + 4 atomic + 10 metadata-only = 16 packs                      │
│  目标: Corti 20 Pre-built Agents (当前 3/20 对齐)                       │
├──────────────────────────────────────────────────────────────────────┤
│  第二层: Agentic Framework (app/icoder/agent_runtime/)                │
│  A2A Protocol + Context/Memory + MCP Server + Orchestrator + 5 atomic │
│  Experts                                                               │
│  (Phase 2-A: 主线已切 — main.py lifespan 用新 wiring, /.well-known/agent.json 200) │
├──────────────────────────────────────────────────────────────────────┤
│  第一层: Runtime Core (icoder_runtime/core/)                          │
│  AgentPackageV1 + Registry + LLMGateway + DataPolicy + Observability  │
│  + Compliance Services (compliance_services/, 横切层)                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. 第一层 — Runtime Core

**位置**: `backend/icoder_runtime/core/` (15 文件)

### 2.1 模块清单

| 模块 | 职责 | 状态 |
|---|---|---|
| `agent_pack_loader.py` | .icoder-agent 包加载 | keep_mainline |
| `agent_pack_schema.py` | pack schema 校验 | keep_mainline |
| `agent_pack_v1.py` | AgentPackageV1 格式 | keep_mainline |
| `builtin_pack_provider.py` | 6 v1.2 builtin pack provider | keep_mainline |
| `data_policy.py` | PHI 脱敏 + 区域数据驻留 | keep_mainline |
| `errors.py` | 错误定义 | keep_mainline |
| `evidence_parser.py` | Stage-1 markdown evidence 解析 (cycle 22) | keep_mainline |
| `llm_gateway.py` | LLM Provider 路由 | keep_mainline |
| `pii_redaction.py` | PII 脱敏 | keep_mainline |
| `registry.py` | Agent 注册表 | keep_mainline |
| `registry_backend.py` | 注册表后端 | keep_mainline |
| `registry_status.py` | 注册表状态 | keep_mainline |
| `runtime_config.py` | Runtime 配置 | keep_mainline |
| `runtime_result.py` | RuntimeRunResult (含 source param 填 metadata.evidences) | keep_mainline |

### 2.2 关键设计

- **AgentPackageV1** — .icoder-agent 包格式, format_version 1.1/1.2, 严格 validator
- **RuntimeAgentRegistry** — 持久化 Agent 注册表, registry.install 按 format_version 分流 (1.1 strict / 1.2 expert_id)
- **LLMGateway** — Provider 路由, DeepSeek 默认 (env 可配, 不绑定厂商)
- **DataPolicy** — EU/US/CN 租户路由, PHI 脱敏 + 区域数据驻留, 原始 PHI 不进云审计
- **Observability** — RunHistory + AuditLog + FallbackTracker + ShadowDiffService

---

## 3. 第二层 — Agentic Framework

**位置**: `backend/app/icoder/agent_runtime/` (4 子目录, 34 文件)

### 3.1 A2A Protocol (`a2a/`, 13 文件)

| 模块 | 职责 | 状态 |
|---|---|---|
| `a2a_routes.py` | A2A 路由聚合 | keep_mainline |
| `agent_card.py` | Agent Card (JSON-LD schema) | keep_mainline |
| `envelope.py` | JSON-RPC 2.0 信封 | keep_mainline |
| `errors.py` | 8 类错误码 | keep_mainline |
| `icoder_metadata.py` | iCoDer metadata (run_id/trace_url/phi_redacted) | keep_mainline |
| `messages.py` | Message (role: user/agent) | keep_mainline |
| `parts.py` | Part (TextPart/DataPart/FilePart) | keep_mainline |
| `routes_discovery.py` | Discovery 端点 (list-registry-experts) | keep_mainline |
| `routes_inbound.py` | 入站端点 | keep_mainline |
| `routes_outbound.py` | 出站端点 | keep_mainline |
| `routes_task_stub.py` | Task stub (5 态: submitted/working/input-required/completed/failed/canceled) | keep_mainline (stub, Phase 2 完整化) |
| `schema_registry.py` | schema 注册 | keep_mainline |
| `version.py` | A2A v0.3 | keep_mainline |

### 3.2 Context/Memory (`context/`, 11 文件)

| 模块 | 职责 | 状态 |
|---|---|---|
| `context.py` | Context 对象 (messages/tasks/artifacts/metadata) | keep_mainline |
| `context_audit.py` | Context 审计 | keep_mainline |
| `context_garbage_collector.py` | GC 策略 (24h active + 7d 物理删除 + 90d audit) | keep_mainline |
| `context_id.py` | contextId UUID v4 服务端生成 | keep_mainline |
| `context_isolation.py` | 三层隔离 (数据/状态/缓存) | keep_mainline |
| `context_lifecycle.py` | Context 生命周期 | keep_mainline |
| `context_repository.py` | Context 仓库 | keep_mainline |
| `context_status.py` | Context 状态 | keep_mainline |
| `db_models.py` | Context DB 模型 | keep_mainline |
| `db_schema.sql` | Context schema | keep_mainline |
| `icoder_metadata.py` | Context metadata | keep_mainline |

### 3.3 MCP Server (`app/icoder/mcp/`, 7 文件)

| 模块 | 职责 | 状态 |
|---|---|---|
| `server.py` | MCP server (/mcp/v1/tools/{list,call}) | keep_mainline |
| `tool_registry.py` | Tool 注册表 | keep_mainline |
| `errors.py` | 8 类错误码 | keep_mainline |
| `handlers/search_icd.py` | search_icd tool | keep_mainline |
| `handlers/verify_code.py` | verify_code tool | keep_mainline |
| `handlers/get_differentiation_hint.py` | get_differentiation_hint tool | keep_mainline |
| `handlers/rerank_codes.py` + `calibrate_confidence.py` | rerank + calibrate tools | keep_mainline |

### 3.4 Orchestrator (`orchestrator/`, 13 文件)

| 模块 | 职责 | 状态 |
|---|---|---|
| `state_machine.py` | 5 态状态机 (received→planning→delegating→aggregating→completed/failed) | keep_mainline |
| `planner.py` | 真实 DeepSeek planner | keep_mainline |
| `delegator.py` | Expert 选择 + 调用 | keep_mainline |
| `aggregator.py` | Expert 结果汇总 | keep_mainline |
| `events.py` | 事件 | keep_mainline |
| `metrics.py` | 指标 | keep_mainline |
| `phi_redactor.py` | PHI redactor (Orchestrator 拥有全部 context 访问权) | keep_mainline |
| `recorder_adapter.py` | 录制适配器 | keep_mainline |
| `run_context.py` | Run context | keep_mainline |
| `wiring.py` | wiring (build_expert_invoker_for_medcoder 路由 4 D2 expert pack) | keep_mainline |
| `prompts.py` | system prompts | keep_mainline |
| `errors.py` | 错误码 (AGENT_NOT_FOUND 等) | keep_mainline |
| `inbound_handler.py` | 入站处理 | keep_mainline |

### 3.5 5 Atomic Experts (`experts/`, 5 文件)

| Expert | MedCodER Stage | LOC | 状态 |
|---|---|---|---|
| `evidence_extractor_expert.py` | Stage 1 (Extraction) | 275 | keep_mainline |
| `index_navigator_expert.py` | Stage 2 (Retrieval) | 236 | keep_mainline |
| `code_reconciler_expert.py` | Stage 4 (Re-rank) | 303 | keep_mainline |
| `tabular_validator_expert.py` | Stage 5 (Compliance) | 159 | keep_mainline |
| `coding_expert.py` | Coding Expert Runtime (首个真 Expert impl) | 226 | keep_mainline |

### 3.6 当前运行状态 (重要)

**注意**: Agentic Framework **spec 完整但主线运行的是 Legacy**. 实际 medical-coding 调用走 `app/api/v2_tools_coding.py` → `icoder_runtime/core/` → `medcoder-coding-review/agent_pack.json` → `HybridCodingAdapter` (5-mode dispatch) → MedCodER 5-stage. 新 `app/icoder/agent_runtime/orchestrator/` 未真实接管. Phase 2 才会切换.

---

## 4. 第三层 — Pre-built Agents

**位置**: `backend/official_agents/` (16 目录)

### 4.1 真实 Agent (keep_mainline, 2 个)

| Pack | 文件 | 描述 |
|---|---|---|
| `medical_coding/` | 5 (agent_pack.json + modes.py + schema.py + __init__.py + __pycache__) | Medical Coding Agent (Corti Pre-built #18) |
| `medcoder-coding-review/` | 1 (agent_pack.json) | MedCodER 5-stage NAACL 2025 pipeline |

### 4.2 4 Atomic Expert Packs (keep_mainline, format_version=1.2)

| Pack | 引用 Expert | MedCodER Stage |
|---|---|---|
| `evidence_extractor/` | `evidence_extractor_expert.py` | Stage 1 |
| `index_navigator/` | `index_navigator_expert.py` | Stage 2 |
| `code_reconciler/` | `code_reconciler_expert.py` | Stage 4 |
| `tabular_validator/` | `tabular_validator_expert.py` | Stage 5 |

### 4.3 10 Metadata-only Packs (unclear / keep_mainline, 待 Phase 3 实装)

对应 Corti Pre-built Agents 但仅 agent_pack.json 无 Python impl:
- `cdi-review/` (Corti #20 CDI)
- `code-validation/` (Corti #4)
- `compliance-guardrail/` (Corti #3)
- `denial-appeals/` (Corti #12)
- `diagnosis-extractor/` (Corti #6)
- `documentation-gap/` (Corti #10 部分)
- `evidence-ranker/` (MedCodER Stage 4 rerank)
- `note-completeness/` (Corti #10)
- `procedure-extractor/` (Corti #5)
- `drg-analyzer/` (3 文件, 中国 DRG/DIP 实验性)

---

## 5. 第四层 — Studio Tools

**位置**: `backend/app/api/v2_tools_*.py` (8 模块, 4034 LOC)

| 模块 | LOC | 端点 | Corti 对齐 | 状态 |
|---|---|---|---|---|
| `v2_tools_coding.py` | 559 | `POST /api/v2/tools/coding/icoder/` | §13.6 | keep_mainline (Phase 1.1) |
| `v2_tools_facts.py` | 619 | `POST /api/v2/tools/extract-facts` + `GET /api/v2/factgroups/` + 5 facts CRUD | §13.5 | keep_mainline (Phase 1.2/1.3) |
| `v2_tools_stt.py` | 866 | `POST /api/v2/interactions/` + transcripts/recordings 9 cycles | §13.3 | keep_mainline (Phase 1.3) |
| `v2_tools_streams.py` | 382 | WSS Streams | §13.3 | keep_mainline (Phase 1.2 cycle 2) |
| `v2_tools_guided_document.py` | 277 | Guided Document Synthesis (Beta) | §13.4 | keep_mainline (Phase 1.2 cycle 3) |
| `v2_tools_sections_templates.py` | 262 | Sections & Templates LIST (Beta) | §13.4 | keep_mainline (Phase 1.2 cycle 4) |
| `v2_tools_documents_classic.py` | 196 | Documents Classic LIST (Planned deprecation) | §13.4 | keep_mainline (Phase 1.2 cycle 5) |
| `oauth.py` | 449 | OAuth 2.0 client_credentials + 5min TTL + scoped + tenant | §13.2 | keep_mainline (Phase 1.0) |

---

## 6. 横切层 — Compliance Services

**位置**: `backend/compliance_services/` (5 文件)

| 模块 | 职责 | 状态 |
|---|---|---|
| `rule_engine.py` | RuleEngine 主体 (multi rule_set) | keep_mainline |
| `medical_coding_rules.py` | ICD-10-CN/ICD-9-CM-3-CN 编码规则 (R001-R010 + MC-R-M80-001) | keep_mainline |
| `medcoder_retrieval_rules.py` | MedCodER retrieval 规则 (catalog + similarity) | keep_mainline |
| `drg_dip_rules.py` | CN-DRG/DIP 规则 | keep_experimental |
| `insurance_rules.py` | 医保审核规则 | keep_experimental |

---

## 7. Legacy 架构 (Deprecated, Phase 2-B 断引用 / 2-C 物理删)

> **Phase 2-A 更新 (2026-07-02)**: 主线已切到 `app/icoder/agent_runtime/` — `main.py` lifespan 用新 wiring (`build_expert_invoker_for_medcoder` + `build_llm_call_from_gateway`), `HybridCodingAdapter(mode="medcoder")` 用新 wiring 构造, `mount_a2a` + `mount_mcp` 已挂载, `/.well-known/agent.json` 返 200. 以下 Legacy 仍存在但已 DEPRECATED 标记 (P1.3 Stage 5), Phase 2-B 断引用, 2-C 物理删.

### 7.1 Legacy 单体 Agent (`app/agents/`)

- `app/agents/orchestrator.py` — Legacy 单体 orchestrator, 引用 `homepage_expert`
- `app/agents/experts/` 11 文件 — Legacy expert library (homepage 664 LOC 最大, 其余 80-340 LOC)
- **状态**: DEPRECATED (P1.3 Stage 5 已标记), 仍被 `app/agents/__init__.py` + `app/api/reviews.py` 引用, Phase 2-B 断, 2-C 删

### 7.2 Legacy AgentRunner (`app/services/agent_runner.py` + `icoder_runtime/agent_runner.py`)

- 1047 LOC + 重复, 被新 `app/icoder/agent_runtime/orchestrator/` 取代
- **状态**: DEPRECATED (P1.3 Stage 5 已标记 + app/services 早前 v2.1 标记), 仍被 `app/api/agents.py` 引用, Phase 2-B 断, 2-C 删

### 7.3 Legacy API 路径 (`app/api/icoder_*.py`)

| 模块 | LOC | 状态 |
|---|---|---|
| `icoder_coding_review.py` | 1283 | deprecated (Corti 用 /v2/tools/coding/) |
| `icoder_agents_hub.py` | 1029 | migrate (Phase 2 迁到 /rest/v1/agent_definitions) |
| `icoder_agents_compat.py` | 123 | deprecated → delete |
| `icoder_registry_compat.py` | 106 | deprecated → delete |

### 7.4 Legacy 前端 (Doctor/MethodCompare/RunTrace/ExpertLibrary/Orchestration 残留)

- `frontend/src/pages/EvaluationPage.tsx` (265) — deprecated
- `frontend/src/pages/GoldCasesPage.tsx` (272) — deprecated
- `frontend/src/pages/ExpertLibraryPage.tsx` (604) — deprecated
- `frontend/src/pages/OrchestrationPage.tsx` (266) — deprecated
- `frontend/src/pages/EmbedDemoCodingReviewPage.tsx` (225) + `.bak` — deprecated → delete
- `frontend/src/components/orchestration/` 7 components — deprecated → delete
- `frontend/src/components/icoder/RunTraceTimeline.tsx` — deprecated → delete
- `frontend/src/components/medical-coding/MethodTraceViewer.tsx` — deprecated → delete
- `frontend/src/services/icoderCodingReviewApi.ts` — deprecated
- `frontend/src/hooks/useReviewPipeline.ts` — deprecated

### 7.5 Legacy 评估资产 (MedCodER 实验性)

- `app/services/gold_case_*.py` + `inter_rater.py` + `pilot_report_builder.py` + `ccl2026_importer.py` + `stt_finetune.py` — keep_experimental (非主线)
- `app/api/evaluation.py` + `agent_evaluation.py` + `gold_cases.py` — deprecated
- `backend/tests/regression/` 8 文件 — keep_experimental (F1 baseline CLAUDE.md 已降级)
- `backend/scripts/e2e_runtime_validation.py` + `e2e_medcoder_validation.py` — keep_experimental

---

## 8. 部署架构 (Cloud-Flip 后)

```
医院 HIS/EMR
   │
   ▼
API Client (backend-service 或 ROPC embedded Web Component)
   │
   ▼
https://{tenant}.{region}.icoder.cloud  ← 单域名子路径
   │
   ├── /api/v1/*                ← FastAPI + SQLAlchemy (Corti api.console /rest/v1/*)
   ├── /api/v1/functions/*      ← Edge Functions 等价 (Corti /functions/v1/*)
   ├── /api/v2/tools/*          ← Studio Tools (Corti api.eu /v2/tools/*)
   ├── /api/runtime/*           ← Runtime status + health
   ├── /assistant/api/*         ← Embedded Assistant (Corti assistant.eu /api/*)
   └── /                        ← Frontend SPA (Corti console.corti.app)
```

**Environments**: EU / US / CN (data residency)
**Tenants**: 医院 = Tenant (Tenant-Name header)
**API Clients**: backend-service (server-side) 或 ROPC embedded (Web Component)

详见 `docs/cloud/CLOUD_DEPLOYMENT.md`.

---

## 9. 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + SQLAlchemy (async) + SQLite (local) / PostgreSQL (CI) |
| LLM | DeepSeek V4 (deepseek-v4-flash) via LLMGateway, env 可配 |
| Embedding | BGE-M3 (BAAI/bge-m3) 本地 sentence-transformers, 1024-dim, fp16 |
| 向量索引 | FAISS IndexFlatIP (cosine via inner product on normalized), MMAP + dtype key |
| 数据 | iCoDerA 资产 (只读, 本地 E:\iCoDerA\, 托管云 region-shared object storage) |
| 前端 | React + TypeScript + Vite + Tailwind CSS + Lucide icons |
| 测试 | pytest (900+ tests) + Vitest (frontend) + Playwright (UI runtime diff) |
| 文档 | 自写 markdown (Mintlify 留 Phase 4) |
| 部署 | Docker compose (local-dev) + 托管云 SaaS (cloud) |

---

## 10. 与 Corti 架构对齐状态 (P1.3 后 + Phase 2-A 主线已切)

| 维度 | iCoDer 得分 | 状态 |
|---|---|---|
| Medical Coding API | 4.67 | ✅ Phase 1.1 |
| Fact Extraction API | 4.60 | ✅ Phase 1.2/1.3 |
| Text Generation API | 4.60 | ✅ Phase 1.2 |
| Speech-to-Text API | 4.00 | ✅ Phase 1.3 |
| Authentication | 4.50 | ✅ Phase 1.0 |
| 数据模型 | 3.38 | 部分对齐 (命名分散) |
| MCP 协议 | 3.50 | 部分对齐 (Resources/Prompts 缺, Phase 2-D) |
| AI Studio 工作台模式 | 3.29→3.5+ | 部分对齐 (WorkbenchLayout 壳已建, Phase 2-E 迁 3 页) |
| Context/Memory | 3.29 | 部分对齐 (spec 完整, Phase 2-D 跑通) |
| Sidebar IA | 3.00→4.0+ | ✅ 已对齐 (P1.3 Stage 6 验证) |
| A2A 协议 | 3.00 | 部分对齐 (Task 5 态 stub, Phase 2-D) |
| Edge Functions | 3.14 | 部分对齐 (4 项 stub) |
| 视觉设计系统 | 2.89→3.5+ | ✅ 已抽离 (P1.3 Stage 6, vermillion 保留) |
| 顶栏元素 | 2.50→4.0+ | ✅ 已对齐 (P1.3 Stage 6 Theme toggle + Reset) |
| 产品定位 | 2.80→4.0+ | ✅ 已对齐 (P1.3 MedCodER 降级) |
| 架构层 (4 域名) | 2.25 | 部分对齐 (第三方缺, Phase 4) |
| Project Home 4 tabs | 1.33→4.0+ | ✅ 已对齐 (P1.3 Stage 6) |
| Embedded Assistant proxy | 1.67 | 严重偏离 (Phase 4) |
| Pre-built Agents (20) | 1.40 | 严重偏离 (17 缺, Phase 3) |
| 文档站 | 1.13→3.5+ | ✅ 已对齐 (P1.3 README_INDEX + 14 docs) |

**P1.3 后总分**: ~75/100 (ALIGNED 边缘). **Phase 2 目标**: ~80/100. **Phase 2-A 主线已切**: app/icoder/agent_runtime/ 确认为唯一主线.

---

## 11. 后续架构演进 (见 CORTI_PARITY_ROADMAP.md)

- **Phase 2** — Agentic Framework 真实跑通 (A2A Task 5 态 + Context + MCP Resources/Prompts + 切换主运行路径到新 orchestrator)
- **Phase 3** — 17 个 Pre-built Agents 实装 (ICU/Triage/Medication Reconciliation/...)
- **Phase 4** — 第三方基础设施 (PostHog/Stripe/Intercom/Mintlify/Keycloak) + Embedded Assistant 子域 proxy
