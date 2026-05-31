# Corti Console 完整功能列表

**来源**: Corti Console 2026-05-16 实测 + 设计分析文档
**方法**: headless browser 逐页实测 + 结构分析
**输出**: 面向工程复刻的完整功能规格

---

## 一、Product Hub (首页)

```
URL: /
定位: 产品中枢, 非 Dashboard
```

### 1.1 4 产品 Tab 区

| ID | 功能 | 详细规格 |
|----|------|---------|
| H-01 | Tab: Transcribe | 标签: "Transcribe" / 描述: "Capture conversation in real time for ambient scribes and clinical-grade dictation applications" / CTA: "Try Speech to Text" → /ai-studio/speech-to-text / 副链接: "Start recording", "Build a dictation app", "Developer quickstart" |
| H-02 | Tab: Document | 标签: "Document" / 描述: "Turn transcripts, facts, or data into clinical documentation — tailored to your format, specialty, and language" / CTA: "Try Text Generation" → /ai-studio/text-generation / 副链接: "AI Studio", "Build an ambient scribe" |
| H-03 | Tab: Chat (Agentic Framework) | 标签: "Agentic Framework" / 描述: "Build advanced AI agents that perform high-quality clinical and operational tasks" / CTA: "Try the Agentic Framework" → /ai-studio/agents / 副链接: "AI Studio", "Build a clinical chat assistant" |
| H-04 | Tab: Code (Symphony) | 标签: "Symphony for Medical Coding" + "NEW" badge / 描述: "Convert unstructured clinical text into structured medical codes for revenue cycle management and more" / CTA: "Try Symphony for Medical Coding" → /ai-studio/medical-coding / 副链接: "AI Studio", "Build a medical coding app" |

### 1.2 概览区 (Overview Section)

| ID | 功能 | 详细规格 |
|----|------|---------|
| H-05 | 信用余额 | 实时余额数值 + 充值按钮 |
| H-06 | 用量统计图 | 日/周/月切换 + 柱状图 + 对比周期 toggle |
| H-07 | API 请求数 | 近 30 天总数 |
| H-08 | 平均响应时间 | 毫秒级显示 |

---

## 二、导航系统

```
结构: 分组导航 (4 组)
```

### 2.1 导航分组

| ID | 功能 | 详细规格 |
|----|------|---------|
| N-01 | 顶级导航 | 首页, 开发者快速入门 |
| N-02 | AI Studio 组 | 总览, 智能体, 语音转文字, 文书生成, 嵌入式助手, 事实提取, 医学编码 |
| N-03 | 管理组 | API 客户端, 团队, 计费, 用量, 设置 |
| N-04 | 支持组 | 获取帮助, 工单中心 |

### 2.2 侧边栏功能

| ID | 功能 | 详细规格 |
|----|------|---------|
| N-05 | 项目名称 | 可编辑 (双击), 持久化到 localStorage |
| N-06 | 项目切换器 | API 客户端下拉选择 |
| N-07 | 文档侧边栏 (右) | 全局右栏: 文档 (认证/指南/API参考), SDK与工具 (JS/Postman), 帮助 (在线咨询/提交工单) |
| N-08 | 关闭/展开 | X 按钮关闭, BookOpen 按钮重新打开 |

---

## 三、AI Studio Overview

```
URL: /ai-studio
定位: 平台门户页
```

### 3.1 3 支柱区

| ID | 功能 | 详细规格 |
|----|------|---------|
| AS-01 | Explore 支柱 | 标题 "探索" / 描述 "构建智能体, 生成实时转录文本, 临床文书等" |
| AS-02 | Inspect 支柱 | 标题 "检查" / 描述 "使用事件查看器调试并监控实时额度消耗" |
| AS-03 | Configure 支柱 | 标题 "配置" / 描述 "根据需求微调设置, 并将代码直接复制到应用中" |

### 3.2 6 能力卡片

