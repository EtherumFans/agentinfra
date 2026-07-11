# Corti 20 Agent Deep Inventory (B-1.1)

**Date:** 2026-07-11
**Source:** `https://api.console.corti.app/functions/v1/external/agents` (via authorized account songluhua@gmail.com, project `b8f8129a-c31d-407f-b723-6ecc592d31e4`)
**Raw dump:** `outputs/phase5_track_b/corti_raw/external_agents_experts.json` (195KB)
**Per-agent prompts:** `outputs/phase5_track_b/corti_prompts/*.txt` (20 files, 180KB total)
**List screenshot:** `screenshots/phase5_track_b/corti_00_agents_list.png`

## Key findings (vs Phase 4-H inventory)

| Dimension | Phase 4-H (2026-07-10) | Phase 5 B-1.1 (2026-07-11) | Delta |
|-----------|------------------------|----------------------------|-------|
| Pre-built agents | 20 | 20 | 0 (stable) |
| Experts | 13 | **22** | **+9 (Coming Soon experts added)** |
| Use cases / categories | 4 inferred | 4 confirmed (named) | Categories now officially named |
| Agents with system prompt exposed | unknown | **20/20** (3-16KB each) | New API surface |
| Agent × expert wiring | unknown | **20/20** wired (except `referral-generator-agent`) | Pure-LLM agent confirmed |

**Biggest delta:** Corti published **9 new "Coming Soon" experts** for non-US coding systems:
- **CCAM** (France surgical)
- **OPS** (Germany surgical)
- **OPCS-4** (UK NHS surgical)
- **CIM-10-FR Outpatient** (France)
- **CIM-10-FR Inpatient** (France)
- **ICD-10-GM Outpatient** (Germany)
- **ICD-10-GM Inpatient** (Germany)
- **CPOE Recommendations** (Clinical Evidence)
- **Checklist** (Clinical Evidence)

Corti is doubling down on **EU + UK expansion**. None of these experts have working MCP servers yet — they're announced but not yet operational. **Strategic implication for iCoDer**: China localization (ICD-10-CN / ICD-9-CM-3 / DRG / DIP) is a parallel track iCoDer already has — Corti has not entered China coding systems yet.

## 4 Official categories (not inferred)

Corti groups agents into 4 official "categories" (previously inferred as "use cases"):

| Category | Count | iCoDer equivalent |
|----------|-------|-------------------|
| Coding and Revenue Cycle | 10 | medical-coding / icd10-navigator / rule-explainer / compliance-guardrail / code-validation / procedure-extractor / diagnosis-extractor / denial-appeals / prior-auth / CDI |
| Point of Care Tools | 4 | note-completeness / icu-summary / triage / med-reconciliation |
| Clinical Evidence and Research | 3 | clinical-education / clinical-guidelines / surgical-registry |
| Care Coordination | 3 | discharge-edu / nursing-handoff / referral-gen |

**iCoDer mapping** is direct 1:1 by name. The seed.py 16 agents align with these 4 categories.

## 20 Agent Inventory

### Coding and Revenue Cycle (10)

| # | Agent ID | Name | Experts | Prompt (chars) | iCoDer match |
|---|----------|------|---------|----------------|--------------|
| 1 | icd-10-index-navigator-agent | ICD-10 Index Navigator | coding-expert | 8,403 | icd10-navigator |
| 2 | rule-explainer-agent | Rule Explainer | coding-expert | 11,274 | rule-explainer |
| 3 | compliance-guardrail-agent | Compliance Guardrail | coding-expert | 13,824 | compliance-guardrail |
| 4 | code-validation-agent | Code Validation | coding-expert | 8,662 | code-validation |
| 5 | procedure-entity-extractor-agent | Procedure Entity Extractor | coding-expert | 16,387 | procedure-entity-extractor |
| 6 | diagnostic-entity-extractor-agent | Diagnostic Entity Extractor | coding-expert | 14,119 | diagnosis-extractor |
| 7 | denial-appeals-agent | Denial Appeals | coding-expert, pubmed-expert, web-search-expert | 7,698 | denial-appeals |
| 8 | prior-authorization-agent | Prior Authorization | web-search-expert, medical-calculator-expert, coding-expert, pubmed-expert | 7,898 | prior-auth |
| 9 | medical-coding-icd-10-cpt-agent | **Medical Coding Agent** | coding-expert, pubmed-expert, web-search-expert, medical-calculator-expert | 5,539 | icoder/medical-coding-agent |
| 10 | clinical-documentation-improvement-cdi-agent | Clinical Documentation Improvement | pubmed-expert, web-search-expert, medical-calculator-expert, coding-expert | 6,238 | (none in seed.py — **iCoDer gap**) |

