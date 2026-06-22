# iCoDer v1 A2A Protocol Spec

**作者**: iCoDer 架构组
**日期**: 2026-06-20
**状态**: Draft (待审, Phase 1 spec 之二)
**范围**: iCoDer v1 A2A (Agent-to-Agent) 协议实现 — JSON-RPC 2.0 信封、Part 类型、Message/Task、Agent Card、Endpoints、错误码、协议版本管理
**前置**:
- `ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20, Q2 决策)
- `ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft, §5 接口定义依赖本 spec)
**并行可写**: `ICODER_V1_MCP_SPEC.md` (Expert↔工具, 与本 spec 独立)
**后续**: `ICODER_V1_CONTEXT_SPEC.md` / `ICODER_V1_TASK_SPEC.md` / `ICODER_V1_AGENT_CARD_SPEC.md` (本 spec 拍板后)

---

## 0. 文档目的

把 RFC 第 3.2.3 节"A2A Protocol"和 Q2 决策（A2A 协议版本对齐 Corti v0.3）展开成**可实现的详细 spec**: JSON-RPC 2.0 信封、Part/Message/Task 数据结构、Agent Card v0.3 schema、4 类 Endpoint（入站/出站/Task/Discovery）、错误码、iCoDer metadata 扩展字段、协议版本管理、测试矩阵。

本 spec **严格对齐 A2A v0.3 spec** (Linux Foundation 维护, Corti 使用同一版本), **不写 iCoDer 私有协议扩展**（iCoDer 特有字段用 A2A `metadata` 命名空间容纳, 见 §12）。

---

## 1. 背景与决定

### 1.1 上游决定 (从 RFC 来)

| 决策 | 拍板 | 对本 spec 的影响 |
|------|------|------------------|
| **Q2** A2A 协议版本对齐 Corti (v0.3) | RFC 第 9 节 | 本 spec 严格按 A2A v0.3 spec 实现, 不写 iCoDer 私有扩展 |
| **Q4** Context 隔离对齐 Corti | RFC 第 9 节 | `contextId` 服务端生成, 客户端不能传 (A2A v0.3 行为) |
| **Q5** 旧 `AgentRunner` 不保留, clean replace | RFC 第 9 节 | 旧 `a2a_protocol.py` (现有 30 预置 Expert 注册) **重做**, 不保留 fallback |
| **Q7** Expert 独立 + 可共享 | RFC 第 9 节 | Agent Card 必须暴露 Expert 自己的 `system_prompt` / `tools` / `model`, 允许第三方注册 |

### 1.2 A2A v0.3 协议参考

- **维护方**: Linux Foundation (原 Google, 2025 移交)
- **最新稳定版**: v0.3 (2026-06)
- **传输**: JSON-RPC 2.0 over HTTPS
- **核心方法**:
  - `message/send` — 发送消息, 返回 Message 或 Task
  - `message/stream` — 流式响应 (SSE, Phase 5 才用)
  - `tasks/get` — 查询 Task 状态
  - `tasks/cancel` — 取消 Task
- **核心对象**: `Message` (立即) / `Task` (异步) / `Part` (TextPart / DataPart / FilePart) / `AgentCard`
- **iCoDer 实现范围**: A2A v0.3 spec 的**子集** (见 N1-N4), 严格按 spec 实现, 不偏移

### 1.3 与 RFC 现有 a2a_protocol.py 的关系

| 现状 | 目标 |
|------|------|
| `AgentCard` (Pydantic, 6 字段) | A2A v0.3 `AgentCard` (10+ 字段, 含 skills / capabilities / securitySchemes / defaultInputModes / defaultOutputModes) |
| `A2ATask` (status 字符串) | A2A v0.3 `Task` (状态机, status.state + status.message) |
| `A2AArtifact` | A2A v0.3 `Artifact` (parts[] 数组, 不只 content 字符串) |
| `coordinate()` / `chain()` (Orchestrator 模拟) | **删除** (Orchestrator 走真 LLM, 不再代码级 chain/parallel) |
| 30 预置 Expert 注册 (硬编码 list) | 改为 Registry 动态加载 (从 AgentDefinition + Expert metadata) |

**结论**: 现有 `a2a_protocol.py` **完全重做**, 不做向后兼容 (Q5 决策)。

---

## 2. 目标 / 非目标

### 2.1 Goals (本 spec 必须达成)

1. **G1**: 严格对齐 A2A v0.3 spec 的核心子集 (见 §3)
2. **G2**: JSON-RPC 2.0 信封正确实现 (请求/响应/错误/批处理)
3. **G3**: Part 类型完整 (TextPart / DataPart / FilePart)
4. **G4**: Message 立即返回 + Task 异步返回 (Phase 1 只 Message, Task 留 Phase 5)
5. **G5**: Agent Card v0.3 schema 完整 (含 skills / capabilities / securitySchemes)
6. **G6**: 4 类 Endpoint 实现 (入站 message/send + 出站 message/send + Discovery + Task)
7. **G7**: A2A v0.3 错误码全集 (8 类)
8. **G8**: iCoDer 特有字段用 `metadata` 命名空间容纳 (run_id / trace_url / phi_redacted / production_writeback_blocked), 不污染 A2A spec
9. **G9**: 协议版本管理明确 (A2A v0.3 + iCoDer 内部版本号)
10. **G10**: 测试矩阵明确 (单元/集成/e2e)

### 2.2 Non-Goals (本 spec 明确不做)

