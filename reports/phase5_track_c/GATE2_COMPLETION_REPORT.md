# Phase 5 Track C — Gate 2 Completion Report

**Date**: 2026-07-11
**Gate**: 2 — China medical business gates (§7.1-§7.6)
**Verdict**: `PASS_GATE2_CORE_CONTRACTS_DEFINED` (5/6 sub-gates shipped; §7.1 deferred to Gate 4 mainline integration)

---

## 1. Gate 2 scope (from PDF §7)

The PDF Gate 2 mandate has 6 sub-gates:

| § | Sub-gate | Status |
|---|---|---|
| 7.1 | Medical Coding Evidence Gate (supported/uncertain/rejected tiers) | ⏳ Deferred to Gate 4 (medical-coding-agent mainline integration) |
| 7.2 | Compliance Guardrail ICD-10-CN (per-code-system validation) | ✅ Closed |
| 7.3 | Procedure Status Gate (performed/planned/historical/cancelled/negated/unknown) | ✅ Closed |
| 7.4 | Evidence Negative Gate (direct/indirect/negated/historical/family_history/suspected/no_evidence) | ✅ Closed |
| 7.5 | Principal Diagnosis Conflict Gate (coding_draft_consistent + manual_review) | ✅ Closed |
| 7.6 | Note Completeness Structured Contract (8 required fields) | ✅ Closed |

Plus Gate 1 deferred P0 fixes:
- Wire `request` through provider.invoke → ✅ Closed (commit 8e15001)
- Migrate compliance-guardrail from RuleEngine → PureLLM → ⏳ Deferred (RuleEngine is still functional for structured-output-only paths; PureLLM migration is substantial rewrite, not Gate 2 critical path)

## 2. Sub-gate evidence (verified on real DeepSeek, 2026-07-11)

### 7.2 Per-code-system validation

**Files**: `backend/compliance_services/medical_coding_rules.py` + `test_code_system_validation.py` (31 new tests).

5 code systems now validated separately:

| Code system | Pattern | Example |
|---|---|---|
| WHO ICD-10 (international) | `^[A-Z]\d{2}(\.\d{1,2})?$` | `I21`, `I21.9`, `I21.19` |
| ICD-10-CN 6-digit | `^[A-Z]\d{2}\.\d{3}$` | `J15.900`, `S22.000` |
| ICD-10 x-placeholder | `^[A-Z]\d{2}\.x\d{0,3}$` | `I21.x00` |
| ICD-9-CM-3 procedure | `^\d{2}\.\d{4}$` | `81.0100`, `84.5100` |
| National clinical extension | `^[A-Z]\d{2}\.\d{4,}[A-Za-z0-9]{0,2}$` | long-form |

Structured validation output (the §7.2 contract):
```python
validate_code_per_system("I21.x00") == {
    "code": "I21.x00",
    "code_system": "icd10_cn_x",
    "normalized_code": "I21.x00",
    "format_valid": True,
    "catalog_valid": None,   # set by catalog-aware caller
    "assignable": False,     # ← x-placeholder cannot be final code
}
```

R002 (diagnosis) now flags x-placeholder codes as medium-severity "incomplete" issues. R004 (procedure) rejects ICD-10 codes placed in procedures[].

### 7.3 Procedure Status Gate

**Integration test** on `procedure-extractor` with mixed input:
```
输入: "本次住院行后路椎体成形术+骨水泥注入。既往曾行阑尾切除术。
       拟行PCI治疗(必要时)。患者拒绝植入人工关节。"

输出:
procedures (performed): 2
  - 81.6600 经皮椎体成形术 [status=performed]
  - 84.5100 骨水泥注入术 [status=performed]
non_billable_mentions: 3
  - 既往曾行阑尾切除术 [status=historical]
  - 拟行PCI治疗(必要时) [status=planned]
  - 患者拒绝植入人工关节 [status=cancelled]
```

Status classifier keywords: 行/performed, 拟行/planned, 既往/historical, 拒绝/cancelled, 未行/negated. Projector enforces the split — only `performed` enters `procedures[]`, others divert to `non_billable_mentions[]`.

### 7.4 Evidence Negative Gate + §7.1 tier classification

**Integration test** on `evidence-extractor` with mixed evidence:
```
输入: "...术后出现肺部感染,痰培养阴性。排除心力衰竭。既往糖尿病史10年。
       父亲高血压病史。疑似肺栓塞待排。"

输出 (supported/uncertain/rejected tiers):
supported_codes (1):
  - E11.9 strength=historical (糖尿病既往史)
uncertain_candidates (2):
  - J15.9 strength=indirect (肺部感染未明确病原体)
  - I26   strength=suspected (肺栓塞待排)
rejected_candidates (2):
  - I12.9 strength=no_evidence (高血压无证据)
  - I50.9 strength=negated (心衰被明确排除)
```

Evidence strength enum extended from 4 values (`direct|indirect|negated|none`) to 7 values per §7.4: `direct|indirect|negated|historical|family_history|suspected|no_evidence`.

### 7.5 Principal Diagnosis Conflict Gate

