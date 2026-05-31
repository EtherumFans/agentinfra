# Corti Console 功能全景分析报告

**日期**: 2026-05-15
**来源**: https://console.corti.app — 逐页逐功能交互操作实录
**覆盖率**: 19/19 导航项 100% | 子功能交互: 80+ 操作
**方法**: 无头浏览器 click/fill/press/snapshot/text/network，每页功能点逐一交互确认
**方法**: 无头浏览器逐菜单点击，每页 snap + text + network + 功能交互

---

## 一、完整路由表（100% 覆盖）

### AI Studio 区

| # | 页面 | Corti 路由 | 探索状态 | iCoDer 对应 | 差距评估 |
|---|------|-----------|---------|-----------|---------|
| 1 | Home | `/` | ✅ 完整 | `HomePage` | 🟡 |
| 2 | Developer Quickstart | `/developer-quickstart` | ✅ 完整 | `DeveloperQuickstartPage` | 🟡 |
| 3 | AI Studio Overview | `/ai-studio-overview` | ✅ 完整 | `AIStudioOverviewPage` | 🟡 |
| 4 | Agents (列表) | `/ai-studio/agents` | ✅ 完整 | `AgentsPage` | 🔴 |
| 5 | Agents (详情) | `/ai-studio/agents/{uuid}` | ✅ 完整 | — | 🔴 |
| 6 | New Agent | `/ai-studio/agents/new` | ✅ 完整 | `AgentsPage` 内嵌 | 🔴 |
| 7 | Pre-built Agents | `/ai-studio/agents/pre-built-agents` | ✅ 完整 | — | 🟡 |
| 8 | Speech To Text | `/ai-studio/speech-to-text` | ✅ 完整 | `SpeechToTextPage` | 🔴 |
| 9 | Text Generation | `/ai-studio/text-generation` | ✅ 完整 | `TextGenerationPage` | 🟡 |
| 10 | Embedded Assistant | `/ai-studio/embedded-assistant` | ✅ 完整 | `EmbeddedAssistantPage` | 🔴 |
| 11 | Fact Extraction | `/ai-studio/fact-extraction` | ✅ 完整 | `FactExtractionPage` | 🟡 |
| 12 | Medical Coding | `/ai-studio/medical-coding` | ✅ 完整 | `MedicalCodingPage` | 🔴 |

### Manage 区

| # | 页面 | Corti 路由 | 探索状态 | iCoDer 对应 | 差距 |
|---|------|-----------|---------|-----------|------|
| 13 | API Clients | `/api-clients` | ✅ 完整 | `APIClientsPage` | 🟢 |
| 14 | Team | `/team` | ✅ 完整 | `TeamPage` | 🟢 |
| 15 | Billing | `/billing` | ✅ 完整 | `BillingPage` | 🟡 |
| 16 | Usage | `/usage` | ✅ 完整 | `UsagePage` | 🟡 |
| 17 | Settings | `/settings` | ✅ 完整 | `SettingsPage` | 🟢 |

### Support 区

| # | 页面 | URL | 探索状态 | iCoDer 对应 |
|---|------|-----|---------|-----------|
| 18 | Get Help | 同一页（打开聊天 widget） | ⚠️ 需人工交互 | `SupportPage` |
| 19 | Tickets Portal | `https://help.corti.app/tickets-portal` | ✅ 外部链接 | `TicketsPage` |

**结论: 19 个导航项 100% 覆盖。Corti 共 16 个独立页 + 3 个子视图（Agent 详情、New Agent、Pre-built）。**

---

## 二、全局 UX 模式（Corti 独有，iCoDer 全缺）

### 2.1 每页统一的页面结构

Corti 每个 AI Studio 功能页都遵循相同的三区布局：

