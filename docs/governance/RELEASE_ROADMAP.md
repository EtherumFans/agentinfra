# iCoDer Release Roadmap — Master Tracker

> **Scope**: 跨 phase 的发布前任务清单，覆盖"试点准入 → 商业试点 → GA 全面开放"三个层级。
> **Source**: 基于 `reports/comprehensive-audit/GATE14_ISSUE_GRADING_ROADMAP_FINAL_VERDICT.md` + `reports/phase-a1c/A1C.9/A1C_FINAL_VERDICT.md` + 各 phase MEMORY.md 状态。
> **Last refresh**: 2026-08-05（A1C.9 PARTIAL 后；A1D 未启动）
> **Authority**: 此文档是 dashboard，不替代任何 charter 或 phase final verdict。Charter §22 的 8 个禁用 verdict 在此文档中同样禁用。

---

## 1. 当前状态摘要

| 维度 | 当前值 | 来源 |
|---|---|---|
| 主线 phase | A1C CLOSED（10/10 子门 filed） | `reports/phase-a1c/A1C.9/A1C_FINAL_VERDICT.md` |
| A1C verdict | `PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN` | 同上 |
| 5-tuple（不可变更） | `GATE4_8=CONTRADICTED / GATE4_9=SUPERSEDED / GATE4_ACCEPTANCE=REOPENED / CORTI_PARITY=NOT_DEMONSTRATED(52.6%) / PRODUCTION_READINESS=NOT_VERIFIED` | A1A Gate 4R-I |
| 综合审计 verdict | `INTERNAL_R_AND_D_PROJECT_NOT_HOSPITAL_PILOT_READY` | `GATE14_ISSUE_GRADING_ROADMAP_FINAL_VERDICT.md` |
| 21 hard gates | 6 PASS + 1 PRIOR_PASS + 8 PARTIAL + 6 BLOCKED_BY_ENV | `A1C_PILOT_READINESS_MATRIX.csv` |
| A1C 开放 blockers | 12（0 P0 security/tenant/data-loss；9 Pilot-env-gated + 11 Eng-in-A1D）| `A1C_OPEN_BLOCKERS.csv` |
| GATE14 P0 | 16 个，其中 **6 已 closed**（A1A Gate 1/2/3R/4 + A1D-DEV.8），**10 仍 OPEN** | 本文档 §2.2 |
| 禁用 verdict（8） | `PRODUCTION_READY` / `READY_FOR_HOSPITAL_DEPLOYMENT` / `CLINICAL_GRADE_VERIFIED` / `PHI_BOUNDED` / `CORTI_PARITY_VERIFIED` / `CORTI_AGENTIC_PARITY_VERIFIED` / `READY_FOR_MVP_SHIP` / `FULLY_VERIFIED` | Charter §22 |

**注**：A1C 已 closed 不等于试点准入通过。"PARTIAL" 意味着工程条件部分就绪，仍有 12 个 blockers 阻碍真实医院试点启动。

---

## 2. 三层级任务清单

### 2.1 Layer 1 — 试点准入（A1C → PASS_A1C）⏱ 工程部分 ~2-3 周 + Pilot env 并行 provisioning

**目标**: 把 A1C verdict 从 `PARTIAL` 升级到 `PASS_A1C_READY_FOR_CONTROLLED_HOSPITAL_PILOT_ENTRY`。
**前置关键路径**: Pilot 云账号 + DNS CNAME + 真实医院 IdP metadata。

#### 2.1.1 工程类（A1D 可闭，~2-3 周）

| ID | 任务 | 当前状态 | 来源 |
|---|---|---|---|
| A1C-B-002 | 88 个历史基线失败 triage（spec/STT/oauth/health_check 债务） | 待 A1D 分批修 | `A1C_OPEN_BLOCKERS.csv` |
| A1C-B-003 | ESLint 引入（`npm ci` in `frontend/`） | 待 A1D | 同上 |
| A1C-B-007 | DeepSeek fallback provider 实现（Azure-OpenAI / Qwen / Moonshot ≥1） | DESIGN only | 同上 |
| A1C-B-008 | KMS key rotation + cache invalidation（KMS version token） | DESIGN only | 同上 |
| A1C-B-010 | allow-side `policy_decision` audit 接入（rbac_role + abac_purpose_match + tenant_match） | 当前仅 deny-side emit | 同上 |
| A1C-B-011 | `purpose_of_use` 写入每条 `audit_log.details` row | DESIGN | 同上 |
| A1C-B-012 | DeepSeek egress 显式 decision log（非 region-default implicit） | DESIGN | 同上 |
| A1C-B-015 | webhook delivery queue：Postgres LISTEN/NOTIFY vs Redis Stream 选型 + 接入 | DESIGN | 同上 |
| A1C-B-018 | `ICODER_AUDIT_WRITE_PAUSED` flag（PITR 回滚时停 audit 写） | 未实现 | 同上 |
| A1C-B-020 | `CDI_SPECIALIST` + `MEDICAL_RECORDS_ADMIN` UserRole 扩展 + migration | DESIGN | 同上 |

