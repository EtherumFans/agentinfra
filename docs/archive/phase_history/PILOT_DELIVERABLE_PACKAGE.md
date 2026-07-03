# Pilot Deliverable Package

**版本**: v1.0-pilot
**日期**: 2026-05-12
**用途**: 医院试点交付物清单

---

## 交付物总览

| # | 交付物 | 文件 | 用途 |
|---|--------|------|------|
| 1 | 金标病例模板 | `scripts/pilot_eval_runbook.py generate-template` | 编码员填写金标编码 |
| 2 | 数据申请模板 | `docs/cloud/CLOUD_INTAKE_TEMPLATE.md` | 向医院/ISV 信息科申请云端 Tenant 数据接入 |
| 3 | 已知限制说明 | `docs/PILOT_KNOWN_LIMITATIONS.md` | 试点前向医院明确能力边界 |
| 4 | 验收清单 | `docs/PILOT_ACCEPTANCE_CHECKLIST.md` | 试点验收逐项确认 |
| 5 | 评估基线报告 | `docs/EVALUATION_BASELINE_REPORT.md` | 10 demo cases 初始评估基线 |
| 6 | 问题报告模板 | `docs/PILOT_ISSUE_TEMPLATE.md` | 编码员反馈问题的标准格式 |
| 7 | 演示脚本 | `docs/PILOT_DEMO_SCRIPT.md` | 10 分钟标准化演示流程 |
| 8 | 试点执行手册 | `docs/PHASE11D_PILOT_EVALUATION_RUNBOOK.md` | 现场操作步骤 |
| 9 | 验收阈值建议 | `docs/PILOT_EVALUATION_ACCEPTANCE_THRESHOLDS.md` | 试点评估通过标准 |
| 10 | 修正汇总 | 由 CLI `run-evaluation` + `export-report` 生成 | 每例 AI vs Gold 对比 |
| 11 | 试点结论报告 | 由 CLI `export-report` 生成 | 最终试点评估结论 |

---

## 交付流程

```
Step 1: 医院/ISV 提供数据 (云端 Tenant 接入)
  → CLOUD_INTAKE_TEMPLATE.md (PHI 边缘脱敏通道)

Step 2: 生成模板 → 编码员填写
  → pilot_eval_runbook.py generate-template

Step 3: 校验 + 导入
  → pilot_eval_runbook.py validate-gold
  → pilot_eval_runbook.py import-gold

Step 4: 仲裁
  → AdjudicationRecord state machine

Step 5: 批量评估
  → pilot_eval_runbook.py run-evaluation

Step 6: 生成报告
  → pilot_eval_runbook.py export-report

Step 7: 试点验收
  → PILOT_ACCEPTANCE_CHECKLIST.md
  → PILOT_EVALUATION_ACCEPTANCE_THRESHOLDS.md

Step 8: 问题反馈闭环
  → PILOT_ISSUE_TEMPLATE.md
```

---

## 不纳入交付的内容

以下内容明确不在试点交付范围：
- 自动编码替代编码员 — iCoDer 定位为审核辅助
- 医保拒付预测 — 未经真实数据校准
- DRG 收益量化 — 样本不足
- 多院泛化 — 单院试点
- 语音实时编码 (STT) — WebSocket 通道未打通
- UI Dashboard — 无前端监控面板
- CI/CD — 手动部署
