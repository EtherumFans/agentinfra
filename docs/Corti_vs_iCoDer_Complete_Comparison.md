# Corti vs iCoDer 完整功能对比与操作流程

**日期**: 2026-05-16 (更新)
**基线**: Corti Console (实测) vs iCoDer V0.5-dev (代码审查 + 截图分析)
**方法**: 每个 Corti 功能逐一点击、截图、GPT-4o 分析、与 iCoDer 逐项对比
**更新**: 2026-05-16 重新审计所有 40 项差距 — 31 已解决, 7 部分解决, 2 未解决

---

## 一、逐页逐功能对比

### 1.1 Medical Coding（最核心页面）

#### Corti 完整操作流程

```
Step 1: 进入页面
  → /ai-studio/medical-coding
  → 左侧 Input 区域为空，Predict codes 按钮 disabled

Step 2: 加载示例或输入文本
  → 方式A: 点击 "Use sample" → 弹出菜单选择:
    - Orthopedic referral letter
    - Hospital medical record
    - GP transcript
  → 方式B: 点击快速入口按钮:
    - "Hospital medical record"
    - "GP transcript"
    - "Orthopedic referral letter"
    - "Guided demo" (教程向导)
  → 方式C: 直接在 textbox 中输入文本
  → 输入后的文本以结构化格式显示(如 <ED_NOTE>, <ADMISSION_NOTE> 标签)

Step 3: 配置编码系统(可选)
  → 右侧 Config 面板 → Settings tab:
    - Coding systems: combobox 支持多选 (9种)
      ☑ ICD-10-CM Outpatient (默认)
      ☐ ICD-10-CM Inpatient
      ☐ ICD-10-PCS
      ☐ CPT
      ☐ ICD-10 Intl. Inpatient / Outpatient
      ☐ ICD-10-UK Inpatient / Outpatient
      ☐ CIM-10-FR Inpatient
    - Filter codes:
      - Include: "Add codes" → 弹窗: 粘贴代码(逗号/换行/tab分隔)
      - Exclude: "Add codes" → 同上
    - Expand: switch (默认 on)

Step 4: 执行预测
  → 点击 "Predict codes" → 等待数秒
  → 实时成本显示: $0.041252 (示例)

Step 5: 查看输出
  → 3 种视图 tab:
    - Rendered: 表格化显示
      - Codes: N (编号列表)
      - 每个 code 附带:
        ├── Evidence: ["原文引用1", "原文引用2", ...]
        ├── Alternatives: [{code, display}, ...]
        └── Candidates: [{code, score, ...}]
    - JSON: 完整 API response
      ```json
      { "codes": [{
          "system": "icd10cm-outpatient",
          "code": "J18.1",
          "display": "Lobar pneumonia...",
          "evidences": [{
            "contextIndex": 0,
            "text": "ED Assessment: Suspected community-acquired pneumonia...",
            "start": 276,
            "end": 328
          }],
          "alternatives": [{"code": "J15.0", "display": "Pneumonia due to..."}]
        }]
      }
      ```
    - Code: SDK 代码片段 (JS/.NET/JSON)

Step 6: 查看 Code tab
  → 右侧 Config → Code tab:
    - JavaScript (SDK) [selected]
    - .NET (SDK)
    - JSON Config
  → 代码自动填充当前 UI 状态(编码系统、输入文本、过滤器)
  → SDK 方法: cortiClient.codes.predict({context, system, filterCodes})
```

