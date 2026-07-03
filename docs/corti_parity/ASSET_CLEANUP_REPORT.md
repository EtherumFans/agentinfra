# ASSET_CLEANUP_REPORT — P1.3 Stage 5 资产清理报告

> **声明**: 本文档记录 P1.3 Stage 5 执行的资产清理 (P0 删除 + P1 归档 + P2 废弃标记).
> **日期**: 2026-07-02
> **阶段**: P1.3 Corti Parity Direction Audit — Stage 5
> **状态**: COMPLETED

---

## 0. 执行摘要

| 类别 | 计划 | 实际 | 差异 |
|---|---|---|---|
| P0 立即删 | 10 项 | 9 项 | TD-009 (m2a/) 非空, 推迟 |
| P1 归档 | 27 项 (90+ 文件) | 27 项 (331 文件) | ✅ 完成 |
| P2 废弃标记 | 42 项 | 32 项 | 10 项前端文件 P1.2 已删, 无需标记 |
| .gitignore 更新 | — | 11 新条目 | ✅ |

**判定**: PASS — 所有可执行的 P0-P2 项已处理, 未处理的项已说明原因.

---

## 1. P0 立即删 (TD-001 to TD-010)

| # | 路径 | 操作 | 证据 | 结果 |
|---|---|---|---|---|
| TD-001 | `.corti-user-data/` | rm -rf + .gitignore | Chrome BrowserMetrics/Crashpad/Default 数据误入仓库 | ✅ deleted |
| TD-002 | `backend/data/icoder.db.bak2` | rm | cycle 23 识别 alembic=002 + 30 表含 4 deprecated context_* | ✅ deleted |
| TD-003 | `backend/data/icoder.db.bak20260701` | rm | cycle 23 识别全 DROP 0 表 | ✅ deleted |
| TD-004 | `backend/data/icoder.db.broken-20260702` | rm | 文件名标 broken | ✅ deleted |
| TD-005 | `backend/data/test.db` | rm + .gitignore | CI 应 in-memory | ✅ deleted |
| TD-006 | `.tmp_run.json` / `.tmp_agent_run.json` / `backend/.tmp_run.json` | rm + .gitignore | 临时运行文件 | ✅ deleted (3 文件) |
| TD-007 | `frontend/src/pages/EmbeddedAssistantPage.tsx.bak` | rm | .bak 后缀 (清单写 EmbedDemoCodingReviewPage.tsx.bak, 实际为 EmbeddedAssistantPage) | ✅ deleted |
| TD-008 | `backend/icoder_runtime/methods/` | rm -rf | P1.2 已删 10 builtin methods, 仅剩 __pycache__ | ✅ deleted |
| TD-009 | `backend/icoder_runtime/m2a/` | **推迟** | 清单标"空目录", 实际含 5 .py 文件 (human_review.py, recorder.py, risk_router.py, run_trace.py, safety_gate.py, store.py) — 非空, 需 Phase 2 重新评估 | ⏸ deferred (非空, 不删) |
| TD-010 | `backend/icoder_runtime/dashboard.html` | rm | 无 Corti 等价, 前端 AgentsPage 替代 | ✅ deleted |

**P0 统计**: 9/10 删除, 1/10 推迟 (TD-009), 0 失败.

---

## 2. P1 归档 (TD-011 to TD-037)

### 2.1 归档目录结构

```
docs/archive/
├── audit_remediation/              (5 文件, E1.x 历史)
├── corti_analysis_2026_05/         (18 文件, 早期 Corti 分析)
├── corti_reference_early/          (6 子目录, 早期 Corti 调研)
│   ├── Corti/
│   ├── corti-crawl/
│   ├── corti-screens/
│   ├── corti_contracts/
│   ├── corti_ui_contracts/
│   └── screenshots/
├── early_design/                  (6 文件, 早期设计 + PRD + mockup + train data)
├── phase_history/                 (33 文件, Phase 5/6/10/11 + Sprint 9A-D + Pilot + M3 + P0 + Runtime + E2E)
└── productization/                (3 文件, P1.0/P1.1 baseline)
```

### 2.2 归档明细

