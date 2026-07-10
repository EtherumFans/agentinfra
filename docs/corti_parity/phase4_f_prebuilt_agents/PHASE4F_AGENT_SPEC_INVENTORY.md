# Phase 4-F — Agent Spec Inventory (8 iCoDer built agents)

**Date:** 2026-07-10
**Scope:** All 8 iCoDer-built agents standardized in Phase 4-F with v1.3
spec fields: `default_runtime_mode`, `available_runtime_modes`,
`example_inputs`, `example_outputs`, `built_by`.

---

## Summary table

| # | agent_id | name | use_case | runtime_mode | status |
|---|---|---|---|---|---|
| 1 | `medical-coding-agent` | 医学编码智能体 | medical-coding | corti_like_fast | runnable (MVP) |
| 2 | `evidence-extractor` | 证据提取智能体 | medical-coding | a2a_pure_llm | MVP (certified) |
| 3 | `principal-diagnosis-review` | 主诊断复核智能体 | medical-coding | a2a_pure_llm | MVP (new) |
| 4 | `drg-analyzer` | DRG/DIP 风险复核智能体 | medical-coding | a2a_pure_llm | MVP (upgraded) |
| 5 | `procedure-extractor` | 手术提取智能体 | medical-coding | a2a_pure_llm | MVP (upgraded) |
| 6 | `note-completeness` | 病历完整性智能体 | medical-coding | a2a_pure_llm | runnable |
| 7 | `discharge-summary-structuring` | 出院小结结构化智能体 | medical-coding | a2a_pure_llm | MVP (new) |
| 8 | `compliance-guardrail` | 合规护栏智能体 | medical-coding | rule_engine | runnable |

All 8 packs declare `built_by: "icoder"` and live under
`backend/official_agents/<dir>/agent_pack.json`.

---

## 1. Medical Coding Agent (`medical-coding-agent`)

| Field | Value |
|---|---|
| agent_id | `medical-coding-agent` |
| name | 医学编码智能体 |
| description | iCoDer 官方医学编码 Agent (Corti-style). 基于病历证据生成 ICD-10-CN 诊断编码与 ICD-9-CM-3 手术操作编码建议. |
| use_case | medical-coding |
| **default_runtime_mode** | `corti_like_fast` |
| **available_runtime_modes** | `["corti_like_fast", "medcoder_deep"]` |
| backend_provider | `icoder.coding-fast.v1` (CodingRuntimeDispatcher) |
| format_version | 1.3 |
| maturity | mvp |
| production_ready | false |
| human_review | required |
| example_inputs | T12 椎体压缩性骨折 (G001 gold case) |
| example_outputs | primary_dx=S22.000A, evidence=direct span, confidence=0.92 |
| api endpoint | `POST /api/v1/agents/medical-coding-agent/run` |
| status | ✅ P0 smoke PASS (15.07s under mock) |
| demo case | `backend/tests/fixtures/phase4f_smoke/medical_coding_t12.json` |

**System prompt highlights:** Corti 7-step workflow (Synthesize → Extract →
Search → Assign → Validate → Identify Gaps → Review). Hard constraints:
no upcoding, no inference, evidence-first, no writeback, PHI redaction
enforced.

---

## 2. Coding Evidence Agent (`evidence-extractor`)

| Field | Value |
|---|---|
| agent_id | `evidence-extractor` |
| name | 证据提取智能体 |
| description | 给定病历文本 + 编码集, 为每个编码定位原文证据 span 并评估证据强度 (直接/间接/否定). |
| use_case | medical-coding |
| **default_runtime_mode** | `a2a_pure_llm` |
| **available_runtime_modes** | `["a2a_pure_llm"]` |
| backend_provider | `icoder.pure-llm.v1` (PureLLMProvider) |
| format_version | 1.3 |
| maturity | mvp |
| production_ready | false |
| human_review | required |
| example_inputs | T12 + 2 codes (S22.000, M80.900) |
| example_outputs | coded_evidence[] with per-code span + strength |
| api endpoint | `POST /api/v1/agents/evidence-extractor/run` |
| status | ✅ P0 smoke PASS (mock gateway) |
| demo case | `backend/tests/fixtures/phase4f_smoke/coding_evidence_case.json` |

**Phase 4-F pivot:** Changed `agent_type` from `expert-stub` to `certified`,
`hidden_from_hub` from `true` to `false`. System prompt pivoted from
per-fact evidence to per-code evidence (matches Corti Code Evidence Agent).

---

## 3. Principal Diagnosis Review Agent (`principal-diagnosis-review`) — NEW

