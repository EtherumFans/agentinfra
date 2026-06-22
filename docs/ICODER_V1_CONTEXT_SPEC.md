# iCoDer v1 Context Spec

**作者**: iCoDer 架构组
**日期**: 2026-06-20
**状态**: Draft (待审, Phase 1 spec 之三)
**范围**: iCoDer v1 Context (会话级上下文) — contextId 数据模型、Context 对象结构、生命周期、跨 contextId 隔离语义、Context/Memory 边界、PHI 处理、GC 策略
**前置**:
- `ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20, Q4 + Q8 决策)
- `ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft, §3.2 步骤 2 / §4.1 RunContext 依赖本 spec)
- `ICODER_V1_A2A_SPEC.md` (Draft, §4.1 Request `message.contextId` / §7.2 入站响应 `result.contextId` 依赖本 spec)
**并行可写**: `ICODER_V1_MCP_SPEC.md` / `ICODER_V1_AGENT_CARD_SPEC.md`
**后续**: `ICODER_V1_TASK_SPEC.md`

---

## 0. 文档目的

把 RFC 第 3.2.5 节"Context Manager"和 Q4 决策（Context 隔离对齐 Corti）+ Q8 决策（短期存 Context, 长期存 Memory）展开成**可实现的详细 spec**: contextId 数据模型、Context 对象 schema、生命周期（create/mutate/expire）、跨 contextId 隔离保证（数据/状态/缓存三层）、Context 与 Memory 的边界、PHI 在 Context 中的处理、Garbage Collection 策略、测试矩阵。

本 spec 是 Q4 + Q8 落地的核心文档, 与 Orchestrator spec 的 RunContext 紧耦合, 与 A2A spec 的 `contextId` 字段紧耦合。

---

## 1. 背景与决定

### 1.1 上游决定 (从 RFC 来)

| 决策 | 拍板 | 对本 spec 的影响 |
|------|------|------------------|
| **Q4** Context 隔离力度与 Corti 对齐 | RFC 第 9 节 | 跨 contextId 完全隔离 (数据/状态/缓存三层), 比 iCoDer 现有 session_id 强 |
| **Q8** 短期存 Context, 长期存 Memory | RFC 第 9 节 | 本 spec 只定义 Context; Memory 留 Phase 5 + `ICODER_V1_MEMORY_SPEC.md` (后续) |
| **Q5** 旧 AgentRunner 不保留, clean replace | RFC 第 9 节 | 现有 `session_id` 字段**重命名为 contextId**, 不保留 session_id 字段 |
| **Q1** Orchestrator 自建, Corti 生产级 | RFC 第 9 节 | Context 接入 Orchestrator, RunContext 引用 Context 对象 |

### 1.2 Corti Context 行为参考

来源: `E:\Corti4C\Corti\llms-full.txt` (corti.ai docs 完整抓取, 2026-06-20)

| 行为 | Corti 做法 | iCoDer 对齐 |
|------|-----------|-------------|
| contextId 生成 | 服务端生成, UUID v4 | **同** |
| 客户端能否传 contextId | 可传 (但服务端不信任, 重生成) | **同** (A2A spec §4.1 已钉死) |
| 跨 contextId 隔离 | 完全隔离 (消息/任务/artifact 永不共享) | **同** (Q4) |
| Context 生命周期 | 一次会话 (user-driven) | **同** |
| Context 存储 | 服务端, 短期 | **同** (Q8) |
| Memory 关系 | Context 短期, Memory 长期, semantic retrieval | **同** (Q8) |
| 同一 contextId 内多轮 | 支持 (同一 contextId 多次 message:send) | **Phase 1 不实现** (单轮), Phase 5 多轮 (Q-S7) |

### 1.3 关键边界 (从 RFC 1.3 + 4.4 来)

- `production_writeback_blocked = true` 恒定 (Context.metadata 必带, 不允许修改)
- PHI 脱敏后**只入 Context** (`redacted_input`), 原文**不入 Context** (原文仅审计表, 单独存储)
- 不接 EMR/HIS 生产写回 (Context 不暴露任何"可写"动作)

---

## 2. 目标 / 非目标

### 2.1 Goals (本 spec 必须达成)

1. **G1**: contextId 服务端生成 (UUID v4), 客户端不能传 (即使传了也忽略)
2. **G2**: 跨 contextId 三层隔离 (数据/状态/缓存) 强保证, 与 Corti 对齐
3. **G3**: Context 存储短期 (SQLite), 自动 expire, 不持久化到长期
4. **G4**: Context/Memory 边界明确, 跨 contextId **不通过 Context 共享**, 走 Memory semantic retrieval (Q8)
5. **G5**: PHI 在 Context 中**只存脱敏后版本**, 原文不入 Context
6. **G6**: Context 接入 Orchestrator (RunContext 引用) + A2A (message.contextId 字段)
7. **G7**: Context 生命周期可观测 (创建/变更/销毁 写 M2aRecorder)
8. **G8**: GC 策略明确 (默认 24h 自动 expire, 可配置)
9. **G9**: 并发安全 (同一 contextId 内串行, 跨 contextId 完全独立)
10. **G10**: 测试矩阵明确 (单元/集成/e2e)

### 2.2 Non-Goals (本 spec 明确不做)

1. **N1**: 不实现 Memory 长期存储 (Phase 5 + `ICODER_V1_MEMORY_SPEC.md` 后续, 本 spec 只定义 Context/Memory 边界)
2. **N2**: 不实现 Context 多轮对话 (同一 contextId 多次 message:send) — Phase 5 才支持
3. **N3**: 不实现 Context 跨进程共享 (单进程 in-memory + SQLite, 跨进程留 Phase 6)
4. **N4**: 不实现 Context 加密 (iCoDer v1 = 托管云, TLS 即可, 不端到端加密)
5. **N5**: 不实现 Context 编辑/回滚 (Append-only, 修改 = 新版本)
6. **N6**: 不实现 Context 配额 (Phase 1 无, Phase 6 才接计费/配额)
7. **N7**: 不实现 Context 主动失效 (e.g., admin 强制 destroy 某个 contextId) — Phase 5
8. **N8**: 不重写 Orchestrator (Orchestrator spec 范围, 本 spec 只定义 Context 对象)