1. **N1**: 不实现 A2A v0.3 spec 全集 (Phase 1 子集: 仅 `message/send` + `tasks/get` + `tasks/cancel` 端点, 不实现 push notifications / auth extensions / multi-tenancy extensions)
2. **N2**: 不实现 SSE 流式 (`message/stream` 留 Phase 5)
3. **N3**: 不实现 push notifications (A2A v0.3 可选扩展, 留 Phase 6)
4. **N4**: 不实现 OAuth2 / API Key / mTLS 等 auth schemes (A2A v0.3 `securitySchemes` schema 预留, 实际验证留 Phase 4)
5. **N5**: 不重写 Orchestrator 内部 (Orchestrator spec 范围, 本 spec 只定义接口契约)
6. **N6**: 不实现 Registry 持久化 (Registry 在内存 dict, Phase 4 才接 DB)
7. **N7**: 不实现 8 原子 Agent 迁移 (Phase 3, 本 spec 只 protocol 本身)

---

## 3. A2A v0.3 协议实现范围 (Phase 1 子集)

| A2A v0.3 组件 | Phase 1 状态 | 备注 |
|--------------|--------------|------|
| JSON-RPC 2.0 信封 | ✅ 完整实现 | `jsonrpc: "2.0"`, `id`, `method`, `params`, `result`, `error` |
| `message/send` 方法 | ✅ 完整实现 | 短任务返回 Message; 长任务返回 Task (Phase 1 只短任务) |
| `message/stream` 方法 | ❌ 不实现 | Phase 5 SSE 端点 |
| `tasks/get` 方法 | ❌ 端点暴露, 实现 stub | Phase 5 完整实现 |
| `tasks/cancel` 方法 | ❌ 端点暴露, 实现 stub | Phase 5 完整实现 |
| `Message` 对象 | ✅ 完整实现 | kind="message", role, parts[], contextId, messageId, metadata |
| `Task` 对象 | ⚠ 端点暴露, 实例化不实现 | Phase 1 不创建 Task 实例 (只返回 Message) |
| `Part` 类型 (TextPart/DataPart/FilePart) | ✅ 完整实现 | TextPart + DataPart Phase 1 必实现; FilePart 留 Phase 4 |
| `AgentCard` | ✅ 完整实现 | v0.3 schema, 含 skills / capabilities / securitySchemes |
| Discovery (`/.well-known/agent.json`) | ✅ 完整实现 | Phase 1 即可, 不依赖 Registry 持久化 |
| `securitySchemes` | ⚠ Schema 预留, 验证 stub | Phase 4 接 RBAC |
| 错误码 | ✅ 8 类完整实现 | 见 §6 |
| 协议版本头 | ✅ `A2A-Protocol-Version: 0.3` | 见 §11 |

---

## 4. JSON-RPC 2.0 信封

### 4.1 Request (客户端 → Orchestrator)

```json
{
  "jsonrpc": "2.0",
  "id": "uuid-or-string-or-number",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [ ... ],
      "contextId": "optional-client-supplied-but-server-ignored",
      "messageId": "optional-client-supplied"
    },
    "configuration": {
      "blocking": true,
      "acceptedOutputModes": ["application/json"]
    }
  }
}
```

### 4.2 Response (成功, 短任务返回 Message)

```json
{
  "jsonrpc": "2.0",
  "id": "echo-of-request-id",
  "result": {
    "kind": "message",
    "role": "agent",
    "messageId": "server-generated-uuid",
    "contextId": "server-generated-uuid",
    "parts": [ ... ],
    "metadata": { ... }
  }
}
```

### 4.3 Response (成功, 长任务返回 Task)

```json
{
  "jsonrpc": "2.0",
  "id": "echo-of-request-id",
  "result": {
    "kind": "task",
    "id": "task-uuid",
    "contextId": "server-generated-uuid",
    "status": {
      "state": "submitted",
      "message": null,
      "timestamp": "2026-06-20T12:34:56.789Z"
    },
    "artifacts": [],
    "history": [ ... ]
  }
}
```

**Phase 1**: 短任务 (医疗编码审核通常 < 60s) 返回 Message; 长任务 (Phase 5) 返回 Task。

### 4.4 Error Response

```json
{
  "jsonrpc": "2.0",
  "id": "echo-of-request-id",
  "error": {
    "code": -32601,
    "message": "Method not found",
    "data": {
      "a2a_error_code": "METHOD_NOT_FOUND",
      "details": "method 'message/foo' not in A2A v0.3 spec"
    }
  }
}
```

**关键**: `data.a2a_error_code` 是 A2A v0.3 业务错误码, 与 JSON-RPC 标准错误码 (`code` 字段) 配合使用。

### 4.5 Batch Requests

A2A v0.3 spec 支持 batch requests (多个 Request 在一个数组里). **Phase 1 不实现 batch**, 单个请求一个响应 (RFC 2616 HTTP 风格)。

### 4.6 HTTP Headers

| Header | 方向 | 值 | 必填 |
|--------|------|---|------|
| `Content-Type` | 双向 | `application/json` | ✅ |
| `A2A-Protocol-Version` | 双向 | `0.3` | ✅ |
| `X-Request-ID` | Request | UUID, 用于链路追踪 | ⚠ 建议 (从 `id` 字段复制亦可) |
| `X-Trace-Context` | Request | W3C trace context (traceparent) | ⚠ 建议 |
| `Authorization` | Request | `Bearer <token>` (Phase 4 才校验) | ⚠ 预留 |
| `X-iCoDer-Agent-Id` | Request | URL 路径已有, Header 冗余校验 | ⚠ 可选 |

---

## 5. Part 类型 (A2A v0.3 spec)

### 5.1 TextPart

```json
{
  "kind": "text",
  "text": "病历原文: 患者主诉胸痛 3 小时..."
}
```

**用途**: 用户自然语言输入, 或 LLM 返回的文本流。

### 5.2 DataPart

