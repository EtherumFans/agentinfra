# iCoDer v1 Task Spec

**作者**: iCoDer 架构组
**日期**: 2026-06-20
**状态**: Draft (待审, Phase 1 spec 之六, **Phase 1 收尾**)
**范围**: iCoDer v1 Task (A2A 异步任务) — Task 数据结构、状态机、生命周期、Cancel 语义、轮询、Task Endpoints
**前置**:
- `ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20)
- `ICODER_V1_A2A_SPEC.md` (Draft 2026-06-20, §4.3 长任务 Task 响应 + §7.5 Task 端点 stub)
- `ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft, §4.1 状态机 failed 终态)
- `ICODER_V1_CONTEXT_SPEC.md` (Draft, §4.2 Task ref 字段)
**Phase 1 状态**: **大部分 stub** (A2A spec §7.5 已留 stub 端点)
**Phase 5 状态**: 完整实现 (状态机 + cancel + 轮询 + 持久化)

---

## 0. 文档目的

把 RFC 第 3.2.8 节"Long-running Tasks (Task Service)" + A2A spec §4.3 / §7.5 展开成**可实现的详细 spec**: Task 数据结构 (A2A v0.3 协议)、状态机 (submitted → working → input-required / completed / failed / canceled)、Cancel 语义 (**Q5 决策: 优雅 drain, 不强制 kill**)、轮询、Task 端点 (Phase 1 stub, Phase 5 完整)、与 Context/Orchestrator/A2A 集成、测试矩阵。

**Phase 1 范围小**: 端点暴露但 stub (501 UNSUPPORTED_OPERATION), 数据结构定义清晰, Phase 5 实施时直接落地。本 spec 80% 是 Phase 5 设计, Phase 1 只做协议对齐 + 端点 stub + 数据结构定义。

---

## 1. 背景与决定

### 1.1 上游决定 (从 RFC 来)

| 决策 | 拍板 | 对本 spec 的影响 |
|------|------|------------------|
| **Q5** 旧 AgentRunner 不保留, clean replace | RFC 第 9 节 | 旧无 Task 抽象, 完全新建 |
| **Q4** Context 隔离对齐 Corti | RFC 第 9 节 | Task.contextId = Context.id, 跨 contextId 隔离 |
| **Q9** Phase 1 直接用 DeepSeek 真实 LLM | RFC 第 9 节 | Phase 1 短任务直接返回 Message; Phase 5 长任务才用 Task 抽象 |
| (N1) A2A spec 完整 N1 留 Phase 1 子集 | RFC / A2A spec | Phase 1 端点 stub, Phase 5 完整 |

### 1.2 A2A v0.3 Task 行为参考

来源: `E:\Corti4C\Corti\llms-full.txt` (corti.ai docs 完整抓取, 2026-06-20)

| 行为 | Corti 做法 | iCoDer Phase 1 | iCoDer Phase 5 |
|------|-----------|----------------|----------------|
| 短任务 (≤ 60s) | 直接返回 Message | ✅ | ✅ |
| 长任务 (> 60s) | 返回 Task (含 taskId) | ❌ (直接返回 Message) | ✅ |
| Task 轮询 | `GET /tasks/{id}` | ⚠ stub (501) | ✅ |
| Task cancel | `POST /tasks/{id}/cancel` | ⚠ stub (501) | ✅ |
| 状态机 | submitted → working → completed / failed / canceled | (不实现) | ✅ |
| 持久化 | 服务端持久化 (跨重启) | (不实现) | ✅ DB-backed |
| input-required 状态 | 支持 (Human-in-loop) | (不实现) | ✅ (Phase 5 后) |

### 1.3 Phase 1 边界

**Phase 1 决策**: 不实现长任务 (Task 抽象)
- 所有 message:send 请求视为短任务 (≤ 60s)
- 短任务直接返回 A2A Message (A2A spec §4.2)
- 不创建 Task 实例, 不返回 taskId
- 端点 `GET /api/icoder/tasks/{task_id}` / `POST /api/icoder/tasks/{task_id}/cancel` 暴露但 stub (返回 501)

**为什么 Phase 1 不实现**:
- 医疗编码审核典型 < 30s, 短任务足够
- Task 抽象 + 持久化 + cancel 语义是 Phase 5 范畴
- Phase 1 端到端跑通更重要 (Q9 真实 LLM)
- 端点 stub 为 Phase 5 留接口, 不破坏客户端

---

## 2. 目标 / 非目标

### 2.1 Goals (本 spec 必须达成)

1. **G1**: Task 数据结构完整 (A2A v0.3 协议格式)
2. **G2**: Task 状态机清晰 (5 状态 + 转移规则)
3. **G3**: Cancel 语义明确 (Q5 决策: 优雅 drain)
4. **G4**: Task 端点 stub 暴露 (Phase 1)
5. **G5**: 轮询策略明确 (Phase 5 客户端)
6. **G6**: 与 Context 集成 (Task.contextId = Context.id)
7. **G7**: 与 Orchestrator 集成 (状态机扩展)
8. **G8**: 测试矩阵明确 (Phase 1 stub 测试 + Phase 5 完整测试)

