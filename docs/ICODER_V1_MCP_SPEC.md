# iCoDer v1 MCP Spec

**作者**: iCoDer 架构组
**日期**: 2026-06-20
**状态**: Draft (待审, Phase 1 spec 之四)
**范围**: iCoDer v1 MCP (Model Context Protocol) 实现 — JSON-RPC 2.0 信封、Tools/Resources/Prompts 声明、Transport (stdio + HTTP)、iCoDer 作为 MCP server 暴露的 8+ 工具、Expert 作为 MCP client 调工具、工具发现、错误处理、安全隔离
**前置**:
- `ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20, Q3 决策)
- `ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft, §5.2 出站委托引用本 spec)
- `ICODER_V1_A2A_SPEC.md` (Draft, JSON-RPC 2.0 信封模式对齐)
- `ICODER_V1_CONTEXT_SPEC.md` (Draft, 安全隔离引用 contextId)
**并行可写**: `ICODER_V1_AGENT_CARD_SPEC.md`
**后续**: `ICODER_V1_TASK_SPEC.md`

---

## 0. 文档目的

把 RFC 第 3.2.4 节"MCP Protocol"和 Q3 决策（MCP 协议对齐 Corti 2025-03-26）展开成**可实现的详细 spec**: MCP 2025-03-26 spec 核心子集、Tools 声明 (JSON schema)、Resources/Prompts 概念、Transport 选择（stdio 本地进程 + HTTP 远程）、iCoDer 作为 MCP server 暴露的工具集（coding 4 + drg 4 + ICD 字典 + BGE-M3 + 编码指南 + DRG/DIP 分组器 + PHI 工具）、Expert 作为 MCP client 调工具流程、工具发现、错误处理、安全隔离（按 contextId）、测试矩阵。

本 spec 是 RFC Q3 的核心落地文档, 与 Orchestrator spec 的 §5.2 出站委托 + A2A spec 的 JSON-RPC 信封 都紧耦合。

---

## 1. 背景与决定

### 1.1 上游决定 (从 RFC 来)

| 决策 | 拍板 | 对本 spec 的影响 |
|------|------|------------------|
| **Q3** MCP 协议对齐 Corti (2025-03-26) | RFC 第 9 节 | 本 spec 严格按 MCP 2025-03-26 spec 实现, 不写 iCoDer 私有扩展 |
| **Q4** Context 隔离对齐 Corti | RFC 第 9 节 | MCP tool call 必带 contextId, 工具结果按 contextId 隔离 (不允许跨 contextId 命中) |
| **Q7** Expert 独立 + 可共享 | RFC 第 9 节 | Expert 自己的 system_prompt 注入, MCP tool 调用的 system_prompt 不被 Orchestrator 覆盖 |
| **Q5** 旧 AgentRunner 不保留, clean replace | RFC 第 9 节 | 既有 `coding_expert.py` / `drg_expert.py` (Python 函数) **重做** 为 MCP server, 不保留 fallback |

### 1.2 MCP 2025-03-26 协议参考

- **维护方**: Anthropic (原 Model Context Protocol)
- **最新稳定版**: 2025-03-26
- **传输**: JSON-RPC 2.0 over stdio (本地进程) 或 HTTP (远程)
- **核心概念**:
  - **Server**: 暴露 Tools / Resources / Prompts (iCoDer 多领域用)
  - **Client**: 调用 Server 提供的 Tools / 读 Resources / 用 Prompts (iCoDer Expert 用)
  - **Tools**: LLM 可调用的"动作" (e.g., `search_icd`, `verify_code`, `group_drg`)
  - **Resources**: 文件/数据源 (e.g., ICD 字典文件, 编码指南 PDF)
  - **Prompts**: 可复用 prompt 模板 (e.g., `coding_review_prompt`)
- **核心方法** (MCP spec):
  - `initialize` — Client 初始化, 协商协议版本 + 能力
  - `tools/list` — 列出 Server 提供的所有 tools
  - `tools/call` — 调用某个 tool
  - `resources/list` — 列出 resources
  - `resources/read` — 读 resource
  - `prompts/list` — 列出 prompts
  - `prompts/get` — 取 prompt
  - `notifications/initialized` — 初始化完成通知

### 1.3 iCoDer MCP 工具来源

iCoDer 既有 (从 CLAUDE.md + icoder-next 整理):

| 工具 | 来源 | 用途 |
|------|------|------|
| ICD-10-CN 字典 (37,897 码) | `E:\iCoDerA\icd10cn_code_catalog.json` (只读) | 编码字典 |
| ICD-9-CM-3 字典 | (iCoDer 既有) | 手术编码 |
| 编码指南 KB | `E:\iCoDerA\evidence_anchoring_kb.json` | 编码规则 |
| 易错码 KB | `E:\iCoDerA\coding_differentiation_kb.json` | 编码鉴别 |
| BGE-M3 + FAISS 索引 | `data/medcoder/faiss.index` (既有) | 语义检索 |
| CHS-DRG 分组器 | `icoder-next/backend/icoder/experts/grouping_expert.py` (语义保留) | DRG 入组 |
| DIP 路径 | 同上 | DIP 病种 |
| PHI 脱敏 | `icoder-next/backend/icoder/safety/redactor.py` | PHI 替换 |

**结论**: iCoDer 既有工具全部**重做** 为 MCP server (Q5 决策), 工具语义保留, 实现改 MCP。

### 1.4 关键边界 (从 RFC 1.3 + 4.4 来)

- `production_writeback_blocked = true` 恒定 (MCP tools 全部 read-only, 没有任何"写回"工具)
- PHI 脱敏: 工具不接触原文 (原文不进 tool call input, 只进 audit)
- LLM 不绑定厂商 (MCP 工具与 LLM 无关, LLM 通过 Expert 调用, Expert 通过 MCP 调工具)

---

## 2. 目标 / 非目标

### 2.1 Goals (本 spec 必须达成)

1. **G1**: 严格对齐 MCP 2025-03-26 spec 核心子集 (§3 范围)
2. **G2**: iCoDer 作为 MCP **server** 暴露 8+ 工具 (coding 4 + drg 4 + PHI)
3. **G3**: iCoDer Expert 作为 MCP **client** 调工具流程完整
4. **G4**: Transport 双支持 (stdio 本地进程 + HTTP 远程)
5. **G5**: Tool 声明按 JSON schema (name / description / inputSchema)
6. **G6**: Tool call 必带 contextId, 按 contextId 隔离 (Q4)
7. **G7**: 工具发现 (tools/list) 完整 + 动态加载
8. **G8**: MCP 错误码全集 (与 MCP spec 一致)
9. **G9**: PHI 强制脱敏 (tool input 必 redacted)
10. **G10**: 测试矩阵明确 (单元/集成/e2e)

