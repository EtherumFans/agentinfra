# 03 — Sprint 2 Implementation Plan

**Date**: 2026-08-07
**Scope**: Goal A → Goal F + Verification + Final Report
**Constraint**: 工程可做子集优先, 不动 charter 5-tuple, 不发禁用 verdict, 不犯禁用 git op

---

## 0. 执行顺序 (依赖驱动)

```
Phase 1 — Review (5 docs)        ← 进行中
  ├─ 00_EXECUTIVE_REVIEW.md       ✅
  ├─ 01_CURRENT_AGENT_ARCHITECTURE.md  ✅
  ├─ 02_DEVELOPER_GOLDEN_PATH_GAP_ANALYSIS.md  ✅
  ├─ 03_IMPLEMENTATION_PLAN.md    ← 本文件
  └─ 04_RISK_ASSESSMENT.md        ⏳

Phase 2 — Implementation
  ├─ G3: Generic templates                (低, 独立)         ⏳
  ├─ G1: Custom Agent runtime DB fallback  (P0, 解锁 Goal B/C)  ⏳
  ├─ G5: last_used_at write                (低, 独立)         ⏳
  ├─ G2: Console UI partner API wiring     (P0, 解锁 Goal D)  ⏳
  ├─ G6: Code Tab verify                   (低, 验证)         ⏳
  └─ G4: External Consumer example         (中, 独立)         ⏳

Phase 3 — Verification
  ├─ Backend unit tests (custom agent run path)         ⏳
  ├─ Backend integration tests (API Client lifecycle)   ⏳
  └─ External consumer dry-run (mock LLM)               ⏳

Phase 4 — Final Report
  └─ docs/reports/sprint2/FINAL_REPORT.md               ⏳
```

---

## 1. G3: Generic Templates (Goal A) — 独立, 低风险

### 1.1 目标

为 `AGENT_TEMPLATES` 添加 2 个 Generic (非医疗) templates:
- `translator-blank` — 通用翻译 (英 ↔ 中, 医疗无关)
- `summarizer-blank` — 通用文档摘要

### 1.2 修改

**文件**: `backend/app/api/agents.py:502-703`

在 `AGENT_TEMPLATES = [...]` list 末尾插入:

```python
{
    "id": "translator-blank",
    "title": "通用翻译智能体 (Generic Translator)",
    "description": "通用文本翻译, 中英互译。无医疗依赖, 无 MedCodER, 无 ICD 编码。可作 Generic Agent 创建的起点。",
    "category": "通用",
    "icon": "Languages",
    "expert_ids": [],
    "config": {},
    "system_prompt": "<role>\nYou are a generic translation assistant. Translate text between Chinese and English. Preserve meaning, tone, and domain-specific terminology. No medical coding, no ICD lookup, no clinical reasoning.\n</role>\n\n<output_format>\nReturn only the translation. If the input is Chinese, translate to English. If English, translate to Chinese. If mixed, default to Chinese output.\n</output_format>"
},
{
    "id": "summarizer-blank",
    "title": "通用摘要智能体 (Generic Summarizer)",
    "description": "通用文档摘要, 适用于任意领域文本。无医疗依赖, 无 MedCodER, 无 ICD 编码。",
    "category": "通用",
    "icon": "AlignLeft",
    "expert_ids": [],
    "config": {},
    "system_prompt": "<role>\nYou are a generic document summarization assistant. Given any input text, produce a concise summary covering key points. Domain-agnostic — no medical, legal, or financial specialization.\n</role>\n\n<output_format>\nSummary:\n1. One-sentence overview\n2. Key points (3-5 bullets)\n3. Action items (if any)\n</output_format>"
},
```

### 1.3 验证

- ✅ Schema 兼容 (`AgentCreate` 接受这些字段)
- ✅ 不引入 `medcoder_*` / `coding_template` 字段
- ✅ category="通用" 是新分类 (与 medical 类目互斥)
- ✅ `expert_ids=[]` 不绑定任何 medical-specific expert
- ✅ system_prompt 显式声明 "no medical coding"

### 1.4 风险

无。`AGENT_TEMPLATES` 是 hardcoded list, 不影响 DB / Runtime / 已有 agent。

---

## 2. G1: Custom Agent Runtime DB Fallback (Goal B + C) — P0, 解锁闭环

### 2.1 目标

让 `_run_via_provider_registry` 能找到 DB 表里的 custom agent, 不再返回 `unknown_agent`。

### 2.2 修改

**文件**: `backend/app/api/agent_run.py`

**Step 1**: 新增 helper `_load_pack_from_db(agent_id, db)`:

