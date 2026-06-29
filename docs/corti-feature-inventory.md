# Corti Feature Inventory (work-in-progress)

> 来源: 直登 https://console.corti.app/ 走查 songluhua@gmail.com,2026-06-29 起。
> 项目 ID sample: b8f8129a-c31d-407f-b723-6ecc592d31e4
> 走查原则:每个 sidebar 入口 / 每个 tab / 每个 modal 截图 + IA + 关键交互记录。

## 顶层 IA(sidebar,从 console.corti.app/project/<id> 抽取)

| 段 | 入口 | iCoDer 现状 | 备注 |
|---|---|---|---|
| Top | Home | iCoDer 有 HomePage,但 IA 不一样 | |
| Top | Developer quickstart | iCoDer 有 DeveloperQuickstartPage | |
| AI Studio | Overview | iCoDer 有 AIStudioOverviewPage | |
| AI Studio | Agents | iCoDer 有 AgentsPage / AgentHubPage / AgentDetailPage | |
| AI Studio | Speech to Text (Dictation / Ambient / Pre-recorded) | iCoDer 有 SpeechToTextPage | |
| AI Studio | Text Generation | iCoDer 有 TextGenerationPage | |
| AI Studio | Embedded Assistant | iCoDer 有 EmbeddedAssistantPage + EmbedDemoCodingReviewPage | |
| AI Studio | Fact Extraction | iCoDer 有 FactExtractionPage | |
| AI Studio | **Medical Coding** | iCoDer 有 MedicalCodingPage + MethodComparePage + (已删)homepage_coding_review | **核心** — 中国编码体系替换点 |
| Manage | API Clients | iCoDer 有 APIClientsPage | |
| Manage | Team | iCoDer 有 TeamPage | |
| Manage | Billing | iCoDer 有 BillingPage | |
| Manage | Usage | iCoDer 有 UsagePage | |
| Manage | Customers | iCoDer **没有** | 待 walk 看是否需要 |
| Manage | Templates (Beta) | iCoDer **没有** | 待 walk 看是否需要 |
| Manage | Settings | iCoDer 有 SettingsPage | |
| Support | Get Help | iCoDer 有 SupportPage | |
| Support | Tickets Portal | iCoDer **没有** | 待 walk |

## Project Home 页面(`/project/<id>`) — 顶部 4 tabs

| Tab | 内容(从 snapshot 抽) | 备注 |
|---|---|---|
| Transcribe | "Capture conversation in real time for ambient scribes and clinical-grade dictation applications" / Start recording / Developer quickstart | STT 入口 |
| Document | (待 walk) | |
| Chat | (待 walk) | |
| **Code NEW** | (待 walk — 重点) | 编码工作台入口 |

## 用户态

- 用户名: Luhua Song (songluhua@gmail.com)
- 余额: $49.51(可用 credits)
- 已消耗: $0.00
- 项目数: 2(Songluhua × 2,ID `b8f8129a...` 和 `4c4193c7...`,Created 31-Dec-2025)

## 截图清单

- `01_home_overview.png` — Project home with 4 tabs (Transcribe/Document/Chat/Code NEW)

## 待 walk 顺序

1. Project home 4 tabs(Transcribe/Document/Chat/Code NEW)
2. AI Studio > Overview
3. AI Studio > Agents
4. AI Studio > Speech to Text(3 子页)
5. AI Studio > Text Generation
6. AI Studio > Embedded Assistant
7. AI Studio > Fact Extraction
8. **AI Studio > Medical Coding(中国编码替换核心)**
9. Manage 7 项
10. Support 2 项
11. Home / Developer quickstart
12. 顶栏交互(theme toggle / Docs / user menu)

## iCoDer 去留决策矩阵

走查后逐项填:
- Corti 有 X → iCoDer 保留/改造/重写
- Corti 没 X → iCoDer 删除
- 中国编码体系替换点 ICD-10-CN / ICD-9-CM-3-CN / CN-DRG / DIP

---

## AI Studio > Agents > Pre-built Agents(20 个,Corti 官方 Agent 集)

> 来源: `/ai-studio/agents` Pre-built tab,截图 `03_agents_prebuilt.png`