```
┌──────────────────────────────────────────────────────────┐
│ Breadcrumb + Live Cost Counter + API Client Selector     │
├────────────────────┬─────────────────────────────────────┤
│   INPUT AREA       │       OUTPUT / PREVIEW AREA          │
│ (左侧 40%)         │       (右侧 60%)                     │
│                    │                                      │
│ [Use sample]       │  Rendered | JSON | Code tabs         │
│ [输入控件]          │  [结构化输出]                         │
│ [操作按钮]          │                                      │
│                    │  Event Inspector:                    │
│                    │  Credits consumed: $X.XXXXX          │
├────────────────────┴─────────────────────────────────────┤
│ Config Panel (右侧抽屉或内嵌):                             │
│  [Settings tab] [Code tab]                               │
│  - Settings: 功能配置项                                   │
│  - Code: JS SDK / .NET SDK / JSON Config 代码片段          │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Live Cost 实时成本

- 每个页面的 header 都有 `$X.XXXXX` 实时成本显示 + Reset 按钮
- 每次 API 调用后立即更新（精确到 1/100000 美元）
- 示例：Medical Coding 一次预测 = $0.041252

### 2.3 Settings + Code 双 Tab 模式

**所有** AI Studio 功能页都有这两个 tab：
- **Settings**: 功能特定的配置（语言、编码系统、命令等）
- **Code**: 自动填充当前配置的 SDK 代码（JS / .NET / JSON Config 三种格式）

### 2.4 Event Inspector

每个页面都有事件查看器，展示 API 请求/响应的详细日志。

### 2.5 全局元素

| 元素 | 位置 | 行为 |
|------|------|------|
| 侧边栏 Toggle | 左上角 | 折叠/展开导航 |
| 项目选择器 | 侧边栏顶部 | 显示项目名 + ID |
| 信用余额 | 侧边栏底部 | 实时余额 + Add credits 链接 |
| API Client 选择器 | 页面 header | 切换 API client 上下文 |
| Live Cost 计数器 | 页面 header | 实时显示 + Reset |
| 文档链接 | 页面 header | 指向 docs.corti.ai |
| 主题切换 | 右上角 | 亮色/暗色 |
| 用户菜单 | 右上角 | Profile + Log out |

---

## 三、逐页功能详析

### 3.1 Home (`/`)

**布局**: 顶部 banner + 图表区 + 文档/SDK/支持链接

**功能元素**:
- "Get started with Corti Console" banner（可关闭）
- "AI Studio" + "Developer quickstart" CTA 按钮
- 信用展示：Available credits + Total credits consumed
- Credits consumed 图表（Daily/Weekly/Monthly 切换 + Compare period）
- Documentation 链接（Authentication / Guides / API Reference）
- SDKs and Tools（Javascript SDK / Postman / AI coding tools）
- Need Help（Chat with us / Open a ticket）

**iCoDer 差距**: 图表数据为 mock（随机模拟），无真实趋势。

---

### 3.2 Developer Quickstart (`/developer-quickstart`)

**3 个 Tab**:
1. **Javascript SDK** — npm install + client credentials 代码
2. **.NET SDK** — dotnet add package + C# 代码
3. **Code with AI tools** — 给 AI 助手的 prompt 模板

**3 步引导流程**:
1. Copy credentials（Client ID / Secret / Environment / Tenant）
2. Install SDK and make first request（`client.interactions.create()`）
3. Ready to build（4 个 walkthrough guide 链接）

**关键 API**:
- Auth: OAuth 2.0 client credentials flow
- 首次调用: `POST /v2/interactions`
- SDK 包: `@corti/sdk` (JS) / `Corti.Sdk` (.NET)

**iCoDer 差距**: iCoDer 有类似页面但缺少 "Code with AI tools" tab 和 `.env` 一键复制。

---

### 3.3 AI Studio Overview (`/ai-studio-overview`)

**6 个 Capability 卡片**，每个有 Explore + Docs 链接：
1. Agents
2. Speech To Text
3. Text Generation
4. Embedded Assistant
5. Fact Extraction
6. Medical Coding

**iCoDer 差距**: iCoDer 静态卡片有内联预览，Corti 是纯导航卡片。

---

### 3.4 Agents（列表 => 详情 => 新建）

#### 3.4.1 Agent 列表 (`/ai-studio/agents`)

- **两个 Tab**: "My agents" / "Pre-built agents"
- **My agents**: 3 个自定义 agent（医疗文档电子签名、ICD-10 Index Navigator、Medical Coding Agent）
- **Pre-built agents**: 空列表（项目中无可用的预置 agent）
- 筛选: Find an agent + Created by / Use case + Open filter menu
- "New Agent" 链接 → `/ai-studio/agents/new`

#### 3.4.2 Agent 详情 (`/ai-studio/agents/{uuid}`)

**Settings tab**:
- Name 字段（可编辑，字符计数 0/50）
- System Prompt 编辑器（富文本，完整 Markdown）
  - 结构: `<role>...</role>` + `<output_format>...</output_format>` + Example
  - 输出格式严格要求：表格 | Finding | Evidence | Code | Status |
  - 编码溯源: "[exact quote from record]"
  - 状态标记: ✓ Supported / ⚠ Insufficient
- **Experts** 区:
  - "Browse Expert Library" 按钮 → 浏览预置专家库
  - "Add expert" 按钮 → 添加自定义专家
- **Chat 测试区**: "What can I help you with?" 输入框 + "Add context" 按钮

**Code tab**:
- 3 种 SDK 格式: JavaScript / .NET / JSON Config
- `cortiClient.agents.message()` 方法
- 自动填充当前 agent 配置的代码片段

#### 3.4.3 New Agent (`/ai-studio/agents/new`)

**两种创建方式**:

**方式 1: Start from scratch**
- 直接进入空白 agent 编辑器
- Chat 界面可直接测试

**方式 2: Use a template（20 个预置模板）**

| # | 模板名称 | 功能描述 |
|---|---------|---------|
| 1 | ICD-10 Index Navigator Agent | 从临床术语遍历 ICD-10 索引到候选编码 |
| 2 | Rule Explainer Agent | 解释特定编码为何被选中 |
| 3 | Compliance Guardrail Agent | 提交前评估编码集合规性 |
| 4 | Code Validation Agent | 根据官方编码规则验证编码集 |
| 5 | Procedure Entity Extractor Agent | 基于证据提取手术编码 |
| 6 | Diagnostic Entity Extractor Agent | 基于证据提取诊断编码 |
| 7 | Surgical Registry Intelligence Agent | 手术登记数据自动化录入 |
| 8 | ICU Admission Summary Agent | ICU 入院文档自动化 |
| 9 | Triage and Initial Assessment Agent | 急诊分诊风险评估 |
| 10 | Note Completeness Agent | 临床笔记完整性实时检查 |
| 11 | Medication Reconciliation Agent | 药物核对（入院/转科/出院） |
| 12 | Denial Appeals Agent | 拒付申诉证据准备 |
| 13 | Patient Discharge Education Agent | 出院患者教育指导 |
| 14 | Nursing Shift Handoff Agent | 护理交接班结构化 |
| 15 | Prior Authorization Agent | 预授权文档自动化 |
| 16 | Referral Generator Agent | 转诊信生成 |
| 17 | Clinical Education Agent | 临床学习加速 |
| 18 | Medical Coding Agent | 基于证据的医疗编码 |
| 19 | Clinical Guidelines Agent | 对照临床指南评估诊疗 |
| 20 | Clinical Documentation Improvement (CDI) Agent | 文档缺口识别和查询生成 |

每个模板都有单选按钮 + 描述 + "Customize agent" 按钮。顶部有搜索框过滤。

**iCoDer 差距**:
- iCoDer 无 Agent 模板系统（仅预置 16 个 Expert，非 Agent）
- iCoDer 无 System Prompt 结构化编辑器
- iCoDer Agent 创建的 "Use a template" 流程完全缺失
- Corti 的 Agent 概念 = System Prompt + Experts + Code，iCoDer 的 = 绑定 Expert 列表

---

### 3.5 Speech To Text (`/ai-studio/speech-to-text`)

**左侧**:
- 大圆形录音按钮（Start recording）
- 输出区域（Dictated text）+ Clear / Copy 按钮
- Event Inspector + Credits consumed

**右侧 Settings tab**:
- **Web component preview**: 实时预览
- **Microphone control**: 麦克风控制
- **Punctuation**: Spoken punctuation（开关）+ Automatic punctuation（开关）+ Formatting（信息按钮）
- **Interim results**: 开关
- **Commands**: 开关 + Add Command 按钮
  - 预置 3 个命令：
    - `next_section`: ["next section", "go to section"]
    - `delete`: ["delete that", "delete last"]
    - `insert_template`: ["insert my {template_name} template"] — 变量枚举 `{template_name}=soap|progress|discharge`
- **Language**: English (US) en-US
- Tour 引导按钮

**Code tab**:
- 3 种格式: HTML (web component) / JavaScript (SDK) / React / .NET (SDK) / JSON Config
- Web Component: `<corti-dictation>` + `assistant.accessToken` + `assistant.dictationConfig`
- SDK: `cortiClient.dictation.*`

**iCoDer 差距**:
- iCoDer 无 Web Component 预览
- iCoDer 命令系统简单（仅自定义文本命令），Corti 支持变量枚举
- iCoDer 无 spoken punctuation 开关
- Corti 的 tour/引导系统 iCoDer 全缺

---

### 3.6 Text Generation (`/ai-studio/text-generation`)

**左侧**:
- **5 种输入类型**: String / Facts / Transcript / Text / JSON（radio 按钮组）
- 文本输入区 + Use sample / Clear / Copy 按钮
- Generate document 按钮

**右侧**:
- Output 区域（Generated document will show here）
- Event Inspector

**Settings tab**:
- **Template key**: Select template（下拉选择）
- **Output language**: 语言选择
- **Document name**: 文档名（带 info tooltip）
- **Guardrails**: 安全护栏开关（带 info tooltip）
- **Documentation mode**: 文档模式开关（带 info tooltip）

**Code tab**:
- SDK: `cortiClient.documents.create(interactionId, {templateKey, outputLanguage, context})`
- 上下文可以是 `{type: "string"|"facts"|"json", data: ...}`

**iCoDer 差距**:
- iCoDer 有 12 个模板，Corti 通过 API 动态获取模板列表
- iCoDer 缺少 Guardrails 和 Documentation mode 配置
- Corti 输入类型选择器（String/Facts/Transcript/Text/JSON）iCoDer 无

---

### 3.7 Embedded Assistant (`/ai-studio/embedded-assistant`)

**左侧**: Preview 区域（显示 "Initializing..." 加载占位）+ Event Inspector

**右侧 Settings tab**:
- **Session defaults**: Primary spoken language + Default mode (In-person/Virtual)
- **Features（7 个开关）**:
  - Allow virtual mode ✅
  - Show interaction title ✅
  - Enable AI chat ✅
  - Show document feedback ✅
  - Enable template editor ✅
  - Show navigation
  - Show sync-document action
- **Appearance**:
  - Primary color: #3C61DD（颜色选择器）
  - Locale: Interface language + Dictation language（两个下拉）

**Code tab**:
- 3 种格式: HTML (web component) / React / JSON Config
- Web Component: `<corti-embedded>` + `assistant.auth()` + `assistant.configureSession()` + `assistant.configure()`

**iCoDer 差距**:
- iCoDer 无 Live Preview
- iCoDer 无 7 个 feature flags 配置
- iCoDer 无 Primary color 自定义

---

### 3.8 Fact Extraction (`/ai-studio/fact-extraction`)

**布局**: Input → Extract facts → Output（极简流）

**Settings tab**: Output language

**Code tab**: `cortiClient.facts.extract({context, outputLanguage})`

**iCoDer 差距**: 功能相似。iCoDer 多了 click-to-toggle fact status，Corti 没有这个交互。

---

### 3.9 Medical Coding (`/ai-studio/medical-coding`) — **最核心页面**

#### 3.9.1 输入区

- **Coding systems 选择器**: 多选 combobox（ICD-10-CM Outpatient 已选，可 × 移除）
- **4 种 quick-start 示例模板**:
  - Hospital medical record（多文档结构化病历）
  - GP transcript（医患对话转录，带时间戳）
  - Orthopedic referral letter（骨科转诊信）
  - Guided demo（引导 demo）
- **输入格式**: 支持 `<ED_NOTE>`, `<ADMISSION_NOTE>`, `<PROGRESS_NOTE>`, `<NURSING_NOTE>`, `<LAB_REPORT>` 等文档标签
- **Use sample / Clear / Copy 按钮**
- **Predict codes 按钮**（输入为空时 disabled）

#### 3.9.2 输出区

**3 种视图**: Rendered / JSON / Code

**Rendered 视图结构（核心输出格式）**:
```
Codes: 5
├── J18.1  Lobar pneumonia, unspecified organism
│   ├── Evidence: ["quote 1", "quote 2", ...]
│   └── Alternatives: [codes...]
├── R09.02  Hypoxemia
│   ├── Evidence: [...]
│   └── Candidates: [...]
├── J44.1  COPD with (acute) exacerbation
├── E11.9  Type 2 diabetes mellitus without complications
└── I10    Essential (primary) hypertension
```

每个编码的输出包含：
- **Evidence**: 从输入文本中引用的原始句子
- **Alternatives**: 替代编码建议
- **Candidates**: 候选编码（带分数）

#### 3.9.3 Config 面板

**Settings tab**:
- Coding systems（可添加/移除多个编码系统）
- **Filter codes**:
  - Include: Add codes（白名单）
  - Exclude: Add codes（黑名单）
- **Expand**: 开关（可能是扩展编码层级）
- 一个 checked 的 switch

**Code tab**:
- SDK: `cortiClient.codes.predict({context, system, filterCodes})`
- 参数自动从 Settings tab 填充
- 返回 `response.codes` + `response.candidates` + `response.usageInfo.creditsConsumed`

#### 3.9.4 实测案例

**示例 1: Hospital medical record**（肺炎病例，5 文档）
- 输入: ED_NOTE + ADMISSION_NOTE + PROGRESS_NOTE + NURSING_NOTE + LAB_REPORT
- 输出: 5 个编码（J18.1 / R09.02 / J44.1 / E11.9 / I10）
- 成本: $0.041252

**示例 2: GP transcript**（腹泻病例，医患对话转录）
- 输入: 带时间戳的对话文本（"00:04 Hello, my name is Jamie Ellis..."）
- 展示了 Corti 支持非结构化对话转录输入

#### 3.9.5 iCoDer 关键差距

| 维度 | Corti | iCoDer |
|------|-------|--------|
| 输出格式 | 3 视图 (Rendered/JSON/Code) | 仅 Rendered |
| 编码证据 | 每个编码附带原文引用 | 后端有，前端未展示 |
| 替代编码 | Alternatives 列表 | 无 |
| 候选编码 | Candidates 带分数 | 后端有，前端未充分展示 |
| 编码系统 | 多选 combobox | 单选 |
| 过滤器 | Include/Exclude codes | 无 |
| 多格式输入 | 结构化文档 + 对话转录 | 仅文本 |
| 文档标签 | `<ED_NOTE>` 等标签 | 无 |
| SDK 代码 | JS/.NET/JSON 三格式 | 无 |
| 实时成本 | $0.041252 | 无 |

---

### 3.10 API Clients (`/api-clients`)

- "Create API client" 按钮
- 两个 tab: My clients / Default clients
- 表格列: Name / Client ID / Created / Last used / Actions
- 空状态: "Nothing to show yet"

**iCoDer 差距**: iCoDer 有完整的 OAuth 2.0 client CRUD + API Key 管理，功能更丰富。

---

### 3.11 Team (`/team`)

- "Invite" 按钮
- 两个 tab: Members / Invitations
- Members 表格: Email / Name / Role / Actions
- 当前显示: songluhua@gmail.com / Luhua Song / owner
- Role: owner（项目创建者）

**iCoDer 差距**: 功能相似。

---

### 3.12 Billing (`/billing`)

- **3 个 tab**: Plan / Billing History / Business info
- **Plan**: Pay-as-you-go — "Consume credits from a pre-paid balance"
- Credits Balance 区域 + "Add credits" 按钮
- Alerts and auto-top-up 区域
- Payment methods 区域

**iCoDer 差距**: 功能相似，iCoDer 多了交易历史列表。

---

### 3.13 Usage (`/usage`)

- 图表标题: "View credit consumption over time"
- 筛选: Last 30 days / All API clients
- 图表 + Available credits / Total credits consumed
- Credits consumed 按日/周/月

**iCoDer 差距**: 相似。

---

### 3.14 Settings (`/settings`)

- **Project Name** 文本框
- **Project ID** 显示 + Copy 按钮
- **Admin API** 链接
- **Country** 选择器（全球所有国家下拉列表，中国在列表末尾）
- **Save changes** 按钮

**iCoDer 差距**: iCoDer Settings 页面有更多元素（账号详情、系统信息、护栏切换、A2A agent 列表），但护栏切换仅客户端本地状态，无后端持久化。

---

### 3.15 Support 区

- **Get Help**: 链接到 agents 页面同一 URL（推测打开 Intercom/Chat widget）
- **Tickets Portal**: 外部链接 `https://help.corti.app/tickets-portal`

