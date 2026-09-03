# Agent Hub stability benchmark

Generated: `2026-08-23T22:15:47.497950+00:00`

Scope: contract, safety and runtime reliability only; this is not a clinical-accuracy score.

Result: **42/42 passed; expected 42**

Pass rate: `1.0`; error rate: `0.0`; P50: `0.223s`; P95: `0.289s`.

Cost coverage: `1.0`; unknown-cost runs: `0`; totals by currency: `{"CNY": {"average": 0.0, "p50": 0.0, "p95": 0.0, "runs": 42, "total": 0.0}}`.

| Agent | Runs | Pass rate | Error rate | P50 (s) | P95 (s) | Cost coverage | Cost totals | Repeatable |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| code-validation-agent | 6 | 1.0 | 0.0 | 0.278 | 0.297 | 1.0 | {"CNY": 0.0} | yes |
| compliance-guardrail-agent | 6 | 1.0 | 0.0 | 0.172 | 0.275 | 1.0 | {"CNY": 0.0} | yes |
| evidence-extractor | 6 | 1.0 | 0.0 | 0.266 | 0.27 | 1.0 | {"CNY": 0.0} | yes |
| evidence-ranker | 6 | 1.0 | 0.0 | 0.182 | 0.211 | 1.0 | {"CNY": 0.0} | yes |
| icd10-navigator | 6 | 1.0 | 0.0 | 0.283 | 0.36 | 1.0 | {"CNY": 0.0} | yes |
| note-completeness-agent | 6 | 1.0 | 0.0 | 0.202 | 0.229 | 1.0 | {"CNY": 0.0} | yes |
| surgical-registry | 6 | 1.0 | 0.0 | 0.195 | 0.228 | 1.0 | {"CNY": 0.0} | yes |
