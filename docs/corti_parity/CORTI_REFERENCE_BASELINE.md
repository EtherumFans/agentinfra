# CORTI_REFERENCE_BASELINE — Corti 产品参考审计

> **阶段**: P1.3 — Corti Parity Direction Audit & Asset Consolidation / Stage 0
> **来源**: `docs/corti-reverse-engineered/` (账号直登 songluhua@gmail.com, 2026-06-30 deep crawl) + `docs/corti-feature-inventory.md` (15 页面走查, 2026-06-29) + `docs/corti-reverse-engineered/docs-site/_extracted/*.md` (Mintlify 文档站)
> **方法**: 账号直登 console.corti.app 走查 15 个 sidebar 入口 + Playwright 抓包 (`api-contracts-v2.json` 1.74 MB) + 49 张全页截图 + 文档站 Mintlify 提取
> **凭证使用范围**: 仅本次参考审计,不入文件、不入代码
> **日期**: 2026-07-02

---

## 1. 产品定位与哲学

### 1.1 一句话定位

> **Corti is the all-in-one AI stack for healthcare, built for medical accuracy, compliance, and scale.**

来源: `docs.corti.ai/about/introduction` (Mintlify 提取)。Corti 是面向医疗开发者的全栈 AI 平台, **API 即产品**, 不是 SaaS 后台, 也不是单点工具。

### 1.2 Corti Symphony — 模型网络 + 编排层

- **Symphony** = model network + orchestration layer (Text + Audio 双模态)
- 驱动三大核心能力: **STT / Text Generation / Agent**
- Symphony 不是单独可调用产品, 是 Corti 平台所有 AI 能力的统一编排内核

### 1.3 LLM 在医疗的两大根本缺口 (Corti 文档明确定义)

| # | LLM 缺口 | Corti 解决方案 |
|---|---|---|
| 1 | **没有可靠的临床数据访问** (LLM 只能基于内部知识推断) | **Expert 工具调用 + 检索增强**: Agents 通过检索从可信外部工具验证事实, 而非 hallucinate |
| 2 | **无法安全地作用于世界** (Clinical workflow 需要调 EHR、写文档、配药品、触发下游流程) | **可控执行层**: 允许 agent 计划动作 + 调工具 + 协调多步 workflow, 但强制 safety boundaries; 需要时暂停 + 请求人类审批 + 明确同意后才恢复 |

### 1.4 设计原则 (8 条, 来自 `agentic/overview`)

1. **Safety First** — 类型化输入输出、显式工具 schema、action-taking 护栏
2. **Auditability** — 每个决策和工具调用可观察、可回放、结构化日志
3. **Domain-Specific Reasoning** — 微调推理层, 专为医疗语言/工作流/合规优化
4. **Multi-Agent Architecture** — 多 agent 而非单体 LLM
5. **Memory & Context Management** — 持久化、context-aware, 支持多活动 context (threads)
6. **Ecosystem of Prebuilt Experts** — 预置 expert 库, 连接数据源/工具/服务
7. **Third-Party Integrations** — 直插 EHR / 临床决策支持 / 医学知识库
8. **Run-time Context** — 每个 query 传结构化 context (如 FHIR resources)

### 1.5 目标用户

- **Healthcare software companies** — 把智能自动化嵌入产品
- **Enterprise customers** — 内部 AI-powered clinical workflow
- **Advanced engineering teams** — 需要灵活、控制力、安全保证, 不想从零自建 agent 基础设施

明确定位: 不是 prompt-based chatbot, 而是 **production-grade clinical AI systems**。

### 1.6 Agent vs Workflow 二元区分

| | Agents | Workflows |
|---|---|---|
| 性质 | 自主思考/推理/适应 | 结构化、预定义路径 |
| 适合 | 不可预测、开放、需要判断 | 重复、一致性、合规 |
| 比喻 | 大厨(看食材随机应变) | 食谱/清单 |
| 实现 | Agentic Framework | 其他 API 套件 |

---

## 2. 架构层 (4 大域名 + 第三方)

