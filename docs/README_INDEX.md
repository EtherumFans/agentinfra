# README_INDEX — iCoDer 文档索引

> **声明**: 本文档是 iCoDer 文档库的总入口, 提供 5 分钟新人了解全局的阅读路径.
> **日期**: 2026-07-02
> **阶段**: P1.3 Corti Parity Direction Audit 后
> **状态**: MAINLINE — 取代零散文档入口

> **当前验证入口（2026-08-14）**：历史评分与数量清单已过时。最新的
> 26-Agent 运行证据、两套 52 例 E2E、Corti 差距和外部上线门禁见
> `docs/corti_parity/CORTI_PARITY_STATUS_2026-08-14.md`。

> **最新失败关闭增量（2026-08-22）**：Agent Hub 公开候选门禁见
> `docs/corti_parity/ICODER_VISIBLE_AGENT_LAUNCH_CANDIDATE_ENFORCEMENT_PHASE_SUMMARY_2026-08-22.md`；
> 深度编排缺失 LLM 时的无 stub 503 合同见
> `docs/corti_parity/ICODER_ORCHESTRATOR_LLM_FAIL_CLOSED_PHASE_SUMMARY_2026-08-22.md`。
> CDI claim-evidence/semantic-necessity 必需门禁降级的无结果、tenant-owned 审计合同见
> `docs/corti_parity/ICODER_CDI_REQUIRED_GATE_FAIL_CLOSED_PHASE_SUMMARY_2026-08-22.md`。
> STT 固定协议样例的 pytest-only、普通进程失败关闭边界见
> `docs/corti_parity/ICODER_STT_PROTOCOL_FIXTURE_FAIL_CLOSED_PHASE_SUMMARY_2026-08-22.md`。
> 编排专家无 noop/stub 成功路径及 A2A DataPart 精确 Pack 字段白名单见
> `docs/corti_parity/ICODER_ORCHESTRATOR_EXPERT_A2A_OUTPUT_ALLOWLIST_PHASE_SUMMARY_2026-08-22.md`。
> Feedback 与训练用途独立、快照/用途/时限绑定且默认不含临床内容的授权门禁见
> `docs/corti_parity/ICODER_FEEDBACK_TRAINING_AUTHORIZATION_PHASE_SUMMARY_2026-08-22.md`。
> Medical Coding/CDI 真实有界模型遥测、ASR 内容无关加密审计及 A2A 结构化 ID 脱敏边界见
> `docs/corti_parity/ICODER_DEDICATED_CLINICAL_TELEMETRY_PHASE_SUMMARY_2026-08-22.md`。
> 26-Agent Pack 自有合成语义门禁、历史真实响应 22/26 诚实回放、Evidence/Surgical 修正及防止旧响应回灌见
> `docs/corti_parity/ICODER_AGENT_HUB_REFERENCE_QUALITY_GATE_PHASE_SUMMARY_2026-08-22.md`。

> **最新本地 Agent 能力增量（2026-08-23）**：Evidence Ranker 的显式来源/span
> 文档可追溯性排序、保守分数含义、v4 合约、统一 Run/A2A/Hub/trace、5/21 离线矩阵
> 及对 Corti 邻近 Medical Coding 能力的差距见
> `docs/corti_parity/ICODER_GOVERNED_EVIDENCE_RANKER_PHASE_SUMMARY_2026-08-23.md`。
> 较早的 ICD-10 Navigator 和 Code Validation 本地基线分别见
> `docs/corti_parity/ICODER_GOVERNED_ICD_NAVIGATOR_PHASE_SUMMARY_2026-08-23.md`、
> `docs/corti_parity/ICODER_GOVERNED_CODE_VALIDATION_PHASE_SUMMARY_2026-08-23.md`。

> **最新本地语义 E2E 增量（2026-08-24）**：ICU Admission Summary 的明确 ICU 字段/span、
> 禁止临床评分、异常阈值、药物筛查和治疗建议、追加式 v3 合同及 13-Agent HTTP 证据见
> `docs/corti_parity/ICODER_GOVERNED_ICU_SUMMARY_PHASE_SUMMARY_2026-08-24.md`。
> Nursing Handoff 的逐患者护理事实/span、最多 10 名患者、
> 禁止 acuity/priority 与无记录状态推断、追加式 v4 合同和 12-Agent HTTP 证据见
> `docs/corti_parity/ICODER_GOVERNED_NURSING_HANDOFF_PHASE_SUMMARY_2026-08-24.md`。
> Medication Reconciliation 的明确 Home/MAR/Discharge 来源、逐字药物字段/span、
> 无授权相互作用失败关闭和追加式 v4 合同见
> `docs/corti_parity/ICODER_GOVERNED_MEDICATION_RECONCILIATION_PHASE_SUMMARY_2026-08-24.md`。
> Rule Explainer 的固定 ICD-10-CN 目录事实、禁用无治理 legacy 指南和规则资产缺口见
> `docs/corti_parity/ICODER_GOVERNED_RULE_EXPLAINER_PHASE_SUMMARY_2026-08-24.md`。
> Diagnosis Extractor 的明示诊断标签、
> 疑似/否定/既往/家族史隔离、逐字 span、唯一 ICD-10-CN 候选、`unresolved` 和追加式 v7 合同见
> `docs/corti_parity/ICODER_GOVERNED_DIAGNOSIS_EXTRACTOR_PHASE_SUMMARY_2026-08-24.md`。
> Procedure Extractor 的上一阶段见
> `docs/corti_parity/ICODER_GOVERNED_PROCEDURE_EXTRACTOR_PHASE_SUMMARY_2026-08-24.md`。
> Patient Discharge Education 的明确出院事实、缺失/冲突澄清和禁止医学释义/新增建议见
> `docs/corti_parity/ICODER_GOVERNED_DISCHARGE_EDUCATION_PHASE_SUMMARY_2026-08-24.md`。
> 中国额外 Discharge Summary Structuring 的明确章节逐字重组、v5 合同、15-Agent HTTP 证据和
> Corti Textgen/Discharge Education 邻近能力差距见
> `docs/corti_parity/ICODER_GOVERNED_DISCHARGE_SUMMARY_STRUCTURING_PHASE_SUMMARY_2026-08-24.md`。
> Referral Generator 的明确转诊字段、缺失失败关闭、固定转诊信装配、中国双向转诊字段、v3 合同和
> Corti 逐项差距见
> `docs/corti_parity/ICODER_GOVERNED_REFERRAL_GENERATOR_PHASE_SUMMARY_2026-08-24.md`。
> DRG/DIP 的明确 ICD-10-CN / ICD-9-CM-3 编码风险复核、非官方候选、禁止分组/计分/支付、
> v8 合同和 Corti Medical Coding 邻近差距见
> `docs/corti_parity/ICODER_GOVERNED_DRG_DIP_RISK_REVIEW_PHASE_SUMMARY_2026-08-24.md`。
> 本地真实 HTTP 门禁现为 23-Agent happy/adversarial/reference 各 23/23、stability 138/138；
> 最初建立 7-Agent 独立门禁的阶段记录见
> `docs/corti_parity/ICODER_AGENT_HUB_LOCAL_SEMANTIC_E2E_PHASE_SUMMARY_2026-08-24.md`。