---

## 3. contextId 数据模型

### 3.1 Format

- **类型**: UUID v4 (随机)
- **长度**: 36 字符 (含 4 个 `-` 分隔符)
- **例**: `550e8400-e29b-41d4-a716-446655440000`
- **字符集**: 十六进制 + `-`, 全部小写
- **生成方式**: `uuid.uuid4()` (Python 标准库, 加密强随机)
- **碰撞概率**: ~0 (2^122 空间, 实际使用 ~10^9 个 contextId/年, 碰撞概率 ~10^-15)

### 3.2 服务端生成 (Q4)

- **生成位置**: Orchestrator 入站 handler (Orchestrator spec §3.2 步骤 2)
- **生成时机**: 每次 A2A `message/send` 请求接收时
- **生成后行为**: 
  1. 服务端用 `uuid4()` 生成 contextId
  2. 校验 client 传入的 `message.contextId` (如有), **忽略**, **不使用**
  3. 把服务端生成的 contextId 写入:
     - RunContext.context_id
     - Context.id
     - 响应 result.contextId
     - M2aRecorder 各 stage 的 context_id 字段

### 3.3 唯一性保证

| 唯一性维度 | 保证机制 |
|-----------|----------|
| 进程内唯一 | UUID v4 随机 (无中心化分配) |
| 跨进程唯一 | 同样 UUID v4 (独立进程独立生成) |
| 跨重启唯一 | UUID v4 不依赖进程状态, 重启后新生成仍唯一 |
| 跨数据库迁移唯一 | Context 表 id 字段加 UNIQUE 约束, 重复时 DB 报错 (防御性) |

### 3.4 contextId 命名空间

- contextId 必带 iCoDer 前缀, 避免与外部系统冲突 (即使外部系统也用 UUID, 前缀避免混淆)
- **Phase 1**: 直接用 UUID v4, **不加前缀** (简单)
- **Phase 4 优化**: 加 `icd-` 前缀, 完整形如 `icd-550e8400-e29b-41d4-a716-446655440000`
- **Q-A 决策**: **Phase 1 不加前缀**, UUID v4 直接用, 留 Phase 4 优化

### 3.5 contextId 客户端可见性

| 位置 | 是否暴露给客户端 |
|------|------------------|
| 响应 result.contextId | ✅ 暴露 (A2A spec §4.2) |
| 响应 metadata.contextId | ✅ 暴露 (iCoDer metadata) |
| M2aRecorder trace URL `/api/m2a/runs/{run_id}` | ✅ 暴露 (URL 中含 run_id) |
| 数据库 Context.id 字段 | ❌ 不直接暴露 (通过 API 间接) |
| 日志 | ⚠ 部分 (脱敏后, 截短: `ctx=550e8400...`) |

---

## 4. Context 对象结构

### 4.1 Schema (Pydantic v2)

```python
class Context(BaseModel):
    """A2A Context — server-side, per-session, strict isolation."""
    
    # 必填
    id: str                              # contextId (UUID v4, server-generated)
    created_at: datetime                 # 服务端创建时间
    updated_at: datetime                 # 最后修改时间
    expires_at: datetime                 # 自动过期时间 (created_at + TTL)
    
    # 必填
    agent_id: str                        # 哪个 Agent (URL 路径传入)
    status: ContextStatus                # 状态 (active / completed / failed / expired)
    
    # 可选
    messages: list[ContextMessage]       # 短期消息 (Q8)
    tasks: list[ContextTaskRef]          # 短期 task 引用 (Q8)
    artifacts: list[ContextArtifactRef]  # 短期 artifact 引用 (Q8)
    
    # iCoDer 特有
    metadata: ContextMetadata            # iCoDer metadata (见 4.4)
    
    # 不存 (留 Memory)
    # memory_chunks: list[MemoryChunk]   # Phase 5 + Memory spec, 本 spec 不实现 (N1)
    
    # 审计
    redacted_input_hash: str = ""        # 脱敏输入的 hash (审计用, 不存原文)
    original_input_ref: str = ""         # 原文引用 (审计表外键, 不在本表)


class ContextStatus(str, Enum):
    ACTIVE = "active"                    # 进行中
    COMPLETED = "completed"              # 正常完成
    FAILED = "failed"                    # 失败终止
    EXPIRED = "expired"                  # TTL 到期 (自动 GC)


class ContextMessage(BaseModel):
    """短期消息 (A2A Message 简化版, 只存必要字段)."""
    message_id: str                      # A2A messageId
    role: str                            # "user" / "agent" / "orchestrator" / "expert"
    parts: list[dict]                    # A2A Part (TextPart/DataPart), 简化存 dict
    timestamp: datetime
    redacted: bool = True                # 必 true, 强制要求 (G5)
    metadata: dict = {}                  # iCoDer 特有


class ContextTaskRef(BaseModel):
    """Task 引用 (Task 主体在 Task spec, 这里只存 ref)."""
    task_id: str                         # A2A Task.id
    state: str                           # submitted / working / completed / failed
    started_at: datetime
    completed_at: datetime | None = None


class ContextArtifactRef(BaseModel):
    """Artifact 引用 (Artifact 主体在外部存储)."""
    artifact_id: str
    name: str
    mime_type: str
    url: str                             # 引用 URL (不存实际内容)


class ContextMetadata(BaseModel):
    """iCoDer Context metadata (iCoDer 特有字段)."""
    production_writeback_blocked: bool = True  # 恒 true, 不可改 (G5 + 硬红线)
    phi_redacted: bool = True                  # 恒 true, 不可改
    phi_redacted_entities: list[str] = []      # 脱敏的实体类型 (e.g., ["NAME", "ID_CARD"])
    user_id: str | None = None                 # 关联用户 (RBAC, Phase 1 可选)
    tenant_id: str | None = None               # 多租户 (Phase 6)
    custom: dict = {}                          # 业务自定义 (e.g., encounter_id)
```