```json
{
  "kind": "data",
  "data": {
    "schema": "MedicalCodingOutputSchema",
    "value": {
      "primary_diagnosis": { "code": "I21.0", "description": "急性前壁心肌梗死", "confidence": 0.95 },
      "secondary_diagnoses": [...],
      "procedures": [...],
      "issues_found": [...],
      "drg_suggestion": "F60A"
    }
  }
}
```

**用途**: 结构化数据 (JSON), 编码审核结果 / 临床指标 / 业务 payload。

**关键**: `data.schema` 是 schema 标识符 (URI 风格), `data.value` 是实际值。**A2A v0.3 不规定具体 schema, iCoDer 自行定义 schema 标识符** (见 §12.3)。

### 5.3 FilePart (Phase 4 留)

```json
{
  "kind": "file",
  "file": {
    "name": "ct_scan.png",
    "mimeType": "image/png",
    "bytes": "base64-encoded-bytes",
    "uri": "optional-external-uri"
  }
}
```

**Phase 1 不实现 FilePart** (N1), 病历数据走 TextPart 即可; FilePart 留 Phase 4 接影像/检验报告等二进制。

### 5.4 Part 类型识别

- 客户端发 `parts: [...]`, 每个 part 必带 `kind` 字段 (`text` / `data` / `file`)
- iCoDer Orchestrator 必校验每个 part 的 `kind` 在 A2A v0.3 spec 范围内
- 未知 `kind` → `INVALID_REQUEST` 错误

---

## 6. 错误码 (A2A v0.3 spec 8 类)

### 6.1 JSON-RPC 标准错误码

| `code` | 含义 | HTTP | 触发 |
|--------|------|------|------|
| `-32700` | Parse error | 400 | 请求体不是合法 JSON |
| `-32600` | Invalid request | 400 | 不是合法 JSON-RPC 2.0 请求 |
| `-32601` | Method not found | 404 | `method` 不在 A2A v0.3 spec (如 `message/foo`) |
| `-32602` | Invalid params | 400 | `params` 字段不合法 (缺 message / 缺 parts / part kind 错) |
| `-32603` | Internal error | 500 | Orchestrator 内部错误 (不预期) |
| `-32000` ~ `-32099` | Server error | 500 | 服务端业务错误 (A2A 自定义) |

### 6.2 A2A v0.3 业务错误码 (`error.data.a2a_error_code`)

| A2A 错误码 | HTTP | 触发 |
|-----------|------|------|
| `INVALID_REQUEST` | 400 | 消息体格式错 (A2A v0.3 spec) |
| `METHOD_NOT_FOUND` | 404 | method 不在 A2A v0.3 spec |
| `INVALID_PARAMS` | 400 | params 字段不合法 |
| `INTERNAL_ERROR` | 500 | Orchestrator 内部错误 |
| `AGENT_NOT_FOUND` | 404 | URL 路径 `agent_id` 不存在 |
| `CONTEXT_INVALID` | 400 | contextId 格式错或已被 GC |
| `TASK_NOT_FOUND` | 404 | `tasks/get` 时 taskId 不存在 |
| `TASK_NOT_CANCELABLE` | 409 | `tasks/cancel` 时 task 已 completed / failed |
| `UNSUPPORTED_OPERATION` | 501 | 调用了 Phase 1 不实现的方法 (如 `message/stream`) |
| `PHI_REDACTION_FAILED` | 500 | PHI 脱敏失败 (iCoDer 特有) |
| `PRODUCTION_WRITEBACK_BLOCKED` | 403 | 检测到客户端尝试写回 EMR/HIS (iCoDer 特有) |
| `AUTH_REQUIRED` | 401 | Phase 4 才用, Phase 1 不触发 |
| `RATE_LIMITED` | 429 | 限流 (Phase 6 才用, Phase 1 不触发) |

### 6.3 错误响应样板

```json
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "error": {
    "code": -32600,
    "message": "Invalid request",
    "data": {
      "a2a_error_code": "INVALID_REQUEST",
      "details": "message.parts[0].kind must be one of: text, data, file",
      "spec_ref": "https://a2a-protocol.org/v0.3/spec#message"
    }
  }
}
```

---

## 7. Endpoints

### 7.1 端点总览

| 类别 | 端点 | 方法 | A2A method | Phase 1 状态 |
|------|------|------|------------|--------------|
| **入站 (Client → Orchestrator)** | `/api/icoder/agents/{agent_id}/v1/message:send` | POST | `message/send` | ✅ 完整实现 |
| **入站 (Client → Agent Card)** | `/api/icoder/agents/{agent_id}/card` | GET | (discovery) | ✅ 完整实现 |
| **入站 (Client → Discovery)** | `/.well-known/agent.json` | GET | (discovery) | ✅ 完整实现 |
| **入站 (Client → LLM 友好)** | `/llms.txt` | GET | (discovery) | ✅ 完整实现 |
| **入站 (Client → Agent list)** | `/api/icoder/agents` | GET | (discovery) | ✅ 完整实现 |
| **出站 (Orchestrator → Expert)** | `/api/icoder/internal/experts/{expert_id}/v1/message:send` | POST | `message/send` | ✅ 完整实现 |
| **Task polling (Client → Orchestrator)** | `/api/icoder/tasks/{task_id}` | GET | `tasks/get` | ⚠ 端点暴露, stub |
| **Task cancel (Client → Orchestrator)** | `/api/icoder/tasks/{task_id}/cancel` | POST | `tasks/cancel` | ⚠ 端点暴露, stub |

### 7.2 入站: Client → Orchestrator

#### 7.2.1 `POST /api/icoder/agents/{agent_id}/v1/message:send`

**URL 路径**: `POST /api/icoder/agents/{agent_id}/v1/message:send`

