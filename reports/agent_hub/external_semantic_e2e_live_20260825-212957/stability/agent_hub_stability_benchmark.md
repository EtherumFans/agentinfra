# Agent Hub stability benchmark

Generated: `2026-08-25T13:39:58.419191+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **156/156 passed; expected 156**

Pass rate: `1.0`; error rate: `0.0`; P50: `0.449s`; P95: `4.981s`.

Cost coverage: `0.9615`; unknown-cost runs: `6`; totals by currency: `{"CNY": {"average": 1.022e-05, "p50": 0.0, "p95": 0.0, "runs": 150, "total": 0.001533}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| claim-check | 6 | 1.0 | 0.0 | 0.234 | 0.243 | 1.0 | {"CNY": 0.0} | yes |
| clinical-documentation-improvement-agent | 6 | 1.0 | 0.0 | 24.686 | 28.067 | 0.0 | {} | yes |
| clinical-education | 6 | 1.0 | 0.0 | 0.366 | 0.575 | 1.0 | {"CNY": 0.0} | yes |
| clinical-guidelines | 6 | 1.0 | 0.0 | 0.603 | 0.88 | 1.0 | {"CNY": 0.0} | yes |
| code-validation-agent | 6 | 1.0 | 0.0 | 0.619 | 0.865 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 0.307 | 0.336 | 1.0 | {"CNY": 0.0} | yes |
| denial-appeals | 6 | 1.0 | 0.0 | 0.297 | 0.33 | 1.0 | {"CNY": 0.0} | yes |
| diagnosis-extractor | 6 | 1.0 | 0.0 | 0.428 | 0.598 | 1.0 | {"CNY": 0.0} | yes |
| discharge-edu | 6 | 1.0 | 0.0 | 0.308 | 0.351 | 1.0 | {"CNY": 0.0} | yes |
| discharge-summary-structuring | 6 | 1.0 | 0.0 | 0.293 | 0.326 | 1.0 | {"CNY": 0.0} | yes |
| drg-analyzer | 6 | 1.0 | 0.0 | 0.308 | 0.37 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 0.516 | 0.646 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.335 | 0.446 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.642 | 0.728 | 1.0 | {"CNY": 0.0} | yes |
| icu-summary | 6 | 1.0 | 0.0 | 0.308 | 0.389 | 1.0 | {"CNY": 0.0} | yes |
| med-reconciliation | 6 | 1.0 | 0.0 | 0.286 | 0.294 | 1.0 | {"CNY": 0.0} | yes |
| medical-coding-agent | 6 | 1.0 | 0.0 | 3.902 | 5.599 | 1.0 | {"CNY": 0.001533} | yes |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.376 | 0.449 | 1.0 | {"CNY": 0.0} | yes |
| nursing-handoff | 6 | 1.0 | 0.0 | 0.337 | 0.371 | 1.0 | {"CNY": 0.0} | yes |
| principal-diagnosis-review | 6 | 1.0 | 0.0 | 0.43 | 0.509 | 1.0 | {"CNY": 0.0} | yes |
| prior-auth | 6 | 1.0 | 0.0 | 0.537 | 0.618 | 1.0 | {"CNY": 0.0} | yes |
| procedure-extractor | 6 | 1.0 | 0.0 | 0.631 | 0.667 | 1.0 | {"CNY": 0.0} | yes |
| referral-gen | 6 | 1.0 | 0.0 | 0.513 | 0.587 | 1.0 | {"CNY": 0.0} | yes |
| rule-explainer | 6 | 1.0 | 0.0 | 0.532 | 0.708 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.552 | 0.663 | 1.0 | {"CNY": 0.0} | yes |
| triage | 6 | 1.0 | 0.0 | 0.538 | 0.811 | 1.0 | {"CNY": 0.0} | yes |