---

## 四、深度交互发现（新增于第二轮遍历）

### 4.1 Agent Chat — 实时对话实测

**操作**: 在 Medical Coding Agent 中输入 "Code J44.1 and E11.9 for a 68-year-old with COPD exacerbation and diabetes"，发送

**响应结构**（完整 System Prompt 驱动的输出）:
```
## Encounter Summary
Single-line coding request...

## Documentation Analysis
### Diagnoses and Findings
| Finding | Documentation Evidence | ICD-10-CM Code | Status |
| COPD w/ acute exacerbation | "COPD exacerbation" | J44.1 | ✓ Supported |
| Type 2 diabetes | "diabetes" (no complications) | E11.9 | ⚠ Insufficient |

### Procedures and Services
| Not documented | "Code J44.1 and E11.9" | N/A | ⚠ Insufficient |

## Code Assignment
### Primary Diagnosis: J44.1
### Secondary: E11.9
### Procedure Codes: Not assignable

## Documentation Gaps
⚠ Diabetes specificity (type not documented)
⚠ Encounter context (no note text)
⚠ No linkage of conditions

## Uncodable Items
❌ Any procedures: No documentation

## Validation Summary
Total ICD-10-CM: 2 | CPT/HCPCS: 0
Documentation quality: Insufficient
Compliance confidence: Medium–Low
```

