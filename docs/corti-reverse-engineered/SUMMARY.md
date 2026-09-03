# Corti Reverse Engineering — Summary

**Date**: 2026-06-30
**Crawler**: `scripts/corti_deep_crawler.py` (Step 0.4 — End-to-end per feature)
**Account**: `songluhua@gmail.com` (project `b8f8129a-c31d-407f-b723-6ecc592d31e4`)
**Output**: `docs/corti-reverse-engineered/` — `api-contracts-v2.json` (1.74 MB) + 49 screenshots + 15 per-feature `summary.json`

---

## 1. 架构层 (4 大域名 + 第三方)

| 域名 | 性质 | 用途 |
|---|---|---|
| **`console.corti.app`** | Web SPA (Remix) | UI 路由壳层；不直接接业务 API |
| **`api.console.corti.app`** | Supabase (PostgREST + Edge Functions) | 项目元数据、用户/团队/账单、客户、模板资产 |
| **`api.eu.corti.app`** | 独立 Studio API (`/v2/*`) | 核心 AI 工具：medical coding / fact extraction / text generation templates / STT |
| **`assistant.eu.corti.app`** | Embedded Assistant proxy (`/api/proxy/*`, `/api/trpc/*`) | Embedded Assistant 模式：session init, template tRPC, proxy to PostHog |
| **`prp.corti.app`** | PostHog (自部署) | Session recording (`/s/`), event capture (`/i/v0/e/`), feature flags (`/flags/`), surveys |
| `js.stripe.com` | 第三方 | Billing |
| `api-iam.intercom.io` | 第三方 | Tickets / Help |
| `analytics.google.com` / `www.googletagmanager.com` | 第三方 | GA4 + GTM |
| `script.crazyegg.com` | 第三方 | 热力图 |

**关键判断**：iCoDer 不应复用 Supabase/PostgREST。FastAPI + SQLAlchemy async 路由可直接对齐 Edge Functions 的 URL 模式。

---

## 2. Sidebar 入口与对应 API 域 (15 个 feature 全部跑完)

| Feature | 路径 | 主要 API | 请求数 |
|---|---|---|---|
| `home` | `/` (4 tabs) | PostHog flags/surveys + Intercom HMAC | 18 |
| `ai-studio-agents` | `/ai-studio/agents` | `/rest/v1/agent_definitions` + PostHog | 113 |
| `ai-studio-agents-new` | `/ai-studio/agents/new` | `/functions/v1/external/agents` + `/rest/v1/agent_definitions` | 21 |
| **`ai-studio-medical-coding`** | `/ai-studio/medical-coding` | **`POST /v2/tools/coding/`** (核心) | 51 |
| `ai-studio-text-generation` | `/ai-studio/text-generation` | `GET /v2/templates/` + `/rest/v1/project_assets` | 29 |
| `ai-studio-fact-extraction` | `/ai-studio/fact-extraction` | `POST /v2/tools/extract-facts` + `GET /v2/factgroups/` | 23 |
| `ai-studio-speech-to-text` | `/ai-studio/speech-to-text` | `POST /v2/interactions/` (audio upload) | 63 |
| **`ai-studio-embedded-asst`** | `/ai-studio/embedded-assistant` | **`assistant.eu.corti.app/api/proxy/*`** + `/api/trpc/template.getAllSections` | 137 |
| `api-clients` | `/api-clients` | `/rest/v1/api_clients` + `access_token` Edge Function | 39 |
| `team` | `/team` | `/rest/v1/project_memberships` + `/rest/v1/team_invitations` | 22 |
| `billing` | `/billing` | `/functions/v1/projects/<id>/billing/balance` + Stripe `r.stripe.com` | 55 |
| `customers` | `/customers` | `/functions/v1/public/projects/<id>/customers` | 21 |
| `templates` | `/templates` | `/rest/v1/api_clients` + `/functions/v1/projects/<id>/assistant-settings` | 50 |
| `settings` | `/settings` | `/rest/v1/projects` + `/rest/v1/team_invitations` | 24 |
| `developer-quickstart` | `/developer-quickstart` | `/rest/v1/api_clients` + auth + onboarding | 31 |

---

## 3. 核心 API 契约 (Studio Tools)

### 3.1 Medical Coding (核心复刻目标)

**Endpoint**: `POST https://api.eu.corti.app/v2/tools/coding/`

