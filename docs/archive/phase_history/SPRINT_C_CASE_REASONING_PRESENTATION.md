# Sprint C — Case Reasoning Presentation

**日期**: 2026-05-12
**范围**: 将 reasoning output 从技术输出升级为高级编码员临床审核解释

---

## 1. 改动前后对比

| 维度 | 之前 | 之后 |
|------|------|------|
| 推理展示 | JSON 字段拼接 | **临床审核笔记** (叙事风格) |
| 证据展示 | 离散 card | **证据依据** (按来源分组叙事) |
| 最终建议 | 无 | **最终审核建议** (确认/复核/升级 + 风险因子列表) |
| Timeline→Diagnosis | 无关联 | **疾病演化叙事** (就诊→治疗→主诊断选择) |
| 语言风格 | 数据聚合 | **中文临床语言** (像编码员审核笔记) |

## 2. 三个叙事组件

### 2.1 Clinical Narrative (临床审核笔记)

```
患者因「直肠癌术后化疗」就诊于肿瘤内科。
临床经过：2025年1月15日 直肠前切除术；2025年2月18日 奥沙利铂+卡培他滨化疗。
综合入院目的、治疗过程与出院诊断，当前主要诊断确定为Z51.102（恶性肿瘤化学治疗）。
本次入院目的为恶性肿瘤化学治疗，根据R013规则，应选择Z51.x编码为主要诊断。
本次选择依据编码规则：R013、R001。
```

### 2.2 Evidence Story (证据依据)

```
当前编码建议主要基于以下2类证据来源：出院小结、现病史。
  · 出院小结：出院诊断：直肠恶性肿瘤化疗
  · 现病史：为行术后辅助化疗入院
```

### 2.3 Final Recommendation (最终审核建议)

```
【建议确认】当前主诊断选择明确，证据充分，建议编码员确认。
证据整体质量良好（平均强度0.75）。
```

或：

```
【建议高级审核】存在以下需要高级编码员关注的风险因素：
  · 与现有编码存在2处分歧，其中1处影响DRG分组。
  · 2个编码被标记为需升级审核（ESCALATE），需高级编码员裁决。
  · 3个编码证据不足，可能需要补充病历资料。
DRG提醒：编码变更可能影响DRG入组，请确认分组结果后再提交。
证据整体质量偏低（平均强度0.35），建议补充关键病历文书。
```

## 4. 实现方式

- **确定性生成**: `_build_clinical_narrative()`, `_build_evidence_story()`, `_build_final_recommendation()` — 纯 Python 字符串构建
- **无 LLM 调用**: 不新增认知模块
- **中文优先**: 所有输出为中文临床语言

## 5. 修改文件

| 文件 | 改动 |
|------|------|
| `schemas/case_reasoning.py` | 新增 `clinical_narrative`, `evidence_story`, `final_recommendation` 字段 |
| `services/reasoning_report_builder.py` | 新增 3 个叙事 builder 函数 (~130 行) |
| `pages/CodingWorkbenchPage.tsx` | Reasoning tab 渲染叙事 + 建议面板 |
| `tests/test_services/test_clinical_narrative.py` | 10 tests |
| `docs/SPRINT_C_CASE_REASONING_PRESENTATION.md` | 本文档 |

## 6. 测试结果

```
test_clinical_narrative.py: 10 passed
全量后端: 491 passed, 9 skipped, 0 failed
```

## 7. 当前未解决问题

| 问题 | 说明 |
|------|------|
| 叙事模板化 | 当前为 Python 字符串拼接，非 LLM 生成的自然语言 |
| 疾病演化依赖于时间线质量 | 时间线不完整时叙事可能简单 |
| 证据故事未关联编码 | evidence_story 按来源分组但不按编码分组 |
| 最终建议阈值硬编码 | confidence_level 判断阈值来自经验 |
