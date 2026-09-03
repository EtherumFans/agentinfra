# 01 — Current Agent Architecture (Sprint 2 Audit)

**Date**: 2026-08-07
**Scope**: Agent Registry, Agent CRUD, Agent Runtime, Test Console, Agent Version, API Client, SDK, Embedded

---

## 1. 双轨 Agent 存储架构

iCoDer 当前有**两套并行的 Agent 存储机制**, 且它们**没有完全同步**:

### 1.1 DB `Agent` 表 (用户视角)

- **Schema**: `app/models/agent.py` (通过 alembic 创建)
- **CRUD API**: `app/api/agents.py` — 9 endpoints under `/api/rest/v1/agent_definitions`
  - `GET /api/rest/v1/agent_definitions` — list (filter by type/category/search)
  - `POST /api/rest/v1/agent_definitions` — create custom agent
  - `GET /api/rest/v1/agent_definitions/{id}` — get by id
  - `POST /api/rest/v1/agent_definitions/{id}/clone` — clone prebuilt/template
  - `GET /api/rest/v1/agent_definitions/categories`
  - `GET /api/rest/v1/agent_definitions/templates` — 20 hardcoded templates
  - `GET /api/rest/v1/agent_definitions/templates/{id}/download` — .icoder-agent package
  - `PUT /api/rest/v1/agent_definitions/{id}` — update
  - `DELETE /api/rest/v1/agent_definitions/{id}` — delete

- **关键字段** (`AgentCreate` schema):
  ```python
  name: str
  description: str = ""
  system_prompt: str = ""
  icon: str = "Bot"
  category: str = "general"
  expert_ids: list[str] = []
  default_expert_id: str = ""
  a2a_enabled: bool = False
  config: dict | None = None
  ```

### 1.2 Runtime Agent Registry (文件 / Agent Pack)

- **存储**: `icoder_runtime/core/registry.py:RuntimeAgentRegistry` — 文件 backend (`.icoder/agent_registry.json`)
- **加载源**: `app/main.py:406` — `BuiltinAgentPackProvider` 扫描 `official_agents/*/agent_pack.json`
- **同步服务**: `app/services/agent_registry_sync_service.py` — 试图同步 DB ↔ Registry

### 1.3 Runtime 调用入口 (实际跑 agent 的地方)

`app/api/agent_run.py:run_agent()` (line 264+):
```python
# Phase 1: idempotency check
# Phase 2: route 分流
if agent_id in _MEDICAL_CODING_AGENT_IDS:  # frozenset({medical-coding-agent, medcoder-coding-review-agent})
    response = await dispatch_medical_coding_fast(...)
else:
    response = await _run_via_provider_registry(...)  # line 810+
```

`_run_via_provider_registry` (line 810):
```python
pack = _load_pack_by_agent_id(agent_id)  # ← 只扫 official_agents/, 不查 DB
if pack is None:
    return _error_response(error_reason="unknown_agent", ...)  # ← 致命断链

registry = get_default_registry()  # ProviderRegistry, NOT RuntimeAgentRegistry
provider = registry.resolve_from_agent_pack(pack)
# → PureLLMProvider / LLMWithToolsProvider / RuleEngineProvider
resp = await provider.invoke(req, ctx, request=request)
```

---

## 2. Test Console (AgentChatPage) 现状

**位置**: `frontend/src/pages/AgentChatPage.tsx`

**调用链**:
```
User input → runtimeAgentApi.agentRun(agentId, content, opts)
           → POST /api/v1/agents/{agent_id}/run
           → agent_run.py:run_agent()
           → _run_via_provider_registry() OR dispatch_medical_coding_fast()
           → AgentRunResponse (HTTP 200, error=false)
           → 前端渲染 message + trace_url
```

**关键证据** (`AgentChatPage.tsx:285-289`):
```ts
// POST /api/v1/agents/{id}/run — uniform 13-field envelope across
const { runtimeAgentApi } = await import('../services/runtimeApi');
const resp = await runtimeAgentApi.agentRun(agentId || '', content, {
```

**Streaming**: ⚠️ **未实现 SSE/WS**. Endpoint 是 request/response. 前端用 typing 动画模拟流式效果。

**Run ID / Status / Error**: ✅ response 含 `{run_id, trace_id, trace_url, error, error_reason}`, 前端有 Run Trace 链接 (`/ai-studio/runs/{run_id}/trace`)。

---

## 3. Agent Templates (Goal A 核心审计)

**位置**: `app/api/agents.py:502-703`

**当前 20 个 templates 全部医疗域**:

