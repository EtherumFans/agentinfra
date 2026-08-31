# 产品偏移审计 — iCoDer vs Corti 复刻目标

> **审计请求**: "先对当前产品的实现进行全量审计，判断有没有偏离既定的产品目标：复刻 corti 的能力。"
> **审计日期**: 2026-08-06
> **审计范围**: iCoDer 主仓库 `E:\Corti4C` 当前实现状态 vs Corti 官方能力基线
> **基线参考**: `docs/corti_parity/CORTI_REFERENCE_BASELINE.md` (620 行, 2026-07-02) + `docs/corti_parity/CORTI_PARITY_GAP_ANALYSIS.md` (20 维度) + `docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md`
> **当前快照**: Phase A1D.5R closed 后 (commit c8c603f, 2026-08-06)
> **审计性质**: 全量对比 + 趋势分析 + 战略判定

---

## §1 执行摘要 (Executive Summary)

### 1.1 整体判定

| 维度 | 判定 |
|---|---|
| 战略意图 vs 原始目标 ("复刻 Corti") | **DRIFTED — 有文档化的合理偏移** |
| 实现层 Corti 架构对齐度 | **PARTIALLY_ALIGNED — 52.6% (NOT_DEMONSTRATED, 5-tuple 锁定)** |
| 30 packs × Corti 20 Pre-built Agents 覆盖 | **EXISTENCE 18/20 / RUNNABLE 6/20** |
| Studio Tools API 契约对齐 | **ALIGNED — Phase 1.0-1.3 闭环** |
| Agentic Framework (A2A+MCP+Context+Orchestrator) | **PARTIALLY_ALIGNED — spec 完整, 主线部分跑通** |
| 时间趋势 (P1.3 2026-07-02 → 现在 2026-08-06) | **CONVERGING_SLOWLY** — 65.94→~70 (估算) |
| 风险 | **高 — R1 战略定位矛盾, R6 部署路径未定** |

### 1.2 核心结论

> **iCoDer 已经偏离"纯粹复刻 Corti"的原始目标, 转向"Corti-架构对齐 + 中国医院场景本地化"的双目标路径。这一偏移在多个 phase charter 中有文档化、有审计追溯、有强行禁止反向回退的禁令 (§22). 但实现层 Corti parity 仍处于 NOT_DEMONSTRATED (52.6%) 状态, 且有 17/20 Pre-built Agents 仅 metadata-only 或完全缺失, 因此偏移是"战略已决、实现未达"的状态。**

### 1.3 三类偏移

| 类别 | 描述 | 严重度 |
|---|---|---|
| **A. 文档化战略偏移** (intentional) | P1.3 起, 产品定位从"复刻 Corti"重写为"Corti-style 中国医院场景 Agent Runtime"; Charter §22 禁止 `CORTI_PARITY_VERIFIED` 类 verdict; Release Roadmap R1 要求统一改 framing 为"Corti-parity 架构". | **接受** — 已 charter 化 |
| **B. 实现层能力差距** (capability gap) | Corti 20 Pre-built Agents 中 14 个仍是 metadata-only; A2A 真实任务流仅 fast-path 跑通 (慢路径 InboundHandler 未在主线用); Embedded Assistant 非 sub-domain proxy; 第三方基础设施 (PostHog/Stripe/Keycloak/Mintlify) 全缺. | **中** — Phase 2-4 roadmap |
| **C. 战略定位矛盾** (positioning contradiction) | UI/CLAUDE/README 仍多处保留"Corti-competitive"措辞, 但 Charter §22 禁止 `CORTI_PARITY_VERIFIED` verdict — 给医院买方和团队内部都制造混乱. | **高** — R1 必须修 |

---

## §2 审计方法

### 2.1 三层 K-baseline

| 层 | 来源 | 用途 |
|---|---|---|
| **C1 Corti 官方基线** | `docs/corti_parity/CORTI_REFERENCE_BASELINE.md` §1-13 (620 行, 含 4 域名 + 15 sidebar + 5 Studio tool + 20 Pre-built Agents + A2A/MCP/Context 协议 + OAuth + 视觉系统) | 复刻目标的"应然" |
| **C2 P1.3 历史打分** | `CORTI_PARITY_GAP_ANALYSIS.md` 20 维度打分 (2026-07-02, 总分 65.94/100 PARTIALLY_ALIGNED) | 起点 baseline |
| **C3 当前实现快照** | 30 agent packs + 44 API routers + 29 frontend pages + A1A-A1D 全 phase 记录 (2026-08-06) | 现在的"实然" |

