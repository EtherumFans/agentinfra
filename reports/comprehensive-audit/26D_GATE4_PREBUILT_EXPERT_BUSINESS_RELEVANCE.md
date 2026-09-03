# 26D — Pre-A0 Gate 4: Prebuilt Expert Business Relevance

> Per spec §16. Classifies each of Corti's 13+1=14 prebuilt experts by business relevance to iCoDer's China hospital pilot product.

## Methodology

- Source list: Corti docs `experts/overview` + Console-discovered AMBOSS = 14 experts total
- Each expert gets: Corti-side description, iCoDer-side status, China hospital relevance, decision
- Decisions per spec §13.2: FOUNDATIONAL_MUST_HAVE, DOMAIN_REQUIRED, PARTNER_INTEGRATION_REQUIRED, PARITY_NICE_TO_HAVE, OUT_OF_CURRENT_SCOPE, DIFFERENT_BY_DESIGN, CORTI_COMING_SOON, NOT_PUBLICLY_VERIFIED, REMOVE_FROM_ICODER

---

## §1. Corti prebuilt expert inventory (verified)

| # | Expert | Category | Corti-side role | Source |
|---|--------|----------|-----------------|--------|
| 1 | Memory | Core toolbox | Persistent context across sessions (RAG-like) | docs + Console |
| 2 | POSOS | Knowledge & clinical reference | Pharmacology / drug interactions | docs |
| 3 | DrugBank | Knowledge & clinical reference | Drug database | docs |
| 4 | PubMed | Knowledge & clinical reference | Biomedical literature search | docs + Console (bound) |
| 5 | Clinical Trials | Knowledge & clinical reference | ClinicalTrials.gov lookup | docs |
| 6 | Web Search | Knowledge & clinical reference | General web search | docs + Console (bound) |
| 7 | Medical Coding (General) | Medical coding | Default coding expert | docs + Console (bound) |
| 8 | ICD-10-CM | Medical coding | US Clinical Modification | docs + Console dropdown |
| 9 | ICD-10-WHO | Medical coding | International WHO variant | docs + Console dropdown |
| 10 | ICD-10-PCS | Medical coding | US Procedure Coding System | docs + Console dropdown |
| 11 | ICD-10-UK | Medical coding | UK NHS variant | docs + Console dropdown |
| 12 | Medical Calculator | Computation | Clinical calculators (BMI, GFR, etc.) | docs + Console (bound) |
| 13 | Interviewing | Computation | Structured interview workflows | docs |
| 14 | AMBOSS | (not in docs list) | Clinical criteria, diagnostic definitions, staging | Discovered in CDI system prompt (Gate 1 §C-04) |

Note: Corti docs claim "5 ICD-10 variants" but Console shows 9 (each variant × Inpatient/Outpatient split). For expert-classification purposes, the 5 standards (CM/WHO/PCS/UK + General) are counted; the inpatient/outpatient split is a setting, not a separate expert.

---

## §2. Per-expert classification

| # | Expert | iCoDer status | China hospital relevance | Decision | Rationale |
|---|--------|---------------|--------------------------|----------|-----------|
| 1 | Memory | ✅ Partial — `app/icoder/agent_runtime/context/` implements context store | HIGH — required for multi-turn agent runs | **FOUNDATIONAL_MUST_HAVE** | Already partially implemented; complete the parity |
| 2 | POSOS | ❌ Not implemented | LOW for coding/CDI focus; MEDIUM if expanded to medication reconciliation | **OUT_OF_CURRENT_SCOPE** | iCoDer focuses on coding/CDI; POSOS is pharmacology — out of scope per CLAUDE.md §产品定位 |
| 3 | DrugBank | ❌ Not implemented | LOW (same as POSOS) | **OUT_OF_CURRENT_SCOPE** | Same rationale as POSOS |
| 4 | PubMed | ❌ Not implemented | MEDIUM — useful for "evidence-based" CDI queries | **PARITY_NICE_TO_HAVE** | iCoDer CDI could cite PubMed for clinical criteria, but not blocking for pilot |
| 5 | Clinical Trials | ❌ Not implemented | LOW for coding/CDI | **OUT_OF_CURRENT_SCOPE** | Not relevant to revenue compliance use case |
| 6 | Web Search | ❌ Not implemented | MEDIUM — useful for guideline lookup | **PARITY_NICE_TO_HAVE** | Could enhance rule_explainer agent; not blocking |
| 7 | Medical Coding (General) | ✅ Implemented — Medical Coding Agent + MedCodER 5-stage | HIGH — this is iCoDer's core entry point | **DOMAIN_REQUIRED** | Already canonical (per Gate 2 §3) |
| 8 | ICD-10-CM | ❌ Not implemented (only ICD-10-CN) | LOW for China hospital pilot | **DIFFERENT_BY_DESIGN** | iCoDer targets CN market; CM is US variant |
| 9 | ICD-10-WHO | ❌ Not implemented | LOW for China hospital pilot | **DIFFERENT_BY_DESIGN** | WHO standard not used in CN hospitals |
| 10 | ICD-10-PCS | ❌ Not implemented | LOW for China hospital pilot | **DIFFERENT_BY_DESIGN** | PCS is US procedure coding; CN uses ICD-9-CM-3 |
| 11 | ICD-10-UK | ❌ Not implemented | LOW for China hospital pilot | **DIFFERENT_BY_DESIGN** | UK variant; irrelevant to CN |
| 12 | Medical Calculator | ❌ Not implemented | MEDIUM — useful for DRG risk scoring | **PARITY_NICE_TO_HAVE** | Could enhance DRG-DIP risk; not blocking |
| 13 | Interviewing | ❌ Not implemented | MEDIUM — useful for CDI Provider Query | **PARITY_NICE_TO_HAVE** | CDI querying is iCoDer's domain; this could augment |
| 14 | AMBOSS | ❌ Not implemented | LOW — German clinical knowledge base | **OUT_OF_CURRENT_SCOPE** | European focus; CN clinical knowledge bases differ |

