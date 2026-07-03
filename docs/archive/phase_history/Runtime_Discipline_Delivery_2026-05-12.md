# Runtime Discipline — 最终交付文档

**日期**: 2026-05-12
**范围**: 5 层安全框架 (State Machine → Tool Gates → DUC → Audit Chain → Human-in-the-Loop)

---

## 1. Runtime 状态图

```
                            ┌─────────────┐
                            │  INGESTED   │ (30min timeout)
                            └──────┬──────┘
                                   │
                            ┌──────▼──────┐
                   ┌────────│CONTEXT_READY│ (10min timeout)
                   │        └──────┬──────┘
                   │               │
                   │        ┌──────▼────────┐
                   │  ┌─────│FACTS_EXTRACTED│ (5min timeout)
                   │  │     └──────┬────────┘
                   │  │            │
                   │  │     ┌──────▼────────┐
                   │  │     │CANDIDATES_READY│ (5min timeout)
                   │  │     └──────┬────────┘
                   │  │            │
                   │  │     ┌──────▼────────┐
                   │  │     │RULES_VALIDATED │
                   │  │     └──┬───────┬────┘
                   │  │        │       │
                   │  │   ┌────▼──┐ ┌──▼──────────┐
                   │  │   │RISK   │ │REVIEW_REQUIRED│ (4h timeout)
                   │  │   │IDENT  │ └──┬───────┬───┘
                   │  │   └──┬───┘    │       │
                   │  │      │   ┌────▼──┐ ┌──▼────────┐
                   │  │      │   │ESCAL- │ │DECISION    │
                   │  │      │   │ATED   │ │CONFIRMED   │
                   │  │      │   └──┬───┘ └──┬────┬────┘
                   │  │      │      │        │    │
                   │  │      │      └────────┘    │
                   │  │      │                     │
                   │  │      │              ┌──────▼──────┐
                   │  │      │              │DOC_FEEDBACK  │
                   │  │      │              │READY         │
                   │  │      │              └──────┬──────┘
                   │  │      │                     │
                   │  │      │              ┌──────▼──────┐
                   │  │      │              │WRITEBACK     │ (2h timeout)
                   │  │      │              │PENDING       │
                   │  │      │              └──┬───────┬──┘
                   │  │      │                 │       │
                   │  │      │          ┌──────▼──┐ ┌──▼────────┐
                   │  │      │          │WRITTEN   │ │ESCALATED   │
                   │  │      │          │BACK      │ └────────────┘
                   │  │      │          └────┬─────┘
                   │  │      │               │
                   └──┴──────┴───────────────┼──────────┐
                                             │          │
                                      ┌──────▼────┐ ┌──▼──────┐
                                      │ ARCHIVED  │ │ FAILED  │
                                      │ (terminal)│ │→INGESTED│
                                      └───────────┘ └─────────┘

新增边 (本次交付):
  CONTEXT_READY ──→ ARCHIVED  (Agent fast-path)
  FACTS_EXTRACTED ──→ ARCHIVED  (Agent fast-path)

Timeout 自动转换:
  REVIEW_REQUIRED (4h)  → ESCALATED
  WRITEBACK_PENDING (2h)→ ESCALATED
  其余状态              → FAILED
```

## 2. DUC Registry (Deny-Unless-Confirmed)

10 项高危操作，需人工确认后才允许执行：

| # | DUC Action | 说明 | 需要状态 |
|---|-----------|------|---------|
| 1 | `finalize_principal_diagnosis` | 锁定主要诊断 | REVIEW_REQUIRED |
| 2 | `confirm_high_dispute_comorbidity` | 确认高争议合并症 | REVIEW_REQUIRED |
| 3 | `submit_payment_high_risk` | 提交高风险支付 | REVIEW_REQUIRED |
| 4 | `writeback_to_emr` | 写回电子病历 | DECISION_CONFIRMED |
| 5 | `writeback_to_his` | 写回医院信息系统 | DECISION_CONFIRMED |
| 6 | `writeback_to_insurance` | 写回医保系统 | DECISION_CONFIRMED |
| 7 | `create_document_correction_task` | 创建文书修正任务 | DECISION_CONFIRMED |
| 8 | `archive_case` | 归档案例 | DECISION_CONFIRMED |
| 9 | `confirm_decision` | 确认审核决定 | REVIEW_REQUIRED |
| 10 | `initiate_writeback` | 启动写回流程 | DECISION_CONFIRMED |

**门控规则**:
```
guard(action) →
  if action not in STATE_ACTIONS[state] → DENY
  if action in DUC_ACTIONS and not human_confirmed → REVIEW
  if action.startswith("writeback") and state not in {DECISION_CONFIRMED, WRITEBACK_PENDING} → DENY
  else → ALLOW
```

## 3. 新状态转换表 (STATE_TRANSITIONS)

| from_state | to_states (新增以 ★ 标注) |
|-----------|--------------------------|
| INGESTED | CONTEXT_READY, FAILED |
| CONTEXT_READY | FACTS_EXTRACTED, **ARCHIVED**★, FAILED |
| FACTS_EXTRACTED | CANDIDATES_READY, **ARCHIVED**★, FAILED |
| CANDIDATES_READY | RULES_VALIDATED, FAILED |
| RULES_VALIDATED | RISK_IDENTIFIED, REVIEW_REQUIRED, FAILED |
| RISK_IDENTIFIED | REVIEW_REQUIRED, FAILED |
| REVIEW_REQUIRED | DECISION_CONFIRMED, ESCALATED, FAILED |
| DECISION_CONFIRMED | DOC_FEEDBACK_READY, WRITEBACK_PENDING, ARCHIVED, FAILED |
| DOC_FEEDBACK_READY | WRITEBACK_PENDING, ARCHIVED, FAILED |
| WRITEBACK_PENDING | WRITTEN_BACK, ESCALATED, FAILED |
| WRITTEN_BACK | ARCHIVED, FAILED |
| ARCHIVED | (terminal — 无合法转出) |
| FAILED | INGESTED (仅重启) |
| ESCALATED | REVIEW_REQUIRED (仅降级) |

