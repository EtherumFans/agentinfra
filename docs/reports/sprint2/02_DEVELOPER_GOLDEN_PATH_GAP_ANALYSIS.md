# 02 — Developer Golden Path Gap Analysis

**Date**: 2026-08-07
**Scope**: 对照 prompt §一 "目标流程" 7 步, 找出每一步的 UX/UI/Backend gap

---

## 1. 目标流程 (per prompt §一)

```
Developer
  ↓ (1)
Agent Hub
  ↓ (2)
Create Agent
  ↓ (3)
Instructions
  ↓ (4)
Runtime
  ↓ (5)
Test Console
  ↓ (6)
Generate Code
  ↓ (7)
API Client
  ↓ (8)
External Application
  ↓ (9)
Response
```

---

## 2. 逐步 Gap 分析

### Step 1 → 2: Developer → Agent Hub

| 项 | 状态 | 备注 |
|----|------|------|
| 登录入口 (`/console`) | ✅ | Username/password + OAuth |
| Hub 列表页 (`/ai-studio/agents`) | ✅ | `AgentsPage.tsx` 含 My Agents + Prebuilt tabs |
| 分类筛选 (use_case) | ✅ | 5 use_case enum + server-side filter |
| 搜索 | ✅ | `search` query param |
| 创建入口 (CTA) | ✅ | "New Agent" 按钮 → 弹 clone picker |

**Gap**: ❌ None. 流畅。

---

### Step 2 → 3: Hub → Create Agent

| 项 | 状态 | 备注 |
|----|------|------|
| 从 template 创建 | ✅ | `POST /agent_definitions/{id}/clone` |
| 从 blank 创建 | ⚠️ | UI 上有, 但 20 个 template 全部医疗域 |
| **Generic / blank template** | ❌ | `AGENT_TEMPLATES` 无 `generic-blank` / `summarizer-blank` |
| 表单字段 (name/desc/instructions) | ✅ | `AgentCreate` schema 完整 |
| Runtime 选择 | ❌ | UI 无 runtime/model/provider 选择控件 |
| Model / Provider 选择 | ❌ | 无, 当前默认 DeepSeek |
| Input/Output schema 编辑器 | ❌ | 无 |
| `medcoder_*` 默认要求 | ✅ | **未要求** — `AgentCreate` schema 不含 medcoder 字段 (Goal A 已合规) |

**Gap**: ❌ **CRITICAL** — 没有 generic template, 开发者要"从空白开始"必须从已有 medical agent clone 后修改, 这违背 prompt §三 Goal A。

---

### Step 3 → 4: Configure Instructions

| 项 | 状态 | 备注 |
|----|------|------|
| Instructions 编辑器 | ✅ | `system_prompt` 字段, UI textarea |
| Model 参数 (temperature 等) | ❌ | UI 无, schema 也无 |
| Tool 选择 (search_icd / verify_code 等 MCP tools) | ⚠️ | `expert_ids` 间接控制 tools |
| Permissions 配置 | ❌ | UI 无, 后端 permissions 来自 agent_pack.json |

**Gap**: ⚠️ Instructions 编辑 OK, 但 model / tool / permissions 配置不可达。

---

### Step 4 → 5: Configure → Runtime (Test)

| 项 | 状态 | 备注 |
|----|------|------|
| **Custom Agent 可运行** | ❌ **CRITICAL** | `_load_pack_by_agent_id` 不查 DB → custom agent 报 `unknown_agent` |
| Real runtime call (not mock) | ✅ | 真调 ProviderRegistry / CodingRuntimeDispatcher |
| Streaming 输出 | ⚠️ | endpoint 是 request/response, 前端模拟 typing |
| Run ID 显示 | ✅ | response.run_id |
| Status (running/completed/failed) | ✅ | response.error + error_reason |
| Trace URL (deep link) | ✅ | response.trace_url |
| 错误友好提示 | ✅ | HTTP 200 + error=true (永不 5xx) |