#### 2.1.2 Pilot-env 类（关键路径，与 A1D 并行）

| ID | 任务 | 前置 | 来源 |
|---|---|---|---|
| A1C-B-001 | PostgreSQL 16 真实 `alembic upgrade head`（CHECK / JSONB / partial index / advisory lock） | Pilot 云账号 | 同上 |
| A1C-B-004 | 真实医院 IdP SSO/OIDC live journey | 医院 IdP metadata | 同上 |
| A1C-B-005 | KMS provider 选型（Aliyun / Tencent / Huawei / Vault）+ adapter 实现 | Pilot 云账号 | 同上 |
| A1C-B-006 | DeepSeek API key 经 KMS 注入 | A1C-B-005 | 同上 |
| A1C-B-009 | live HAR capture + PHI regex 扫描（11 脱敏面真实测试） | Pilot 部署 | 同上 |
| A1C-B-013 | `api.cn.icoder.cloud` DNS CNAME + TLS cert | Pilot 云账号 | 同上 |
| A1C-B-014 | Prometheus exporter + Sentry CN relay 接入（14 metrics + 10 alerts） | Pilot 云账号 | 同上 |
| A1C-B-016 | toxiproxy 故障注入（17 scenarios live replay） | Pilot 部署 | 同上 |
| A1C-B-017 | blue/green + PITR 回滚 live drill | 多副本 Pilot 环境 | 同上 |
| A1C-B-019 | 20-journey live replay（PDF ≥15） | Pilot 部署 | 同上 |

**Layer 1 出口条件**: 21 hard gates 全部 PASS / PRIOR_PASS，`A1C_OPEN_BLOCKERS.csv` 清空 → A1C charter 允许重裁 → 升级 `PASS_A1C_READY_FOR_CONTROLLED_HOSPITAL_PILOT_ENTRY`。

---

### 2.2 Layer 2 — 商业试点可启动（GATE14 Phase B）⏱ ~6 周 + 等保认证并行 3-6 月

**目标**: 让一家真实医院能签合同、部署、付费、跑生产。

#### GATE14 16 个 P0 中仍 OPEN 的 10 个

| P0 ID | 任务 | 现状 | 估时 |
|---|---|---|---|
| G13-002 | **等保2.0 三级** 启动认证（不可压缩 3-6 月） | 未启动 | 立即启动 |
| G11-001 / G13-004 | 选定**唯一**部署路径并落地（cloud SaaS or on-prem Docker） | Charter 当前强制 cloud-only；CLAUDE.md "不再支持医院内网 Docker" 与 GATE14 推荐（on-prem）冲突 — **战略决策** | 2 周 |
| G13-001 | 支付接入（Stripe 国际 / 微信 / 支付宝 CN）+ 真实计费 | 0 transactions; fake ¥50 balance | 1 周 |
| G13-003 | Privacy Policy + Terms + DPA + SLA 模板（`/legal/*`） | 0 legal docs | 3 天 |
| G13-006 | 定价方案（Pilot / Pro / Enterprise 三档） | 无 tiers / 无 contracts | 3 天 |
| G5-004 | **CDI 临床闭环**：医生答复机制 + 文档修订跟踪 + 再编码反馈 | 443 queries emitted / 0 responses | 2 周 |
| G10-001 | **201-case F1 baseline** 月度运行（当前仅 20-case） | A1D-DEV.8 仅 20-case | 持续 |
| G3-001 / G12-002 | 删除 13 个 Corti 外链 + 战略定位重写 | `docs.corti.ai/*` + `help.corti.app/*` 仍在 AI Studio | 1 周 |
| G8-001 | npm publish `@icoder/sdk@1.0.0` + `@icoder/embedded@2.x` | registry 仍 404 | 1 天 |

#### GATE14 16 P0 中已 CLOSED（仅记录，不再追踪）