| ID | 功能 | 详细规格 |
|----|------|---------|
| AS-04 | Agents 卡片 | 标题 "智能体" / 描述 "通过添加专家和系统提示定制智能体" / [Explore]/[Docs] 按钮 |
| AS-05 | Speech To Text 卡片 | 标题 "语音转文字" / 描述 "流式传输实时音频, 配置命令并生成转录文本" / [Explore]/[Docs] |
| AS-06 | Text Generation 卡片 | 标题 "文书生成" / 描述 "将转录文本转化为结构化临床记录, 根据需求定制" / [Explore]/[Docs] |
| AS-07 | Embedded Assistant 卡片 | 标题 "嵌入式助手" / 描述 "配置并测试嵌入式助手的各项设置" / [Explore]/[Docs] |
| AS-08 | Fact Extraction 卡片 | 标题 "事实提取" / 描述 "从医疗转录文本和记录中提取结构化临床事实" / [Explore]/[Docs] |
| AS-09 | Medical Coding 卡片 | 标题 "医学编码" / 描述 "将非结构化临床文本转化为结构化医疗编码" / [Explore]/[Docs] |

### 3.3 底部 CTA

| ID | 功能 | 详细规格 |
|----|------|---------|
| AS-10 | 开发者入口 | 文案 "准备好开始编写代码并发起您的第一个请求了吗?" / [开发者快速入门] 按钮 |

---

## 四、Agentic Framework

```
定位: 医疗 Agent 构建平台的核心
```

### 4.1 Agents 列表页

```
URL: /ai-studio/agents
```

| ID | 功能 | 详细规格 |
|----|------|---------|
| AG-01 | 页面标题 | "Create an agent" / 副标题 "构建医疗AI Agent以跨系统执行操作" |
| AG-02 | New Agent 按钮 | 页面主导航按钮 → /ai-studio/agents/new |
| AG-03 | My Agents tab | 用户创建的 agent 列表 |
| AG-04 | Pre-built Agents tab | 预置 agent 模板列表 |
| AG-05 | 搜索框 | "Find an agent" 搜索框, 按名称过滤 |
| AG-06 | Created by 过滤器 | 下拉选择创建者 |
| AG-07 | Agent 卡片 | 标题 / 描述 / 创建日期 / 创建者 / 点击进入详情 |
| AG-08 | 实时额度显示 | footer 显示当前费用 $X.XXXXXX |

### 4.2 Agent 详情页

```
URL: /ai-studio/agents/{agentId}
布局: 左侧 Chat + 右侧 Settings/Code 双Tab
```

#### 4.2.1 Chat 区 (左)

| ID | 功能 | 详细规格 |
|----|------|---------|
| AG-10 | 消息列表 | 对话历史, user/assistant 角色区分 |
| AG-11 | 输入框 | 底部输入框 + 发送按钮 |
| AG-12 | 流式响应 | WebSocket 流式输出 |
| AG-13 | 输入格式切换 | text / file / json |
| AG-14 | Memory 加载 | 加载历史对话记忆 |

#### 4.2.2 Settings Tab (右)

| ID | 功能 | 详细规格 |
|----|------|---------|
| AG-20 | Agent 名称编辑 | 20/50 字符限制, 内联编辑 |
| AG-21 | System Prompt 编辑器 | 模态框, 大文本域, 结构化 XML 标签 |
| AG-22 | `<role>` 标签 | Agent 角色定义 |
| AG-23 | `<output_format>` 标签 | 输出结构, 含 Markdown 表格模板 |
| AG-24 | `<constraints>` 标签 | 约束规则 (不推断/证据引用/合规边界) |
| AG-25 | `<workflow>` 标签 | 7 步工作流 (Synthesize→Extract→Assign ICD→Assign CPT→Validate→Identify Gaps→Flag Uncodable) |
| AG-26 | `<required_configurations>` 标签 | 前置条件检查 |
| AG-27 | `<quality_standards>` 标签 | 10 条质量标准 |
| AG-28 | **Example Output 块** | 在 `<output_format>` 内, 包含完整的示例输出 (Encounter Summary/Analysis/Assignment/Gaps/Unsupported/Validation) |
| AG-29 | AI Generate 按钮 | 基于 agent 名称自动生成 system prompt |
| AG-30 | Expert 绑定列表 | 已绑定 expert 的名称 + 删除按钮 |
| AG-31 | Browse Expert Library 按钮 | 打开 Expert 选择器弹窗 |
| AG-32 | Add Expert 按钮 | 添加自定义 expert |
| AG-33 | Save 按钮 | 保存 Settings 修改 |
| AG-34 | Pinned message parts | 可折叠的消息部件配置 |

