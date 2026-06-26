# Repo Baseline Audit

**日期**: 2026-06-25
**审计前置**: `ICODER_PRODUCT_ARCHITECTURE_AUDIT.md` (2026-06-24)
**审计原则**: 只读不改, 仅描述当前仓库快照
**审计人**: iCoDer 首席产品架构师 + 全栈 + QA

---

## 1. 仓库基础状态

| 项 | 值 | 备注 |
|---|---|---|
| 当前分支 | `master` | — |
| HEAD commit | `43157e2 refactor(medcoder): M1 — delete MedCodERExpertAdapter bridge, wire CodingExpert` | 最近 5 commit 全部 M0/M1 重构 |
| 仓库根 | `E:\Corti4C` | Windows 10, bash via git-bash |
| Python | 3.12.3 | pip 24.0 |
| Node | v22.20.0 | npm 10.9.3 |
| Git 状态 | 11 modified / 12 untracked | 集中在 `app/icoder/mcp/` + `data/medcoder/` + `scripts/analyze_retrieval.py` + `build_medcoder_icd9cm3_index.py` |

### 1.1 修改 / 新增文件

```
 M backend/.icoder/agent_registry.json
 M backend/.icoder/m2a/production_runs.jsonl
 M backend/app/main.py
 M backend/icoder_runtime/providers/medical_coding/hybrid_adapter.py
 M backend/icoder_runtime/providers/medical_coding/medcoder_strategy.py
 M backend/official_agents/homepage-coding-review/agent_pack.json
 M backend/official_agents/homepage_coding_review.py
 M backend/official_agents/medcoder-coding-review/agent_pack.json
 M backend/official_agents/medical_coding/schema.py
 M backend/tests/test_services/test_medical_coding_schema.py
?? backend/app/icoder/mcp/
?? backend/app/services/medcoder_index_health.py
?? backend/data/medcoder/
?? backend/official_agents/medical_coding/modes.py
?? backend/reports/
?? backend/scripts/analyze_retrieval.py
?? backend/scripts/build_medcoder_icd9cm3_index.py
?? backend/scripts/download_bge_m3.py
?? backend/tests/integration/icoder/retrieval/
?? backend/tests/unit/app/
?? backend/tests/unit/icoder/mcp/
?? backend/tests/unit/medical_coding/
```

### 1.2 最近 5 commit

```
43157e2 refactor(medcoder): M1 — delete MedCodERExpertAdapter bridge, wire CodingExpert
a61f687 refactor(medcoder): M1 — HybridCodingAdapter 4-mode MedCodER dispatch
d375c81 feat(medcoder): M1 — CodingExpert runtime Expert impl
0102a41 feat(medcoder): M1 — MedCodERStrategy 5 public stages + 4 ablation variants
3c6a638 refactor(medcoder): M0 — drop legacy shims + publish standard Agent Card
```

---

## 2. 测试基线

### 2.1 测试函数总数

```
$ cd E:/Corti4C/backend && python -m pytest --collect-only -q
1843 tests collected in 2.75s
```

**与 CLAUDE.md 的 752/886 数字不一致** — 实际是 **1843 个测试函数**, 分布在 126 个测试文件。CLAUDE.md 数字是旧历史, 不再代表现状。

### 2.2 已知警告

```
DeprecationWarning: official_agents.homepage_coding_review is deprecated since 2026-06-22;
  use the MedCodER Coding Review Agent (icoder/medcoder-coding-review-agent@1.0.0) instead.
  This module will be removed in M2b.
  Source: backend/app/api/icoder_coding_review.py:60
```

`app/api/icoder_coding_review.py` 仍 `from official_agents.homepage_coding_review import` — 删 homepage_coding_review.py 必须先迁移该 import。

### 2.3 测试目录结构

```
backend/tests/
├── unit/                (MedCodER/Orchestrator/A2A/Context/MCP 真单元测试)
├── test_services/       (hybrid_medcoder / llm_gateway / m2a / gold_case / medcoder_retriever)
├── test_api/            (auth / oauth / coding_review_* / RBAC / PHI)
├── regression/          (F1 baseline / confidence / disagreement / evidence / timeline)
├── e2e_product/         (workbench 3-col / pipeline_full_flow / run_trace_14_stages)
├── integration/icoder/  (a2a / context / retrieval)
├── e2e/icoder/          (a2a_e2e / orchestrator_real_deepseek / orchestrator_throughput)
├── review/              (M3 redline invariants)
├── test_models/         (1)
├── test_compliance/     (1)
└── root                 (test_concurrency)
```