| # | Agent 名称 | 一句话描述 | iCoDer 现状 |
|---|---|---|---|
| 1 | **ICD-10 Index Navigator Agent** | Traverse ICD-10 Alphabetic Index from clinical terms to candidate codes for coder review | iCoDer 部分对应(ICD-9-CM-3 retriever 已做,ICD-10-CN Index Navigator 待做) |
| 2 | **Rule Explainer Agent** | Why a specific ICD-10-CM / ICD-10-PCS / CPT code was selected | **iCoDer 缺** |
| 3 | **Compliance Guardrail Agent** | Evaluate medical code sets against payer/org ruleset | iCoDer 有 RuleEngine 但无 Guardrail Agent |
| 4 | **Code Validation Agent** | Validate proposed medical code sets against official coding rules | iCoDer 部分对应(R001-R010 + 修复 loop) |
| 5 | **Procedure Entity Extractor Agent** | Extract and assign procedure codes grounded in documented evidence | iCoDer Stage 1 procedure_mentions(已做) |
| 6 | **Diagnostic Entity Extractor Agent** | Extract and assign diagnosis codes grounded in documented evidence | iCoDer Stage 1 disease(已做) |
| 7 | **Surgical Registry Intelligence Agent** | Automate surgical registry data entry | **iCoDer 缺** |
| 8 | **ICU Admission Summary Agent** | ICU admission documentation by synthesizing EHR data | **iCoDer 缺** |
| 9 | **Triage and Initial Assessment Agent** | Emergency triage with validated risk scores | **iCoDer 缺** |
| 10 | **Note Completeness Agent** | Real-time checks for completeness/accuracy/compliance | iCoDer 的"Doctor"概念相近但粒度不同,**需重做** |
| 11 | **Medication Reconciliation Agent** | Medication errors prevention across admissions/transfers/discharges | **iCoDer 缺** |
| 12 | **Denial Appeals Agent** | Evidence-backed appeals aligned to payer requirements | **iCoDer 缺** |
| 13 | **Patient Discharge Education Agent** | Discharge instructions personalized | **iCoDer 缺** |
| 14 | **Nursing Shift Handoff Agent** | Structured shift handoffs surface critical info | **iCoDer 缺** |
| 15 | **Prior Authorization Agent** | PA documentation guideline-aligned | **iCoDer 缺** |
| 16 | **Referral Generator Agent** | Clinician-to-clinician referral letters | **iCoDer 缺** |
| 17 | **Clinical Education Agent** | Evidence-based explanations from authoritative sources | **iCoDer 缺** |
| 18 | **Medical Coding Agent** | Generate accurate medical codes grounded in clinical evidence | iCoDer MedicalCodingPage(已做,但 IA 需对齐 Corti) |
| 19 | **Clinical Guidelines Agent** | Evaluate against professional clinical guidelines | **iCoDer 缺** |
| 20 | **Clinical Documentation Improvement (CDI) Agent** | Documentation gaps + provider queries | iCoDer 之前想过的 CDI,**需做** |

**iCoDer 自创但 Corti 没有 → 删除**:
- "MethodCompare" 概念 — Corti 没有 method 对比,直接选 Agent(Medical Coding Agent)
- "10 builtin methods" — Corti 是 Pre-built Agents 列表,不是 methods
- "Doctor 自检" — Corti 没有 21 项 check,改用 Note Completeness Agent + Coding 系统自带的 Validation
- "MethodSwitcher" — 删除,改为 Coding System 下拉选择(ICD-10-CM Outpatient 等)

**截图**:
- `03_agents_prebuilt.png` — 20 个 pre-built agents 列表

---

## AI Studio > Agents > New Agent(`/ai-studio/agents/pre-built-agents` 路由共用)

| 区段 | 内容 | 备注 |
|---|---|---|
| Start from scratch | "Configure your agent from the ground up" + Create agent button | 用户自建 |
| Use a template | "Start with a pre-configured agent" + 搜索框 + 20 个 agent 单选列表 | **就是 pre-built agents 列表**,但加了 radio 选择 |
| 选中后预览 | Agent 名 + 描述 + **Customize agent** 按钮 + **"Ask the agent..."** 聊天输入框 + Add context / What can you do? | 试运行界面 = 聊天式 |

**关键发现**:
- 20 个 pre-built agents 既在 `/ai-studio/agents` (Pre-built tab) 列表展示,也在 New Agent 模板选择里展示(双入口)
- "Ask the agent..." 是统一的 try-it-out 交互(聊天式),iCoDer 当前 MedicalCodingPage 是表单式输入 → 需改为聊天 + 按钮混合(保留 textarea 用于粘贴大段 EMR)
- 每个 agent 的 preview 是同一个聊天壳子,根据选中的 agent 切换 system prompt
- "Customize agent" → 进入 agent builder(类似 workflow builder)

