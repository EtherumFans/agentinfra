# Phase 3-A Section C — Medical Coding Agent 产品化规格

**Date**: 2026-07-04
**Status**: COMPLETE — all 5 sub-tasks landed; 1230/1 pass; health_check 7/7; tsc 0; build OK; vitest 54/54

## C.1 Agent Pack / Agent Card 重写

### `official_agents/medical_coding/agent_pack.json` (Corti-style 产品包)

**Before**: name="Medical Coding Agent", description 提 MedCodER 5-stage pipeline + NAACL 2025, system_prompt 描写 5-stage 行为契约, output_contract=v1 (7 fields), 无 maturity/production_ready/human_review 字段, 无 Corti 红线 (no-upcoding / no-inference / evidence-required)。

**After**: 同名 "Medical Coding Agent" v2.0.0, 但全面 Corti-style:

| 字段 | Before | After |
|---|---|---|
| `agent_type` | certified | certified (unchanged — slug) |
| `manifest.category` | medical-coding | medical-coding (slug kept for back-compat with `coding_review_constants.py:38` + tests + main.py:512) |
| `manifest.category_display` | (无) | **"Coding and Revenue Cycle / 编码与收入周期"** (Corti-style display name) |
| `manifest.icon` | Stethoscope | Stethoscope (unchanged) |
| `manifest.tags` | [icd-10-cn, icd-9-cm-3, medcoder, rag, rerank] | **[icd-10-cn, icd-9-cm-3, evidence-first, no-upcoding, no-inference, human-review-required, corti-style]** |
| `manifest.maturity` | (无) | **mvp** |
| `manifest.production_ready` | (无) | **false** |
| `manifest.human_review` | (无) | **required** |
| `system_prompt` | 5-stage 行为契约 | **Corti 7-step workflow** (Synthesize Encounter → Extract Clinical Evidence → Search Coding Candidates → Assign Codes → Validate Coding → Identify Documentation Gaps → Generate Review Summary) + 9 Corti 红线 |
| `non_goals` | 6 条技术约束 | **10 条 Corti 红线** (不替代编码员 / 不 upcoding / 不推断未记录 / 每个 code 必须有 evidence / 不写回 / 不声称 fully automated / 不绕过 PHI / 不输出 F1 / gaps 必须显式输出 / 不调用外部写 API) |
| `output_contract.schema_ref` | icoder/MedicalCodingOutputSchema/v1 | **icoder/MedicalCodingAgentOutputV2/v1** |
| `output_contract.required_fields` | 7 fields (primary_dx, secondary_dx, procedures, issues, manual_review, confidence, conclusion) | **8 Corti-style fields** (encounter_summary, documentation_analysis, code_assignment, documentation_gaps, uncodable_items, validation_summary, human_review, trace_refs) |
| `permissions.no_upcoding/no_inference/evidence_required` | (无) | **true** (Corti 红线 enforced) |
| `human_review_required_when` | 4 triggers | **6 triggers** (+documentation_gaps non-empty, +uncodable_items non-empty, +review_conclusion==FAIL) |
| `a2a.endpoint` | (无) | `/api/icoder/agents/medical-coding-agent/v1/message:send` |
| `internal_engine` | (无) | **NEW** — 指向 `icoder/medcoder-coding-review-agent@1.0.0` 作为 internal_engine, 5 stages 列出, 注明 "Internal implementation detail. Not user-facing." |

### `official_agents/medcoder-coding-review/agent_pack.json` (internal_engine 降级)

**Before**: agent_type="reference", name="MedCodER Coding Review Agent", description 描写 14-stage 替代 + 5-stage 管线, 系统提示中宣传 MedCodER 5-stage, 暴露给最终用户。

**After**: agent_type=**internal_engine**, name=**"Medical Coding Agent — Internal Engine (MedCodER 5-stage)"**, description 改为"内部实现引擎, 仅供 icoder/medical-coding-agent@2.0.0 作为 internal_engine 调用, 最终用户应使用 Medical Coding Agent (Corti-style)", maturity=internal, hidden_from_hub=true, category_display="Internal Engine", tags=[internal-engine, medcoder, 5-stage-pipeline, not-user-facing]。

**Preserved**: agent_ref (`icoder/medcoder-coding-review-agent@1.0.0`), experts (4 个 D2 expert packs), tools (5 个 MCP tools), pipeline (5-stage), model config, output_contract (MedicalCodingOutputSchema/v1) — 这些是 internal_engine 的实现细节, 不变。

### Loader + schema 更新