## 4. guard_post 统一规则

| # | 规则 | 条件 | 结果 |
|---|------|------|------|
| 1 | 输出非空 | output is None 或 dict 所有值为空 | → **DENY** |
| 2 | Code candidates 合法 | diagnosis_candidates / procedure_candidates 非 list | → **REVIEW** |
| 3 | Evidence 存在 | evidence.diagnosis_facts + procedure_facts 均为空 | → **REVIEW** |
| 4 | DRG 结构合法 | drg_impact 非 dict | → **DENY** |
| 5 | Report 非空 | report_markdown 字符串 < 10 字符 | → **REVIEW** |
| 6 | 高风险输出拦截 | 包含 "处方" / "建议用药" / "手术方案" / "剂量" | → **DENY** |
| — | 关键字段非 null | primary_diagnosis / main_procedure / evidence / errors 为 None | → **REVIEW** |

## 5. check_timeout 行为

| 状态 | Timeout | 行为 | 审计 |
|------|---------|------|------|
| INGESTED | 1800s (30min) | → FAILED ("auto_retry") | timeout_escalation |
| CONTEXT_READY | 600s (10min) | → FAILED ("auto_retry") | timeout_escalation |
| FACTS_EXTRACTED | 300s (5min) | → FAILED ("auto_retry") | timeout_escalation |
| CANDIDATES_READY | 300s (5min) | → FAILED ("auto_retry") | timeout_escalation |
| REVIEW_REQUIRED | 14400s (4h) | → ESCALATED ("escalate_to_supervisor") | timeout_escalation |
| WRITEBACK_PENDING | 7200s (2h) | → ESCALATED ("alert_oncall") | timeout_escalation |
| 其他状态 | 无配置 | 不检查 | — |

## 6. 修改文件列表

| 文件 | 修改内容 |
|------|----------|
| `backend/app/services/runtime.py` | ✅ `STATE_TRANSITIONS` 新增 CONTEXT_READY→ARCHIVED, FACTS_EXTRACTED→ARCHIVED |
| | ✅ `ToolGate.post_check()` 重构为 6 条统一 guard_post 规则 |
| | ✅ `ToolGate.BLOCKED_OUTPUT_TERMS` 新增 (处方/建议用药/手术方案/剂量) |
| | ✅ `DeterministicRuntime.check_timeout()` 增加自动 transition + audit 记录 |
| `backend/app/services/agent_runner.py` | ✅ `run()`: 3 处 `check_timeout()` + 修正 guard_post 传参 |
| | ✅ `stream()`: 2 处 `check_timeout()` + 修正 guard_post 传参 |
| | ✅ `_run_single_expert()`: 修正 guard_post 传参 |
| | ✅ `_run_fixed_order()`: 修正 guard_post 传参 |
| | ✅ `_run_llm_planned()`: 修正 guard_post 传参 |
| `backend/app/agents/orchestrator.py` | ✅ `run_pipeline()`: 5 处 `check_timeout()` |
| | ✅ `run_intelligent_pipeline()`: Runtime 创建 + guardrails + check_timeout |
| `backend/app/api/reviews.py` | ✅ `review_candidate()`: `check_timeout()` + Runtime guard |
| | ✅ `complete_review()`: `check_timeout()` + Runtime guard |
| | ✅ 新增 `_extract_pipeline_id()` 辅助函数 |

## 7. 新增测试列表

| 文件 | 用例数 | 范围 |
|------|--------|------|
| `test_agent_runner_runtime.py` | 7 | AgentRunner Runtime 创建、状态转换、audit、多次运行隔离、stream 路径 |
| `test_review_runtime_guards.py` | 11 | pipeline_id 提取、guard 调用、human_confirm、DUC 拒绝、非法转换、audit 完整性 |
| `test_runtime_discipline.py` | **44** | 合法状态流(5)、非法转换(5)、REVIEW_REQUIRED 阻断(3)、human_confirm 要求(3)、timeout 升级(6)、guard 拒绝(3)、guard_post 拒绝(12)、audit 完整性(7) |

**总计**: 62 个 Runtime 相关测试，全部通过。

## 8. 当前剩余技术债

| # | 项目 | 严重度 | 备注 |
|---|------|--------|------|
| 1 | Runtime API 无前端消费者 (6 端点) | P1 | 见 `FRONTEND_FAKE_FEATURES_AUDIT.md` |
| 2 | A2A coordinate/chain 从未被调用 | P1 | 仅 SettingsPage toggle 用到了 a2aApi |
| 3 | WebSocket STT 不可用 | P0 | nginx / Vite proxy 问题 |
| 4 | CodingWorkbench 导出按钮无 onClick | P1 | 死按钮 |
| 5 | 4/11 Expert 未在固定 pipeline 中 | P1 | CDI/Denial/Audit/HCC |
| 6 | 前端单元测试 0 | P1 | vitest 已装但无用例 |
| 7 | CI/CD 不存在 | P1 | 无 GitHub Actions |
| 8 | 数据库迁移脚本为空 | P2 | Alembic versions/ 空 |
| 9 | test_oauth.py / test_code_dictionary.py 预存在失败 | P2 | 需单独修复 |
| 10 | guard_post 在 stream 路径无法完整验证 | P2 | stream 输出非结构化 dict，仅做 light check |
