# A1C.0 — Entry Audit (入场审计)

**Audit date**: 2026-07-25
**Auditor**: SONG Luhua (git config)
**A1C branch baseline (pre-A1C.0)**: `phase-a1a/emergency-containment` @ `3d50b11`
**Reference RV terminal**: `phase-a1b/agent-expert-terminal-reverification` @ `0f107d0`

---

## §1 仓库与 worktree 拓扑

### 1.1 仓库根
- **Repository root**: `E:/Corti4C`
- **Remote (origin)**: `https://github.com/EtherumFans/agentinfra.git` (fetch + push; A1C 全程 **不** push)
- **Bare check (is repo?)**: yes (`git rev-parse --show-toplevel` returned `E:/Corti4C`)

### 1.2 Worktree 清单 (4 个)

| # | Worktree 路径 | 分支 | HEAD (short) | HEAD (full) | 用途 |
|---|---------------|------|--------------|-------------|------|
| 1 | `E:/Corti4C` | `phase-a1a/emergency-containment` | `3d50b11` | `3d50b116597c992ac92de189fad70def11349dcb` | **A1C 主 worktree** |
| 2 | `E:/Corti4C-agent-expert-reverification` | `phase-a1b/agent-expert-terminal-reverification` | `0f107d0` | `0f107d0694867a84cced54e8a2e7948dc04d8bdb` | A1B-AE-RV 终态 (referenced) |
| 3 | `E:/Corti4C-agent-expert-runtime` | `phase-a1b/agent-expert-runtime-verification` | `8546184` | `85461848b4067100df7df40367cb49753559506f` | A1B-AE-R 终态 (frozen) |
| 4 | `E:/Corti4C-worktrees/a1b-ae-baseline-85a5c9a` | (detached) | `85a5c9a` | `85a5c9abc40fd85648e45343de6d3e1924cdd5a2` | A1B-AE baseline (frozen) |

### 1.3 分支清单 (local)

- `audit/phase-a0.1r-freeze` (Phase A0.1R secure freeze)
- `master` (default main branch — **A1C 全程不**直接提交)
- `phase-a1a/emergency-containment` (**A1C 主分支**)
- `phase-a1a/gate4r-regression-reconciliation` (4R sub-phase,merged at ca36c51)
- `phase-a1b/agent-expert-clean-room` (A1B-AE clean room baseline)
- `phase-a1b/agent-expert-runtime-verification` (A1B-AE-R,predecessor of RV)
- `phase-a1b/agent-expert-terminal-reverification` (A1B-AE-RV terminal)

### 1.4 标签清单 (annotated)

- `audit/phase-a1b-ae-rv-baseline-8546184` → `0f107d0` (RV terminal, annotated)
- `audit/phase-a1b-agent-expert-clean-room-final-85a5c9a` → `85a5c9a` (A1B-AE baseline)
- (A1A Gate 4R-I baseline tags — 见 `reports/phase-a1a/gate4r-integration/`)

---

## §2 当前 HEAD 与继承链

### 2.1 A1C 起点 HEAD (pre-A1C.0)

| 字段 | 值 |
|------|-----|
| `HEAD` (full) | `3d50b116597c992ac92de189fad70def11349dcb` |
| `HEAD` (short) | `3d50b11` |
| `HEAD^` (parent full) | `a0b56da23cbc09fa2b763bd1ca023a8fe44b577a` |
| Subject | `audit/phase-a1a: Gate 4R-I.11 — final verdict + closure notice` |
| Branch ref | `refs/heads/phase-a1a/emergency-containment` |

### 2.2 前 5 个近期 commit (上下文)

```
3d50b11 audit/phase-a1a: Gate 4R-I.11 — final verdict + closure notice
a0b56da audit/phase-a1a: Gate 4R-I.10 — development backlog + roadmap
a2a1136 audit/phase-a1a: Gate 4R-I.9 — release tier verdicts
4fda130 audit/phase-a1a: Gate 4R-I.8 — security/compliance release re-audit
f614f01 audit/phase-a1a: Gate 4R-I.4 — engineering debt liquidation
```

### 2.3 与 RV 分支拓扑关系

```
3d50b11 (current HEAD) ─── ancestor of ─── 0f107d0 (RV HEAD)
                                               │
                                               └── RV.7 final verdict
```

- `git merge-base --is-ancestor 3d50b11 0f107d0` → **YES**
- `git rev-list --left-right --count 3d50b11...0f107d0` → `0  34` (current 0 commits ahead, 34 commits behind RV)
- 含义: 从 current HEAD 到 RV HEAD 是线性可 fast-forward / `--no-ff` merge 的关系,**无冲突风险**

---