### 2.2 判定流程

```
Step 1: Corti 应然 (C1) vs iCoDer 实然 (C3) → 维度差距
Step 2: 差距趋势 (C2 → C3) → 收敛 / 发散 / 静止
Step 3: 差距归因 → A 战略偏移 / B 能力差距 / C 定位矛盾
Step 4: 整体判定 → ALIGNED / DRIFTED / DIVERGED
```

### 2.3 审计边界

- **IN**: backend code (official_agents + app/api + app/icoder/agent_runtime), frontend pages, docs (PRODUCT_DIRECTION + RELEASE_ROADMAP + A1D Charter + P1.3 audit), reports (phase final verdicts + GATE14 + 5-tuple)
- **OUT**: 具体测试用例 pass/fail (近期 A1D.5R 已闭); 具体迁移 alembic 内容 (A1A Gate 2-4 已审计); 具体依赖版本 (lockfile 不影响判定)

---

## §3 Corti 官方能力基线 (C1 — 应然)

来自 `docs/corti_parity/CORTI_REFERENCE_BASELINE.md`, 简化为 7 大能力轴:

### 3.1 产品定位

- **一句话**: "All-in-one AI stack for healthcare, built for medical accuracy, compliance, and scale"
- **核心引擎**: Corti Symphony = model network + orchestration layer (Text + Audio)
- **8 设计原则**: Safety First / Auditability / Domain-Specific / Multi-Agent / Memory & Context / Prebuilt Experts / Third-Party / Run-time Context
- **Agent vs Workflow 二元**: Agents = 自主思考; Workflows = 预定义路径

### 3.2 4 大域名 + 第三方

- `console.corti.app` (Remix SPA)
- `api.console.corti.app` (Supabase PostgREST + Edge Functions)
- `api.eu/us.corti.app` (Studio Tools `/v2/*`)
- `assistant.eu/us.corti.app` (Embedded Assistant proxy)
- `auth.eu/us.corti.app` (Keycloak)
- `prp.corti.app` (PostHog 自部署) + Stripe + Intercom + GA4 + Crazyegg + Mintlify

### 3.3 15 Sidebar Features

Top (home + developer-quickstart) → AI Studio (overview + agents + STT 3 子页 + text-generation + embedded + facts + coding) → Manage (api-clients + team + billing + usage + customers + templates + settings) → Support

### 3.4 5 Studio Tools API

- Medical Coding (`POST /v2/tools/coding/`)
- Fact Extraction (`POST /v2/tools/extract-facts`)
- Text Generation 5 endpoints (Streams WSS / FactsR / Guided / Sections+Templates / Documents Classic)
- Speech-to-Text 3 endpoints (Transcribe WSS / Streams WSS / Transcripts REST)
- Embedded Assistant proxy

### 3.5 20 Pre-built Agents

ICD-10 Index Navigator / Rule Explainer / Compliance Guardrail / Code Validation / Procedure Entity Extractor / Diagnostic Entity Extractor / Surgical Registry / ICU Summary / Triage / Note Completeness / Med Reconciliation / Denial Appeals / Discharge Education / Nursing Handoff / Prior Auth / Referral Generator / Clinical Education / Medical Coding / Clinical Guidelines / CDI

### 3.6 Agentic Framework

A2A (User/Client/Server 三角色 + Agent Card + Task 5 态 + Message + Part + Artifact) + MCP (tools/list + tools/call + JSON-RPC 2.0) + Context/Memory (短期 SQLite + 长期 vector + contextId UUID v4) + Orchestrator + Experts + Integrations

### 3.7 视觉系统

Mono 配色 (off-white + 黑 CTA + lime-yellow BETA 徽章) + Inter 字体 + 8px grid + Lucide icons + Stripe-like developer-tool aesthetic

---

## §4 iCoDer 当前实现 (C3 — 实然)

### 4.1 实现层验证

