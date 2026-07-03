# Phase 11A — Regression & Reliability Stabilization

**日期**: 2026-05-12
**范围**: 验证 Clinical Reasoning Layer 在真实条件下的稳定性、确定性、容错性

---

## 1. 动机

Phase 9-10 构建了完整的临床推理链，但 49 个文件未提交、未作为整体验证。进入 Pilot 前必须确认：
- 认知 pipeline 在确定性和随机输入下是否稳定
- Fallback 路径是否掩盖错误
- LLM 异常输入是否导致崩溃
- Runtime 是否能正确处理失败和恢复

---

## 2. Regression Test Suite

新增 `tests/regression/` 目录，10 个文件，100 个测试：

| 文件 | 测试数 | 覆盖范围 |
|------|--------|---------|
| `test_timeline_regression.py` | 11 | Timeline 确定性 (10 runs)、fallback 覆盖率 (7 种边界)、畸形输入 |
| `test_reasoning_regression.py` | 14 | 推理确定性、fallback 覆盖、畸形输入、degraded expert |
| `test_evidence_regression.py` | 16 | 证据排名确定性、11-factor 边界、unsupported/conflict 边界 |
| `test_disagreement_regression.py` | 13 | 分歧分类确定性、8-type 全覆盖、DRG 敏感性确定性 |
| `test_confidence_regression.py` | 14 | 校准确定性、路由确定性、tier 边界、degraded 输入 |
| `test_case_report_regression.py` | 8 | Degraded report (6 种缺失场景)、determinism (10 runs)、section ordering |
| `test_fallback_audit.py` | 13 | 全部 7 个模块的 fallback 路径审计、中文错误信息验证 |
| `test_runtime_recovery.py` | 14 | 状态恢复 (3)、超时升级 (3)、Guard 恢复 (3)、Audit 持久性 (4)、Registry 隔离 |

---

## 3. 关键发现

### 3.1 确定性验证 — 全部通过

所有认知模块的确定性函数在 10 次连续运行中产生完全一致的输出：
- Timeline `_fallback_extraction()`: 相同输入 → 相同 events + anchors
- Principal Diagnosis `_generate_why_selected()`: 相同输入 → 相同文本
- Evidence `rank_evidence_for_code()`: 相同输入 → 相同 strength_score
- Disagreement `_classify_disagreement_type()`: 相同输入 → 相同 type
- Confidence `calibrate_confidence()`: 相同输入 → 相同 calibrated_score
- Case Report `build_case_reasoning_report()`: 相同输入 → 相同 summary (不包括 timestamp)

### 3.2 Fallback 审计 — 全部通过

全部 7 个模块的 fallback 路径均产生合法、非空输出：
- 空文本 → 空列表/空字典 (不崩溃)
- 无日期文本 → 返回结构完整的结果
- 畸形输入 → 优雅降级 (不抛出未处理异常)

### 3.3 Runtime 恢复 — 全部通过

- FAILED → INGESTED 重试路径工作正常
- 非法状态转换返回 False (不抛异常)
- Timeout 正确触发 FAILED/ESCALATED
- Audit chain 在错误后继续记录
- Registry 多 pipeline 隔离正确

---

## 4. 新增文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `tests/regression/__init__.py` | 新增 | Package marker |
| `tests/regression/test_timeline_regression.py` | 新增 | 11 tests |
| `tests/regression/test_reasoning_regression.py` | 新增 | 14 tests |
| `tests/regression/test_evidence_regression.py` | 新增 | 16 tests |
| `tests/regression/test_disagreement_regression.py` | 新增 | 13 tests |
| `tests/regression/test_confidence_regression.py` | 新增 | 14 tests |
| `tests/regression/test_case_report_regression.py` | 新增 | 8 tests |
| `tests/regression/test_fallback_audit.py` | 新增 | 13 tests |
| `tests/regression/test_runtime_recovery.py` | 新增 | 14 tests |
| `docs/PHASE11A_REGRESSION_STABILIZATION.md` | 新增 | 本文档 |

---

## 5. 测试结果

```
tests/regression/: 100 passed, 0 failed
全量后端测试: 409 passed, 9 skipped, 0 failed
```

增量: +100 个回归测试，无业务代码修改，0 个破坏。

---

## 6. 当前局限

| 局限 | 说明 |
|------|------|
| 回归测试仅覆盖确定性路径 | LLM 依赖的路径未测试（需要真实 LLM 环境） |
| 无 LLM 输出的随机性回归 | 相同 prompt → 不同 LLM 输出 → 认知链是否稳定？需 LLM 环境验证 |
| 无并发回归 | 多 pipeline 同时运行时的 Runtime 隔离未充分验证 |
| 无持久化恢复回归 | Runtime flush-to-DB 后的恢复路径未测试 |