| 域名 | 性质 | 用途 |
|---|---|---|
| **`console.corti.app`** | Web SPA (Remix) | UI 路由壳层; 不直接接业务 API |
| **`api.console.corti.app`** | Supabase (PostgREST + Edge Functions) | 项目元数据、用户/团队/账单、客户、模板资产 |
| **`api.eu.corti.app`** / `api.us.corti.app` | 独立 Studio API (`/v2/*`) | 核心 AI 工具: medical coding / fact extraction / text generation templates / STT |
| **`assistant.eu.corti.app`** / `assistant.us.corti.app` | Embedded Assistant proxy (`/api/proxy/*`, `/api/trpc/*`) | Embedded Assistant 模式: session init, template tRPC, proxy to PostHog |
| **`auth.eu.corti.app`** / `auth.us.corti.app` | **Keycloak** (OAuth 2.0 client-credentials) | 认证 IdP, tenant 隔离, 5 分钟 short-lived tokens |
| **`prp.corti.app`** | PostHog (自部署) | Session recording (`/s/`), event capture (`/i/v0/e/`), feature flags (`/flags/`), surveys |
| `js.stripe.com` | 第三方 | Billing |
| `api-iam.intercom.io` | 第三方 | Tickets / Help |
| `analytics.google.com` / `www.googletagmanager.com` | 第三方 | GA4 + GTM |
| `script.crazyegg.com` | 第三方 | 热力图 |
| `mintcdn.com/corti/...` | Mintlify 文档 CDN | docs.corti.ai |

**关键判断**: iCoDer 不应复用 Supabase/PostgREST。FastAPI + SQLAlchemy async 路由可直接对齐 Edge Functions 的 URL 模式。iCoDer 单域名子路径模式已通过 cloud flip 决议, 路径完全对齐 Corti 即可。

---

## 3. Sidebar 信息架构 (15 个 feature 全部跑完)

| 段 | Feature | 路径 | 主要 API | 请求数 |
|---|---|---|---|---|
| Top | `home` | `/` (4 tabs) | PostHog flags/surveys + Intercom HMAC | 18 |
| Top | `developer-quickstart` | `/developer-quickstart` | `/rest/v1/api_clients` + auth + onboarding | 31 |
| AI Studio | `ai-studio-overview` (隐含) | `/ai-studio` | (抓包归在 agents) | — |
| AI Studio | `ai-studio-agents` | `/ai-studio/agents` | `/rest/v1/agent_definitions` + PostHog | 113 |
| AI Studio | `ai-studio-agents-new` | `/ai-studio/agents/new` | `/functions/v1/external/agents` + `/rest/v1/agent_definitions` | 21 |
| AI Studio | **`ai-studio-medical-coding`** | `/ai-studio/medical-coding` | **`POST /v2/tools/coding/`** (核心) | 51 |
| AI Studio | `ai-studio-text-generation` | `/ai-studio/text-generation` | `GET /v2/templates/` + `/rest/v1/project_assets` | 29 |
| AI Studio | `ai-studio-fact-extraction` | `/ai-studio/fact-extraction` | `POST /v2/tools/extract-facts` + `GET /v2/factgroups/` | 23 |
| AI Studio | `ai-studio-speech-to-text` | `/ai-studio/speech-to-text` | `POST /v2/interactions/` (audio upload) | 63 |
| AI Studio | **`ai-studio-embedded-asst`** | `/ai-studio/embedded-assistant` | **`assistant.eu.corti.app/api/proxy/*`** + `/api/trpc/template.getAllSections` | 137 |
| Manage | `api-clients` | `/api-clients` | `/rest/v1/api_clients` + `access_token` Edge Function | 39 |
| Manage | `team` | `/team` | `/rest/v1/project_memberships` + `/rest/v1/team_invitations` | 22 |
| Manage | `billing` | `/billing` | `/functions/v1/projects/<id>/billing/balance` + Stripe | 55 |
| Manage | `customers` | `/customers` | `/functions/v1/public/projects/<id>/customers` | 21 |
| Manage | `templates` | `/templates` | `/rest/v1/api_clients` + `/functions/v1/projects/<id>/assistant-settings` | 50 |
| Manage | `settings` | `/settings` | `/rest/v1/projects` + `/rest/v1/team_invitations` | 24 |
| Support | `support` (Get Help) | (Intercom) | `api-iam.intercom.io` | — |
| Support | `tickets-portal` | (外部 Zendesk) | — | — |

**Sidebar 段顺序** (Corti 严格按此顺序):
1. Top: Home / Developer quickstart
2. **AI Studio**: Overview → Agents → Speech to Text (3 子页) → Text Generation → Embedded Assistant → Fact Extraction → Medical Coding
3. **Manage**: API Clients → Team → Billing → Usage → Customers → Templates (BETA) → Settings
4. Support: Get Help / Tickets Portal

**缩进规则**: 仅 1 级 (16px)

---

## 4. Project Home 4 tabs

`/project/<id>` Home 顶部 4 tabs (从 `01_home_overview.png` 抽取):

| Tab | 内容 | 备注 |
|---|---|---|
| **Transcribe** | "Capture conversation in real time for ambient scribes and clinical-grade dictation applications" / Start recording / Developer quickstart | STT 入口 |
| **Document** | (Text Generation 入口) | 文档生成入口 |
| **Chat** | (Embedded Assistant 入口) | 聊天式 assistant 入口 |
| **Code NEW** | (Medical Coding 入口, NEW 徽章) | 编码工作台入口, 加 NEW 标记表示新发布 |

