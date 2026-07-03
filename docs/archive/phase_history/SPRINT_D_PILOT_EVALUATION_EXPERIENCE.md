# Sprint D — Pilot Evaluation Experience

**日期**: 2026-05-12
**范围**: 将 evaluation 输出从技术指标升级为医院可汇报、可解释、可管理的验证体验

---

## 1. 医院视角 Summary

### 之前 (技术指标)
```
primary_diag_accuracy: 0.70
secondary_diag_recall_avg: 0.55
evidence_completeness_avg: 0.72
hallucination_rate: 0.12
```

### 之后 (管理语言)
```
# iCoDer 试点评估报告
评估病例数: 45 例

## 一、总体结果
| 主诊断匹配率（严格） | 67% (30/45) | ≥ 50% |
| 主诊断匹配率（宽松） | 80% (36/45) | ≥ 70% |
| 手术编码匹配率       | 75% (33/45) | ≥ 60% |

## 二、AI 工作负载分布
| 自动通过 | 人工复核 | 升级审核 |
| 12       | 28       | 5        |

## 三、文书支撑不足病例
共 3 例存在至少一个编码证据不足。

## 七、试点结论建议
试点达到预期标准。建议进入下一阶段。
```

## 2. 新增功能

| 函数 | 用途 |
|------|------|
| `build_hospital_summary()` | 7-section Markdown 报告（总体结果/AI工作负载/文书不足/不一致/高风险/编码员一致性/结论） |
| `build_unsupported_evidence_report()` | 病历质控式报告：病例→编码→建议处理 |
| `build_drg_sensitive_report()` | DRG 风险报告：风险优先排序 |
| `build_pilot_conclusion()` | 一段式管理摘要 |

## 3. 设计原则

- **管理语言**: 不用 `precision/recall/F1`，用"匹配率/覆盖率"
- **Summary First**: 总体结果在最前
- **Risk First**: DRG 风险病例优先展示
- **中文优先**: 全部中文
- **行动导向**: 每个 section 给出建议

## 4. 修改文件

| 文件 | 改动 |
|------|------|
| `services/pilot_report_builder.py` | 新增 (4 个函数) |
| `tests/test_services/test_pilot_report.py` | 11 tests |
| `docs/SPRINT_D_PILOT_EVALUATION_EXPERIENCE.md` | 本文档 |
| Backend cognitive modules | 0 行改动 |

## 5. 测试结果

```
test_pilot_report.py: 11 passed
全量后端: 502 passed, 9 skipped, 0 failed
```
