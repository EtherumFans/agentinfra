# A1D — Layer 1 工程债务清理与 CI 信号恢复 — CHARTER

**Phase**: A1D — Layer 1 工程债务清理与 CI 信号恢复 (Engineering Debt Cleanup & CI Signal Restoration)
**Charter version**: 1.0 (2026-08-05)
**Execution prompt**: `docs/governance/RELEASE_ROADMAP.md` §2.1.1 (master tracker)
**Opened**: 2026-08-05 (A1D.0 charter + entry audit)
**Worktree (primary)**: `E:/Corti4C`
**Branch (A1D commits stack onto)**: `phase-a1a/emergency-containment` (local-only, never pushed)
**Baseline ancestor (predecessor)**: `0a7bb11` (RELEASE_ROADMAP v1.0)
**Reference phase (A1C terminal)**: `209f25a` on `phase-a1a/emergency-containment` — `PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN`

---

## §一 阶段定位

A1D 不是上线阶段、不是部署阶段、不是试点准入阶段。A1D 回答且只回答一个问题:

> **A1C.9 列出的 9 个 Engineering 类 open blockers 是否全部清零,使 Layer 1 工程部分达到可重裁 A1C 的状态?**

A1D 严格不处理 9 个 Pilot-env-gated blockers (A1C-B-001/004/005/006/009/013/014/016/017/019) — 这些是 Pilot ops 责任,与 A1D 工程工作并行推进,不进入 A1D verdict 范围。

允许的最终裁决**(三选一,不得创造模糊裁决)**:

| Verdict | 含义 |
|---------|------|
| `PASS_A1D_LAYER1_ENGINEERING_DEBT_CLEARED_ALL_9_ENG_BLOCKERS_CLOSED` | A1C-B-002/003/007/008/010/011/012/015/018/020 全部 closed;回归全 PASS;CI 信号 clean;Layer 1 工程部分可请求 A1C 重裁。**不等于**试点准入通过 — A1C 重裁仍需 Pilot env 12 blockers 闭环。 |
| `PARTIAL_A1D_SOME_ENG_BLOCKERS_REMAIN` | 至少一项 Eng blocker 未闭;已列入 `A1D_OPEN_BLOCKERS.csv`。 |
| `FAIL_A1D_ENGINEERING_REGRESSION` | 修复过程引入 P0 安全/租户隔离/数据丢失/迁移损坏缺陷,或回归数 > A1C.9 基线。 |

`PASS_A1D` **不代表**:
- ❌ 生产就绪 / 医院部署就绪 (Charter §22 禁用)
- ❌ A1C 重裁为 `PASS_A1C_READY_FOR_CONTROLLED_HOSPITAL_PILOT_ENTRY` (那是 A1C charter 范围,需 Pilot env 12 blockers 同步闭环后由 A1C charter v1.x 流程处理)
- ❌ Corti parity / PHI bounded / Clinical grade (Charter §22 禁用)

---

## §二 继承的真实状态 (不得覆盖、淡化或重新解释)

A1D 承接 A1C.9 终态 `PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN` (commit `209f25a`,2026-07-25)。继承的 5-tuple 状态在 A1D 全程**不得变更**:

| 字段 | 值 | 来源 |
|------|-----|------|
| `GATE4_8_NO_NEW_REGRESSION_CLAIM` | `CONTRADICTED` | A1A Gate 4R-I (a2613b7) |
| `GATE4_9_FINAL_PASS` | `SUPERSEDED` | A1A Gate 4R-I (a2613b7) |
| `GATE4_ACCEPTANCE_STATUS` | `REOPENED` | A1A Gate 4R-I (a2613b7) |
| `CORTI_PARITY_VERDICT` | `NOT_DEMONSTRATED` (52.6% weighted) | A1A Gate 4R-I (1a9cbe7) |
| `PRODUCTION_READINESS` | `NOT_VERIFIED` | A1A Gate 4R-I (a2a1136) |

A1C.9 继承并继续生效的事实清单 (以下 BLOCKED/未解决项**继续生效**带入 A1D):

- A1C 12 open blockers 见 `reports/phase-a1c/A1C.9/A1C_OPEN_BLOCKERS.csv`
  - **9 个 Engineering 类** (A1D 范围): A1C-B-002/003/007/008/010/011/012/015/018/020
  - **9 个 Pilot-env 类** (A1D 范围外,并行推进): A1C-B-001/004/005/006/009/013/014/016/017/019
- A1C 5-tuple 状态不可变更 (见上表)
- Charter §22 8 个禁用 verdict 继续生效

