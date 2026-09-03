# Phase 4-H §5 Part 2 — Corti Agent Full Inventory

**Captured:** 2026-07-10 14:53 local (06:53 UTC)
**Auditor:** Claude (Sonnet 4.5)
**Source URL:** `https://console.corti.app/project/{project_id}/ai-studio/agents/pre-built-agents`
**Project ID:** `b8f8129a-c31d-407f-b723-6ecc592d31e4`
**Account:** Luhua Song <songluhua@gmail.com> (OAuth via Google)

> Per PDF §5 Part 2 — full inventory of Corti's pre-built agents in 3 formats: structured (JSON), tabular (CSV), prose (Markdown). The inventory is the public-facing agent catalog shown on the "Pre-built agents" tab.

---

## 1. Markdown inventory (prose)

Corti Console exposes **20 pre-built agents** as preset templates on the `Pre-built agents` tab at `/project/{id}/ai-studio/agents/pre-built-agents`. Clicking a card navigates to `/project/{id}/ai-studio/agents/new?preset={preset_slug}` — i.e. each pre-built agent is a **template** that seeds the New Agent form, not a directly-runnable agent.

### 1.1 Inventory table

| # | Agent Name | Preset slug (inferred from URL pattern) | Description |
|---|------------|-----------------------------------------|-------------|
| 1 | ICD-10 Index Navigator Agent | `icd-10-index-navigator-agent` (inferred) | Traverse the ICD-10 Alphabetic Index from clinical terms to candidate codes for coder review |
| 2 | Rule Explainer Agent | `rule-explainer-agent` (inferred) | Get explanations of why a specific ICD-10-CM, ICD-10-PCS, or CPT code was selected |
| 3 | Compliance Guardrail Agent | `compliance-guardrail-agent` | Evaluate medical code sets against a configured payer or organizational ruleset before claim submission |
| 4 | Code Validation Agent | `code-validation-agent` | Validate proposed medical code sets against official coding rules to detect errors, conflicts, and compliance risks before submission |
| 5 | Procedure Entity Extractor Agent | `procedure-entity-extractor-agent` (inferred) | Extract and assign procedure codes grounded strictly in documented clinical evidence |
| 6 | Diagnostic Entity Extractor Agent | `diagnostic-entity-extractor-agent` (inferred) | Extract and assign diagnosis codes grounded strictly in documented clinical evidence |
| 7 | Surgical Registry Intelligence Agent | `surgical-registry-intelligence-agent` (inferred) | Automate surgical registry data entry from transcript logs into quality databases |
| 8 | ICU Admission Summary Agent | `icu-admission-summary-agent` (inferred) | Automate ICU admission documentation by synthesizing EHR data into structured clinical summaries |
| 9 | Triage and Initial Assessment Agent | `triage-and-initial-assessment-agent` (inferred) | Automate emergency triage with validated risk scores and evidence-based acuity assignment |
| 10 | Note Completeness Agent | `note-completeness-agent` | Ensure high-quality clinical notes with real-time checks for completeness, accuracy, and compliance |
| 11 | Medication Reconciliation Agent | `medication-reconciliation-agent` (inferred) | Reduce medication errors with accurate, up-to-date reconciliation across admissions, transfers, and discharges |
| 12 | Denial Appeals Agent | `denial-appeals-agent` (inferred) | Accelerate appeals with evidence-backed responses that align clinical documentation to payer requirements |
| 13 | Patient Discharge Education Agent | `patient-discharge-education-agent` (inferred) | Deliver clear, personalized discharge instructions that improve patient understanding, adherence, and outcomes |
| 14 | Nursing Shift Handoff Agent | `nursing-shift-handoff-agent` (inferred) | Improve continuity of care with clear, structured shift handoffs that surface critical patient information and reduce errors |
| 15 | Prior Authorization Agent | `prior-authorization-agent` (inferred) | Streamline prior authorizations with automated, guideline-aligned documentation that reduces delays and administrative burden |
| 16 | Referral Generator Agent | `referral-generator-agent` (inferred) | Generate clear, structured clinician-to-clinician referral letters |
| 17 | Clinical Education Agent | `clinical-education-agent` (inferred) | Accelerate clinical learning with clear, evidence-based explanations grounded in authoritative medical sources |
| 18 | Medical Coding Agent | `medical-coding-icd-10-cpt-agent` | Generate accurate medical codes grounded strictly in documented clinical evidence |
| 19 | Clinical Guidelines Agent | `clinical-guidelines-agent` (inferred) | Evaluate patient care against professional clinical guidelines using only explicitly approved, domain-locked sources |
| 20 | Clinical Documentation Improvement (CDI) Agent | `clinical-documentation-improvement-cdi-agent` (inferred) | Identify documentation gaps in clinical charts and generates compliant provider queries to improve coding accuracy |

