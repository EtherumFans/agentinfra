# EvaluationPage

**路由**: `/evaluation` | **定位**: AI评估 (Phase 2.1-B 起 `/api/evaluation/run` 已删除)

> ⚠️ Phase 2.1-B Step 1 删除 `app/api/evaluation.py`, 此页面的 API 调用已失效。
> 评估能力现通过 MedCodER Pre-built Agent + A2A 任务流提供。
> 此页面待 Phase 3 重写或删除。

## 元素
| 元素 | 操作 | 预期 |
|------|------|------|
| 运行评估 | 点击 | (DEPRECATED) 原 POST /api/evaluation/run |
| 6 个指标卡片 | 查看 | 主诊断/手术准确率/证据完整度/幻觉率/召回率/总分 |
| 案例表格 | 查看 | 案例ID/AI诊断/匹配状态/幻觉编码/证据/得分 |
| 空状态 | 查看 | BarChart3 图标 + 提示文字 |
