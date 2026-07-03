# Phase 11B — Gold Case Template & Inter-Rater Agreement

**日期**: 2026-05-12
**范围**: 金标病例模板生成、导入校验、编码员间一致性评估

---

## 1. Gold Case Template Generator

### 用途
为医院编码员生成可填写的金标病例模板，支持 JSON 和 Markdown 两种输出格式。

### 模板结构
```
├── _instructions              # 填写说明
├── case_metadata              # 科室、诊断分组、专科、难度、入院原因、病历文档
├── original_codes             # 医院原始编码
├── gold_codes                 # 金标准编码（由专家填写）
│   ├── expected_principal_diagnosis
│   ├── expected_principal_procedure
│   ├── expected_secondary_diagnoses
│   ├── expected_procedure_codes
│   └── expected_drg_group
├── acceptable_alternatives    # 可接受的其他编码
├── reasoning_expectations     # AI 推理期望
├── evidence_spans             # 证据标注
└── known_issues               # 已知问题（缺失/无支撑/文书缺口）
```

### 使用
```python
from app.services.gold_case_template import generate_gold_case_template

# JSON 格式
template = generate_gold_case_template(department="骨科")

# Markdown 格式（适合打印/手动填写）
md = generate_gold_case_template(department="骨科", output_format="markdown")
```

## 2. Gold Case Validator

### 校验规则
| 检查项 | 类型 | 说明 |
|--------|------|------|
| 必填字段 | error | department, expected_principal_diagnosis |
| ICD-10 格式 | warning | `[A-Z]\d\d(\.\d+[xX]?\d*\|[xX]\d+)?` |
| ICD-9-CM-3 格式 | warning | `\d\d\.\d+[xX]?\d*` |
| 难度值 | warning | easy/medium/hard |
| 重复编码 | warning | 同一编码不能同时出现在主诊断和次要诊断 |
| 替代编码格式 | warning | acceptable_alternatives 也必须是合法 ICD-10 |

### 导入流程
1. 生成模板 → 编码员填写 → `validate_gold_case()` → `import_gold_case()` → `GoldCaseCreate` → 数据库

## 3. Inter-Rater Agreement

### 指标
| 指标 | 适用场景 | 说明 |
|------|---------|------|
| **Percent Agreement** | 简单一致性 | 两位编码员编码完全相同的比例 |
| **Cohen's Kappa** | 2 人一致性 | 排除随机一致的修正一致性 |
| **Fleiss' Kappa** | ≥3 人一致性 | 多名编码员间的一致性 |
| **Pairwise Matrix** | 多人比较 | 每对编码员的 Kappa 矩阵 |

### Kappa 解释标准
| Kappa | 一致性等级 |
|-------|----------|
| ≥ 0.81 | 几乎完全一致 |
| 0.61–0.80 | 高度一致 |
| 0.41–0.60 | 中等一致 |
| 0.21–0.40 | 一般一致 |
| 0.00–0.20 | 轻微一致 |
| < 0.00 | 低于随机 |

### 使用
```python
from app.services.inter_rater import compute_inter_rater, compute_multi_rater_agreement

# 两人一致性
result = compute_inter_rater(
    ["Z51.102", "C20.x00", "M80.900"],
    ["Z51.102", "C20.x00", "M80.000"],
)
# result = {percent_agreement: 0.67, cohens_kappa: 0.57, interpretation: "中等一致"}

# 多人一致性
result = compute_multi_rater_agreement({
    "coder_a": ["Z51.102", "C20.x00"],
    "coder_b": ["Z51.102", "C20.x00"],
    "coder_c": ["Z51.102", "M80.900"],
})
# result = {avg_cohens_kappa: 0.75, fleiss_kappa: 0.72, ...}
```

## 4. 新增文件

| 文件 | 说明 |
|------|------|
| `services/gold_case_template.py` | 模板生成 + 校验器 + 导入器 |
| `services/inter_rater.py` | Cohen's Kappa + Fleiss' Kappa + 多人矩阵 |
| `tests/test_services/test_gold_case_template.py` | 16 tests |
| `tests/test_services/test_inter_rater.py` | 18 tests |
| `docs/PHASE11B_GOLD_CASE_QUALITY.md` | 本文档 |

## 5. 测试结果

```
新增: 34 passed
全量: 443 passed, 9 skipped, 0 failed
```
