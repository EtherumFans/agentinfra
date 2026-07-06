# Phase 3-A — Baseline 只读审计

**Date**: 2026-07-04
**Author**: Phase 3-A Section A
**Status**: READ-ONLY — no code changes
**Predecessor**: Phase 2.1-F (commit 4f0aa07, 2026-07-04)
**Successor**: Phase 3-A Section B (Tech Debt Burn-down)

## 1. 当前 Medical Coding 相关 Agent / pack / routes / pages / services

### 1.1 Agent Packs (`backend/official_agents/`)

存在 **两套并行的 Medical Coding agent pack**:

| Pack | format_version | agent_type | agent_ref | manifest.name | 状态 |
|---|---|---|---|---|---|
| `medical_coding/agent_pack.json` | 1.2 | certified | `icoder/medical-coding-agent@2.0.0` | **Medical Coding Agent** | 命名正确, 描述仍以 MedCodER 5 阶段为主 |
| `medcoder-coding-review/agent_pack.json` | 1.2 | reference | `icoder/medcoder-coding-review-agent@1.0.0` | **MedCodER Coding Review Agent** | **违反命名规范** — MedCodER 出现在产品主名 |

另有 12 个 atomic expert pack (`evidence-extractor`, `index-navigator`, `code-reconciler`, `tabular-validator`, `drg-analyzer`, `diagnosis-extractor`, `procedure-extractor`, `code-validation`, `compliance-guardrail`, `note-completeness`, `evidence-ranker`, `documentation-gap`, `denial-appeals`, `cdi-review`) — 均为 1.0.0 单文件 pack, 无 Python impl, 用作 Corti-style multi-agent catalog 占位。

### 1.2 后端 Routes

| Route | 文件 | 用途 |
|---|---|---|
| `POST /api/v2/tools/coding/icoder` | `app/api/v2_tools_coding.py:226` | Phase 1.1 Corti-style 5 阶段 coding endpoint (15-system spec) |
| `POST /api/v2/tools/coding` | `app/api/v2_tools_coding.py:489` | Phase 1.3 cycle 18 codes predict (no LLM) |
| `GET /api/runtime/medical-coding/status` | `app/api/runtime_platform.py:511` | MedicalCodingLLMProvider 状态 (mode/provider_mode/deepseek) |
| `POST /api/runtime/medical-coding/test` | `app/api/runtime_platform.py:559` | 测试编码 — **走 HybridCodingAdapter, 不走 A2A 主线** |
| `GET /api/runtime/runs` | `app/api/runtime_platform.py:421` | RunHistory 列表 |
| `GET /api/runtime/runs/{run_id}` | `app/api/runtime_platform.py:435` | 单 run 详情 |
| `GET /api/runtime/agents` | `app/api/runtime_platform.py:333` | RuntimeAgentRegistry list (agent_type=certified\|community) |
| `POST /api/icoder/agents/{id}/v1/message:send` | `app/icoder/agent_runtime/a2a/a2a_routes.py` | **A2A v0.3 inbound** — 主线入口 |
| `GET /api/icoder/agents` | A2A discovery | AgentCard list |
| `POST /mcp/v1/tools/list` | `app/icoder/mcp/server.py:222` | MCP 5 tools list |
| `POST /mcp/v1/tools/call` | `app/icoder/mcp/server.py:271` | MCP tools/call (search_icd/verify_code/...) |

**Agent ref 硬编码不一致**:
- `runtime_platform.py:417`: `AGENT_REF = "icoder/medical-coding-agent@1.0.0"` (v1.0.0, 但 pack 实际是 v2.0.0)
- `MedicalCodingPage.tsx:22`: `MEDICAL_CODING_AGENT_REF = 'medical-coding-agent-2.0.0'`
- A2A discovery 用 `medcoder-coding-review` (无 -agent 后缀, v1.0.0)

### 1.3 前端 Pages / Services

