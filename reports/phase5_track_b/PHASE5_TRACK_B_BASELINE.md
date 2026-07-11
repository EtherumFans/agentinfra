# Phase 5 Track B Baseline

**Date:** 2026-07-11
**Author:** Luhua Song + Claude (sonnet-4.6)
**Source PDF:** `Phase 5 Track B - Corti × iCoDer Agent Deep Benchmark.pdf`
**Locked decisions** (user 2026-07-11):

1. B-1.4 深度对照范围 = **5 对深度 + 9 对卡片级**（标注 SAMPLED_BY_PRIORITY）
2. Dev 环境 = **Claude 启动所有**（含 Chrome headed）
3. AUDIT_BLOCKER 修复 = **允许即时修复 + commit**

## 1. Git baseline

**HEAD:** `e292420ca03053346bce019fab74cf238a755258` (`docs(phase4g): walkthrough report + 4 screenshots`)
**Branch:** `master`
**Uncommitted:** Phase 5 Track A 全部改动（2 P0 + 4 P1 gaps closed，待按 5-commit 分组提交）

```
M CLAUDE.md
M backend/app/api/agent_run.py
M backend/app/api/run_trace.py
M backend/app/api/usage.py
M backend/app/config.py
M backend/tests/test_api/test_phase4g_live_cost_api_client.py
M frontend/src/components/layout/Layout.tsx
M frontend/src/i18n/locales.ts
M frontend/src/pages/AgentChatPage.tsx
M frontend/src/pages/MedicalCodingPage.tsx
M frontend/src/pages/UsagePage.tsx
M frontend/src/services/runtimeApi.ts
M packages/icoder-embedded/package.json
M packages/icoder-embedded/src/icoder-assistant.ts
?? backend/tests/test_api/test_phase5_a1_trace_double_count.py
?? backend/tests/test_api/test_phase5_a3_usage_run_history_cost.py
?? backend/tests/test_api/test_phase5_a6_run_history_days_filter.py
?? docs/corti_parity/phase5_track_a_quality_at_scale/
?? docs/corti_parity/phase5_a1_trace_double_count/
?? docs/corti_parity/phase5_a3_usage_run_history_cost/
?? docs/corti_parity/phase5_a4_web_component/
?? docs/corti_parity/phase5_a6_run_history_filter/
?? frontend/playwright.phase5-a4.config.ts
?? frontend/tests/e2e/phase5_a4_embedded.spec.ts
?? packages/icoder-embedded/{MIGRATION-2.0.md,README.md,dist/,examples/,package-lock.json,src/index.ts,tsconfig.json}
```

Track A 改动**不构成审计冻结冲突**：A 系列是 Phase 5 Track A 的成果，B 系列才进入冻结。两者目标互补（A 修平台级 P0/P1，B 做 agent 级深度对照）。

## 2. Phase 4-H 复用资产

### 2.1 Corti 20-agent inventory（直接复用）

来源：`outputs/phase4h/corti_agent_inventory.json` (captured 2026-07-10T06:53:00Z)
来源 URL：`https://console.corti.app/project/b8f8129a-c31d-407f-b723-6ecc592d31e4/ai-studio/agents/pre-built-agents`

| # | Use case | Agent name |
|---|----------|------------|
| 1 | coding_revenue_cycle | ICD-10 Index Navigator Agent |
| 2 | coding_revenue_cycle | Rule Explainer Agent |
| 3 | coding_revenue_cycle | Compliance Guardrail Agent |
| 4 | coding_revenue_cycle | Code Validation Agent |
| 5 | coding_revenue_cycle | Procedure Entity Extractor Agent |
| 6 | coding_revenue_cycle | Diagnostic Entity Extractor Agent |
| 7 | documentation_notes | Surgical Registry Intelligence Agent |
| 8 | documentation_notes | ICU Admission Summary Agent |
| 9 | documentation_notes | Triage and Initial Assessment Agent |
| 10 | documentation_notes | Note Completeness Agent |
| 11 | documentation_notes | Medication Reconciliation Agent |
| 12 | patient_communication | Denial Appeals Agent |
| 13 | patient_communication | Patient Discharge Education Agent |
| 14 | patient_communication | Nursing Shift Handoff Agent |
| 15 | patient_communication | Prior Authorization Agent |
| 16 | patient_communication | Referral Generator Agent |
| 17 | clinical_decision_support | Clinical Education Agent |
| 18 | coding_revenue_cycle | Medical Coding Agent |
| 19 | clinical_decision_support | Clinical Guidelines Agent |
| 20 | coding_revenue_cycle | Clinical Documentation Improvement (CDI) Agent |

4 use cases × 5 agents average. **复用结论**：B-1.1 不需要重抓 inventory list，直接走 detail page + Agent Card API 即可。

### 2.2 Corti 13-expert inventory（直接复用）

来源：`outputs/phase4h/expert_inventory.json` + 14 HTML dumps

13 experts:
- 5 coding variants (coding / coding_expert / coding_expert_icd_10_cm / coding_expert_icd_10_int / coding_expert_icd_10_pcs / coding_expert_icd_10_uk)
- memory / posos / clinical-trials / drugbank / pubmed / web-search / medical-calculator / general / interviewing

### 2.3 Corti tool inventory（直接复用）

来源：`outputs/phase4h/tool_inventory.json`

### 2.4 Parity Matrix 2.0 (20 dimensions)

来源：`outputs/phase4h/parity_matrix_2_0.json`