**关键**: 4 tabs 是 Project Home 的唯一功能, 是 4 大 AI 能力的入口分发器, 不是 dashboard 也不是 admin 首页。每个 tab promo 跳到对应 AI Studio 工作台。

---

## 5. AI Studio 工作台通用模式 (5 个 Studio tool 共享)

### 5.1 通用 Layout

```
┌──────────────────────────────────────────────────────────┐
│ [feature] / breadcrumb                  [Predict codes] │
├──────────────────────────────────────────────────────────┤
│ Coding systems ⓘ  [ICD-10-CM Outpatient ⓧ] [+]    [⚙]  │
├────────────────────────────┬─────────────────────────────┤
│ Input                      │ Output                      │
│ [Samples] [🗑] [📋]         │ [Rendered|JSON] [🗑][📋][⬇]│
│ ┌──────────────────────┐    │ ┌─────────────────────────┐ │
│ │ clinical text...     │    │ │ codes[] w/ evidence     │ │
│ └──────────────────────┘    │ └─────────────────────────┘ │
│                            │ [Credits: $0.086464]         │
├────────────────────────────┴─────────────────────────────┤
│ › Event Inspector (collapsible)                          │
└──────────────────────────────────────────────────────────┘
```

### 5.2 共同元素

- 左 Input / 右 Output **50/50 split**
- Input 控件: Samples (demo 文本) + 清除 + 复制
- Output 控件: Rendered/JSON toggle + 清除 + 复制 + 下载
- 右侧 Settings panel (Settings/Code tabs + Template dropdown + Output language)
- 底部 Event Inspector 可折叠 (日志 API 事件, SSE 流)
- Empty state 一句话: "Predicted codes will show here"

### 5.3 5 个 Studio tool

| Tool | Endpoint | 输入 | 输出 |
|---|---|---|---|
| Medical Coding | `POST /v2/tools/coding/` | 临床文本 + 编码体系 | codes[] + evidence + alternatives |
| Fact Extraction | `POST /v2/tools/extract-facts` | 文本 | facts[] |
| Text Generation | `POST /v2/templates/...` + `POST /v2/generate` | context + template | document |
| Speech-to-Text | `POST /v2/interactions/` | 音频 | transcript |
| Embedded Assistant | `POST /api/proxy/relay/*` + tRPC | session | SSE stream |

### 5.4 Agent 双入口 + Builder

- **My agents** (用户建) / **Pre-built agents** (Corti 官方 20 个)
- 任意 Pre-built agent 都有 **Preview / Customize** 右键菜单
- **Preview** = "Ask the agent..." 聊天壳 (try-it-out 交互)
- **Customize** → 进入 builder (workflow builder 形式)

---

## 6. 核心 API 契约 (Studio Tools)

### 6.1 Medical Coding (核心复刻目标)

**Endpoint**: `POST https://api.eu.corti.app/v2/tools/coding/`

**Request** (real EMR 抓包):
```json
{
  "context": [
    {"text": "患者男性,67 岁,因「反复胸闷...LVEF 38%。诊断:1. 慢性心力衰竭 心功能 III 级(NYHA);2. 心房颤动;...", "type": "text"}
  ],
  "system": ["icd10cm-outpatient"]
}
```

**Response** (200, 8 codes):
```json
{
  "codes": [
    {
      "system": "icd10cm-outpatient",
      "code": "I50.22",
      "display": "Chronic systolic (congestive) heart failure",
      "evidences": [
        {"contextIndex": 0, "text": "心脏超声示左心扩大,LVEF 38%", "start": 110, "end": 128}
      ],
      "alternatives": [
        {"code": "I50.20", "display": "Unspecified systolic (congestive) heart failure"},
        {"code": "I50.21", "display": "Acute systolic (congestive) heart failure"}
      ]
    }
  ]
}
```

**字段含义**:
- `context[]` — 多模态输入 (text 类型, 目前仅文本; 未来可能音频/图像)
- `system[]` — 编码体系 (可多选): `icd10cm-outpatient` / `icd10cm-inpatient` / `icd10pcs` / `icd9cm` / `cpt`
- `evidences[]` — 每条 evidence 是一个 char span, 绑定到具体 `contextIndex` + start/end offset
- `alternatives[]` — 备选编码 (rerank 候选)

### 6.2 Fact Extraction

**Endpoint**: `POST https://api.eu.corti.app/v2/tools/extract-facts`

抓包见 `feature-flows/ai-studio-fact-extraction/summary.json`。关联目录: `GET /v2/factgroups/` — 返回 fact group 分类体系。

