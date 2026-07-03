# LEGACY_REFERENCE_CUTOVER_REPORT — Phase 2-B Legacy 引用切断报告

> **声明**: 本文档记录 Phase 2-B 执行的 legacy Agent 引用切断.
> **日期**: 2026-07-02
> **阶段**: Phase 2 — Agentic Framework Mainline Cutover — Phase 2-B
> **状态**: COMPLETED

---

## 0. 执行摘要

| 引用点 | 操作 | 结果 |
|---|---|---|
| `app/agents/__init__.py:2` | 删 `from app.agents.orchestrator import AgentOrchestrator` | ✅ |
| `app/api/reviews.py:27` | 替换为 `_LegacyOrchestratorStub` (run_pipeline raises NotImplementedError) | ✅ |
| `app/api/agents.py:20` | 替换为 `_LegacyAgentRunnerStub` (run/stream raises NotImplementedError) | ✅ |

**验证**: app import OK (299 routes), health_check 7/7 PASS, 0 remaining legacy imports.

---

## 1. 引用切断详情

### 1.1 app/agents/__init__.py (TD-038 关联)

**Before** (113 bytes):
```python
# iCoDer - Agents Package
from app.agents.orchestrator import AgentOrchestrator

__all__ = ["AgentOrchestrator"]
```

**After**:
```python
# iCoDer - Agents Package
# Phase 2-B (2026-07-02): legacy orchestrator reference cut.
# AgentOrchestrator is DEPRECATED; new orchestrator at app/icoder/agent_runtime/orchestrator/.
# Callers should import from app.icoder.agent_runtime.orchestrator directly.
# __all__ = ["AgentOrchestrator"]  # removed in Phase 2-B
```

**效果**: `from app.agents import AgentOrchestrator` 不再可用, 强制调用方用新路径 `app.icoder.agent_runtime.orchestrator`.

### 1.2 app/api/reviews.py:27 (TD-051 关联)

**Before**:
```python
from app.agents.orchestrator import agent_orchestrator
```

**After** (inline stub):
```python
# Phase 2-B (2026-07-02): legacy orchestrator reference cut.
# agent_orchestrator moved to app/icoder/agent_runtime/orchestrator/.
# Stub surfaces any accidental legacy calls during Phase 2-C deletion window.
class _LegacyOrchestratorStub:
    async def run_pipeline(self, *a, **kw):
        raise NotImplementedError(
            "Legacy agent_orchestrator removed in Phase 2-B. "
            "Use app.icoder.agent_runtime.orchestrator instead."
        )
agent_orchestrator = _LegacyOrchestratorStub()
```

**影响调用点** (4 处, 全部在 reviews.py, DEPRECATED 文件):
- line 74: `await agent_orchestrator.run_pipeline(encounter_data, progress_callback=progress_callback)`
- line 83: 同
- line 90: 同
- line 93: 同

**策略**: reviews.py 整体 DEPRECATED (P1.3 Stage 5 标记), Phase 2-C 物理删. 此处 stub 确保任何意外调用立即 raise, 不会静默走 legacy.

### 1.3 app/api/agents.py:20 (TD-056 关联)

**Before**:
```python
from app.services.agent_runner import agent_runner
```

**After** (inline stub):
```python
# Phase 2-B (2026-07-02): legacy agent_runner reference cut.
# agent_runner moved to app/icoder/agent_runtime/orchestrator/.
# Stub surfaces any accidental legacy calls during Phase 2-C deletion window.
class _LegacyAgentRunnerStub:
    async def run(self, *a, **kw):
        raise NotImplementedError(
            "Legacy agent_runner.run removed in Phase 2-B. "
            "Use platform_runtime.run_agent instead."
        )
    async def stream(self, *a, **kw):
        raise NotImplementedError(
            "Legacy agent_runner.stream removed in Phase 2-B. "
            "Use platform_runtime.stream_agent instead."
        )
agent_runner = _LegacyAgentRunnerStub()
```

**影响调用点** (2 处, 全部在 agents.py legacy fallback path):
- line 454: `output = await agent_runner.run(...)`
- line 482: `async for token in agent_runner.stream(...)`

**策略**: agents.py 已有注释 "legacy: uses app.services.agent_runner (old DB-based path)" + "Falling back to legacy agent_runner...". 该 fallback 路径已 stub 化, 任何触发都会 raise. 主路径用 platform_runtime.run_agent.

---

## 2. 验证

### 2.1 无残留 legacy imports

```
grep -rn "from app.agents.orchestrator\|from app.services.agent_runner\|from app.agents import" app/
→ (empty after filtering Phase 2-B comments)
```

### 2.2 App 导入

```
python -c "from app.main import app; print('OK, routes:', len(app.routes))"
→ OK, routes: 299
```

### 2.3 health_check (7/7 PASS)

```
[PASS] alembic_head         at head: 008
[PASS] schema_drift         0 divergences
[PASS] agents_installed     28 agents
[PASS] runtime_started      started=true
[PASS] registry_sync        last_status=success
[PASS] auth_register        registered
[PASS] auth_login           logged in
VERDICT: PASS  (7/7 passed)
```

---

## 3. Stub 行为说明

`_LegacyOrchestratorStub` 和 `_LegacyAgentRunnerStub` 的设计:

- **不静默**: 任何调用立即 raise `NotImplementedError`, 不会假装成功
- **消息明确**: 错误消息指向新路径 (`app.icoder.agent_runtime.orchestrator` / `platform_runtime.run_agent`)
- **临时**: Phase 2-C 物理删 reviews.py + agents.py legacy 路径后, stub 一起删

---

## 4. 不可删 legacy (Phase 2-C 评估)

以下 legacy 文件**不在 Phase 2-B 切断范围** (因无引用或实验性):

| 文件 | 原因 |
|---|---|
| `app/services/agent_runner.py` (1047 LOC) | Phase 2-B 已断 agents.py 引用, 但文件本身 Phase 2-C 删 |
| `icoder_runtime/agent_runner.py` | 无外部引用 (P1.3 已验证), Phase 2-C 删 |
| `app/agents/orchestrator.py` + `base.py` + 11 experts | __init__.py 已断 re-export, 但文件本身 Phase 2-C 删 |
| `icoder_runtime/m2a/` (5 .py) | 非空, 需 Phase 2 重新评估 (TD-009) |
| 4 experimental services (gold_case_importer + gold_case_template + inter_rater + pilot_report_builder + ccl2026_importer) | 实验性保留, 不删 |

---

## 5. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, Phase 2-B 完成 (3 引用点切断 + stub 化) | Phase 2-B |
