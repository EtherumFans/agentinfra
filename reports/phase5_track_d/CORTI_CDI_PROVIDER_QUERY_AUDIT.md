# Gate 2 — Corti CDI Provider Query Compliance Audit

**Date**: 2026-07-11
**Source**: Corti CDI system prompt `<query_guidelines>` + `<constraints>` blocks
**Scope**: Non-leading query contract, compliant vs non-compliant patterns, runtime gate spec

---

## 1. The non-leading query contract (Corti verbatim)

From `clinical-documentation-improvement-cdi-agent` system prompt:

> "All queries must be non-leading, clinically supported, and framed as requests for clarification. Queries must never be designed to upcode or persuade providers toward a particular diagnosis."

> "Do not suggest or imply a specific diagnosis in your queries. Do not use leading language that presumes a particular answer. Do not frame queries in ways that could incentivize upcoding. Do not ask about conditions that have no supporting clinical evidence in the excerpt."

This is **the** compliance invariant. iCoDer Track D Gate 5 implements it as a runtime gate.

## 2. Corti's compliant example (verbatim)

> "Based on the documented elevated creatinine of 2.1 and baseline of 0.9, please clarify the etiology of the acute kidney injury if clinically applicable. Options include: prerenal azotemia, acute tubular necrosis, other etiology, or clinically undetermined at this time."

Anatomy of the compliant query:

| Element | Example value | Why it matters |
|---|---|---|
| Clinical context (from chart) | "elevated creatinine of 2.1 and baseline of 0.9" | Anchors the query in evidence the clinician recognizes |
| Clarification request | "please clarify the etiology" | Open-ended, not yes/no |
| Conditional phrasing | "if clinically applicable" | Gives the clinician permission to defer |
| Response options | 4 options including "clinically undetermined" | Avoids forcing the clinician into a specific bucket |
| Inclusion of escape hatch | "clinically undetermined at this time" | Compliant queries always include an "I don't know" option |

## 3. Corti's non-compliant example (verbatim, must be avoided)

> "Would you agree the patient has acute kidney injury due to sepsis?"

Why this fails (Corti prompt + AHIMA/ACDIS practice):

| Failure mode | Detection signal |
|---|---|
| Yes/no question | starts with "Would you agree" |
| Presumes diagnosis | "has acute kidney injury due to sepsis" |
| Single implied answer | no response options |
| No escape hatch | no "clinically undetermined" option |
| Leading toward etiology | ties AKI to sepsis specifically |

## 4. Non-leading query detection rules (synthesized)

Rule set iCoDer Track D Gate 5 will implement (BLOCKED_LEADING_QUERY gate):

