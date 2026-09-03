# iCoDer v1 Orchestrator Spec

**作者**: iCoDer 架构组
**日期**: 2026-06-20
**状态**: Draft (待审, Phase 1 spec 之一)
**范围**: iCoDer v1 Orchestrator 内部实现 (状态机 / 接口 / prompt / 错误处理 / 可观测性)
**前置**: `ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20)
**后续 spec**: A2A / MCP / Context / Task / Agent Card (本 spec 拍板后按 W1 顺序起)

---

## 0. 文档目的

把 RFC 第 3.2.1 节"Orchestrator"和 Q1 决策（自建, 达到 Corti 生产级）展开成**可实现的详细 spec**: 状态机的状态/转移/触发条件、与 A2A/M2aRecorder/Expert Registry 的接口契约、System Prompt 模板、错误处理策略、可观测性指标、测试矩阵、iCoDer 差异化叠加。

本 spec 不写代码 (留给 Phase 1 实施), 但**所有可写错的地方都钉死**: 状态名、prompt 注入点、错误码、metric 名、test 数量。

---

## 1. 背景与决定

### 1.1 上游决定 (从 RFC 来)

| 决策 | 拍板 | 对本 spec 的影响 |
|------|------|------------------|
| **Q1** Orchestrator 自建, 达到 Corti 生产级 | RFC 第 9 节 | 本 spec 必须覆盖生产级质量要求 (错误处理/可观测性/测试), 不写临时脚本 |
| **Q2** A2A 协议版本对齐 Corti (v0.3) | RFC 第 9 节 | Orchestrator 与 Expert 之间的 JSON-RPC 消息体 = A2A v0.3 spec, 不写 iCoDer 私有扩展 |
| **Q4** Context 隔离对齐 Corti | RFC 第 9 节 | Orchestrator 必须**服务端生成 contextId**, 不接受客户端传入 |
| **Q5** 旧 `AgentRunner` 不保留, clean replace | RFC 第 9 节 | Orchestrator = 新引擎, 不写 fallback 兼容旧 AgentRunner |
| **Q7** Expert 独立 + 可共享 | RFC 第 9 节 | Orchestrator 调用 Expert 时, Expert 自己的 system_prompt 必注入, 不被 LLM 调用覆盖 |
| **Q8** 短期存 Context, 长期存 Memory | RFC 第 9 节 | Orchestrator 只读/写 Context (短期), 不直写 Memory (Phase 5 才接) |
| **Q9** Phase 1 直接用 DeepSeek 真实 LLM | RFC 第 9 节 | Orchestrator 的 planning LLM call 走真实 DeepSeek (走 LLMGateway), 不走 Mock |

### 1.2 关键边界 (从 RFC 1.3 + 4.4 来)

- `production_writeback_blocked = true` 恒定 (Orchestrator system prompt 必带)
- PHI 脱敏 = Orchestrator 第一步 (system prompt 注入说明)
- 不接 EMR/HIS 生产写回 (Orchestrator 暴露的"可写动作" = 0)
- LLM 不绑定厂商 (LLMGateway 是 env 可配的, Orchestrator 通过 gateway 调用)

### 1.3 与其他 5 spec 的关系

```
ICODER_V1_ORCHESTRATOR_SPEC (本 spec, 基础)
    ↓ 依赖
ICODER_V1_A2A_SPEC (Orchestrator 与 Expert 之间的 JSON-RPC 协议)
ICODER_V1_CONTEXT_SPEC (Orchestrator 生成/管理 contextId)
ICODER_V1_TASK_SPEC (Orchestrator 创建/管理 Task 对象)
    ↓ 不依赖 Orchestrator
