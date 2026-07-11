# Agent Mapping Report (B-1.3)

**Date:** 2026-07-11
**Source data:** `outputs/phase5_track_b/agent_mapping.json`
**Corti inventory:** 20 agents (from B-1.1)
**iCoDer inventory:** 14 agents (from B-1.2)

## Mapping summary

| Class | Count | Coverage |
|-------|-------|----------|
| **EXACT_MATCH** | 5 | Direct 1:1 name+purpose, both runnable |
| **PARTIAL_MATCH** | 3 | Same purpose but iCoDer metadata-only OR significant scope diff |
| **COMPOSITE_MATCH** | 0 | (No Corti multi-agent that maps to iCoDer single, or vice versa) |
| **CORTI_ONLY** | 11 | Corti has agent, iCoDer has no runnable equivalent |
| **ICODER_ONLY** | 5 | iCoDer has agent, Corti has no direct equivalent |
| **NO_VALID_MAPPING** | 0 | — |

**Total mappings:** 24 (5 + 3 + 11 + 5 = 24 mapping entries; some Corti agents stay unmatched)

**Coverage of Corti 20 agents:**
- Matched (EXACT + PARTIAL + COMPOSITE): **8/20 = 40%**
- Unmatched (CORTI_ONLY): **11/20 = 55%**
- Composite / No valid: 0/20 = 0%

**Coverage of iCoDer 14 agents:**
- Matched (EXACT + PARTIAL): **8/14 = 57%**
- iCoDer-only: **5/14 = 36%**
- 1 iCoDer agent (medcoder-coding-review in A2A cards) was not in hub — internal engine

## 1. EXACT_MATCH (5 pairs → B-1.4 deep audit targets)

These 5 are the deep-audit candidates for B-1.4:

| # | Corti agent | iCoDer agent | Confidence | Why exact |
|---|-------------|--------------|------------|-----------|
| 001 | medical-coding-icd-10-cpt-agent | medical-coding-agent | High | Both main coding agent; iCoDer adds medcoder_deep mode + ICD-10-CN |
| 002 | procedure-entity-extractor-agent | procedure-extractor | High | Same purpose (ICD-9-CM-3 / ICD-10-PCS extraction); both runnable |
| 003 | code-validation-agent | code-validation-agent | High | Same name; both LLMWithTools style; iCoDer has 4 MCP tools vs Corti's coding-expert |
| 004 | compliance-guardrail-agent | compliance-guardrail-agent | High | Same name; both rule-engine + LLM; iCoDer adds MedicalCodingRuleSet |
| 005 | note-completeness-agent | note-completeness-agent | High | Same name; both check 病历书写基本规范; iCoDer maturity=runnable |

**Original B-1.4 plan was**: Medical Coding / Evidence Extractor / DRG Analyzer / Discharge Structuring / Code Validation.
**Revised based on mapping**: Medical Coding / Procedure Extractor / Code Validation / Compliance Guardrail / Note Completeness.

**Rationale:** Evidence Extractor / DRG Analyzer / Discharge Structuring are ICODER_ONLY (no Corti equivalent for direct comparison). Replacing with 5 EXACT_MATCH pairs gives symmetric Corti↔iCoDer data on both sides. Original plan didn't have this mapping data.

**Recommendation:** Confirm with user whether to (a) stick with original 5 (1 EXACT + 4 ICODER_ONLY) or (b) switch to 5 EXACT pairs. (a) shows iCoDer's unique value; (b) gives deeper Corti comparison.

## 2. PARTIAL_MATCH (3 pairs)

| # | Corti agent | iCoDer agent | Why partial |
|---|-------------|--------------|-------------|
| 006 | diagnostic-entity-extractor-agent | diagnosis-extractor | iCoDer is metadata-only; Corti is runnable |
| 007 | denial-appeals-agent | denial-appeals | iCoDer is metadata-only; Corti has 3 experts |
| 008 | clinical-documentation-improvement-cdi-agent | cdi-review | iCoDer is metadata-only; Corti has 4 experts |