## §3 Dirty state (A1C.0 入场时)

| 项 | 数值 |
|----|------|
| 总 untracked + modified 文件 | **69** |
| 已 stage 文件 | 0 |
| 已修改未 stage 文件 | 0 |
| Untracked 文件 | 69 (全部为既有 audit 工作产物 — XML/JSON/MD/PNG/DB 等,非 A1C 引入) |

**A1C.0 入场结论**: dirty state 全部为既有 audit 工作 (Gate 4/4R/4R-I/comprehensive-audit) 的未跟踪产物。A1C.0 **不**清理这些产物,以维持"不重写历史"原则。A1C 自身产物在 `reports/phase-a1c/` 与 `docs/phase-a1c/` 下集中管理,使用明确文件列表 commit。

---

## §4 运行时与操作系统

### 4.1 OS

| 字段 | 值 |
|------|-----|
| Platform | win32 |
| OS Version | Windows 10 Home China 10.0.19045.6466 (build 19045) |
| Shell | bash (Git Bash on Windows) |

### 4.2 运行时版本

| 工具 | 版本 | 状态 |
|------|------|------|
| Python | `3.12.3` | OK (backend runtime) |
| Node | `v22.20.0` | OK (frontend runtime) |
| npm | `10.9.3` | OK |
| Docker | — | **NOT INSTALLED** (A1C.2 / A1C.7 阻塞预警) |
| Docker Compose | — | **NOT INSTALLED** (同上) |
| Podman | — | NOT INSTALLED |
| psql (PostgreSQL client) | — | **NOT INSTALLED** (A1C.2 阻塞预警) |
| chromedriver | — | NOT INSTALLED (Playwright 自带 chromium,A1C.8 不影响) |
| pdftoppm (Poppler) | — | NOT INSTALLED (A1C 不需要) |
| Playwright | `@playwright/test ^1.59.1` (frontend) | OK |
| TypeScript | `5.6.2` | OK |
| Vitest | `2.1.1` | OK |
| ESLint | script 配置但 dep 未在 `package.json` `dependencies` 中明示 | **待 A1C.1 验证** (A1B-AE-RV BLOCKED_BY_MISSING_DEV_DEPENDENCY) |

### 4.3 关键环境变量 (A1C.0 入场时)

| 变量 | 值 | 影响 |
|------|-----|------|
| `ICODER_DEPLOYMENT_MODE` | (unset) | 默认 local-mode;A1C.6/A1C.7 测试 cloud-mode 时需 monkeypatch |
| `ICODER_ENVIRONMENT` | (unset) | 同上 |
| `ICODER_REGION` | (unset) | 同上 |
| `DATABASE_URL` | (unset) | 使用 SQLite default `data/icoder.db`;A1C.2 PG 测试需显式注入 |
| `LLM_API_KEY` | (unset) | **A1C.5 DeepSeek 真实调用阻塞** |

---

## §5 仓库结构概览

### 5.1 顶层目录

```
archive/           artifacts/    backend/             deploy/
docs/              examples/     fixtures/            frontend/
gate4r_diff/       golden_captures/  node_modules/    outputs/
packages/          phase7-external-consumer/  postman/  public/
reports/           screenshots/  scripts/             tests/
```

### 5.2 后端

- **Backend root**: `backend/`
- **App entry**: `backend/app/main.py`
- **API surface**: `backend/app/api/` (~190 endpoints per CLAUDE.md)
- **Alembic 版本** (current branch `phase-a1a/emergency-containment`): `001..021` (共 21 个,**无 022-026**,缺 RV.2 fail-closed migration)
- **DB**: SQLite default at `backend/data/icoder.db`

### 5.3 前端

- **Frontend root**: `frontend/`
- **Build**: Vite + React + TypeScript
- **Test**: Vitest (`npm run test`) + Playwright (`playwright.config.ts`)
- **Test 文件数**: 25 (vitest unit/contract)
- **Lint script**: `eslint . --ext ts,tsx` (定义在 `package.json`)

### 5.4 SDK

- **Package**: `@icoder/sdk@1.0.0-beta.2` (per A1B-AE-RV.6 build)
- **Build artefacts**: 29 dist files (per RV state)
- **Source**: `packages/icoder-sdk/`

### 5.5 测试体量

| 维度 | 数值 |
|------|------|
| Backend pytest test files | 275 (`find backend/tests -name "test_*.py"`) |
| Backend collected tests (at HEAD 3d50b11) | **3658/3668** (10 deselected) |
| Frontend test files | 25 |
| A1B-AE-RV reported baseline failures (at 0f107d0) | 88 (carryover from 8546184) |

---

## §6 能力清单 (每项按 §5.1 标记)