**注意**: URL 路径用 `message:send` (Corti 风格, 冒号分隔), 不是 A2A spec 的 `message/send` (斜杠分隔). 这是 URL 风格选择, 实际 method 字段在 JSON body 内仍用 A2A spec 的 `message/send`。

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "client-req-123",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {"kind": "text", "text": "病历: 患者男 65 岁..."}
      ]
    },
    "configuration": {
      "blocking": true,
      "acceptedOutputModes": ["application/json"]
    }
  }
}
```

**Response (短任务, 成功)**:
```json
{
  "jsonrpc": "2.0",
  "id": "client-req-123",
  "result": {
    "kind": "message",
    "role": "agent",
    "messageId": "srv-msg-uuid",
    "contextId": "ctx-uuid",
    "parts": [
      {
        "kind": "data",
        "data": {
          "schema": "icoder/MedicalCodingOutputSchema/v1",
          "value": { /* MedicalCodingOutputSchema 全部字段 */ }
        }
      }
    ],
    "metadata": {
      "run_id": "...",
      "trace_id": "...",
      "trace_url": "/api/m2a/runs/...",
      "phi_redacted": true,
      "production_writeback_blocked": true,
      "state_history": ["received", "planning", "delegating", "aggregating", "completed"]
    }
  }
}
```

**Response (错误)**:
```json
{
  "jsonrpc": "2.0",
  "id": "client-req-123",
  "error": {
    "code": -32600,
    "message": "Invalid request",
    "data": {
      "a2a_error_code": "INVALID_REQUEST",
      "details": "..."
    }
  }
}
```

### 7.3 出站: Orchestrator → Expert (内部)

#### 7.3.1 `POST /api/icoder/internal/experts/{expert_id}/v1/message:send`

**URL 路径**: `POST /api/icoder/internal/experts/{expert_id}/v1/message:send`

**与入站端点的区别**:
- 路径在 `/internal/` 命名空间下
- 不暴露公网 (RFC 7234 内部访问控制)
- 接受 Orchestrator 特定的 `metadata` (见下)

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "orch-req-456",
  "method": "message/send",
  "params": {
    "message": {
      "role": "orchestrator",
      "parts": [
        {
          "kind": "data",
          "data": {
            "subtask_input": "从以下病历提取主诊断, 返回 ICD-10-CN 编码: 患者男 65 岁...",
            "context": {
              "redacted_input_summary": "...",
              "agent_id": "homepage-coding-review"
            }
          }
        }
      ],
      "contextId": "ctx-uuid-from-orchestrator"
    }
  },
  "metadata": {
    "delegated_by": "orchestrator-{orchestrator_run_id}",
    "expert_required": true,
    "tool_constraints": ["icd_search", "code_verify"],
    "timeout_ms": 30000
  }
}
```

**关键 (Q7 决策)**:
- Orchestrator **不传** Expert 的 system_prompt
- Expert 收到请求后**自己加载** `AgentDefinition.system_prompt`, 不依赖 Orchestrator 注入
- `metadata.delegated_by` 让 Expert 知道这是 Orchestrator 委托, 不是客户端直调
- `metadata.tool_constraints` 限制 Expert 可调工具 (可选, 严格模式用)

### 7.4 Discovery Endpoints

#### 7.4.1 `GET /.well-known/agent.json` (A2A v0.3 标准)

**URL**: `GET /.well-known/agent.json`

**Response**: 当前 iCoDer 实例所有 Agent 的列表 (Phase 1 = 内置 1 个, Phase 2-3 = 8 原子 Agent)
```json
{
  "agents": [
    {
      "id": "homepage-coding-review",
      "name": "Homepage Coding Review Agent",
      "description": "...",
      "url": "/api/icoder/agents/homepage-coding-review/v1/message:send",
      "version": "1.0.0",
      "capabilities": { ... },
      "skills": [ ... ],
      "defaultInputModes": ["text"],
      "defaultOutputModes": ["application/json"],
      "securitySchemes": { ... }
    }
  ]
}
```

#### 7.4.2 `GET /api/icoder/agents/{agent_id}/card`

**URL**: `GET /api/icoder/agents/{agent_id}/card`

**Response**: 单个 Agent 的完整 A2A v0.3 `AgentCard` (见 §8)

#### 7.4.3 `GET /api/icoder/agents`

**URL**: `GET /api/icoder/agents?capability=icd_coding`

**Query**: `?capability=icd_coding` 过滤 (可选)

**Response**: Agent 列表 (简化版, 只 id + name + capabilities)

#### 7.4.4 `GET /llms.txt` (LLM 友好)

**URL**: `GET /llms.txt`

**Response**: Markdown 格式, 描述 iCoDer Agent 生态, 给 LLM (Claude / GPT) 阅读用
```markdown
# iCoDer v1 Agent Runtime

iCoDer 是面向中国医院场景的医疗收入合规 AI 平台。

## Available Agents

### homepage-coding-review (v1.0.0)
- 描述: 病案首页编码审核 (DRG/DIP/合规)
- 端点: POST /api/icoder/agents/homepage-coding-review/v1/message:send
- 输入: text (病历)
- 输出: application/json (MedicalCodingOutputSchema)
- ...
```

### 7.5 Task Endpoints (Phase 5 stub)

#### 7.5.1 `GET /api/icoder/tasks/{task_id}` (Phase 5 实现)

**Phase 1 stub**: 端点暴露, 返回 `501 UNSUPPORTED_OPERATION` + 提示 "Task 在 Phase 5 才完整实现"

#### 7.5.2 `POST /api/icoder/tasks/{task_id}/cancel` (Phase 5 实现)

**Phase 1 stub**: 端点暴露, 返回 `501 UNSUPPORTED_OPERATION` + 提示同上

