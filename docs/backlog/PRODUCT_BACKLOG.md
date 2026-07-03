# PRODUCT_BACKLOG — 产品 Backlog

> **声明**: 本文档是 iCoDer **产品** backlog, 含 P1.3 + Phase 2-4 产品功能. 不含技术债 (见 `TECH_DEBT_BACKLOG.md`).
> **日期**: 2026-07-02
> **阶段**: P1.3 Corti Parity Direction Audit 后的产品 backlog 梳理
> **状态**: MAINLINE — 取代 `docs/PRODUCT-ROADMAP.md` 中关于 MedCodER 主线的描述

---

## 0. Backlog 原则

- 只接受对齐 Corti-style 方向的产品功能
- MedCodER Stage 1/4/rerank/few-shot 改动 / F1 提升实验 / 模型训练 — **拒绝**
- 与 Corti 方向无关的 SaaS 后台功能堆叠 — **拒绝**
- 17 个 Pre-built Agents 实装 / Theme toggle / 工作台共享 layout / Event Inspector / Embedded Assistant 子域 proxy — **接受**

---

## 1. P1.3 范围内 (本审计)

### P1.3-1 Sidebar IA 段顺序对齐 Corti (Stage 6)

- **优先级**: P0
- **维度**: 3 (Sidebar IA, 3.00 → 4.0+)
- **任务**: Layout.tsx sidebar nav 按 Top → AI Studio → Manage → Support 段顺序排列, AI Studio 7 子页顺序 (Overview → Agents → STT → TextGen → Embedded → FactExtraction → MedicalCoding), Medical Coding 降为 AI Studio 第 7 子页
- **验收**: 截图对比 Corti sidebar, 段顺序完全对齐

### P1.3-2 Project Home 4 tabs 雏形 (Stage 6)

- **优先级**: P0
- **维度**: 4 (Project Home 4 tabs, 1.33 → 3.0+)
- **任务**: HomePage.tsx 重写为 4 tabs (Transcribe/Document/Chat/Code NEW), 每个 tab promo 卡片跳对应 AI Studio 工作台
- **验收**: Home 页面 4 tabs 渲染, 点击跳转正确

### P1.3-3 顶栏 Theme toggle + Reset live cost (Stage 6)

- **优先级**: P0
- **维度**: 13 (顶栏元素, 2.50 → 3.5+)
- **任务**: 顶栏加 Theme toggle (深/浅) + Reset live cost 按钮
- **验收**: Theme toggle 切换深浅, Reset live cost 重置计数

### P1.3-4 工作台共享 layout 壳子 (Stage 6)

- **优先级**: P1
- **维度**: 5 (工作台通用模式, 3.29 → 3.5+)
- **任务**: 抽离 5 Studio tool 共享 layout 组件 (左 Input / 右 Output 50/50 + Input/Output 控件 + 右侧 Settings panel + 底部 Event Inspector), 不动各页内部
- **验收**: 5 tool 页面使用共享 layout, 视觉一致

### P1.3-5 设计 token 抽离 (Stage 6, 部分)

- **优先级**: P1
- **维度**: 19 (视觉设计系统, 2.89 → 3.0+)
- **任务**: 抽离 design token (color mono / Inter font / 8px radius / 8px grid), tailwind.config.js 统一, primary CTA 全黑
- **验收**: tailwind config 含 design token, 全站视觉一致

---

## 2. Phase 2 — Agentic Framework 真实跑通

### PH2-1 切换主运行路径到新 Orchestrator

- **优先级**: P0
- **维度**: 15 (A2A)
- **任务**: medical-coding 调用从 HybridCodingAdapter 切到 `app/icoder/agent_runtime/orchestrator/wiring.py` → `build_expert_invoker_for_medcoder` → 4 D2 expert pack, hybrid_fallback back-compat 保留
- **验收**: e2e 测试不退化, `/api/v2/tools/coding/icoder/` 仍返回 200 + codes

### PH2-2 A2A 真实任务流

- **优先级**: P0
- **维度**: 15 (A2A 3.00 → 4.0+)
- **任务**: `routes_task_stub.py` → 完整实装 Task 5 态 (submitted→working→input-required/completed/failed/canceled), Artifact 产出, A2A 真实任务流跑通
- **验收**: A2A inbound → orchestrator → outbound → completed 端到端跑通

### PH2-3 MCP Resources/Prompts + Expert as MCP client

- **优先级**: P1
- **维度**: 16 (MCP 3.50 → 4.0+)
- **任务**: MCP 加 `resources/list` + `prompts/list`, Expert 作为 MCP client 跑通 (调用第三方 MCP server), Transport stdio 默认 + HTTP Phase 4
- **验收**: MCP resources + prompts 端点返回 200, Expert 调用外部 MCP server 成功

### PH2-4 Context/Memory 真实跑通

