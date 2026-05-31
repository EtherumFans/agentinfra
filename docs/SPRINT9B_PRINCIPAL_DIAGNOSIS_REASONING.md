# Sprint 9B — Principal Diagnosis Reasoning

**日期**: 2026-05-12
**范围**: 主诊断推理能力 — 可解释、可审计的编码选择

---

## 1. 动机

之前 `MedicalRecordHomepageExpert` 选择主要诊断的逻辑是纯 score 排序 —— 取排名最高的候选，rationale 是模板字符串 `"Ranked 1st: finding=X, score=Y"`。这无法解释为什么选 A 不选 B，不应用任何编码规则，也不使用已构建的临床时间线。

Sprint 9B 的目标是：让主要诊断选择具有 **推理过程可追溯、编码规则可引用、时间线证据可关联、不确定性可升级** 的临床认知能力。

---

## 2. Reasoning Model

### 2.1 PrincipalDiagnosisReasoning 结构

```
PrincipalDiagnosisReasoning
├── why_selected: str              ← 2–4 句中文解释
├── why_not_selected: list[dict]   ← 对未选中候选的逐一排除原因
│   ├── code
│   ├── name
│   ├── reason
│   └── rule_reference
├── rule_basis: list[str]          ← 引用的编码规则 ID (R001, R013…)
├── timeline_evidence: str         ← 时间线锚点 + 入院原因 + 关键事件
├── confidence_level: str          ← high | medium | low
├── confidence_rationale: str      ← 置信度判断依据
├── disagreement_analysis: dict    ← 与现有编码的分歧分析
│   ├── has_disagreement
│   ├── existing_code / ai_code
│   ├── analysis
│   ├── recommendation            ← accept_ai / accept_existing / needs_senior_review
│   └── rule_basis
└── confidence_escalation: dict    ← 低置信度升级建议
    ├── escalated
    ├── reason
    ├── trigger                    ← score_gap / evidence_conflict / rule_ambiguity
    └── candidates_in_contention
```

### 2.2 示例输出 (DEMO-001 化疗病例)

```json
{
  "why_selected": "选择 Z51.102（恶性肿瘤化学治疗）为主要诊断。本次入院目的为恶性肿瘤化学治疗，根据R013规则，应选择Z51.x编码为主要诊断。对应临床发现：直肠癌术后化疗。",
  "why_not_selected": [
    {
      "code": "C20.x00",
      "name": "直肠恶性肿瘤",
      "reason": "匹配规则R001，但综合评分低于主要诊断",
      "rule_reference": "R001"
    }
  ],
  "rule_basis": ["R001", "R013"],
  "timeline_evidence": "入院原因: 直肠癌术后化疗\n关键历史事件: 2月前: 直肠前切除术; 1月前: 第1周期化疗",
  "confidence_level": "high",
  "confidence_rationale": "与第二名候选分差较大（0.28），选择明确。",
  "disagreement_analysis": {"has_disagreement": false},
  "confidence_escalation": {"escalated": false}
}
```

---

## 3. Diagnosis Prioritization (诊断优先级排序)

纯 score 排序 → **多因子规则加权排序**：

| 因子 | 权重 | 机制 |
|------|------|------|
| LLM/Dictionary score | base | 原有分数 |
| R013 化疗规则 | +0.12 | `admission_reason` 含"化疗/放疗/免疫治疗" → 强制提升 Z51.x |
| R014 透析规则 | +0.10 | 病历含"透析/CRRT"关键词 → 提升 N18 |
| R002 病因优先 | +0.08 | 候选有明确 etiology → 提升病因编码 |
| R015 合并编码 | +0.07 | 检测到合并编码机会 → 提升 |
| R012 多椎体骨折 | +0.06 | 候选含 M80/S32 + 多椎体文本 |
| R001 总则 | +0.02 | 始终应用，微调 tiebreaker |
| certainty penalty | -0.05 | `suspected` → 降权 |
| negation penalty | -0.15 | 否定 → 降权 |

---

## 4. Timeline Interpretation

从已构建的 `ClinicalTimeline` 中提取推理证据：

| 时间线数据 | 推理用途 |
|-----------|---------|
| `anchor_points.admission_date` | 确认本次入院时间，判断住院时长 |
| `anchor_points.surgery_date` | 入院前 vs 入院后手术，判断入院目的 |
| `events[type=chemotherapy]` | 确认化疗周期数，支持 R013 触发 |
| `events[type=surgery]` (relative_time) | "术后X月" 判断手术与本次入院关系 |
| `admission_reason` | 入院原因文字描述 |

