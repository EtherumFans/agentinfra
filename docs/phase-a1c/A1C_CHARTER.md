# A1C — Hospital Pilot Readiness & Integration Validation — CHARTER

**Phase**: A1C — 医院试点部署准入与集成验证 (Hospital Pilot Readiness & Integration Validation)
**Charter version**: 1.0 (2026-07-25)
**Execution prompt**: `C:\Users\huawei\Downloads\iCoDer Phase A1C 医院试点部署准入与集成验证.pdf`
**Opened**: 2026-07-25 (A1C.0 charter + entry audit + RV consistency)
**Worktree (primary)**: `E:/Corti4C`
**Branch (A1C commits stack onto)**: `phase-a1a/emergency-containment` (local-only)
**Baseline ancestor (predecessor)**: `3d50b11` (A1A Gate 4R-I.11 closure)
**Reference phase (A1B-AE-RV terminal)**: `0f107d0` on `phase-a1b/agent-expert-terminal-reverification` (separate worktree `E:/Corti4C-agent-expert-reverification`)

---

## §一 阶段定位

A1C 不是上线阶段,也不是部署阶段。A1C 回答且只回答一个问题:

> **iCoDer 是否已经具备进入一家真实医院进行受控试点的工程条件?**

允许的最终裁决**(三选一,不得创造模糊裁决)**:

| Verdict | 含义 |
|---------|------|
| `PASS_A1C_READY_FOR_CONTROLLED_HOSPITAL_PILOT_ENTRY` | 全部 21 项硬门槛满足;可进入受控试点准入流程。不等同生产就绪。 |
| `PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN` | 至少一项硬门槛未满足;blocker 已列入 `A1C_OPEN_BLOCKERS.csv`。 |
| `FAIL_A1C_HOSPITAL_PILOT_READINESS_NOT_DEMONSTRATED` | 发现严重安全/租户隔离/数据丢失/迁移缺陷。 |

`PASS` 仅表示 `READY_FOR_CONTROLLED_HOSPITAL_PILOT_ENTRY`,不解释为生产就绪或正式部署就绪。

---

## §二 继承的真实状态 (不得覆盖、淡化或重新解释)

A1C 承接 A1B-AE-RV 终态 `PASS_A1B_AE_RV_TERMINAL_EVIDENCE_REPAIR_FULL_REGRESSION_MIGRATION_CONTEXT_SCRUB_PUBLIC_EXPERT_LIVE_AND_HEADED_WORKFLOWS_VERIFIED` (commit `0f107d0`,2026-07-25)。继承的 5-tuple 状态在 A1C 全程**不得变更**:

| 字段 | 值 | 来源 |
|------|-----|------|
| `GATE4_8_NO_NEW_REGRESSION_CLAIM` | `CONTRADICTED` | A1A Gate 4R-I (a2613b7) |
| `GATE4_9_FINAL_PASS` | `SUPERSEDED` | A1A Gate 4R-I (a2613b7) |
| `GATE4_ACCEPTANCE_STATUS` | `REOPENED` | A1A Gate 4R-I (a2613b7) |
| `CORTI_PARITY_VERDICT` | `NOT_DEMONSTRATED` | A1A Gate 4R-I (1a9cbe7, 52.6% weighted) |
| `PRODUCTION_READINESS` | `NOT_VERIFIED` | A1A Gate 4R-I (a2a1136) |

A1B-AE-RV 继承的事实清单(以下 BLOCKED/未解决项**继续生效**带入 A1C):

- PostgreSQL migration scenarios — `BLOCKED_BY_ENVIRONMENT` (no psql/docker/podman on host)
- 88 个历史基线失败 (spec/STT/oauth/health_check 债务, A1B-AE-RV §五 列为 out-of-scope)
- 1 个 DevDbSessionGuard teardown 归因噪声 (test body PASS)
- ESLint `BLOCKED_BY_MISSING_DEV_DEPENDENCY`
- 部分浏览器旅程 `BLOCKED_BY_MISSING_UI` (J4/J5) 或 `BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT` (J8)