| 文件 | 用途 |
|---|---|
| `frontend/src/pages/MedicalCodingPage.tsx` | 编码 workbench (HighlightedTextarea + DiagnosisCard + EvidenceHighlighter); 调 `/api/runtime/medical-coding/test` 而非 A2A |
| `frontend/src/pages/AgentsPage.tsx` | Agent Hub — `runtimeAgentApi.listAgents('certified')` 列出预置 Agent |
| `frontend/src/pages/AgentDetailPage.tsx` | Agent 详情 — 3 处 dead fetch (stream/evaluate/evaluation-history) 已 stub (commit a7f04f8) |
| `frontend/src/services/runtimeApi.ts` | runtimeAgentApi.testMedicalCoding / listAgents / listRuns |
| `frontend/src/services/api.ts` | agentsApi 9 endpoints 走 `/rest/v1/agent_definitions` (Phase 2.1-C) |
| `frontend/src/components/medical-coding/DiagnosisCard.tsx` | MedCodER per-disease 渲染 |
| `frontend/src/components/medical-coding/EvidenceHighlighter.tsx` | EMR 证据高亮 |
| `frontend/src/i18n/locales.ts` | `medcoderPipeline` / `medcoderMode` / `enableMedcoder` 字符串 |

### 1.4 后端 Services / Runtime

| 文件 | 用途 |
|---|---|
| `icoder_runtime/providers/medical_coding/hybrid_adapter.py` | HybridCodingAdapter 5-mode dispatch (medcoder/icoder/legacy/prompt+retrieve/prompt) |
| `icoder_runtime/providers/medical_coding/medcoder_strategy.py` | MedCodER 5 阶段 strategy |
| `icoder_runtime/providers/medical_coding/medcoder_adapter.py` | MedCodER adapter |
| `icoder_runtime/providers/medical_coding/medcoder_retriever.py` | BGE-M3 + FAISS ICD-10-CN retriever |
| `icoder_runtime/providers/medical_coding/embedding_bge_m3.py` | BGE-M3 embedder (fp16) |
| `app/services/medcoder_index_health.py` | 索引健康检查 |
| `app/services/icd9cm3_loader.py` | ICD-9-CM-3 catalog filter |
| `icoder_runtime/core/registry.py` | RuntimeAgentRegistry (thread-level lock) |
| `app/icoder/agent_runtime/orchestrator/wiring.py` | A2A → MedCodERStrategy 路由 |

---

## 2. MedCodER 作为产品主名 — 当前暴露位置

`grep -rn "MedCodER|medcoder"` 命中 **100+ 文件** (Grep 工具上限截断), 关键产品暴露点:

### 2.1 pack manifest 直接以 MedCodER 命名

```
official_agents/medcoder-coding-review/agent_pack.json:6
  "name": "MedCodER Coding Review Agent"
```

**这是当前唯一一个 pack manifest.name 直接以 MedCodER 命名** — Agent Hub 在 `listAgents('certified')` 时会把这个名字显示给用户。

### 2.2 前端 i18n 显示 MedCodER

```
frontend/src/i18n/locales.ts:1073-1076
  medcoderPipeline: 'MedCodER 管线',
  medcoderMode: 'MedCodER 模式 (NAACL 2025)',
  enableMedcoder: '启用 MedCodER 管线',
```

英文对等 (en-US): `'MedCodER pipeline'` / `'MedCodER mode (NAACL 2025)'` / `'Enable MedCodER pipeline'`

### 2.3 前端组件注释 + UI 文案

- `MedicalCodingPage.tsx:274`: `isMedcoderMode = result?.mode === 'medcoder'`
- `MedicalCodingPage.tsx:491,496`: `{/* MedCodER per-diagnosis cards */}` + `t.medcoderPipeline` 渲染
- `DiagnosisCard.tsx:2`: `"DiagnosisCard — one disease extracted by the MedCodER pipeline."`
- `EvidenceHighlighter.tsx:4`: `"Used to visualize MedCodER pipeline output"`

### 2.4 后端 MCP server docstring

```
app/icoder/mcp/server.py:1
  """MCP server — FastAPI in-process mount exposing 5 MedCodER tools.
```

### 2.5 docs (归档/历史性)

