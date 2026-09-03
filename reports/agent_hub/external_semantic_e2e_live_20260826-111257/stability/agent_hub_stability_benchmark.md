# Agent Hub stability benchmark

Generated: `2026-08-26T03:22:39.409580+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **156/156 passed; expected 156**

Pass rate: `1.0`; error rate: `0.0`; P50: `0.443s`; P95: `5.236s`.

Cost coverage: `1.0`; unknown-cost runs: `0`; totals by currency: `{"CNY": {"average": 6.903e-05, "p50": 0.0, "p95": 0.0, "runs": 156, "total": 0.01076906}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| claim-check | 6 | 1.0 | 0.0 | 0.278 | 0.281 | 1.0 | {"CNY": 0.0} | yes |
| clinical-documentation-improvement-agent | 6 | 1.0 | 0.0 | 21.319 | 28.91 | 1.0 | {"CNY": 0.00922306} | yes |
| clinical-education | 6 | 1.0 | 0.0 | 0.303 | 0.33 | 1.0 | {"CNY": 0.0} | yes |
| clinical-guidelines | 6 | 1.0 | 0.0 | 0.307 | 0.333 | 1.0 | {"CNY": 0.0} | yes |
| code-validation-agent | 6 | 1.0 | 0.0 | 0.46 | 0.536 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 0.321 | 0.35 | 1.0 | {"CNY": 0.0} | yes |
| denial-appeals | 6 | 1.0 | 0.0 | 0.338 | 0.349 | 1.0 | {"CNY": 0.0} | yes |
| diagnosis-extractor | 6 | 1.0 | 0.0 | 0.523 | 0.571 | 1.0 | {"CNY": 0.0} | yes |
| discharge-edu | 6 | 1.0 | 0.0 | 0.367 | 0.404 | 1.0 | {"CNY": 0.0} | yes |
| discharge-summary-structuring | 6 | 1.0 | 0.0 | 0.374 | 0.396 | 1.0 | {"CNY": 0.0} | yes |
| drg-analyzer | 6 | 1.0 | 0.0 | 0.408 | 0.442 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 0.601 | 0.624 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.386 | 0.411 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.6 | 0.628 | 1.0 | {"CNY": 0.0} | yes |
| icu-summary | 6 | 1.0 | 0.0 | 0.404 | 0.431 | 1.0 | {"CNY": 0.0} | yes |
| med-reconciliation | 6 | 1.0 | 0.0 | 0.427 | 0.464 | 1.0 | {"CNY": 0.0} | yes |
| medical-coding-agent | 6 | 1.0 | 0.0 | 4.422 | 5.388 | 1.0 | {"CNY": 0.001546} | yes |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.444 | 0.471 | 1.0 | {"CNY": 0.0} | yes |
| nursing-handoff | 6 | 1.0 | 0.0 | 0.453 | 0.465 | 1.0 | {"CNY": 0.0} | yes |
| principal-diagnosis-review | 6 | 1.0 | 0.0 | 0.448 | 0.475 | 1.0 | {"CNY": 0.0} | yes |
| prior-auth | 6 | 1.0 | 0.0 | 0.461 | 0.489 | 1.0 | {"CNY": 0.0} | yes |
| procedure-extractor | 6 | 1.0 | 0.0 | 0.497 | 0.52 | 1.0 | {"CNY": 0.0} | yes |
| referral-gen | 6 | 1.0 | 0.0 | 0.476 | 0.518 | 1.0 | {"CNY": 0.0} | yes |
| rule-explainer | 6 | 1.0 | 0.0 | 0.46 | 0.699 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.455 | 0.491 | 1.0 | {"CNY": 0.0} | yes |
| triage | 6 | 1.0 | 0.0 | 0.438 | 0.46 | 1.0 | {"CNY": 0.0} | yes |
