# iCoDer v1 Agent Runtime Architecture RFC

**作者**: iCoDer 架构组
**日期**: 2026-06-20
**状态**: **Decided** (10 决策已拍板, 进入 Phase 1 spec 编写)
**范围**: iCoDer v1 Agent Runtime (Agent 编排 / Expert 装配 / 协议层 / 上下文 / 任务)
**级别**: 战略 RFC (非实现 spec; 详细 spec 在此 RFC 拍板后另写)

---

## 0. 文档目的

为 iCoDer v1 Agent Runtime 锁定**目标架构**与**迁移路径**,让"在 Corti Agentic Framework 100% 复刻架构 + 私有化 v1 取消 + iCoDer 域差异化保留"三件事对齐到一张图上。本 RFC 不写代码、不写 API 签名,只回答"是什么 / 为什么 / 怎么走"。

详细组件 spec (Orchestrator 内部状态机 / A2A JSON-RPC 消息体 / MCP 工具 schema / Context 数据模型) 在本 RFC 拍板后另起 spec 文件。

---

## 1. 背景与决定 (Context & Decision)

### 1.1 战略线索 (按时间倒序)

| 日期 | 事件 | 决定 |
|------|------|------|
| **2026-06-20** | 用户对前几轮"iCoDer-next `AgentExecutor` 是 Corti 风格"的修正 | **Agent 运行时目标架构 = 100% 复刻 Corti Agentic Framework** |
| 2026-06-19 | WIP 合并, 3 个 commit 完成 M3-0 backend 子集 | M3-0 验证通过(06-11 baseline), 进入 M-arch |
| 2026-06-17 | 战略转向 | v1 = 托管云; **私有化部署要求取消**; 全产品 frontend; 视觉近 1:1 Corti |
| 2026-06-14 | 原子能力架构拍板 | Agent = systemPrompt + experts; 路线二 = LLM 工具调用执行器 |
| 2026-06-13 | icoder-next 切片开工 | 0 依赖最小薄竖切验证 Corti 范式 |

### 1.2 用户原话

> "**完全 100% 复刻 corti 的架构,我觉得这才是值得学习的。**"

含义:
- "100% 复刻"指 **Agent 运行时架构**这一层(Orchestrator / Expert / 协议 / 上下文),不是产品视觉层(那一条已在 06-17 拍板为"近 1:1")
- "值得学习"指 Corti 在 healthcare 域是成熟范式(multi-agent 解耦调度、Expert 独立 LLM 可独立评测、A2A/MCP 协议标准化、Context 数据隔离是 PHI 合规前提),ReAct 单 Agent 范式把这一切压扁到一个 LLM 里, **撑不住编码/医保审计的多步决策+多源证据+多角色协作场景**

### 1.3 关键约束 (从战略线索中提取)

| 约束 | 出处 | 含义 |
|------|------|------|
| v1 = 托管云 (hosted cloud) | 06-17 pivot | 无私有化部署; 无"数据不出院"红线; 架构不需考虑院内网 / 离线 / 内网 LLM 场景 |
| 合规 = PHI 脱敏 + 全链路审计 + 证据回链 | 06-17 pivot | 替代旧"数据不出院"叙事; 但仍是核心,不能省 |
| production_writeback_blocked 恒 true | 硬红线 | 不写回 EMR/HIS 生产库 |
| 不接 B0 / 不做 SFT | 硬红线 | 不训练、不评估,Pipeline Validation ≠ 模型评估 |
| ICD-10-CN + ICD-9-CM-3 + CHS-DRG/DIP | 域约束 | Corti 没有这个 wedge, 是 iCoDer 保留的差异化层 |
| LLM 不绑定厂商 | env 可配 | base_url/model/key 全 env 可配; DeepSeek 仅默认端点 |
| 不可声明模型效果 | 验证红线 | pipeline validation 模式 ≠ 模型评估; B0 未接, 不声明 F1 |

### 1.4 iCoDer-next 切片定位调整 (Q10 决策: 保留)

| 资产 | 定位 |
|------|------|
| `icoder-next/backend/icoder/runtime/executor.py` (`AgentExecutor`) | **过渡形态**——ReAct 单 Agent 范式 (单 LLM + 函数工具 + MAX_ROUNDS + submit_findings), 让"atomic agent + LLM 调工具"概念先跑起来; **不是目标** |
| `icoder-next/backend/icoder/agents/*.py` (8 个原子 Agent) | 起步素材: AgentDefinition 声明式形态可参考; 实际能力建设按 Corti 范式重做 |
| `icoder-next/backend/icoder/experts/coding_expert.py` (4 工具 search/verify/guidelines/explore) | 起步素材: 工具清单可参考, 实现**改**为 Expert-as-LLM + MCP, 不是函数 |
| `icoder-next/backend/icoder/experts/compliance.py` (4 RuleSet) | 起步素材: RuleSet 分类 (medical_coding/drg_dip/insurance_audit/document_evidence) 命名与 iCoDer 既有 5 RuleSet 对齐 |
| `icoder-next/backend/icoder/experts/grouping_expert.py` (CHS-DRG/DIP) | 起步素材: DrgRoute.rationale 思路 (可解释 DRG 推导) 可保留 |
| `icoder-next/frontend/icoder-embedded.js` (Web Component) | **不迁移**——iCoDer 走 React 嵌入组件 (IcoderEvidenceViewer/ReviewPanel/TraceViewer), 战略层嵌入契约另写 |
| `icoder-next/frontend/llms.txt` + `.well-known/agent-skills/` | **目标态保留**——A2A 发现契约, 直接迁移到 iCoDer |
| **整个 `icoder-next/` 仓库** | **Q10 决策: 保留**——标记 "superseded by iCoDer v1 Agent Runtime Architecture RFC (2026-06-20)"; 26 tests 继续跑; 不再添加新功能; 新功能进 iCoDer 主仓按本 RFC 落地 |

**结论**: iCoDer-next 切片的所有**测试 + 业务素材 + 仓库本身**留下 (Q10), **架构范式不沿用** (本 RFC 重做)。

---

## 2. 目标 / 非目标 (Goals / Non-Goals)

### 2.1 Goals (本 RFC 拍板要做)

1. **G1**: 复刻 Corti Agentic Framework 的 **Orchestrator + Expert + A2A + MCP + Context + message:send + SSE + Task + Registry + Agent Card + Memory** 11 个核心组件
2. **G2**: 1 个端到端 Agent (推荐 `homepage-coding-review`) 走通 Corti 范式,作为后续 Agent 的参考实现
3. **G3**: iCoDer 域差异化 (ICD-10-CN/CM-3、CHS-DRG/DIP、6 域合规门禁、PHI 脱敏、审计、证据回链) 作为**架构之上的层**叠加, 不修改架构本身
4. **G4**: M3-0 验证基线 (06-11, 1227 tests) 保留, 不破坏
5. **G5**: iCoDer-next 切片的 8 原子 Agent / 4 RuleSet / 4 工具 coding-expert / 4 Agent Runner 概念沉淀到新架构中, 不重起炉灶