### 2.2 Non-Goals (本 spec 明确不做)

1. **N1**: Phase 1 不创建 Task 实例 (短任务直接返回 Message)
2. **N2**: Phase 1 不实现 Task 持久化 (Phase 5 留)
3. **N3**: Phase 1 不实现 Task 轮询 (Phase 5 留)
4. **N4**: Phase 1 不实现 cancel 语义 (Phase 5 留)
5. **N5**: Phase 1 不实现 input-required 状态 (Phase 5 留, Human-in-loop)
6. **N6**: Phase 1 不实现 Task 跨进程 (Phase 5 留)
7. **N7**: 不重写 Orchestrator 状态机 (Orchestrator spec 范围, 本 spec 引用)

---

## 3. Task 数据结构 (A2A v0.3 协议)

### 3.1 Task (A2A v0.3 spec 兼容)

```python
class Task(BaseModel):
    """A2A v0.3 Task — async task with lifecycle.
    
    Phase 1: 不创建, 仅数据结构定义
    Phase 5: 完整实现, DB 持久化
    """
    
    # 必填 (A2A v0.3)
    kind: Literal["task"] = "task"
    id: str                              # taskId (UUID v4, server-generated)
    contextId: str                       # 关联 contextId (Phase 1 必有, 短任务不创建 Task)
    status: TaskStatus                   # 状态机当前状态
    
    # 推荐 (A2A v0.3)
    artifacts: list[TaskArtifact] = []   # 任务产出
    history: list[TaskHistoryEntry] = [] # 状态机转移历史 (审计)
    
    # 可选
    metadata: dict = {}                  # iCoDer metadata (run_id / agent_id / ...)
```

### 3.2 TaskStatus

```python
class TaskStatus(BaseModel):
    """A2A v0.3 Task status."""
    state: TaskState                     # 状态枚举
    message: TaskMessage | None = None   # 当前状态关联的 message (可选, 进度信息)
    timestamp: datetime                  # 状态切换时间


class TaskState(str, Enum):
    """A2A v0.3 Task 状态枚举."""
    SUBMITTED = "submitted"              # 已创建, 等待开始
    WORKING = "working"                  # 正在执行
    INPUT_REQUIRED = "input-required"    # 需要 human input (Phase 5 留)
    COMPLETED = "completed"              # 完成
    FAILED = "failed"                    # 失败
    CANCELED = "canceled"                # 取消 (Phase 5 留)


class TaskMessage(BaseModel):
    """Task 关联 message (进度信息)."""
    role: str                            # "agent" / "user" / "system"
    parts: list[dict]                    # A2A Part (TextPart/DataPart)
    timestamp: datetime
```

### 3.3 TaskArtifact

```python
class TaskArtifact(BaseModel):
    """A2A v0.3 Task 产出 (Part-based)."""
    name: str                            # 产出名 (e.g., "coding_review_report")
    description: str = ""                # 产出描述
    parts: list[dict]                    # A2A Part[] (与 Message 格式一致)
    metadata: dict = {}                  # iCoDer metadata (e.g., report_url)
    index: int = 0                       # 产出顺序
    append: bool = False                 # 是否追加 (vs 替换)
    lastChunk: bool = False              # 是否最后一块 (chunked artifact)
```

### 3.4 TaskHistoryEntry

```python
class TaskHistoryEntry(BaseModel):
    """Task 状态机转移历史 (审计)."""
    state: TaskState                     # 切换到的状态
    timestamp: datetime
    message: TaskMessage | None = None   # 状态切换原因
    metadata: dict = {}                  # iCoDer metadata
```

### 3.5 iCoDer metadata (Task)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `run_id` | string | ✅ | M2aRecorder run ID |
| `agent_id` | string | ✅ | 哪个 Agent |
| `orchestrator_state_history` | list[string] | ⚠ | Orchestrator 状态序列 (审计) |
| `total_duration_ms` | int | ⚠ | 完整 run 时延 (completed 时填) |
| `phi_redacted` | bool | ✅ | 恒 true (硬红线) |
| `production_writeback_blocked` | bool | ✅ | 恒 true (硬红线) |
| `canceled_by` | string | ❌ | cancel 触发者 (user_id / admin) |
| `cancel_reason` | string | ❌ | cancel 原因 |

---

## 4. Task 状态机

### 4.1 状态定义 (5 + 1)

| 状态 | 含义 | Phase 1 | Phase 5 |
|------|------|---------|---------|
| `submitted` | 已创建, 等待开始 (e.g., 排队中) | ❌ | ✅ |
| `working` | 正在执行 | ❌ | ✅ |
| `input-required` | 等待 human input (Human-in-loop) | ❌ | ✅ (Phase 5 后) |
| `completed` | 完成 | ❌ (短任务直接返回 Message) | ✅ |
| `failed` | 失败 | ❌ | ✅ |
| `canceled` | 取消 (Phase 5) | ❌ | ✅ |