**Gap**: ❌ **CRITICAL** — Custom agent runtime 路径断链。Sprint 2 必须修。

---

### Step 5 → 6: Test → Generate Code

| 项 | 状态 | 备注 |
|----|------|------|
| Code Tab 存在 | ✅ | `SettingsCodeTab` + `CodeSnippet` |
| cURL 格式 | ✅ | CodeSnippet tabs 含 `curl` |
| JavaScript SDK 格式 | ✅ | CodeSnippet tabs 含 `javascript` |
| Python 格式 | ✅ | CodeSnippet tabs 含 `python` |
| **真实 agent_id 注入** | ⚠️ | 需要验证 — 可能是 placeholder `<your-agent-id>` |
| **真实 endpoint URL** | ⚠️ | baseURL 是 `localhost:8000` or `api.icoder.cloud`? |
| 复制按钮 | ✅ | 2-second Check icon feedback |
| 一键运行示例 | ❌ | 没有 "Run this example" 按钮 |

**Gap**: ⚠️ 需验证 Code Tab 实际填充。如果 agent_id 是 placeholder, Sprint 2 Goal E 需修复。

---

### Step 6 → 7: Generate Code → API Client

| 项 | 状态 | 备注 |
|----|------|------|
| API Clients 页面 | ✅ | `APIClientsPage.tsx` |
| Create API Client | ✅ | `oauthApi.create` |
| Reveal secret once | ✅ | Modal + 复制按钮 |
| **Rotate secret** | ❌ | UI 无按钮 (后端 platform_api_clients 有 endpoint) |
| **Disable client** | ❌ | UI 无 toggle (后端 platform_api_clients 有 endpoint) |
| Copy client_id | ✅ | 复制按钮 |
| Delete client | ✅ | Confirm modal |
| `last_used_at` 显示 | ⚠️ | UI 读, 后端不写 |
| `rotated_at` 显示 | ❌ | UI 无, model 无 column |

**Gap**: ❌ **HIGH** — Console UI 不调 partner endpoint, rotate/disable 完全不可达。

---

### Step 7 → 8: API Client → External Application

| 项 | 状态 | 备注 |
|----|------|------|
| SDK `@icoder/sdk` | ✅ | v1.0.0-beta.2, 16 resource classes |
| `client_credentials` flow | ✅ | `/api/oauth/token` (and realm variant) |
| partner-reference-app | ✅ | Express server + token exchange + web component embed |
| **external-agent-consumer (pure REST)** | ❌ | 待新增 |
| 浏览器 / 命令行 consumer | ❌ | 待新增 |
| Python SDK | ❌ | 不存在 (只 JS/TS) |

**Gap**: ❌ **HIGH** — 无独立 pure-REST consumer example。Sprint 2 Goal F 必须新增。

---

### Step 8 → 9: External Application → Response

| 项 | 状态 | 备注 |
|----|------|------|
| Agent Run endpoint (`/api/v1/agents/{id}/run`) | ✅ | 完整契约 |
| Idempotency-Key 支持 | ✅ | Phase 7 Gate 3 |
| Tenant-Name header hint | ✅ | JWT org_id authoritative |
| Response envelope | ✅ | 13-field `{run_id, trace_id, trace_url, cost, latency_ms, output, ...}` |
| Error envelope (HTTP 200 + error=true) | ✅ | Phase 4-F2 failure contract |
| **Cost in CNY** | ✅ | `{amount, currency: "CNY"}` |

**Gap**: ❌ None. 调用契约完整。

---

## 3. Gap 优先级排序 (按影响 + 修复成本)