### 4.2 Context 字段对比 A2A Message / Task

| Context 字段 | A2A 对应 | 关系 |
|--------------|---------|------|
| `id` | A2A `Message.contextId` / `Task.contextId` | 同一 UUID |
| `messages[].message_id` | A2A `Message.messageId` | 同一 UUID |
| `messages[].role` | A2A `Message.role` | 枚举对齐 |
| `messages[].parts` | A2A `Message.parts` | 简化存, 实际有完整结构 |
| `tasks[].task_id` | A2A `Task.id` | 同一 UUID |
| `tasks[].state` | A2A `Task.status.state` | 枚举对齐 |
| `artifacts[]` | A2A `Task.artifacts[]` | ref 而非完整 |
| `metadata.production_writeback_blocked` | (iCoDer 扩展) | 不污染 A2A spec |
| `metadata.phi_redacted` | (iCoDer 扩展) | 不污染 A2A spec |

### 4.3 存储 (SQLite, 短期)

**数据库表设计**:

```sql
CREATE TABLE contexts (
    id TEXT PRIMARY KEY,                          -- contextId (UUID v4)
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,                -- created_at + TTL
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,                         -- active / completed / failed / expired
    metadata_json TEXT NOT NULL,                  -- ContextMetadata JSON
    redacted_input_hash TEXT NOT NULL DEFAULT '',
    original_input_ref TEXT NOT NULL DEFAULT '',
    
    -- 索引
    INDEX idx_contexts_expires_at (expires_at),
    INDEX idx_contexts_agent_id (agent_id),
    INDEX idx_contexts_status (status)
);

CREATE TABLE context_messages (
    context_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    role TEXT NOT NULL,
    parts_json TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    redacted BOOLEAN NOT NULL DEFAULT 1,           -- 必 1
    metadata_json TEXT NOT NULL DEFAULT '{}',
    
    PRIMARY KEY (context_id, message_id),
    FOREIGN KEY (context_id) REFERENCES contexts(id) ON DELETE CASCADE
);

CREATE TABLE context_task_refs (
    context_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    state TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    
    PRIMARY KEY (context_id, task_id),
    FOREIGN KEY (context_id) REFERENCES contexts(id) ON DELETE CASCADE
);

CREATE TABLE context_artifact_refs (
    context_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    url TEXT NOT NULL,
    
    PRIMARY KEY (context_id, artifact_id),
    FOREIGN KEY (context_id) REFERENCES contexts(id) ON DELETE CASCADE
);

-- 原文审计表 (与 Context 表分离, 不在 Context 生命周期内)
CREATE TABLE original_input_audit (
    id TEXT PRIMARY KEY,                          -- 原文 ID
    context_id TEXT NOT NULL,                     -- 关联 contextId
    original_input TEXT NOT NULL,                 -- 原文 (PHI)
    created_at TIMESTAMP NOT NULL,
    retention_until TIMESTAMP NOT NULL,           -- 审计保留期 (e.g., 90 天)
    
    INDEX idx_original_input_context_id (context_id),
    INDEX idx_original_input_retention (retention_until)
);
```

**关键设计**:
- `redacted BOOLEAN NOT NULL DEFAULT 1` — 强制 messages 必脱敏
- `original_input_audit` 独立表, 不属于 Context, 有独立 retention 策略
- `ON DELETE CASCADE` — Context 销毁时, 子表自动清理

### 4.4 iCoDer metadata 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `production_writeback_blocked` | bool | ✅ | 恒 true, 不可改 (G5 + 硬红线) |
| `phi_redacted` | bool | ✅ | 恒 true, 不可改 |
| `phi_redacted_entities` | list[string] | ⚠ | 脱敏的实体类型, 审计用 |
| `user_id` | string | ⚠ | 关联用户 (RBAC) |
| `tenant_id` | string | ❌ | 多租户 (Phase 6) |
| `custom` | dict | ❌ | 业务自定义, 自由扩展 |

### 4.5 与既有 session_id 的关系 (Q5)

- 既有 `M2aRecorder` 用 `session_id` (UUID), 字段名沿用
- Context 用 `contextId` (UUID v4), 字段名不同
- **映射关系**: `M2aRecorder.session_id` = `Context.id` (语义统一)
- **Phase 1 实施**: M2aRecorder 加 `context_id` 字段 (alias of session_id), 不破坏既有调用

---

## 5. Context 生命周期

### 5.1 状态机

```
                    ┌──────────────────┐
                    │    (无 context)  │
                    └─────────┬────────┘
                              │ create_context() (Orchestrator 入站)
                              ▼
                    ┌──────────────────┐
                    │      active      │
                    └────┬───┬───┬─────┘
                         │   │   │
            complete() ──┘   │   └── fail()
                            │   │
                            │   │   ┌──────────────┐
                            │   └──▶│    failed    │
                            │       └──────────────┘
                            │
                            │   ┌──────────────┐
                            └──▶│  completed   │
                                └──────────────┘
                                
            (任意状态) ──── TTL 到期 ────▶ ┌──────────────┐
                                          │   expired    │
                                          └──────────────┘
```

### 5.2 Create (创建)

**时机**: Orchestrator 入站 handler 接收 A2A `message/send` 请求时 (Orchestrator spec §3.2 步骤 2)

