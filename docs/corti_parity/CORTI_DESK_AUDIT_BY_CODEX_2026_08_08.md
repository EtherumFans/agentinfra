# Corti Desk Audit by Codex — 2026-08-08

> **Verdict**: `PARTIAL_CORTI_DESK_AUDIT_BY_CODEX_*_FILED` (NOT VERIFIED, NOT BINDING)
> **Audit date**: 2026-08-08
> **iCoDer HEAD**: `8b69847` (phase-a1a/emergency-containment, NEVER pushed)
> **Corti reference source**: `docs/corti-reverse-engineered/` (214 files, public Corti docs)
> **Corti live access**: BLOCKED (5-min token TTL + Cloudflare bot detection, per A1E-GP1 memory)
> **Reviewer**: Codex (NOT an independent human reviewer per Charter §Gate 7)

---

## §0 非免责声明 (Read This First)

本文件是 **Codex 自审 desk audit**, 不是 Charter verdict. 它 **不能** 用于:

1. 升级 `CORTI_PARITY` 5-tuple 状态 (仍 `NOT_DEMONSTRATED`)
2. 宣称任何 `PROVEN_SUPERIOR_KEEP` / `CORTI_PARITY_DEMONSTRATED` / `VERIFIED` 等 8 forbidden verdicts
3. 替代独立人类 reviewer (Charter §Gate 7 final clause)
4. 引用为 user-visible 跨厂商比较 claim (违反 R2 EVALUATION_CITATION_POLICY.md §2 rule 3)

本文件 **能** 用于:

1. 作为 fresh Corti re-gate reviewer pack (`docs/corti_parity/FRESH_REGATE_REVIEWER_PACK.md`) 的 evidence 输入
2. 帮助独立 reviewer 快速锁定 high-value 审查点
3. 记录 Codex 当前对 Corti 公开文档的理解 + iCoDer 对照点

**每个 finding 都标 `NEEDS_INDEPENDENT_REVIEW`**. Codex 看到的 Corti 文档是公开快照, 不是 Corti 真实生产行为. 实际 Corti 平台可能有未公开的能力 / gap.

---

## §1 Corti 公开 reference baseline 抽出

来源: `docs/corti-reverse-engineered/docs-site/_extracted/*.md` (13 files) + `api-contracts*.json` (3 files) + `feature-flows/*.png` (19+ flows).

### §1.1 架构

Corti Agentic Framework 三件套 (per `agentic_architecture.md`):
- **Orchestrator** — 中央协调者, 接收 user request → 分派给 Experts
- **Experts** — 特化子 agent, 通过 MCP 调外部服务
- **Memory** — 持久化 context + state, 让 Orchestrator 跨 conversation 保持连续性

### §1.2 A2A protocol 元素 (per `agentic_core-concepts.md`)

| 元素 | Corti 描述 |
|---|---|
| Agent Card | JSON metadata, identity + endpoint + capabilities + skills + auth |
| Task | 有 ID + lifecycle 的 stateful work unit |
| Message | 单轮 communication, role + content |
| Part | 内容容器 (TextPart / DataPart / FilePart) |
| Artifact | Task 的 tangible output (document / image / structured data) |
| Context | `contextId` 把多个 Task 串起来 (per encounter / call / workflow) |

### §1.3 Authentication (per `authentication_overview.md`)

OAuth 2.0 `client_credentials` grant. 流程:
```
Service → POST /token (grant_type, client_id, client_secret) → 200 OK + access_token
Service → API Request (Authorization: Bearer + Tenant-Name: base)
```

Corti API server URL: `https://api.{environment}.corti.app/v2/` (environment: `eu` / `us`).

### §1.4 Coding capability (per `api-reference_codes_predict-codes.md`)

`POST /tools/coding/` — stateless, 支持 code systems:
- ICD-10-CM, ICD-10-PCS (US)
- ICD-10 (international)
- ICD-10-UK, CIM-10-FR, ICD-10-GM (regional)
- OPCS-4, OPS, CCAM (procedure)
- CPT

Request: `{text | documentId, codeSystems}`. Response: `{Codes, Candidates}` (Candidates = 低 confidence 备选).

### §1.5 Expert registry (per `agentic_experts.md`)

Common registry experts (9 列出):
- `memory-expert`, `coding-expert`, `medical-calculator-expert`, `drugbank-expert`
- `posos-expert`, `pubmed-expert`, `clinical-trials-expert`, `web-search-expert`
- `interviewing-expert`