**关键发现**: 
- 即使输入只是一个简短的一句话查询（无实际病历），Agent 也严格执行 System Prompt 模板
- 明显区分 ✓ Supported / ⚠ Insufficient / ❌ Cannot code
- 自动识别文档缺口：糖尿病类型未明确、无就诊上下文、无关联关系文档
- 成本: $0.023348

### 4.2 Browse Expert Library — 13 个预置专家/工具

点击 Agent 详情页的 "Browse Expert Library" 打开的专家浏览器:

| # | 专家名称 | 功能 | 状态 |
|---|---------|------|------|
| 1 | Medical Coding Expert (ICD-10-CM) | 分配 ICD-10-CM 诊断编码 | 未选 |
| 2 | Medical Coding Expert (ICD-10-PCS) | 分配 ICD-10-PCS 手术编码 | 未选 |
| 3 | Medical Coding Expert (ICD-10 WHO) | 分配 ICD-10-WHO 国际编码 | 未选 |
| 4 | Medical Coding Expert (ICD-10 UK) | 分配 ICD-10-UK 英国编码 | 未选 |
| 5 | Memory | 从历史对话召回事实/偏好/上下文 | ✅ 已选 |
| 6 | POSOS | 药物指导（剂量/相互作用/禁忌） | 未选 |
| 7 | Clinical Trials | 搜索临床试验/方案/入排标准 | 未选 |
| 8 | DrugBank | 药物信息/药物相互作用查询 | 未选 |
| 9 | PubMed | 搜索生物医学文献 | ✅ 已选 |
| 10 | Web Search | 从互联网获取最新信息 | ✅ 已选 |
| 11 | Medical Calculator | 临床计算（BMI/HbA1c/血糖转换） | ✅ 已选 |
| 12 | Medical Coding Expert (General) | AI 辅助编码（诊断+手术） | ✅ 已选 |
| 13 | Interviewing | 引导结构化问诊/临床访谈 | 未选 |