---

## §三 A1C 不得直接宣称的裁决 (Charter §一 红线)

下列裁决在 A1C 全程**禁用**。任何子门若需要宣称,必须先升级 Charter:

1. `PRODUCTION_READY`
2. `READY_FOR_HOSPITAL_DEPLOYMENT`
3. `CLINICAL_GRADE_VERIFIED`
4. `PHI_BOUNDED` (除非 §十三 A1C.6 全部约束得到充分证明)
5. `CORTI_PARITY_VERIFIED`
6. `CORTI_AGENTIC_PARITY_VERIFIED`
7. `READY_FOR_MVP_SHIP`
8. `FULLY_VERIFIED`

---

## §四 10 子门序列

| 子门 | 标题 | 主要交付 |
|------|------|----------|
| A1C.0 | 入场审计与试点准入 Charter | 5 份 deliverable (本文件 + ENTRY_AUDIT + BASELINE_STATE + ACCEPTANCE_MATRIX + RV_CLOSEOUT_CONSISTENCY) |
| A1C.1 | 历史基线失败清理与 CI 信号恢复 | BASELINE_FAILURE_LEDGER.csv + ROOT_CAUSE_REPORT + CI_GATE_POLICY + DEV_DB_ISOLATION_REPORT + ESLINT_INTRODUCTION_REPORT + CI_TEST_COLLECTION_DIFF.json |
| A1C.2 | PostgreSQL 生产等价迁移验证 | docker-compose.a1c-postgres.yml + MIGRATION_MATRIX + RESULTS + CONSTRAINT_REPORT + RECOVERY_REPORT |
| A1C.3 | HIS/EMR 集成契约与模拟器 | INTEGRATION_CONTRACT.md + 3 schema JSON + SIMULATOR/ + SCENARIO_MATRIX.csv |
| A1C.4 | 身份、SSO、租户和组织授权闭环 | IDENTITY_AUTH_MODEL + ROLE_PERMISSION_MATRIX + CROSS_TENANT_ATTACK_MATRIX + SSO_INTEGRATION_TEST_RESULTS + AUTH_AUDIT_REPORT |
| A1C.5 | DeepSeek 云服务与 KMS 密钥闭环 | KMS_INTEGRATION_REPORT + SECRET_LEAK_SCAN + DEEPSEEK_FAILURE_MODE_MATRIX + LIVE_TEST_RESULTS + AI_DISABLED_MODE_REPORT |
| A1C.6 | PHI 边界、脱敏、驻留与审计验证 | PHI_DATA_FLOW_DIAGRAM + 3 MATRIX + REDACTION_TEST_RESULTS + AUDIT_EVENT_SCHEMA + AUDIT_COMPLETENESS_REPORT |
| A1C.7 | 部署、可观测性、故障恢复与回滚 | PILOT_DEPLOYMENT_ARCHITECTURE + DEPLOYMENT_RUNBOOK + OBSERVABILITY_SPEC + FAILURE_INJECTION_RESULTS + ROLLBACK_DRILL_REPORT |
| A1C.8 | 真实浏览器端到端试点旅程 (≥15 旅程) | 每旅程 9 件证据 (step_log/network_manifest/console/screenshots/trace.zip/video.webm/secret_leak_count/backend_trace/audit_events) |
| A1C.9 | 最终准入裁决与试点 Runbook | A1C_FINAL_VERDICT + A1C_FINAL_STATE.json + A1C_FINAL_COMMIT_MANIFEST.json + A1C_EVIDENCE_SHA256SUMS.detached.txt + A1C_PILOT_READINESS_MATRIX.csv + A1C_OPEN_BLOCKERS.csv + 3 Runbooks + A1C_EVIDENCE_INDEX.md |

子门不得跳过。每完成一个子门必须输出 8 项:Sub-gate / Commit / Files changed / Tests / Evidence / Findings / Remaining blockers / Verdict。

---

## §五 执行原则

