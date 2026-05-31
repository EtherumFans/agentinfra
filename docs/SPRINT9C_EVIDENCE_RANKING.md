# Sprint 9C — Evidence Ranking & Support Validation

**日期**: 2026-05-12
**范围**: 证据排名、证据强度评分、无支撑编码检测、冲突检测、Runtime 审计

---

## 1. 动机

之前的 `EvidenceVerificationExpert` 对证据质量的判断极其粗糙：仅基于文本长度 (>20 字符 = "good", ≤20 = "marginal", 空 = "none")。没有来源加权、没有证据冲突检测、没有无支撑编码标记。

Sprint 9C 的目标：让 iCoDer 不只是"找到了证据"，而是能够判断证据的强弱、来源、直接性，主动检测冲突和无支撑编码，并将这些结果写入 Runtime 审计链。

---

## 2. Evidence Category

| Category | 定义 | 判定条件 |
|----------|------|---------|
| **direct** | 直接证据 — 出院诊断/手术记录中的明确陈述 | strength_score ≥ 0.6 |
| **inferred** | 推断证据 — 从治疗过程推断 | 0.3 ≤ strength_score < 0.6 |
| **weak** | 弱证据 — 既往史/背景/不确定描述 | strength_score < 0.3 |
| **conflicting** | 冲突证据 — 否定/排除描述 | negation=True |
| **unsupported** | 无支撑 — 未找到任何证据 | strength_score < 0.2 |

---

## 3. Evidence Strength Scoring (11 因子)

| # | 因子 | 权重 | 判定方式 |
|---|------|------|---------|
| 1 | 出院诊断/出院小结 | +0.15 | doc_type 含"出院" |
| 2 | 手术记录 | +0.12 | doc_type == "手术记录" |
| 3 | 病程记录 | +0.08 | doc_type == "病程记录" |
| 4 | 检查/检验报告 | +0.06 | doc_type 含检查/检验/报告/病理/MRI/CT |
| 5 | 既往史 | -0.10 | doc_type == "既往史" 或 "N年前" 模式 |
| 6 | 入院原因一致性 | +0.05 | 2-char 分词 token 匹配 |
| 7 | 治疗一致性 | +0.05 | 手术/操作名称在证据中出现 |
| 8 | 时间线一致性 | +0.05 | 证据描述与时间线事件匹配 |
| 9 | 主诊断一致性 | +0.03 | 证据文本含主要诊断名称或编码 |
| 10 | 否定词 | -0.20 | negation == True |
| 11 | 不确定描述 | -0.05 | certainty == "suspected"/"probable" |

---

## 4. Unsupported Coding Detection

每个候选编码检查其是否有足够证据支撑：

| 判定条件 | 结果 |
|---------|------|
| 未找到任何相关证据 | unsupported_flag=true, review_required=true |
| 证据强度 < 0.2 | unsupported_flag=true, review_required=true |
| 证据强度 0.2–0.35 | 边界标记（暂不升级） |
| 证据强度 ≥ 0.35 | 通过 |

无支撑编码检测结果写入 Runtime audit (`unsupported_code_flagged` 事件)。

---

## 5. Conflict Detection (5 种冲突类型)

| 冲突类型 | 检测方式 | 严重度 |
|---------|---------|--------|
| **diagnosis_treatment_mismatch** | 存在感染诊断但无抗感染治疗/操作 | 高 |
| **discharge_progress_contradiction** | 候选编码含否定/排除证据 | 高 |
| **procedure_record_mismatch** | 手术编码部位与证据文本不一致 | 中 |
| **primary_diag_admission_mismatch** | 主诊断(化疗Z51)与入院原因(手术)矛盾 | 高 |
| **diagnosis_outcome_mismatch** | 预留 — 诊断与出院结局不一致 | 低 |

冲突检测结果写入 Runtime audit (`evidence_conflict_detected` 事件)。

---

## 6. Runtime Integration

新增 2 个 DUC 操作：

| DUC Action | 触发条件 | 审计事件 |
|-----------|---------|---------|
| `flag_unsupported_code` | 检测到无支撑编码 | `unsupported_code_flagged` (code, name, reason, strength_best) |
| `resolve_evidence_conflict` | 检测到证据冲突 | `evidence_conflict_detected` (conflict_type, summary, affected_codes) |

这两个操作都需要 REVIEW_REQUIRED 状态 — Runtime guard 确保人工复核后才能确认。

---

## 7. Evaluation Enhancement

新增评估指标：

| 指标 | 计算方式 | 含义 |
|------|---------|------|
| `evidence_strength_avg` | mean(strength_score) | 所有证据的平均强度 |
| `unsupported_code_rate` | unsupported_codes / total_codes | 无支撑编码占比 |
| `conflict_rate` | conflicts / total_codes | 存在证据冲突的编码占比 |

这些指标补充了原有的 `evidence_binding_rate` (20% 评测权重)。

---

## 8. Pipeline 变更

```
Step 7a: Evidence Verification   [已有 — 绑定率检查]
Step 7b: Evidence Ranking         [新增 — 排名、无支撑检测、冲突检测]
Step 8a: DRG/DIP Analysis         [已有]
```

---

## 9. 新增/修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `services/evidence_ranker.py` | 新增 | EvidenceRanker 确定性评分引擎 (392 行) |
| `schemas/evidence_ranking.py` | 新增 | EvidenceRank, EvidenceRankingResult, ConflictResult 等 Pydantic 模型 |
| `tests/test_services/test_evidence_ranker.py` | 新增 | 36 个测试用例 |
| `agents/orchestrator.py` | 修改 | 插入 evidence_ranking 步骤 + Runtime audit |
| `services/llm_planner.py` | 修改 | FIXED_PIPELINE_STEPS 新增 evidence_ranking |
| `services/runtime.py` | 修改 | DUC_ACTIONS 新增 flag_unsupported_code, resolve_evidence_conflict |

---

## 10. 测试结果

```
test_evidence_ranker.py: 36 passed, 1 skipped
全量后端测试: 245 passed, 4 skipped, 0 failed
```

测试覆盖：
- 来源文档评分 (7): 出院/手术/病程/检查/既往史/主诉/未知
- 既往史检测 (3): N年前/N月前/当前症状
- 入院一致性 (3): 高匹配/无匹配/空原因
- 否定与不确定 (4): 否定/疑似/排除/确认
- 分类赋值 (5): direct/inferred/weak/conflicting/suspected-weak
- 单编码证据排名 (4): 排序/否定惩罚/空文本跳过/字段完整性
- 无支撑编码检测 (2): 无证据/有证据
- 冲突检测 (4): 否定候选/化疗vs手术/化疗入学/无冲突
- 全证据排名 (2): 结构完整性/分数范围
- Schema 往返 (2): EvidenceRank/EvidenceRankingResult
- Pipeline 集成 (1): API 响应含 evidence_ranking

---

## 11. 当前局限

| 局限 | 说明 |
|------|------|
| 评分权重硬编码 | 11 个因子的权重来自经验，未经校准 |
| 入院原因一致性粗糙 | 2-char 分词 token 匹配可能漏掉语义相近但字面不同的描述 |
| 感染-治疗冲突检测简单 | 仅检查关键词，不分析实际治疗方案与诊断的临床关系 |
| 时间线一致性有限 | 当前时间线数据依赖 LLM 提取质量 |
| 无 LLM 语义理解 | 所有判断均为规则/关键词匹配，不涉及语义推理 |
| unsupported 和 weak 边界模糊 | 阈值 0.2/0.35 需根据真实数据校准 |