- **优先级**: P0
- **维度**: 17 (Context/Memory 3.29 → 4.0+)
- **任务**: contextId UUID v4 服务端生成主线跑通, 三层隔离 (数据/状态/缓存) 主线跑通, GC 策略 (24h active + 7d 物理删除 + 90d audit) 主线跑通, Memory expert 长期记忆 (BGE-M3 + FAISS) 跑通
- **验收**: Context 端到端跑通, GC 自动触发, Memory 跨 session 检索

### PH2-5 Edge Functions 4 项 stub 实装

- **优先级**: P1
- **维度**: 12 (Edge Functions 3.14 → 4.0+)
- **任务**: `onboarding` / `assistant-settings` / `external/agents` (真实版) / `intercom-hmac` 4 端点实装
- **验收**: 4 端点返回 200 + 真实数据

---

## 3. Phase 3 — 20 Pre-built Agents 实装

### PH3-1 ICD-10-CN Index Navigator Agent (Corti #1 完整版)

- **优先级**: P1
- **任务**: 基于 `icd10cn_code_catalog.json` (37,897 码) 实装 Alphabetic Index 索航 Agent
- **验收**: 输入临床术语, 输出 candidate codes

### PH3-2 Rule Explainer Agent (Corti #2)

- **优先级**: P1
- **任务**: 解释 ICD-10-CN/ICD-9-CM-3-CN code 选择理由, 调 RuleEngine + code_dictionary
- **验收**: 输入 code, 输出选择理由 + 规则引用

### PH3-3 Compliance Guardrail Agent 完整版 (Corti #3)

- **优先级**: P1
- **任务**: 升级 RuleEngine 为 Pre-built Agent, 评估 code sets vs CN 医保规则 (CN-DRG / DIP)
- **验收**: 输入 code sets, 输出违规项 + 建议

### PH3-4 Code Validation Agent 完整版 (Corti #4)

- **优先级**: P1
- **任务**: 升级 R001-R010 + 修复 loop 为 Pre-built Agent, validate against official coding rules
- **验收**: 输入 code sets, 输出 validation 结果

### PH3-5 Procedure Entity Extractor Agent 完整版 (Corti #5)

- **优先级**: P1
- **任务**: 升级 Stage 1 procedure_mentions 为 Pre-built Agent, ICD-9-CM-3-CN procedure 码
- **验收**: 输入 EMR, 输出 procedure codes + evidence

### PH3-6 Diagnostic Entity Extractor Agent 完整版 (Corti #6)

- **优先级**: P1
- **任务**: 升级 Stage 1 disease 为 Pre-built Agent, ICD-10-CN diagnostic 码
- **验收**: 输入 EMR, 输出 diagnosis codes + evidence

### PH3-7 Surgical Registry Intelligence Agent (Corti #7)

- **优先级**: P2
- **任务**: 中国手术登记数据自动录入
- **验收**: 输入手术 EMR, 输出登记字段

### PH3-8 ICU Admission Summary Agent (Corti #8)

- **优先级**: P2
- **任务**: ICU 入院文档, synthesizing EHR data
- **验收**: 输入 ICU EHR, 输出 admission summary

### PH3-9 Triage and Initial Assessment Agent (Corti #9)

- **优先级**: P2
- **任务**: 急诊分诊 + validated risk scores, 已有 `clinical_triage.py` 部分基础
- **验收**: 输入急诊症状, 输出 triage level + risk score

### PH3-10 Note Completeness Agent 完整版 (Corti #10)

- **优先级**: P1
- **任务**: 实时完整性/准确性/合规检查, 替代 iCoDer Doctor 概念
- **验收**: 输入 EMR, 输出缺失项 + 建议补充

### PH3-11 Medication Reconciliation Agent (Corti #11)

- **优先级**: P2
- **任务**: 用药安全, 跨入院/转科/出院
- **验收**: 输入 medication list, 输出冲突 + 建议

### PH3-12 Denial Appeals Agent 完整版 (Corti #12)

- **优先级**: P2
- **任务**: 医保拒付申诉, evidence-backed
- **验收**: 输入 denial case, 输出申诉文档

### PH3-13 Patient Discharge Education Agent (Corti #13)

- **优先级**: P3
- **任务**: 出院教育, 个性化
- **验收**: 输入 discharge diagnosis, 输出 education materials

### PH3-14 Nursing Shift Handoff Agent (Corti #14)

- **优先级**: P3
- **任务**: 护理交班, structured handoff
- **验收**: 输入 shift data, 输出 handoff report

### PH3-15 Prior Authorization Agent (Corti #15)

- **优先级**: P2
- **任务**: 预授权文档, guideline-aligned
- **验收**: 输入 PA request, 输出 PA 文档

### PH3-16 Referral Generator Agent (Corti #16)

- **优先级**: P3
- **任务**: 转诊信, clinician-to-clinician
- **验收**: 输入 referral reason, 输出 referral letter

### PH3-17 Clinical Education Agent (Corti #17)

- **优先级**: P3
- **任务**: 临床教育, evidence-based explanations
- **验收**: 输入 query, 输出教育内容

### PH3-18 Clinical Guidelines Agent (Corti #19)

- **优先级**: P3
- **任务**: 评估 vs 专业临床指南
- **验收**: 输入 case + guideline, 输出对齐评估