### 2.2 Non-Goals (本 spec 明确不做)

1. **N1**: 不实现 MCP spec 全集 (Phase 1 子集: 只 Tools, Resources/Prompts 留 Phase 4/5)
2. **N2 (REMOVED 2026-07-05, Phase 3-C1)**: OAuth / API Key auth 现已实现 —
   见 §10 "MCP Auth (Phase 3-C1, 2026-07-05)"。支持 4 种 auth 类型:
   `none` / `bearer` / `inherit` / `oauth2.0` (client_credentials grant)。
3. **N3**: 不实现 MCP Sampling (LLM-from-MCP, 反向, Phase 6)
4. **N4**: 不实现 MCP Roots (文件系统访问, Phase 4)
5. **N5**: 不实现第三方 MCP server 注册 (Phase 4, Phase 1 只内置)
6. **N6**: 不重写 Orchestrator (Orchestrator spec 范围)
7. **N7**: 不实现 8 原子 Agent 迁移 (Phase 3, 本 spec 只 protocol 本身)
8. **N8**: 不实现 MCP over WebSocket (MCP spec 2025-03-26 不支持, 留 Phase 6)

---

## 3. MCP 2025-03-26 协议实现范围 (Phase 1 子集)

| MCP 组件 | Phase 1 状态 | 备注 |
|----------|--------------|------|
| **JSON-RPC 2.0 信封** | ✅ 完整实现 | 复用 A2A spec §4 模式 |
| **Server** | ✅ 完整实现 | iCoDer 作为 server, 暴露 8+ 工具 |
| **Client** | ✅ 完整实现 | iCoDer Expert 作为 client |
| **Transport: stdio** | ✅ 完整实现 | 本地进程, 默认 |
| **Transport: HTTP** | ✅ 完整实现 | 远程服务, 可选 |
| **`initialize` 方法** | ✅ 完整实现 | 协商协议版本 + 能力 |
| **`tools/list` 方法** | ✅ 完整实现 | 列出 tools |
| **`tools/call` 方法** | ✅ 完整实现 | 调用 tool |
| **`resources/list` / `resources/read`** | ❌ 端点暴露, 不实现 | Phase 4 留 |
| **`prompts/list` / `prompts/get`** | ❌ 端点暴露, 不实现 | Phase 5 留 |
| **`notifications/initialized`** | ✅ 完整实现 | 通知用 |
| **Tool 声明 (JSON schema)** | ✅ 完整实现 | name / description / inputSchema |
| **错误码 (MCP spec)** | ✅ 完整实现 | 见 §6 |
| **`securitySchemes`** | ✅ Phase 3-C1 实现 | 4 auth types: none / bearer / inherit / oauth2.0 |
| **Tools 缓存** | ❌ 不实现 | Phase 1 实时查, Phase 5 加缓存 |

---

## 4. JSON-RPC 2.0 信封 (MCP 模式)

### 4.1 Request (Client → Server)

```json
{
  "jsonrpc": "2.0",
  "id": "uuid-or-string-or-number",
  "method": "tools/call",
  "params": {
    "name": "search_icd",
    "arguments": {
      "term": "急性心梗",
      "top_k": 5
    },
    "_meta": {
      "contextId": "550e8400-e29b-41d4-a716-446655440000",
      "agent_id": "homepage-coding-review"
    }
  }
}
```

**关键 (Q4 隔离)**:
- `_meta.contextId` 必填, 服务端按 contextId 隔离缓存/状态
- `_meta.agent_id` 必填, 用于审计追踪

### 4.2 Response (成功)

```json
{
  "jsonrpc": "2.0",
  "id": "echo-of-request-id",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"hits\": [{\"code\": \"I21.0\", \"display\": \"急性前壁心肌梗死\", \"score\": 0.95}]}"
      }
    ],
    "isError": false,
    "_meta": {
      "tool_invocation_id": "tool-inv-uuid",
      "contextId": "550e8400-e29b-41d4-a716-446655440000",
      "duration_ms": 42
    }
  }
}
```

**关键**: `content` 数组里每个 element 是 `{type, text}` (text) 或 `{type, data, mimeType}` (binary/structured), 与 A2A Part 风格一致 (但 MCP 单独定义)。

### 4.3 Error Response (MCP spec)

```json
{
  "jsonrpc": "2.0",
  "id": "echo-of-request-id",
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": {
      "mcp_error_code": "INVALID_TOOL_ARGUMENTS",
      "details": "term must be non-empty string",
      "tool_name": "search_icd"
    }
  }
}
```

### 4.4 HTTP Headers (MCP HTTP transport)

| Header | 方向 | 值 | 必填 |
|--------|------|---|------|
| `Content-Type` | 双向 | `application/json` | ✅ |
| `MCP-Protocol-Version` | 双向 | `2025-03-26` | ✅ |
| `X-Request-ID` | Request | UUID | ⚠ 建议 |
| `X-Trace-Context` | Request | W3C trace context | ⚠ 建议 |

---

## 5. Tools 声明 (JSON Schema)

### 5.1 Tool 声明结构

```python
class Tool(BaseModel):
    """MCP 2025-03-26 Tool declaration."""
    name: str                                # 工具名 (e.g., "search_icd")
    description: str                         # 工具描述 (LLM 阅读用)
    inputSchema: dict                        # JSON Schema (input 校验)
    # 不实现 (Phase 1 不需要)
    # annotations: ToolAnnotations | None
    # _meta: dict | None
```

### 5.2 Example: `search_icd` Tool 声明

```json
{
  "name": "search_icd",
  "description": "按术语检索 ICD-10-CN / ICD-9-CM-3 编码 (支持同义词扩展). 返回 top-K 候选编码, 包含 code / display / score / system.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "term": {
        "type": "string",
        "description": "检索词 (中文 / 英文疾病名 / 同义词)"
      },
      "system": {
        "type": "string",
        "enum": ["icd10cn", "icd9cm3", "both"],
        "default": "both",
        "description": "目标编码体系"
      },
      "top_k": {
        "type": "integer",
        "default": 5,
        "minimum": 1,
        "maximum": 30
      },
      "include_synonyms": {
        "type": "boolean",
        "default": true
      }
    },
    "required": ["term"],
    "additionalProperties": false
  }
}
```

