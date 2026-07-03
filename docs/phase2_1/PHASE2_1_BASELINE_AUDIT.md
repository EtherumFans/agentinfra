# Phase 2.1 — Baseline Audit (Phase 0)

> **日期**: 2026-07-02
> **执行人**: Runtime 架构师 (Claude)
> **阶段**: Phase 0 — 基线盘点
> **目的**: 在进入 Phase 2.1-A~G 之前，盘点当前代码、API、服务、Browser QA 状态，建立可量化基线，使后续每一步改动可对照本基线判定无回归。
> **状态**: BASELINE LOCKED

---

## 0. 执行摘要

| 维度 | 当前状态 | 后续阶段目标 |
|---|---|---|
| AgentRunner stub | `icoder_runtime/agent_runner.py` 仍是 stub (≈80 LOC)，被 `PlatformRuntime` import | 2.1-A: 去掉 stub 或明确保留原因 |
| 15 legacy API router | 全部已加 `# DEPRECATED` 头注释，但路由仍挂载且未物理删除 | 2.1-B: 每个有 mainline/compat/deprecated/deleted 状态；可删者物理删 |
| app/tools ↔ legacy experts | 5 个 tool 文件 import `app.agents.experts.*` | 2.1-C: 解耦或记录保留原因；可删的 legacy experts 物理删 |
| runtime.py / fhir.py / review_coding_service | runtime/review 已 DEPRECATED；fhir 未标 | 2.1-D: 每个有 mainline/experimental/deprecated/delete 结论 |
| icoder_runtime/m2a | 6 个 .py 文件 (非空，与 MAINLINE_VS_LEGACY.md 旧描述不符) | 2.1-E: 每个文件有 migrate/keep/archive/delete 结论 |
| Browser QA (Playwright) | `auth.setup.ts` 硬编码 `admin/admin123` | 2.1-F: 改为动态注册/seed；PARTIAL → PASS |
| 健康检查 | 7/7 PASS | 2.1-G: 保持 7/7 |
| schema drift | 0 | 2.1-G: 保持 0 |
| OpenAPI | 557,053 bytes (baseline) | 2.1-G: 无破坏性变更 |
| frontend tsc | PASS (0 错误) | 2.1-G: 保持 PASS |
| frontend build | 未运行 (待 2.1-G) | 2.1-G: PASS |
| A2A mainline smoke | 待运行 (2.1-G) | 2.1-G: PASS |
| MCP tools/list + tools/call | 待运行 (2.1-G) | 2.1-G: PASS |
| Medical Coding smoke | 待运行 (2.1-G) | 2.1-G: 不回退 |

**基线判定**: 当前代码库处于 P1.3 Stage 5 完成后的稳定状态，所有 legacy 资产已打 DEPRECATED 标记但尚未物理删除。Phase 2.1 的工作量集中在 (a) 真删 legacy，(b) 修 Browser QA，(c) 去掉 AgentRunner stub。

---

## 1. AgentRunner Stub 现状 (对应 Phase 2.1-A)

### 1.1 三处 AgentRunner 符号

| 位置 | 类型 | 状态 | 行号 |
|---|---|---|---|
| `backend/app/services/agent_runner.py` | 旧文件 | **已 staged 删除** (`git status` 显示 `D`) | — |
| `backend/icoder_runtime/agent_runner.py` | STUB (≈80 LOC) | **保留** — `PlatformRuntime` 仍 import 它 | 文件头 docstring |
| `backend/app/api/agents.py` `_LegacyAgentRunnerStub` | 模块级 `agent_runner` 符号 | **保留** — 兜底 legacy 调用 | lines 23-34 |

### 1.2 stub 保留原因 (来自 `icoder_runtime/agent_runner.py` docstring)