**Request** (来自 real EMR 抓包):
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
        {
          "contextIndex": 0,
          "text": "心脏超声示左心扩大,LVEF 38%",
          "start": 110,
          "end": 128
        }
      ],
      "alternatives": [
        {"code": "I50.20", "display": "Unspecified systolic (congestive) heart failure"},
        {"code": "I50.21", "display": "Acute systolic (congestive) heart failure"},
        ...
      ]
    }
  ]
}
```

**字段含义**:
- `context[]` — 多模态输入（text 类型，目前仅文本；未来可能音频/图像）
- `system[]` — 编码体系（可多选）：`icd10cm-outpatient` / `icd10cm-inpatient` / `icd10pcs` / `icd9cm` / `cpt`
- `evidences[]` — 每条 evidence 是一个 char span，绑定到具体 `contextIndex` + start/end offset
- `alternatives[]` — 备选编码（rerank 候选）

### 3.2 Fact Extraction

**Endpoint**: `POST https://api.eu.corti.app/v2/tools/extract-facts`

抓包见 `feature-flows/ai-studio-fact-extraction/summary.json`。

**关联目录**: `GET /v2/factgroups/` — 返回 fact group 分类体系。

### 3.3 Text Generation

**Endpoint**: `GET https://api.eu.corti.app/vv2/templates/` — 模板清单（对应 iCoDer Text Generation 工作台的 Template 下拉）。

### 3.4 Speech-to-Text

**Endpoint**: `POST https://api.eu.corti.app/v2/interactions/` — 音频上传 + 转写。

3 个子 tab: `Dictation` / `Ambient` / `Pre-recorded`（不同音频模式）。

### 3.5 Embedded Assistant (proxy 模式)

**Endpoints** (host: `assistant.eu.corti.app`):
- `GET /api/auth/session` — 检查 assistant session
- `GET /api/ready` — assistant 服务就绪
- `POST /api/proxy/dd` — Datadog RUM proxy
- `POST /api/proxy/mp/t`, `/api/proxy/mp/e` — Mixpanel proxy
- `POST /api/proxy/relay/i/v0/e/`, `/api/proxy/relay/e/`, `/api/proxy/relay/flags/` — PostHog relay
- `GET /api/trpc/template.getAllSections` — tRPC query 取所有 sections
- `POST /embedded` — 创建 embedded session

**iCoDer 对应**: Embedded Assistant Page 现有（`backend/app/api/embedded.py`），但**不是**独立子域 proxy 模式，复刻方向应是"session init + tRPC template list + embedded 创建"。

---

## 4. 数据模型 (PostgREST 表)

从 `/rest/v1/*` 推断的表清单：

| 表 | 用途 | iCoDer 对应 |
|---|---|---|
| `projects` | 项目元数据 (id, name, customer_id, plan, ...) | `Org/Tenant` |
| `project_memberships` | 成员绑定 (project_id, user_id, role) | `Org` |
| `team_invitations` | 邀请 (email, accepted_at, project_id, role) | `Org` invitation |
| `api_clients` | API 客户端 (client_id, project_id, name, secret_hash) | `API Client` |
| `agent_definitions` | Agent 模板定义 (system, tools, model, ...) | Agent hub |
| `project_assets` | 客户级资产 | `Customer` assets |
| `customer_assets` | 公开资产 | `Customer` |

**RPC**: `POST /rest/v1/rpc/is_limited_admin_user` — admin 角色校验。

---

## 5. Edge Functions (`/functions/v1/*`)

| 路径 | 用途 |
|---|---|
| `POST /functions/v1/projects/<id>/api_clients/<client_id>/access_token` | 颁发 ROPC access_token（**iCoDer 必须支持**） |
| `GET /functions/v1/projects/<id>/billing/balance` | 项目余额 |
| `GET /functions/v1/projects/<id>/onboarding` | onboarding 状态 |
| `GET /functions/v1/projects/<id>/assistant-settings` | embedded assistant 配置 |
| `GET /functions/v1/external/agents` | 公开 agent 目录 |
| `GET /functions/v1/public/projects/<id>/customers` | 公开 customer 列表 |
| `POST /functions/v1/intercom-hmac` | Intercom HMAC 校验 |

---

## 6. 顶部全局元素 (来自 home/agents 抓包)

