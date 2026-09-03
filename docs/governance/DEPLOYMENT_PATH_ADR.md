# ADR-001 — Deployment Path Decision: Cloud-Only

> **Status**: ACCEPTED
> **Date**: 2026-08-06
> **Decider**: Product Owner (战略评审)
> **Source**: `docs/governance/RELEASE_ROADMAP.md` §3 R6（部署路径战略未定 → 已定）
> **Authority**: 本 ADR 是战略决策记录。Charter §22 的 8 个禁用 verdict 在此 ADR 中同样禁用。

---

## 1. Context — 为什么需要决策

RELEASE_ROADMAP.md §3 R6 列出三方冲突：

| 来源 | 立场 | 强度 |
|---|---|---|
| Charter §产品定位 | 强制 cloud-only（托管云 SaaS）| 强 |
| CLAUDE.md | "不再支持医院内网 Docker 部署"| 强 |
| GATE14 综合 verdict | 推荐 on-prem given China hospital preference | 中（推荐性，非强制）|

R6 风险声明：**决策推迟会 cost 重做**。Layer 2（商业试点可启动）启动前必须定。

## 2. Decision

**ACCEPTED**: iCoDer 部署路径 = **cloud-only 托管 SaaS**。

具体含义：
- 后端 = 多租户 FastAPI on 托管控制面（`https://{tenant_slug}.{region}.icoder.cloud`）
- 三层架构：Environment (EU/US/CN) → Tenant (医院) → API Client (backend-service 或 ROPC embedded)
- 医院 HIS/EMR 通过 API Client 接入（OAuth 2.0 client_credentials 或 ROPC）
- Runtime 是 iCoDer Server 内核（非独立 pip 包安装到医生电脑）
- **不支持**：医院内网 Docker 部署、on-prem 单租户私有部署、便携 Runtime、offline-only 模式

## 3. Consequences

### Positive
- **单一部署路径**：工程、运维、SRE、计费、监控、安全都围绕一套架构 — 不分裂团队
- **与已有投入一致**：Phase 7（Partner Reference App / Three Demos / Gate 13 Embedded Assistant）+ Phase A1A Gate 4（PHI 边界 + 租户隔离 + at-rest encryption）+ Phase A1D（KMS / 多 LLM provider / audit pause）全部基于 cloud 假设
- **商业模式清晰**：multi-tenant SaaS pricing tier（Pilot / Pro / Enterprise）天然适配
- **Charter / CLAUDE.md 无需重写**：决策 = 强化现有立场

### Negative
- **中国医院 on-prem 偏好**：三甲医院 IT 部门保守派（数据不出院原则）对 SaaS 排斥
- **等保 2.0 三级合规路径变窄**：必须通过 cloud region + KMS + 跨境数据评估 + 网信办备案 解决，不能靠物理隔离
- **网络隔离客户不可达**：军医 / 公安系统 / 部分国企的物理隔离内网医院无法接入
- **GATE14 on-prem 推荐被拒**：审计文档需明确记录此决策的依据

### Neutralizations (缓解措施)
- 区域数据驻留已实现（EU/US/CN regions，详见 Phase A1A Gate 4 + DataPolicy）
- China region 走 `api.cn.icoder.cloud` 子域名 + 国内云厂商（阿里云 / 腾讯云 / 华为云）
- KMS 加密 + per-tenant keys（A1D.6 部分实现，需 Pilot 期落地 per-tenant KMS adapter）
- 数据不出境 + 跨境评估（China PIPL 合规）
- 未来 Pilot 反馈可考虑：**cloud-first 但医院可选区域 provider**（不是 on-prem，而是多 cloud 厂商选项）

## 4. Alternatives Considered

### Alt-A: On-prem Docker (GATE14 推荐)
**拒绝**，理由：
- Charter §产品定位 明确 multi-tenant SaaS，on-prem 单租户私有部署与 Charter 冲突
- 多租户 SaaS 商业模式不可逆（pricing tier / billing / quota / observability 全部基于 cloud）
- Phase 7 / Phase A1A 全栈投入基于 cloud 假设，转 on-prem 等于推倒重来
- 运维多套部署（cloud + on-prem）= 成本爆炸 + 团队分裂
- 等保合规问题在 on-prem 同样存在（医院内网 ≠ 等保通过）

