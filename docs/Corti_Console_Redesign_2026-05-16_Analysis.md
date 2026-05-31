# Corti Console 2026-05-16 产品重设计实测分析

**日期**: 2026-05-16
**方法**: headless browser 实测 (已登录 console.corti.app, account: Luhua Song)
**对比基线**: `Corti_vs_iCoDer_Complete_Comparison.md` (2026-05-15)

---

## 一、核心发现: Corti 已从 "AI Feature Console" 进化为 "Agent 平台"

Corti Console 进行了全面的产品重设计, 核心变化是将定位从"多个 AI 功能的控制台"升级为**统一 Agent 平台的产品中枢**。

### 重设计前后对比

| 维度 | 旧版 (2026-05-15 之前) | 新版 (2026-05-16 实测) |
|------|----------------------|----------------------|
| 首页定位 | Dashbaord (信用余额+图表) | **Product Hub** (4 产品 tab 展示) |
| 导航结构 | 平铺链接 | **分组导航**: Home/DQ → AI Studio → Manage → Support |
| Agent 定位 | "Agent 聊天测试" | **"Agentic Framework"** — 构建医疗 Agent 的平台 |
| 首页内容 | 余额表+使用图 | 4 产品卡片(tab) + Explorer/Inspector/Configurator 三段 |
| 开发者引导 | SDK tab | **"Code with AI tools"** — 给 Claude Code/Cursor/Codex 的 prompt |
| 新页面 | — | **AI Studio Overview** — 6 能力卡片 |
| Overview | 无 | 有 (`/ai-studio-overview`) — 但实测 404 |
| Medical Coding | 无品牌名 | **"Symphony for Medical Coding"** 品牌 |
| Expert 数量 | ~13 | **14** (新增 POSOS/Clinical Trials/Interviewing) |
| 文档链接 | docs.corti.ai | **docs.corti.ai/agentic/**overview |

---

## 二、首页 4 产品 Tab 详细分析

首页现在有 4 个 tab, 每个代表一个核心产品:

### Tab 1: Transcribe (Speech To Text)
```
描述: "Capture conversation in real time for ambient scribes 
       and clinical-grade dictation applications"
CTA: "Try Speech to Text" → /ai-studio/speech-to-text
副链: "Start recording" + "Build a dictation app" + Developer quickstart
```

### Tab 2: Document (Text Generation)
```
描述: "Turn transcripts, facts, or data into clinical documentation 
       — tailored to your format, specialty, and language"
CTA: "Try Text Generation" → /ai-studio/text-generation
副链: "AI Studio" + "Build an ambient scribe"
```

### Tab 3: Chat (Agentic Framework) ★ 核心新定位
```
描述: "Build advanced AI agents that perform high-quality 
       clinical and operational tasks"
CTA: "Try the Agentic Framework" → /ai-studio/agents
副链: "AI Studio" + "Build a clinical chat assistant"
```
**关键**: Corti 正式将 Agent 能力命名为 "Agentic Framework", 而非简单的 "Agent Chat"。

### Tab 4: Code NEW (Medical Coding / Symphony)
```
描述: "Convert unstructured clinical text into structured medical 
       codes for revenue cycle management and more"
CTA: "Try Symphony for Medical Coding" → /ai-studio/medical-coding
副链: "AI Studio" + "Build a medical coding app"
```
**关键**: Medical Coding 产品被品牌化为 "Symphony"。

---

## 三、AI Studio Overview — 全新平台门户页

URL: `/ai-studio-overview` (实测返回 404, 但导航中有链接)

设计结构:
```
┌──────────────────────────────────────────────┐
│  AI Studio Overview                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Explore  │ │ Inspect  │ │  Configure   │ │
│  │ Build    │ │ Debug w/ │ │ Fine tune    │ │
│  │ agents,  │ │ events   │ │ settings,    │ │
│  │ transcr, │ │inspector,│ │ copy code    │ │
│  │ docs...  │ │monitor $ │ │ into app     │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
│                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Agents   │ │Speech To │ │Text Gen      │ │
│  │Customize │ │ Text     │ │Turn transcrs │ │
│  │w/experts │ │Stream    │ │→struct notes │ │
│  │[Explore] │ │audio...  │ │[Explore][Doc]│ │
│  │[Docs]    │ │[Expl][Doc]│ │              │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │Embedded  │ │Fact Extr │ │Medical Code  │ │
│  │Assistant │ │Extract   │ │Convert text  │ │
│  │Configure │ │facts...  │ │→struct codes │ │
│  │[Expl][Doc]│[Expl][Doc]│ │[Expl][Doc]   │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
│                                              │
│  "Ready to dive into code?"                  │
│  [Developer quickstart]                      │
└──────────────────────────────────────────────┘
```

**6 个能力卡片**, 每个都有 "Explore" 和 "Docs" 链接。

---

## 四、Agentic Framework 详细分析

### 4.1 Agents 列表页 (`/ai-studio/agents`)

```
头文: "Build healthcare agents to take action across your systems"
按钮: [New Agent]
Tabs: My agents | Pre-built agents
过滤: Find an agent (搜索) + Created by (下拉) + Open filter menu
卡片: ICD-10 Index Navigator Agent (09-May-2026)
      Medical Coding Agent (05-May-2026)
Live Cost: $0.000000 (实时显示)
```

### 4.2 Agent 详情页 (`/ai-studio/agents/{uuid}`)

这是 Agent 平台的核心。左侧 Chat 测试, 右侧 Settings/Code 双 tab。

**Settings tab:**
- **Name**: 20/50 字符限制
- **System Prompt**: 结构化的 XML 标签 prompt:
  - `<role>` — agent 角色定义
  - `<output_format>` — 输出结构(含 Markdown 表格模板 + Example Output)
  - `<constraints>` — 约束(不推断、不主观判断、证据引用等)
  - `<workflow>` — 7 步工作流(Synthesize→Extract→Assign ICD→Assign CPT→Validate→Identify Gaps→Flag Uncodable)
  - `<required_configurations>` — 前置条件检查
  - `<quality_standards>` — 10 条质量标准
- **Experts**: 5 个已绑定 expert (Coding/Pubmed/Web Search/Medical Calculator/Memory)
- **[Browse Expert Library]** — 打开 expert 选择器
- **[Add expert]** — 添加自定义 expert
- **Pinned message parts** — 可折叠

**Code tab (SDK):**
```javascript
const agent = await cortiClient.agents.create({
  name: "Medical Coding Agent",
  experts: [
    { name: "coding-expert", type: "reference" },
    { name: "pubmed-expert", type: "reference" },
    ...
  ],
  systemPrompt: "<role>...</role>...",
});
const result = await cortiClient.agents.messageSend(agentId, {
  message: { role: "user", parts: [{ text: "", kind: "text" }] }
});
```
自动填充当前 UI 配置 — 真正的 "Configure → Copy Code" 闭环。

### 4.3 Expert Library (弹窗)

**14 个专家:**

| 专家 | 描述 |
|------|------|
| Medical Coding Expert (ICD-10-CM) | 美国标准 ICD-10-CM 诊断编码 |
| Medical Coding Expert (ICD-10-PCS) | 美国标准 ICD-10-PCS 住院手术编码 |
| Medical Coding Expert (ICD-10 WHO) | 国际 ICD-10 诊断编码 |
| Medical Coding Expert (ICD-10 UK) | 英国标准 ICD-10 诊断编码 |
| Medical Coding Expert (General) | AI 辅助通用医学编码 |
| Memory | 跨对话事实/偏好/上下文回忆 |
| POSOS ★ 新增 | 用药指导(剂量/相互作用/禁忌) |
| Clinical Trials ★ 新增 | 搜索临床试验/研究方案 |
| DrugBank | 药品详细信息/药物相互作用 |
| PubMed | 生物医学文献搜索 |
| Web Search | 网络实时信息检索 |
| Medical Calculator | 临床计算(BMI/HbA1c/血糖) |
| Interviewing ★ 新增 | 引导用户完成结构化问卷 |

每个 card 有 "Read more" 链接 + 复选框。底部 "Cancel" + "Done"。

### 4.4 New Agent 页 (`/ai-studio/agents/new`)

简洁的两选一:
- **Start from scratch**: "Configure your agent from the ground up" → Create agent
- **Use a template**: "Start with a pre-configured agent" + 搜索
- 底部: "Messaging an agent consumes credits"

---

## 五、Developer Quickstart — "Code with AI tools" (重大创新)

### 新 Tab: Code with AI tools

这是 Corti 最具前瞻性的新功能:

**Step 1 — Select your use case** (4 个):
- Build a dictation app
- Build an ambient scribe
- Build a medical coding app
- Build a clinical chat assistant

**Step 2 — Prompt your coding agent**:
预写的 AI coding agent prompt, 一键复制到:
- **Claude Code** (默认)
- Cursor
- Codex
- Lovable

**Step 3 — Copy credentials into your app**:
.env 格式凭据 + "Copy all as .env variables" 按钮

这是 **"用 AI 工具来构建 AI 应用"** 的元模式 — Corti 不只是提供 API, 还给 AI coding agent 提供 prompt template。

### 传统 SDK tab (JavaScript / .NET)

4 个 walkthrough guides, 包含了新的 "Get started with the Corti Agentic Framework" 指南。

---

## 六、与 iCoDer 的差距影响分析

Corti 这次重设计对 iCoDer 差距清单的影响:

### 扩大差距 (iCoDer 需追赶)

| 新能力 | Corti 现状 | iCoDer 现状 | 优先级 |
|--------|-----------|------------|--------|
| **Agentic Framework** | 完整 agent 创建/管理/测试/模板/SDK | AgentRunner + ExpertRegistry | **P0 NEW** |
| **Expert Library (14个)** | 浏览/搜索/Read more/勾选/Done | 无 Expert 浏览器 | **P0 NEW** |
| **System Prompt 结构化** | XML 标签 + Example Output + 7步workflow | 无 | **P0** (已有) |
| **Code with AI tools** | 4 use case × 4 AI tool 的 prompt | 无 | **P1 NEW** |
| **4 产品 Tab 首页** | Transcribe/Document/Chat/Code | 无产品中枢 | **P1 NEW** |
| **AI Studio Overview** | 6 能力卡片 + Explorer/Inspector/Configurator | 无 | **P2 NEW** |
| **Symphony 品牌** | Medical Coding = "Symphony" | 无产品品牌 | **P2** |
| **POSOS/Clinical Trials/Interviewing** | 3 个新 Expert | 无对应 | P2 |
| **SDK agent.create() 代码生成** | 自动填充当前 UI 配置 | 无 | P1 (已有) |

### iCoDer 仍保持的独有优势

| 功能 | 说明 |
|------|------|
| 多码表管理 (4套编码字典+跨表映射) | Corti 有9种编码系统但无跨表映射 |
| 金标准评估 (CSV导入+批量+指标) | Clinical evaluation pipeline |
| 人工审核工作台 (逐编码确认/驳回) | CaseReviewPage 四面板 |
| LLM 主诊断选择 (Corti风格prompt) | acute admission > chronic, .9降权 |
| 规则库浏览+测试沙盒 | 15条中文编码规则 |
| 6种角色权限系统 | Corti 仅 owner 一种 |

---

## 七、iCoDer 新差距清单 (追加)

### P0 NEW — Agent Platform 核心

| # | 差距 | 描述 |
|---|------|------|
| N-P0-1 | **Agent 模板系统** | Corti: 模板选择器 + 搜索; iCoDer: 无 |
| N-P0-2 | **Expert Library 浏览器** | Corti: 14 专家 + Read more + 搜索; iCoDer: 无浏览器 |
| N-P0-3 | **Agent SDK 代码生成** | Corti: `cortiClient.agents.create({experts, systemPrompt})` 自动填充 |
| N-P0-4 | **System Prompt 结构化**(<role>/<output_format>/<workflow>/<quality_standards> + Example Output) | iCoDer: EditSystemPromptModal 有基础 XML 标签但缺模板结构 |

### P1 NEW — 产品平台化

| # | 差距 | 描述 |
|---|------|------|
| N-P1-1 | **产品首页 4 Tab** | Corti: Transcribe/Document/Chat/Code + hero + CTA; iCoDer: Dashboard |
| N-P1-2 | **"Code with AI tools" tab** | Corti: 4 use case prompt 给 Claude Code/Cursor/Codex/Lovable |
| N-P1-3 | **AI Studio Overview** | Corti: 6 能力卡片; iCoDer: 无 (P2-1 已修复但可对其 design) |
| N-P1-4 | **Documentation 侧边栏** | Corti: 全局右侧 auth/guides/api/sdk/help; iCoDer: 无 |

### P2 NEW — 品牌 & 体验

| # | 差距 | 描述 |
|---|------|------|
| N-P2-1 | **产品品牌命名** | Corti: "Symphony", "Agentic Framework"; iCoDer: 无品牌 |
| N-P2-2 | **POSOS 用药指导 Expert** | Corti 新增; iCoDer 无 |
| N-P2-3 | **Clinical Trials Expert** | Corti 新增; iCoDer 无 |
| N-P2-4 | **Interviewing Expert** | Corti 新增; iCoDer 无 |

---

## 八、总结

Corti 这次重设计的核心信号是:

1. **从 "AI feature vendor" 到 "Agent platform"** — Agentic Framework 是定位核心
2. **从 "single-player console" 到 "developer platform"** — Code with AI tools 面向 AI 时代的开发者
3. **从 "tools for humans" 到 "tools for humans via AI agents"** — Claude Code/Cursor prompt 模板说明 Corti 默认开发者用 AI 写代码
4. **从 "无品牌" 到 "产品品牌"** — Symphony for Medical Coding 品牌化

对 iCoDer 而言:
- 产品首页需要从 Dashboard 升级为 Product Hub (4 tab 或类似)
- Agent 系统需要 Expert Library 浏览器 + 模板系统 + SDK 代码生成
- 可以考虑 "Code with AI tools" tab (给 Claude Code 写好的 prompt)
- 但 iCoDer 的 Clinical Pipeline (金标准评估+人工审核+主诊断推理) 仍然是差异化优势