**步骤**:
1. 服务端 `contextId = uuid4()`
2. 创建 Context 对象 (status=active, created_at=now, expires_at=now+TTL)
3. 写 SQLite (INSERT INTO contexts ...)
4. 写 M2aRecorder stage `context_created` (payload: `{contextId, agent_id, ttl_seconds}`)
5. 触发 PHI 脱敏 (Orchestrator spec §6.3)
6. 脱敏后, 创建第一条 `ContextMessage` (role=user, parts=TextPart(redacted_input))
7. 写 SQLite (INSERT INTO context_messages ...)

**TTL**: 默认 24 小时 (`CONTEXT_TTL_SECONDS=86400` env 可配)

### 5.3 Mutate (修改)

**触发**: 状态机状态切换 / 新 message 到达 / 新 task 创建

**步骤**:
1. 更新 `Context.updated_at = now`
2. 必要时更新 `Context.status` (active → completed / failed)
3. 追加 `ContextMessage` (role=agent / orchestrator / expert)
4. 追加 `ContextTaskRef` (新 task 引用)
5. 写 M2aRecorder stage (按 Orchestrator spec §8.2)
6. 写 SQLite (UPDATE / INSERT)

**约束**:
- Append-only (N5): 不允许修改/删除已存在的 message / task_ref, 只追加
- `metadata.production_writeback_blocked` 和 `metadata.phi_redacted` 不可改 (G5)

### 5.4 Complete / Fail (终态)

**Complete 触发**:
- Orchestrator 状态机到 `completed` 终态 (Orchestrator spec §4.1)
- Context.status = completed
- Context.expires_at = now + COMPLETED_TTL (默认 1 小时, 留时间给客户端查 trace)

**Fail 触发**:
- Orchestrator 状态机到 `failed` 终态
- Context.status = failed
- Context.expires_at = now + COMPLETED_TTL (同上)

### 5.5 Expire / Destroy (过期/销毁)

**自动 GC**:
- 后台任务 (cron-like) 每 5 分钟扫一次
- `WHERE expires_at < now AND status != 'expired'` → 标记 expired
- `WHERE expires_at < now - 7 days AND status = 'expired'` → **物理删除** (DELETE CASCADE)

**物理删除策略**:
- 立即删除 messages / task_refs / artifact_refs (CASCADE)
- `original_input_audit` **不删** (独立 retention, 审计要求)
- M2aRecorder 完整 trace **不删** (独立 retention, 审计要求)

**主动销毁** (Phase 5, N7):
- Phase 1 不暴露 admin API
- Phase 5 Task spec 一并实现

### 5.6 生命周期审计

每个 lifecycle event 写 M2aRecorder stage:

| Event | M2aRecorder stage | payload |
|-------|------------------|---------|
| Create | `context_created` | `{contextId, agent_id, ttl_seconds, phi_redacted_entities}` |
| Mutate (add message) | `context_message_added` | `{contextId, message_id, role, redacted}` |
| Mutate (add task) | `context_task_added` | `{contextId, task_id, state}` |
| Complete | `context_completed` | `{contextId, total_messages, total_tasks}` |
| Fail | `context_failed` | `{contextId, error_code, error_stage}` |
| Expire (mark) | `context_expired` | `{contextId, age_seconds}` |
| Destroy (delete) | `context_destroyed` | `{contextId, reason}` |

---

## 6. 跨 contextId 隔离 (Q4 核心)

### 6.1 隔离三层

| 隔离层 | 隔离对象 | 隔离机制 |
|--------|----------|----------|
| **数据隔离** | messages / tasks / artifacts | SQLite 表按 contextId 分区 + 所有查询必带 `WHERE context_id = ?` |
| **状态隔离** | Orchestrator 状态 / Planner 进度 / 缓存 | in-memory state machine 按 contextId 隔离, 无共享变量 |
| **缓存隔离** | LLM response 缓存 / Tool result 缓存 | 缓存 key 必含 contextId, 不同 contextId 永不命中 |

### 6.2 数据隔离实现

**SQLite 层**:
- 所有表 (`context_messages` / `context_task_refs` / `context_artifact_refs`) 主键第一列 = `context_id`
- 所有查询强制带 `WHERE context_id = ?`, 由 SQLAlchemy 约束 (用 `query.filter(Context.id == ctx_id)` 风格)
- 写测试: 跨 contextId 读写必须抛 `ContextIsolationError`

**Repository 层** (新增, 强制):
```python
class ContextRepository:
    """强制按 contextId 隔离的 Context 数据访问层."""
    
    def get_context(self, context_id: str) -> Context:
        # 强制按 contextId 查询, 不允许不带
        ...
    
    def get_messages(self, context_id: str, message_id: str | None = None) -> list[ContextMessage]:
        # message_id 可选, 但 context_id 必填
        ...
    
    def add_message(self, context_id: str, message: ContextMessage) -> None:
        # 强制 contextId 一致性校验 (防串)
        if message.context_id != context_id:
            raise ContextIsolationError(...)
        ...
```

### 6.3 状态隔离实现

**Orchestrator 层**:
- `RunContext` 已经是 per-run 隔离 (Orchestrator spec §4.5)
- State machine instance = per-run, 无共享 (Orchestrator spec §4.3)

**Planner / Delegator 层**:
- Planner LLM call 的 `context` 参数 = 当前 RunContext 的内容, 不混入其他 context
- Delegator 出站时, 透传 contextId (A2A spec §7.3)
- **禁止** Planner / Delegator 持有跨 contextId 的全局缓存 (Phase 1 不实现 LLM 缓存, 留 Phase 5)

### 6.4 缓存隔离实现