### 5.3 工具返回格式 (统一)

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"hits\": [{\"code\": \"I21.0\", \"display\": \"急性前壁心肌梗死\", \"system\": \"icd10cn\", \"score\": 0.95, \"chapter\": \"循环系统疾病\"}]}"
    }
  ],
  "isError": false
}
```

**约定**: 所有工具返回 `content[0].text` 为 JSON 字符串, 客户端解析。`isError=true` 表示工具调用成功但业务报错 (e.g., 找不到匹配项)。

---

## 6. 错误码 (MCP spec)

### 6.1 JSON-RPC 标准错误码

| `code` | 含义 | 触发 |
|--------|------|------|
| `-32700` | Parse error | 请求体不是合法 JSON |
| `-32600` | Invalid request | 不是合法 JSON-RPC 2.0 请求 |
| `-32601` | Method not found | `method` 不在 MCP spec 范围 |
| `-32602` | Invalid params | `params` 字段不合法 (缺必填 / 类型错) |
| `-32603` | Internal error | MCP server 内部错误 |
| `-32000` ~ `-32099` | Server error | 业务错误 (MCP 自定义) |

### 6.2 MCP 业务错误码 (`error.data.mcp_error_code`)

| MCP 错误码 | 触发 |
|-----------|------|
| `TOOL_NOT_FOUND` | `tools/call` 时 `name` 不存在 |
| `INVALID_TOOL_ARGUMENTS` | `tools/call` 时 `arguments` 不通过 inputSchema 校验 |
| `TOOL_EXECUTION_FAILED` | 工具执行失败 (e.g., ICD 字典加载失败) |
| `CONTEXT_REQUIRED` | `tools/call` 缺 `_meta.contextId` (Q4 强制) |
| `CONTEXT_INVALID` | `_meta.contextId` 格式错或已 expire |
| `PHI_DETECTED` | tool input 检测到未脱敏 PHI (iCoDer 特有) |
| `RATE_LIMITED` | 工具调用频次超限 (Phase 6 留) |
| `TIMEOUT` | 工具调用超时 (默认 30s) |

### 6.3 MCP Auth 错误码 (Phase 3-C1, 2026-07-05 新增 7 个)

| Wire code | MCP 错误码 | HTTP | 触发 |
|-----------|-----------|------|------|
| `-32006` | `mcp_auth_duplicate_name` | 400 | `tools/list` 重复 tool name |
| `-32007` | `mcp_auth_missing_name` | 400 | `tools/call` 缺 `name` 字段 |
| `-32008` | `mcp_auth_missing_token` | 401 | bearer / inherit 缺 token |
| `-32009` | `mcp_auth_missing_credentials` | 401 | oauth2.0 缺 client_id / secret |
| `-32010` | `mcp_auth_invalid_oauth_config` | 400 | oauth2.0 配置字段非法 |
| `-32011` | `mcp_auth_token_exchange_failed` | 401 | oauth2.0 token exchange 失败 (HTTP non-200) |
| `-32012` | `mcp_auth_forbidden` | 403 | token 有效但无权调该 tool |

**Redaction 要求**: 任何 auth 错误的 `data.details` 字段都不得包含 raw token / client_secret / bearer 值. 仅可包含 `redacted_view` (e.g., `"Bearer ••••1234"`). 见 §11.6.

---

## 7. Transport (stdio + HTTP)

### 7.1 stdio (本地进程, 默认)

**适用场景**: iCoDer 内置工具 (ICD 字典 / BGE-M3 / 编码指南), 同进程调用

**实现**:
- MCP server 启动为子进程 (subprocess)
- Client (Expert) 通过 stdin/stdout 与 server 通信
- JSON-RPC 2.0 over newline-delimited JSON (每行一个 JSON 对象)
- 启动命令: `python -m icoder.mcp.servers.icd_server --transport stdio`

**优点**:
- 低时延 (同进程)
- 简单 (无 HTTP)
- 安全 (进程隔离)

**缺点**:
- 不可跨进程 (虽然同进程, 但子进程, 不能跨服务器)
- 不可第三方贡献 (Phase 1 不需要)

### 7.2 HTTP (远程服务, 可选)

**适用场景**: 第三方 ISV 提供的 MCP server (Phase 4 才用), 远程工具服务

**实现**:
- MCP server 启动 HTTP server (e.g., FastAPI on port 8001)
- Client (Expert) 通过 HTTP POST 调用
- URL: `POST /mcp/v1/tools/call`
- 协议头: `MCP-Protocol-Version: 2025-03-26`

**优点**:
- 可跨进程
- 可跨服务器
- 可第三方贡献

**缺点**:
- 时延高 (HTTP)
- 安全 (需 auth, Phase 4)

### 7.3 iCoDer Phase 1 选择

**Phase 1 默认 stdio** (本地内置工具), HTTP 端点暴露但暂不实现 (Phase 4)。

| 工具 | Phase 1 Transport | Phase 4+ |
|------|-------------------|----------|
| ICD 字典 / 编码指南 / 易错码 | stdio | HTTP (可选) |
| BGE-M3 + FAISS | stdio (同进程, 快) | HTTP (可选) |
| DRG / DIP 分组器 | stdio | HTTP (可选) |
| PHI 脱敏 | stdio | HTTP (可选) |
| 第三方 ISV 工具 | (Phase 1 不存在) | HTTP |

---

## 8. iCoDer 工具集 (Phase 1 必实现)

8 个核心工具, 覆盖 coding-expert + drg-expert + PHI 三大领域。

### 8.1 工具清单

| # | Tool name | 领域 | 描述 | 来源 (语义保留) |
|---|-----------|------|------|------------------|
| 1 | `search_icd` | coding | 检索 ICD 编码 | icoder-next `coding_expert.search` |
| 2 | `verify_code` | coding | 查 code 详情 + 注释 | icoder-next `coding_expert.verify` |
| 3 | `get_guidelines` | coding | 查编码指南 | icoder-next `coding_expert.guidelines` |
| 4 | `explore_code` | coding | 查 parent/sibling/child | icoder-next `coding_expert.explore` |
| 5 | `group_drg` | drg | CHS-DRG 分组 | icoder-next `grouping_expert.mdc_of` + `adrg_of` + `drg_tier` |
| 6 | `group_dip` | drg | DIP 病种路径 | icoder-next `grouping_expert.dip_of` |
| 7 | `semantic_search` | coding | BGE-M3 语义检索 | iCoDer 既有 (MedCodER pipeline) |
| 8 | `redact_phi` | safety | PHI 脱敏 (内部) | icoder-next `safety/redactor.py` |

### 8.2 工具 1-4: coding 领域

#### 8.2.1 `search_icd`

```json
{
  "name": "search_icd",
  "description": "按术语检索 ICD-10-CN / ICD-9-CM-3 编码. 返回 top-K 候选, 包含 code / display / score / system.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "term": { "type": "string", "minLength": 1 },
      "system": { "type": "string", "enum": ["icd10cn", "icd9cm3", "both"], "default": "both" },
      "top_k": { "type": "integer", "default": 5, "minimum": 1, "maximum": 30 }
    },
    "required": ["term"]
  }
}
```

**返回**:
```json
{
  "hits": [
    {"code": "I21.0", "display": "急性前壁心肌梗死", "system": "icd10cn", "score": 0.95, "chapter": "循环系统疾病"},
    ...
  ]
}
```

#### 8.2.2 `verify_code`

```json
{
  "name": "verify_code",
  "description": "查 code 详情 + 教学注释 (Includes/Excludes/Code First/Use Additional) + high_risk 标记.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "code": { "type": "string", "pattern": "^[A-Z][0-9]{2}(\\.[0-9]{1,4})?$|^[0-9]{2}\\.[0-9]{1,4}(x[0-9]{1,3})?$" }
    },
    "required": ["code"]
  }
}
```

**返回**:
```json
{
  "code": "I21.0",
  "display": "急性前壁心肌梗死",
  "system": "icd10cn",
  "code_type": "diagnosis",
  "high_risk": false,
  "notes": [
    {"kind": "Includes", "text": "..."},
    {"kind": "Excludes", "text": "..."}
  ]
}
```

#### 8.2.3 `get_guidelines`

```json
{
  "name": "get_guidelines",
  "description": "查官方编码指南 (mandatory per code).",
  "inputSchema": {
    "type": "object",
    "properties": { "code": { "type": "string" } },
    "required": ["code"]
  }
}
```

**返回**:
```json
{ "code": "I21.0", "guideline": "急性心肌梗死编码要点: 1. 主诊断必选 2. 注明部位..." }
```

#### 8.2.4 `explore_code`

```json
{
  "name": "explore_code",
  "description": "查 parent / siblings / children codes (用于鉴别诊断).",
  "inputSchema": {
    "type": "object",
    "properties": { "code": { "type": "string" } },
    "required": ["code"]
  }
}
```

**返回**:
```json
{
  "code": "I21.0",
  "parent": "I21",
  "siblings": ["I21.1", "I21.2", "I21.3", "I21.4"],
  "children": []
}
```

### 8.3 工具 5-6: drg/dip 领域

#### 8.3.1 `group_drg`

```json
{
  "name": "group_drg",
  "description": "CHS-DRG 分组. 输入确诊编码集, 返回 MDC + ADRG + DRG + 解释路径.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "primary_diagnosis": { "type": "string" },
      "secondary_diagnoses": { "type": "array", "items": { "type": "string" } },
      "procedures": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["primary_diagnosis"]
  }
}
```

**返回**:
```json
{
  "mdc": "MDCF",
  "mdc_name": "循环系统疾病及功能障碍",
  "adrg": "FT2",
  "adrg_name": "心力衰竭、休克",
  "drg": "FT21",
  "drg_name": "心力衰竭、休克，伴严重并发症或合并症",
  "tier": "MCC",
  "rationale": "primary_diagnosis I50.900 → MDCF → FT2 → MCC (N18.500)"
}
```

#### 8.3.2 `group_dip`

```json
{
  "name": "group_dip",
  "description": "DIP 病种路径. 输入主诊断, 返回 DIP 病种 + 分值.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "primary_diagnosis": { "type": "string" },
      "secondary_diagnoses": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["primary_diagnosis"]
  }
}
```

**返回**:
```json
{
  "dip_code": "DIP-I50.900",
  "dip_name": "慢性心力衰竭（内科保守治疗）",
  "base_score": 285.0,
  "adjusted_score": 370.5,
  "adjustment_reason": "MCC 系数 1.30"
}
```

### 8.4 工具 7: `semantic_search`

```json
{
  "name": "semantic_search",
  "description": "BGE-M3 + FAISS 语义检索. 输入自然语言查询, 返回 top-K 相关 ICD 编码 (含 evidence 锚点).",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "minLength": 1 },
      "top_k": { "type": "integer", "default": 20, "minimum": 1, "maximum": 50 }
    },
    "required": ["query"]
  }
}
```

**返回**:
```json
{
  "hits": [
    {
      "code": "I21.0",
      "display": "急性前壁心肌梗死",
      "score": 0.92,
      "evidence_pattern": "急性前壁心肌梗死 急诊 PCI 术后",
      "evidence_kb_id": "P0-001"
    }
  ]
}
```

### 8.5 工具 8: `redact_phi`

```json
{
  "name": "redact_phi",
  "description": "PHI 脱敏. 替换姓名/身份证/电话/地址/邮箱/病案号/医保号 为 <REDACTED:XXX> 占位符. (内部用, Expert 不直接调, Orchestrator 入口已调)",
  "inputSchema": {
    "type": "object",
    "properties": {
      "text": { "type": "string" },
      "entity_types": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["text"]
  }
}
```

**返回**:
```json
{
  "redacted_text": "患者 <REDACTED:NAME> 身份证 <REDACTED:ID_CARD> ...",
  "redacted_entities": ["NAME", "ID_CARD"]
}
```

**关键 (Q4 + PHI)**:
- 此工具仅 Orchestrator 内部使用, 不暴露给普通 Expert (避免重复脱敏)
- 工具调用 contextId 必带

---

## 9. 工具发现 (tools/list)

### 9.1 `tools/list` 方法

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "method": "tools/list"
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "result": {
    "tools": [
      { "name": "search_icd", "description": "...", "inputSchema": {...} },
      { "name": "verify_code", "description": "...", "inputSchema": {...} },
      ... (共 8 个)
    ],
    "_meta": { "server_version": "1.0.0", "icoder_version": "1.0.0" }
  }
}
```

### 9.2 动态加载

- 工具列表**不在代码里硬编码** (避免 iCoDer 30 预置 Expert 那种反模式)
- 工具通过 `@mcp_tool` 装饰器注册, server 启动时扫描
- 第三方 ISV 可通过 Plugin 机制注册新 tool (Phase 4)

### 9.3 iCoDer 工具元数据

每个工具描述 (LLM 阅读用) 必含:
- 用途 (中文 + 英文)
- 输入 schema (JSON Schema 完整)
- 输出 schema (隐式, 文档化)
- 使用示例 (1-2 个)
- 限制 (e.g., `search_icd` 不支持 "code/xxx/yyy" 模糊匹配)

---

## 10. iCoDer Expert 作为 MCP Client

### 10.1 Expert 调工具流程

```
1. Orchestrator → Expert (A2A out, A2A spec §7.3)
   { subtask_input: "...", contextId: "..." }

2. Expert (LLM) 推理: 要做"按术语检索 ICD"
   决定调用 search_icd tool

3. Expert (MCP client) → MCP server (stdio/HTTP)
   { method: "tools/call", params: { name: "search_icd", arguments: {...}, _meta: { contextId, agent_id } } }

4. MCP server (iCoDer) 执行工具
   - 校验 inputSchema
   - 校验 _meta.contextId (Q4)
   - 调用 search_icd 实现 (BGE-M3 / ICD 字典)
   - 写 M2aRecorder stage("tool_called", { tool_name, args, contextId })
   - 返回结果

5. Expert (MCP client) 收到结果
   - 解析 content[0].text (JSON)
   - 把结果注入 Expert LLM context
   - Expert LLM 继续推理 (可能再调其他 tools, 或返回最终结论)

6. Expert → Orchestrator (A2A return)
   { expert_id, output, evidence, confidence }
```

### 10.2 Tool call 限制

| 限制 | 默认 | 可配置 |
|------|------|--------|
| 单 Expert 单 run 最多 tool call | 20 | Plan.metadata 可覆盖 |
| 单 tool call 超时 | 30s | per-tool inputSchema |
| 总 tool call 耗时 | 5min | Plan.metadata 可覆盖 |
| 同 tool 重复 call (短时间) | 3 | per-tool |

### 10.3 Tool call 错误处理

| 错误类型 | 处理 |
|----------|------|
| `TOOL_NOT_FOUND` | Expert 跳过, 不重试, 改用其他 tool 或人工 review |
| `INVALID_TOOL_ARGUMENTS` | Expert 收到错误, 改 arguments 重试 1 次, 仍失败 = skip |
| `TOOL_EXECUTION_FAILED` | 重试 2 次 (指数退避), 仍失败 = Expert 决定是否 skip |
| `CONTEXT_REQUIRED` | 这是 server bug, 不应发生; 发生 = 报警 + fail run |
| `CONTEXT_INVALID` | contextId 已 expire, fail run (Q4 严格) |
| `PHI_DETECTED` | fail run (合规底线) |
| `TIMEOUT` | 重试 1 次, 仍超时 = skip |

---

## 11. 安全 + 隔离 (Q4 落地)

### 11.1 contextId 强制

| 规则 | 实现 |
|------|------|
| tool call 必带 `_meta.contextId` | server 校验, 缺失 = `CONTEXT_REQUIRED` |
| tool result 按 contextId 隔离 | server 内部缓存 key 含 contextId, 跨 contextId 不命中 |
| 跨 contextId tool call 阻断 | server 校验 `contextId` 在 Context 表中存在, 不存在 = `CONTEXT_INVALID` |

### 11.2 PHI 强制

| 规则 | 实现 |
|------|------|
| tool input 必 redacted | server 调用前校验 (用 `redact_phi` 反向: 找是否有 `<REDACTED:` 占位符; 占位符越多 = 已脱敏) |
| 检测到原始 PHI | `PHI_DETECTED` 错误, fail run |
| 原文不进 tool input | Orchestrator spec §6.3 保证, 本 spec 二次校验 |

### 11.3 工具可发现性

| 规则 | 实现 |
|------|------|
| 工具列表可发现 | `tools/list` 公开 (本进程内) |
| 工具不暴露给外部 | MCP HTTP 端点 Phase 4 才接 |
| 工具调用记录全留痕 | M2aRecorder stage("tool_called", ...) + stage("tool_returned", ...) |

### 11.4 工具审计

每个 tool call 写 M2aRecorder:

| Stage | payload |
|-------|---------|
| `tool_invoked` | `{ tool_name, arguments_summary, contextId, agent_id, start_ts }` |
| `tool_returned` | `{ tool_name, result_summary, duration_ms, contextId, agent_id }` |
| `tool_failed` | `{ tool_name, error_code, error_message, contextId, agent_id }` |

### 11.5 RBAC

- Phase 1: 所有 Expert 可调所有 tools (无 RBAC 限制)
- Phase 4: 引入 role-based access, 不同角色可调不同 tools (e.g., auditor 可调 compliance tool, 但不调 semantic_search)

### 11.6 MCP Auth (Phase 3-C1, 2026-07-05)

**背景**: MCP 2025-03-26 spec 把 `securitySchemes` 标为可选, iCoDer Phase 1 起步时 (N2) 推迟到 Phase 4. Phase 3-C1 闭坑 — 实装 4 种 auth 类型, 对齐 Corti `corti_deep_scan` 反查出的 auth code 全集.

**4 种 auth 类型** (`MCPAuthConfig.discriminator = type`):

| `type` | 用途 | Header 注入 | 失败码 |
|--------|------|-------------|--------|
| `none` | 内部 stub 工具 (search_icd / verify_code 等本地) | 不注入 | n/a |
| `bearer` | 静态 token 引用 (`secret://mcp/.../bearer_token`) | `Authorization: Bearer <token>` | `mcp_auth_missing_token` |
| `inherit` | 继承 project / session / studio / runtime context 的 auth | 从 `RunContext.auth_context` 取 | `mcp_auth_missing_token` |
| `oauth2.0` | OAuth2.0 client_credentials grant, 带 token 缓存 + 过期 + clock skew -60s | `Authorization: Bearer <access_token>` | `mcp_auth_token_exchange_failed` / `mcp_auth_invalid_oauth_config` |

**Config schema** (Pydantic discriminated union):

```python
class MCPAuthConfig(BaseModel):
    type: Literal["none", "bearer", "inherit", "oauth2.0"]
    # bearer
    secret_ref: str | None = None        # "secret://mcp/{provider}/{key}"
    # inherit
    inherit_from: Literal["project", "session", "studio", "runtime"] | None = None
    # oauth2.0
    oauth: OAuth2ClientCredentialsConfig | None = None
    # display
    redacted_view: str | None = None     # "Bearer ••••1234"

class OAuth2ClientCredentialsConfig(BaseModel):
    token_url: str
    client_id_ref: str                   # secret_ref
    client_secret_ref: str               # secret_ref
    scopes: list[str] = []
    audience: str | None = None
    cache_ttl_seconds: int = 3600
```

**Token 解析** (`resolve_mcp_auth(auth_config, context) -> AuthHeader`):

1. `none` → return `AuthHeader(kind="none")`.
2. `bearer` → resolve `secret_ref` via `CredentialVault`; raise `mcp_auth_missing_token` if absent.
3. `inherit` → 从 `RunContext.auth_context` 拿 (`project` > `session` > `studio` > `runtime` 优先级); raise `mcp_auth_missing_token` if empty.
4. `oauth2.0` → 检查 token 缓存 (key = `provider_url + client_id + scopes_hash`, **不**含 secret); 若未过期 (含 -60s clock skew) 直接复用; 否则做 client_credentials grant, 缓存 + 返回. Exchange 失败 = `mcp_auth_token_exchange_failed`; 配置缺字段 = `mcp_auth_invalid_oauth_config`.

**缓存安全**:
- 缓存 key 仅含 `provider_url + client_id + scopes_hash` (公开值), **不**含 `client_secret`.
- 缓存 value 仅存 `access_token + expires_at`, 内存中, 进程退出即清.
- `redacted_view` 字段用于日志/UI 显示 (`"Bearer ••••1234"`), 不含完整 token.

**MCP auth 错误码** (与 §6 衔接, 7 个新码):

| Wire code | MCP 错误码 | HTTP | 触发 |
|-----------|-----------|------|------|
| -32006 | `mcp_auth_duplicate_name` | 400 | tools/list 重复 tool name (Corti §B-04) |
| -32007 | `mcp_auth_missing_name` | 400 | tool name 缺失 |
| -32008 | `mcp_auth_missing_token` | 401 | bearer / inherit 缺 token |
| -32009 | `mcp_auth_missing_credentials` | 401 | oauth2.0 缺 client_id/secret |
| -32010 | `mcp_auth_invalid_oauth_config` | 400 | oauth2.0 配置字段非法 |
| -32011 | `mcp_auth_token_exchange_failed` | 401 | oauth2.0 token exchange 失败 (any HTTP non-200) |
| -32012 | `mcp_auth_forbidden` | 403 | token 有效但无权调该 tool |

**测试矩阵** (Phase 3-C1 §B5):

1. `test_mcp_auth_none_type_no_header` — none 不注入 Authorization.
2. `test_mcp_auth_bearer_resolves_secret_ref` — bearer 从 vault 拿到 token, 注入 `Authorization: Bearer <token>`.
3. `test_mcp_auth_bearer_missing_secret_ref_raises` — 缺 secret_ref → `mcp_auth_missing_token`.
4. `test_mcp_auth_inherit_from_project_context` — inherit 从 `RunContext.auth_context.project` 取.
5. `test_mcp_auth_oauth2_exchanges_then_caches` — 首次 exchange, 二次命中缓存 (httpx MockTransport 验证只调一次).
6. `test_mcp_auth_oauth2_expires_then_refreshes` — expires_in 过期 + clock skew -60s 触发 refresh.
7. `test_mcp_auth_oauth2_invalid_config_raises` — 缺 token_url → `mcp_auth_invalid_oauth_config`.
8. `test_mcp_auth_oauth2_exchange_failure_raises` — 4xx/5xx response → `mcp_auth_token_exchange_failed`.
9. `test_mcp_auth_cache_key_excludes_secret` — 缓存 key 字符串里**不**含 client_secret.
10. `test_mcp_auth_redacted_view_in_logs` — 日志只输出 `redacted_view`, 不输出 raw token.
11. `test_mcp_auth_forbidden_on_insufficient_scope` — token 有效但 scope 不匹配 → `mcp_auth_forbidden`.

---

## 12. 与 Orchestrator / A2A / Expert / Context 的关系

### 12.1 Orchestrator 集成

| Orchestrator 概念 | 引用 MCP |
|------------------|----------|
| Plan.experts[].tool_constraints | 限制 Expert 可调 tools (e.g., `["search_icd", "verify_code"]`) |
| Delegator 委托 Expert | Expert 内部用 MCP client 调 tools (不经过 Orchestrator) |
| Recorder stage | 写 tool call 记录 (MCP server 端) |

### 12.2 A2A 集成

| A2A 字段 | 引用 MCP |
|---------|----------|
| 出站 message.metadata.tool_constraints | MCP tool call 限制 |
| 出站 message.metadata.timeout_ms | MCP tool call timeout |
| iCoDer metadata.expert_invocations | 每个 Expert 调用的 tools 列表 (聚合自 MCP) |

### 12.3 Expert 集成

| Expert 概念 | 引用 MCP |
|------------|----------|
| Expert system_prompt (Q7) | 注入 MCP tool 列表 + 使用方法 (LLM 看) |
| Expert LLM 推理 | LLM 决定调哪些 MCP tools |
| Expert 输出 | 把 MCP tool 结果聚合成 Expert 自己的子结论 |

### 12.4 Context 集成

| Context 字段 | 引用 MCP |
|--------------|----------|
| contextId | MCP tool call 必带 (Q4 隔离) |
| Context.expires_at | MCP server 校验 contextId 未 expire |
| Context.status | MCP server 校验 Context.status != expired |

---

## 13. 测试要求

### 13.1 单元测试 (≥50 cases)

**文件**: `backend/tests/unit/icoder/mcp/test_protocol.py` + 8 个 tool 各 1 文件

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **JSON-RPC 信封** | 请求/响应/错误/批处理 (批处理不实现) | 5 |
| **MCP 错误码** | 8 类业务 + 5 类 JSON-RPC 标准 | 8 |
| **Tool 声明** | 8 个 tool 各自 inputSchema 校验 | 8 |
| **`search_icd`** | 输入校验 + 返回结构 + 同义词 + top_k 限制 | 5 |
| **`verify_code`** | 输入校验 + high_risk 标记 + notes 结构 | 4 |
| **`get_guidelines`** | 输入校验 + 返回结构 | 2 |
| **`explore_code`** | 输入校验 + parent/sibling/child 关系 | 4 |
| **`group_drg`** | 主诊断必填 + MDC/ADRG/DRG 推导 + tier 判定 | 6 |
| **`group_dip`** | 主诊断必填 + DIP 路径 + 系数计算 | 4 |
| **`semantic_search`** | BGE-M3 + FAISS 调用 + top_k 限制 | 2 |
| **`redact_phi`** | 7 类 PHI 替换 + 原文不进 output | 4 |
| **contextId 强制** | 缺 contextId / 错误 contextId / 跨 contextId 阻断 | 3 |
| **PHI 强制** | tool input 含原始 PHI = 拒绝 | 2 |

**总计**: 50 单元测试 (8 tools 平均 4-5 + protocol 13)

### 13.2 集成测试 (≥15 cases)

**文件**: `backend/tests/integration/icoder/mcp/test_mcp_integration.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **stdio transport** | 子进程启动 + JSON-RPC over stdio | 1 |
| **HTTP transport** | HTTP server 启动 + JSON-RPC over HTTP | 1 |
| **`initialize` 握手** | 协议版本协商 + 能力声明 | 1 |
| **`tools/list`** | 返回 8 个 tools, schema 正确 | 1 |
| **`tools/call` 完整流程** | search_icd → verify_code → group_drg 串起来 | 1 |
| **contextId 隔离** | 同 tool 不同 contextId 结果不串 | 1 |
| **PHI 阻断** | tool input 含原始 PHI = PHI_DETECTED | 1 |
| **M2aRecorder 集成** | tool call 写 3 个 stage | 1 |
| **超时重试** | 工具超时 → 重试 1 次 → 仍超时 = fail | 1 |
| **错误码** | 8 类 MCP 错误码各 1 触发 | 1 |
| **跨工具协作** | search_icd + verify_code + group_drg 1 条病历走通 | 1 |
| **缓存隔离 (Q4)** | contextId A 缓存不命中 contextId B (Phase 5 留) | 1 |
| **tool call 限制** | 单 run 20 次 / 单 tool 3 次重复 触发限制 | 2 |
| **Expert 集成** | Expert LLM 调 MCP tool 完整跑通 (mock LLM) | 1 |
| **真实 LLM 集成** | **Expert + 真实 DeepSeek 调 MCP tool 跑通** | 1 |

**总计**: 15 集成测试

### 13.3 e2e 测试 (与 Orchestrator e2e 合并)

**文件**: `backend/tests/e2e/icoder/test_mcp_e2e.py` (与 Orchestrator/A2A/Context 共享)

| 测试 | 覆盖 |
|------|------|
| **1 条病历完整 run: Orchestrator + Expert + MCP 工具链** | 验证: 真实 DeepSeek + 8 MCP tools + A2A 端点 + Context + M2aRecorder 全链路; Expert 调用 search_icd + verify_code + group_drg 全部成功 |

**总计**: 1 e2e (与 Orchestrator/A2A/Context 共享)

### 13.4 测试矩阵汇总

| 层级 | 数量 | Phase 1 必需 |
|------|------|--------------|
| 单元 | 50 | ✅ |
| 集成 | 15 | ✅ |
| e2e | 1 (共享) | ✅ |
| **小计** | **66** | |

加上 Orchestrator 44 + A2A 53 + Context 46 + 1227 baseline = **1436+**。

---

## 14. 与 RFC 映射 (验收对齐)

| RFC 章节 | 本 spec 章节 | 验证方式 |
|----------|--------------|----------|
| 3.2.4 MCP Protocol (Q3) | 全部 | 1436+ tests 全绿 |
| 3.3 协议版本锁定 (MCP 2025-03-26) | §3 / §7 | 单元测试: 协议头校验 |
| 4.1 编码体系 (ICD 字典 / BGE-M3 / 编码指南 / DRG/DIP) | §8 | 集成测试: 8 tools 全覆盖 |
| 5 节映射表 MCP 行 | §8 / §12 | 全覆盖 |
| 9.2 W2 (协议对齐写法) | §1.2 / §1.3 | 全部按 MCP 2025-03-26 spec 写, 不写 iCoDer 私有扩展 |
| 9.2 W5 (Expert metadata 公开) | §12.3 (Expert system_prompt 注入 tool 列表) | 集成测试: system_prompt 含 8 tools 描述 |
| 10.1 Phase 1 成功标准 | §13.4 | 1436+ tests 全绿 |
| 10.2 v1 完成时 | (Phase 4-5 才完整) | HTTP transport + 第三方 ISV tool |

---

## 15. 实现路径 (Phase 1 落地)

### 15.1 文件结构 (新增 + 重做)

```
backend/app/icoder/agent_runtime/mcp/
├── __init__.py
├── envelope.py                  # JSON-RPC 2.0 信封 (复用 A2A spec §4 模式)
├── errors.py                    # MCP 错误码
├── tool.py                      # Tool 数据类 + @mcp_tool 装饰器
├── tool_registry.py             # 工具注册表 (动态加载)
├── transport/
│   ├── __init__.py
│   ├── stdio.py                 # stdio transport (subprocess)
│   └── http.py                  # HTTP transport (FastAPI, Phase 4 stub)
├── server.py                    # MCP server (启动 + 处理请求)
├── client.py                    # MCP client (Expert 用)
├── context_validator.py         # contextId 校验 (Q4 隔离)
├── phi_validator.py             # PHI 校验 (G9)
├── icoder_metadata.py           # iCoDer 特有 metadata (tool_invocation_id)
└── tools/                       # 8 个 tool 实现
    ├── __init__.py
    ├── search_icd.py            # 工具 1
    ├── verify_code.py           # 工具 2
    ├── get_guidelines.py        # 工具 3
    ├── explore_code.py          # 工具 4
    ├── group_drg.py             # 工具 5
    ├── group_dip.py             # 工具 6
    ├── semantic_search.py       # 工具 7
    └── redact_phi.py            # 工具 8

backend/app/icoder/agent_runtime/
├── __init__.py
├── mcp_routes.py                # MCP 路由总挂载 (stdio 自动 / HTTP Phase 4)
└── (其他 4 spec 实现: orchestrator/ a2a/ context/ tasks/ agent_card/)

backend/tests/unit/icoder/mcp/
├── test_protocol.py             # 13 cases
├── test_search_icd.py           # 5 cases
├── test_verify_code.py          # 4 cases
├── test_get_guidelines.py       # 2 cases
├── test_explore_code.py         # 4 cases
├── test_group_drg.py            # 6 cases
├── test_group_dip.py            # 4 cases
├── test_semantic_search.py      # 2 cases
├── test_redact_phi.py           # 4 cases
├── test_context_validator.py    # 3 cases
└── test_phi_validator.py        # 2 cases
# 50 unit tests total

backend/tests/integration/icoder/mcp/
└── test_mcp_integration.py      # 15 cases

backend/tests/e2e/icoder/
└── test_mcp_e2e.py              # 1 e2e (与 Orchestrator/A2A/Context 共享)

# 重做
icoder-next/backend/icoder/experts/coding_expert.py  # 工具语义保留, 实现改 MCP
icoder-next/backend/icoder/experts/grouping_expert.py  # 同上
icoder-next/backend/icoder/safety/redactor.py       # 同上
```

### 15.2 依赖

| 依赖 | 已有? | 用途 |
|------|-------|------|
| `pydantic v2` | ✅ | Tool / Request / Response 数据类 |
| `asyncio` (Python std) | ✅ | stdio / HTTP async |
| `BGE-M3` (sentence-transformers) | ✅ (既有) | semantic_search |
| `FAISS` (`faiss-cpu`) | ✅ (既有) | semantic_search |
| `rapidfuzz` | ✅ (既有) | search_icd (字符串匹配) |
| ICD-10-CN 字典 (37,897 码) | ✅ (既有) | search_icd / verify_code |
| ICD-9-CM-3 字典 | ✅ (既有) | search_icd |
| 编码指南 KB | ✅ (既有) | get_guidelines |
| 易错码 KB | ✅ (既有) | explore_code |
| M2aRecorder | ✅ | 审计 |
| Context (Context spec) | ✅ | contextId 校验 |

### 15.3 实施顺序 (Phase 1 内部)

1. **M1**: envelope.py + errors.py + tool.py (核心数据类, 单元测试)
2. **M2**: tool_registry.py + @mcp_tool 装饰器 (动态加载, 单元测试)
3. **M3**: transport/stdio.py (stdio transport, 单元测试)
4. **M4**: transport/http.py (HTTP transport stub, 单元测试)
5. **M5**: server.py (MCP server 主循环, 单元测试)
6. **M6**: context_validator.py (contextId 校验, 单元测试)
7. **M7**: phi_validator.py (PHI 校验, 单元测试)
8. **M8**: tools/search_icd.py + verify_code.py + get_guidelines.py + explore_code.py (coding 4 工具, 单元测试)
9. **M9**: tools/group_drg.py + group_dip.py (drg 2 工具, 单元测试)
10. **M10**: tools/semantic_search.py (BGE-M3 + FAISS, 单元测试)
11. **M11**: tools/redact_phi.py (PHI 脱敏, 单元测试)
12. **M12**: client.py (Expert 用 MCP client, 单元测试)
13. **M13**: 集成测试 (stdio + HTTP + initialize + tools/list + tools/call + 8 tools)
14. **M14**: Expert 集成 (Expert LLM 调 MCP tools, 集成测试)
15. **M15**: e2e test (与 Orchestrator/A2A/Context 共享, 真实 DeepSeek 跑通)

每个 M = 1 个 PR, M1-M15 全过才进 Phase 2。

### 15.4 与 icoder-next 切片的关系 (Q5 + Q10)

- **Q5 决策**: 旧 `coding_expert.py` / `grouping_expert.py` / `safety/redactor.py` (Python 函数) **完全重做** 为 MCP server
- **Q10 决策**: 仓库保留, 标注 superseded; 工具语义 (search/verify/guidelines/explore/mdc/adrg/drg/dip/redact) 全部保留, 实现改 MCP

---

## 16. 开放问题 (本 spec 级别)

| # | 问题 | 选项 | 倾向 |
|---|------|------|------|
| Q-M1 | Transport 默认选 stdio vs HTTP? | 倾向: stdio (本地快, 简单), HTTP 留 Phase 4 | |
| Q-M2 | Tool 列表动态加载 vs 静态声明? | 倾向: 动态 (@mcp_tool 装饰器) | |
| Q-M3 | tool call 限制默认值: 20 次/run? | 倾向: 20 次 (经验值, 够用不浪费) | |
| Q-M4 | BGE-M3 模型本地加载 vs 远程? | 倾向: 本地 (既有, 延迟低) | |
| Q-M5 | FAISS 索引本地 vs 远程? | 倾向: 本地 (既有) | |
| Q-M6 | 工具是否支持 streaming (长任务)? | 倾向: 不支持 (MCP 2025-03-26 spec 不支持), Phase 5 留 | |
| Q-M7 | 工具结果缓存 (Q4 隔离)? | 倾向: 不缓存 (Phase 1 简单), Phase 5 加 | |
| Q-M8 | PHI 校验 (反向找 `<REDACTED:` 占位符) 准确率? | 倾向: 80% 准确率够用, 误报可接受 | |
| Q-M9 | 第三方 ISV 工具注册机制? | 倾向: Plugin 机制 (Phase 4), Phase 1 只内置 8 tools | |
| Q-M10 | e2e test 是否强制依赖 DeepSeek? | 倾向: 是 (与 Orchestrator/A2A/Context 共享 e2e) | |

---

## 17. 参考

### 17.1 战略 RFC 与上游 spec

- `E:\Corti4C\docs\ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20)
  - 第 3.2.4 节: MCP Protocol 目标形态
  - 第 3.3 节: 协议版本锁定
  - 第 9 节: Q3 决策
