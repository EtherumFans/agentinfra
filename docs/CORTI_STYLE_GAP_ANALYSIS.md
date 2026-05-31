# Corti-Style Gap Analysis — iCoDer 产品体验差距评估

**日期**: 2026-05-12
**评分**: 1=不存在, 2=仅有后端, 3=后端完整但前端弱, 4=接近对标, 5=Corti-style 体验

---

## 1. Case Intake & Workflow Initiation

| 评分 | **3/5** |
|------|---------|
| **当前证据** | CodingWorkbenchPage 有病历搜索 + Run Review 按钮；支持同步/异步模式；seed 导入 10 demo cases |
| **差距** | 病历选择器仅支持 ID 搜索，无按科室/日期/状态筛选；无批量导入前端；无"最近病历"快速入口 |
| **修复建议** | 添加科室筛选 + 日期范围 + 批量导入按钮；添加"最近处理"快速入口 |
| **优先级** | P1 |

---

## 2. Evidence-First UX

| 评分 | **2/5** |
|------|---------|
| **当前证据** | Evidence tab 展示 diagnosis_facts + procedure_facts 表；Evidence Ranking (9C) 在 backend 产生 top_supporting/weak/conflicting 分类 |
| **差距** | Frontend **未消费** evidence_ranking 输出 (top/weak/conflicting 分类在前端不可见)；证据未按强度视觉区分（颜色/图标）；点击证据不跳转到原文位置；无 evidence → code → rationale 的连续展示 |
| **修复建议** | Evidence tab 改为三区布局（强/弱/冲突）；添加强度颜色编码；证据点击→原文高亮；每个证据下展示关联的候选编码 |
| **优先级** | **P0** |

---

## 3. Clinical Reasoning Depth

| 评分 | **3/5** |
|------|---------|
| **当前证据** | Timeline (9A) 已构建并传递到 homepage；Principal Diagnosis Reasoning (9B) 输出 why_selected/why_not_selected/rule_basis；Disagreement (9D) 输出 8-type taxonomy |
| **差距** | Timeline **未在前端展示**；why_selected/why_not_selected 仅在 JSON 中，前端 report tab 只有简单的 markdown；rule_basis 未在前端渲染为可点击的规则引用；clinical timeline 不可视化 |
| **修复建议** | 前端新增 Timeline 展示（时间轴组件）；why_selected/why_not_selected 渲染为独立卡片；rule_basis 链接到规则详情 |
| **优先级** | **P0** |

---

## 4. Coding Candidate Experience

| 评分 | **2/5** |
|------|---------|
| **当前证据** | Candidates tab 展示表格（code/name/score/status）；Confidence Calibration (9E) 输出 routing_decision (auto/review/escalate) |
| **差距** | 候选编码未分组（主诊断/次要诊断/手术）；未展示 confidence 颜色编码；未展示 evidence coverage 每候选；未展示 DRG impact badge；未展示 routing tier badge；前端**未消费** routing_decision |
| **修复建议** | 候选编码卡片化（非表格）；confidence 绿/黄/红颜色条；每个候选显示证据数量 + DRG impact badge + routing tier badge |
| **优先级** | **P0** |

---

## 5. Human Review Ergonomics

| 评分 | **3/5** |
|------|---------|
| **当前证据** | CaseReviewPage 支持 Approve/Reject/Modify；有 Decision Summary shield 面板；代码 candidate 有 human_decision 状态 |
| **差距** | 无键盘快捷键 (A=Approve, R=Reject, M=Modify)；无批量 approve/reject；无 review notes 输入框；修正原因无标准化选项（自由文本）；无"下一个未审核"快速跳转 |
| **修复建议** | 键盘快捷键；批量操作 checkbox + "全部确认"；review notes 输入；修正原因下拉（编码错误/特异性不足/规则违反/其他）；"跳转到下一个"按钮 |
| **优先级** | P1 |

---

## 6. Disagreement & Correction Loop

| 评分 | **3/5** |
|------|---------|
| **当前证据** | Disagreement Analyzer (9D) 在后端产生 8-type taxonomy + correction model + DRG sensitivity；Gold evolution tracking；Inter-rater agreement (11B) |
| **差距** | 分歧分析**未在前端展示**；AI vs Gold 对比不可见；修正记录未沉淀为 learnable 反馈；无"上次修正原因"记忆 |
| **修复建议** | CaseReview 展示 AI vs Gold 对比面板；修正记录持久化并展示"常见修正模式"；learnable=True 的修正标记 |
| **优先级** | P1 |

---

## 7. Confidence & Routing

