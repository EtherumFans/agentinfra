# TECH_DEBT_BACKLOG — 技术债 Backlog

> **声明**: 本文档是 iCoDer **技术债** backlog, 含 legacy 删除 / 命名分散 / 三套架构合并 / 重复代码等. 不含产品功能 (见 `PRODUCT_BACKLOG.md`).
> **日期**: 2026-07-02
> **阶段**: P1.3 Corti Parity Direction Audit 后的技术债梳理
> **状态**: MAINLINE

---

## 0. 技术债原则

- 优先消除"三套 Agent 架构并存"和"API 路径双轨"
- Legacy 代码删除必须先断引用, 再删代码
- 命名分散 (organization vs projects, agent vs agent_definitions) 高代价可放缓
- 不允许 skip / xfail / 删除测试来绕过技术债

---

## 1. P0 立即删 (Stage 5 执行, 无引用 / 备份 / 误入仓库)

| # | 路径 | 类型 | 证据 | 状态 |
|---|---|---|---|---|
| TD-001 | `.corti-user-data/` | 浏览器 profile 误入仓库 | Chrome BrowserMetrics/Crashpad/Default 等数据 | delete + .gitignore |
| TD-002 | `backend/data/icoder.db.bak2` | stale DB 备份 | cycle 23 已识别 alembic=002 + 30 表含 4 deprecated context_* | delete |
| TD-003 | `backend/data/icoder.db.bak20260701` | stale DB 备份 | cycle 23 已识别全 DROP 0 表 | delete |
| TD-004 | `backend/data/icoder.db.broken-20260702` | 损坏 DB | 文件名标 broken | delete |
| TD-005 | `backend/data/test.db` | 测试 DB | CI 应 in-memory | delete + .gitignore |
| TD-006 | `.tmp_run.json` / `.tmp_agent_run.json` / `backend/.tmp_run.json` | 临时运行文件 | 文件名 .tmp_ 前缀 | delete + .gitignore |
| TD-007 | `frontend/src/pages/EmbedDemoCodingReviewPage.tsx.bak` | 备份文件 | .bak 后缀 | delete |
| TD-008 | `icoder_runtime/methods/` | 空目录 | P1.2 已删 10 builtin methods, 仅剩 __pycache__ | delete |
| TD-009 | `icoder_runtime/m2a/` | 空目录 | 概念已弃 | delete |
| TD-010 | `icoder_runtime/dashboard.html` | Standalone HTML | 无 Corti 等价, 前端 AgentsPage 替代 | delete |

---

## 2. P1 归档 (Stage 5 执行, 移到 docs/archive/ 或 archive/)

### 2.1 90+ 历史文档归档

