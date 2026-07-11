# Phase 5 Track B-1 Correction (Per PDF §3.3 + §17)

**Issued**: 2026-07-11 (during Phase 5 Track C Gate 0A)
**Supersedes**: Phase 5 Track B-1 verdict `PASS_WITH_CORTI_PERMISSION_LIMITATIONS` (tier 2)
**Corrected by**: Phase 5 Track B-2 runtime evidence (commits `ea14f0c` through `e4a6a30`)

---

## 1. B-1 → B-2 → Track C 纠错链

PDF §3.3 + §17 要求 B-2 完成 6 项纠错声明。B-2 commit `e4a6a30` 已完成主体纠错；本报告正式归档 6 项撤销/修正：

| B-1 原结论 | B-2 修正证据 | 状态 |
|---|---|---|
| **iCoDer UX 全面高于 Corti** (B-1 56.8/100) | B-2 UX 重算 **76.8/100** (3.84/5 × 20)；UX 单维度最高 copy_download=5.0 全员，最低 trace_transparency=2.11（PureLLM agents 仅 1 event） | **CORRECTED** |
| **Code Validation 可运行** | B-2 runtime evidence: provider NotImplementedError → SKELETON fallback，无 LLM call，无 cost；CP2 verdict 降为 `METADATA_ONLY` | **CORRECTED** |
| **DRG/DIP grouping 已实现** | B-2 CP9 evidence: drg-analyzer 输出仅 `risk_points` + `drg_dip_rule_reservation_note` 明示"DRG 分组由医保结算侧引擎完成"；Grouper/DIP Score/CMI/Payment Simulation 全部 NOT_IMPLEMENTED | **CORRECTED** |
| **Expert 配置即 Expert 调用** | B-2 全 9 agent §19 Expert 实证：medical-coding 标 `EXPERT_INVOKED (LLM-level)`，CP4-CP9 PureLLM agents 标 `EXPERT_INVOKED (LLM-level)` 但实际无 tool_calling；区分 EXPERT_INVOKED vs CONFIGURED-only | **CORRECTED** |
| **Embedded Smoke 即医院集成 Ready** | B-2 §26 hospital integration matrix：medical-coding 标 READY，CP4/CP6/CP7 标 CONDITIONAL READY（markdown JSON 需 parse），CP2/CP5/CP8/CP9 标 NOT APPLICABLE / CONDITIONAL；区分 embedded chain validated vs hospital ready | **CORRECTED** |
| **Medical Coding 已 Production Ready** | B-2 CP1 verdict 升 `READY_FOR_QUALITY_BENCHMARK`（最高）但 production_ready=false 仍标记；不宣称医院生产部署 | **CORRECTED** |

---

## 2. B-1 错误根源

### 2.1 UX 平均分计算偏差（B-1 56.8 vs B-2 76.8）

B-1 用 12 dimension 平均但未对每个 agent 单独评分，导致某些维度（如 trace_transparency）拖累整体；B-2 per-agent × per-dimension 矩阵化后，trace_transparency 仅影响 PureLLM agents（CP4-CP9），medical-coding 不受影响。

### 2.2 CP2 SKELETON 误判（B-1 RUNTIME_INVOKED）

B-1 仅静态分析 backend code，未跑 CP2 runtime；B-2 实际调用 `/api/v1/agents/code-validation-agent/run` 显示：
- envelope.error=false 但 `result.raw_provider_response.skeleton=true`
- 无 latency_ms（skeleton 立即返回）
- 无 cost（无 LLM 调用）

→ CP2 实际 `AGENT_CONFIGURED` 层，非 `RUNTIME_INVOKED + RESULT_CONSUMED`。

### 2.3 DRG/DIP Grouper 推断（B-1 "已实现"）

B-1 误读 drg-analyzer pack 中的 `high_cost_drg_families: ["AH", "AL", "BB", "BJ", "CB"]` 配置为已 wired；B-2 实际运行确认 agent 仅输出风险提示，未调用任何 Grouper engine。

### 2.4 Corti webhook/SSE 未实证

B-1 + B-2 均未实证（Corti 运行权限限制，标 `CORTI_RUNTIME_BLOCKED_BY_PERMISSION`）。**Track C Gate 0B 会重新尝试浏览器观察**。

---

## 3. 修正后的 Phase 5 Track B 整体裁决

# `PASS_ALL_RUNNABLE_AGENTS_DEEPLY_VALIDATED_WITH_GAPS`

(tier 1 + WITH_GAPS qualifier, supersedes B-1 tier 2)

理由：
- 9/9 checkpoints runtime validated
- 8/9 real DeepSeek evidence
- 32-34 field reports
- Corti similar-agent replication analysis (per user directive 2026-07-11)
- 7-stage orchestrator wiring roadmap (per user directive 2026-07-11)
- 32 gap backlog (1 P0 + 15 P1 + 10 P2 + 6 P3)
- 6 B-1 errors all corrected

---

## 4. 影响 Track C

B-2 的 15 P1 gap 直接成为 Track C 范围：
- Gate 1 修 CP2 SKELETON P0
- Gate 1 修 8× unified API 结构化 P1
- Gate 2 修 R002 ICD-10-CN localization P1
- Gate 3-4 修 7× orchestrator wiring P1

Track C 完成后 B-2 verdict 限定词 `WITH_GAPS` 可去掉，进入正式 quality benchmark。
