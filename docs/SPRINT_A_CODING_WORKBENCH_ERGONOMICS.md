# Sprint A — Coding Workbench Ergonomics

**日期**: 2026-05-12
**范围**: CodingWorkbenchPage 从“开发者工具”升级为 Corti-style 编码员工作台

---

## 1. 改动前后对比

| 维度 | 之前 | 之后 |
|------|------|------|
| 标签数 | 4 (Evidence/Candidates/Report/DRG+Audit) | **7** (Evidence/Timeline/Candidates/Reasoning/Report/DRG/Audit) |
| Evidence 展示 | 扁平列表 (evidences array) | **三区布局** (强证据/弱证据/冲突) + 颜色编码 |
| Candidate 展示 | 表格化列表 | **卡片** + confidence 进度条 + routing tier badge |
| Timeline | 后端有，前端无 | **时间轴组件**，垂直展示临床事件 |
| Reasoning | 后端有，前端仅 markdown | **独立 Tab**：why_selected/why_not_selected/rule_basis/confidence 卡片 |
| Routing | 后端有，前端无 | **每个候选旁**显示 AUTO/REVIEW/ESCALATE badge |
| Human Summary | 后端有，前端无 | **Header 下方蓝色摘要条** |
| 临床感 | 开发者工具 (英文术语、JSON暴露) | 编码员工作台 (中文术语、引导文案) |
| 后端改动 | — | **0 行后端代码改动** |

## 2. 组件结构

```
CodingWorkbenchPage
├── Header
│   ├── 病历信息 (科室·入院原因·文档数)
│   ├── 病历搜索 / 运行审核 / 异步切换 / 人工复核 / 导出
│   ├── Runtime 状态标签
│   └── 临床摘要条 (CaseReasoningReport.human_readable_summary)
├── Left Panel (18%)
│   └── 病历原文 (文档列表 + 内容)
└── Right Panel (82%)
    ├── Tab Bar (7 tabs)
    └── Tab Content
        ├── Evidence   → 强证据 / 弱证据 / 冲突证据 / 证据不足编码
        ├── Timeline   → 垂直时间轴 + 摘要
        ├── Candidates → 编码卡片 (status icon + code + routing badge + confidence bar)
        ├── Reasoning  → why_selected + why_not_selected + confidence + timeline evidence
        ├── Report     → Markdown
        ├── DRG        → DRG分组 / 特异性风险 / 编码不匹配
        └── Audit      → 审计事件 / 状态流转 / 警告
```

## 3. Evidence-First UX

- 强证据 (emerald 绿色): `evidence_ranking.top_supporting_evidence`
- 弱证据 (amber 黄色): `evidence_ranking.weak_evidence`
- 冲突证据 (red 红色): `evidence_ranking.conflicting_evidence`
- 证据不足编码 (red 标签): `evidence_ranking.unsupported_codes`
- Fallback: 如果 evidence_ranking 为空，回退到旧的 evidences 数组

## 4. Candidate Card Design

每个编码建议卡片包含:
- 状态图标 (supported/unsupported/needs_review)
- 编码 + 编码系统
- **Routing tier badge** (绿=AUTO / 黄=REVIEW / 红=ESCALATE)
- 证据状态标签 (有证据/无证据/需复核)
- 编码名称 + 临床发现
- **Confidence 进度条** (颜色: 绿≥0.80 / 黄≥0.50 / 红<0.50)
- 规则检查结果
- Routing override reason (如有)

## 5. Timeline Presentation

- 垂直时间轴 (左边框 + 圆点)
- 每个事件: event_type 标签 + timestamp + relative_time + description + source_document
- 底部时间线摘要

## 6. Clinical Cockpit Principles

- **中文优先**: 所有 UI 文本为中文
- **颜色编码**: 绿(好/通过)、黄(需关注)、红(问题)
- **引导文案**: 空状态显示“选择病历后点击「运行审核」”
- **减少技术暴露**: 不直接展示 JSON、英文 event_type
- **信息层级**: 摘要→详情→原始数据

## 7. 当前仍未解决的问题

| 问题 | 说明 |
|------|------|
| 无键盘快捷键 | 复核效率优化留到 Sprint B |
| Evidence-click-to-source | 点击证据不跳转到病历原文位置 |
| CaseReviewPage 未同步更新 | 复核页面仍是旧 UI，留到 Sprint B |
| 前端测试 0 | CodingWorkbench 无 vitest 覆盖 |
| 颜色方案未全局统一 | 仅 CodingWorkbench 改了色调 |
| Export 仅 JSON | Markdown/PDF 留到 Sprint C |

## 8. 修改文件

| 文件 | 改动 |
|------|------|
| `frontend/src/pages/CodingWorkbenchPage.tsx` | 707行→~350行，完全重写 |
| Backend | 0 行改动 |

## 9. 测试结果

```
后端: 481 passed, 9 skipped, 0 failed (无变化)
前端: 页面可编译，功能需浏览器验证
```