### 4.2 状态转移图 (Phase 5)

```
                    ┌──────────────────┐
                    │   (无 Task)      │
                    └─────────┬────────┘
                              │ create_task() (长任务, > 60s)
                              ▼
                    ┌──────────────────┐
                    │    submitted     │
                    └─────────┬────────┘
                              │ start_task()
                              ▼
                    ┌──────────────────┐
        ┌──────────▶│     working      │◀──┐
        │           └────┬───┬───┬─────┘   │
        │                │   │   │         │ (HIL loop)
        │  cancel()      │   │   │         │
        │  (Q5 优雅drain)│   │   │ input_  │
        │                │   │   │ required│
        │                │   │   │         │
        │                │   │   └─────────┘
        │                │   │
        │       ┌────────┘   └────────┐
        │       │                    │
        │       ▼                    ▼
        │ ┌──────────┐         ┌──────────┐
        │ │completed │         │  failed  │
        │ └──────────┘         └──────────┘
        │
        │   ┌──────────────┐
        └──▶│   canceled   │
            └──────────────┘
            (终态)
```

### 4.3 状态转移函数 (Phase 5)

```python
def transition(current_state: TaskState, event: TaskEvent) -> TaskState:
    """Pure function, no side effects (side effects go to recorder)."""
    valid_transitions = {
        TaskState.SUBMITTED: {
            TaskEvent.START: TaskState.WORKING,
            TaskEvent.CANCEL: TaskState.CANCELED,
            TaskEvent.FAIL: TaskState.FAILED,
        },
        TaskState.WORKING: {
            TaskEvent.COMPLETE: TaskState.COMPLETED,
            TaskEvent.FAIL: TaskState.FAILED,
            TaskEvent.CANCEL: TaskState.CANCELED,
            TaskEvent.INPUT_REQUIRED: TaskState.INPUT_REQUIRED,
        },
        TaskState.INPUT_REQUIRED: {
            TaskEvent.RESUME: TaskState.WORKING,
            TaskEvent.CANCEL: TaskState.CANCELED,
            TaskEvent.FAIL: TaskState.FAILED,
        },
        # 终态不再转移
        TaskState.COMPLETED: {},
        TaskState.FAILED: {},
        TaskState.CANCELED: {},
    }
    if event not in valid_transitions[current_state]:
        raise InvalidTaskTransitionError(...)
    return valid_transitions[current_state][event]


class TaskEvent(str, Enum):
    """Task 状态机事件."""
    START = "start"                      # submitted → working
    COMPLETE = "complete"                # working → completed
    FAIL = "fail"                        # 任意 → failed
    CANCEL = "cancel"                    # 任意 → canceled (Q5 优雅 drain)
    INPUT_REQUIRED = "input_required"    # working → input-required
    RESUME = "resume"                    # input-required → working
```

### 4.4 状态机实现要求 (Phase 5, 与 Orchestrator 状态机一致)

| 要求 | 说明 |
|------|------|
| 不可变 state object | 每次切换生成新对象 |
| 转移函数纯函数 | 不抛异常 (错误转 event) |
| side-effect 显式 | recorder / metrics / logger 显式调用 |
| 终态不可转移 | completed / failed / canceled 防御式 raise |
| 状态序列可序列化 | recorder 写入 M2aRecorder |

---

## 5. Task 生命周期 (Phase 5 完整)

### 5.1 Create (创建)

**触发**: 客户端送 message:send + 期望长任务处理 (e.g., `configuration.timeout_hint > 60s`)

**步骤**:
1. 服务端生成 `taskId = uuid4()`
2. 服务端生成 `contextId = uuid4()` (若客户端没传, 即使传了也忽略)
3. 创建 Task 对象 (status.submitted, status.timestamp=now)
4. 写 SQLite (INSERT INTO tasks ...)
5. 写 M2aRecorder stage(`task_created`)
6. 返回 Task 响应 (A2A spec §4.3 格式)
7. Orchestrator 调度 (background): submitted → working

**何时是长任务**:
- 客户端 `params.configuration.timeout_hint` 显式声明 > 60s
- Orchestrator 估算耗时 > 60s (e.g., 多个 Expert + 复杂推理)
- 客户端 `params.configuration.streaming = true`

### 5.2 Mutate (状态变更)

**触发**: Orchestrator 状态切换 / 新 artifact 产出 / 进度更新

**步骤**:
1. 更新 Task.status (按状态机)
2. 追加 Task.history[] (新 entry)
3. 追加 Task.artifacts[] (产出)
4. 写 M2aRecorder stage (task_state_changed / task_artifact_added)
5. 写 SQLite (UPDATE)

**约束**:
- Append-only (history / artifacts)
- 终态不可再 mutate
- metadata.phi_redacted 不可改 (硬红线)

### 5.3 Complete / Fail (终态)