---

## 8. Agent Card Schema (A2A v0.3)

### 8.1 完整 schema

```python
class AgentCard(BaseModel):
    """A2A v0.3 Agent Card (完整 schema, iCoDer 实现)."""
    
    # 必填字段
    name: str                          # Agent 显示名
    description: str                   # Agent 功能描述
    url: str                           # message:send 端点 URL
    
    # 推荐字段
    version: str = "1.0.0"             # Agent 版本 (semver)
    provider: str = "iCoDer"           # 提供方 (iCoDer 固定)
    documentation_url: str = ""        # Agent 文档 URL
    
    # A2A v0.3 必填字段
    capabilities: AgentCapabilities    # Agent 能力声明
    skills: list[AgentSkill]           # Agent 技能列表 (vs capabilities 更具体)
    defaultInputModes: list[str]       # 默认输入模式 ["text", "data", "file"]
    defaultOutputModes: list[str]      # 默认输出模式 ["application/json"]
    securitySchemes: dict              # 安全方案 (Phase 1 预留, Phase 4 校验)
    
    # iCoDer 特有扩展 (在 metadata 命名空间)
    metadata: dict = {}                # iCoDer 字段: rule_sets / non_goals / ...
```

### 8.2 子结构

```python
class AgentCapabilities(BaseModel):
    """Agent 能力声明."""
    streaming: bool = False            # 是否支持 message/stream (Phase 5)
    pushNotifications: bool = False    # 是否支持 push notifications (Phase 6)
    stateTransitionHistory: bool = True  # 是否暴露 state history (iCoDer 必为 true, 审计需要)
    extensions: list[dict] = []        # 自定义扩展 (Phase 1 不用)


class AgentSkill(BaseModel):
    """Agent 技能 (比 capabilities 更具体, 带 input/output schema)."""
    id: str                            # 技能 ID (在 Agent 内唯一)
    name: str                          # 技能名
    description: str                   # 技能描述
    input_schema: dict = {}            # 输入 JSON schema (e.g., MedicalCodingInputSchema)
    output_schema: dict = {}           # 输出 JSON schema (e.g., MedicalCodingOutputSchema)
    examples: list[dict] = []          # 使用示例 (LLM 友好)


class SecurityScheme(BaseModel):
    """安全方案定义 (A2A v0.3 规范, Phase 4 才用)."""
    type: str                          # "apiKey" / "oauth2" / "mutualTLS" / "none"
    description: str = ""
    # ... 其他字段按 type 而定
```

### 8.3 真实样板 (homepage-coding-review, Phase 1)

```json
{
  "name": "Homepage Coding Review Agent",
  "description": "病案首页编码审核 Agent。给定病历文本, 输出主诊断/次诊断/手术编码, 标注高风险易错码, 生成 DRG/DIP 分组建议, 全链路审计。",
  "url": "/api/icoder/agents/homepage-coding-review/v1/message:send",
  "version": "1.0.0",
  "provider": "iCoDer",
  "documentation_url": "/docs/agents/homepage-coding-review",
  
  "capabilities": {
    "streaming": false,
    "pushNotifications": false,
    "stateTransitionHistory": true,
    "extensions": []
  },
  
  "skills": [
    {
      "id": "icd_coding",
      "name": "ICD-10-CN / ICD-9-CM-3 编码审核",
      "description": "从病历抽取诊断和手术, 映射到 ICD-10-CN / ICD-9-CM-3",
      "input_schema": { "type": "object", "properties": { "text": { "type": "string" } } },
      "output_schema": { "$ref": "icoder/MedicalCodingOutputSchema/v1" },
      "examples": [
        {
          "input": { "text": "患者男 65 岁, 急性前壁心梗 3 小时" },
          "output": { "primary_diagnosis": { "code": "I21.0" } }
        }
      ]
    },
    {
      "id": "drg_grouping",
      "name": "CHS-DRG / DIP 分组",
      "description": "基于诊断和手术, 计算 CHS-DRG 入组路径 + DIP 病种",
      "input_schema": { ... },
      "output_schema": { ... },
      "examples": []
    }
  ],
  
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["application/json"],
  
  "securitySchemes": {
    "bearer": {
      "type": "apiKey",
      "description": "Phase 4 才校验, Phase 1 接受任意 bearer"
    }
  },
  
  "metadata": {
    "icoder": {
      "rule_sets": ["medical_coding", "drg_dip", "audit"],
      "non_goals": [
        "不直接做最终诊断决策",
        "不写回 EMR/HIS",
        "不评估模型效果"
      ],
      "experts": ["coding-expert", "drg-expert", "compliance-expert"],
      "production_writeback_blocked": true,
      "phi_redaction": "required"
    }
  }
}
```

---

## 9. iCoDer 特有扩展 (在 metadata 命名空间)

按 Q2 决策"不写 iCoDer 私有协议扩展", 所有 iCoDer 特有字段都塞在 A2A `metadata` 命名空间, **不污染 A2A spec**。

### 9.1 Orchestrator → Expert metadata

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `delegated_by` | string | ✅ | 格式: `orchestrator-{run_id}`, 让 Expert 知道这是 Orchestrator 委托 |
| `expert_required` | bool | ⚠ | true = 关键 Expert, 失败 = 整体 fail; false = 非关键, 失败 = skip |
| `tool_constraints` | list[string] | ❌ | 限制 Expert 可调工具 (严格模式) |
| `timeout_ms` | int | ⚠ | 单 Expert 超时, 默认 30000 |
| `retry_policy` | dict | ❌ | 重试策略 (Phase 1 不实现, 走 Orchestrator 默认) |

