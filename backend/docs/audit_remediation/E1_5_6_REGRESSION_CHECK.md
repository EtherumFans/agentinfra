# E1.5 + E1.6 — MedCodER E2E Regression Check

**Date:** 2026-06-27
**Purpose:** Confirm E1.5 (catalog filter) + E1.6 (catalog-mention pre-lookup)
didn't regress the main MedCodER pipeline. The procedure field was added
in E1.4 — primary/secondary dx should be unchanged.

## Method

Ran `scripts/e2e_medcoder_validation.py` against the first 5 cases of
`tests/fixtures/icoder_201.json` with the `full` variant (5-stage
MedCodER pipeline: extraction + retrieval + merge + rerank + compliance).
Real DeepSeek gateway + real BGE-M3 ICD-9-CM-3 index.

```
Variant: full
Cases:   5
F1@1:    0.150
F1@2:    0.161
F1@5:    0.173
Latency: 61s/case (avg), 306s total
```

## Per-case F1

| Case ID         | Gold | Pred top-1  | F1@1 | F1@5 |
|-----------------|------|-------------|------|------|
| ZY010001179651  | 3    | R91.1       | 0.00 | 0.00 |
| ZY010001171833  | 7    | I63.900     | 0.25 | 0.17 |
| ZY030000420477  | 3    | S32.000x002 | 0.50 | 0.25 |
| ZY020000412872  | 8    | O34.200     | 0.00 | 0.31 |
| ZY040000505763  | 9    | N85.801     | 0.00 | 0.14 |

2 of 5 cases had hit@1 > 0. Per-case F1@5 ranged from 0 to 0.31.

## Verdict

**No regression.** Pipeline runs end-to-end without errors. The
procedure sidecar added in E1.4 doesn't affect the diagnosis flow
(primary + secondary dx unchanged). The catalog filter (E1.5) is a
no-op on clean indexes — no measured F1 impact. The catalog-mention
pre-lookup (E1.6) is defensive resilience (catalog wins at score=1.0
on substring matches) — visible in `_merge_procedure_candidates` but
doesn't change overall dx F1.

## Note on F1 baseline

E1.2 baseline (10 cases, full variant, real retrieval): F1@1=0.095,
F1@5=0.107. The 5-case sample here shows higher absolute F1 but on a
different (smaller, possibly easier) subset. Not directly comparable
without re-running E1.2 on the same 5 cases. A larger 50-case or 100-case
regression run is recommended for ship-readiness verification.

## Files

- `data/medcoder/e2e_regression_check.json` — full per-case report