| Rule ID | Pattern | Action |
|---|---|---|
| NLQ-001 | Starts with yes/no trigger ("是不是", "是否", "Would you agree", "Is it", "Are they") | BLOCK |
| NLQ-002 | Names a specific diagnosis in the question body | BLOCK (unless diagnosis is already in the chart verbatim) |
| NLQ-003 | No response options array (`response_options: []` or missing) | BLOCK |
| NLQ-004 | Fewer than 3 response options | BLOCK (single- or two-option queries are inherently leading) |
| NLQ-005 | No escape hatch ("clinically undetermined" / "unable to determine" / "临床不支持" / "无法确定" not in options) | BLOCK |
| NLQ-006 | Treatment advice in query body | BLOCK (constraint #2) |
| NLQ-007 | Diagnosis not in chart appears in query | BLOCK (constraint #4 — evidence binding) |
| NLQ-008 | Single diagnosis suggested as primary answer | BLOCK |
| NLQ-009 | Query mentions payment, DRG weight, CMI, reimbursement | BLOCK (these are red-line terms) |

These 9 rules map to PDF §8.3 Non-leading Query Gate requirements.

## 5. China-localized compliant query example (iCoDer target)

Per Gate 1 `SOLUTION-SCENARIOS.md` rewrite:

```markdown
## 临床澄清任务 (Provider Query)

**query_id**: q_cdi_2026_0711_a3c5
**gap_id**: gap_diagnostic_specificity_pneumonia
**priority**: routine
**status**: DRAFT

### 临床问题
入院记录诊断为"肺炎", 痰培养结果为"肺炎链球菌". 请根据您的临床判断回答:

### 答复选项 (单选, 也允自由文本 / 无法确定 / 临床不支持)
- [ ] A. 肺炎病原体为肺炎链球菌 (J13)
- [ ] B. 肺炎病原体为其他已知病原体 (请在自由文本中说明)
- [ ] C. 痰培养结果为定植菌, 不作为病原体
- [ ] D. 无法确定 (unable to determine)
- [ ] E. 临床不支持 (痰培养结果与临床表现不符)

### 证据 (基于病历原文)
- 入院记录: "诊断: 肺炎" (char 234-240)
- 微生物检验报告: "痰培养: 肺炎链球菌 (3+)" (char 12-32)
```

Anatomy:

| Element | Value | Corti parity |
|---|---|---|
| Clinical context | 入院记录"肺炎" + 痰培养"肺炎链球菌" | ✓ |
| Clarification request | "请根据您的临床判断回答" | ✓ (open-ended) |
| Response options | 5 options including "无法确定" + "临床不支持" | ✓ (>3, escape hatch) |
| Evidence binding | char spans on chart documents | ✓ |
| No diagnosis presumption | query asks about pathogen, does not assert it | ✓ |
| No reimbursement language | no DRG/CMI/支付 terms | ✓ |

## 6. Query lifecycle (PDF §7 spec, Corti-compatible)

```
DRAFT                          AI generates, default state, NOT visible to clinicians
  ↓ (CDI specialist review)
PENDING_CDI_REVIEW             Queued for CDI specialist approval
  ↓ (CDI specialist approves)
APPROVED                       Approved by CDI specialist, ready to send
  ↓ (send to clinician)
SENT_TO_CLINICIAN              Delivered via portal/page/message
  ↓ (clinician opens)
VIEWED                         Clinician acknowledged
  ↓ (clinician responds)
RESPONDED                      Clinician selected an option or wrote free text
  ↓ (clinician updates chart based on response)
DOCUMENTATION_UPDATED          Chart now reflects the clarified fact
  ↓ (CDI re-runs against updated chart)
REVALIDATED                    CDI confirms gap is closed (or new gap raised)
  ↓ (no further action needed)
CLOSED                         Terminal state
```

Side states:

| State | Trigger |
|---|---|
| `CANCELLED` | CDI specialist withdraws before sending |
| `ESCALATED` | Clinician disputes the query (free-text response contradicts) |
| `EXPIRED` | SLA timeout (configurable, default 72h for routine, 24h for urgent) |

## 7. Response option taxonomy (iCoDer target)

iCoDer will standardize response options into 4 categories:

| Category | Example | When to use |
|---|---|---|
| Specific clinical answer | "肺炎病原体为肺炎链球菌 (J13)" | Clinician confirms a specific clinical fact |
| Free text fallback | "其他已知病原体, 请说明" | Catch-all for unlisted answers |
| Colonization / non-pathological | "痰培养结果为定植菌" | Lab result does not equal clinical diagnosis |
| Escape hatches | "无法确定" / "临床不支持" | Required in every query (NLQ-005) |

A query without at least one escape hatch is automatically blocked.

## 8. Compliance reference standards

Corti's prompt does not name a specific compliance standard. iCoDer will explicitly anchor to:

| Standard | Coverage |
|---|---|
| AHIMA/ACDIS "Guidelines for Achieving a Compliant Query Practice" (2022 update) | Non-leading query definition, response option requirements |
| 《病历书写基本规范》(原卫生部 2010) | China clinical documentation requirements |
| 《医疗保障基金结算清单填写规范》(国家医保局 2020) | Insurance settlement documentation |
| 《住院病案首页数据填写质量规范》(国家卫健委 2016) | Front-page quality requirements |

Corti's implicit standard is AHIMA/ACDIS (US). iCoDer's explicit standard is AHIMA/ACDIS + the 3 China standards. This is a **localization for China** property, not a divergence.

## 9. Audit trail per query (iCoDer RunTrace events)

For every Provider Query, the CDI agent emits these trace events:

| Event | When | Required fields |
|---|---|---|
| `query.generated` | After LLM proposes a query | gap_id, query_text, response_options, evidence_spans |
| `query.nlq_gate` | After non-leading gate runs | rule_results{rule_id, passed:bool}, verdict |
| `query.cdi_review` | After CDI specialist reviews | reviewer_id, decision, comment |
| `query.sent` | After delivery to clinician | channel, recipient, sent_at |
| `query.viewed` | After clinician opens | viewed_at |
| `query.responded` | After clinician answers | response_value, free_text, responded_at |
| `query.documentation_updated` | After chart writeback (manual) | document_id, updated_section, char_span |
| `query.revalidated` | After CDI re-run on updated chart | gap_closed:bool, new_gaps[] |
| `query.closed` | On terminal state | close_reason, closed_at |

This audit trail satisfies Corti prompt requirement: "Maintain a complete audit trail so that every conclusion can be traced back to specific evidence in the chart excerpt."

## 10. Leading query detection implementation hint

The non-leading gate will use a hybrid approach:

1. **Lexical rules** (NLQ-001, NLQ-006, NLQ-009): regex on phrases like "是不是", "是否为", "Would you agree", payment terms
2. **Structural rules** (NLQ-003, NLQ-004, NLQ-005): schema validation on `response_options[]` array
3. **Semantic rules** (NLQ-002, NLQ-007, NLQ-008): LLM-as-judge with a focused critic prompt that compares the query text to the chart excerpt and flags diagnosis presumption

Each rule emits a `rule_result` in the trace. Any BLOCK verdict prevents the query from leaving DRAFT state.

## 11. Verdict

`CORTI_PROVIDER_QUERY_CONTRACT_FULLY_CAPTURED`

Corti's compliant vs non-compliant examples plus the 4 constraint block rules give iCoDer a complete spec for the non-leading query gate. The 9 detection rules (NLQ-001 through NLQ-009) are derived from the prompt + AHIMA/ACDIS practice. iCoDer's localization adds the China reference standards and the China-compliant query example.

## 12. Next

Gate 2 continues with `CORTI_CDI_EXPERT_TOOL_TRACE_AUDIT.md` (4 Experts + tool invocation pattern).
