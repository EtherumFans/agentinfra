# iCoDer 产品与架构状态审计

**审计日期**: 2026-06-24
**审计范围**: Runtime Core / Coding & MedCodER / 前端 / 测试与 CI / 技术债
**审计原则**: 只读不改 — 不动代码、不删代码、不重构代码、不新增功能
**审计人**: iCoDer Runtime 首席架构师

---

## 1. 当前产品状态结论

iCoDer 已完成 **M0 + M1 + M2 三个 MedCodER Runtime Upgrade 节点**，从「单一 MedCodER Agent」逐步演化为「Coding Method Runtime」的雏形。当前系统**已具备以下真实能力**:

1. **Runtime Core 新旧双栈并存**: 新版 `app/icoder/orchestrator/*` (~2200 LOC) + `app/icoder/a2a/*` (~2400 LOC) + `app/icoder/context/*` (~600 LOC) + `app/icoder/mcp/*` (752 LOC) 全部真实实现并通过 main.py 挂载;但 `icoder_runtime/agent_runner.py` (491 LOC) + `app/services/agent_runner.py` (1047 LOC DEPRECATED) + `app/agents/orchestrator.py` (848 LOC DEPRECATED) 三套 Runtime 平行挂着。
2. **MedCodER 已下沉到 Expert 层**: HybridCodingAdapter 9-mode dispatch + MedCodERStrategy 5-stage public API + 4 ablation variants + CodingExpert Runtime 真 Expert impl (226 LOC) + MCP 5 handlers (search_icd/rerank_codes/verify_code/calibrate_confidence/get_differentiation_hint) — 是第一个真接通 Runtime 的领域 Agent。
3. **FAISS 索引资产全 MISSING** (`backend/data/medcoder/`): 148 MB `faiss.index` + 6.5 MB `metadata.pkl` + 2.3 GB BGE-M3 模型 cache 于 2026-06-19 22:33 静默消失,**无 error 日志、无 audit trail**;`build_medcoder_index.py` 重建需 ~3.85 hr (CPU)。当前所有 retrieve variant 跑在降级模式, F1@1=0.0921 不可解读为真实性能。
4. **Code Like Humans 4 组件是 metadata-only 孤岛**: `evidence_extractor` / `index_navigator` / `tabular_validator` / `code_reconciler` 四个目录只有 `agent_pack.json`,**无实现、无 system_prompt、无工具接通、无 MCP 接入**。
5. **前端仍写死 MedCodER**: `MedicalCodingPage.tsx` (803 LOC) 是单 mode, 仅在 `mode === 'medcoder'` 时渲染 `DiagnosisCard`;`CodingReviewWorkbenchPage.tsx` 导入不存在的 `../components/icoder/*` 与 `../services/icoderCodingReviewApi`, 该路径无法编译/运行;`App.tsx:81` 仍挂载 `/studio/agents/homepage-coding-review` 路由。
6. **CI 跳过 95% 后端测试**: `ci.yml` 用 `--ignore=tests/integration` 排除 integration/regression/e2e/e2e_product 全部 28+ 文件, 201-case F1、4-variant ablation、hybrid_medcoder_subprocess 全部**不在 PR gate**。

**战略对齐度**: "Coding Method Runtime" 战略已**有骨架无肉** — 架构层 (Orchestrator + A2A + MCP + Agent Card + Context) 完成度 70%, 但 Method 切换 UI、Code Like Humans 4 组件真实实现、FAISS 重建、legacy 清理、CI 完整化这 5 件事是真正的 90 天关键路径。

---

## 2. 已实现能力清单

### 2.1 Runtime Core

| 模块 | 路径 | 状态 | 完成度 | 风险 |
|---|---|---|---|---|
| **Orchestrator** | `app/icoder/orchestrator/` (planner 393 / inbound 482 / delegator 271 / aggregator 252 / state_machine 125 / metrics 279 / recorder_adapter 410 / wiring 274 / phi_redactor 189 / prompts 173) | 真实实现 | 85% | RecorderAdapter 是单点桥接层, 修改需谨慎 |
| **A2A v0.3** | `app/icoder/a2a/` (5 routers + envelope 297 + messages 205 + parts 188 + agent_card 382 + errors 306 + icoder_metadata 174) | 真实实现 | 75% | `routes_task_stub.py` Phase 1 stub 返 501, Task 完整生命周期 Phase 5 |
| **Context** | `app/icoder/context/` (lifecycle 251 / repository 244 / audit / gc / isolation / db_models / icoder_metadata) | 真实实现 | 70% | DB model + repository 已建, 未直接 mount HTTP 端点 |
| **MCP Server** | `app/icoder/mcp/` (server 490 + tool_registry 262 + errors 85 + 5 handlers) | 真实挂载 | 80% | main.py:578 已 mount, 5 个 MedCodER 工具接通 |
| **LLMGateway** | `icoder_runtime/core/llm_gateway.py` (536 LOC) | 真实实现 | 85% | Circuit breaker + fallback + 4 providers |
| **RuntimeAgentRegistry** | `icoder_runtime/core/registry.py` (295) + `registry_backend.py` (158) | 真实实现 | 90% | file/SQLite/Postgres 3 backends |
| **AgentPackageV1** | `icoder_runtime/core/agent_pack_v1.py` (322) | 真实实现 | 90% | sha256 校验 + validate_llm_capabilities |
| **DataPolicy / PII** | `icoder_runtime/core/data_policy.py` (100) + `pii_redaction.py` (116) | 真实实现 | 75% | 与 `app/icoder/orchestrator/phi_redactor.py:121` 平行 PHI |
| **PlatformRuntime** | `icoder_runtime/embedded/platform_runtime.py` (216) | 真实实现 | 80% | 与新版 Orchestrator 互补 |
| **Observability** | `icoder_runtime/observability/` (run_history 99 + audit_log 80 + fallback 127 + shadow_diff 197) | 真实实现, **未 wire main.py** | 50% | 全是 class 但 main.py 不 import |
| **M2a 闭环** | `icoder_runtime/m2a/` (1212 LOC: recorder/run_trace/safety_gate/risk_router/human_review/store) | 真实挂载 | 90% | `/api/m2a/*` 已 mount |
| **legacy AgentRunner** | `icoder_runtime/agent_runner.py` (491) | 真实但**应淘汰** | 0% 推荐 | PreGuard/PostGuard/SafetySpiral 已被新版覆盖 |
| **legacy agent_runner service** | `app/services/agent_runner.py` (1047) | DEPRECATED v2.1 | 0% 推荐 | 20+ import 链未清 |
| **legacy orchestrator service** | `app/agents/orchestrator.py` (848) | DEPRECATED v2.2 | 0% 推荐 | reviews.py:26 + pilot_eval 仍调用 |
| **legacy llm_service** | `app/services/llm_service.py` (265) | DEPRECATED v2.1 | 0% 推荐 | 14 处 import 横跨 tools/agents/api |
| **legacy runtime API** | `app/api/runtime.py` (386) `/api/runtime-legacy/*` | DEPRECATED | 0% 推荐 | main.py 仍挂, 待删 |
| **serve.py / cli.py / dashboard.html** | `icoder_runtime/serve.py` (331) / `cli.py` (388) / `dashboard.html` (15KB) | dead path | 0% | main.py 不挂, 纯死物 |