### Point of Care Tools (4)

| # | Agent ID | Name | Experts | Prompt (chars) | iCoDer match |
|---|----------|------|---------|----------------|--------------|
| 11 | note-completeness-agent | Note Completeness | coding-expert | 5,828 | note-completeness |
| 12 | icu-admission-summary-agent | ICU Admission Summary | pubmed-expert, medical-calculator-expert, drugbank-expert | 8,825 | icu-summary |
| 13 | triage-and-initial-assessment-agent | Triage and Initial Assessment | pubmed-expert, interviewing-expert, medical-calculator-expert, drugbank-expert | 3,059 | triage |
| 14 | medication-reconciliation-agent | Medication Reconciliation | medical-calculator-expert, web-search-expert, drugbank-expert | 5,571 | med-reconciliation |

### Clinical Evidence and Research (3)

| # | Agent ID | Name | Experts | Prompt (chars) | iCoDer match |
|---|----------|------|---------|----------------|--------------|
| 15 | surgical-registry-intelligence-agent | Surgical Registry Intelligence | pubmed-expert, coding-expert, drugbank-expert | 9,411 | surgical-registry |
| 16 | clinical-education-agent | Clinical Education | web-search-expert, pubmed-expert, medical-calculator-expert | 9,603 | (none — **iCoDer gap**) |
| 17 | clinical-guidelines-agent | Clinical Guidelines | web-search-expert | 9,811 | (none — **iCoDer gap**) |

### Care Coordination (3)

| # | Agent ID | Name | Experts | Prompt (chars) | iCoDer match |
|---|----------|------|---------|----------------|--------------|
| 18 | patient-discharge-education-agent | Patient Discharge Education | medical-calculator-expert, web-search-expert, pubmed-expert | 5,804 | discharge-edu |
| 19 | nursing-shift-handoff-agent | Nursing Shift Handoff | medical-calculator-expert | 5,939 | nursing-handoff |
| 20 | referral-generator-agent | Referral Generator | **(none — pure LLM)** | 6,236 | referral-gen |

## 22 Expert Inventory

### Coding and Revenue Cycle (13)

| Expert ID | Status | Region / Coding system | iCoDer equivalent |
|-----------|--------|------------------------|-------------------|
| coding-expert | Live | Global (main) | icoder-coding-expert |
| coding-expert-icd-10-cm | Live | US ICD-10-CM | (iCoDer has ICD-10-CN, not CM) |
| coding-expert-icd-10-pcs | Live | US ICD-10-PCS | (iCoDer has ICD-9-CM-3, not PCS) |
| coding-expert-icd-10-int | Live | International ICD-10 | — |
| coding-expert-icd-10-uk | Live | UK ICD-10 | — |
| ccam-coding-expert | **Coming Soon** | France CCAM surgical | — |
| ops-coding-expert | **Coming Soon** | Germany OPS surgical | — |
| opcs-4-coding-expert | **Coming Soon** | UK OPCS-4 surgical | — |
| cim-10-fr-outpatient-coding-expert | **Coming Soon** | France CIM-10 outpatient | — |
| cim-10-fr-inpatient-coding-expert | **Coming Soon** | France CIM-10 inpatient | — |
| icd-10-gm-outpatient-coding-expert | **Coming Soon** | Germany ICD-10-GM outpatient | — |
| icd-10-gm-inpatient-coding-expert | **Coming Soon** | Germany ICD-10-GM inpatient | — |

