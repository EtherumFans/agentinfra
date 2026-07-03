# Sprint 9E — Confidence Calibration & Selective Automation

**日期**: 2026-05-12
**范围**: 置信度校准、选择性自动化、风险分层路由、校准指标

---

## 1. 动机

之前的置信度是单一的 raw LLM score，使用一个固定的 `AGENT_CONFIDENCE_THRESHOLD = 0.6` 阈值。没有校准验证、没有多源信号融合、没有风险分层路由。高置信编码和低置信编码走同样的路径。

Sprint 9E 的目标："让系统知道哪些编码建议可以信，哪些必须人工复核。"

---

## 2. Confidence Inputs (多源融合)

| # | 输入源 | Sprint 出处 | 权重 | 含义 |
|---|--------|-----------|------|------|
| 1 | raw_score | LLM/Dictionary | 0.35 | 原始模型置信度 |
| 2 | evidence_strength | Sprint 9C Evidence Ranker | 0.25 | 证据质量评分 |
| 3 | rule_match_count | Sprint 9B Homepage Rules | 0.15 | 匹配到的编码规则数 (cap 3) |
| 4 | disagreement_penalty | Sprint 9D Disagreement | -0.15 | 存在分歧时扣分 |
| 5 | negation_penalty | Evidence Extraction | -0.10 | 证据含否定描述时扣分 |
| 6 | specificity_bonus | Code Check | +0.05 | 非 .9 未特指编码加分 |

**校准公式**: `calibrated_score = clamp(Σ(weight_i × input_i), 0, 1)`

---

## 3. Selective Automation Policy (3-Tier)

| Tier | Score Range | 自动化策略 | 人工参与 |
|------|-----------|----------|---------|
| **AUTO** | ≥ 0.80 | 自动通过，快速通道 | 无 (仅审计追踪) |
| **REVIEW** | 0.50–0.79 | 标准人工复核 | 写回前必须复核 |
| **ESCALATE** | < 0.50 | 升级给高级编码员 | 强制资深复核 |

### 强制 override 规则

即使 calibrated_score ≥ 0.80，以下情况强制降级：

| 条件 | 强制最低 Tier | 理由 |
|------|-------------|------|
| 为主要诊断 | REVIEW | 主要诊断绝不自动通过 |
| 编码含 `.9` (未特指) | REVIEW | 特异性不足 |
| 证据标记为 unsupported | ESCALATE | 无支撑编码不可信 |
| 分歧为 DRG_SENSITIVE | ESCALATE | DRG 影响需高级判断 |
| 存在 disagreement | REVIEW (min) | 有分歧需人工裁决 |

---

## 4. Risk-Tier Routing Policy

| 编码类别 | 策略 | 说明 |
|---------|------|------|
| `primary_diagnosis` | REVIEW | 主要诊断绝不自动通过 |
| `secondary_diagnosis` | AUTO | 高分可自动通过 |
| `procedure_code` | AUTO | 高分可自动通过 |
| `drg_sensitive_code` | ESCALATE | DRG 敏感编码始终升级 |
| `mcc_cc_code` | REVIEW | MCC/CC 需复核 |
| `unspecified_code` | REVIEW | .9 编码需复核 |

---

## 5. Calibration Metrics

| 指标 | 计算方式 | 意义 |
|------|---------|------|
| `auto_accept_rate` | auto / total | 自动通过率 |
| `calibration_error_avg` | mean(\|calibrated - correctness\|) | 校准准确度 |
| `false_confidence_rate` | 高置信但错误的编码占比 | 系统过度自信程度 |
| `override_count` | 本可 auto 但被策略降级的编码数 | 安全策略严格度 |
| `tier_distribution` | auto/review/escalate计数 | 工作负载分布 |

---

## 6. Runtime Audit

| 事件 | Payload |
|------|---------|
| `confidence_calibrated` | code, calibrated_score, tier |
| `routing_decision` | code, tier, risk_factors, override_reason |

---

## 7. Pipeline

```
Step 7c: Disagreement Analysis
Step 7d: Confidence Calibration  [NEW]
Step 8a: DRG/DIP Analysis
```

---

## 8. 新增/修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `services/confidence_calibrator.py` | 新增 | 多源校准引擎 + 3-tier 路由 + 风险分层策略 |
| `schemas/confidence.py` | 新增 | CodingConfidence, RoutingDecision, CalibrationMetrics |
| `tests/test_services/test_confidence_calibrator.py` | 新增 | 24 tests |
| `agents/orchestrator.py` | 修改 | 插入 confidence_calibration 步骤 + Runtime audit |
| `services/llm_planner.py` | 修改 | FIXED_PIPELINE_STEPS 新增 |

---

## 9. 测试结果

```
test_confidence_calibrator.py: 24 passed, 1 skipped
全量后端测试: 288 passed, 6 skipped, 0 failed
```

---

## 10. 当前局限

| 局限 | 说明 |
|------|------|
| 权重为经验值 | 6 个输入的权重未经过真实数据校准 |
| 校准 error 计算依赖 gold codes | 无 gold 标注时无法计算 calibration_error_avg |
| false_confidence_rate 需大量样本 | 10 个 demo cases 不足以统计 |
| 风险策略为手工规则 | 未使用 ML 或反馈学习调整策略 |
| 编码类别分类粗糙 | primary/secondary/procedure 三分类，未区分 MCC/CC |

---

## 11. 为什么当前不能宣称 Full Autonomous Coding

1. **主要诊断绝不自动通过** — 始终 REVIEW 最低 — 这是设计决策，不是技术限制
2. **校准权重未经数据验证** — 6 个权重来自工程判断，未在真实数据上校准
3. **校准 error 未收敛** — 10 个 demo cases 样本不足，无法评估校准质量
4. **无安全回退机制** — auto-accept 后无自动修复路径
5. **DRG 影响未量化** — DRG 敏感的自动决策后果未在生产环境中评估
6. **编码员接受度未验证** — 自动接受的编码是否被编码员信任尚未测试

当前系统的自动化仅适用于 **非主要诊断、有高质量证据支撑、无分歧、有特异性编码** 的边缘诊断和手术编码，且仍需保留完整审计追踪。