### Alt-B: Hybrid (cloud SaaS + on-prem Docker for 保守客户)
**拒绝**，理由：
- 双路径分裂工程团队（cloud team + on-prem team）
- 数据同步 / 跨租户一致性 / 跨云迁移复杂度爆炸
- 反而增加运维负担（两个 SRE pipeline）
- 时间表：双路径开发 12-18 月，远超 Pilot 关键路径
- 商业上：维护两套 pricing tier + 两套 SLA

### Alt-C: Cloud-only with hybrid region (cloud 厂商可选，不可 on-prem)
**保留为未来 Pilot 反馈驱动 feature**，但本 ADR 不预先承诺。当前决策 = Alt-D。

### Alt-D: Cloud-only with region tenant isolation（**本决策**）
- 多 cloud 厂商支持（CN region: 阿里/腾讯/华为云任选；EU/US region: AWS/Azure/GCP）
- 单租户隔离通过 KMS per-tenant key + 数据库 row-level security
- 不允许 on-prem，但允许"医院选择哪个 cloud 厂商"

## 5. Implications for Other Artifacts

| 文档 / 资产 | 影响 | 行动 |
|---|---|---|
| `CLAUDE.md` §部署模型 | 一致（已声明 cloud-only）| 无需修改 |
| `docs/cloud/CLOUD_DEPLOYMENT.md` | 一致 | 无需修改 |
| `docs/governance/RELEASE_ROADMAP.md` §3 R6 | 风险状态变更 | 标 DECIDED + 指向本 ADR |
| `reports/comprehensive-audit/GATE14_*` | on-prem 推荐被战略覆盖 | 添加 ADR 引用注脚（不动原文）|
| Charter | 一致 | 无需修改 |
| `.env.cloud.example` | 一致 | 无需修改 |

## 6. Reversibility

**Low reversibility**：此决策一旦写入 Charter + 落地 Pilot，反悔成本 = 重做工程栈。

**Reversibility triggers**（什么情况下可能重审）:
1. Pilot 阶段连续 3 家 design-partner 医院明确因 cloud-only 拒签 — 触发 Charter 重审
2. 等保 2.0 三级证书在 cloud-only 模式下被监管明确拒绝 — 触发混合模式评估
3. 中国监管环境发生重大变化（如新增 "医疗数据强制本地化" 法规，cloud SaaS 模式不再合规）— 触发紧急重审

以上任一发生时，本 ADR Status 变更 `SUPERSEDED`，新建 ADR-002。

## 7. Validation Plan

本 ADR 的有效性由以下条件验证：
- **Pilot 阶段**：≥ 1 家 design-partner 医院接受 cloud-only 模式并签约
- **等保 2.0 三级**：在 cloud-only 模式下获得证书（不可在物理隔离 on-prem 模式获得）
- **数据合规**：China PIPL + 网信办跨境评估通过
- **客户接受性**：A1E-GP1 BLK-1 独立验证矩阵 (10×3×3) 中 cloud-only journey 全 PASS

任一失败则触发 §6 重审。

## 8. References

- `docs/governance/RELEASE_ROADMAP.md` §3 R6（决策来源）
- `CLAUDE.md` §部署模型（既有立场）
- `docs/cloud/CLOUD_DEPLOYMENT.md`（实施细节）
- `reports/comprehensive-audit/GATE14_ISSUE_GRADING_ROADMAP_FINAL_VERDICT.md`（被覆盖的 on-prem 推荐）
- Charter §产品定位（强制 cloud-only）
- Charter §22 禁用 verdict 列表

---

**文档版本**: 1.0（2026-08-06 初始创建）
**Verdict**: PARTIAL_R6_DEPLOYMENT_PATH_DECIDED_CLOUD_ONLY_FILED（不接受 VERIFIED — 战略决策需 Pilot 客观验证）
**下次评审触发**: §6 任一 reversibility trigger 发生 / Pilot 签约 / 等保 2.0 三级结果
