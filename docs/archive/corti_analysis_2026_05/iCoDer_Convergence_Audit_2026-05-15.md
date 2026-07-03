# iCoDer 收敛审计报告（更新版）

**日期**: 2026-05-15
**版本**: V0.4-dev
**审计方式**: 全量代码阅读（非文档推断），覆盖 backend/app/api/*、backend/app/services/*、backend/app/agents/**、backend/app/models/*、backend/app/schemas/*、frontend/src/pages/*、frontend/src/services/*
**上版审计**: 2026-05-11（`iCoDer_Convergence_Audit_2026-05-11.md`）

---

## 2026-05-15 已修复问题（本轮代码修改）

| # | 问题 | 改动文件 | 修复摘要 |
|---|------|---------|---------|
| N1 | SSE Manager done 后心跳永不停止 | `services/sse_manager.py` | done 事件后调用 `stop_event.set()`，移除无限心跳循环 |
| N2 | ReviewResponse DB 加载丢失 candidates/evidences | `api/reviews.py` | `_build_review_response` 改为 async，无 pipeline_result 时从 DB 查询关联表 |
| N3 | GoldCase 缺 PUT 更新端点 | `api/gold_cases.py` | 新增 `PUT /api/gold-cases/{case_id}`，支持部分更新 |
| N5 | evaluation batch 存根 + 3 个硬编码指标 | `api/evaluation.py` | batch 端点重写为独立实现；missing_code_recall/unsupported_code_precision/documentation_gap_recall 从实际 gold case 数据计算 |
| N6 | usage.py credits/响应时间为硬编码常数 | `api/usage.py` | credits_used 从 Transaction 表实数聚合；avg_response_time_ms 从 CodingReview 表查询 |
| N7 | OAuthToken 不继承 TimestampMixin | `models/oauth.py` | OAuthToken 改为继承 TimestampMixin，移除手动 id/created_at 定义 |
| N11 | RuleLibrariesPage 创建规则仅存本地 state | `api/rules.py` + `services/rule_engine.py` + `api.ts` + `RuleLibrariesPage.tsx` | 后端新增 `POST /api/rules` 端点 + `add_custom_rule()`；前端改为调用后端保存 |
| P1-6 | Vite `/api` 代理拦截 `/api-clients` 前端路由 | `vite.config.ts` | proxy bypass 函数排除 `/api-clients` 路径 |

---

## 变更摘要：5月11日→5月15日

本次审计基于对全部源代码的直接阅读，而非依赖历史文档。发现原5月11日审计描述的多个 P1 问题在当前**工作区（未提交）**中已有实质性修复，但**已提交代码（HEAD at eebdb47）**中仍然存在。

| 层面 | 已提交 (HEAD) | 工作区 (未提交) | 变化规模 |
|------|-------------|----------------|---------|
| `agent_runner.py` | 0 处 Runtime 调用 | 全面集成 Runtime（每路径创建实例、状态转换、guard/guard_post、审计、超时检查） | +280 行 |
| `orchestrator.py` | 有限 Runtime 集成 | 补齐 Timeline Expert、临床分诊、证据排序、不一致分析、置信度校准、推理报告；更多 guard_post 调用 | +395 行 |
| `runtime.py` | 基础实现 | 新增 6 条 guard_post 规则、输出拦截词表；ARCHIVED 可作为中间状态 | +297 行 |
| `api/runtime.py` | 基础实现 | 新增审核摘要端点、人工审核决策集成 | +160 行 |

---

## 一、P1 问题状态更新

### P1-1: WebSocket STT 不可用

**原状态**: /ws 端点返回 426 Upgrade Required
**当前状态**: ⚠️ **部分修复，待验证**

代码证据：
- `vite.config.ts` 中有代理配置变更（工作区修改）
- `websocket.py` 的 STT WebSocket 实现了三种回退链：FunASR Paraformer → openai-whisper → Google Web Speech API
- `SpeechToTextPage.tsx` 和 `EmbeddedAssistantPage.tsx` 都通过 WebSocket 连接 `ws://host:8001/ws/speech-to-text`

剩余风险：FunASR Paraformer、whisper、speech_recognition 均为可选导入，若全部缺失则 STT 完全不可用。imageio_ffmpeg 导入失败仅警告不阻塞。

**判定**: 仍为 P1，需实际启动服务验证 WebSocket 升级是否正常。

---

### P1-2: Runtime 安全框架大面积空洞

**原状态**: guard() 仅 1 处调用，guard_post() 调用 0 次，DUC 仅 1 个高危操作有门控
**当前状态 (工作区)**: ✅ **实质性修复**

代码证据（orchestrator.py 工作区版本）：
- `rt.guard_post()` 当前有 **5 处调用**：evidence_result、diag_result、proc_result、drg_result、report_result
- `rt.guard()` 当前有 **3 处调用**：flag_unsupported_code、resolve_evidence_conflict、finalize_principal_diagnosis
- `rt.check_timeout()` 当前有 **5 处调用**：每个关键状态转换前
- `runtime.py` 的 `ToolGate.post_check()` 新增 6 条统一 guard_post 规则：output_non_empty、code_candidates_valid、evidence_exists、drg_structure_valid、report_non_empty、high_risk_output_blocked
- OUTPUT 拦截词：处方、建议用药、手术方案、剂量

仍缺失：INTELLIGENT_PIPELINE 路径中无 Runtime（见 P2-4）。

**判定**: P1-2 在工作区代码中已从"大面积空洞"改善为"基本覆盖"。但未提交。

---

### P1-3: AgentRunner 完全绕过 Runtime

**原状态**: AgentRunner 不创建任何 DeterministicRuntime 实例
**当前状态 (工作区)**: ✅ **已修复**

代码证据（agent_runner.py 工作区版本，第 54 行注释）：
> "Every execution path creates a DeterministicRuntime instance."

实际实现：
- `run()` 方法：创建 `AR-{uuid}` Runtime，INGESTED → CONTEXT_READY → ... → ARCHIVED
- `stream()` 方法：创建 `ARS-{uuid}` Runtime，同样的状态转换链
- 三种路由策略（single_expert、fixed_order、llm_plan）全部有 Runtime 门控
- 每个 expert 调用前后有 `rt.guard()` 和 `rt.guard_post()`
- 执行完成后调用 `rt.flush_to_db(db)` 持久化
- 返回结果包含 `run_id` 和 `runtime_state`

**判定**: P1-3 在工作区代码中已修复。但未提交。

---

### P1-4: Orchestrator 跳过 5 个中间状态

**原状态**: 仅 4/12 状态被使用
**当前状态 (工作区)**: ✅ **已修复**

代码证据（orchestrator.py 工作区版本，实际状态转换序列）：

```
INGESTED → CONTEXT_READY → FACTS_EXTRACTED → CANDIDATES_READY → RULES_VALIDATED
→ RISK_IDENTIFIED → REVIEW_REQUIRED → DECISION_CONFIRMED → ARCHIVED
```

9 个主要状态全部使用。仍未被主动使用的 3 个状态：DOC_FEEDBACK_READY（文档反馈）、WRITEBACK_PENDING（写回待定）、WRITTEN_BACK（已写回）— 这些是为 HIS/EMR 集成预留的，当前阶段合理。

**判定**: P1-4 在工作区代码中已修复。但未提交。

---

### P1-5: 语义记忆数据损坏

**原状态**: save/recall 数据格式契约断裂
**当前状态**: ✅ **已修复（已提交）**

已于 commit `375bfc8` 中修复：`fix: P0-3 — Memory semantic search (embedding overwrite bug)`

当前 `memory_expert.py` 代码状态：
- `save()` 统一使用 `{"facts": [...], "_embedding": [...]}` 格式
- `recall()` 统一按 dict 格式读取 key_facts，带关键词回退
- 嵌入模型：paraphrase-multilingual-MiniLM-L12-v2（~80MB，懒加载）
- 30 天时间窗口 + 0.3 重要性阈值

**判定**: 已修复。

---

### P1-6: 路由冲突 /api-clients 被 Vite 代理拦截

**原状态**: Vite proxy `'^/api'` 规则太宽泛
**当前状态**: 待确认

`vite.config.ts` 在工作区有修改，APIClientsPage.tsx 是完整功能页面（调用 `oauthApi.list()` 等）。需实际启动前端确认路由是否正常。

**判定**: 仍为 P1，待验证。

---

## 二、P2 问题状态更新

### P2-1: 4/11 Expert 未在固定 Pipeline 中连线

**原状态**: CDI/Denial/Audit/HCC 仅在 intelligent_pipeline 中可达
**当前状态**: ⚠️ **架构设计，非 bug**

代码证据：
- 固定 pipeline（`run_pipeline()`）现在调用 **10 个处理步骤**（含新加的 Timeline Reconstruction 和 Clinical Triage），但不包含 CDI/Denial/Audit/HCC
- 这 4 个专家在 `_execute_step()` 中完整实现，且被 `run_intelligent_pipeline()` 的 LLM 规划器按需调用
- 这 4 个专家的语义是"增强分析"而非"核心编码流程"：CDI（临床文档改进）是审核后优化，Denial（拒付管理）是支付场景，Audit（审计追踪）是合规需求，HCC（风险调整）是美国医保场景

**判定**: 降级为 P3。当前设计合理——固定 pipeline 覆盖核心编码流程，intelligent pipeline 按需启用扩展专家。可考虑在固定 pipeline 尾部分阶段添加（如 Audit 在 ARCHIVED 前自动运行）。

---

### P2-2: A2A 协议未启用

**原状态**: register_agent() 调用 0 次
**当前状态**: ⚠️ **部分改善**

已于 commit `16693c0` 修复：`fix: A2A registration — all 30 experts (was only 8)`

当前代码状态：
- `main.py` 启动时调用 `a2a_registry.register_all_experts()`
- `experts.py` 中 A2A 端点完整：`.well-known/agent.json`、agents 列表、task CRUD、chain 执行
- `register_all_experts()` 有 30 个硬编码专家，URL 硬编码为 `localhost:8000`
- `coordinate()` 方法创建协调计划但不实际执行子任务（返回计划而非执行）

**判定**: 仍为 P2。A2A 注册已工作，但 `coordinate()` 的并行执行是骨架，且 localhost:8000 硬编码需改为可配置。

---

### P2-3: Orchestrator 与 AgentRunner 双轨执行

**原状态**: 两条独立执行路径，输出格式不同
**当前状态**: ⚠️ **有所改善但仍存在**

工作区改善：
- AgentRunner 和 Orchestrator 现在都使用 Runtime（统一的 `DeterministicRuntime` + `CaseState` 枚举）
- 两者都返回 `run_id` 和 `runtime_state` 字段
- 输出格式仍不同：Orchestrator 返回 `CodingReview` 结构化数据，AgentRunner 返回自由文本 `output` 字段

**判定**: 仍为 P2。统一抽象是中长期架构目标，当前 Runtime 统一已消除最大的安全不一致。

---

### P2-4: intelligent_pipeline 无 Runtime

**原状态**: run_intelligent_pipeline() 完全无安全护栏
**当前状态**: ❌ **未修复**

代码证据（orchestrator.py 工作区版本）：
- `run_intelligent_pipeline()` 仍然不创建 Runtime 实例
- `_execute_step()` 直接调用 expert，无任何 `rt.transition()` 或 `rt.guard()`
- 但 LLM 规划器失败时会回退到 `run_pipeline()`（有 Runtime）

**判定**: 仍为 P2。intelligent_pipeline 允许 LLM 动态决定跳过哪些专家，这使得 Runtime 按固定序列的状态机模型难以直接套用。需要设计一个"动态状态机"模式，或限制 intelligent_pipeline 仅用于非关键场景。

---

### P2-5: 前端分页/搜索/计算器等 UI 装饰性元素

**原状态**: 多处按钮无 onClick
**当前状态**: ✅ **已修复**

已于 commit `83fc16c` 修复：`fix: wire up decorative UI elements — search, calculator, pagination, support/privacy links`

**判定**: 已修复。

---

### P2-6: CodingWorkbench 导出按钮无功能

**原状态**: 点击无效
**当前状态**: ⚠️ **仍有硬编码/模拟行为**

CodingWorkbenchPage 仍有部分 mock 行为（如 report_markdown 的 mock 数据），但导出功能已有 Markdown/HTML 双格式支持。实际取决于后端数据是否完整返回。

**判定**: 降级为 P3。

---

### P2-7: TicketPage 为纯占位页

**原状态**: 无任何后端集成
**当前状态**: 未变化

TicketsPage.tsx 仍为 4 行 JSX，指向外部 URL。

**判定**: 设计为外部系统入口，非 bug。

---

### P2-8: 后端测试不稳定

**原状态**: test_oauth.py 和 test_code_dictionary.py 可能失败
**当前状态**: 待验证

两个测试文件在工作区有修改。实际运行状态未知。

**判定**: 仍为 P2。

---

### P2-9: 无数据库迁移脚本

**原状态**: Alembic versions/ 为空
**当前状态**: 未变化

**判定**: 仍为 P2。SQLite 在开发阶段可用 `create_all`，但生产迁移必须 Alembic。

---

### P2-10: LLM token 消耗无监控

**原状态**: Agent 聊天无 token 计数
**当前状态**: 未变化

`llm_service.py` 的 `chat()` 和 `chat_stream()` 方法返回 token 使用数据，但 `agent_runner.py` 和前端均未收集/展示。

**判定**: 仍为 P2。

---

## 三、本次深度代码审计新发现的问题

以下问题在 5月11日审计中未被记录，通过本次全量代码阅读发现。

### 新 P2 问题

| # | 问题 | 影响 | 根因 |
|---|------|------|------|
| N2 | ✅ **已修复** — ReviewResponse DB 加载丢失关联数据 | `reviews.py` _build_review_response 改为 async，查询 candidates/evidences 表 |
| N3 | ✅ **已修复** — GoldCase 缺少更新端点 | `gold_cases.py` 新增 PUT 端点 |
| N4 | **10/18 数据模型无 Pydantic Schema** — TeamMember、TeamInvite、ApiKey、Transaction、OAuthClient、OAuthToken、Expert、McpServer、Agent、ConversationMemory 均缺少专用 schema | API 响应未经 Pydantic 验证 | 快速原型阶段遗留 |
| N5 | ✅ **已修复** — evaluation.py batch 端点存根 + 3 个硬编码指标 | `evaluation.py` batch 端点重写，指标从实际数据计算 |
| N6 | ✅ **已修复** — usage.py credits/响应时间硬编码 | `usage.py` 从 Transaction 和 CodingReview 表实际查询 |
| N7 | ✅ **已修复** — OAuthToken 模型不一致 | `oauth.py` OAuthToken 继承 TimestampMixin |
| N8 | **前端多处 mock 数据** — MedicalCodingPage 流式输出为 setTimeout 模拟；FactExtractionPage 成本每次硬编码 +0.000001；BillingPage addCredits 固定 50 元；SettingsPage 护栏切换无后端持久化 | 用户体验不连贯 | 快速原型 |
| N9 | **stt_service.py 全局可变状态** — `_stt_model`、`_stt_streaming_model`、`_term_index_loaded` 为模块级变量，非线程安全 | 并发 STT 请求可能冲突 | 未使用锁保护 |
| N10 | **DRG 分组器仅基于手术代码** — `drg_grouper.py` 的 `group_drg()` 完全不使用诊断代码进行分组 | 内科 DRG 分组不准确 | 实现简化 |
| N11 | ✅ **已修复** — RuleLibrariesPage 规则创建无后端集成 | `rules.py` POST 端点 + `rule_engine.py` add_custom_rule + 前端调用 |
| N12 | **前端组件/单元测试零覆盖** — vitest 和 @testing-library/react 已安装但无任何测试文件 | 回归风险 | 未开始编写 |

### 架构观察

1. **单体 FastAPI + SQLite**: 当前架构适合单机部署和 pilot 验证。生产环境需 PostgreSQL + Redis + 水平扩展。
2. **单例模式普遍使用**: 32 个服务几乎全部是模块级单例（`xxx = Xxx()`），在单进程下工作正常，但多 worker 部署时需重构。
3. **无异步任务队列**: `task_manager.py` 是内存实现，注释标注 "Production: replace with Redis + Celery/ARQ"。
4. **WebRTC 缺失**: 实时音视频流式 STT 需要 WebRTC，当前仅 WebSocket 文本/音频数据。
5. **6 个内部 Schema 文件未导出**: `timeline.py`、`principal_diagnosis_reasoning.py`、`evidence_ranking.py`、`disagreement_reasoning.py`、`confidence.py`、`case_reasoning.py` 在 `schemas/__init__.py` 中未被导出，但被内部服务使用——这是合理的设计（内部 schema），但需文档说明。

---

## 四、更新后的执行路径图

```
                       ┌─────────────────────────────────┐
                       │         Frontend Entry           │
                       └──────────────┬──────────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 │                    │                    │
                 ▼                    ▼                    ▼
 POST /api/reviews         POST /api/agents/:id/run    POST /api/agents/:id/stream
 (编码审核)                 (Agent 聊天)                (Agent 流式聊天)
                 │                    │                    │
                 ▼                    ▼                    ▼
      ┌──────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
      │ AgentOrchestrator │  │    AgentRunner        │  │    AgentRunner        │
      │ run_pipeline()    │  │    .run()              │  │    .stream()          │
      └────────┬─────────┘  └──────────┬───────────┘  └──────────┬───────────┘
               │                       │                          │
      ┌────────┴─────────┐  ┌──────────┴───────────┐  ┌──────────┴───────────┐
      │ ✅ Runtime 创建   │  │ ✅ Runtime 创建 (新)   │  │ ✅ Runtime 创建 (新)   │
      │ ✅ 9 状态全流转   │  │ ✅ INGESTED→ARCHIVED  │  │ ✅ INGESTED→ARCHIVED  │
      │ ✅ guard() 3处    │  │ ✅ guard() 门控       │  │ ✅ guard() 门控       │
      │ ✅ guard_post 5处  │  │ ✅ guard_post() 输出  │  │ ✅ guard_post() 输出  │
      │ ✅ check_timeout 5处│  │ ✅ check_timeout()   │  │ ✅ check_timeout()   │
      │ ✅ audit chain    │  │ ✅ audit chain (新)   │  │ ✅ audit chain (新)   │
      │ ✅ flush_to_db    │  │ ✅ flush_to_db (新)   │  │ ✅ flush_to_db (新)   │
      └────────┬─────────┘  └──────────┬───────────┘  └──────────┬───────────┘
               │                       │                          │
      ┌────────┴─────────┐  ┌──────────┴───────────┐  ┌──────────┴───────────┐
      │ 10 步固定 Pipeline│  │ LLM 规划 →           │  │ LLM 规划 →           │
      │ + 推理报告        │  │ expert_runner.run()  │  │ expert_runner.stream │
      │                   │  │   (逐个调用 expert)  │  │   (逐个调用 expert)  │
      │ 1. Guardrails     │  │                       │  │                       │
      │ 2. Evidence       │  │ Routing:              │  │ Routing:              │
      │ 3. Timeline (新)  │  │ - single_expert       │  │ - single_expert       │
      │ 4. ClinicalTriage │  │ - fixed_order         │  │ - fixed_order         │
      │ 5. Diagnosis      │  │ - llm_plan (default)  │  │ - llm_plan (default)  │
      │ 6. Procedure      │  └───────────────────────┘  └───────────────────────┘
      │ 7. Homepage       │
      │ 8. Evidence Verify │    ┌──────────────────────────┐
      │ 9. Ranking/Disagree│    │ run_intelligent_pipeline  │
      │ 10. Confidence     │    │ ❌ 仍无 Runtime           │
      │ 11. DRG + DocGap   │    │ ❌ 仍无 Guardrails        │
      │ 12. Report +Reason │    └──────────────────────────┘
      │ 13. Guardrails out │
      └────────────────────┘

图例: ✅ = 已集成 (工作区)  ⚠️ = 部分集成  ❌ = 完全缺失
注: 标注"(新)"的功能仅在工作区代码中存在，尚未提交
```

---

## 五、全栈收敛度量

### 后端 API 层

| 指标 | 数值 |
|------|------|
| 总端点数 | ~102 |
| 完全实现 | ~96 (94%) |
| 部分实现/存根 | ~6 (6%) |
| 涉及的路由文件 | 18 个 |

部分实现的端点：
- `encounters.py`: `/text` 的文档拆分幼稚（仅靠标题关键词匹配）
- `evaluation.py`: `/batch` 是存根；3 个指标为硬编码常量
- `usage.py`: credits_used 和 avg_response_time_ms 为硬编码
- `oauth.py`: `authorize` 跳过登录页面；auth_codes 在内存中
- `experts.py`: `/stream` 不是真正的流式传输（一次性返回全部输出）
- `websocket.py`: Agent LLM 响应为模拟流式（按单词分块，非 token 级）

### 后端服务层

| 指标 | 数值 |
|------|------|
| 服务文件数 | 32 |
| 完全实现 | 32 (100%) |
| 有已知 bug | 1 (SSE Manager 心跳泄漏) |
| 有硬编码路径/值 | 3 (DRG 路径、A2A localhost、规则引擎) |

### 后端智能体层

| 指标 | 数值 |
|------|------|
| Expert 总数 | 13 |
| 完全实现 | 13 (100%) |
| 固定 Pipeline 调用 | 9 (Evidence/Timeline/Diagnosis/Procedure/Homepage/DRG/DocGap/Verify/Report) |
| 仅 Intelligent Pipeline 调用 | 4 (CDI/Denial/Audit/HCC) |
| 基于 LLM | 6 (Evidence/Timeline/Diagnosis/Procedure/CDI/Denial/HCC) |
| 纯规则/模板 | 7 (Homepage/DRG/DocGap/Verify/Report/Audit/ClinicalTriage) |

### 前端层

| 指标 | 数值 |
|------|------|
| 总页面数 | 24 |
| 功能完整 | 21 (88%) |
| 部分实现 | 2 (RuleLibraries 无后端保存、Support 静态) |
| 存根 | 1 (Tickets 外部链接) |
| 有 mock 数据 | 6 (HomePage 趋势/MC 流式/Fact 成本/Billing 充值/Settings 护栏/Embedded 聊天) |
| 前端单元测试 | 0 |
| E2E 测试 | 0 |

### 数据层

| 指标 | 数值 |
|------|------|
| SQLAlchemy 模型 | 18 |
| 有 Pydantic Schema 的模型 | 8 (User/Encounter/Document/CodingReview/ClinicalEvidence/CodeCandidate/GoldCase/AuditLog) |
| 缺少 Schema 的模型 | 10 |
| ReviewResponse 能从 DB 正确加载 | ❌ (from_attributes=False) |
| GoldCase 有 Update 端点 | ❌ |
| Alembic 迁移 | 0 |

### 工程质量

| 指标 | 数值 |
|------|------|
| 后端测试文件 | ~5 个（状态未知） |
| 前端测试文件 | 0 个 |
| GitHub Actions CI | ❌ |
| Pre-commit hooks | ❌ |
| 数据库迁移 | ❌ |
| Token 消耗监控 | ❌ |
| 结构化日志 | 部分（Python logging） |

---

## 六、优先工作项（按紧迫度排列）

### 立即（本周）

1. **提交工作区代码** — agent_runner.py (+280)、orchestrator.py (+395)、runtime.py (+297) 的 Runtime 集成是最关键的安全改进，不应长时间留在工作区
2. **验证 P1-1 (WebSocket STT)** — 启动前后端，确认 `/ws/speech-to-text` 端到端可用
3. **验证 P1-6 (路由冲突)** — 确认 APIClientsPage 在前端可正常访问

### 短期（1-2 周）

4. **修复 N1 (SSE Manager 心跳泄漏)** — 在 `done` 事件发送后设置 stop_event
5. **修复 N2 (ReviewResponse 空关联数据)** — 查询 candidates/evidences 表并填充响应
6. **修复 N4 部分** — 至少为 Agent、Expert、ApiKey 添加 Pydantic Schema
7. **intelligent_pipeline 集成 Runtime** (P2-4) — 设计动态状态机或限制使用场景
8. **A2A coordinate() 实现真实执行** (P2-2)

### 中期（3-4 周）

9. **前端测试初始化** — 核心页面（Login/Agents/CaseReview/CodingWorkbench）组件测试
10. **后端测试补齐** — Runtime、AgentRunner、Orchestrator 集成测试
11. **GitHub Actions CI** — pytest + vitest，PR 触发
12. **数据库迁移初始化** — 生成初始 Alembic migration
13. **N5-N12 修复** — 各新发现问题的修复

### 上线阻塞项总结

当前真正阻塞上线的只有 **P1-1**（WebSocket STT 不可用）和 **P1-6**（路由冲突），且两者都需要实际启动环境验证。其余 P1 项在工作区代码中已有完整修复方案。

---

## 附录 A：各 Expert 详细状态

| Expert | 实现 | LLM 调用 | 固定 Pipeline | Intelligent Pipeline |
|--------|------|---------|--------------|---------------------|
| EvidenceExtractionExpert | 完整 | ✅ (extract_json) + regex 回退 | Step 1 | 可选 |
| TimelineReconstructionExpert | 完整 | ✅ (chat) + regex 回退 | Step 2 (工作区新增) | 可选 |
| ICDDiagnosisExpert | 完整 | ✅ Phase D | Step 3a | 可选 |
| ProcedureCodingExpert | 完整 | ✅ Phase D | Step 3b | 可选 |
| MedicalRecordHomepageExpert | 完整 | 否（纯规则） | Steps 4-6 | 可选 |
| EvidenceVerificationExpert | 完整 | 否（纯规则） | Step 7 | 可选 |
| DRGDIPExpert | 完整 | 否（纯规则，硬编码 MCC 列表） | Step 8a | 可选 |
| DocumentationGapExpert | 完整 | 否（纯规则，硬编码关键词） | Step 8b | 可选 |
| ReportExpert | 完整 | 否（Jinja2 模板渲染） | Step 9 | 可选 |
| CDIExpert | 完整 | ✅ | **否** | 可选 |
| DenialManagementExpert | 完整 | ✅ | **否** | 可选 |
| AuditTrailExpert | 完整 | 否（纯聚合） | **否** | 可选 |
| HCCRiskAdjustmentExpert | 完整 | ✅ | **否** | 可选 |

## 附录 B：服务层清单

| 服务 | 行数 | 状态 | 关键备注 |
|------|------|------|---------|
| runtime.py | 684 | 核心安全 | 5 层安全框架；工作区新增 6 条 guard_post 规则 |
| agent_runner.py | 499 | 工作区大幅改进 | 工作区新增全面 Runtime 集成 |
| code_dictionary.py | 472 | 完整 | 导入时加载数据；rapidfuzz 模糊匹配 |
| evidence_ranker.py | 506 | 完整 | 冲突类型 4 有占位代码 |
| stt_service.py | 391 | 完整 | FunASR Paraformer；全局可变状态 |
| speaker_diarizer.py | 363 | 完整 | MFCC + 凝聚聚类；3 层回退 |
| confidence_calibrator.py | 359 | 完整 | 多源加权校准 |
| gold_case_importer.py | 324 | 完整 | 裁决状态机 |
| disagreement_analyzer.py | 319 | 完整 | 8 类不一致分类 |
| reasoning_report_builder.py | 302 | 完整 | 5 认知链整合 |
| a2a_protocol.py | 295 | 部分 | coordinate() 创建计划但不执行 |
| memory_expert.py | 271 | 完整 | 80MB 向量模型 |
| rule_engine.py | 226 | 完整 | 15 条硬编码中文编码规则 |
| gold_case_template.py | 231 | 完整 | 模板生成 + 验证 |
| llm_planner.py | 209 | 完整 | 12 步固定后备 |
| clinical_triage.py | 195 | 完整 | 5 规则 + LLM 回退 |
| runtime_state_sync.py | 201 | 完整 | 14 状态 → 领域模型映射 |
| inter_rater.py | 193 | 完整 | Cohen's Kappa + Fleiss' Kappa |
| llm_service.py | 187 | 完整 | DeepSeek V4 Pro；token 追踪 |
| expert_registry.py | 173 | 完整 | LLM 匹配 + 10min 缓存 |
| mcp_wrapper.py | 169 | 完整 | 变量作用域边缘情况 |
| task_manager.py | 156 | 完整 | 内存实现，TODO 生产 Redis |
| punctuation_service.py | 154 | 完整 | CT-Transformer + LLM 两阶段 |
| drg_grouper.py | 155 | 完整 | 仅基于手术，路径硬编码 |
| guardrails.py | 149 | 完整 | 纯规则；15-19 位数字可能误报 |
| expert_runner.py | 142 | 完整 | 简单服务检测启发式 |
| context_scoper.py | 138 | 完整 | 9 个已定义专家 |
| pilot_report_builder.py | 176 | 完整 | 医院管理语言 |
| mcp_client.py | 177 | 部分 | DrugBank/Web 搜索端点为 None |
| sse_manager.py | 109 | **有 bug** | done 后心跳不停止 |
| agent_analytics.py | 92 | 完整 | 未使用的 Transaction 导入 |