### Clinical Evidence and Research (7)

| Expert ID | Status | iCoDer equivalent |
|-----------|--------|-------------------|
| memory-expert | Live | (iCoDer Memory provider — partial) |
| pubmed-expert | Live | (iCoDer gap — no PubMed MCP) |
| posos-expert | Live | (iCoDer gap — no Posos MCP) |
| drugbank-expert | Live | (iCoDer gap — no DrugBank MCP) |
| clinical-trials-expert | Live | (iCoDer gap — no ClinicalTrials.gov MCP) |
| web-search-expert | Live | (iCoDer has web search via provider) |
| cpoe-recommendations-expert | **Coming Soon** | (iCoDer gap) |
| checklist-expert | **Coming Soon** | (iCoDer gap) |

### Point of Care Tools (1)

| Expert ID | Status | iCoDer equivalent |
|-----------|--------|-------------------|
| medical-calculator-expert | Live | (iCoDer gap — no Medical Calculator MCP) |

### Care Coordination (1)

| Expert ID | Status | iCoDer equivalent |
|-----------|--------|-------------------|
| interviewing-expert | Live | (iCoDer gap — no Interviewing MCP) |

**Summary**: 22 experts total = 13 live + 9 Coming Soon. iCoDer has 1 partial (memory) + 1 parallel (web search). **iCoDer lags significantly on Expert library** (1/13 live = 8% coverage).

## Agent runtime permission check

**Findings from clicking first agent (icd-10-index-navigator-agent):**
- Clicking a pre-built agent card navigates to `/agents/new?preset=icd-10-index-navigator-agent` — i.e., Corti's UI **always creates a new agent from preset** (no "view detail" for pre-built)
- The "Customize agent" button on the preset detail page is what forks
- Chat is available WITHOUT forking — user can chat with the preset directly

**iCoDer comparison**: iCoDer separates "view detail" from "fork" — user can browse an agent's full definition (system prompt, experts, tools, code) WITHOUT creating an instance. This is an **iCoDer advantage** for transparency / developer experience.

## Permission limitations (PASS_WITH_CORTI_PERMISSION_LIMITATIONS evidence)

- **Cannot fork without consuming credits**: chat consumes credits per message
- **No direct "view Agent Card" for pre-builts**: must infer from system prompt + expert wiring (we have via /external/agents)
- **No MCP server config exposed**: expert_inventory.json from Phase 4-H captured 2/13 with MCP servers (posos, drugbank); other 11 experts have hidden/no MCP bindings
- **Cannot create test runs for all 20 agents**: would consume significant credits ($48.69 balance; per-message cost ~$0.001-0.01). Strategy: only smoke-run the 5 B-1.4 deep-dive targets

## What's NOT in B-1.1 (deferred to B-1.4)

- Per-agent screenshots (would require 20 clicks × 3 tabs = 60+ screenshots; not high-value at inventory level)
- Per-agent smoke runs (credits + time; reserved for B-1.4 5-pair deep audit)
- Network observation per agent (deferred to B-1.4)
- Settings tab content (Configuration schema — needs fork; deferred to B-1.4)

## Recommendations

1. **iCoDer Expert library gap is the #1 P0** for Track B Gap Backlog. iCoDer should build/populate 5+ experts (PubMed, DrugBank, Medical Calculator, ClinicalTrials, Interviewing) — even as MCP stubs.
2. **iCoDer should preserve its "view detail without fork" advantage** — don't blindly copy Corti's "click = fork" pattern.
3. **9 "Coming Soon" experts are strategic warning** — Corti is moving into EU/UK. iCoDer should accelerate CN coding expert (ICD-10-CN, ICD-9-CM-3, DRG, DIP) before Corti announces China entry.
4. **3 Corti agents with no iCoDer match** (CDI / Clinical Education / Clinical Guidelines) — these are P1 candidates for iCoDer to build.

## Status

**B-1.1 complete.** Move to B-1.2 (iCoDer runtime inventory) which requires starting dev server.