### 9.2 Orchestrator → Client metadata (响应里)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `run_id` | string | ✅ | M2aRecorder run ID, 客户端可用于查完整 trace |
| `trace_id` | string | ✅ | M2aRecorder trace ID |
| `trace_url` | string | ✅ | `/api/m2a/runs/{run_id}` 完整 URL |
| `phi_redacted` | bool | ✅ | true = LLM 只见脱敏文本, 客户端**不应**在 UI 渲染原始 PHI |
| `production_writeback_blocked` | bool | ✅ | 恒 true, 提醒客户端此 Agent 不写回生产 |
| `state_history` | list[string] | ✅ | 状态机状态序列 (审计/调试用) |
| `expert_invocations` | list[dict] | ⚠ | 每个 Expert 的调用记录 (id / latency_ms / status) |
| `llm_model` | string | ⚠ | 实际用的 LLM 模型 (e.g., "deepseek-v4-flash") |
| `total_duration_ms` | int | ⚠ | 完整 run 时延 |

### 9.3 Orchestrator → Expert 业务 schema 标识符

| Schema 标识符 | 用途 |
|--------------|------|
| `icoder/MedicalCodingOutputSchema/v1` | 编码审核输出 (复用既有 schema.py) |
| `icoder/MedicalCodingInputSchema/v1` | 编码审核输入 (Phase 1 不单独定义, 走 TextPart) |
| `icoder/DrgGroupingOutputSchema/v1` | DRG 分组输出 (Phase 2 才用) |
| `icoder/ComplianceOutputSchema/v1` | 合规审计输出 (Phase 2 才用) |
| `icoder/EvidenceSpan/v1` | 证据回链 (既有, 见 schema.py) |

**关键**: schema 标识符是 URI 风格, **iCoDer 自行定义**, A2A spec 不规定具体 schema。

---

## 10. 协议版本管理

### 10.1 A2A 协议版本

- 当前实现: **A2A v0.3** (2026-06 stable)
- 升级路径: 跟 Corti 同步, 未来 A2A v0.4 / v1.0 发布时, 整体升级
- 兼容性: 同一 minor version 内向后兼容 (v0.3.x); 跨 minor version 不保证 (v0.3 → v0.4)
- 协议头: `A2A-Protocol-Version: 0.3` (强制)

### 10.2 iCoDer 内部版本

- Agent Card 的 `version` 字段: iCoDer Agent 自身版本 (semver)
- Agent metadata 的 `icoder.runtime_version`: iCoDer Runtime 版本 (e.g., "1.0.0")
- Orchestrator 端点: `/v1/...` 路径中 `v1` 是 iCoDer 端点主版本

### 10.3 版本不兼容处理

| 场景 | 行为 |
|------|------|
| 客户端送 A2A v0.2, 服务端 v0.3 | 接受请求, 按 v0.3 处理; 响应头加 `A2A-Protocol-Version: 0.3` |
| 客户端送 A2A v0.4 (未来), 服务端 v0.3 | 接受请求, 按 v0.3 处理; 响应头加 `A2A-Protocol-Version: 0.3` (降级) |
| 客户端送完全未知版本 (v0.99) | 拒绝, `INVALID_REQUEST` + 提示 "A2A v0.3 only" |
| 服务端升级到 v0.4 时 | 保留 v0.3 端点 6 个月 (deprecation header), 同时暴露 v0.4 端点 |

---

## 11. 测试要求

### 11.1 单元测试 (≥40 cases)

**文件**: `backend/tests/unit/icoder/a2a/test_protocol.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **JSON-RPC 信封** | 请求/响应/错误/批处理 (批处理 Phase 1 不实现) | 6 |
| **Part 类型** | TextPart/DataPart/FilePart 解析 + 校验 | 5 |
| **错误码** | 8 类 A2A 错误码 + 5 类 JSON-RPC 标准错误码 | 8 |
| **Agent Card schema** | 必填字段校验 + 默认值 + iCoDer metadata 扩展 | 5 |
| **schema 标识符** | `icoder/MedicalCodingOutputSchema/v1` 等 5 个标识符解析 | 5 |
| **iCoDer metadata** | run_id/trace_id/trace_url/phi_redacted/production_writeback_blocked 字段序列化 | 5 |
| **协议版本头** | `A2A-Protocol-Version: 0.3` 校验 + 缺失/错误处理 | 3 |
| **HTTP header** | Content-Type / X-Request-ID / X-Trace-Context 解析 | 3 |

**总计**: 40 单元测试

### 11.2 集成测试 (≥12 cases)

**文件**: `backend/tests/integration/icoder/a2a/test_endpoints.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **入站 message:send** | 1 条病历 → Orchestrator → 响应含完整 DataPart | 1 |
| **入站错误路径** | 5 类错误 (格式错 / method 错 / params 错 / agent_id 不存在 / PHI 失败) | 5 |
| **出站 message:send** | Orchestrator 委托 → Expert 返回, metadata.delegated_by 透传 | 1 |
| **Discovery: /.well-known/agent.json** | 返回 Agent 列表, 含 iCoDer 1 Agent | 1 |
| **Discovery: /api/icoder/agents/{id}/card** | 返回单 Agent 完整 Card | 1 |
| **Discovery: /llms.txt** | 返回 LLM 友好 Markdown | 1 |
| **Discovery: /api/icoder/agents?capability=xxx** | 按能力过滤 | 1 |
| **Task stub** | GET /tasks/{id} / POST /tasks/{id}/cancel 返回 501 | 1 |

**总计**: 12 集成测试

### 11.3 e2e 测试 (1 case, 与 Orchestrator e2e 合并)

**文件**: `backend/tests/e2e/icoder/test_a2a_e2e.py`