> This file was physically deleted in Phase 2-C because the mainline now uses `app.icoder.agent_runtime.orchestrator`. It is restored here as a **minimal stub** because `icoder_runtime.embedded.platform_runtime.PlatformRuntime` still imports `AgentRunner` for its `_runner` slot and calls `register_expert` / `register_tool` / `run` on it.

### 1.3 PlatformRuntime 引用 AgentRunner 的位置

| 文件 | 行 | 用途 |
|---|---|---|
| `icoder_runtime/embedded/platform_runtime.py:27` | `from ..agent_runner import AgentRunner` | 类导入 |
| `icoder_runtime/embedded/platform_runtime.py:68` | `self._runner: AgentRunner \| None = None` | `_runner` slot 类型注解 |
| `icoder_runtime/embedded/platform_runtime.py:77` | `self._runner = AgentRunner(gateway=self._gateway)` | `start()` 内构造 |
| `icoder_runtime/embedded/platform_runtime.py:84,152,153` | `self._runner.register_expert(...)` / `register_tool(...)` | 注册 experts/tools |
| `icoder_runtime/embedded/platform_runtime.py:221,224` | 同上 | `run_agent` 内重复注册 |
| `icoder_runtime/embedded/platform_runtime.py:246` | `await self._runner.run(...)` | 执行入口 (**此行会触发 stub 的 NotImplementedError**) |
| `icoder_runtime/cli.py:133` | `from .agent_runner import AgentRunner` | CLI 命令 |
| `icoder_runtime/serve.py:23` | `from .agent_runner import AgentRunner` | 服务器启动 |

### 1.4 关键观察

- `PlatformRuntime.run_agent` 最终调 `self._runner.run()` → stub `raise NotImplementedError`。这意味着 **如果任何主线调用 `PlatformRuntime.run_agent`，会立即抛错**。
- 当前主线 (`app.icoder.agent_runtime.orchestrator.InboundHandler`) 不依赖 `PlatformRuntime`，所以 stub 不被触发。
- 测试中仍存在 `from app.services.agent_runner import AgentRunner` (3 个 test 文件) 和 `from icoder_runtime.agent_runner import AgentRunner` (1 个 test 文件) — 这些测试 import 一个已删除的模块路径，预计 `ImportError` 或被跳过。

### 1.5 Phase 2.1-A 决策空间

| 选项 | 描述 | 代价 |
|---|---|---|
| A1 | 删 `icoder_runtime/agent_runner.py` stub + 重构 `PlatformRuntime` 不再持有 `_runner` | 中 — 需重写 `PlatformRuntime.start/install_agent/run_agent` |
| A2 | 保留 stub，明确文档化"PlatformRuntime 已非主线，仅用于兼容性 import" | 低 — 但与"主线"叙事冲突 |
| A3 | 删 `PlatformRuntime` 整个类，迁移所有 caller 到新 orchestrator | 高 — 需查所有 caller |

**推荐**: A1（去 stub，PlatformRuntime 改为 thin wrapper 不再持 `_runner`）。后续 Phase 2.1-A 会细化。

---

## 2. 15 Legacy API Router 现状 (对应 Phase 2.1-B)

### 2.1 全部 15 个 DEPRECATED router 清单

通过 `grep -l "DEPRECATED" backend/app/api/*.py` + 头注释模式匹配，确认 15 个文件已标 DEPRECATED：