#### 对比表

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| 输入方式 | Use sample 下拉菜单 + 4 个快捷入口 + 手动输入 | Use sample + 手动输入 | 🟡 |
| 示例类型 | 3 种(转诊信/病历/对话转录) + 教程 | 3 种(类似) | 🟢 |
| 文档标签支持 | `<ED_NOTE>`, `<ADMISSION_NOTE>`, `<PROGRESS_NOTE>` 等 | 无标签 | 🔴 |
| 编码系统选择 | 多选 combobox，9 种(跨 4 地区) | 复选 5 种(ICD-10-CN/ICD-9-CM-3/ICD-10-CM Outpatient/Inpatient/ICD-10-PCS) | 🟡 **↑P1→partial** |
| 过滤器 | Include + Exclude codes 弹窗 | ✅ Include + Exclude codes 弹窗 | 🟢 **已修复** |
| Expand 开关 | ✅ switch | ✅ switch | 🟢 **已修复** |
| 输出视图 | **3 种**: Rendered / JSON / Code | ✅ **3 种**: Rendered / JSON / Code | 🟢 **已修复** |
| 输出结构 | Codes → Evidence(引用+位置) → Alternatives → Candidates | ✅ Evidence + Alternatives + Candidates 全部前端展示 | 🟢 **已修复** |
| 证据定位 | start/end 字符位置 → 原文高亮 | ✅ 原文引用 + entity_type + confidence | 🟢 **已修复** |
| Settings/Code Tab | ✅ 每页双 tab | ✅ 每页双 tab (SettingsCodeTab 组件) | 🟢 **已修复** |
| SDK 代码自动生成 | ✅ 3 种格式(JS/.NET/JSON) | ✅ 4 种格式(JS/Python/C#/JSON) | 🟢 **已修复** |
| 实时成本 | ✅ $0.041252/次 | ✅ LiveCost 全局 header (useCostStore) | 🟢 **已修复** |
| Event Inspector | ✅ 每页 | ✅ 每页可折叠底部面板 | 🟢 **已修复** |
| Predict 状态 | disabled → enabled(有输入) | 类似 | 🟢 |
| Credits consumed 显示 | 每次预测后更新 | ✅ 有显示 | 🟢 **已修复** |

---

### 1.2 Agents

#### Corti 完整操作流程

```
=== 浏览 Agent 列表 ===
Step 1: /ai-studio/agents
  → 两个 tab: "My agents" / "Pre-built agents"
  → My agents: 3 个自定义 agent 卡片
    - 医疗文档电子签名 (09-May-2026, Luhua Song)
    - ICD-10 Index Navigator Agent (09-May-2026, Luhua Song)
    - Medical Coding Agent (05-May-2026, Luhua Song)
  → Pre-built agents: 空列表(搜索栏: Use case 筛选)
  → "New Agent" 按钮 → /ai-studio/agents/new

=== 查看 Agent 详情 ===
Step 2: 点击 agent 卡片 → /ai-studio/agents/{uuid}
  → 左侧: Chat 测试区
    - "Ask the agent..."
    - 输入框: "What can I help you with?"
    - "+" 按钮(Add context)
    - "Messaging an agent consumes credits"
  → 右侧: Settings tab
    - Name: textbox (如 "Medical Coding Agent", 带字符计数)
    - System Prompt: 大型富文本编辑器
      结构:
        <role>...</role>
        <output_format>...</output_format>
        ## Example Output
    - Experts 区:
      - 已绑定 expert 列表(可扩展/折叠)
        - Coding Expert (coding-expert)
        - Pubmed Expert (pubmed-expert)
        - Web Search Expert (web-search-expert)
        - Medical Calculator Expert (medical-calculator-expert)
      - "Browse Expert Library" 按钮 → 打开专家浏览器
      - "+ Add expert" 按钮 → 添加自定义专家
    - "Pinned message parts" 可折叠区

Step 3: 在 Chat 中测试 Agent
  → 输入 "Code J44.1 and E11.9 for a 68-year-old..."
  → 显示 "Waiting for agent response..."
  → 响应: 完整的结构化编码分析
    - ## Encounter Summary
    - ## Documentation Analysis (表格)
    - ## Code Assignment (Primary/Secondary/Procedures)
    - ## Documentation Gaps (⚠ 标记)
    - ## Uncodable Items (❌ 标记)
    - ## Validation Summary
  → 成本: $0.023348
  → 出现 "Clear chat" 按钮

Step 4: 查看 Code tab
  → 3 种 SDK: JavaScript / .NET / JSON Config
  → SDK 方法: cortiClient.agents.message(agentId, {message, context})

=== 创建新 Agent ===
Step 5: /ai-studio/agents/new
  → 左侧: 模板选择
    - "Start from scratch" + "Create agent" 按钮
    - "Use a template" + "Search templates" 搜索框
    - 20 个预置模板(radio 列表，各带描述)
      ├── 1. ICD-10 Index Navigator Agent
      ├── 2. Rule Explainer Agent
      ├── ...
      └── 20. CDI Agent
  → 右侧: Agent 预览 + Chat 测试区
    - 选中模板后显示模板名称和描述
    - "Customize agent" 按钮
    - Chat 输入框 + "What can you do?" + "Suggest prompt"

=== Browse Expert Library ===
Step 6: 点击 "Browse Expert Library"
  → 弹窗: 搜索 "Search experts"
  → 13 个专家卡片，每个有:
    - 名称 + 描述 + "Read more" 链接
    - 复选框(选中/取消)
  → 底部: "Cancel" + "Done" 按钮
  
=== Edit System Prompt ===
Step 7: 点击 System Prompt 编辑区
  → 弹窗标题: "Edit system prompt"
  → 副标题: "Define the agent's role and style."
  → 大型 textarea，预填完整 prompt
  → "Cancel" + "Save" 按钮
```

#### 对比表

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| Agent 列表 | My agents + Pre-built 两 tab | ✅ My agents + Pre-built 两 tab | 🟢 **已修复** |
| Agent 详情页 | 独立页面 `/agents/{uuid}` | ✅ `/ai-studio/agents/{agentId}` 详情页 | 🟢 **已修复** |
| System Prompt 编辑器 | 弹窗富文本，含 role + output_format | ✅ EditSystemPromptModal 含 XML 标签 + AI 辅助 | 🟢 **已修复** |
| Chat 测试 | 内置聊天，实时响应 | ✅ 内置聊天 + inputFormat(file/json/text) | 🟢 **已修复** |
| Expert 库 | 13 个预置专家(带 Read more) | ✅ 专家浏览器(搜索+分类过滤), 缺 Read more 链接 | 🟡 **partial** |
| Add Expert 弹窗 | 表单: Name + Type + Description | 有但实现不同 | 🟡 |
| 模板系统 | 20 个 pre-configured agent 模板 | ✅ 16 个预置模板 + 搜索 + 模板选择器 | 🟡 **partial** |
| Create from scratch | 直接打开空白 agent | 有类似功能 | 🟢 |
| Code tab(SDK) | 3 种格式，自动填充 | ✅ 4 种格式(JS/Python/C#/JSON) | 🟢 **已修复** |
| Agent 角色 | System Prompt + Experts + Chat | Expert 列表 + AgentRunner | 🔴 → 🟡 |
| Agent Chat 成本显示 | ✅ $0.023348 | ✅ LiveCost header 显示 | 🟢 **已修复** |

---

### 1.3 Speech To Text

#### Corti 完整操作流程

```
Step 1: /ai-studio/speech-to-text
  → 左侧: 录音区
    - "web component preview" 标签
    - 大圆形录音按钮(麦克风图标)
    - "Dictated text" 输出区
    - "Start recording to begin"
    - 右下角: "Detected commands" 区域
  → 右侧: Settings 面板

Step 2: 配置 Settings
  → Dictation language: English (US) en | en-US (combobox)
  → Web component: 折叠区(可展开)
  → Microphone control: 折叠区
  → Punctuation: 折叠区(expanded)
    - Spoken punctuation: switch (default OFF)
    - Automatic punctuation: switch (default ON, per screenshot)
    - Formatting: info 按钮
  → Interim results: switch (default ON)
  → Commands: 折叠区
    - switch (default ON)
    - "+ Add Command" 按钮
    - 预置命令列表:
      - next_section: ["next section", "go to section"] [编辑] [删除]
      - delete: ["delete that", "delete last"] [编辑] [删除]
      - insert_template: ["insert my {template} template", ...] [编辑] [删除]
        - 变量: {template_name}=soap | progress | discharge

Step 3: 录音
  → 浏览器弹出麦克风权限请求 → 允许
  → 点击 "Start recording" → 开始录入
  → 实时显示 interim results
  → 停止后 Dictated text 显示完整转录
  → Event Inspector 记录事件
  → Credits consumed 实时更新(如 $0.004360)

Step 4: 查看 Code tab
  → 5 种格式:
    - HTML (web component)
    - JavaScript (SDK)
    - React
    - .NET (SDK)
    - JSON Config
  → Web Component: <corti-dictation> + dictationConfig(commands)

Step 5: Add Command
  → 点击 "+ Add Command" → 弹窗:
    - Command ID: textbox
    - "Add phrase": button
    - "Add variable": button
    - Cancel / "Add command" [disabled] / Close
```

#### 对比表

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| 录音按钮 | ✅ 大圆形麦克风 | ✅ 类似 | 🟢 |
| Web Component 预览 | ✅ 可见 | ⚠️ 录音UI存在但非Corti风格大圆形麦克风 | 🟡 **partial** |
| 标点设置 | Spoken + Automatic + Formatting | 类似 | 🟢 |
| Interim results | ✅ switch | ✅ 类似 | 🟢 |
| Commands 系统 | ✅ 预置3个 + Add Command | ✅ 有 Add Command | 🟢 |
| 命令变量 | ✅ enum 类型(如 template_name) | ⚠️ CommandVariable interface 存在, enum 支持有限 | 🟡 **partial** |
| 命令编辑/删除 | ✅ 每个命令有独立按钮 | ✅ 类似 | 🟢 |
| Code tab 格式 | 5 种 | ✅ 4 种(JS/Python/C#/JSON), HTML web component 代码作为变量存在 | 🟡 **partial** |
| Tour 引导 | ✅ "New to Speech to Text? Take a tour" | ✅ showTour state + 教程 | 🟢 **已修复** |

---

### 1.4 Embedded Assistant

#### Corti 完整操作流程

```
Step 1: /ai-studio/embedded-assistant
  → 左侧: Preview 区
    - "Preview session"
    - Context tab [active] | + tab
    - "Write something" textbox
    - "Start recording to begin. Facts automatically captured while recording."
    - Record 按钮
  → 右侧: Settings 面板

Step 2: 配置 Settings
  → Default Mode:
    - In-person (radio, selected)
    - Virtual (radio)
  → "Restart session to see changes in the preview" 按钮
  
  → Features(5个 switch):
    - Allow virtual mode: ON
    - Show interaction title: OFF (per screenshot)
    - Enable AI chat: OFF (per screenshot)
    - Show document feedback: OFF (per screenshot)
    - Show navigation: OFF (per screenshot)

  → Appearance:
    - Primary color: #3C61DD (textbox + reset 按钮)

  → Locale:
    - Interface language: Auto (browser default) (combobox)
    - Dictation language: English (US) (combobox)

Step 3: AI Chat (截图 EmbeddedAssistantAIchat)
  → Preview 区有独立 chat 面板
  → 可发送消息与 AI 交互

Step 4: Transcript (截图 EmbeddedAssistantTranscript)
  → 显示录音转录结果

Step 5: 查看 Code tab
  → HTML (web component) / React / JSON Config
  → <corti-embedded> + assistant.auth() + assistant.configureSession()
```

#### 对比表

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| Preview 区 | ✅ "Preview session" + Context tab | ✅ 预览区 + 桌面/移动切换 + AI聊天面板 | 🟢 **已修复** |
| Record 按钮 | ✅ | ✅ 红色录音按钮 | 🟢 |
| Mode 选择 | In-person / Virtual radio | ✅ 诊室内/远程 radio | 🟢 |
| Feature switches | 5 个独立开关 | ✅ 7 个开关(allowVirtual/showTitle/enableAiChat/showFeedback/showNav/enableEditor/showSyncDocument) | 🟢 |
| Primary color | ✅ #3C61DD color picker | ❌ 无 | 🟡 |
| Locale | Interface + Dictation 语言 | ✅ 界面语言+语言 | 🟢 |
| Live Preview | 真实 Web Component | ✅ 实时预览 + 上下文面板 + 转录 | 🟢 **已修复** |
| 5 步引导 Tour | ✅ | ✅ 5 步教程(配置→语音→代码→事件→完成) | 🟢 **已修复** |
| iCoDer 独有 | — | ✅ 自动捕获事实提示 | 🟢 |

---

### 1.5 Text Generation

#### Corti 完整操作流程

```
Step 1: /ai-studio/text-generation
  → 左侧 Input:
    - 输入类型 tabs: String | Facts | Transcript (截图显示 Transcript active)
    - 下方 radio: Text | JSON
    - Use sample 下拉: 3 种示例
    - 文本显示区(时间戳转录文本)
  → 右侧 Output: "Generated document will show here"

Step 2: 配置 Settings
  → Template key: info 图标
  → "Select template" 按钮
  → Output language: English (US) en-US (combobox)
  → Document name: 可折叠
  → Guardrails: 可折叠(info: "Info about disableGuardrails")
  → Documentation mode: 可折叠(info: "Info about documentationMode")

Step 3: 生成
  → "Generate document" 按钮(需先选 template)
```

#### 对比表

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| 输入类型选择 | String/Facts/Transcript (tabs) + Text/JSON (radio) | 类似 | 🟡 |
| Use sample | 3 种示例 | 12 个模板 | 🟢 |
| Template 系统 | 通过 API 动态获取 | ✅ API 动态获取 + localStorage 用户自定义 | 🟢 **已修复** |
| Guardrails 开关 | ✅ toggle | ✅ toggle (传递给 API) | 🟢 **已修复** |
| Documentation mode | ✅ toggle | ❌ 无 | 🟡 |
| iCoDer 独有 | — | ✅ localStorage 模板 CRUD | 🟢 |

---

### 1.6 Fact Extraction

#### Corti 完整操作流程

```
Step 1: /ai-studio/fact-extraction
  → 左侧 Input:
    - "Use sample" 按钮
    - 文本输入区(Enter a text string)
    - "Extract facts" 按钮(disabled until text)
  → 右侧 Output:
    - "Generated facts will show here"
  → Settings tab:
    - Output language: English (US) en-US
  → Code tab:
    - JS/.NET/JSON 3 种
```

#### 对比表

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| 基础流程 | Use sample → Extract → Output | ✅ 相同 | 🟢 |
| 输出结构 | Demographics/HPI/Denials/PMH/Medications/Findings/Assessment/Plan | 有类似结构 | 🟢 |
| Output 操作按钮 | Clear/Copy for Text Gen/Copy/Download | 类似 | 🟢 |
| iCoDer 独有 | — | ✅ click-to-toggle fact status | 🟢 |
| Settings/Code Tab | 共 2 个 tab | 有 Settings+Code | 🟢 |

---

### 1.7 Home / Dashboard

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| CTA 按钮 | "AI Studio" + "Developer quickstart" | 类似 | 🟢 |
| 信用余额 | $50.00 Available + Add credits | ✅ $50.00 + Add | 🟢 |
| 消耗图表 | ✅ Credits consumed chart (日期轴) | ✅ 有图表 | 🟢 |
| 时间范围 | Last 30 days / Compare period | ✅ 30天/7天 | 🟢 |
| iCoDer 独有 | — | ✅ 通知 + 用户菜单 | 🟢 |

---

### 1.8 Developer Quickstart

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| 3 tab | JS SDK / .NET SDK / Code with AI tools | ✅ JS / .NET 双 tab | 🟢 **已修复** |
| Copy .env | ✅ "Copy all as .env variables" | ✅ envVars + 一键复制按钮 | 🟢 **已修复** |
| 凭据显示 | Client ID + Secret + Environment + Tenant | 类似 | 🟢 |
| AI tools tab | ✅ 给 AI 的 prompt 模板 | ❌ 无 | 🟡 |
| 4 个 walkthrough 链接 | ✅ Build dictation/scribe/coding/agentic | 类似 | 🟢 |

---

### 1.9 Billing

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| 3 tab | Plan / Billing History / Business info | ✅ 3 tab(Plan/History/Business info) | 🟢 **已修复** |
| Pay-as-you-go | ✅ Plan 描述 | 类似 | 🟢 |
| Credits Balance | $50.00 + Last updated | ✅ 有 | 🟢 |
| Low balance alerts | ✅ switch ON ($10 threshold) | ✅ switch + threshold | 🟢 **已修复** |
| Auto top-up | ✅ switch OFF | ✅ switch | 🟢 **已修复** |
| Payment methods | "Add a payment method" | ✅ "Add a payment method" | 🟢 **已修复** |
| Business info | Company Name/Email/Tax ID/Address form | ✅ Company/Email/Tax ID/Address 表单 | 🟢 **已修复** |

---

### 1.10 Settings

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| Project Name | ✅ textbox | ✅ 账号详情 | 🟢 |
| Project ID | ✅ 显示 + Copy 按钮 | ✅ 系统信息 | 🟢 |
| Country | ✅ 全球国家列表 combobox | ✅ 国家下拉选择器 | 🟢 **已修复** |
| Save changes | ✅ 按钮 | ✅ handleSave + save 按钮 | 🟢 **已修复** |
| Admin API | ✅ 链接 | ❌ 无 | 🟡 |
| iCoDer 独有 | — | ✅ 护栏切换(6个) | 🟢 |
| iCoDer 独有 | — | ✅ A2A agent 列表 | 🟢 |

---

### 1.11 Team

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| 两 tab | Members / Invitations | Members | 🟡 |
| Invite 弹窗 | Email + Role(Viewer) + Add Member | 类似 | 🟢 |
| 角色显示 | owner | Owner/Admin/Coder/DeptHead/Viewer | 🟢 |

---

### 1.12 API Clients

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| 两 tab | My clients / Default clients | ✅ My/Default clients 双 tab | 🟢 **已修复** |
| Create 弹窗 | Name + Client ID(prefixed) + Usage type + Region | ✅ M2M + OAuth 客户端 | 🟢 |
| Default clients | 预置 2 个(client/embedded) | ✅ 2 个预置(icoder_default/icoder_embedded) | 🟢 **已修复** |

---

### 1.13 Usage

| 功能点 | Corti | iCoDer | 差距 |
|--------|-------|--------|------|
| 时间范围 | Today/7d/30d/Week/Month 下拉 | ✅ 7/30/90 天 | 🟢 |
| 图表 | 柱状图，日粒度 | ✅ 有图表 | 🟢 |
| API client 筛选 | ✅ "All API clients" 下拉 | 类似 | 🟢 |
| Compare period | ✅ checkbox | ✅ checkbox | 🟢 **已修复** |

---

## 二、全局模式差距

| 模式 | Corti | iCoDer | 状态 |
|------|-------|--------|------|
| **Settings/Code 双 Tab** | 所有 AI Studio 页面 | ✅ 所有页面 (SettingsCodeTab 组件) | ✅ 已修复 |
| **Live Cost 实时计数** | 每页 header，$X.XXXXXX 精度 | ✅ 全局 header (useCostStore) | ✅ 已修复 |
| **Event Inspector** | 每页右侧底部 | ✅ 每页可折叠底部面板 | ✅ 已修复 |
| **SDK Code 片段** | JS/.NET/JSON 3 格式，自动填充 | ✅ 4 格式(JS/Python/C#/JSON) | ✅ 已修复 |
| **输出 3 视图** | Rendered/JSON/Code | ✅ Rendered/JSON/Code 三 tab | ✅ 已修复 |
| **编码证据溯源** | 每编码含原文引用 + 字符位置 | ✅ Evidence + entity_type + confidence | ✅ 已修复 |
| **编码系统多选** | combobox + Include/Exclude 过滤器 | 🟡 复选框 5 种 + Include/Exclude | 🟡 部分 |
| **Agent 模板系统** | 20 个预置模板 + System Prompt 编辑器 | ✅ 16 预置模板 + Prompt 编辑器 | 🟡 部分 |
| **Use sample 下拉** | 统一 3 种示例 | 各页面独立实现 | 🟡 |
| **Guided Tour** | 多页面"Take a tour" | 🟡 EmbeddedAssistant 有, STT 有 state, 无全局系统 | 🟡 部分 |
| **暗色主题** | Toggle 按钮 | ✅ Toggle 按钮 (useThemeStore) | ✅ 已修复 |
| **产品分流支持** | CortiHelp: 4 产品选项 + AI 优先 + 可转人工 | 静态支持页 | 🟡 |

---

## 三、iCoDer 完整差距清单（40 项，按优先级）

### P0 — 核心流程缺失（阻塞工作流）

| # | 差距 | 影响页 | 状态 |
|---|------|--------|------|
| P0-1 | **Medical Coding 3 视图输出** | MedicalCodingPage | ✅ 已修复 |
| P0-2 | **编码证据原文引用展示** | MedicalCodingPage | ✅ 已修复 |
| P0-3 | **编码替代建议(Alternatives)** | MedicalCodingPage | ✅ 已修复 |
| P0-4 | **编码系统多选 combobox** | MedicalCodingPage | 🟡 部分 (5种复选框 vs 9种combobox) |
| P0-5 | **Agent 列表/详情独立路由** | AgentsPage | ✅ 已修复 |
| P0-6 | **Agent 20 模板系统** | AgentsPage | 🟡 部分 (16 个预置模板 vs 20) |
| P0-7 | **System Prompt 结构化编辑器** | AgentsPage | ✅ 已修复 |
| P0-8 | **Live Cost 实时成本** | 全局 | ✅ 已修复 (useCostStore) |
| P0-9 | **Settings/Code 双 Tab(始终可见)** | 全局 | ✅ 已修复 (SettingsCodeTab 组件) |
| P0-10 | **Event Inspector(每页)** | 全局 | ✅ 已修复 |
| P0-11 | **Embedded Assistant Live Preview** | EmbeddedAssistantPage | ✅ 已修复 |
| P0-12 | **Embedded Assistant Feature Flags** | EmbeddedAssistantPage | 🟡 部分 (7 toggle vs 5) |
| P0-13 | **过滤器 Include/Exclude codes** | MedicalCodingPage | ✅ 已修复 |
| P0-14 | **SDK Code 片段(每页)** | 全局 | ✅ 已修复 (4 种格式) |

### P1 — UI 模式缺失（显著影响体验）

| # | 差距 | 影响页 | 状态 |
|---|------|--------|------|
| P1-1 | 暗色/亮色主题 Toggle | 全局 | ✅ 已修复 |
| P1-2 | Guided Tour 引导 | STT / Embedded Assistant | 🟡 部分 (仅 EmbeddedAssistant 有完整5步教程) |
| P1-3 | Agent Chat "Add file/json/text/context" 多类型输入 | AgentsPage | ✅ 已修复 |
| P1-4 | "What can you do?" / "Suggest prompt" 引导按钮 | AgentsPage | ✅ 已修复 |
| P1-5 | Expert Library "Read more" 文档链接 | AgentsPage | 🔴 未解决 |
| P1-6 | Expert Library 搜索框 | AgentsPage | ✅ 已修复 |
| P1-7 | Developer Quickstart .NET SDK tab | DeveloperQuickstartPage | ✅ 已修复 |
| P1-8 | Developer Quickstart .env 一键复制 | DeveloperQuickstartPage | ✅ 已修复 |
| P1-9 | Billing Alerts + Auto top-up + Payment methods | BillingPage | ✅ 已修复 |
| P1-10 | Billing Business info 表单 | BillingPage | ✅ 已修复 |
| P1-11 | Speech To Text 指令变量枚举 | SpeechToTextPage | 🟡 部分 (CommandVariable interface 存在, enum 支持有限) |
| P1-12 | Speech To Text Web Component 预览 | SpeechToTextPage | 🟡 部分 (录音UI存在但非 Corti 风格) |
| P1-13 | Text Generation Guardrails 独立 toggle | TextGenerationPage | ✅ 已修复 |
| P1-14 | Settings Country 选择 | SettingsPage | ✅ 已修复 |
| P1-15 | Agent 列表搜索/筛选 | AgentsPage | ✅ 已修复 |

### P2 — 锦上添花（体验提升）

| # | 差距 | 影响页 | 状态 |
|---|------|--------|------|
| P2-1 | AI Studio Overview 独立页面 | AIStudioOverviewPage | ✅ 已修复 |
| P2-2 | Embedded Assistant 5 步引导 Tour | EmbeddedAssistantPage | ✅ 已修复 |
| P2-3 | Home/Usage Compare period 复选框 | HomePage/UsagePage | ✅ 已修复 |
| P2-4 | Billing History 独立 tab | BillingPage | ✅ 已修复 |
| P2-5 | STT .NET SDK Code tab | SpeechToTextPage | 🟡 部分 (4种格式 vs 5) |
| P2-6 | Medical Coding Expand 开关 | MedicalCodingPage | ✅ 已修复 |
| P2-7 | Settings Save changes 按钮 | SettingsPage | ✅ 已修复 |
| P2-8 | Default API Clients 预置 | APIClientsPage | ✅ 已修复 |
| P2-9 | New Agent 模板搜索 | AgentsPage | ✅ 已修复 |
| P2-10 | Get Help Intercom chat widget | SupportPage | 🔴 未解决 (静态链接, 无实时聊天) |
| P2-11 | Text Generation 模板 API 动态获取 | TextGenerationPage | ✅ 已修复 |

### 差距闭合统计 (2026-05-16)

| 优先级 | 总数 | ✅ 已修复 | 🟡 部分 | 🔴 未解决 | 闭合率 |
|--------|------|-----------|---------|-----------|--------|
| P0 | 14 | 11 | 3 | 0 | 78.6% |
| P1 | 15 | 11 | 3 | 1 | 73.3% |
| P2 | 11 | 9 | 1 | 1 | 81.8% |
| **总计** | **40** | **31** | **7** | **2** | **77.5%** |

**剩余 2 项未解决:**
- P1-5: Expert Library "Read more" 文档链接
- P2-10: Get Help Intercom 实时聊天组件

**剩余 7 项部分解决:**
- P0-4: 编码系统 5 种复选框 vs Corti 9 种 combobox
- P0-6: Agent 16 预置模板 vs Corti 20
- P0-12: Embedded Assistant 7 toggle vs Corti 5
- P1-2: Guided Tour 仅 EmbeddedAssistant 完整, 缺跨页面全局系统
- P1-11: STT CommandVariable enum 支持有限
- P1-12: STT 录音UI 非 Corti 大圆形麦克风风格
- P2-5: STT Code tab 4 种格式 vs Corti 5 种

---

## 四、iCoDer 独有优势（Corti 缺失的功能）

iCoDer 并非全面落后——以下功能 Corti 没有：

| 功能 | 页面 | 描述 |
|------|------|------|
| click-to-toggle fact status | FactExtractionPage | 点击事实切换状态: 已确认/待确认/已排除/已执行/计划中/已讨论 |
| 编码字典查询 | CodeDictionariesPage | ICD-10/ICD-9 编码字典模糊搜索 + 层级浏览 |
| 规则库浏览+检索 | RuleLibrariesPage | 15 条中文编码规则 + 规则测试沙盒 |
| 金标准评估 | GoldCasesPage + EvaluationPage | CSV 导入 + 批量评估 + 指标报告 |
| 人工审核工作台 | CaseReviewPage | 逐编码确认/驳回/修改 + 键盘快捷键 + 批量操作 |
| 编码工作台 | CodingWorkbenchPage | 4 面板(原文/证据/候选/报告) + DRG 面板 |
| OAuth 2.0 + API Key 双认证 | APIClientsPage | Corti 仅 OAuth |
| 模板 CRUD | TextGenerationPage | localStorage 创建/编辑/删除模板 |
| 多角色权限系统 | LoginPage/全局 | 6 种角色 (admin/coder/dept_head/insurance/qc/clinician) |
| 置信度阈值 slider | MedicalCodingPage | 0-1 slider 控制编码建议阈值 |
| 多码表管理 | CodeTablePage | 4 套编码字典(国标/医保/院内/ICD-9-CM-3), 跨表映射 |
| LLM 主诊断选择 | MedicalCodingPage | LLM 临床推理: "急性入院原因优先于慢性病", .9 未特指码降权 |
| 编码审核跨表视图 | ReviewResponse | cross_table_view 显示主诊断在每个码表中的表达 + 有效性 |