ICODER_V1_MCP_SPEC (Expert ↔ 工具, Orchestrator 不直连)
ICODER_V1_AGENT_CARD_SPEC (Registry 公开, Orchestrator 从 Registry 读 Agent metadata)
```

**关键**: Orchestrator spec 拍板后, A2A/Context/Task spec 才能写 (因为它们定义 Orchestrator 的接口契约); MCP/Agent Card spec 可并行写。

---

## 2. 目标 / 非目标 (Goals / Non-Goals)

### 2.1 Goals (本 spec 必须达成)

1. **G1**: Orchestrator 内部状态机生产级 (状态/转移/触发/错误全覆盖)
2. **G2**: Orchestrator 与 A2A 0.3 协议对齐 (入站 `message:send` / 出站 `Expert` 委托)
3. **G3**: Orchestrator 与 M2aRecorder 14 阶段集成 (每个状态切换/每次 Expert 委托记入 stage)
4. **G4**: Orchestrator 暴露的指标满足生产级可观测性 (Prometheus 5+ 指标)
5. **G5**: Orchestrator 实现 PHI 脱敏 + production_writeback_blocked 强制 (system prompt 注入)
6. **G6**: Orchestrator 不做编码/分组/审计的具体活, 全部委托给 Expert
7. **G7**: Orchestrator 的 planning LLM 走真实 DeepSeek (Q9), 不走 Mock
8. **G8**: Orchestrator 单元测试 + 集成测试 + e2e test 矩阵明确 (在第 9 节)

### 2.2 Non-Goals (本 spec 明确不做)

1. **N1**: 不实现 A2A spec 全集 (push notifications / auth extensions / multi-tenancy extensions 等) — Phase 4/5/6 之后才考虑
2. **N2**: 不实现 SSE 实时流 (Phase 5 才做, 本 spec 只产出 `Message` / `Task` 对象, 不开 SSE)
3. **N3**: 不实现长任务 cancel 语义 (Phase 5 Task spec 细化, 本 spec 只支持短任务 = `Message` 返回)
4. **N4**: 不实现 Memory semantic retrieval (Phase 5, 本 spec 只读写 Context)
5. **N5**: 不实现 Expert Registry 公开 API (Phase 4, 本 spec 从内部 Registry dict 读 Agent metadata)
6. **N6**: 不实现 Agent Card 公开 (Phase 4, 本 spec 只生成 Agent Definition 内部表示)
7. **N7**: 不实现多 Orchestrator 协作 (Phase 6, 本 spec 是单 Orchestrator)
8. **N8**: 不写 8 原子 Agent 的具体业务 (Phase 3, 本 spec 只 Orchestrator 自身 + Phase 1 用 1 Agent)
9. **N9**: 不实现 Orchestrator 持久化 (状态机 in-memory + M2aRecorder 记录即可, DB 持久化留 Phase 6)

---

## 3. 架构总览

### 3.1 内部组件

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Orchestrator (单进程, in-memory)                  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              Inbound: A2A message:send Handler                  │  │
│  │  - 接收 A2A spec 兼容请求体                                      │  │
│  │  - 服务端生成 contextId (UUID v4)                                │  │
│  │  - 校验 agent_id 存在, 加载 AgentDefinition                     │  │
│  │  - 第一步 PHI 脱敏 (注入 redacted text 到 Context)               │  │
│  │  - 启动 State Machine                                            │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              State Machine (核心, Q1 生产级)                     │  │
│  │                                                                  │  │
│  │   received → planning → delegating → aggregating → completed   │  │
│  │       │           │           │            │            │       │  │
│  │       └─failed────┴────failed──┴────failed──┴────failed──┘       │  │
│  │                                                                  │  │
│  │   事件: user_input / plan_generated / expert_invoked /           │  │
│  │         expert_returned / aggregation_done / error / timeout    │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              Planner (LLM 推理, 调度)                            │  │
│  │  - 输入: context.messages + Agent.definition                    │  │
│  │  - 输出: structured Plan (JSON: expert[] + tool_constraints)     │  │
│  │  - LLM: 真实 DeepSeek via LLMGateway (Q9)                       │  │
│  │  - Prompt: 见第 6 节 (含 PHI 脱敏 + production_writeback_blocked)│  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              Delegator (A2A 客户端, 出站)                        │  │
│  │  - 输入: Plan.expert[]                                          │  │
│  │  - 行为: 对每个 Expert 发起 A2A JSON-RPC 调用                    │  │
│  │  - 协议: A2A 0.3 (见 ICODER_V1_A2A_SPEC)                       │  │
│  │  - 并发: Phase 1 顺序 (简单可调试); 后续 Phase 优化为并行         │  │
│  │  - 错误: 重试 2 次 + 指数退避; 失败时记录并继续或 abort          │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              Aggregator (结果组合)                                │  │
│  │  - 输入: Plan + Experts 返回的子结论                              │  │
│  │  - 行为: 拼接/去重/冲突解决, 生成最终 A2A Message                │  │
│  │  - 冲突解决策略: 见第 7 节                                        │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              M2aRecorder 适配器 (审计)                            │  │
│  │  - 每次状态切换: recorder.stage(state_name)                      │  │
│  │  - 每次 Expert 委托: recorder.stage(expert_invocation)           │  │
│  │  - 关键决策 (Plan 生成): recorder.stage(plan_generated)          │  │
│  │  - 顶层 run: recorder.inference(agent_ref=...)                  │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 数据流 (1 条病历 1 次完整跑通)

```
1. Client → POST /api/icoder/agents/{id}/v1/message:send
   { message: { parts: [TextPart|DataPart], contextId?: ..., interactionId?: ... } }

2. Inbound Handler:
   - 首轮生成 contextId = uuid4()；续轮接收 transport 已验证的服务端 contextId
   - 加载 AgentDefinition from Registry
   - 提取 message.parts → 文本
   - PHI 脱敏: 替换姓名/身份证/电话/地址 → <REDACTED:NAME> 等
   - 启动 State Machine (state = received)
   - Context 写入: { contextId, messages: [redacted_text], agent_id, ... }

3. State Machine → planning:
   - Planner 调 LLM (DeepSeek): 输入 redacted text + AgentDefinition
   - LLM 返回 Plan: { experts: [{ expert_id, input, priority }], reason }
   - 状态切换: planning → delegating
   - Recorder: stage("plan_generated", plan)

4. State Machine → delegating:
   - 对每个 Expert 顺序发起 A2A 调用 (Phase 1 顺序)
   - Expert 返回: { expert_id, output, evidence, confidence }
   - 错误: 重试 2 次 → 失败 → skip + 标记 expert_failed (见第 7 节)
   - Recorder: stage("expert_invoked", expert_ref) + stage("expert_returned", result)

5. State Machine → aggregating:
   - 组合 Expert 输出
   - 冲突解决 (见 7.x)
   - 生成最终 Message
   - Recorder: stage("aggregated", message)

6. State Machine → completed:
   - 返回 A2A Message 响应
   - recorder.inference context manager 退出
   - metrics: orchestrator_runs_total{status="success"}++
```

---

## 4. 状态机 (核心 - Q1 生产级)

### 4.1 状态定义

| 状态 | 含义 | 入口事件 | 出口事件 |
|------|------|----------|----------|
| **`received`** | Inbound handler 已接收请求, contextId 已生成, PHI 脱敏完成 | inbound_request_validated | phi_redacted / inbound_invalid |
| **`planning`** | Planner LLM 正在生成 Plan | phi_redacted | plan_generated / plan_failed / planning_timeout |
| **`delegating`** | Delegator 正在调用 Expert(s) | plan_generated | all_experts_returned / critical_expert_failed / delegating_timeout |
| **`aggregating`** | Aggregator 正在组合 Expert 输出 | all_experts_returned | aggregated / aggregation_failed |
| **`completed`** | 全部成功, Message 已生成 | aggregated | (终态) |
| **`failed`** | 任何阶段失败, 整体失败 | *_failed / *_timeout | (终态) |

### 4.2 状态转移图

```
                    ┌─────────────────┐
                    │   (created)     │
                    └────────┬────────┘
                             │ inbound_request_validated
                             ▼
                    ┌─────────────────┐
              ┌────▶│    received     │
              │     └────────┬────────┘
              │              │ phi_redacted
              │              ▼
              │     ┌─────────────────┐
              │     │    planning     │◀──┐
              │     └────────┬────────┘   │ (重试: plan_failed → planning)
              │              │             │
              │   ┌──────────┼──────────┐  │
              │   │          │          │  │
              │ plan_     plan_      planning_│
              │ generated failed     timeout  │
              │   │          │          │     │
              │   ▼          │          ▼     │
              │ ┌──────┐     │   ┌──────────┐│
              │ │del-  │     │   │  failed  ││
              │ │egat- │     │   └──────────┘│
              │ │ing   │     │               │
              │ └──┬───┘     │               │
              │    │         │               │
              │    │ all_    │               │
              │    │ experts_│               │
              │    │ returned│               │
              │    │         │               │
              │    ▼         │               │
              │ ┌──────────┐ │               │
              │ │aggregat- │ │               │
              │ │ing       │ │               │
              │ └────┬─────┘ │               │
              │      │       │               │
              │      │aggregated             │
              │      ▼       │               │
              │ ┌──────────┐ │               │
              │ │completed │ │               │
              │ └──────────┘ │               │
              │               │               │
              │   critical_   │               │
              │   expert_     │               │
              │   failed ─────┴───────────────┘
              │   (delegating)
              │
              └──── (终态)