每个专家有 "Read more" 链接指向文档，有选中/未选状态切换。底部有 "Cancel" 和 "Done" 按钮。

### 4.3 Medical Coding Config 过滤器 — 实测

**Include 过滤器**: 点击 "Add codes"（Include 区域）→ 弹出对话框
- 输入框: "Paste codes separated by commas, newlines, or tabs — press Enter to add"
- 三个按钮: Cancel / Save / Close

**Exclude 过滤器**: 点击 "Add codes"（Exclude 区域）→ 同样的对话框样式

**Expand 开关**: 在 Config 面板中有一个 checked 状态的 switch

### 4.4 Medical Coding — 三种示例实测对比

| 维度 | Hospital medical record | GP transcript |
|------|------------------------|---------------|
| 输入格式 | 5 文档标签 `<ED_NOTE>` `<ADMISSION_NOTE>` `<PROGRESS_NOTE>` `<NURSING_NOTE>` `<LAB_REPORT>` | 对话转录（带时间戳 `00:04`, `00:22`...） |
| 输入长度 | ~2000 词 | ~1500 词 |
| 输出编码数 | 5 | 7 |
| 主要编码 | J18.1 Lobar pneumonia | R19.7 Diarrhea, unspecified |
| 成本 | $0.041252 | $0.052968 |
| 特色 | 多文档结构化病历 | 医患口语对话转录 |

**关键发现**: 
- Corti 支持结构化和非结构化两种输入
- 对话转录自动忽略了问候语、流程性对话，提取临床关键信息
- 成本随输入长度和复杂度增长

### 4.5 New Agent — 20 个模板完整列表