| 测试 | 覆盖 |
|------|------|
| **curl 模拟客户端 → A2A 端点 → 真实 DeepSeek → A2A 响应** | 验证: Content-Type / A2A-Protocol-Version 头 + JSON-RPC 2.0 信封 + Message.kind=message + DataPart 含 MedicalCodingOutputSchema + metadata.run_id 可查 trace |

**总计**: 1 e2e (与 Orchestrator spec 的 1 e2e 是同一个, A2A spec 复用)

### 11.4 测试矩阵汇总

| 层级 | 数量 | Phase 1 必需 |
|------|------|--------------|
| 单元 | 40 | ✅ |
| 集成 | 12 | ✅ |
| e2e | 1 (与 Orchestrator 共享) | ✅ |
| **小计** | **53** | |

加上 Orchestrator spec 的 44 + 1227 baseline = **1324+**。

---

## 12. 实现路径 (Phase 1 落地)

### 12.1 文件结构 (新增 + 重做)

```
backend/app/icoder/agent_runtime/a2a/
├── __init__.py
├── envelope.py                  # JSON-RPC 2.0 信封 (parse / serialize / validate)
├── parts.py                     # TextPart / DataPart / FilePart 数据类
├── messages.py                  # A2A Message / Task 数据类
├── agent_card.py                # A2A v0.3 AgentCard 数据类 (重做旧 a2a_protocol.py)
├── errors.py                    # A2A 错误码 (8 类业务 + 5 类 JSON-RPC 标准)
├── routes_inbound.py            # POST /v1/message:send (入站)
├── routes_outbound.py           # POST /internal/experts/.../v1/message:send (出站)
├── routes_discovery.py          # /.well-known/agent.json + /llms.txt + /api/icoder/agents
├── routes_task_stub.py          # /tasks/{id} + /tasks/{id}/cancel (Phase 1 stub)
├── icoder_metadata.py           # iCoDer 特有 metadata 字段 (run_id / trace_url / ...)
├── schema_registry.py           # icoder/MedicalCodingOutputSchema/v1 等 schema 标识符
├── version.py                   # 协议版本头 + 版本协商
└── icoder_schemas/              # iCoDer schema 标识符定义
    ├── medical_coding.py
    ├── drg_grouping.py
    ├── compliance.py
    └── evidence.py

backend/app/icoder/agent_runtime/
├── __init__.py
├── a2a_routes.py                # A2A 路由总挂载
└── (其他 4 spec 实现: orchestrator/ context/ tasks/ mcp/ agent_card/)

backend/tests/unit/icoder/a2a/
├── test_protocol.py             # 40 单元测试
├── test_agent_card.py
├── test_parts.py
├── test_envelope.py
└── test_errors.py

backend/tests/integration/icoder/a2a/
└── test_endpoints.py            # 12 集成测试

backend/tests/e2e/icoder/
└── test_a2a_e2e.py              # 1 e2e (与 Orchestrator 共享, 实际写 1 个)

# 废弃
backend/app/services/a2a_protocol.py  # Q5 决策: 完全废弃, 不做兼容
```

### 12.2 依赖

| 依赖 | 已有? | 用途 |
|------|-------|------|
| `pydantic v2` | ✅ | AgentCard / Message / Part 数据类 |
| `fastapi` | ✅ | HTTP 路由 |
| `httpx` (async) | ✅ | 出站 A2A 调用 (Orchestrator → Expert) |
| `python-ulid` 或 `uuid` | ✅ | run_id / contextId / messageId |
| A2A v0.3 spec 校验库 | ❌ 需引入 | 验证 A2A 消息体合规 (或自写 validator) |

### 12.3 实施顺序 (Phase 1 内部)

1. **A1**: envelope.py + parts.py + messages.py + errors.py (核心数据类, 单元测试可写)
2. **A2**: agent_card.py (v0.3 schema 完整, 单元测试)
3. **A3**: icoder_metadata.py + schema_registry.py (iCoDer 扩展, 单元测试)
4. **A4**: version.py (协议版本头, 单元测试)
5. **A5**: routes_inbound.py (入站 message:send, 集成测试)
6. **A6**: routes_outbound.py (出站 message:send, 集成测试)
7. **A7**: routes_discovery.py (4 个 discovery 端点, 集成测试)
8. **A8**: routes_task_stub.py (Task 端点 stub, 集成测试)
9. **A9**: e2e test (与 Orchestrator 共享, 真实 DeepSeek 跑通)
10. **A10**: 废弃旧 `a2a_protocol.py` (Q5 决策: 完全删除, 不保留)

每个 A = 1 个 PR, A1-A9 全过才进 Phase 2。

### 12.4 与 Orchestrator spec 的衔接

| Orchestrator spec 章节 | A2A spec 提供 |
|----------------------|--------------|
| §3.2 数据流 步骤 1 (Client 请求) | §7.2 入站 message:send 端点 |
| §3.2 数据流 步骤 2-6 (Orchestrator 内部) | (Orchestrator 内部, A2A 不管) |
| §5.1 入站接口契约 | §7.2 (URL / Request / Response 样板) |
| §5.2 出站接口契约 | §7.3 (URL / Request / Response 样板 + metadata.delegated_by) |
| §5.1.3 错误码 | §6 (8 类 A2A 错误码) |
| §11 RFC 映射 §5 节 "A2A Protocol" | 全部 |

---

## 13. 开放问题 (本 spec 级别)