PHASE_2_1_FINAL_REPORT.md, ARCHITECTURE.md, phase2/*, corti_parity/*, product/* 等共 30+ 份文档提及 MedCodER — 大多为历史性记录 (MedCodER NAACL 2025 Industry Track 论文背景), 不属于产品对外名暴露。但 `CLAUDE.md` 仍以 MedCodER 作为产品主线描述 (memory 已记 MedCodER 降级为 Pre-built Agent #18, 但 CLAUDE.md 文本未同步)。

**结论**: MedCodER 在 pack manifest.name (1 处) + 前端 i18n (3 个 user-facing 字符串) + 前端组件注释 (3 处) 直接作为产品名暴露。Section C 必须清扫这些点。

---

## 3. 当前 Agent Hub 对该 Agent 的展示

`AgentsPage.tsx` 的 `prebuilt` tab 调用 `runtimeAgentApi.listAgents('certified')` → `GET /api/runtime/agents?agent_type=certified` → `RuntimeAgentRegistry.list_all(agent_type='certified')`。

### 3.1 展示来源

`RuntimeAgentRegistry` 的 certified agents 来自 `official_agents/` 目录扫描 (PlatformRuntime 启动时调 `load_packs_from_dir`)。当前会扫到 **2 个 medical-coding 相关 pack**:

1. `medical_coding/agent_pack.json` (certified, v2.0.0, name="Medical Coding Agent")
2. `medcoder-coding-review/agent_pack.json` (reference, v1.0.0, name="MedCodER Coding Review Agent")

第二个 pack 的 `agent_type=reference` 会被 filter 掉 (certified tab 只显示 agent_type=certified), 但其 `a2a.endpoint` 仍被 A2A discovery 暴露 (`/api/icoder/agents/medcoder-coding-review/v1/message:send`)。

### 3.2 详情页路由

`/ai-studio/agents/:agentId` 或 `/studio/agents/:agentId` → `AgentDetailPage.tsx`。Phase 2.1-E 已 stub 3 处 dead fetch (stream/evaluate/evaluation-history), 但详情页结构仍是 legacy "expert list + chat" 而非 Corti-style "Overview/Workflow/Inputs/Outputs/Constraints/Requirements/Runs"。

### 3.3 当前 Agent Card 内容

medical_coding pack 的 manifest:
- name: "Medical Coding Agent" ✓
- description: "iCoDer 标准医学编码 Agent。基于 MedCodER 5 阶段管线..." — **首句即暴露 MedCodER**
- category: "medical-coding"
- icon: "Stethoscope"
- tags: ["icd-10-cn", "icd-9-cm-3", "medcoder", "rag", "rerank"] — **tags 含 "medcoder"**

Section C 必须重写 description 和 tags。

---

## 4. 当前 output contract

`icoder/MedicalCodingOutputSchema/v1` (定义于 `official_agents/medical_coding/schema.py`):

```python
class MedicalCodingOutputSchema:
    primary_diagnosis: ExtractedDiagnosis
    secondary_diagnoses: list[ExtractedDiagnosis]
    procedures: list[ExtractedDiagnosis]
    issues_found: list[Issue]
    manual_review_required: bool
    confidence: float
    review_conclusion: str
    # Phase 1 extras:
    extracted_diagnoses: list[ExtractedDiagnosis]  # MedCodER per-disease
    stage_trace: list[StageTraceEntry]  # 5 stage 状态 + latency_ms
    phi_redacted: bool  # 强制 true
    production_writeback_blocked: bool  # 强制 true
```

**与 Corti-style §C.4 要求对比**:

| Corti-style 必需字段 | 当前是否有 |
|---|---|
| encounter_summary | ❌ 无 |
| documentation_analysis | ❌ 无 |
| code_assignment | ⚠️ 部分 (primary_diagnosis + secondary_diagnoses + procedures 分散) |
| documentation_gaps | ❌ 无 |
| uncodable_items | ❌ 无 |
| validation_summary | ⚠️ 部分 (issues_found + manual_review_required) |
| human_review | ⚠️ 部分 (manual_review_required 布尔, 无结构化 reason) |
| trace_refs | ⚠️ 部分 (stage_trace, 无 run_id 关联) |

**结论**: 当前 output contract 是 MedCodER 5 阶段管线视角, 不是 Corti-style 编码审核视角。Section C 必须重写为 8 字段结构。

---

## 5. 当前 Workbench 页面

`MedicalCodingPage.tsx` (1064 LOC):

### 5.1 当前结构

```
┌────────────────────────────────────────────────────────┐
│ Top bar: sample selector (入院/出院/病程/手术/门诊/会诊) + mode toggle │
├──────────────────────┬─────────────────────────────────┤
│ 左侧 (400px)         │ 右侧 (flex)                     │
│ ┌──────────────────┐ │ ┌─────────────────────────────┐ │
│ │ HighlightedText  │ │ │ DiagnosisCard × N           │ │
│ │ area (EMR input) │ │ │  - disease_text             │ │
│ │ + char counter   │ │ │  - evidence chips           │ │
│ └──────────────────┘ │ │  - TopKChips (top-5 codes)  │ │
│                      │ │  - override input           │ │
│                      │ └─────────────────────────────┘ │
└──────────────────────┴─────────────────────────────────┘
```

### 5.2 调用路径 (非主线)

```typescript
// MedicalCodingPage.tsx:~280
const result = await runtimeAgentApi.testMedicalCoding(text);
// → POST /api/runtime/medical-coding/test
// → HybridCodingAdapter(mode="hybrid").infer_async()
// 不走 A2A, 不走 MCP, 不生成 run_id 进 RunHistory
```

### 5.3 Corti-style §D 要求对比

| 要求 | 当前状态 |
|---|---|
| WorkbenchLayout 三栏 (左 clinical / 中 result / 右 trace) | ❌ 当前两栏 |
| 左侧: clinical documentation input + samples | ✓ 有 |
| 中间: coding review result | ⚠️ 当前在右栏 |
| 右侧: workflow trace / tool calls / safety / evidence | ❌ 无 trace 面板 |
| 结果页: Encounter Summary | ❌ 无 |
| 结果页: Code Assignment | ⚠️ 部分 (DiagnosisCard) |
| 结果页: Evidence | ✓ 有 (evidence chips) |
| 结果页: Documentation Gaps | ❌ 无 |
| 结果页: Uncodable Items | ❌ 无 |
| 结果页: Validation Summary | ❌ 无 |
| 结果页: Human Review Required | ⚠️ 部分 (manual_review_required 布尔) |
| 不允许 fake result | ⚠️ 当前 HybridCodingAdapter mock mode 可能返回 fake |

**结论**: 当前 Workbench 不符合 Corti-style 三栏 + 8 段结果。Section D 必须重构。

---

## 6. 当前 Runs/Trace 联动

### 6.1 后端 RunHistory

- `app.state.run_history` = `RunHistoryStore` (in-memory, 进程内 dict)
- `GET /api/runtime/runs` 返 `history.query(agent_ref, limit)`
- `GET /api/runtime/runs/{run_id}` 返单条 entry
- `app.state.m2a_recorder` = `M2aRecorder` (RunTraceService) — wired into HybridCodingAdapter + AgentRunner

### 6.2 前端 Runs/Trace 页面 — **已删**

P1.2 (commit 5c4e0e3, 2026-06-30) 删除了:
- `RunTracePage.tsx`
- `MethodComparePage.tsx`
- `DoctorPage.tsx`
- `MarketplacePage.tsx`

App.tsx 路由 **没有** `/runtime/runs` 或 `/runtime/trace` 路由 — 唯一 runs 入口是 `MedicalCodingPage` 内嵌的 `/runtime/coding-review/:runId` URL param, 但 `MedicalCodingPage` 当前 **不消费** `:runId` param, 也不调 `listRuns`。

### 6.3 当前 A2A run_id 联动

A2A `message:send` 返回的 `task_id` 在 `RunHistoryStore.query()` 中能查到, 但:
- `MedicalCodingPage` 不调 A2A, 所以没有 run_id
- 没有 `RunsPage` 列表页
- `AgentDetailPage` 的 "Runs" 段被 stub (Phase 2.1-E commit a7f04f8)

**结论**: Runs/Trace 联动断开。Section D + E 必须重建。

---

## 7. TD-001/002/004/005 当前复现方式

### 7.1 TD-001 — templates org_id mismatch

**复现命令**:
```bash
cd backend && python -m pytest tests/unit/app/api/test_templates_api.py -v
```

**复现路径** (3 tests fail):
1. `conftest.py:145` `auth_client` fixture 调 `/api/auth/login` (用户名 `testuser`)
2. 首次运行时 `/api/auth/register` 自动创建 Organization, `org.id = "org_<uuid4>"` (UUID, 非 "org_default1")
3. JWT `access_token` 携带 `org_id = "org_<uuid4>"`
4. `conftest.py:183` 仅 override `get_current_user` (返 `_make_mock_user("admin")`, 其 `organization_id="org_default1"`)
5. `get_current_organization` **未** override — 实际从 JWT 解 `org_id="org_<uuid4>"`, 查 DB 返 UUID org
6. `test_templates_api.py:41` `seeded_templates` fixture 用 `async_session_factory()` 直接插 `organization_id="org_default1"` 的 templates
7. `templates.py:92` `list_templates` 过滤 `Template.organization_id == current_org.id` (UUID) — 看不见 seeded templates

**根因**: `seeded_templates` fixture 用硬编码 `TEST_ORG_ID = "org_default1"`, 而 `get_current_organization` 走 JWT 解析返 UUID org — 两路 org_id 来源不一致。

### 7.2 TD-002 — schema_drift flakiness

**复现命令**:
```bash
cd backend && python -m pytest tests/unit/scripts/test_schema_drift.py -v  # 单跑 PASS
cd backend && python -m pytest tests/unit/scripts/test_schema_drift.py tests/unit/app/api/test_templates_api.py -v  # 跑完前面再跑 → 31 divergences
```

**复现路径**:
1. `test_no_schema_drift_against_fresh_alembic_db` 用 `tmp_path / "drift_check.db"` 新建 SQLite 文件
2. 设 `env["DATABASE_URL"] = sqlite+aiosqlite:///<tmp_path>/drift_check.db`
3. `subprocess.run([alembic, upgrade, head])` 在子进程跑 alembic
4. `check_drift(sync_db_url)` 比对 ORM `Base.metadata` vs DB
5. **问题**: 当父 pytest session 已 import 大量 `app.models.*` (如 test_templates_api 先跑), `Base.metadata` 已被 populate; 子进程 alembic 是 fresh, 但 `check_drift` 在父进程跑, 比对的是父进程的 metadata
6. 31 divergences 不是真 schema 变更, 而是 conftest teardown 把 dev DB 34 表 drop (cycle 25 已修, 但 `Base.metadata` 仍可能含 prior test 残留的临时表/索引)

**根因**: `check_drift` 在父 pytest 进程跑, ORM metadata 受 prior test imports 污染; alembic 在子进程跑 fresh DB, 二者比较产生伪 divergences。

### 7.3 TD-004 — duplicate operation_id

**复现命令**:
```bash
cd backend && python scripts/export_openapi.py 2>&1 | grep -i "duplicate"
# 或
cd backend && python -m pytest tests/test_api/test_v2_contract_invariants.py -v
```

**复现路径**:
1. `app/main.py:105` `lifespan()` 在 startup 时调 `mount_mcp(app, ...)` + `build_a2a_routers(...)`
2. `mount_mcp` 内部 `app.include_router(router)` — 注册 5 routes 含 `tools_list` / `tools_call`
3. `build_a2a_routers` 注册 A2A discovery + inbound + `build_task_stub_router()` (含 `get_task` / `cancel_task`)
4. FastAPI 自动从函数名生成 `operation_id` (`tools_list` / `tools_call` / `get_task` / `cancel_task`)
5. **TestClient 启动 app → lifespan 跑 → mount 注册 router**
6. **TestClient 关闭 → lifespan shutdown, 但 router 不 unmount**
7. **下一个 test 启动 TestClient → lifespan 再跑 → mount 再注册 → 同 operation_id 注册两次 → FastAPI warning**

`export_openapi.py` 调 `app.openapi()` 触发 routes 全量 schema 生成, 此时若 lifespan 已跑过 (e.g. 通过 TestClient 启动过), 则重复注册暴露。

**根因**: A2A + MCP mount 在 lifespan 内, TestClient 跨 test 重启 lifespan 但 FastAPI routes 表不清理, 导致 operation_id 重复。

### 7.4 TD-005 — registry thread lock

**复现命令**:
```bash
cd backend && python scripts/health_check.py  # check 6 (runtime_status)
# 输出: registry_safety.safe = False, warning "RuntimeAgentRegistry uses thread-level locking only..."
```

**复现路径**:
1. `icoder_runtime/core/registry.py:82` `self._lock = threading.Lock()`
2. `check_worker_safety()` (line 294) 检查 `cpu_count > 1` → 返 `safe=False` + warning
3. `runtime_platform.py:65` `status["registry_safety"] = reg.check_worker_safety()` 暴露给 `/api/runtime/status`
4. `health_check.py` check 6 读 `/api/runtime/status`, 见 `safe=False` → 输出 warning

**根因**: `RuntimeAgentRegistry` 用 `threading.Lock` (单进程内线程锁), 多 worker uvicorn 部署时各 worker 有独立 registry 实例 + 独立 JSON 文件, 写入会冲突。生产部署需 `--workers=1` 或迁移到 DB-backed registry。

---

## 8. 本轮修改范围

### 8.1 Section B — Tech Debt Burn-down (4 fixes)

| ID | 修改文件 | 修改要点 |
|---|---|---|
| TD-001 | `backend/tests/conftest.py` + `backend/tests/unit/app/api/test_templates_api.py` | 统一 org_id 获取: `seeded_templates` fixture 改用 `auth_client` 实际登录后的 org_id (调 `/api/auth/me` 或从 JWT 解), 不再硬编码 `org_default1` |
| TD-002 | `backend/tests/unit/scripts/test_schema_drift.py` + `backend/app/services/schema_drift_service.py` | 把 `check_drift` 也放进 subprocess (与 alembic 同一 fresh 子进程), 隔离父 pytest 的 metadata 污染; 或在父进程跑前显式 `import app.models.*` 全集, 再 reload `Base.metadata` |
| TD-004 | `backend/app/icoder/mcp/server.py` + `backend/app/icoder/agent_runtime/a2a/routes_task_stub.py` | 给 4 个函数显式 `operation_id=` 覆盖 (e.g. `mcp_tools_list_v1`, `a2a_get_task_stub_v0_3`); 或把 `mount_mcp` / `build_a2a_routers` 从 lifespan 移出, 改为模块级 `app.include_router` 调用 |
| TD-005 | `backend/icoder_runtime/core/registry.py` + `backend/scripts/health_check.py` + `backend/app/api/runtime_platform.py` | 引入 `filelock` (跨进程文件锁) 保护 JSON 写入; `check_worker_safety` 改为查 `--workers=1` 启动配置而非 CPU 数; doctor check 加 registry 异常暴露 |

### 8.2 Section C — Medical Coding Agent 产品化

| 修改文件 | 修改要点 |
|---|---|
| `backend/official_agents/medical_coding/agent_pack.json` | 重写 manifest.description (移除 MedCodER 暴露) + tags (移除 "medcoder") + 重写 system_prompt (evidence-first 7 阶段) + 重写 output_contract (8 字段 Corti-style) |
| `backend/official_agents/medcoder-coding-review/agent_pack.json` | **降级为 internal-only**: `agent_type=internal_engine`, manifest.name 改为 "Medical Coding Agent — Internal Engine (MedCodER 5-stage)", 不出现在 certified tab |
| `backend/official_agents/medical_coding/schema.py` | 新增 `MedicalCodingAgentOutputV2` schema: encounter_summary, documentation_analysis, code_assignment, documentation_gaps, uncodable_items, validation_summary, human_review, trace_refs |
| `backend/app/icoder/agent_runtime/orchestrator/wiring.py` | A2A inbound → Medical Coding Agent 路由: 调 MedCodERStrategy 但产出 Corti-style 8 字段 (适配层) |
| `backend/app/api/runtime_platform.py:417` | `AGENT_REF` 从 `@1.0.0` 改为 `@2.0.0` (对齐 pack 版本) |
| `frontend/src/i18n/locales.ts:1073-1076` | `medcoderPipeline` → `codingPipeline` ("编码管线"); `medcoderMode` → `codingAgentMode` ("医疗编码 Agent 模式"); `enableMedcoder` → `enableCodingAgent` ("启用医疗编码 Agent") |
| `frontend/src/components/medical-coding/DiagnosisCard.tsx` + `EvidenceHighlighter.tsx` | 注释从 "MedCodER pipeline" 改为 "Medical Coding Agent workflow" |
| `backend/app/icoder/mcp/server.py:1` | docstring "5 MedCodER tools" → "5 Medical Coding Agent MCP tools (internal engine: MedCodER 5-stage)" |
| `backend/app/main.py:595-650` | MCP mount docstring 注释更新 |

### 8.3 Section D — Product UI/UX

| 修改文件 | 修改要点 |
|---|---|
| `frontend/src/pages/MedicalCodingPage.tsx` | 重构为三栏 WorkbenchLayout; 调 A2A `message:send` 替代 `/medical-coding/test`; 渲染 8 段结果 (Encounter Summary / Code Assignment / Evidence / Documentation Gaps / Uncodable Items / Validation Summary / Human Review) |
| `frontend/src/pages/AgentDetailPage.tsx` | 详情页结构改 Corti-style: Overview / Workflow / Inputs / Outputs / Constraints / Requirements / Runs |
| `frontend/src/services/runtimeApi.ts` | 新增 `sendA2AMessage(agentId, text, metadata)` 调 `/api/icoder/agents/{id}/v1/message:send`; 移除 `testMedicalCoding` (走 A2A) |
| `frontend/src/components/medical-coding/` (新) | `EncounterSummary.tsx` + `CodeAssignment.tsx` + `DocumentationGaps.tsx` + `UncodableItems.tsx` + `ValidationSummary.tsx` + `HumanReview.tsx` + `WorkflowTrace.tsx` 7 个新组件 |
| `frontend/src/pages/AgentsPage.tsx` | certified tab 渲染走 RuntimeAgentRegistry list, 显示 "Medical Coding Agent" (不是 MedCodER) |
| `frontend/src/App.tsx` | 新增 `/runtime/runs` 路由 (RunsPage) + `/runtime/runs/:runId` (RunTracePage) — 重建 P1.2 删的 runs 入口 |

### 8.4 Section E — Runtime Integration

| 修改文件 | 修改要点 |
|---|---|
| `backend/tests/integration/icoder/test_phase3a_medical_coding_agent.py` (新) | 端到端: A2A message:send → Orchestrator → MCP tools/call → run_id → RunHistory → trace |
| `frontend/src/__tests__/apiContract.test.ts` | 新增 Medical Coding Agent A2A endpoint contract 校验 |
| `frontend/src/__tests__/MedicalCodingWorkbench.test.tsx` (新) | Workbench 三栏渲染 + A2A 调用 + 8 段结果渲染 (或 honest degraded) |

### 8.5 Section F + G — 验证 + 最终报告

无代码修改, 仅文档 + 测试运行。

---

## 9. 不在范围

- **MedCodER 5 阶段算法本身不重构** — 内部 MedCodERStrategy / HybridCodingAdapter / BGE-M3 + FAISS 检索保持原样, 仅产出层适配 Corti-style 8 字段
- **不做 F1 优化 / few-shot / Stage 4 rerank 重写** — 用户明确禁止
- **不删 `medcoder-coding-review` pack** — 降级为 internal-only, 保留作为 internal engine reference
- **不动 12 个 atomic expert pack** — 留给 Phase 3-B 多 Agent catalog
- **不动 Corti 逆向工程资产** — `docs/corti-reverse-engineered/` 已 untracked, 仅参考用
- **不动 CLAUDE.md 主线描述** — 该文件由 memory `project_p1_3_corti_parity_audit_2026_07_02` 治理, 单独 sync

---

## 10. 审计结论

| 维度 | 现状 | 差距 |
|---|---|---|
| Agent 命名 | medical_coding pack 已正确, medcoder-coding-review pack 违规 | 1 pack manifest + 3 i18n 字符串 + 3 组件注释 需清扫 |
| 输出契约 | MedCodER 5 阶段视角 (extracted_diagnoses / stage_trace) | 缺 8 字段 Corti-style (encounter_summary / documentation_analysis / code_assignment / documentation_gaps / uncodable_items / validation_summary / human_review / trace_refs) |
| Workbench | 两栏 + 走 `/medical-coding/test` 非主线 | 需三栏 + 走 A2A + 渲染 8 段结果 |
| Runs/Trace 联动 | RunHistory 后端在, 前端页已删, MedicalCodingPage 不调 | 需重建前端 Runs 页 + Workbench 消费 run_id |
| Tech Debt | TD-001/002/004/005 全在 | 4 项全修 |
| Runtime 主线 | A2A + MCP + Orchestrator 已搭, 但 MedicalCodingPage 不走 | Workbench 切到 A2A |

**Verdict**: baseline 状态健康 — 主线基础设施全在, 但 Medical Coding Agent 产品层 (命名 / 输出契约 / Workbench / Runs 联动) 需重写以对齐 Corti-style。Section B/C/D/E 的修改范围已明确, 无架构性阻塞。