### 5.1 先审计,后开发
任何修改前全面审查 (worktree/branch/HEAD/CI/DB/部署/OpenAPI/SDK/身份体系/租户边界/Context 生命周期/KMS/HIS 接口/审计/可观测性/健康检查/数据迁移/浏览器旅程/历史失败)。每项能力必须标记 `EXISTS_AND_VERIFIED` / `EXISTS_BUT_UNVERIFIED` / `PARTIALLY_IMPLEMENTED` / `MISSING` / `BLOCKED_BY_ENVIRONMENT` / `OUT_OF_SCOPE`。

### 5.2 证据优先
每个 PASS 必须有可复现证据:执行命令 + Git SHA + 配置摘要 + 测试结果 + JUnit/JSON/CSV + 失败日志 + 环境信息 + 截图/视频/trace + SHA-256 指纹。**不得仅在 Markdown 中声称通过**。

### 5.3 不掩盖历史问题
禁止排除失败测试 / 修改收集规则 / 跳过测试 / 删除测试 / 缩小测试范围 / 用 mock 替代真实调用 / 把功能缺失改写为"符合预期" / 将环境 blocker 写成 PASS / 将历史失败直接忽略而不建立债务台账。

### 5.4 医疗系统 fail-closed
以下信息缺失时默认拒绝继续:organization_id / tenant_id / 操作用户身份 / 患者上下文 / 数据来源系统 / 请求用途 / 审计 trace ID / 密钥来源 / 数据驻留区域 / 必要授权信息。**禁止自动填写生产环境默认值**。

### 5.5 连续执行
Charter §20 pattern — 在授权范围内连续推进,不要在每个子门之间等待人工确认,除非遇到真实外部硬 blocker。

---

## §六 Git 与执行纪律 (PDF §十五)

### 6.1 禁用操作 (zero tolerance)

| 类 | 禁用项 |
|----|--------|
| 远端 | `git push` / `gh pr create` / deploy 到真实医院 |
| 历史 | amend A1B-AE-RV 历史提交 / rebase / squash / 删除 tag |
| 提交 | `git add -A` / `git add .` / `git commit -a` / 删除失败测试 / 用跳过代替修复 |
| 替代 | 用 mock 代替真实 KMS 或 DeepSeek 最终验证 / 提交真实密钥到仓库 |

### 6.2 强制操作

- 每个子门独立提交 (推荐序列 A1C.0..A1C.9)
- 每次提交使用**明确文件列表** (禁用 `add -A`/`add .`/`commit -a`)
- 提交前 `git diff --check`
- 提交信息记录:测试命令 + 结果 + 当前 blocker + (不提前发出最终裁决)
- 中间子门 verdict 必须用 `*_FILED` / `*_VERIFIED` / `BLOCKED_BY_*` 三类之一

### 6.3 允许操作

- 在 `phase-a1a/emergency-containment` 上**新增** A1C.* commits
- `--no-ff merge` 已存在的 RV/R 分支以整合工作 (Gate 4R-I.1 先例 ca36c51)
- 新建 annotated tag (`audit/phase-a1c-*`) 标记关键基线 (local-only)
- 在 worktree 内编辑/新增文件

---

## §七 A1C.0 范围 (本子门)

### 必须完成
1. 记录 repository / worktree / branch / HEAD / parent SHA / dirty state / remote state / runtime versions / OS
2. 核查 A1B-AE-RV 终态:
   - RV.7 commit 是否真实落盘 → ✓ `0f107d0` (truth)
   - `PENDING_RV7_COMMIT` 是否全部回填 → ✗ 见 §八 IC-1..IC-3
   - `FINAL_VERDICT.md` / `FINAL_COMMIT_MANIFEST.json` / `A1B_AE_RV_STATE.json` 是否一致 → ✗ 见 §八
   - evidence 数量 400 vs 403 → ✗ 真相 = **403**,见 §八 IC-4
   - SHA manifest 自指问题 → ✗ 见 §八 IC-5
   - 本地 annotated tag 是否真实指向 RV.7 commit → ✓ `audit/phase-a1b-ae-rv-baseline-8546184` → `0f107d0` (truth)

