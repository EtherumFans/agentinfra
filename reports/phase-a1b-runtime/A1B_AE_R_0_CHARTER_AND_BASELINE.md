# Phase A1B-AE-R — Agent Runtime Verification & Human-Workflow Closure Charter (A1B-AE-R.0)

**Date**: 2026-07-22
**Phase**: A1B-AE-R (Agent Runtime Closure + Preset Materialization + Public Expert Live Integration + MCP Wiring + Headed-Browser Verification)
**Charter version**: v1.0 (2026-07-22)
**Worktree**: `E:/Corti4C-agent-expert-runtime`
**Branch (new, local-only)**: `phase-a1b/agent-expert-runtime-verification`
**Branch source**: verified HEAD `85a5c9abc40fd85648e45343de6d3e1924cdd5a2` on `phase-a1b/agent-expert-clean-room` (A1B-AE.11 phase terminal)
**Predecessor immutable anchors** (all preserved, NOT rewritten):
- `audit/phase-a0.1r-baseline` (annotated tag `3cd1bec`) on `64590fa`
- `audit/phase-a1a-gate4-pre4r-b3ea064` (annotated tag `fa0d461`) on `b3ea064`
- `audit/phase-a1a-gate4r-closure-24967da` (annotated tag `43c2395`) on `24967da`
- `3d50b11` — Phase A1A Gate 4R-I.11 final verdict
- `85a5c9a` — Phase A1B-AE.11 phase terminal reconciliation (immediate parent)

---

## §1. 为什么需要这个 Charter

Phase A1B-AE 在 `85a5c9a` 提交了 **能力表面**(capability surface):
- 9/9 Corti 公开 §3.2 Expert keys 已归档(其中 6 个是 reference stub)
- 5/5 iCoDer Preset Agent Cards 已归档(其中只有 1 个有真实 Pack 支撑)
- `/api/v1/experts`、`/api/v1/agents`、`/api/v1/presets`、`/external-gate/evaluate` REST surface 已落地
- 10 个 user journey 在 `API_FALLBACK_PER_§4.3` 模式下完成

A1B-AE.11 terminal verdict `PARTIAL_A1B_AE_..._FILED` 明确记录了**未关闭的 tech debt**:
- Task endpoint 仍是 501 stub(`routes_task_stub.py`)
- ThreadAuthRegistry 是进程内 dict(文件本身注释建议迁移到 DB/Redis)
- 4/5 Preset Agent 的 `delegates_to_pack=null`
- 3 个 dual-named legacy orphan Pack 目录(underscore + dash 共存)未删除
- PubMed / ClinicalTrials / MCP server 未接入
- Calculator 只有 BMI + Cockcroft-Gault
- Interviewing 仅 schema-driven,无可恢复状态机
- **前端没有 UI 消费 A1B-AE.3..9 的 endpoint** — Journey 7 在 response body 明确返回 `"Agent not found for key='code_validation'"` 的情况下被错误标记为 `API_WORKFLOW_VERIFIED`

A1B-AE-R 关闭这些 gap。每个能力必须经过:
```
人工观察 → 合同 → 实现 → 人工运行 → 负向验证 → 证据归档
```

`HUMAN_OPERATION_SIMULATION_REQUIRED` 模式下,**有头浏览器证据是最终裁决依据** — `HTTP 200 = 完成` 的推断在本 phase 内被明确禁止。

本 Charter **不关闭 Gate 4**、**不主张 Corti parity**、**不主张生产就绪**、**不修改任何 A1A/A1B-AE 已标记的 commit / branch / tag**。

## §2. 授权范围(in scope)

本 Charter 授权且仅授权:

A. 在新本地-only worktree `E:/Corti4C-agent-expert-runtime` 上,从已验证 HEAD `85a5c9a` 创建新本地-only branch `phase-a1b/agent-expert-runtime-verification`(worktree 已在 R.0 创建;见 §5)。

B. 在 iCoDer 后端完成 **Agent Runtime 纵向闭环**(R.1):
   - `Message → Task → Context → Expert → Artifact` 完整链路
   - Task 状态机:`submitted / working / completed / failed / canceled`
   - ThreadAuthRegistry 从进程内 dict 迁移到 DB-derived state(查询 `context_messages` 行数)
   - Context 真实 scrub(物理删除,非 `status=EXPIRED` 软标记)
   - Artifact 存储 + 跨租户隔离