- `icoder_runtime/core/agent_pack_schema.py:31-36`: `LEGAL_AGENT_TYPES_V12` 加 `"internal_engine"` (在 reference 后, expert-stub 前)
- `icoder_runtime/core/agent_pack_loader.py:391-401`: `_classify` 加 `internal_engine` 分支 — 同 reference 语义 (EXECUTABLE + production_ready=True)
- `tests/unit/icoder_runtime/test_agent_pack_loader.py:546,554-559`: 断言从 `agent_type == "reference"` 改为 `agent_type == "internal_engine"`, 注释标 "Phase 3-A: was reference pre-productization"

## C.2 System Prompt / Agent Instructions 重写

新 system_prompt 体现 Corti-style 7-step workflow:

```
你是 iCoDer Medical Coding Agent (Corti-style, MVP)。职责: 基于病历证据生成
ICD-10-CN 诊断编码与 ICD-9-CM-3 手术操作编码建议, 输出 Corti-style 8-field 结构化结果。

核心行为契约 (Corti 7-step workflow):
1. Synthesize Encounter: 整合入院记录 / 出院小结 / 手术记录 / 病程记录 / 检查报告,
   形成 encounter_summary (主诉、诊疗经过、关键发现)。
2. Extract Clinical Evidence: 抽取诊断证据、手术证据、否定发现、既往病史 —
   每条证据必须 char-anchored span (能在原文找到), 不得编造。
3. Search Coding Candidates: BGE-M3 + FAISS 检索 ICD-10-CN / ICD-9-CM-3 候选编码
   top-20, 经 icd10cn_code_catalog 合规过滤。
4. Assign Codes: RankGPT-style 重排序 top-5 per diagnosis, 编码员可选 final code;
   每个最终编码必须附 evidence span + confidence。
5. Validate Coding: 跑 MedicalCodingRuleSet (R001-R010 + MC-R-M80-001) —
   catalog membership / chapter metadata / 主诊断冲突 / 手术-诊断一致性;
   输出 validation_summary。
6. Identify Documentation Gaps: 标记证据不足 / 候选编码冲突 / 否定发现未编码 /
   历史诊断未编码 — 输出 documentation_gaps + uncodable_items。
7. Generate Review Summary: 输出 review_conclusion (PASS | WARNING | FAIL)
   + manual_review_required + 人工复核重点 + trace_refs。

硬约束 (Corti 红线):
- 不替代编码员 (AI-assisted, human_review=required)
- 不 upcoding (不优先选择高补偿编码)
- 不推断未记录的诊断 / 手术 (evidence-first, no inference beyond documentation)
- 每个最终编码必须附 evidence span (no evidence = no code)
- 不写回 EMR / HIS / 医保结算系统 (production_writeback_blocked=true)
- 不声称 fully automated coding
- 不绕过 PHI redaction (Context 强制)
- 不输出 F1 / 模型效果指标给最终用户
- documentation_gaps + uncodable_items + human_review 必须显式输出 (即使为空)
```

## C.3 Workflow 重构为 Corti-style

| Corti Step | MedCodER Stage (internal_engine) | Output Field |
|---|---|---|
| 1. Synthesize Encounter | (new — top-level synthesis) | `encounter_summary` |
| 2. Extract Clinical Evidence | Stage 1 (Extraction) | `documentation_analysis` |
| 3. Search Coding Candidates | Stage 2 (Retrieval) | (intermediate — feeds Stage 4) |
| 4. Assign Codes | Stage 3+4 (Merge + Re-Rank) | `code_assignment` |
| 5. Validate Coding | Stage 5 (Calibration) | `validation_summary` |
| 6. Identify Documentation Gaps | (new — surfaced from Stage 1+5) | `documentation_gaps` + `uncodable_items` |
| 7. Generate Review Summary | (new — top-level conclusion) | `human_review` + `trace_refs` |

The MedCodER 5-stage pipeline continues to power steps 2-5 as `internal_engine`. Users interact with the Corti 7-step workflow + 8-field output only — the 5-stage technical surface does NOT surface to users.

## C.4 Output Contract 重构 (8 Corti-style fields)

New schema `MedicalCodingAgentOutputV2` added to `official_agents/medical_coding/schema.py`:

| Field | Type | Purpose |
|---|---|---|
| `encounter_summary` | EncounterSummary | chief_complaint, treatment_course, key_findings, document_sources, encounter_date |
| `documentation_analysis` | DocumentationAnalysis | diagnosis_evidence, procedure_evidence, negated_findings, historical_conditions (each list[EvidenceSpan]) |
| `code_assignment` | CodeAssignment | primary_diagnosis (DiagnosisEntry), secondary_diagnoses (list), procedures (list) — each code carries evidence + confidence |
| `documentation_gaps` | list[DocumentationGap] | gap_type (insufficient_evidence / candidate_conflict / negated_uncoded / historical_uncoded), description, related_code, suggestion |
| `uncodable_items` | list[UncodableItem] | item_type (negated_finding / historical_condition / deferred_diagnosis / other), text, reason |
| `validation_summary` | ValidationSummary | passed (bool), issues_found (list[CodingIssue]), manual_review_required, rule_set, fired_rules |
| `human_review` | HumanReview | review_conclusion (PASS / WARNING / FAIL), review_required (bool, always true in MVP), review_focus (list[str]), notes |
| `trace_refs` | TraceRefs | run_id, stage_trace, rule_fired, mode, method_id, provider, model |