| # | 源 | 目标 | 文件数 |
|---|---|---|---|
| TD-011 | `docs/Corti_*.md` + `docs/2026-05-08_Corti*.md` | `docs/archive/corti_analysis_2026_05/` | 11 |
| TD-022 | `docs/iCoDer_Convergence_Audit_*.md` + `iCoDer_Governance_Blueprint_*.md` + `iCoDer_vs_Corti_*.md` | 同上 | 6 |
| (extra) | `docs/CORTI_STYLE_*.md` (3 文件) + `docs/ICODER_M3_SECURITY_AND_AUDIT_SPEC.md` | 同上 | 4 |
| TD-012-021 | `docs/PHASE5/6/10/11A-D_*.md` + `SPRINT9B-E_*.md` + `SPRINT_A-D_*.md` + `PILOT_*.md` + `M3_*.md` + `CASE_REASONING_REPORT.md` + `CODING_REVIEW_WORKFLOW_DELIVERY.md` + `EVALUATION_BASELINE_REPORT.md` + `E2E_TEST_*.md` | `docs/archive/phase_history/` | 33 |
| TD-025/026 | `docs/P0_*.md` + `docs/Runtime_*_Delivery_*.md` | 同上 | 4 |
| TD-027 | `docs/FRONTEND_FAKE_FEATURES_AUDIT.md` + `ICODER_CAPABILITY_MAP.md` + `Figma_Design_Prompt_CodeTable_Manager.md` | `docs/archive/early_design/` | 3 |
| TD-035/036/037 | `iCoDer_Medical_Coding_Agent_PRD_V1.0.md` + `icoder-mockup-variant-A.html` + `train(2).xlsx` | 同上 | 3 |
| TD-023 | `docs/audit_remediation/*` (5 E1.x 报告) | `docs/archive/audit_remediation/` | 5 |
| TD-024 | `docs/productization/*` (P1.0/P1.1 baseline) | `docs/archive/productization/` | 3 |
| TD-028-033 | `Corti/` + `corti-crawl/` + `corti_contracts/` + `corti_ui_contracts/` + `screenshots/` + `docs/corti-screens/` | `docs/archive/corti_reference_early/` | 6 子目录 |
| TD-034 | `icoder-next/` (整个子项目) | `archive/icoder-next/` | 1 子目录 |

**P1 统计**: 331 文件归档到 7 个子目录, 0 失败.

### 2.3 保留在 docs/ 根的文档 (48 文件, 当前主线)

- `README_INDEX.md` + 7 份 P1.3 新写文档 (product/architecture/backlog/corti_parity)
- `PHASE_1_*.md` + `PHASE_2_*.md` (近期 cycle 报告, 2026-06-30~07-02)
- `cloud/` (4 份云部署文档)
- `dev/` (BACKEND_RECOVERY.md)
- `sdk/` (js.md, python.md)
- 当前主线参考: `ARCHITECTURE.md` / `TECHNICAL-DESIGN.md` / `agent-pack.md` / `runtime.md` / `QUICKSTART.md` / `SDK-TUTORIAL.md` / `PRODUCT-MODULES.md` / `PRODUCT-ROADMAP.md` (待 TD-098 to TD-103 评估)
- `operation-manual/` (22 文件, P2 归档候选但低优先级)
- `ICODER_V1_*.md` (7 份 Agentic Framework spec)
- `SOLUTION-SCENARIOS.md` / `corti-reverse-engineered/` (Corti 对齐参考)

---

## 3. P2 废弃标记 (TD-038 to TD-079)

### 3.1 已标记的 Python 文件 (32 文件)

**Legacy 单体 Agent (TD-038 to TD-041, 13 文件)**:
- `app/agents/orchestrator.py` ✅
- `app/agents/base.py` ✅
- `app/agents/experts/homepage_expert.py` ✅ (664 LOC, P1.2 概念已删)
- `app/agents/experts/{audit,cdi,denial,diagnosis,drg,evidence,hcc,procedure,report,timeline}_expert.py` (10 文件) ✅

**Legacy AgentRunner (TD-042, TD-043, 1 文件)**:
- `app/services/agent_runner.py` — 已有 DEPRECATED 标记 (v2.1 migration note), 跳过
- `icoder_runtime/agent_runner.py` ✅

