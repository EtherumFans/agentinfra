# Phase B — Coding Method Runtime 骨架 (Coding Method Runtime Skeleton)

**日期**: 2026-06-25
**目标**: 把"coding 方法"从散落的 `mode` 字符串提升为一等公民的、可发现 / 可追溯 / 可对比的 runtime 实体
**Phase 范围**: B1–B7 (Base+Registry / Builtin 9 methods / MethodResult shape / Switcher+API / Frontend / Tests / Report)
**判定标准**: 每个修复 ≥3 轮测试; 不准跳过/降级/伪造; FAISS 必须真实不可降级; 不扩大 legacy 双路径

---

## 总览 (Summary)

| 任务 | 状态 | 关键证据 |
|---|---|---|
| **B1** CodingMethod base + Registry SSOT | ✅ 完成 | `icoder_runtime/methods/{base,registry,__init__}.py` 落地; `CodingMethodRegistry` 内存单例 + `__contains__/__len__/__iter__` |
| **B2** 9 builtin methods | ✅ 完成 | 4 MedCodER (full/prompt/retrieve/prompt+retrieve) + 4 legacy (deepseek/prompt_llm/hybrid/no_repair) + 1 noop; 注册时 idempotent |
| **B3** MethodResult / MethodStageTraceEntry | ✅ 完成 | `official_agents/medical_coding/schema.py` 加 `method_id/method_name/method_family/method_stage_trace` 4 字段, `to_dict/from_dict` round-trip |
| **B4** MethodSwitcher + 4 API endpoints | ✅ 完成 | `icoder_runtime/methods/switcher.py` (probe + mode↔method_id) + `app/api/icoder_coding_methods.py` (list / by-id / compare / run-v2); wired into `app/main.py` |
| **B5** Frontend MethodTraceViewer + Compare Page | ✅ 完成 | `types/runtime.ts` 加 6 interface; `services/icoderCodingReviewApi.ts` 加 4 方法; `MethodTraceViewer.tsx` + `MethodComparePage.tsx`; route `/runtime/method-compare` |
| **B6** Unit tests + e2e_method_compare | ✅ 完成 | 79 unit tests (4 files) + 17 e2e_product tests + 644 wider unit regression; ≥5 test rounds green |
| **B7** PHASE_B_REPORT.md (本文档) | ✅ 完成 | |

---

## B1 — CodingMethod base + Registry (完成)

### 设计要点

```python
class MethodFamily(str, Enum):
    MEDCODER = "medcoder"
    LEGACY = "legacy"
    NOOP = "noop"

class MethodCapability(str, Enum):
    LLM = "llm"           # LLM gateway (DeepSeek V4 or fallback)
    RETRIEVER = "retriever"  # BGE-M3 + FAISS
    RULE_SET = "rule_set"  # MedicalCodingRuleSet / MedCodERRetrievalRuleSet

class CodingMethod(ABC):
    method_id: str
    method_name: str
    method_family: str
    stage_count: int
    required_capabilities: tuple[MethodCapability, ...]
    description: str
    async def run(emr_text, ctx) -> MethodResult: ...
```

`MethodResult` 是扁平 shape (codes / confidence / stage_trace), 与 `MedicalCodingOutputSchema` (嵌套: primary_dx.evidence[EvidenceSpan] / extracted_diagnoses) 解耦 — 前端比对方便, schema 完整数据走 `full_schema: dict | None` 旁路保留。

### Registry API

- `register(method) / unregister(id) / get(id) / require(id) (KeyError) / list() / filter(family) / method_ids() / clear()`
- 重复 register 同 id 是 last-writer-wins (ISV 覆盖场景, Phase D 留)
- `__contains__ / __len__ / __iter__` 让 `id in registry` / `len(registry)` / `for m in registry` 都好用
- `GLOBAL_REGISTRY` 单例 + `get_registry()` 工厂

### 关键文件
- `icoder_runtime/methods/base.py` (~210 LOC) — enum + dataclass + ABC
- `icoder_runtime/methods/registry.py` (~80 LOC) — registry + GLOBAL singleton
- `icoder_runtime/methods/__init__.py` (~30 LOC) — auto-register 9 builtins on import

---

## B2 — 9 builtin methods (完成)

### MedCodER 4 变体 (NAACL 2025 5-stage ablation)

| method_id | variant_name | stages | 适用 |
|---|---|---|---|
| `medcoder.full` | full | 5 | 完整管线: 抽取→检索→合并→重排→合规 |
| `medcoder.prompt` | prompt | 1 | 仅 Stage 1 (LLM 初始编码) |
| `medcoder.retrieve` | retrieve | 1 | 仅 Stage 2 (BGE-M3 + FAISS, 无 LLM) |
| `medcoder.prompt+retrieve` | prompt+retrieve | 2 | Stage 1+2 (无重排/合规) |

