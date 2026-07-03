# CORTI_PARITY_ROADMAP — Corti 对齐路线图

> **声明**: 本文档是 iCoDer 朝 Corti-style 平台对齐的**路线图**, 含 P1.3 范围 + Phase 2-4 后续. 取代 docs/PRODUCT-ROADMAP.md 中关于 MedCodER 主线的描述.
> **日期**: 2026-07-02
> **阶段**: P1.3 Corti Parity Direction Audit 后的路线图梳理
> **状态**: MAINLINE

---

## 0. 当前状态 (Stage 2 baseline)

- **总分**: 65.94/100 (3.30/5)
- **判断**: PARTIALLY_ALIGNED
- **已对齐 (5 维度, ≥4.0)**: Medical Coding API / Fact Extraction API / Text Generation API / STT API / Authentication
- **部分对齐 (11 维度, 2.0-4.0)**: 产品定位 / 架构 / Sidebar IA / 工作台模式 / 数据模型 / Edge Functions / 顶栏 / A2A / MCP / Context / 视觉系统
- **严重偏离 (4 维度, <2.0)**: Project Home 4 tabs / Embedded Assistant proxy / Pre-built Agents (20) / 文档站

---

## 1. P1.3 范围内 (本审计, Stage 4-8)

### 1.1 文档重写 (Stage 4, 已完成)

- ✅ `docs/product/PRODUCT_DIRECTION.md` — 新主线声明
- ✅ `docs/architecture/CURRENT_ARCHITECTURE.md` — 当前架构 4 层
- ✅ `docs/architecture/MAINLINE_VS_LEGACY.md` — 三层分类清单
- ✅ `docs/product/CORTI_PARITY_ROADMAP.md` — 本文档
- ⏳ `docs/backlog/PRODUCT_BACKLOG.md` — 产品 backlog
- ⏳ `docs/backlog/TECH_DEBT_BACKLOG.md` — 技术债 backlog
- ⏳ `docs/README_INDEX.md` — 文档索引

### 1.2 资产清理 (Stage 5)

- **P0 立即删 (10 项)**: .corti-user-data/ + 3 db.bak + test.db + 3 tmp_run.json + .bak + 2 空目录 + dashboard.html
- **P1 归档 (90+ docs + repo-root extras)**: 移到 `docs/archive/` 或 `archive/`
- **P2 Deprecated 标记 (代码不动)**: app/agents/ + agent_runner + icoder_* API + legacy 前端 + 评估 services

### 1.3 UI IA 最小纠偏 (Stage 6)

- Sidebar 段顺序对齐 Corti (Top → AI Studio → Manage → Support)
- Medical Coding 在 sidebar 降为 AI Studio 第 7 子页
- Project Home 加 4 tabs 雏形 (Transcribe/Document/Chat/Code)
- 顶栏加 Theme toggle + Reset live cost
- 工作台 5 tool 抽离共享 layout 壳子 (不动各页内部)

### 1.4 测试验证 (Stage 7)

- Asset/Docs/Direction Audit
- Backend/Runtime Regression (`health_check.py` + `check_schema_drift.py` + `export_openapi.py` + 关键 API 测试)
- Frontend Product Flow (`npx tsc --noEmit` + `npx vitest run`)
- Browser QA (可选)

### 1.5 最终报告 (Stage 8)

- `docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md`

### 1.6 P1.3 目标得分提升

| 维度 | P1.3 前 | P1.3 目标 | 提升手段 |
|---|---|---|---|
| 1 产品定位 | 2.80 | 4.0+ | MedCodER 降级 + PRODUCT_DIRECTION 重写 |
| 3 Sidebar IA | 3.00 | 4.0+ | Stage 6 sidebar 段顺序 |
| 4 Project Home 4 tabs | 1.33 | 3.0+ | Stage 6 Home 4 tabs 雏形 |
| 5 工作台通用模式 | 3.29 | 3.5+ | Stage 6 抽离共享 layout 壳子 |
| 13 顶栏元素 | 2.50 | 3.5+ | Stage 6 Theme toggle + Reset |
| 19 视觉设计系统 | 2.89 | 3.0+ | Stage 6 设计 token 抽离 (部分) |
| 20 文档站 | 1.13 | 3.0+ | Stage 4 README_INDEX + 7 份方向性文档 |

**P1.3 后预期总分**: ~75/100 (从 65.94 提升 ~10 分, 进入 "ALIGNED" 阈值边缘).

---

## 2. Phase 2 — Agentic Framework 真实跑通 (P1.3 后)

### 2.1 切换主运行路径到新 Orchestrator

**当前**: medical-coding 调用走 `v2_tools_coding.py` → `icoder_runtime/core/` → `medcoder-coding-review/agent_pack.json` → `HybridCodingAdapter` → MedCodER 5-stage (绕过新 orchestrator).