| # | 问题 | 选项 | 倾向 |
|---|------|------|------|
| Q-A1 | A2A v0.3 spec 校验: 严格 (拒绝任何不合规) vs 宽松 (warn)? | 倾向: **严格**, 不合规直接 `INVALID_REQUEST` | |
| Q-A2 | A2A 协议版本头: 必填 vs 可选? | 倾向: 必填, 缺失 = `INVALID_REQUEST` | |
| Q-A3 | 出站 Orchestrator → Expert 失败重试: Orchestrator 负责 vs Expert 端负责? | 倾向: **Orchestrator 负责** (单一责任, Expert 端不重试) | |
| Q-A4 | Discovery `/.well-known/agent.json`: 单 Agent vs 多 Agent? | 倾向: 单 Agent (URL 路径 = agent_id), 多 Agent 走 `/api/icoder/agents` | |
| Q-A5 | iCoDer schema 标识符命名空间: `icoder/...` vs `https://icoder.cn/schemas/...`? | 倾向: `icoder/...` (简短, 内部用) | |
| Q-A6 | Auth: Phase 1 是否完全跳过 (不校验 Authorization header)? | 倾向: **跳过**, 接受任意 header, Phase 4 才接 | |
| Q-A7 | 旧 `a2a_protocol.py` 30 预置 Expert 怎么办? | 倾向: **完全删除** (Q5 决策), 改从 AgentDefinition 动态加载 (Phase 2-3 接入) | |
| Q-A8 | Agent Card `extensions` 字段 (A2A v0.3 可选) 是否用? | 倾向: 不用, iCoDer 字段全走 `metadata` | |
| Q-A9 | FilePart 缺失的 backward compat 怎么办? | 倾向: Phase 1 直接不实现, 客户端送 FilePart = `INVALID_REQUEST` | |
| Q-A10 | 出站端点 `/internal/experts/...` 访问控制: 同进程 vs IP 白名单? | 倾向: **同进程** (内部函数调用, 不走 HTTP), 出站端点只为 A2A spec 验证 | |

---

## 14. 与 RFC 映射 (验收对齐)

| RFC 章节 | 本 spec 章节 | 验证方式 |
|----------|--------------|----------|
| 3.2.3 A2A Protocol (Q2) | 全部 | 1324+ tests 全绿 |
| 3.3 协议版本锁定 (A2A v0.3) | §3 / §10 | 单元测试: 协议版本头校验 |
| 5 节映射表 A2A 行 | §7 / §12 | 集成测试: 4 类端点全覆盖 |
| 9.2 W2 (协议对齐写法) | §1.2 / §1.3 | 全部按 A2A v0.3 spec 写, 不写 iCoDer 私有扩展 |
| 9.2 W3 (旧 API deprecation) | §1.3 (旧 a2a_protocol.py 完全废弃) | 集成测试: 旧文件删除, 旧路由加 deprecation header |
| 9.2 W5 (Expert metadata 公开) | §8.3 / §9.3 | 集成测试: Agent Card 包含 experts[] 列表 |
| 10.1 Phase 1 成功标准 | §11.4 | 53 cases 全绿 |
| 10.2 v1 完成时 | (Phase 4-5 才完整) | Task stub 转实现 + Auth 接入 |

---

## 15. 参考

### 15.1 战略 RFC 与上游 spec

- `E:\Corti4C\docs\ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20)
  - 第 3.2.3 节: A2A Protocol 目标形态
  - 第 3.3 节: 协议版本锁定
  - 第 9 节: Q2 决策
- `E:\Corti4C\docs\ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft 2026-06-20)
  - 第 5.1 节: 入站接口契约
  - 第 5.2 节: 出站接口契约
  - 第 5.1.3 节: 错误码

### 15.2 A2A 协议官方

- A2A Protocol v0.3 spec: `https://a2a-protocol.org/v0.3/spec` (Linux Foundation 维护)
  - JSON-RPC 2.0 envelope
  - Part types (TextPart / DataPart / FilePart)
  - Message / Task
  - AgentCard schema
  - Discovery `/.well-known/agent.json`
  - Error codes

### 15.3 Corti 官方文档

- `E:\Corti4C\Corti\llms-full.txt`
  - `/agentic/a2a-protocol` - A2A 协议
  - `/agentic/agents/send-message-to-agent` - message:send 端点
  - `/agentic/faq` - A2A vs MCP

### 15.4 iCoDer 既有代码

- `backend/app/services/a2a_protocol.py` - 旧 A2A (Q5 决策: 完全重做, 不保留)
- `backend/official_agents/medical_coding/schema.py` - MedicalCodingOutputSchema (DataPart value 用)
- `backend/icoder_runtime/m2a/recorder.py` - M2aRecorder (run_id / trace_id 来源)
- `backend/icoder_runtime/agents/registry.py` - AgentRegistry (AgentDefinition 来源)

### 15.5 iCoDer 战略线索

- 2026-06-20: 100% Corti 复刻 + 10 决策 (Q2: A2A v0.3)
- 2026-06-17: 战略转向 (v1=托管云)
- 2026-06-14: 原子能力架构
- 2026-06-13: icoder-next 切片开工

---

## 16. 签字 (待审)

| 角色 | 签字 | 日期 |
|------|------|------|
| 架构组 | ___ | ___ |
| 工程 owner | ___ | ___ |
| 安全/合规 | ___ | ___ |

---

**本 spec 拍板后**:
1. 起 `ICODER_V1_CONTEXT_SPEC.md` (contextId 数据模型 + 隔离, 本 spec §7.2/§7.3 引用)
2. 起 `ICODER_V1_TASK_SPEC.md` (Task Service, 本 spec §7.5 留 stub)
3. 起 `ICODER_V1_MCP_SPEC.md` (并行, Expert ↔ 工具)
4. 起 `ICODER_V1_AGENT_CARD_SPEC.md` (并行, Registry 公开)
5. 6 spec 全部拍板 → Phase 1 实施 (A1-A10, 加上 Orchestrator 的 T1-T10)