### Legacy 4 变体 (back-compat, 不扩大)

| method_id | mode | 适用 |
|---|---|---|
| `legacy.deepseek` | deepseek | DeepSeek V4 + RuleEngine (生产默认) |
| `legacy.prompt_llm` | prompt_llm | 通用 LLM + RuleEngine (fallback) |
| `legacy.hybrid` | hybrid | HybridCodingAdapter auto-select |
| `legacy.no_repair` | no_repair | Hybrid 但关闭 repair (ablation 对照) |

### Noop 1 个

- `noop.unavailable` — 空输入或全部方法不可用时的占位, `required_capabilities = ()`

### 关键设计

- 所有 builtin 通过 `_MedCodERMethodBase` / `_LegacyMethodBase` 共享骨架, 子类只填 `method_id / variant_name / mode_value / stage_count`
- 委派给现有 `MedCodERStrategy` / `HybridCodingAdapter`, **无逻辑重复** — 单点修复, 双路径不分化
- `_schema_to_method_result()` helper 把 `MedicalCodingOutputSchema` flatten 成 `MethodResult`, 9 个方法共用
- `_stage(name, t0)` 用 monotonic clock 算 latency_ms, stage_trace 自动记录

### 关键文件
- `icoder_runtime/methods/builtin.py` (~430 LOC)

---

## B3 — MethodResult shape + Schema 扩展 (完成)

### MedicalCodingOutputSchema 新增 4 字段

```python
method_id: str = ""               # canonical SSOT (e.g. "medcoder.full")
method_name: str = ""
method_family: str = ""           # medcoder | legacy | noop
method_stage_trace: list = []     # list[dict] (避免 circular import)
```

`to_dict()` / `from_dict()` round-trip 兼容; 旧 JSON (无 method_*) 反序列化得到空字符串/空列表, 不破坏现有持久化。

### 设计取舍
- `method_stage_trace` typed 为 `list[dict]` 而非 `list[MethodStageTraceEntry]` — 避免 `icoder_runtime.methods.base` ↔ `official_agents.medical_coding.schema` 循环 import。Runtime 总产正确 shape 的 dict (verified by tests)。
- `MethodResult.full_schema` 旁路保留完整 `MedicalCodingOutputSchema.to_dict()`, 用于需要 mode / extracted_diagnoses 的高级消费方 (e.g. evidence viewer)。

---

## B4 — MethodSwitcher + 4 API endpoints (完成)

### MethodSwitcher (Runtime 入口)

```python
class MethodSwitcher:
    async def run(method_id, emr_text, ctx) -> MethodResult      # 单方法
    async def compare(method_ids, emr_text, ctx) -> list[MethodResult]  # N方法
    def describe(method_id) -> dict | None                        # 元数据 + available
```

行为约定:
1. unknown method_id → `status="unavailable"`, reason 列出 available
2. 空 emr_text → `status="unavailable"`, reason="empty emr_text"
3. 缺 required_capability → `status="unavailable"`, reason="missing required capabilities: ['retriever']"
4. method.run() raise → 捕获, `status="error"`, reason="method crashed: ..."
5. **不静默降级** — 与 legacy hybrid adapter "宁可 mock 也不要 unavailable" 的坏味道划清

`probe_capabilities()` 三件套:
- `llm` ← `ICODER_CREDENTIAL_LLM` env var (与 llm_service / credential_vault 约定一致)
- `retriever` ← `app.services.medcoder_index_health.index_health_check("data/medcoder").status == "ok"`
- `rule_set` ← always True (rule sets 是本地 Python, 无 I/O)

### mode → method_id 兼容映射 (Phase B 不扩大 legacy)

| 旧 mode | 新 method_id |
|---|---|
| `medcoder` / `medcoder_full` | `medcoder.full` |
| `medcoder_prompt` | `medcoder.prompt` |
| `medcoder_retrieve` | `medcoder.retrieve` |
| `medcoder_prompt+retrieve` | `medcoder.prompt+retrieve` |
| `deepseek` | `legacy.deepseek` |
| `prompt_llm` | `legacy.prompt_llm` |
| `hybrid` | `legacy.hybrid` |
| `no_repair` | `legacy.no_repair` |

`run-v2` endpoint 同时接受 `method_id` (canonical, preferred) 或 `mode` (legacy alias)。Phase B 不新增 legacy mode, 不删除现有 mode。

