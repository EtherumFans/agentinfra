# Phase 10 — Gold Case Validation & Pilot Metrics

**日期**: 2026-05-12
**范围**: 金标病例 Schema 扩展 + 批量评估 + 扩展指标

---

## 1. 动机

Phase 9 (Sprints 9A-9E) 构建了完整的临床推理链。Phase 10 用金标数据验证这些能力的实际效果，不再新增认知模块。

之前的 gold case 数据管道存在严重问题：
- `demo_cases.py` 的字段名与 `GoldCase` 模型不匹配
- `seed.py` 使用的字段在模型中不存在
- 评估 API 读取的 `full_case_data` 从未被种子代码填充
- 没有批量评估能力

## 2. Gold Case Schema (修复 + 扩展)

### 修复
- 统一字段命名：`gold_primary_diagnosis` → `expected_principal_diagnosis`
- `gold_secondary_diagnoses` → `expected_secondary_diagnoses`
- `gold_other_procedures` → `expected_procedure_codes`

### 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `expected_drg_group` | Optional[str] | 期望的 DRG 分组 |
| `acceptable_alternatives` | Optional[list[str]] | 可接受的其他编码 (软匹配) |
| `reasoning_expectations` | Optional[list[str]] | 推理期望检查项 |
| `difficulty` | str | easy / medium / hard |
| `specialty` | Optional[str] | 临床专科 |
| `risk_tags` | Optional[list[str]] | drg_sensitive / mcc_cc / rare_disease |

## 3. 扩展评估指标

新增 6 项指标：

| 指标 | 计算方式 | 含义 |
|------|---------|------|
| `primary_diag_soft_accuracy` | 严格匹配 OR 在 `acceptable_alternatives` 中 | 宽松准确率 |
| `secondary_diag_recall_avg` | 平均 secondary code 召回率 | 次要编码完整度 |
| `procedure_recall_avg` | 平均手术编码召回率 | 手术编码完整度 |
| `drg_match_rate` | DRG 分组匹配率 | DRG 预测准确度 |
| `reasoning_score_avg` | CaseReasoningReport 6-section 完整度 | 推理报告质量 |
| `reasoning_expectations_met` | 每例满足的推理期望数 | 推理合规度 |

## 4. 种子数据修复

`seed.py` 修复：
- 正确映射字段名
- 构建 `full_case_data`（含 documents + codes）
- 填充新字段（specialty, risk_tags, reasoning_expectations）

`demo_cases.py` 扩展：
- DEMO-001 新增 `reasoning_expectations`, `acceptable_alternatives`, `risk_tags`, `specialty`, `difficulty`

## 5. 批量评估

`POST /api/evaluation/batch` — 批量评估端点，输出：
- 每例 `CaseReasoningReport`
- 扩展评估指标
- 幻觉编码列表
- 推理期望满足情况

## 6. 修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `schemas/gold_case.py` | 重写 | 字段改名 + 新增 6 个字段 + 扩展 EvaluationResult/Summary |
| `models/gold_case.py` | 重写 | 列名对齐 + 新增 specialty/risk_tags/reasoning_expectations 等 |
| `api/gold_cases.py` | 修改 | 创建 GoldCase 使用新字段名 |
| `api/evaluation.py` | 重写 | 扩展指标计算 + 批量端点 |
| `seed.py` | 修复 | 正确映射字段 + full_case_data |
| `data/demo_cases.py` | 扩展 | DEMO-001 新增 Phase 10 字段 |
| `tests/test_services/test_gold_case_validation.py` | 新增 | 9 tests |
| `docs/PHASE10_GOLD_CASE_VALIDATION.md` | 新增 | 本文档 |

## 7. 测试结果

```
test_gold_case_validation.py: 9 passed, 2 skipped
全量后端测试: 309 passed, 9 skipped, 0 failed
```

## 8. 当前局限

| 局限 | 说明 |
|------|------|
| 金标病例仅 10 例 | 样本不足以计算统计置信区间 |
| `acceptable_alternatives` 仅 DEMO-001 有值 | 其他 9 例尚未标注 |
| `reasoning_expectations` 仅 DEMO-001 有值 | 其他 9 例尚未标注 |
| DRG 分组验证无数据 | 10 例均为化疗/复查病例，DRG 不适用 |
| 批量评估无后台异步 | 当前串行执行，大量病例时需改为异步队列 |
| `full_case_data` 不完整 | 缺少 admission_time/discharge_time |