**Integration test** on `principal-diagnosis-review`:
```
recommended: {code: S22.000, display: T12 椎体压缩性骨折}
coding_draft_consistent: true
manual_review_required: false
rationale: 主诊断应为 S22.000 (T12椎体压缩性骨折)。患者因该诊断入院,
            接受了后路椎体成形术这一主要治疗, 消耗了最多医疗资源, 且对
            患者健康危害最严重。肺部感染为术后并发症, 骨质疏松和高血压
            为慢性合并症, 均不应作为主诊断。
```

New fields added per §7.5: `coding_draft_consistent` (bool), `conflict_reason` (str), `manual_review_required` (bool).

### 7.6 Note Completeness Structured Contract

**Integration test** on `note-completeness-agent`:
```
required_sections: [主诉, 现病史, 既往史, 体格检查, 辅助检查, 诊断, 治疗经过, 手术记录]
present_sections: implicit from below
missing_sections: [主诉, 现病史, 既往史, 体格检查, 辅助检查]
incomplete_sections: [
  {section: 诊断, deficit_note: 缺少入院诊断与出院诊断的明确区分...},
  {section: 治疗经过, deficit_note: 缺少术前准备/术中情况/术后恢复...},
  {section: 手术记录, deficit_note: 缺少手术日期/术者/麻醉方式...}
]
completeness_score: 0.375
review_conclusion: 病历严重不完整, 必填章节缺失 5/8, 且已存在的 3 个章节内容均不完整。
```

The 8-field structured contract is now emitted as JSON, not embedded in markdown.

## 3. Files changed (Gate 2)

| File | Status | Purpose |
|---|---|---|
| `backend/app/api/agent_run.py` | MODIFIED | Wire `request` through to provider.invoke (P0) |
| `backend/icoder_runtime/backends/pure_llm_provider.py` | MODIFIED | Accept `request: Any = None` kwarg |
| `backend/icoder_runtime/backends/rule_engine_provider.py` | MODIFIED | Accept `request: Any = None` kwarg |
| `backend/compliance_services/medical_coding_rules.py` | MODIFIED | §7.2 per-code-system validation |
| `backend/icoder_runtime/backends/structured_output_projector.py` | MODIFIED | §7.3-§7.6 extractors |
| `backend/official_agents/procedure-extractor/agent_pack.json` | MODIFIED | §7.3 status gate prompt |
| `backend/official_agents/evidence_extractor/agent_pack.json` | MODIFIED | §7.4 evidence strength + §7.1 tiers |
| `backend/official_agents/principal_diagnosis_review/agent_pack.json` | MODIFIED | §7.5 conflict gate prompt |
| `backend/official_agents/note-completeness/agent_pack.json` | MODIFIED | §7.6 structured contract prompt |
| `backend/tests/test_compliance/test_code_system_validation.py` | NEW | §7.2 31 tests |
| `backend/tests/unit/icoder_runtime/test_structured_output_projector.py` | MODIFIED | +4 Gate 2 contract tests |

**3 commits**:
- `8e15001` fix(track-c2): thread fastapi request through provider.invoke
- `6d59ad6` feat(track-c2): china medical business gates (§7.3-§7.6)
- `768cb27` feat(track-c2): §7.2 per-code-system validation (R002/R004 split)

## 4. What this closes

- ✅ **§7.2** Code-system format validation no longer coalesces all codes through one regex
- ✅ **§7.3** Procedure status gate ensures only `performed` procedures enter formal coding
- ✅ **§7.4** Evidence extractor surfaces negated/historical/suspected/no_evidence explicitly
- ✅ **§7.5** Principal diagnosis conflict detection produces structured recommendation + consistency flag
- ✅ **§7.6** Note completeness output is now a structured contract (8 fields), not markdown
- ✅ **P0 fix** Code-validation-agent's MCP tools now actually execute (request wired through)

## 5. Deferred

### §7.1 Medical Coding Evidence Gate (HybridCodingAdapter)

HybridCodingAdapter (medical-coding-agent's backend) already produces `extracted_diagnoses[]` with per-diagnosis `final_confidence` and evidence. Classifying into supported/uncertain/rejected is a post-processing step. Deferred to Gate 4 when the coding compliance mainline wires medical-coding into the orchestrator — at that point the tier classification will be added to the medical-coding-agent's output schema.

### Compliance-guardrail RuleEngine → PureLLM migration

The RuleEngineProvider is still functional for structured-output paths (returns proper R001-R010 issues). Full PureLLM migration requires:
- New system prompt emitting JSON compliance report
- New extractor in StructuredOutputProjector
- Migration of existing rule semantics (R001-R010) into prompt instructions
- Preserving back-compat with the RuleEngine for fallback

This is ~2-3 hours of focused work. Tracked as Gate 5 dependency (UI workbench for compliance-guardrail needs the new contract).

## 6. Next: Gate 3 — Corti-like Orchestrator kernel

Gate 3 implements the Corti-style orchestrator: ContextBuilder + Planner + CapabilityRegistry + Delegator + ResultNormalizer + Aggregator + ConflictResolver + CompletionController + PolicyGuard. Reuses the existing `backend/app/icoder/agent_runtime/orchestrator/` modules where possible.
