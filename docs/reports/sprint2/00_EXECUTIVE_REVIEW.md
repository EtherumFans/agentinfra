# 00 — Sprint 2 Executive Review

**Date**: 2026-08-07
**Phase**: A1E Sprint 2 — Developer Golden Path Validation & Implementation
**Verdict (target)**: `PARTIAL_A1E_SPRINT_2_DEVELOPER_GOLDEN_PATH_*_FILED`
**Charter 5-tuple**: NOT MUTATED (carry-forward from Sprint 1 commit `273370e`)
**Forbidden verdicts / git ops**: 8 + 12 honoured

---

## 1. Sprint 2 核心问题

> 一个不了解 iCoDer 内部实现的开发者，是否可以像使用 Corti、OpenAI Assistants、Anthropic Claude Console 一样，在平台创建 Agent，并在自己的工作环境中调用它？

**短答**: **不能**。当前 iCoDer 在 Agent 创建 → 运行闭环中存在一处致命断链。

---

## 2. 当前能力总览 (evidence-based)

| 能力 | 状态 | 证据 |
|------|------|------|
| Agent Hub (浏览) | ✅ DONE | `/api/icoder/agents/hub` (Phase 3-B1) + `AgentsPage.tsx` |
| Agent CRUD (DB-stored) | ✅ DONE | `app/api/agents.py` 9 endpoints under `/api/rest/v1/agent_definitions` |
| 20 个 hardcoded templates | ✅ DONE | `agents.py:502-703` (但全部医疗域, 无 generic) |
| **Generic Template (blank agent)** | ❌ **MISSING** | `AGENT_TEMPLATES` 全部 medical, 无 `translator-blank` / `summarizer-blank` / `generic-llm` |
| **Runtime 调用 — Generic Agent 路径** | ❌ **BROKEN** | `agent_run.py:842` `_load_pack_by_agent_id` 只扫 `official_agents/`, 不查 DB Agent 表 |
| Runtime 调用 — Official Medical Agent | ✅ DONE | `_MEDICAL_CODING_AGENT_IDS` frozenset → CodingRuntimeDispatcher |
| Test Console UI (AgentChatPage) | ✅ DONE | `runtimeAgentApi.agentRun` → `POST /api/v1/agents/{id}/run` |
| Streaming 输出 | ⚠️ PARTIAL | endpoint 是 request/response (not SSE), `AgentChatPage` 模拟 typing |
| Run ID / Trace URL | ✅ DONE | response 含 `{run_id, trace_id, trace_url}` |
| API Client: list/create/delete | ✅ DONE | `oauth.py:406-508` |
| API Client: rotate secret | ✅ DONE | `platform_api_clients.py:344-399` (partner endpoint) |
| API Client: disable / enable | ✅ DONE | `platform_api_clients.py:302-343` |
| API Client: PATCH scopes/origins | ✅ DONE | `platform_api_clients.py:400-435` |
| **Console UI 调用 platform_api_clients** | ❌ **MISSING** | `APIClientsPage.tsx` 只调 `oauthApi` (oauth.py), 不调 partner endpoint |
| `last_used_at` 字段 | ✅ DONE | `oauth.py:41` column exists |
| **`last_used_at` 写入 (oauth.py)** | ❌ **MISSING** | `_handle_client_credentials` 未写 `last_used_at` |
| Code Tab (SettingsCodeTab+CodeSnippet) | ✅ DONE | JS / Python / curl / JSON 四种格式 |
| External Consumer (partner-reference-app) | ✅ DONE | `examples/partner-reference-app/` Express 服务器 |
| **External Consumer (clean agent run example)** | ❌ **MISSING** | 无独立 `examples/external-agent-consumer/` 走完 create→run 闭环 |
| SDK `@icoder/sdk@1.0.0-beta.2` | ✅ DONE | 16 resource classes, `runs.runText()` |

---

## 3. 致命断链 (CRITICAL BREAK)

### 3.1 Custom Agent 无法运行

**症状**: 开发者在 Console 创建一个 Generic Agent → 在 Test Console 输入消息 → 后端返回 `unknown_agent` error。

**根因** (`agent_run.py:88-108, 842-857`):

```python
def _load_pack_by_agent_id(agent_id: str) -> dict[str, Any] | None:
    if not OFFICIAL_AGENTS_DIR.exists():
        return None
    for path in sorted(OFFICIAL_AGENTS_DIR.rglob("agent_pack.json")):
        ...
        if _agent_id_from_ref(ref) == agent_id:
            return pack
    return None  # ← Custom DB-stored agents 永远走这里
```