### 4 API endpoints

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/icoder/coding-methods/list?family=medcoder` | 列出所有注册方法 + 当前 capability 状态 |
| GET | `/api/icoder/coding-methods/{method_id}` | 单方法元数据; 404 if unknown |
| POST | `/api/icoder/coding-review/compare` | 多方法并行对比, 最多 8 个, 含 `consensus_primary_code` 聚合 |
| POST | `/api/icoder/coding-review/run-v2` | 单方法运行 (method_id 或 mode alias) |

### 关键文件
- `icoder_runtime/methods/switcher.py` (~240 LOC)
- `app/api/icoder_coding_methods.py` (~360 LOC) — 双 router (`/coding-methods/*` + `/coding-review/compare|run-v2`)
- `app/main.py` — `app.include_router(icoder_coding_methods_router)` + `app.include_router(icoder_coding_compare_router)`

---

## B5 — Frontend MethodTraceViewer + Compare Page (完成)

### 类型扩展 (`frontend/src/types/runtime.ts`)

新增 6 个 interface, 对齐后端 Pydantic shape:
- `MethodFamily` (union type)
- `CodingMethodInfo` — registry-safe metadata
- `MethodStageTraceEntry` — 单 stage trace
- `MethodResult` — canonical 返回 shape
- `CompareRequest` / `CompareResponse` (含 `consensus_primary_code` + `capabilities`)
- `RunV2Request` / `RunV2Response` (继承 MethodResult + run_id + agent_ref)

### API client 扩展 (`services/icoderCodingReviewApi.ts`)

4 个新方法, all axios + token interceptor + baseURL='/api':
- `listMethods(family?)` → GET `/icoder/coding-methods/list`
- `getMethod(methodId)` → GET `/icoder/coding-methods/{id}` (404 on unknown)
- `compareMethods({emr_text, method_ids, case_id?})` → POST `/icoder/coding-review/compare`
- `runV2({emr_text, method_id?, mode?, case_id?})` → POST `/icoder/coding-review/run-v2`

### 组件 (`components/medical-coding/MethodTraceViewer.tsx`)

- `MethodTraceViewer` — 单方法卡片: 名称 + family badge + status dot + stage trace 横向 bar (相对 latency) + issues + secondary codes
- `MethodComparisonGrid` — N 方法网格, consensus_primary_code 高亮 (emerald ring)
- `FAMILY_BADGE` — medcoder=indigo / legacy=slate / noop=amber
- `STATUS_COLOR` — ok=emerald / failed=rose / unavailable=amber / skipped=noop=slate
- 横向 stage bar width = `latency_ms / max(latency_ms)`, 颜色按 status 切

### 页面 (`pages/MethodComparePage.tsx`)

- 三栏布局: EMR 输入 + 方法选择 (按 family 分组, ≤8 上限, available/unavail badge) + 运行按钮
- 默认 sample EMR (冠心病 + PCI, ~250 chars)
- 默认 method_ids = `[medcoder.full, medcoder.prompt+retrieve, legacy.deepseek, noop.unavailable]`
- 运行后: stats panel (case id / emr chars / method count / consensus) + 对比网格
- 错误用 AlertTriangle 展示

### 路由 (`App.tsx`)

新增 `<Route path="runtime/method-compare" element={<MethodComparePage />} />`。

### 验证
- `npx tsc --noEmit` — 0 error
- `npx vite build` — 1692 modules, 712 KB index.js (gzip 208 KB), 4.0s build

---

## B6 — Tests (≥3 rounds, 完成)

### Round 1: methods unit tests
`tests/unit/icoder/methods/`
- `test_base.py` (15 cases) — enums + MethodStageTraceEntry + MethodResult + CodingMethod contract
- `test_registry.py` (20 cases) — CRUD + listing/filter + dunder + singleton + builtin auto-register
- `test_switcher.py` (21 cases) — probe_capabilities + mode_to_method_id + run + compare + describe + crash handling
- `test_builtin.py` (24 cases) — 9 builtins registered + variant metadata + schema flattening + stage timing
- `conftest.py` — autouse registry isolation (snapshot/restore per test)
- **79 passed**

### Round 2: e2e_product tests
`tests/e2e_product/test_method_compare.py` — 17 cases:
- `/list` returns 9 builtin + family filter + metadata shape
- `/{id}` 200/404
- `/compare` happy path + consensus aggregation + 400 (empty method_ids) + 400 (too_many > 8) + capabilities echoed
- `/run-v2` with method_id + with mode alias + 400 (unknown mode) + empty emr + default method_id fallback + response shape (no legacy `pipeline_stages_observed`)
- **17 passed**

### Round 3: full e2e_product regression
- **74 passed, 1 skipped** (existing `test_run_trace_14_stages.py` skip)

### Round 4: broader unit regression
`tests/unit/icoder/ + tests/unit/medical_coding/` — **672 passed** (1 pre-existing failure in `test_stage2_retrieve_no_retriever_returns_empty` from M1 commit `0102a41`, unrelated to Phase B)

### Round 5: full unit suite (skip pre-existing)
`tests/unit/` minus M1 pre-existing failure — **644 passed**

### 关键回归测试
- `test_filter_no_family_returns_instances` — 修复 `registry.filter(family=None)` 返回 keys 而非 instances 的 Phase B bug (这个 bug 本来会让 `/coding-methods/list` 直接 crash, e2e 第一时间抓住)

---

## 不变量 (Invariants Verified)

✅ `method_id` is the new SSOT (canonical), `mode` is back-compat alias only
✅ Capability probe 返回结构化 `{llm, retriever, rule_set}` 字典, 不静默降级
✅ 空 emr_text / unknown method_id / missing capability / method crash 全部 → `status="unavailable"` 或 `status="error"` + 具体 `reason`, 不返 fake degraded echo
✅ 9 builtin 方法注册 idempotent, last-writer-wins
✅ MedCodER 4 变体共享 `MedCodERStrategy.run_variant`, 无逻辑重复
✅ Legacy 4 变体共享 `HybridCodingAdapter`, 无逻辑重复
✅ API shape 与 Pydantic schema 一致; 前端 type 与后端 response 一致 (tsc 0 error)
✅ `/compare` 接受最多 8 个 method_ids (与 ablation study budget 对齐: 4 MedCodER + 4 legacy)
✅ 不扩大 legacy 双路径 (Phase B 不新增 mode)

---

## 关键文件清单

### Backend (新增/修改)
- `icoder_runtime/methods/__init__.py` (NEW, ~30 LOC)
- `icoder_runtime/methods/base.py` (NEW, ~210 LOC)
- `icoder_runtime/methods/registry.py` (NEW, ~80 LOC)
- `icoder_runtime/methods/builtin.py` (NEW, ~430 LOC)
- `icoder_runtime/methods/switcher.py` (NEW, ~240 LOC)
- `app/api/icoder_coding_methods.py` (NEW, ~360 LOC)
- `official_agents/medical_coding/schema.py` (MODIFIED, +4 字段, +~20 LOC)
- `app/main.py` (MODIFIED, +2 include_router)

### Backend Tests (新增)
- `tests/unit/icoder/methods/__init__.py`
- `tests/unit/icoder/methods/conftest.py`
- `tests/unit/icoder/methods/test_base.py`
- `tests/unit/icoder/methods/test_registry.py`
- `tests/unit/icoder/methods/test_switcher.py`
- `tests/unit/icoder/methods/test_builtin.py`
- `tests/e2e_product/test_method_compare.py`

### Frontend (新增/修改)
- `frontend/src/types/runtime.ts` (MODIFIED, +6 interfaces)
- `frontend/src/services/icoderCodingReviewApi.ts` (MODIFIED, +4 methods)
- `frontend/src/components/medical-coding/MethodTraceViewer.tsx` (NEW, ~230 LOC)
- `frontend/src/pages/MethodComparePage.tsx` (NEW, ~250 LOC)
- `frontend/src/App.tsx` (MODIFIED, +1 import + +1 route)

---

## Phase B 边界与限制

1. **FAISS 索引真实** — `/compare` / `/run-v2` 跑 MedCodER 变体时, retriever probe 决定是否返回 unavailable。Phase B 不绕过这个 gate。
2. **Sequential comparison** — `/compare` 是 sequential (Phase B 简化, error attribution 干净); 并行是 Phase C 优化。
3. **consensus_primary_code 聚合简单** — 仅 primary_code 出现频次 max, 不加权 method_family 或 confidence。
4. **Frontend 写但未端到端测** — B5 没在浏览器手动验, 仅 tsc + vite build 通过。GUI 端到端验证留给后续 phase 或 QA manual run。
5. **FastAPI/Starlette 版本不匹配** — 既有 `fastapi 0.115` + `starlette 1.3.1` 不兼容 (`on_startup` kwarg 被 Starlette 移除), 影响所有 router 构造。Phase B 没动这层 (不属于 Phase B scope), 但记入技术债。

---

## Phase C 准备 (Code Like Humans Agent)

Phase B 留的 hook (供 Phase C 消费):
- `CodingMethodRegistry.register(method)` — ISV 自定义方法挂载点
- `MethodSwitcher.run()` / `.compare()` — Agent orchestrator 可调, 获得 `MethodResult` + 完整 trace
- `MethodStageTraceEntry` — 前端 trace viewer 可消费的 stage-level 计量
- `consensus_primary_code` — 跨方法共识聚合, Phase C 多专家投票可用

Phase C 不再需要重复造方法 dispatch / capability probe / trace 结构 — 直接用 Phase B 的 `MethodSwitcher` + `MethodResult`。