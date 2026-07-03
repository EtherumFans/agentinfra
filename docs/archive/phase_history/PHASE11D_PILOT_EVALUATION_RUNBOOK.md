# Phase 11D — Pilot Evaluation Runbook

**日期**: 2026-05-12
**范围**: 医院试点现场可执行的标准操作流程

---

## 1. 试点前准备

### 环境要求
- [ ] Python 3.12+
- [ ] iCoDer 后端已部署
- [ ] 数据库已初始化
- [ ] LLM 服务可用 (DeepSeek 或 LM Studio)
- [ ] `python -m app.seed` 已执行 (导入 10 demo cases)

### 文件准备
- [ ] 云端 Tenant 数据接收清单 (`docs/cloud/CLOUD_INTAKE_TEMPLATE.md`)
- [ ] 金标病例模板 (通过 CLI 生成)
- [ ] 已知限制说明 (`PILOT_KNOWN_LIMITATIONS.md`)
- [ ] 验收清单 (`PILOT_ACCEPTANCE_CHECKLIST.md`)

## 2. 数据接收

### 接收内容
1. 脱敏病案首页 (≥ 50 份)
2. 出院小结 (≥ 20 份)
3. 编码员标注的金标病例

### 接收后动作
```bash
# 1. 生成金标模板分发给编码员
python scripts/pilot_eval_runbook.py generate-template --department <科室> --output gold_template.json

# 2. 编码员填写后，收集所有 JSON/CSV 文件到 data/pilot_input/
```

## 3. 模板校验

```bash
# Dry-run 校验（不导入）
python scripts/pilot_eval_runbook.py validate-gold data/pilot_input/hospital_gold.json

# 校验 CSV 格式
python scripts/pilot_eval_runbook.py validate-gold data/pilot_input/hospital_gold.csv

# 预期输出：
# ✅ 行000 [T001] — ok
# ⚠️ 行001 [T002] — warning: expected_principal_procedure 'abc' invalid ICD-9-CM-3 format
# ❌ 行002 [T003] — error: Missing required field: expected_principal_diagnosis
```

### 常见错误
| 错误 | 原因 | 修正 |
|------|------|------|
| Missing required field | 必填字段为空 | 补充 expected_principal_diagnosis |
| invalid ICD-10 format | 编码格式不符合规范 | 检查编码格式：`[A-Z]XX.XXX` |
| invalid ICD-9-CM-3 format | 手术编码格式错误 | 检查格式：`XX.XXXX` |
| duplicate code | 主诊断和其他诊断重复 | 从其他诊断中移除重复编码 |

## 4. 导入

```bash
# Dry-run 预导入
python scripts/pilot_eval_runbook.py import-gold data/pilot_input/hospital_gold.json --dry-run

# 正式导入
python scripts/pilot_eval_runbook.py import-gold data/pilot_input/hospital_gold.json

# 更新已存在的记录
python scripts/pilot_eval_runbook.py import-gold data/pilot_input/hospital_gold.json --upsert
```

## 5. 仲裁

当多位编码员对同一病例标注不一致时：

```python
from app.services.gold_case_importer import AdjudicationRecord, AdjudicationState

rec = AdjudicationRecord("GC-001")
rec.transition(AdjudicationState.IN_REVIEW)
rec.add_review("coder_a", {"expected_principal_diagnosis": "Z51.102"})
rec.add_review("coder_b", {"expected_principal_diagnosis": "C20.x00"})

if rec.check_agreement():
    rec.transition(AdjudicationState.APPROVED)
else:
    rec.transition(AdjudicationState.DISPUTED)
    # 高级编码员裁决
    rec.transition(AdjudicationState.ADJUDICATED)

rec.final_codes = {"expected_principal_diagnosis": "Z51.102"}
rec.promote_to_final("v1.0")
```

## 6. Final Gold 确认

晋升条件：
- 全部必填字段已填充
- 无校验错误
- ≥ 2 位审核员同意（或 1 + 仲裁员）
- final_gold_version 已标记

## 7. 批量运行评估

```bash
# 运行评估
python scripts/pilot_eval_runbook.py run-evaluation --output pilot_results.json
```

输出包含：
- 每例 AI vs Gold 主诊断对比
- 主诊断准确率
- CaseReasoningReport 完整度评分

## 8. 输出报告

```bash
# 生成报告框架
python scripts/pilot_eval_runbook.py export-report --pilot_name "XX医院试点" --output final_report.json
```

将 run-evaluation 的结果填入报告各 section。

## 9. 常见错误处理

| 症状 | 可能原因 | 解决 |
|------|---------|------|
| `ModuleNotFoundError` | 未在 backend 目录执行 | `cd backend` |
| 数据库为空 | 未执行 seed | `python -m app.seed` |
| LLM 调用超时 | LLM 服务不可用 | 检查 LLM 配置 |
| CSV 乱码 | 文件编码不是 UTF-8 | 另存为 UTF-8 BOM |
| 导入 0 条 | 格式不匹配 | 检查 JSON 是否是数组 |