**影响**:
- Sprint 2 Goal A (Generic Agent Creation) 创建后, **Goal B (Runtime decoupling)** 验证会失败
- Test Console (Goal C) 对 custom agent 报 `unknown_agent`, 用户体验崩溃
- External Consumer (Goal F) 无法演示 create→run 闭环

**修复**: `agent_run.py` 需要 fallback 到 DB Agent 表 (`select(Agent).where(Agent.id == agent_id)`),把 DB row 合成 agent_pack dict 传给 ProviderRegistry。

### 3.2 Console UI 不调 partner 端点

**症状**: Console API Clients 页面无法 rotate secret / disable client。

**根因** (`APIClientsPage.tsx: 38-50` + `services/api.ts:170-179`):
```ts
const oauthApi = {
  list: () => api.get('/oauth/clients'),
  create: (...) => api.post('/oauth/clients', params, ...),
  delete: (clientId) => api.delete(`/oauth/clients/${clientId}`),
  // ❌ NO rotate, NO disable, NO enable
};
```

后端 `platform_api_clients.py` 已有完整生命周期, 但 Console UI 不调用它。

**影响**: Sprint 2 Goal D (API Client lifecycle) 在 Console 不可用。

**修复**: 把 `oauthApi` 扩展为调 `/api/v1/api-clients/*` (platform_api_clients) 而不是 `/api/oauth/clients/*` (oauth.py 内部 endpoint)。

---

## 4. 产品决策回顾 (与 prompt §一对照)

| 决策 | 当前状态 | 行动 |
|------|---------|------|
| Corti 作为默认体验基线 | ⚠️ 部分 — Code Tab / Test Console 已 Corti-style | 保留, 不需变更 |
| 不实现 Corti Agent 导入 | ✅ N/A — 当前无 Corti 导入代码 | 不动 |
| MedCodER 不是默认 Runtime | ❌ — 当前 `_MEDICAL_CODING_AGENT_IDS` frozenset 硬编码 routing | 验证至少 1 个 Generic Agent `MedCodER invocation = 0` |

---

## 5. 风险评估 (汇总, 详见 `04_RISK_ASSESSMENT.md`)

| 风险 | 等级 | 缓解 |
|------|------|------|
| Custom Agent runtime 断链 → Goal A/B/C/E/F 全部受影响 | 🔴 高 | 在 `agent_run.py` 加 DB fallback |
| Console UI 不调 partner API → Goal D 受影响 | 🟡 中 | 改 `oauthApi` 指向 platform_api_clients |
| Real LLM credentials 仍未 provisioned | 🔴 高 | 当前 fallback 返回 `error_reason=llm_degraded`, 不能演示真实运行 |
| Charter 禁止 mock 冒充真实运行 | 🔴 高 | Test Console 必须真实 LLM; 若无 key 则报错, 不 mock |
| 浏览器验证需 dev server 运行 | 🟡 中 | 当前 session 不一定有 dev server |

---

## 6. Sprint 2 执行策略

### 工程可做子集 (本 session 完成)
1. ✅ 5 个 review docs (含本文件)
2. ✅ Goal A: 添加 2 个 Generic templates (`generic-blank`, `summarizer-blank`) 到 `AGENT_TEMPLATES`
3. ✅ Goal B + C 修复: `agent_run.py` 加 DB fallback, 使 custom agent 真实可运行
4. ✅ Goal D 修复: 扩展 `oauthApi` 指向 platform_api_clients endpoints
5. ✅ Goal E: 验证 Code Tab 真实可运行 (cURL + JS)
6. ✅ Goal F: 新增 `examples/external-agent-consumer/` 独立消费者
7. ✅ Backend 单元测试覆盖 custom agent runtime path
8. ✅ FINAL_REPORT.md

### 超出本 session 范围 (依赖外部)
- 真实 LLM_API_KEY provisioning (Pilot env)
- Dev server / Playwright 浏览器验证 (需要本地 dev 环境)
- Docusaurus 部署 (Sprint 1 已交付 scaffold)

---

## 7. Charter 合规

- **5-tuple** (GATE4_8 / GATE4_9 / GATE4_ACCEPTANCE / CORTI_PARITY / PRODUCTION_READINESS): NOT MUTATED
- **8 forbidden verdicts**: NOT EMITTED — 使用 `PARTIAL_*_FILED`
- **12 forbidden git ops**: NOT PERFORMED — 显式文件清单, 无 `-A`, 无 push, 无 master, 无 amend
- **货币约定**: CNY (¥) — 无 USD 引用

---

## 8. 下一步 (Phase 1 review docs 完成后)

进入 Phase 2 实施 — 按 `03_IMPLEMENTATION_PLAN.md` 顺序执行 Goal A→F, 每个 Goal 完成后更新对应 task。最后产出 `FINAL_REPORT.md`。