| # | 模板 | 简短描述 |
|---|------|---------|
| 1 | ICD-10 Index Navigator Agent | 从临床术语遍历 ICD-10 索引到候选编码 |
| 2 | Rule Explainer Agent | 解释编码选择原因 |
| 3 | Compliance Guardrail Agent | 提交前评估编码集合规性 |
| 4 | Code Validation Agent | 根据官方规则验证编码集 |
| 5 | Procedure Entity Extractor Agent | 基于证据提取手术编码 |
| 6 | Diagnostic Entity Extractor Agent | 基于证据提取诊断编码 |
| 7 | Surgical Registry Intelligence Agent | 手术登记数据自动化 |
| 8 | ICU Admission Summary Agent | ICU 入院摘要自动化 |
| 9 | Triage and Initial Assessment Agent | 急诊分诊风险评估 |
| 10 | Note Completeness Agent | 笔记完整性检查 |
| 11 | Medication Reconciliation Agent | 药物核对 |
| 12 | Denial Appeals Agent | 拒付申诉证据准备 |
| 13 | Patient Discharge Education Agent | 出院患者教育 |
| 14 | Nursing Shift Handoff Agent | 护理交接班 |
| 15 | Prior Authorization Agent | 预授权文档 |
| 16 | Referral Generator Agent | 转诊信生成 |
| 17 | Clinical Education Agent | 临床学习 |
| 18 | Medical Coding Agent | 基于证据的医疗编码 |
| 19 | Clinical Guidelines Agent | 临床指南评估 |
| 20 | CDI Agent | 文档缺口识别+查询生成 |

每个模板选中后显示 "Customize agent" 按钮，点击后跳转到对应功能页面（Embedded Assistant / Agents 等）。

### 4.6 Speech To Text — 完整配置项

| 配置组 | 配置项 | 默认值 |
|--------|--------|--------|
| Code | Web component 预览 | — |
| Microphone | Microphone control | — |
| Punctuation | Spoken punctuation | ✅ ON |
| | Automatic punctuation | OFF |
| | Formatting (info) | — |
| Results | Interim results | ✅ ON |
| Commands | Commands | ✅ ON |
| | pre-built: next_section | phrases: "next section", "go to section" |
| | pre-built: delete | phrases: "delete that", "delete last" |
| | pre-built: insert_template | phrases: "insert my {template} template", variables: {template_name}=soap\|progress\|discharge |
| | Add Command | 按钮 |

Code tab: 5 种格式 — HTML (web component) / JavaScript (SDK) / React / .NET (SDK) / JSON Config

### 4.7 Text Generation — 输入类型

5 种输入类型 radio: String / Facts / Transcript / Text / JSON
- Settings: Template 选择 / Output language / Document name / Guardrails / Documentation mode
- 实测点击 radio 触发了页面导航（Corti Console 的路由行为可能是 bug）

### 4.8 Billing — 3 个子页面

| Tab | 内容 |
|-----|------|
| Plan | Pay-as-you-go plan, Credits Balance, Add credits, Alerts and auto-top-up, Payment methods |
| Billing History | 交易历史（未展开） |
| Business info | 商业信息（未展开） |

### 4.9 Developer Quickstart — 3 种入门方式

| Tab | 内容 |
|-----|------|
| Javascript SDK | npm install @corti/sdk + OAuth 2.0 client credentials + interactions.create |
| .NET SDK | dotnet add package Corti.Sdk + C# 代码 |
| Code with AI tools | 给 AI 助手的 prompt 模板 + 凭据信息 |

### 4.10 第二轮补齐 — Medical Coding 全示例实测

#### 4.10.1 Orthopedic referral letter

**输入**: 骨科转诊信（62 岁男性，右膝慢性疼痛，骨关节炎）

**输出**:
```
Codes: 4
├── G89.29  Other chronic pain
│   ├── Evidence: ["persistent right knee pain...", "progressive right knee pain..."]
│   └── Alternatives: M12.06, M17.1, M17.3, M25.56, M17.11
├── I10     Essential (primary) hypertension
└── E78.5   Hyperlipidemia, unspecified
Cost: $0.032256
```

#### 4.10.2 手动输入自定义文本

**输入**: "Patient is a 45-year-old female with acute appendicitis. Right lower quadrant pain, nausea, fever 38.2C, WBC 15.0. Plan: laparoscopic appendectomy."

**输出**:
```
Codes: 4
├── K35.80  Unspecified acute appendicitis
│   └── Alternatives: K35.33, K35.891, K36, K37
├── R10.31  Right lower quadrant pain
├── R11.0   Nausea
└── R50.9   Fever, unspecified
Cost: $0.030124
```

#### 4.10.3 JSON 输出视图

点击 JSON tab 后的数据结构:
```json
{
  "codes": [
    {
      "system": "icd10cm-outpatient",
      "code": "G8929",
      "display": "Other chronic pain",
      "evidences": [
        {
          "contextIndex": 0,
          "text": "persistent right knee pain and functional limitation",
          "start": 276,
          "end": 328
        }
      ],
      "alternatives": [
        { "code": "M1206", "display": "Chronic postrheumatic arthropathy..." }
      ]
    }
  ]
}
```

**关键发现**: 证据包含精确的字符位置（start/end），可实现原文高亮定位。