---

## 0. 5 分钟了解 iCoDer

**iCoDer 是什么**: 面向中国医院场景的 **Corti-style 医疗 Agent Runtime 平台**, 以托管云 SaaS 形式交付 (Environments: EU / US / CN; 医院 = Tenant; HIS/EMR = API Client).

**架构 4 层**:
```
第四层: Business Workbenches   app/api/*         ~190 endpoints (Studio Tools)
第三层: Pre-built Agents       official_agents/   32 pack / 26 个用户可见候选
第二层: Agentic Framework      app/icoder/agent_runtime/  A2A + MCP + Context + Orchestrator (spec 完整, 主线待切)
第一层: Runtime Core           icoder_runtime/   AgentRunner + LLMGateway + Registry + DataPolicy
```

**主线方向** (P1.3 拍板, 见 `docs/product/PRODUCT_DIRECTION.md`):
- Corti-style 平台 = 主体
- MedCodER 5-stage 管线 = Pre-built Agent #18 的实现选项 (不是产品本身)
- 不做 F1 提升 / 模型训练 / SaaS 后台堆叠
- 托管云 SaaS (单域名子路径模式), 不做私有化

**当前状态**: P1.3 审计后总分 65.94/100 (PARTIALLY_ALIGNED), P1.3 后预期 ~75, Phase 2-4 后 ~90.

---

## 1. 新人 5 步阅读路径

| 步 | 文档 | 用时 | 目的 |
|---|---|---|---|
| 1 | `CLAUDE.md` (项目根) | 1 min | 项目宪法: 产品定位 + 架构层次 + 启动命令 + 金标准 |
| 2 | `docs/README_INDEX.md` (本文档) | 1 min | 文档地图 + 阅读路径 |
| 3 | `docs/product/PRODUCT_DIRECTION.md` | 1 min | 主线声明 + MedCodER 降级 + 不做清单 |
| 4 | `docs/architecture/CURRENT_ARCHITECTURE.md` | 1.5 min | 4 层架构 + 主线/实验/legacy 三类资产 |
| 5 | `docs/product/CORTI_PARITY_ROADMAP.md` | 0.5 min | P1.3 + Phase 2-4 路线图 |