| P0 ID | 任务 | Closed by |
|---|---|---|
| G9-001 | `SECRET_KEY=change-me` 移除 | A1A Gate 1 |
| G9-002 | audit coverage（5 → 全） | A1A Gate 3R |
| G9-003 | tenancy NULL 235/240 → backfill | A1A Gate 2 |
| G7-001 | `RUNTRACE_STORE` flip memory→db | A1A Gate 3R |
| G9-005 | at-rest encryption | A1A Gate 4 |
| G5-001 / G5-002 | cost=0 hardcode 修复 | A1D-DEV.8 B-003 |

**Layer 2 出口条件**: 16 P0 全部 closed + 1 家 design-partner 医院签约 + 真实部署 + 真实计费运行。

---

### 2.3 Layer 3 — GA 全面开放（GATE14 Phase C+D）⏱ ~12 周 + ongoing

**目标**: 4 核心能力 production-ready + 战略定位去 Corti-clone + 销售可复制。

| ID | 任务 | 类型 |
|---|---|---|
| G12-003 | Medical Coding F1@1 ≥ 0.80（持续评测 + 调优） | 核心 capability |
| G12-003 | CDI 达 `PASS_READY_FOR_CDI_FORMAL_QUALITY_BENCHMARK` | 核心 capability |
| G5-007 | DRG grouper 接入产线 coding-compliance run（当前 real 但 unused） | 核心 capability |
| G5-008 | DIP 真实实现（当前 501 + demo HTML） | 核心 capability |
| G2-003 / G5-005 | 13 metadata-only Agent Hub 卡片：实现 or 移除 | 产品决策 |
| G6-001/002/003 | 收敛 3 个并行 runtime 层 + 3 个 expert 层级 + 删 legacy `app/tools/` | 重构 |
| G10-002 | model identifier 收敛到 1 个（当前 4 个：`deepseek-chat` / `deepseek-v4` / `deepseek-v4-flash` / 等） | 清理 |
| G10-003 | 资产上传到 OSS / `ICODER_ASSET_BUCKET` 真实接入（当前 gitignored + 单 Windows 路径） | 基础设施 |
| G13-005 / G13-007 | ≥1 design-partner 签约 + ISV 合伙协议模板 | 销售 |
| G11-002 | 生产 latency 监控（P99 ≤ 120s 验证） | 观测 |
| G11-003 | 前端 Vitest 单测（当前 0 个） | 测试 |
| G11-004 | release 自动化（semantic versioning + changelog） | 工程基础设施 |
| G11-005 | ops runbook（事件响应 / 备份恢复） | 运维 |
| G10-005 | held-out 评测集（脱离 CCL 2026 train monoculture） | 评测 |
| A1E-GP1 BLK-1 | 独立人工接受性验证（10×3×3 journey 矩阵，21/24 DONE，3 blocked） | 验证 |

**Layer 3 出口条件**: 4 核心能力 production-ready + 等保2.0 三级证书 + 战略定位重写完成 + ≥1 真实医院付费运行 ≥3 月稳定。

---

## 3. 关键风险与判断题

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | **战略定位矛盾** — Charter §22 禁止 `CORTI_PARITY_VERIFIED`，但 UI/CLAUDE/README 仍说"Corti-competitive"。Corti parity 实际 34%/52.6%（维度不同）。 | 高 — 给医院买方制造"低质 Corti 克隆"印象 | G3-001 + G12-002；改为"中国本地化医疗合规 AI，Corti-parity 架构" |
| R2 | **CN/EN 评测不对称** — A1D-DEV.8 Corti head-to-head DEFERRED 到 pilot gate（DeepSeek 中文 vs Corti 英文不可直接对比）。F1 数字不能直接用于 Corti 比较。 | 中 — 容易误读竞争力 | held-out 双语评测集；不要在 marketing 引用 Corti 数字 |
| R3 | **A1E-GP1 独立验证缺口** — 21/24 charter 条件 DONE，3 blocked on BLK-1（需独立人执行 10×3×3）。工程完整 ≠ 产品接受。 | 中 — 工程团队自证无效 | 招募独立 dev / 外部接受性伙伴 |
| R4 | **等保认证不可压缩** — 3-6 个月，是 GA 时间表硬关键路径。 | 高 — 不启动则 GA 永远追不上 | 立即启动，与 Layer 2 并行 |
| R5 | **PostgreSQL 真实运行从未做过** — SQLite parity 通过，但 PG 特有行为（CHECK / JSONB / partial index / advisory lock）从未在真实 PG 16 上跑过 alembic upgrade。 | 中 — 可能暴露 6+ 月 hidden bugs | A1C-B-001 必须在 Pilot 启动前完成 |
| ~~R6~~ | **部署路径已定 — cloud-only**（2026-08-06 战略评审决策；详见 `docs/governance/DEPLOYMENT_PATH_ADR.md`）。Charter §产品定位 + CLAUDE.md 立场强化，GATE14 on-prem 推荐被战略覆盖。 | 已 closed — reversibility triggers 见 ADR §6（连续 3 家拒签 / 等保拒绝 / 监管变化）| 已闭，无需后续行动 |
| R7 | **3 个并行 runtime 层 + 3 个 expert 层级** — 重构债务 12 周规模。 | 中 — 影响新功能速度 | Layer 3 G6 收敛，不要在收敛前加新 feature |