| 评分 | **3/5** |
|------|---------|
| **当前证据** | Confidence Calibrator (9E) 在后端产生 3-tier routing + 6 override rules + routing explanation；主要诊断禁止 AUTO |
| **差距** | Routing 决策**未在前端展示**；编码员看不到为什么某个编码被 REVIEW/ESCALATE；无 routing explanation 可见；auto/review/escalate 无颜色区分 |
| **修复建议** | 每个候选编码旁显示 routing badge (绿色AUTO/黄色REVIEW/红色ESCALATE)；hover 显示 routing explanation；主要诊断显式标记 "必须人工复核" |
| **优先级** | P1 |

---

## 8. Auditability

| 评分 | **3/5** |
|------|---------|
| **当前证据** | Runtime Audit Chain (不可篡改)；Audit tab 5 个子面板 (摘要/状态流转/警告/事件分布/决策)；Export JSON 按钮 |
| **差距** | Export 仅 JSON（无 Markdown/PDF）；Audit 内容过于技术化（event_type/actor/payload），非编码员可读；无"一键导出报告"；CaseReasoningReport 未包含在 Export 中 |
| **修复建议** | Export 增加 Markdown 格式；Audit tab 增加"编码员摘要"视图（中文、非技术）；Export 包含 CaseReasoningReport |
| **优先级** | P1 |

---

## 9. Demo / Pilot Readiness

| 评分 | **4/5** |
|------|---------|
| **当前证据** | 10 分钟演示脚本 (PILOT_DEMO_SCRIPT.md)；Pilot Runbook CLI (Phase 11D)；验收清单 + 已知限制 + 问题模板 + 数据申请模板 (Phase 7)；Gold case 模板 + 导入 + 仲裁 + 一致性 (Phase 11B-11C)；481 后端测试 + 100 regression |
| **差距** | Pilot 需要在真实医院数据上运行过至少 1 次；50-case gold 尚未验证；前端在无 LLM 时不友好（静默 loading） |
| **修复建议** | 执行至少 1 轮 dry-run；前端 fallback 状态提示；Demo 前检查清单 checklist |
| **优先级** | P2 |

---

## 10. Product Feel — 编码员副驾驶感

| 评分 | **2/5** |
|------|---------|
| **当前证据** | 功能齐全的后端推理引擎；CodingWorkbench 有基本布局；CaseReview 有复核流程 |
| **差距** | 前端更像"开发者工具"而非"编码员驾驶舱"；表格化展示而非卡片化；大量 JSON/技术术语暴露；无 Corti-style "clinical cockpit"感；颜色/排版/间距未统一为临床产品风格；大量冷冰冰的数据面板，缺少"助手感" |
| **修复建议** | 参考 Medical Scribe 类产品（不抄袭 Corti 视觉）；减少表格、增加卡片；中文术语替代技术术语（"候选编码"→"编码建议"，"confidence"→"可信度"）；增加编码员引导性文案；统一 clinical 色调（蓝/白/灰） |
| **优先级** | **P0** |

---

## 评分总览

| 维度 | 评分 | 优先级 |
|------|------|--------|
| 1. Case Intake & Workflow | 3/5 | P1 |
| 2. **Evidence-First UX** | **2/5** | **P0** |
| 3. **Clinical Reasoning Depth** | **3/5** | **P0** |
| 4. **Coding Candidate Experience** | **2/5** | **P0** |
| 5. Human Review Ergonomics | 3/5 | P1 |
| 6. Disagreement & Correction | 3/5 | P1 |
| 7. Confidence & Routing | 3/5 | P1 |
| 8. Auditability | 3/5 | P1 |
| 9. Demo / Pilot Readiness | 4/5 | P2 |
| 10. **Product Feel** | **2/5** | **P0** |
| **平均** | **2.8/5** | — |

---

## Top 10 Gaps (按严重度)

1. **Evidence-First UX 前端未实现** — 证据强/弱/冲突分类在 backend 但前端不可见
2. **Coding Candidate 展示粗糙** — 表格化、无 confidence 颜色、无 routing badge
3. **Product Feel 偏开发者** — 缺少编码员副驾驶感
4. **Timeline 前端不可见** — 临床时间线构建了但编码员看不到
5. **Clinical Reasoning 展示不足** — why_selected/why_not_selected 仅在 JSON 中
6. **Routing Decisions 前端未消费** — AUTO/REVIEW/ESCALATE 在 backend 但前端不展示
7. **Disagreement Analysis 前端未展示** — AI vs Gold 对比不可见
8. **无键盘快捷键** — 复核效率低
9. **Export 仅 JSON** — 无编码员可读格式
10. **Human Readable Summary 未在前端渲染** — CaseReasoningReport 的 human_readable_summary 未在 UI 展示