| 元素 | 数据来源 | iCoDer 现状 |
|---|---|---|
| Live cost (6 位小数) | `GET /functions/v1/projects/<id>/billing/balance` | ✅ 已实现 (Loop 4) |
| Reset live cost | POST 触发 | ❌ 缺 |
| API Client dropdown | `GET /rest/v1/api_clients` | ✅ |
| $credits 余额 | `/billing/balance` | ✅ |
| Docs link | static | ✅ |
| **Theme toggle (深/浅)** | — | ❌ 缺 (P1) |
| Breadcrumb | URL 驱动 | ✅ |
| PostHog session replay | `prp.corti.app/s/` | — |

---

## 7. iCoDer 复刻路线图 (按优先级)

### Phase 1: 核心工作台对齐 (本次目标)

| # | 任务 | 现状 | 行动 |
|---|---|---|---|
| 1.1 | Medical Coding endpoint 重命名+schema 对齐 | `/api/medical-coding/generate` 是 iCoDer 内部路径，**应改为** `POST /api/v2/tools/coding/` 与 Corti 完全对齐 | ✅ 改路径 |
| 1.2 | Medical Coding response schema | iCoDer `HybridCodingAdapter.infer_async` 返回 `{extracted_diagnoses: [...]}`，需加 `codes[]` wrapper 与 Corti `{system, code, display, evidences[], alternatives[]}` 对齐 | ✅ 重构 |
| 1.3 | Fact Extraction endpoint | iCoDer 内部路径 → 改 `POST /api/v2/tools/extract-facts` | ✅ |
| 1.4 | Speech-to-Text endpoint | 改 `POST /api/v2/interactions/` | ✅ |
| 1.5 | Text Generation templates | iCoDer 无独立 templates 端点 → 加 `GET /api/v2/templates/` | ✅ 新增 |
| 1.6 | **Theme toggle** | iCoDer 全局无切换 | ✅ 加 (顶栏) |
| 1.7 | **Event Inspector** | iCoDer 无右侧日志面板 | ✅ 加 (右侧) |

### Phase 2: 业务侧 API 对齐

| # | 任务 |
|---|---|
| 2.1 | `GET /api/projects/{id}/billing/balance` |
| 2.2 | `POST /api/projects/{id}/api-clients/{client_id}/access-token` (ROPC) |
| 2.3 | `GET /api/projects/{id}/customers` |
| 2.4 | `GET /api/projects/{id}/onboarding` |
| 2.5 | `GET /api/projects/{id}/assistant-settings` |

### Phase 3: 20 Pre-built Agents 复刻 (大坑)

详见 `docs/corti-feature-inventory.md` 的 20 个清单。当前 iCoDer 仅 1/20 对齐（Medical Coding）。

### Phase 4: 部署与监控对齐

| # | 任务 |
|---|---|
| 4.1 | PostHog 自部署 (prp.corti.app) |
| 4.2 | Intercom Tickets 嵌入 |
| 4.3 | Stripe Billing 全套 |
| 4.4 | Embedded Assistant 子域 proxy |

---

## 8. 已确认的 URL 命名对齐表

| Corti | iCoDer 目标 |
|---|---|
| `https://console.corti.app` | `https://{tenant}.{region}.icoder.cloud` |
| `https://api.console.corti.app/rest/v1/*` | `https://{tenant}.{region}.icoder.cloud/api/v1/*` (FastAPI + SQLAlchemy) |
| `https://api.console.corti.app/functions/v1/*` | `https://{tenant}.{region}.icoder.cloud/api/v1/functions/*` |
| `https://api.eu.corti.app/v2/tools/*` | `https://{tenant}.{region}.icoder.cloud/api/v2/tools/*` |
| `https://assistant.eu.corti.app/api/*` | `https://{tenant}.{region}.icoder.cloud/assistant/api/*` (子路径) |

**判断**：iCoDer 单域名子路径模式已通过 cloud flip 决议（见 `project_cloud_flip_2026_06_27.md`），路径完全对齐 Corti 即可。

---

## 9. 截图 & 详细数据

- 49 张全页截图：`docs/corti-reverse-engineered/feature-flows/*/*.png`
- 15 个 `summary.json`（每 feature 一个，含全部 API 请求+响应）
- 完整原始抓包：`docs/corti-reverse-engineered/api-contracts-v2.json` (1.74 MB)
- 历史抓包：`api-contracts.json` (Step 0.2 page-load only) + `api-contracts-interactive.json` (Step 0.3 click-driven)
- WS/SSE 流：`ws-streams.jsonl`