```

### 4.3 状态机实现要求 (Q1 生产级)

| 要求 | 说明 |
|------|------|
| **不可变状态对象** | 每次状态切换生成新 state object, 不 mutate 旧 object (便于审计/回放) |
| **状态转移函数纯函数** | `transition(current_state, event) → new_state` 不应有副作用 (副作用走 side-effect handler) |
| **side-effect handler 显式** | 状态转移时**显式调用** recorder / metrics / logger, 不隐式 |
| **状态机不抛异常** | 错误转为 event (`plan_failed` / `critical_expert_failed`), 不抛 Exception |
| **终态不可转移** | `completed` / `failed` 不允许再转移 (防御式: raise if attempted) |
| **state 序列可序列化** | recorder 写入 M2aRecorder 的 state 序列可重放 (debug / 审计) |
| **单 instance per run** | 每次 A2A 请求 = 1 个 StateMachine instance, 跑完即 GC, 不跨请求共享 |
| **in-memory only** | 状态机不直接写 DB, 由 M2aRecorder 负责持久化 (N9 决策) |

### 4.4 事件定义 (精确)

```python
# 这些是事件名, 不是代码 (代码用 enum / dataclass)
class OrchestratorEvent(Enum):
    INBOUND_REQUEST_VALIDATED = "inbound_request_validated"
    PHI_REDACTED = "phi_redacted"
    INBOUND_INVALID = "inbound_invalid"            # → failed

    PLAN_GENERATED = "plan_generated"
    PLAN_FAILED = "plan_failed"                    # 重试 2 次后仍失败 → failed
    PLANNING_TIMEOUT = "planning_timeout"          # 超时 → failed

    ALL_EXPERTS_RETURNED = "all_experts_returned"
    CRITICAL_EXPERT_FAILED = "critical_expert_failed"  # 关键 Expert 失败 → failed
    DELEGATING_TIMEOUT = "delegating_timeout"      # → failed

    AGGREGATED = "aggregated"
    AGGREGATION_FAILED = "aggregation_failed"      # → failed
```

### 4.5 状态 + 上下文 (RunContext)

```python
@dataclass
class RunContext:
    """Per-run state. Created at received, destroyed at completed/failed."""
    run_id: str                # M2aRecorder run id
    context_id: str            # A2A contextId (server-generated)
    agent_id: str              # 哪个 Agent
    agent_definition: AgentDefinition  # 从 Registry 加载
    original_input: str        # 客户端原文 (PHI 脱敏前, 仅审计用)
    redacted_input: str        # PHI 脱敏后, 给 LLM
    plan: Optional[Plan] = None
    expert_results: list[ExpertResult] = field(default_factory=list)
    final_message: Optional[Message] = None
    error: Optional[OrchestratorError] = None
    state_history: list[StateTransition] = field(default_factory=list)  # 状态机审计
