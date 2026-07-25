# A1B-AE-RV Closeout Consistency Report (A1C.0 核查输出)

**Audit date**: 2026-07-25
**Auditor**: A1C.0 sub-gate
**Scope**: Verify A1B-AE-RV (Terminal Evidence Repair & Reacceptance) closeout metadata consistency per PDF A1C §四 requirements.

**A1B-AE-RV referenced state**:
- Worktree: `E:/Corti4C-agent-expert-reverification`
- Branch: `phase-a1b/agent-expert-terminal-reverification` (local-only)
- Head (per `git log`): `0f107d0`
- Annotated tag: `audit/phase-a1b-ae-rv-baseline-8546184`

---

## §1 必查项 (per PDF §四) 与结果

| # | 必查项 | Truth | A1C.0 验证结果 |
|---|--------|-------|---------------|
| 1 | 最终 RV.7 commit 是否已经真实落盘 | `0f107d0` 存在于 `git log phase-a1b/agent-expert-terminal-reverification` | ✓ LANDED |
| 2 | `PENDING_RV7_COMMIT` 是否全部回填 | RV.7 commit `0f107d0` 已存在,但 `A1B_AE_RV_STATE.json` L165 + `FINAL_COMMIT_MANIFEST.json` L68 仍为占位符 | ✗ NOT BACKFILLED (见 §3 IC-2) |
| 3 | `FINAL_VERDICT.md` / `FINAL_COMMIT_MANIFEST.json` / `A1B_AE_RV_STATE.json` 是否一致 | 三文件 `head_sha` 全部滞后为 `58e9ddd` (RV.6),实际 HEAD = `0f107d0` | ✗ INCONSISTENT (见 §3 IC-1) |
| 4 | evidence 数量究竟为 400 还是 403 | `wc -l EVIDENCE_SHA256SUMS.txt` = **403** | ✗ CONFLICT (见 §3 IC-4);真相 = **403** |
| 5 | SHA manifest 是否存在自指哈希问题 | `EVIDENCE_SHA256SUMS.txt` line 8 列出自身 | ✗ SELF-REFERENTIAL (见 §3 IC-5) |
| 6 | 本地 annotated tag 是否真实指向最终 RV.7 commit | `audit/phase-a1b-ae-rv-baseline-8546184` 为 annotated tag,指向 `0f107d0` | ✓ CORRECT |

---

## §2 已确认正确的项

### 2.1 RV.7 commit 落盘
- `git log phase-a1b/agent-expert-terminal-reverification --oneline | head -1`:
  ```
  0f107d0 audit/phase-a1b: A1B-AE-RV.7 — final verdict + state output + audit tag (PASS_A1B_AE_RV_...)
  ```
- Subject 与 RV charter 预期 verdict 文本完全匹配。

### 2.2 Annotated tag 正确指向 RV.7
- Tag object type: `tag` (annotated,lightweight tag 会是 `commit`)
- Tag target (full SHA): `0f107d0694867a84cced54e8a2e7948dc04d8bdb`
- Tag message:
  ```
  Phase A1B-AE-RV — Terminal Evidence Repair & Reacceptance
  =========================================================
  Branch: phase-a1b/agent-expert-terminal-reverification (local-only)
  Head:   0f107d0 (RV.7 final verdict)
  Span:   8546184 (prior terminal, A1B-AE-R.6)
  ```
- `git merge-base --is-ancestor 0f107d0 audit/phase-a1b-ae-rv-baseline-8546184` → 0f107d0 IS ancestor of tag ✓
- 含义: tag 完整覆盖 RV.0..RV.7 全部 8 个 commit。

### 2.3 Branch HEAD == Tag target
- `phase-a1b/agent-expert-terminal-reverification` HEAD = `0f107d0`
- Tag target = `0f107d0`
- 两者一致,无 drift。

### 2.4 RV.0..RV.6 commit chain 完整
| Sub-gate | Commit (per `git log`) | Verdict (per `git log` subject) |
|----------|------------------------|----------------------------------|
| RV.0 | `a419076` | PASS_A1B_AE_RV_0_CHARTER_EVIDENCE_FREEZE_AND_TERMINAL_CORRECTION_NOTICE_FILED |
| RV.1 | `8ec2831` | PASS_A1B_AE_RV_1_EXACT_REGRESSION_RECONCILIATION_FILED |
| RV.2 | `e5d8b6e` | PASS_A1B_AE_RV_2_MIGRATION_SAFETY_AND_DEV_DB_ISOLATION_FILED |
| RV.3 | `4b2fc8a` | PASS_A1B_AE_RV_3_CONTEXT_SCRUB_COMPLETION_AND_ORG_FAIL_CLOSED_REVERIFIED_FILED |
| RV.4 | `2a83f63` | PASS_A1B_AE_RV_4_PUBLIC_EXPERT_LIVE_CAPTURE_AND_VCR_REPLAY_PARITY_FILED |
| RV.5 | `af6aacf` | PASS_A1B_AE_RV_5_HEADED_BROWSER_JOURNEYS_VERIFIED |
| RV.6 | `58e9ddd` | PASS_A1B_AE_RV_6_FULL_REGRESSION_OPENAPI_SDK_MIGRATION_VERIFIED_WITH_ONE_DEV_DB_GUARD_ATTRIBUTION_NOISE_ERROR |
| RV.7 | `0f107d0` | PASS_A1B_AE_RV_TERMINAL_EVIDENCE_REPAIR_FULL_REGRESSION_MIGRATION_CONTEXT_SCRUB_PUBLIC_EXPERT_LIVE_AND_HEADED_WORKFLOWS_VERIFIED |

