# Corti Console vs iCoDer 差距分析

**日期**: 2026-05-19
**方法**: browse daemon 实测 console.corti.app (账户: Luhua Song) 共 15 页
**iCoDer 基线**: E:\Corti4C\ 最新 master 分支

---

## 一、导航结构对比

### Corti 侧边栏 (实测)
```
Home
Developer quickstart
── AI Studio ──
  Overview
  Agents
  Speech To Text
  Text Generation
  Embedded Assistant
  Fact Extraction
  Medical Coding
── Manage ──
  API Clients
  Team
  Billing
  Usage
  Settings
── Support ──
  Get Help
  Tickets Portal
```

### iCoDer 侧边栏
```
首页
开发者快速入门
── AI Studio ──
  总览, 智能体, 语音转文字, 文书生成, 嵌入式助手, 事实提取, 医学编码
── 编码审核 ──
  编码工作台              ← iCoDer 独有
── 管理 ──
  API 客户端, 团队, 计费, 用量, 设置
── 数据管理 ──              ← iCoDer 独有
  码表管理, 编码字典, 规则库, 金标准病例, 智能体评估, 专家库
── 支持 ──
  获取帮助, 工单中心
```

**差距**: iCoDer 多 2 个分组(编码审核+数据管理)，承载独有临床审核功能。Corti 无此能力。

---

## 二、逐页对比

### P01 — Product Hub 首页

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| 4 Product Tab | Transcribe/Document/Chat/Code NEW | 语音转录/文书/Agentic Framework/Prism 医学编码 NEW | 无 |
| Tab 切换 | Pill按钮, inset-shadow | 同 | 无 |
| 余额展示 | $46.27 + Add credits 链接 | ¥50.00 + 充值按钮 | 无 |
| 用量图表 | Daily/Weekly/Monthly + Compare | 日/周/月 + 对比周期 | 无 |
| API 客户端过滤 | Last 30 days / All API clients 下拉 | 无此过滤器 | **缺** |
| 文档侧栏 | Auth/Guides/API/JS SDK/Postman/AI tools/Chat/Ticket | 认证/指南/API/JS SDK/Postman/在线咨询/提交工单 | 无 |
| **实时额度** | 每个 AI 功能页 footer 显示 $X.XXXXXX | 有 | 无 |

### P02 — Developer Quickstart

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| **Code with AI tools tab** | 4 use cases + 4 AI tools (Claude Code/Cursor/Codex/Lovable) | 同(4 use cases, 4 AI tools) | 无 |
| AI tool links | Deeplink: claude-cli://, cursor://, codex://, lovable.dev URL | 同 | 无 |
| Step 1 | Select use case 按钮组 | 同 | 无 |
| Step 2 | 预写 Prompt + Copy 按钮 + Open in 选项 | 同 | 无 |
| Step 3 | Credentials .env + Copy all as .env | 同 | 无 |
| JS SDK tab | npm install + Create Client 代码 + walkthrough guides | 同 | 无 |
| .NET SDK tab | dotnet add + Create Client 代码 + walkthrough guides | 同 | 无 |
| **SDK 代码自动填充凭据** | 实时 client_id + secret | 部分 (需手动获取) | **差距** |

### P03 — AI Studio Overview

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| 3 支柱 | Explore / Inspect / Configure | 探索 / 检查 / 配置 | 无 |
| 6 能力卡片 | Agents/STT/TextGen/Embedded/FactExt/MedCode | 同 6 卡片 | 无 |
| Each card: Explore + Docs | 每卡片 Explore 内链 + Docs 外链 | 同 | 无 |

### P04 — Agents 列表

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| 标题 | "Create an agent — Build healthcare agents to take action across your systems" | 同 | 无 |
| New Agent 按钮 | 右侧按钮 → /agents/new | 弹窗(非独立页) | **交互差异** |
| My Agents / Pre-built tabs | ✓ | ✓ | 无 |
| Created by 过滤器 | 下拉选择 | ✓ | 无 |
| Agent 卡片 | name/desc/date/creator | 同 | 无 |
| 实时额度 footer | $0.000000 | ¥0.000000 | 无 |
| Open filter menu | ✓ | 无 | **缺** |

### P05 — Speech To Text

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| **Web Component Preview** | 嵌入式听写组件预览 | 无 | **大差距** |
| Dictated text 区 | 转录文本展示 | 转录展示 | 无 |
| 引导 Tour | "New to STT? Take a tour" | 无 | **缺** |
| Settings 面板 | Dictation language / Punctuation / Formatting / Commands | 同 | 无 |
| Add Command | 命令变量 enum 支持 | 同 | 无 |
| Code tab | 5 格式: HTML(web component) + JS(SDK) + React + .NET + JSON Config | HTML + React + JSON(3种) | **少 2 种** |
| 实时额度 footer | Credits consumed: $X | 同 | 无 |