**Complete 触发**:
- Orchestrator 状态机到 completed
- Task.status.state = completed
- Task.artifacts[] 完整 (含最终产出)
- Task.metadata.total_duration_ms 填入
- M2aRecorder stage(`task_completed`)

**Fail 触发**:
- Orchestrator 状态机到 failed
- Task.status.state = failed
- Task.status.message 含错误信息
- M2aRecorder stage(`task_failed`)

### 5.4 Cancel (Phase 5, Q5 优雅 drain)

**触发**:
- 客户端 `POST /api/icoder/tasks/{task_id}/cancel`
- admin 强制 cancel (Phase 5 后)
- TTL 到期 (Phase 5 后)

**Q5 决策: 优雅 drain (不强制 kill)**

**流程**:
```
1. 客户端 POST /tasks/{task_id}/cancel
2. Task Service: 检查 task.status.state (必须 != 终态)
3. 设置 internal flag: cancel_requested = True
4. **不**立即中断当前 LLM call / Expert 调用
5. 当前 round 完成后, Orchestrator 检查 cancel_requested
6. 如 cancel_requested = True:
   - Orchestrator 进入 canceled 终态 (新转移: working → canceled)
   - 释放 in-memory 资源
   - Task.status.state = canceled
   - Task.metadata.canceled_by = user_id
   - Task.metadata.cancel_reason = reason
7. M2aRecorder stage("task_canceled", {reason, duration_to_cancel_ms})
8. 返回 A2A Task (status.state = canceled)
```

**关键 (Q5 决策)**:
- 不强制 kill 当前 LLM call (会浪费 token + 留半成品状态)
- 等当前 round 结束 (LLM streaming / tool call 完成) 再 cancel
- 极端情况: 卡死的 LLM call (e.g., 30min 无响应) → 走 timeout, 不靠 cancel

**Cancel 时机保障**:
- Orchestrator 状态机每 round 切换前检查 cancel_requested
- LLM call 完成后检查 cancel_requested
- Tool call 完成后检查 cancel_requested
- 典型 cancel 响应时延: < 5s (等当前 round 结束)

### 5.5 input-required (Phase 5 后, Human-in-loop)

**触发**: Orchestrator / Expert 推理需要 human input (e.g., "请确认主诊断")

**流程**:
1. Task.status.state = input-required
2. Task.status.message 含 human prompt (e.g., "请选择主诊断: A / B / C")
3. M2aRecorder stage("task_input_required")
4. 客户端通过 `POST /tasks/{task_id}/messages` (新方法) 提交 human input
5. 验证 input 合法后, Task.status.state = working (resume)
6. Orchestrator 继续推理

**Phase 1 不实现** (N5), 留 Phase 5 后

### 5.6 生命周期审计

每个 lifecycle event 写 M2aRecorder:

| Event | Stage | payload |
|-------|-------|---------|
| Create | `task_created` | `{task_id, context_id, agent_id}` |
| submitted → working | `task_started` | `{task_id, start_ts}` |
| 工作进度 | `task_progress` | `{task_id, expert_id, progress_pct, intermediate_artifact}` |
| Artifact 产出 | `task_artifact_added` | `{task_id, artifact_name, artifact_id}` |
| input-required | `task_input_required` | `{task_id, prompt}` |
| working → completed | `task_completed` | `{task_id, total_duration_ms, artifacts_count}` |
| 任意 → failed | `task_failed` | `{task_id, error_code, error_stage, error_message}` |
| 任意 → canceled (Q5) | `task_canceled` | `{task_id, reason, duration_to_cancel_ms, drain_completed: true}` |

---

## 6. Task Endpoints (Phase 1 stub, Phase 5 完整)

### 6.1 Phase 1 stub 端点

**A2A spec §7.5 已定义**, 本 spec 负责 stub 实现:

```python
# Phase 1 stub: 端点暴露, 返回 501 UNSUPPORTED_OPERATION

@router.get("/api/icoder/tasks/{task_id}")
async def get_task(task_id: str):
    raise HTTPException(
        status_code=501,
        detail={
            "a2a_error_code": "UNSUPPORTED_OPERATION",
            "details": "Task polling is Phase 5 (留待 Phase 5 实现). Phase 1 短任务直接返回 Message (A2A spec §4.2), 不创建 Task 实例.",
            "phase": "phase_5_留"
        }
    )


@router.post("/api/icoder/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    raise HTTPException(
        status_code=501,
        detail={
            "a2a_error_code": "UNSUPPORTED_OPERATION",
            "details": "Task cancel is Phase 5 (Q5 决策: 优雅 drain).",
            "phase": "phase_5_留"
        }
    )
```

### 6.2 Phase 5 完整端点

#### 6.2.1 `GET /api/icoder/tasks/{task_id}` (Polling)

**Request**: 无 body