**Backward compatibility**: `MedicalCodingAgentOutputV2.from_legacy_v1(legacy, run_id=...)` classmethod projects a v1 `MedicalCodingOutputSchema` (runtime internal) to v2 (user contract). Used by the A2A / API layer to expose Corti-style output without breaking the runtime's internal representation.

**Contract enforcement**: every field must be present in the output, even if empty (no field may be omitted — Corti contract). The `to_dict()` always returns all 8 keys.

## C.5 中国场景本地化

| Aspect | Localization |
|---|---|
| Diagnosis coding system | ICD-10-CN (37,897 codes from `icd10cn_code_catalog.json`) |
| Procedure coding system | ICD-9-CM-3 (13,617 codes from `icd9cm3_code_catalog.json`) |
| Synonym expansion | `icd10cn_synonym_map.json` (75,968 synonyms, 21 term_index classes) |
| Differentiation hints | `coding_differentiation_kb.json` (2,090 P0/P1 code-pair hints) |
| Evidence anchoring | `evidence_anchoring_kb.json` (972 codes × 6,490 patterns) — wired in E1.2 audit |
| CoT few-shot | `cot_generation_progress_v2.json` (175/500 verified rerank CoT) — Phase 2 wire |
| DRG/DIP | 病案首页逻辑保留为 compliance reminder only (drg_suggestion / dip_suggestion fields in v1 schema, NOT promoted to v2 user-facing fields) |
| PHI redaction | GB/T 35273-2020 compliant — Context 强制 PHI 脱敏 (redacted=1 不可改) |

## Files changed (Section C)

```
backend/official_agents/medical_coding/agent_pack.json          (rewrite, 138 → 183 lines)
backend/official_agents/medcoder-coding-review/agent_pack.json  (manifest rewrite, 13 lines)
backend/official_agents/medical_coding/schema.py                (+270 lines: 8 Corti-style dataclasses + V2 schema + from_legacy_v1)
backend/app/api/runtime_platform.py                             (1 line: AGENT_REF 1.0.0 → 2.0.0)
backend/app/icoder/mcp/server.py                                (docstring: 5 tools back Medical Coding Agent)
backend/icoder_runtime/core/agent_pack_schema.py                (+1 line: LEGAL_AGENT_TYPES_V12 +internal_engine)
backend/icoder_runtime/core/agent_pack_loader.py                (+11 lines: _classify internal_engine branch)
backend/tests/unit/icoder_runtime/test_agent_pack_loader.py     (5 lines: reference → internal_engine)
frontend/src/i18n/locales.ts                                    (+9 lines: codingPipeline/codingMode/enableCoding keys zh+en, deprecated aliases kept)
frontend/src/pages/MedicalCodingPage.tsx                        (1 line: medcoderPipeline → codingPipeline label)
frontend/src/components/medical-coding/DiagnosisCard.tsx        (comment update: MedCodER pipeline → Medical Coding Agent)
frontend/src/components/medical-coding/EvidenceHighlighter.tsx  (comment update: same)
```

13 files changed, +310 / -50.

## Verification

```
$ python -m pytest tests/test_api/ tests/unit/ tests/regression/ tests/e2e/icoder/
1230 passed, 1 skipped, 0 failed in 117.61s

$ python scripts/health_check.py
VERDICT: PASS  (7/7 passed)

$ cd frontend && npx tsc --noEmit  (0 errors)
$ cd frontend && npm run build     (✓ built in 5.79s)
$ cd frontend && npx vitest run src/  (54 passed)
```

## Non-goals (out of scope for Section C)

- A2A agent_card factory refactor (`medcoder_coding_review_card` still produces "MedCodER Coding Review Agent" name — tests assert it; will be addressed in Section D/E when A2A discovery is rewired to expose `medical-coding-agent` as the user-facing card)
- Frontend UI changes for 8-field output rendering (Section D)
- Runtime integration of v2 schema in API responses (Section E)
- F1 improvement / Stage 1 prompt / Stage 4 rerank (out of scope per spec)

Section D (Product UI/UX) can proceed on this stable product base.
