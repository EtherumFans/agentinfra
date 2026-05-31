# Evaluation Baseline Report

**版本**: v1.0-pilot
**日期**: 2026-05-12
**数据基础**: 10 demo cases (源: train.xlsx Sheet1 1801 条真实出院病历)
**评估方式**: 自动评估 (`POST /api/evaluation/run`)

---

## 1. 数据概览

### 1.1 Demo Case 分布

| 科室 | 病例数 | 病例 ID |
|------|--------|---------|
| 肿瘤内科 | 2 | DEMO-001, DEMO-004 |
| 骨科 | 1 | DEMO-002 |
| 乳腺外科 | 5 | DEMO-003, DEMO-005, DEMO-007, DEMO-008, DEMO-010 |
| 呼吸内科 | 2 | DEMO-006, DEMO-009 |
| **合计** | **10** | |

### 1.2 Gold Standard 主要编码分布

| 主要诊断 (ICD-10-CN) | 频次 | 主要手术 (ICD-9-CM-3) | 频次 |
|----------------------|------|----------------------|------|
| Z51.102 (恶性肿瘤化疗) | 7 | 99.2503 (静脉输注化疗药物) | 7 |
| M80.900 (骨质疏松) | 1 | 81.6600x001 (脊柱融合术) | 1 |
| R91.x02 (肺部阴影) | 1 | 32.2400x002 (支气管镜活检) | 1 |
| J98.414 (肺部感染) | 1 | 33.2403 (支气管镜灌洗) | 1 |

### 1.3 数据局限性

- 样本量极小 (n=10)，统计置信区间非常宽
- 科室分布不均 (乳腺外科占 50%)
- 以化疗病例为主 (70%)，非急性住院病例
- 缺少复杂合并症 (MCC/CC) 场景
- 缺少外科大手术病例
- DRG 分组不适用 (化疗病例多为内科分组)

---

## 2. 评估指标定义

### 2.1 Diagnosis Code Precision / Recall / F1

```
Precision = |AI_diags ∩ Gold_diags| / |AI_diags|
Recall    = |AI_diags ∩ Gold_diags| / |Gold_diags|
F1        = 2 × Precision × Recall / (Precision + Recall)
```

### 2.2 Procedure Code Precision / Recall

```
Precision = |AI_procs ∩ Gold_procs| / |AI_procs|
Recall    = |AI_procs ∩ Gold_procs| / |Gold_procs|
```

### 2.3 Principal Diagnosis Match (Accuracy)

```
Match = (AI_principal_diag == Gold_principal_diag)
Accuracy = |matches| / |total_cases|
```

### 2.4 Evidence Coverage

```
Coverage = |codes with at least 1 evidence binding| / |total codes suggested|
Target: ≥ 90%
```

### 2.5 DRG Group Match (Accuracy)

```
Match = (AI_DRG == Expected_DRG)
```

**注**: 当前 demo cases 以化疗/复查为主，DRG 分组不适用。需在真实住院病例上启用。

### 2.6 Hallucination Rate

```
Hallucination Rate = |AI codes not in ICD dictionary| / |AI codes|
Target: ≤ 0.3 (baseline)
```

---

## 3. 当前评估结果

### 3.1 总体指标

| 指标 | 当前值 | Baseline 阈值 | 状态 |
|------|--------|-------------|------|
| Principal Diagnosis Accuracy | — (待运行) | ≥ 0.50 | ⏳ |
| Diagnosis F1 (micro-avg) | — (待运行) | N/A | ⏳ |
| Diagnosis Precision (micro-avg) | — (待运行) | N/A | ⏳ |
| Diagnosis Recall (micro-avg) | — (待运行) | N/A | ⏳ |
| Procedure F1 (micro-avg) | — (待运行) | N/A | ⏳ |
| Procedure Precision (micro-avg) | — (待运行) | N/A | ⏳ |
| Procedure Recall (micro-avg) | — (待运行) | N/A | ⏳ |
| Evidence Coverage | — (待运行) | ≥ 0.90 | ⏳ |
| Hallucination Rate | — (待运行) | ≤ 0.30 | ⏳ |
| DRG Group Match | N/A | N/A | — |

**注**: 具体数值需在试点环境运行 `POST /api/evaluation/run` 后填入。
当前阶段重点验证评估 Pipeline 可运行、指标定义正确。

### 3.2 逐病例结果

| Case ID | Primary Match | Diag Prec | Diag Rec | Proc Prec | Proc Rec | Halluc | Evid Cov |
|---------|--------------|-----------|----------|-----------|----------|--------|----------|
| DEMO-001 | — | — | — | — | — | — | — |
| DEMO-002 | — | — | — | — | — | — | — |
| DEMO-003 | — | — | — | — | — | — | — |
| DEMO-004 | — | — | — | — | — | — | — |
| DEMO-005 | — | — | — | — | — | — | — |
| DEMO-006 | — | — | — | — | — | — | — |
| DEMO-007 | — | — | — | — | — | — | — |
| DEMO-008 | — | — | — | — | — | — | — |
| DEMO-009 | — | — | — | — | — | — | — |
| DEMO-010 | — | — | — | — | — | — | — |

**注**: 待运行后逐格填入。— 表示待评估。