**LLM response 缓存** (Phase 5 留, N1):
- Phase 1 不实现 LLM 缓存 (避免 stale / isolation bug)
- Phase 5 实现时, 缓存 key 必含 `contextId + model + system_prompt_hash + input_hash`
- 缓存 value 必带 `contextId`, 命中时校验一致

**Tool result 缓存** (Phase 5 留):
- 同 LLM 缓存, Phase 5 实现, 缓存 key 必含 contextId

**Phase 1 不实现任何缓存** → 隔离风险 = 0

### 6.5 隔离不变量 (Invariant)

**核心不变量**: `∀ context_a, context_b: context_a.id != context_b.id ⟹ context_a.data ∩ context_b.data = ∅`

**测试**:
- 单元测试: 跨 contextId 读写 5 类数据 (messages / tasks / artifacts / metadata / redacted_input_hash), 全部抛 `ContextIsolationError`
- 集成测试: 并发 10 个 contextId 同时跑, 数据互不可见
- e2e 测试: 1 次完整 run, 验证其他 contextId 数据不混入

### 6.6 隔离失败处理

| 隔离失败类型 | 检测 | 响应 |
|--------------|------|------|
| SQL 注入 (跨 contextId 读) | SQLAlchemy ORM 自动防 (但测试必覆盖) | 抛 `ContextIsolationError` |
| 代码 bug (忘记带 WHERE) | 单元测试全覆盖 + Code review | 抛 `ContextIsolationError` + 报警 |
| 并发竞争 (contextId 复用) | UUID v4 强随机 (碰撞概率 ~0) | 实际不会发生 |
| 恶意客户端 (伪造 contextId) | 服务端忽略, 重生成 | 正常流程 |

---

## 7. Context vs Memory 边界 (Q8 核心)

### 7.1 边界原则

| 数据类型 | 生命周期 | 范围 | 存储 | 检索方式 |
|----------|----------|------|------|----------|
| **Context** | 短期 (24h) | 当前 contextId 内 | SQLite | 直接读 (按 contextId 查) |
| **Memory** | 中长期 (90d+) | 跨 contextId | BGE-M3 + FAISS (Phase 5) | semantic retrieval (按 query 检索) |

### 7.2 什么进 Context

| 数据 | 进 Context? | 说明 |
|------|------------|------|
| 当前 user message (脱敏后) | ✅ | 短期, 一次性 |
| 当前 agent response | ✅ | 短期, 一次性 |
| Orchestrator 中间状态 (Plan / 进度) | ✅ | 短期, 一次性 |
| 当前 task 引用 (task_id / state) | ✅ | 短期, 一次性 |
| 当前 artifact 引用 (artifact_id / url) | ✅ | 短期, 一次性 |
| PHI 脱敏标记 (哪些字段被脱敏) | ✅ (metadata) | 审计 |
| LLM 调用的完整 prompt / response | ❌ | **不进** Context, 走 M2aRecorder (审计) |
| 跨会话患者信息 | ❌ | **不进** Context, 走 Memory (Phase 5) |
| 历史编码决策 | ❌ | **不进** Context, 走 Memory (Phase 5) |
| 用户反馈 (accept/reject) | ❌ | **不进** Context, 走 Memory (Phase 5) |

### 7.3 什么进 Memory (Phase 5 留)

| 数据 | 用途 | 检索方式 |
|------|------|----------|
| 跨会话患者基本信息 | 重复患者识别 | semantic + key lookup |
| 历史编码决策 | 编码一致性 | semantic |
| 高风险患者标记 | 主动告警 | semantic |
| 用户反馈 (accept/reject/modify) | 模型微调信号 | semantic |
| Agent 行为模式 | 个性化 | semantic |
| 临床指南版本 | 知识更新 | semantic |

**Memory 实现**: Phase 5 + `ICODER_V1_MEMORY_SPEC.md` (后续), 用 BGE-M3 + FAISS (iCoDer 既有)

### 7.4 跨 contextId 共享 (Q8 严格)

**Q8 落地原则**:
> 跨 contextId **不通过 Context 共享**, 必走 Memory semantic retrieval

**实现约束**:
- 代码中**禁止**出现 `SELECT * FROM context_messages WHERE context_id != ?` 这类跨 contextId 查询
- 跨 contextId 数据访问**只通过** Memory API (`memory.retrieve(query)`)
- 单元测试覆盖: 跨 contextId 数据访问必走 Memory, 不走 Context

**为什么**: Context 是会话级短期, Memory 是跨会话长期; 跨 contextId 直接读 Context 会破坏"会话隔离"语义, 也违反 Q4 隔离保证。

### 7.5 同 contextId 共享 (允许)

**同 contextId 内**:
- Orchestrator / Planner / Delegator / Aggregator **可** 自由读写当前 Context
- 不需要走 Memory (Memory 是跨 contextId 用)
- 性能: 直接 SQLite 读, 不走 embedding 检索

**多轮同 contextId** (Phase 5, N2):
- Phase 1 不支持多轮 (一次 message:send = 一次 run, 一次 Context)
- Phase 5 支持: 客户端送同 contextId 多次 message:send, Context 累积 messages

---

## 8. PHI 在 Context 中的处理

### 8.1 严格规则 (G5)

| 规则 | 实现 |
|------|------|
| **只存脱敏后版本** | `ContextMessage.parts` 必为 `redacted_input` 后的内容; DB 约束 `redacted BOOLEAN NOT NULL DEFAULT 1` |
| **原文不入 Context** | 原文存独立 `original_input_audit` 表, 不在 Context 生命周期内 |
| **可验证** | `redacted_input_hash` 字段存 hash, 校验原文与脱敏版本一致 |
| **不可改** | `metadata.phi_redacted` 字段恒 true, DB 触发器禁止 UPDATE |

### 8.2 PHI 脱敏集成

**位置**: Orchestrator spec §6.3, 在 Context 创建前 (Create 步骤 5)