| # | 文件 | 行数 | 当前 DEPRECATED 原因 | 拟定状态 |
|---|---|---|---|---|
| 1 | `agent_evaluation.py` | 152 | F1 评估非 Corti 方向, Phase 2 删 | **delete** |
| 2 | `agents.py` | 736 | migrate 到 /rest/v1/agent_definitions | **migrate** (但 v2 路径已有，倾向 delete legacy) |
| 3 | `code_tables.py` | 169 | iCoDer 内部概念无 Corti 等价 | **delete** |
| 4 | `evaluation.py` | 104 | F1 评估非 Corti 方向 | **delete** |
| 5 | `experts.py` | 551 | Corti 用 Pre-built Agents + MCP | **delete** |
| 6 | `facts.py` | 204 | 合并到 v2_tools_facts | **delete** (after 确认无 caller) |
| 7 | `gold_cases.py` | 144 | F1 评估非 Corti 方向 | **delete** |
| 8 | `icoder_agents_compat.py` | 123 | Legacy compat shim | **delete** |
| 9 | `icoder_agents_hub.py` | 1029 | migrate 到 /rest/v1/agent_definitions | **delete** (P1.1-B/C 已被取代) |
| 10 | `icoder_coding_review.py` | 1283 | Corti 用 /api/v2/tools/coding/ | **delete** |
| 11 | `icoder_registry_compat.py` | 106 | Legacy compat shim | **delete** |
| 12 | `m2a.py` | 277 | iCoDer 内部概念无 Corti 等价 | **delete** |
| 13 | `reviews.py` | 921 | Phase 2 降级为 Pre-built Agent | **compat** (被 review_coding_service 用) |
| 14 | `runtime.py` | 386 | 合并到 runtime_platform.py | **delete** (prefix `/api/runtime-legacy` 已是 compat) |
| 15 | `text_gen.py` | 131 | 合并到 v2_tools_guided_document.py | **delete** |

### 2.2 main.py 注册情况

`backend/app/main.py:787-885` 注册了 46+ 个 router，其中上述 15 个全部已 `include_router`。物理删除任一 router 必须同时:
1. 删除文件
2. 删除 `main.py` 中对应的 `from app.api.X import router as X_router` + `app.include_router(X_router)`
3. 删除前端调用 (services/api.ts 等)
4. 运行回归测试

### 2.3 风险评估

- `reviews.py` (921 行) 是最大且最危险的 — 它被 `review_coding_service.py` 和 `runtime.py` 引用，可能仍有真实业务路径。需先确认 caller 链。
- `agents.py` (736 行) 的 `/api/agents/*` 端点可能被前端 AgentsPage 调用。需对照前端 services。
- 其他 13 个 router 大多已无主线 caller，删除风险低。

---

## 3. app/tools ↔ Legacy Experts 耦合 (对应 Phase 2.1-C)

### 3.1 5 个 tool 文件 import legacy experts

| tool 文件 | 引用 | 引用类 |
|---|---|---|
| `analysis_tools.py:7-8` | `app.agents.experts.drg_expert`, `cdi_expert` | DRGDIPExpert, DocumentationGapExpert, CDIExpert |
| `extraction_tools.py:8-9` | `app.agents.experts.evidence_expert`, `timeline_expert` | EvidenceExtractionExpert, TimelineReconstructionExpert |
| `report_tools.py:9` | `app.agents.experts.report_expert` | ReportExpert |
| `verification_tools.py:11` | `app.agents.experts.drg_expert` | EvidenceVerificationExpert |
| (其他 6 个 tool 文件) | (无 legacy expert 引用) | — |

### 3.2 11 个 legacy expert 文件 (2,460 LOC)

| expert 文件 | 行数 | 被引用情况 |
|---|---|---|
| `homepage_expert.py` | 665 | 已被 P1.2 删 (`D backend/app/agents/orchestrator.py`) |
| `report_expert.py` | 343 | `report_tools.py` |
| `diagnosis_expert.py` | 268 | (未在 app.tools 引用，但 `__init__.py` 导出) |
| `procedure_expert.py` | 230 | (同上) |
| `timeline_expert.py` | 229 | `extraction_tools.py` |
| `drg_expert.py` | 206 | `analysis_tools.py`, `verification_tools.py` |
| `evidence_expert.py` | 127 | `extraction_tools.py` |
| `audit_expert.py` | 111 | (仅 `__init__.py`) |
| `hcc_expert.py` | 86 | (仅 `__init__.py`) |
| `cdi_expert.py` | 85 | `analysis_tools.py` |
| `denial_expert.py` | 84 | (仅 `__init__.py`) |