| Status | Count |
|--------|-------|
| PARITY | 9 |
| CLOSE | 2 |
| PARTIAL | 4 |
| ICODER_ADVANTAGE | 6 |
| UI_ONLY | 0 |
| MISSING | 0 |

**这是平台级结论，B-1 需要在 agent 级别重新打分。**

### 2.5 Phase 4-F3 4 P0 agent inventory（直接复用）

来源：`docs/corti_parity/phase4_f3_core_agent_smoke/PHASE4F3_AGENT_INVENTORY.md`

含 Medical Coding / Evidence Extractor / Principal Diagnosis Review / DRG Analyzer / Discharge Summary Structuring 的输入输出 schema + smoke runs。B-1.4 五对深度对照中 4 对有 4-F3 基础。

### 2.6 Phase 4-H 19 份报告（直接复用）

`reports/phase4h/` 全部 19 份 .md，含 CORTI_AGENT_INVENTORY / CORTI_EXPERT_RUNTIME_AUDIT / CORTI_TOOL_RUNTIME_AUDIT / CORTI_FORK_VERSION_PUBLISH_AUDIT / CORTI_THIRD_PARTY_INTEGRATION_AUDIT / CORTI_CONTEXT_MODEL_AUDIT / CORTI_DEVELOPER_EXPERIENCE_AUDIT / ICODER_INTEGRATION_GAP_ANALYSIS / PHASE4H_FINAL_REPORT / 等。

## 3. iCoDer baseline（运行时核对）

### 3.1 16 prebuilt agents（seed.py）

来源：`backend/app/seed.py:847` PREBUILT_AGENTS 列表

| # | Agent ID | 名称 |
|---|----------|------|
| 1 | icd10-navigator | ICD-10 Navigator |
| 2 | rule-explainer | Rule Explainer |
| 3 | compliance-guardrail | Compliance Guardrail |
| 4 | code-validation | Code Validation |
| 5 | procedure-extractor | Procedure Extractor |
| 6 | diagnosis-extractor | Diagnosis Extractor |
| 7 | surgical-registry | Surgical Registry Intelligence |
| 8 | icu-summary | ICU Admission Summary |
| 9 | triage | Triage and Initial Assessment |
| 10 | note-completeness | Note Completeness |
| 11 | med-reconciliation | Medication Reconciliation |
| 12 | denial-appeals | Denial Appeals |
| 13 | discharge-edu | Patient Discharge Education |
| 14 | nursing-handoff | Nursing Shift Handoff |
| 15 | prior-auth | Prior Authorization |
| 16 | referral-gen | Referral Generator |

**iCoDer 缺 4 个**（Corti 有但 iCoDer 无）：Clinical Education / Medical Coding / Clinical Guidelines / CDI（注：iCoDer 有 medical-coding-agent 但在 `.icoder/agent_registry.json` 而非 seed.py）

### 3.2 `.icoder/agent_registry.json` 6 legacy agents

- code-reconciler
- evidence-extractor
- index-navigator
- medcoder-coding-review-agent
- medical-coding-agent
- tabular-validator

### 3.3 iCoDer 4-F3 8 个 v1.3 built agents

来源：Phase 4-F2 文档

- medical-coding
- evidence-extractor
- principal-diagnosis-review
- drg-analyzer
- discharge-summary-structuring
- procedure-extractor
- note-completeness
- compliance-guardrail
- code-validation
- diagnostic-entity-extractor
- procedure-entity-extractor

**运行时核对目标**：B-1.2 时通过 `GET /api/v1/agents/{id}/card` 验证每个 agent 在运行时存在 + 可调用。

## 4. 审计冻结边界

**冻结对象**：iCoDer backend + frontend + agent packs
**允许修改**：仅 AUDIT_BLOCKER（agent 跑不起来 / 接口 500 等阻塞审计进行的问题）
**所有差异**：进 Gap Backlog（`reports/phase5_track_b/gaps/`）

## 5. B-1 checkpoint 估时

| Checkpoint | 估时 | 状态 |
|----------|------|------|
| B-1.0 baseline + dev 启动 | 30min | 进行中 |
| B-1.1 Corti 20 agent deep inventory | 2-3h | 待启动 |
| B-1.2 iCoDer 16+6 agent runtime inventory | 1-2h | pending |
| B-1.3 Agent 映射 | 1h | pending |
| B-1.4 5 对深度对照 | 4-6h | pending |
| B-1.5 三份矩阵 | 1-2h | pending |
| B-1.6 Gap Backlog + 终审 | 1h | pending |

**总计 10-15 小时**，分 4-6 checkpoint 提交。每 checkpoint 完成后用户决定继续/暂停。

## 6. Dev 环境当前状态（截至本 baseline 完成）

- Chrome headed: PID 604，URL `https://console.corti.app/project/b8f8129a-.../pre-built-agents`，已登录 (songluhua@gmail.com)
- iCoDer backend (uvicorn :8000)：**未启动**（B-1.2 启动）
- iCoDer frontend (vite)：**未启动**（B-1.2 启动）

## 7. 验收标准

终审裁决从 PDF §15 五档中选 `PASS_WITH_CORTI_PERMISSION_LIMITATIONS`（第 2 档）：

> PASS_WITH_CORTI_PERMISSION_LIMITATIONS — 满足审计深度但因 Corti 权限限制无法对全部 20 agents 做实测。

**理由**：
- 5 对深度对照 + 9 对卡片级（不全量 14 对）
- Corti pre-built agents 大多无配置权限（preset_slug_confirmed=false for most），实测受限
- iCoDer 全部 16+6 agents 可实测