---

## §三 A1D 不得直接宣称的裁决 (Charter §22 红线 + A1D-specific)

下列裁决在 A1D 全程**禁用**。任何子门若需要宣称,必须先升级 Charter:

### 3.1 继承自 Charter §22 (8 个)

1. `PRODUCTION_READY`
2. `READY_FOR_HOSPITAL_DEPLOYMENT`
3. `CLINICAL_GRADE_VERIFIED`
4. `PHI_BOUNDED`
5. `CORTI_PARITY_VERIFIED`
6. `CORTI_AGENTIC_PARITY_VERIFIED`
7. `READY_FOR_MVP_SHIP`
8. `FULLY_VERIFIED`

### 3.2 A1D-specific (3 个)

9. `A1C_REASSESSED_PASS` — A1C 重裁必须由 A1C charter v1.x 流程处理,不由 A1D 宣称
10. `Pilot_ENV_READY` — Pilot env 状态由 Pilot ops 团队宣称,不由 A1D 宣称
11. `LAYER1_COMPLETE` — Layer 1 包含工程 + Pilot env 两部分,工程部分闭 ≠ Layer 1 完整

---

## §四 7 子门序列

| 子门 | 标题 | 覆盖 A1C blockers | 主要交付 |
|------|------|-------------------|----------|
| A1D.0 | 入场审计与 A1D Charter | — | 4 deliverable (本文件 + ENTRY_AUDIT + BASELINE_STATE + A1C_PREDECESSOR_CONSISTENCY_REPORT) |
| A1D.1 | ESLint 引入与前端 lint 信号恢复 | A1C-B-003 | ESLINT_BASELINE.json + LINT_FAILURE_TRIAGE.csv + ESLINT_RULE_TUNING.md + FRONTEND_LINT_INTRODUCTION_REPORT.md |
| A1D.2 | 小基础设施: audit pause + egress decision log + webhook queue | A1C-B-012, A1C-B-015, A1C-B-018 | 3 source code changes + 3 unit test suites + SMALL_INFRA_CHANGELOG.md |
| A1D.3 | 身份与审计: UserRole 扩展 + audit_middleware 改造 | A1C-B-010, A1C-B-011, A1C-B-020 | alembic migration N + UserRole enum + audit_middleware patches + IDENTITY_AUDIT_REPORT.md |
| A1D.4 | 云弹性: KMS rotation + LLM fallback provider | A1C-B-007, A1C-B-008 | kms_version_token.py + fallback_provider.py (≥1 impl) + FALLBACK_FAILOVER_TEST_RESULTS.json + KMS_ROTATION_REPORT.md |
| A1D.5 | CI 信号: 88 个历史基线失败 triage | A1C-B-002 | BASELINE_FAILURE_LEDGER.csv (root-caused) + 4 per-suite fix batches (spec/STT/oauth/health_check) + CI_GATE_POLICY.md |
| A1D.6 | 最终裁决与状态归档 | — | A1D_FINAL_VERDICT.md + A1D_FINAL_STATE.json + A1D_FINAL_COMMIT_MANIFEST.json + A1D_EVIDENCE_SHA256SUMS.detached.txt + A1D_OPEN_BLOCKERS.csv (应清空) |

子门不得跳过。每完成一个子门必须输出 8 项:Sub-gate / Commit / Files changed / Tests / Evidence / Findings / Remaining blockers / Verdict。

---

## §五 执行原则

### 5.1 先审计,后开发
任何修改前全面审查该 blocker 的真实状态(EXISTS_AND_VERIFIED / EXISTS_BUT_UNVERIFIED / PARTIALLY_IMPLEMENTED / MISSING / BLOCKED_BY_ENVIRONMENT / OUT_OF_SCOPE)。**不得直接打字"修一下"**。

### 5.2 证据优先
每个 PASS 必须有可复现证据:执行命令 + Git SHA + 配置摘要 + 测试结果 + JUnit/JSON/CSV + 失败日志 + 环境信息。**不得仅在 Markdown 中声称通过**。

### 5.3 不掩盖历史问题
禁止排除失败测试 / 修改收集规则 / 跳过测试 / 删除测试 / 缩小测试范围 / 用 mock 替代真实调用 / 把功能缺失改写为"符合预期" / 将环境 blocker 写成 PASS。

### 5.4 医疗系统 fail-closed
以下信息缺失时默认拒绝继续:organization_id / tenant_id / 操作用户身份 / 患者上下文 / 数据来源系统 / 请求用途 / 审计 trace ID / 密钥来源 / 数据驻留区域 / 必要授权信息。**禁止自动填写生产环境默认值**。