**目标**: 切换到 `v2_tools_coding.py` → `app/icoder/agent_runtime/orchestrator/wiring.py` → `build_expert_invoker_for_medcoder` → 4 D2 expert pack → MedCodER 5-stage (E1 已有 factory, hybrid_fallback back-compat 保留).

**预计**: 1-2 cycles, 需确保 e2e 测试不退化.

### 2.2 A2A 真实任务流

- `routes_task_stub.py` → 完整实装 Task 5 态 (submitted→working→input-required/completed/failed/canceled)
- Artifact 产出 (不同于 Message)
- A2A 真实任务流跑通 (inbound → orchestrator → outbound → completed)

**对应维度**: 维度 15 (A2A 3.00 → 4.0+)

### 2.3 MCP Resources/Prompts + Expert as MCP client

- MCP `tools/list` + `tools/call` 已实装 (M2), 加 `resources/list` + `prompts/list`
- Expert 作为 MCP client 跑通 (调用第三方 MCP server)
- Transport stdio 默认 + HTTP Phase 4

**对应维度**: 维度 16 (MCP 3.50 → 4.0+)

### 2.4 Context/Memory 真实跑通

- contextId UUID v4 服务端生成主线跑通
- 三层隔离 (数据/状态/缓存) 主线跑通
- GC 策略 (24h active + 7d 物理删除 + 90d audit) 主线跑通
- Memory expert 长期记忆 (BGE-M3 + FAISS) 跑通

**对应维度**: 维度 17 (Context/Memory 3.29 → 4.0+)

### 2.5 Legacy API 迁移 + 删除

- `app/api/icoder_coding_review.py` (1283) → 删 (Corti 用 /v2/tools/coding/)
- `app/api/icoder_agents_hub.py` (1029) + `agents.py` (736) → 合并迁到 `/rest/v1/agent_definitions`
- `app/api/icoder_agents_compat.py` + `icoder_registry_compat.py` → 删
- `app/api/runtime.py` (386) → 合并到 `runtime_platform.py`
- `app/api/text_gen.py` (131) → 合并到 `v2_tools_guided_document.py`
- `app/api/facts.py` (204) → 合并到 `v2_tools_facts.py`
- `app/services/agent_runner.py` (1047) + `icoder_runtime/agent_runner.py` → 删
- `app/services/runtime.py` (702) → 合并到 runtime_platform service
- `app/agents/` 整套 → 删 (orchestrator + 11 experts, 需先断引用)
- `frontend/src/components/orchestration/` 7 components → 删
- `frontend/src/components/icoder/RunTraceTimeline.tsx` + `medical-coding/MethodTraceViewer.tsx` → 删
- `frontend/src/services/icoderCodingReviewApi.ts` + `hooks/useReviewPipeline.ts` → 删
- `frontend/src/pages/EvaluationPage.tsx` + `GoldCasesPage.tsx` + `ExpertLibraryPage.tsx` + `OrchestrationPage.tsx` + `EmbedDemoCodingReviewPage.tsx` → 删

**对应维度**: 维度 6-9 (API 契约, 已 4.5+, 删 legacy 是隐患清除, 不加分)

### 2.6 Edge Functions 4 项 stub 实装

- `onboarding` 端点
- `assistant-settings` 端点
- `external/agents` 端点 (真实版, 非 Agent Hub 临时实现)
- `intercom-hmac` 端点

**对应维度**: 维度 12 (Edge Functions 3.14 → 4.0+)

### 2.7 Phase 2 目标得分

| 维度 | P1.3 后 | Phase 2 目标 |
|---|---|---|
| 6-9 API 契约 | 4.5+ | 4.5+ (维持, legacy 删) |
| 11 数据模型 | 3.38 | 3.5+ (改名评估) |
| 12 Edge Functions | 3.14+ | 4.0+ |
| 15 A2A | 3.0+ | 4.0+ |
| 16 MCP | 3.5+ | 4.0+ |
| 17 Context/Memory | 3.29+ | 4.0+ |

**Phase 2 后预期总分**: ~80/100 (进入 "ALIGNED").

---

## 3. Phase 3 — 20 Pre-built Agents 实装 (大坑)

### 3.1 17 个完全缺的 Pre-built Agents

按 Corti 20 Pre-built Agents 清单, 中国编码体系替换 (ICD-10-CM → ICD-10-CN, ICD-10-PCS → ICD-9-CM-3-CN, CPT → 删除, MS-DRG → CN-DRG/DIP):