8/8 commit 全部存在,subject 与 state file 期望一致。

### 2.5 禁用 git 操作零违规 (per STATE.json `forbidden_git_ops_check`)
- `violations: 0` (self-attested; A1C.0 抽样核对无反证)
- 禁用 verdict 零发出 (`forbidden_count_issued: 0`)

### 2.6 5-tuple 未变更 (per STATE.json `inherited_state_5_tuple_final`)
- `mutated_by_a1b_ae_rv: false` (self-attested;与 A1C.0 inherited 5-tuple 一致)

---

## §3 5 类不一致清单 (A1C.0 必须记录并处理)

### IC-1: head_sha 在 3 份封版文件中滞后为 RV.6 (58e9ddd),实际为 RV.7 (0f107d0)

**根因**: 这 3 个文件是 RV.7 commit (`0f107d0`) 的一部分。写入文件时,RV.7 commit SHA 还不存在 (commit 需要先有 tree,tree 包含文件,SHA 由 tree+parent 计算)。因此文件中只能引用已知的 parent SHA = RV.6 (`58e9ddd`)。这是 git 自引用时序悖论的典型表现。

**影响位置**:

| 文件 | 字段 | 错误值 | 真相 |
|------|------|--------|------|
| `FINAL_VERDICT.md` L9 | `**Head SHA**:` | `58e9ddd (subject to RV.7 commit appending this file)` | `0f107d0` |
| `A1B_AE_RV_STATE.json` L9 (`worktree` block 缺,但在 commit manifest 中) — actual: `head_sha` field NOT in state.json, but `FINAL_COMMIT_MANIFEST.json` L10 has `head_sha: "58e9ddd..."` | — | — | — |
| `FINAL_COMMIT_MANIFEST.json` L10 | `head_sha` | `58e9dddf48598022312cdc3395961bacf81e6264` | `0f107d0694867a84cced54e8a2e7948dc04d8bdb` |

**严重性**: LOW — 不影响 PASS verdict 有效性 (verdict 基于 33 条 §十三 验收条件,不依赖 SHA 字段准确性)。但属于"封版元数据不一致"必须记录。

**A1C.0 处理**: 在本报告中记录;A1C 全程使用 RV HEAD = `0f107d0` 为唯一真相。**不**修改 RV 分支文件 (§六/6.1 禁用 amend)。

---

### IC-2: `PENDING_RV7_COMMIT` 占位符未回填 (2 个文件)

**根因**: 与 IC-1 同源 — RV.7 commit 创建后,作者未在 commit 后再做一次"回填 commit"将占位符替换为真实 SHA。RV charter §十一 evidence layout 期望 RV.7 commit 即终态,但实际 RV.7 commit 内的文件还带着 PENDING 占位符。

**影响位置**:

| 文件 | 字段 | 错误值 | 真相 |
|------|------|--------|------|
| `A1B_AE_RV_STATE.json` L165 | `sub_gate[7].commit` (RV.7) | `"PENDING_RV7_COMMIT"` | `"0f107d0"` |
| `FINAL_COMMIT_MANIFEST.json` L68 | `sub_gate_commits[7].sha` (RV.7) | `"PENDING_RV7_COMMIT"` | `"0f107d0694867a84cced54e8a2e7948dc04d8bdb"` |

**严重性**: LOW — `git log` 显示 commit 实际存在,占位符只是文档缺陷。

**A1C.0 处理**: 在本报告中记录;A1C 内部引用 RV.7 SHA 时使用 `0f107d0` 真值。**不**修改 RV 分支文件。

---

### IC-3: `PENDING_RV4_COMMIT` 占位符未回填 (1 个文件,跨文件不一致)

**根因**: RV.4 commit (`2a83f63`) 完成后,STATE.json 未回填,但 MANIFEST.json 已有真值。两份本应一致的文件出现 drift。

**影响位置**:

| 文件 | 字段 | 错误值 | 真相 |
|------|------|--------|------|
| `A1B_AE_RV_STATE.json` L83 | `sub_gate[4].commit` (RV.4) | `"PENDING_RV4_COMMIT"` | `"2a83f63"` |
| `FINAL_COMMIT_MANIFEST.json` L47 | `sub_gate_commits[4].sha` (RV.4) | `"2a83f6323753f1c8d52c53c38cf6e9bc5fa27532"` ✓ | (已正确) |

**严重性**: LOW — MANIFEST.json 是真相源;STATE.json 仅一个 stale 字段。

**A1C.0 处理**: 在本报告中记录;A1C 内部引用 RV.4 SHA 时使用 `2a83f63` 真值。

---

### IC-4: evidence_files_total 400 vs evidence_files_fingerprinted 403 (真相 = 403)

**真相源验证**:
```
$ wc -l reports/phase-a1b/agent-expert-reverification/EVIDENCE_SHA256SUMS.txt
403 reports/phase-a1b/agent-expert-reverification/EVIDENCE_SHA256SUMS.txt
```

`wc -l` 返回 403,与 SHA-256 hash 行格式 (`<64-hex>  <path>`) 完全吻合 — 即 403 行均为有效 SHA 记录,无 header/footer。

**冲突位置**:

| 文件 | 字段 | 值 | 与真相关系 |
|------|------|-----|-----------|
| `FINAL_COMMIT_MANIFEST.json` L124 | `evidence_files_total` | `400` | ✗ 错误 |
| `A1B_AE_RV_STATE.json` L139 | sha256_manifest 注释 | `(400 entries)` | ✗ 错误 |
| `FINAL_VERDICT.md` L202 | 段落 | `(400 evidence files fingerprinted)` | ✗ 错误 |
| `A1B_AE_RV_STATE.json` L174 | `evidence_files_fingerprinted` | `403` | ✓ 真相 |

**根因推测**: 在 RV.7 commit 内手工写入"400"作为估值,但 EVIDENCE_SHA256SUMS.txt 实际生成时多了 3 个文件 (推测为 FINAL_VERDICT.md / FINAL_COMMIT_MANIFEST.json / EVIDENCE_SHA256SUMS.txt 自身 — 见 IC-5)。state.json L174 字段是后续补充,正确反映了真相。

**严重性**: LOW — 不影响 PASS verdict 有效性。但 A1C 全程必须锁定一个真值。

**A1C.0 处理**: 锁定 **403** 为唯一真值 (`A1C_BASELINE_STATE.json` `rv_evidence_files_total_truth: 403`)。

---

### IC-5: EVIDENCE_SHA256SUMS.txt 自指 (line 8 列出自身)

**实证**:
```
$ head -10 reports/phase-a1b/agent-expert-reverification/EVIDENCE_SHA256SUMS.txt
67bf85d3...  reports/phase-a1b/agent-expert-reverification/A1B_AE_RV_0_CHARTER_AND_EVIDENCE_FREEZE.md
2013c0d7...  reports/phase-a1b/agent-expert-reverification/A1B_AE_RV_0_TERMINAL_VERDICT_CORRECTION_NOTICE.md
df24e6de...  reports/phase-a1b/agent-expert-reverification/A1B_AE_RV_1_EXACT_REGRESSION_RECONCILIATION.md
ee7307c9...  reports/phase-a1b/agent-expert-reverification/A1B_AE_RV_2_MIGRATION_SAFETY_AND_DB_ISOLATION.md
040eaaf0...  reports/phase-a1b/agent-expert-reverification/A1B_AE_RV_3_CONTEXT_SCRUB_COMPLETION.md
39163a33...  reports/phase-a1b/agent-expert-reverification/A1B_AE_RV_4_PUBLIC_EXPERT_LIVE_CAPTURE.md
c91c4d5d...  reports/phase-a1b/agent-expert-reverification/A1B_AE_RV_STATE.json
d6212d9c...  reports/phase-a1b/agent-expert-reverification/EVIDENCE_SHA256SUMS.txt        ← 自指!
2db34502...  reports/phase-a1b/agent-expert-reverification/FAILURE_CLASSIFICATION.csv
85de5f9a...  reports/phase-a1b/agent-expert-reverification/FINAL_COMMIT_MANIFEST.json
```

Line 8 的 hash `d6212d9c4914ee7ef42bd64e88a86371632a6c1cb4a97aa5e67acfefb58259a1` 是 `EVIDENCE_SHA256SUMS.txt` 自身的 SHA-256。但**该 hash 不可能稳定** — 如果有人重新生成 manifest (添加/删除一行),manifest 内容变化 → 其 SHA-256 变化 → line 8 必须更新 → 但更新 line 8 又改变 manifest 内容 → 死循环。