### 2.2 Non-Goals (本 RFC 明确不做)

1. **N1**: 不复制 Corti 商业模型 (PAYG 计费、计费 API、Stripe 集成等)
2. **N2**: 不复制 Corti 私有化部署 (v1 = 托管云, 私有化不在范围)
3. **N3**: 不复制境外编码体系 (ICD-10-CM/CPT/HCPCS 等); 保留 ICD-10-CN/ICD-9-CM-3
4. **N4**: 不引入 LangGraph / CrewAI / AutoGen 等第三方 Agent 框架 (用户拍板: 自建最小实现)
5. **N5**: 不接 B0 prediction / 不做 SFT / 不写训练数据 (验证红线)
6. **N6**: 不重写 M2a 14 阶段 Recorder (它是 audit / observability 层, 与 Agent 架构正交, 只在新 Agent 接入时按新规约调用)
7. **N7**: 不在 RFC 阶段定 API 签名 / JSON-RPC 消息体 / 数据库表结构 (留待详细 spec)

---

## 3. 目标架构: Corti Agentic Framework 100% 复刻

来源: `E:\Corti4C\Corti\llms-full.txt` (corti.ai docs 完整抓取, 2026-06-20)

### 3.1 总览

```
┌──────────────────────────────────────────────────────────────────┐
│                      客户端 / 第三方应用                          │
│           (HIS / EMR 门户 / iCoDer Frontend)                     │
└────────────┬─────────────────────────────────┬───────────────────┘
             │  A2A over HTTPS / SSE            │
             │  (POST /v1/message:send)         │
             ▼                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                    iCoDer v1 Agent Runtime                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Orchestrator  (中央 LLM 协调器, 调度不做事)                  │  │
│  │  - 接收 user request, 解析 task                              │  │
│  │  - 选择 Experts, 通过 A2A 委托子任务                          │  │
│  │  - 组合 Experts 返回, 生成最终答复                             │  │
│  └────┬─────────────────┬─────────────────┬───────────────────┘  │
│       │ A2A             │ A2A             │ A2A                 │
│       ▼                 ▼                 ▼                      │
│  ┌─────────┐      ┌─────────┐       ┌──────────┐                │
│  │ Expert  │      │ Expert  │       │  Expert  │                 │
│  │ 编码    │      │ DRG     │       │  文档    │                 │
│  │ (LLM)   │      │ (LLM)   │       │  (LLM)   │                 │
│  └────┬────┘      └────┬────┘       └────┬─────┘                │
│       │ MCP            │ MCP            │ MCP                    │
│       ▼                ▼                ▼                        │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  MCP Tools  (各 Expert 自己的工具集)                          │  │
│  │  coding-expert: search / verify / guidelines / explore /   │  │
│  │                 alternatives / submit_findings              │  │
│  │  drg-expert:    mdc / adrg / cc_level / dip / group        │  │
│  │  document-expert: standardize / draft / review              │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Context Manager  (服务端 contextId, 数据隔离)                │  │
│  │  Memory Service   (context + memory chunks 持久化)           │  │
│  │  Expert Registry  (专家可发现 + 元数据)                      │  │
│  │  Agent Card       (`/.well-known/agent.json`)               │  │
│  │  Task Service     (长任务 taskId 生命周期)                   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  横向:  PHI 脱敏层 / 审计层 / 证据回链层 / M2a Run Trace Recorder │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 11 核心组件 (逐一)

#### 3.2.1 Orchestrator (中央协调器)

**Corti 定义**: 接收用户请求, 推理"要做什么", 委托给对应的 Experts。**不**做具体活, **只**调度与组合。

**iCoDer 现状**: ❌ 不存在。`agent_runner.py` 是单 Agent 一次性执行, 不是协调器 (且 Q5 决策后不保留)。

**目标形态 (Q1 决策: 自建, 达到 Corti 生产级)**:
- 自身也是一个 LLM (system prompt 设定"你是协调器, 不做事只调度")
- 输入: 用户的 `message:send` 请求 (A2A 协议体)
- 输出: 多 Expert 子任务委托 (A2A JSON-RPC) + 组合 Experts 结果
- 内部状态机: **生产级实现** (不是临时脚本)
  - 状态: `received` → `planning` → `delegating` → `aggregating` → `completed` / `failed`
  - 错误处理: Expert 失败重试 (默认 2 次) / 优雅降级 / 整体失败回滚
  - 可观测性: 每个状态切换记入 M2aRecorder stage + 暴露 Prometheus 指标
  - 单元测试: 状态转移全覆盖 + 错误路径全覆盖
  - 集成测试: 与 M2aRecorder / LLMGateway / Expert Registry 联动验证
- 协议层: A2A 0.3 兼容 (Q2 决策), 不写 iCoDer 私有扩展
- 与 M2a 14 阶段 Recorder 集成 (每个委托动作记入 stage)

**iCoDer 差异化叠加**: Orchestrator 的 system prompt 注入"PHI 已脱敏 / 不要在答复中回显 PHI / production_writeback_blocked=true"。

#### 3.2.2 Expert (LLM sub-agent)

**Corti 定义**: **本身也是 LLM** (不是 Python 函数), 接受 Orchestrator 委托, 通过 MCP 协议调工具, 返回子结论。每个 Expert 独立可评测。

**iCoDer 现状**: ⚠ `coding_expert.py` / `drg_expert.py` 是 **Python 函数** (`search()`, `verify()`, `mdc_of()` 等), 不是 sub-agent。这是**最大架构差距**。

**目标形态 (Q7 决策: 独立 + 可共享)**:
- **独立** = 每个 Expert 拥有自己的完整配置:
  - `system_prompt` (Expert 角色设定)
  - `tools[]` (MCP 工具声明, 各自不同)
  - `model` (Expert 自己的 LLM model 配置: `deepseek-v4-flash` / `mock` / 等)
  - `non_goals` (Expert 明确不做什么)
  - `output_contract` (Expert 输出的结构契约)
  - 第三方可独立注册新 Expert (Registry 暴露)
- **可共享** = 多个 Expert 可共用同一 LLM 实例 (LLMGateway infra 复用):
  - LLMGateway 是 infra 层 (进程级, 单例)
  - Expert 是配置层 (每个 Expert 注册时声明自己用哪个 model, 但调用时都走同一个 Gateway)
  - 调用时: Gateway 收到 `system_prompt + messages + tools` 三个参数, Expert 自己的 system_prompt 必注入, 不会被 LLM 调用覆盖
- 每个 Expert = `AgentDefinition(system_prompt + tools[] + non_goals + output_contract)` 元数据
- 工具通过 MCP 协议声明, 不内嵌到 Python 函数
- 接受委托时, Expert 自己再调工具 (递归, 子工具调用) → 返回 Markdown 结构化子结论
- Expert 之间**不直接通信**, 全部经 Orchestrator
- 第三方可通过 Registry 注册 Expert (Q7 实现要点)

**iCoDer 差异化叠加**:
- 编码类 Expert 的 system prompt 注入"ICD-10-CN/ICD-9-CM-3 + CHS-DRG/DIP" 域知识
- 工具结果通过 `M2a Run Trace` 记入 stage
- Expert 注册时, 必声明 `production_writeback_blocked=true` (Q5 决策下, 旧路径全替换, 新 Expert 必带此约束)

#### 3.2.3 A2A Protocol (Agent-to-Agent)

**Corti 定义**: Agent ↔ Agent 通信协议。客户端↔Corti 用, Expert↔Orchestrator 用, Expert↔Expert (间接) 用。A2A 是标准协议, 不是 iCoDer 自造。

**iCoDer 现状**: ❌ 不存在。Orchestrator/Expert/Client 全部走内部 Python 函数调用。

**目标形态**:
- iCoDer 内部 A2A: JSON-RPC over HTTP, 自建最小实现 (用户拍板: 不引入第三方 Agent 框架)
- 外部 A2A (Client → iCoDer): `POST /agents/{id}/v1/message:send`, 接受 `TextPart` / `DataPart` / `interactionId`
- 协议版本: 跟 Corti 0.3 (latest stable) 对齐
- 不实现**完整 A2A spec** (含 push notifications / auth extensions), 只实现 iCoDer 需要的子集 (详细 spec 阶段定)

#### 3.2.4 MCP Protocol (Model Context Protocol)

**Corti 定义**: Expert ↔ 工具通信协议 (JSON-RPC, stdio 或 HTTP)。Expert 通过 MCP 调外部工具 (ICD 字典 / 编码指南 / DRG 分组器等)。

**iCoDer 现状**: ❌ 不存在。Expert 工具以 Python 函数直接调用, 没有协议层。

**目标形态**:
- 工具以 MCP server 形式暴露 (stdio 本地进程 或 HTTP)
- iCoDer 既有 ICD 字典 / BGE-M3 FAISS / 编码指南 KB / DRG 分组器 全部包成 MCP server
- Expert 调工具通过 JSON-RPC 调用, 不直接 import Python 模块
- 协议版本: MCP 2025-03-26 (latest stable)

**好处**:
- 工具**可独立部署** (远程 MCP server)
- 工具**可独立评测** (调工具的 LLM step 单独打点)
- 工具**可外部贡献** (第三方 ISV 提供 MCP server, 通过 Registry 注册)

#### 3.2.5 Context Manager

**Corti 定义**: `contextId` 服务端生成, **严格数据隔离** (跨 context 永不泄漏)。一个 context = 一次用户会话/任务的生命周期。

**iCoDer 现状**: ⚠ 有 `session_id` / `run_id` (M2aRecorder 生成), 但**没有 context 抽象**, 没有"多 context 隔离"语义, 也没有"context 关联 interactionId"。Q4 决策后, 隔离力度直接对齐 Corti。

**目标形态 (Q4 决策: 隔离力度与 Corti 对齐)**:
- **服务端生成 `contextId` (UUID v4)**, 客户端**不能**自己生成 (防止 ID collision / 数据串)
- **跨 contextId 完全隔离** (Q4 拍板):
  - 数据隔离: 跨 context 永不泄漏 messages / artifacts / 工具结果
  - 状态隔离: 跨 context 状态独立 (一个 context 的中间态不污染另一个)
  - 缓存隔离: 跨 context 缓存不共享 (避免 PHI 串)
- 同一 contextId 内: messages + tasks + artifacts + memory chunks 共享
- 生命周期: contextId 从 `message:send` 接收时创建, 到 task 完成 / cancel / 超时销毁
- iCoDer 既有 `M2aRecorder` 接入到 contextId (一次推理 = 一个 stage 序列, 挂在 contextId 下)
- 现有 `session_id` 退化为 `contextId` 的一部分 (或直接重命名)
- **Q8 决策落地**: Context 只存短期 (当前会话 messages / 当前 task 状态); 跨会话事实不存 Context, 走 Memory (见 3.2.11)

#### 3.2.6 message:send Endpoint

**Corti 定义**: `POST /agents/{id}/v1/message:send` 端点。接受 `TextPart` + `DataPart` + 可选 `interactionId`, 返回 `Task` (长任务) 或 `Message` (短任务)。

**iCoDer 现状**: ❌ 没有等价端点。`/api/runtime/medical-coding/test` 是私有端点, 不符合 A2A 协议。

**目标形态**:
- 路径: `POST /api/icoder/agents/{agent_id}/v1/message:send`
- 请求体: A2A spec 兼容 (`message.parts: TextPart|DataPart`, `message.contextId` 可选, `message.interactionId` 可选)
- 响应: 短任务 = `Message`, 长任务 = `Task` (含 `taskId` 用于后续轮询)
- 内部: Orchestrator 接收 → 选 Experts → A2A 委托 → 组合 → 返回

#### 3.2.7 SSE Streaming

**Corti 定义**: 实时增量事件 (用于 ambient notes / live guidance)。客户端开 SSE 长连接, 服务端持续推 `message.delta` / `task.status` 事件。

**iCoDer 现状**: ❌ 没有 SSE, 只有 Request/Response。

**目标形态**:
- 端点: `POST /api/icoder/agents/{agent_id}/v1/message:stream` (SSE variant)
- 事件类型: `message.start` / `message.delta` / `message.complete` / `task.status.changed` / `expert.delegated` / `tool.called` / `tool.returned`
- iCoDer 差异化: 事件流包含 `phi_redacted: true` 标记, 客户端**强制**不允许渲染原始文本

#### 3.2.8 Long-running Tasks (Task Service)

**Corti 定义**: 长任务 = 异步执行 + `taskId` 轮询。任务生命周期: `submitted` → `working` → `input-required` / `completed` / `failed` / `canceled`。

**iCoDer 现状**: ❌ 没有 task 抽象, 只有 run_id (一次性同步执行)。

**目标形态**:
- 长任务 (生成完整审核报告 / 复杂编码决策) 返回 `Task` 而非 `Message`
- `GET /api/icoder/tasks/{task_id}` 客户端轮询状态
- `POST /api/icoder/tasks/{task_id}/cancel` 客户端取消
- 状态机: `submitted` → `working` → `completed` (或 `failed` / `canceled`)
- iCoDer 差异化: `task.audit` 字段 (M2aRecorder 完整 14 阶段 trace)

#### 3.2.9 Expert Registry

**Corti 定义**: 专家可发现注册表 (`GET /agents/list-registry-experts`)。每个 Expert 有 metadata (capabilities / description / configuration)。

**iCoDer 现状**: ⚠ `default_expert_registry()` 是内部 dict, 不可发现。

**目标形态**:
- `GET /api/icoder/experts` 列出所有注册 Expert
- `GET /api/icoder/experts/{expert_id}` 单个 Expert 元数据
- 第三方 ISV 可通过 MCP server 注册新 Expert
- iCoDer 既有 (medical_coding / drg_dip / insurance_audit / document_evidence / charge_compliance / audit) 6 域 Expert 全部注册

#### 3.2.10 Agent Card

**Corti 定义**: `/.well-known/agent.json` 暴露 Agent 元数据 (capabilities / experts / rule_sets / non_goals / output_contract), A2A 发现契约。

**iCoDer 现状**: ⚠ `.icoder/agent_registry.json` 是内部注册表, 没有公开发现端点。

**目标形态**:
- `GET /.well-known/agent.json` 公开当前 Agent 列表 + 元数据
- `GET /agents/{agent_id}/card` 单 Agent 详细 card
- `GET /llms.txt` LLM 可读的 Agent 描述 (LLM 友好格式)
- 格式: A2A spec `AgentCard` schema

#### 3.2.11 Memory

**Corti 定义**: `context` (会话级) + `memory chunks` (语义检索)。`TextPart` 直接进 LLM, `DataPart` 自动索引进 memory, semantic retrieval 触发时取出。

**iCoDer 现状**: ❌ 没有 memory 抽象。

**目标形态 (Q8 决策: 短期存 Context, 长期存 Memory)**:
- **Context** (短期, 3.2.5 已定义) = 当前会话的 messages + 当前 task 状态
  - 存储: SQLite (短期表, 自动 expire)
  - 范围: 当前 contextId 生命周期内
- **Memory** (长期, 本节) = 跨会话的事实 / 患者 / 编码历史
  - 存储: BGE-M3 embedding + FAISS (Phase 5 实现)
  - 范围: 跨 contextId, 跨会话
  - 触发: semantic retrieval 命中时从 Memory 取出, 注入到 Context
- 实现: 短期走 SQLite (现有), 中期走 embedding + FAISS (BGE-M3 已部署, 复用)
- iCoDer 差异化: `memory.kind` 枚举 (`patient` / `encounter` / `code_history` / `feedback`), 与编码域语义对齐
- **边界原则 (Q8 落地)**:
  - 跨 contextId **不通过 Context 共享**, 必走 Memory semantic retrieval
  - 同一 contextId 内**优先 Context**, 避免重复 retrieval
  - Memory chunk 入库: 显式声明 `kind` + `redact_level` (Q4 PHI 隔离)

### 3.3 协议版本锁定

| 协议 | 目标版本 | 备注 |
|------|----------|------|
| A2A Protocol | 0.3 (latest stable @ 2026-06-20) | 实现子集, 不是全 spec |
| MCP Protocol | 2025-03-26 (latest stable) | 完整实现, stdio + HTTP 两种 transport |
| A2A Discovery (Agent Card) | 0.3 `AgentCard` schema | 与 A2A 协议版本对齐 |

详细协议子集在 spec 阶段定 (本 RFC 不展开 JSON-RPC 消息体)。

---

## 4. iCoDer 域差异化叠加层 (架构之上)

Corti 没有, iCoDer 保留 (按 06-17 pivot 与战略线索):

### 4.1 编码体系

| 体系 | Corti | iCoDer |
|------|-------|--------|
| 诊断 | ICD-10-CM (美国) | **ICD-10-CN** (国标临床版) |
| 手术 | CPT (美国) | **ICD-9-CM-3** (中国) |
| 分组 | MS-DRG (美国) | **CHS-DRG** (中国) + **DIP** (按病种分值) |

**实现位置**:
- ICD 字典 / 编码指南 / 易错码表: 全部以 **MCP server** 形式暴露 (3.2.4)
- 编码类 Expert 的 system prompt 注入域知识
- 37,897 码 `icd10cn_code_catalog.json` 资产从 `E:\iCoDerA\` 走只读 MCP server

### 4.2 合规门禁 (6 RuleSet)

按 CLAUDE.md 既有 5 RuleSet + 1 audit:

| RuleSet | 严重度 | 触发场景 |
|---------|--------|----------|
| `medical_coding` | Critical + Moderate | 编码证据回链 / 目录成员 / 高风险易错码 (5 PRIORITY: I66.901 / J98.414 / M80.900 / 45.1600x001 / Z51.102) / 主诊断必填 |
| `drg_dip` | Moderate + Informational | 无主诊断无法入组 / ADRG 落歧义 / CC/MCC 候选待确认 / DIP 目录缺失 |
| `insurance_audit` | Moderate | 外科组医保支付资质 / 候选手术改变结算路径 |
| `charge_compliance` | Moderate | 收费项与编码映射 / 自费项目标记 |
| `document_evidence` | Moderate | 主诊断病历证据锚点 / 手术记录支撑 |
| `audit` | Informational | production_writeback_blocked 始终 true / 审计日志全量 |

**实现位置**:
- RuleSet 作为 Expert (`compliance-expert` 父 Expert 下 6 子 Expert, 或 1 个 Expert 配 6 RuleSet 配置)
- 通过 A2A 由 Orchestrator 按 Agent 声明的 `rule_sets` 选择性调用

### 4.3 PHI 脱敏 + 全链路审计 + 证据回链

| 层 | 实现位置 |
|----|----------|
| PHI 脱敏 | Orchestrator **第一步** (LLM 只见 redacted text, 与 icoder-next executor 一致) |
| 全链路审计 | M2a 14 阶段 Recorder (M3-0 已实现, 不动) + AuditLog 表 |
| 证据回链 | 编码 Expert 工具链产出 `EvidenceSpan(char_start, char_end, doc_id, doc_type)`, 落 18 节 HTML 报告 |

### 4.4 不变硬红线 (从 CLAUDE.md 1:1 复制)

- `production_writeback_blocked = true` 恒定
- 不接 EMR/HIS 生产写回
- 不接 B0 prediction
- 不做 SFT / 不出训练数据
- 不编造模型预测 (pipeline validation ≠ 模型评估)
- LLM 不绑定厂商 (env 可配, DeepSeek 默认)

---

## 5. 当前 iCoDer 状态 → 目标态 映射

| 组件 | iCoDer 当前 | 目标态 | 差距 | 备注 |
|------|-------------|--------|------|------|
| Orchestrator | ❌ 不存在 | LLM 中央协调器 | 全建 | 新增 `icoder/agent_runtime/orchestrator/` |
| Expert (LLM) | ⚠ Python 函数 | LLM sub-agent | 全部重构 | `coding_expert.py` / `drg_expert.py` 改 LLM + MCP |
| A2A | ❌ 不存在 | JSON-RPC 协议 | 全建 | 新增 `icoder/agent_runtime/a2a/` |
| MCP | ❌ 不存在 | MCP server 协议 | 全建 | 新增 `icoder/agent_runtime/mcp/` + 各域 MCP server |
| Context | ⚠ `session_id` (M2a) | `contextId` 服务端生成 | 重构 | 现有 session_id 退化为 contextId |
| message:send | ❌ 不存在 | A2A 端点 | 全建 | 新增路由 |
| SSE | ❌ 不存在 | 实时流 | 全建 | 新增 streaming 路由 |
| Task Service | ❌ 不存在 | 任务生命周期 | 全建 | 新增 `icoder/agent_runtime/tasks/` |
| Expert Registry | ⚠ 内部 dict | 公开可发现 | 公开化 | 现有 registry 暴露 API |
| Agent Card | ⚠ 内部 json 文件 | 公开端点 | 公开化 | 现有 `agent_registry.json` 暴露 |
| Memory | ❌ 不存在 | context + chunks | 全建 | 短期 SQLite + 中期 BGE-M3 + FAISS |
| RuleEngine | ✅ 5 RuleSet (medical_coding 已实, 其余预留) | 6 RuleSet | 补 4 (drg_dip/insurance_audit/document_evidence/charge_compliance) | iCoDer-next 切片有现成实现可参考 |
| coding-expert 4 工具 | ⚠ Python 函数 | LLM + MCP 工具 | 重构 | 工具语义保留, 实现改 LLM 调 MCP |
| DRG 分组器 | ✅ 已有 | Expert-as-LLM + MCP | 包成 MCP | 不动逻辑, 只换调用方式 |
| M2a Recorder | ✅ 14 阶段 | 不变 | 0 | 与架构正交, 接入新规约 |
| LLM Gateway | ✅ 4 provider (DeepSeek/Mock/Prompt/OpenAI) | 不变 | 0 | 与架构正交 |
| RBAC | ✅ 5 角色 (admin/coder/medical_insurance_reviewer/it_operator/auditor) | 不变 | 0 | A2A 端点复用 |

---

## 6. 迁移阶段 (Migration Phases)

> **原则**: 不一步到位。每阶段都跑通, 都有测试, 都不破坏 M3-0 baseline (1227 tests)。

### Phase 0: Spec (本 RFC) ← **当前**

- 拍板 11 组件 + 域差异化叠加
- 锁定 A2A / MCP 协议版本
- 拍板 iCoDer-next 切片定位

### Phase 1: Orchestrator + 1 Agent 端到端 (最小可走通, Q9 决策: 直接用 DeepSeek 真实 LLM)

**目标**: 1 个 Agent (推荐 `homepage-coding-review`) 端到端走通 Corti 范式。**直接接 DeepSeek 真实 LLM 接口, 不走 Mock**。

**范围**:
- Orchestrator (最小生产级: 接收 message → 选 Expert → 委托 → 组合 → 返回)
- 1 Expert: `coding-expert` (LLM sub-agent + 4 工具 MCP)
- 1 Agent: `homepage-coding-review` (orchestrator + coding-expert 组合)
- 协议: A2A / MCP 最小子集 (本阶段只支持 `TextPart`, 不实现 `DataPart` / `interactionId` / SSE)
- 端点: `POST /api/icoder/agents/homepage-coding-review/v1/message:send` (Request/Response, 不开 SSE)
- Context: 服务端生成 contextId, 接到 M2aRecorder
- LLM: **DeepSeek 真实接口** (走既有 LLMGateway, env 注入 key, `ICODER_CREDENTIAL_LLM`)

**Q9 决策影响 (W6 触发)**:
- Phase 1 dev/test 阶段需准备 DeepSeek API key (已有, 走 `ICODER_CREDENTIAL_LLM` 用户环境变量)
- 不写 mock 兜底; 如果 DeepSeek 不可用, Phase 1 失败 = 整体失败, 不"自动降级到 mock"
- e2e test 走真实 LLM 调用, 端到端时延 / 真实响应作为 Phase 1 验证基准

**不做的**: 6 RuleSet 全跑通; SSE; 长任务; Memory; Registry 公开; Agent Card 公开。

**成功标准**:
- 1 条病历 → Orchestrator 委托 → coding-expert 调 search/verify/guidelines → submit_findings → 返回 codes + candidates + 证据 (**真实 DeepSeek 调用**)
- A2A `POST /v1/message:send` 端点可被 curl 调用, 返回 A2A 兼容 JSON
- 1 个 MCP server (coding-expert 工具) 可独立启动, 接受 JSON-RPC
- M3-0 1227 tests 不破坏
- 新增 ≥20 单元测试 + 1 e2e test (走真实 LLM)
- 旧 AgentRunner 的 5 个 API 路由加 deprecation header + 重定向到 A2A 端点 (Q5 决策)

### Phase 2: 6 RuleSet + 6 Expert + RuleEngine 集成

**目标**: 把 iCoDer 既有 6 RuleSet 全部跑通, 作为 `compliance-expert` 暴露。

**范围**:
- 6 子 Expert: `medical_coding` / `drg_dip` / `insurance_audit` / `document_evidence` / `charge_compliance` / `audit`
- 每个 Expert 接对应 RuleSet
- Orchestrator 按 Agent 声明的 `rule_sets` 选择性委托
- 高风险易错码 5 PRIORITY 强制人工复核

**成功标准**:
- 5 PRIORITY 码 (I66.901 / J98.414 / M80.900 / 45.1600x001 / Z51.102) 全部走通
- `production_writeback_blocked = true` 5 处验证 (response / audit_log / report §17 / UI / embed)

### Phase 3: 8 原子 Agent 逐个 Corti 化 (Q6 决策: 逐个迁移 + 每个端到端验证)

**目标**: icoder-next 切片的 8 原子 Agent 全部按 Corti 范式重做。**逐个迁移, 每迁移完一个 Agent 立即端到端验证, 验证通过才进下一个**。

**8 个 sub-phase (顺序可调, 但每个 sub-phase 必须独立闭环)**:

| Sub-phase | Agent | Experts | 端到端验证样本 |
|-----------|-------|---------|--------------|
| **3.1** | `homepage-coding-review` | orchestrator + coding-expert + compliance-expert + drg-expert | 1 条真实病历 (急性心梗) → Orchestrator 委托 → 4 个 Expert 返回 → 合并报告 |
| **3.2** | `code-validation` | coding-expert | 1 条已有编码的病历 → 调 search/verify/guidelines → 给出 PASS/WARNING/FAIL |
| **3.3** | `compliance-guardrail` | compliance-expert (6 RuleSet 全跑) | 1 条高风险病历 (含 5 PRIORITY 码之一) → 全部 RuleSet 触发 → 报告 |
| **3.4** | `document-standardization` | document-expert (新增) | 1 份非标准病历 → 标准化 → 与原文档 diff |
| **3.5** | `drg-grouping-review` | drg-expert + compliance-expert | 1 条病历 → CHS-DRG 入组 + DIP 路径 → 解释 rationale |
| **3.6** | `fact-extraction` | coding-expert (只抽取) | 1 条病历 → 抽取疾病 + 证据 (不编码) → 输出 EvidenceSpan 列表 |
| **3.7** | `index-navigation` | coding-expert (只查目录) | 1 个查询 → ICD 字典检索 → top-20 候选 |
| **3.8** | `revenue-compliance-review` | insurance-expert + drg-expert | 1 条病历 + 收费项 → 合规审计 + DRG 路径 → 报告 |

**每个 sub-phase 的硬性闭环 (W4 触发)**:
1. AgentDefinition 声明 (system_prompt + tools[] + non_goals + output_contract)
2. 切到新架构 (Orchestrator + Expert-as-LLM + MCP tools)
3. e2e test: 1 条真实样本走通 (有 input / output 对照)
4. 验证: M3-0 baseline (1227 tests) 全绿 + 该 Agent 自身 ≥10 单元测试
5. 单独 PR, 验证通过才合并

**Sub-phase 顺序可调, 但不允许跳过端到端验证就进下一个**。

**Phase 3 整体成功标准**:
- 8 原子 Agent 全部注册 + Agent Card 公开
- 每个 Agent ≥10 单元测试 + 1 e2e
- 8 e2e test 全绿 (每 sub-phase 1 个)

### Phase 4: Registry + Agent Card 公开 + A2A Discovery

**目标**: 第三方 ISV 可发现 / 可调用 / 可注册 Expert。

**范围**:
- `GET /api/icoder/experts` 列表
- `GET /api/icoder/experts/{expert_id}` 详情
- `GET /.well-known/agent.json` 全 Agent 列表
- `GET /agents/{agent_id}/card` 单 Agent card
- `GET /llms.txt` LLM 友好描述
- 第三方 ISV 通过 MCP server 注册 Expert

**成功标准**:
- 1 个 mock 第三方 Expert 走通注册 + 发现 + 委托

### Phase 5: SSE + 长任务 + Memory

**目标**: 实时流式 + 长任务异步 + 跨会话记忆。

**范围**:
- SSE 端点 + 7 种事件类型
- Task Service + taskId 轮询 + cancel
- Memory Service (BGE-M3 + FAISS) + `memory.kind` 5 类

**成功标准**:
- 1 条病历长任务 (生成完整审核报告) SSE 推流
- Memory 跨会话: 上次会话的"高风险患者"在本次会话中 semantic retrieval 出来

### Phase 6: Memory + 8 原子 + 多 Orchestrator (可选)

**目标**: 多 Orchestrator 协作 (按业务域拆分), 全部 8 原子 Agent 走通完整 pipeline。

**范围**:
- 多个 Orchestrator (如: `coding-orchestrator` / `clinical-orchestrator` / `revenue-orchestrator`)
- Orchestrator 间通过 A2A 互相委托
- Memory 跨 Orchestrator 共享

---

## 7. iCoDer-next 切片处理方案 (Q10 决策: 保留整个仓库)

| 资产 | 处理 |
|------|------|
| **`icoder-next/` 整个仓库** | **Q10 决策: 保留**, 标注 "superseded by iCoDer v1 Agent Runtime Architecture RFC (2026-06-20)"; 仓库 README 加 deprecation notice |
| `icoder-next/backend/icoder/runtime/executor.py` | **保留为参考**, 不再添加新功能; 未来可作为 `AgentExecutor` 的"agent-as-tool" 简化模式供简单 Expert 用 |
| `icoder-next/backend/icoder/agents/*.py` (8 原子 Agent) | **AgentDefinition 模板可复用**, 实际 Expert 实现按 Phase 1-3 重做 |
| `icoder-next/backend/icoder/experts/coding_expert.py` | **4 工具语义保留**, 改实现: Python 函数 → LLM 调 MCP |
| `icoder-next/backend/icoder/experts/compliance.py` | **6 RuleSet 语义保留**, 改实现: 函数 → Expert-as-LLM |
| `icoder-next/backend/icoder/experts/grouping_expert.py` | **DrgRoute.rationale 保留**, 改实现: 工具 → MCP server |
| `icoder-next/backend/icoder/runtime/registry.py` | **AgentDefinition 模式可复用** |
| `icoder-next/backend/icoder/runtime/types.py` | **pydantic v2 数据模型可复用** |
| `icoder-next/frontend/icoder-embedded.js` | **不迁移**——iCoDer 走 React 嵌入组件 |
| `icoder-next/frontend/llms.txt` + `.well-known/` | **目标态保留**, 迁移到 iCoDer |
| `icoder-next/frontend/dist/` | **不迁移** |
| `icoder-next/docs/EMBED_CONTRACT.md` | **参考**, 嵌入契约按 iCoDer 既有 React 组件改写 |
| `icoder-next/backend/tests/` (26 tests) | **保留**, 作为新架构测试的种子 |

**结论**: icoder-next 切片 80% 沉淀到新架构, 20% (前端 + 嵌入契约 + 范式选择) 不沿用。**整个仓库保留** (Q10), 不合并/不删除, 仅标记 superseded。

---

## 8. iCoDer 差异化保留清单 (Not In Corti)

| 差异化 | 实现位置 | 优先级 |
|--------|----------|--------|
| ICD-10-CN (诊断) | coding-expert 工具 + MCP | P0 |
| ICD-9-CM-3 (手术) | coding-expert 工具 + MCP | P0 |
| CHS-DRG (分组) | drg-expert 工具 + MCP | P0 |
| DIP (按病种分值) | drg-expert 工具 + MCP | P0 |
| 高风险易错码 5 PRIORITY | medical_coding RuleSet | P0 |
| 6 域合规 RuleSet | compliance-expert 6 子 Expert | P0 |
| PHI 脱敏层 | Orchestrator 第一步 + 各 Expert 第一步 | P0 |
| 全链路审计 (14 阶段) | M2aRecorder (已有) | P0 |
| 证据回链 (char-span) | EvidenceSpan 数据结构 + 18 节报告 | P0 |
| `production_writeback_blocked` 硬阻断 | audit RuleSet | P0 |
| 5 角色 RBAC | 既有 (admin/coder/medical_insurance_reviewer/it_operator/auditor) | P0 |
| DeepSeek 默认 + env 可配 LLM | 既有 LLMGateway | P0 |
| 字符级证据偏移 (char_start/char_end) | EvidenceSpan 数据结构 | P1 |
| 14 阶段 Run Trace | M2aRecorder 既有 | P1 |
| 编码 human-review (5 动作: accept/reject/modify/insufficient_evidence/escalate) | m2a human_review 子模块 | P1 |
| 18 节 HTML 报告 | coding_review_report.py | P1 |
| i18n (zh-CN / en-US) | 既有 locales.ts | P2 |
| MedCodER 5 阶段管线 (BGE-M3 + FAISS) | MedCodER pipeline 既有 | P2 |

---

## 9. 已拍板决策 (10 Decisions, 2026-06-20)

| # | 决策点 | 拍板 | 影响 |
|---|--------|------|------|
| **Q1** | Orchestrator 内部状态机实现 | **自建, 达到 Corti 生产级** | Orchestrator 视为产品级模块, 不是临时脚本; 需单元测试 + 集成测试 + 错误处理 + 可观测性全到位 |
| **Q2** | A2A 协议版本 | **与 Corti 对齐** (v0.3 latest stable @ 2026-06-20) | 协议消息体 / 错误码 / 端点路径全跟 Corti 走, 不自造私有扩展 |
| **Q3** | MCP 协议 | **与 Corti 对齐** (2025-03-26 latest stable) | 工具声明 / JSON-RPC / transport 全跟 MCP spec 走 |
| **Q4** | Context 数据隔离力度 | **与 Corti 对齐** (跨 context 完全隔离, 服务端 contextId) | 隔离语义: 跨 contextId 永不泄漏数据/状态/缓存; 比 iCoDer 现有 session_id 强 |
| **Q5** | 既有 iCoDer `AgentRunner` (one-shot) 处置 | **不保留** (clean replace) | 旧 AgentRunner 不做 fallback 兼容路径; 新架构 100% 替代, 旧 API 路由直接重定向到 A2A 端点 |
| **Q6** | 8 原子 Agent 迁移策略 | **逐个迁移, 每个迁移完都做端到端验证** | Phase 3 拆成 8 个 sub-phase (3.1-3.8), 每 sub-phase: 迁移该 Agent → e2e test (1 条真实病历走通) → 验证通过才进下一 sub-phase |
| **Q7** | Expert 与 LLM 关系 | **独立 + 可共享** | "独立" = 每个 Expert 拥有自己的 `system_prompt` / `tools[]` / `model` / `non_goals` / `output_contract` 配置; "可共享" = 多个 Expert 可共用同一 LLM 实例 (LLMGateway 复用), 但**调用时** Expert 自己的 system_prompt 必注入 |
| **Q8** | Context vs Memory 边界 | **同意: 短期存 Context, 长期存 Memory** | Context = 当前会话 messages (SQLite 短期); Memory = 跨会话 facts (BGE-M3 + FAISS 中期) |
| **Q9** | Phase 1 端到端验证用 LLM | **直接用 DeepSeek 真实 LLM 接口** | 不经过 Mock 阶段; Phase 1 跑通就接 DeepSeek API, 用既有 LLMGateway (env 可配) |
| **Q10** | iCoDer-next 切片仓库处置 | **保留** (作为过渡形态参考) | 仓库保留, 标注 "superseded by v1 arch RFC 2026-06-20"; 26 tests 继续跑; 不再添加新功能 |

### 9.1 决策间一致性检查

| 检查项 | 结果 |
|--------|------|
| Q5 (不保留 AgentRunner) vs Q9 (直接用 DeepSeek) | 一致: 旧路径全替换, 新路径直接走真实 LLM, 不留 mock 兜底 |
| Q6 (逐个迁移+端到端) vs Q9 (直接 DeepSeek) | 一致: 每个 Agent 端到端验证 = 真实 LLM 调用 + 真实病历 + 真实工具 |
| Q1 (Orchestrator 生产级) vs Q2/Q3 (协议对齐) | 一致: Orchestrator 内部状态机 = 生产级实现, 协议层 = 标准 A2A/MCP |
| Q4 (Context 隔离) vs Q8 (Context/Memory 边界) | 一致: Context = 服务端生成 + 严格隔离 (会话级); Memory = 跨会话 (跨 Context 检索) |
| Q7 (Expert 独立可共享) vs 既有 LLMGateway | 一致: LLMGateway 是 infra 层 (共享); Expert 是配置层 (独立) |

### 9.2 决策触发的额外工作项

- **W1** (Q1 触发): Orchestrator 状态机需 spec + 实现 + 测试, 建议直接生成 `ICODER_V1_ORCHESTRATOR_SPEC.md`
- **W2** (Q2/Q3 触发): 6 个详细 spec 全部按对齐 Corti 写, 不写"iCoDer 私有扩展"
- **W3** (Q5 触发): 旧 AgentRunner 的 5 个 API 路由 (`/api/runtime/medical-coding/test` 等) 全部加 deprecation header + 重定向到 A2A 端点, 给客户 1 个 release cycle 迁移
- **W4** (Q6 触发): Phase 3 拆 sub-phase, 每个 sub-phase 单独 PR + e2e test
- **W5** (Q7 触发): Expert metadata 暴露 `model` 字段 (公开可发现, 第三方可注册), 避免 LLM 调用时隐式覆盖 system_prompt
- **W6** (Q9 触发): Phase 1 dev/test 阶段需准备 DeepSeek API key, 走既有 env 注入 (`ICODER_CREDENTIAL_LLM` 用户环境变量)

---

## 10. 成功标准 (Success Criteria)

### 10.1 Phase 1 完成后 (Q1/Q5/Q6/Q9 综合验收)

1. ✅ 1 条病历 → Orchestrator 委托 → coding-expert 调 4 MCP 工具 → submit_findings → 返回 codes + candidates + 证据 (**真实 DeepSeek 调用**, Q9)
2. ✅ A2A `POST /v1/message:send` 端点可被 curl 调用, 返回 A2A 兼容 JSON
3. ✅ 1 个 MCP server (coding-expert 工具) 可独立启动, 接受 JSON-RPC
4. ✅ M3-0 1227 tests 不破坏
5. ✅ 新增 ≥20 单元测试 + 1 e2e test (走真实 LLM)
6. ✅ iCoDer-next 切片的 26 tests 可继续独立跑通 (作为参考实现, Q10)
7. ✅ **Orchestrator 生产级** (Q1): 状态转移 + 错误路径 + 重试 + 降级 + 可观测性 + 单元测试全覆盖
8. ✅ **旧 AgentRunner 5 个 API 路由加 deprecation header + 重定向到 A2A 端点** (Q5)

### 10.2 v1 完成时

1. ✅ 11 个 Corti 核心组件全部实现 (A2A v0.3 + MCP 2025-03-26 协议对齐, Q2/Q3)
2. ✅ 8 原子 Agent 全部按 Corti 范式落地 (**逐个迁移 + 每个端到端验证**, Q6)
3. ✅ 第三方 ISV 可注册 Expert + 可发现 (Q7: Expert 独立可共享)
4. ✅ PHI 脱敏 + 审计 + 证据回链 三件套全链路验证
5. ✅ **Context 跨 contextId 完全隔离** (Q4) + **Memory 跨会话语义检索** (Q8)
6. ✅ M3-0 baseline + 6 Phase 测试全绿
7. ✅ 文档完整 (RFC + 6 spec + 8 Agent 各自 README)
8. ✅ 旧 AgentRunner 代码完全移除 (Q5 决定, 客户已迁移到 A2A 端点)

---

## 11. 参考 (Reference)

### 11.1 Corti 官方文档

- `E:\Corti4C\Corti\llms-full.txt` (corti.ai docs 完整抓取, 2026-06-20)
  - `/agentic/architecture` - 多 Agent 架构总览
  - `/agentic/orchestrator` - Orchestrator 角色
  - `/agentic/experts` - Expert 抽象
  - `/agentic/a2a-protocol` - A2A 协议
  - `/agentic/mcp-protocol` - MCP 协议
  - `/agentic/context-memory` - Context & Memory
  - `/agentic/agents/send-message-to-agent` - message:send 端点
  - `/agentic/faq` - Orchestrator vs Expert / A2A vs MCP / Task vs Message

### 11.2 iCoDer 既有文档

- `E:\Corti4C\CLAUDE.md` - iCoDer 总架构 (Runtime Core / Compliance Services / Agent Packs / Workbenches)
- `E:\Corti4C\docs\ICODER_CURRENT_PRODUCT_STATUS_SUMMARY.md` - (注: 06-11 后未更新)
- `E:\Corti4C\docs\M3_PRODUCT_E2E_VALIDATION_REPORT.md` - M3-0 验证 (06-11)
- `E:\Corti4C\docs\ICODER_M3_SECURITY_AND_AUDIT_SPEC.md` - 安全审计 spec
- `E:\Corti4C\docs\M3_HOMEPAGE_CODING_REVIEW_AGENT_SPEC.md` - homepage-coding-review spec
- `E:\Corti4C\backend\docs\M3_AGENT_PRODUCTIZATION_PRECHECK.md` - M3-0 预检

### 11.3 iCoDer-next 切片 (过渡形态)

- `E:\Corti4C\icoder-next\README.md` - 切片 README
- `E:\Corti4C\icoder-next\docs\EMBED_CONTRACT.md` - 嵌入契约 (参考)
- `E:\Corti4C\icoder-next\backend\icoder\runtime\executor.py` - AgentExecutor (ReAct 范式, 过渡)
- `E:\Corti4C\icoder-next\backend\icoder\experts\coding_expert.py` - 4 工具 coding-expert (工具语义保留)
- `E:\Corti4C\icoder-next\backend\icoder\experts\compliance.py` - 4 RuleSet (语义保留)
- `E:\Corti4C\icoder-next\backend\icoder\runtime\registry.py` - AgentDefinition 模式

### 11.4 战略线索

- 2026-06-20 拍板: 100% 复刻 Corti Agent 架构 (本 RFC)
- 2026-06-17 战略转向: v1=托管云 / 私有化取消 / 全产品 frontend / 近 1:1 Corti 视觉
- 2026-06-14 原子能力架构: Agent=systemPrompt+experts / 路线二=LLM 工具调用执行器
- 2026-06-13 icoder-next 切片开工

---

## 12. 签字 (Decided 2026-06-20)

| 角色 | 签字 | 日期 |
|------|------|------|
| 架构组 | ✅ 决策已拍板 (Q1-Q10) | 2026-06-20 |
| 产品 | ✅ 100% Corti 复刻方向确认 | 2026-06-20 |
| 工程 owner | ✅ Phase 1 起跑 (Orchestrator + homepage-coding-review + DeepSeek 真实调用) | 2026-06-20 |
| 安全/合规 | ✅ Context 隔离 + PHI 脱敏 + 审计 三件套对齐 Corti | 2026-06-20 |

**RFC 状态**: Decided (10 决策已落入 RFC 第 9 节 + 反射到 3.2/5/6/7/10 各节)

**下一步 (W1 触发)**:
1. 进入 Phase 1 详细 spec 编写, 顺序: Orchestrator → A2A → MCP → Context → Task → Agent Card (6 spec)
2. 详细 spec 拍板后, 起 Phase 1 实现
3. Phase 1 完成 (Q9: 真实 DeepSeek 端到端) 后, 走 Phase 2-3 迁移 (Q6: 逐个 + 每个端到端)

---

**本 RFC 拍板完成 (Decided 2026-06-20), 接下来另起 6 个详细 spec** (按 W1 触发顺序):
1. `ICODER_V1_ORCHESTRATOR_SPEC.md` - Orchestrator 状态机 (Q1 生产级) + prompt + 接口
2. `ICODER_V1_A2A_SPEC.md` - A2A v0.3 (Q2 协议对齐) JSON-RPC 消息体 + 端点
3. `ICODER_V1_MCP_SPEC.md` - MCP 2025-03-26 (Q3 协议对齐) 工具 schema + transport
4. `ICODER_V1_CONTEXT_SPEC.md` - contextId 数据模型 + 隔离语义 (Q4 隔离力度对齐 Corti + Q8 Context/Memory 边界)
5. `ICODER_V1_TASK_SPEC.md` - Task Service 状态机 + 轮询/cancel 接口
6. `ICODER_V1_AGENT_CARD_SPEC.md` - Agent Card schema + A2A Discovery (Q7 Expert 独立可共享 metadata)

**Spec 拍板后, Phase 1 实现起跑**:
- 端到端目标: 1 条病历走通 Orchestrator + coding-expert (Expert-as-LLM) + 4 MCP 工具 + 真实 DeepSeek (Q9) + A2A 端点
- 旧 AgentRunner 5 个 API 路由加 deprecation header + 重定向 (Q5)
- 1227 tests 不破坏 + 新增 ≥20 单元测试 + 1 e2e test
- 完成 = Phase 1 进入 Phase 2 (6 RuleSet 全跑通)