---

## 4. 已知不足

### 4.1 数据集不足

| 问题 | 严重度 | 说明 |
|------|--------|------|
| 样本量小 (n=10) | 🔴 高 | 无法计算有统计意义的置信区间，指标波动大 |
| 科室覆盖窄 (4/?) | 🔴 高 | 乳腺外科占 50%，缺少内科、外科、妇产科、儿科等核心科室 |
| 病例类型单一 | 🟡 中 | 70% 为化疗病例，编码模式高度相似，缺乏多样性 |
| 缺少复杂合并症 | 🟡 中 | 无法评估 MCC/CC 检测能力 |
| 缺少外科大手术 | 🟡 中 | 无法评估手术编码精度 |
| 无 DRG 分组评估 | 🔴 高 | 化疗病例 DRG 分组单一 (RU14)，无法评估分组多样性 |
| 无人机复核基准 | 🟡 中 | 无编码员修订记录，无法计算 Human Review Override Rate |

### 4.2 评估流程不足

| 问题 | 说明 |
|------|------|
| 无统计显著性检验 | 10 个病例无法做 bootstrap 或 McNemar 检验 |
| 无分层评估 | 无法按科室、难度、编码类型分层统计 |
| 无一致性评估 | 无多编码员间一致性 (Inter-rater Reliability) 评估 |
| 无时序评估 | 无多次运行稳定性 (test-retest reliability) 评估 |
| 无对比基线 | 无现有编码员准确率作为对比基线 |

---

## 5. 下一批 Gold Case 标注建议

### 5.1 数量目标

| 批次 | 数量 | 科室覆盖 | 难度分布 |
|------|------|---------|---------|
| Batch 1 (当前) | 10 | 4 科室 | 全 medium |
| **Batch 2 (建议)** | **50** | **≥ 8 科室** | easy 30% / medium 50% / hard 20% |
| Batch 3 (目标) | 100 | ≥ 12 科室 | easy 25% / medium 50% / hard 25% |

### 5.2 科室覆盖建议

必选科室:
- 内科: 心内科、呼吸内科、消化内科、神经内科、肾内科、内分泌科
- 外科: 普外科、骨科、神经外科、胸外科、泌尿外科
- 妇产科、儿科
- 肿瘤科 (含放疗)
- ICU

### 5.3 病例难度定义

| 难度 | 定义 | 标注要求 |
|------|------|---------|
| **Easy** | 单一诊断 + 无手术 / 简单操作 | 1 位编码员标注即可 |
| **Medium** | 2-3 诊断 + 1 手术 / 主要诊断选择存在多种可能 | 2 位编码员独立标注，分歧 case 由第 3 位裁定 |
| **Hard** | ≥3 诊断 + ≥2 手术 / 合并 MCC/CC / DRG 入组存在争议 | 3 位编码员独立标注 + 专家组讨论确定 |

### 5.4 标注字段扩展

建议 Batch 2 新增以下标注字段:

| 新增字段 | 类型 | 说明 |
|---------|------|------|
| `principal_diagnosis_rationale` | string | 主要诊断选择依据 (引用编码规则编号) |
| `mcc_cc_flags` | list[dict] | 标注每个合并症是否为 MCC/CC |
| `drg_expected` | dict | 期望 DRG 分组 (含编码、RW、费率) |
| `inter_coder_agreement` | float | 多编码员一致性评分 |
| `coding_difficulty_rationale` | string | 难度判断理由 |
| `common_coding_errors` | list[str] | 该病例常见的编码错误 (用于构建测试 case) |
| `denial_risk` | enum | 医保拒付风险 (none/low/medium/high) |

---

## 6. 评估运行命令

```bash
# 1. 确保种子数据已导入
cd backend && python -m app.seed

# 2. 运行评估
curl -X POST http://localhost:8000/api/evaluation/run \
  -H "Content-Type: application/json" \
  -d '{}'

# 3. 查看结果 (示例输出)
# {
#   "run_id": "EVAL-20260512-001",
#   "per_case_results": [ ... ],
#   "summary": {
#     "primary_diag_accuracy": ...,
#     "diagnosis_f1_avg": ...,
#     "procedure_f1_avg": ...,
#     "evidence_coverage_avg": ...,
#     "hallucination_rate": ...
#   }
# }

# 4. 前端查看
# 导航到 EvaluationPage 查看可视化结果
```

---

## 7. 评估更新记录

| 日期 | 批次 | 病例数 | Primary Acc | Diag F1 | Proc F1 | Halluc | 备注 |
|------|------|--------|-------------|---------|---------|--------|------|
| 2026-05-12 | Batch 1 | 10 | — | — | — | — | 初始 baseline，待运行 |
| | | | | | | | |

---

## 8. 结论

当前评估体系的 **框架已就绪** (指标定义、评估 API、前端展示)，
但 **数据基础薄弱** (10 cases, 4 科室, 化疗为主)。

试点期间的优先事项:
1. 运行初始评估，填入实际指标值
2. 向医院方收集 ≥ 50 份标注病例
3. 扩大科室和难度覆盖
4. 建立编码员间一致性评估
5. 积累 ≥ 100 份病例后计算统计置信区间