| # | 路径 | 目标 | 证据 |
|---|---|---|---|
| TD-011 | `docs/Corti_*.md` (10 文件) + `2026-05-08_Corti*.md` | `docs/archive/corti_analysis_2026_05/` | 早期 Corti 分析, 已被 corti-reverse-engineered 替代 |
| TD-012 | `docs/PHASE5_LOCAL_DEV_CI_REPORT.md` | `docs/archive/phase_history/` | Phase 5 历史 |
| TD-013 | `docs/PHASE6_PILOT_DATA_EVALUATION_REPORT.md` | 同上 | Phase 6 pilot |
| TD-014 | `docs/PHASE10_GOLD_CASE_VALIDATION.md` | 同上 | Phase 10 |
| TD-015 | `docs/PHASE11A/B/C/D_*.md` (4 文件) | 同上 | Phase 11A-D |
| TD-016 | `docs/SPRINT9B/C/D/E_*.md` (4 文件) | 同上 | Sprint 9B-E |
| TD-017 | `docs/SPRINT_A/B/C/D_*.md` (4 文件) | 同上 | Sprint A-D |
| TD-018 | `docs/PILOT_*.md` (6 文件) | 同上 | Pilot 系列 |
| TD-019 | `docs/M3_*.md` (3 文件) | 同上 | M3 (homepage_coding_review P1.2 已删) |
| TD-020 | `docs/CASE_REASONING_REPORT.md` + `CODING_REVIEW_WORKFLOW_DELIVERY.md` | 同上 | MedCodER 内部 |
| TD-021 | `docs/EVALUATION_BASELINE_REPORT.md` + `E2E_TEST_*.md` (3 文件) | 同上 | F1 baseline + E2E test |
| TD-022 | `docs/iCoDer_Convergence_Audit_*.md` (3 文件) + `iCoDer_Governance_Blueprint_*.md` + `iCoDer_vs_Corti_*.md` | `docs/archive/convergence/` | Convergence audit |
| TD-023 | `docs/audit_remediation/` (5 E1.x 报告) | `docs/archive/audit_remediation/` | E1.x 历史 |
| TD-024 | `docs/productization/` (P1.0 + P1.1 baseline) | `docs/archive/productization/` | P1.0/P1.1 历史 |
| TD-025 | `docs/P0_Gap_Closure_Plan.md` + `P0_QUALITY_GATE_REPORT.md` | `docs/archive/phase_history/` | P0 |
| TD-026 | `docs/Runtime_Discipline_Delivery_2026-05-12.md` + `Runtime_Persistence_Delivery_2026-05-12.md` | 同上 | Runtime 历史 |
| TD-027 | `docs/FRONTEND_FAKE_FEATURES_AUDIT.md` + `ICODER_CAPABILITY_MAP.md` + `Figma_Design_Prompt_CodeTable_Manager.md` | `docs/archive/early_design/` | 早期设计 |

### 2.2 Repo-root extras 归档

| # | 路径 | 目标 | 证据 |
|---|---|---|---|
| TD-028 | `Corti/` (PDF + llms-full.txt) | `docs/archive/corti_reference_early/` | 早期 Corti 调研 |
| TD-029 | `corti-crawl/` | 同上 | 早期 crawler 输出 |
| TD-030 | `corti_contracts/` | 同上 | 早期契约 |
| TD-031 | `corti_ui_contracts/` | 同上 | 早期 UI 契约 |
| TD-032 | `screenshots/` (repo root 早期截图) | 同上 | 早期截图 |
| TD-033 | `docs/corti-screens/` | 同上 | 早期截图分析 |
| TD-034 | `icoder-next/` (整个子项目) | `archive/icoder-next/` (repo root) | Pivot 2026-06-17 已逆转 |
| TD-035 | `iCoDer_Medical_Coding_Agent_PRD_V1.0.md` | `docs/archive/early_design/` | 早期 PRD |
| TD-036 | `icoder-mockup-variant-A.html` | 同上 | 早期 mockup |
| TD-037 | `train(2).xlsx` | 同上 | 训练数据 |

---

## 3. P2 Deprecated 标记 (Stage 5 执行, 代码不动, 加注释 + 文档标记)

### 3.1 Legacy 单体 Agent

| # | 路径 | 标记 | 删除前置条件 |
|---|---|---|---|
| TD-038 | `app/agents/orchestrator.py` | `# DEPRECATED — Phase 2 切换到 app/icoder/agent_runtime/orchestrator/ 后删` | 断 homepage_expert 引用 |
| TD-039 | `app/agents/base.py` | 同上 | 同 |
| TD-040 | `app/agents/experts/homepage_expert.py` (664 LOC) | `# DEPRECATED — P1.2 homepage_coding_review 概念已删, Phase 2 删` | 断 orchestrator.py 引用 |
| TD-041 | `app/agents/experts/` 其余 10 个 | `# DEPRECATED — Phase 2 切换到 app/icoder/agent_runtime/experts/ 后删` | 同 |

### 3.2 Legacy AgentRunner

| # | 路径 | 标记 | 删除前置条件 |
|---|---|---|---|
| TD-042 | `app/services/agent_runner.py` (1047 LOC) | `# DEPRECATED — Phase 2 切换到新 orchestrator 后删` | 断所有引用 |
| TD-043 | `icoder_runtime/agent_runner.py` (重复) | 同上 | 同 |

### 3.3 Legacy API 路径