### 6.3 Text Generation (5 endpoints)

| 端点 | 连接 | 架构 | 用途 | 状态 |
|---|---|---|---|---|
| Streams | WSS | Stateful | 实时 FactsR 抽取 | GA |
| **FactsR™** | REST | **Stateless** | 文本→事实 | GA |
| Guided Document Synthesis | REST | Stateless/Stateful | 结构化文档生成 (template 驱动) | **Beta** |
| Sections & Templates | REST | — | 模板/Section CRUD | **Beta** |
| Documents Classic | REST | Stateful | 文档生成 (templateKey) | **Planned deprecation** |

模板清单: `GET https://api.eu.corti.app/v2/templates/`

**重点**: Guided Documents 是 **interaction-optional** — 可以 supply `context` (text/transcript/facts) 做 stateless call, 或 supply `interactionId` 拉既有 interaction 的 facts/transcripts。两者目前互斥, 合并是 roadmap。

### 6.4 Speech-to-Text (3 endpoints)

| 端点 | 连接 | 处理 | 架构 | 用途 |
|---|---|---|---|---|
| **Transcribe** | WSS | Real-time | Stateless | 听写 + 命令控制 |
| **Streams** | WSS | Real-time | **Stateful** | 会话转写 + FactsR 抽取 |
| **Transcripts** | REST | Sync→Async | Stateful | 批量音频文件 |

3 个子 tab: `Dictation` / `Ambient` / `Pre-recorded` (不同音频模式)

### 6.5 Embedded Assistant (proxy 模式)

**Endpoints** (host: `assistant.eu.corti.app`):
- `GET /api/auth/session` — 检查 assistant session
- `GET /api/ready` — assistant 服务就绪
- `POST /api/proxy/dd` — Datadog RUM proxy
- `POST /api/proxy/mp/t`, `/api/proxy/mp/e` — Mixpanel proxy
- `POST /api/proxy/relay/i/v0/e/`, `/api/proxy/relay/e/`, `/api/proxy/relay/flags/` — PostHog relay
- `GET /api/trpc/template.getAllSections` — tRPC query 取所有 sections
- `POST /embedded` — 创建 embedded session

**iCoDer 对应**: Embedded Assistant Page 现有 (`backend/app/api/embedded.py`), 但**不是**独立子域 proxy 模式, 复刻方向应是 "session init + tRPC template list + embedded 创建"。

### 6.6 Codes predict (§13.6)

**Endpoint**: `POST https://api.eu.corti.app/v2/tools/coding/predict-codes`

详见 `docs/corti-reverse-engineered/codes-predict-codes.md` — 15-system spec predictor (no LLM), 用于纯规则预测。

---

## 7. 数据模型 (PostgREST 表)

从 `/rest/v1/*` 推断的表清单:

| 表 | 用途 | iCoDer 对应 |
|---|---|---|
| `projects` | 项目元数据 (id, name, customer_id, plan, ...) | `Org/Tenant` |
| `project_memberships` | 成员绑定 (project_id, user_id, role) | `Org` membership |
| `team_invitations` | 邀请 (email, accepted_at, project_id, role) | `Org` invitation |
| `api_clients` | API 客户端 (client_id, project_id, name, secret_hash) | `API Client` |
| `agent_definitions` | Agent 模板定义 (system, tools, model, ...) | Agent hub |
| `project_assets` | 客户级资产 | `Customer` assets |
| `customer_assets` | 公开资产 | `Customer` |

**RPC**: `POST /rest/v1/rpc/is_limited_admin_user` — admin 角色校验。

---

## 8. Edge Functions (`/functions/v1/*`)

| 路径 | 用途 | iCoDer 对应状态 |
|---|---|---|
| `POST /functions/v1/projects/<id>/api_clients/<client_id>/access_token` | 颁发 ROPC access_token (5min TTL, scoped) | ✅ Phase 1.0 已对齐 |
| `GET /functions/v1/projects/<id>/billing/balance` | 项目余额 | ✅ Loop 4 已实现 |
| `GET /functions/v1/projects/<id>/onboarding` | onboarding 状态 | ⚠ stub |
| `GET /functions/v1/projects/<id>/assistant-settings` | embedded assistant 配置 | ⚠ stub |
| `GET /functions/v1/external/agents` | 公开 agent 目录 | ⚠ 部分 (Agent Hub) |
| `GET /functions/v1/public/projects/<id>/customers` | 公开 customer 列表 | ✅ Loop 1 已实现 |
| `POST /functions/v1/intercom-hmac` | Intercom HMAC 校验 | ❌ 缺 |

---

## 9. 顶部全局元素 (来自 home/agents 抓包)