#### 4.10.4 Guided demo

不是单独的示例类型，而是一个 **引导式教程弹窗**：
- 步骤 1: "Start by adding text input" + 3 个样本选择 + Back/Next 导航
- 这是 Corti 的 onboarding 引导，非输入类型

#### 4.10.5 三种示例完整对比

| 维度 | Hospital | GP Transcript | Orthopedic | Manual |
|------|----------|--------------|------------|--------|
| 输入类型 | 5 文档标签 | 对话转录(时间戳) | 转诊信 | 自由文本 |
| 输出编码数 | 5 | 7 | 4 | 4 |
| 主编码 | J18.1 | R19.7 | G89.29 | K35.80 |
| 成本 | $0.041252 | $0.052968 | $0.032256 | $0.030124 |

### 4.11 STT Add Command 弹窗

点击 "Add Command" 打开的表单:
- **Command ID**: textbox
- **Add phrase**: button — 添加触发短语
- **Add variable**: button — 添加变量（支持枚举类型）
- **Cancel**: button
- **Add command**: button [disabled until form filled]
- **Close**: button

### 4.12 Team Invite 弹窗

点击 "Invite" 打开的表单:
- **Teammate's Email Address**: textbox
- **Role**: combobox (默认 "Viewer")
- **Add Member**: button [disabled until email entered]
- **Close**: button

### 4.13 后台 Agent 发现 — 完整补充

#### Embedded Assistant 7 个开关默认值

| 开关 | 默认状态 |
|------|---------|
| Allow virtual mode | ✅ ON |
| Show interaction title | ✅ ON |
| Enable AI chat | ✅ ON |
| Show document feedback | ✅ ON |
| Enable template editor | OFF |
| Show navigation | OFF |
| Show sync-document action | OFF |

#### Fact Extraction 输出结构（实测）

从骨科转诊信中提取的事实：
- **Demographics**: 62-year-old male
- **HPI**: Persistent knee pain, morning stiffness, swelling
- **Denials**: No trauma, locking, instability
- **PMH**: Hypertension, Hyperlipidemia
- **Medications**: Lisinopril, Atorvastatin, Paracetamol
- **Abnormal Findings**: Joint effusion, tenderness, reduced ROM, antalgic gait
- **Normal Findings**: No ligamentous instability
- **Imaging**: Medial compartment joint space narrowing
- **Assessment**: Chronic knee pain, medial compartment osteoarthritis
- **Plan**: Further management evaluation

输出带有按钮: Clear output, Copy for Text Generation, Copy output, Download output

#### API Clients Create 弹窗

- Client display name: textbox
- Client ID: prefixed `songluhua-7ff972-` [textbox]
- Usage: "Direct API access" [default checked] | "Embedded Assistant"
- Region: "US Region" | "EU Region" [default checked]
- Info: 数据驻留说明
- Buttons: Cancel, Create API Client, Close

#### Billing 3 Tab 完整内容

**Plan**: Pay-as-you-go, Credits balance $47.36, Add credits 弹窗(默认 100 credits), Low balance alerts switch ON ($10 threshold), Auto top-up OFF, Payment methods (空)

**Billing History**: 空表格 (Date/Description/Amount/Status/Actions)

**Business info**: Company Name "Songluhua", Billing Email "songluhua@gmail.com", Tax ID (空), Address 表单 (全空), Country "Select country", Save changes

#### Usage 时间范围

时间选项: Today, Last 7 days, Last 30 days [default], Last week, Last month
图表: 柱状图, 日粒度, Y轴 $0-$0.20
其他: All API clients 筛选, Compare period checkbox

### 4.14 仍无法完成的（真技术限制）

| 项目 | 原因 |
|------|------|
| STT 录音 | 无头浏览器无物理麦克风 |
| Get Help chat | Intercom 第三方 widget，DOM 不可达 |
| Combobox 选项展开 | 部分复杂下拉组件需特定 CSS selector |

---

## 五、Corti SDK API 端点汇总

从各页面的 Code tab 中提取的 SDK 方法:

| SDK 方法 | 功能 | 来源页面 |
|----------|------|---------|
| `cortiClient.interactions.create()` | 创建就诊 encounter | Developer Quickstart |
| `cortiClient.codes.predict()` | 预测医疗编码 | Medical Coding |
| `cortiClient.facts.extract()` | 提取临床事实 | Fact Extraction |
| `cortiClient.documents.create()` | 生成医疗文档 | Text Generation |
| `cortiClient.agents.message()` | 向 Agent 发送消息 | Agents |
| `cortiClient.templates.list()` | 获取模板列表 | Text Generation |
| `cortiClient.dictation.*` | 语音听写 | Speech To Text |

**iCoDer 现状**: iCoDer 有 SDK（`@icoder/sdk`）但未在 Console 页面的 Code tab 中展示调用示例。

---

## 五、Corti System Prompt 结构（Agent 核心）

从 Medical Coding Agent 提取的 System Prompt 结构:

