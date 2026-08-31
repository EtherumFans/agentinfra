# Agent Hub stability benchmark

Generated: `2026-08-25T13:27:09.644658+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **155/156 passed; expected 156**

Pass rate: `0.9936`; error rate: `0.0064`; P50: `0.299s`; P95: `5.269s`.

Cost coverage: `0.9615`; unknown-cost runs: `6`; totals by currency: `{"CNY": {"average": 1.032e-05, "p50": 0.0, "p95": 0.0, "runs": 150, "total": 0.001548}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| claim-check | 6 | 1.0 | 0.0 | 0.203 | 0.218 | 1.0 | {"CNY": 0.0} | yes |
| clinical-documentation-improvement-agent | 6 | 1.0 | 0.0 | 20.296 | 29.194 | 0.0 | {} | yes |
| clinical-education | 6 | 1.0 | 0.0 | 0.134 | 0.244 | 1.0 | {"CNY": 0.0} | yes |
| clinical-guidelines | 6 | 1.0 | 0.0 | 0.148 | 0.279 | 1.0 | {"CNY": 0.0} | yes |
| code-validation-agent | 6 | 1.0 | 0.0 | 0.334 | 0.388 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 0.251 | 0.424 | 1.0 | {"CNY": 0.0} | yes |
| denial-appeals | 6 | 1.0 | 0.0 | 0.219 | 0.287 | 1.0 | {"CNY": 0.0} | yes |
| diagnosis-extractor | 6 | 1.0 | 0.0 | 0.277 | 0.318 | 1.0 | {"CNY": 0.0} | yes |
| discharge-edu | 6 | 1.0 | 0.0 | 0.197 | 0.294 | 1.0 | {"CNY": 0.0} | yes |
| discharge-summary-structuring | 6 | 1.0 | 0.0 | 0.217 | 0.88 | 1.0 | {"CNY": 0.0} | yes |
| drg-analyzer | 6 | 1.0 | 0.0 | 0.22 | 0.263 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 0.298 | 0.45 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.223 | 0.254 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.385 | 0.531 | 1.0 | {"CNY": 0.0} | yes |
| icu-summary | 6 | 1.0 | 0.0 | 0.438 | 0.777 | 1.0 | {"CNY": 0.0} | yes |
| med-reconciliation | 6 | 1.0 | 0.0 | 0.614 | 0.809 | 1.0 | {"CNY": 0.0} | yes |
| medical-coding-agent | 6 | 0.8333 | 0.1667 | 4.439 | 6.806 | 1.0 | {"CNY": 0.001548} | no |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.337 | 0.448 | 1.0 | {"CNY": 0.0} | yes |
| nursing-handoff | 6 | 1.0 | 0.0 | 0.425 | 0.7 | 1.0 | {"CNY": 0.0} | yes |
| principal-diagnosis-review | 6 | 1.0 | 0.0 | 0.378 | 0.425 | 1.0 | {"CNY": 0.0} | yes |
| prior-auth | 6 | 1.0 | 0.0 | 0.368 | 0.614 | 1.0 | {"CNY": 0.0} | yes |
| procedure-extractor | 6 | 1.0 | 0.0 | 0.375 | 0.508 | 1.0 | {"CNY": 0.0} | yes |
| referral-gen | 6 | 1.0 | 0.0 | 0.261 | 0.328 | 1.0 | {"CNY": 0.0} | yes |
| rule-explainer | 6 | 1.0 | 0.0 | 0.285 | 0.706 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.239 | 0.453 | 1.0 | {"CNY": 0.0} | yes |
| triage | 6 | 1.0 | 0.0 | 0.202 | 0.255 | 1.0 | {"CNY": 0.0} | yes |
