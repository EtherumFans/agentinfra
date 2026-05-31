# Case Reasoning Report — 临床认知链整合

**日期**: 2026-05-12
**范围**: 将 Sprint 9A-9E 的临床认知能力整合为统一、可审计、可演示的推理报告

---

## 1. 动机

Sprints 9A-9E 构建了 5 个独立的临床认知能力：

| Sprint | 能力 | 输出 |
|--------|------|------|
| 9A | Clinical Timeline Reconstruction | 时间线事件 + 锚点 |
| 9B | Principal Diagnosis Reasoning | 主诊断选择推理 + 规则引用 + 置信度 |
| 9C | Evidence Ranking & Support Validation | 证据强度排名 + 无支撑/冲突检测 |
| 9D | Disagreement Reasoning | 分歧分类 + 修正模型 + DRG 敏感性 |
| 9E | Confidence Calibration & Selective Automation | 多源校准 + 3-tier 分流 |

每个 Sprint 独立输出结构化数据到 pipeline context，但没有统一的报告把完整的临床推理链条串起来。

**Case Reasoning Report** 是将这 5 条认知链合成为一个完整、可读、可审计的报告。

---

## 2. Report Structure

### 2.1 Case Overview
```
encounter_id, department, admission_reason, doc_count, generated_at
```

### 2.2 Clinical Timeline (9A)
```
summary, anchor_count, event_count, unresolved_count, key_events (top 5)
```

### 2.3 Evidence Assessment (9C)
```
top_count, weak_count, conflicting_count, unsupported_code_count
strength_avg, unsupported_codes (top 5), conflicts (top 3)
```

### 2.4 Principal Diagnosis (9B)
```
code, name, why_selected, why_not_selected (reasons), rule_basis, confidence_level, timeline_evidence
```

### 2.5 Disagreement Analysis (9D)
```
has_disagreement, correction_count, drg_impacted_count
type_distribution, top_corrections (top 5)
```

### 2.6 Confidence Routing (9E)
```
auto_count, review_count, escalate_count, auto_accept_rate, override_count
```

### 2.7 Audit Summary
```
total_events, state_path, gate_outcomes, warnings
```

### 2.8 Human-Readable Summary
3-5 段中文自然语言摘要，讲述完整的临床推理故事。

---

## 3. Human-Readable Summary 示例

> 患者就诊于肿瘤内科，入院原因：直肠癌术后化疗。
>
> 临床经过：直肠癌术后2月余，行奥沙利铂+卡培他滨方案化疗。
>
> 主要诊断选择为Z51.102（恶性肿瘤化学治疗），高置信。本次入院目的为恶性肿瘤化学治疗，根据R013规则，应选择Z51.x编码为主要诊断。
>
> 证据评估：2条强证据支持，0个编码证据不足。证据平均强度0.75。
>
> 自动化分流：AUTO=0, REVIEW=1, ESCALATE=0。主要诊断需人工复核。

---

## 4. 实现方式

- **Builder function**: `services/reasoning_report_builder.py` — 从 pipeline context 读取所有认知输出，组装为 `CaseReasoningReport`
- **无新 pipeline step** — builder 在 Step 9 Report Generation 之后作为后处理聚合运行
- **无 LLM 调用** — 报告组装完全是确定性的数据聚合
- **Runtime audit**: `case_reasoning_report_built` 事件记录报告生成

---

## 5. 新增/修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `schemas/case_reasoning.py` | 新增 | CaseReasoningReport 统一 schema |
| `services/reasoning_report_builder.py` | 新增 | build_case_reasoning_report() builder |
| `tests/test_services/test_case_reasoning_report.py` | 新增 | 12 tests |
| `agents/orchestrator.py` | 修改 | 调用 builder + 捕获输出 + audit |
| `docs/CASE_REASONING_REPORT.md` | 新增 | 本文档 |

---

## 6. 测试结果

```
test_case_reasoning_report.py: 12 passed, 1 skipped
全量后端测试: 300 passed, 7 skipped, 0 failed
```

---

## 7. 当前局限

| 局限 | 说明 |
|------|------|
| audit_summary 未接入 Runtime | 当前 total_events/state_path 为占位值，需从 Runtime 实时读取 |
| human_readable_summary 为模板拼接 | 非 LLM 生成的自然语言，是结构化数据拼接 |
| 报告为 JSON 结构 | 无 Markdown/HTML/PDF 渲染，需要时可由前端或 ReportExpert 转换 |
| 无持久化 | case_reasoning_report 当前只在 API 响应中，未存入数据库 |
