# PHASE2_TESTING_VERIFICATION_REPORT — Phase 2-H 回归 + Browser QA 报告

> **声明**: 本文档记录 Phase 2-H 执行的 4 轮回归 + Browser QA.
> **日期**: 2026-07-02
> **阶段**: Phase 2 — Agentic Framework Mainline Cutover — Phase 2-H
> **状态**: COMPLETED (R3 PARTIAL — 见 §3)

---

## 0. 执行摘要

| Round | 范围 | 结果 |
|---|---|---|
| R1 | Backend schema / health | ✅ PASS (alembic 008, 0 drift, 7/7 health) |
| R2 | API contract + frontend | ✅ PASS (64 backend + 71 frontend tests, tsc 0) |
| R3 | Browser e2e | ⚠️ PARTIAL (pages 200, auth API OK, Playwright auth.setup 失败 — 预存 infra issue) |
| R4 | 综合 | ✅ PASS (R1+R2 green, R3 partial 有明确原因) |

**关键发现**: Phase 2-C 删除 `icoder_runtime/agent_runner.py` 导致 `PlatformRuntime` import 失败 (28 test errors). 已修复 — 恢复为 stub (Phase 2-B stub 模式同款).

---

## 1. R1 — Backend schema / health

### 1.1 Alembic

```
python -m alembic current
→ 008 (head)
```

### 1.2 Schema drift

```
python scripts/check_schema_drift.py
→ OK — 0 divergences across 33 tables / 473 columns
```

### 1.3 health_check (7/7 PASS)

```
[PASS] alembic_head         (1063ms)  at head: 008
[PASS] schema_drift         (770ms)   0 divergences across 33 tables / 473 columns
[PASS] agents_installed     (2ms)     28 agents in DB
[PASS] runtime_started      (2188ms)  started=true (providers: ['mock', 'medical_coding', 'deepseek'])
[PASS] registry_sync        (0ms)     last_status=success, agents_created=12
[PASS] auth_register        (2405ms)  registered healthcheck_27331ba3
[PASS] auth_login           (2432ms)  logged in healthcheck_27331ba3
VERDICT: PASS  (7/7 passed)
```

**R1 结论**: PASS.

---

## 2. R2 — API contract + frontend

### 2.1 Backend tests

```
python -m pytest tests/unit/app/api/ tests/unit/scripts/ -q
→ 64 passed, 53 warnings in 55.67s
```

**初轮 28 errors → 修复后 0 errors**: 见 §5 regression fix.

### 2.2 Frontend tsc

```
npx tsc --noEmit
→ exit 0 (no errors)
```

### 2.3 Frontend vitest

```
npx vitest run
→ 2 test files, 71 tests passed (apiContract 62 + locales 9)
→ Duration 1.09s
```

**Phase 2-G vite config fix 验证**: vitest 现在自动排除 `e2e/**` 和 `tests/e2e/**` (Playwright specs), 不再误跑.

**R2 结论**: PASS.

---

## 3. R3 — Browser e2e

### 3.1 Frontend pages (curl 200)

```
/                          -> 200
/login                     -> 200
/customers                 -> 200
/templates                 -> 200
/tickets                   -> 200
/ai-studio/medical-coding  -> 200
/settings                  -> 200
```

### 3.2 Auth API (curl 验证)

```
POST /api/auth/register  {username:e2e_test, password:Test1234!, email, full_name}
→ 200, access_token present

POST /api/auth/login     {username:e2e_test, password:Test1234!}
→ 200, access_token present
```

### 3.3 Playwright smoke (auth.setup.ts 失败)

```
npx playwright test smoke-test
→ 1 failed (setup: authenticate)
→ Error: POST /api/auth/login {admin, admin123} → 401 Invalid credentials
```

**原因**: `app/config.py:23` `SEED_ON_STARTUP: bool = False` (Cloud-Flip 2026-06-27 默认翻转). 运行中的 backend 未 seed admin/admin123 用户. Playwright auth.setup.ts 硬编码依赖 admin/admin123.