### 2.2 Agent / Expert / MCP Tool

| 能力 | 状态 | 完成度 | 代码位置 | 风险 |
|---|---|---|---|---|
| **CodingExpert** | 真 Expert impl | 95% | `app/icoder/experts/coding_expert.py:226` | 已接 Runtime Expert interface |
| **MedCodER Agent** | Official Agent Pack | 85% | `official_agents/medcoder-coding-review/agent_pack.json` | M2 tools[].ref 指向真 route |
| **MedCodER 5-stage Strategy** | public API + 4 ablation | 90% | `icoder_runtime/providers/medical_coding/medcoder_strategy.py` | `full` variant 跑通, retrieve 降级 |
| **HybridCodingAdapter** | 9-mode dispatch | 80% | `icoder_runtime/providers/medical_coding/hybrid_adapter.py` | mode 枚举完整, retrieve variants 跑降级 |
| **evidence_extractor (CLH)** | metadata-only | 5% | `official_agents/evidence_extractor/agent_pack.json` | 无 system_prompt, 无 tool 接通 |
| **index_navigator (CLH)** | metadata-only | 5% | `official_agents/index_navigator/agent_pack.json` | 同上 |
| **tabular_validator (CLH)** | metadata-only | 5% | `official_agents/tabular_validator/agent_pack.json` | 同上 |
| **code_reconciler (CLH)** | metadata-only | 5% | `official_agents/code_reconciler/agent_pack.json` | 同上 |
| **homepage_coding_review.py** | 14-stage cosmetic | **应删** | `official_agents/homepage_coding_review.py:96` | 7 处 deprecated warning |
| **homepage-coding-review pack** | 14 tool 平行 manifest | **应 WRAP** | `official_agents/homepage-coding-review/agent_pack.json` | 迁 14 tool → MedCodER Agent Card |
| **MCP search_icd** | 真接通 | 90% | `app/icoder/mcp/handlers/search_icd.py` | 共享 `_hybrid_adapter._strategy` |
| **MCP rerank_codes** | 真接通 | 90% | 同上 | — |
| **MCP verify_code** | 真接通 | 90% | 同上 | — |
| **MCP calibrate_confidence** | 真接通 | 85% | 同上 | — |
| **MCP get_differentiation_hint** | 真接通 | 85% | 同上 | — |
| **MedicalCodingRuleSet** | R001-R010 + MC-R-M80-001 | 90% | `compliance_services/medical_coding_rules.py` | 与 legacy rule_engine.py 平行 |
| **RepairLoop** | HybridCodingAdapter.infer_async | 80% | `hybrid_adapter.py` | 201 case F1 测试基础 |

### 2.3 Coding 方法

| 方法 | 状态 | 完成度 | 风险 |
|---|---|---|---|
| **MedCodER** (5-stage) | 真接通, retrieve 降级 | 75% | FAISS MISSING, Stage 2 全失败 |
| **Code Like Humans** | 4 agent 仅 metadata | 5% | 完整 Agent impl + system_prompt + MCP 接入全部待做 |
| **Tree Search** | 未启动 | 0% | 无设计文档, 无 Agent |
| **Evidence-first Coding** | 部分 (evidence_anchoring_kb 8.1MB, 972 码 × 6490 patterns) | 40% | KB 资产就绪, 无 Agent 包装 |
| **Rule-guided Coding** | 真接通 (MedicalCodingRuleSet R001-R010) | 80% | 12 rules, RepairLoop 已 wire |

### 2.4 Frontend