| # | 路径 | 标记 | 删除前置条件 |
|---|---|---|---|
| TD-044 | `app/api/icoder_coding_review.py` (1283 LOC) | `# DEPRECATED — Phase 2 删 (Corti 用 /v2/tools/coding/)` | 确认 v2_tools_coding 完全覆盖 |
| TD-045 | `app/api/icoder_agents_hub.py` (1029 LOC) | `# DEPRECATED — Phase 2 migrate 到 /rest/v1/agent_definitions` | 迁移完成 |
| TD-046 | `app/api/icoder_agents_compat.py` (123 LOC) | `# DEPRECATED — Phase 2 删` | 迁移完成 |
| TD-047 | `app/api/icoder_registry_compat.py` (106 LOC) | `# DEPRECATED — Phase 2 删` | 迁移完成 |
| TD-048 | `app/api/evaluation.py` (104) + `agent_evaluation.py` (152) | `# DEPRECATED — F1 评估非 Corti 方向` | Phase 2 删 |
| TD-049 | `app/api/gold_cases.py` (144) | `# DEPRECATED — Gold case 非 Corti 方向` | 同 |
| TD-050 | `app/api/code_tables.py` (169) + `m2a.py` (277) | `# DEPRECATED — iCoDer 内部概念无 Corti 等价` | 同 |
| TD-051 | `app/api/reviews.py` (921) | `# DEPRECATED — Phase 2 降级为 Pre-built Agent (Note Completeness + CDI)` | 降级完成 |
| TD-052 | `app/api/experts.py` (551) | `# DEPRECATED — Corti 用 Pre-built Agents + MCP` | 同 |
| TD-053 | `app/api/runtime.py` (386) | `# DEPRECATED — Phase 2 合并到 runtime_platform.py` | 合并完成 |
| TD-054 | `app/api/text_gen.py` (131) | `# DEPRECATED — Phase 2 合并到 v2_tools_guided_document.py` | 合并完成 |
| TD-055 | `app/api/facts.py` (204) | `# DEPRECATED — Phase 2 合并到 v2_tools_facts.py` | 合并完成 |
| TD-056 | `app/api/agents.py` (736) | `# DEPRECATED — Phase 2 migrate 到 /rest/v1/agent_definitions` | 迁移完成 |

### 3.4 Legacy Services

| # | 路径 | 标记 | 删除前置条件 |
|---|---|---|---|
| TD-057 | `app/services/review_coding_service.py` (326) | `# DEPRECATED — 非 Corti 方向` | Phase 2 删 |
| TD-058 | `app/services/gold_case_importer.py` (324) + `gold_case_template.py` (231) | `# EXPERIMENTAL — MedCodER 评估专用, 非主线` | 保留 (实验性) |
| TD-059 | `app/services/inter_rater.py` (193) | 同上 | 同 |
| TD-060 | `app/services/pilot_report_builder.py` (176) | 同上 | 同 |
| TD-061 | `app/services/ccl2026_importer.py` (221) | 同上 | 同 |
| TD-062 | `app/services/stt_finetune.py` (323) | `# DEPRECATED — 不训练模型` | Phase 2 删 |
| TD-063 | `app/services/runtime.py` (702) | `# DEPRECATED — Phase 2 合并到 runtime_platform service` | 合并完成 |

### 3.5 Legacy icoder_runtime

| # | 路径 | 标记 | 删除前置条件 |
|---|---|---|---|
| TD-064 | `icoder_runtime/sandbox.py` | `# DEPRECATED — 无 Corti 等价` | Phase 2 删 |
| TD-065 | `icoder_runtime/symbolic_state.py` | `# DEPRECATED — 实验性` | 同 |

### 3.6 Legacy Frontend Pages