| Gap | 影响范围 | 修复成本 | 优先级 |
|-----|---------|---------|--------|
| **G1**: Custom Agent runtime 断链 | Goal A/B/C/E/F | 中 (改 `agent_run.py` ~50 行) | 🔴 P0 |
| **G2**: Console UI 不调 platform_api_clients | Goal D | 中 (改 `oauthApi` + `APIClientsPage.tsx`) | 🔴 P0 |
| **G3**: 无 generic template | Goal A | 低 (加 2 个 entry 到 `AGENT_TEMPLATES`) | 🔴 P0 |
| **G4**: 无 external-agent-consumer | Goal F | 低 (新增 ~150 行 Node.js 脚本) | 🟡 P1 |
| **G5**: `last_used_at` backend 不写 | Goal D | 低 (`_handle_client_credentials` 加 1 行 + commit) | 🟡 P1 |
| **G6**: Code Tab placeholder 验证 | Goal E | 低 (Read 验证 + 可能微调) | 🟡 P1 |
| **G7**: Streaming SSE 未实现 | Goal C (UX) | 高 (endpoint 改造 + 前端 EventSource) | 🟢 P2 (defer) |
| **G8**: Model/Provider 选择 UI | UX | 高 (新 UI 控件 + schema 扩展) | 🟢 P2 (defer) |
| **G9**: Python SDK | Sprint 3+ | 高 (新建 package) | ⚪ defer |
| **G10**: Input/Output schema editor | Sprint 3+ | 高 (JSON Schema editor) | ⚪ defer |

---

## 4. Corti 对照 (per prompt §一.1 "Corti 作为默认体验基线")

| 能力 | Corti | iCoDer 当前 | iCoDer Sprint 2 后 |
|------|-------|------------|-------------------|
| Agent Hub 浏览 | ✅ | ✅ | ✅ |
| Blank agent 创建 | ✅ | ❌ | ✅ (G3 修复) |
| Instructions 编辑 | ✅ | ✅ | ✅ |
| Model / Provider 选择 | ✅ | ❌ | ⚠️ (defer to Sprint 3) |
| Test Console 真实运行 | ✅ | ⚠️ (custom 断链) | ✅ (G1 修复) |
| Streaming | ✅ | ⚠️ (假 typing) | ⚠️ (defer) |
| Code samples (curl/JS) | ✅ | ✅ | ✅ |
| API Client rotate | ✅ | ❌ UI / ✅ API | ✅ (G2 修复) |
| API Client disable | ✅ | ❌ UI / ✅ API | ✅ (G2 修复) |
| External consumer example | ✅ | ⚠️ (有 embed, 无 pure REST) | ✅ (G4 修复) |
| Run trace URL | ✅ | ✅ | ✅ |
| 13-field response envelope | ✅ | ✅ | ✅ |

**结论**: 修完 G1+G2+G3+G4 后, iCoDer 在开发者闭环核心能力上达到 Corti 基线。Streaming / Model 选择 / Python SDK 等次要能力 defer 到 Sprint 3+。

---

## 5. 不能在本 session 修复的 (依赖外部)

- **真实 LLM_API_KEY**: 当前 fallback 返回 `error_reason=llm_degraded`, 真实 Test Console 运行需要 Pilot env 提供 DeepSeek API key
- **Dev server 实际启动**: 浏览器 Playwright 验证需要本地 dev 环境 (前端 Vite + 后端 uvicorn)
- **真实医院数据库**: External consumer 端到端验证需要 Pilot tenant + 真实 OAuth Client

---

## 6. Gap → Implementation Plan 映射

详见 `03_IMPLEMENTATION_PLAN.md`:

- G1 (Custom Agent runtime) → 修改 `agent_run.py:_load_pack_by_agent_id` + 新增 `_load_pack_from_db`
- G2 (Console UI partner API) → 改 `frontend/src/services/api.ts:oauthApi` + `APIClientsPage.tsx`
- G3 (Generic templates) → `agents.py:AGENT_TEMPLATES` 加 2 entry
- G4 (External consumer) → 新增 `examples/external-agent-consumer/{server.mjs, README.md}`
- G5 (last_used_at write) → `oauth.py:_handle_client_credentials` 加 1 行
- G6 (Code Tab verify) → Read `AgentDetailPage.tsx` Code prop, 必要时修 placeholder