| 能力 | 状态 | 完成度 | 代码位置 | 风险 |
|---|---|---|---|---|
| **MedicalCodingPage** | 单 mode (MedCodER only) | 70% | `frontend/src/pages/MedicalCodingPage.tsx:803` | 仅 MedCodER mode 渲染 DiagnosisCard |
| **DiagnosisCard** | 完整 (evidence + TopK + override) | 90% | `components/medical-coding/DiagnosisCard.tsx:136` | 含 5 字段 + override 回调 |
| **EvidenceHighlighter** | 完整 (server-side fuzzy 回退) | 90% | `components/medical-coding/EvidenceHighlighter.tsx:99` | `<mark>` 包裹 |
| **TopKChips** | 完整 (4 source 颜色 + 选中态) | 90% | `components/medical-coding/TopKChips.tsx:70` | — |
| **Method Trace** | **缺失** | 0% | 无对应组件 | Method Trace 是 Runtime run_trace 前端投影 |
| **Method 切换器** | **缺失** | 0% | 无 MedCodER ↔ CLH ↔ Tree Search UI | Coding Method Runtime 最大缺口 |
| **Embed Review Panel** | 完整 (5 种 action) | 90% | `components/embed/IcoderReviewPanel.tsx:226` | accept/reject/modify/escalate/insufficient_evidence |
| **Embed Evidence / Trace Viewer** | 完整 | 85% | `components/embed/IcoderEvidenceViewer.tsx:139` + `IcoderTraceViewer.tsx:95` | — |
| **CodingReviewWorkbenchPage** | **不可编译** | 0% | `pages/CodingReviewWorkbenchPage.tsx:1229` | 导入不存在 `components/icoder/*` + `icoderCodingReviewApi` |
| **homepage-coding-review 路由** | **未清理** | 0% | `App.tsx:81` + `CodingReviewWorkbenchPage.tsx:343` + `EmbedDemoCodingReviewPage.tsx:125` | 3 处仍引用旧 agent ref |

### 2.5 Test

