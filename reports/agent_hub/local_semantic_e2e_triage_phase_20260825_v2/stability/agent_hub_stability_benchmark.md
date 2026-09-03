# Agent Hub stability benchmark

Generated: `2026-08-24T16:34:14.920320+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **144/144 passed; expected 144**

Pass rate: `1.0`; error rate: `0.0`; P50: `0.212s`; P95: `0.321s`.

Cost coverage: `1.0`; unknown-cost runs: `0`; totals by currency: `{"CNY": {"average": 0.0, "p50": 0.0, "p95": 0.0, "runs": 144, "total": 0.0}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| claim-check | 6 | 1.0 | 0.0 | 0.127 | 0.143 | 1.0 | {"CNY": 0.0} | yes |
| clinical-education | 6 | 1.0 | 0.0 | 0.143 | 0.16 | 1.0 | {"CNY": 0.0} | yes |
| clinical-guidelines | 6 | 1.0 | 0.0 | 0.144 | 0.16 | 1.0 | {"CNY": 0.0} | yes |
| code-validation-agent | 6 | 1.0 | 0.0 | 0.282 | 0.484 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 0.135 | 0.155 | 1.0 | {"CNY": 0.0} | yes |
| denial-appeals | 6 | 1.0 | 0.0 | 0.131 | 0.156 | 1.0 | {"CNY": 0.0} | yes |
| diagnosis-extractor | 6 | 1.0 | 0.0 | 0.188 | 0.507 | 1.0 | {"CNY": 0.0} | yes |
| discharge-edu | 6 | 1.0 | 0.0 | 0.199 | 0.214 | 1.0 | {"CNY": 0.0} | yes |
| discharge-summary-structuring | 6 | 1.0 | 0.0 | 0.192 | 0.212 | 1.0 | {"CNY": 0.0} | yes |
| drg-analyzer | 6 | 1.0 | 0.0 | 0.212 | 0.246 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 0.28 | 0.343 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.219 | 0.234 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.282 | 0.295 | 1.0 | {"CNY": 0.0} | yes |
| icu-summary | 6 | 1.0 | 0.0 | 0.177 | 0.227 | 1.0 | {"CNY": 0.0} | yes |
| med-reconciliation | 6 | 1.0 | 0.0 | 0.203 | 0.226 | 1.0 | {"CNY": 0.0} | yes |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.211 | 0.246 | 1.0 | {"CNY": 0.0} | yes |
| nursing-handoff | 6 | 1.0 | 0.0 | 0.22 | 0.321 | 1.0 | {"CNY": 0.0} | yes |
| principal-diagnosis-review | 6 | 1.0 | 0.0 | 0.209 | 0.258 | 1.0 | {"CNY": 0.0} | yes |
| prior-auth | 6 | 1.0 | 0.0 | 0.198 | 0.244 | 1.0 | {"CNY": 0.0} | yes |
| procedure-extractor | 6 | 1.0 | 0.0 | 0.2 | 0.289 | 1.0 | {"CNY": 0.0} | yes |
| referral-gen | 6 | 1.0 | 0.0 | 0.226 | 0.252 | 1.0 | {"CNY": 0.0} | yes |
| rule-explainer | 6 | 1.0 | 0.0 | 0.295 | 0.359 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.22 | 0.29 | 1.0 | {"CNY": 0.0} | yes |
| triage | 6 | 1.0 | 0.0 | 0.215 | 0.233 | 1.0 | {"CNY": 0.0} | yes |