```python
async def _load_pack_from_db(agent_id: str, db: AsyncSession) -> dict[str, Any] | None:
    """Load an agent_pack dict from the DB Agent table.
    
    Used as fallback when _load_pack_by_agent_id (which scans official_agents/)
    returns None. This is the path for user-created custom agents that don't
    have a physical agent_pack.json on disk.
    """
    from app.models.agent import Agent
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        return None
    # Synthesize an agent_pack dict from the DB row
    return {
        "format_version": "1.2",
        "agent_type": "certified",
        "agent_ref": f"icoder/{agent.id}@{agent.version or '1.0.0'}",
        "manifest": {
            "name": agent.name,
            "version": agent.version or "1.0.0",
            "description": agent.description or "",
            "category": agent.category or "general",
            "icon": agent.icon or "Bot",
            "tags": [],
            "maturity": "custom",
            "production_ready": False,
            "hidden_from_hub": False,
            "use_case": "generic",
        },
        "system_prompt": agent.system_prompt or "",
        "experts": [],
        "tools": [],
        "model": {
            "primary": "deepseek-chat",
            "fallback": "deepseek-chat",
            "temperature": 0.0,
            "max_tokens": 4096,
        },
        "permissions": {
            "key": f"custom-{agent.id}-default",
            "name": "Custom Agent Default",
            "description": "Default permissions for user-created agents.",
            "tools": {},
            "production_writeback_blocked": True,
        },
        "phi_redaction": "required",
        "context_required": True,
        "recorder_required": True,
        "metrics_required": True,
        "code": {},
        "integrity": {"sha256": "DB_SYNTHESIZED_NO_PACK_FILE"},
    }
```

**Step 2**: 修改 `_run_via_provider_registry` 签名加 `db: AsyncSession`, 改 line 842:

```python
# Before:
pack = _load_pack_by_agent_id(agent_id)
if pack is None:
    return _error_response(error_reason="unknown_agent", ...)

# After:
pack = _load_pack_by_agent_id(agent_id)
if pack is None:
    # Fallback: try DB Agent table for user-created custom agents
    pack = await _load_pack_from_db(agent_id, db)
if pack is None:
    return _error_response(error_reason="unknown_agent", ...)
```

**Step 3**: 把 `db` 传到 `_run_via_provider_registry` 调用点 (在 `run_agent` 中)。

### 2.3 验证

新增 backend test `tests/test_custom_agent_run.py`:
- ✅ Create a custom agent via DB
- ✅ POST `/api/v1/agents/{custom_id}/run` returns 200 with `error=false`
- ✅ response.result is non-empty (or `error_reason=llm_degraded` if no LLM key)
- ✅ Backend log: NO `CodingRuntimeDispatcher` import (MedCodER not loaded)

### 2.4 风险

- 🟡 `_run_via_provider_registry` 当前签名没有 `db`, 需要修改调用链传参
- 🟡 `ProviderRegistry.resolve_from_agent_pack` 期望真实 pack 字段, 需确认合成 dict 通过 schema validation
- 🟢 Migration: 无 DB schema 变更, 无 alembic 文件

### 2.5 MedCodER 解耦证明 (Goal B)

修完后, 跑一个 custom agent → backend 应满足:
- `app.coding_runtime.*` 未 import (sys.modules 检查)
- `icoder_runtime.providers.medical_coding.*` 未 import
- 只有 `icoder_runtime.backends.pure_llm_provider` 等通用模块加载

新增测试 `test_no_medcoder_imports_for_generic_agent.py` 用 `sys.modules` snapshot 验证。

---

## 3. G5: `last_used_at` Write — 低成本, 独立

### 3.1 修改

**文件**: `backend/app/api/oauth.py:_handle_client_credentials` (line 358+)

在 token issue 成功后, 加 1 行:
```python
client.last_used_at = datetime.now(timezone.utc)
db.add(client)
await db.flush()
```

### 3.2 验证

- 调 `/api/oauth/token` 两次 → 第二次 GET `/api/oauth/clients` 时 `last_used_at` 是新时间
- Console UI 自动展示 (已读 `c.last_used_at`)

### 3.3 风险

无。Single-line change, 向后兼容。

---

## 4. G2: Console UI Wiring to Platform API Clients (Goal D) — P0

### 4.1 目标

让 Console API Clients 页面调 `platform_api_clients.py` 的 rotate/disable/enable endpoints。

### 4.2 修改

**文件**: `frontend/src/services/api.ts:170-179`

扩展 `oauthApi`:

```ts
export const oauthApi = {
  // Existing (kept for back-compat)
  list: () => api.get<{ clients: any[] }>('/v1/api-clients'),  // 改路径
  create: (name: string, description = '', scopes = 'api:read api:write', tokenExpires = 3600) => {
    const params = new URLSearchParams({ name, description, scopes, token_expires_seconds: String(tokenExpires) });
    return api.post<{ client_id: string; client_secret: string; name: string; scopes: string }>('/v1/api-clients', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  },
  delete: (clientId: string) => api.delete(`/v1/api-clients/${clientId}`),

  // NEW (Phase 7 platform_api_clients)
  rotate: (clientId: string) => api.post<{ client_secret: string }>(`/v1/api-clients/${clientId}/rotate`),
  disable: (clientId: string) => api.post(`/v1/api-clients/${clientId}/disable`),
  enable: (clientId: string) => api.post(`/v1/api-clients/${clientId}/enable`),
  patchScopes: (clientId: string, scopes: string) => api.patch(`/v1/api-clients/${clientId}/scopes`, { scopes }),
};
```