```

---

## 5. 接口定义

### 5.1 入站: `POST /api/icoder/agents/{agent_id}/v1/message:send`

**协议**: A2A 0.3 spec
**路径**: `POST /api/icoder/agents/{agent_id}/v1/message:send`
**Content-Type**: `application/json`

#### 5.1.1 请求体 (A2A 0.3 兼容)

```json
{
  "message": {
    "role": "user",
    "parts": [
      {
        "kind": "text",
        "text": "病历文本: 患者 XXX..."
      }
    ],
    "contextId": "optional-server-issued-continuation-id",  // transport 校验租户/Agent/状态后传入
    "interactionId": "optional-correlation-id"
  }
}
```

**关键**: 即使客户端传 `contextId`, Orchestrator **服务端重新生成** (Q4 隔离对齐 Corti, 防止 collision / 串数据)。

#### 5.1.2 响应 (A2A 0.3 兼容, Phase 1 只 Message 不 Task)

```json
{
  "kind": "message",
  "messageId": "uuid",
  "contextId": "server-generated-uuid",
  "parts": [
    {
      "kind": "data",
      "data": { /* A2A DataPart, 含 MedicalCodingOutputSchema + evidence + run_id */ }
    }
  ],
  "metadata": {
    "run_id": "...",
    "trace_id": "...",
    "trace_url": "/api/m2a/runs/...",
    "state_history": ["received", "planning", "delegating", "aggregating", "completed"],
    "phi_redacted": true,
    "production_writeback_blocked": true
  }
}
```

#### 5.1.3 错误响应 (A2A 0.3 错误码)

| 状态 | A2A 错误码 | HTTP | 触发 |
|------|-----------|------|------|
| `inbound_invalid` | `INVALID_REQUEST` | 400 | 消息体格式错 / 必填字段缺失 |
| `phi_redacted` 失败 | `PHI_REDACTION_FAILED` | 500 | PHI 脱敏模块异常 |
| `plan_failed` (重试用尽) | `PLANNING_FAILED` | 500 | LLM 调用失败 3 次 |
| `critical_expert_failed` | `EXPERT_FAILED` | 502 | 关键 Expert 失败 |
| `delegating_timeout` | `DELEGATION_TIMEOUT` | 504 | Expert 调用超时 |
| `aggregation_failed` | `AGGREGATION_FAILED` | 500 | 组合结果失败 |
| 整体 `failed` | `ORCHESTRATION_FAILED` | 500 | 兜底错误码 |

### 5.2 出站: Orchestrator → Expert (A2A 0.3 委托)

**协议**: A2A 0.3 JSON-RPC over HTTP (内部)
**路径**: `POST /api/icoder/internal/experts/{expert_id}/v1/message:send` (内部端点, 见 A2A spec)

#### 5.2.1 委托请求

```json
{
  "message": {
    "role": "orchestrator",
    "parts": [
      {
        "kind": "data",
        "data": {
          "subtask_input": "...",
          "context": { /* 从 RunContext 截取 */ }
        }
      }
    ],
    "contextId": "原 contextId (透传)",
    "interactionId": "orchestrator-原 interactionId"
  },
  "metadata": {
    "delegated_by": "orchestrator-{run_id}",
    "expert_required": true,
    "tool_constraints": ["icd_search", "code_verify"]
  }
}
```

**关键**: `metadata.delegated_by` 让 Expert 知道这是 Orchestrator 委托 (非客户端直调)。

#### 5.2.2 Expert 返回

Expert 返回标准 A2A Message, Orchestrator 解析 `parts[0].data` 作为子结论。

#### 5.2.3 Q7 决策: Expert 独立 system_prompt 必注入

Orchestrator 调用 Expert 时**不传** system_prompt, 由 Expert 自己加载 (`AgentDefinition.system_prompt`)。**LLMGateway 收到的 `system_prompt` 参数 = Expert 自己的, 不被 Orchestrator 覆盖**。

### 5.3 内部: M2aRecorder 集成

| 状态切换 | Recorder stage 名 | payload |
|----------|------------------|---------|
| → `received` | `inbound_received` | `{ contextId, agent_id, original_input_len, redacted_input_len }` |
| PHI 脱敏完成 | `phi_redacted` | `{ redacted_entities: ["NAME", "ID_CARD", "PHONE"] }` |
| → `planning` | `planning_started` | `{ llm_model: "deepseek-v4-flash" }` |
| Plan 生成 | `plan_generated` | `{ plan: Plan }` |
| → `delegating` | `delegating_started` | `{ expert_count }` |
| 调用 Expert X | `expert_invoked` | `{ expert_id, subtask_input, attempt }` |
| Expert X 返回 | `expert_returned` | `{ expert_id, result, latency_ms }` |
| → `aggregating` | `aggregating_started` | `{ expert_result_count }` |
| 组合完成 | `aggregated` | `{ final_message }` |
| → `completed` | `run_completed` | `{ total_duration_ms }` |
| 任何 → `failed` | `run_failed` | `{ error_code, error_stage, error_message }` |

**模式**: 与 RFC 第 5.1 节"RunTraceService 接入点"一致 (`recorder.inference` 顶层 + `ctx.stage` 子层), 不另造。

---

## 6. System Prompt 设计

### 6.1 Orchestrator 自身 prompt (Planner 用)

**目的**: 让 LLM 知道自己是**协调器**, 不做事只调度, 严格按 Plan schema 输出 JSON。

**Prompt 模板** (放 `backend/app/icoder/agent_runtime/orchestrator/prompts.py`):

```markdown
# Role
你是 iCoDer Agent Runtime 的中央协调器 (Orchestrator)。你的唯一职责是**调度**, 不做具体业务。
- 不编码、不分组、不审计、不算费
- 不直接回答用户的临床问题
- 不调用任何工具 (工具由 Expert 调用, 你不接触)

# 任务
根据用户输入 + Agent 声明的 Experts, 产出一个**调度 Plan** (JSON), 说明:
1. 需要委托哪些 Expert (按优先级)
2. 每个 Expert 接收什么子输入
3. Expert 之间的依赖关系 (可选, Phase 1 不实现)

# 输入
- 用户输入: 已 PHI 脱敏 (姓名/身份证/电话/地址 等已替换为 <REDACTED:XXX>)
- Agent 定义: {agent_id, name, available_experts[], rule_sets[], non_goals, output_contract}

# 严格约束 (硬红线)
1. **PHI 已脱敏**: 你的所有输入都已脱敏, 你看到 <REDACTED:NAME> 等占位符时, **不要试图还原或回显**
2. **production_writeback_blocked = true**: 你**不**调用任何写回 EMR/HIS 的动作, 这条红线恒定
3. **不做具体活**: 你只输出 Plan JSON, 不输出业务结论
4. **Expert 委托边界**: 业务能力 = Experts 的能力, 你不替代
5. **结构化输出**: 必须严格按 Plan schema 输出 JSON, 不输出 markdown / 自然语言

# Plan schema
{
  "experts": [
    {
      "expert_id": "coding-expert",
      "priority": 1,
      "subtask_input": "提取病历中的疾病诊断并按 ICD-10-CN 编码",
      "tool_constraints": ["icd_search", "code_verify"]
    }
  ],
  "reason": "病历包含疾病诊断, 需要先做编码审核"
}