- `E:\Corti4C\docs\ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft 2026-06-20)
  - 第 5.2 节: 出站委托 (Plan.expert[].tool_constraints)
  - 第 6.3 节: PHI 脱敏
- `E:\Corti4C\docs\ICODER_V1_A2A_SPEC.md` (Draft 2026-06-20)
  - 第 4 节: JSON-RPC 2.0 信封 (MCP 复用)
  - 第 7.3 节: 出站 message:send (Expert 通过 MCP client 调 tools)
- `E:\Corti4C\docs\ICODER_V1_CONTEXT_SPEC.md` (Draft 2026-06-20)
  - 第 6 节: 三层隔离 (MCP tool call 必带 contextId)

### 17.2 MCP 协议官方

- MCP 2025-03-26 spec: `https://modelcontextprotocol.io/spec/2025-03-26` (Anthropic 维护)
  - JSON-RPC 2.0 envelope
  - Tools / Resources / Prompts
  - Transport (stdio / HTTP)
  - Error codes

### 17.3 Corti 官方文档

- `E:\Corti4C\Corti\llms-full.txt`
  - `/agentic/mcp-protocol` - MCP 协议
  - `/agentic/experts` - Expert 抽象 (用 MCP 调工具)
  - `/agentic/faq` - A2A vs MCP