**Response (200)**:
```json
{
  "jsonrpc": "2.0",
  "id": "client-req-1",
  "result": {
    "kind": "task",
    "id": "task-uuid",
    "contextId": "ctx-uuid",
    "status": {
      "state": "working",
      "message": null,
      "timestamp": "2026-06-20T12:34:56.789Z"
    },
    "artifacts": [...],
    "history": [
      {"state": "submitted", "timestamp": "2026-06-20T12:34:50.000Z"},
      {"state": "working", "timestamp": "2026-06-20T12:34:51.000Z"}
    ],
    "metadata": {
      "run_id": "...",
      "agent_id": "homepage-coding-review",
      "phi_redacted": true,
      "production_writeback_blocked": true
    }
  }
}
```

**Response (404)**: `TASK_NOT_FOUND`

#### 6.2.2 `POST /api/icoder/tasks/{task_id}/cancel`

**Request** (可选 body):
```json
{
  "reason": "user_requested"  // 或 "timeout" / "admin_kill"
}
```

**Response (200)**: Task 状态已变 canceled
```json
{
  "jsonrpc": "2.0",
  "id": "client-req-2",
  "result": {
    "kind": "task",
    "id": "task-uuid",
    "status": {
      "state": "canceled",
      "message": {"role": "system", "parts": [{"kind": "text", "text": "Canceled by user"}]},
      "timestamp": "..."
    },
    "metadata": {
      "canceled_by": "user_id",
      "cancel_reason": "user_requested"
    }
  }
}
```

**Response (404)**: `TASK_NOT_FOUND`
**Response (409)**: `TASK_NOT_CANCELABLE` (已 completed / failed / canceled)

#### 6.2.3 `GET /api/icoder/tasks` (Phase 5 List, 可选)

**Query**: `?contextId=...` / `?state=working` / `?agent_id=...`

**Response**:
```json
{
  "tasks": [
    { "id": "...", "contextId": "...", "status": {...}, "metadata": {...} },
    ...
  ],
  "total": 42
}
```

**RBAC**: 仅 admin / 任务创建者 / auditor 可查 (Phase 5)

### 6.3 端点错误码

| 状态 | A2A 错误码 | HTTP | 触发 |
|------|-----------|------|------|
| Task 不存在 | `TASK_NOT_FOUND` | 404 | taskId 不在 DB |
| Task 不可 cancel | `TASK_NOT_CANCELABLE` | 409 | task 已是终态 |
| Phase 1 stub | `UNSUPPORTED_OPERATION` | 501 | (Phase 1 触发) |
| 权限不足 | `AUTH_REQUIRED` | 401 | (Phase 4) |
| Context 已 expire | `CONTEXT_INVALID` | 400 | contextId 关联 Context 已 GC |

---

## 7. 轮询策略 (Phase 5 客户端)

### 7.1 推荐轮询模式

**长轮询 (Long Polling)** vs **短轮询 (Short Polling)**:

| 模式 | 优点 | 缺点 |
|------|------|------|
| **长轮询** | 实时性好, 服务端 hold 30s 等状态变 | 服务端连接数高 |
| **短轮询** | 简单, 服务端无状态 | 实时性差 (5s 间隔) |

**Phase 5 推荐**: 短轮询 (简单, 服务端无需 hold), 间隔 5s

**轮询代码样板 (客户端)**:
```python
import time
import requests

def poll_task(task_id: str, base_url: str, max_wait_seconds: int = 300):
    """轮询 task 直到终态或超时."""
    interval = 5
    start = time.time()
    while time.time() - start < max_wait_seconds:
        resp = requests.get(f"{base_url}/api/icoder/tasks/{task_id}")
        task = resp.json()["result"]
        if task["status"]["state"] in ("completed", "failed", "canceled"):
            return task
        time.sleep(interval)
    raise TimeoutError(f"Task {task_id} did not complete within {max_wait_seconds}s")
```

### 7.2 轮询限制

| 限制 | 默认 | 说明 |
|------|------|------|
| 轮询间隔 | 5s | 可由客户端自定义 |
| 最大轮询时长 | 24h | 与 Context 24h TTL 对齐 |
| 同时轮询 task 数 | 100/客户端 | 服务端限流 (Phase 6) |

### 7.3 任务最大时长

| 限制 | 默认 | 触发 |
|------|------|------|
| 任务 TTL | 24h | Task 强制 fail (超时), 与 Context TTL 对齐 |
| 单 round 超时 | 60s | Orchestrator 状态机 round (LLM + tool) 超时 |
| 单 LLM call 超时 | 60s | Planner / Expert LLM 单次调用超时 |
| 单 tool call 超时 | 30s | MCP tool 单次调用超时 (MCP spec §10.2) |

---

## 8. Cancel 语义 (Q5 决策)

### 8.1 优雅 drain (Q5 默认)

**Q5 决策**: 长任务的 cancel 语义 = **优雅 drain**, 不强制 kill

**为什么**:
- 强制 kill 当前 LLM call 浪费 token + 留半成品状态
- LLM call 通常 < 60s, 等完再 cancel 用户感知不强
- 优雅 drain 保持数据一致性 (state machine 完整转移)

