# A1B-AE-R.0 — Journey 7 Evidence Correction

**Sub-gate**: A1B-AE-R.0
**Captured at**: 2026-07-22T12:55:56Z
**Target journey**: Journey 7 (`clone_preset`) in `reports/phase-a1b/evidence/journey_07_clone_preset/`
**A1B-AE.10 verdict under review**: `API_WORKFLOW_VERIFIED`
**A1B-AE-R.0 corrected verdict**: `EVIDENCE_MISJUDGMENT_CORRECTED`

---

## §1. 原始证据(A1B-AE.10 归档)

### §1.1 Operation

```
GET /api/v1/agents/resolve/code_validation
```

### §1.2 Observed response

- Status: `404`
- Response SHA-256: `6348a9ccc03eee02b3afc551d33bfd94abd385b5d37bc269e474136ec2783a72`
- Body:
  ```json
  {
    "detail": "Agent not found for key='code_validation' (resolved='code-validation')"
  }
  ```

### §1.3 A1B-AE.10 inspection.md 原文

```
# Journey 7: Agent Alias Resolution (code_validation → code-validation)

**Slug**: `clone_preset`
**Captured**: 2026-07-22T092838Z
**Verdict**: `API_WORKFLOW_VERIFIED`
**Provenance**: `ICODER_INTERNAL`

## Notes

404 is acceptable if no Agent named 'code_validation' has been seeded; the alias
resolver still attempted resolution without crashing.
```

---

## §2. 为什么原 verdict 是误判

### §2.1 Journey 7 的语义意图

按 A1B-AE.10 driver(`backend/scripts/a1b_ae_10_run_journeys.py`)和 A1B-AE Charter §4.3 的 journey 列表,Journey 7 的 slug 是 `clone_preset`。**Slug 即语义**:这个 journey 的目的是**从 Preset 克隆出一个可运行 Agent**,不是测 alias resolver 是否崩溃。

`API_WORKFLOW_VERIFIED` 这个 verdict 暗示"journey 的预期目标已达成"。但一个返回 `"Agent not found"` 的 404 显然没达成 clone-preset 的目标。

### §2.2 Response body 是决定性证据

```json
{
  "detail": "Agent not found for key='code_validation' (resolved='code-validation')"
}
```

这句话明确说:
1. AliasResolver 正确把 `code_validation` 解析为 `code-validation`(这部分是 PASS)
2. **但数据库里没有 canonical_key = `code-validation` 的 Agent 行**(这部分是 FAIL)

也就是说,clone-preset 从来没有真的发生 — 没有创建任何 Agent。Journey 7 实际上**只是验证了 alias resolver 不崩溃**,没有验证 clone-preset 功能本身。

### §2.3 A1B-AE.10 driver 自身的局限

A1B-AE.10 driver 在 `API_FALLBACK_PER_§4.3` 模式下运行,仅检查 HTTP 状态 + 响应 SHA-256 + 关键字段存在。它没有:
- 检查 Agent 是否真被创建(DB 二级验证)
- 区分"alias 解析成功 + Agent 存在"和"alias 解析成功 + Agent 不存在"
- 对照 journey slug 的语义意图核验 verdict token

A1B-AE.10 已经在 inspection.md 的 Notes 里承认 "404 is acceptable **if** no Agent named 'code_validation' has been seeded" — 这个 conditional 本身就是缺陷信号(seed 应该有这个 Agent,没有就是 bug)。

### §2.4 根因

A1B-AE.4 AliasResolver 实现正确(underscore → dash 解析),但 A1B-AE.8 Preset catalog 里只定义了 5 个 `icoder-*-preset` Agent,**`code-validation` 这个 canonical_key 不在任何 Preset 里**。同时 A1B-AE.9 DEPRECATED.md notices 只标记了 legacy orphan dirs,**没有把 dash-form canonical_key 加入 seed.py 的 prebuilt Agent 列表**。

结果:`GET /api/v1/agents/resolve/code_validation` 永远会返回 404,无论运行多少次。

---

## §3. 纠正后的 verdict

```
EVIDENCE_MISJUDGMENT_CORRECTED
```

### §3.1 为什么不是 `NEGATIVE_VERDICT_CORRECTED`

`NEGATIVE_VERDICT_CORRECTED` 用于**本意就是负向测试**的 journey(如 Journey 8 的 context-delete-nonexistent 404)。Journey 7 本意是正向(clone preset 成功),实测返回 404 是**缺陷被误读为通过**,不是负向测试通过。

