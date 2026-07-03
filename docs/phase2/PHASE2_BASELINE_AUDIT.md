# PHASE2_BASELINE_AUDIT — Phase 2 Agentic Framework 主线切换基线审计

> **声明**: 本文档是 Phase 2 启动时的基线审计, 记录当前 3 套 Agent 架构状态 / 主线路径 / 测试通过率 / Phase 2 待办.
> **日期**: 2026-07-02
> **阶段**: Phase 2 — Agentic Framework Mainline Cutover — Phase 0 (Baseline)
> **状态**: MAINLINE
> **前置**: P1.3 Corti Parity Direction Audit (2026-07-02, VERDICT: PASS)

---

## 0. 执行摘要

P1.3 已完成方向纠偏 (MedCodER 降级为 Pre-built Agent #18, 新主线 = Corti-style Agent Runtime 平台). Phase 2 目标 = 把方向落实到代码: 切换主运行路径到新 Orchestrator, 断 legacy 引用, 物理删安全 legacy 资产, A2A+MCP+Context+Orchestrator 主线联调, WorkbenchLayout 迁移.

**当前判定**: PARTIALLY_READY — 主线路径已通 (main.py lifespan 用新 wiring + /.well-known/agent.json 200), 但 legacy 引用未断 + 32 DEPRECATED 文件未删 + WorkbenchLayout 仅壳未迁 + CLAUDE.md 未更新.

---

## 1. 3 套 Agent 架构当前状态

### 1.1 Legacy 单体 Agent (app/agents/)

**状态**: DEPRECATED (P1.3 Stage 5 已标记)

**文件** (13 个, 全部第一行加 `# DEPRECATED`):
- `app/agents/orchestrator.py` — AgentOrchestrator 类
- `app/agents/base.py`
- `app/agents/experts/{audit,cdi,denial,diagnosis,drg,evidence,hcc,homepage,procedure,report,timeline}_expert.py` (11 文件, homepage_expert.py 664 LOC)

**仍被引用**:
- `app/agents/__init__.py:1` — `from app.agents.orchestrator import AgentOrchestrator`
- `app/api/reviews.py:1` — `from app.agents.orchestrator import agent_orchestrator`

**Phase 2-B 任务**: 断这 2 处引用, 改用新 orchestrator 或 stub.

### 1.2 Legacy AgentRunner (icoder_runtime/agent_runner.py + app/services/agent_runner.py)

**状态**: DEPRECATED (P1.3 Stage 5 已标记, app/services/agent_runner.py 早前已有 v2.1 deprecation note)

**文件**:
- `icoder_runtime/agent_runner.py` — P1.3 标记
- `app/services/agent_runner.py` (1047 LOC) — 早前标记 `*** DEPRECATED — will be removed in v2.1 ***`

**仍被引用**:
- `app/api/agents.py` — `from app.services.agent_runner import agent_runner` (注释标 "legacy: uses app.services.agent_runner (old DB-based path)")

**Phase 2-B 任务**: 断 agents.py 引用, 改用 platform_runtime.

### 1.3 New Agent Runtime (app/icoder/agent_runtime/)

**状态**: MAINLINE (main.py lifespan 已用)

**目录结构**:
```
app/icoder/agent_runtime/
├── orchestrator/
│   ├── wiring.py              ← build_expert_invoker_for_medcoder + build_llm_call_from_gateway
│   ├── planner.py             ← PlannerConfig
│   ├── delegator.py           ← DelegatorConfig
│   ├── aggregator.py
│   ├── state_machine.py
│   ├── inbound_handler.py
│   ├── phi_redactor.py
│   ├── recorder_adapter.py
│   ├── run_context.py
│   ├── errors.py / events.py / metrics.py / prompts.py
├── a2a/
│   ├── mount_a2a              ← main.py:587 调用
│   ├── agent_card.py          ← medcoder_coding_review_card() factory
│   ├── envelope.py / messages.py / parts.py / errors.py
│   ├── routes_discovery.py    ← /.well-known/agent.json (已 200)
│   ├── routes_inbound.py / routes_outbound.py
│   ├── routes_task_stub.py    ← Task 5 态 stub
├── mcp/                       ← mount_mcp (main.py:631)
├── context/                   ← Context 服务端生成 (spec 完整, 主线待跑通)
└── experts/                   ← 4 D2 expert pack (evidence-extractor/index-navigator/code-reconciler/tabular-validator)
```

**主线已通**:
- `main.py:396` — `from app.icoder.agent_runtime.orchestrator import ...`
- `main.py:406-407` — `build_expert_invoker_for_medcoder` + `build_llm_call_from_gateway`
- `main.py:445` — `HybridCodingAdapter(mode="medcoder")` 用新 wiring 构造
- `main.py:587` — `mount_a2a(...)`
- `main.py:631` — `mount_mcp(...)`
- `/.well-known/agent.json` 返回 200 + MedCodER agent card

**主线未跑通**:
- A2A Task 5 态 (routes_task_stub.py) — 仍是 stub
- Context contextId UUID v4 服务端生成 — spec 完整, 主线待跑通
- MCP resources/list + prompts/list — 仅有 tools/list + tools/call

---

## 2. 主线路径确认

### 2.1 Medical Coding 主路径 (Pre-built Agent #18)

```
POST /api/v2/tools/coding/icoder/  (Phase 1.1, 2026-06-30)
  → v2_tools_coding.py
  → HybridCodingAdapter(mode="medcoder").infer_async()
  → 新 wiring: build_expert_invoker_for_medcoder (4 D2 expert pack)
  → MedCodER 5-stage: Extraction → Retrieval → Merge → Re-rank → Compliance
  → MedicalCodingOutputSchema
```

**Corti-spec predictor** (Cycle 18, stateless, no LLM):
```
POST /api/v2/tools/coding/  (15-system, 无 LLM)
  → v2_tools_coding.py
  → 直接 catalog 查询
  → {codes, candidates, usageInfo}
```

### 2.2 A2A 主路径

```
GET  /.well-known/agent.json          ← routes_discovery.py (200 ✅)
POST /a2a/inbound                     ← routes_inbound.py (stub)
POST /a2a/outbound                    ← routes_outbound.py (stub)
GET  /a2a/tasks/{id}                  ← routes_task_stub.py (5 态 stub)
```

### 2.3 MCP 主路径

```
POST /mcp/v1/tools/list               ← mount_mcp (M2 已实装)
POST /mcp/v1/tools/call               ← mount_mcp (5 MedCodER tool handlers)
```

### 2.4 Context 主路径

**状态**: spec 完整 (ICODER_V1_CONTEXT_SPEC.md), 主线未跑通.

**待 Phase 2-D**: contextId UUID v4 服务端生成 + 三层隔离 + GC 策略.

---

## 3. P1.3 已完成项 (Phase 2 基线)

### 3.1 文档 (14 份)

- `docs/README_INDEX.md`
- `docs/product/PRODUCT_DIRECTION.md` + `CORTI_PARITY_ROADMAP.md`
- `docs/architecture/CURRENT_ARCHITECTURE.md` + `MAINLINE_VS_LEGACY.md`
- `docs/backlog/PRODUCT_BACKLOG.md` + `TECH_DEBT_BACKLOG.md`
- `docs/corti_parity/{CORTI_REFERENCE_BASELINE, ICODER_ASSET_INVENTORY, CORTI_PARITY_GAP_ANALYSIS, DIRECTION_CORRECTION_PLAN, ASSET_CLEANUP_REPORT, UI_IA_CORRECTION_REPORT, TESTING_VERIFICATION_REPORT, P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT}.md`

### 3.2 资产清理

- P0 删除: 9/10 项 (TD-009 m2a/ 推迟)
- P1 归档: 331 文件到 docs/archive/ 7 子目录
- P2 废弃标记: 32 Python 文件 (13 legacy agent + 1 AgentRunner + 15 legacy API + 3 legacy service + 2 legacy icoder_runtime)
- .gitignore +11 条目

### 3.3 UI IA

- Sidebar IA: 已对齐 (Top → AI Studio → Manage → Support)
- Home 4 tabs: 已对齐 (Transcribe/Document/Chat/Code NEW)
- 顶栏 Theme toggle + Reset live cost: 已对齐
- WorkbenchLayout 壳子: 已建 (88 LOC, 未迁移)
- 设计 token: 已抽离 (vermillion primary 保留)

### 3.4 测试通过率 (P1.3 Stage 7 验证)

| 检查 | 结果 |
|---|---|
| health_check.py (7 项) | 7/7 PASS |
| check_schema_drift.py | 0 divergences (33 表 / 473 列) |
| export_openapi.py | 557KB JSON |
| app import | 299 routes |
| tsc --noEmit | 0 errors |
| vitest run src/ | 71/71 passed |
| 14 deprecated 文件 import smoke | 14/14 OK |

---

## 4. Phase 2 待办 (按优先级)

### Phase 2-A — 统一 Agent Runtime 主路径 + 更新架构文档

- 确认 `app/icoder/agent_runtime/` 为唯一主线 (已在 main.py lifespan)
- 更新 CURRENT_ARCHITECTURE.md / MAINLINE_VS_LEGACY.md 标注主线已切
- 不动代码 (代码已切), 仅文档明确

### Phase 2-B — 断 legacy Agent 引用

**待断引用** (3 处):
- `app/agents/__init__.py:1` — import AgentOrchestrator
- `app/api/reviews.py:1` — import agent_orchestrator
- `app/api/agents.py` — import agent_runner

**策略**:
- reviews.py: 改用 platform_runtime service 或标 stub
- agents.py: 改用 platform_runtime.run_agent
- app/agents/__init__.py: 清空或保留空壳

**输出**: `docs/phase2/LEGACY_REFERENCE_CUTOVER_REPORT.md`

### Phase 2-C — 物理删除安全 legacy 资产

**删除候选** (P1.3 标 DEPRECATED + 2-B 断引用后):
- 13 legacy 单体 Agent 文件 (app/agents/orchestrator.py + base.py + 11 experts)
- 1 legacy AgentRunner (icoder_runtime/agent_runner.py)
- 15 legacy API (icoder_coding_review + agents_hub + compat + registry_compat + evaluation + agent_evaluation + gold_cases + code_tables + m2a + reviews + experts + runtime + text_gen + facts + agents)
- 3 legacy service (review_coding_service + stt_finetune + runtime)
- 2 legacy icoder_runtime (sandbox + symbolic_state)

**不可删** (有引用或实验性):
- app/services/agent_runner.py — 待 Phase 2-B 断 agents.py 引用后删
- icoder_runtime/m2a/ — 非空 5 .py, 需重新评估
- 实验性 4 services (gold_case_importer + gold_case_template + inter_rater + pilot_report_builder + ccl2026_importer) — 保留

**输出**: `docs/phase2/LEGACY_DELETION_REPORT.md`

### Phase 2-D — A2A + MCP + Context + Orchestrator 主线联调

**目标**: 真实主线链路跑通 (非 mock).

**子任务**:
- A2A inbound → orchestrator → outbound → completed 端到端
- MCP resources/list + prompts/list (现仅 tools/list + tools/call)
- Context contextId UUID v4 服务端生成主线
- MedCodER Pre-built Agent #18 主线 smoke (至少 1 次工具调用)
- Run Trace 诚实暴露主线运行状态

### Phase 2-E — WorkbenchLayout 迁移

**目标**: 至少 3 个核心页面迁移到 WorkbenchLayout.

**候选**:
- `frontend/src/pages/SpeechToTextPage.tsx` (或对应 STT 工作台)
- `frontend/src/pages/TextGenerationPage.tsx`
- `frontend/src/pages/MedicalCodingPage.tsx`
- `frontend/src/pages/FactExtractionPage.tsx`
- `frontend/src/pages/EmbeddedAssistantPage.tsx`

**输出**: `docs/phase2/WORKBENCH_LAYOUT_MIGRATION_REPORT.md`

### Phase 2-F — 文档一致性修复

- CLAUDE.md §MedCodER 主线描述 (TD-098) — 改为引用 PRODUCT_DIRECTION.md
- 旧 docs/ARCHITECTURE.md / PRODUCT-ROADMAP.md / PRODUCT-MODULES.md / TECHNICAL-DESIGN.md / runtime.md (TD-099 to TD-103) — 评估 + 标 DEPRECATED 或引用新版

**输出**: `docs/phase2/DOCS_CONSISTENCY_REPORT.md`

### Phase 2-G — vite 配置修复

- `frontend/vite.config.ts` 加 `test: { exclude: ['tests/e2e/**'] }` 避免 vitest 捡 Playwright e2e specs

### Phase 2-H — 4 轮回归 + Browser QA

**4 轮**:
1. Asset/Docs/Direction Audit
2. Backend/Runtime Regression (health_check + schema_drift + OpenAPI + 关键 API)
3. Frontend Product Flow (tsc + vitest + build)
4. Browser QA (导航 + Medical Coding smoke)

**输出**: `docs/phase2/PHASE2_TESTING_VERIFICATION_REPORT.md`

### Final — PHASE2_AGENTIC_FRAMEWORK_CUTOVER_FINAL_REPORT.md

19 章节 + PASS/FAIL 判定.

---

## 5. 20 项成功标准基线评估

| # | 标准 | 当前状态 | Phase 2 目标 |
|---|---|---|---|
| 1 | 3 套 Agent 架构有清晰收敛结果 | PARTIAL (P1.3 标 DEPRECATED, 未删) | 2-C 删后收敛 |
| 2 | 唯一主路径 app/icoder/agent_runtime/ 确认 | YES (main.py 已用) | 2-A 文档明确 |
| 3 | 主线不再依赖 legacy orchestrator | NO (reviews.py 仍引用) | 2-B 断 |
| 4 | 主线不再依赖 legacy AgentRunner | NO (agents.py 仍引用) | 2-B 断 |
| 5 | 可安全删除 DEPRECATED 文件已删 | NO (32 文件仅标记) | 2-C 删 |
| 6 | 不可删 legacy 有明确原因 | PARTIAL (TECH_DEBT_BACKLOG 已列) | 2-C 报告确认 |
| 7 | A2A + MCP + Context + Orchestrator 主线跑通 | PARTIAL (A2A 200, MCP tools 已, Context stub) | 2-D 跑通 |
| 8 | MedCodER #18 主线 smoke | PARTIAL (endpoint 200, body 解析失败) | 2-D smoke |
| 9 | Run Trace 诚实暴露主线状态 | PARTIAL (recorder_adapter 已, 需验证) | 2-D 验证 |
| 10 | WorkbenchLayout 至少 3 页迁移 | NO (仅壳) | 2-E 迁 3 页 |
| 11 | CLAUDE.md 与新方向一致 | NO (TD-098 待) | 2-F 更新 |
| 12 | vite test.exclude 修复 | NO | 2-G 修 |
| 13 | schema_drift = 0 | YES (0 divergences) | 维持 |
| 14 | health_check 通过 | YES (7/7) | 维持 |
| 15 | OpenAPI contract 通过 | YES (557KB 导出) | 维持 |
| 16 | tsc --noEmit 通过 | YES (0 errors) | 维持 |
| 17 | npm run build 通过 | UNTESTED | 2-H 验证 |
| 18 | Browser QA 通过 | UNTESTED | 2-H 验证 |
| 19 | 无编码质量优化带回主线 | YES (未改 F1/rerank/few-shot) | 维持 |
| 20 | 无 fake data | YES | 维持 |

**基线**: 7/20 已满足 (2, 13, 14, 15, 16, 19, 20). 需 Phase 2 补 13 项.

---

## 6. 验证 (本次基线审计)

- ✅ 3 套架构状态确认 (代码 + 引用)
- ✅ 主线路径确认 (main.py + /.well-known/agent.json 200)
- ✅ P1.3 完成项确认 (14 docs + 331 archive + 32 deprecation)
- ✅ 测试通过率确认 (health_check 7/7 + schema_drift 0 + tsc 0 + vitest 71/71)
- ✅ 20 项成功标准基线评估 (7/20 已满足)

---

## 7. 下一步

进入 Phase 2-A — 统一 Agent Runtime 主路径 + 更新架构文档.

---

## 8. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, Phase 2 基线审计 | Phase 2 启动 |