**方法**:
- 复用 `icoder-next/backend/icoder/safety/redactor.py` (Phase 1 搬过来)
- 脱敏目标: 姓名 / 身份证号 / 电话 / 地址 / 邮箱 / 病案号 / 医保号
- 替换格式: `<REDACTED:NAME>` / `<REDACTED:ID_CARD>` / 等

**Context 写入**:
- `ContextMessage.parts = [{"kind": "text", "text": redacted_input}]`
- `ContextMessage.redacted = true` (DB 必为 1)
- `Context.metadata.phi_redacted = true`
- `Context.metadata.phi_redacted_entities = ["NAME", "ID_CARD", ...]`

**原文审计**:
- `original_input_audit` 表: `{ id, context_id, original_input, retention_until }`
- retention_until = now + 90 天 (合规要求, 待 Security spec 定)

### 8.3 PHI 脱敏失败

- Orchestrator 入口已 fail (`PHI_REDACTION_FAILED`, Orchestrator spec §5.1.3)
- Context 不会被创建 (在 PHI 脱敏之后才创建)
- 原文不入任何表 (即不写 `original_input_audit`)

### 8.4 PHI 跨 contextId 隔离

- `original_input_audit.context_id` = 当前 contextId, 必带
- 跨 contextId 读 `original_input_audit` 走 `WHERE context_id = ?`, 不允许不带

---

## 9. Context 在 Orchestrator / A2A 中的角色

### 9.1 Orchestrator 集成

| Orchestrator 概念 | 引用 Context 字段 | 说明 |
|------------------|-------------------|------|
| `RunContext` (Orchestrator spec §4.5) | `context_id: str` | 与 `Context.id` 同步 |
| `RunContext.original_input` | (不入 Context, 走 original_input_audit) | 原文不入 Context |
| `RunContext.redacted_input` | `Context.messages[0].parts` (第一条 user message) | 脱敏后入 Context |
| `RunContext.plan` | (Orchestrator 内部, 不入 Context) | 短期中间态 |
| `RunContext.expert_results` | (Orchestrator 内部, 不入 Context) | 短期中间态 |
| `RunContext.final_message` | `Context.messages[-1].parts` (最后一条 agent message) | 最终答复入 Context |

**关键**: Orchestrator 中间态 (Plan / expert_results) **不入 Context**, 只最终结果入 Context。这些中间态由 M2aRecorder 记审计。

### 9.2 A2A 集成

| A2A 字段 | 引用 Context 字段 | 说明 |
|---------|-------------------|------|
| `Message.contextId` (请求) | (客户端可传, 服务端忽略) | A2A spec §4.1 |
| `Message.contextId` (响应) | `Context.id` | A2A spec §4.2 |
| `Task.contextId` | `Context.id` | A2A spec §4.3 |
| `Message.metadata` (iCoDer) | `Context.metadata` 的子集 (production_writeback_blocked / phi_redacted) | A2A spec §9 |

### 9.3 数据流 (1 条病历 1 次完整 run)

```
1. Client → POST /v1/message:send (A2A spec §7.2)
   { message: { parts: [TextPart("病历原文...")], contextId?: "client-supplied-but-ignored" } }

2. Orchestrator Inbound Handler:
   a. 生成 contextId = uuid4()           (Q4 服务端生成)
   b. PHI 脱敏: original_input → redacted_input
   c. 写 original_input_audit (原文, 90d retention)
   d. 创建 Context: id=contextId, status=active, expires_at=now+24h
   e. 追加 ContextMessage: role=user, parts=[redacted_input]
   f. M2aRecorder: stage("context_created", {contextId, ...})

3. State Machine → planning → ... → completed

4. State Machine → completed:
   a. 创建 ContextMessage: role=agent, parts=[final_message]
   b. 更新 Context.status = completed, expires_at = now + 1h
   c. M2aRecorder: stage("context_completed", {contextId, ...})

5. Client 收到响应:
   { result: { kind: "message", contextId: "550e8400-...", ... } }

6. 后台 GC:
   - 24h 后 (active → expired)
   - 7d 后 (expired → 物理删除)
   - original_input_audit 单独 retention 90d
```

### 9.4 多 contextId 并发

- 10 个客户端同时发请求 → 10 个 contextId (独立 UUID)
- 10 个 RunContext (Orchestrator 状态机独立)
- 10 个 SQLite row (互不可见, 隔离)
- 10 条 M2aRecorder trace (独立 run_id)

**并发安全保证**:
- SQLite WAL 模式 (既有, 读写并发)
- 状态机 in-memory, per-instance, 无共享
- M2aRecorder 14 阶段 stage 写入串行化 (有锁)

---

## 10. 测试要求

### 10.1 单元测试 (≥35 cases)

**文件**: `backend/tests/unit/icoder/context/test_context.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **contextId 生成** | UUID v4 格式 / 唯一性 / 客户端忽略 | 5 |
| **Context 创建** | 必填字段 / 默认值 / expires_at 计算 | 3 |
| **Context 状态机** | active → completed / active → failed / active → expired | 4 |
| **生命周期事件** | create / mutate / complete / fail / expire / destroy | 6 |
| **ContextMessage** | role 枚举 / redacted=true 强制 / 追加 | 4 |
| **ContextTaskRef / ArtifactRef** | 创建 / 状态更新 / ref 完整性 | 3 |
| **ContextMetadata** | production_writeback_blocked 不可改 / phi_redacted 不可改 | 3 |
| **跨 contextId 数据隔离** | 5 类数据 (messages / tasks / artifacts / metadata / redacted_input_hash) | 5 |
| **PHI 强制** | redacted=false 写库失败 / 原文不入 Context | 2 |

**总计**: 35 单元测试

### 10.2 集成测试 (≥10 cases)

**文件**: `backend/tests/integration/icoder/context/test_context_integration.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **SQLite 持久化** | 完整 create + mutate + query, DB 行为正确 | 1 |
| **GC 自动过期** | TTL 到期 → status=expired, 7d 后物理删除 | 1 |
| **CASCADE 删除** | Context 销毁 → 子表自动清空 | 1 |
| **M2aRecorder 集成** | 6 个 lifecycle event 都写 stage | 1 |
| **Orchestrator 集成** | 1 条病历完整 run, Context 字段正确 | 1 |
| **A2A 集成** | 请求/响应 contextId 字段对得上 | 1 |
| **并发安全** | 10 个 contextId 并发, 数据互不可见 | 1 |
| **PHI 脱敏集成** | redactor 触发 → Context 只见 redacted, 原文进 audit 表 | 1 |
| **TTL 配置** | env `CONTEXT_TTL_SECONDS` 修改生效 | 1 |
| **跨 contextId 强制隔离** | 写带 context_a 的数据 + 读 context_b 数据 = 抛异常 | 1 |