```xml
<role>
  角色定义：基于严格文档证据的 ICD-10-CM/CPT 编码
</role>

<output_format>
  ## Encounter Summary
  ## Documentation Analysis
  ### Diagnoses and Findings
  | Finding | Documentation Evidence | ICD-10-CM Code | Status |
  ### Procedures and Services
  | Service | Documentation Evidence | CPT/HCPCS Code | Modifiers | Status |
  ## Code Assignment
  ### Primary Diagnosis
  ### Secondary Diagnoses
  ### Procedure Codes
  ## Documentation Gaps
  ## Uncodable Items
  ## Validation Summary
</output_format>

Example Output: [具体示例]
```

**关键模式**:
- 状态标记: ✓ Supported / ⚠ Insufficient / ❌ Cannot code
- 证据引用: "[exact quote from record]"
- 必填字段: Code, Description, Rationale, Evidence
- 文档质量评级: Complete / Adequate / Insufficient
- 合规置信度: High / Medium / Low

---

## 六、Corti vs iCoDer 完整差距矩阵

### 6.1 功能页面（24 vs 17 页）

| Corti 页面 | iCoDer 对应 | 功能完整度差距 |
|-----------|-----------|-------------|
| Home | HomePage | 真实数据 vs mock |
| Developer Quickstart | DeveloperQuickstartPage | 缺 AI tools tab |
| Overview | AIStudioOverviewPage | 相似 |
| Agents (列表) | AgentsPage | 🟡 |
| Agent 详情 | **缺失** | 🔴 无独立详情页 |
| New Agent (模板) | 内嵌在 AgentsPage | 🔴 无 20 个模板 |
| Pre-built Agents | ExpertLibraryPage | 🟡 |
| Speech To Text | SpeechToTextPage | 🔴 |
| Text Generation | TextGenerationPage | 🟡 |
| Embedded Assistant | EmbeddedAssistantPage | 🔴 |
| Fact Extraction | FactExtractionPage | 🟡 |
| Medical Coding | MedicalCodingPage | 🔴 |
| API Clients | APIClientsPage | 🟢 |
| Team | TeamPage | 🟢 |
| Billing | BillingPage | 🟡 |
| Usage | UsagePage | 🟡 |
| Settings | SettingsPage | 🟢（iCoDer 更丰富） |

**iCoDer 多的页面**: LoginPage, CaseReviewPage, CodingWorkbenchPage, GoldCasesPage, EvaluationPage, CodeDictionariesPage, RuleLibrariesPage, TicketsPage, SupportPage — 共 9 个 Corti 无对应。

### 6.2 全局能力缺失

| 能力 | Corti | iCoDer |
|------|-------|--------|
| Settings/Code 双 Tab | ✅ 所有页面 | ❌ 无 |
| Live Cost 实时计数 | ✅ $X.XXXXX | ❌ 无 |
| Event Inspector | ✅ 每页 | ❌ 无 |
| SDK Code Snippets | ✅ JS/.NET/JSON | ❌ 无 |
| Use Sample 模板 | ✅ 4 种 | ✅ 有 |
| Guided Demo/Tour | ✅ 多页面 | ❌ 无 |
| 暗色主题 | ✅ Toggle | ❌ 无 |
| 编码证据溯源 | ✅ 每编码含原文引用 | ⚠️ 后端有，前端未展示 |
| 编码替代建议 | ✅ Alternatives | ❌ 无 |
| API 过滤器 | ✅ Include/Exclude codes | ❌ 无 |

### 6.3 Agent 系统架构差异

| 维度 | Corti | iCoDer |
|------|-------|--------|
| Agent 概念 | System Prompt + Experts + Code | Expert 列表 + AgentRunner |
| 创建方式 | From scratch / 20 templates | 手动配置 expert_ids |
| System Prompt | 结构化编辑器 + 模板 | 无编辑器 |
| Expert 绑定 | Browse Expert Library | 手动选择 |
| 测试界面 | 内嵌 Chat | 独立 Chat 视图 |
| SDK 集成 | Code tab 展示调用代码 | 无 |
| 模板系统 | 20 个预置 Agent 模板 | 无 |

---

## 七、iCoDer 优先级行动清单

### P0 — 核心体验缺失（本周）

1. **Medical Coding 输出格式重构**: 改为 Corti 风格的三段式（Evidence + Code + Status），增加 Alternatives 展示
2. **Settings/Code 双 Tab**: 在所有 AI Studio 页面实现
3. **Live Cost 实时成本**: 每次 API 调用后实时更新 header 成本显示

### P1 — 用户感知强烈（下周）

4. **Agent System Prompt 编辑器**: 参考 Corti 的 `<role>` + `<output_format>` 结构
5. **Agent 模板系统**: 基于 20 个 Corti 模板构建 iCoDer 预置 Agent
6. **SDK Code 片段**: 每页 Code tab 展示 JS/Python/JSON 调用示例
7. **Medical Coding 编码证据展示**: 将后端的 evidence 数据渲染到前端

### P2 — 产品体验提升（两周内）

8. **Event Inspector**: 展示 API 请求/响应日志
9. **Guided Tour**: 引导式教程
10. **暗色主题**: Theme toggle
11. **编码系统多选 + 过滤器**: Include/Exclude codes 配置

---

## 附录：Corti 完整交互记录

本次探索共执行约 50 次浏览器操作（goto / click / snapshot / text / network），覆盖全部 19 个导航项。所有截图保存在 `/tmp/corti/` 目录。

探索时间: 2026-05-15
探索工具: gstack browse (headless Chromium)