---

## 3. FAISS / MedCodER 资产状态

### 3.1 backend/data/medcoder/ 目录

```
build.log                          1979B   2026-06-08 00:19
build_m25_icd10.log                2035B   2026-06-22 17:26
build_m25_icd10_mirror.log         3968B   2026-06-22 17:45
build_m25_icd10_mirror2.log        6358B   2026-06-22 17:48
build_m25_icd10_v3.log             2695B   2026-06-22 21:38
download_bge_m3.log                6040B   2026-06-22 18:12
models/                            (空目录, BGE-M3 MISSING)
```

**FAISS 索引**: ❌ **MISSING** — `faiss.index` (148 MB) + `metadata.pkl` (6.5 MB) 自 2026-06-19 22:33 静默消失, 无 error 日志、无 audit trail。
**BGE-M3 模型缓存**: ❌ **MISSING** — `~/.cache/huggingface/hub/` 下无 `models--BAAI--bge-m3`, 仅 `bge-large-zh-v1.5` (0.4 GB, 不同模型)。
**重建成本**: ~3.85 hr CPU only (无 GPU)。

### 3.2 HuggingFace Hub cache (`C:/Users/huawei/.cache/huggingface/hub/`)

| 模型 | 状态 |
|---|---|
| `models--BAAI--bge-m3` | ❌ MISSING (需 re-download 2.3 GB) |
| `models--BAAI--bge-large-zh-v1.5` | ✅ present (0.4 GB, **不同模型**) |
| `models--sentence-transformers--all-MiniLM-L6-v2` | ✅ present |
| `models--Systran--faster-whisper-small.en` | ✅ present |

---

## 4. 前端基线

### 4.1 框架栈

| 项 | 值 |
|---|---|
| 框架 | React 18.3.1 |
| 构建 | Vite 5.4.8 |
| 语言 | TypeScript 5.6.2 (strict mode) |
| 样式 | Tailwind 3.4.13 |
| 状态 | zustand 4.5.5 |
| 路由 | react-router-dom 6.26.2 |
| 单元测试 | vitest 2.1.1 + @testing-library/react 16.0.1 |
| E2E | @playwright/test 1.59.1 |
| Lint | eslint |
| HTTP | axios 1.7.7 |

### 4.2 npm scripts

```
dev       vite
build     tsc && vite build
preview   vite preview
test      vitest
lint      eslint . --ext ts,tsx
```

### 4.3 已知阻塞

`CodingReviewWorkbenchPage.tsx` (1229 LOC) 导入不存在的模块:
- `../components/icoder/EvidenceViewer`
- `../components/icoder/HighRiskCodingPointPanel`
- `../components/icoder/RunTraceTimeline`
- `../components/icoder/HumanReviewHistoryTimeline`
- `../services/icoderCodingReviewApi`
- `../components/agent-console/AgentRuntimeConsole`

这些目录/文件**不存在**于 `frontend/src/`。前端 `npm run build` 会编译失败。

---

## 5. CI / Workflow

### 5.1 workflow 文件

```
backend/.github/workflows/ci.yml       1522B  2026-05-31
backend/.github/workflows/e2e.yml      1736B  2026-05-31
backend/.github/workflows/test.yml     1148B  2026-06-05
```

注: `.github/workflows/` 实际在仓库根 `E:/Corti4C/.github/workflows/` (与 backend 平级), 但 `find` 显示在 `E:/Corti4C/backend/.github/workflows/` 也有。**实际路径待 Phase A A5 阶段确认**。

### 5.2 ci.yml 关键命令

```yaml
- run: python -m pytest tests/ -v --ignore=tests/integration
```

**跳过 integration/regression/e2e/e2e_product 全部 28+ 文件, 1843 tests 中实际 CI 跑约 1300-1400 个**。

---

## 6. Legacy 引用命中

### 6.1 legacy 主路径 import 命中 (23 个文件)