### PH3-19 CDI Agent 完整版 (Corti #20)

- **优先级**: P1
- **任务**: Clinical Documentation Improvement, documentation gaps + provider queries
- **验收**: 输入 EMR, 输出 gaps + queries

### PH3-20 10 metadata-only packs 实装真实 Python impl

- **优先级**: P2
- **任务**: 10 metadata-only packs (cdi-review/code-validation/compliance-guardrail/denial-appeals/diagnosis-extractor/documentation-gap/evidence-ranker/note-completeness/procedure-extractor/drg-analyzer) 加真实 Python impl
- **验收**: 10 packs 通过 agent_pack 1.2 validator, 真实运行

---

## 4. Phase 4 — 第三方基础设施 + Embedded Assistant 子域 proxy

### PH4-1 PostHog 自部署

- **优先级**: P1
- **维度**: 2 (架构 2.25 → 4.0+) + 13 (顶栏 PostHog replay)
- **任务**: 自部署 PostHog (session replay + feature flags + event capture), 替代 GA4 + Crazyegg
- **验收**: session replay 可用, feature flags 工作

### PH4-2 Stripe Billing 全套

- **优先级**: P1
- **维度**: 2 (架构)
- **任务**: Stripe 订阅 + invoice + 支付, 替代当前简单 billing
- **验收**: 订阅创建 + invoice 生成 + 支付成功

### PH4-3 Intercom Tickets 嵌入

- **优先级**: P2
- **维度**: 2 (架构)
- **任务**: 评估是否替换 in-app TicketsPage 为 Intercom 外部 Zendesk, 或保留 in-app 等价
- **验收**: 决策文档 + 实施

### PH4-4 Mintlify 文档站 + llms.txt

- **优先级**: P1
- **维度**: 20 (文档站 3.0 → 4.0+)
- **任务**: Mintlify 自部署 + `llms.txt` (AI ingestion 友好) + 27 详细页面 + 377 索引 + product positioning 显式章节 + architecture 显式章节
- **验收**: 文档站可访问, llms.txt 可被 AI ingestion, 5 分钟新人了解全局

### PH4-5 Keycloak IdP

- **优先级**: P2
- **维度**: 18 (Authentication 4.5 → 5.0)
- **任务**: 评估是否上 Keycloak 替代自实现 JWT (功能等价, 高代价可放缓)
- **验收**: 决策文档 + 实施 (如决策上)

### PH4-6 Embedded Assistant 子域 proxy

- **优先级**: P1
- **维度**: 10 (Embedded Assistant 1.67 → 4.0+)
- **任务**: 独立子域 `assistant.{region}.icoder.cloud` (或子路径 `/assistant/api/*`), `/api/auth/session` + `/api/ready` + `/api/proxy/dd` (Datadog) + `/api/proxy/mp/*` (Mixpanel) + `/api/proxy/relay/*` (PostHog relay) + `/api/trpc/template.getAllSections` (tRPC) + `POST /embedded` session init
- **验收**: 子域 proxy 全部端点 200, tRPC template getAllSections 工作, embedded session 创建

### PH4-7 顶栏 Reset live cost + PostHog session replay

- **优先级**: P2
- **维度**: 13 (顶栏 3.5+ → 4.0+)
- **任务**: 顶栏 Reset live cost 按钮 (P1.3-3 已加雏形, Phase 4 完整化) + PostHog session replay 嵌入
- **验收**: Reset 工作完整, session replay 可访问

---

## 5. 永不上主线 (拒绝项)

| 项 | 拒绝理由 |
|---|---|
| MedCodER Stage 1/4/rerank/few-shot 改动 | CLAUDE.md 已降级, 不做 F1 提升实验 |
| 模型训练 / STT 微调 | 不训练模型 |
| Doctor 自检 / MethodCompare / 10 builtin methods / MethodSwitcher / RunTrace / ExpertLibrary / OrchestrationPage / EvaluationPage / GoldCasesPage | P1.2/P1.3 已删或降级 |
| 私有化部署 / 数据不出院 | Cloud-Flip 2026-06-27 已逆转 |
| icoder-next 切片 | Pivot 2026-06-17 已逆转 |
| 与 Corti 方向无关的 SaaS 后台功能堆叠 | 不堆功能 |
| Medical Coding 页面当作整个平台中心 | MedCodER 仅 Pre-built Agent #18 |

---

## 6. Backlog 优先级矩阵

| 优先级 | 数量 | 时间窗 |
|---|---|---|
| P0 | 4 (P1.3) + 3 (Phase 2) | 本审计 + 紧接 Phase 2 |
| P1 | 1 (P1.3) + 2 (Phase 2) + 6 (Phase 3) + 4 (Phase 4) | 短期 |
| P2 | 7 (Phase 3) + 2 (Phase 4) | 中期 |
| P3 | 4 (Phase 3) | 长期 |

---

## 7. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, P1.3 + Phase 2-4 产品 backlog | P1.3 Stage 3 方向纠偏 |
