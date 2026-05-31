# Sprint B — Human Review Cockpit

**日期**: 2026-05-12
**范围**: CaseReviewPage 从基础复核页面升级为 Corti-style 编码员复核驾驶舱

---

## 1. 改动前后对比

| 维度 | 之前 | 之后 |
|------|------|------|
| Candidate 展示 | 扁平行列表 | **卡片布局**：checkbox + status + code + routing tier + confidence |
| 操作方式 | 点击按钮 | **键盘快捷键** (A/R/M/Tab/Enter/Esc) |
| 批量操作 | 仅"全部确认" | **checkbox 选择 + 批量确认/拒绝 + 安全规则** |
| 修正原因 | 自由文本 | **标准下拉 (9 种) + 补充说明** |
| AI vs Gold | 不展示 | **右侧面板**：分歧编码对比 + DRG 影响标记 |
| 复核进度 | 仅文字 | **进度条 + 各状态计数 + "跳转下一个未审核"** |
| 视觉焦点 | 无 | **当前卡片 ring 高亮** |
| Toast 反馈 | 无 | **操作后浮动提示** |
| 后端 | — | **0 行改动** |

## 2. 复核驾驶舱结构

```
CaseReviewPage
├── Toast (操作反馈)
├── Header
│   ├── 复核标题 + 进度计数
│   ├── 批量操作栏 (全选/批量确认/批量拒绝)
│   ├── 跳转下一个未审核按钮
│   ├── 完成审核按钮
│   ├── 进度条 (confirmed/rejected/modified)
│   └── 快捷键提示行
├── Left Panel
│   └── Candidate Cards (带 checkbox + focus ring)
│       └── Expanded Review Form (decision buttons + 修正原因 dropdown + textarea)
└── Right Sidebar (272px)
    ├── 验证摘要 (supported/needs_review/unsupported/evidence_rate)
    ├── AI与标准分歧 (disagreement panel)
    ├── 复核决策 (decision summary)
    ├── 审核备注 textarea
    └── 批量安全规则说明
```

## 3. 快捷键

| 键 | 动作 |
|----|------|
| `A` | Approve 当前候选 |
| `R` | Reject 当前候选 |
| `M` | Modify 当前候选 |
| `Tab` | 下一个候选 |
| `Shift+Tab` | 上一个候选 |
| `Enter` | 提交当前审核 |
| `Esc` | 关闭审核表单 |

规则：输入框/textarea 聚焦时**不触发**全局快捷键。

## 4. 批量操作安全规则

| 条件 | 批量确认 | 批量拒绝 |
|------|---------|---------|
| 主诊断 (primary_diagnosis) | ❌ 跳过 | ✅ 允许（需原因） |
| ESCALATE routing tier | ❌ 跳过 | ✅ 允许（需原因） |
| unsupported status | ❌ 跳过 | ✅ 允许（需原因） |
| 批量拒绝 | — | **必须填写原因** |

## 5. 修正原因标准

9 种下拉选项：
1. 编码错误
2. 主诊断选择争议
3. 特异性不足
4. 证据不足
5. 规则违反
6. DRG敏感
7. 手术顺序问题
8. 重复编码
9. 其他

格式：`[原因] 补充说明` → 映射到 `human_reason` 字段。

## 6. Disagreement 展示逻辑

当 `disagreement_analysis.corrections` 非空时，右侧面板展示：
- AI 编码 → Gold 编码 (箭头)
- 分歧类型 (disagreement_type)
- DRG 影响标记 (drg_impacted → 红色标签)

## 7. 当前未解决问题

| 问题 | 说明 |
|------|------|
| 前端测试 0 | CaseReview 无 vitest 覆盖 |
| Review Notes 未持久化 | 当前 `handleComplete` 传入但不验证是否保存成功 |
| Toast 简单 | 无动画、无自动消失 |
| 无 Undo | 确认/拒绝后无法撤销 |
| 快捷键提示无 toggle | 始终显示，可能干扰 |
| Disagreement 数据依赖 API 返回 | 当前 API 可能不返回 disagreement_analysis 字段 |

## 8. 修改文件

| 文件 | 改动 |
|------|------|
| `frontend/src/pages/CaseReviewPage.tsx` | 344行→~280行，完全重写 |
| Backend | 0 行改动 |

## 9. 测试

```
后端: 481 passed, 9 skipped, 0 failed (无变化)
前端: 页面可编译，键盘快捷键 + 批量操作需浏览器验证
```