**文件**: `frontend/src/pages/APIClientsPage.tsx`

在每个 client row 加 2 个按钮:
- 🔄 Rotate (调 `oauthApi.rotate`, 弹 reveal-once modal 同 create flow)
- ⏻ Disable / Enable (调 `oauthApi.disable` / `enable`, 切换 `is_active` 状态)

### 4.3 验证

- ✅ 创建 client → 调 rotate → 新 secret reveal-once
- ✅ 创建 client → disable → list 显示 `is_active=false`
- ✅ Disabled client 调 `/api/oauth/token` 返回 401 `invalid_client`

### 4.4 风险

- 🟡 后端两个 endpoint 系列 (oauth.py vs platform_api_clients.py) 可能用不同的 client_id 命名空间 — 需验证它们共享同一 `oauth_clients` 表
- 🟢 UI 变更, 无 DB migration

---

## 5. G6: Code Tab Verification (Goal E) — 验证, 可能微调

### 5.1 验证步骤

Read `frontend/src/pages/AgentDetailPage.tsx` 找 `<CodeSnippet javascript={...} curl={...} />` 调用点:
- 检查 `javascript` prop 是否注入 `agent.id` (而非 placeholder)
- 检查 `curl` prop 是否含真实 endpoint URL (`/api/v1/agents/{agent.id}/run`)
- 检查 `Bearer $TOKEN` 是否带说明 ("替换为你的 access_token")

### 5.2 可能修复

如果发现 placeholder, 修成真实 `agent.id` + 真实 URL + 文档链接。

### 5.3 风险

低。Read + 微调。

---

## 6. G4: External Consumer Example (Goal F) — 中等成本

### 6.1 目标

新增 `examples/external-agent-consumer/` — 一个独立的 Node.js 脚本, 完成:
1. 用 client_credentials 拿 access_token
2. 调 `/api/v1/agents/{id}/run` 跑一个 agent
3. 打印 response

### 6.2 修改

**新增文件**:
- `examples/external-agent-consumer/package.json` — 依赖 only `node-fetch` (Node 18+ 内置)
- `examples/external-agent-consumer/run-agent.mjs` — 主脚本
- `examples/external-agent-consumer/README.md` — 用法
- `examples/external-agent-consumer/.env.example` — env vars

**主脚本框架**:
```js
// run-agent.mjs
const BASE_URL = process.env.ICODER_BASE_URL || 'http://localhost:8000';
const CLIENT_ID = requiredEnv('ICODER_API_CLIENT_ID');
const CLIENT_SECRET = requiredEnv('ICODER_API_CLIENT_SECRET');
const AGENT_ID = process.env.ICODER_AGENT_ID || 'translator-blank';
const INPUT_TEXT = process.env.ICODER_INPUT_TEXT || 'Hello, world.';

// 1. Exchange token
const tokenResp = await fetch(`${BASE_URL}/api/oauth/token`, {
  method: 'POST',
  headers: { 'content-type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: CLIENT_ID,
    client_secret: CLIENT_SECRET,
    scope: 'api:read api:write',
  }),
});
const { access_token } = await tokenResp.json();

// 2. Run agent
const runResp = await fetch(`${BASE_URL}/api/v1/agents/${AGENT_ID}/run`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access_token}`,
    'Content-Type': 'application/json',
    'Idempotency-Key': `consumer-${Date.now()}`,
  },
  body: JSON.stringify({
    input: { text: INPUT_TEXT },
  }),
});
const result = await runResp.json();

console.log('run_id:', result.run_id);
console.log('trace_url:', result.trace_url);
console.log('cost:', result.cost);
console.log('output:', result.result);
```

### 6.3 验证

- ✅ 脚本不 import 任何 iCoDer 内部模块
- ✅ 脚本不访问 iCoDer 数据库
- ✅ 只通过 REST API
- ✅ `Idempotency-Key` 头正确使用

### 6.4 风险

- 🟡 需要 backend 真实启动 + 真实 LLM key 才能完整跑通; 本 session 可只能 dry-run syntax check

---

## 7. Verification Phase

### 7.1 Backend 自动化测试

新增 `backend/tests/test_sprint2_developer_golden_path.py`:

```python
# test_generic_template_exists
def test_generic_templates_in_agent_templates():
    response = client.get('/api/rest/v1/agent_definitions/templates')
    template_ids = [t['id'] for t in response.json()['templates']]
    assert 'translator-blank' in template_ids
    assert 'summarizer-blank' in template_ids