| 元素 | 数据来源 | iCoDer 现状 |
|---|---|---|
| Live cost (6 位小数) | `GET /functions/v1/projects/<id>/billing/balance` | ✅ 已实现 (Loop 4) |
| Reset live cost | POST 触发 | ❌ 缺 |
| API Client dropdown | `GET /rest/v1/api_clients` | ✅ |
| $credits 余额 | `/billing/balance` | ✅ |
| Docs link | static | ✅ |
| **Theme toggle (深/浅)** | — | ❌ 缺 (P1) |
| Breadcrumb | URL 驱动 | ✅ |
| PostHog session replay | `prp.corti.app/s/` | — (第三方, 可选) |

**顶栏顺序** (固定): logo + breadcrumb → live cost pill → API Client dropdown → credits pill → theme toggle → Docs 按钮

---

## 10. 20 Pre-built Agents 清单 (Corti 官方 Agent 集)

> 来源: `/ai-studio/agents` Pre-built tab, 截图 `03_agents_prebuilt.png`

| # | Agent 名称 | 一句话描述 | iCoDer 现状 |
|---|---|---|---|
| 1 | **ICD-10 Index Navigator Agent** | Traverse ICD-10 Alphabetic Index from clinical terms to candidate codes for coder review | 部分 (ICD-9-CM-3 retriever 已做, ICD-10-CN Index Navigator 待做) |
| 2 | **Rule Explainer Agent** | Why a specific ICD-10-CM / ICD-10-PCS / CPT code was selected | ❌ 缺 |
| 3 | **Compliance Guardrail Agent** | Evaluate medical code sets against payer/org ruleset | 有 RuleEngine 但无 Guardrail Agent |
| 4 | **Code Validation Agent** | Validate proposed medical code sets against official coding rules | 部分 (R001-R010 + 修复 loop) |
| 5 | **Procedure Entity Extractor Agent** | Extract and assign procedure codes grounded in documented evidence | Stage 1 procedure_mentions (已做) |
| 6 | **Diagnostic Entity Extractor Agent** | Extract and assign diagnosis codes grounded in documented evidence | Stage 1 disease (已做) |
| 7 | **Surgical Registry Intelligence Agent** | Automate surgical registry data entry | ❌ 缺 |
| 8 | **ICU Admission Summary Agent** | ICU admission documentation by synthesizing EHR data | ❌ 缺 |
| 9 | **Triage and Initial Assessment Agent** | Emergency triage with validated risk scores | ❌ 缺 |
| 10 | **Note Completeness Agent** | Real-time checks for completeness/accuracy/compliance | Doctor 概念相近但粒度不同, 需重做 |
| 11 | **Medication Reconciliation Agent** | Medication errors prevention across admissions/transfers/discharges | ❌ 缺 |
| 12 | **Denial Appeals Agent** | Evidence-backed appeals aligned to payer requirements | ❌ 缺 |
| 13 | **Patient Discharge Education Agent** | Discharge instructions personalized | ❌ 缺 |
| 14 | **Nursing Shift Handoff Agent** | Structured shift handoffs surface critical info | ❌ 缺 |
| 15 | **Prior Authorization Agent** | PA documentation guideline-aligned | ❌ 缺 |
| 16 | **Referral Generator Agent** | Clinician-to-clinician referral letters | ❌ 缺 |
| 17 | **Clinical Education Agent** | Evidence-based explanations from authoritative sources | ❌ 缺 |
| 18 | **Medical Coding Agent** | Generate accurate medical codes grounded in clinical evidence | MedicalCodingPage (已做, IA 需对齐 Corti) |
| 19 | **Clinical Guidelines Agent** | Evaluate against professional clinical guidelines | ❌ 缺 |
| 20 | **Clinical Documentation Improvement (CDI) Agent** | Documentation gaps + provider queries | 之前想过的 CDI, 需做 |

**iCoDer 自创但 Corti 没有 → 应删除**:
- "MethodCompare" 概念 — Corti 没有 method 对比, 直接选 Agent
- "10 builtin methods" — Corti 是 Pre-built Agents 列表, 不是 methods
- "Doctor 自检" — Corti 没有 21 项 check, 改用 Note Completeness Agent + Coding 系统自带的 Validation
- "MethodSwitcher" — 删除, 改为 Coding System 下拉选择

---

## 11. Agentic Framework 核心概念 (A2A + Agent Card + Task + Message + Part + Artifact)

### 11.1 A2A 协议核心角色

| 角色 | 职责 |
|---|---|
| **User** | 发起请求的人或系统 |
| **A2A Client** | 代表 User 调用 A2A Server (即 agent) |
| **A2A Server** | Agent 本体, 暴露 A2A 接口 |

### 11.2 核心数据结构