### 处理 RV 不一致 (per PDF §四)
- **不得**重写 RV 历史
- 在 A1C.0 内**新建 closeout commit** 记录原始错误 / 修正值 / 修正原因
- **生成 detached SHA manifest** (新 manifest 不包括自身,避免自指)

### 验收 (§四 验收)
- 不存在未解释的 `PENDING_*` → 本子门全部归零或转入 `A1C_OPEN_BLOCKERS.csv`
- 所有最终 SHA 一致 → A1C_BASELINE_STATE.json 与 closeout report 一致
- 证据数量定义唯一 → **403** 为 A1C 锁定值
- SHA manifest 不自相矛盾 → A1C.0 内生成的 `A1C_ENTRY_SHA256SUMS.detached.txt` 不含自身
- 阶段 PASS/PARTIAL/FAIL 规则提前冻结 → 本 §一/§六 已冻结

---

## §八 A1B-AE-RV 封版元数据不一致清单 (A1C.0 核查输出)

| ID | 文件 | 字段 | 错误值 | 真相 (truth) | 修正原因 |
|----|------|------|--------|--------------|----------|
| IC-1 | `FINAL_VERDICT.md` L9 | `head_sha` | `58e9ddd` (RV.6) | `0f107d0` (RV.7) | 文件在 RV.7 commit 内写入,只能感知 parent |
| IC-1 | `A1B_AE_RV_STATE.json` L9 | `head_sha` | `58e9ddd...` | `0f107d0...` | 同上 |
| IC-1 | `FINAL_COMMIT_MANIFEST.json` L10 | `head_sha` | `58e9ddd...` | `0f107d0...` | 同上 |
| IC-2 | `A1B_AE_RV_STATE.json` L165 | `RV.7.commit` | `PENDING_RV7_COMMIT` | `0f107d0` | 未在 commit 后回填 |
| IC-2 | `FINAL_COMMIT_MANIFEST.json` L68 | `RV.7.sha` | `PENDING_RV7_COMMIT` | `0f107d0694867a84cced54e8a2e7948dc04d8bdb` | 同上 |
| IC-3 | `A1B_AE_RV_STATE.json` L83 | `RV.4.commit` | `PENDING_RV4_COMMIT` | `2a83f63` | STATE.json 未回填,但 MANIFEST.json L47 已有真值 (跨文件不一致) |
| IC-4 | `FINAL_COMMIT_MANIFEST.json` L124 | `evidence_files_total` | `400` | `403` | `wc -l EVIDENCE_SHA256SUMS.txt` = 403 |
| IC-4 | `A1B_AE_RV_STATE.json` L139 | sha256_manifest 注释 | `(400 entries)` | `(403 entries)` | 同上 |
| IC-4 | `FINAL_VERDICT.md` L202 | 段落 | `(400 evidence files fingerprinted)` | `(403 ...)` | 同上 |
| IC-4 | `A1B_AE_RV_STATE.json` L174 | `evidence_files_fingerprinted` | `403` | `403` | **此字段是真相**,与其他字段冲突 |
| IC-5 | `EVIDENCE_SHA256SUMS.txt` L8 | 自指 | `d6212d9c...  EVIDENCE_SHA256SUMS.txt` | 应不含自身 | manifest 把自己列了进去,导致 SHA 不稳定 (改变 manifest 内容即改变自身 hash) |

**A1C.0 处理**:
- **不**修改 RV 分支 (`phase-a1b/agent-expert-terminal-reverification`) 上的原文件 → 遵守 §六/6.1 禁用 amend
- 在 A1C 仓库 (`phase-a1a/emergency-containment`) 内记录本不一致清单 → 已在 `A1B_AE_RV_CLOSEOUT_CONSISTENCY_REPORT.md` 详述
- 在 A1C.0 内生成 `A1C_ENTRY_SHA256SUMS.detached.txt` (新 manifest,**不含自身**,避免 IC-5 类问题)
- 不一致项**不影响**RV.7 PASS verdict 的有效性 — PASS 是基于 33 条 Charter §十三 验收条件,而非基于元数据 SHA 准确性