读完这 5 份, 应能回答:
- iCoDer 是什么? (Corti-style 医疗 Agent Runtime 平台)
- 4 层架构是什么? (Studio Tools / Pre-built Agents / Agentic Framework / Runtime Core)
- MedCodER 在哪个位置? (Pre-built Agent #18, 不是产品主体)
- 当前完成度? (65.94/100, PARTIALLY_ALIGNED)
- 下一步做什么? (P1.3 → Phase 2 → Phase 3 → Phase 4)

---

## 2. 文档树 (按类别)

### 2.1 方向性文档 (P1.3 新写, MAINLINE)

```
docs/
├── README_INDEX.md                              ← 本文档 (总入口)
├── product/
│   ├── PRODUCT_DIRECTION.md                     ← 主线声明 + MedCodER 降级
│   └── CORTI_PARITY_ROADMAP.md                  ← P1.3 + Phase 2-4 路线图
├── architecture/
│   ├── CURRENT_ARCHITECTURE.md                  ← 4 层架构当前状态
│   └── MAINLINE_VS_LEGACY.md                    ← 三层分类清单 (Mainline/Experimental/Legacy)
├── backlog/
│   ├── PRODUCT_BACKLOG.md                       ← 产品 backlog (P1.3 + Phase 2-4)
│   └── TECH_DEBT_BACKLOG.md                     ← 技术债 backlog (107 项)
└── corti_parity/
    ├── CORTI_REFERENCE_BASELINE.md              ← Stage 0: Corti 参考基线
    ├── ICODER_ASSET_INVENTORY.md                ← Stage 1: iCoDer 资产清单
    ├── CORTI_PARITY_GAP_ANALYSIS.md             ← Stage 2: 20 维度 gap 分析
    └── DIRECTION_CORRECTION_PLAN.md             ← Stage 3: 方向纠偏计划
```

### 2.2 Corti 对齐审计 (P1.3 Stage 0-3)

| 文档 | 内容 |
|---|---|
| `corti_parity/CORTI_REFERENCE_BASELINE.md` | Corti 产品定位 / 4 域架构 / Sidebar 15 项 / Home 4 tabs / 5 Studio tool API / 20 Pre-built Agents / Agentic Framework (A2A + Agent Card + Task + Message + Part + Artifact) / URL 对齐表 / 视觉系统 |
| `corti_parity/ICODER_ASSET_INVENTORY.md` | 38 backend API + 50+ services + 3 套 Agent 架构 + 16 agent pack + 30 frontend page + 90+ docs 清单, 含 keep/archive/deprecate 标签 |
| `corti_parity/CORTI_PARITY_GAP_ANALYSIS.md` | 20 维度打分 (0-5), 总分 65.94, 判定 PARTIALLY_ALIGNED, 5 aligned + 11 partial + 4 severe |
| `corti_parity/DIRECTION_CORRECTION_PLAN.md` | 5 项最大偏离 + 模块分类 + 新主线定义 + sidebar nav 建议 + P1.3 行动项 + 风险 + 成功标准 20 项 |
| `corti_parity/CORTI_PARITY_STATUS_2026-08-14.md` | 当前 26-Agent 运行矩阵、快乐/对抗 E2E、Corti 逐项差距、中国适配与外部上线门禁 |
| `corti_parity/AGENT_HUB_DEDICATED_A2A_REAL_LLM_PHASE_SUMMARY_2026-08-15.md` | 5 条专用 A2A 合同收敛、Diagnosis/Medical Coding 最终真实 DeepSeek 签名证据、Windows 安全词法回退、Medical Coding v8 与阶段差距 |
| `corti_parity/AGENT_HUB_RELEASE_CANDIDATE_AUTOMATION_PHASE_SUMMARY_2026-08-15.md` | 三语言 SDK 版本一致性、只构建发布候选流水线、SHA-256 工件清单、Windows Web 构建修复与正式发布外部门禁 |
| `corti_parity/AGENT_HUB_E2E_AUTH_NATIVE_SAFETY_PHASE_SUMMARY_2026-08-15.md` | Agent Chat API Client 真实归因、E2E 无硬编码凭证与 loopback 自注册、Windows 禁用原生 MedCodER 后零 FAISS 导入证据 |
| `corti_parity/CORTI_20_AGENT_CATALOG_GATE_PHASE_SUMMARY_2026-08-15.md` | Corti 20 个预置 Agent 的机器可校验一对一映射、逐项中国适配、开发门禁和外部差距 |
| `corti_parity/AGENT_HUB_COMPLIANCE_CODE_VALIDATION_CHAIN_PHASE_SUMMARY_2026-08-15.md` | Compliance Guardrail 审查编码集合、Code Validation 上游证明与跨 Agent 失败关闭 |
| `corti_parity/AGENT_HUB_CHINA_CODING_CHAIN_PHASE_SUMMARY_2026-08-15.md` | 诊断/手术抽取至 Medical Coding、Code Validation、Compliance 和 DRG/DIP 的签名可验证中国编码主链 |
| `corti_parity/ICODER_MODELS_EGRESS_ENFORCEMENT_PHASE_SUMMARY_2026-08-15.md` | Corti Models/20 模板只读对照、iCoDer Models 目录、LLM Provider 选择、Gateway/旧路径数据出境强制门禁与剩余外部差距 |
| `corti_parity/ICODER_TENANT_MODEL_ROUTING_PHASE_SUMMARY_2026-08-15.md` | 租户级模型选择、精确失败关闭路由、多部署秘密隔离、逐 Run 模型版本审计、SDK beta.16 与 Corti Models 托管差距 |
| `corti_parity/CORTI_ICODER_LIVE_GAP_MATRIX_2026-08-21.md` | 当前权威 Corti × iCoDer 差距：26-Agent 开发证据、真实 DeepSeek 最小 E2E、可开发任务与外部上线门禁 |
| `corti_parity/ICODER_AGENT_HUB_LOCAL_SEMANTIC_E2E_PHASE_SUMMARY_2026-08-24.md` | 首批 7 个本地确定性 Agent 的真实 HTTP happy/adversarial/reference/stability 证据、两个语义缺陷修复、局部门禁与 26-Agent 严格门禁隔离 |
| `corti_parity/ICODER_GOVERNED_DRG_DIP_RISK_REVIEW_PHASE_SUMMARY_2026-08-24.md` | DRG/DIP 明确编码输入的本地确定性风险复核、非官方候选与支付失败关闭、v8 合同、23-Agent 签名 HTTP E2E、宽回归和 Corti Medical Coding 邻近差距 |
| `corti_parity/ICODER_GOVERNED_PROCEDURE_EXTRACTOR_PHASE_SUMMARY_2026-08-24.md` | Procedure Extractor 明示状态/span、固定 ICD-9-CM-3 唯一候选、错误示例码修正、8-Agent 真实 HTTP E2E、Corti 同名 Agent 逐项差距及外部门禁 |
| `corti_parity/ICODER_GOVERNED_DIAGNOSIS_EXTRACTOR_PHASE_SUMMARY_2026-08-24.md` | Diagnosis Extractor 明示标签/断言状态/span、固定 ICD-10-CN 唯一候选、`unresolved`、追加式 v7 合同、9-Agent 真实 HTTP E2E 与 Corti 逐项差距 |
| `corti_parity/ICODER_GOVERNED_RULE_EXPLAINER_PHASE_SUMMARY_2026-08-24.md` | Rule Explainer 固定 ICD-10-CN 目录事实、禁用无治理 legacy 指南、追加式 v4 合同、10-Agent 真实 HTTP E2E 与 Corti instructional-note/指南差距 |
| `corti_parity/ICODER_GOVERNED_MEDICATION_RECONCILIATION_PHASE_SUMMARY_2026-08-24.md` | Medication Reconciliation 明确 Home/MAR/Discharge 来源、逐字字段/span、无授权药品知识失败关闭、追加式 v4 合同、11-Agent 真实 HTTP E2E 与 Corti 药学能力差距 |
| `corti_parity/ICODER_GOVERNED_NURSING_HANDOFF_PHASE_SUMMARY_2026-08-24.md` | Nursing Handoff 逐患者护理事实/span、最多 10 名患者、禁止优先级和无记录状态推断、追加式 v4 合同、12-Agent 真实 HTTP E2E 与 Corti 护理交接差距 |
| `corti_parity/ICODER_GOVERNED_ICU_SUMMARY_PHASE_SUMMARY_2026-08-24.md` | ICU Admission Summary 明确标签事实/span、禁止评分/阈值/药物筛查/治疗建议、追加式 v3 合同、13-Agent 真实 HTTP E2E 与 Corti ICU 能力差距 |
| `corti_parity/ICODER_GOVERNED_DISCHARGE_EDUCATION_PHASE_SUMMARY_2026-08-24.md` | Patient Discharge Education 明确字段事实/span、缺失与冲突澄清、禁止医学释义/结果解释/药物重整/新增建议、追加式 v3 合同、14-Agent 真实 HTTP E2E 与 Corti 患者教育差距 |
| `corti_parity/ICODER_GOVERNED_DISCHARGE_SUMMARY_STRUCTURING_PHASE_SUMMARY_2026-08-24.md` | 中国额外 Discharge Summary Structuring 明确章节逐字重组、禁止自由叙事总结/推断/编码/药物重整、追加式 v5 合同、15-Agent 真实 HTTP E2E、822 项宽回归及 Corti Textgen 邻近能力差距 |
| `corti_parity/ICODER_GOVERNED_CODE_VALIDATION_PHASE_SUMMARY_2026-08-23.md` | Code Validation 受治理 ICD-10-CN / ICD-9-CM-3 本地目录基线、v7 合约、统一运行与审计、957 项扩展回归及 Corti 逐项能力差距 |
| `corti_parity/ICODER_AGENTIC_CONNECTOR_GRAPH_RUNTIME_PHASE_SUMMARY_2026-08-22.md` | 五类 Connector 的管理员受控顺序 graph 接入通用 Agent Run：租户/revision/DAG/最小输入、输出 PHI 与注入门禁、失败关闭、Run Trace、JS/Python SDK 和 214 项联合回归 |
| `corti_parity/ICODER_AGENTIC_CONNECTOR_GRAPH_A2A_PHASE_SUMMARY_2026-08-22.md` | Connector graph 接入通用同步 A2A v0.3/v1：租户 DB Agent、Task 成功/失败终态、无失败 Artifact、Run/Trace/Connector task 审计和 364 项联合回归 |
| `corti_parity/ICODER_A2A_AGENT_CARD_PARALLEL_GRAPH_PHASE_SUMMARY_2026-08-22.md` | A2A 1.0 标准/租户动态 Agent Card、结构化条件、依赖层有界并行 Connector Graph、SDK beta.21、OpenAPI 与剩余外部门禁 |
| `corti_parity/ICODER_GOVERNED_CONNECTOR_TRANSPORT_PHASE_SUMMARY_2026-08-22.md` | 受治理 MCP/A2A HTTP transport：握手/session、Agent Card digest pin、DNS-to-socket pin、同源 redirect、OAuth2、CN/PHI 失败关闭、SDK beta.22 与外部门禁 |
| `corti_parity/ICODER_LOCAL_REGISTRY_INTERNAL_AGENT_CONNECTOR_PHASE_SUMMARY_2026-08-22.md` | 本地 Registry 与内部 Agent Connector 启动接线：四类本地能力、五类外部 provider 失败关闭、child Run/签名、递归/服务端 channel 守卫及 270 项后端验证 |
| `corti_parity/ICODER_GOVERNED_PUBLIC_REGISTRY_PHASE_SUMMARY_2026-08-22.md` | PubMed/ClinicalTrials.gov 受治理公共 Provider：去标识化查询、固定主机/pinned transport、最小字段投影、ClinicalTrials 单次实网验证与 PubMed 合规联系邮箱门禁 |
| `corti_parity/ICODER_INCREMENTAL_ARTIFACT_STREAM_PHASE_SUMMARY_2026-08-22.md` | A2A v1 验证后增量 Artifact：精确加密 chunk、append/lastChunk、断线重放、三 SDK 入口与原生首 token 安全边界 |
| `corti_parity/ICODER_MANAGED_ARTIFACT_OBJECT_PHASE_SUMMARY_2026-08-22.md` | Task/Artifact 强绑定托管对象：隔离、恶意内容/PDF/中文 DLP、用途绑定一次性下载、三 SDK、053 影子迁移与生产外部门禁 |
| `corti_parity/ICODER_ARTIFACT_DOWNLOAD_GRANT_PRIVACY_PHASE_SUMMARY_2026-08-22.md` | 托管对象下载授权隐私：query-secret-free 同 actor grant、OAuth client 精确绑定、访问日志最小化、A2A 游标规范化与 64/64 部署预检 |
| `corti_parity/ICODER_VISIBLE_AGENT_LAUNCH_CANDIDATE_ENFORCEMENT_PHASE_SUMMARY_2026-08-22.md` | 用户可见 Agent 强制门禁：26/26 executable/provider-resolvable/非 MVP 上线候选、后端/前端双层失败关闭、285/285 回归与 65/65 部署预检 |
| `corti_parity/ICODER_STT_PROTOCOL_FIXTURE_FAIL_CLOSED_PHASE_SUMMARY_2026-08-22.md` | STT 真实录音/转写与固定协议样例隔离：样例仅 pytest 可达、普通 development/Uvicorn 进程失败关闭、145/145 回归与 68/68 部署预检 |
| `corti_parity/ICODER_ORCHESTRATOR_EXPERT_A2A_OUTPUT_ALLOWLIST_PHASE_SUMMARY_2026-08-22.md` | 编排专家缺失 503、无运行时 noop/stub 成功；24 条通用/简单专用 A2A 路由精确 Pack 输出投影、原生 SSE 无正文 provisional 遥测、348 passed/5 skipped 与 72/72 部署预检 |
| `corti_parity/ICODER_FEEDBACK_TRAINING_AUTHORIZATION_PHASE_SUMMARY_2026-08-22.md` | Feedback 训练用途独立授权：owner/admin、精确快照、固定 metadata-only 质量改进、最长 30 天、变更即撤销、三 SDK、96/96 扩大回归与 73/73 预检 |
| `corti_parity/ICODER_OPENINFERENCE_PROVIDER_TELEMETRY_PHASE_SUMMARY_2026-08-22.md` | OpenInference Provider telemetry：标准 llm/tool 属性、真实 token/cost 多轮汇总、正文默认不导出、679/679 扩大回归与 74/74 预检 |
| `corti_parity/ICODER_DEDICATED_CLINICAL_TELEMETRY_PHASE_SUMMARY_2026-08-22.md` | Medical Coding/CDI 实际 provider/model/token 汇总、ASR 无正文加密推理遥测、手机号样式 UUID 脱敏边界修复、1041/1041 与 76/76 预检 |
| `corti_parity/ICODER_AGENT_HUB_REFERENCE_QUALITY_GATE_PHASE_SUMMARY_2026-08-22.md` | 26-Agent Pack 自有合成参考语义、历史真实响应 22/26 回放、Evidence/Surgical 语义修正、同步防回灌、718 项宽矩阵与 77/77 预检 |
| `corti_parity/ICODER_GOVERNED_CLINICAL_GUIDELINES_PHASE_SUMMARY_2026-08-24.md` | Clinical Guidelines 声明规则比较、冲突识别、精确 evidence span、v6 合同、21-Agent 签名 HTTP E2E、1193 项宽回归及 Corti 检索/指南能力差距 |
| `corti_parity/ICODER_GOVERNED_PRINCIPAL_DIAGNOSIS_REVIEW_PHASE_SUMMARY_2026-08-24.md` | 编码员主诊断初稿/候选/声明依据集合一致性、精确 evidence span、v11 合同、22-Agent 签名 HTTP E2E、1203 项宽回归及 Corti Medical Coding 相邻差距 |
| `corti_parity/ICODER_GOVERNED_CLINICAL_EDUCATION_PHASE_SUMMARY_2026-08-24.md` | Clinical Education 医院批准来源原句装配、精确 evidence span、v6 合同、20-Agent 签名 HTTP E2E、1176 项宽回归及 Corti 教学能力差距 |
| `corti_parity/ICODER_AGENT_HUB_PROJECT_CLONE_RUNTIME_PHASE_SUMMARY_2026-08-23.md` | Hub Clone→Customize→Run/A2A 项目双身份、Provider Expert、Connector Graph、Trace/Audit、三 SDK、Windows 原生守卫与当前 Corti 差距 |

### 2.3 架构 & 规范 (Agentic Framework spec)

```
docs/
├── ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md  ← 总 RFC (4 sub-spec)
├── ICODER_V1_ORCHESTRATOR_SPEC.md               ← Orchestrator 5 态状态机
├── ICODER_V1_A2A_SPEC.md                        ← A2A JSON-RPC 2.0 + Agent Card v0.3
├── ICODER_V1_CONTEXT_SPEC.md                    ← Context UUID + 三层隔离 + GC 策略
├── ICODER_V1_MCP_SPEC.md                        ← MCP server 8 工具 + Expert as client
├── ICODER_V1_AGENT_CARD_SPEC.md                 ← AgentDefinition / ExpertCard / AgentCard 三层
└── ICODER_V1_TASK_SPEC.md                       ← Task 5 态 (Phase 1 stub, Phase 5 完整)
```

### 2.4 云部署

```
docs/cloud/
├── CLOUD_DEPLOYMENT.md                          ← 托管云部署总文档 (3 层 Env/Tenant/API Client)
├── API_CLIENT_MODEL.md                          ← backend-service vs ROPC embedded 模型
├── MULTI_REGION.md                              ← EU/US/CN 三 region 路由
├── CLOUD_INTAKE_TEMPLATE.md                     ← 客户接入模板
├── EXTERNAL_REGISTRY_GATEWAYS.md                ← DrugBank/POSOS/Web Search 企业网关门禁
├── SEMANTIC_MEMORY_SERVICE.md                   ← 隔离语义 Memory 与患者授权边界
└── DATABASE_LOGGING_PRIVACY.md                  ← SQL 语句诊断与临床参数日志禁令
```

### 2.5 开发运维

```
docs/dev/
└── BACKEND_RECOVERY.md                          ← 后端 DB 恢复 runbook (cycle 23)
```

### 2.6 审计修复历史 (E1.x, 已闭环)

```
docs/audit_remediation/
├── PHASE_B_REPORT.md
├── PHASE_C_REPORT.md
├── E1_1_REAL_BOOT_GATE_REPORT.md
├── E1_2_ASSET_WIRING_AUDIT.md
└── E1_2_REAL_RETRIEVAL_BASELINE.md
```

### 2.7 API & SDK 参考

```
docs/
├── ARCHITECTURE.md                              ← 旧架构文档 (legacy, 逐步替换)
├── TECHNICAL-DESIGN.md                          ← 技术设计 (legacy)
├── agent-pack.md                                ← .icoder-agent 包格式
├── runtime.md                                   ← Runtime 旧文档
├── QUICKSTART.md                                ← 快速开始
├── SDK-TUTORIAL.md                              ← SDK 教程
├── PRODUCT-MODULES.md                           ← 产品模块清单
└── sdk/
    ├── js.md                                    ← JS SDK
    └── python.md                                ← Python SDK
packages/
└── icoder-dotnet/README.md                      ← .NET 10 SDK、契约与验证命令
```

### 2.8 操作手册 (旧, 逐步归档)

```
docs/operation-manual/
├── 01-HomePage.md ~ 22-Docs.md                  ← 22 页操作手册 (legacy, P2 归档)
└── SUMMARY.md
```

### 2.9 归档区 (P1.3 Stage 5 归档, 90+ 历史文档)

```
docs/archive/                                    ← P1.3 Stage 5 创建, 含 90+ 历史审计/对比/冲刺文档
```

详见 `docs/corti_parity/ASSET_CLEANUP_REPORT.md` (Stage 5 输出).

---

## 3. 关键概念速查

| 概念 | 定义 | 出处 |
|---|---|---|
| **Corti-style 平台** | 医疗 Agent Runtime 平台范式 (4 域 + Agentic Framework + Pre-built Agents + Studio Tools) | `product/PRODUCT_DIRECTION.md` §1-2 |
| **4 层架构** | Studio Tools / Pre-built Agents / Agentic Framework / Runtime Core | `architecture/CURRENT_ARCHITECTURE.md` §1 |
| **MedCodER 降级** | 5-stage ICD 编码管线 = Pre-built Agent #18, 不是产品主体 | `product/PRODUCT_DIRECTION.md` §4 |
| **3 类资产** | Mainline (主线) / Experimental (实验) / Legacy-Deprecated (废弃) | `architecture/MAINLINE_VS_LEGACY.md` §1 |
| **20 Pre-built Agents** | Corti 标准 agent 清单, iCoDer 已 3/20, 缺 17 | `corti_parity/CORTI_REFERENCE_BASELINE.md` §10 |
| **Agentic Framework** | A2A + Agent Card + Task + Context + MCP + Orchestrator | `ICODER_V1_*.md` (7 sub-spec) |
| **A2A 协议** | JSON-RPC 2.0 + Part (Text/Data/File) + Message + Task + Agent Card v0.3 | `ICODER_V1_A2A_SPEC.md` |
| **托管云 SaaS** | Env (EU/US/CN) → Tenant (医院) → API Client (backend/ROPC) | `cloud/CLOUD_DEPLOYMENT.md` |
| **PHI 脱敏** | 原始 PHI 不进云审计通道, 仅脱敏样本用于合规审计 | `CLAUDE.md` Runtime Core 职责 |
| **金标准评估** | 201 cases, per-case micro-F1, subdivision-tolerant | `CLAUDE.md` §金标准评估 |
| **20 维度 gap** | iCoDer vs Corti 对齐评分, 当前 65.94/100 | `corti_parity/CORTI_PARITY_GAP_ANALYSIS.md` |

---

## 4. 角色阅读路径

### 4.1 新人 (5 分钟)

按 §1 顺序读 5 份文档.

### 4.2 后端工程师 (30 分钟)

1. §1 五份 (5 min)
2. `architecture/CURRENT_ARCHITECTURE.md` (full, 5 min)
3. `architecture/MAINLINE_VS_LEGACY.md` (5 min)
4. `ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (10 min)
5. `CLAUDE.md` §MedCodER 管线 (5 min)

### 4.3 前端工程师 (20 分钟)

1. §1 五份 (5 min)
2. `corti_parity/CORTI_REFERENCE_BASELINE.md` §3-5 (Sidebar IA + Home 4 tabs + Workbench) (5 min)
3. `product/CORTI_PARITY_ROADMAP.md` §1.3 (UI IA 最小纠偏) (5 min)
4. `frontend/src/pages/` + `frontend/src/components/` (5 min)

### 4.4 产品经理 (15 分钟)

1. `product/PRODUCT_DIRECTION.md` (3 min)
2. `product/CORTI_PARITY_ROADMAP.md` (5 min)
3. `backlog/PRODUCT_BACKLOG.md` (5 min)
4. `corti_parity/CORTI_PARITY_GAP_ANALYSIS.md` §1 + §20 (2 min)

### 4.5 DevOps (15 分钟)

1. `cloud/CLOUD_DEPLOYMENT.md` (5 min)
2. `dev/BACKEND_RECOVERY.md` (5 min)
3. `CLAUDE.md` §启动命令 (5 min)

---

## 5. 文档不在哪里 (避免误读)

| 误读 | 真实位置 |
|---|---|
| MedCodER 是产品主体? | 不是. `PRODUCT_DIRECTION.md` §4 明确降级为 Pre-built Agent #18 |
| 私有化部署? | 不做. `cloud/CLOUD_DEPLOYMENT.md` 仅托管云 SaaS |
| icoder-next 切片? | 已逆转. `PRODUCT_DIRECTION.md` §6 全产品 frontend |
| F1 提升实验? | 不做. `backlog/PRODUCT_BACKLOG.md` §5 永不上主线 |
| 旧 PRODUCT-ROADMAP.md? | 已被 `product/CORTI_PARITY_ROADMAP.md` 取代 |
| 旧 ARCHITECTURE.md? | 已被 `architecture/CURRENT_ARCHITECTURE.md` 取代 |

---

## 6. 文档维护规则

- **新增文档**: 优先放 `docs/{category}/`, 不放 repo root
- **命名**: ALL_CAPS_WITH_UNDERSCORES.md (与现有约定一致)
- **frontmatter**: 必含 `声明 / 日期 / 阶段 / 状态` 4 行
- **变更日志**: 每份文档末尾必含 `## 变更日志` 表 (日期 / 变更 / 触发)
- **归档**: 旧文档移到 `docs/archive/`, 不删除 (历史可查)
- **废弃标记**: 在文档顶部加 `> ⚠ DEPRECATED (2026-07-02): 见 XXX.md`

---

## 7. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_DRG_DIP_RISK_REVIEW_PHASE_SUMMARY_2026-08-24.md`，记录显式编码病例本地 Provider、v8 合同、非官方分组/支付失败关闭、23-Agent 签名 HTTP E2E、串行回归和 Corti 邻近差距 | Agent Hub 本地语义能力扩展至 23/26，外部模型强依赖降至 3 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_PRINCIPAL_DIAGNOSIS_REVIEW_PHASE_SUMMARY_2026-08-24.md`，记录删除旧自动推荐、主诊断初稿证据一致性本地 Provider、v11 合同、22-Agent 签名 HTTP E2E、1203 项宽回归和 Corti 相邻编码差距 | Agent Hub 本地语义能力扩展至 22/26，外部模型强依赖降至 4 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_CLINICAL_GUIDELINES_PHASE_SUMMARY_2026-08-24.md`，记录医院批准来源/声明规则本地 Provider、v6 合同、21-Agent 签名 HTTP E2E、1193 项宽回归、ISO 时间来源审计和 Corti 官方差距 | Agent Hub 本地语义能力扩展至 21/26，外部模型强依赖降至 5 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_CLINICAL_EDUCATION_PHASE_SUMMARY_2026-08-24.md`，记录批准来源约束本地 Provider、v6 合同、20-Agent 签名 HTTP E2E、1176 项宽回归、中文脱敏修复和 Corti 官方差距 | Agent Hub 本地语义能力扩展至 20/26，外部模型强依赖降至 6 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_DENIAL_APPEALS_PHASE_SUMMARY_2026-08-24.md`，记录 Denial Appeals 本地 Provider、v3 合同、19-Agent 签名 HTTP E2E、1167 项宽回归、脱敏最长短语修复和 Corti 官方差距 | Agent Hub 本地语义能力扩展至 19/26，外部模型强依赖降至 7；官方 Pack 全部迁移至 v1.2 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_CLAIM_CHECK_PHASE_SUMMARY_2026-08-24.md`，记录 Claim Check 本地 Provider、v4 合同、18-Agent 签名 HTTP E2E、1156 项宽回归、双重脱敏修复、数据库恢复审计和 Corti Revenue Cycle 差距 | Agent Hub 本地语义能力扩展至 18/26，外部模型强依赖降至 8 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_DISCHARGE_SUMMARY_STRUCTURING_PHASE_SUMMARY_2026-08-24.md`，记录中国额外 Discharge Summary Structuring 从外部 pure-LLM 模板转为明确章节本地 Provider、v5 合同、15-Agent 四类 HTTP E2E、822 项宽回归、磁盘写满诊断和 Corti Textgen 邻近差距 | Agent Hub 本地语义能力扩展至 15/26，外部模型强依赖降至 11 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_DISCHARGE_EDUCATION_PHASE_SUMMARY_2026-08-24.md`，记录 Patient Discharge Education 从外部 pure-LLM 模板转为明确标签本地 Provider、v3 合同、14-Agent 四类 HTTP E2E、744 项宽回归和 Corti 逐项差距 | Agent Hub 本地语义能力扩展至 14/26，外部模型强依赖降至 12 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_ICU_SUMMARY_PHASE_SUMMARY_2026-08-24.md`，记录 ICU Summary 从外部模型模板转为明确标签本地 Provider、v3 合同、13-Agent 四类 HTTP E2E、719 项宽回归和 Corti 逐项差距 | Agent Hub 本地语义能力扩展至 13/26，外部模型强依赖降至 13 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_MEDICATION_RECONCILIATION_PHASE_SUMMARY_2026-08-24.md`，记录无证据肾功能/恢复条件删除、受治理本地来源比较、v4 追加合同、11-Agent 四类 HTTP E2E、745 项宽回归和 Corti 逐项差距 | Agent Hub 本地语义能力扩展至 11/26，外部模型强依赖降至 15 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_RULE_EXPLAINER_PHASE_SUMMARY_2026-08-24.md`，记录 Rule Explainer 从 LLM+Tools 转为目录事实本地 Provider、legacy 指南禁用、v4 追加合同、10-Agent 四类 HTTP E2E、726 项扩大回归和 Corti 逐项差距 | Agent Hub 本地语义能力扩展至 10/26，外部模型强依赖降至 16 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_DIAGNOSIS_EXTRACTOR_PHASE_SUMMARY_2026-08-24.md`，记录 Diagnosis Extractor 从强制 LLM+Tools 到受治理本地基线、错误 span/PASS 修正、v7 追加合同、9-Agent 四类 HTTP E2E、337 项回归和 Corti 逐项差距 | Agent Hub 本地语义能力扩展至 9/26，外部模型强依赖降至 17 |
| 2026-08-24 | 新增 `corti_parity/ICODER_GOVERNED_PROCEDURE_EXTRACTOR_PHASE_SUMMARY_2026-08-24.md`，记录 Procedure Extractor 从强制 PureLLM 到受治理本地基线、`81.0100` 错码/span 修正、8-Agent 四类 HTTP E2E、305 项回归和 Corti 逐项差距 | Agent Hub 本地语义能力扩展至 8/26，外部模型强依赖降至 18 |
| 2026-08-24 | 新增 `corti_parity/ICODER_AGENT_HUB_LOCAL_SEMANTIC_E2E_PHASE_SUMMARY_2026-08-24.md`，记录 7-Agent 真实本地 HTTP 四类 E2E、ICD Navigator/Note Completeness 语义修正、264 项回归、90/90 预检，以及严格 26-Agent 门禁仍为 0/26 的诚实边界 | Agent Hub 本地语义证据阶段收口 |
| 2026-08-23 | 新增 `corti_parity/ICODER_AGENT_HUB_CLONE_PROJECTION_PHASE_SUMMARY_2026-08-23.md`，记录 Hub-visible Pack Clone、完整 Registry 投影、字段漂移修复、双投影 ownership、5168 项全量回归及项目副本定制执行 P0 差距 | 关闭 Clone 404 与重复启动投影漂移 |
| 2026-08-23 | 新增 `corti_parity/ICODER_AGENT_HUB_PROJECT_CLONE_RUNTIME_PHASE_SUMMARY_2026-08-23.md`，记录 Clone→Customize→Run/A2A 双身份、Provider Expert、Connector Graph、三 SDK、Windows 稳定性与当前 Corti 差距 | 关闭项目副本定制执行 P0 并保留语义/生产外部门禁 |
| 2026-08-23 | 新增 `corti_parity/ICODER_GOVERNED_EVIDENCE_EXTRACTOR_PHASE_SUMMARY_2026-08-23.md`，记录显式候选码精确提及定位、声明区遮蔽、上下文标记、v11 合约、6/20 离线矩阵与 Corti 全病历证据抽取差距 | Evidence Extractor 本地能力收敛 |
| 2026-08-23 | 新增 `corti_parity/ICODER_GOVERNED_EVIDENCE_RANKER_PHASE_SUMMARY_2026-08-23.md`，记录保守文档可追溯性排序、span 校验、v4 合约、5/21 离线矩阵、986/986 回归与 Corti 邻近能力差距 | Evidence Ranker 本地能力收敛 |
| 2026-08-23 | 新增 `corti_parity/ICODER_GOVERNED_ICD_NAVIGATOR_PHASE_SUMMARY_2026-08-23.md`，记录 Navigator 受治理本地 Search/一层 Explore、双资产完整性、v4 合约、4/22 离线矩阵、967/967 回归与 Corti 差距 | ICD-10 Navigator 本地能力收敛 |
| 2026-08-23 | 新增 `corti_parity/ICODER_GOVERNED_CODE_VALIDATION_PHASE_SUMMARY_2026-08-23.md`，记录 Code Validation 受治理本地目录、v7 合约、3/23 离线矩阵、957 项扩展回归与 Corti 语义差距 | Code Validation 本地基线收敛 |
| 2026-08-23 | 新增 `corti_parity/ICODER_NOTE_COMPLETENESS_LOCAL_RULES_PHASE_SUMMARY_2026-08-23.md`，记录 Note Completeness 本地 7+1 章节规则、统一 Run/A2A/Hub Provider 归因、24/2 离线矩阵与 602/602 回归 | Agent Hub 本地确定性能力收敛 |
| 2026-08-23 | 新增 `corti_parity/ICODER_AGENT_HUB_TENANT_RUNTIME_READINESS_PHASE_SUMMARY_2026-08-23.md`，记录公开/租户 Hub 边界、探针/Canary 租户隔离、前端整批失败关闭及三 SDK `beta.28`/`b28` 合同 | Agent Hub 租户运行就绪收敛 |
| 2026-08-23 | 新增 `corti_parity/ICODER_HTTPX2_TESTCLIENT_ZERO_WARNING_PHASE_SUMMARY_2026-08-23.md`，记录 5002 项严格零告警回归、80/80 预检和 26/26 Agent 运行矩阵 | 关闭 Starlette TestClient 最后一条已知弃用告警 |
| 2026-08-23 | 新增 `corti_parity/ICODER_STRICT_WARNING_NATIVE_WORKER_PHASE_SUMMARY_2026-08-23.md`，记录严格 5001 项完整回归、79/79 预检、Worker 握手与置信度边界 | 持续开发门禁收敛 |
| 2026-08-22 | 新增 `corti_parity/ICODER_FULL_BACKEND_RELEASE_GATE_PHASE_SUMMARY_2026-08-22.md`，记录 4996 项完整默认后端通过、78/78 预检与 26/26 Agent 运行矩阵 | 完整后端发布门阶段总结 |
| 2026-07-02 | 初始版本, 文档索引 + 5 分钟新人路径 | P1.3 Stage 4 文档重写 |