# 决策原则
- 单一目标 = 单一 Expert (如: "纯编码审核" → 调 coding-expert)
- 复合目标 = 多 Expert (如: "编码 + DRG 分组" → 调 coding-expert + drg-expert)
- 拒绝越界: 用户问"这个病历严重吗" → 拒绝, 让 Expert 回答
```

### 6.2 Prompt 注入点

| 注入位置 | 内容 | 来源 |
|----------|------|------|
| Planner LLM call 的 system 消息 | 上述 prompt 全文 | Orchestrator prompts.py |
| Planner LLM call 的 user 消息 | redacted_input + agent_definition 摘要 | RunContext |
| Expert LLM call 的 system 消息 | **Expert 自己的** system_prompt (Q7 决策) | Expert.metadata |
| Expert LLM call 的 user 消息 | Orchestrator 委托的 subtask_input | Plan.experts[].subtask_input |

**关键**: Orchestrator 不污染 Expert 的 system_prompt (Q7 决策), 委托 = 传 subtask_input + metadata, Expert 自己加载自己的 prompt。

### 6.3 PHI 脱敏实施

**位置**: Orchestrator 入站 handler 第一步 (RFC 4.3 + 本 spec 3.2 步骤 2)

**方法**:
- 复用既有 `redact_phi` 工具 (在 `icoder-next/backend/icoder/safety/redactor.py` 有, Phase 1 搬过来)
- 脱敏目标: 姓名 / 身份证号 / 电话 / 地址 / 邮箱 / 病案号 / 医保号
- 替换格式: `<REDACTED:NAME>` / `<REDACTED:ID_CARD>` / `<REDACTED:PHONE>` / `<REDACTED:ADDRESS>` / `<REDACTED:EMAIL>` / `<REDACTED:MEDICAL_RECORD_NO>` / `<REDACTED:INSURANCE_NO>`
- 原文 (`original_input`) 仅审计用, 不入 LLM context

**容错**: 脱敏失败 → 整 run fail (`PHI_REDACTION_FAILED` 错误码), 不允许跳过

---

## 7. 错误处理 + 重试 + 降级

### 7.1 错误分类

| 错误类型 | 错误码前缀 | 严重度 | 处理策略 |
|----------|-----------|--------|----------|
| **协议错误** (入站消息格式错) | `INVALID_REQUEST_*` | Critical | 不重试, 直接 fail |
| **PHI 脱敏错误** | `PHI_*` | Critical | 不重试, 直接 fail (合规底线) |
| **LLM 错误** (网络/超时/限流) | `LLM_*` | Recoverable | 重试 + 降级 |
| **Expert 错误** (单 Expert 失败) | `EXPERT_*` | 分情况 | 关键 Expert = Critical, 失败 = fail; 非关键 = Warning, 失败 = skip + warning |
| **M2aRecorder 错误** | `RECORDER_*` | Recoverable | 重试, 失败 = log + 继续 (audit 不阻塞主流程) |
| **超时** | `*_TIMEOUT` | Recoverable | 重试 1 次, 仍超时 = fail |
| **未知错误** | `UNKNOWN_*` | Critical | 不重试, fail + 报警 |

### 7.2 重试策略

| 错误类型 | 重试次数 | 退避 | 总超时 |
|----------|----------|------|--------|
| LLM (网络/超时) | 3 次 | 指数退避 (1s, 2s, 4s) | 60s |
| LLM (限流 429) | 3 次 | 指数退避 (5s, 10s, 20s) | 60s |
| LLM (4xx 业务错) | 0 次 | - | - |
| Expert 关键 | 2 次 | 指数退避 (1s, 2s) | 30s |
| Expert 非关键 | 1 次 | 常数 (1s) | 15s |
| M2aRecorder | 3 次 | 常数 (0.5s) | 5s |
| PHI 脱敏 | 0 次 | - | - |

### 7.3 降级策略

| 阶段 | 降级方案 | 触发 |
|------|----------|------|
| PHI 脱敏 | 无降级, 失败 = fail | 脱敏不可跳过 (合规) |
| Planning LLM | 重试 3 次后 → fail | 协调器是核心, 不能降级 |
| Delegating (关键 Expert) | 无降级, 失败 = fail | 关键 = 业务必走 |
| Delegating (非关键 Expert) | skip + warning + recorder 记录 | 业务可降级, 报告标注 |
| Aggregating | 简单拼接 (不冲突解决) | 冲突解决失败时降级 |
| M2aRecorder | log + 继续 (不阻塞主流程) | 审计不阻塞业务 |

### 7.4 冲突解决 (Aggregating)

**冲突类型**:
- 同一字段, 多个 Expert 返回不同值 (如: 同一诊断, coding-expert 和 drg-expert 返回不同 ICD)
- 时序冲突: 后续 Expert 返回与前序 Expert 矛盾

**解决策略** (Phase 1 简单版):
1. 按 `priority` 排序 (Plan.experts[].priority, 数字小的优先)
2. 高 priority Expert 覆盖低 priority
3. 同 priority: 按 expert 声明顺序 (AgentDefinition.experts[] 顺序)
4. 实在无法解决: 标记 `conflicted: true` + 列出冲突方 + 让人工 review (Phase 1 不上 LLM 二次裁决)

**Phase 5 优化**: 引入 Aggregator LLM call 二次裁决 (在所有 Expert 返回后, 调一次 LLM 整合)。

### 7.5 整体失败回滚

- 任何阶段失败 → 状态机到 `failed` 终态
- 释放 in-memory 资源 (LLM client, MCP connections)
- M2aRecorder 写入 `run_failed` stage
- Prometheus 指标: `orchestrator_runs_total{status="failed"}++`
- 返回 A2A 错误响应 (5.1.3 节错误码)
- **不**补偿已成功的 Expert 调用 (Phase 1 无补偿, 留 Phase 6)

---

## 8. 可观测性

### 8.1 Prometheus 指标 (5+ 指标)

| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `orchestrator_runs_total` | Counter | `agent_id, status` | 运行总数, status ∈ {success, failed, timeout} |
| `orchestrator_run_duration_seconds` | Histogram | `agent_id, terminal_state` | 完整 run 时延分布 |
| `orchestrator_state_transitions_total` | Counter | `from_state, to_state` | 状态转移总数 (用于分析卡点) |
| `orchestrator_expert_invocations_total` | Counter | `expert_id, result` | Expert 委托次数, result ∈ {success, retry, failed, skipped} |
| `orchestrator_expert_duration_seconds` | Histogram | `expert_id` | Expert 委托时延分布 |
| `orchestrator_phi_entities_redacted_total` | Counter | `entity_type` | PHI 脱敏实体数, entity_type ∈ {NAME, ID_CARD, PHONE, ...} |
| `orchestrator_planning_llm_calls_total` | Counter | `model, result` | Planner LLM 调用次数 |
| `orchestrator_planning_llm_duration_seconds` | Histogram | `model` | Planner LLM 调用时延 |

### 8.2 日志

**结构化日志** (JSON 格式, 每行一个事件):

| 日志级别 | 事件 | 字段 |
|----------|------|------|
| INFO | run_started | `{ run_id, context_id, agent_id, input_len }` |
| INFO | state_transition | `{ run_id, from_state, to_state, event }` |
| INFO | phi_redacted | `{ run_id, entity_types: [...] }` |
| INFO | plan_generated | `{ run_id, expert_count, plan }` |
| INFO | expert_invoked | `{ run_id, expert_id, attempt }` |
| WARN | expert_retry | `{ run_id, expert_id, attempt, error }` |
| ERROR | expert_failed | `{ run_id, expert_id, error, critical }` |
| INFO | expert_returned | `{ run_id, expert_id, latency_ms }` |
| INFO | aggregated | `{ run_id, expert_count, conflicted }` |
| INFO | run_completed | `{ run_id, total_duration_ms }` |
| ERROR | run_failed | `{ run_id, error_code, error_stage, error_message }` |

### 8.3 M2aRecorder 集成 (5.3 节)

每个状态切换 + 关键决策都写 stage, 用于:
- 审计回放
- 调试 (按 run_id 查完整 trace)
- 性能分析 (state transition 卡点)

---

## 9. 测试要求 (Q1 生产级 + RFC 10.1 验收)

### 9.1 单元测试 (≥30 cases)

**文件**: `backend/tests/unit/icoder/agent_runtime/orchestrator/test_state_machine.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **状态转移正确性** | 5 状态 × 3 出口事件 = 15 转移, 每个转移 1 test | 15 |
| **状态机不可变性** | 状态转移不 mutate 旧 object, 新 object 独立 | 2 |
| **终态不可转移** | `completed` / `failed` 再转移 = 抛异常 | 2 |
| **事件枚举完整** | OrchestratorEvent 全部事件可触发 | 1 |
| **side-effect 显式** | 状态转移时 recorder/metrics/logger 各被调用 1 次 | 3 |
| **RunContext 生命周期** | 字段初始化 / 序列化 / 销毁 | 3 |
| **错误路径全覆盖** | 7 类错误 (协议/PHI/LLM/Expert/Recorder/超时/未知) 各 1 test | 7 |

