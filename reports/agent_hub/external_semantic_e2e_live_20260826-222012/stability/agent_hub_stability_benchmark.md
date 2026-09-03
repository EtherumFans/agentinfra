# Agent Hub stability benchmark

Generated: `2026-08-26T14:30:36.356768+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **155/156 passed; expected 156**

Pass rate: `0.9936`; error rate: `0.0064`; P50: `0.273s`; P95: `4.207s`.

Cost coverage: `0.9936`; unknown-cost runs: `1`; totals by currency: `{"CNY": {"average": 6.126e-05, "p50": 0.0, "p95": 0.0, "runs": 155, "total": 0.00949474}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| claim-check | 6 | 1.0 | 0.0 | 0.428 | 0.711 | 1.0 | {"CNY": 0.0} | yes |
| clinical-documentation-improvement-agent | 6 | 0.8333 | 0.1667 | 19.987 | 27.244 | 0.8333 | {"CNY": 0.00794374} | no |
| clinical-education | 6 | 1.0 | 0.0 | 0.254 | 0.304 | 1.0 | {"CNY": 0.0} | yes |
| clinical-guidelines | 6 | 1.0 | 0.0 | 0.256 | 0.334 | 1.0 | {"CNY": 0.0} | yes |
| code-validation-agent | 6 | 1.0 | 0.0 | 0.338 | 0.384 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 0.211 | 0.293 | 1.0 | {"CNY": 0.0} | yes |
| denial-appeals | 6 | 1.0 | 0.0 | 0.26 | 0.275 | 1.0 | {"CNY": 0.0} | yes |
| diagnosis-extractor | 6 | 1.0 | 0.0 | 0.361 | 0.526 | 1.0 | {"CNY": 0.0} | yes |
| discharge-edu | 6 | 1.0 | 0.0 | 0.223 | 0.244 | 1.0 | {"CNY": 0.0} | yes |
| discharge-summary-structuring | 6 | 1.0 | 0.0 | 0.251 | 0.266 | 1.0 | {"CNY": 0.0} | yes |
| drg-analyzer | 6 | 1.0 | 0.0 | 0.229 | 0.264 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 0.335 | 0.354 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.203 | 0.257 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.336 | 0.429 | 1.0 | {"CNY": 0.0} | yes |
| icu-summary | 6 | 1.0 | 0.0 | 0.225 | 0.319 | 1.0 | {"CNY": 0.0} | yes |
| med-reconciliation | 6 | 1.0 | 0.0 | 0.251 | 0.318 | 1.0 | {"CNY": 0.0} | yes |
| medical-coding-agent | 6 | 1.0 | 0.0 | 3.825 | 4.539 | 1.0 | {"CNY": 0.001551} | yes |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.213 | 0.223 | 1.0 | {"CNY": 0.0} | yes |
| nursing-handoff | 6 | 1.0 | 0.0 | 0.242 | 0.271 | 1.0 | {"CNY": 0.0} | yes |
| principal-diagnosis-review | 6 | 1.0 | 0.0 | 0.256 | 0.592 | 1.0 | {"CNY": 0.0} | yes |
| prior-auth | 6 | 1.0 | 0.0 | 0.223 | 0.275 | 1.0 | {"CNY": 0.0} | yes |
| procedure-extractor | 6 | 1.0 | 0.0 | 0.225 | 1.312 | 1.0 | {"CNY": 0.0} | yes |
| referral-gen | 6 | 1.0 | 0.0 | 0.698 | 2.016 | 1.0 | {"CNY": 0.0} | yes |
| rule-explainer | 6 | 1.0 | 0.0 | 0.58 | 1.586 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.539 | 0.739 | 1.0 | {"CNY": 0.0} | yes |
| triage | 6 | 1.0 | 0.0 | 0.243 | 1.177 | 1.0 | {"CNY": 0.0} | yes |