---

## §九 21 项硬门槛 (PDF §十四)

只有**同时全部**满足,才允许 `PASS_A1C_READY_FOR_CONTROLLED_HOSPITAL_PILOT_ENTRY`:

1. PostgreSQL 全部要求场景 PASS
2. 默认 CI 无未解释 failed/error
3. ESLint PASS
4. Dev DB 与测试 DB 完全隔离
5. Context 生命周期闭环 (Create/Delete/Expire)
6. HIS/EMR 标准契约和模拟器完成
7. 跨租户攻击用例全部拒绝
8. 真实 SSO/OIDC 流程完成
9. DeepSeek 真实调用完成
10. KMS 真实接入完成
11. Secret leak count = 0
12. PHI 数据流和驻留边界明确
13. AI 关闭模式完整可用
14. 审计事件完整
15. 部署可重复
16. 健康检查准确
17. 监控和告警可用
18. 故障注入完成
19. 回滚演练完成
20. ≥15 条真实浏览器旅程全部完成
21. 不存在 P0 blocker

任意一项未满足 → `PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN`。
发现严重安全/租户隔离/数据丢失/迁移缺陷 → `FAIL_A1C_HOSPITAL_PILOT_READINESS_NOT_DEMONSTRATED`。

---

## §十 预期 BLOCKED 项目 (Charter §20 pattern, 本机环境)

| 项目 | 子门 | 原因 | 缓解 |
|------|------|------|------|
| PostgreSQL 16 实例 | A1C.2 | host 无 docker / psql / podman | 列入 OPEN_BLOCKERS;在 A1C.2 内准备 docker-compose.a1c-postgres.yml + 模拟矩阵,真正 PG run 留给医院 pilot 环境 |
| DeepSeek 真实云调用 | A1C.5 | LLM_API_KEY 未注入 | 列入 OPEN_BLOCKERS;在 A1C.5 内验证 backend 已 wire DeepSeek client + 真实调用占位 |
| KMS 真实接入 | A1C.5 | 无云 KMS 凭证 | 列入 OPEN_BLOCKERS;在 A1C.5 内验证 secret loader 抽象 + 本地 envoy 模拟 |
| 真实 SSO/OIDC IdP | A1C.4 | 无医院 IdP 凭证 | 列入 OPEN_BLOCKERS;在 A1C.4 内自起 test IdP (dex / Keycloak 容器) |
| 真实 HIS/EMR | A1C.3 | 无医院 HIS 凭证 | 列入 OPEN_BLOCKERS;在 A1C.3 内建 HIS/EMR Simulator |

PDF §十六 已认可:**"如遇到真实外部环境缺失,不得伪造结果,先完成可在本地完成的实现、模拟器和证据,将外部依赖明确列入 blocker,最终根据硬门槛诚实输出 PARTIAL 或 FAIL。"**

---

## §十一 A1C 子门 verdict 进展

| 子门 | 状态 | Commit | Verdict |
|------|------|--------|---------|
| A1C.0 | in_progress | (this commit) | (待发) |
| A1C.1 | pending | — | — |
| A1C.2 | pending | — | — |
| A1C.3 | pending | — | — |
| A1C.4 | pending | — | — |
| A1C.5 | pending | — | — |
| A1C.6 | pending | — | — |
| A1C.7 | pending | — | — |
| A1C.8 | pending | — | — |
| A1C.9 | pending | — | — |

---

## §十二 Charter 冻结声明

本 Charter 在 A1C.0 内冻结。后续子门如需扩展范围、变更裁决规则或解除 §三 红线,**必须**新建 Charter 修订 commit 并标注版本号 (e.g., v1.1)。在 Charter 修订落盘前,所有子门继续按 v1.0 执行。

**A1C 开始执行。**