### 3.3 新主线对应物

`app/icoder/agent_runtime/experts/` (5 个 atomic experts, keep_mainline) 已取代上述 legacy experts 的角色。`app/agents/experts/` 整体属 legacy。

### 3.4 解耦策略 (2.1-C 细化)

1. 删除 5 个 tool 文件中"仅给 legacy expert 当 wrapper"的 tool 函数（如果 caller 已不存在）。
2. 如果 tool 函数仍被 `app/api/tools.py` 或前端调用，记录保留原因 + 标 DEPRECATED。
3. 物理删除 11 个 legacy expert 文件中"无 caller"的 (audit/hcc/denial/diagnosis/procedure/homepage)。
4. 保留有 caller 的 (cdi/drg/evidence/report/timeline) 直到 caller 迁移。

---

## 4. runtime.py / fhir.py / review_coding_service 去留 (对应 Phase 2.1-D)

| 文件 | 行数 | 当前标记 | 拟定状态 | 原因 |
|---|---|---|---|---|
| `app/api/runtime.py` | 386 | `# DEPRECATED` 头 + prefix `/api/runtime-legacy` | **delete** | 与 runtime_platform.py 重复，prefix 已 isolate |
| `app/api/fhir.py` | 429 | 无 DEPRECATED 标记 | **experimental** | FHIR R4 prototype，Corti 无等价但医院 EHR 互通有用 |
| `app/services/runtime.py` | 702 | `# DEPRECATED` 头 | **delete** (合并到 runtime_platform service) | DeterministicRuntime 12 态机已被 orchestrator 5 态取代 |
| `app/services/review_coding_service.py` | 326 | `# DEPRECATED` 头 | **delete** | "非 Corti 方向"，CodingPipelineOrchestrator 4-agent 已被 MedCodER Agent 取代 |

### 4.1 关键 caller 链 (需在 2.1-D 中验证)

- `app/api/runtime.py` → `app/services/runtime.py` (DeterministicRuntime, CaseState, GateOutcome)
- `app/services/review_coding_service.py` → `app/services/runtime.py` (CaseState)
- `app/main.py:671` 注释 "M2a Run Trace recorder (wired into HybridCodingAdapter + AgentRunner)" → 可能引用 m2a/recorder

### 4.2 删除前必须

1. 查所有 import 站点 (grep)
2. 修 caller 改用新主线 (`runtime_platform.py`, `app.icoder.agent_runtime`)
3. 删文件 + 删 main.py 注册
4. 跑回归

---

## 5. icoder_runtime/m2a 现状 (对应 Phase 2.1-E)

> **重要修正**: `docs/architecture/MAINLINE_VS_LEGACY.md` §3.5 写 "icoder_runtime/m2a/ (空) — delete_candidate"。**实际不为空**，有 6 个 .py 文件 + `__init__.py`。

### 5.1 文件清单 + 拟定去留

| 文件 | 行数 | 用途 | 拟定状态 |
|---|---|---|---|
| `__init__.py` | ~20 | 包说明 | **delete** (随包整体) |
| `human_review.py` | (待数) | Task 4 人工复核写回 (13 reason_code) | **archive** |
| `recorder.py` | (待数) | Task 5 AgentRunner/HybridCodingAdapter bridge | **delete** (AgentRunner 已 stub) |
| `risk_router.py` | (待数) | Task 2 4-tier risk router | **archive** |
| `run_trace.py` | (待数) | Task 1 UUIDv7 run trace | **archive** |
| `safety_gate.py` | (待数) | Task 3 12 指标 + 8 rules | **archive** |
| `store.py` | (待数) | JSONL append-only + sample/prod 隔离 | **archive** |

### 5.2 m2a 是否被主线引用

