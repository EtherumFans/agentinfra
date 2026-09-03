# Agent Hub stability benchmark

Generated: `2026-08-24T00:01:32.950075+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **60/60 passed; expected 60**

Pass rate: `1.0`; error rate: `0.0`; P50: `0.206s`; P95: `0.296s`.

Cost coverage: `1.0`; unknown-cost runs: `0`; totals by currency: `{"CNY": {"average": 0.0, "p50": 0.0, "p95": 0.0, "runs": 60, "total": 0.0}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| code-validation-agent | 6 | 1.0 | 0.0 | 0.258 | 0.339 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 0.166 | 0.199 | 1.0 | {"CNY": 0.0} | yes |
| diagnosis-extractor | 6 | 1.0 | 0.0 | 0.264 | 0.271 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 0.248 | 0.331 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.181 | 0.205 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.27 | 0.297 | 1.0 | {"CNY": 0.0} | yes |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.167 | 0.214 | 1.0 | {"CNY": 0.0} | yes |
| procedure-extractor | 6 | 1.0 | 0.0 | 0.204 | 0.274 | 1.0 | {"CNY": 0.0} | yes |
| rule-explainer | 6 | 1.0 | 0.0 | 0.195 | 0.284 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.192 | 0.224 | 1.0 | {"CNY": 0.0} | yes |