C. 在 iCoDer 后端**实体化 Preset Agent**(R.2):
   - 4 个 stub preset 接上真实 Pack(cdi / drg-dip / claim-check)
   - 允许新建薄壳 Pack(包装现有 service,禁止临床逻辑重写)
   - 删除 3 个 legacy orphan Pack 目录(underscore form)并迁移 call site
   - 修复 Clone Preset 404(Journey 7 必须返回 200 + Agent 行)

D. 接入**公共 Expert + MCP**(R.3):
   - PubMed E-utilities(`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`)真实调用 + 合成查询
   - ClinicalTrials.gov v2 API(`https://clinicaltrials.gov/api/v2/`)真实调用
   - MCP server `tools/list` + `tools/call` JSON-RPC 路由
   - SSRF allowlist:拒绝 RFC1918 / loopback / link-local / cloud metadata endpoint
   - Deny 路径 = 0 network egress(packet counter 测试)
   - DrugBank / POSOS 保持 `LICENCE_REQUIRED`,无授权不联网
   - Web Search 默认 off,显式 `feature_flag=web_search_enabled` 才开启

E. 完成**本地 Expert**(R.4):
   - Calculator 扩充目录(BMI、Cockcroft-Gault、CHADS₂-VASc、MELD-Na、eGFR CKD-EPI 2021、Wells DVT — 全部确定性计算,不调 LLM)
   - Memory Expert 接到真实 Context persistence(sentence-transformers 语义搜索已在 `memory_expert.py:8-22`,只需接通 Context 表)
   - Interviewing 添加可恢复状态机(state 存 `contexts.metadata_json` 或独立表)

F. 在 iCoDer 前端**落地 UI 并完成 10 个有头浏览器 journey**(R.5):
   - 新建 `ExpertsPage.tsx`(消费 `/api/v1/experts`)
   - 扩展 `NewAgentPage.tsx`(Corti create-then-customize,调 `/api/v1/agents/quick`)
   - 扩展 `AgentDetailPage.tsx`(展示 Task / Context / Artifact)
   - 10 个 journey 通过 Playwright MCP 有头浏览器执行,每个产生 screenshot + sanitized HAR + inspection.md + manifest entry

G. **回归验证**(R.6):运行 164 A1B-AE 测试 + Gate 4R 回归 + 后端全套 + 前端 build/test + Playwright;要求 `NEW_FAIL=0 NEW_ERROR=0`。

H. 生成 R.0..R.6 的 charter、report、evidence、INDEX 文件。

I. 在 phase 结束时创建本地-only annotated tag(不 push):
   - `audit/phase-a1b-agent-expert-runtime-verification-baseline-85a5c9a` 在 `85a5c9a`
   - `audit/phase-a1b-agent-expert-runtime-verification-final-<SHA>` 在 final commit(仅当 §10 所有 acceptance 条件满足)

## §3. 范围外(NOT authorised)

本 Charter **不授权**:

- Merge 到 `master`;修改 `origin/master`;push;创建 PR;deploy。
- 使用真实患者数据;用生产凭证调用真实 Corti API;用真实 PHI 调用真实 LLM Provider。
- 重写、amend、rebase 或 squash 任何 ancestor commit(包括 `3d50b11`、`85a5c9a`、任何 A0.1R / A1A-tagged object、任何 A1B-AE commit)。
- 删除审计分支或审计 tag。
- 修改 Medical Coding / CDI / DRG-DIP **临床** prompt(需要单独的临床质量 Charter)。
- 弱化 JWT、tenant boundary、encryption、redaction、egress、retention 或 fail-closed control 来通过测试。
- 营销式 Corti parity 主张或 "Corti-fully-replicated" verdict。
- 复制 Corti 专有源码、内部 prompt、UI 资产、logo、商标或任何非公开材料到 iCoDer 仓库。
- 在未独立重新 author 的情况下直接使用 Corti 文档示例 prompt 作为生产 prompt(每个新 prompt 必须按 A1B-AE Charter Amendment 1 §7 声明 `clean_room_authored: true`)。
- 在未取得 licence 的情况下 web scrape DrugBank / POSOS 或任何付费内容。
- 把患者可识别数据发给 PubMed / ClinicalTrials.gov / 任何外部 Expert。
- 通过直接 DB 写入伪造用户操作结果;绕过公开 API surface 模拟用户动作。
- 使用 `git add -A`、`git add .` 或 `git commit -a`;每个 commit 必须用显式文件列表。
- 在 R.3 测试中默认 real-call 每次(必须 VCR:首次实打 + 后续 replay)。
- 把 Journey 7 的 404 直接改成 200 而不补真实 Agent 行(clone-preset 必须真的创建 Agent)。