**总计**: 33 单元测试

### 9.2 集成测试 (≥10 cases)

**文件**: `backend/tests/integration/icoder/agent_runtime/test_orchestrator_integration.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **与 LLMGateway 联动** | Planner LLM call 走真实 DeepSeek (Q9), 成功返回 Plan | 1 |
| **与 M2aRecorder 联动** | 完整 run 产生 14 阶段 trace, 验证 stage 序列 | 1 |
| **与 Expert Registry 联动** | 加载 AgentDefinition + 解析 experts[] | 1 |
| **与 A2A 端点联动** | POST /v1/message:send 入站 → A2A 响应格式正确 | 1 |
| **与 PHI 脱敏联动** | 脱敏输入正确替换 + 原文不暴露 | 1 |
| **真实病历端到端 (无 LLM)** | mock LLM + 真实其他模块, 1 条病历跑通 | 1 |
| **真实病历端到端 (有 LLM)** | **真实 DeepSeek + 真实其他模块, 1 条病历跑通 (Q9)** | 1 |
| **重试行为** | LLM 失败 3 次 → fail, 重试 2 次成功 → 继续 | 1 |
| **降级行为** | 非关键 Expert 失败 → skip + warning, 关键 Expert 失败 → fail | 1 |
| **并发安全** | 多 run 并发 (10 个同时) 不串数据 (contextId 隔离验证) | 1 |

**总计**: 10 集成测试

### 9.3 e2e 测试 (1 case, Q9 真实 LLM)

**文件**: `backend/tests/e2e/icoder/test_homepage_coding_review_e2e.py`

| 测试 | 覆盖 |
|------|------|
| **1 条真实病历走通 homepage-coding-review** | curl 模拟客户端 → Orchestrator 真实 LLM planning → coding-expert 真实 4 工具 MCP → A2A 响应含 MedicalCodingOutputSchema + evidence + run_id |

**样本**: 急性心梗病历 1 条 (从既有 m2b_smoke_20.json 取 1 条, 真实病历已脱敏)

**验收**:
- HTTP 200 + A2A 兼容响应
- response.metadata.run_id 可在 `/api/m2a/runs/{run_id}` 查到完整 14 阶段 trace
- response.parts[0].data 含 primary_diagnosis.code + evidence (≥1 EvidenceSpan) + confidence
- 时延: 完整 run ≤ 60s (真实 DeepSeek 端到端)

### 9.4 测试矩阵汇总

| 层级 | 数量 | Phase 1 必需 |
|------|------|--------------|
| 单元 | 33 | ✅ |
| 集成 | 10 | ✅ |
| e2e | 1 | ✅ |
| **小计** | **44** | |

加上 RFC 要求的 1227 baseline 不破坏, Phase 1 完成时总测试数 = 1227 + 44 = **1271+**。

---

## 10. iCoDer 差异化叠加

### 10.1 编码体系约束

| 约束 | 落地位置 |
|------|----------|
| ICD-10-CN (诊断) | Orchestrator 委托 coding-expert, 不直连 ICD 字典 |
| ICD-9-CM-3 (手术) | 同上 |
| CHS-DRG / DIP | Orchestrator 委托 drg-expert, 不直连 DRG 分组器 |
| 高风险易错码 5 PRIORITY (I66.901 / J98.414 / M80.900 / 45.1600x001 / Z51.102) | 在 coding-expert 内部强制人工复核标记, Orchestrator 不知此细节 (Q7 决策: Expert 独立) |

### 10.2 合规门禁 (6 RuleSet)

| RuleSet | Orchestrator 行为 |
|---------|-------------------|
| `medical_coding` | 委托给 coding-expert, 报告含 5 PRIORITY 提示 |
| `drg_dip` | 委托给 drg-expert, 报告含 DRG/DIP 路径 |
| `insurance_audit` | 委托给 compliance-expert (Phase 2 才接) |
| `charge_compliance` | 委托给 compliance-expert (Phase 2 才接) |
| `document_evidence` | 委托给 compliance-expert (Phase 2 才接) |
| `audit` | Orchestrator 自身执行 (production_writeback_blocked 强制 + Recorder 完整记录) |

**Phase 1 范围**: Orchestrator 只支持 `audit` RuleSet 自身, 其余 5 个 RuleSet 留 Phase 2/3 (Orchestrator 调用 Expert 时, 透传 AgentDefinition.rule_sets, 由 Expert 自己执行)。

### 10.3 证据回链 (char-span)

- Orchestrator **不直连** 证据回链 (Q7 决策: Expert 独立)
- Orchestrator 只在 Aggregating 阶段把 Expert 返回的 evidence 字段透传 + 拼接到最终 Message
- EvidenceSpan 数据结构见 `backend/official_agents/medical_coding/schema.py` (既有)

### 10.4 RBAC (5 角色)

- Orchestrator 入站端点复用既有 RBAC 中间件 (admin/coder/medical_insurance_reviewer/it_operator/auditor)
- Phase 1: 全角色可调, 后续按 agent_id 细粒度权限
- 与 RFC 第 5 节"RAC 0 差距"对齐 (不新增 RBAC, 复用)

---

## 11. 与 RFC 映射 (验收对齐)

| RFC 章节 | 本 spec 章节 | 验证方式 |
|----------|--------------|----------|
| 3.2.1 Orchestrator 目标形态 (Q1) | 第 4 节 状态机 | 单元测试 33 + 集成测试 10 |
| 3.2.3 A2A 协议 (Q2) | 第 5.1 / 5.2 节接口 | e2e test: curl 调用返回 A2A 兼容 |
| 3.2.5 Context (Q4) | 第 3.2 节步骤 2 + 第 5.1.1 节 | 集成测试: contextId 隔离验证 |
| 3.2.11 Memory (Q8) | 第 1.1 节"短期存 Context, 长期存 Memory" | 不实现 Memory (Phase 5) |
| 3.2.6 message:send | 第 5.1 节 | e2e test |
| 4.3 PHI 脱敏 | 第 6.3 节 | 集成测试: 脱敏验证 |
| 4.4 production_writeback_blocked | 第 6.1 节 prompt 硬红线 | 单元测试: prompt 含该字符串 |
| 5 节映射表 Orchestrator 行 | 全部 | 全覆盖 |
| 6 Phase 1 成功标准 | 第 9.4 节测试矩阵 | 1271+ tests 全绿 |
| 6 Phase 1 旧 API 重定向 (Q5) | (本 spec 不直接管, 留 Phase 1 实施) | 集成测试: 旧路由 deprecation header |
| 9.2 W6 (Phase 1 DeepSeek key 准备) | (本 spec 不直接管, 由实施者准备) | dev 环境: `ICODER_CREDENTIAL_LLM` 已设 |

---

## 12. 实现路径 (Phase 1 落地)

### 12.1 文件结构 (新增)

```
backend/app/icoder/agent_runtime/orchestrator/
├── __init__.py
├── state_machine.py          # 状态机实现 (核心)
├── run_context.py            # RunContext dataclass
├── events.py                 # OrchestratorEvent enum
├── errors.py                 # OrchestratorError 异常类
├── planner.py                # Planner LLM 推理
├── delegator.py              # A2A 客户端, Expert 委托
├── aggregator.py             # 结果组合 + 冲突解决
├── recorder_adapter.py       # M2aRecorder 集成
├── metrics.py                # Prometheus 指标
├── prompts.py                # Orchestrator system prompt
├── phi_redactor.py           # PHI 脱敏 (复用 icoder-next 的, Phase 1 搬)
└── inbound_handler.py        # POST /v1/message:send handler