**实现**:
- Task Service 维护 `cancel_requested: bool` flag
- Orchestrator 状态机每 round 切换前 / LLM call 完成时 / Tool call 完成时检查 flag
- 检查到 True → 走 canceled 转移, 释放资源

### 8.2 强制 kill (Phase 5 后, admin 用)

**Phase 5 后**: admin 可强制 kill (不优雅)
- `POST /api/icoder/tasks/{task_id}/force-kill` (新方法, Phase 5+)
- 强制中断当前 LLM call (close httpx connection)
- 资源可能半成品 (LLM response 不完整)

**默认不暴露** (admin only, RBAC 严格)

### 8.3 Cancel 响应时延

| 场景 | 时延 |
|------|------|
| 正常 cancel (LLM call 即将完成) | < 5s |
| 长 LLM call 中 | < 60s (等当前 LLM call 结束) |
| Tool call 中 | < 30s (等当前 tool call 结束) |
| 极端 (死锁) | 60s (round timeout 兜底) |

---

## 9. 与 Context / Orchestrator / A2A 集成

### 9.1 Context 集成

| Context 字段 | 引用 Task | 说明 |
|--------------|-----------|------|
| `Context.id` | `Task.contextId` | 同 UUID |
| `Context.tasks[]` | `Task.id` 引用 | ref 而非完整 (Context spec §4.1) |
| `Context.expires_at` | `Task` 不可超 | Task TTL ≤ Context TTL |

### 9.2 Orchestrator 集成

| Orchestrator 状态 | Task 状态 | 说明 |
|-------------------|-----------|------|
| `received` | `submitted` | Task 刚创建 |
| `planning` | `working` | Planner LLM 推理中 |
| `delegating` | `working` | Delegator 调 Expert 中 |
| `aggregating` | `working` | Aggregator 组合中 |
| `completed` | `completed` | Task 完成 |
| `failed` | `failed` | Task 失败 |
| (Phase 5) | `canceled` | 新 Orchestrator 状态 (或走 failed, 标 canceled) |

**关键**: Phase 5 时, Orchestrator 状态机扩展加 `canceled` 终态, 与 Task.status.state 同步

### 9.3 A2A 集成

| A2A 字段 | 引用 Task |
|---------|-----------|
| `message/send` 返回 (长任务) | Task 对象 (§4.3) |
| `tasks/get` 端点 | Task 轮询 (§6.2.1) |
| `tasks/cancel` 端点 | Task 取消 (§6.2.2) |
| `message/stream` (Phase 5) | SSE 推 task.status.changed 事件 (Task spec N4 留) |

---

## 10. 测试要求

### 10.1 单元测试 (≥20 cases, Phase 1 + Phase 5)

**文件**: `backend/tests/unit/icoder/task/test_state_machine.py` + `test_lifecycle.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **Task 数据结构** | Task / TaskStatus / TaskArtifact / TaskHistory 序列化 | 4 |
| **Task 状态机 (Phase 5)** | 6 状态 × 5 转移 = 15 转移覆盖, 防御式测试 | 6 |
| **状态机不变量** | 不可变 / 终态不可转移 / 防御式 raise | 3 |
| **Cancel 优雅 drain (Q5)** | cancel_requested flag + drain 时机 | 3 |
| **iCoDer metadata** | phi_redacted / production_writeback_blocked 恒 true | 2 |
| **Phase 1 stub** | 端点 501 + 错误信息正确 | 2 |

**总计**: 20 单元测试

### 10.2 集成测试 (≥8 cases, Phase 1 + Phase 5)

**文件**: `backend/tests/integration/icoder/task/test_endpoints.py` + `test_lifecycle_integration.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **Phase 1 stub 端点** | GET /tasks/{id} / POST /tasks/{id}/cancel 返回 501 | 2 |
| **Phase 5 GET /tasks/{id}** | 200 + 404 (TASK_NOT_FOUND) | 2 |
| **Phase 5 POST /tasks/{id}/cancel** | 200 + 409 (TASK_NOT_CANCELABLE) | 2 |
| **Cancel 优雅 drain** | cancel_requested 设置 + Orchestrator 检测到 + 状态转移 | 1 |
| **M2aRecorder 集成** | 8 类 lifecycle event 写 stage | 1 |

**总计**: 8 集成测试

### 10.3 e2e 测试 (与 Orchestrator e2e 合并)

**文件**: `backend/tests/e2e/icoder/test_task_e2e.py` (与 Orchestrator/A2A/Context/MCP/Agent Card 共享)

| 测试 | 覆盖 |
|------|------|
| **(Phase 5)** 长任务: curl 发起 → 轮询 → canceled (Q5 drain) | 真实 DeepSeek + Task 状态机 + 优雅 drain |

**Phase 1 e2e**: 不单独写 Task e2e (Phase 1 短任务, 与 Orchestrator e2e 共享)

**总计**: 1 e2e (Phase 5 才用)

### 10.4 测试矩阵汇总

