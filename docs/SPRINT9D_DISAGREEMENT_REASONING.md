# Sprint 9D — Disagreement Reasoning

**日期**: 2026-05-12
**范围**: 分歧分类、修正模型、DRG 敏感性检测、Gold evolution、Runtime audit、评估增强

---

## 1. 动机

之前的不一致检测 (`_analyze_disagreement` in homepage_expert) 仅限于主要诊断级别的 AI-vs-现有编码比较，没有分歧类型分类、结构化修正模型、DRG 影响敏感度、或系统学习能力。

Sprint 9D 的目标："让人工修正成为可解释、可沉淀、可评估的认知反馈。"

---

## 2. Disagreement Taxonomy (分歧分类法)

8 种分歧类型，按严重度排列：

| # | 类型 | 描述 | 示例 |
|---|------|------|------|
| 1 | **code_specificity** | 编码特异性差异 — 同一概念，不同粒度 | M80.900 (未特指) vs M80.000 (绝经后) |
| 2 | **code_selection** | 编码选择差异 — 不同概念，不同编码 | J15.200 (肺炎) vs R91.x02 (肺部阴影) |
| 3 | **diagnosis_interpret** | 诊断解读差异 — 同一临床证据，不同诊断理解 | 同一影像报告解读不同 |
| 4 | **primary_vs_secondary** | 主次优先级差异 — AI选了A为主诊断，金标选了B | Z51.102 (化疗为主) vs C20.x00 (肿瘤为主) |
| 5 | **rule_violation** | 规则违反 — 一方有规则支撑，另一方没有 | AI有R013支撑，现有编码无 |
| 6 | **evidence_contradiction** | 证据矛盾 — 证据指向不同编码 | 否定描述被编码为确认诊断 |
| 7 | **drg_sensitive** | DRG敏感 — 编码变更影响DRG分组 | AI的RW 0.82 vs 修正后 RW 1.35 |
| 8 | **documentation_gap** | 文书缺口 — AI遗漏了金标中有的编码 | 金标C50.900未被AI识别 |

---

## 3. Correction Model (修正模型)

每条修正记录包含：

```json
{
  "case_id": "DEMO-001",
  "code_ai": "M80.900",
  "code_ai_name": "未特指骨质疏松伴病理性骨折",
  "code_correct": "M80.000",
  "code_correct_name": "绝经后骨质疏松伴病理性骨折",
  "disagreement_type": "code_specificity",
  "type_rationale": "编码特异性差异：AI选择M80.900，金标准为M80.000...",
  "drg_impacted": false,
  "drg_before": "",
  "drg_after": "",
  "rw_delta": 0.0,
  "rule_reference": ["R003"],
  "evidence_support": "骨密度检查确认绝经后骨质疏松",
  "reviewer": "CODER-A",
  "timestamp": "2026-05-12T10:00:00",
  "learnable": true
}
```

### learnable 字段

标记此修正模式是否可复用于未来案例：
- **True**: specificity 差异、rule violation、documentation gap — 系统可学习
- **False**: diagnosis_interpret — 需要临床判断，不能自动推广

---

## 4. DRG-Sensitive Disagreement (DRG敏感分歧)

通过比较 AI 编码和修正编码的 DRG 分组差异判断：

| 检测条件 | 严重度 |
|---------|--------|
| 编码大类不同 (不同 ICD 章节首字母) | 高 — 可能改变 DRG |
| 编码出现在 DRG 风险列表中 | 高 — 已知影响 DRG |
| 同一章节但特异性不同 | 低 — 可能在同 DRG 内 |

---

## 5. Gold Evolution (金标进化)

修正记录的积累路径：
1. 每轮评估产生 `CorrectionRecord` 列表
2. `learnable=True` 的记录可沉淀为规则调整建议
3. `type_distribution` 统计哪个分歧类型最常见 → 优先修复方向
4. 高频 `code_specificity` 分歧 → 提示需要增强编码特异性训练
5. 高频 `documentation_gap` 分歧 → 提示证据提取需改进

---

## 6. Runtime Audit

新增审计事件：

| 事件 | 触发条件 | Payload |
|------|---------|---------|
| `disagreement_analyzed` | 每个检测到的分歧 | code_ai, code_correct, type, drg_impacted |
| `drg_impact_correction` | 分歧变更了 DRG | code_ai, code_correct, drg_before, drg_after |

---

## 7. Evaluation Enhancement

新增评估维度：

| 指标 | 计算 | 意义 |
|------|------|------|
| `disagreement_rate` | disagreements / total_codes | 整体一致率 |
| `drg_impact_rate` | drg_impacted / total_disagreements | 高影响分歧占比 |
| `learnable_corrections` | learnable=True 的修正数 | 可沉淀为系统改进的比例 |
| `type_distribution` | 每种 DisagreementType 的计数 | 分歧根因分布 |

---

## 8. Pipeline 位置

```
Step 7a: Evidence Verification
Step 7b: Evidence Ranking
Step 7c: Disagreement Analysis  [NEW]
Step 8a: DRG/DIP Analysis
```

---

## 9. 新增/修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `schemas/disagreement_reasoning.py` | 新增 | DisagreementType 枚举, CorrectionRecord, DisagreementSummary, DisagreementAnalysisResult |
| `services/disagreement_analyzer.py` | 新增 | 分类引擎 + DRG 敏感检测 + 修正建模 |
| `tests/test_services/test_disagreement_analyzer.py` | 新增 | 19 个测试用例 |
| `agents/orchestrator.py` | 修改 | 插入 disagreement_analysis 步骤 + Runtime audit |
| `services/llm_planner.py` | 修改 | FIXED_PIPELINE_STEPS 新增 |

---

## 10. 测试结果

```
test_disagreement_analyzer.py: 19 passed, 1 skipped
全量后端测试: 264 passed, 5 skipped, 0 failed
```

---

## 11. 当前局限

| 局限 | 说明 |
|------|------|
| Gold codes 依赖外部提供 | 当前通过 encounter_data["gold_diagnosis_codes"] 传入，实际使用时需要 gold case 标注数据 |
| DRG 敏感检测简单 | 仅按编码首字母章节不同判断，未使用真实 DRG grouper 计算 |
| learnable 判定粗糙 | 仅按 type 排除 diagnosis_interpret，未分析具体修正模式 |
| 时间线未用于分歧分析 | 可增加时间线事件与编码选择的时间关系判断 |
| Gold evolution 无持久化 | 修正记录当前只在内存中，需要持久化存储 + 定期分析 pipeline |