---

## 10. Crawler 使用方式

```bash
# 一次性 SSO bootstrap（headed Edge 弹窗手动登 Google）
python scripts/corti_reverse_engineer.py --auth-bootstrap

# 跑全部 15 个 feature（深 E2E，每步 wait_for_api 验证）
python scripts/corti_deep_crawler.py --all

# 单个 feature
python scripts/corti_deep_crawler.py --only ai-studio-medical-coding

# 多个 feature 串行
python scripts/corti_deep_crawler.py --features ai-studio-medical-coding,ai-studio-fact-extraction

# 抓 docs.corti.ai 文档(Mintlify + llms.txt)
python scripts/corti_docs_crawler.py

# 从某个 feature 恢复
python scripts/corti_deep_crawler.py --from settings
```

---

## 11. 产品定位 (从 docs.corti.ai 提炼)

> 来源: `docs/corti-reverse-engineered/docs-site/_extracted/*.md` + `docs-content.json` (27 详细页面 + 377 索引)

### 11.1 一句话定位

**Corti 是面向医疗开发者的全栈 AI 平台** (all-in-one AI stack for healthcare)。**Corti Symphony** 是其模型网络 + 编排层 (Text + Audio),驱动 STT / Text Generation / Agent 三大能力。

> 原文: "Corti is the all-in-one AI stack for healthcare, built for medical accuracy, compliance, and scale."

### 11.2 产品哲学 — 解决 LLM 在医疗的两大根本缺口

Corti 文档明确定义了 LLM 在临床场景的**两大根本缺口**,Corti 通过 Agentic Framework 解决:

| # | LLM 缺口 | Corti 解决方案 |
|---|---|---|
| 1 | **没有可靠的临床数据访问**(LLM 只能基于内部知识推断) | **Expert 工具调用 + 检索增强**:Agents 通过检索从可信外部工具验证事实,而不是 hallucinate |
| 2 | **无法安全地作用于世界**(Clinical workflow 需要调 EHR、写文档、配药品、触发下游流程) | **可控执行层**:允许 agent 计划动作 + 调工具 + 协调多步 workflow,但强制 **safety boundaries**;需要时**暂停 + 请求人类审批 + 明确同意后才恢复** |

### 11.3 设计原则 (8 条)

来自 `agentic/overview`:

1. **Safety First** — 类型化输入输出、显式工具 schema、action-taking 护栏
2. **Auditability** — 每个决策和工具调用可观察、可回放、结构化日志
3. **Domain-Specific Reasoning** — 微调推理层,专为医疗语言/工作流/合规优化
4. **Multi-Agent Architecture** — 多 agent 而非单体 LLM
5. **Memory & Context Management** — 持久化、context-aware,支持多活动 context (threads)
6. **Ecosystem of Prebuilt Experts** — 预置 expert 库,连接数据源/工具/服务
7. **Third-Party Integrations** — 直插 EHR / 临床决策支持 / 医学知识库
8. **Run-time Context** — 每个 query 传结构化 context(如 FHIR resources)

### 11.4 目标用户

- **Healthcare software companies** — 把智能自动化嵌入产品
- **Enterprise customers** — 内部 AI-powered clinical workflow
- **Advanced engineering teams** — 需要灵活、控制力、安全保证,不想从零自建 agent 基础设施

**明确定位**:不是 prompt-based chatbot,而是 **production-grade clinical AI systems**。

### 11.5 Agent vs Workflow (Corti 的二元区分)

| | Agents | Workflows |
|---|---|---|
| 性质 | 自主思考/推理/适应 | 结构化、预定义路径 |
| 适合 | 不可预测、开放、需要判断 | 重复、一致性、合规 |
| 比喻 | 大厨(看食材随机应变) | 食谱/清单 |
| 实现 | Agentic Framework | 其他 API 套件 |

---

## 12. 架构 (从 docs + 抓包联合提炼)

### 12.1 三层架构图

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

### 12.2 Orchestrator 职责