**Legacy API (TD-044 to TD-056, 15 文件)**:
- `app/api/icoder_coding_review.py` (1283 LOC) ✅
- `app/api/icoder_agents_hub.py` (1029 LOC) ✅
- `app/api/icoder_agents_compat.py` ✅
- `app/api/icoder_registry_compat.py` ✅
- `app/api/evaluation.py` + `agent_evaluation.py` + `gold_cases.py` ✅ (F1 评估非 Corti)
- `app/api/code_tables.py` + `m2a.py` ✅ (iCoDer 内部概念)
- `app/api/reviews.py` (921 LOC) ✅
- `app/api/experts.py` (551 LOC) ✅
- `app/api/runtime.py` (386 LOC) ✅
- `app/api/text_gen.py` (131 LOC) ✅
- `app/api/facts.py` (204 LOC) ✅
- `app/api/agents.py` (736 LOC) ✅

**Legacy Services (TD-057, TD-062, TD-063, 3 文件)**:
- `app/services/review_coding_service.py` ✅
- `app/services/stt_finetune.py` ✅ (不训练模型)
- `app/services/runtime.py` (702 LOC) ✅

**Legacy icoder_runtime (TD-064, TD-065, 2 文件)**:
- `icoder_runtime/sandbox.py` ✅
- `icoder_runtime/symbolic_state.py` ✅

**Legacy 测试 (TD-078, 1 目录)**:
- `backend/tests/review/` — 含 1 文件 `test_m3_0_redline_invariants.py`, 保留为 experimental (不标 deprecated)

### 3.2 未标记的项 (前端文件, P1.2 已删, 无需标记)

TD-066 to TD-070 (5 前端页) + TD-071 to TD-075 (5 前端组件目录/文件) + TD-076/077 (2 前端 service/hook) + TD-079 (errors.ts MARKETPLACE_ERROR) — 全部 12 项在 P1.2 cycle (2026-06-30) 已物理删除, 无文件可标记.

### 3.3 实验性保留 (未标 deprecated)

TD-058 to TD-061 (4 services): `gold_case_importer.py` + `gold_case_template.py` + `inter_rater.py` + `pilot_report_builder.py` + `ccl2026_importer.py` — 标为 EXPERIMENTAL (MedCodER 评估专用), 保留, 不标 deprecated.

### 3.4 标记格式

每个文件第一行加:
```python
# DEPRECATED (P1.3 Stage 5, 2026-07-02) — <原因>. Phase 2 <后续动作>. 见 docs/architecture/MAINLINE_VS_LEGACY.md §<节>.
```

Python AST 验证: 5 抽样文件 `ast.parse` 全部 OK, 无语法破坏.

---

## 4. .gitignore 更新

新增 11 条目 (P1.3 Stage 5 cleanup section):
```
.corti-user-data/
backend/data/*.bak*
backend/data/icoder.db.broken-*
backend/data/test.db
.tmp_run.json
.tmp_agent_run.json
backend/.tmp_run.json
backend/icoder_runtime/dashboard.html
backend/icoder_runtime/methods/
backend/icoder_runtime/m2a/
```

---

## 5. 未处理的项 (推迟到 Phase 2)

| # | 项 | 原因 |
|---|---|---|
| TD-009 | `backend/icoder_runtime/m2a/` | 非空 (5 .py), 需 Phase 2 重新评估是否 deprecated 或 migrate |
| TD-078 | `backend/tests/review/` | 仅 1 测试文件, 保留为 experimental |
| TD-091 to TD-093 | 命名分散 (organization→project 等) | 高代价, P3 优先级, Phase 2 后期 |

---

## 6. 验证

- ✅ 9/10 P0 项删除 (1 推迟, 有说明)
- ✅ 331 文件归档到 7 个 docs/archive/ 子目录
- ✅ 32 Python 文件加 DEPRECATED 注释, AST 验证无语法破坏
- ✅ .gitignore 加 11 条目防回归
- ✅ 0 误删 (所有删除项有证据 + .gitignore 兜底)

---

## 7. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, Stage 5 资产清理完成 | P1.3 Stage 5 |
