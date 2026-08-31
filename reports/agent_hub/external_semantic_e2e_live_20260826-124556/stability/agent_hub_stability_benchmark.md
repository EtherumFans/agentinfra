# Agent Hub stability benchmark

Generated: `2026-08-26T04:55:51.443629+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **156/156 passed; expected 156**

Pass rate: `1.0`; error rate: `0.0`; P50: `0.465s`; P95: `3.672s`.

Cost coverage: `1.0`; unknown-cost runs: `0`; totals by currency: `{"CNY": {"average": 7.084e-05, "p50": 0.0, "p95": 0.0, "runs": 156, "total": 0.0110504}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| claim-check | 6 | 1.0 | 0.0 | 1.143 | 1.494 | 1.0 | {"CNY": 0.0} | yes |
| clinical-documentation-improvement-agent | 6 | 1.0 | 0.0 | 20.089 | 28.98 | 1.0 | {"CNY": 0.0095004} | yes |
| clinical-education | 6 | 1.0 | 0.0 | 0.443 | 0.588 | 1.0 | {"CNY": 0.0} | yes |
| clinical-guidelines | 6 | 1.0 | 0.0 | 0.396 | 0.483 | 1.0 | {"CNY": 0.0} | yes |
| code-validation-agent | 6 | 1.0 | 0.0 | 0.593 | 0.805 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 0.264 | 0.276 | 1.0 | {"CNY": 0.0} | yes |
| denial-appeals | 6 | 1.0 | 0.0 | 0.32 | 0.574 | 1.0 | {"CNY": 0.0} | yes |
| diagnosis-extractor | 6 | 1.0 | 0.0 | 0.52 | 0.927 | 1.0 | {"CNY": 0.0} | yes |
| discharge-edu | 6 | 1.0 | 0.0 | 0.375 | 0.429 | 1.0 | {"CNY": 0.0} | yes |
| discharge-summary-structuring | 6 | 1.0 | 0.0 | 0.39 | 0.894 | 1.0 | {"CNY": 0.0} | yes |
| drg-analyzer | 6 | 1.0 | 0.0 | 0.457 | 0.854 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 0.402 | 0.668 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.237 | 0.246 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.404 | 0.524 | 1.0 | {"CNY": 0.0} | yes |
| icu-summary | 6 | 1.0 | 0.0 | 0.253 | 0.352 | 1.0 | {"CNY": 0.0} | yes |
| med-reconciliation | 6 | 1.0 | 0.0 | 0.288 | 0.424 | 1.0 | {"CNY": 0.0} | yes |
| medical-coding-agent | 6 | 1.0 | 0.0 | 3.556 | 3.916 | 1.0 | {"CNY": 0.00155} | yes |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.289 | 0.386 | 1.0 | {"CNY": 0.0} | yes |
| nursing-handoff | 6 | 1.0 | 0.0 | 0.397 | 0.474 | 1.0 | {"CNY": 0.0} | yes |
| principal-diagnosis-review | 6 | 1.0 | 0.0 | 0.496 | 0.904 | 1.0 | {"CNY": 0.0} | yes |
| prior-auth | 6 | 1.0 | 0.0 | 0.48 | 0.732 | 1.0 | {"CNY": 0.0} | yes |
| procedure-extractor | 6 | 1.0 | 0.0 | 0.538 | 0.811 | 1.0 | {"CNY": 0.0} | yes |
| referral-gen | 6 | 1.0 | 0.0 | 0.776 | 1.069 | 1.0 | {"CNY": 0.0} | yes |
| rule-explainer | 6 | 1.0 | 0.0 | 0.516 | 1.228 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.535 | 0.697 | 1.0 | {"CNY": 0.0} | yes |
| triage | 6 | 1.0 | 0.0 | 0.488 | 0.76 | 1.0 | {"CNY": 0.0} | yes |