| 能力 | 子门关注 | 当前状态 (A1C.0 入场) |
|------|---------|---------------------|
| Repository 结构 | A1C.0 | `EXISTS_AND_VERIFIED` (本审计完成) |
| Worktree 拓扑 | A1C.0 | `EXISTS_AND_VERIFIED` (4 个 worktree 全部健康) |
| HEAD 与 parent SHA | A1C.0 | `EXISTS_AND_VERIFIED` (`3d50b11` / `a0b56da`) |
| Dirty state | A1C.0 | `EXISTS_AND_VERIFIED` (69 文件全部为既有 audit 产物) |
| Annotated tags | A1C.0 | `EXISTS_AND_VERIFIED` (`audit/phase-a1b-ae-rv-baseline-8546184` → `0f107d0`) |
| Python/Node/npm runtime | A1C.0 | `EXISTS_AND_VERIFIED` |
| Docker / psql / KMS / DeepSeek live env | A1C.2 / A1C.5 / A1C.7 | `BLOCKED_BY_ENVIRONMENT` (host 无凭证/二进制) |
| Alembic migrations 001..021 | A1C.2 | `EXISTS_AND_VERIFIED` (SQLite);`EXISTS_BUT_UNVERIFIED` (PG) |
| Alembic migrations 022..026 | A1C.2 | `PARTIALLY_IMPLEMENTED` (在 RV 分支,需 merge) |
| OpenAPI snapshot | A1C.6 | `EXISTS_BUT_UNVERIFIED` (当前 162 paths stale;RV.6 已 regen 208 paths 但在 RV 分支) |
| Frontend typecheck/build/vitest | A1C.1 | `EXISTS_BUT_UNVERIFIED` (待 A1C.1 重测) |
| Frontend ESLint | A1C.1 | `MISSING` (`BLOCKED_BY_MISSING_DEV_DEPENDENCY`) |
| Backend pytest 3658 collected | A1C.1 | `EXISTS_BUT_UNVERIFIED` (88 历史失败待分类) |
| Playwright headed browser | A1C.8 | `EXISTS_BUT_UNVERIFIED` (Playwright 1.59.1 安装) |
| DeepSeek backend client | A1C.5 | `EXISTS_BUT_UNVERIFIED` (LLM_API_KEY 未注入) |
| KMS / Secret loader | A1C.5 | `PARTIALLY_IMPLEMENTED` (无真实 KMS,backend 有 env loader) |
| HIS/EMR integration contract | A1C.3 | `MISSING` (无标准 contract;Context Create API 待 A1C.3 设计) |
| HIS/EMR Simulator | A1C.3 | `MISSING` |
| SSO/OIDC IdP integration | A1C.4 | `PARTIALLY_IMPLEMENTED` (本地 JWT auth;真实 IdP 未接入) |
| PHI redaction service | A1C.6 | `EXISTS_AND_VERIFIED` (Phase A1A Gate 4: `phi_encryption.py` + `audit_detail_redactor.py`) |
| Audit log completeness | A1C.6 | `EXISTS_AND_VERIFIED` (Phase A1A Gate 3R: system_audit allowlist + Migration 019/020) |
| Tenant isolation (organization_id fail-closed) | A1C.4 / A1C.6 | `EXISTS_AND_VERIFIED` (Phase A1A Gate 2/3 + RV.2/RV.3 tightening,在 RV 分支) |
| Observability (RunHistory/AuditLog/trace) | A1C.7 | `EXISTS_AND_VERIFIED` (基础);`PARTIALLY_IMPLEMENTED` (metrics/健康检查分层) |
| Deployment runbook | A1C.7 | `PARTIALLY_IMPLEMENTED` (`docs/cloud/CLOUD_DEPLOYMENT.md`,缺 hospital pilot 特化) |
| Failure injection harness | A1C.7 | `MISSING` |
| Rollback drill | A1C.7 | `MISSING` |

---

## §7 A1C.0 关键发现摘要

### 7.1 入场基线一致 (无 I/O 异常)

- HEAD/parent/dirty state 全部可读 ✓
- 4 worktree 全部健康 ✓
- Annotated tag 正确指向 RV.7 ✓
- 与 RV 分支拓扑为线性 (fast-forward-able,零冲突风险) ✓

### 7.2 A1B-AE-RV 封版元数据不一致 (5 类)

详见 `A1B_AE_RV_CLOSEOUT_CONSISTENCY_REPORT.md` 与 `A1C_CHARTER.md` §八。摘要:

- **IC-1** head_sha 在 3 份封版文件中滞后为 RV.6 (58e9ddd),实际为 RV.7 (0f107d0)
- **IC-2** `PENDING_RV7_COMMIT` 占位符未回填 (2 个文件)
- **IC-3** `PENDING_RV4_COMMIT` 占位符未回填 (1 个文件 — STATE.json;MANIFEST.json 已有真值)
- **IC-4** evidence_files_total 400 vs fingerprinted 403 (真相 = **403**)
- **IC-5** EVIDENCE_SHA256SUMS.txt 自指 (line 8 列出自身)

**处理** (per PDF §四): 不重写 RV 历史 → 在 A1C 内记录 + 生成 detached manifest。**不影响** RV.7 PASS verdict 的有效性 (PASS 基于 33 条 Charter §十三 验收条件,而非元数据 SHA 准确性)。

### 7.3 预期 BLOCKED 项目 (5 项)

详见 `A1C_CHARTER.md` §十。摘要: PostgreSQL / DeepSeek live / KMS / SSO IdP / real HIS-EMR → 全部 `BLOCKED_BY_ENVIRONMENT`,本机无法验证,将在相应子门内建模拟器+契约,真正 external 验证留给医院 pilot 环境。

### 7.4 已识别的工程债务 (跨子门)

- 88 历史基线失败 (A1C.1 处理)
- ESLint 未配置 (A1C.1 处理)
- DevDbSessionGuard 归因噪声 (A1C.1 处理)
- Stale OpenAPI 162 paths vs 208 paths (merge RV 即可解决)
- Stale Migration 021 vs 026 (merge RV 即可解决)
- 无 Context Create API (A1C.3 处理)
- 无 HIS/EMR Simulator (A1C.3 处理)
- 无真实 SSO (A1C.4 处理)
- 无真实 KMS (A1C.5 处理)
- 无 Failure injection harness (A1C.7 处理)

---

## §8 A1C.0 验收

| 验收项 (PDF §四 "输出") | 文件 | 状态 |
|------------------------|------|------|
| A1C_CHARTER.md | `docs/phase-a1c/A1C_CHARTER.md` | ✓ (本子门) |
| A1C_ENTRY_AUDIT.md | `docs/phase-a1c/A1C_ENTRY_AUDIT.md` | ✓ (本文件) |
| A1C_BASELINE_STATE.json | `reports/phase-a1c/A1C_BASELINE_STATE.json` | ✓ |
| A1C_ACCEPTANCE_MATRIX.csv | `reports/phase-a1c/A1C_ACCEPTANCE_MATRIX.csv` | ✓ |
| A1B_AE_RV_CLOSEOUT_CONSISTENCY_REPORT.md | `reports/phase-a1c/A1B_AE_RV_CLOSEOUT_CONSISTENCY_REPORT.md` | ✓ |
| A1C_ENTRY_SHA256SUMS.detached.txt | `reports/phase-a1c/A1C_ENTRY_SHA256SUMS.detached.txt` | ✓ (detached,不自指) |

| 验收项 (PDF §四 "验收") | 状态 |
|------------------------|------|
| 不存在未解释的 PENDING_* | ✓ (RV `PENDING_RV7_COMMIT` / `PENDING_RV4_COMMIT` 已在本审计中显式列出并转入 closeout report) |
| 所有最终 SHA 一致 | ✓ (本审计锁定 RV HEAD = `0f107d0`,tag = `audit/phase-a1b-ae-rv-baseline-8546184` → `0f107d0`) |
| 证据数量定义唯一 | ✓ (truth = **403**;A1C 全程使用 403 为唯一值) |
| SHA manifest 不自相矛盾 | ✓ (`A1C_ENTRY_SHA256SUMS.detached.txt` 不含自身) |
| PASS/PARTIAL/FAIL 规则提前冻结 | ✓ (`A1C_CHARTER.md` §一 + §九 已冻结) |

---

## §9 A1C.0 verdict

```
PASS_A1C_0_ENTRY_AUDIT_AND_PILOT_READINESS_CHARTER_FILED
```

依据:
- Charter v1.0 已冻结
- Entry audit 5 deliverable 全部生成
- A1B-AE-RV closeout 5 类不一致已识别并归档 (不重写历史)
- A1C entry SHA manifest (detached, 不自指) 已生成
- 21 项硬门槛已列入 ACCEPTANCE_MATRIX,无任何门槛被默认通过
- 预期 BLOCKED 项目 (5 项环境依赖) 已诚实列入 OPEN_BLOCKERS (在 BASELINE_STATE.json)

后续: A1C.0 close 后,以独立 commit `--no-ff merge phase-a1b/agent-expert-terminal-reverification` 整合 RV 工作 (Gate 4R-I.1 ca36c51 先例),作为 A1C.1+ 的基线。