| # | Agent | 优先级 | 数据来源 |
|---|---|---|---|
| 2 | Rule Explainer | P1 | 解释 ICD-10-CN/ICD-9-CM-3-CN code 选择理由 |
| 3 | Compliance Guardrail (完整版) | P1 | CN 医保合规 (CN-DRG / DIP 规则) |
| 7 | Surgical Registry Intelligence | P2 | 中国手术登记 |
| 8 | ICU Admission Summary | P2 | ICU 文档 |
| 9 | Triage and Initial Assessment | P2 | 急诊分诊 ( validated risk scores) |
| 10 | Note Completeness (完整版) | P1 | 实时完整性/准确性/合规检查 |
| 11 | Medication Reconciliation | P2 | 用药安全 |
| 12 | Denial Appeals (完整版) | P2 | 医保拒付申诉 |
| 13 | Patient Discharge Education | P3 | 出院教育 |
| 14 | Nursing Shift Handoff | P3 | 护理交班 |
| 15 | Prior Authorization | P2 | 预授权 |
| 16 | Referral Generator | P3 | 转诊 |
| 17 | Clinical Education | P3 | 临床教育 |
| 19 | Clinical Guidelines | P3 | 临床指南 |
| 20 | CDI (完整版) | P1 | Clinical Documentation Improvement |

### 3.2 10 metadata-only packs 实装真实 Python impl

- `cdi-review/` → cdi_expert.py
- `code-validation/` → code_validation_expert.py (升级 R001-R010)
- `compliance-guardrail/` → compliance_guardrail_expert.py (升级 RuleEngine)
- `denial-appeals/` → denial_appeals_expert.py
- `diagnosis-extractor/` → 升级 evidence_extractor (Stage 1 disease)
- `documentation-gap/` → documentation_gap_expert.py
- `evidence-ranker/` → 升级 code_reconciler (Stage 4 rerank)
- `note-completeness/` → note_completeness_expert.py
- `procedure-extractor/` → 升级 evidence_extractor (Stage 1 procedure)
- `drg-analyzer/` → 已有 3 文件, 升级到完整 impl

### 3.3 Phase 3 目标得分

| 维度 | Phase 2 后 | Phase 3 目标 |
|---|---|---|
| 14 Pre-built Agents | 1.40+ | 4.0+ (17 个缺补齐 + 10 metadata-only 实装) |

**Phase 3 后预期总分**: ~85/100.

---

## 4. Phase 4 — 第三方基础设施 + Embedded Assistant 子域 proxy

### 4.1 第三方基础设施

- **PostHog 自部署** (prp.corti.app 等价) — session replay + feature flags + event capture
- **Stripe Billing 全套** — 订阅 + invoice + 支付
- **Intercom Tickets** 嵌入 (替代自实现 TicketsPage, 或保留 in-app 等价)
- **Mintlify 文档站** 自部署 + `llms.txt` (AI ingestion 友好) + 27 详细页面 + 377 索引
- **Keycloak** IdP (替代自实现 JWT, 功能等价但 Corti 同 IdP)

### 4.2 Embedded Assistant 子域 proxy

- 独立子域 `assistant.{region}.icoder.cloud` (或子路径 `/assistant/api/*`)
- `/api/auth/session` + `/api/ready`
- `/api/proxy/dd` (Datadog RUM)
- `/api/proxy/mp/*` (Mixpanel)
- `/api/proxy/relay/*` (PostHog relay)
- `/api/trpc/template.getAllSections` (tRPC)
- `POST /embedded` session init

### 4.3 Phase 4 目标得分

| 维度 | Phase 3 后 | Phase 4 目标 |
|---|---|---|
| 2 架构层 | 2.25+ | 4.0+ (第三方齐全) |
| 10 Embedded Assistant | 1.67+ | 4.0+ (子域 proxy + tRPC + relay) |
| 13 顶栏 PostHog replay | 缺 | 4.0+ |
| 20 文档站 | 3.0+ | 4.0+ (Mintlify + llms.txt) |
| 18 Authentication Keycloak | 4.5 (自实现) | 5.0 (Keycloak) |

**Phase 4 后预期总分**: ~90/100 (完全 ALIGNED).

---

## 5. 不在 Roadmap (永不上主线)

- F1 提升实验 / 模型训练 / Stage 1/4/rerank/few-shot 改动 — CLAUDE.md 已降级, 永不上主线
- Doctor 自检 / MethodCompare / 10 builtin methods / MethodSwitcher / RunTrace / ExpertLibrary / OrchestrationPage / EvaluationPage / GoldCasesPage — P1.2/P1.3 已删或降级, 永不上主线
- 私有化部署 / 数据不出院 — Cloud-Flip 2026-06-27 已逆转, 永不上主线
- icoder-next 切片 — Pivot 2026-06-17 已逆转, 永不上主线

---

## 6. 优先级矩阵

| Phase | 维度提升 | 工作量 | 优先级 |
|---|---|---|---|
| P1.3 (本审计) | 7 维度 (+10 分) | 低 (文档 + 最小 UI 纠偏) | NOW |
| Phase 2 | 5 维度 (+5 分) | 中 (Agentic Framework 真实跑通 + legacy 删) | NEXT |
| Phase 3 | 1 维度 (+5 分) | 高 (17 Pre-built Agents + 10 impl) | MID-TERM |
| Phase 4 | 4 维度 (+5 分) | 高 (第三方基础设施 + 子域 proxy) | LONG-TERM |

---

## 7. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, P1.3 + Phase 2-4 路线图 | P1.3 Stage 3 方向纠偏 |