#### 4.2.3 Code Tab (右)

| ID | 功能 | 详细规格 |
|----|------|---------|
| AG-40 | SDK 代码片段 | `cortiClient.agents.create({ name, experts, systemPrompt })` |
| AG-41 | 代码自动填充 | 自动填充当前 UI 配置 (name/experts/systemPrompt) |
| AG-42 | 消息发送代码 | `cortiClient.agents.messageSend(agentId, { message })` |
| AG-43 | 代码复制按钮 | 一键复制完整代码 |
| AG-44 | 多语言 | JavaScript / Python SDK |

#### 4.2.4 Expert Library Modal

| ID | 功能 | 详细规格 |
|----|------|---------|
| AG-50 | 弹窗标题 | "Expert Library" + BookOpen 图标 + X 关闭 |
| AG-51 | 搜索框 | "Search experts" 实时过滤 |
| AG-52 | Expert 列表 | 14 个专家, 每个有: 图标 + 名称 + Prebuilt badge + 描述 |
| AG-53 | Checkbox 选择 | 多选, 可视化 selected/unselected |
| AG-54 | Read more 展开 | 内联展开显示 system_prompt + MCP servers |
| AG-55 | 选中计数 | footer: "X experts selected" |
| AG-56 | Cancel + Done 按钮 | 底部操作栏 |

### 4.3 New Agent 页

```
URL: /ai-studio/agents/new
```

| ID | 功能 | 详细规格 |
|----|------|---------|
| AG-60 | 面包屑 | Agents > New |
| AG-61 | 页面标题 | "Create an agent" |
| AG-62 | Start from scratch | 卡片: 标题 + 描述 + "Create agent" 按钮 |
| AG-63 | Use a template | 卡片: 标题 + 描述 + 搜索框 + 20 个模板 radio 列表 |
| AG-64 | 模板搜索 | 实时过滤模板列表 |
| AG-65 | 模板 radio | 每个模板: radio + 图标 + 标题 + 类别 badge + 描述 + expert 计数 |
| AG-66 | 右侧 Preview 面板 | 选中模板后显示: 标题/描述/类别/专家列表/system prompt 预览 |
| AG-67 | Credits 提示 | "Messaging an agent consumes credits" 信息条 |

### 4.4 Agent 运行

| ID | 功能 | 详细规格 |
|----|------|---------|
| AG-70 | POST /api/agents/{id}/run | 同步运行 agent |
| AG-71 | POST /api/agents/{id}/stream | 流式运行 agent (SSE/WebSocket) |
| AG-72 | LLM Planning | 自动规划 expert 调用顺序 (llm_plan / fixed_order / single_expert) |
| AG-73 | Expert Routing | 根据输入内容路由到最相关的 expert |

---

## 五、Speech To Text

```
URL: /ai-studio/speech-to-text
```

| ID | 功能 | 详细规格 |
|----|------|---------|
| ST-01 | 录音按钮 | 开始/停止录音 |
| ST-02 | 实时转录 | 录音过程中实时显示文本 |
| ST-03 | 文档模板选择 | 出院小结/入院记录/手术记录/会诊记录/护理记录 |
| ST-04 | 语言选择 | 中文/英文/混合 |
| ST-05 | 自定义命令 | 预设命令 (跳转段落/新段落/撤销/删除/标记) + 自定义 |
| ST-06 | 转录文本编辑 | 可手动编辑转录结果 |
| ST-07 | 导出 | 复制/下载转录文本 |
| ST-08 | Code tab | 4 种 SDK 格式 + 代码复制 |