**总计**: 10 集成测试

### 10.3 e2e 测试 (与 Orchestrator/A2A e2e 共享)

**文件**: `backend/tests/e2e/icoder/test_context_e2e.py` (与 Orchestrator/A2A e2e 合并)

| 测试 | 覆盖 |
|------|------|
| **1 条病历完整 run** | 验证: client 收到的 contextId 可在 `GET /api/m2a/runs/{run_id}` 查到; SQLite 中 context 行存在; 原文在 `original_input_audit` 表 |

**总计**: 1 e2e (与 Orchestrator spec + A2A spec 的 1 e2e 是同一个)

### 10.4 测试矩阵汇总

| 层级 | 数量 | Phase 1 必需 |
|------|------|--------------|
| 单元 | 35 | ✅ |
| 集成 | 10 | ✅ |
| e2e | 1 (与 Orchestrator/A2A 共享) | ✅ |
| **小计** | **46** | |

加上 Orchestrator 44 + A2A 53 + 1227 baseline = **1370+**。

---

## 11. 与 RFC 映射 (验收对齐)

| RFC 章节 | 本 spec 章节 | 验证方式 |
|----------|--------------|----------|
| 3.2.5 Context Manager 目标形态 (Q4) | §3 / §6 | 单元测试 35 + 集成测试 10 |
| 3.2.11 Memory (Q8) | §7 (边界原则) | 不实现 Memory (Phase 5 留) |
| 5 节映射表 Context 行 | 全部 | 全覆盖 |
| 6 Phase 1 成功标准 | §10.4 | 1370+ tests 全绿 |
| 6 Phase 1 旧 session_id 重命名 (Q5) | §4.5 | 集成测试: M2aRecorder.session_id = Context.id |
| 9.2 W1 (6 spec 顺序) | (本 spec 是第 3) | spec 拍板 |
| 9.2 W3 (旧 API deprecation) | (不直接管, 由 Orchestrator 实施) | - |
| 10.1 Phase 1 成功标准 | §10.4 测试矩阵 | 全绿 |
| 10.2 v1 完成时 | §7.3 Memory 实现 | Phase 5 留 |

---

## 12. 实现路径 (Phase 1 落地)

### 12.1 文件结构 (新增)

```
backend/app/icoder/agent_runtime/context/
├── __init__.py
├── context.py                 # Context / ContextMessage / ContextTaskRef / ContextArtifactRef / ContextMetadata dataclass
├── context_id.py              # contextId 生成 + 校验
├── context_status.py          # ContextStatus enum
├── context_repository.py      # 数据访问层 (强制按 contextId 隔离)
├── context_isolation.py       # ContextIsolationError + 隔离不变量校验
├── context_lifecycle.py       # 状态机: create / mutate / complete / fail / expire
├── context_garbage_collector.py  # GC 后台任务 (TTL + 物理删除)
├── context_audit.py           # original_input_audit 表 + retention
├── icoder_metadata.py         # ContextMetadata 字段 (iCoDer 特有)
├── db_models.py               # SQLAlchemy 模型
├── db_schema.sql              # SQLite 表 DDL
└── migrations/                # Alembic 迁移 (Phase 1 创表)

backend/app/icoder/agent_runtime/
├── __init__.py
├── context_routes.py          # (Phase 5 才暴露 admin API, Phase 1 不暴露)
└── (其他 3 spec 实现: orchestrator/ a2a/ tasks/ mcp/ agent_card/)

backend/tests/unit/icoder/context/
├── test_context.py            # 35 单元测试
├── test_context_id.py
├── test_context_lifecycle.py
├── test_context_isolation.py
└── test_context_audit.py

backend/tests/integration/icoder/context/
└── test_context_integration.py  # 10 集成测试

backend/tests/e2e/icoder/
└── test_context_e2e.py        # 1 e2e (与 Orchestrator/A2A 共享)
```

### 12.2 依赖

| 依赖 | 已有? | 用途 |
|------|-------|------|
| `SQLAlchemy` (async) | ✅ | ORM |
| `pydantic v2` | ✅ | Context dataclass |
| `uuid` (Python std) | ✅ | contextId 生成 |
| `python-redactor` (从 icoder-next 搬) | ⚠ 需搬 | PHI 脱敏 (Orchestrator spec §6.3 触发) |
| M2aRecorder | ✅ | 生命周期 event stage |
| Alembic | ✅ | DB 迁移 |

### 12.3 实施顺序 (Phase 1 内部)

