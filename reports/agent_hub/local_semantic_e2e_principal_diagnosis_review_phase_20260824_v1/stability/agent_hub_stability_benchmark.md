# Agent Hub stability benchmark

Generated: `2026-08-24T13:36:50.631157+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **132/132 passed; expected 132**

Pass rate: `1.0`; error rate: `0.0`; P50: `0.403s`; P95: `0.59s`.

Cost coverage: `1.0`; unknown-cost runs: `0`; totals by currency: `{"CNY": {"average": 0.0, "p50": 0.0, "p95": 0.0, "runs": 132, "total": 0.0}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| claim-check | 6 | 1.0 | 0.0 | 0.327 | 0.441 | 1.0 | {"CNY": 0.0} | yes |
| clinical-education | 6 | 1.0 | 0.0 | 0.344 | 0.364 | 1.0 | {"CNY": 0.0} | yes |
| clinical-guidelines | 6 | 1.0 | 0.0 | 0.351 | 0.637 | 1.0 | {"CNY": 0.0} | yes |
| code-validation-agent | 6 | 1.0 | 0.0 | 0.516 | 0.56 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 0.349 | 0.362 | 1.0 | {"CNY": 0.0} | yes |
| denial-appeals | 6 | 1.0 | 0.0 | 0.351 | 0.367 | 1.0 | {"CNY": 0.0} | yes |
| diagnosis-extractor | 6 | 1.0 | 0.0 | 0.558 | 0.598 | 1.0 | {"CNY": 0.0} | yes |
| discharge-edu | 6 | 1.0 | 0.0 | 0.365 | 0.383 | 1.0 | {"CNY": 0.0} | yes |
| discharge-summary-structuring | 6 | 1.0 | 0.0 | 0.371 | 0.389 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 0.533 | 0.553 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.369 | 0.408 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.586 | 0.597 | 1.0 | {"CNY": 0.0} | yes |
| icu-summary | 6 | 1.0 | 0.0 | 0.369 | 0.406 | 1.0 | {"CNY": 0.0} | yes |
| med-reconciliation | 6 | 1.0 | 0.0 | 0.379 | 0.42 | 1.0 | {"CNY": 0.0} | yes |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.397 | 0.421 | 1.0 | {"CNY": 0.0} | yes |
| nursing-handoff | 6 | 1.0 | 0.0 | 0.391 | 0.451 | 1.0 | {"CNY": 0.0} | yes |
| principal-diagnosis-review | 6 | 1.0 | 0.0 | 0.411 | 0.449 | 1.0 | {"CNY": 0.0} | yes |
| prior-auth | 6 | 1.0 | 0.0 | 0.41 | 0.424 | 1.0 | {"CNY": 0.0} | yes |
| procedure-extractor | 6 | 1.0 | 0.0 | 0.442 | 0.538 | 1.0 | {"CNY": 0.0} | yes |
| referral-gen | 6 | 1.0 | 0.0 | 0.425 | 0.497 | 1.0 | {"CNY": 0.0} | yes |
| rule-explainer | 6 | 1.0 | 0.0 | 0.437 | 0.637 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.426 | 0.432 | 1.0 | {"CNY": 0.0} | yes |