---

## 六、Text Generation

```
URL: /ai-studio/text-generation
```

| ID | 功能 | 详细规格 |
|----|------|---------|
| TG-01 | 输入类型选择 | text / audio / file |
| TG-02 | 模板选择 | 11 个文书模板 (出院小结/入院记录/手术记录/会诊记录/护理记录/病程记录/转诊信/死亡记录/急诊记录/门诊记录/检查报告) |
| TG-03 | 输入框 | 自由文本输入 |
| TG-04 | 语言选择 | 中文/英文/丹麦语/多语言自动检测 |
| TG-05 | Generate 按钮 | 触发生成 |
| TG-06 | 输出区 | 生成的文书 + 复制/下载 |
| TG-07 | 模板分类 | 住院/门诊/急诊/文书/护理 |
| TG-08 | 样本载入 | 每个模板有预置样本 |

---

## 七、Medical Coding (Symphony)

```
URL: /ai-studio/medical-coding
品牌: Symphony for Medical Coding
```

| ID | 功能 | 详细规格 |
|----|------|---------|
| MC-01 | 输入区 | 自由文本 + 样本病例载入 |
| MC-02 | 编码系统选择 | 9 种 combobox: ICD-10-CM Outpatient / ICD-10-CM Inpatient / ICD-10-PCS / ICD-9-CM-3 / ICD-10-CN / CPT / HCPCS / SNOMED CT / ICD-11 |
| MC-03 | 运行按钮 | 执行编码 |
| MC-04 | 输出视图 | Rendered / JSON / Code 三视图切换 |
| MC-05 | 证据展示 | 每个编码关联证据文本 |
| MC-06 | 替代建议 | 替代编码选项 |
| MC-07 | 编码过滤 | Include/Exclude code 过滤器 |
| MC-08 | 置信度阈值 | 滑块控制 |
| MC-09 | 实时额度消耗 | 每次调用显示费用 |

---

## 八、Embedded Assistant

```
URL: /ai-studio/embedded-assistant
```

| ID | 功能 | 详细规格 |
|----|------|---------|
| EA-01 | 配置区 | 7 个 toggle 开关 (Speech-to-Text/Fact Extraction/Medical Coding/Text Generation等) |
| EA-02 | 实时预览 | 嵌入式助手外观预览 |
| EA-03 | 语言切换 | 界面语言 (EN/ZH/DA) |
| EA-04 | 主题颜色 | 预设颜色选择 |
| EA-05 | Guided Tour | 新用户引导流程 |
| EA-06 | Code tab | 嵌入代码 + 配置 JSON |

---

## 九、Fact Extraction

```
URL: /ai-studio/fact-extraction
```

| ID | 功能 | 详细规格 |
|----|------|---------|
| FE-01 | 输入区 | 文本输入 + 骨科/GP 样本 |
| FE-02 | 语言选择 | 中文/英文 |
| FE-03 | 提取结果 | 结构化 JSON 事实列表 |
| FE-04 | 每个事实 | 类型/值/证据/置信度 |

---

## 十、Developer Quickstart

```
URL: /developer-quickstart
```

| ID | 功能 | 详细规格 |
|----|------|---------|
| DQ-01 | Code with AI tools tab | 用 AI 工具构建应用的 prompt 模板 |
| DQ-02 | Step 1: 选择用例 | 4 个: Build dictation app / Build ambient scribe / Build medical coding app / Build clinical chat assistant |
| DQ-03 | Step 2: Prompt | 预写 AI coding agent prompt, 可复制 |
| DQ-04 | Step 2: AI 工具选择 | Claude Code (默认) / Cursor / Codex / Lovable |
| DQ-05 | Step 3: 凭据 | .env 格式凭据 + "Copy all as .env" 按钮 |
| DQ-06 | JS SDK tab | 传统 SDK 文档, 4 个 walkthrough guides |
| DQ-07 | .NET SDK tab | .NET 集成指南 |
| DQ-08 | API 文档链接 | → docs.corti.ai |

