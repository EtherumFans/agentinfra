# CORTI_PARITY_GAP_ANALYSIS — 对标差距分析

> **阶段**: P1.3 — Corti Parity Direction Audit & Asset Consolidation / Stage 2
> **输入**: Stage 0 baseline (`CORTI_REFERENCE_BASELINE.md`) + Stage 1 inventory (`ICODER_ASSET_INVENTORY.md`)
> **日期**: 2026-07-02
> **评分**: 0-5 each (0 = 完全不齐 / 5 = 完全对齐), 总分 100
> **总体判断**: ALIGNED / PARTIALLY_ALIGNED / MISALIGNED / SEVERELY_MISALIGNED

---

## 0. 评分尺度

| 分数 | 含义 |
|---|---|
| 0 | 完全缺失 (无任何对齐) |
| 1 | 概念存在但路径/字段/IA 严重偏离 |
| 2 | 部分对齐 (路径或字段二选一) |
| 3 | 主要对齐 (路径 + 字段大致对齐, 缺细节) |
| 4 | 接近完全对齐 (仅缺次要元素) |
| 5 | 完全对齐 (Corti baseline 100% 覆盖) |

---

## 1. 20 维度逐项评分

### 维度 1 — 产品定位与哲学

**Corti baseline**: All-in-one AI stack for healthcare, Corti Symphony (model network + orchestration), LLM 两大缺口 (无可靠数据访问 + 无法安全作用于世界), 8 设计原则 (Safety/Auditability/Domain-Specific/Multi-Agent/Memory/Prebuilt Experts/Third-Party/Run-time Context), Agent vs Workflow 二元区分.

**iCoDer 现状**: CLAUDE.md 已声明 "医疗收入合规 AI 平台 (托管云 SaaS, Corti-style)", 8 层合规体系 (编码/分组/结算/收费/病历/审计). 但 MedCodER 仍被当作产品本体 (CLAUDE.md 大段描述 5-stage pipeline + NAACL 2025 + 4 ablation variant), 偏向"医疗编码单点工具". E1.x 系列 cycle 全部围绕 MedCodER 优化, 未实施真正多 Agent 架构.

| 子项 | 分数 | 理由 |
|---|---|---|
| 一句话定位 Corti-style | 4 | CLAUDE.md 声明 Corti-style, 但 MedCodER 描述过度 |
| LLM 两大缺口认知 | 3 | A2A spec 引用, 但未在主线代码体现 |
| 8 设计原则 | 3 | Safety/Auditability/Memory 部分实现, Multi-Agent 仅 spec |
| Agent vs Workflow 二元 | 2 | 仅 Agent 概念, Workflow 完全缺 (Corti §11.5) |
| MedCodER 不是产品本体 | 2 | CLAUDE.md 仍把 MedCodER 当主线描述 |

**维度得分**: **14/25** = 2.8/5

**证据**: `CLAUDE.md:3-30` (Corti-style 声明), `CLAUDE.md:80-130` (MedCodER 主线描述), `docs/ICODER_V1_ORCHESTRATOR_SPEC.md` (spec 草稿未实装)

**最大差距**: MedCodER 仍是事实主线, 多 Agent + Workflow 二元未落地.

**所需行动**: Stage 3 方向纠偏 — MedCodER 降级为 Pre-built Agent #18, 平台定位重写为 Agent Runtime.

---

### 维度 2 — 架构层 (4 大域名 + 第三方)

**Corti baseline**: 4 大域名 (console / api.console / api.eu / assistant.eu) + Keycloak auth + PostHog 自部署 + Stripe + Intercom + GA4 + Crazyegg + Mintlify 文档 CDN.

**iCoDer 现状**: 单域名子路径 (cloud flip 已决议 + 落地), `{tenant}.{region}.icoder.cloud` 模式. 但 `auth.{region}.icoder.cloud` Keycloak 未实装 (自实现 JWT, Phase 1.0 已对齐 OAuth 2.0 但不走 Keycloak). PostHog 自部署未实装. Stripe/Intercom 缺. Mintlify 文档 CDN 缺 (自写 markdown). 第三方集成 (Datadog/Mixpanel/PostHog relay) 在 Embedded Assistant 上完全缺.