**iCoDer 对齐**:
- iCoDer Agent Hub / AgentDetailPage 需加 Pre-built / My agents 切分
- 每个 Pre-built agent 一个卡片,点开 preview = 聊天 + Customize 按钮
- "Customize agent" 进入 builder(iCoDer 当前没有 agent builder UI,需新做)

---

## 走查完整清单(15 页面)

| # | URL | 关键 IA | 截图 |
|---|---|---|---|
| 1 | `/project/<id>` Home | 4 tabs: Transcribe / Document / Chat / **Code NEW**(promo → AI Studio) | `01_home_overview.png` |
| 2 | `/ai-studio/medical-coding` | 编码系统 multi-select(ICD-10-CM Outpatient)+ Input + Output(Rendered/JSON toggle)+ Event Inspector + 5 codes with evidence+alternatives | `02_medical_coding.png` `02b_medical_coding_predicted.png` |
| 3 | `/ai-studio/agents` | My agents / Pre-built agents 切分 + Find an agent + Created by/Use case 过滤器 | (未单独截,用 03) |
| 4 | `/ai-studio/agents/pre-built-agents` | Start from scratch + Use a template(20 个 agent 列表)+ Customize agent + Ask the agent... 聊天 | `03_agents_prebuilt.png` `04_agent_new.png` |
| 5 | `/ai-studio/speech-to-text` (Dictation) | Web Component preview + Start recording + Dictated text + Detected commands + Settings(语言) | `05_stt.png` |
| 6 | `/ai-studio/text-generation` | Input(Samples/Clear/Copy)+ Template 选择 + Output language + Generate document | `06_text_gen.png` |
| 7 | `/ai-studio/fact-extraction` | Input + Extract facts + Output language | `07_fact.png` |
| 8 | `/ai-studio/embedded-assistant` | Preview(初始化中)+ Session defaults(Primary language/Default mode) | `08_embed.png` |
| 9 | `/templates` (Manage Templates Beta) | Manage templates and sections + Template builder + View: Templates/Sections + 搜索 | `09_templates.png`(原本 10) |
| 10 | `/customers` | Manage customers for Embedded Assistant + Add customer + Search(name/customer ID/region/tenant) | `11_customers.png` |
| 11 | `/api-clients/default-clients` | Create API client + My clients/Default clients + Client ID 展示 | `12_api_clients.png` |
| 12 | `/team` | Invite + Members/Invitations 切分 + Email/Name/Role/Actions 表 | `13_team.png` |
| 13 | `/billing` | Plan/Billing History/Business info 切分 | `14_billing.png` |
| 14 | `/settings` | Project settings + Project Name + Project ID + Copy ID | `15_settings.png` |
| 15 | `/developer-quickstart` | View: Code with AI tools / JS SDK / .NET SDK + AI tools(Claude/Cursor/Codex/Lovable) + Step 1: use case + Step 2: prompt + credentials | (需补截图) |

**未走 / 404**:
- `/manage/customers` 路由 404,真地址是 `/customers`
- Speech to Text > Ambient / Pre-recorded(子页)未单独走
- Usage(Manage)、Get Help、Tickets Portal 未走

---

## 总体 IA 关键发现(Corti console)

### 1. 路由结构
```
/                                  → Project 选择(选/建 project)
/project/<id>                      → Project Home(4 tabs)
/project/<id>/ai-studio/...        → AI Studio 各子页
/project/<id>/customers            → Customers
/project/<id>/templates            → Templates Beta
/project/<id>/api-clients/...      → API Clients
/project/<id>/team                 → Team
/project/<id>/billing              → Billing
/project/<id>/settings             → Settings
/project/<id>/developer-quickstart → Developer Quickstart
```

### 2. 顶栏统一元素(所有 AI Studio 页都有)
- Breadcrumb(AI Studio > 当前页)
- 实时 cost 计数器($0.041952 这种,精度到 6 位小数)+ Reset live cost
- API Client 下拉选择(用于标识调用来自哪个 credential)
- $credits 余额 + Docs 链接
- Toggle theme(深/浅)

