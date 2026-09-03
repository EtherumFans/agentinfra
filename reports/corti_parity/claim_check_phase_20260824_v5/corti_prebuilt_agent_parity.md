# Corti pre-built Agent parity gate

Generated: `2026-08-24T08:59:21.195696+00:00`

Gate result: **PASS**

## Verified scope

- Catalog mapped: 20/20
- Development verified: 20/20
- China profile declared: 20/20
- Clinical quality verified: 0/20 (external gate)
- Production ready verified: 0/20 (external gate)

> PASS means offline catalog mapping and development engineering gates pass. It does not mean clinical-quality parity or production approval.

## Per-Agent result

| # | Corti Agent | iCoDer Agent | Mapped | Dev | China | Remaining gap |
|---:|---|---|:---:|:---:|:---:|---|
| 1 | ICD-10 Index Navigator | `icd10-navigator` | yes | yes | yes | Corti global coding-system breadth and same-dataset navigation quality are not independently benchmarked. |
| 2 | Rule Explainer | `rule-explainer` | yes | yes | yes | The governed local asset does not contain Includes/Excludes, Code First, Use Additional Code, Code Also, combination/sequencing rules, CPT, ICD-10-CM/PCS or authoritative China payment policy. Authoritative licensed rule assets and an independent coder benchmark remain external gates. |
| 3 | Compliance Guardrail | `compliance-guardrail-agent` | yes | yes | yes | Payer-specific live rules, charge compliance depth and hospital claim integration remain external or incomplete. |
| 4 | Code Validation | `code-validation-agent` | yes | yes | yes | No independent clinical coding accuracy benchmark or production catalog service SLO. |
| 5 | Procedure Entity Extractor | `procedure-extractor` | yes | yes | yes | Only explicit status extraction and unique lexical catalog matches are locally verified; comprehensive procedure normalization, clinical appropriateness, authoritative catalog licensing and representative hospital benchmarking remain open. |
| 6 | Diagnostic Entity Extractor | `diagnosis-extractor` | yes | yes | yes | Only explicit diagnosis labels and explicit suspected/negated/history/family-history states are locally verified. Full-note entity and symptom recall, implied-condition review, combination/sequencing/Excludes/guideline verification, authoritative catalog licensing and real de-identified chart benchmarking remain open. |
| 7 | Surgical Registry Intelligence | `surgical-registry` | yes | yes | yes | No production surgical registry connector or registry-specific validation set. |
| 8 | ICU Admission Summary | `icu-summary` | yes | yes | yes | The local baseline only reorganizes explicitly labelled documented facts. Corti-style EHR/device/MAR/LIS synthesis, institution-configured templates and thresholds, PubMed/DrugBank/Medical Calculator integration, APACHE II/SOFA/GCS calculation, medication screening, approval workflow, longitudinal clinical validation and independent ICU-clinician review remain unavailable or external gates. |
| 9 | Triage and Initial Assessment | `triage` | yes | yes | yes | Cannot be treated as an autonomous triage device; local protocol validation and safety approval are required. |
| 10 | Note Completeness | `note-completeness-agent` | yes | yes | yes | Hospital-template coverage and specialty-specific completeness scoring need local validation. |
| 11 | Medication Reconciliation | `med-reconciliation` | yes | yes | yes | Only exact documented-name alignment and literal allergy matching are available locally. Licensed DrugBank/hospital formulary integration, brand-generic normalization, interaction/contraindication screening, dose suitability, prescribing workflow and independent pharmacist validation remain external gates. |
| 12 | Denial Appeals | `denial-appeals` | yes | yes | yes | Regional payer policies, submission integration and outcome validation remain unavailable. |
| 13 | Patient Discharge Education | `discharge-edu` | yes | yes | yes | The local baseline only reorganizes explicitly labelled verbatim discharge facts. Corti-style patient-friendly medical translation, reading-level and language adaptation, conservative result explanation, medication-change explanation, PubMed/Web Search/Medical Calculator experts, EHR/AVS/patient-portal integration, accessibility/comprehension studies and prospective outcome validation remain unavailable or external gates. |
| 14 | Nursing Shift Handoff | `nursing-handoff` | yes | yes | yes | Local baseline requires explicit labels and does not provide Corti-style free-text/multi-source synthesis, Medical Calculator results, live nursing/MAR/lab integration or prospective nurse handoff safety validation. |
| 15 | Prior Authorization | `prior-auth` | yes | yes | yes | No real-time payer eligibility, policy or submission connector. |
| 16 | Referral Generator | `referral-gen` | yes | yes | yes | No regional referral-platform delivery or closed-loop receipt tracking. |
| 17 | Clinical Education | `clinical-education` | yes | yes | yes | No LMS integration, curriculum governance or learner-outcome validation. |
| 18 | Medical Coding | `medical-coding-agent` | yes | yes | yes | Corti global coding-system breadth and independent same-dataset accuracy/cost/latency parity are unverified. |
| 19 | Clinical Guidelines | `clinical-guidelines` | yes | yes | yes | No governed guideline ingestion/update service or specialty benchmark. |
| 20 | Clinical Documentation Improvement (CDI) | `clinical-documentation-improvement-agent` | yes | yes | yes | Hospital CDI-team acceptance, documentation improvement outcomes and frozen benchmark parity are not complete. |

## External gates

- independent clinical-quality benchmark on representative de-identified records
- real hospital workflow and upstream/downstream integration validation
- security, privacy, regulatory and clinical-governance approval
- production infrastructure, observability, disaster recovery and operations validation