**Action:** Promote these 3 iCoDer agents from metadata-only to runnable. They already have declared intent + 6 default MCP tools.

## 3. CORTI_ONLY (11 Corti agents with no iCoDer runnable equivalent)

| # | Corti agent | iCoDer seed.py declares? | Reason |
|---|-------------|--------------------------|--------|
| 1 | icd-10-index-navigator-agent | YES (icd10-navigator) | seed.py declares, runtime missing |
| 2 | rule-explainer-agent | YES (rule-explainer) | seed.py declares, runtime missing |
| 3 | surgical-registry-intelligence-agent | YES (surgical-registry) | seed.py declares, runtime missing |
| 4 | icu-admission-summary-agent | YES (icu-summary) | seed.py declares, runtime missing |
| 5 | triage-and-initial-assessment-agent | YES (triage) | seed.py declares, runtime missing |
| 6 | medication-reconciliation-agent | YES (med-reconciliation) | seed.py declares, runtime missing |
| 7 | patient-discharge-education-agent | YES (discharge-edu) | seed.py declares, runtime missing |
| 8 | nursing-shift-handoff-agent | YES (nursing-handoff) | seed.py declares, runtime missing |
| 9 | prior-authorization-agent | YES (prior-auth) | seed.py declares, runtime missing |
| 10 | referral-generator-agent | YES (referral-gen) | seed.py declares, runtime missing |
| 11 | clinical-education-agent | NO | iCoDer has no equivalent at all |
| 12 | clinical-guidelines-agent | NO | iCoDer has no equivalent at all |

**Action:** 
- For 1-10: Wire seed.py agents into runtime (10 agents blocked by GAP-13-02 from B-1.2)
- For 11-12: Decision required — build OR explicitly decide not to build

## 4. ICODER_ONLY (5 iCoDer agents with no Corti equivalent)

| # | iCoDer agent | Status | Strategic value |
|---|--------------|--------|-----------------|
| 1 | drg-analyzer | runnable | **HIGH** — Corti has no DRG/DIP; China-specific (CN-DRG + DIP) |
| 2 | principal-diagnosis-review | runnable | **HIGH** — Corti bundles into Medical Coding; standalone is cleaner |
| 3 | discharge-summary-structuring | runnable | **MEDIUM** — Corti CDI is closest but different scope |
| 4 | evidence-extractor | runnable | **HIGH** — Corti bundles into coding-expert; standalone enables reuse |
| 5 | evidence-ranker | metadata-only | **LOW** — internal utility, may stay internal |

**Recommendation:** Preserve 1-4 as iCoDer advantages. evidence-ranker may merge into other agents.

## 5. Composite / No valid mapping

**0 cases.** No Corti multi-agent maps to iCoDer single agent or vice versa.

## 6. Implications for B-1.4 deep audit

Given the mapping:
- **5 EXACT pairs** are the natural deep-audit set (symmetric data on both sides)
- **3 PARTIAL pairs** can be card-level only (iCoDer side is metadata-only)
- **11 CORTI_ONLY** can be card-level on Corti side only
- **5 ICODER_ONLY** can be card-level on iCoDer side only

**B-1.4 estimated effort:** 5 deep pairs × 1-1.5h = 5-7.5h. Add 9 card-level pairs × 15min = 2.25h. Total 7-10h.

## 7. Decision needed

Should B-1.4 deep audit use:
- (a) Original plan: Medical Coding / Evidence Extractor / DRG Analyzer / Discharge Structuring / Code Validation (1 EXACT + 4 ICODER_ONLY)
- (b) Revised: 5 EXACT_MATCH pairs (Medical Coding / Procedure / Code Validation / Compliance / Note Completeness)
- (c) Hybrid: 3 EXACT + 2 ICODER_ONLY (Medical Coding / Code Validation / Note Completeness + DRG Analyzer / Evidence Extractor)

Recommendation: **(c) Hybrid** — preserves the iCoDer advantage showcase while ensuring Corti symmetric comparison.
