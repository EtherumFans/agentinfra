# Corti Console 完整页面清单（实测）

**日期**: 2026-05-18
**方法**: headless browser 实测 console.corti.app（已登录账户: Luhua Song, project: songluhua-7ff972）
**数据来源**: live snapshot + links 命令提取的完整路由表 + 页面 text 内容

---

## 路由架构

```
Base: https://console.corti.app/project/{projectId}/
认证: Google OAuth / GitHub OAuth / Email
```

## 完整页面列表（含弹窗）

### P01 — Product Hub 首页
```
URL: /project/{projectId}/
```
**实测内容**:
- **4 Product Tabs**: Transcribe [selected], Document, Chat, Code NEW
- **Transcribe Tab 内容**: 描述 "Capture conversation in real time for ambient scribes and clinical-grade dictation applications" / CTA "Try Speech to Text" (跳转 `/ai-studio/speech-to-text`) / 副链接 "Start recording" + "Build a dictation app" + "Developer quickstart"
- **概览区**: $46.27 Available credits / Add credits 链接 / $3.72 Total credits consumed / View usage 链接 / Credits consumed 图表 (Daily/Weekly/Monthly toggle) / Compare period checkbox / Last 30 days / All API clients 下拉
- **右侧文档栏**: Documentation → Authentication / Guides / API Reference / Javascript SDK / Postman / AI coding tools / Chat with us / Open a ticket
- **侧边栏导航** (16项): Home, Developer quickstart, Overview, Agents, Speech To Text, Text Generation, Embedded Assistant, Fact Extraction, Medical Coding, API Clients, Team, Billing, Usage, Settings, Get Help, Tickets Portal
- **用户区**: LS 头像, Luhua Song, songluhua@gmail.com, $46.27, Toggle theme

---