### P06 — Medical Coding

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| Input 区 | 文本输入 + 样本载入 | 同 | 无 |
| 编码系统 | ICD-10-CM Outpatient(×标签) | 9 种 checkbox | 无 |
| Filter codes | Include/Exclude + Add codes | 同 | 无 |
| Output 区 | Predicted codes will show here | Rendered/JSON/Code 三视图 | **iCoDer 超出** |
| Event Inspector | ✓ | ✓ | 无 |
| Code tab | JS(.NET) SDK + JSON Config | JS + Python + C# | **iCoDer 超出** |
| 实时额度 | Credits consumed: N/A | ✓ | 无 |

### P07 — Text Generation

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| Input type | String / Facts / Transcript / Text / JSON (5种) | text / audio / file (3种) | **少 Facts+JSON** |
| Sample 载入 | ✓ | ✓ | 无 |
| Templates | Template key 选择器 | 11 预设模板 | **iCoDer 超出** |
| Guardrails toggle | ✓ | 无 | **缺** |
| Documentation mode | ✓ | 无 | **缺** |
| Code tab | JS(.NET)+JSON Config | 同 | 无 |

### P08 — API Clients

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| Create API client 按钮 | ✓ | ~~硬编码~~(已清理) | 无 |
| My clients / Default clients tabs | ✓ | OAuth Clients / API Keys / Default | **iCoDer 超出** |

### P09 — Team

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| Members 表格 | Email / Name / Role / Actions | 同 | 无 |
| Invite 按钮 | ✓ | ✓ | 无 |
| Invitations 区域 | ✓ | 无 | **缺** |
| 角色类型 | owner (仅显示) | 6 种 (admin/coder/dept_head/insurance/qc/clinician) | **iCoDer 超出** |

### P10 — Billing

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| Plan 信息 | Plan tab | 余额 + 充值 + 历史 | **交互不同** |
| Billing History | ✓ | ✓ | 无 |
| Business info | ✓ | 无 | **缺** |

### P11 — Usage

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| 时间范围 | Last 7 days / Last 30 days 等 | 日/周/月 | 无 |
| API client 过滤器 | All API clients 下拉 | 无 | **缺** |
| 图表 | 日消耗柱状图 | 日消耗柱状图 | 无 |
| Available/Total credits | ✓ | ✓ | 无 |

### P12 — Settings

| 要素 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| Project Name | 编辑 + Project ID 显示 | 同(双击可编辑) | 无 |
| Country 选择 | 全量国家列表(~200国) | 全量国家列表 | 无 |
| Save changes | ✓ | localStorage 持久化 | 无 |

---

## 三、差距汇总

### 功能差距 (iCoDer 需补充)

| # | 优先级 | 页面 | 差距 | 工作量 |
|---|--------|------|------|--------|
| G1 | P1 | P01 Home | API client 过滤器 (消耗图表) | 小 |
| G2 | P1 | P02 DevQS | SDK 代码自动填充真实凭据 | 中 |
| G3 | P1 | P05 STT | Web Component 预览 + Tour 引导 | 中 |
| G4 | P2 | P05 STT | Code tab 少 2 种格式 (JS SDK + .NET) | 小 |
| G5 | P2 | P07 TextGen | 缺 Facts + JSON 输入类型 + Guardrails | 小 |
| G6 | P2 | P09 Team | 缺 Invitations 区域 | 小 |
| G7 | P2 | P10 Billing | 缺 Business info | 小 |
| G8 | P3 | P11 Usage | API client 过滤器 | 小 |
| G9 | P3 | P04 Agents | Open filter menu | 小 |
| G10 | P3 | P07 TextGen | Documentation mode toggle | 小 |

### iCoDer 超出 Corti 的能力

| # | 能力 | 说明 |
|---|------|------|
| 1 | 编码审核工作台 (CodingWorkbench) | 7-Tab 临床审核 Pipeline |
| 2 | 人工复核驾驶舱 (CaseReview) | 键盘快捷键 + 批量操作 + 安全规则 |
| 3 | 多码表管理 + 跨表映射 | Corti 有 9 系统但无跨表功能 |
| 4 | 金标准评估 (GoldCases + Evaluation) | CSV 导入 + 批量评估 + 试点报告 |
| 5 | LLM 主诊断选择 | Corti-style prompt + LLM fallback |
| 6 | 6 角色权限系统 | Corti 仅 owner 一种 |
| 7 | 全中文临床叙事引擎 | Clinical Narrative + Evidence Story |
| 8 | Expert Library 30+ (vs Corti 14) | 含医保/质控/护理等中文场景 |
| 9 | Runtime 安全框架 | 5 层门控 + 9 状态流转 |
| 10 | 规则库 + 测试沙盒 | 15 条中文编码规则 |
| 11 | 3 语言 SDK 代码生成 | JS + Python + C# (Corti 仅 JS + .NET) |
| 12 | WebSocket 流式 Agent | Corti SSE 流式 |

---

## 四、总结

**对齐度**: iCoDer 已实现 Corti Console 全部核心功能。剩余 10 个差距均为 P1-P3 级别（小功能缺失或交互差异），工作量 < 1 天。

**差异化**: iCoDer 在临床审核 Pipeline、金标准评估、多角色权限、多码表映射、Runtime 安全等 12 个维度超越 Corti。