| # | id | category |
|---|-----|----------|
| 1 | icd10-navigator | 编码 |
| 2 | rule-explainer | 编码 |
| 3 | compliance-guardrail | 医保 |
| 4 | code-validation | 编码 |
| 5 | procedure-extractor | 编码 |
| 6 | diagnosis-extractor | 编码 |
| 7 | surgical-registry | 质控 |
| 8 | icu-summary | 文书 |
| 9 | triage | 急诊 |
| 10 | note-completeness | 质控 |
| 11 | med-reconciliation | 药学 |
| 12 | denial-appeals | 医保 |
| 13 | discharge-edu | 护理 |
| 14 | nursing-handoff | 护理 |
| 15 | prior-auth | 医保 |
| 16 | referral-gen | 文书 |
| 17 | clinical-edu | 教育 |
| 18 | medical-coding | 编码 |
| 19 | clinical-guidelines | 教育 |
| 20 | cdi | 质控 |

**Generic templates 状态**: ❌ **零个** `translator-blank` / `summarizer-blank` / `generic-llm` / `blank-canvas`。

**Sprint 2 Goal A 行动**: 添加至少 2 个 Generic templates, 字段不含 `medcoder_*` / `coding_template`。

---

## 4. API Client 体系 (Goal D 核心)

iCoDer 当前有**两个并行的 OAuth Client API**:

### 4.1 Console-internal (`app/api/oauth.py`)

- **路由前缀**: `/api/oauth`
- **Endpoints**:
  - `POST /api/oauth/clients` — create
  - `GET /api/oauth/clients` — list
  - `DELETE /api/oauth/clients/{id}` — delete
  - `POST /api/oauth/token` — token exchange
  - `POST /api/oauth/realms/{realm}/token` — realm-style token exchange
- **缺失**: ❌ rotate / disable / enable / patch scopes

### 4.2 Partner / Phase 7 (`app/api/platform_api_clients.py`)

- **路由前缀**: `/api/v1/api-clients` (或 `/api/rest/v1/api-clients`, 待确认)
- **Endpoints** (完整生命周期):
  - `GET /api/v1/api-clients` — list (line 222)
  - `POST /api/v1/api-clients` — create (line 237)
  - `GET /api/v1/api-clients/{id}` — get (line 287)
  - `POST /api/v1/api-clients/{id}/disable` — disable (line 302)
  - `POST /api/v1/api-clients/{id}/enable` — enable (line 325)
  - `POST /api/v1/api-clients/{id}/rotate` — **rotate secret** (line 344)
  - `PATCH /api/v1/api-clients/{id}/scopes` — update scopes (line 400)
  - `PATCH /api/v1/api-clients/{id}/origins` — update allowed_origins (line 419)
  - `POST /api/v1/api-clients/{id}/test-connection` — test (line 438)

### 4.3 Console UI 当前 wiring

**`frontend/src/services/api.ts:170-179`**:
```ts
export const oauthApi = {
  list: () => api.get<{ clients: any[] }>('/oauth/clients'),
  create: (...) => api.post('/oauth/clients', params, ...),
  delete: (clientId) => api.delete(`/oauth/clients/${clientId}`),
};
```

→ 只调 oauth.py, 不调 platform_api_clients.py。

**Sprint 2 Goal D 行动**: 改 `oauthApi` 调 `/api/v1/api-clients/*`, 解锁 rotate / disable / enable。

### 4.4 last_used_at 字段

- ✅ Column exists (`oauth.py:41` `last_used_at: Mapped[datetime | None]`)
- ❌ Write path missing in `oauth.py:_handle_client_credentials` (line 358+)
- ✅ `platform_api_clients.py` line 91 `last_used_at: Optional[datetime]` — 同样的 column, 同样未写

**修复**: 在 `_handle_client_credentials` 加 `client.last_used_at = datetime.now(timezone.utc)` + commit。

---

## 5. Code Tab (Goal E 现状)

**位置**: `frontend/src/components/common/SettingsCodeTab.tsx` + `CodeSnippet.tsx`

**已支持格式**: JavaScript SDK / Python SDK / curl / JSON config (4 tabs)

**使用位置**:
- `AgentDetailPage.tsx:15` — agent 详情页有 Settings/Code/Tools 三 tab
- `AgentChatPage.tsx` — chat 页右侧 Code tab

**真实可运行验证**: ⚠️ 需要确认 Code Tab 是否填了真实 `agent_id` (而非 placeholder)。如果是 placeholder, 开发者复制后无法直接运行。

**Sprint 2 Goal E 行动**: 验证 Code Tab 用的是当前 agent 的真实 `agent_id`, 修正任何 placeholder; 确保 cURL 命令包含正确的 `Authorization: Bearer $TOKEN` + 真实 endpoint。

---

## 6. SDK 现状

**包**: `@icoder/sdk@1.0.0-beta.2` (`packages/icoder-sdk/`)