| 层级 | 数量 | Phase 1 必需 | Phase 5 必需 |
|------|------|--------------|--------------|
| 单元 | 20 | ✅ (8 stub) | ✅ (12 完整) |
| 集成 | 8 | ✅ (2 stub) | ✅ (6 完整) |
| e2e | 1 (Phase 5) | ❌ | ✅ |
| **小计** | **29** | Phase 1: 10 | Phase 5: 19 |

加上 Orchestrator 44 + A2A 53 + Context 46 + MCP 66 + Agent Card 43 = **252 新增 (Phase 1) + 19 增量 (Phase 5) + 1227 baseline = 1498+ (Phase 1) → 1517+ (Phase 5)**。

---

## 11. 与 RFC 映射 (验收对齐)

| RFC 章节 | 本 spec 章节 | 验证方式 |
|----------|--------------|----------|
| 3.2.8 Long-running Tasks (Task Service) | §3 / §4 / §5 | Phase 5 单元 + 集成 + e2e |
| 3.3 协议版本锁定 (A2A v0.3 兼容) | §3 (Task 协议格式) | 单元测试: Task 数据类与 A2A v0.3 一致 |
| 5 节映射表 Task Service 行 | 全部 | Phase 5 覆盖 |
| 6 Phase 5 完整实现 (Task Service) | §4-§9 | Phase 5 实施时验证 |
| 9.2 W3 (旧 API deprecation) | (A2A spec §7.5 留 stub) | 集成测试: stub 端点返回 501 |
| 10.1 Phase 1 成功标准 | §10.4 (Phase 1: 10 cases) | 全绿 |
| 10.2 v1 完成时 | §10.4 (Phase 5: 19 cases) | Phase 5 验证 |

---

## 12. 实现路径 (Phase 1 + Phase 5)

### 12.1 文件结构 (新增)

```
backend/app/icoder/agent_runtime/task/
├── __init__.py
├── task.py                     # Task / TaskStatus / TaskArtifact / TaskHistory 数据类
├── task_state.py               # TaskState / TaskEvent enum
├── task_state_machine.py       # 状态机 (Phase 5 完整)
├── task_lifecycle.py           # create / mutate / complete / fail / cancel (Phase 5)
├── task_cancel.py              # 优雅 drain (Q5 决策, Phase 5)
├── task_repository.py          # DB-backed (Phase 5)
├── icoder_metadata.py          # iCoDer metadata 字段
└── routes_task_stub.py         # Phase 1 stub 端点 (与 A2A spec §7.5 对齐)

backend/app/icoder/agent_runtime/
├── __init__.py
├── task_routes.py              # 路由挂载
└── (其他 5 spec 实现: orchestrator/ a2a/ context/ mcp/ agent_card/)

backend/tests/unit/icoder/task/
├── test_state_machine.py       # 9 cases
├── test_lifecycle.py           # 6 cases
└── test_data_structures.py     # 5 cases
# 20 unit tests total

backend/tests/integration/icoder/task/
├── test_endpoints_stub.py      # 2 cases (Phase 1)
└── test_endpoints_full.py      # 6 cases (Phase 5)
# 8 integration tests total

backend/tests/e2e/icoder/
└── test_task_e2e.py            # 1 e2e (Phase 5, 与 Orchestrator 共享)
```

### 12.2 依赖

| 依赖 | 已有? | 用途 |
|------|-------|------|
| `pydantic v2` | ✅ | Task 数据类 |
| `fastapi` | ✅ | 路由 |
| `SQLAlchemy` (async) | ✅ | DB (Phase 5) |
| `httpx` (async) | ✅ | LLM cancel (close connection, Phase 5) |
| M2aRecorder | ✅ | lifecycle event |
| Context (Context spec) | ✅ | Task.contextId |
| Orchestrator (Orchestrator spec) | ✅ | cancel_requested flag 注入 |

### 12.3 实施顺序

**Phase 1 实施** (现在做):
1. **TK1**: task.py + task_state.py (数据类, 单元测试)
2. **TK2**: routes_task_stub.py (Phase 1 stub 端点, 集成测试)

**Phase 5 实施** (后续):
3. **TK3**: task_state_machine.py (状态机, 单元测试)
4. **TK4**: task_repository.py (DB-backed, 集成测试)
5. **TK5**: task_lifecycle.py (create / mutate / complete / fail, 集成测试)
6. **TK6**: task_cancel.py (Q5 优雅 drain, 集成测试 + e2e)
7. **TK7**: 真实长任务 e2e (与 Orchestrator 共享)

每个 TK = 1 个 PR, 单独合并。

### 12.4 与 Orchestrator 状态机的衔接 (Phase 5)

**关键**: Phase 5 时 Orchestrator 状态机扩展, 加 `canceled` 终态

```python
# Orchestrator spec §4.1 扩展 (Phase 5)
class OrchestratorEvent(Enum):
    # ... (既有)
    CANCELED = "canceled"             # working → canceled (Phase 5 新增)
    CANCELED_TIMEOUT = "canceled_timeout"  # 兜底: round 超时
```

