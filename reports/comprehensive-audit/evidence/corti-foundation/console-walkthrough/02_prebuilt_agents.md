# Corti Pre-built Agents — Verified List (Console)

> Source: `https://console.corti.app/project/4c4193c7-.../ai-studio/agents/pre-built-agents`
> Access date: 2026-07-16. Login: Luhua Song. Evidence: `02_prebuilt_agents_full_list.png`.

## Authoritative count: **20 pre-built agents** (not 13 as prior Gate 4/14 reports claimed)

The "13 metadata-only agents" claim from historical Gate 4/14 was about *iCoDer* `official_agents/`. Corti's own pre-built agent count is a different question, and the Console authoritative answer is **20**.

This corrects a classification confusion in Pre-A0 Gate 0 §6: Corti has **20 pre-built AGENTS** and **13 prebuilt EXPERTS**. Agents ≠ Experts. Experts are sub-agents that an Orchestrator calls; Agents are top-level autonomous workflows users can invoke directly.

## Verified pre-built agent inventory

| # | Corti Pre-built Agent | Stated Purpose | iCoDer `official_agents/` mirror |
|---|-----------------------|----------------|----------------------------------|
| 1 | ICD-10 Index Navigator Agent | Traverse the ICD-10 Alphabetic Index from clinical terms to candidate codes for coder review | `icd10_navigator` / `index_navigator` ✅ |
| 2 | Rule Explainer Agent | Get explanations of why a specific ICD-10-CM, ICD-10-PCS, or CPT code was selected | `rule_explainer` ✅ |
| 3 | Compliance Guardrail Agent | Evaluate medical code sets against a configured payer or organizational ruleset before claim submission | `compliance-guardrail` ✅ |
| 4 | Code Validation Agent | Validate proposed medical code sets against official coding rules to detect errors, conflicts, and compliance risks before submission | `code_validation` ✅ |
| 5 | Procedure Entity Extractor Agent | Extract and assign procedure codes grounded strictly in documented clinical evidence | `procedure-extractor` ✅ |
| 6 | Diagnostic Entity Extractor Agent | Extract and assign diagnosis codes grounded strictly in documented clinical evidence | `diagnosis-extractor` ✅ |
| 7 | Surgical Registry Intelligence Agent | Automate surgical registry data entry from transcript logs into quality databases | `surgical_registry` ✅ |
| 8 | ICU Admission Summary Agent | Automate ICU admission documentation by synthesizing EHR data into structured clinical summaries | `icu_summary` ✅ |
| 9 | Triage and Initial Assessment Agent | Automate emergency triage with validated risk scores and evidence-based acuity assignment | `triage` ✅ |
| 10 | Note Completeness Agent | Ensure high-quality clinical notes with real-time checks for completeness, accuracy, and compliance | `note_completeness` ✅ |
| 11 | Medication Reconciliation Agent | Reduce medication errors with accurate, up-to-date reconciliation across admissions, transfers, and discharges | `med_reconciliation` ✅ |
| 12 | Denial Appeals Agent | Accelerate appeals with evidence-backed responses that align clinical documentation to payer requirements | `denial-appeals` ✅ |
| 13 | Patient Discharge Education Agent | Deliver clear, personalized discharge instructions that improve patient understanding, adherence, and outcomes | `discharge_edu` ✅ |
| 14 | Nursing Shift Handoff Agent | Improve continuity of care with clear, structured shift handoffs that surface critical patient information and reduce errors | `nursing_handoff` ✅ |
| 15 | Prior Authorization Agent | Streamline prior authorizations with automated, guideline-aligned documentation that reduces delays and administrative burden | `prior_auth` ✅ |
| 16 | Referral Generator Agent | Generate clear, structured clinician-to-clinician referral letters | `referral_gen` ✅ |
| 17 | Clinical Education Agent | Accelerate clinical learning with clear, evidence-based explanations grounded in authoritative medical sources | ❌ **no iCoDer equivalent** |
| 18 | Medical Coding Agent | Generate accurate medical codes grounded strictly in documented clinical evidence | `medical_coding` / `medcoder-coding-review` ✅ |
| 19 | Clinical Guidelines Agent | Evaluate patient care against professional clinical guidelines using only explicitly approved, domain-locked sources | ❌ **no iCoDer equivalent** |
| 20 | Clinical Documentation Improvement (CDI) Agent | Identify documentation gaps in clinical charts and generates compliant provider queries to improve coding accuracy | `cdi-review` / `clinical-documentation-improvement-agent` / `documentation-gap` ✅ |

## Parity observations

- **18 of 20 Corti pre-built agents** have a direct iCoDer `official_agents/` mirror (some with multiple iCoDer variants).
- **2 Corti agents with no iCoDer equivalent**: Clinical Education Agent, Clinical Guidelines Agent.
- **iCoDer-only agents** (in official_agents/ but not in Corti's prebuilt list): `code_reconciler`, `evidence-ranker`, `evidence_extractor`, `drg-analyzer`, `principal_diagnosis_review`, `discharge_summary_structuring`, `tabular_validator`, `medcoder-coding-review`. Some of these are sub-components of the Medical Coding pipeline (e.g., evidence-ranker + code_reconciler = internal MedCodER stages) rather than top-level agents — which matches Corti's architecture where Medical Coding is a single agent with internal stages.

## Filter UI

- Tab filter "Use case" is the only filter exposed (not category, not expert-type).
- "New Agent" button top-right — confirms Agent CRUD is enabled for the user.
- API Client selector top-right — confirms Agent runs are tied to an API Client credential.
- "$0.000000" inline balance indicator — confirms live cost metering per API Client.

## Critical reverification result

- **HC-4 "13 metadata-only Agents"** — historical claim was about iCoDer `official_agents/` and needs recounting there (Pre-A0 Gate 2 will do this).
- **Corti side**: there are 20 pre-built agents, not the "0 preset agents" some prior docs suggested. Corti DOES ship pre-built agents, not just Experts.
- **iCoDer side**: mirrors 18/20 Corti prebuilt agents + has additional domain-specific variants (DRG analyzer, principal diagnosis, etc.).