Bring Your Own Expert via MCP server registration.

### §1.6 Healthcare-by-design 7 原则 (per `agentic_overview.md`)

Safety First / Auditability / Domain-Specific Reasoning / Multi-Agent Architecture / Memory & Context / Prebuilt Experts / Third-Party Integrations / Run-time Context.

---

## §2 iCoDer 当前状态 (HEAD `8b69847`)

### §2.1 架构 (per CLAUDE.md)

四层架构:
- L1 Runtime Core (`icoder_runtime/`) — AgentRunner / LLMGateway / Registry / Observability / DataPolicy
- L2 Compliance Services (`compliance_services/`) — RuleEngine + MedicalCodingRuleSet (12 rules)
- L3 Official Agent Packs (`official_agents/`) — Medical Coding Agent
- L4 Business Workbenches (`app/api/*`) — ~190 endpoints

两个 CORE_ENTRY_AGENT (Phase 5 Track D):
- **CDI Agent** — 临床文档改进
- **Medical Coding Agent** — ICD-10-CN + ICD-9-CM-3 编码

### §2.2 A2A 支持

- A2A JSON-RPC v0.3.0 at `/agents/{id}/v1` (per CORTI-AGENT-DEV-RESEARCH-01 memory)
- Agent Card 在 `agent-card.json` (NOT `/card`)
- `_MEDICAL_CODING_AGENT_IDS` frozenset 路由 medical coding agent 走 fast-path

### §2.3 Authentication

- OAuth 2.0 `client_credentials` at `POST /api/oauth/token`
- Realm hint-only, JWT `org_id` authoritative
- Access token TTL 5 min (实测, per Sprint 2 live verify)
- API Clients 端点: `/api/clients/{id}/rotate|disable|enable` (Sprint 2 commit `1ff7973`)

### §2.4 Coding capability

- MedCodER 5-stage pipeline (per CLAUDE.md): Extraction / Retrieval / Merge / Re-rank / Compliance+Calibration
- 支持 ICD-10-CN + ICD-9-CM-3 (中国国标)
- 数据资产: 37,897 codes + 75,968 synonyms + 6,490 evidence patterns + 2,090 differentiation pairs
- BGE-M3 (1024-dim) + FAISS retrieval
- 20-case live benchmark: full=0.109/0.190/0.187 F1@1/2/5 (per A1D-DEV D.8 memory)

### §2.5 Expert registry

A1B-AE phase 已建 9 个 Corti-aligned Expert keys (6 reference stubs):
- memory / coding / drugbank / posos / pubmed / clinical-trials / web-search / medical-calculator / interviewing

Public Expert MCP 已搭骨架 (`app/icoder/mcp/`), 但 PubMed / ClinicalTrials / MCP live 测试仍 deferred (per A1B-AE memory tech debt).

### §2.6 Auditability

- `audit_logs` table + `run_history` + `run_trace` (Migration 019/020/030)
- Trace capture state machine (`trace_capture_status` 6-literal)
- AuditDetailRedactor (Phase A1A Gate 4.3) allowlist chokepoint
- 3-layer fail-closed tenancy (Pydantic + ORM + DB CHECK)

---

## §3 Capability-by-capability desk comparison

**Verdict scale** (本 audit 自定义, NOT Charter verdicts):
- **DESK_PARITY_MATCHES** — Corti 公开描述的能力 iCoDer 也有等价实现
- **DESK_PARITY_REGIONAL_DIVERGENT** — 双方都有此能力, 但针对不同 region / 标准
- **DESK_PARITY_BENIGN_GAP** — 一方有, 另一方没, 但不影响核心医疗编码场景
- **DESK_PARITY_INFERIOR_CANDIDATE** — iCoDer 实现明显落后, 但需 reviewer 实测确认
- **DESK_PARITY_SUPERIOR_CANDIDATE** — iCoDer 实现可能领先, 但需 reviewer 实测确认

**所有 findings 标 `NEEDS_INDEPENDENT_REVIEW`** — Codex 不能自判 PROVEN_SUPERIOR 或 PROVEN_INFERIOR.

### §3.1 架构模式