## §4. 快照保留

| Object | Role | Mutability after this Charter |
|---|---|---|
| `audit/phase-a0.1r-baseline` (tag `3cd1bec`) | A0.1R immutable anchor | IMMUTABLE |
| `audit/phase-a0.1r-freeze` (branch `64590fa`) | A0.1R freeze branch | NOT DELETED |
| `audit/phase-a1a-gate4-pre4r-b3ea064` (tag `fa0d461`) | Pre-4R Gate 4 closure snapshot | IMMUTABLE |
| `audit/phase-a1a-gate4r-closure-24967da` (tag `43c2395`) | 4R P0-5 closure snapshot | IMMUTABLE |
| `phase-a1a/emergency-containment` (branch `3d50b11`) | A1A main work | NOT MODIFIED by A1B-AE-R |
| `phase-a1b/agent-expert-clean-room` (branch `85a5c9a`) | A1B-AE carrier | NOT MODIFIED by A1B-AE-R |
| `phase-a1b/agent-expert-runtime-verification` (branch, new) | A1B-AE-R carrier | APPENDED only via new commits |
| `E:/Corti4C-agent-expert-runtime` (worktree, new) | A1B-AE-R workspace | APPENDED only via new commits |
| `E:/Corti4C-agent-expert` (worktree, existing) | A1B-AE workspace | NOT MODIFIED by A1B-AE-R |
| `E:/Corti4C` (worktree, existing) | A1A workspace | NOT MODIFIED by A1B-AE-R |

新 annotated tags(本地-only,不 push),phase 结束时创建:
- `audit/phase-a1b-agent-expert-runtime-verification-baseline-85a5c9a` on `85a5c9a`
- `audit/phase-a1b-agent-expert-runtime-verification-final-<SHA>` on final commit(仅当 §10 所有 acceptance 条件满足)

## §5. Worktree 和 branch 操作(R.0 已执行)

```
git worktree add E:/Corti4C-agent-expert-runtime \
    -b phase-a1b/agent-expert-runtime-verification \
    85a5c9abc40fd85648e45343de6d3e1924cdd5a2
```

创建后验证(本 Charter §6 baseline):
```
worktree path : E:/Corti4C-agent-expert-runtime
HEAD          : 85a5c9abc40fd85648e45343de6d3e1924cdd5a2
branch        : phase-a1b/agent-expert-runtime-verification
predecessor   : 85a5c9a (A1B-AE.11 phase terminal, immediate parent)
```

此前该路径不存在 worktree。此前不存在 `phase-a1b/agent-expert-runtime-verification` branch 或 tag。未执行 reset、stash 或 force 操作。

## §6. 基线状态(本 commit 冻结)

### §6.1 继承的 5-tuple 状态

```json
{
  "GATE4_8_NO_NEW_REGRESSION_CLAIM": "CONTRADICTED",
  "GATE4_9_FINAL_PASS":              "SUPERSEDED",
  "GATE4_ACCEPTANCE_STATUS":         "REOPENED",
  "CORTI_PARITY_VERDICT":            "NOT_DEMONSTRATED",
  "PRODUCTION_READINESS":            "NOT_VERIFIED"
}
```

这些 flag 继承自 Phase A1B-AE.11(`85a5c9a`),**不被本 Charter 修改**。Phase 结束时会重新核验;任何变化需要单独的 Charter amendment。

完整 JSON:[A1B_AE_R_0_BASELINE_STATE_5_TUPLE.json](A1B_AE_R_0_BASELINE_STATE_5_TUPLE.json)

### §6.2 环境清单(节选;完整 JSON 在附件)

- host: Windows 10 Home China 10.0.19045 / bash (Git for Windows) / Python 3.12.3 / Node v22.20.0
- git head: `85a5c9a` (subject: A1B-AE.11 phase terminal)
- alembic head: `023` (Migration 022 Expert Registry + 023 Agent canonical_key backfill)
- 既有测试基线: **258 passed / 1 failed / 2 skipped in 76.21s**
  - 唯一失败:`test_L11_migration_head_is_020_on_fresh_db`(stale assertion, expects 021 actual 023)
  - 此失败是 A1B-AE 时期遗留,非 A1B-AE-R 引入

完整 JSON:[A1B_AE_R_0_ENVIRONMENT_MANIFEST.json](A1B_AE_R_0_ENVIRONMENT_MANIFEST.json)

### §6.3 Pre-change SHA-256 基线