- **Reasoning & planning** — 分析请求,决定步骤
- **Expert selection** — 决定调哪些 expert、顺序、传什么数据
- **Task decomposition** — 复杂请求拆成离散任务
- **Response generation** — 汇总 expert 结果,生成最终回复
- **Context management** — Orchestrator 拥有**全部 context** 访问权,Expert 通常只有 scoped
- **Safety enforcement** — 护栏、类型校验、策略约束

> 关键设计:**Orchestrator 不做专项工作**,只做编排;专项工作全交给 Expert。

### 12.3 Expert 设计

**Expert = LLM-powered capability,执行小型、离散任务**

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
1. **可自定义**:Corti 包装 MCP server,用户控制系统 prompt
2. **可发现**:通过 `GET /v2/agents/list-registry-experts` API 程序化发现
3. **可组合**:Multi-Agent Composition (A2A 协议,coming soon)

### 12.4 交互模式

| 模式 | 用途 | 例子 |
|---|---|---|
| **Request/Response (Polling)** | 同步,大多数 Corti API | STT Transcripts |
| **Streaming with SSE** | 实时体验,ambient note / live guidance | Embedded Assistant |

---

## 13. 技术路线 (从 docs + 抓包联合提炼)

### 13.1 域与基础设施

| 域名 | 性质 | 来源 |
|---|---|---|
| `console.corti.app` | Web SPA (Remix) | 抓包 |
| `api.console.corti.app` | Supabase PostgREST + Edge Functions | 抓包 + 推断 |
| `api.{eu,us}.corti.app` | 独立 Studio API (`/v2/*`) | 抓包 |
| `assistant.{eu,us}.corti.app` | Embedded Assistant proxy + tRPC | 抓包 |
| `prp.corti.app` | 自部署 PostHog (session replay + feature flags) | 抓包 |
| `auth.{eu,us}.corti.app` | **Keycloak** (OAuth 2.0 client-credentials) | **docs 明文** |
| `mintcdn.com/corti/...` | Mintlify 文档 CDN | 抓包 (文档) |

### 13.2 认证 (OAuth 2.0 client_credentials)

**明文理由 (docs)**:
- API key 是 long-lived → 泄漏影响大
- Client credentials → **5 分钟 short-lived tokens** + scope + tenant 隔离