| 维度 | Corti 公开描述 | iCoDer 现状 | Desk parity | 备注 |
|---|---|---|---|---|
| Orchestrator | 中央协调者 | `AgentRunner` (L1) | MATCHES | 名称不同, 职责相同 |
| Experts | 特化子 agent via MCP | A1B-AE Expert registry (9 keys, 6 stubs) | MATCHES | iCoDer stub 多, MCP live 弱 |
| Memory | 跨 conversation context | RunHistory + PatientContext | MATCHES | iCoDer 偏 audit-trace 而非 conversation memory |

### §3.2 A2A protocol

| 维度 | Corti | iCoDer | Desk parity |
|---|---|---|---|
| Agent Card JSON | ✓ | ✓ (`agent-card.json`) | MATCHES |
| Task lifecycle | ✓ | ✓ (RunHistory `state_history`) | MATCHES |
| Message + Part | ✓ (Text/Data/File) | ✓ (input.text + input.extra) | MATCHES |
| Artifact | ✓ | partial (`result.markdown` 不是独立 Artifact 对象) | BENIGN_GAP |
| Context (contextId) | ✓ | partial (run_id + trace_id, 无 explicit contextId 串多 task) | BENIGN_GAP |
| JSON-RPC v0.3 endpoint | (Corti 内部) | ✓ (`/agents/{id}/v1`) | MATCHES |

### §3.3 Authentication

| 维度 | Corti | iCoDer | Desk parity |
|---|---|---|---|
| OAuth 2.0 client_credentials | ✓ | ✓ | MATCHES |
| Token endpoint | `POST /token` | `POST /api/oauth/token` | MATCHES (path 不同, 都符合 RFC 6749) |
| Bearer token in Authorization | ✓ | ✓ | MATCHES |
| Tenant hint | `Tenant-Name: base` header | JWT `org_id` authoritative + Tenant-Name hint-only | MATCHES (iCoDer 更严, JWT 强制) |
| Region selector | `environment: eu\|us` | `ICODER_ENVIRONMENT: eu\|us\|cn` | MATCHES (iCoDer 多 CN) |
| Client lifecycle (rotate/disable) | (Corti 公开文档无此细节) | ✓ `/api/clients/{id}/rotate\|disable\|enable` | SUPERIOR_CANDIDATE (iCoDer Sprint 2 加, Corti 公开文档无描述) |

### §3.4 Coding capability

| 维度 | Corti | iCoDer | Desk parity |
|---|---|---|---|
| ICD-10-CM (US) | ✓ | ✗ (iCoDer 中国医院定位, 不支持 US 临床修改版) | REGIONAL_DIVERGENT |
| ICD-10-PCS (US procedure) | ✓ | ✗ | REGIONAL_DIVERGENT |
| ICD-10 (international) | ✓ | partial (ICD-10-CN 是中国版, 不是 WHO 原版) | REGIONAL_DIVERGENT |
| ICD-10-CN | ✗ (Corti 不在中国市场) | ✓ | REGIONAL_DIVERGENT (iCoDer only) |
| ICD-9-CM-3 (CN procedure) | ✗ | ✓ | REGIONAL_DIVERGENT (iCoDer only) |
| ICD-10-UK / CIM-10-FR / ICD-10-GM / OPCS-4 / OPS / CCAM / CPT | ✓ | ✗ | BENIGN_GAP (iCoDer 区域专注) |
| Multi-code-system per request | ✓ | partial (CN 主要) | REGIONAL_DIVERGENT |
| Response shape: Codes + Candidates | ✓ | ✓ (`extracted_diagnoses` + `top_k_chips` 仿 Candidates) | MATCHES |
| Pipeline stages | (Corti 公开为 black-box) | MedCodER 5-stage (Extraction/Retrieval/Merge/Re-rank/Compliance) | SUPERIOR_CANDIDATE (iCoDer 公开论文级管线, Corti 不公开) |
| Retrieval-augmented (RAG) | (未公开) | ✓ BGE-M3 + FAISS, 37,897 codes | SUPERIOR_CANDIDATE |
| Compliance rule engine | (未公开) | ✓ `MedicalCodingRuleSet` 12 rules (R001-R010 + MC-R-M80-001) | SUPERIOR_CANDIDATE |
| Coding differentiation KB | (未公开) | ✓ 2,090 code-pair P0/P1/P2 决策 | SUPERIOR_CANDIDATE |

