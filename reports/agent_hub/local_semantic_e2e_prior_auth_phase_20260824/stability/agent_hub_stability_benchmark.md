# Agent Hub stability benchmark

Generated: `2026-08-24T07:02:30.786199+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **102/102 passed; expected 102**

Pass rate: `1.0`; error rate: `0.0`; P50: `0.243s`; P95: `0.359s`.

Cost coverage: `1.0`; unknown-cost runs: `0`; totals by currency: `{"CNY": {"average": 0.0, "p50": 0.0, "p95": 0.0, "runs": 102, "total": 0.0}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| code-validation-agent | 6 | 1.0 | 0.0 | 0.298 | 0.363 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 0.196 | 0.233 | 1.0 | {"CNY": 0.0} | yes |
| diagnosis-extractor | 6 | 1.0 | 0.0 | 0.293 | 0.46 | 1.0 | {"CNY": 0.0} | yes |
| discharge-edu | 6 | 1.0 | 0.0 | 0.228 | 0.243 | 1.0 | {"CNY": 0.0} | yes |
| discharge-summary-structuring | 6 | 1.0 | 0.0 | 0.224 | 0.251 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 0.32 | 0.33 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.214 | 0.255 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.296 | 0.349 | 1.0 | {"CNY": 0.0} | yes |
| icu-summary | 6 | 1.0 | 0.0 | 0.245 | 0.38 | 1.0 | {"CNY": 0.0} | yes |
| med-reconciliation | 6 | 1.0 | 0.0 | 0.226 | 0.265 | 1.0 | {"CNY": 0.0} | yes |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.237 | 0.371 | 1.0 | {"CNY": 0.0} | yes |
| nursing-handoff | 6 | 1.0 | 0.0 | 0.239 | 0.359 | 1.0 | {"CNY": 0.0} | yes |
| prior-auth | 6 | 1.0 | 0.0 | 0.211 | 0.237 | 1.0 | {"CNY": 0.0} | yes |
| procedure-extractor | 6 | 1.0 | 0.0 | 0.269 | 0.279 | 1.0 | {"CNY": 0.0} | yes |
| referral-gen | 6 | 1.0 | 0.0 | 0.233 | 0.345 | 1.0 | {"CNY": 0.0} | yes |
| rule-explainer | 6 | 1.0 | 0.0 | 0.228 | 0.372 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.197 | 0.321 | 1.0 | {"CNY": 0.0} | yes |