**不是 Phase 2 回归**: 此 issue 在 Phase 2 之前就存在 (Cloud-Flip 决策). Phase 1.0 OAuth Corti parity (2026-06-30) 已记录此默认值.

**R3 结论**: PARTIAL. 页面 200, auth API 工作 (register+login 验证), 但 Playwright auth.setup 因预存 infra issue 失败. 不阻塞 Phase 2 VERDICT.

---

## 4. R4 — 综合

| 验证项 | 结果 |
|---|---|
| Backend schema | ✅ 0 drift |
| Backend health | ✅ 7/7 |
| Backend tests | ✅ 64 passed |
| Frontend tsc | ✅ 0 errors |
| Frontend vitest | ✅ 71 passed |
| Frontend pages | ✅ 7/7 return 200 |
| Auth API | ✅ register+login works |
| A2A mainline smoke | ✅ Phase 2-D 验证 (4 experts, 10.9s) |
| MCP tools/call | ✅ Phase 2-D 验证 (search_icd) |
| Playwright e2e | ⚠️ auth.setup fails (pre-existing, admin not seeded) |

**R4 结论**: PASS (R1+R2 green, R3 partial 有明确预存原因).

---

## 5. 回归修复 — agent_runner.py stub

### 5.1 问题

Phase 2-C 删除 `icoder_runtime/agent_runner.py` (LEGACY_DELETION_REPORT §1.2) 时, 漏检 `icoder_runtime/embedded/platform_runtime.py:27` 的 import:

```python
from ..agent_runner import AgentRunner  # ← ModuleNotFoundError
```

**影响**: 
- 28 个 `test_icoder_agents_hub.py` 测试 ERROR at setup (fixture 启动 app 时 lifespan 触发 import)
- 运行中的 backend (port 8000) 因旧代码在内存中未受影响, 但**重启会失败**

### 5.2 修复

恢复 `icoder_runtime/agent_runner.py` 为**最小 stub** (Phase 2-B stub 模式同款):

```python
class AgentRunner:
    def __init__(self, gateway=None, config=None, data_policy=None): ...
    def register_expert(self, expert): ...  # no-op
    def register_tool(self, tool): ...      # no-op
    async def run(self, *a, **kw):          # raise NotImplementedError
    async def stream(self, *a, **kw):       # raise NotImplementedError
    def status(self): ...                   # 返回 stub 状态
```

### 5.3 验证

**单元验证**:
```
python -c "from icoder_runtime.embedded.platform_runtime import PlatformRuntime; ..."
→ PlatformRuntime import: OK
→ AgentRunner stub: OK
→ register_expert/register_tool: OK (no-op)
→ run() raises NotImplementedError: OK
```

**测试验证**:
```
python -m pytest tests/unit/app/api/test_icoder_agents_hub.py -q
→ 17 passed (修复前 28 errors)
```

**Fresh start 验证** (port 8090, 不影响运行中的 port 8000):
```
timeout 30 python -m uvicorn app.main:app --port 8090
→ /api/health: 200
→ /api/runtime/status: started=True, providers=['mock','medical_coding','deepseek']
```

### 5.4 后续

`PlatformRuntime` 仍 wrap 旧 `AgentRunner` stub. 后续 cycle 需:
1. 将 `app/api/{admin,agents,evaluation,fhir}.py` 的 `platform_runtime` 调用迁到新 orchestrator
2. 删 `PlatformRuntime` 或重构为 wrap `InboundHandler`
3. 删 `icoder_runtime/agent_runner.py` stub

---

## 6. 成功标准进度

| # | 标准 | Phase 2-H 后状态 |
|---|---|---|
| 17 | 4 轮回归全绿 | ⚠️ R1+R2+R4 green, R3 partial (预存 infra, 非 Phase 2 回归) |
| 18 | Browser QA 通过核心流程 | ⚠️ 页面 200 + auth API OK, Playwright auth.setup 失败 (预存) |
| 19 | 无新增 regression | ✅ (Phase 2-C regression 已发现 + 修复) |

---

## 7. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, Phase 2-H 完成 (R1+R2+R4 PASS, R3 PARTIAL, 1 regression fixed) | Phase 2-H |