[A1B_AE_R_0_PRE_CHANGE_SHA256SUMS.txt](A1B_AE_R_0_PRE_CHANGE_SHA256SUMS.txt) 记录 R.1..R.5 即将修改的 15 个文件的 SHA-256(R.1 4 个、R.2 3 个、R.3 2 个、R.4 2 个、R.0 evidence correction 4 个)。

### §6.4 既有测试基线

[A1B_AE_R_0_BASELINE_TEST_RESULTS.txt](A1B_AE_R_0_BASELINE_TEST_RESULTS.txt) 记录:
- 258 passed / 1 failed (pre-existing) / 2 skipped / 76.21s
- pre-existing failure 分类:stale-test-assertion(A1A Gate 3R.8 territory,R 范围内不修)
- R.6 final regression 的 `NEW_FAIL=0 NEW_ERROR=0` 相对这个 baseline 计算

## §7. 子门序列(R.0..R.6)

| # | Sub-gate | Commits | 关键交付 |
|---|---|---|---|
| R.0 | Charter + baseline + Journey 7 evidence correction | 1(本 commit) | worktree / charter / 5-tuple / SHA-256 / Expert key mapping / Journey 7 降级 / INDEX |
| R.1 | Agent Runtime closure(最高优先级) | 2-3 | 替换 `routes_task_stub.py` 501;ThreadAuthRegistry DB-derived;ContextLifecycle `destroy_now()`;cross-tenant 404 负向测试 |
| R.2 | Preset Agent 实体化 | 1-2 | 建 cdi/drg-dip/claim-check Pack(薄壳);4 preset `delegates_to_pack` 接通;删 3 legacy orphan;Clone Preset 200 |
| R.3 | 公共 Expert + MCP | 2 | PubMed/ClinicalTrials 真实 + VCR fixture;MCP tools/list+call + SSRF;deny=0 egress |
| R.4 | 本地 Expert 完成 | 1-2 | Calculator 扩目录(6 formulae);Memory 接 Context;Interviewing 可恢复状态机 |
| R.5 | 前端 + 10 浏览器 journey | 2-3 | ExpertsPage 新建 + NewAgentPage/AgentDetailPage 扩展;10 Playwright 有头 journey;screenshot+HAR+inspection+manifest |
| R.6 | 回归 + final verdict | 1 | 全套 pytest + npm build/test + Playwright;`NEW_FAIL=0`;终态 reconciliation 报告 |

预计总 commit:11-13。

## §8. 人机协作操作协议(继承 A1B-AE.0 §4)

执行模式:`CLAUDE_CODE_EXECUTION_MODE = HUMAN_OPERATION_SIMULATION_REQUIRED`

每个能力必须经过:
```
人工观察(Corti 公开文档 / iCoDer 现有 UI)
  → 合同(明确 REST surface + DB schema + 状态机)
  → 实现(代码 + migration + service + route)
  → 人工运行(真实 LLM / 真实 API / 真实 Pack)
  → 负向验证(404 / 401 / 403 / 422 / 状态机非法转移 / SSRF 拦截 / deny=0 egress)
  → 证据归档(screenshot + HAR + SHA-256 + DB secondary verification + inspection.md + manifest.json)
```

**禁止的证据替代**:
- headless crawler 截图
- 静态源码扫描单独作为"已实现"证据
- 直接 DB 写入伪造用户操作
- batch curl loop
- `HTTP 200` 作为唯一成功标准
- API fallback 替代浏览器 journey(A1B-AE.10 的 `API_FALLBACK_PER_§4.3` 逃逸条款在 A1B-AE-R 内**不适用** — R.5 必须真实浏览器证据)

## §9. Expert key mapping 概要

详见 [A1B_AE_R_0_EXPERT_KEY_MAPPING.md](A1B_AE_R_0_EXPERT_KEY_MAPPING.md)。核心映射:

| Corti §3.2 key | iCoDer canonical_key | Pack slug | Preset Agent | Corti alignment |
|---|---|---|---|---|
| memory | `memory` / `memory-expert` | (no Pack, service-only) | medical-coding / cdi / drg-dip / intake-interview / claim-check(auxiliary) | CORTI_REFERENCE → R.4 升级为 CORTI_ALIGNED |
| coding | `coding-expert` | `icoder/medical-coding-agent@2.0.0` | medical-coding(primary) / drg-dip / claim-check | CORTI_ALIGNED |
| medical-calculator | `medical-calculator` / `medical-calculator-expert` | (no Pack, service-only) | medical-coding / drg-dip(auxiliary) | CORTI_ADAPTED → R.4 扩目录 |
| drugbank | `drugbank-expert` | (no Pack, licence-gated stub) | (no preset) | CORTI_REFERENCE (licence-required) |
| posos | `posos-expert` | (no Pack, licence-gated stub) | (no preset) | CORTI_REFERENCE (licence-required) |
| pubmed | `pubmed-expert` | (no Pack, offline stub) | cdi / claim-check(auxiliary) | CORTI_REFERENCE → R.3 升级为 CORTI_ALIGNED |
| clinical-trials | `clinical-trials-expert` | (no Pack, offline stub) | cdi / claim-check(auxiliary) | CORTI_REFERENCE → R.3 升级为 CORTI_ALIGNED |
| web-search | `web-search-expert` | (no Pack, policy-gated stub) | (no preset) | CORTI_REFERENCE (default-off) |
| interviewing | `interviewing-expert` | (no Pack, schema-driven) | intake-interview(primary) / cdi(auxiliary) | CORTI_ALIGNED → R.4 加状态机 |

## §10. 接受条件

Phase terminal verdict 为 `PASS_A1B_AE_R_..._VERIFIED` 当且仅当:

1. R.0..R.6 全部 sub-gate 已 commit,branch `phase-a1b/agent-expert-runtime-verification` 为 phase terminal HEAD。
2. 10 个有头浏览器 journey 全部产出 screenshot + sanitized HAR + inspection.md + manifest.json,verdict = `HUMAN_WORKFLOW_VERIFIED`(或对负向 journey,`NEGATIVE_VERDICT_CORRECTED`)。**任何 journey 不得以 `API_FALLBACK_PER_§4.3` 收尾**。
3. R.6 回归验证 `NEW_FAIL=0 NEW_ERROR=0`(相对 R.0 baseline 的 258 passed / 1 pre-existing failure / 2 skipped)。Pre-existing failure(`test_L11_migration_head_is_020_on_fresh_db`)允许保留。
4. 5-tuple 状态在 R.6 终态无 mutation(全部保留 inherited value)。
5. 8 个 forbidden verdict 全部 absent。
6. 所有 commit 使用显式 `git add <file>` 列表;未使用 `--amend` / `rebase` / `reset --hard` / `add -A` / `commit -a` / `push`。
7. 未修改 master / origin/master / audit branch / audit tag。
8. 未对临床 prompt 做任何修改(Medical Coding / CDI / DRG-DIP 临床逻辑)。
9. Journey 7(clone-preset)在 R.5 必须返回 200 + 真实 Agent 行(DB 二级验证)。
10. 公共 Expert(PubMed/ClinicalTrials)deny 路径 = 0 network egress(packet counter 测试)。
11. SSRF 拦截:`http://169.254.169.254/` 等 metadata endpoint 返回 400 BLOCKED。
12. DrugBank / POSOS 保持 `LICENCE_REQUIRED`;Web Search 保持 default-off。

任一条件未满足,verdict 退化为 `PARTIAL_A1B_AE_R_RUNTIME_AND_HUMAN_WORKFLOW_RECONCILIATION_FILED`。

## §11. 禁止的 verdict(8 — 与 A1B-AE 完全一致)

```
PRODUCTION_READY
FULLY_VERIFIED
PHI_BOUNDED
CORTI_PARITY_VERIFIED
PASS_A1A_GATE4_FINAL
READY_FOR_HOSPITAL_DEPLOYMENT
CLINICAL_GRADE_VERIFIED
CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED
```

## §12. 禁止的操作(全 phase 适用)

```
NO push                          (any branch)
NO merge --no-ff to master
NO commit --amend                (any ancestor, including 85a5c9a)
NO rebase                        (any branch)
NO reset --hard                  (any branch)
NO git add -A / git add . / git commit -a
NO force-push                    (any branch, any tag)
NO modify master / origin/master
NO delete audit branches or audit tags
NO weaken JWT / tenant boundary / encryption / redaction / egress / retention
NO real patient data
NO call real Corti API with production credentials
NO call real LLM Provider with real PHI
NO clinical prompt changes       (Medical Coding / CDI / DRG-DIP)
NO web scrape DrugBank / POSOS without licence
NO direct DB writes to fake user operations
NO API_FALLBACK_PER_§4.3 escape hatch in R.5 journeys
```

每个 commit 必须使用显式文件列表。每个 commit message 必须显式引用 sub-gate 名称和允许的 verdict token。

---

**Charter end**