### 3. 工作台通用模式
```
┌─────────────────────────────────────────┐
│ Coding systems: [ICD-10-CM ×]    Config │
├─────────────────────────────────────────┤
│ Input        Samples  Clear  Copy      │
│ ┌─────────────────────────────────┐    │
│ │ textarea (Enter clinical text)  │    │
│ └─────────────────────────────────┘    │
│ Get started with:                      │
│  [Hospital medical record]             │
│  [GP transcript]                       │
│  [Orthopedic referral letter]          │
│  [Guided demo]                         │
├─────────────────────────────────────────┤
│ Output: N codes / Rendered|JSON        │
│ - Code1 (expanded)                     │
│   Evidence: "quoted text"               │
│   Alternatives: alt1 / alt2 / ...      │
│ - Code2                                │
│ ...                                    │
│ Candidates –                            │
└─────────────────────────────────────────┘
Right panel:
  Settings | Code
  - Output language
  - Template ID
  - ...
  Event Inspector (logs API events)
```

### 4. Agent 双入口 + Builder
- **My agents**(用户建) / **Pre-built agents**(Corti 官方 20 个)
- 任意 Pre-built agent 都有 **Preview / Customize** 右键菜单
- Preview = "Ask the agent..." 聊天壳
- Customize → 进入 builder(workflow builder 形式)

### 5. API-as-Product 模式
- API Clients(My / Default)管 credentials
- Developer Quickstart 提供预制 prompt 模板给 Claude/Cursor/Codex/Lovable
- Customer(对应 Embedded Assistant 的 end-user)单独管理

---

## iCoDer 重构路线(基于 Corti 走查)

### Phase A — 立即删(Corti 没有)
- ❌ DoctorPage / MethodComparePage / MethodSwitcher / Doctor API / 10 builtin methods / 4 expert stub packs / MedCodER Adapter 全套
- ❌ RunTracePage(没有对应物,Corti 用 Event Inspector)
- ❌ AgentHubPage(Corti 改名 + 改 IA)

### Phase B — Frontend 重写对齐 Corti IA
- ✅ Sidebar 段(Home / Developer quickstart / AI Studio / Manage / Support)
- ✅ AI Studio 6 个工作台:Overview / Agents / Speech to Text / Text Generation / Embedded Assistant / Fact Extraction / Medical Coding
- ✅ Manage 7 项:API Clients / Team / Billing / Usage / Customers / Templates / Settings
- ✅ Project Home 4 tabs(Transcribe / Document / Chat / Code NEW)
- ✅ 顶栏:实时 cost 计数器 + Reset + API Client 选择 + Toggle theme + Docs

### Phase C — 20 Pre-built Agents 实装
按 Corti 列表,iCoDer 必须有这 20 个 Agent(中国编码体系替换点:ICD-10-CM → ICD-10-CN 等):
1. ICD-10 Index Navigator → ICD-10-CN Index Navigator(用 icd10cn_code_catalog)
2. Rule Explainer → ICD-10-CN Rule Explainer
3. Compliance Guardrail → CN 医保合规 Guardrail(CN-DRG / DIP 规则)
4. Code Validation → ICD-10-CN Code Validation
5. Procedure Entity Extractor → ICD-9-CM-3-CN Procedure Extractor
6. Diagnostic Entity Extractor → ICD-10-CN Diagnostic Extractor
7-20. 其余 14 个 Agent(ICU Admission / Triage / Discharge / Shift Handoff / PA / Denial Appeals / CDI / Education / Referral / Surgical Registry / Note Completeness / Medication Reconciliation / Clinical Guidelines / Clinical Education)— **iCoDer 全部新建**

### Phase D — Runtime 层适配
- 保留 `icoder_runtime/` 中的 A2A / MCP / Context / SSE / Agent Card(对齐 Corti)
- 删除 icoder_runtime/ 中 iCoDer 自创的 AgentRunner + LLMGateway(用 Corti 风格的 agent executor)
- 删除 MedCodERStrategy / HybridCodingAdapter(改用 Corti 风格的 multi-agent orchestration)
- Loader / agent_pack.json 保留并对齐 Corti AgentDefinition 格式

### Phase E — 编码体系替换(在 Phase C 同步)
- ICD-10-CM → ICD-10-CN(iCoDerA `icd10cn_code_catalog.json` 37,897 码已就绪)
- ICD-10-PCS → ICD-9-CM-3-CN(手术,iCoDerA 23,165 码已就绪)
- CPT → 删除(CPT 是美国医师操作码,中国用 ICD-9-CM-3-CN 替代)
- MS-DRG → CN-DRG / DIP(分组)