**RunContext** 扩展加 `cancel_requested: bool = False` 字段, Orchestrator 状态机每 round 切换前检查

---

## 13. 开放问题 (本 spec 级别)

| # | 问题 | 选项 | 倾向 |
|---|------|------|------|
| Q-T1 | 长任务判断标准: 客户端声明 vs Orchestrator 估算? | 倾向: 两者都支持, 客户端 `configuration.timeout_hint > 60s` 触发 | |
| Q-T2 | Phase 1 是否完全跳过 Task 抽象? | 倾向: 是 (短任务直接 Message), 端点 stub 即可 | |
| Q-T3 | Cancel 强制 kill 是否暴露? | 倾向: 不暴露 Phase 5, Phase 5+ admin only | |
| Q-T4 | input-required 状态是否 Phase 5 实现? | 倾向: 不, 留 Phase 5+ (Human-in-loop) | |
| Q-T5 | Task TTL 默认值? | 倾向: 24h (与 Context TTL 对齐) | |
| Q-T6 | 轮询间隔默认值? | 倾向: 5s (短轮询, 简单) | |
| Q-T7 | 优雅 drain 超时 (Q5 兜底)? | 倾向: round timeout 60s, 超时 = 强制转 failed | |
| Q-T8 | Phase 1 端点是否完全 stub? | 倾向: 是, 端点暴露但返回 501 UNSUPPORTED_OPERATION | |
| Q-T9 | Task 与 Context 关系: 1:1 vs 1:N? | 倾向: 1:1 (一个 Task 关联一个 Context, 一个 Context 可多个 Task) | |
| Q-T10 | Task 列表 API (Phase 5)? | 倾向: 实现, admin 角色可查所有, 普通用户查自己创建的 | |

---

## 14. 参考

### 14.1 战略 RFC 与上游 spec

- `E:\Corti4C\docs\ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20)
  - 第 3.2.8 节: Task Service 目标形态
- `E:\Corti4C\docs\ICODER_V1_A2A_SPEC.md` (Draft 2026-06-20)
  - 第 4.3 节: 长任务 Task 响应
  - 第 7.5 节: Task 端点 (本 spec 实现 stub)
- `E:\Corti4C\docs\ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft 2026-06-20)
  - 第 4.1 节: 状态机 (Phase 5 扩展加 canceled)
  - 第 4.5 节: RunContext (Phase 5 加 cancel_requested 字段)
- `E:\Corti4C\docs\ICODER_V1_CONTEXT_SPEC.md` (Draft 2026-06-20)
  - 第 4.1 节: ContextTaskRef (Task 引用)

### 14.2 A2A 协议官方

- A2A Protocol v0.3 spec: `https://a2a-protocol.org/v0.3/spec`
  - Task object schema
  - Task lifecycle states
  - `tasks/get` / `tasks/cancel` methods

### 14.3 Corti 官方文档

- `E:\Corti4C\Corti\llms-full.txt`
  - `/agentic/architecture` - 多 Agent 架构
  - `/agentic/agents/send-message-to-agent` - 长任务返回 Task
  - `/agentic/faq` - Task vs Message

### 14.4 iCoDer 战略线索

- 2026-06-20: 100% Corti 复刻 + 10 决策 (Q5 决策延伸: 优雅 drain)
- 2026-06-17: 战略转向
- 2026-06-14: 原子能力架构
- 2026-06-13: icoder-next 切片开工

---

## 15. 签字 (待审)

| 角色 | 签字 | 日期 |
|------|------|------|
| 架构组 | ___ | ___ |
| 工程 owner | ___ | ___ |
| 产品 | ___ | ___ |

---

**🎉 6 spec 全部拍板完成!**

**Phase 1 6 spec 全集**:
1. ✅ `ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20)
2. ✅ `ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft, 状态机 + 接口)
3. ✅ `ICODER_V1_A2A_SPEC.md` (Draft, 协议 + Discovery)
4. ✅ `ICODER_V1_CONTEXT_SPEC.md` (Draft, 隔离 + PHI)
5. ✅ `ICODER_V1_MCP_SPEC.md` (Draft, 8 工具 + client/server)
6. ✅ `ICODER_V1_AGENT_CARD_SPEC.md` (Draft, Registry + 4 Discovery 端点)
7. ✅ `ICODER_V1_TASK_SPEC.md` (Draft, Phase 1 stub + Phase 5 完整)

**下一步**:
- 6 spec 全部审完拍板 → Phase 1 实施 (T1-T10 + A1-A10 + C1-C11 + M1-M15 + AC1-AC11 + TK1-TK7 = 64 个 PR)
- Phase 1 完成: 1498+ tests 全绿 + 真实 DeepSeek 端到端跑通
- Phase 2-3 迁移: 6 RuleSet + 8 原子 Agent (Q6 逐个 + 每个端到端)
- Phase 4-6: SSE / 长任务 / Memory / 多 Orchestrator