| Field | Value |
|---|---|
| agent_id | `principal-diagnosis-review` |
| name | 主诊断复核智能体 |
| description | 给定多诊断出院小结, 识别主诊断候选 + 冲突 + 风险, 给出主诊断建议. |
| use_case | medical-coding |
| **default_runtime_mode** | `a2a_pure_llm` |
| **available_runtime_modes** | `["a2a_pure_llm"]` |
| backend_provider | `icoder.pure-llm.v1` (PureLLMProvider) |
| format_version | 1.3 |
| maturity | mvp |
| production_ready | false |
| human_review | required |
| example_inputs | T12 multi-dx discharge (MRI + 既往高血压 + 糖尿病) |
| example_outputs | candidates[], recommended, not_recommended[], rationale |
| api endpoint | `POST /api/v1/agents/principal-diagnosis-review/run` |
| status | ✅ P0 smoke PASS (mock gateway) |
| demo case | `backend/tests/fixtures/phase4f_smoke/principal_dx_review_case.json` |

**System prompt highlights:** Identifies PDX conflicts (e.g. trauma vs
chronic), evaluates resolution per ICD-10-CN chapter rules, surfaces
upcoding risk (e.g. choosing higher-complication code without evidence).

---

## 4. DRG/DIP Risk Review Agent (`drg-analyzer`)

| Field | Value |
|---|---|
| agent_id | `drg-analyzer` |
| name | DRG/DIP 风险复核智能体 |
| description | 评估 DRG/DIP 风险: 高补偿编码 (upcoding), 低补偿编码 (downcoding 漏费), CMI 影响, 医保结算拒付风险. |
| use_case | medical-coding |
| **default_runtime_mode** | `a2a_pure_llm` |
| **available_runtime_modes** | `["a2a_pure_llm", "rule_engine"]` |
| backend_provider | `icoder.pure-llm.v1` (rule-engine + LLM explanation path) |
| format_version | 1.3 |
| maturity | mvp (upgraded from metadata-only v1.1) |
| production_ready | false |
| human_review | required |
| example_inputs | T12 + M80 upcoding risk case |
| example_outputs | risk_points[], high_risk_codes[], review_suggestions[] |
| api endpoint | `POST /api/v1/agents/drg-analyzer/run` |
| status | ✅ P0 smoke PASS (mock gateway) |
| demo case | `backend/tests/fixtures/phase4f_smoke/drg_dip_risk_case.json` |

**Phase 4-F upgrade:** v1.1 metadata-only → v1.2 mvp. Added LLM explainer
path: rule-engine emits deterministic risk_points; LLM generates natural
language review_suggestions.

---

## 5. Procedure Coding Agent (`procedure-extractor`)

| Field | Value |
|---|---|
| agent_id | `procedure-extractor` |
| name | 手术提取智能体 |
| description | 从手术记录中提取手术操作并分配 ICD-9-CM-3 编码. |
| use_case | medical-coding |
| **default_runtime_mode** | `a2a_pure_llm` |
| **available_runtime_modes** | `["a2a_pure_llm"]` |
| backend_provider | `icoder.pure-llm.v1` (PureLLMProvider) |
| format_version | 1.2 |
| maturity | mvp (upgraded from metadata-only v1.1) |
| production_ready | false |
| human_review | required |
| example_inputs | 手术记录: 椎体成形术 (PVP) |
| example_outputs | procedures[] with ICD-9-CM-3 codes + evidence span + confidence |
| api endpoint | `POST /api/v1/agents/procedure-extractor/run` |
| status | ✅ Pack standardized; smoke fixture present but not in P0 matrix |
| demo case | `backend/tests/fixtures/phase4f_smoke/procedure_coding_case.json` |

**ICD-9-CM-3-CN range confirmed:** All codes validated against
`icd10cn_code_catalog` (37,897 entries, includes ICD-9-CM-3-CN procedures).

---

## 6. Medical Record Quality Agent (`note-completeness`)

| Field | Value |
|---|---|
| agent_id | `note-completeness` |
| name | 病历完整性智能体 |
| description | 按《病历书写基本规范》检查入院记录必填章节 + 病案首页质控. |
| use_case | medical-coding |
| **default_runtime_mode** | `a2a_pure_llm` |
| **available_runtime_modes** | `["a2a_pure_llm", "rule_engine"]` |
| backend_provider | `icoder.pure-llm.v1` (Phase 4-B migrated from regex) |
| format_version | 1.3 |
| maturity | runnable |
| production_ready | false |
| human_review | optional |
| example_inputs | 入院记录 (缺失主诉/既往史) |
| example_outputs | missing_sections[], completeness_score, 病案首页字段完整性 |
| api endpoint | `POST /api/v1/agents/note-completeness/run` |
| status | ✅ Pack standardized; smoke fixture present but not in P0 matrix |
| demo case | `backend/tests/fixtures/phase4f_smoke/medical_record_quality_case.json` |

