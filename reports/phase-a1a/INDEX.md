# Phase A1A Reports Index

**Branch**: `phase-a1a/emergency-containment`
**Branch head**: `ca36c51` (post Gate 4R-I.1 merge)

## Gate closure chain (chronological)

| Gate | Commit | Verdict | Artefact |
|---|---|---|---|
| Gate 0 | `f6bbd60` | PASS_A1A_GATE1_SECRETS_AND_AUTHENTICATION_FAIL_CLOSED | `A1A_GATE0_ADDENDUM_CLOSURE.md` |
| Gate 1 | `06624b4` | (consolidated into Gate 0 + Gate 1) | `A1A_GATE1_*.md` (8 reports) |
| Gate 2 | `de2feaa` | PASS_A1A_GATE2_TENANCY_AND_DATA_ISOLATION_VERIFIED | (within commit) |
| Gate 3 | `d1447f3` | PASS_A1A_GATE3_TENANCY_TRUTH_CONTAINMENT_AND_TRACE_ISOLATION_VERIFIED | (within commit) |
| Gate 3R | `b737eab` | PASS_A1A_GATE3R_*_RECONCILED_VERIFIED | (within commit) |
| Gate 4 | `880f49c` | PASS_A1A_GATE4_PHI_BOUNDARY_..._VERIFIED (REOPENED by 4R) | (within commit) |
| Gate 4.9 | `b3ea064` | (final verdict artefact for 880f49c; tag `audit/phase-a1a-gate4-pre4r-b3ea064`) | (within commit) |
| Gate 4R | `24967da` (on `phase-a1a/gate4r-regression-reconciliation`) | PASS_A1A_GATE4R_P0_5_REGRESSION_RECONCILIATION_TEST_HARNESS_HERMETICITY_VERIFIED (tag `audit/phase-a1a-gate4r-closure-24967da`) | `adversarial-audit/A1A_GATE4R_P0_5_CLOSURE_NOTICE.md` |
| Gate 4R-I.0 | `777d96d` | (Charter only; no verdict) | `integration/A1A_GATE4R_I_0_INTEGRATION_CHARTER.md` |
| Gate 4R-I.1 | `ca36c51` | (merge commit; no verdict yet) | `integration/evidence/MERGE_PRECOMMIT_VERIFICATION.txt` |

## Gate closure chain (by sub-gate)

### Gates 0 + 0B/C/D/E + 1
- `A1A_GATE0B_HTTP_AUTH_REJECTION.md`
- `A1A_GATE0C_UNTRACKED_FILES_CLASSIFICATION.md`
- `A1A_GATE0D_BUNDLE_VERIFY_AND_RESTORE.md`
- `A1A_GATE0E_FINGERPRINT_MIGRATION_PLAN.md`
- `A1A_GATE0_ADDENDUM_CLOSURE.md`

### Gate 4R (adversarial audit sub-charter)
- `adversarial-audit/A1A_GATE4R_0_EVIDENCE_FREEZE_CORRECTION_NOTICE.md`
- `adversarial-audit/A1A_GATE4R_1_NODE_ID_DIFF_AND_TRANSITION_LEDGER.md`
- `adversarial-audit/A1A_GATE4R_2_TEST_HARNESS_HERMETICITY.md`
- `adversarial-audit/A1A_GATE4R_3_PER_REGRESSION_LIQUIDATION_LEDGER.md`
- `adversarial-audit/A1A_GATE4R_P0_5_CLOSURE_NOTICE.md`

### Gate 4R-I (integration sub-charter, in progress)
See `integration/README.md`.

## Mandatory state carried through all gates

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED   (since Gate 4R.0 a2613b7)
GATE4_9_FINAL_PASS              = SUPERSEDED     (since Gate 4R.0 a2613b7)
GATE4_ACCEPTANCE_STATUS         = REOPENED       (since Gate 4R.0 a2613b7)
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED (all gates)
PRODUCTION_READINESS            = NOT_VERIFIED   (all gates)
```

## Screenshot evidence

- `screenshots/` — Browser E2E screenshots (Phase A1A Gate 3R + earlier)
- `gate3-8-browser-evidence.png` (root, untracked) — needs reconciliation

## Evidence freeze

- `adversarial-audit/evidence-freeze/` — Gate 4R JUnit XML + logs (frozen post-24967da)
- `integration/evidence/` — Gate 4R-I pre/post-merge evidence (current)