**Canonical API** (`src/index.ts:57-99`):
```js
import iCoDer from '@icoder/sdk';
const icoder = new iCoDer({ baseURL, auth: { accessToken, refreshToken } });
await icoder.runs.runText(agentId, text, options);
```

**16 个 resource classes**: client / facts / agents / experts / reviews / speechToText / textGen / billing / usage / oauth / runtime / marketplace / compliance / runs / runHistory / runTrace / patientContext

**Sprint 2 状态**: SDK 已就绪, 无需变更。Goal E + F 直接消费。

---

## 7. Embedded 能力

**Backend**: `app/api/embedded.py`
**Frontend**: `frontend/src/pages/EmbeddedAssistantPage.tsx`
**Web Component**: `<icoder-embedded>` (Phase 7 Gate 5)

**Reference App**: `examples/partner-reference-app/`
- Express server holding `ICODER_API_CLIENT_SECRET` in env
- Token exchange via `client_credentials` grant
- Serves shell that loads `<icoder-embedded>` web component

**Sprint 2 Goal F 行动**: 新增 `examples/external-agent-consumer/` (与 partner-reference-app 并列), 演示**纯 REST API + SDK** 调用, 无 web component 依赖。

---

## 8. Agent Version 机制

**当前**:
- `Agent.version` 字段 (string, default `"1.0.0"`)
- 每次 update 不自动 bump
- 无 version history / rollback
- `agent_pack.json` 有 `manifest.version` 字段, 与 DB `Agent.version` 不自动同步

**Sprint 2 状态**: Version 机制不在 Goal A-F 范围内, 不动。

---

## 9. MedCodER 解耦验证 (Goal B 前置)

**当前 coupling 点**:
1. `agent_run.py:258-261` — `_MEDICAL_CODING_AGENT_IDS` frozenset 硬编码 `{medical-coding-agent, medcoder-coding-review-agent}`
2. `app/coding_runtime/` — `CodingRuntimeDispatcher` 模块 (只对上述 2 个 agent_id 触发)
3. `icoder_runtime/providers/medical_coding/` — HybridCodingAdapter / MedCodER 5-stage 实现

**Generic Agent 解耦证明** (Sprint 2 Goal B 任务):
- 创建一个 `generic-blank` template → clone 成 custom agent
- 在 Test Console 跑该 custom agent
- 验证后端 log: `coding_runtime` 模块**未** import, `HybridCodingAdapter`**未**实例化
- 验证 `icoder_runtime.providers.medical_coding.*` **未**加载

**预期证据**: backend log 不出现 `CodingRuntimeDispatcher` / `HybridCodingAdapter` / `medcoder` 字串, 仅出现 `PureLLMProvider` / `LLMGateway`。

---

## 10. 当前架构图

```
┌──────────────────────────────────────────────────────────────────┐
│ Console UI (React SPA)                                            │
│  ├─ AgentsPage (Hub + My Agents)                                  │
│  ├─ AgentChatPage (Test Console) → runtimeAgentApi.agentRun      │
│  ├─ AgentDetailPage (Settings + Code + Tools tabs)                │
│  └─ APIClientsPage → oauthApi (❌ 不调 platform_api_clients)      │
└──────────────────┬───────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│ FastAPI Backend                                                   │
│                                                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Agent CRUD: /api/rest/v1/agent_definitions (agents.py)       │ │
│ │  ├─ DB Agent table                                           │ │
│ │  └─ 20 hardcoded templates (全部 medical)                    │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Agent Run: /api/v1/agents/{id}/run (agent_run.py)            │ │
│ │  ├─ Medical path: _MEDICAL_CODING_AGENT_IDS frozenset        │ │
│ │  │   → CodingRuntimeDispatcher → MedCodER 5-stage            │ │
│ │  └─ Generic path: _run_via_provider_registry                 │ │
│ │      → _load_pack_by_agent_id (❌ 只扫 official_agents/)     │ │
│ │      → ProviderRegistry.resolve_from_agent_pack              │ │
│ │      → PureLLMProvider → LLMGateway → DeepSeek               │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ OAuth Clients (内部): /api/oauth/clients (oauth.py)           │ │
│ │  └─ create / list / delete (无 rotate / disable)             │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ API Clients (partner): /api/v1/api-clients                    │ │
│ │   (platform_api_clients.py)                                   │ │
│ │  └─ 完整生命周期 (rotate / disable / enable / scopes)         │ │
│ └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│ External Consumer (examples/)                                     │
│  ├─ partner-reference-app/ (web component embed)                  │
│  └─ external-agent-consumer/ (❌ 待新增 — pure REST + SDK)        │
└──────────────────────────────────────────────────────────────────┘
```

**红色 ❌ 标记** = Sprint 2 需修复的断点。