| 概念 | 定义 |
|---|---|
| **Agent Card** | Agent 元数据 + capabilities + skills + default I/O modes + examples (JSON-LD schema) |
| **Task** | A2A 工作单元, 5 态: submitted → working → input-required / completed / failed / canceled |
| **Message** | Task 内的消息, 由一个或多个 Part 组成 (role: user/agent) |
| **Part** | Message 的最小单位: TextPart / DataPart / FilePart |
| **Artifact** | Task 产出 (不同于 Message, 是最终 deliverable) |

### 11.3 三层架构 (从 docs + 抓包联合提炼)

```
┌─────────────────────────────────────────────────────────┐
│  Corti Symphony  ← "model network + orchestration layer"│
│      ├── Text                                          │
│      └── Audio                                         │
├─────────────────────────────────────────────────────────┤
│  Agentic Framework (多 agent 架构)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Orchestrator │←→│   Memory     │←→│   Experts    │  │
│  │  (中枢)       │  │ (持久 context)│  │  (原子能力)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         ↑ A2A 协议   ↑ Context/Memory  ↑ MCP 协议      │
├─────────────────────────────────────────────────────────┤
│  Expert Registry (first-party + third-party MCP)         │
│  • memory-expert        • coding-expert  ← 核心        │
│  • medical-calculator   • drugbank-expert                │
│  • posos-expert         • pubmed-expert                  │
│  • clinical-trials      • web-search                     │
│  • interviewing                                            │
├─────────────────────────────────────────────────────────┤
│  Integrations                                             │
│  • 预置产品:Corti Assistant (EHR-agnostic ambient scribe) │
│  • Embedded Web Components (dictation/ambient)            │
│  • SDKs: JS / .NET / Dictation / Ambient                │
└─────────────────────────────────────────────────────────┘
```

### 11.4 Orchestrator 职责

- **Reasoning & planning** — 分析请求, 决定步骤
- **Expert selection** — 决定调哪些 expert、顺序、传什么数据
- **Task decomposition** — 复杂请求拆成离散任务
- **Response generation** — 汇总 expert 结果, 生成最终回复
- **Context management** — Orchestrator 拥有**全部 context** 访问权, Expert 通常只有 scoped
- **Safety enforcement** — 护栏、类型校验、策略约束

**关键设计**: Orchestrator 不做专项工作, 只做编排; 专项工作全交给 Expert。

### 11.5 Expert 设计

Expert = LLM-powered capability, 执行小型、离散任务。

```json
{
  "type": "expert",
  "id": "ecg_interpreter",
  "name": "ECG Interpreter",
  "description": "Interprets 12 lead ECGs.",
  "systemPrompt": "You are an expert ECG interpreter.",
  "mcpServers": [
    {
      "id": "srv1",
      "name": "ECG API Svc",
      "transportType": "streamable_http",
      "authorizationType": "none",
      "url": "https://api.ecg.com/x"
    }
  ]
}
```

**Expert 三大特性**:
1. **可自定义** — Corti 包装 MCP server, 用户控制系统 prompt
2. **可发现** — 通过 `GET /v2/agents/list-registry-experts` API 程序化发现
3. **可组合** — Multi-Agent Composition (A2A 协议, coming soon)

### 11.6 交互模式

| 模式 | 用途 | 例子 |
|---|---|---|
| **Request/Response (Polling)** | 同步, 大多数 Corti API | STT Transcripts |
| **Streaming with SSE** | 实时体验, ambient note / live guidance | Embedded Assistant |

### 11.7 认证 (OAuth 2.0 client_credentials)

```bash
# 拿 access token (Keycloak, 5min TTL, scoped)
curl "https://auth.${ENVIRONMENT}.corti.app/realms/base/protocol/openid-connect/token" \
  -d "client_id=${CLIENT_ID}" -d "client_secret=${CLIENT_SECRET}" \
  -d 'grant_type=client_credentials' -d 'scope=openid'

# 用 token 调 API (强制 tenant header)
curl "https://api.${ENVIRONMENT}.corti.app/v2/interactions" \
  -H "Authorization: Bearer ${access_token}" \
  -H "Tenant-Name: base"
```

**Limited-scope tokens** (for browser STT):
- `scope="openid transcribe"` — 仅 STT Transcribe
- `scope="openid streams"` — 仅 Streams

---

## 12. URL 命名对齐表