| # | 路径 | 标记 | 删除前置条件 |
|---|---|---|---|
| TD-066 | `frontend/src/pages/EvaluationPage.tsx` (265) | `// DEPRECATED — 非 Corti 方向, Phase 2 删` | App.tsx 断路由 |
| TD-067 | `frontend/src/pages/GoldCasesPage.tsx` (272) | 同上 | 同 |
| TD-068 | `frontend/src/pages/ExpertLibraryPage.tsx` (604) | `// DEPRECATED — Corti 用 Pre-built Agents + MCP` | 同 |
| TD-069 | `frontend/src/pages/OrchestrationPage.tsx` (266) | `// DEPRECATED — Corti 无此独立页` | 同 |
| TD-070 | `frontend/src/pages/EmbedDemoCodingReviewPage.tsx` (225) | `// DEPRECATED — 整合到 EmbeddedAssistantPage` | 同 |

### 3.7 Legacy Frontend Components

| # | 路径 | 标记 | 删除前置条件 |
|---|---|---|---|
| TD-071 | `frontend/src/components/orchestration/` (7 components) | `// DEPRECATED — P1.2 概念已删, Phase 2 删` | 断所有引用 |
| TD-072 | `frontend/src/components/icoder/RunTraceTimeline.tsx` | `// DEPRECATED — P1.2 应删` | 断 embed 包装引用 |
| TD-073 | `frontend/src/components/medical-coding/MethodTraceViewer.tsx` | `// DEPRECATED — P1.2 概念已删` | 同 |
| TD-074 | `frontend/src/components/ExpertLibraryModal.tsx` | `// DEPRECATED — 同 ExpertLibraryPage` | 同 |
| TD-075 | `frontend/src/components/embed/IcoderTraceViewer.tsx` | `// DEPRECATED — 包装 RunTraceTimeline` | 同 |

### 3.8 Legacy Frontend Services/Hooks

| # | 路径 | 标记 | 删除前置条件 |
|---|---|---|---|
| TD-076 | `frontend/src/services/icoderCodingReviewApi.ts` | `// DEPRECATED — Phase 2 删` | 断引用 |
| TD-077 | `frontend/src/hooks/useReviewPipeline.ts` | 同上 | 同 |

### 3.9 Legacy 测试

| # | 路径 | 标记 | 删除前置条件 |
|---|---|---|---|
| TD-078 | `backend/tests/review/` | `# DEPRECATED — MedCodER 内部, Phase 2 评估是否保留` | Phase 2 决策 |
| TD-079 | `frontend/src/utils/errors.ts` 中 `MARKETPLACE_ERROR` | `// DEPRECATED — Marketplace P1.2 已删, 清理` | Phase 2 清理 |

---

## 4. P3 Migrate (Phase 2 执行, 高代价可放缓)

### 4.1 API 合并

| # | 路径 | 目标 | 优先级 |
|---|---|---|---|
| TD-080 | `app/api/icoder_agents_hub.py` (1029) + `agents.py` (736) | 合并迁到 `/rest/v1/agent_definitions` Corti 风格 | P2 |
| TD-081 | `app/api/runtime.py` (386) | 合并到 `runtime_platform.py` | P2 |
| TD-082 | `app/api/text_gen.py` (131) | 合并到 `v2_tools_guided_document.py` | P2 |
| TD-083 | `app/api/facts.py` (204) | 合并到 `v2_tools_facts.py` | P2 |
| TD-084 | `app/services/runtime.py` (702) | 合并到 runtime_platform service | P2 |

### 4.2 icoder_runtime 重复模块合并

| # | 路径 | 目标 | 优先级 |
|---|---|---|---|
| TD-085 | `icoder_runtime/contract_engine.py` vs `app/services/contract_engine.py` | 合并 | P2 |
| TD-086 | `icoder_runtime/guardrails.py` vs `app/services/guardrails.py` | 合并 | P2 |
| TD-087 | `icoder_runtime/permissions.py` vs `app/services/permissions.py` | 合并 | P2 |
| TD-088 | `icoder_runtime/tool_registry.py` vs `app/services/tool_registry.py` | 合并 | P2 |

### 4.3 前端 web-components 合并

| # | 路径 | 目标 | 优先级 |
|---|---|---|---|
| TD-089 | `web-components/` (repo root) | 合并到 `packages/web-components/` | P2 |
| TD-090 | `frontend/src/services/agentHubApi.ts` | 改名对齐 Corti `agent_definitions` | P2 |

### 4.4 命名分散 (高代价, 可放缓)

