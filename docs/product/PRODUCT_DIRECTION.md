# PRODUCT_DIRECTION — iCoDer 产品方向

> **声明**: 本文档是 iCoDer 产品的**主线方向声明**, 取代 CLAUDE.md 中关于 MedCodER 是产品本体的描述.
> **日期**: 2026-07-02
> **阶段**: P1.3 Corti Parity Direction Audit 后的方向纠偏
> **状态**: MAINLINE — 任何与本文档冲突的旧文档以本文档为准

---

## 1. 一句话定位

> **iCoDer 是面向中国医院场景的 Corti-style 医疗 Agent Runtime 平台**, 以托管云 SaaS 形式交付 (Environments: EU/US/CN; 医院 = Tenant; HIS/EMR = API Client).
> **Runtime 是 iCoDer Server 的内核执行引擎**, 不是独立 pip 包.
> **MedCodER 是第一个官方 Agent 应用** (Pre-built Agent #18), 不是产品本体.

---

## 2. 产品范式 (Corti-style)

### 2.1 核心理念

iCoDer 复刻 Corti 的产品范式, 信息架构, 交互体验, Agent 开发/部署/运行方式, Runtime 平台组织方式和整体产品气质. 不复制 Corti 的私有代码, 受保护素材, 商标视觉资产或非授权内容.

### 2.2 LLM 在医疗的两大根本缺口 (Corti 文档定义)

| # | LLM 缺口 | iCoDer 解决方案 |
|---|---|---|
| 1 | 没有可靠的临床数据访问 | Expert 工具调用 + 检索增强 (BGE-M3 + FAISS + icd10cn/icd9cm3 catalogs) |
| 2 | 无法安全地作用于世界 | 可控执行层 (Orchestrator + Guardrails + PHI redactor + 人工审批 gate) |

### 2.3 8 设计原则 (Corti agentic/overview)

1. **Safety First** — 类型化输入输出, 显式工具 schema, action-taking 护栏
2. **Auditability** — 每个决策和工具调用可观察, 可回放, 结构化日志
3. **Domain-Specific Reasoning** — 微调推理层, 专为医疗语言/工作流/合规优化
4. **Multi-Agent Architecture** — 多 agent 而非单体 LLM
5. **Memory & Context Management** — 持久化, context-aware, 多活动 context (threads)
6. **Ecosystem of Prebuilt Experts** — 预置 expert 库 (目标 20 Pre-built Agents)
7. **Third-Party Integrations** — 直插 EHR / 临床决策支持 / 医学知识库
8. **Run-time Context** — 每个 query 传结构化 context (FHIR resources)

### 2.4 Agent vs Workflow 二元区分

| | Agents | Workflows |
|---|---|---|
| 性质 | 自主思考/推理/适应 | 结构化, 预定义路径 |
| 适合 | 不可预测, 开放, 需要判断 | 重复, 一致性, 合规 |
| iCoDer 实现 | Agentic Framework (app/icoder/agent_runtime/) | Studio Tools (v2_tools_*, 直接 API 调用) |

---

## 3. 平台架构 (4 层)

```
第四层: Studio Tools           app/api/v2_tools_*     8 endpoints (Corti §13)
第三层: Pre-built Agents       official_agents/        2 real + 4 atomic + 14 待实装 (Corti 20)
第二层: Agentic Framework      app/icoder/agent_runtime/  A2A + Context + MCP + Orchestrator + 5 atomic Experts
第一层: Runtime Core           icoder_runtime/core/    AgentPackageV1 + Registry + LLMGateway + DataPolicy + Observability
```

### 3.1 Runtime Core 职责 (第一层)

通用 Agent 基础设施, 不包含任何医学编码领域知识:
- AgentPackageV1 — .icoder-agent 包格式与校验
- RuntimeAgentRegistry — 持久化 Agent 注册表
- AgentRunner — Agent 执行引擎 (Corti Orchestrator 风格)
- LLMGateway — LLM Provider 路由层 (DeepSeek 默认, env 可配)
- DataPolicy — 边缘 PHI 脱敏 + 区域数据驻留策略 (EU/US/CN 租户路由)
- Observability — RunHistory, AuditLog, FallbackTracker, ShadowDiffService

### 3.2 Agentic Framework 职责 (第二层)

Corti §11 完整对齐的 Agent 协作框架:
- **A2A Protocol** (Agent-to-Agent, JSON-RPC 2.0) — Agent Card + Task (5 态) + Message + Part (Text/Data/File) + Artifact
- **Context/Memory** — 短期 SQLite + 长期 BGE-M3+FAISS + contextId UUID v4 + 三层隔离 + GC 策略
- **MCP Server** — tools/list + tools/call, 5 handlers (search_icd/verify_code/get_differentiation_hint/rerank_codes/calibrate_confidence)
- **Orchestrator** — state_machine (5 态) + planner + delegator + aggregator + phi_redactor + recorder_adapter
- **5 Atomic Experts** — evidence_extractor (Stage 1) + index_navigator (Stage 2) + code_reconciler (Stage 4) + tabular_validator (Stage 5) + coding_expert

### 3.3 Pre-built Agents 职责 (第三层)

Corti 20 Pre-built Agents 的 iCoDer 实装, 中国编码体系替换 (ICD-10-CM → ICD-10-CN, ICD-10-PCS → ICD-9-CM-3-CN, CPT → 删除, MS-DRG → CN-DRG/DIP):

| # | Agent | iCoDer 状态 |
|---|---|---|
| 18 | Medical Coding Agent | ✅ 已对齐 (medical_coding + medcoder-coding-review) |
| 1 | ICD-10 Index Navigator | 部分 (ICD-9-CM-3 retriever 已做, ICD-10-CN Index Navigator 待做) |
| 4 | Code Validation | 部分 (R001-R010 + 修复 loop) |
| 5 | Procedure Entity Extractor | 部分 (Stage 1 procedure_mentions) |
| 6 | Diagnostic Entity Extractor | 部分 (Stage 1 disease) |
| 3 | Compliance Guardrail | 部分 (RuleEngine 有, Guardrail Agent 无) |
| 10 | Note Completeness | 部分 (Doctor 概念相近, 需重做) |
| 20 | CDI | metadata_only pack |
| 12 | Denial Appeals | metadata_only pack |
| 2,7,8,9,11,13,14,15,16,17,19 | 其余 11 个 | 完全缺, 待 Phase 3 实装 |

### 3.4 Studio Tools 职责 (第四层)

Corti §13 完整对齐的 8 个 v2_tools 端点:
- **Medical Coding** — `POST /api/v2/tools/coding/icoder/` (Phase 1.1)
- **Fact Extraction** — `POST /api/v2/tools/extract-facts` + `GET /api/v2/factgroups/` + 5 facts CRUD (Phase 1.2/1.3)
- **Text Generation 5 endpoints** — Streams WSS + FactsR + Guided Doc + Sections/Templates + Documents Classic (Phase 1.2)
- **STT 3 endpoints** — Transcribe WSS + Streams WSS + Transcripts REST 9 cycles (Phase 1.3)
- **Codes predict** — `POST /api/v2/tools/coding/predict-codes` 15-system spec (Phase 1.3)

### 3.5 Compliance Services (横切层)

领域独立的合规规则验证框架:
- RuleEngine — 多 rule_set 支持
- MedicalCodingRuleSet — ICD-10-CN/ICD-9-CM-3-CN 编码规则 (R001-R010 + MC-R-M80-001)
- MedCodERRetrievalRuleSet — catalog membership + 高 similarity
- DRG_DIP_RuleSet — CN-DRG/DIP (实验性)
- InsuranceRuleSet — 医保审核 (实验性)

---

## 4. MedCodER 降级声明

### 4.1 MedCodER 不再是产品本体

MedCodER 是 Pre-built Agent #18 (Medical Coding Agent) 的 5-stage pipeline 实现选项, 不是 iCoDer 的产品定位. 触发方式: `POST /api/v2/tools/coding/icoder/` (用户调 Medical Coding Agent, Agent 内部走 MedCodER 5-stage).

### 4.2 MedCodER 5-stage pipeline (NAACL 2025) 仅作为 Pre-built Agent #18 内部实现

```
EMR text
  ↓
[Stage 1: Extraction] (DeepSeek chat) → evidence_extractor expert
  ↓
[Stage 2: Retrieval] (BGE-M3 + FAISS) → index_navigator expert
  ↓
[Stage 3: Merge] candidate_set = LLM ∪ Retrieved
  ↓
[Stage 4: Re-rank] (DeepSeek RankGPT-style) → code_reconciler expert
  ↓
[Stage 5: Compliance + Calibration] → tabular_validator expert
  ↓
MedicalCodingOutputSchema (codes[] + evidences[] + alternatives[])
```

### 4.3 MedCodER 评估资产降级为实验性

以下资产**不在主线**, 仅保留用于离线评估:
- 4 ablation variant (full / prompt / retrieve / prompt+retrieve)
- F1@1 / F1@5 / per-case micro-F1 / aggregate micro-pooled
- Gold case 导入 (ccl2026_train_gold + ccl2026_val_100 + icoder_201)
- Inter-rater / Pilot report / CoT few-shot

**主线文档不再描述 4 ablation variant 为产品主线**. 评估脚本保留在 `backend/scripts/` 但不在 CLAUDE.md / PRODUCT_DIRECTION 描述.

### 4.4 编码质量优化移出主线

CLAUDE.md "金标准评估" 和 "MedCodER 评估" 章节降级为**实验性**, 不在主线 backlog. 不做 F1 提升实验, 不训练模型, 不改 Stage 1 / Stage 4 / rerank / few-shot (P1.3 约束).

---

## 5. 部署模型

| 环境 | 方式 | 说明 |
|------|------|------|
| 本地开发 | `python -m uvicorn` + `npm run dev`, 或 `docker compose -f docker-compose.local-dev.yml up` | 唯一受测开发路径, 绝不部署医院或生产 |
| 托管云 SaaS | `https://{tenant_slug}.{region}.icoder.cloud` | 三层架构: Environment (EU/US/CN) → Tenant (医院) → API Client |
| ISV 开发 | CLI: `icoder pack`, `icoder test` | Agent 打包和本地测试 |

详见 `docs/cloud/CLOUD_DEPLOYMENT.md`.

---

## 6. 信息架构 (对齐 Corti)

### 6.1 Sidebar 4 段

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
└── Medical Coding  ← 第 7 子页, 非首页主入口

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

### 6.2 工作台通用模式 (5 Studio tool 共享)

- 左 Input / 右 Output 50/50 split
- Input 控件: Samples + Clear + Copy
- Output 控件: Rendered/JSON toggle + Clear + Copy + Download
- 右侧 Settings panel (Settings/Code tabs + Template dropdown + Output language)
- 底部 Event Inspector 可折叠
- Empty state microcopy ("Predicted codes will show here")

---

## 7. 不在主线 (Out of Scope)

以下**不上主线**, 不在 P1.3 范围, 列入后续 Phase:

- 17 个 Pre-built Agents 实装 (Phase 3)
- A2A 真实任务流跑通 + Task 5 态 + Artifact (Phase 2)
- MCP Resources/Prompts + Expert as MCP client (Phase 2)
- Context/Memory 真实跑通 + 三层隔离 + GC 策略 (Phase 2)
- Embedded Assistant 子域 proxy + tRPC + 第三方 relay (Phase 4)
- PostHog 自部署 + Stripe 全套 + Intercom + Mintlify 文档站 + Keycloak (Phase 4)
- F1 提升实验 / 模型训练 / Stage 1/4/rerank/few-shot 改动 (永不上主线)
- Doctor 自检 / MethodCompare / 10 builtin methods / MethodSwitcher / RunTrace / ExpertLibrary / OrchestrationPage / EvaluationPage / GoldCasesPage (P1.2/P1.3 已删或降级)

---

## 8. 目标用户

- **中国医院信息科** — 通过 API Client 接入 iCoDer 平台, 调 Pre-built Agents 或自建 Agent
- **医疗软件 ISV** — 用 CLI (`icoder pack`, `icoder test`) 打包 Agent, 发布到 iCoDer Marketplace (Phase 4)
- **医院合规/病案** — 用 Pre-built Agents 做编码/分组/结算/收费/病历/审计合规

---

## 9. 与 CLAUDE.md 的关系

CLAUDE.md 是项目说明, 但其中关于 MedCodER 是产品本体的描述 (CLAUDE.md:80-130) **已被本文档降级**. 任何冲突以本文档为准. CLAUDE.md 应在 Stage 4 后更新以反映本文档方向.

---

## 10. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, MedCodER 降级为 Pre-built Agent #18, 平台定位重写为 Corti-style 医疗 Agent Runtime 平台 | P1.3 Corti Parity Direction Audit (Stage 2 总分 65.94/100, PARTIALLY_ALIGNED) |