```bash
# 拿 access token
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

### 13.3 STT 三个端点 (按场景选择)

| 端点 | 连接 | 处理 | 架构 | 用途 |
|---|---|---|---|---|
| **Transcribe** | WSS | Real-time | Stateless | 听写 + 命令控制 |
| **Streams** | WSS | Real-time | **Stateful** | 会话转写 + FactsR 抽取 |
| **Transcripts** | REST | Sync→Async | Stateful | 批量音频文件 |

### 13.4 Text Generation 五个端点

| 端点 | 连接 | 架构 | 用途 | 状态 |
|---|---|---|---|---|
| Streams | WSS | Stateful | 实时 FactsR 抽取 | GA |
| **FactsR™** | REST | **Stateless** | 文本→事实 | GA |
| Guided Document Synthesis | REST | Stateless/Stateful | 结构化文档生成 (template 驱动) | **Beta** |
| Sections & Templates | REST | — | 模板/Section CRUD | **Beta** |
| Documents Classic | REST | Stateful | 文档生成 (templateKey) | **Planned deprecation** |

> 重点:**Guided Documents 是 interaction-optional** — 可以 supply `context` (text/transcript/facts) 做 stateless call,或 supply `interactionId` 拉既有 interaction 的 facts/transcripts。两者目前**互斥**,合并是 roadmap。

### 13.5 协议与数据格式

- **A2A (Agent-to-Agent)** — Agent 间通信协议
- **MCP (Model Context Protocol)** — Expert 暴露 tools/list + tools/call
- **FHIR** — Run-time context 传结构化医疗数据
- **OAuth 2.0 + JWT** — 认证
- **Keycloak** — IdP / tenant 隔离
- **PostHog** — 产品分析 + session replay + feature flags

### 13.6 Compliance / Trust

`about/compliance` 页面未抓到(skip in crawler),但 llms.txt 列出分类:`HIPAA`,`SOC2`,`GDPR`,`data-residency`,`security_best_practices`。EU/US region split 是 data residency 的体现。

---

## 14. 设计方法 (从 49 张截图提炼)

> 来源:`feature-flows/*/*.png` (49 张,2026-06-30 Playwright SSO 抓取)

### 14.1 视觉系统

| 维度 | 规格 |
|---|---|
| **配色** | 极简 mono:off-white 背景 (#FAFAFA)、纯白面板、1px 浅灰分隔线;**主 CTA 全黑** (#000000);中性灰文字 (#6B7280 / #9CA3AF);唯一彩色 = lime-yellow (BETA 徽章 + 代码高亮);Embedded Assistant 露出 brand 蓝 (#3C61DD) |
| **字体** | Inter 风 sans-serif (页标题 28-32px semibold / 副标题 14px regular / 正文 14px);monospaced 用于代码块 (~13px) |
| **圆角** | 统一 `rounded-lg` (~8px) for 卡片/输入框/按钮 |
| **间距** | 8px grid,section gap 24-32px,page padding 32px |
| **图标** | Lucide-style 16-20px, 1.5px stroke, 全 monochrome |
| **阴影** | 极少;深度靠 hairline border + 浅灰填充 |

### 14.2 信息架构模式

**Sidebar 结构**:
- 顶部:项目切换 (可折叠"Your Projects")
- 主导航:Home → Developer quickstart → AI Studio section → 8 子页 → Manage section → 7 子页 → Support
- AI Studio 顺序:**Overview → Agents → Speech to Text** (含 3 子页) → Text Generation → Embedded Assistant → Fact Extraction → Medical Coding
- Manage 顺序:API Clients → Team → Billing → Usage → Customers → Templates (BETA) → Settings
- 缩进规则:仅 1 级 (16px)

**Top bar** (顺序固定):
- 左:logo + breadcrumb (`Agents › Pre-built Agents`)
- 右 (密集 4-元素):live cost pill → API Client dropdown → credits pill ($49.37) → theme toggle → Docs 按钮

**Cards vs List vs Table**:
- 单一实体工作台 → **cards**
- 多行数据 (API clients, team, customers) → **flat tables** + 右下 pagination
- 项目选择 → cards

### 14.3 工作台通用模式 (5 个 Studio tool 共享)

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

**共同元素**:
- 左 Input / 右 Output 50/50 split
- Input 控件:Samples (demo 文本) + 清除 + 复制
- Output 控件:Rendered/JSON toggle + 清除 + 复制 + 下载
- 右侧 Settings panel (Settings/Code tabs + Template dropdown + Output language)
- 底部 Event Inspector 可折叠
- Empty state 一句话: "Predicted codes will show here"

### 14.4 组件库

| 组件 | 样式 |
|---|---|
| Primary button | 实心黑 + 白字 + leading `+` icon |
| Secondary button | 白底 + 黑边 + 黑字 |
| Ghost button | 纯文字 + icon |
| Input | 1px 灰边,固定 label 在上 |
| Search input | 前置 magnifier icon,14px 半径 |
| Multi-select chip | `ICD-10-CM Outpatient ⓧ` |
| Segmented control | 2 选项 (Rendered/JSON, My/Default, Dictation/Ambient/Pre-recorded) |
| Toggle | pill,右 on / 左 off |
| Code block | 浅灰底 + monospaced + 复制 icon |
| Modal | 居中 + dimmed backdrop + X 关闭 |
| Toast | 右下浮动卡 + 持续显示 (不自动消失) |

### 14.5 Microcopy 风格

- **CTA 动词 = 价值动词**:"Predict codes" / "Generate document" / "Extract facts" (而非 "Submit")
- **Empty state = 位置明确**:"Predicted codes will show here" / "Facts will appear here during recording"
- **Section header = 标题 + 一句话说明**: `Medical Coding — Convert unstructured clinical text...`
- **Tooltip `ⓘ` 图标** 在字段 label 旁,密集

### 14.6 设计方法论 — 7 条观察

1. **密度 > 装饰** — 控制面 chrome 极简,只包一个 endpoint 的薄壳
2. **API-as-product loud and clear** — 每屏 = 单个 REST/SSE 端点的包装
3. **配置 > 约束** — 每个默认做对的事(自动语种/默认 region/默认开 alert),需要时一键 toggle
4. **Demo before commit** — 每个工作台都有 Samples + Guided demo,API Clients 默认建一个 client
5. **预置而非空画布** — 20 Pre-built Agents 是**不可改的成品**,Customize = clone 后改;blank canvas 隐藏在二级入口
6. **诚实地标注 beta** — Templates 顶部 "Powered by new templates API" + Provide feedback 链接
7. **审美偏开发者工具**(Stripe-like)而非临床 SaaS — chrome 是 hairline,palette 是 mono,品牌小且只在 embedded 时露蓝

---

## 15. iCoDer 复刻对齐原则 (基于 §11-§14 提炼)

> 用户反馈:`技术选择不确定时默认参考 Corti 实现` (memory: feedback_corti_default_when_uncertain)

### 15.1 产品定位对齐

- iCoDer 仍聚焦中国医院场景,但应保留 **Corti-style 全栈 AI 平台**姿态
- 抛弃"数据不出院"叙事 → 改为"PHI 脱敏 + 合规审计"(已 by project_cloud_flip)
- 模板/SDK/MCP server 等基础设施复刻;中国编码体系作为差异化层

### 15.2 架构对齐

| Corti | iCoDer 当前 | 应改 |
|---|---|---|
| Orchestrator (multi-agent) | 单体 Adapter + Hybrid | ✅ Phase 1.1 已有草案 E2 |
| Memory (Context/Memory) | 缺 | ✅ 已有 E1.x 系列 (context_memory) |
| Experts (MCP-wrapped) | iCoDer Expert Library (硬编码) | ✅ 应改 MCP server 包装 |
| OAuth 2.0 + JWT + tenant | 简单 JWT | ✅ 应改 (Phase 1.2) |
| A2A protocol | 缺 | ❌ 暂缓 |
| Pre-built Experts 20 | 16 pack 中 1 真对齐 | ❌ Phase 2 |

### 15.3 技术栈对齐

| 维度 | Corti | iCoDer | 差距 |
|---|---|---|---|
| 文档 | Mintlify | 自写 markdown | 应统一 doc site |
| 认证 | Keycloak OAuth 2.0 | 简单 JWT | 改 Keycloak or 自实现 |
| 流协议 | SSE + WSS | 部分 | 补 SSE 端点 (Event Inspector 后端) |
| 编排 | 自研 Orchestrator | 单 AgentRunner | 实施 Orchestrator + Experts |
| FHIR 集成 | Run-time context | FHIR 部分已实现 | 完整化 |

### 15.4 UI 对齐 (按截图提炼)

| Corti | iCoDer 现状 | 应改 |
|---|---|---|
| Theme toggle (深/浅) | ❌ 缺 | 加 (顶栏) |
| Event Inspector (右侧面板) | ❌ 缺 | 加 (工作台底部) |
| Live cost (6 位小数 + reset) | ✅ Loop 4 | — |
| Coding systems multi-select chip | 部分 | 强化 |
| Rendered/JSON toggle | 部分 | 统一 |
| 8px 圆角 + 1px 灰边 | 大致 | 规范化 |
| Inter 字体 + 14px 正文 | 部分 | 统一 typography token |
| 黑 CTA | 部分 | 统一 |

### 15.5 Phase 1 重排 (基于文档 + 截图提炼)

按 `Corti 文档明确指出的 4 个核心能力 + iCoDer 现状` 重排 Phase 1:

1. **Authentication (OAuth 2.0 + tenant)** — Phase 1.0 (前置)
2. **Medical Coding 路径 + schema 对齐** (§3.1) — Phase 1.1
3. **Text Generation 5 endpoints** (§13.4) — Phase 1.2 (抽取 2 个 GA 端点即可)
4. **STT 3 endpoints** (§13.3) — Phase 1.3 (优先 Transcribe + Transcripts)
5. **Agentic Framework (Orchestrator + Experts + Memory)** — Phase 2 (大坑,先 E2.x 沉淀)
6. **UI:** Theme toggle + Event Inspector — Phase 1.x (独立轨道)
7. **UI:** 工作台通用模式 — Phase 1.x (Layout 组件库抽离)
8. **Compliance:** HIPAA/SOC2/GDPR docs — 暂缓 (中国合规不同)

### 15.6 文档站本身

Corti 用 Mintlify 自部署,iCoDer 可考虑:
- Docusaurus + 中文
- 或 Mintlify OSS
- 必须含 `llms.txt` (AI ingestion 友好)
- 必须含 **product positioning + architecture 显式页** (Corti 文档里都是显式章节,新开发者能 5 分钟了解全局)