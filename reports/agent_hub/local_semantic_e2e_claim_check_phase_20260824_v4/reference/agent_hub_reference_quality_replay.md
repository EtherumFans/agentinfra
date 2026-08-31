# Agent Hub Pack reference quality replay

Generated: `2026-08-24T08:37:54.018364+00:00`

Scope: Pack-owned synthetic reference semantics; not independent clinical gold.

Result: **18/18 passed; expected 18**

| Agent | Contract/safety | Reference semantics | Outcome |
|---|---:|---:|---|
| claim-check | yes | yes | pack_reference_semantics_passed |
| code-validation-agent | yes | yes | pack_reference_semantics_passed |
| compliance-guardrail-agent | yes | yes | pack_reference_semantics_passed |
| diagnosis-extractor | yes | yes | pack_reference_semantics_passed |
| discharge-edu | yes | yes | pack_reference_semantics_passed |
| discharge-summary-structuring | yes | yes | pack_reference_semantics_passed |
| evidence-extractor | yes | yes | pack_reference_semantics_passed |
| evidence-ranker | yes | yes | pack_reference_semantics_passed |
| icd10-navigator | yes | yes | pack_reference_semantics_passed |
| icu-summary | yes | yes | pack_reference_semantics_passed |
| med-reconciliation | yes | yes | pack_reference_semantics_passed |
| note-completeness-agent | yes | yes | pack_reference_semantics_passed |
| nursing-handoff | yes | yes | pack_reference_semantics_passed |
| prior-auth | yes | yes | pack_reference_semantics_passed |
| procedure-extractor | yes | yes | pack_reference_semantics_passed |
| referral-gen | yes | yes | pack_reference_semantics_passed |
| rule-explainer | yes | yes | pack_reference_semantics_passed |
| surgical-registry | yes | yes | pack_reference_semantics_passed |

## Limitations

- Assertions are maintained against synthetic Pack examples, not independent clinician gold.
- Offline replay does not prove current Provider availability, latency, cost, stability, or Corti parity.
- A fresh live run must be captured separately with a new temporary credential before release evidence can be current.