| 子项 | 分数 | 理由 |
|---|---|---|
| 单域名子路径模式 | 5 | cloud flip 已落地 (project_cloud_flip_2026_06_27) |
| api.console → /api/v1/* 对齐 | 4 | FastAPI + SQLAlchemy 已对齐路径 |
| api.eu → /api/v2/tools/* 对齐 | 5 | Phase 1.1/1.2/1.3 全部 CLOSE |
| assistant.eu → /assistant/api/* 对齐 | 2 | 路径有但 proxy 模式 (relay/trPC) 未实装 |
| auth Keycloak | 2 | 自实现 JWT, 未走 Keycloak (Phase 1.0 4 gap closed 但非 Keycloak) |
| PostHog 自部署 | 0 | 完全缺 |
| Stripe / Intercom / GA4 / Crazyegg | 0 | 全部缺 |
| Mintlify 文档 CDN | 0 | 自写 markdown, 无 llms.txt |

**维度得分**: **18/40** = 2.25/5 → 标准化 **2.25/5**

**证据**: `CLAUDE.md:31-50` (架构层声明), `backend/app/api/oauth.py` (449 LOC, 自实现 OAuth 2.0), `backend/app/middleware/tenant_extractor.py` (tenant header), `docs/cloud/CLOUD_DEPLOYMENT.md`

**最大差距**: 第三方基础设施 (PostHog/Stripe/Intercom/Mintlify) 完全缺, Keycloak 未实装.

**所需行动**: Stage 3 — 第三方基础设施列为 Phase 4 (部署与监控对齐), 不在 P1.3 范围内但需明确 roadmap.

---

### 维度 3 — Sidebar 信息架构 (15 个 feature)

**Corti baseline**: 15 feature 严格按 Top → AI Studio → Manage → Support 段顺序. AI Studio: Overview → Agents → STT (3 子页) → Text Generation → Embedded Assistant → Fact Extraction → Medical Coding. Manage: API Clients → Team → Billing → Usage → Customers → Templates (BETA) → Settings. Support: Get Help / Tickets Portal.

**iCoDer 现状**: App.tsx 路由全部存在 (24 Corti-aligned pages). 但 sidebar 实际顺序 + 段划分未对齐 Corti (App.tsx 注释 "Task #4 rewrites the sidebar to align with Corti's IA"). Medical Coding 在 Corti 是 AI Studio 最后一个, iCoDer 把它当首页主入口. /studio/ + /manage/ 别名仍存在作为 no-op redirect.

| 子项 | 分数 | 理由 |
|---|---|---|
| 4 段 (Top/AI Studio/Manage/Support) | 3 | 段概念存在但 sidebar 未严格对齐 |
| AI Studio 7 子页顺序 | 3 | 路由有, sidebar 顺序未对齐 Corti |
| Manage 7 项顺序 | 3 | 同 |
| Support 2 项 | 4 | SupportPage + TicketsPage 已对齐 |
| Medical Coding 位置 (AI Studio 最后) | 2 | iCoDer 把它当首页主入口, 位置偏离 |
| 缩进规则 (1 级 16px) | 3 | 部分对齐 |

**维度得分**: **18/30** = 3.0/5

**证据**: `frontend/src/App.tsx:60-130` (路由), `frontend/src/components/layout/Layout.tsx` (sidebar), `docs/corti-feature-inventory.md:7-29` (15 feature 走查)

**最大差距**: Sidebar 实际段顺序 + Medical Coding 在 IA 中的位置偏离 Corti.

**所需行动**: Stage 6 (UI IA 纠正) — 重写 sidebar 段顺序, Medical Coding 降为 AI Studio 第 7 个子页.

---

### 维度 4 — Project Home 4 tabs

**Corti baseline**: `/project/<id>` Home 顶部 4 tabs: Transcribe / Document / Chat / Code NEW. 每个 tab promo 跳到对应 AI Studio 工作台. 不是 dashboard 也不是 admin 首页.

**iCoDer 现状**: `HomePage.tsx` 181 LOC, 有 HomePage 但不是 Corti 风格 4 tabs. App.tsx 注释 "Task #4 rewrites the sidebar" 暗示 Home 也待重写.

| 子项 | 分数 | 理由 |
|---|---|---|
| 4 tabs (Transcribe/Document/Chat/Code) | 1 | HomePage 不是 4 tabs 模式 |
| 每个 tab promo 跳工作台 | 1 | 同 |
| 不是 dashboard | 2 | HomePage 偏 dashboard 风格 |

**维度得分**: **4/15** = 0.8/5

**证据**: `frontend/src/pages/HomePage.tsx` (181 LOC, 非 4 tabs 模式), `docs/corti-feature-inventory.md:30-38` (Corti 4 tabs 抓包)

**最大差距**: HomePage 不是 Corti 4 tabs 模式, 偏 dashboard.

**所需行动**: Stage 6 — 重写 HomePage 为 4 tabs (Transcribe/Document/Chat/Code).

---

### 维度 5 — AI Studio 工作台通用模式

**Corti baseline**: 5 个 Studio tool 共享 layout: 左 Input / 右 Output 50/50 split + Input 控件 (Samples/Clear/Copy) + Output 控件 (Rendered/JSON toggle/Clear/Copy/Download) + 右侧 Settings panel (Settings/Code tabs + Template dropdown + Output language) + 底部 Event Inspector 可折叠 + Empty state "Predicted codes will show here".

**iCoDer 现状**: `MedicalCodingPage.tsx` 760 LOC 有 Input/Output + HighlightedTextarea (cycle 19) + char counter + click-code→green-highlight (cycle 22). `components/common/EventInspector.tsx` 已存在. 但其他 Studio tool (FactExtraction/TextGeneration/SpeechToText/EmbeddedAssistant) 未严格共享同一 layout, 各自实现.

| 子项 | 分数 | 理由 |
|---|---|---|
| Input/Output 50/50 split | 4 | MedicalCodingPage 已对齐, 其他页部分 |
| Input 控件 (Samples/Clear/Copy) | 4 | 已对齐 |
| Output 控件 (Rendered/JSON toggle/Clear/Copy/Download) | 3 | 部分, 缺 Download |
| 右侧 Settings panel (Settings/Code tabs) | 3 | 部分对齐 |
| 底部 Event Inspector | 4 | `components/common/EventInspector.tsx` 已存在 |
| Empty state microcopy | 3 | 部分对齐 |
| 5 tool 共享同一 layout | 2 | 仅 MedicalCoding 完整, 其他 4 个不齐 |

**维度得分**: **23/35** = 3.3/5

**证据**: `frontend/src/pages/MedicalCodingPage.tsx` (760 LOC), `frontend/src/components/common/EventInspector.tsx`, `frontend/src/components/medical-coding/HighlightedTextarea.tsx` (cycle 19), `docs/corti-reverse-engineered/SUMMARY.md:499-525` (Corti 工作台 layout)

**最大差距**: 5 个 Studio tool 不共享统一 layout, 只有 MedicalCoding 完整.

**所需行动**: Stage 6 — 抽离工作台通用 Layout 组件, 5 个 Studio tool 共享.

---

### 维度 6 — Medical Coding API 契约

**Corti baseline**: `POST /v2/tools/coding/` + `context[]` (多模态) + `system[]` (icd10cm-outpatient/inpatient/pcs/icd9cm/cpt) + `evidences[]` (char span + contextIndex + start/end) + `alternatives[]` (rerank 候选) + `codes[]` wrapper.

**iCoDer 现状**: Phase 1.1 已落地 `POST /api/v2/tools/coding/icoder/` (中国 ICD-10-CN/ICD-9-CM-3-CN 命名, US 命名故意 400). char-span evidence + rerank alternatives 直接投影. `evidence_parser.py` 解析 Stage-1 markdown. `RuntimeRunResult` 加 source param 填 metadata.evidences. 但 schema 与 Corti 完全等价 (codes/system/code/display/evidences/alternatives).

| 子项 | 分数 | 理由 |
|---|---|---|
| Endpoint 路径 `/v2/tools/coding/` | 4 | `/api/v2/tools/coding/icoder/` 多一段 icoder, 但 v2/tools/coding 对齐 |
| Request schema (context/system) | 5 | 完全对齐 |
| Response schema (codes/evidences/alternatives) | 5 | 完全对齐 |
| char span evidence | 5 | evidence_parser.py 已实装 (cycle 22) |
| rerank alternatives | 4 | 已投影, 部分对齐 |
| 中国编码体系替换 | 5 | ICD-10-CN/ICD-9-CM-3-CN 已就绪 |

**维度得分**: **28/30** = 4.67/5

**证据**: `backend/app/api/v2_tools_coding.py` (559 LOC), `backend/app/schemas/v2_tools_coding.py`, `backend/icoder_runtime/core/evidence_parser.py` (cycle 22), `docs/PHASE_1_1_MEDICAL_CODING_PATH_SCHEMA.md`

**最大差距**: Endpoint 路径多一段 `/icoder/` (Corti 是 `/v2/tools/coding/`, iCoDer 是 `/v2/tools/coding/icoder/`).

**所需行动**: 评估是否去掉 `/icoder/` 后缀 (CLAUDE.md Phase 1.1 决议是 transparent 暴露体系差, 故保留).

---

### 维度 7 — Fact Extraction API 契约

**Corti baseline**: `POST /v2/tools/extract-facts` + `GET /v2/factgroups/` + FactsR™ stateless 文本→事实 + Streams WSS stateful 实时.

**iCoDer 现状**: Phase 1.2 cycle 1 (extract-facts) + Phase 1.3 cycle 13-17 (5 facts CRUD cycles CLOSED). `v2_tools_facts.py` 619 LOC. 但 Streams WSS 走 `v2_tools_streams.py` (382 LOC, Phase 1.2 cycle 2).

| 子项 | 分数 | 理由 |
|---|---|---|
| `POST /v2/tools/extract-facts` | 5 | Phase 1.2 cycle 1 已对齐 |
| `GET /v2/factgroups/` | 5 | Phase 1.3 cycle 15 已对齐 |
| Facts CRUD (list/add/update/batch) | 5 | Phase 1.3 cycle 13-17 全 CLOSE |
| Streams WSS stateful | 4 | Phase 1.2 cycle 2 已对齐, 部分 |
| FactsR stateless | 4 | 已对齐, 但与 Corti FactsR™ 商标不同 |

**维度得分**: **23/25** = 4.6/5

**证据**: `backend/app/api/v2_tools_facts.py` (619 LOC), `backend/app/api/v2_tools_streams.py` (382 LOC), `docs/PHASE_1_3_CYCLE17_FACTS_UPDATE_BATCH_2026_07_01.md`

**最大差距**: 无明显差距, Phase 1.2/1.3 已闭环.

**所需行动**: 无, 维护即可.

---

### 维度 8 — Text Generation API 契约 (5 endpoints)

**Corti baseline**: Streams (WSS stateful) + FactsR™ (REST stateless) + Guided Document Synthesis (REST stateless/stateful, Beta) + Sections & Templates (REST CRUD, Beta) + Documents Classic (REST stateful, Planned deprecation).

**iCoDer 现状**: Phase 1.2 cycle 1-5 (5 cycles wrap-up CLOSED). `v2_tools_streams.py` (382) + `v2_tools_guided_document.py` (277) + `v2_tools_sections_templates.py` (262) + `v2_tools_documents_classic.py` (196). 5 endpoints 全对齐, 状态标 Beta/Deprecated 也对齐 Corti.

| 子项 | 分数 | 理由 |
|---|---|---|
| Streams WSS | 4 | 已对齐 |
| FactsR stateless | 4 | 已对齐 |
| Guided Document Synthesis (Beta) | 5 | Phase 1.2 cycle 3 已对齐 |
| Sections & Templates (Beta) | 5 | Phase 1.2 cycle 4 已对齐 |
| Documents Classic (deprecated) | 5 | Phase 1.2 cycle 5 已对齐 |

**维度得分**: **23/25** = 4.6/5

**证据**: `backend/app/api/v2_tools_*.py` (5 文件), `docs/PHASE_1_2_CYCLE5_DOCUMENTS_CLASSIC_LIST.md`

**最大差距**: 无明显差距.

**所需行动**: 无.

---

### 维度 9 — Speech-to-Text API 契约 (3 endpoints)

**Corti baseline**: Transcribe (WSS stateless real-time) + Streams (WSS stateful real-time) + Transcripts (REST sync→async stateful batch).

**iCoDer 现状**: Phase 1.3 cycle 6-12.2 (9+ cycles STT CLOSED). `v2_tools_stt.py` 866 LOC. Transcripts LIST/GET/CREATE + Recordings LIST/UPLOAD/GET/DELETE + get-transcript-status + delete-transcript 全对齐. 但 Transcribe WSS real-time 部分对齐 (`websocket.py` 521 LOC), Streams WSS 已在 `v2_tools_streams.py`. 3 子 tab (Dictation/Ambient/Pre-recorded) 在 SpeechToTextPage 部分对齐.

| 子项 | 分数 | 理由 |
|---|---|---|
| Transcribe WSS stateless | 3 | websocket.py 部分, 未完全 stateless |
| Streams WSS stateful | 4 | 已对齐 |
| Transcripts REST | 5 | Phase 1.3 cycle 6-12.2 全 CLOSE |
| 3 子 tab (Dictation/Ambient/Pre-recorded) | 3 | 部分对齐 |
| Transcripts CRUD (9 cycles) | 5 | 完整对齐 |

**维度得分**: **20/25** = 4.0/5

**证据**: `backend/app/api/v2_tools_stt.py` (866 LOC), `backend/app/api/websocket.py` (521 LOC), `docs/PHASE_1_3_CYCLE12_2_STT_DELETE_TRANSCRIPT_2026_07_01.md`

**最大差距**: Transcribe WSS stateless real-time 未完全对齐, 3 子 tab 部分缺.

**所需行动**: Stage 3 列入 roadmap (非 P1.3 范围).

---

### 维度 10 — Embedded Assistant (proxy 模式)

**Corti baseline**: `assistant.eu.corti.app` 独立子域 + `/api/auth/session` + `/api/ready` + `/api/proxy/dd` (Datadog) + `/api/proxy/mp/*` (Mixpanel) + `/api/proxy/relay/*` (PostHog) + `/api/trpc/template.getAllSections` (tRPC) + `POST /embedded` (session init).

**iCoDer 现状**: `app/api/embedded.py` 95 LOC, 仅 session init + 简单 endpoint. 无独立子域 proxy 模式, 无 tRPC, 无 Datadog/Mixpanel/PostHog relay. `EmbeddedAssistantPage.tsx` 714 LOC 是工作台 UI 但非 proxy 模式.

| 子项 | 分数 | 理由 |
|---|---|---|
| 独立子域 proxy | 1 | 无, 走单域名子路径 |
| `/api/auth/session` + `/api/ready` | 2 | 部分, embedded.py 有简单实现 |
| `/api/proxy/*` (Datadog/Mixpanel/PostHog) | 0 | 完全缺 |
| `/api/trpc/template.getAllSections` | 0 | 完全缺 |
| `POST /embedded` session init | 3 | 已对齐 |
| Web Component 嵌入 | 4 | `packages/icoder-embedded/` + `web-components/` 已有 |

**维度得分**: **10/30** = 1.67/5

**证据**: `backend/app/api/embedded.py` (95 LOC), `frontend/src/pages/EmbeddedAssistantPage.tsx` (714 LOC), `packages/icoder-embedded/src/icoder-assistant.ts`

**最大差距**: 独立子域 proxy + tRPC + 第三方 relay 完全缺.

**所需行动**: Stage 3 列入 Phase 4 roadmap (非 P1.3 范围, 需大量基础设施).

---

### 维度 11 — 数据模型 (PostgREST 表)

**Corti baseline**: 7 表 (projects / project_memberships / team_invitations / api_clients / agent_definitions / project_assets / customer_assets) + RPC `is_limited_admin_user`.

**iCoDer 现状**: 22 models (`app/models/`), 涵盖 user/organization/team/agent/audit_log/api_key/billing/customer/encounter/evidence/expert/gold_case/memory/oauth/review/runtime_persistence/template/ticket/code_table/code_candidate/coding_review_run/agent_account. 多租户 + multi-tenant schema (migration 003) + alembic 8 migrations. 但 model 命名与 Corti 不完全一致 (iCoDer 用 organization, Corti 用 projects; iCoDer 用 agent, Corti 用 agent_definitions).

| 子项 | 分数 | 理由 |
|---|---|---|
| projects → organization | 3 | 概念对齐, 命名不同 |
| project_memberships → team | 4 | 对齐 |
| team_invitations → team | 4 | 对齐 |
| api_clients → api_key/platform_api_clients | 3 | 概念对齐, 命名分散 |
| agent_definitions → agent | 3 | 概念对齐, 命名不同 |
| project_assets / customer_assets → customer | 3 | 部分对齐 |
| RPC is_limited_admin_user | 2 | 部分 (admin.py 有 admin role check) |
| Multi-tenant 隔离 | 5 | migration 003 已对齐 |

**维度得分**: **27/40** = 3.375/5

**证据**: `backend/app/models/` (22 文件), `backend/alembic/versions/` (8 migrations), `docs/corti-reverse-engineered/SUMMARY.md:131-146` (Corti 7 表)

**最大差距**: 命名分散 (organization vs projects, agent vs agent_definitions), 缺 RPC.

**所需行动**: Stage 3 — 评估是否改名 organization → project, agent → agent_definition (高代价, 可放缓).

---

### 维度 12 — Edge Functions

**Corti baseline**: 7 Edge Functions (access_token ROPC / billing/balance / onboarding / assistant-settings / external/agents / public/projects/.../customers / intercom-hmac).

**iCoDer 现状**: `access_token` (Phase 1.0 已对齐, 5min TTL + scoped) + `billing/balance` (Loop 4) + `customers` (Loop 1) 全对齐. `onboarding`/`assistant-settings`/`external/agents`/`intercom-hmac` 4 项缺或 stub.

| 子项 | 分数 | 理由 |
|---|---|---|
| `access_token` ROPC | 5 | Phase 1.0 已对齐 (4 gap closed) |
| `billing/balance` | 5 | Loop 4 已对齐 |
| `customers` | 5 | Loop 1 已对齐 |
| `onboarding` | 2 | stub 状态 |
| `assistant-settings` | 2 | stub 状态 |
| `external/agents` | 3 | Agent Hub 部分对齐 |
| `intercom-hmac` | 0 | 完全缺 |

**维度得分**: **22/35** = 3.14/5

**证据**: `backend/app/api/oauth.py` (449 LOC, Phase 1.0), `backend/app/api/billing.py` (80 LOC), `backend/app/api/customers.py` (217 LOC), `backend/app/api/icoder_agents_hub.py` (1029 LOC, external/agents 部分对齐)

**最大差距**: 4 个 Edge Functions 缺或 stub (onboarding/assistant-settings/external/agents 真实版/intercom-hmac).

**所需行动**: Stage 3 列入 roadmap (onboarding + assistant-settings + external/agents 是 Phase 2 业务侧 API 对齐).

---

### 维度 13 — 顶部全局元素

**Corti baseline**: Breadcrumb + Live cost (6 位小数) + Reset live cost + API Client dropdown + $credits 余额 + Docs link + Theme toggle (深/浅) + PostHog session replay.

**iCoDer 现状**: Breadcrumb ✅ + Live cost ✅ (Loop 4) + API Client dropdown ✅ + $credits ✅ + Docs link ✅. Reset live cost ❌ + Theme toggle ❌ + PostHog session replay ❌.

| 子项 | 分数 | 理由 |
|---|---|---|
| Breadcrumb | 5 | 已对齐 |
| Live cost (6 位小数) | 5 | Loop 4 已对齐 |
| Reset live cost | 0 | 缺 |
| API Client dropdown | 5 | 已对齐 |
| $credits 余额 | 5 | 已对齐 |
| Docs link | 5 | 已对齐 |
| Theme toggle (深/浅) | 0 | 完全缺 |
| PostHog session replay | 0 | 完全缺 |

**维度得分**: **20/40** = 2.5/5

**证据**: `frontend/src/components/layout/Layout.tsx`, `frontend/src/pages/BillingPage.tsx` (383 LOC, live cost 实现), `docs/corti-reverse-engineered/SUMMARY.md:163-176` (顶栏元素)

**最大差距**: Theme toggle + Reset live cost + PostHog 完全缺.

**所需行动**: Stage 6 — 加 Theme toggle + Reset live cost (PostHog 列入 Phase 4).

---

### 维度 14 — 20 Pre-built Agents 清单

**Corti baseline**: 20 Pre-built Agents (ICD-10 Index Navigator / Rule Explainer / Compliance Guardrail / Code Validation / Procedure Entity Extractor / Diagnostic Entity Extractor / Surgical Registry Intelligence / ICU Admission Summary / Triage / Note Completeness / Medication Reconciliation / Denial Appeals / Patient Discharge Education / Nursing Shift Handoff / Prior Authorization / Referral Generator / Clinical Education / Medical Coding / Clinical Guidelines / CDI).

**iCoDer 现状**: 16 agent pack 目录, 仅 2 个真实 Python impl (medical_coding + medcoder-coding-review), 4 个 atomic expert stub packs (evidence_extractor/index_navigator/code_reconciler/tabular_validator 引用 agent_runtime experts), 10 个仅 metadata (agent_pack.json 无 impl). 20 个 Corti Pre-built Agents 中 iCoDer 仅 3 个对齐 (Medical Coding Agent #18 + 部分 Index Navigator #1 + 部分 Code Validation #4), 其余 17 个完全缺.

| 子项 | 分数 | 理由 |
|---|---|---|
| Medical Coding Agent (#18) | 5 | 已对齐 |
| ICD-10 Index Navigator (#1) | 3 | 部分对齐 (ICD-9-CM-3 retriever 已做, ICD-10-CN Index Navigator 待做) |
| Code Validation (#4) | 3 | 部分对齐 (R001-R010 + 修复 loop) |
| Procedure Entity Extractor (#5) | 3 | Stage 1 procedure_mentions 已做 |
| Diagnostic Entity Extractor (#6) | 3 | Stage 1 disease 已做 |
| Compliance Guardrail (#3) | 2 | 有 RuleEngine 但无 Guardrail Agent |
| Note Completeness (#10) | 2 | Doctor 概念相近但粒度不同, 需重做 |
| CDI (#20) | 1 | 想过, 需做 |
| Denial Appeals (#12) | 1 | metadata_only pack, 无 impl |
| Surgical Registry (#7) | 0 | 完全缺 |
| ICU Admission (#8) | 0 | 完全缺 |
| Triage (#9) | 0 | 完全缺 |
| Medication Reconciliation (#11) | 0 | 完全缺 |
| Patient Discharge Education (#13) | 0 | 完全缺 |
| Nursing Shift Handoff (#14) | 0 | 完全缺 |
| Prior Authorization (#15) | 0 | 完全缺 |
| Referral Generator (#16) | 0 | 完全缺 |
| Clinical Education (#17) | 0 | 完全缺 |
| Clinical Guidelines (#19) | 0 | 完全缺 |
| Rule Explainer (#2) | 0 | 完全缺 |

**维度得分**: **28/100** = 1.4/5

**证据**: `backend/official_agents/` (16 dirs, 仅 2 real), `docs/corti-feature-inventory.md:74-99` (20 Pre-built Agents 清单)

**最大差距**: 17 个 Pre-built Agents 完全缺, 10 个 metadata-only packs 无真实 impl.

**所需行动**: Stage 3 — Phase 3 列入 20 Pre-built Agents 复刻 roadmap (大坑, 不在 P1.3 范围).

---

### 维度 15 — A2A 协议

**Corti baseline**: A2A (Agent-to-Agent) 协议 — User / A2A Client / A2A Server 三角色 + Agent Card (JSON-LD schema) + Task (5 态: submitted→working→input-required/completed/failed/canceled) + Message (role: user/agent) + Part (TextPart/DataPart/FilePart) + Artifact.

**iCoDer 现状**: `app/icoder/agent_runtime/a2a/` 13 文件 — envelope/agent_card/messages/parts/errors/icoder_metadata/routes_inbound/outbound/discovery/task_stub/schema_registry/version/a2a_routes. spec 草稿完整 (`docs/ICODER_V1_A2A_SPEC.md`). 但 routes_task_stub 是 stub, 真实 A2A 任务流未跑通. 旧 `app/agents/orchestrator.py` 不走 A2A.

| 子项 | 分数 | 理由 |
|---|---|---|
| A2A 三角色 | 4 | spec + envelope 已对齐 |
| Agent Card (JSON-LD) | 4 | agent_card.py 已对齐 |
| Task 5 态 | 2 | routes_task_stub.py 是 stub |
| Message (role) | 4 | messages.py 已对齐 |
| Part (Text/Data/File) | 4 | parts.py 已对齐 |
| Artifact | 2 | 概念有, 未真实产出 |
| A2A 真实任务流跑通 | 1 | stub 状态 |

**维度得分**: **21/35** = 3.0/5

**证据**: `backend/app/icoder/agent_runtime/a2a/` (13 文件), `docs/ICODER_V1_A2A_SPEC.md`, `docs/corti-reverse-engineered/docs-site/_extracted/agentic_core-concepts.md`

**最大差距**: Task 5 态 + Artifact + 真实任务流未跑通.

**所需行动**: Stage 3 — Phase 2 实施 A2A 真实任务流 (P1.3 范围外, 但需明确 roadmap).

---

### 维度 16 — MCP 协议

**Corti baseline**: MCP (Model Context Protocol) — Expert 暴露 `tools/list` + `tools/call`, JSON-RPC 2.0, Tools/Resources/Prompts, Transport stdio 默认 + HTTP Phase 4.

**iCoDer 现状**: `app/icoder/mcp/` 7 文件 — server.py + tool_registry.py + errors.py + handlers/ (5 handlers: search_icd/verify_code/get_differentiation_hint/rerank_codes/calibrate_confidence). `/mcp/v1/tools/list` + `/mcp/v1/tools/call` 端点已实装 (M2 阶段). Mode StrEnum SSOT.

| 子项 | 分数 | 理由 |
|---|---|---|
| `tools/list` + `tools/call` | 4 | M2 已实装 |
| JSON-RPC 2.0 信封 | 4 | 已对齐 |
| Tools/Resources/Prompts | 3 | Tools 完整, Resources/Prompts 缺 |
| stdio transport | 3 | 部分, HTTP 已有 |
| 5 tool handlers | 5 | M2 已实装 |
| Expert as MCP client | 2 | 概念有, 未真实跑通 |

**维度得分**: **21/30** = 3.5/5

**证据**: `backend/app/icoder/mcp/` (7 文件), `docs/ICODER_V1_MCP_SPEC.md`

**最大差距**: Resources/Prompts 缺, Expert 作为 MCP client 未跑通.

**所需行动**: Stage 3 列入 roadmap (Phase 2 完整化).

---

### 维度 17 — Context / Memory

**Corti baseline**: Context (短期, SQLite) + Memory (长期, BGE-M3+FAISS) + contextId UUID v4 服务端生成 + 三层隔离 (数据/状态/缓存) + PHI 强制脱敏 (redacted=1 不可改) + GC 策略 (24h active + 7d 物理删除 + 90d audit 独立 retention).

**iCoDer 现状**: `app/icoder/agent_runtime/context/` 11 文件 — context/context_audit/context_garbage_collector/context_id/context_isolation/context_lifecycle/context_repository/context_status/db_models/db_schema.sql/icoder_metadata. `app/services/memory_expert.py` 271 LOC. `app/models/memory.py`. PHI redactor 已实装 (`app/services/phi_redactor.py` 72 LOC).

| 子项 | 分数 | 理由 |
|---|---|---|
| contextId UUID v4 服务端生成 | 4 | context_id.py 已对齐 |
| Context 对象 (messages/tasks/artifacts/metadata) | 4 | context.py 已对齐 |
| 三层隔离 (数据/状态/缓存) | 3 | context_isolation.py 部分 |
| Context/Memory 边界 (短期 vs 长期) | 3 | memory_expert.py 部分 |
| PHI 强制脱敏 | 4 | phi_redactor.py 已对齐 |
| GC 策略 (24h/7d/90d) | 3 | context_garbage_collector.py 部分 |
| 真实 Context 跑通 | 2 | 概念有, 主线未跑 |

**维度得分**: **23/35** = 3.29/5

**证据**: `backend/app/icoder/agent_runtime/context/` (11 文件), `backend/app/services/memory_expert.py` (271 LOC), `docs/ICODER_V1_CONTEXT_SPEC.md`

**最大差距**: Context/Memory 真实跑通 + 三层隔离 + GC 策略主线未用.

**所需行动**: Stage 3 — Phase 2 完整化 Context 真实跑通.

---

### 维度 18 — Authentication (OAuth 2.0 + Keycloak)

**Corti baseline**: OAuth 2.0 client_credentials + Keycloak IdP + 5 分钟 short-lived tokens + scope (transcribe/streams/textgen/facts) + tenant 隔离 + realm-based token URL.

**iCoDer 现状**: Phase 1.0 (4 gap closed) — TenantHeaderMiddleware + 5min client_credentials TTL + capability scopes (transcribe/streams/textgen/facts) + realm-based token URL. 但**不走 Keycloak**, 自实现 JWT (`app/api/oauth.py` 449 LOC + `app/api/auth.py` 435 LOC).

| 子项 | 分数 | 理由 |
|---|---|---|
| OAuth 2.0 client_credentials | 5 | Phase 1.0 已对齐 |
| 5min short-lived tokens | 5 | Phase 1.0 已对齐 |
| capability scopes (transcribe/streams/textgen/facts) | 5 | Phase 1.0 已对齐 |
| realm-based token URL | 5 | Phase 1.0 已对齐 |
| tenant 隔离 (Tenant-Name header) | 5 | TenantHeaderMiddleware 已对齐 |
| Keycloak IdP | 2 | 自实现 JWT, 非 Keycloak |

**维度得分**: **27/30** = 4.5/5

**证据**: `backend/app/api/oauth.py` (449 LOC), `backend/app/middleware/tenant_extractor.py`, `docs/PHASE_1_0_OAUTH_CORTI_PARITY.md` (memory)

**最大差距**: 不走 Keycloak (自实现 JWT, 功能等价但非 Corti 同 IdP).

**所需行动**: 评估是否上 Keycloak (高代价, 可放缓; 功能已等价).

---

### 维度 19 — 视觉设计系统

**Corti baseline**: Mono 配色 (off-white #FAFAFA + 纯白面板 + 1px 浅灰分隔 + 主 CTA 全黑 #000000 + 中性灰文字 + 唯一彩色 lime-yellow BETA 徽章 + Embedded 蓝 #3C61DD) + Inter 字体 + 8px 圆角 + 8px grid + Lucide 图标 + 极少阴影 + Primary button 实心黑 + Multi-select chip + Segmented control + Toast 右下浮动.

**iCoDer 现状**: Tailwind CSS + Lucide icons 已用. 但配色未严格 mono (有 primary 色但非全黑 CTA), 字体未统一 Inter, 圆角未规范 8px, Theme toggle 缺 (维度 13 已识别). 设计 token 未抽离.

| 子项 | 分数 | 理由 |
|---|---|---|
| Mono 配色 + 黑 CTA | 3 | 部分, primary 色非全黑 |
| Inter 字体 | 3 | 部分, 未统一 |
| 8px 圆角 + 8px grid | 3 | 大致, 未规范化 |
| Lucide 图标 | 5 | 已用 |
| Primary button 实心黑 | 3 | 部分 |
| Multi-select chip | 3 | 部分 |
| Segmented control | 3 | 部分 |
| Toast 右下浮动 | 4 | 已对齐 |
| 设计 token 抽离 | 2 | 未抽离 |

**维度得分**: **26/45** = 2.89/5

**证据**: `frontend/src/index.css`, `frontend/tailwind.config.js` (assumed), `docs/corti-reverse-engineered/SUMMARY.md:470-540` (Corti 视觉系统)

**最大差距**: 设计 token 未抽离, 配色/字体/圆角未严格对齐 Corti.

**所需行动**: Stage 6 — 抽离设计 token, 统一 mono 配色 + Inter + 8px 圆角.

---

### 维度 20 — 文档站 (Mintlify + llms.txt)

**Corti baseline**: Mintlify 自部署 docs.corti.ai + `llms.txt` (AI ingestion 友好) + 27 详细页面 + 377 索引 + product positioning + architecture 显式章节 + 5 分钟新人了解全局.

**iCoDer 现状**: `docs/` 90+ markdown 文件 + 11 子目录. 无 Mintlify, 无 `llms.txt`, 无文档站构建. CLAUDE.md 是项目说明但非文档站入口. `docs/README.md` 是入口但未对齐 Corti 文档结构. 90+ 文件混杂 (historical + mainline + specs), 不便新人快速了解.

| 子项 | 分数 | 理由 |
|---|---|---|
| Mintlify 文档站 | 0 | 完全缺 |
| `llms.txt` | 0 | 完全缺 |
| 27 详细页面 | 3 | 有 90+ 文件但混杂 |
| 377 索引 | 0 | 无索引 |
| product positioning 显式章节 | 2 | CLAUDE.md 有, 但文档站无 |
| architecture 显式章节 | 2 | 同 |
| 5 分钟新人了解 | 2 | 90+ 文件不便快速了解 |
| `docs/README_INDEX.md` | 0 | 缺 (Stage 4 要建) |

**维度得分**: **9/40** = 1.125/5

**证据**: `docs/` (90+ 文件), `docs/corti-reverse-engineered/docs-site/_extracted/` (Corti Mintlify 提取)

**最大差距**: 无 Mintlify + 无 llms.txt + 无文档索引.

**所需行动**: Stage 4 — 建 `docs/README_INDEX.md` + 7 份方向性文档 (PRODUCT_DIRECTION/CURRENT_ARCHITECTURE/MAINLINE_VS_LEGACY/CORTI_PARITY_ROADMAP/PRODUCT_BACKLOG/TECH_DEBT_BACKLOG/README_INDEX). Mintlify + llms.txt 列入 Phase 4.

---

## 2. 评分汇总

| # | 维度 | 得分 | 标准化 (x5) |
|---|---|---|---|
| 1 | 产品定位与哲学 | 14/25 | 2.80 |
| 2 | 架构层 (4 域名 + 第三方) | 18/40 | 2.25 |
| 3 | Sidebar IA (15 feature) | 18/30 | 3.00 |
| 4 | Project Home 4 tabs | 4/15 | 1.33 |
| 5 | AI Studio 工作台通用模式 | 23/35 | 3.29 |
| 6 | Medical Coding API 契约 | 28/30 | 4.67 |
| 7 | Fact Extraction API 契约 | 23/25 | 4.60 |
| 8 | Text Generation API 契约 (5 endpoints) | 23/25 | 4.60 |
| 9 | Speech-to-Text API 契约 (3 endpoints) | 20/25 | 4.00 |
| 10 | Embedded Assistant (proxy 模式) | 10/30 | 1.67 |
| 11 | 数据模型 (PostgREST 表) | 27/40 | 3.38 |
| 12 | Edge Functions (7 项) | 22/35 | 3.14 |
| 13 | 顶部全局元素 | 20/40 | 2.50 |
| 14 | 20 Pre-built Agents 清单 | 28/100 | 1.40 |
| 15 | A2A 协议 | 21/35 | 3.00 |
| 16 | MCP 协议 | 21/30 | 3.50 |
| 17 | Context / Memory | 23/35 | 3.29 |
| 18 | Authentication (OAuth 2.0) | 27/30 | 4.50 |
| 19 | 视觉设计系统 | 26/45 | 2.89 |
| 20 | 文档站 (Mintlify + llms.txt) | 9/40 | 1.13 |

**总分 (标准化 5 分制, 加权平均)**: **(2.80+2.25+3.00+1.33+3.29+4.67+4.60+4.60+4.00+1.67+3.38+3.14+2.50+1.40+3.00+3.50+3.29+4.50+2.89+1.13) / 20 = 65.94/100 / 5 = **3.30/5**

**总分 (百分制)**: **65.94/100**

---

## 3. 总体判断

### 3.1 Verdict

> **PARTIALLY_ALIGNED**

iCoDer 当前与 Corti baseline 总体得分 65.94/100 (3.30/5), 处于"部分对齐"状态. 核心矛盾是: **API 契约层已高度对齐 (维度 6-9 平均 4.5+), 但产品形态层严重偏离 (维度 4 Home 4 tabs 1.33 / 维度 14 Pre-built Agents 1.40 / 维度 20 文档站 1.13)**.

### 3.2 已对齐 (score ≥ 4.0)

| 维度 | 得分 | 状态 |
|---|---|---|
| 6 Medical Coding API | 4.67 | ✅ Phase 1.1 已对齐 |
| 7 Fact Extraction API | 4.60 | ✅ Phase 1.2/1.3 已对齐 |
| 8 Text Generation API | 4.60 | ✅ Phase 1.2 已对齐 |
| 9 Speech-to-Text API | 4.00 | ✅ Phase 1.3 已对齐 |
| 18 Authentication | 4.50 | ✅ Phase 1.0 已对齐 |

**5 项已对齐, 总分 22.37/25 = 89.5%** — 这是 iCoDer Phase 1.0-1.3 的成果, API 契约层已闭环.

### 3.3 部分对齐 (2.0 ≤ score < 4.0)

| 维度 | 得分 | 主要差距 |
|---|---|---|
| 1 产品定位 | 2.80 | MedCodER 仍当主线, 多 Agent + Workflow 未落地 |
| 2 架构层 | 2.25 | Keycloak/PostHog/Stripe/Mintlify 缺 |
| 3 Sidebar IA | 3.00 | 段顺序未对齐, Medical Coding 位置偏离 |
| 5 工作台通用模式 | 3.29 | 5 tool 不共享 layout |
| 11 数据模型 | 3.38 | 命名分散 (organization vs projects) |
| 12 Edge Functions | 3.14 | 4 项缺或 stub |
| 13 顶栏元素 | 2.50 | Theme toggle + Reset + PostHog 缺 |
| 15 A2A 协议 | 3.00 | Task 5 态 + Artifact + 真实任务流未跑 |
| 16 MCP 协议 | 3.50 | Resources/Prompts + Expert as client 缺 |
| 17 Context/Memory | 3.29 | 真实 Context 跑通 + 三层隔离 + GC 缺 |
| 19 视觉设计系统 | 2.89 | 设计 token 未抽离, 配色/字体未统一 |

**11 项部分对齐, 总分 32.34/55 = 58.8%** — 这是 P1.3 主要纠偏目标.

### 3.4 严重偏离 (score < 2.0)

| 维度 | 得分 | 主要差距 |
|---|---|---|
| 4 Project Home 4 tabs | 1.33 | HomePage 非 4 tabs 模式 |
| 10 Embedded Assistant proxy | 1.67 | 独立子域 + tRPC + 第三方 relay 缺 |
| 14 Pre-built Agents (20) | 1.40 | 17 个完全缺, 10 metadata-only 无 impl |
| 20 文档站 | 1.13 | Mintlify + llms.txt + 索引缺 |

**4 项严重偏离, 总分 5.53/20 = 27.6%** — 这是 Stage 3 方向纠偏的重点.

### 3.5 不在 P1.3 范围 (列入 Phase 2-4 roadmap)

| 维度 | 列入 Phase |
|---|---|
| 2 第三方基础设施 (PostHog/Stripe/Intercom/Mintlify) | Phase 4 |
| 10 Embedded Assistant 子域 proxy | Phase 4 |
| 14 Pre-built Agents 17 个缺 | Phase 3 |
| 15 A2A 真实任务流 | Phase 2 |
| 16 MCP Resources/Prompts + Expert as client | Phase 2 |
| 17 Context 真实跑通 | Phase 2 |
| 12 Edge Functions 4 项 stub | Phase 2 |

### 3.6 P1.3 范围内可纠偏 (Stage 3-6 行动项)

| 维度 | 行动 | Stage |
|---|---|---|
| 1 产品定位 | MedCodER 降级为 Pre-built Agent, 平台定位重写 | Stage 3 + 4 |
| 3 Sidebar IA | 段顺序对齐 Corti, Medical Coding 降为 AI Studio 第 7 子页 | Stage 6 |
| 4 Project Home 4 tabs | 重写 HomePage 为 4 tabs (Transcribe/Document/Chat/Code) | Stage 6 |
| 5 工作台通用模式 | 抽离 5 tool 共享 layout 组件 | Stage 6 |
| 13 顶栏 Theme toggle + Reset | 加 Theme toggle + Reset live cost | Stage 6 |
| 19 视觉设计系统 | 抽离设计 token, 统一 mono + Inter + 8px | Stage 6 |
| 20 文档站 | 建 README_INDEX + 7 份方向性文档 (Mintlify 留 Phase 4) | Stage 4 |

---

## 4. 关键洞察

### 4.1 iCoDer 已完成"API 契约层闭环"但未完成"产品形态层闭环"

5 个 API 契约维度 (6-9, 18) 平均 4.5+, 说明 Phase 1.0-1.3 的工作扎实. 但产品形态层 (Home 4 tabs / Sidebar IA / 工作台通用模式 / 顶栏 / 视觉系统 / 文档站) 平均仅 2.5, 说明 iCoDer 仍是"API 端点的杂乱集合", 不是"Corti-style 统一产品".

### 4.2 MedCodER 是产品形态层偏离的根因

CLAUDE.md 仍把 MedCodER 5-stage pipeline + NAACL 2025 + 4 ablation variant 当主线描述, 导致:
- HomePage 不是 4 tabs 而是 MedicalCoding 入口
- Sidebar 把 Medical Coding 当首页主入口 (Corti 是 AI Studio 最后一个)
- 5 tool 不共享 layout 因为 MedicalCodingPage 760 LOC 独立实现
- 视觉系统未抽离因为 MedCodER DiagnosisCard 等组件特殊化
- 文档站 90+ 文件混杂因为 MedCodER 评估系列文档占大头

**根因**: MedCodER 被当作产品本体, 而非 Pre-built Agent #18.

### 4.3 三套 Agent 架构并存是 Agentic Framework 维度 (15-17) 偏离的根因

Legacy `app/agents/orchestrator.py` + Legacy `icoder_runtime/agent_runner.py` + 新 `app/icoder/agent_runtime/` 三套并存. 新 Agentic Framework (A2A + MCP + Context) spec 完整但未真实跑通, 因为实际运行的是 Legacy 单体.

### 4.4 17 个 Pre-built Agents 缺失是 Phase 3 大坑

iCoDer 仅 3/20 对齐, 17 个完全缺. 这是 Corti 复刻最大的工作量, 不在 P1.3 范围, 但需在 Stage 3 roadmap 明确.

### 4.5 第三方基础设施缺是 Phase 4 部署对齐的难点

PostHog 自部署 / Stripe 全套 / Intercom / Mintlify / Keycloak 等第三方基础设施完全缺. 这是 Corti 复刻的"非编码"工作, 但影响产品气质.

---

## 5. Stage 3 输入要求

基于本 gap analysis, Stage 3 方向纠偏方案必须明确:

1. **最大偏差**: MedCodER 被当作产品本体 (维度 1 + 3 + 4 + 5 + 19 共同根因)
2. **哪些模块偏向"医疗编码单点工具"**: MedCodER 5-stage pipeline + 14-stage coding review + 10 builtin methods (已删) + MethodCompare (已删) + Doctor 自检 + F1 评估 / Gold case / Pilot 系列
3. **哪些模块偏向"普通 SaaS 后台"**: organization/team/billing/usage/customers/templates/settings (维度 11-12 部分对齐)
4. **哪些符合 Corti 方向**: v2_tools_* API + oauth + runtime_platform + app/icoder/agent_runtime/ (A2A+MCP+Context+Experts+Orchestrator) + 2 real Agent packs + 4 atomic expert packs
5. **应降级**: MedCodER 整套 (从产品本体降为 Pre-built Agent #18)
6. **应归档**: 90+ 历史文档 + icoder-next + corti-crawl/contracts/ui_contracts + .corti-user-data
7. **应删除**: P0 7 项 (Stage 1 已列)
8. **新的主线定义**: Corti-style 医疗 Agent Runtime 平台 (Platform = Runtime + A2A + MCP + Context + 20 Pre-built Agents; MedCodER = Pre-built Agent #18)
9. **主导航建议**: Sidebar 4 段 (Top/AI Studio/Manage/Support) + AI Studio 7 子页顺序 + Medical Coding 降为 AI Studio 第 7 子页 + Project Home 4 tabs (Transcribe/Document/Chat/Code)

---

## Stage 2 完成, 等待继续指令。