**Key observation**: iCoDer 与 Corti 在 coding 维度是 **区域互补** 而非直接竞争. Corti 覆盖欧美多 code system, iCoDer 专注中国国标. 同 LLM 同双语评测才能横比 (R2 前提 #3).

### §3.5 Expert registry

| 维度 | Corti | iCoDer | Desk parity |
|---|---|---|---|
| First-party Expert 数 | 9+ (memory/coding/calc/drugbank/posos/pubmed/clinical-trials/web-search/interviewing) | 9 (相同 keys, 6 reference stubs) | INFERIOR_CANDIDATE (iCoDer stub 多, 实跑少) |
| Bring Your Own Expert via MCP | ✓ | ✓ (`app/icoder/mcp/`) | MATCHES |
| MCP transport: streamable_http | ✓ | ✓ | MATCHES |
| MCP authentication | ✓ (per `mcp-authentication`) | partial (`auth_resolver.py` + `auth.py`, 缺完整 OAuth flow) | INFERIOR_CANDIDATE |
| PubMed / ClinicalTrials live | (presumed live) | DEFERRED (VCR fixtures only, A1B-AE memory) | INFERIOR_CANDIDATE |

### §3.6 Auditability

| 维度 | Corti | iCoDer | Desk parity |
|---|---|---|---|
| Replayable traces | ✓ (per `agentic_overview.md` "replayable traces and structured logs") | ✓ (`run_trace` table + trace_capture_status state machine) | MATCHES |
| Structured logs | ✓ | ✓ (`audit_logs` JSON details) | MATCHES |
| PHI redaction | (Corti 公开未细化) | ✓ AuditDetailRedactor (Phase A1A Gate 4.3) allowlist + per-tenant encryption | SUPERIOR_CANDIDATE (iCoDer 公开实现细) |
| Per-tenant KMS | (Corti /safety 引用 Azure AD + per-customer keys per ICODER-CORTI-AGENT-DEV-GAP-01 G.8-R1) | partial (KMSVersionToken + CredentialVault cache stamping, 缺 real cloud KMS adapter) | INFERIOR_CANDIDATE (iCoDer 框架就绪, 云集成 deferred) |
| Compliance certifications | FIPS AES + HIPAA/GDPR/SOC2/ISO27001 + DRATA (per G.8-R1) | ✗ (Pilot 阶段未做认证) | INFERIOR_CANDIDATE |

### §3.7 Healthcare-by-design 7 原则

| Corti 原则 | iCoDer 实现 | Desk parity |
|---|---|---|
| Safety First | 7-stage 编码 + Compliance RuleEngine + Deny-First 权限 | MATCHES |
| Auditability | 3-layer fail-closed + trace state machine | MATCHES |
| Domain-Specific Reasoning | MedCodER + CDI Agent (Phase 5 Track D) | MATCHES |
| Multi-Agent Architecture | A2A v0.3 + Agent Hub (24 visible) | MATCHES |
| Memory & Context | partial (run-scoped, 缺 conversation-scoped) | INFERIOR_CANDIDATE |
| Prebuilt Experts | A1B-AE 9 stubs | INFERIOR_CANDIDATE |
| Third-Party Integrations | MCP support + 4 LLM fallback factories | MATCHES |
| Run-time Context | ✓ PatientContext (FHIR-aligned) | MATCHES |

---

## §4 高价值审查点 (给独立 reviewer)

按 desk audit 视角, 独立 reviewer 应优先实测以下 5 点 (capability matrix P0):

1. **Coding 准确率 head-to-head** — 同一英文病历在 Corti (ICD-10-CM) 与 iCoDer (翻译成中文后跑 ICD-10-CN) 上跑, 比 F1. **当前阻塞**: 双语 100-case 评测集只 5-case (held_out_bilingual_v1.json).
2. **Latency** — Corti A2A v0.3 endpoint vs iCoDer `/api/v1/agents/{id}/run`. **历史数据**: iCoDer 4.77s vs Corti 3.88s (per A1D.5R memory). **需 fresh 重测**.
3. **Cost** — 同 input 在两家跑, 比成本. **当前阻塞**: Corti 凭证 + 实时定价.
4. **Expert availability** — Corti 9+ first-party Experts vs iCoDer 9 (6 stubs). **需 Corti live 验证 stub-vs-real 差距**.
5. **Audit completeness** — Corti "replayable traces" 公开描述 vs iCoDer `run_trace` 表实测. **需 Corti live 抓 trace 样本对照**.

---

## §5 区域互补, 非直接竞争 (key insight)

iCoDer 与 Corti 在用户群 + code system + 区域合规上是 **互补** 而非直接竞争:

| 维度 | Corti | iCoDer |
|---|---|---|
| 主要市场 | EU + US | CN (中国医院) |
| 主要 code system | ICD-10-CM/PCS + ICD-10 (intl) + 区域变体 | ICD-10-CN + ICD-9-CM-3 |
| 部署模型 | Corti-managed cloud | 托管云 SaaS (R6 决策) |
| 合规框架 | HIPAA / GDPR / SOC2 / ISO27001 | 等保 + PIPL + 个人信息保护法 (Pilot 阶段) |

直接 PROVEN_SUPERIOR / PROVEN_INFERIOR 比较需要双语 100-case + 同 LLM + 独立 reviewer (R2 EVALUATION_CITATION_POLICY.md §2 rule 3 + 5 前提). **当前 0/5 前提满足**.

---

## §6 本 desk audit 自评局限性

1. **Corti 公开文档快照** — 214 files 抓取时间不一, 可能滞后于 Corti 实际产品.
2. **0 live 验证** — Codex 没跑 Corti API, 也没跑 Corti 浏览器. 所有 Corti 行为基于公开文档描述.
3. **iCoDer 自报数据** — F1 数字 / latency / Expert count 都是 iCoDer 自测, 没独立验证.
4. **PROVEN_SUPERIOR 候选需保留怀疑** — §3 中标 SUPERIOR_CANDIDATE 的项是基于"Corti 公开文档没说"推得, Corti 可能实际有此能力只是未公开.
5. **PROVEN_INFERIOR 候选同样需保留怀疑** — iCoDer 的 stub / deferred 状态可能已在我没读到的 commit 中改进.
6. **区域互补不是劣势** — iCoDer 不支持 ICD-10-CM 不是 bug, 是定位选择.

---

## §7 输出建议

独立 reviewer 接手时, 应:

1. **不引用本文件作为 verdict** — 用 `FRESH_REGATE_REVIEWER_PACK.md` 的 §5 checklist 重做.
2. **优先验证 §4 的 5 P0 审查点** — 这些是 desk audit 锁定的高 ROI 实测点.
3. **对每个 SUPERIOR_CANDIDATE / INFERIOR_CANDIDATE 标记做 live 验证** — Codex 标记只是猜测.
4. **把本文件作为 evidence-for-reviewer 而非 evidence-from-reviewer** — direction 是 Codex → reviewer, 不是反向.

---

## §8 引用

- `docs/corti-reverse-engineered/docs-site/_extracted/agentic_overview.md` — Corti 7 设计原则
- `docs/corti-reverse-engineered/docs-site/_extracted/agentic_architecture.md` — Orchestrator/Experts/Memory 三件套
- `docs/corti-reverse-engineered/docs-site/_extracted/agentic_core-concepts.md` — A2A 6 元素
- `docs/corti-reverse-engineered/docs-site/_extracted/agentic_experts.md` — Expert registry 9 keys + MCP BYOE
- `docs/corti-reverse-engineered/docs-site/_extracted/agentic_orchestrator.md` — Orchestrator 6 职责
- `docs/corti-reverse-engineered/docs-site/_extracted/authentication_overview.md` — OAuth 2.0 client_credentials
- `docs/corti-reverse-engineered/docs-site/_extracted/api-reference_codes_predict-codes.md` — Coding code systems
- `docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md` — 2026-07-02 baseline
- `docs/corti_parity/CORTI_PARITY_GAP_ANALYSIS.md`
- `docs/corti_parity/FRESH_REGATE_REVIEWER_PACK.md` — reviewer checklist
- `docs/governance/EVALUATION_CITATION_POLICY.md` — 5 规则
- `MEMORY.md` → `project_a1e_gp1_2026_07_30.md` — 10×3×3 capability matrix BLK-1
- `MEMORY.md` → `project_icoder_corti_agent_dev_gap_2026_07_29.md` — G.8-R1 corti.ai/safety verbatim
- `CLAUDE.md` — iCoDer 架构 + MedCodER 管线 + 货币约定
- HEAD `8b69847` (phase-a1a/emergency-containment, NEVER pushed)