### 17.4 iCoDer 既有代码

- `icoder-next/backend/icoder/experts/coding_expert.py` - 4 工具 coding-expert (Q5 决策: 重做, 工具语义保留)
- `icoder-next/backend/icoder/experts/grouping_expert.py` - DRG/DIP 分组 (同上)
- `icoder-next/backend/icoder/safety/redactor.py` - PHI 脱敏 (同上)
- `E:\iCoDerA\icd10cn_code_catalog.json` - 37,897 码 (M8 用)
- `E:\iCoDerA\evidence_anchoring_kb.json` - 编码指南 (M8 用)
- `E:\iCoDerA\coding_differentiation_kb.json` - 易错码 KB (M8 用)
- `data/medcoder/faiss.index` - FAISS 索引 (M10 用)
- `data/medcoder/models/` - BGE-M3 模型 (M10 用)

### 17.5 iCoDer 战略线索

- 2026-06-20: 100% Corti 复刻 + 10 决策 (Q3: MCP 2025-03-26)
- 2026-06-17: 战略转向
- 2026-06-14: 原子能力架构
- 2026-06-13: icoder-next 切片开工

---

## 18. 签字 (待审)

| 角色 | 签字 | 日期 |
|------|------|------|
| 架构组 | ___ | ___ |
| 工程 owner | ___ | ___ |
| 安全/合规 | ___ | ___ (重点审 PHI 校验 + contextId 隔离) |

---

**本 spec 拍板后**:
1. 起 `ICODER_V1_AGENT_CARD_SPEC.md` (并行, Registry 公开 + Agent Card 后端)
2. 起 `ICODER_V1_TASK_SPEC.md` (Task Service, Phase 5 完整, Phase 1 stub)
3. 6 spec 全部拍板 → Phase 1 实施 (M1-M15, 加上 Orchestrator T1-T10 + A2A A1-A10 + Context C1-C11)