| # | 路径 | 目标 | 优先级 |
|---|---|---|---|
| TD-091 | `app/models/organization.py` | 评估改名 `project` (Corti 用 projects) | P3 (高代价) |
| TD-092 | `app/models/agent.py` | 评估改名 `agent_definition` (Corti 用 agent_definitions) | P3 (高代价) |
| TD-093 | `app/api/organizations.py` (363) | 评估改名 `projects.py` | P3 (高代价) |

---

## 5. 测试债

### 5.1 现有测试

| # | 路径 | 状态 | 行动 |
|---|---|---|---|
| TD-094 | `backend/tests/regression/` (8 文件: F1/confidence/disagreement/evidence/reasoning/fallback/runtime_recovery) | keep_experimental | 保留 (F1 baseline CLAUDE.md 已降级非主线, 但测试保留) |
| TD-095 | `backend/tests/conftest.py` | keep_mainline | Cycle 25 已加固 |
| TD-096 | `backend/tests/test_api/` | keep_mainline | 不动 |
| TD-097 | `frontend/src/services/__tests__/apiContract.test.ts` | keep_mainline | Cycle 25 加的 OpenAPI contract test |

### 5.2 测试债原则

- 不允许 skip / xfail / 删除测试来绕过技术债
- 任何测试失败必须修复后重跑
- Legacy 测试 (regression F1 等) 保留为 experimental, 不上线但不删

---

## 6. 文档债

### 6.1 CLAUDE.md 更新 (Stage 4 后)

| # | 路径 | 状态 | 行动 |
|---|---|---|---|
| TD-098 | `CLAUDE.md` (项目根) | 含 MedCodER 主线描述 (CLAUDE.md:80-130) | Stage 4 后更新, MedCodER 降级为 Pre-built Agent #18, 引用 PRODUCT_DIRECTION.md |

### 6.2 旧架构文档更新

| # | 路径 | 状态 | 行动 |
|---|---|---|---|
| TD-099 | `docs/ARCHITECTURE.md` | 可能含旧架构描述 | Stage 4 后评估是否引用 CURRENT_ARCHITECTURE.md |
| TD-100 | `docs/PRODUCT-ROADMAP.md` | 可能含旧路线图 | Stage 4 后评估是否引用 CORTI_PARITY_ROADMAP.md |
| TD-101 | `docs/PRODUCT-MODULES.md` | 可能含旧模块描述 | 同 |
| TD-102 | `docs/TECHNICAL-DESIGN.md` | 同 | 同 |
| TD-103 | `docs/runtime.md` | 同 | 同 |

### 6.3 新文档 (Stage 4 已建)

| # | 路径 | 状态 |
|---|---|---|
| TD-104 | `docs/product/PRODUCT_DIRECTION.md` | ✅ 已建 |
| TD-105 | `docs/architecture/CURRENT_ARCHITECTURE.md` | ✅ 已建 |
| TD-106 | `docs/architecture/MAINLINE_VS_LEGACY.md` | ✅ 已建 |
| TD-107 | `docs/product/CORTI_PARITY_ROADMAP.md` | ✅ 已建 |
| TD-108 | `docs/backlog/PRODUCT_BACKLOG.md` | ✅ 已建 |
| TD-109 | `docs/backlog/TECH_DEBT_BACKLOG.md` | 本文档 |
| TD-110 | `docs/README_INDEX.md` | ⏳ Stage 4 最后建 |

---

## 7. 技术债统计

| 优先级 | 数量 | 时间窗 |
|---|---|---|
| P0 (立即删) | 10 | Stage 5 |
| P1 (归档) | 27 (90+ 文件) | Stage 5 |
| P2 (Deprecated 标记) | 42 | Stage 5 |
| P3 (Migrate) | 11 | Phase 2 |
| 测试债 | 4 | 持续 |
| 文档债 | 13 | Stage 4 + Phase 2 |

**总计**: ~107 项技术债, 其中 P0-P2 79 项在 P1.3 范围内处理.

---

## 8. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, 107 项技术债清单 | P1.3 Stage 3 方向纠偏 |