---

## 5. Conflict Handling (分歧处理)

当 AI 选择的主要诊断与现有编码不一致时，触发分歧分析：

```
现有编码: C20.x00 (直肠恶性肿瘤)
  vs
AI 推荐:   Z51.102 (恶性肿瘤化学治疗)

分析: AI 推荐 Z51.102 为主要诊断，与现有编码 C20.x00 不一致。
      AI 选择有编码规则支撑（R013,R001），现有编码未匹配到明确规则。

建议: accept_ai (AI 推荐有 R013 规则支撑)
```

三条建议路径：
- `accept_ai` — AI 有更强规则支撑
- `accept_existing` — 现有编码有更强规则支撑
- `needs_senior_review` — 双方规则相当，需编码员裁决

---

## 6. Uncertainty Discipline (不确定性升级)

三级置信度：

| Level | 条件 | 行为 |
|-------|------|------|
| **high** | score ≥ 0.85 + 与第二名 gap > 0.15 + 无分歧 | 自动通过 |
| **medium** | score 0.5–0.85 + gap > 0.10 | 建议编码员复核 |
| **low** | score < 0.5 或 gap ≤ 0.10 或 有分歧 | 强制升级人工裁决 |

升级触发类型：
- `score_gap` — 前两名候选分差过小 (<0.10)
- `evidence_conflict` — 与现有编码分歧 或 置信度不足
- `rule_ambiguity` — 多个规则指向不同候选

---

## 7. 新增/修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/app/schemas/principal_diagnosis_reasoning.py` | 新增 | Reasoning Pydantic model |
| `backend/app/agents/experts/homepage_expert.py` | 重写 | v2: 规则匹配 + 多因子排序 + reasoning 输出 |
| `backend/app/schemas/review.py` | 修改 | PrimaryDiagResult 新增 `reasoning` 字段 |
| `backend/app/models/review.py` | 修改 | CodingReview 新增 `primary_diagnosis_reasoning` JSON 列 |
| `backend/app/services/context_scoper.py` | 修改 | HomepageExpert scope 新增 timeline, admission_reason |
| `backend/app/agents/orchestrator.py` | 修改 | 传递 admission_reason + 捕获 primary_diagnosis_reasoning |
| `backend/app/api/reviews.py` | 修改 | _build_review_response 传递 reasoning + CodingReview 构造函数 |
| `backend/tests/test_services/test_principal_diagnosis_reasoning.py` | 新增 | 40 个测试用例 |

---

## 8. 测试结果

```
tests/test_services/test_principal_diagnosis_reasoning.py: 40 passed, 1 skipped
全量后端测试: 209 passed, 3 skipped, 0 failed
```

测试覆盖：
- 规则匹配 (8 tests): chemo/dialysis/spine context 检测, R001/R002/R012/R013/R014 匹配
- 调整分数 (6 tests): rule bonus, baseline, penalty, cap
- why-selected (3 tests): R013 reasoning, R001-only, finding inclusion
- why-not-selected (3 tests): reasons, unspecific flag, cap at 3
- 分歧分析 (3 tests): no disagreement, empty existing, detected disagreement
- 置信度评估 (5 tests): high/medium/low, disagreement escalation, close scores
- 时间线证据 (3 tests): available, unavailable, with events
- Schema 往返 (2 tests): full reasoning, disagreement schema
- 全专家运行 (5 tests): chemo case, no-chemo case, why_not output, disagreement escalation, empty candidates
- Pipeline 集成 (1 test): API response includes reasoning

---

## 9. 当前局限

| 局限 | 说明 | 改善方向 |
|------|------|---------|
| 规则触发为关键词匹配 | 非 LLM 理解，可能漏掉隐式化疗/透析场景 | 后续可引入 LLM-based 规则分类 |
| 时间线依赖 LLM 提取质量 | 时间线不完整时推理证据不足 | 增强时间线提取的 recall |
| 合并编码检测不完整 | 仅检测 E11+N18 → E11.2 等已知模式 | 导入 ICD-10 合并编码映射表 |
| R001 资源消耗判断粗糙 | 当前仅用入院原因 + 事件序列推断 | 需引入费用数据或住院天数进行量化 |
| 置信度阈值硬编码 | score_threshold=0.85, gap=0.15 等来自经验 | 需要基于评估数据校准 |