| 类别 | 数量 | 状态 | 风险 |
|---|---|---|---|
| **测试文件总数** | 126 (find) | — | 与 CLAUDE.md 752/886 不符, 需 `--collect-only` 出权威数 |
| **unit/icoder/** | 30 (orchestrator 14 / context 7 / mcp 3 / a2a 4 / experts 1 / providers 1) | 真覆盖 | M2 MCP 测试齐全 |
| **test_services/** | 48 | 真覆盖 | 含 hybrid_medcoder/llm_gateway/m2a/gold_case/medcoder_retriever |
| **test_api/** | 9 | 真覆盖 | auth/oauth/coding_review_* |
| **regression/** | 9 | **CI 跳过** | F1 baseline/confidence/disagreement/evidence/timeline/reasoning/runtime_recovery/fallback_audit/case_report |
| **e2e_product/** | 8 | **CI 跳过** | workbench/pipeline_full_flow/run_trace_14_stages/disclaimer/high_risk/negative/evidence_viewer/embed_demo |
| **integration/icoder/** | 7 | **CI 跳过** | a2a 1 / context 5 / **retrieval 仅 1 smoke** |
| **e2e/icoder/** | 3 | **CI 跳过** | a2a_e2e / orchestrator_real_deepseek / orchestrator_throughput |
| **unit/medical_coding/** | 1 (mode_enum only) | **空壳** | MedCodER 真测试散在 test_services/ |
| **unit/app/** | 1 | 真覆盖 | — |
| **unit/icoder/mcp/** | 3 (handlers/server/tool_registry) | 真覆盖 | M2 验证 |
| **CI workflow** | ci.yml / e2e.yml / test.yml | active | ci.yml + test.yml 重复且 `--ignore=tests/integration` |

### 2.6 Infra

| 能力 | 状态 | 完成度 | 风险 |
|---|---|---|---|
| **Docker Compose** | 已配置 (PostgreSQL + Redis + Nginx) | 85% | `backend/Dockerfile` + `docker-compose.yml` |
| **FAISS 索引** | **MISSING** | 0% | 148 MB index + 6.5 MB metadata + 2.3 GB 模型 cache 静默消失 |
| **BGE-M3 模型** | **MISSING** (cache 目录空, HF Hub 无 bge-m3) | 0% | 需 re-download 2.3 GB |
| **iCoDerA 资产** | 健康 (8 个 KB 文件, 100+ MB) | 100% | 只读, 医院本地 |
| **data/medcoder build log** | 6 个 log 文件 (2026-06-08 ~ 2026-06-22) | — | 显示多次 build attempt, 最后一次 2026-06-22 21:38 v3 失败 |
| **Alembic migrations** | 已配置 | 80% | `backend/alembic/` + `alembic.ini` |
| **pytest-cov** | 装在 requirements, **从未跑过** | 0% | `htmlcov/` + `.coverage` 缺失 |
| **CI** | 3 workflow active, 跳过 95% 测试 | 30% | ci.yml/test.yml 重复, 分支监听不一致 |

---

## 3. Runtime 成熟度矩阵

| 模块 | 当前成熟度 | 目标 | 关键缺口 |
|---|---|---|---|
| **Context** | 1 Working | 2 Production | HTTP 端点未直接 mount, GC 策略未实跑 |
| **A2A** | 1.5 Working | 2 Production | Task lifecycle Phase 1 stub 501, SSE Phase 6 |
| **Orchestrator** | 2 Production | 3 Enterprise | RecorderAdapter 单点, 无 Planner LLM 真实跑通 e2e orchestrator_real_deepseek |
| **MCP** | 2 Production | 3 Enterprise | 仅 5 MedCodER tools, 无 tools/list discoverability 前端 |
| **Recorder (m2a)** | 2 Production | 3 Enterprise | run_trace → 前端 trace 投影未接通 |
| **Metrics** | 1.5 Working | 2 Production | orchestrator/metrics.py 279 LOC 实现, 但 `/api/metrics` 仅 prometheus client, orchestrator metrics 未暴露 |
| **Agent Card** | 2 Production | 3 Enterprise | medcoder-coding-review + medcoder_coding_review_card factory 真实, 缺 ISV registry (Phase 4) |
| **Expert (CodingExpert)** | 2 Production | 3 Enterprise | 226 LOC 真 Expert impl, 但 4 CLH agent 是 metadata-only |
| **legacy AgentRunner** | 1 Working (已淘汰) | DELETE | 与新版三轨并行, 风险源 |
| **legacy agent_runner service** | 0 (DEPRECATED) | DELETE | 1047 LOC + 20+ import 链 |
| **legacy orchestrator service** | 0 (DEPRECATED) | DELETE | 848 LOC + reviews.py 调用 |
| **legacy llm_service** | 0 (DEPRECATED) | DELETE | 265 LOC + 14 处 import |
| **legacy runtime API** | 0 (DEPRECATED) | DELETE | 386 LOC, `/api/runtime-legacy/*` |

**分级标准**:
- 0 = Prototype (stub / 单文件 demo)
- 1 = Working (class/函数真实实现, 但未 wire / 未挂载)
- 2 = Production Ready (wire 完整, 测试覆盖, 文档)
- 3 = Enterprise Ready (observability + SLA + 灾备 + 横向扩展)

---

## 4. Coding Method Runtime 差距

战略定位: "iCoDer 不只是 MedCodER Agent, 而是 Coding Method Runtime", 需支持 MedCodER / Code Like Humans / Tree Search / Evidence-first / Rule-guided 五种方法。

### 4.1 已具备什么

| 能力 | 状态 | 位置 |
|---|---|---|
| 5-stage MedCodER 管线 | 真实实现 | `medcoder_strategy.py` (5 public stages + 4 variants) |
| HybridCodingAdapter 多 mode dispatch | 真实实现 (9 mode) | `hybrid_adapter.py` |
| MCP tools 接入机制 | 真实 (5 tools 接通 MedCodER) | `app/icoder/mcp/handlers/` |
| Agent Card factory + Discovery 端点 | 真实 | `app/icoder/a2a/agent_card.py:382` |
| Evidence anchoring KB 资产 | 真实 (8.1 MB, 6490 patterns) | `E:/iCoDerA/DataAsset/evidence_anchoring_kb.json` |
| Coding differentiation KB 资产 | 真实 (2.9 MB, 2090 groups) | `E:/iCoDerA/DataAsset/coding_differentiation_kb.json` |
| BGE-M3 embedding pipeline | 代码真实, **资产 MISSING** | `scripts/build_medcoder_index.py` |
| Recorder + run_trace | 真实 | `icoder_runtime/m2a/` |
| HybridCodingAdapter.infer_async RepairLoop | 真实 | `hybrid_adapter.py` |

### 4.2 缺什么

| 缺口 | 影响 |
|---|---|
| **Method 切换 UI** | 前端无法选 MedCodER / CLH / Tree Search, 全部走后端默认 mode |
| **Method Trace 前端投影** | run_trace 数据已记录, 但前端无组件 |
| **Tree Search Agent** | 整方法未启动, 无 Agent |
| **FAISS 索引 + BGE-M3 模型** | 全部 Stage 2 跑降级, retrieve variant 失效 |
| **Code Like Humans 4 agent 实现** | 全部 metadata-only, 无 system_prompt / 无 tool 接通 |
| **CDI / DRG / Charge Compliance Agents** | `official_agents/cdi-review/` 等目录空 |
| **多 Expert 协同 Planner** | Orchestrator 已实现, 但未配 multi-expert coding scenario |
| **跨方法对比** | 无法跑 "MedCodER vs CLH" F1 对比 |
| **Confidence calibration UI** | MCP calibrate_confidence 已实现, 前端无显式 confidence 展示 |

### 4.3 需要新增什么

| 新增项 | 优先级 | 说明 |
|---|---|---|
| `MethodSwitcher` 前端组件 | P0 | MedCodER / CLH / Tree Search 三选一 + 显示当前 trace method |
| `MethodTraceViewer` 前端组件 | P0 | 接收 run_trace → 5 阶段时间线 + per-disease evidence chips |
| Code Like Humans 4 agent 真实现 | P0 | system_prompt + tool list + MCP handler + agent_pack test fixture |
| FAISS rebuild 自动化 | P0 | CI step `python scripts/build_medcoder_index.py`, 产物入 git LFS 或 S3 |
| Tree Search agent v0.1 | P1 | 概念验证, 接 MedCodER Stage 4 rerank 框架 |
| `CodingMethodRegistry` | P0 | Runtime 端 method 注册表 (类似 `experts/registry`), `app/icoder/coding_methods/` |
| `MethodCompare` e2e 脚本 | P1 | 同 case 跑 MedCodER vs CLH vs Tree Search, 输出 F1 对比表 |

---

## 5. MedCodER 定位

### 5.1 当前归属

MedCodER 在当前系统中属于 **Runtime Expert 级别**, 具体证据链:

```
HybridCodingAdapter (icoder_runtime/providers/medical_coding/)
  └─ mode="medcoder" → MedCodERStrategy (5-stage public API)
                       └─ CodingExpert (app/icoder/experts/coding_expert.py:226) 真 Expert impl
                       └─ 5 MCP handlers (app/icoder/mcp/handlers/) 真接通
                       └─ MedCodER Agent Card (a2a/agent_card.py medcoder_coding_review_card)
                       └─ MedCodER Agent Pack (official_agents/medcoder-coding-review/agent_pack.json)
```

**不是**: Runtime Core / Legacy Pipeline / 单纯 Strategy

### 5.2 是否存在写死 / 双路径 / 旧 pipeline

| 问题 | 状态 | 证据 |
|---|---|---|
| **写死 MedCodER** | 前端**是**, 后端**否** | `MedicalCodingPage.tsx:272` `isMedcoderMode = result.mode === 'medcoder'` 是唯一分支, 但后端 HybridCodingAdapter 是 9 mode dispatch |
| **双路径** | **是**, 高风险 | HomepageCodingReview (14-stage cosmetic) ‖ ReviewCodingService+CodingPipelineOrchestrator (4-agent) ‖ MedCodERStrategy (5-stage) — 同一 API 三入口 |
| **旧 pipeline 残留** | **是**, 标记 DEPRECATED 但仍挂 | `app/services/agent_runner.py` L1 DEPRECATED, `app/agents/orchestrator.py` L2 DEPRECATED, `app/api/runtime.py` L15 `/api/runtime-legacy` 注释并存 |
| **MedCodERExpertAdapter bridge** | **已删** (M1) | 仅 docs 提及, 源码 0 hit |
| **a2a_protocol.py** | **已删** (M0) | 源 0 hit, 但 `.pyc` 残留未清 |
| **coding_schema shim** | **已删** (M0) | 源 0 hit, `.pyc` 残留未清 |
| **homepage-coding-review pack** | **未删**, 与 medcoder-coding-review 平行 manifest | `MEDCODER_CAPABILITY_AUDIT.md:201` 标注 |
| **homepage-coding-review 路由** | **未删**, 前端仍挂载 | `App.tsx:81` + 2 处引用 |

### 5.3 风险评级

**MedCodER 本身**: 健康, M0+M1+M2 收口干净。
**周围生态**: HIGH 风险, 双路径 + 14-stage cosmetic + legacy AgentRunner 都在挂。

---

## 6. Code Like Humans Readiness

Code Like Humans 需 4 个核心能力组件, 当前真实状态:

| 组件 | metadata | system_prompt | tool list | MCP 接通 | runtime impl | 测试 |
|---|---|---|---|---|---|---|
| **evidence_extractor** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **index_navigator** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **tabular_validator** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **code_reconciler** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

**完成度**: 5% (仅 metadata, 0% runtime)

### 6.1 缺什么

| 缺项 | 优先级 | 描述 |
|---|---|---|
| evidence_extractor system_prompt | P0 | 抽取病历中的 {disease, supporting_evidence, span} 三元组 |
| evidence_extractor tool list | P0 | `extract_evidence(emr_text) → List[Evidence]` |
| evidence_extractor MCP handler | P0 | `app/icoder/mcp/handlers/extract_evidence.py` |
| index_navigator system_prompt | P0 | BGE-M3 + FAISS top-K + synonym expansion |
| index_navigator tool list | P0 | `navigate(code_or_text) → List[Candidate]` |
| index_navigator MCP handler | P0 | 接入现有 FAISS 资产 (待重建) |
| tabular_validator system_prompt | P1 | tabular 校验 (性别/年龄/合并症/手术编码) |
| tabular_validator tool list | P1 | `validate(code, patient_meta) → Violations` |
| code_reconciler system_prompt | P0 | 多源 evidence → final code 收敛 |
| code_reconciler tool list | P0 | `reconcile(evidence_set, candidates) → FinalCode` |
| Orchestrator 多 Expert 协同 | P0 | 当前 planner 是单 expert, 需 4 expert 编排 |
| e2e_compare 测试 | P1 | MedCodER full vs CLH 4-expert 对比 |

### 6.2 资产就绪度

| 资产 | 状态 | 用途 |
|---|---|---|
| `evidence_anchoring_kb.json` (8.1 MB) | 健康 | evidence_extractor 锚点 |
| `coding_differentiation_kb.json` (2.9 MB) | 健康 | code_reconciler 决策 |
| `cot_generation_progress_v2.json` (175 样本) | 健康 | code_reconciler CoT few-shot |
| FAISS index + BGE-M3 | **MISSING** | index_navigator 阻塞 |

---

## 7. 技术债清单

### 7.1 Legacy 文件 (DEPRECATED 但未删)

| 模块 | 路径 | LOC | 风险等级 | 建议 |
|---|---|---|---|---|
| legacy agent_runner service | `app/services/agent_runner.py` | 1047 | **HIGH** | DELETE (gated by `RuntimeConfig.fallback_to_legacy`) |
| legacy orchestrator service | `app/agents/orchestrator.py` | 848 | **HIGH** | DELETE after M2b |
| legacy llm_service | `app/services/llm_service.py` | 265 | **HIGH** | DELETE/MIGRATE |
| legacy runtime API | `app/api/runtime.py` (`/api/runtime-legacy/*`) | 386 | MED | DELETE |
| legacy rule_engine (CODING_RULES KB) | `app/services/rule_engine.py` | 246 | MED | DELETE (compliance_services/ 已替代) |
| homepage_coding_review.py | `official_agents/homepage_coding_review.py` | 96 | **HIGH** | DELETE (M2b 计划) |
| homepage-coding-review pack | `official_agents/homepage-coding-review/` | 116 | **HIGH** | WRAP (迁 14 tool → MedCodER Agent Card) |
| legacy AgentRunner (runtime) | `icoder_runtime/agent_runner.py` | 491 | **HIGH** | REFACTOR (PreGuard/PostGuard 逻辑并入 Orchestrator) |
| coding_schema.pyc 残留 | `__pycache__/coding_schema.cpython-312.pyc` | 797B | LOW | DELETE |
| a2a_protocol.pyc 残留 | `__pycache__/a2a_protocol.cpython-312.pyc` | — | LOW | DELETE |
| serve.py / cli.py / dashboard.html | `icoder_runtime/` | 734+15KB | MED | DELETE (main.py 不挂) |
| MedCodERExpertAdapter bridge | — | — | NONE | 已删 M1, 0 hit |
| a2a_protocol.py 源 | — | — | NONE | 已删 M0, 0 hit |

### 7.2 双路径 / 平行路径

| 双路径 | 入口 A | 入口 B | 切换机制 | 风险 |
|---|---|---|---|---|
| **AgentRunner 双副本** | `app/services/agent_runner.py` (旧 DB) | `icoder_runtime/agent_runner.py` (新 registry) | `RuntimeConfig.execution_mode` (legacy|platform_runtime|shadow) | HIGH — `app/api/agents.py:468-526` 显式 shadow |
| **Coding 三轨** | HomepageCodingReview (14-stage) | ReviewCodingService + CodingPipelineOrchestrator (4-agent) | MedCodERStrategy (5-stage) | HIGH — 同一 API 多入口 |
| **LLM 调用双栈** | `app.services.llm_service.LLMService` | `icoder_runtime.core.llm_gateway.LLMGateway` | — | MED — 14 处 import 横跨 |
| **RuleEngine 三栈** | `app/services/rule_engine.py` (旧 KB) | `icoder_runtime/.../rule_engine_adapter.py` (R001-R012) | `compliance_services/rule_engine.py` (新 framework) | MED — 三个互不引用 |
| **PHI 处理** | `icoder_runtime/core/pii_redaction.py` | `icoder_runtime/core/data_policy.py` | `app/icoder/orchestrator/phi_redactor.py` | MED — 三处独立实现 |
| **Audit logger** | `icoder_runtime/observability/audit_log.py` | `app/icoder/agent_runtime/context/context_audit.py` | `icoder_runtime/m2a/run_trace.py` | MED — 三处审计 |
| **Tests 双目录** | `backend/tests/` | `backend/icoder_runtime/tests/` | — | LOW — 部分 test 重名 (`test_runtime.py` x2) |

### 7.3 死代码

| 项 | 状态 |
|---|---|
| `MedCodERExpertAdapter` bridge | 已删 M1 (源码 0 hit, docs 提及) |
| `a2a_protocol.py` 源 | 已删 M0 (源码 0 hit, `.pyc` 残留未清) |
| `coding_schema` shim | 已删 M0 (源 0 hit, `.pyc` 残留未清) |
| `app/services/rule_engine.py` `CODING_RULES` KB | 死 — 无 Runtime 引用 |
| `expert_runner.py` | 可能脱离热路径 — 仍 import `llm_service` |
| `serve.py` / `cli.py` / `dashboard.html` | 死 — main.py 不挂 |

### 7.4 调试残留

| 项 | 命中 |
|---|---|
| `pdb` / `breakpoint()` | 0 hit |
| `print()` | 14 个文件, 12 个在 `scripts/`/`cli.py`/`serve.py`/`sandbox.py` (脚本合理); `app/services/stt_finetune.py`、`app/config.py`、`app/seed.py` 需复核 |

### 7.5 死依赖 / 重复依赖

`requirements.txt` 50 行, `python-multipart==0.0.12` 与 `httpx==0.27.2` 重复列出 (L7、L22 vs L49)。`passlib[bcrypt]` 在 `app/api/auth.py:143` 自动 upgrade legacy SHA — 保留。

### 7.6 总风险评级

**HIGH** — 三条平行主路径 (legacy AgentRunner / 14-stage Homepage / 5-stage MedCodER) 同时挂在 `RuntimeConfig.execution_mode` 上, 默认仍 `legacy`; `agent_runner.py` (1047 LOC) + `orchestrator.py` (848 LOC) + `llm_service.py` (265 LOC) 三块 DEPRECATED 核心仍被 20+ import 链依赖, 迁移未完成, 任何"切新路径"都是大爆炸风险。

---

## 8. 前端差距

### 8.1 已具备

| 组件 | 路径 | 状态 |
|---|---|---|
| MedicalCodingPage | `pages/MedicalCodingPage.tsx:803` | 单 mode MedCodER |
| DiagnosisCard | `components/medical-coding/DiagnosisCard.tsx:136` | evidence + TopK + override |
| EvidenceHighlighter | `components/medical-coding/EvidenceHighlighter.tsx:99` | server-side fuzzy 回退 |
| TopKChips | `components/medical-coding/TopKChips.tsx:70` | 4 source 颜色 |
| Embed Review Panel | `components/embed/IcoderReviewPanel.tsx:226` | 5 action |
| Embed Evidence / Trace | `components/embed/IcoderEvidenceViewer.tsx:139` + `IcoderTraceViewer.tsx:95` | 完整 |

### 8.2 缺失

| 缺口 | 优先级 | 描述 |
|---|---|---|
| **MethodSwitcher** | **P0** | 无 MedCodER ↔ CLH ↔ Tree Search 切换 UI; `useMode`/`setMode` 状态缺失 |
| **MethodTraceViewer** | **P0** | 无 5-stage timeline 前端投影; run_trace 数据已记录 |
| **CodingMethodRegistry 客户端** | **P0** | 前端无 coding method 列表/选择 API |
| **Confidence Calibration UI** | P1 | MCP calibrate_confidence 已实现, 前端无显式 confidence 显示 |
| **Cross-method Compare View** | P1 | 无 MedCodER vs CLH 同 case 对比 |
| **Tree Search Visualization** | P2 | 待 Tree Search Agent 设计 |

### 8.3 写死 / 旧引用

| 问题 | 位置 | 状态 |
|---|---|---|
| **写死 MedCodER** | `MedicalCodingPage.tsx:272` `isMedcoderMode = result.mode === 'medcoder'` | 是, 唯一分支 |
| **CodingReviewWorkbenchPage 导入不存在组件** | `pages/CodingReviewWorkbenchPage.tsx:1229` | **HIGH 风险**, 导入 `../components/icoder/EvidenceViewer`、`HighRiskCodingPointPanel`、`RunTraceTimeline`、`HumanReviewHistoryTimeline`、`../services/icoderCodingReviewApi`、`../components/agent-console/AgentRuntimeConsole` — 该目录**不存在**, 路径无法编译/运行 |
| **homepage-coding-review 路由未删** | `App.tsx:81` `studio/agents/homepage-coding-review` → CodingReviewWorkbenchPage | 未删 |
| **homepage-coding-review 硬编码** | `CodingReviewWorkbenchPage.tsx:343` 顶部状态栏显示 `icoder/homepage-coding-review-agent@1.0.0` | 未改 |
| **homepage-coding-review 旧链接** | `EmbedDemoCodingReviewPage.tsx:125` | 未改 |

### 8.4 类型契约

`frontend/src/types/runtime.ts:45-72` 含 `ExtractedDiagnosis`/`CandidateCode`/`EvidenceSpan`, 与后端 `MedicalCodingOutputSchema` 字段对齐良好。**但 mode 枚举在 `runtime.ts:25` 仍是 `deepseek/prompt_llm/hybrid/no_repair/medcoder` 五 mode**, 缺 `code_like_humans` / `tree_search` / `evidence_first` / `rule_guided`。

---

## 9. 90 天迭代路线图

### Phase A: 立即修复 (Week 1-2, 2026-06-24 ~ 2026-07-07)

| 任务 | 目标 | 工时 | Owner |
|---|---|---|---|
| **A1. FAISS 重建** | `python scripts/build_medcoder_index.py` + `build_medcoder_icd9cm3_index.py` 跑通, 产物入 git LFS 或 S3, 加 README 写明 rebuild 命令 | 1 天 (含 build wall time 5h) | Backend |
| **A2. CodingReviewWorkbenchPage 编译修复** | 删除 `CodingReviewWorkbenchPage.tsx`, 路由改指真组件 (`MedicalCodingPage` 或新建 `WorkbenchPage`) | 0.5 天 | Frontend |
| **A3. homepage-coding-review 路由清理** | `App.tsx:81` 删除, 旧链接 2 处改指 medcoder-coding-review | 0.5 天 | Frontend |
| **A4. legacy .pyc 清理** | 删 `coding_schema.cpython-312.pyc` + `a2a_protocol.cpython-312.pyc` + 全 `__pycache__` 重建 | 0.5 天 | Backend |
| **A5. CI 修复 (集成测试不被跳过)** | ci.yml 拆 ci.yml (unit) + integration.yml (integration/regression/e2e) + e2e_medcoder.yml (4-variant ablation) | 1 天 | DevOps |
| **A6. data/medcoder 资产 gitignore** | 决定 faiss.index 是否入仓, 不入仓则需 build pipeline | 0.5 天 | Backend |
| **A7. coding_differentiation_kb 校验** | `metadata.py` 与 KB 文件 schema diff 检查 | 0.5 天 | Backend |

**Phase A 验收**: `pytest tests/` 全绿 + FAISS index 在线 + Workbench 编译通过 + homepage-coding-review 路由 0 hit。

---

### Phase B: Coding Method Runtime 骨架 (Week 3-6, 2026-07-08 ~ 2026-07-29)

| 任务 | 目标 | 工时 |
|---|---|---|
| **B1. CodingMethodRegistry 后端** | `app/icoder/coding_methods/` 新建, 类似 `experts/registry`, 注册 MedCodER/CLH/TreeSearch | 3 天 |
| **B2. RuntimeRunResult.mode 扩展** | 后端 mode 枚举加 `code_like_humans` / `tree_search` / `evidence_first` / `rule_guided`, HybridCodingAdapter 适配 | 3 天 |
| **B3. MethodSwitcher 前端组件** | `components/coding/MethodSwitcher.tsx`, UI 三选一下拉 + 当前 method badge | 2 天 |
| **B4. MethodTraceViewer 前端组件** | 接 run_trace API, 5-stage timeline + per-disease evidence chips | 3 天 |
| **B5. types/runtime.ts 扩展** | mode 枚举加 4 个新 method, 加 `MethodTrace` / `CodingMethodMeta` 类型 | 1 天 |
| **B6. MethodCompare e2e 脚本** | `scripts/e2e_coding_method_compare.py`, 同 case 跑多 method, 输出 F1 对比 | 2 天 |

**Phase B 验收**: 前端可见 Method 切换; MethodTrace 时间线显示; 4 method 跑通同 case 对比脚本。

---

### Phase C: Code Like Humans Agent (Week 7-10, 2026-07-30 ~ 2026-08-26)

| 任务 | 目标 | 工时 |
|---|---|---|
| **C1. evidence_extractor 真实现** | system_prompt + tool list + MCP handler `app/icoder/mcp/handlers/extract_evidence.py` + 单元测试 5+ | 4 天 |
| **C2. index_navigator 真实现** | 接 FAISS (待 A1 完成), tool `navigate(code_or_text) → List[Candidate]`, MCP handler + 5 测试 | 4 天 |
| **C3. tabular_validator 真实现** | system_prompt + 校验逻辑 (性别/年龄/合并症/手术编码) + tool + 5 测试 | 4 天 |
| **C4. code_reconciler 真实现** | system_prompt + 多源 evidence 收敛 + tool + 5 测试 | 4 天 |
| **C5. Orchestrator 多 Expert 编排** | Planner 支持 multi-expert coding scenario (4 expert 顺序/并行) | 5 天 |
| **C6. CLH end-to-end 测试** | 100 case 跑 CLH pipeline, F1@1 ≥ MedCodER prompt variant 基线 | 3 天 |
| **C7. CLH 前端 UI** | 4 expert 各自 evidence 显示 + cross-expert reconciliation 可视化 | 3 天 |

**Phase C 验收**: CLH pipeline 真接通; 4 expert 各自跑通; F1@1 ≥ prompt variant; 前端可见 4 expert trace。

---

### Phase D: 平台化 / Agent Hub (Week 11-13, 2026-08-27 ~ 2026-09-16)

| 任务 | 目标 | 工时 |
|---|---|---|
| **D1. Legacy 清理** | DELETE `app/services/agent_runner.py` + `app/agents/orchestrator.py` + `app/services/llm_service.py` + `app/api/runtime.py` + `official_agents/homepage_coding_review.py` + `official_agents/homepage-coding-review/` | 3 天 |
| **D2. 三轨合一** | `RuntimeConfig.execution_mode` 删除, 默认 `platform_runtime`, 唯一入口 `/api/runtime/*` | 2 天 |
| **D3. Tree Search Agent v0.1** | 概念验证, 接 MedCodER Stage 4 rerank 框架, beam search 5 candidate | 5 天 |
| **D4. ISV Agent Registry stub** | `app/icoder/agent_registry/isv.py`, 第三方 Agent 注册骨架 (Phase 4) | 3 天 |
| **D5. Agent Marketplace UI** | Agent 浏览/安装/发布/版本管理 (前端) | 5 天 |
| **D6. Coverage 报告** | `pytest-cov` 接 CI, 80% 阈值门 | 1 天 |
| **D7. DRG / Charge Compliance Agents v0.1** | 复用 CLH 模式, 接 `compliance_services/` 规则 | 5 天 |

**Phase D 验收**: Legacy 0 hit; Tree Search v0.1 跑通; Agent Marketplace 上线; 覆盖率 ≥ 80%; 1 个 DRG Agent 跑通。

---

## 10. 最终建议

### 10.1 立即行动 (本周)

1. **修 CodingReviewWorkbenchPage 编译** — 删 1229 LOC 死文件, 路由改指真组件。**阻塞前端编译, 优先级最高**。
2. **跑 FAISS rebuild** — 5h wall time 阻塞 retrieve variant 真实 F1 评估, Phase A 第一天就跑。
3. **CI 拆 3 workflow** — 当前 `--ignore=tests/integration` 跳过 95% 测试, 任何回归都不会在 PR gate 抓到。

### 10.2 30 天目标

- 前端可见 Method 切换 (MedCodER / CLH / Tree Search)
- Code Like Humans 4 agent 真接通 (system_prompt + MCP handler + test)
- Legacy 0 hit (删 5 个 DEPRECATED 文件)
- CI 跑全量测试, 95% 通过

### 10.3 90 天目标

- **Coding Method Runtime v1.0**: 5 method 全部跑通 + Method Trace UI + Method Compare e2e
- **Code Like Humans F1 ≥ MedCodER**: 在 icoder_201 fixture 上跑, F1@1 ≥ MedCodER full variant
- **Legacy 收口**: 三轨变一轨, 单一 Runtime 入口
- **Platform 化**: ISV Agent Registry + Marketplace + DRG Agent v1

### 10.4 战略对齐

战略方向 "Coding Method Runtime" 已**有骨架无肉**。Phase A 修阻塞 (FAISS + 编译 + CI); Phase B 补方法骨架 (registry + 切换 UI + trace viewer); Phase C 填 CLH 4 agent; Phase D 收口 legacy + 上 Tree Search + 平台化。

**最关键判断**: MedCodER M0+M1+M2 收口干净, 周边 legacy 才是真正阻塞 Coding Method Runtime 上线的瓶颈。Phase A 7 个任务是"代码就绪", Phase B+C 是"产品成型", Phase D 是"平台化"。90 天后, iCoDer 才能真正从"MedCodER Agent" 演进为 "Coding Method Runtime"。

---

**报告结束** | **审计人**: iCoDer Runtime 首席架构师 | **日期**: 2026-06-24