backend/app/icoder/agent_runtime/
├── __init__.py
├── a2a_routes.py             # 路由挂载 (见 5.1 节)
└── (后续 spec 实现: a2a/ context/ tasks/ mcp/ agent_card/)

backend/tests/unit/icoder/agent_runtime/orchestrator/
├── test_state_machine.py     # 33 单元测试
├── test_planner.py
├── test_delegator.py
├── test_aggregator.py
└── test_inbound_handler.py

backend/tests/integration/icoder/agent_runtime/
└── test_orchestrator_integration.py  # 10 集成测试

backend/tests/e2e/icoder/
└── test_homepage_coding_review_e2e.py  # 1 e2e test
```

### 12.2 依赖

| 依赖 | 已有? | 用途 |
|------|-------|------|
| `LLMGateway` (`backend/icoder_runtime/llm_gateway.py`) | ✅ | Planner LLM 调用 (Q9: 真实 DeepSeek) |
| `M2aRecorder` (`backend/icoder_runtime/m2a/recorder.py`) | ✅ | 14 阶段 trace |
| `AgentRegistry` (`backend/icoder_runtime/agents/registry.py`) | ✅ | Agent metadata 加载 |
| `redact_phi` (从 `icoder-next/backend/icoder/safety/redactor.py` 搬) | ⚠ 需搬 | PHI 脱敏 |
| `prometheus_client` | ✅ (既有) | 指标暴露 |
| `pydantic v2` | ✅ | A2A 消息体 dataclass |

### 12.3 与既有模块的衔接 (Q5 决策: clean replace)

| 既有模块 | Orchestrator 关系 |
|----------|------------------|
| `agent_runner.py` (旧 AgentRunner) | **完全废弃** (Q5 决策), 不写 fallback 兼容路径 |
| `/api/runtime/medical-coding/test` 路由 | **保留路径, 加 deprecation header + 重定向到 A2A 端点** (W3) |
| 其余旧 API 路由 (5 个) | 同上, 全部 deprecation + 重定向 |
| `AgentPackageV1` (.icoder-agent 包格式) | **保留**, Orchestrator 从 Registry 加载 AgentDefinition 时复用 |
| `M2aRecorder` | **完全复用**, Orchestrator 适配器只是薄包装 |
| `LLMGateway` | **完全复用**, Orchestrator 不直连 LLM SDK |

### 12.4 实施顺序 (Phase 1 内部)

1. **T1**: state_machine.py + run_context.py + events.py + errors.py (核心状态机, 单元测试可写)
2. **T2**: phi_redactor.py (从 icoder-next 搬, 加单元测试)
3. **T3**: prompts.py (Orchestrator prompt 模板, 单元测试 prompt 字符串)
4. **T4**: planner.py (Planner LLM 推理, 集成测试)
5. **T5**: delegator.py (A2A 客户端, 集成测试)
6. **T6**: aggregator.py (结果组合, 单元测试)
7. **T7**: recorder_adapter.py + metrics.py (可观测性, 单元测试)
8. **T8**: inbound_handler.py + a2a_routes.py (HTTP 路由, 集成测试)
9. **T9**: e2e test (1 条病历真实 DeepSeek 跑通)
10. **T10**: 旧 API 路由 deprecation header + 重定向 (W3)

每个 T = 1 个 PR, 单独合并, T1-T9 全过才进 Phase 2。

---

## 13. 开放问题 (本 spec 级别)

| # | 问题 | 选项 | 倾向 |
|---|------|------|------|
| Q-S1 | Planner LLM 输出 Plan 的 schema 验证: 严格 pydantic vs 容错? | 倾向: 严格 pydantic v2 + 失败 = 重试 1 次 | |
| Q-S2 | Expert 并发委托: Phase 1 顺序 vs 直接并发? | 倾向: 顺序 (简单可调试), Phase 5 优化并发 | |
| Q-S3 | 状态机是否需要持久化 (DB-backed, 支持重启恢复)? | 倾向: 不需要, in-memory + Recorder 即可, 重启 = fail-fast (N9 决策) | |
| Q-S4 | Aggregator 阶段是否引入二次 LLM 裁决? | 倾向: 不引入 (Phase 1 简单拼接), Phase 5 优化 | |
| Q-S5 | PHI 脱敏失败是否可降级 (用原文 + 警告)? | 倾向: **不降级**, 直接 fail (合规底线) | |
| Q-S6 | Expert 委托是否支持 timeout per Expert? | 倾向: 支持, 默认 30s/Expert, 可由 Plan.expert.timeout_ms 覆盖 | |
| Q-S7 | Orchestrator 是否需要支持多轮 (同一 contextId 多次 message:send)? | **已实现**：持久化脱敏历史，有界检索后注入每轮执行 | 2026-08-10 |
| Q-S8 | 旧 API 路由 deprecation header 内容? | 倾向: `Deprecation: true` + `Sunset: 2026-12-31` + `Link: <A2A 端点 URL>; rel="successor-version"` | |
| Q-S9 | Orchestrator 是否暴露 admin API (查 in-flight runs / kill run)? | 倾向: 不暴露, Phase 5 Task spec 一并实现 | |
| Q-S10 | 真实 LLM (DeepSeek) 端到端 e2e test 失败时, CI 怎么处理? | 倾向: e2e test 标记 `@pytest.mark.requires_llm`, 无 LLM key 时 skip + warning, 不阻塞 CI | |

---

## 14. 参考

### 14.1 战略 RFC

- `E:\Corti4C\docs\ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20)
  - 第 3.2.1 节: Orchestrator 目标形态
  - 第 9 节: 10 决策 (Q1/Q2/Q4/Q5/Q7/Q8/Q9)
  - 第 10.1 节: Phase 1 成功标准