| 模块 | 命中数 | 备注 |
|---|---|---|
| `app.services.agent_runner` | 8 | L1 DEPRECATED v2.1, 1047 LOC, RuntimeConfig.fallback_to_legacy gate |
| `app.agents.orchestrator` | 8 | L2 DEPRECATED v2.2, 848 LOC |
| `app.services.llm_service` | 6 | L2 DEPRECATED, 265 LOC, 14 import chain |
| `app.services.llm_adapter` | 1 | L2 DEPRECATED |
| `app.services.llm_planner` | 1 | L2 DEPRECATED |

**关键 import 文件清单**:
```
backend/app/agents/base.py
backend/app/agents/orchestrator.py
backend/app/agents/__init__.py
backend/app/api/agents.py
backend/app/api/experts.py
backend/app/api/medical_docs.py
backend/app/api/reviews.py
backend/app/api/text_gen.py
backend/app/api/websocket.py
backend/app/services/agent_runner.py
backend/app/services/clinical_triage.py
backend/app/services/expert_registry.py
backend/app/services/expert_runner.py
backend/app/services/llm_adapter.py
backend/app/services/llm_planner.py
backend/app/services/memory_expert.py
backend/app/services/punctuation_service.py
backend/app/tools/coding_tools.py
backend/app/tools/report_tools.py
backend/scripts/pilot_eval_runbook.py
backend/tests/test_services/test_agent_runner_runtime.py
backend/tests/test_services/test_agent_runner_tool_native.py
backend/tests/test_services/test_review_runtime_guards.py
```

### 6.2 homepage-coding-review 命中 (30+ 文件)

```
backend/alembic/versions/004_coding_review_run.py
backend/app/api/icoder_coding_review.py        ← 真 import, 不能直接删
backend/app/icoder/agent_runtime/a2a/agent_card.py
backend/app/icoder/agent_runtime/a2a/routes_discovery.py
backend/app/icoder/agent_runtime/a2a/__init__.py
backend/app/main.py
backend/app/models/coding_review_run.py
backend/data/versions.json
backend/icoder_runtime/reports/coding_review_report.py
backend/official_agents/homepage-coding-review/agent_pack.json
backend/official_agents/homepage-coding-review/__init__.py
backend/official_agents/homepage_coding_review.py
backend/official_agents/medcoder-coding-review/agent_pack.json
backend/tests/e2e/icoder/test_a2a_e2e.py
backend/tests/e2e/icoder/test_orchestrator_real_deepseek.py
backend/tests/e2e_product/test_high_risk_priority_codes.py
backend/tests/e2e_product/test_pipeline_validation_full_flow.py
backend/tests/e2e_product/test_report_disclaimer_visible.py
backend/tests/e2e_product/test_run_trace_14_stages.py
backend/tests/e2e_product/test_workbench_three_column_layout.py
backend/tests/integration/icoder/a2a/test_endpoints.py
backend/tests/integration/icoder/context/test_context_lifecycle.py
backend/tests/integration/icoder/context/test_context_repository.py
backend/tests/integration/icoder/context/test_db_schema.py
backend/tests/review/test_m3_0_redline_invariants.py
backend/tests/test_api/test_coding_review_persistence.py
backend/tests/test_api/test_coding_review_phi_export.py
backend/tests/test_api/test_coding_review_rbac.py
backend/tests/test_api/test_coding_review_real_trace.py
backend/tests/test_api/test_icoder_coding_review_no_key.py
```

**关键**: `app/api/icoder_coding_review.py:60` 仍 `from official_agents.homepage_coding_review import (...)` — Phase A 删 homepage_coding_review.py 之前必须先迁移该 import。

### 6.3 a2a_protocol / coding_schema 残留

```
backend/icoder_runtime/core/__pycache__/coding_schema.cpython-312.pyc   ← 源已删, .pyc 残留
```

`a2a_protocol.py` 源 0 hit, **.pyc 也未残留** (M0 已清)。
`coding_schema.py` 源 0 hit, **.pyc 残留 1 个文件** (Phase A A4 待清)。

---

## 7. 仓库 .gitignore

根 `.gitignore` 已存在 (E:/Corti4C/.gitignore):

```
.env / .env.* / !.env.example
**/__pycache__/
*.pyc
*.pyo
*.egg-info/
.pytest_cache/
node_modules/
frontend/dist/
web-components/dist/
sdk/dist/
**/tests/e2e/.auth.json
*.log
*.db
backend/data/*.db
frontend/playwright-report/
frontend/test-results/
htmlcov/
.coverage
coverage.xml
screenshots/  (recursively)
.vscode/
```