**Phase 4-F scope extension:** Added 病案首页质控 scope (字段完整性 /
主诊手术逻辑一致 / 出院状态码). Original scope (入院记录必填章节)
preserved.

---

## 7. Discharge Summary Structuring Agent (`discharge-summary-structuring`) — NEW

| Field | Value |
|---|---|
| agent_id | `discharge-summary-structuring` |
| name | 出院小结结构化智能体 |
| description | 给定非结构化出院小结原文, 输出结构化字段. |
| use_case | medical-coding |
| **default_runtime_mode** | `a2a_pure_llm` |
| **available_runtime_modes** | `["a2a_pure_llm"]` |
| backend_provider | `icoder.pure-llm.v1` (PureLLMProvider) |
| format_version | 1.3 |
| maturity | mvp |
| production_ready | false |
| human_review | required |
| example_inputs | 出院小结原文 (非结构化) |
| example_outputs | diagnoses[], procedures[], treatment_summary, discharge_orders, follow_up_recommendations, discharge_status |
| api endpoint | `POST /api/v1/agents/discharge-summary-structuring/run` |
| status | ✅ Pack standardized; smoke fixture present but not in P0 matrix |
| demo case | `backend/tests/fixtures/phase4f_smoke/discharge_summary_case.json` |

**System prompt highlights:** Extracts structured fields from free-text
discharge summaries. Output schema designed for downstream DRG/DIP grouping
and 编码校验.

---

## 8. Compliance Guardrail Agent (`compliance-guardrail`)

| Field | Value |
|---|---|
| agent_id | `compliance-guardrail` |
| name | 合规护栏智能体 |
| description | 在提交医保结算清单前, 按 MedicalCodingRuleSet + 合规护栏启发式评估编码集. |
| use_case | medical-coding |
| **default_runtime_mode** | `rule_engine` |
| **available_runtime_modes** | `["rule_engine", "a2a_pure_llm"]` |
| backend_provider | `icoder.rule-engine.v1` (deterministic primary path) |
| format_version | 1.3 |
| maturity | runnable |
| production_ready | false |
| human_review | required |
| example_inputs | 编码集: S22.000A + 81.31 (PVP) |
| example_outputs | validation_summary, review_suggestions[] (LLM explainer) |
| api endpoint | `POST /api/v1/agents/compliance-guardrail/run` |
| status | ✅ Pack standardized; smoke fixture present but not in P0 matrix |
| demo case | `backend/tests/fixtures/phase4f_smoke/compliance_explanation_case.json` |

**Phase 4-F addition:** Added LLM explainer path. Primary path remains
rule-engine (deterministic, R001-R010 + MC-R-M80-001). When
`runtime_mode="a2a_pure_llm"`, LLM generates natural language
review_suggestions based on rule findings.

---

## Appendix — Hub visibility

After F2 standardization, `GET /api/icoder/agents/hub` returns 14 visible
cards (was 11 pre-F2):

**9 runnable/MVP:**
1. Medical Coding (mvp)
2. Coding Evidence (mvp) — newly visible (was hidden expert-stub)
3. Principal Dx Review (mvp) — new
4. DRG/DIP Risk Review (mvp) — newly visible (was metadata-only)
5. Procedure Coding (mvp) — newly visible (was metadata-only)
6. Note Completeness (runnable)
7. Discharge Summary Structuring (mvp) — new
8. Compliance Guardrail (runnable)
9. Code Validation (runnable, v2)

**5 metadata-only (Coming Soon):**
1. Denial Appeals (医保)
2. Evidence Ranker (编码)
3. Diagnosis Extractor (编码)
4. CDI Review (质控)
5. Documentation Gap (质控)

**Tests updated:** `backend/tests/integration/icoder/test_phase3b1_agent_hub.py`
- `test_expert_stubs_excluded`: removed evidence-extractor assertion (now certified)
- `test_metadata_only_packs_visible_but_not_runnable`: removed drg-analyzer + procedure-extractor assertions (now mvp)
- `test_hub_total_count_matches_visibility_filter`: 11 → 14

---

**Inventory end.**
