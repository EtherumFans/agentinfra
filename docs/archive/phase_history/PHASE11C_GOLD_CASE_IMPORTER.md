# Phase 11C — Gold Case Importer & Adjudication

**日期**: 2026-05-12
**范围**: 金标病例批量导入、行级校验、仲裁状态机、Final Gold 晋升

---

## 1. Gold Case Importer

### 支持格式
- **JSON**: `[{...}, {...}]` 数组或 `{"cases": [{...}]}` 包装
- **CSV**: 标准 CSV (UTF-8 BOM 兼容)

### 三种模式
| 模式 | 说明 |
|------|------|
| `dry_run` | 校验但不导入，输出完整错误报告 |
| `validation_only` | 仅校验，忽略所有导入逻辑 |
| `import` | 校验通过后执行导入 |

### Upsert 支持
- `upsert=False`: 已存在的 encounter_id 跳过
- `upsert=True`: 更新已存在的记录

### 行级错误报告
每行输出独立状态：
```json
{
  "row_index": 0,
  "encounter_id": "T001",
  "status": "ok",
  "errors": [],
  "warnings": ["expected_principal_procedure 'abc' invalid ICD-9-CM-3 format"]
}
```

### Import Summary
```json
{
  "total_rows": 50,
  "imported": 45,
  "skipped": 3,
  "errors": 2,
  "warnings": 8,
  "row_results": [...],
  "adjudication_needed": [{"encounter_id": "T042", "reviewer1": "coder_a", "reviewer2": "coder_b"}]
}
```

## 2. Adjudication State Machine

```
PENDING ──→ IN_REVIEW ──→ APPROVED ──→ FINAL
                │   │                      ↑
                │   └──→ DISPUTED ──→ ADJUDICATED ──→ RESOLVED ──┘
                │                                │
                └────────────────────────────────┘
```

| 状态 | 含义 |
|------|------|
| `PENDING` | 已提交，等待审核 |
| `IN_REVIEW` | 审核中 |
| `APPROVED` | 全部审核员一致通过 |
| `DISPUTED` | 审核员意见不一致 |
| `ADJUDICATED` | 高级仲裁员已裁决 |
| `RESOLVED` | 争议已解决 |
| `FINAL` | 已晋升为最终金标 |

## 3. Final Gold Promotion Rules

从 `APPROVED` 或 `ADJUDICATED` 晋升到 `FINAL` 需满足：

1. 全部必填字段已填充
2. 无残余校验错误
3. 至少 2 位审核员同意（或 1 位 + 仲裁员裁决）
4. `final_codes` 已设置
5. `final_gold_version` 已标记

## 4. 使用方式

```python
from app.services.gold_case_importer import (
    import_gold_cases_from_data, import_gold_cases_from_string,
    import_gold_cases_from_file, AdjudicationRecord, AdjudicationState,
)

# Dry-run 校验
result = import_gold_cases_from_file("hospital_gold.json", mode="dry_run")
print(f"Errors: {result['errors']}, Warnings: {result['warnings']}")

# 正式导入
result = import_gold_cases_from_file("hospital_gold.json", mode="import", upsert=True)

# CSV导入
result = import_gold_cases_from_string(csv_content, file_format="csv", mode="import")

# 仲裁流程
rec = AdjudicationRecord("GC-001")
rec.transition(AdjudicationState.IN_REVIEW)
rec.add_review("coder_a", {"expected_principal_diagnosis": "Z51.102"})
rec.add_review("coder_b", {"expected_principal_diagnosis": "C20.x00"})
if not rec.check_agreement():
    rec.transition(AdjudicationState.DISPUTED)
    rec.transition(AdjudicationState.ADJUDICATED)
rec.final_codes = {"expected_principal_diagnosis": "Z51.102"}
rec.promote_to_final("v1.0")
```

## 5. 新增文件

| 文件 | 说明 |
|------|------|
| `services/gold_case_importer.py` | Importer (CSV/JSON) + Adjudication state machine + Final promotion |
| `tests/test_services/test_gold_case_importer.py` | 31 tests |
| `docs/PHASE11C_GOLD_CASE_IMPORTER.md` | 本文档 |

## 6. 测试结果

```
test_gold_case_importer.py: 31 passed
全量: 474 passed, 9 skipped, 0 failed
```