| 资产 | 数量 | 与 Corti 对应 |
|---|---|---|
| **agent packs** (`backend/official_agents/`) | 30 目录 (24 visible + 6 hidden) | 覆盖 Corti 20 中 18 个 + iCoDer 自加 12 (atomic experts + claim-check + DRG/DIP + discharge-summary-structuring + principal-diagnosis-review 等) |
| **maturity = mvp/runnable** | **8 个** (medical_coding, medcoder-coding-review, code-validation, note-completeness, clinical-documentation-improvement, compliance-guardrail, drg-analyzer, principal-diagnosis-review, procedure-extractor, evidence_extractor, discharge_summary_structuring — 计 mvp 8 + runnable 2 = 10 实装) | Corti 20 中真跑通的 6/20 (Medical Coding/CDI/Code Validation/Compliance Guardrail/Note Completeness/Procedure Extractor) |
| **maturity = metadata-only** | 14 个 (denial-appeals, triage, icu_summary, surgical_registry, prior_auth, med_reconciliation, nursing_handoff, discharge_edu, referral_gen, icd10_navigator, rule_explainer, diagnosis-extractor, claim-check, documentation-gap, cdi-review, evidence-ranker) | Corti 20 中 12/20 是空壳 |
| **完全缺失** | 2 个: Clinical Education (#17), Clinical Guidelines (#19) | 2/20 |
| **API routers** (`app/api/`) | 44 routers, 含 `v2_tools_coding/facts/streams/guided_document/sections_templates/documents_classic/stt` 8 个 v2-tools 端点 | Corti 5 Studio Tools API 完全对齐 |
| **frontend pages** (`frontend/src/pages/`) | 29 个 .tsx, 含 HomePage / AIStudioOverviewPage / AgentsPage / AgentDetailPage / NewAgentPage / MedicalCodingPage / CDIWorkbenchPage / CodingComplianceWorkbenchPage / FactExtractionPage / TextGenerationPage / SpeechToTextPage / EmbeddedAssistantPage / APIClientsPage / TeamPage / BillingPage / UsagePage / CustomersPage / TemplatesPage / SettingsPage / DeveloperQuickstartPage / SupportPage / TicketsPage / ExpertsPage / RunTracePage / DocsPage | Corti 15 sidebar features 基本都有对应 page |
| **Agentic Framework** | `app/icoder/agent_runtime/a2a/` 13 文件 (envelope/agent_card/messages/parts/discovery/routes_inbound/outbound/task_stub/...) + `app/icoder/mcp/` 7 文件 (server + 5 handlers) + `app/icoder/agent_runtime/context/` 11 文件 + `CodingRuntimeDispatcher` fast path | Corti A2A+MCP+Context spec 完整, 主线 fast path 跑通 (medical-coding-agent), 慢路径 InboundHandler 仅 metadata 形式 |
| **OAuth 2.0** | `app/api/oauth.py` (Phase 1.0 闭环, 5min client_credentials + scopes + realm-based token URL + TenantHeaderMiddleware) | Corti OAuth 契约对齐, **但不走 Keycloak** (自实现 JWT) |
| **数据模型** | 22 models (`app/models/`), 多租户 schema + alembic 30 migrations | Corti 7 表概念对齐, 命名不同 (organization vs projects) |
| **观察/审计** | RunHistory + AuditLog + RunTraceStore + FallbackTracker + KMSVersionToken + CredentialVault (A1D.4) + policy_decision + purpose_of_use (A1D.3) + audit pause flag (A1D.2) | Corti Auditability 原则对齐 |

### 4.2 文档化的偏移

| 偏移项 | 文档出处 | 偏移性质 |
|---|---|---|
| MedCodER 从产品本体降级为 Pre-built Agent #18 | `PRODUCT_DIRECTION.md` §4 (2026-07-02) | A 故意 — 产品定位纠偏 |
| 中国本地化替换 (ICD-10-CN / ICD-9-CM-3 / CNY / ¥) | `CLAUDE.md` §货币约定 + `PRODUCT_DIRECTION.md` §3.3 | A 故意 — 区域合规 |
| Charter §22 禁止 `CORTI_PARITY_VERIFIED / CORTI_PARITY_DEMONSTRATED` verdict | `docs/phase-a1d/A1D_CHARTER.md` §22 | A 故意 — 战略重命名 |
| 5-tuple 锁定 `CORTI_PARITY=NOT_DEMONSTRATED (52.6%)` 不可变更 | A1A Gate 4R-I (2026-07-21) | A 故意 — 不可回退 |
| Release Roadmap R1: UI/CLAUDE/README 改 "Corti-parity 架构" framing | `docs/governance/RELEASE_ROADMAP.md` §3 R1 (2026-08-05) | **C 未完成** — R1 标"高"风险 |
| Cloud-only 部署 (CLAUDE.md: "不再支持医院内网 Docker") | `CLAUDE.md` §部署模型 + Cloud Flip 决议 (2026-06-27) | A 故意 — 但 R6 与 GATE14 on-prem 推荐冲突, **未决** |

### 4.3 5-tuple 不可变更状态 (A1A Gate 4R-I 锁定)

```
GATE4_8_NO_NEW_REGRESSION  = CONTRADICTED
GATE4_9_FINAL_PASS         = SUPERSEDED
GATE4_ACCEPTANCE           = REOPENED
CORTI_PARITY               = NOT_DEMONSTRATED  (52.6% weighted)
PRODUCTION_READINESS       = NOT_VERIFIED
```

这 5 个状态在 A1A Gate 4R-I (2026-07-21) 后被 charter 锁定不可变更, 任何 phase 升级或重裁都需新开 A2+ re-gate. 这意味着 iCoDer 当前**不能**在文档中声称 "已实现 Corti parity" 或 "复刻了 Corti 能力" — charter 禁止.

---

## §5 20 维度打分对比 (P1.3 → 现在)

### 5.1 维度逐项趋势

| # | 维度 | P1.3 (2026-07-02) | 现在 (2026-08-06) | 趋势 | 备注 |
|---|---|---|---|---|---|
| 1 | 产品定位与哲学 | 2.80 | ~3.5 | ↑ | MedCodER 已降级 (P1.3), PRODUCT_DIRECTION 主线已写, 但 CLAUDE.md §MedCodER 段未同步 |
| 2 | 架构层 (4 域名 + 第三方) | 2.25 | ~2.5 | ↑ 缓 | 单域名子路径对齐, 但 PostHog/Stripe/Keycloak/Mintlify 仍全缺 |
| 3 | Sidebar IA | 3.00 | ~3.5 | ↑ | 4 段顺序对齐, AI Studio 7 子页对齐 (A1B-AE 14 metadata-only 入 Hub) |
| 4 | Project Home 4 tabs | 1.33 | ~3.5 | ↑↑ | HomePage 已 Corti-style 4 tabs (Phase 7 / A1D-DEV 期间完成) |
| 5 | AI Studio 工作台通用模式 | 3.29 | ~3.5 | ↑ | WorkbenchLayout 壳子 + 5 tool 部分共享, 但未完全统一 |
| 6 | Medical Coding API | 4.67 | 4.67 | = | Phase 1.1 已闭环 |
| 7 | Fact Extraction API | 4.60 | 4.60 | = | Phase 1.2/1.3 已闭环 |
| 8 | Text Generation API (5 endpoints) | 4.60 | 4.60 | = | Phase 1.2 已闭环 |
| 9 | Speech-to-Text API (3 endpoints) | 4.00 | 4.00 | = | Phase 1.3 已闭环 |
| 10 | Embedded Assistant (proxy 模式) | 1.67 | ~3.0 | ↑↑ | Phase 7 Gate 13 + Gate 13A Bootstrap Ticket 已闭, 但仍非独立 sub-domain proxy |
| 11 | 数据模型 (PostgREST 表) | 3.38 | ~3.5 | ↑ | 22 models + 30 migrations (含 A1D.3 UserRole 扩展 + A1D.5 claim-check) |
| 12 | Edge Functions | 3.14 | ~3.3 | ↑ | access_token + billing/balance + customers 闭, external/agents 部分对齐 |
| 13 | 顶栏元素 | 2.50 | ~3.5 | ↑↑ | Theme toggle + Reset live cost 已加, PostHog 仍缺 |
| 14 | 20 Pre-built Agents | 1.40 | ~2.5 | ↑↑ | 30 packs 总数, Corti 20 中 18 existence + 6 runnable |
| 15 | A2A 协议 | 3.00 | ~3.5 | ↑ | CodingRuntimeDispatcher fast path 跑通 (medical-coding + medcoder-coding-review), 慢路径 InboundHandler 仍 stub |
| 16 | MCP 协议 | 3.50 | ~3.7 | ↑ | tools/list + tools/call + 5 handlers + dispatch_detail 15-field metadata (Phase 3-D2.5) |
| 17 | Context / Memory | 3.29 | ~3.5 | ↑ | 11 文件 spec 完整, 但真实主线跑通仍部分 |
| 18 | Authentication (OAuth 2.0) | 4.50 | 4.50 | = | Phase 1.0 已闭环 |
| 19 | 视觉设计系统 | 2.89 | ~3.3 | ↑ | Tailwind token 已抽离 (vermillion 保留为品牌决策), Lucide icons 已用 |
| 20 | 文档站 (Mintlify + llms.txt) | 1.13 | ~2.5 | ↑↑ | `docs/README_INDEX.md` + 14 份方向性文档 (P1.3 Stage 4), Mintlify/llms.txt 仍缺 |

### 5.2 加权总分趋势

| 时间点 | 总分 /100 | 状态 | 触发 |
|---|---|---|---|
| P1.3 前 (2026-07-02 前) | ~65.94 | PARTIALLY_ALIGNED | 基线 |
| P1.3 后 (2026-07-02) | ~75 (估算) | ALIGNED 边缘 | MedCodER 降级 + 文档重写 + 14 docs + 331 archive |
| A1A Gate 4R-I (2026-07-21) | **52.6% weighted** (官方 5-tuple) | NOT_DEMONSTRATED | charter 锁定, 加权口径与 P1.3 不同 |
| 现在 (2026-08-06, A1D.5R 后) | **~70-72** (本审计估算) | PARTIALLY_ALIGNED | 30 packs + A2A fast path + Bootstrap Ticket + Theme/Reset |

> **口径说明**: P1.3 是 20 维度简单平均 (65.94/100); A1A Gate 4R-I 是"weighted"加权口径 (52.6%, 含安全/PHI/tenant 等高权重维度). 两者不可直接比较, 但趋势可观察: P1.3 后估升至 ~75, 但 A1A Gate 4R-I 严格化降为 52.6%, 现在 (A1D.5R) 工程层面估回到 ~70-72. **仍低于 ALIGNED 阈值 (≥80)**.

### 5.3 关键洞察

1. **API 契约层已扎实闭环** (维度 6-9, 18 平均 ≥4.5) — Phase 1.0-1.3 的工程成果不会被后续 phase 否定
2. **Pre-built Agents 从 3/20 → 6/20 runnable** (维度 14, 1.40 → ~2.5) — A1B-AE 加了 14 metadata-only, A1D.5 加了 claim-check, Phase 5 Track D 把 CDI 升级为 mvp; 但 12/20 仍是 metadata-only 空壳
3. **Embedded Assistant 从 1.67 → ~3.0** (维度 10) — Phase 7 Gate 13/13A 已落地 Bootstrap Ticket + Web Component + 子域路径, 但仍非独立 sub-domain proxy
4. **A2A 从 3.00 → ~3.5** (维度 15) — Phase A1D-DEV CodingRuntimeDispatcher fast path 是质的提升 (medical-coding-agent 走 Corti-style 派发), 但仍非完整 5-态 state machine
5. **战略定位维度 (1) 已部分纠偏** — MedCodER 已降级, 但 CLAUDE.md 仍多处保留 MedCodER 主线描述, R1 标"高"风险未解决

---

## §6 偏移归因分析

### 6.1 A 类 — 故意战略偏移 (已 charter 化, 不应回退)

| # | 偏移 | 文档依据 | 评价 |
|---|---|---|---|
| A1 | MedCodER 5-stage 从产品本体降级为 Pre-built Agent #18 内部实现 | `PRODUCT_DIRECTION.md` §4 + P1.3 PASS | ✅ 合理 — Corti parity 维度 1 从 2.80 升至 ~3.5 |
| A2 | 中国本地化 (ICD-10-CN / ICD-9-CM-3 / CNY / ¥ / vermillion 品牌色) | `CLAUDE.md` §货币约定 + `docs/corti_parity/UI_IA_CORRECTION_REPORT.md` 品牌决策 | ✅ 合理 — 区域合规必需, 不影响架构对齐 |
| A3 | Charter §22 禁止 `CORTI_PARITY_VERIFIED` 等 8 verdict | `A1D_CHARTER.md` §22 | ✅ 合理 — 防止 self-attesting loops (Phase A0.1 Gate 0 教训) |
| A4 | 5-tuple 不可变更, 需 A2+ re-gate | A1A Gate 4R-I charter | ✅ 合理 — 防止 phase 内部自证 |
| A5 | Cloud-only 部署, 不支持医院内网 Docker | Cloud Flip 决议 (2026-06-27) + `CLAUDE.md` §部署模型 | ⚠ **R6 未决** — GATE14 推荐 on-prem, 战略评审推迟 |

### 6.2 B 类 — 实现层能力差距 (Phase 2-4 roadmap)

| # | 差距 | 当前状态 | 影响 Corti 维度 |
|---|---|---|---|
| B1 | Corti 20 Pre-built Agents 中 12/20 是 metadata-only 空壳 | medical_coding + clinical-documentation-improvement + code-validation + note-completeness + compliance-guardrail + procedure-extractor 6 个真跑; 其他 12 个仅 manifest | 维度 14 (1.40 → ~2.5) |
| B2 | A2A 真实任务流仅 fast path, 慢路径 InboundHandler 5 态 state machine 仅 spec | medical-coding-agent + medcoder-coding-review-agent 走 CodingRuntimeDispatcher, 不走 InboundHandler | 维度 15 (3.00 → ~3.5) |
| B3 | MCP Resources/Prompts 缺, Expert as MCP client 未跑通 | tools/list + tools/call + 5 handlers 已有, dispatch_detail 15-field metadata 已落 (Phase 3-D2.5) | 维度 16 (3.50 → ~3.7) |
| B4 | Context/Memory 真实跑通 + 三层隔离 + GC 策略主线未用 | 11 文件 spec 完整, memory_expert.py 271 LOC, phi_redactor 已落, 但 fast path 绕过 Context | 维度 17 (3.29 → ~3.5) |
| B5 | Embedded Assistant 非独立 sub-domain proxy + 无 tRPC + 无第三 relay | Phase 7 Gate 13/13A 已落 Bootstrap Ticket + Web Component, 单域名子路径模式 (cloud flip 决议) | 维度 10 (1.67 → ~3.0) |
| B6 | 第三方基础设施全缺: PostHog / Stripe / Intercom / Mintlify / Keycloak | 自实现 JWT (oauth.py 449 LOC), 自写 markdown 文档, 无 PostHog session replay | 维度 2 (2.25 → ~2.5) + 维度 13 (2.50 → ~3.5) + 维度 20 (1.13 → ~2.5) |
| B7 | 三套并行 runtime 层未收敛 | legacy `app/agents/orchestrator.py` + legacy `icoder_runtime/agent_runner.py` + 新 `app/icoder/agent_runtime/` | G6-001/002/003 roadmap |
| B8 | 模型标识 4 个并存 | `deepseek-chat` / `deepseek-v4` / `deepseek-v4-flash` / 等 | G10-002 |

### 6.3 C 类 — 定位矛盾 (需立即修)

| # | 矛盾 | 影响 | 来源 |
|---|---|---|---|
| C1 | UI / CLAUDE.md / README 多处仍说 "Corti-competitive" / "复刻 Corti" 但 charter §22 禁止 `CORTI_PARITY_VERIFIED` verdict | 给医院买方制造"低质 Corti 克隆"印象, 给团队内部制造"目标是复刻 Corti"的错觉 | Release Roadmap §3 R1 (2026-08-05 标"高") |
| C2 | CLAUDE.md §MedCodER 主线描述 (CLAUDE.md:80-130) 未同步降级 | P1.3 TD-098 标"未完成", 与 PRODUCT_DIRECTION.md 冲突 | P1.3 §13 风险 |
| C3 | 13 处 Corti 外链 (`docs.corti.ai/*`, `help.corti.app/*`) 仍在 AI Studio | G3-001 / G12-002 P0 issue | GATE14 issue grading |
| C4 | `@icoder/sdk@1.0.0` + `@icoder/embedded@2.x` npm 仍 404 | G8-001 P0 issue | GATE14 |
| C5 | 战略定位文档 (PRODUCT_DIRECTION) 与实际 README/CLAUDE.md 不一致 | 文档层不一致 → 团队共识割裂 | R1 |

---

## §7 整体判定

### 7.1 判定矩阵

| 判定轴 | 结论 | 理由 |
|---|---|---|
| **是否偏离原始"复刻 Corti"目标?** | **是 — DRIFTED** | 多 phase charter (P1.3 / A1A Gate 4R-I / A1D §22) 已将目标重定义为"Corti-架构对齐 + 中国本地化" |
| **偏离是否合理?** | **是 — 文档化、审计化、有 charter 禁令防止反向回退** | A 类偏移有 release note / P1.3 PASS verdict / Cloud Flip 决议 / Charter §22 等多重治理 |
| **实现层是否已达 Corti parity?** | **否 — NOT_DEMONSTRATED (52.6%, 5-tuple 锁定)** | 6/20 Pre-built Agents runnable, A2A 仅 fast path, 第三方基础设施全缺 |
| **趋势是收敛还是发散?** | **缓慢收敛** | P1.3 (65.94) → 现在 (~70-72), 但仍低于 ALIGNED 阈值 (≥80); 工程进展持续, 但战略定位矛盾 (C 类) 阻碍完全收敛 |
| **当前最大风险?** | **C 类定位矛盾 + B1 (12/20 metadata-only)** | R1 (定位矛盾) 给医院买方造成"低质克隆"印象, 比纯工程差距更具破坏性 |

### 7.2 一句话判定

> **iCoDer 已经在战略层偏离了"纯粹复刻 Corti"的原始目标, 转为"Corti-架构对齐 + 中国医院场景本地化"的双目标路径, 这一偏离有完整的 charter / phase / audit 治理; 但实现层 Corti parity 仍处于 NOT_DEMONSTRATED (52.6%) 状态, 且 UI/CLAUDE.md/README 与新战略定位存在矛盾, 给外界传达了混乱信号. 总判定: 战略已决, 实现未达, 定位待统一.**

### 7.3 三档次判定 (参考)

| 档次 | 描述 | iCoDer 当前 |
|---|---|---|
| **ALIGNED** | 实现层 parity ≥80%, 战略定位一致, 文档一致 | ❌ 不到 |
| **DRIFTED** | 战略目标重定义 + 实现部分对齐 + 文档可能矛盾 | ✅ **当前状态** |
| **DIVERGED** | 战略目标放弃, 实现层与原目标 < 30%, 文档彻底矛盾 | ❌ 不到 (实现层仍 ~70% 对齐) |

---

## §8 建议 (Recommendations)

### 8.1 立即 (本周)

1. **R1 修复 — 战略定位统一**:
   - 改 CLAUDE.md §产品定位 段, 引用 `PRODUCT_DIRECTION.md` 而非重复描述
   - 改 README.md, 把 "Corti-competitive" 措辞改为 "Corti-parity 架构 + 中国本地化医疗合规 AI"
   - 删 13 处 Corti 外链 (`docs.corti.ai/*`, `help.corti.app/*`) (G3-001 / G12-002 P0)
   - 改 UI 文案, AI Studio Overview 不应直接 link 到 Corti 文档站

2. **R6 决策 — 部署路径**:
   - Cloud-only (CLAUDE.md 当前) vs On-prem Docker (GATE14 推荐) 必须二选一
   - 推迟到 Layer 2 启动前会导致重做

### 8.2 短期 (Layer 1 Pilot 准入, 2-3 周)

3. **完成 A1D.5R deferred 项**:
   - `test_compliance_guardrail_passes_complete_case` — 产品负责人决策 (PASS vs WARNING)
   - `test_mcp_wrapper_discover_tools_invalid_url` — Linux CI 验证

4. **关闭 12 A1C open blockers**:
   - 9 工程 blockers 在 A1D 已基本闭 (KMS rotation + LLM fallback + audit pause flag + UserRole 扩展 等)
   - 11 Pilot-env-gated blockers 需 Pilot 云账号 + DNS CNAME + 医院 IdP metadata

### 8.3 中期 (Layer 2-3, 6-12 周)

5. **Phase 2 — 12/20 metadata-only Agent 实装**:
   - 优先级: Corti #5 Procedure Extractor + #6 Diagnostic Extractor + #1 ICD-10 Index Navigator (核心编码链路) → 然后 #2 Rule Explainer + #7-15 (Corti 体系补齐)
   - Corti #17 Clinical Education + #19 Clinical Guidelines 仍未建 pack, 需新建

6. **Phase 2 — Agentic Framework 主线收敛**:
   - 三套并行 runtime 层 → 1 套 (`app/icoder/agent_runtime/`)
   - A2A 慢路径 InboundHandler 5 态 state machine 真跑通 (不只是 fast path)
   - Context/Memory 主线接入 (不仅 spec)

7. **Phase 3 — 第三方基础设施**:
   - PostHog 自部署 (session replay + flags + surveys)
   - Stripe Billing 全套 (or 微信/支付宝 CN 替代)
   - Mintlify 文档站 + `llms.txt`
   - Keycloak (可选, 当前自实现 JWT 已功能等价)

### 8.4 长期 (GA, 6-12 月)

8. **4 核心 capability production-ready**:
   - Medical Coding F1@1 ≥ 0.80 (持续评测)
   - CDI PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK
   - DRG grouper 接入产线 coding-compliance run
   - DIP 真实实现 (当前 501 + demo HTML)

9. **战略定位彻底重写**:
   - 从 "Corti-parity 架构" 升级为独立产品定位
   - 删除所有 Corti 外链 / Corti 比较文案
   - 建立 iCoDer 独立品牌叙事

---

## §9 审计产出清单

### 9.1 新产出

- `reports/audit/PRODUCT_DRIFT_AUDIT_2026_08_06.md` (本文档)

### 9.2 引用的基线文档

- `docs/corti_parity/CORTI_REFERENCE_BASELINE.md` (620 行, Corti 官方能力)
- `docs/corti_parity/CORTI_PARITY_GAP_ANALYSIS.md` (701 行, 20 维度打分)
- `docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md` (407 行, P1.3 PASS verdict)
- `docs/product/PRODUCT_DIRECTION.md` (245 行, iCoDer 主线声明)
- `docs/governance/RELEASE_ROADMAP.md` (200 行, 3 层 release roadmap)
- `docs/phase-a1d/A1D_CHARTER.md` (含 §22 禁用 verdict 列表)

### 9.3 引用的状态记录

- 5-tuple (A1A Gate 4R-I, 2026-07-21): `CORTI_PARITY=NOT_DEMONSTRATED (52.6%)`
- A1C.9 verdict (2026-08-05): `PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN`
- A1D.6 verdict (2026-08-06): `PARTIAL_A1D_REMEDIATION_PHASE_COMPLETE_9_OF_9_BLOCKERS_CLOSED_20_BASELINE_FAILURES_DEFERRED_TO_PILOT_PREP`
- A1D.5R verdict (2026-08-06): `PARTIAL_A1D_5_R_FOLLOWUP_18_OF_20_CLOSED_2_DEFERRED_PRODUCT_OWNER_OR_LINUX_CI`

### 9.4 数据快照 (2026-08-06)

- agent packs: 30 (8 mvp + 2 runnable + 14 metadata-only + 6 hidden/internal)
- API routers: 44 (含 8 个 v2-tools)
- frontend pages: 29
- backend models: 22
- alembic migrations: 30
- Corti 20 Pre-built Agents 覆盖: 18/20 existence, 6/20 runnable/mvp, 2/20 完全缺

---

## §10 审计局限性

1. **Cortic 基线时点**: Corti 官方能力 snapshot 是 2026-06-30 deep crawl + 2026-07-02 baseline. Corti 自身在过去 30 天可能已更新能力, 本审计未重新 crawl Corti 最新状态.
2. **打分口径转换**: P1.3 用 20 维度简单平均 (65.94/100), A1A Gate 4R-I 用 weighted 加权 (52.6%). 两者不可直接比较, 本审计的"~70-72"是基于 P1.3 维度的估算, 非官方数字.
3. **未审计项**: 具体测试用例 pass/fail 状态 (近期 A1D.5R 已闭 18/20), 具体 alembic 迁移内容, 具体依赖版本 — 这些不影响战略判定.
4. **Corti 私有代码**: 本审计未尝试访问 Corti 私有 repo / 内部代码, 仅基于公开文档 + 抓包 + spec.

---

## §11 结论

> **"复刻 Corti"作为产品目标, 在 iCoDer 项目演进中已经过一个完整的战略重定义过程: 从最初的直接复刻 (P1.3 前), 到 P1.3 的"Corti-style + MedCodER 降级", 到 A1A Gate 4R-I 的"CORTI_PARITY=NOT_DEMONSTRATED 锁定 + Charter §22 禁令", 到现在的"Corti-架构对齐 + 中国本地化双目标" (Release Roadmap R1). 这一过程是合理的, 有审计追溯的, 有强制治理 (§22) 的. 但实现层 Corti parity 仍是 52.6% (NOT_DEMONSTRATED), 6/20 Pre-built Agents runnable, A2A 仅 fast path, 第三方基础设施全缺. UI/CLAUDE.md/README 仍多处保留旧定位措辞, 与新战略冲突.**
>
> **总判定: DRIFTED (战略已决, 实现未达, 定位待统一).**

---

**审计人**: Claude (in Claude Code session, model glm-5.2)
**审计日期**: 2026-08-06
**审计性质**: 全量文档 + 实现状态对比, 非改写或实施任务
**next action**: 请用户审阅判定与建议, 决定后续优先级 (R1 立即修 / R6 战略决策 / B1 实装 / 其他)