| Corti | iCoDer 目标 |
|---|---|
| `https://console.corti.app` | `https://{tenant}.{region}.icoder.cloud` |
| `https://api.console.corti.app/rest/v1/*` | `https://{tenant}.{region}.icoder.cloud/api/v1/*` (FastAPI + SQLAlchemy) |
| `https://api.console.corti.app/functions/v1/*` | `https://{tenant}.{region}.icoder.cloud/api/v1/functions/*` |
| `https://api.eu.corti.app/v2/tools/*` | `https://{tenant}.{region}.icoder.cloud/api/v2/tools/*` |
| `https://assistant.eu.corti.app/api/*` | `https://{tenant}.{region}.icoder.cloud/assistant/api/*` (子路径) |
| `https://auth.eu.corti.app/realms/base/...` | `https://auth.{region}.icoder.cloud/realms/{tenant}/...` (or self-implemented JWT) |

**判断**: iCoDer 单域名子路径模式已通过 cloud flip 决议 (见 `project_cloud_flip_2026_06_27.md`), 路径完全对齐 Corti 即可。

---

## 13. 视觉设计系统 + 复刻路线图 + 资料清单

### 13.1 视觉系统

| 维度 | 规格 |
|---|---|
| **配色** | 极简 mono: off-white 背景 (#FAFAFA)、纯白面板、1px 浅灰分隔线; **主 CTA 全黑** (#000000); 中性灰文字 (#6B7280 / #9CA3AF); 唯一彩色 = lime-yellow (BETA 徽章 + 代码高亮); Embedded Assistant 露出 brand 蓝 (#3C61DD) |
| **字体** | Inter 风 sans-serif (页标题 28-32px semibold / 副标题 14px regular / 正文 14px); monospaced 用于代码块 (~13px) |
| **圆角** | 统一 `rounded-lg` (~8px) for 卡片/输入框/按钮 |
| **间距** | 8px grid, section gap 24-32px, page padding 32px |
| **图标** | Lucide-style 16-20px, 1.5px stroke, 全 monochrome |
| **阴影** | 极少; 深度靠 hairline border + 浅灰填充 |

### 13.2 信息架构模式

- **单一实体工作台** → cards
- **多行数据** (API clients, team, customers) → flat tables + 右下 pagination
- **项目选择** → cards

### 13.3 组件库

| 组件 | 样式 |
|---|---|
| Primary button | 实心黑 + 白字 + leading `+` icon |
| Secondary button | 白底 + 黑边 + 黑字 |
| Ghost button | 纯文字 + icon |
| Input | 1px 灰边, 固定 label 在上 |
| Search input | 前置 magnifier icon, 14px 半径 |
| Multi-select chip | `ICD-10-CM Outpatient ⓧ` |
| Segmented control | 2 选项 (Rendered/JSON, My/Default, Dictation/Ambient/Pre-recorded) |
| Toggle | pill, 右 on / 左 off |
| Code block | 浅灰底 + monospaced + 复制 icon |
| Modal | 居中 + dimmed backdrop + X 关闭 |
| Toast | 右下浮动卡 + 持续显示 (不自动消失) |

### 13.4 Microcopy 风格

- **CTA 动词 = 价值动词**: "Predict codes" / "Generate document" / "Extract facts" (而非 "Submit")
- **Empty state = 位置明确**: "Predicted codes will show here" / "Facts will appear here during recording"
- **Section header = 标题 + 一句话说明**: `Medical Coding — Convert unstructured clinical text...`
- **Tooltip `ⓘ` 图标** 在字段 label 旁, 密集

### 13.5 设计方法论 — 7 条观察

1. **密度 > 装饰** — 控制面 chrome 极简, 只包一个 endpoint 的薄壳
2. **API-as-product loud and clear** — 每屏 = 单个 REST/SSE 端点的包装
3. **配置 > 约束** — 每个默认做对的事(自动语种/默认 region/默认开 alert), 需要时一键 toggle
4. **Demo before commit** — 每个工作台都有 Samples + Guided demo, API Clients 默认建一个 client
5. **预置而非空画布** — 20 Pre-built Agents 是不可改的成品, Customize = clone 后改; blank canvas 隐藏在二级入口
6. **诚实地标注 beta** — Templates 顶部 "Powered by new templates API" + Provide feedback 链接
7. **审美偏开发者工具** (Stripe-like) 而非临床 SaaS — chrome 是 hairline, palette 是 mono, 品牌小且只在 embedded 时露蓝

### 13.6 复刻路线图 (4 phases)

#### Phase 1 — 核心工作台对齐

| # | 任务 | 现状 | 行动 |
|---|---|---|---|
| 1.0 | Authentication (OAuth 2.0 + tenant + scope) | 简单 JWT | ✅ Phase 1.0 已对齐 (4 gap closed) |
| 1.1 | Medical Coding endpoint 重命名 + schema 对齐 | `/api/v2/tools/coding/icoder/` | ✅ Phase 1.1 已对齐 (§3.1) |
| 1.2 | Text Generation 5 endpoints | 部分 | ✅ Phase 1.2 已对齐 (5 cycles wrap-up) |
| 1.3 | STT 3 endpoints (Transcribe/Streams/Transcripts) + Facts §13.5 + Codes predict §13.6 | 部分 | ✅ Phase 1.3 已对齐 (9 + 5 + 1 cycles CLOSED) |
| 1.4 | **Theme toggle** (深/浅) | ❌ 缺 | ⚠ 待做 (顶栏) |
| 1.5 | **Event Inspector** (右侧/底部日志面板) | ❌ 缺 | ⚠ 待做 |

#### Phase 2 — 业务侧 API 对齐

| # | 任务 |
|---|---|
| 2.1 | `GET /api/projects/{id}/billing/balance` ✅ |
| 2.2 | `POST /api/projects/{id}/api-clients/{client_id}/access-token` (ROPC) ✅ |
| 2.3 | `GET /api/projects/{id}/customers` ✅ |
| 2.4 | `GET /api/projects/{id}/onboarding` ⚠ stub |
| 2.5 | `GET /api/projects/{id}/assistant-settings` ⚠ stub |

#### Phase 3 — 20 Pre-built Agents 复刻 (大坑)

详见 §10。当前 iCoDer 仅 ~3/20 对齐 (Medical Coding Agent + 部分 Index Navigator + 部分 Code Validation)。剩余 17 个 Agent 需新建, 中国编码体系替换点: ICD-10-CM → ICD-10-CN, ICD-10-PCS → ICD-9-CM-3-CN, CPT → 删除, MS-DRG → CN-DRG/DIP。

#### Phase 4 — 部署与监控对齐

| # | 任务 |
|---|---|
| 4.1 | PostHog 自部署 (prp.corti.app 等价) |
| 4.2 | Intercom Tickets 嵌入 (or 自实现 TicketsPage) ✅ |
| 4.3 | Stripe Billing 全套 |
| 4.4 | Embedded Assistant 子域 proxy |

### 13.7 资料清单 (iCoDer 已有)

- **49 张全页截图**: `docs/corti-reverse-engineered/feature-flows/*/*.png`
- **15 个 `summary.json`** (每 feature 一个, 含全部 API 请求+响应): `docs/corti-reverse-engineered/feature-flows/*/summary.json`
- **完整原始抓包**: `docs/corti-reverse-engineered/api-contracts-v2.json` (1.74 MB)
- **历史抓包**: `api-contracts.json` (Step 0.2 page-load only) + `api-contracts-interactive.json` (Step 0.3 click-driven)
- **WS/SSE 流**: `ws-streams.jsonl`
- **文档站提取**: `docs/corti-reverse-engineered/docs-site/_extracted/*.md` (27 详细页面 + 377 索引)
- **per-feature 走查 md**: `feature-flows/ai-studio-*/summary.json` + 顶层 `*-*.md` (codes-predict-codes / documents-classic-list / facts-* / guided-* / stt-* / stream-asyncapi / ui-flows / interaction-graph)
- **Crawler 脚本**: `scripts/corti_deep_crawler.py` + `scripts/corti_docs_crawler.py` + `scripts/corti_reverse_engineer.py` + `scripts/corti_reverse_engineer_interact.py`

### 13.8 Crawler 使用方式

```bash
# 一次性 SSO bootstrap (headed Edge 弹窗手动登 Google)
python scripts/corti_reverse_engineer.py --auth-bootstrap

# 跑全部 15 个 feature (深 E2E, 每步 wait_for_api 验证)
python scripts/corti_deep_crawler.py --all

# 单个 feature
python scripts/corti_deep_crawler.py --only ai-studio-medical-coding

# 抓 docs.corti.ai 文档 (Mintlify + llms.txt)
python scripts/corti_docs_crawler.py
```

---

## 基线结论

Corti 是 **API 即产品的全栈医疗 AI 平台**, 以 **Corti Symphony** 模型网络 + **Agentic Framework** (Orchestrator + Memory + Experts) 为内核, 通过 4 大域名 (console / api.console / api.eu / assistant.eu) + 15 个 sidebar feature + 5 个 Studio tool + 20 个 Pre-built Agents + OAuth 2.0 + Keycloak tenant 隔离交付。

iCoDer 已对齐: Phase 1.0 OAuth (4 gap closed) / Phase 1.1 Medical Coding v2 / Phase 1.2 TextGen (5 cycles) / Phase 1.3 STT+Facts+Codes (15 cycles CLOSED) / Cloud flip (单域名子路径)。

iCoDer 未对齐: Theme toggle / Event Inspector / 17 个 Pre-built Agents / PostHog 自部署 / Stripe 全套 / Embedded Assistant 子域 proxy / Agentic Framework (Orchestrator + Memory + Experts 真实实装)。

**Stage 0 完成, 等待继续指令。**