# test_custom_agent_runtime_path
async def test_custom_agent_runs_via_provider_registry():
    # 1. Create custom agent
    create_resp = await client.post('/api/rest/v1/agent_definitions', json={...})
    agent_id = create_resp.json()['id']
    # 2. Run it
    run_resp = await client.post(f'/api/v1/agents/{agent_id}/run', json={...})
    assert run_resp.status_code == 200
    body = run_resp.json()
    assert body['error'] is False or body['error_reason'] == 'llm_degraded'

# test_no_medcoder_for_generic_agent
def test_no_medcoder_module_imported_for_generic(monkeypatch):
    import sys
    snapshot = set(sys.modules.keys())
    # Trigger a generic agent run
    ...
    after = set(sys.modules.keys())
    new_modules = after - snapshot
    assert not any('coding_runtime' in m for m in new_modules)
    assert not any('medcoder' in m for m in new_modules)

# test_api_client_lifecycle
async def test_api_client_rotate_disable_enable():
    # Create
    create_resp = await client.post('/v1/api-clients', ...)
    client_id = create_resp.json()['client_id']
    # Rotate
    rotate_resp = await client.post(f'/v1/api-clients/{client_id}/rotate')
    assert rotate_resp.json()['client_secret']
    # Disable
    await client.post(f'/v1/api-clients/{client_id}/disable')
    # Token exchange should fail
    token_resp = await client.post('/api/oauth/token', ...)
    assert token_resp.status_code == 401
```

### 7.2 浏览器验证 (本 session 不一定完成)

- Login (`/login`)
- Navigate to Agents Hub (`/ai-studio/agents`)
- Create from `translator-blank` template
- Edit system_prompt
- Open Test Console
- Send message → see response
- Switch to Code tab → see curl + JS samples
- Navigate to API Clients (`/console/api-clients`)
- Create new client → see reveal-once modal
- Rotate secret → see new modal
- Disable → see status change

### 7.3 External Consumer 验证

```bash
cd examples/external-agent-consumer
npm install  # only node-fetch if Node < 18
export ICODER_BASE_URL=http://localhost:8000
export ICODER_API_CLIENT_ID=...
export ICODER_API_CLIENT_SECRET=...
node run-agent.mjs
```

预期: 打印 run_id + trace_url + output。

---

## 8. Final Report Phase

`docs/reports/sprint2/FINAL_REPORT.md` 含 12 节 (per prompt §七):

1. Sprint 2 最终判断
2. 是否修改原计划
3. 当前 Agent 架构
4. Golden Path 完成情况
5. Generic Agent 验证
6. MedCodER 独立性证明
7. API Client 验证
8. External Consumer 验证
9. 浏览器验证
10. 测试结果
11. 未完成事项
12. 下一阶段建议

---

## 9. 提交策略

按 Goal 边界拆 commit (便于回滚):

1. `audit/sprint2: G3 — generic templates (translator-blank, summarizer-blank)`
2. `audit/sprint2: G1 — custom agent runtime DB fallback + no-medcoder test`
3. `audit/sprint2: G5 — last_used_at write in _handle_client_credentials`
4. `audit/sprint2: G2 — Console UI wiring to platform_api_clients (rotate + disable)`
5. `audit/sprint2: G6 — Code Tab verification (or merged into G2)`
6. `audit/sprint2: G4 — external-agent-consumer example`
7. `audit/sprint2: FINAL_REPORT`

或合并为 1 个大 commit。倾向**单一 Sprint 2 commit** — 避免中间状态不可独立验证。

---

## 10. Charter 合规检查表

- [ ] 5-tuple NOT MUTATED (GATE4_8 / GATE4_9 / GATE4_ACCEPTANCE / CORTI_PARITY / PRODUCTION_READINESS)
- [ ] 8 forbidden verdicts NOT EMITTED (用 PARTIAL_*_FILED)
- [ ] 12 forbidden git ops NOT PERFORMED (no push, no master, no amend, no -A)
- [ ] 货币 CNY (¥), 无 USD
- [ ] 不删除历史证据 (Sprint 1 commit `273370e` 保留)
- [ ] 不覆盖已有报告 (新 docs/reports/sprint2/ 文件)
- [ ] 不增加 Agent 数量 (G3 加的是 template 不是 agent)
- [ ] 不开发 MedCodER 能力 (只验证 MedCodER **不**被 generic agent 加载)
- [ ] 不创建第二套 Runtime (复用 ProviderRegistry)
- [ ] 不创建第二套 SDK (复用 @icoder/sdk)
- [ ] 不 mock 冒充真实 (real LLM key 不在本 session, 验证用 `error_reason=llm_degraded`)