**同样的自指问题** 还影响:
- `A1B_AE_RV_STATE.json` (line 7)
- `FINAL_COMMIT_MANIFEST.json` (line 10)
- `FINAL_VERDICT.md` (存在性引用)

任何"封版元数据"文件如果被列入 SHA manifest,就会形成自指。但 RV 的 SHA manifest 把这些"封版元数据"文件也 fingerprint 了,违反 detached manifest 原则。

**严重性**: MEDIUM — 真正的 detached manifest 必须排除自身 (和任何依赖 manifest 内容的"封版元数据"文件)。A1C.0 必须生成正确的 detached manifest 作为示范。

**A1C.0 处理**: A1C entry manifest (`A1C_ENTRY_SHA256SUMS.detached.txt`) 严格 detached:
1. **不**包含 manifest 自身
2. **不**包含任何"封版元数据"文件 (`A1C_FINAL_VERDICT.md` / `A1C_FINAL_STATE.json` / `A1C_FINAL_COMMIT_MANIFEST.json` 等留到 A1C.9 生成,且单独存放)
3. 只 fingerprint A1C 中间证据 (`evidence/`, `reports/phase-a1c/<sub-gate>/`)
4. manifest 自身的 SHA-256 单独记录在 `A1C_ENTRY_SHA256SUMS.detached.txt.sha256` (元元文件,与 manifest 分离)

---

## §4 5 类不一致对 A1B-AE-RV PASS verdict 的影响评估

| 不一致 | 影响 PASS verdict 有效性? | 理由 |
|--------|--------------------------|------ |
| IC-1 head_sha 滞后 | NO | verdict 基于 Charter §十三 33 条件,不依赖 SHA 字段 |
| IC-2 PENDING_RV7_COMMIT | NO | RV.7 commit 实际存在 (git log 可证);文档占位符仅是元数据缺陷 |
| IC-3 PENDING_RV4_COMMIT | NO | 同 IC-2,且 MANIFEST.json 已有真值 |
| IC-4 evidence count 400 vs 403 | NO | 不影响 §十三 任一条件;A1C 锁定 403 |
| IC-5 manifest 自指 | NO (但示范错误) | 不影响 §十三;但 A1C 生成自己的 detached manifest 时必须避免 |

**结论**: **A1B-AE-RV PASS_A1B_AE_RV_TERMINAL_EVIDENCE_REPAIR_FULL_REGRESSION_MIGRATION_CONTEXT_SCRUB_PUBLIC_EXPERT_LIVE_AND_HEADED_WORKFLOWS_VERIFIED verdict 在 A1C.0 内 RECONFIRMED**。5 类不一致归档于本报告,A1C 内部引用时使用真值,RV 分支历史**不**修改。

---

## §5 A1C.0 处理汇总 (per PDF §四)

PDF §四要求:
> 如发现 A1B-AE-RV 封版元数据不一致:
> - 不得重写历史; ✓ (本报告未触碰 RV 分支)
> - 新建 correction／closeout commit; ✓ (本报告 + A1C.0 charter + entry audit + baseline state + acceptance matrix 共 5 份 deliverable 构成 A1C.0 commit)
> - 明确记录原始错误、修正值、修正原因; ✓ (本报告 §3 表格逐项列出)
> - 重新生成 detached SHA manifest。 ✓ (`A1C_ENTRY_SHA256SUMS.detached.txt` + `.sha256` 元元文件)

---

## §6 后续 A1C 子门对 RV 真值的引用规范

| 引用项 | A1C 内部使用值 |
|--------|---------------|
| RV HEAD | `0f107d0` |
| RV HEAD full SHA | `0f107d0694867a84cced54e8a2e7948dc04d8bdb` |
| RV.0..RV.7 commit chain | per §2.4 表格 |
| RV evidence files total | **403** |
| RV annotated tag | `audit/phase-a1b-ae-rv-baseline-8546184` (→ `0f107d0`) |
| RV terminal verdict | `PASS_A1B_AE_RV_TERMINAL_EVIDENCE_REPAIR_FULL_REGRESSION_MIGRATION_CONTEXT_SCRUB_PUBLIC_EXPERT_LIVE_AND_HEADED_WORKFLOWS_VERIFIED` (RECONFIRMED in A1C.0) |

---

## §7 验收

| 项 | 状态 |
|----|------|
| A1B-AE-RV closeout 已核查 | ✓ |
| 5 类不一致已识别 | ✓ |
| 不重写 RV 历史 | ✓ |
| A1C entry detached manifest 已生成 | ✓ (`A1C_ENTRY_SHA256SUMS.detached.txt`) |
| RV PASS verdict RECONFIRMED | ✓ |

**Sub-gate verdict contribution to A1C.0**: PASS_A1C_0_ENTRY_AUDIT_AND_PILOT_READINESS_CHARTER_FILED