---

## 十一、管理功能

### 11.1 API Clients

| ID | 功能 | 详细规格 |
|----|------|---------|
| MG-01 | API Keys tab | 创建/列出/删除 API Key |
| MG-02 | OAuth Clients tab | 创建/列出 OAuth 客户端 |
| MG-03 | 显示 client_id + secret | 仅创建时显示完整 secret |
| MG-04 | 权限范围 | scopes 选择 |

### 11.2 Team

| ID | 功能 | 详细规格 |
|----|------|---------|
| MG-10 | 成员列表 | 成员名称/角色/状态 |
| MG-11 | 邀请成员 | email + role 邀请 |
| MG-12 | 角色管理 | Owner/Admin/Member/Coder 等 |

### 11.3 Billing

| ID | 功能 | 详细规格 |
|----|------|---------|
| MG-20 | 余额查看 | 当前信用余额 |
| MG-21 | 充值 | 手动添加信用额度 |
| MG-22 | 交易历史 | 消费/充值记录列表 |

### 11.4 Usage

| ID | 功能 | 详细规格 |
|----|------|---------|
| MG-30 | 用量摘要 | 总请求/消耗额度/平均响应时间 |
| MG-31 | 用量历史 | 按时间排序的使用记录 |
| MG-32 | Token 统计 | prompt/completion/total tokens |

### 11.5 Settings

| ID | 功能 | 详细规格 |
|----|------|---------|
| MG-40 | 个人资料 | 用户名/邮箱/全名 |
| MG-41 | 国家设置 | 21 个国家选项 |
| MG-42 | 安全护栏 | 6 个护栏 toggle (处方拦截/诊断免责/急诊拦截/可疑编码/PHI检测/屏蔽词) |
| MG-43 | 护栏启用/禁用 | 每个护栏独立 toggle |
| MG-44 | 保存按钮 | 持久化设置 |

---

## 十二、Corti 14 个 Expert 清单

| # | Expert 名称 | 类别 | 功能描述 |
|---|------------|------|---------|
| 1 | Medical Coding Expert (ICD-10-CM) | coding | 美国 ICD-10-CM 诊断编码 |
| 2 | Medical Coding Expert (ICD-10-PCS) | coding | 美国 ICD-10-PCS 住院手术编码 |
| 3 | Medical Coding Expert (ICD-10 WHO) | coding | 国际 ICD-10 诊断编码 |
| 4 | Medical Coding Expert (ICD-10 UK) | coding | 英国 ICD-10 诊断编码 |
| 5 | Medical Coding Expert (General) | coding | AI 辅助通用医学编码 |
| 6 | Memory | memory | 跨对话事实/偏好/上下文回忆 |
| 7 | POSOS | medication | 用药指导 (剂量/相互作用/禁忌) |
| 8 | Clinical Trials | search | 搜索临床试验/研究方案 |
| 9 | DrugBank | medication | 药品详细信息/药物相互作用 |
| 10 | PubMed | search | 生物医学文献搜索 |
| 11 | Web Search | search | 网络实时信息检索 |
| 12 | Medical Calculator | utility | 临床计算 (BMI/HbA1c/血糖) |
| 13 | Interviewing | interview | 引导用户完成结构化问卷 |
| 14 | ICD-10 Index Navigator | coding | 遍历 ICD-10 字母索引 |

---

## 十三、Corti 20 个 Agent 模板清单