---

## 4. 时间表

```
Layer 1 (试点准入 PASS):
  Eng blockers (A1D):       2-3 周
  Pilot env provisioning:   3-4 周（并行）
  ─────────────────────────────────
  关键路径:                  4-6 周

Layer 2 (商业试点可启动):
  Phase B 工程:              6 周（与 Layer 1 重叠）
  等保2.0 三级:              3-6 月（不可压缩，并行）
  Design-partner 销售:      4-8 周（与上并行）
  ─────────────────────────────────
  关键路径:                  ~3 月（含等保）

Layer 3 (GA 全面开放):
  Phase C 工程:              12 周
  Pilot 真实运行:            ≥3 月稳定
  ─────────────────────────────────
  关键路径:                  ~6-9 月（与 Layer 2 重叠后）

总计: GA ≈ 12 个月（GATE14 P8 估算）
```

---

## 5. Verdict 升级路径

| 当前 verdict | 升级目标 | 触发条件 |
|---|---|---|
| `PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN` | `PASS_A1C_READY_FOR_CONTROLLED_HOSPITAL_PILOT_ENTRY` | 12 A1C blockers 全闭 + 21 hard gates 全 PASS |
| `CORTI_PARITY=NOT_DEMONSTRATED` (52.6%) | 不可升级到 `CORTI_PARITY_VERIFIED`（charter 禁用） | 只能改 "Corti-parity 架构" framing |
| `PRODUCTION_READINESS=NOT_VERIFIED` | 不可升级到 `PRODUCTION_READY`（charter 禁用） | 走 `READY_FOR_PILOT` → `PILOT_IN_PRODUCTION` → GA 路径 |
| `GATE4_ACCEPTANCE=REOPENED` | 重裁为 `PASS` | A1D 阶段重新执行 Gate 4 验证（含真实 Pilot 环境） |

---

## 6. 维护规则

1. 本文档**只在 phase 边界更新**（A1D 启动 / Pilot 启动 / GA 启动），不在子门粒度更新 — 子门追踪在各 phase 的 FINAL_VERDICT.md。
2. **不重复 GATE14 issue grading** — 引用 P0/P1/P2 ID 即可，详情看 `reports/comprehensive-audit/GATE14_*`。
3. **不引入新 verdict** — 严格遵守 Charter §22 禁用列表。
4. **战略决策点必须显式标 RISK** — 例如 R6 部署路径，不允许在文档里隐式决定。
5. 与 `MEMORY.md` 互补：MEMORY.md 记录历史 verdict，本文档记录 forward-looking 任务。

---

## 7. 引用

- Charter: `docs/phase-a1c/A1C_CHARTER.md`（A1C v1.0）+ `docs/governance/CHARTER_INDEX.md`
- 综合 verdict: `reports/comprehensive-audit/GATE14_ISSUE_GRADING_ROADMAP_FINAL_VERDICT.md`
- A1C 终态: `reports/phase-a1c/A1C.9/A1C_FINAL_VERDICT.md` + `A1C_PILOT_READINESS_MATRIX.csv` + `A1C_OPEN_BLOCKERS.csv`
- 5-tuple 不可变更来源: A1A Gate 4R-I（commit a2613b7 / 1a9cbe7 / a2a1136）
- A1E-GP1 状态: `project_phase_a1e_gp1_2026_07_30.md`（MEMORY.md）
- Corti 对等审计: `docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md`

---

**文档版本**: 1.0（2026-08-05 初始创建，A1C.9 PARTIAL 后）
**下次评审触发**: A1D.0 启动 / Pilot 云账号 provisioning 完成 / 等保认证启动 — 任一发生时