**关键缺口**:
- `backend/data/medcoder/` **未 ignore** — 重建 FAISS 后 `faiss.index` (148 MB) 会进入 git
- `backend/data/medcoder/models/` **未 ignore** — 重建 BGE-M3 cache 后会进入 git
- `backend/data/*.db` 已 ignore 但只针对根 db, `data/medcoder/*.db` 未涵盖

---

## 8. requirements.txt 摘要

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
python-multipart==0.0.12
sqlalchemy[asyncio]==2.0.35
alembic==1.13.2
aiosqlite==0.20.0
asyncpg==0.29.0
redis==5.0.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
pydantic[email]==2.9.2
httpx==0.27.2              ← 重复 (L22 vs L49)
starlette==0.38.0
openai==1.51.0
tiktoken==0.7.0
sentence-transformers==3.2.1
faiss-cpu==1.9.0
pandas==2.2.3
numpy==1.26.4
openpyxl==3.1.5
python-dotenv==1.0.1
pydantic-settings==2.5.2
pyyaml==6.0.2
jinja2==3.1.4
rapidfuzz==3.10.0
pytest==8.3.3
pytest-asyncio==0.24.0
pytest-cov==5.0.0
httpx==0.27.2              ← 重复
```

---

## 9. Conftest 与 RBAC gate

`backend/tests/conftest.py` 关键环境变量:

| 变量 | 默认 | 作用 |
|---|---|---|
| `ICODER_ALLOW_DEGRADED_NO_KEY` | 1 | 允许无 DeepSeek key 时降级 echo |
| `ICODER_DISABLE_AUTH_FOR_TESTS` | 1 | 测试默认 bypass JWT, mock admin user |
| `ICODER_DATABASE_URL` | sqlite+aiosqlite:///./data/test.db | 默认 SQLite, CI 切 PG |

`fastapi 0.115.0 + starlette 0.38.0` 不兼容 (Router 无 `on_startup` kwarg), conftest 已 patch。

---

## 10. Baseline Verdict

| 项 | 状态 |
|---|---|
| 仓库可 checkout | ✅ |
| 后端可 import | ✅ (1843 tests collected) |
| 前端可 typecheck | ⚠ **不可** (CodingReviewWorkbenchPage 引用不存在模块) |
| 前端可 build | ⚠ **不可** (同上) |
| FAISS 真实检索 | ❌ **不可** (索引 MISSING, retrieve variant 跑降级) |
| BGE-M3 模型 | ❌ **MISSING** (HF cache 无 bge-m3) |
| CI 跑全量 | ❌ **不可** (`--ignore=tests/integration` 跳过 28+ 文件) |
| legacy 主路径下线 | ❌ 23 文件仍依赖, RuntimeConfig.fallback_to_legacy 仍是默认 |
| homepage-coding-review 退场 | ❌ 30+ 命中, 1 个真实 import (`icoder_coding_review.py:60`) |

---

## 11. Baseline → Phase A 入口

Phase A 任务清单 (A1-A7) 与 baseline 对应:

| Phase A 任务 | Baseline 阻塞 |
|---|---|
| **A1** FAISS / MedCodER 检索资产修复 | `data/medcoder/` 仅 6 log + 空 models/, 无 faiss.index |
| **A2** 前端 CodingReviewWorkbenchPage 编译修复 | 1229 LOC 文件导入不存在的 6 个模块 |
| **A3** 清理 homepage-coding-review 旧路由 | 30+ 命中, 1 个真实 import (icoder_coding_review.py:60) |
| **A4** 清理 legacy .pyc 残留 | `coding_schema.cpython-312.pyc` 1 文件 |
| **A5** 修复 CI | ci.yml `--ignore=tests/integration` 跳过 28+ 文件 |
| **A6** data/medcoder 资产管理策略 | 根 .gitignore 无 `data/medcoder/` ignore 规则 |
| **A7** KB schema 校验 | 无现成 schema validator, KB 与 metadata schema 关系未审计 |

---

**报告结束** | **审计人**: iCoDer 首席架构师 | **日期**: 2026-06-25