- `app/api/m2a.py` (277 行, DEPRECATED) — 唯一 API 入口
- `app/main.py:671` 注释提到 m2a recorder — 需查实际 import
- `icoder_runtime/m2a/recorder.py` docstring 说 "If `recorder is None`, all calls are no-ops → 752 existing tests stay green"，意味着 recorder 是 opt-in，主线默认不启用

### 5.3 决策方向

m2a 整体属 iCoDer 内部概念（"M2a 技术闭环"），Corti 无等价。6 个文件实现了真实逻辑（非 stub），但被 DEPRECATED API `app/api/m2a.py` 包裹。Phase 2.1-E 决策:
- **Option 1**: 整包 `archive` 到 `docs/archive/m2a/` 或 `backend/icoder_runtime/_archive/m2a/`
- **Option 2**: 物理删除 (cleaner，但丢失可恢复逻辑)
- **Option 3**: 保留但加 `# EXPERIMENTAL — 非主线` 标记 (与 MAINLINE_VS_LEGACY §6 规则冲突，不推荐)

**推荐**: Option 1 (archive) — 保留实现知识，但移出主线代码树。

---

## 6. Browser QA 现状 (对应 Phase 2.1-F)

### 6.1 Playwright 配置

`frontend/playwright.config.ts`:
- 2 projects: `setup` (auth.setup.ts) + `e2e` (依赖 setup)
- `storageState: 'tests/e2e/.auth.json'`
- `webServer`: `npx vite --port 3000` (CI 外自动启动)
- `baseURL`: `http://localhost:3000` (非 CI)

### 6.2 auth.setup.ts 问题

`frontend/tests/e2e/auth.setup.ts:9-13`:
```ts
setup('authenticate', async ({ request, page }) => {
  const resp = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },  // ← 硬编码
  });
```

**违反成功标准 #10**: "Playwright auth.setup 不依赖 admin/admin123，使用动态注册或测试专用 seed"。

### 6.3 .auth.json 状态

- 文件存在 (1513 bytes, Jul 1 21:07)
- 内含 access_token + refresh_token + Zustand state
- 已 commit 在 .gitignore? (需查)

### 6.4 修复方向 (2.1-F 细化)

1. 改 auth.setup.ts 用动态注册 (POST /api/auth/register + unique username like `e2e_<uuid>`)
2. 或用测试专用 seed user (在 backend startup lifespan 中 ensure `e2e@seed.local` 存在)
3. 删除 .auth.json from git tracking (如已 commit)
4. 跑全部 e2e spec 文件确认 PASS

---

## 7. 验证基线 (对应 Phase 2.1-G 起跑线)

| 检查项 | 命令 | 结果 | 备注 |
|---|---|---|---|
| health_check | `python backend/scripts/health_check.py` | **7/7 PASS** | alembic_head + schema_drift + agents_installed=28 + runtime_started + registry_sync + auth_register + auth_login |
| schema_drift | (health_check 内) | **0 divergences** across 33 tables / 473 columns | |
| OpenAPI export | `python backend/scripts/export_openapi.py --out /tmp/openapi_baseline.json` | **557,053 bytes** | 后续对比基线 |
| frontend tsc | `npx tsc --noEmit` | **PASS** (无输出 = 无错误) | |
| frontend build | `npm run build` | 未运行 | 2.1-G 跑 |
| A2A mainline smoke | (待定义命令) | 未运行 | 2.1-G 跑 |
| MCP tools/list + tools/call | (待定义命令) | 未运行 | 2.1-G 跑 |
| Medical Coding smoke | (待定义命令) | 未运行 | 2.1-G 跑 |
| icoder_doctor | `python backend/scripts/health_check.py` (源 .py 已删) | **7/7 PASS** | 用 health_check 替代 |

### 7.1 命令等价映射 (任务文档 .sh → 实际 .py)

任务文档要求 `backend/scripts/{compileall,health_check,icoder_doctor,schema_drift,export_openapi}.sh`，但仓库实际只有 .py 版本:

| 任务文档命令 | 实际命令 | 备注 |
|---|---|---|
| `backend/scripts/compileall.sh` | `python -m compileall backend/app backend/icoder_runtime` | 直接用 Python 内置 |
| `backend/scripts/health_check.sh` | `python backend/scripts/health_check.py` | 已用 |
| `backend/scripts/icoder_doctor.sh` | (源已删，.pyc 残留) → `python backend/scripts/health_check.py` | health_check.py 文件头注明 "Replaces the deleted icoder_doctor.py" |
| `backend/scripts/schema_drift.sh` | `python backend/scripts/check_schema_drift.py` 或 health_check 的 #2 检查 | |
| `backend/scripts/export_openapi.sh` | `python backend/scripts/export_openapi.py --out <path>` | 已用 |

**结论**: 任务文档列的 .sh 命令在仓库中不存在，等价 .py 已就位。后续 2.1-G 报告会注明此映射。

---

## 8. 主线 vs 实验性 vs Legacy 三层基线

参考 `docs/architecture/MAINLINE_VS_LEGACY.md` (2026-07-02 已生成):

| 层 | Backend | Frontend | Docs | 状态 |
|---|---|---|---|---|
| Mainline | ~80 | ~30 | ~70 | keep |
| Experimental | ~15 | 0 | ~5 | keep, 不上线 |
| Legacy | ~50 | ~15 | ~90+ | deprecated / archive / delete |

Phase 2.1 工作量集中在 Legacy 层 (~50 backend + ~15 frontend) 的物理删除/归档，不动 Mainline + Experimental。

---

## 9. 已 staged 但未 commit 的删除 (git status)

```
 D backend/app/agents/orchestrator.py
 D backend/app/services/agent_runner.py
 D backend/app/services/stt_finetune.py
 D backend/icoder_runtime/dashboard.html
 D backend/icoder_runtime/sandbox.py
 D backend/icoder_runtime/symbolic_state.py
 D backend/icoder_runtime/tests/test_integration.py
 D backend/icoder_runtime/tests/test_runtime.py
 D backend/icoder_runtime/tests/test_sandbox.py
```

这 9 个文件已 `git rm` 但未 commit。Phase 2.1-A/B/E 可能与此 staging 区冲突 — 操作前需 `git status` 确认。

---

## 10. Phase 2.1 执行计划

基于本基线，后续 7 个子阶段 (A-G) 的执行顺序与依赖:

```
Phase 0 (本报告, 基线锁定)
  ↓
Phase 2.1-A (PlatformRuntime 去 stub) — 独立
  ↓
Phase 2.1-B (15 legacy router 收口) — 独立但大，可能分多轮
  ↓
Phase 2.1-C (app/tools ↔ legacy experts 解耦) — 依赖 B 部分完成 (tools.py 是 legacy)
  ↓
Phase 2.1-D (runtime/fhir/review_coding 决策) — 依赖 A (PlatformRuntime) + B (runtime.py)
  ↓
Phase 2.1-E (m2a 重新评估) — 独立但依赖 B (m2a.py router)
  ↓
Phase 2.1-F (Browser QA 修复) — 独立
  ↓
Phase 2.1-G (四轮回归) — 依赖 A-F 全部完成
  ↓
Final Report
```

---

## 11. 基线锁定声明

本报告数据采集时间: **2026-07-02 23:00 ~ 23:10 (UTC+8)**
- 后端运行中 (localhost:8000)，28 agents installed
- 前端 dev server 未启 (2.1-F 启)
- git: 分支 `master`，最近 commit `267c66f fix(qa): ISSUE-005`

后续 Phase 2.1-A~G 的每一步变更将以本基线为对照，判定无回归。

**基线锁定**: ✅ BASELINE LOCKED — 可进入 Phase 2.1-A。