| # | Agent 模板 | 类别 |
|---|-----------|------|
| 1 | ICD-10 Index Navigator Agent | 编码 |
| 2 | Rule Explainer Agent | 编码 |
| 3 | Compliance Guardrail Agent | 医保 |
| 4 | Code Validation Agent | 编码 |
| 5 | Procedure Entity Extractor Agent | 编码 |
| 6 | Diagnostic Entity Extractor Agent | 编码 |
| 7 | Surgical Registry Intelligence Agent | 质控 |
| 8 | ICU Admission Summary Agent | 文书 |
| 9 | Triage and Initial Assessment Agent | 急诊 |
| 10 | Note Completeness Agent | 质控 |
| 11 | Medication Reconciliation Agent | 药学 |
| 12 | Denial Appeals Agent | 医保 |
| 13 | Patient Discharge Education Agent | 护理 |
| 14 | Nursing Shift Handoff Agent | 护理 |
| 15 | Prior Authorization Agent | 医保 |
| 16 | Referral Generator Agent | 文书 |
| 17 | Clinical Education Agent | 教育 |
| 18 | Medical Coding Agent | 编码 |
| 19 | Clinical Guidelines Agent | 教育 |
| 20 | Clinical Documentation Improvement (CDI) Agent | 质控 |

---

## 十四、System Prompt 结构化标签规格

### 14.1 标签定义

```
<role>         — Agent 角色定义, 一句话说明 Agent 是做什么的
<output_format> — 输出结构, 必须包含:
                  - Markdown 表格模板 (| Field | Description | Status |)
                  - ## Section 结构
                  - Summary 行 (Total items / Quality / Confidence)
                  - Example Output 块 (完整的模拟输出)
<constraints>  — 4+ 条约束
                  - 不推断: "Do not infer diagnoses not documented"
                  - 不主观判断: "Base all assignments on documented evidence"
                  - 证据引用: "Every code must link to specific quoted text"
                  - 合规边界: "Do not output treatment recommendations"
<workflow>     — 7 步工作流
                  1. Synthesize — 综合所有文档
                  2. Extract — 提取所有诊断/手术
                  3. Assign ICD — 分配 ICD-10 诊断编码
                  4. Assign CPT — 分配手术编码
                  5. Validate — 验证编码一致性
                  6. Identify Gaps — 识别文书缺口
                  7. Flag Uncodable — 标记无法编码项
<required_configurations> — 前置条件
                  - 需要 coding system 选择
                  - 需要 encounter_type
<quality_standards> — 10 条质量标准
                  - Every code must link to specific quoted documentation
                  - No inferred codes without explicit evidence
                  - Codes must use maximum specificity
                  - Laterality must be specified when documented
                  - ...
```

### 14.2 Example Output 结构

```
## Encounter Summary
[2-3 句现实案例摘要]

## Analysis
| Finding | Evidence | Code | Status |
|---------|----------|------|--------|

## Assignment
### Primary
- Code / Description / Rationale

### Secondary
1. Code / Description / Evidence

## Gaps
- ⚠ Specific gap: missing info

## Unsupported Items
- ❌ Item: reason

## Validation Summary
- Total codes / Documentation quality / Compliance confidence
```

---

## 十五、技术架构特征

| 特征 | 规格 |
|------|------|
| 前端框架 | React + TypeScript (推测) |
| 导航模式 | React Router, 分组侧边栏 |
| 状态管理 | Zustand 或 Context |
| 实时通信 | WebSocket (STT 流式) |
| LLM 提供商 | 多模型 (通过 API) |
| 认证 | OAuth 2.0 + API Key |
| 样式方案 | Tailwind CSS 风格 |
| 设计系统 | 统一颜色/间距/圆角 |
| 图标库 | Lucide React |
| 字体 | DM Serif Display + JetBrains Mono + 系统字体 |

---

**图例**: [功能ID] 功能名称 — 详细描述
**按页面组织**: Product Hub → AI Studio → Agentic Framework → STT → Text Gen → Medical Coding → Embedded → Fact Extraction → Developer → Management → Experts → Templates