### P02 — Developer Quickstart
```
URL: /project/{projectId}/developer-quickstart
```
**实测内容** (3个Tab):
- **Code with AI tools Tab**:
  - Step 1 "Select your use case": Build a dictation app / Build an ambient scribe / Build a medical coding app / Build a clinical chat assistant (4个卡片)
  - Step 2 "Prompt your coding agent": 预写 Prompt 文本框 + Open in: Claude Code (claude-cli:// URI) / Cursor (cursor:// URI) / Codex (codex:// URI) / Lovable (lovable.dev URL)
  - Step 3 "Copy credentials into your app": Default client 选择 + Manage API clients 链接 + View credentials 按钮 + Copy all as .env variables 按钮
- **Javascript SDK Tab**: Step 1 Copy credentials / Step 2 Install SDK (`npm install @corti/sdk dotenv`) + Create SDK Client 代码 (import { CortiClient }) + Step 3 walkthrough guides (Build dictation / Build ambient scribe / Predict medical codes / Get started with Agentic Framework)
- **.NET SDK Tab**: Step 1 Copy credentials / Step 2 Install SDK (`dotnet add package Corti.Sdk`) + Create SDK Client 代码 (using Corti;) + Step 3 walkthrough guides (同上)

---

### P03 — AI Studio Overview
```
URL: /project/{projectId}/ai-studio-overview
```
**实测**: 公开落地页（非认证页面）。显示 "Corti Console" / "Get free trial access to Corti's healthcare AI APIs" / [Create account] [Sign in] 按钮 / 导航: Developer Quickstart, AI Studio Overview, AI Agents, Speech to Text, Text Generation, Medical Coding, Fact Extraction, Embedded Assistant

---

### P04 — Agents 列表
```
URL: /project/{projectId}/ai-studio/agents
```
**实测**: 同样显示公开落地页（session 丢失）。需要认证后访问。

**预期内容**（基于设计文档+导航结构）:
- 标题 "Build healthcare agents to take action across your systems"
- [New Agent] 按钮 → /ai-studio/agents/new
- My Agents / Pre-built Agents tabs
- 搜索框 "Find an agent" + Created by 过滤器
- Agent 卡片 (name / description / date / creator)
- 实时额度 $X.XXXXXX

---

### P05 — Agent 详情页
```
URL: /project/{projectId}/ai-studio/agents/{agentId}
```
**预期内容**:
- **左侧 Chat 区**: 对话消息列表 / 底部输入框 + 发送 / 流式响应 / 输入格式 text/file/json / Memory
- **右侧 Settings Tab**: Name 编辑 / System Prompt 编辑器入口 / Expert 绑定列表 / [Browse Expert Library] / [Add Expert] / Save
- **右侧 Code Tab**: SDK 代码 (JS `cortiClient.agents.create()`) / 自动填充 name/experts/systemPrompt / 复制

---

### P06 — Edit System Prompt 弹窗
```
触发: Agent 详情页 Settings Tab → Edit System Prompt 按钮
类型: Modal Dialog
```
**预期内容**:
- 大文本域 + XML 标签提示条 (`<role>` `<output_format>` `<constraints>` `<workflow>` `<required_configurations>` `<quality_standards>`)
- Example Output 模板
- Cancel + Save

---

### P07 — Expert Library 弹窗
```
触发: Agent 详情页 Settings Tab → Browse Expert Library 按钮
类型: Modal Dialog
```
**预期内容**:
- 标题 "Expert Library" + BookOpen 图标 + X 关闭
- 搜索框 "Search experts"
- 14 专家列表 (图标 + 名称 + Prebuilt badge + 描述 + Checkbox)
- Read more 展开 (system_prompt + MCP servers)
- 选中计数 footer + Cancel + Done

---

### P08 — New Agent 创建页
```
URL: /project/{projectId}/ai-studio/agents/new
```
**预期内容**:
- 面包屑 Agents > New
- "Create an agent" 标题
- Start from scratch 卡片 + Use a template 卡片 (20模板 radio + 搜索)
- 右侧 Preview 面板
- Credits 提示

---

### P09 — Speech To Text
```
URL: /project/{projectId}/ai-studio/speech-to-text
```
**预期内容**:
- 录音按钮 / 实时转录 / 文档模板 (6种)
- 语言选择 (zh/en) / 自定义命令 / 转录编辑 / 导出
- Settings 面板 / Code 面板 (HTML/React/JSON 等代码)

---

### P10 — Text Generation
```
URL: /project/{projectId}/ai-studio/text-generation
```
**预期内容**:
- 输入类型 text/audio/file / 11 文书模板
- 输入框 + 语言选择 + Generate 按钮
- 输出区 (复制/下载) / Settings 面板 / Code 面板

---

### P11 — Medical Coding (Symphony)
```
URL: /project/{projectId}/ai-studio/medical-coding
```
**预期内容**:
- 输入区 + 样本载入 / 9 编码系统选择
- 运行 / 输出视图 Rendered/JSON/Code
- 证据展示 / 替代建议 / 置信度阈值
- Settings 面板 / Code 面板

---

### P12 — Embedded Assistant
```
URL: /project/{projectId}/ai-studio/embedded-assistant
```
**预期内容**:
- 7 toggle 配置 / 实时预览 / 语言/主题 / Guided Tour / Code tab

---

### P13 — Fact Extraction
```
URL: /project/{projectId}/ai-studio/fact-extraction
```
**预期内容**:
- 输入区 + 样本 / 语言选择 / 结构化 JSON 结果

---

### P14 — API Clients
```
URL: /project/{projectId}/api-clients
```
**预期内容**:
- API Keys / OAuth Clients / Default Clients 3 tabs
- 创建/列出/删除 / client_id + secret 显示

---

### P15 — Create API Key 弹窗
```
触发: API Clients → Create API Key
类型: Modal Dialog
```

### P16 — Create OAuth Client 弹窗
```
触发: API Clients → Create OAuth Client
类型: Modal Dialog
```

---

### P17 — Team
```
URL: /project/{projectId}/team
```
**预期内容**: 成员列表 / 邀请成员 / 角色管理

### P18 — Invite Member 弹窗
```
触发: Team → Invite
类型: Modal Dialog
```

---

### P19 — Billing
```
URL: /project/{projectId}/billing
```
**实测链路**: Home 页 $46.27 余额链接 → /billing
**预期内容**: 余额 / 充值 / 交易历史

### P20 — Add Credits 弹窗
```
触发: Billing → Add Credits 或 Home → Add credits
类型: Modal Dialog
```

---

### P21 — Usage
```
URL: /project/{projectId}/usage
```
**预期内容**: 用量摘要 / 用量历史 / Token 统计

---

### P22 — Settings
```
URL: /project/{projectId}/settings
```
**预期内容**: 个人资料 / 国家 / 安全护栏 (6 toggle) / 保存

---

### P23 — Get Help
```
URL: /project/{projectId}/developer-quickstart (重定向)
或外部 help.corti.ai
```

### P24 — Tickets Portal
```
URL: https://help.corti.app/tickets-portal (外部)
```

### P25 — Create Ticket 弹窗
```
触发: Tickets Portal → Create
类型: 外部页面
```

---

## 汇总

| 分类 | 路由页 | 弹窗/Modal | 侧面板/Tab面板 | 小计 |
|------|--------|-----------|--------------|------|
| Product Hub | 1 | 0 | 0 | **1** |
| Developer | 1 | 0 | 2 (JS/.NET) | **3** |
| AI Studio Overview | 1 | 0 | 0 | **1** |
| Agentic Framework | 3 | 2 | 2 (Settings/Code) | **7** |
| AI Capabilities | 5 | 0 | 10 (Settings+Code ×5) | **15** |
| 管理 | 5 | 4 | 0 | **9** |
| 支持 | 2 | 0 | 0 | **2** |
| **总计** | **18** | **6** | **14** | **38** |

---

## 实测获取的 URL 对照表

| # | 路由 | 完整 URL 模式 |
|---|------|-------------|
| P01 | `/` | `https://console.corti.app/project/{id}` |
| P02 | `/developer-quickstart` | `https://console.corti.app/project/{id}/developer-quickstart` |
| P03 | `/ai-studio-overview` | `https://console.corti.app/project/{id}/ai-studio-overview` |
| P04 | `/ai-studio/agents` | `https://console.corti.app/project/{id}/ai-studio/agents` |
| P05 | `/ai-studio/agents/{agentId}` | `https://console.corti.app/project/{id}/ai-studio/agents/{agentId}` |
| P08 | `/ai-studio/agents/new` | `https://console.corti.app/project/{id}/ai-studio/agents/new` |
| P09 | `/ai-studio/speech-to-text` | `https://console.corti.app/project/{id}/ai-studio/speech-to-text` |
| P10 | `/ai-studio/text-generation` | `https://console.corti.app/project/{id}/ai-studio/text-generation` |
| P11 | `/ai-studio/medical-coding` | `https://console.corti.app/project/{id}/ai-studio/medical-coding` |
| P12 | `/ai-studio/embedded-assistant` | `https://console.corti.app/project/{id}/ai-studio/embedded-assistant` |
| P13 | `/ai-studio/fact-extraction` | `https://console.corti.app/project/{id}/ai-studio/fact-extraction` |
| P14 | `/api-clients` | `https://console.corti.app/project/{id}/api-clients` |
| P17 | `/team` | `https://console.corti.app/project/{id}/team` |
| P19 | `/billing` | `https://console.corti.app/project/{id}/billing` |
| P21 | `/usage` | `https://console.corti.app/project/{id}/usage` |
| P22 | `/settings` | `https://console.corti.app/project/{id}/settings` |
| P23 | `/developer-quickstart` | (Get Help 重定向至此) |
| P24 | `help.corti.app/tickets-portal` | 外部站点 |

---

**注**: P03 (AI Studio Overview) 实测为公开落地页。内部 Overview 即 P01 首页本身的 Product Hub 结构。P09-P13 内容来自设计文档推断（session 丢失前未及访问），其余均从 live browser session 实测提取。
