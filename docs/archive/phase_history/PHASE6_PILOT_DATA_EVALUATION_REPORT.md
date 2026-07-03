# Phase 6 — 试点数据与评估体系报告

**日期**: 2026-05-12
**数据源**: train.xlsx (Sheet1: 1801 条真实出院病历)

---

## 1. Demo Case 清单 (10 条)

| ID | 科室 | 主要诊断 | Gold 主要诊断 | Gold 主要手术 |
|----|------|---------|-------------|-------------|
| DEMO-001 | 肿瘤内科 | Z51.102 | Z51.102 | 99.2503 |
| DEMO-002 | 骨科 | M80.900 | M80.900 | 81.6600x001 |
| DEMO-003 | 乳腺外科 | Z51.102 | Z51.102 | 99.2503 |
| DEMO-004 | 肿瘤内科 | Z51.102 | Z51.102 | 99.2503 |
| DEMO-005 | 乳腺外科 | Z51.102 | Z51.102 | 99.2503 |
| DEMO-006 | 呼吸内科 | R91.x02 | R91.x02 | 32.2400x002 |
| DEMO-007 | 乳腺外科 | Z51.102 | Z51.102 | 99.2503 |
| DEMO-008 | 乳腺外科 | Z51.102 | Z51.102 | 99.2503 |
| DEMO-009 | 呼吸内科 | J98.414 | J98.414 | 33.2403 |
| DEMO-010 | 乳腺外科 | Z51.102 | Z51.102 | 99.2503 |

**分布**: 肿瘤内科(2) + 骨科(1) + 乳腺外科(5) + 呼吸内科(2)

## 2. Gold Case 字段说明

| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| `case_id` | string | 病例唯一标识 | train.xlsx 病案号 |
| `department` | string | 科室 | train.xlsx 推断 |
| `diagnosis_group` | string | 诊断分组 | 入院原因摘要 |
| `gold_diagnosis_codes` | list[string] | 金标准 ICD-10-CN 诊断编码 | train.xlsx col 15-16 |
| `gold_procedure_codes` | list[string] | 金标准 ICD-9-CM-3 手术编码 | train.xlsx col 17-18 |
| `gold_principal_diagnosis` | string | 金标准主要诊断 | train.xlsx col 15 |
| `gold_principal_procedure` | string | 金标准主要手术 | train.xlsx col 17 |
| `difficulty` | enum | 难度 (easy/medium/hard) | 默认 medium |

## 3. 评估指标定义

### Diagnosis Code Precision/Recall

```
Precision = |AI_diags ∩ Gold_diags| / |AI_diags|
Recall    = |AI_diags ∩ Gold_diags| / |Gold_diags|
F1        = 2 × Precision × Recall / (Precision + Recall)
```

### Procedure Code Precision/Recall

```
Precision = |AI_procs ∩ Gold_procs| / |AI_procs|
Recall    = |AI_procs ∩ Gold_procs| / |Gold_procs|
```

### Principal Diagnosis Match

```
Match = (AI_principal_diag == Gold_principal_diag)
Accuracy = |matches| / |total_cases|
```

### Evidence Coverage

```
Coverage = |codes with at least 1 evidence binding| / |total codes suggested|
Target: ≥90%
```

### DRG Group Match

```
Match = (AI_DRG == Expected_DRG)
```
**注**: 当前 demo cases 以化疗/复查为主，DRG 分组不适用。需在真实住院病例上启用。

### Human Review Override Rate

```
Override Rate = |codes where human_decision ≠ AI_suggestion| / |total reviewed codes|
```
**注**: 需人工复核后才能统计。

## 4. 试点验证流程

```
1. 种子数据导入
   $ cd backend && python -m app.seed
   输出: "Demo cases: 10 encounters, 10 gold cases seeded"

2. 运行 Coding Review Workflow
   POST /api/reviews  { "encounter_id": "DEMO-001" }
   → Orchestrator.run_pipeline() → ReviewResponse

3. 验证 Runtime Audit
   GET /api/runtime/summary/{review_id}
   → event_counts, guard_outcomes, state_timeline, warnings

4. 运行 Evaluation
   POST /api/evaluation/run
   → per_case_results with precision/recall per case

5. 检查结果
   - primary_diag_accuracy ≥ 0.5 (baseline)
   - hallucination_rate ≤ 0.3 (baseline)
   - evidence_completeness_avg ≥ 0.5 (baseline)

6. 重复执行 (可多次运行，指标稳定)
   Seed 使用 upsert 逻辑，不会重复创建
```

## 5. 当前不适合宣称的能力

| 能力 | 原因 |
|------|------|
| **DRG 分组准确率** | 当前 demo cases 以化疗(Z51.102)为主，非急性住院病例。DRG 分组依赖完整首页编码组合 |
| **Human Review Override Rate** | 人工复核流程需要真实编码员参与，demo 数据不足以统计 |
| **MCC/CC 分析完整度** | 当前 demo cases 主要诊断较简单，缺少复杂合并症场景 |
| **跨科室泛化** | 10 个 case 集中在 4 个科室，不足以覆盖全科室 |
| **真实 WER 评估** | 前端 STT 不可用 (WebSocket proxy 缺失)，无语音输入评估 |

## 6. 医院试点所需外部数据清单

| 数据类型 | 数量要求 | 优先级 | 说明 |
|----------|---------|--------|------|
| 出院病历首页 | ≥500 份 | P0 | 含完整诊断编码 + 手术编码 + DRG 分组 |
| 金标准编码审核结果 | ≥100 份 | P0 | 由资深编码员复核确认的 gold standard |
| 病历文书 | 与首页关联 | P1 | 入院记录、病程记录、手术记录、出院小结 |
| DRG 分组反馈 | ≥100 份 | P1 | 医保返回的实际入组结果 vs 预期入组 |
| 编码争议案例 | ≥30 份 | P2 | 编码员之间有分歧的案例 (用于评估一致性) |
| 语音病历 (可选) | ≥50 份 | P3 | 用于评估 STT + NLP pipeline 端到端准确率 |

## 7. 验收结果

| 标准 | 结果 |
|------|------|
| 10 demo cases 可导入 | ✅ `python -m app.seed` |
| 10 gold cases 可导入 | ✅ 含 ICD-10-CN + ICD-9-CM-3 编码 |
| evaluation 可运行 | ✅ `POST /api/evaluation/run` |
| 后端测试 154/154 | ✅ |
| CI 不破坏 | ✅ CI workflow 不变 |
| 不新增业务功能 | ✅ 仅种子数据 + 测试 |

## 8. 种子数据命令

```bash
# 导入 demo cases + gold cases
cd backend
python -m app.seed

# 验证
python -c "
from app.data.demo_cases import DEMO_CASES
for c in DEMO_CASES:
    print(f'{c[\"encounter_id\"]}: {c[\"gold_principal_diagnosis\"]} / {c[\"gold_principal_procedure\"]} ({c[\"department\"]})')
"
```