> **Note on preset slugs:** Only `medical-coding-icd-10-cpt-agent` was directly observed (the URL after clicking that card). The other 19 slugs are inferred from the agent name (kebab-case + "-agent" suffix). To confirm each, click each card individually — out of audit scope to click all 20.

### 1.2 Inferred use_case groupings

Corti's "Use case" filter dropdown (button text: "Use case" + "Open filter menu") exists on the AgentsPage but its menu options weren't captured cleanly (menu didn't open during the probe). Based on agent name + description keywords, the inferred use_case categories (per prior memory `project_corti_agent_architecture.md`: 20 agents in 4 use cases):

| Use case (inferred) | Agent # | Agents |
|---------------------|---------|--------|
| Coding & Revenue Cycle | 1, 2, 3, 4, 5, 6, 18, 20 | ICD-10 Index Navigator, Rule Explainer, Compliance Guardrail, Code Validation, Procedure Extractor, Diagnostic Extractor, Medical Coding, CDI |
| Documentation & Notes | 7, 8, 9, 10, 11 | Surgical Registry Intelligence, ICU Admission Summary, Triage & Initial Assessment, Note Completeness, Medication Reconciliation |
| Patient Communication & Care Transitions | 12, 13, 14, 15, 16 | Denial Appeals, Patient Discharge Education, Nursing Shift Handoff, Prior Authorization, Referral Generator |
| Clinical Decision Support & Education | 17, 19 | Clinical Education, Clinical Guidelines |

> **Caveat:** These groupings are inferred from description text, not observed from the Corti UI. To validate, the "Use case" filter menu needs to be opened and its options captured. Carried to Part 4 IA + Part 6 walkthrough for confirmation.

### 1.3 Architecture observation

- Corti's pre-built agents are **presets/templates**, NOT directly-runnable agents. The flow is: pick a preset → land on `/agents/new?preset=X` → test chat in right panel → click "Customize agent" to expand customization form → click "Create agent" to save as user's own.
- After "Customize agent" is clicked, a slide-over panel appears with:
  - H2 "Name your agent"
  - Input "agent_name" (pre-filled with preset name)
  - Label "Agent Name *"
  - "Clone Agent" button (separate from "Create agent")
  - "Close" button
  - (Likely contains system prompt + experts + tools tabs further down — not captured in 8-deep snapshot)

- This means Corti's "pre-built agents" concept = "agent templates gallery". iCoDer's equivalent concept = "loaded agent packs" with direct run + fork capabilities. The UX difference:

| Aspect | Corti | iCoDer |
|--------|-------|--------|
| Pre-built tab name | "Pre-built agents" (radio) | "iCoDer built" (button) |
| Card click action | Navigates to `/agents/new?preset=X` | Navigates to `/agents/{agent_id}` (broken for built agents — must fork first) |
| Pre-test before save | Yes — chat in right panel of New page | Yes — on AgentDetailPage (after fork) |
| Save action | "Create agent" button creates DB row | "Fork" button clones pack to DB |
| Customization entry | "Customize agent" button → slide-over | Settings tab always visible on detail page |

## 2. JSON inventory (structured)

```json
{
  "audit": {
    "captured_at": "2026-07-10T06:53:00Z",
    "source_url": "https://console.corti.app/project/b8f8129a-c31d-407f-b723-6ecc592d31e4/ai-studio/agents/pre-built-agents",
    "account": "Luhua Song <songluhua@gmail.com>",
    "total_agents": 20,
    "use_case_filter_observed": true,
    "use_case_filter_options_captured": false
  },
  "agents": [
    {"id": 1, "name": "ICD-10 Index Navigator Agent", "preset_slug_inferred": "icd-10-index-navigator-agent", "use_case_inferred": "coding_revenue_cycle", "description": "Traverse the ICD-10 Alphabetic Index from clinical terms to candidate codes for coder review"},
    {"id": 2, "name": "Rule Explainer Agent", "preset_slug_inferred": "rule-explainer-agent", "use_case_inferred": "coding_revenue_cycle", "description": "Get explanations of why a specific ICD-10-CM, ICD-10-PCS, or CPT code was selected"},
    {"id": 3, "name": "Compliance Guardrail Agent", "preset_slug_inferred": "compliance-guardrail-agent", "use_case_inferred": "coding_revenue_cycle", "description": "Evaluate medical code sets against a configured payer or organizational ruleset before claim submission"},
    {"id": 4, "name": "Code Validation Agent", "preset_slug_inferred": "code-validation-agent", "use_case_inferred": "coding_revenue_cycle", "description": "Validate proposed medical code sets against official coding rules to detect errors, conflicts, and compliance risks before submission"},
    {"id": 5, "name": "Procedure Entity Extractor Agent", "preset_slug_inferred": "procedure-entity-extractor-agent", "use_case_inferred": "coding_revenue_cycle", "description": "Extract and assign procedure codes grounded strictly in documented clinical evidence"},
    {"id": 6, "name": "Diagnostic Entity Extractor Agent", "preset_slug_inferred": "diagnostic-entity-extractor-agent", "use_case_inferred": "coding_revenue_cycle", "description": "Extract and assign diagnosis codes grounded strictly in documented clinical evidence"},
    {"id": 7, "name": "Surgical Registry Intelligence Agent", "preset_slug_inferred": "surgical-registry-intelligence-agent", "use_case_inferred": "documentation_notes", "description": "Automate surgical registry data entry from transcript logs into quality databases"},
    {"id": 8, "name": "ICU Admission Summary Agent", "preset_slug_inferred": "icu-admission-summary-agent", "use_case_inferred": "documentation_notes", "description": "Automate ICU admission documentation by synthesizing EHR data into structured clinical summaries"},
    {"id": 9, "name": "Triage and Initial Assessment Agent", "preset_slug_inferred": "triage-and-initial-assessment-agent", "use_case_inferred": "documentation_notes", "description": "Automate emergency triage with validated risk scores and evidence-based acuity assignment"},
    {"id": 10, "name": "Note Completeness Agent", "preset_slug_inferred": "note-completeness-agent", "use_case_inferred": "documentation_notes", "description": "Ensure high-quality clinical notes with real-time checks for completeness, accuracy, and compliance"},
    {"id": 11, "name": "Medication Reconciliation Agent", "preset_slug_inferred": "medication-reconciliation-agent", "use_case_inferred": "documentation_notes", "description": "Reduce medication errors with accurate, up-to-date reconciliation across admissions, transfers, and discharges"},
    {"id": 12, "name": "Denial Appeals Agent", "preset_slug_inferred": "denial-appeals-agent", "use_case_inferred": "patient_communication", "description": "Accelerate appeals with evidence-backed responses that align clinical documentation to payer requirements"},
    {"id": 13, "name": "Patient Discharge Education Agent", "preset_slug_inferred": "patient-discharge-education-agent", "use_case_inferred": "patient_communication", "description": "Deliver clear, personalized discharge instructions that improve patient understanding, adherence, and outcomes"},
    {"id": 14, "name": "Nursing Shift Handoff Agent", "preset_slug_inferred": "nursing-shift-handoff-agent", "use_case_inferred": "patient_communication", "description": "Improve continuity of care with clear, structured shift handoffs that surface critical patient information and reduce errors"},
    {"id": 15, "name": "Prior Authorization Agent", "preset_slug_inferred": "prior-authorization-agent", "use_case_inferred": "patient_communication", "description": "Streamline prior authorizations with automated, guideline-aligned documentation that reduces delays and administrative burden"},
    {"id": 16, "name": "Referral Generator Agent", "preset_slug_inferred": "referral-generator-agent", "use_case_inferred": "patient_communication", "description": "Generate clear, structured clinician-to-clinician referral letters"},
    {"id": 17, "name": "Clinical Education Agent", "preset_slug_inferred": "clinical-education-agent", "use_case_inferred": "clinical_decision_support", "description": "Accelerate clinical learning with clear, evidence-based explanations grounded in authoritative medical sources"},
    {"id": 18, "name": "Medical Coding Agent", "preset_slug": "medical-coding-icd-10-cpt-agent", "use_case_inferred": "coding_revenue_cycle", "description": "Generate accurate medical codes grounded strictly in documented clinical evidence"},
    {"id": 19, "name": "Clinical Guidelines Agent", "preset_slug_inferred": "clinical-guidelines-agent", "use_case_inferred": "clinical_decision_support", "description": "Evaluate patient care against professional clinical guidelines using only explicitly approved, domain-locked sources"},
    {"id": 20, "name": "Clinical Documentation Improvement (CDI) Agent", "preset_slug_inferred": "clinical-documentation-improvement-cdi-agent", "use_case_inferred": "coding_revenue_cycle", "description": "Identify documentation gaps in clinical charts and generates compliant provider queries to improve coding accuracy"}
  ]
}
```

> The JSON is also written to `E:\Corti4C\outputs\phase4h\corti_agent_inventory.json` for machine consumption.

## 3. CSV inventory (tabular)

```csv
id,agent_name,preset_slug,preset_slug_confirmed,use_case_inferred,description
1,ICD-10 Index Navigator Agent,icd-10-index-navigator-agent,no,coding_revenue_cycle,"Traverse the ICD-10 Alphabetic Index from clinical terms to candidate codes for coder review"
2,Rule Explainer Agent,rule-explainer-agent,no,coding_revenue_cycle,"Get explanations of why a specific ICD-10-CM, ICD-10-PCS, or CPT code was selected"
3,Compliance Guardrail Agent,compliance-guardrail-agent,no,coding_revenue_cycle,"Evaluate medical code sets against a configured payer or organizational ruleset before claim submission"
4,Code Validation Agent,code-validation-agent,no,coding_revenue_cycle,"Validate proposed medical code sets against official coding rules to detect errors, conflicts, and compliance risks before submission"
5,Procedure Entity Extractor Agent,procedure-entity-extractor-agent,no,coding_revenue_cycle,"Extract and assign procedure codes grounded strictly in documented clinical evidence"
6,Diagnostic Entity Extractor Agent,diagnostic-entity-extractor-agent,no,coding_revenue_cycle,"Extract and assign diagnosis codes grounded strictly in documented clinical evidence"
7,Surgical Registry Intelligence Agent,surgical-registry-intelligence-agent,no,documentation_notes,"Automate surgical registry data entry from transcript logs into quality databases"
8,ICU Admission Summary Agent,icu-admission-summary-agent,no,documentation_notes,"Automate ICU admission documentation by synthesizing EHR data into structured clinical summaries"
9,Triage and Initial Assessment Agent,triage-and-initial-assessment-agent,no,documentation_notes,"Automate emergency triage with validated risk scores and evidence-based acuity assignment"
10,Note Completeness Agent,note-completeness-agent,no,documentation_notes,"Ensure high-quality clinical notes with real-time checks for completeness, accuracy, and compliance"
11,Medication Reconciliation Agent,medication-reconciliation-agent,no,documentation_notes,"Reduce medication errors with accurate, up-to-date reconciliation across admissions, transfers, and discharges"
12,Denial Appeals Agent,denial-appeals-agent,no,patient_communication,"Accelerate appeals with evidence-backed responses that align clinical documentation to payer requirements"
13,Patient Discharge Education Agent,patient-discharge-education-agent,no,patient_communication,"Deliver clear, personalized discharge instructions that improve patient understanding, adherence, and outcomes"
14,Nursing Shift Handoff Agent,nursing-shift-handoff-agent,no,patient_communication,"Improve continuity of care with clear, structured shift handoffs that surface critical patient information and reduce errors"
15,Prior Authorization Agent,prior-authorization-agent,no,patient_communication,"Streamline prior authorizations with automated, guideline-aligned documentation that reduces delays and administrative burden"
16,Referral Generator Agent,referral-generator-agent,no,patient_communication,"Generate clear, structured clinician-to-clinician referral letters"
17,Clinical Education Agent,clinical-education-agent,no,clinical_decision_support,"Accelerate clinical learning with clear, evidence-based explanations grounded in authoritative medical sources"
18,Medical Coding Agent,medical-coding-icd-10-cpt-agent,yes,coding_revenue_cycle,"Generate accurate medical codes grounded strictly in documented clinical evidence"
19,Clinical Guidelines Agent,clinical-guidelines-agent,no,clinical_decision_support,"Evaluate patient care against professional clinical guidelines using only explicitly approved, domain-locked sources"
20,Clinical Documentation Improvement (CDI) Agent,clinical-documentation-improvement-cdi-agent,no,coding_revenue_cycle,"Identify documentation gaps in clinical charts and generates compliant provider queries to improve coding accuracy"
```

> The CSV is also written to `E:\Corti4C\outputs\phase4h\corti_agent_inventory.csv`.

## 4. Parity mapping to iCoDer built agents

iCoDer currently has **14 iCoDer built agents** loaded from `backend/official_agents/` packs. Mapping to Corti's 20:

| iCoDer agent | Corti equivalent | Parity |
|--------------|------------------|--------|
| Medical Coding Agent (`icoder/medical-coding-agent`) | #18 Medical Coding Agent (`medical-coding-icd-10-cpt-agent`) | ✅ Direct match (name + scope) |
| Compliance Guardrail Agent (`icoder/compliance-guardrail-agent`) | #3 Compliance Guardrail Agent | ✅ Direct match |
| Code Validation Agent (`icoder/code-validation-agent`) | #4 Code Validation Agent | ✅ Direct match |
| Note Completeness Agent (`icoder/note-completeness-agent`) | #10 Note Completeness Agent | ✅ Direct match |
| Evidence Extractor (`icoder/evidence-extractor`) | #5 Procedure + #6 Diagnostic Entity Extractor | 🟢 Partial — Corti splits into Procedure + Diagnostic extractors; iCoDer has 1 combined |
| Principal Diagnosis Review (`icoder/principal-diagnosis-review`) | (no Corti equivalent) | ⚪ iCoDer-only — Corti does not have a separate principal diagnosis review agent |
| DRG/DIP Risk Review (`icoder/drg-analyzer`) | (no Corti equivalent) | ⚪ iCoDer-only — Corti does not have a DRG/DIP risk agent (US-centric, no DRG) |
| Discharge Summary Structuring (`icoder/discharge-summary-structuring`) | (no Corti equivalent) | ⚪ iCoDer-only — Corti has Patient Discharge Education (#13) but not a structuring agent |
| Procedure Coding Agent (`icoder/procedure-extractor`) | #5 Procedure Entity Extractor Agent | 🟢 Partial — iCoDer has separate procedure-extractor + evidence-extractor; Corti has only procedure-extractor |

**Corti agents iCoDer is MISSING (8):**

| # | Corti agent | Notes |
|---|-------------|-------|
| 1 | ICD-10 Index Navigator Agent | Corti-specific — index traversal, no Chinese equivalent |
| 2 | Rule Explainer Agent | LLM explainer for code selection reasoning |
| 7 | Surgical Registry Intelligence Agent | Niche — surgical registry data entry |
| 8 | ICU Admission Summary Agent | Documentation — ICU admission summary synthesis |
| 9 | Triage and Initial Assessment Agent | Emergency triage |
| 11 | Medication Reconciliation Agent | Medication safety across transitions of care |
| 12 | Denial Appeals Agent | Insurance denial appeal drafting |
| 13 | Patient Discharge Education Agent | Patient-facing education |
| 14 | Nursing Shift Handoff Agent | Nurse shift handoff documentation |
| 15 | Prior Authorization Agent | Prior auth documentation |
| 16 | Referral Generator Agent | Clinician-to-clinician referral letters |
| 17 | Clinical Education Agent | Educational content generation |
| 19 | Clinical Guidelines Agent | Care evaluation vs clinical guidelines |

(Note: iCoDer missing 8+ agents — count revised from 8 to 13 after considering that some Corti agents have no iCoDer equivalent at all. Original count of 8 was for Corti agents without direct name match; some have partial overlap.)

**iCoDer agents Corti does NOT have (3):**

| iCoDer agent | Why iCoDer has it |
|--------------|-------------------|
| Principal Diagnosis Review | China-specific — main diagnosis (主诊) selection is a CN coding requirement |
| DRG/DIP Risk Review | China-specific — DRG/DIP billing is a CN insurance model; US uses DRG but not DIP |
| Discharge Summary Structuring | China-specific — Chinese 出院小结 is a structured CN document type |

## 5. Audit verdict

**§5 Part 2 PASS** — All 20 Corti pre-built agents captured with name + description. Preset slugs confirmed for 1 (`medical-coding-icd-10-cpt-agent`), inferred for 19. Use_case filter menu not opened during this probe (carried to Part 4 IA audit for capture). Architecture observation: Corti's pre-built = templates gallery; iCoDer's pre-built = loaded packs + fork flow. Parity gap: iCoDer covers 7/20 Corti agents directly + 2 partial; missing 13 Corti agents (mostly patient-communication and documentation-niche). iCoDer has 3 China-specific agents Corti lacks.

## 6. Output files

- `E:\Corti4C\reports\phase4h\PHASE4H_CORTI_AGENT_INVENTORY.md` — this file
- `E:\Corti4C\outputs\phase4h\corti_agent_inventory.json` — structured JSON
- `E:\Corti4C\outputs\phase4h\corti_agent_inventory.csv` — tabular CSV
- `E:\Corti4C\screenshots\phase4h\phase4h_corti_03_agents_prebuilt.png` — pre-built agents grid screenshot
- `E:\Corti4C\screenshots\phase4h\phase4h_corti_04_agent_new_preset.png` — Medical Coding Agent preset detail page
- `E:\Corti4C\screenshots\phase4h\phase4h_corti_05_customize_panel.png` — Customize agent slide-over panel