### 14.2 Corti 官方文档

- `E:\Corti4C\Corti\llms-full.txt`
  - `/agentic/architecture` - 多 Agent 架构
  - `/agentic/orchestrator` - Orchestrator 角色
  - `/agentic/agents/send-message-to-agent` - message:send 端点
  - `/agentic/faq` - Orchestrator vs Expert

### 14.3 iCoDer 既有模块

- `backend/icoder_runtime/agent_runner.py` - 旧 AgentRunner (Q5 决策: 不保留)
- `backend/icoder_runtime/llm_gateway.py` - LLMGateway (复用)
- `backend/icoder_runtime/m2a/recorder.py` - M2aRecorder (复用)
- `backend/icoder_runtime/agents/registry.py` - AgentRegistry (复用)
- `backend/official_agents/medical_coding/schema.py` - MedicalCodingOutputSchema (e2e test 验证用)
- `icoder-next/backend/icoder/safety/redactor.py` - PHI 脱敏 (T2 阶段搬)

### 14.4 A2A / MCP 协议

- A2A Protocol v0.3 spec (待 ICODER_V1_A2A_SPEC 拍板后引用)
- MCP Protocol 2025-03-26 spec (待 ICODER_V1_MCP_SPEC 拍板后引用)

### 14.5 iCoDer 战略线索

- 2026-06-20: 100% Corti 复刻 + 10 决策 (本 spec 拍板基础)
- 2026-06-17: 战略转向 (v1=托管云, 私有化取消, 全产品 frontend)
- 2026-06-14: 原子能力架构 (Agent=systemPrompt+experts)
- 2026-06-13: icoder-next 切片开工

---

## 15. 签字 (待审)

| 角色 | 签字 | 日期 |
|------|------|------|
| 架构组 | ___ | ___ |
| 工程 owner | ___ | ___ |
| 安全/合规 | ___ | ___ |

---

**本 spec 拍板后**:
1. 起 `ICODER_V1_A2A_SPEC.md` (Orchestrator 与 Expert 之间协议)
2. 起 `ICODER_V1_CONTEXT_SPEC.md` (contextId 数据模型 + 隔离)
3. 起 `ICODER_V1_TASK_SPEC.md` (Task Service 状态机)
4. 起 `ICODER_V1_MCP_SPEC.md` (可与上面并行, Expert ↔ 工具)
5. 起 `ICODER_V1_AGENT_CARD_SPEC.md` (可与上面并行, Registry 公开)
6. 6 spec 全部拍板 → Phase 1 实施 (T1-T10)