1. **C1**: context_id.py + context_status.py (UUID 生成 + 状态枚举, 单元测试)
2. **C2**: context.py + icoder_metadata.py (dataclass + metadata 字段, 单元测试)
3. **C3**: db_schema.sql + db_models.py + migrations/ (DB 创表, 集成测试)
4. **C4**: context_repository.py (数据访问层, 强制隔离, 单元测试 + 集成测试)
5. **C5**: context_isolation.py (ContextIsolationError + 隔离校验, 单元测试)
6. **C6**: context_lifecycle.py (状态机, 单元测试)
7. **C7**: context_audit.py (original_input_audit 表 + retention, 单元测试)
8. **C8**: context_garbage_collector.py (GC 后台任务, 集成测试)
9. **C9**: Orchestrator 集成 (Orchestrator spec 的 RunContext 引用 Context, 集成测试)
10. **C10**: A2A 集成 (A2A spec 的 contextId 字段引用 Context.id, 集成测试)
11. **C11**: e2e test (与 Orchestrator/A2A 共享, 真实 DeepSeek 跑通)

每个 C = 1 个 PR, C1-C11 全过才进 Phase 2。

### 12.4 与既有 session_id 的衔接 (Q5)

| 既有 | 新 |
|------|---|
| `M2aRecorder.session_id` (UUID) | `M2aRecorder.session_id` = `Context.id` (alias) |
| `RecorderContext` 无 contextId 概念 | 加 `Context` 表 + 引用 |
| `RunTraceService` 按 session_id 查 | 改按 `context_id` 查 (alias 兼容) |

**Phase 1 实施**: M2aRecorder 不改 API, 加 `context_id` 字段 (从 Context 复制); 旧调用仍用 `session_id`, 内部 alias。

---

## 13. 开放问题 (本 spec 级别)

| # | 问题 | 选项 | 倾向 |
|---|------|------|------|
| Q-C1 | contextId 是否加 iCoDer 前缀 (`icd-...`)? | 倾向: Phase 1 不加 (简单), Phase 4 优化 | |
| Q-C2 | Context TTL 默认值: 24h vs 1h vs 7d? | 倾向: 24h (active) + 1h (completed/failed), 平衡审计需求 | |
| Q-C3 | `original_input_audit` retention: 90d vs 180d vs 1y? | 倾向: 90d (中国合规基础线, 待 Security spec 定) | |
| Q-C4 | 物理删除时机: 7d 后 vs 30d 后 vs 不删? | 倾向: 7d (auto), audit 表不删 (独立 retention) | |
| Q-C5 | Context 暴露 admin API (查/改/删): Phase 1 vs Phase 5? | 倾向: Phase 1 不暴露, Phase 5 与 Task spec 一并实现 | |
| Q-C6 | Context/Memory 边界: 编码决策 (用户 accept/reject) 走 Context 还是 Memory? | 倾向: **走 Memory** (跨会话, 后续会话可参考) | |
| Q-C7 | `custom` metadata 字段是否限定 schema? | 倾向: 不限定 (自由 dict, 但建议加 schema 文档) | |
| Q-C8 | Context 加密: Phase 1 不做, 何时做? | 倾向: Phase 6 (企业客户才需要, 托管云 SSL 足够) | |
| Q-C9 | Context 跨进程: 何时支持 (多实例部署)? | 倾向: Phase 6 (Redis 共享 Context 元数据, SQLite 仍本地) | |
| Q-C10 | e2e test 是否强制依赖 DeepSeek? | 倾向: 是 (与 Orchestrator/A2A 共享 e2e, 真实 LLM) | |

---

## 14. 参考

### 14.1 战略 RFC 与上游 spec

- `E:\Corti4C\docs\ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20)
  - 第 3.2.5 节: Context Manager 目标形态
  - 第 3.2.11 节: Memory
  - 第 9 节: Q4 + Q8 决策
- `E:\Corti4C\docs\ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft 2026-06-20)
  - 第 3.2 节: 数据流步骤 2 (Context 创建)
  - 第 4.5 节: RunContext (引用 Context)
  - 第 6.3 节: PHI 脱敏
- `E:\Corti4C\docs\ICODER_V1_A2A_SPEC.md` (Draft 2026-06-20)
  - 第 4.1 节: Request `message.contextId`
  - 第 4.2 / 4.3 节: Response `result.contextId`
  - 第 7.2 节: 入站响应样板

### 14.2 Corti 官方文档

- `E:\Corti4C\Corti\llms-full.txt`
  - `/agentic/context-memory` - Context & Memory
  - `/agentic/faq` - Context vs Memory

### 14.3 iCoDer 既有代码

- `backend/icoder_runtime/m2a/recorder.py` - M2aRecorder (session_id 兼容)
- `backend/icoder_runtime/agents/registry.py` - AgentRegistry (Phase 1 不变, Phase 4 接)
- `icoder-next/backend/icoder/safety/redactor.py` - PHI 脱敏 (C 阶段搬)

### 14.4 iCoDer 战略线索

- 2026-06-20: 100% Corti 复刻 + 10 决策 (Q4 Context 隔离 + Q8 Context/Memory 边界)
- 2026-06-17: 战略转向
- 2026-06-14: 原子能力架构
- 2026-06-13: icoder-next 切片开工

---

## 15. 签字 (待审)

| 角色 | 签字 | 日期 |
|------|------|------|
| 架构组 | ___ | ___ |
| 工程 owner | ___ | ___ |
| 安全/合规 | ___ | ___ (重点审 PHI 处理 + audit retention) |

---

**本 spec 拍板后**:
1. 起 `ICODER_V1_TASK_SPEC.md` (Task Service, 与本 spec §5.4/§7.2 task ref 字段衔接)
2. 起 `ICODER_V1_MCP_SPEC.md` (并行, Expert ↔ 工具)
3. 起 `ICODER_V1_AGENT_CARD_SPEC.md` (并行, Registry 公开, 与 A2A spec §8 重叠需明确分工)
4. 6 spec 全部拍板 → Phase 1 实施 (C1-C11, 加上 Orchestrator 的 T1-T10 + A2A 的 A1-A10)