### §3.2 为什么不直接降级为 `FAILED`

降级到 `FAILED` 会触发 A1B-AE 的 acceptance §10 失败,但 A1B-AE 已经 closed 在 `85a5c9a`。这个纠正发生在 **A1B-AE-R** 范围内,是对 A1B-AE.10 证据层的 rebase,不是对 A1B-AE terminal verdict 的重开。因此用 `EVIDENCE_MISJUDGMENT_CORRECTED` 标记:**证据被纠正,但 A1B-AE terminal 不动**。

---

## §4. 纠正落到哪里

### §4.1 A1B-AE-R 范围内的修复

R.2 Preset Agent 实体化 必须:
1. 让 Clone Preset 真的创建 Agent 行 — 通过 `POST /api/v1/agents/quick?from_preset=icoder-...` 实现 Corti create-then-customize
2. R.5 Journey 7 重跑必须返回 200 + DB 二级验证(查询 `agents` 表确认新行)

### §4.2 不在 A1B-AE-R 范围内的修改

**不修改** `reports/phase-a1b/evidence/journey_07_clone_preset/inspection.md` 原文 — 该文件是 A1B-AE.10 frozen evidence,A1B-AE-R Charter §3 明确禁止修改 A1B-AE 已提交的 evidence。

**改为** 在本文件(`A1B_AE_R_0_JOURNEY7_EVIDENCE_CORRECTION.md`)记录纠正,并在 `reports/phase-a1b-runtime/evidence/journey_07_clone_preset_replay/`(R.5 时创建)归档重跑结果。

### §4.3 在 INDEX 里的标注

`reports/phase-a1b-runtime/INDEX.md` 在 Journey 7 条目下标注:
```
Journey 7 (clone_preset):
  A1B-AE.10 verdict    = API_WORKFLOW_VERIFIED    [MISJUDGED]
  A1B-AE-R.0 regrade   = EVIDENCE_MISJUDGMENT_CORRECTED
  A1B-AE-R.5 target    = HUMAN_WORKFLOW_VERIFIED  (with DB row evidence)
```

---

## §5. Journey 1-6, 8-10 不受影响

| Journey | A1B-AE.10 verdict | A1B-AE-R 复核 |
|---|---|---|
| 1 registry_browse | API_WORKFLOW_VERIFIED | 保持(R.5 时升级到 HUMAN_WORKFLOW_VERIFIED) |
| 2 research_agent_create | API_WORKFLOW_VERIFIED | 保持 |
| 3 research_agent_run | API_WORKFLOW_VERIFIED | 保持 |
| 4 calculator | API_WORKFLOW_VERIFIED | 保持 |
| 5 interviewing | API_WORKFLOW_VERIFIED | 保持 |
| 6 external_expert_disabled | API_WORKFLOW_VERIFIED | 保持 |
| **7 clone_preset** | **API_WORKFLOW_VERIFIED** | **EVIDENCE_MISJUDGMENT_CORRECTED(本文件)** |
| 8 context_delete | API_WORKFLOW_VERIFIED | 保持(本来就是合法负向测试,404 = no-leak 正确) |
| 9 cross_tenant | API_WORKFLOW_VERIFIED | 保持(R.5 时升级,加第二 JWT 负向测试) |
| 10 logout_cleanup | API_WORKFLOW_VERIFIED | 保持 |

**只有 Journey 7 被降级**。其他 9 个 journey 的 verdict 保持,在 R.5 时统一升级到 `HUMAN_WORKFLOW_VERIFIED`(或对负向的 `NEGATIVE_VERDICT_CORRECTED`)。

---

## §6. 系统性教训(recorded for future phases)

1. **Slug 即语义** — journey 的 verdict token 必须对照 slug 的意图核验,不能只看 HTTP 状态。
2. **Response body 是决定性证据** — `"Agent not found"` 是 fail 信号,不是"alias resolver 没崩溃"的 pass 信号。
3. **DB 二级验证** — clone/create 类操作必须查表确认 row 真的被写入,不能只看 HTTP 200/404。
4. **API fallback 的 conditional note 是缺陷信号** — "404 is acceptable if X" 这种 conditional 说明 X 本身就是未完成的功能。
5. **证据层纠正 ≠ terminal verdict 重开** — A1B-AE-R 可以纠正 A1B-AE.10 的证据判断,但不重开 A1B-AE terminal verdict(那是 Charter §3 out-of-scope)。