### 5.5 不引入新 verdict
A1D 全程严格遵守 §三 的 11 个禁用 verdict。任何新裁决表述必须在 §一 三选一范围内,或在 subgate 内使用 `*_FILED` / `*_VERIFIED` / `BLOCKED_BY_*` 三类之一。

### 5.6 连续执行
Charter §20 pattern — 在授权范围内连续推进,不要在每个子门之间等待人工确认,除非遇到真实外部硬 blocker。

---

## §六 Git 与执行纪律 (PDF §十五)

### 6.1 禁用操作 (zero tolerance)

| 类 | 禁用项 |
|----|--------|
| 远端 | `git push` / `gh pr create` / deploy 到真实医院 |
| 历史 | amend A1C 历史提交 / rebase / squash / 删除任何 annotated tag |
| 提交 | `git add -A` / `git add .` / `git commit -a` / 删除失败测试 / 用跳过代替修复 |
| 替代 | 用 mock 代替真实 KMS 抽象或 DeepSeek client / 提交真实密钥到仓库 |
| 数据 | 修改任何 A1C final artifact (`reports/phase-a1c/A1C.9/*`, `A1C_OPEN_BLOCKERS.csv` 等) — 这些是冻结的真相 |

### 6.2 强制操作

- 每个子门独立提交 (推荐序列 A1D.0..A1D.6)
- 每次提交使用**明确文件列表** (禁用 `add -A` / `add .` / `commit -a`)
- 提交前 `git diff --check`
- 提交信息记录:测试命令 + 结果 + 当前 blocker + (不提前发出最终裁决)
- 中间子门 verdict 必须用 `*_FILED` / `*_VERIFIED` / `BLOCKED_BY_*` 三类之一
- 任何 source code change 必须先有对应失败测试 (TDD pattern for A1D.2/A1D.3/A1D.4)

### 6.3 允许操作

- 在 `phase-a1a/emergency-containment` 上**新增** A1D.* commits
- 新建 annotated tag (`audit/phase-a1d-*`) 标记关键基线 (local-only)
- 在 worktree 内编辑/新增 backend / frontend / docs / reports 文件
- 引用 A1C final artifacts (read-only,不修改)

---

## §七 A1D.0 范围 (本子门)

### 必须完成
1. 记录 repository / worktree / branch / HEAD / parent SHA / dirty state / remote state / runtime versions / OS
2. 核查 A1C.9 终态:
   - A1C.9 commit 是否真实落盘 → `209f25a` (truth)
   - RELEASE_ROADMAP.md commit 是否真实落盘 → `0a7bb11` (truth)
   - `A1C_FINAL_VERDICT.md` / `A1C_FINAL_STATE.json` / `A1C_FINAL_COMMIT_MANIFEST.json` 三者一致性
   - `A1C_OPEN_BLOCKERS.csv` 12 项是否完整
   - 本地 annotated tag 是否真实指向 A1C.9 → 检查 `audit/phase-a1c-*` tags
3. 划分 A1C 12 blockers 为 Engineering 类 (9 项,A1D 范围) 与 Pilot-env 类 (9 项,A1D 范围外)
4. 创建 `A1D_OPEN_BLOCKERS.csv` (初始 = 9 Engineering 类,从 A1C OPEN_BLOCKERS.csv 衍生)
5. 创建 `A1D_BASELINE_STATE.json` (含 5-tuple + 子门 verdict 占位)
6. 生成 `A1D_ENTRY_SHA256SUMS.detached.txt` (A1D.0 内的新 manifest,**不含自身**,避免自指问题,per A1C IC-5 教训)

### 不允许
- 修改 A1C 任何 final artifact
- 在 A1D.0 内做任何 source code change (A1D.0 是纯审计子门)
- 提前发出最终裁决

### 验收
- A1C.9 与 RELEASE_ROADMAP v1.0 一致性确认 → 一致 / 列入不一致清单 (类似 A1C §八)
- A1D OPEN_BLOCKERS.csv 9 项与 A1C OPEN_BLOCKERS.csv 中 Engineering 类一一对应
- A1D BASELINE_STATE.json 5-tuple 与 A1C 继承一致 (不得变更)
- entry SHA manifest 不自指

---

## §八 A1D 出口条件 (Aggregate)

A1D 全 phase 出口 (A1D.6) 必须同时满足:

1. **9 个 Engineering 类 blockers 全部 closed in `A1D_OPEN_BLOCKERS.csv`** (status = CLOSED, 含 closure commit + test reference)
2. **回归全 PASS**: A1C.9 baseline 测试数 + A1D 新增测试全 PASS;不允许新增 skip
3. **CI 信号 clean**: 默认 CI 无未解释 failed/error (HG-02 升级到 PASS)
4. **ESLint PASS** (HG-03 升级到 PASS)
5. **8 个禁用 verdict + 3 个 A1D-specific 禁用 verdict 全部 honoured** (§三 11 项)
6. **12 个禁用 git 操作全部 honoured** (§6.1)
7. **5-tuple 不可变更** (§二 表)
8. **A1C final artifacts 未被修改** (SHA-256 守护)

满足全部 → `PASS_A1D_LAYER1_ENGINEERING_DEBT_CLEARED_ALL_9_ENG_BLOCKERS_CLOSED`
任一未满足 → `PARTIAL_A1D_SOME_ENG_BLOCKERS_REMAIN` 或 `FAIL_A1D_ENGINEERING_REGRESSION`

---

## §九 A1D 不处理的范围 (显式排除)

以下属于其他 phase / 团队责任,A1D 不处理:

| 项目 | 责任方 | 何时处理 |
|------|--------|----------|
| A1C 9 个 Pilot-env blockers (B-001/004/005/006/009/013/014/016/017/019) | Pilot ops | Pilot 云账号 provisioning 后 |
| R6 部署路径战略决策 (cloud-only vs on-prem) | Product + Eng leadership | A1D 与 Pilot provisioning 之间 |
| R4 等保2.0 三级认证启动 | Compliance officer | 立即启动,与 A1D 并行 |
| GATE14 16 P0 中除 A1C 已 closed 6 个外的 10 个 | Layer 2 (TBD phase) | A1D 完成后 |
| Corti 战略定位重写 (R1 / G3-001 / G12-002) | Product + Eng | Layer 2 启动前 |
| 等保 / 法务 / 支付 / DRG / DIP / 13 metadata-only agents | Layer 2 / Layer 3 phase | 后续 phase |

---

## §十 预期 BLOCKED 项目 (Charter §20 pattern, 本机环境)

| 项目 | 子门 | 原因 | 缓解 |
|------|------|------|------|
| LLM fallback provider 真实接入 | A1D.4 | 需要 fallback provider API key (Azure OpenAI / Qwen / Moonshot 任一) | 实现 provider abstraction + 本地 mock 验证;真实 fallback 调用留给 Pilot env |
| KMS 真实 rotation 端到端 | A1D.4 | 无云 KMS 凭证 | 实现 version token 抽象 + 单元测试;真实 KMS 留给 Pilot env |

PDF §十六 认可:**"如遇到真实外部环境缺失,不得伪造结果,先完成可在本地完成的实现、模拟器和证据,将外部依赖明确列入 blocker,最终根据硬门槛诚实输出 PARTIAL 或 FAIL。"**

---

## §十一 A1D 子门 verdict 进展

| 子门 | 状态 | Commit | Verdict |
|------|------|--------|---------|
| A1D.0 | in_progress | (this commit) | (待发) |
| A1D.1 | pending | — | — |
| A1D.2 | pending | — | — |
| A1D.3 | pending | — | — |
| A1D.4 | pending | — | — |
| A1D.5 | pending | — | — |
| A1D.6 | pending | — | — |

---

## §十二 Charter 冻结声明

本 Charter 在 A1D.0 内冻结。后续子门如需扩展范围、变更裁决规则或解除 §三 红线,**必须**新建 Charter 修订 commit 并标注版本号 (e.g., v1.1)。在 Charter 修订落盘前,所有子门继续按 v1.0 执行。

---

## §十三 引用

- **Master tracker**: `docs/governance/RELEASE_ROADMAP.md` v1.0
- **A1C charter**: `docs/phase-a1c/A1C_CHARTER.md` v1.0
- **A1C final verdict**: `reports/phase-a1c/A1C.9/A1C_FINAL_VERDICT.md`
- **A1C open blockers (frozen truth)**: `reports/phase-a1c/A1C.9/A1C_OPEN_BLOCKERS.csv`
- **GATE14 issue grading**: `reports/comprehensive-audit/GATE14_ISSUE_GRADING_ROADMAP_FINAL_VERDICT.md`
- **Charter index**: `docs/governance/CHARTER_INDEX.md`

---

**A1D 开始执行。**
