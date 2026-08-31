# Agent Hub stability benchmark

Generated: `2026-08-26T04:11:51.193174+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **156/156 passed; expected 156**

Pass rate: `1.0`; error rate: `0.0`; P50: `0.774s`; P95: `4.991s`.

Cost coverage: `1.0`; unknown-cost runs: `0`; totals by currency: `{"CNY": {"average": 8.199e-05, "p50": 0.0, "p95": 0.0, "runs": 156, "total": 0.0127908}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| claim-check | 6 | 1.0 | 0.0 | 0.611 | 1.232 | 1.0 | {"CNY": 0.0} | yes |
| clinical-documentation-improvement-agent | 6 | 1.0 | 0.0 | 27.196 | 36.104 | 1.0 | {"CNY": 0.0112168} | yes |
| clinical-education | 6 | 1.0 | 0.0 | 1.579 | 2.166 | 1.0 | {"CNY": 0.0} | yes |
| clinical-guidelines | 6 | 1.0 | 0.0 | 1.853 | 2.164 | 1.0 | {"CNY": 0.0} | yes |
| code-validation-agent | 6 | 1.0 | 0.0 | 2.255 | 4.11 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 1.329 | 1.529 | 1.0 | {"CNY": 0.0} | yes |
| denial-appeals | 6 | 1.0 | 0.0 | 1.391 | 1.658 | 1.0 | {"CNY": 0.0} | yes |
| diagnosis-extractor | 6 | 1.0 | 0.0 | 1.993 | 2.568 | 1.0 | {"CNY": 0.0} | yes |
| discharge-edu | 6 | 1.0 | 0.0 | 1.28 | 1.663 | 1.0 | {"CNY": 0.0} | yes |
| discharge-summary-structuring | 6 | 1.0 | 0.0 | 1.22 | 1.37 | 1.0 | {"CNY": 0.0} | yes |
| drg-analyzer | 6 | 1.0 | 0.0 | 0.752 | 2.078 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 1.244 | 1.599 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.931 | 1.536 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.755 | 0.777 | 1.0 | {"CNY": 0.0} | yes |
| icu-summary | 6 | 1.0 | 0.0 | 0.36 | 0.499 | 1.0 | {"CNY": 0.0} | yes |
| med-reconciliation | 6 | 1.0 | 0.0 | 0.371 | 0.422 | 1.0 | {"CNY": 0.0} | yes |
| medical-coding-agent | 6 | 1.0 | 0.0 | 4.151 | 5.063 | 1.0 | {"CNY": 0.001574} | yes |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.389 | 0.411 | 1.0 | {"CNY": 0.0} | yes |
| nursing-handoff | 6 | 1.0 | 0.0 | 0.368 | 0.392 | 1.0 | {"CNY": 0.0} | yes |
| principal-diagnosis-review | 6 | 1.0 | 0.0 | 0.403 | 0.409 | 1.0 | {"CNY": 0.0} | yes |
| prior-auth | 6 | 1.0 | 0.0 | 0.4 | 0.411 | 1.0 | {"CNY": 0.0} | yes |
| procedure-extractor | 6 | 1.0 | 0.0 | 0.429 | 0.498 | 1.0 | {"CNY": 0.0} | yes |
| referral-gen | 6 | 1.0 | 0.0 | 0.41 | 0.435 | 1.0 | {"CNY": 0.0} | yes |
| rule-explainer | 6 | 1.0 | 0.0 | 0.412 | 0.604 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.406 | 0.415 | 1.0 | {"CNY": 0.0} | yes |
| triage | 6 | 1.0 | 0.0 | 0.418 | 0.444 | 1.0 | {"CNY": 0.0} | yes |