---

## §3. Decision matrix summary

| Decision | Count | Experts |
|----------|-------|---------|
| FOUNDATIONAL_MUST_HAVE | 1 | Memory |
| DOMAIN_REQUIRED | 1 | Medical Coding (General) |
| PARITY_NICE_TO_HAVE | 4 | PubMed, Web Search, Medical Calculator, Interviewing |
| OUT_OF_CURRENT_SCOPE | 4 | POSOS, DrugBank, Clinical Trials, AMBOSS |
| DIFFERENT_BY_DESIGN | 4 | ICD-10-CM, ICD-10-WHO, ICD-10-PCS, ICD-10-UK |
| PARTNER_INTEGRATION_REQUIRED | 0 | (none) |
| CORTI_COMING_SOON | 0 | (none verified) |
| NOT_PUBLICLY_VERIFIED | 0 | (all 14 verified via docs/Console) |
| REMOVE_FROM_ICODER | 0 | (none) |

---

## §4. iCoDer unique capabilities (no Corti expert equivalent)

These iCoDer capabilities exist without a Corti expert mirror — they are iCoDer ADVANTAGES:

| Capability | iCoDer implementation | Corti equivalent |
|-----------|----------------------|------------------|
| ICD-10-CN (Chinese National) | MedCodER + 37,897 codes + 75,968 synonyms | ❌ Corti has no ICD-10-CN |
| DRG-DIP risk analysis | `app/api/drg.py` + compliance_services/drg_dip_rules.py | ❌ Corti has no DRG-DIP |
| Compliance Rule Engine | compliance_services/rule_engine.py (5 rule_sets) | ❌ Corti has no equivalent in docs |
| Coding Differentiation KB | 2,090 code-pair differentiation decisions | ❌ Not in Corti docs |
| Evidence Anchoring KB | 972 codes × 6,490 evidence patterns | ❌ Not in Corti docs |
| RunHistory + signed trace_url | `run_history` table + trace_token HMAC | ❌ Corti has no signed trace per Gate 1 |
| Patient context isolation events | `patient.context.cleared` / `session.cleared` | ❌ Corti has no equivalent events |

---

## §5. Findings raised in Gate 4

| ID | Severity | Title |
|----|----------|-------|
| **G4-001** | P2 | 4 Corti experts classified OUT_OF_CURRENT_SCOPE (POSOS, DrugBank, Clinical Trials, AMBOSS) — document explicitly so partners don't expect them |
| **G4-002** | P2 | 4 Corti ICD-10 variants classified DIFFERENT_BY_DESIGN — iCoDer remains CN-only by product scope |
| **G4-003** | P3 | 4 Corti experts classified PARITY_NICE_TO_HAVE — backlog for future phases, not blocking pilot |
| **G4-004** | P3 | AMBOSS expert discovered (Gate 1) but not in Corti docs list — Corti's docs are incomplete |

---

## §6. Gate 4 verdict

```
PRE_A0_GATE_4_PREBUILT_EXPERT_BUSINESS_RELEVANCE_COMPLETE
14_EXPERTS_CLASSIFIED (13 docs + 1 discovered)
2_FOUNDATIONAL_OR_DOMAIN_REQUIRED (Memory + Medical Coding)
4_PARITY_NICE_TO_HAVE (PubMed, Web Search, Medical Calculator, Interviewing)
4_OUT_OF_CURRENT_SCOPE (POSOS, DrugBank, Clinical Trials, AMBOSS)
4_DIFFERENT_BY_DESIGN (ICD-10-CM/WHO/PCS/UK)
7_ICODER_UNIQUE_CAPABILITIES_IDENTIFIED (vs 0 Corti equivalents)
0_FORBIDDEN_VERDICTS_CLAIMED
```

Gate 4 closes. Proceed to **Pre-A0 Gate 5 — China Medical Scenario Mapping**.
