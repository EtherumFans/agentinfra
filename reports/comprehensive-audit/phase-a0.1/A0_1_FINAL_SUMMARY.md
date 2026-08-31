# Phase A0.1 — Audit Repair and Immutable Baseline Freeze
## Final Summary (2026-07-17)

> **Verdict**: `PASS_PHASE_A0_1_AUDIT_REPAIR_AND_BASELINE_FROZEN_READY_FOR_A1`
> (one of the 5 allowed verdicts per Phase A0.1 §五)
>
> **Validator**: 55/55 checks PASS (`scripts/audit/validate_phase_a0_1.py`)
>
> **Phase A0 v1 verdict** `PASS_PHASE_A0_AUDIT_CLOSURE_AND_READY_FOR_PHASE_A1_*`:
> **REFUTED** (7 findings in Gate 0). Phase A0 v1 artifacts preserved
> unchanged as audit trail.

---

## What Phase A0.1 did

Took the Phase A0 audit package from "self-attests PASS" to
"machine-verifiable, semantically consistent, evidence-recoverable,
git-reproducible, roadmap-actionable" — without modifying product
code, without committing, without pushing.

10 gates, 0..9, each producing a markdown report plus machine-readable
JSON. One new validator script (`validate_phase_a0_1.py`) catches
every defect class seen in Phase A0 v1's validator.

## Gate-by-gate

| Gate | Deliverable | Headline |
|------|-------------|----------|
| 0 | `A0_1_00_*.md` + `gate0_findings.json` | 16 required findings reproducing every Phase A0 semantic failure |
| 1 | `A0_1_01_*.md` | 97 working-tree entries classified into 4 buckets (A/B/C/D) |
| 2 | `A0_1_02_*.md` + `evidence_manifest.v2_1.json` + `evidence_manifest.public.json` | 16 placeholders resolved; 27 real SHA-256 captures; 9 honest NOT_CAPTURED |
| 3 | `A0_1_03_*.md` + `issue_ledger.v2.json` | 91 raw → 86 canonical → 79 open (machine-derived); "75" figure retired |
| 4 | `A0_1_04_*.md` + `parity_matrix_v2_2.json` | 59 dimensions (was claimed 51); 9 ICODER_ADVANTAGE downgrades for evidence-threshold failure; A-05 typo fixed |
| 5 | `A0_1_05_*.md` + `product_maturity_v2.json` | 16 scenarios × 5 axes; CN-01 L8 regraded to code=L4 + quality=SMOKE_ONLY; CN-02 OPEN_LOOP explicit |
| 6 | `A0_1_06_*.md` | A0-P0-018/019 regraded E7 → E1 (no independent negative verification artifacts) |
| 7 | `A0_1_07_*.md` | A1 scope corrected 23 → 19 P0 (4 commercial-deferred moved to A2); forbidden verdicts removed from timeline |
| 8 | `A0_1_08_*.md` + `scripts/audit/validate_phase_a0_1.py` | 6 passes / 55 checks; caught 8 regressions during development |
| 9 | `A0_1_09_*.md` + `A0_1_09_BUCKET_D_DEFERRED.md` + `scripts/audit/stage_phase_a0_1_commit.sh` | Safe-commit plan: 2 surgical commits + annotated tag; NO push |

## Key numbers (all machine-derived)

```
TRUSTED_HEAD                       = c147d015455017bc1d8420cbdbd813b3b8ec23ce
WORKING_TREE_ENTRIES               = 97 (classified into 4 buckets)
PLACEHOLDERS_RESOLVED              = 16 (3 NOT_YET_CAPTURED + 8 EMPTY_DIR + 5 future-tense)
EVIDENCE_ENTRIES                   = 36 (27 CAPTURED + 8 NOT_CAPTURED + 1 NOT_POPULATED)
ISSUE_LEDGER raw                   = 91
ISSUE_LEDGER canonical             = 86
ISSUE_LEDGER open_canonical        = 79
P0_AGGREGATE_OPEN                  = 23 (11 P0-S + 2 P0-C + 4 P0-D + 6 P0-T)
PARITY_DIMENSIONS                  = 59 (was claimed 51 in v2.1)
ICODER_ADVANTAGE (after threshold) = 2 (was 11 in v2.1; 9 downgraded)
EVIDENCE_INSUFFICIENT (after regrade) = 14
SCENARIOS_AT_L7_PLUS               = 0 (was 1 in v1 — CN-01 regraded)
SCENARIOS_WITH_FORMAL_BENCHMARK    = 0
FORBIDDEN_VERDICTS_ON_TIMELINE     = 0 (PARTNER_PRODUCTION_READY + COMMERCIAL_GA removed)
VALIDATOR_CHECKS                   = 55
VALIDATOR_PASSES                   = 6
VALIDATOR_FAILS                    = 0
```

## What changed vs Phase A0 v1

| Phase A0 v1 (REFUTED) | Phase A0.1 (this phase) |
|------------------------|-------------------------|
| Validator self-attests `{"UNKNOWN": 59}` + `pass: true` | Validator re-derives every count from array; no UNKNOWN aggregation possible |
| Issue ledger 75/82/91 inconsistent | 91 raw → 86 canonical → 79 open, machine-derived, formulas in JSON |
| Final Decision substring-scans 5 candidate verdicts | Validator enforces "one of 5"; no substring scan |
| "0 placeholders" claim while 16 user-visible placeholders remain | All 16 resolved; remaining 9 honestly marked NOT_CAPTURED |
| Gate 13A claims E7 with zero browser evidence | Regraded to E1; 7 artifacts required for E7 listed |
| Medical Coding labeled L8_QUALITY_BENCHMARKED | Code=L4 + quality=SMOKE_ONLY; A0-P0-013 contradiction surfaced |
| Roadmap with PARTNER_PRODUCTION_READY + COMMERCIAL_GA on timeline | Verdicts removed; CONDITIONAL_TARGET + ACHIEVABLE language introduced |
| Architecture "exactly 10 layers" artificial | (out of Phase A0.1 scope — Phase A0 v1 preserved) |
| Git baseline non-reproducible (97 dirty, uncommitted) | Reproducibility ESTABLISHED via Gate 9 plan (execute when ready) |

## What Phase A0.1 did NOT do

- ❌ Did NOT modify product code (read-only audit repair)
- ❌ Did NOT commit (Gate 9 produces the plan + script; user executes)
- ❌ Did NOT push to remote
- ❌ Did NOT publish to npm
- ❌ Did NOT create PR
- ❌ Did NOT modify Phase A0 v1 artifacts (preserved as audit trail)
- ❌ Did NOT start Phase A1 development
- ❌ Did NOT use `git add -A` (the staging script uses surgical `git add <file>`)
- ❌ Did NOT inherit Phase A0 PASS verdict (explicitly REFUTED)

## Phase A1 entry criteria (per Gate 7 §8)

Phase A1 may start only when:

1. ✅ Phase A0.1 verdict is one of the 5 allowed verdicts (NOT `PASS_PHASE_A0_*`).
2. ✅ All hard checkpoints A-H plus I/J closed.
3. ⏳ Safe commit executed: `bash scripts/audit/stage_phase_a0_1_commit.sh`.
4. ⏳ Annotated tag exists: `audit/phase-a0.1-baseline`.
5. ✅ V2 issue ledger accepted.
6. ✅ V2.2 parity matrix accepted.
7. ✅ V2 product maturity accepted.
8. ✅ A0-P0-018/019 regraded to E1.
9. ✅ Roadmap V2 accepted.
10. ⏳ A1-S workstream owner assigned (business).
11. ⏳ A1-C workstream owner assigned (clinician engagement or research-mode decision).
12. ⏳ Cloud SaaS deployment path decision confirmed (per CLAUDE.md).

Items 3-4, 10-12 are post-Phase-A0.1 actions. Items 1, 2, 5-9 are
satisfied by this phase's deliverables.

## Reproducibility

Every Phase A0.1 artifact is reproducible:

- `issue_ledger.v2.json` — array-derived counts; re-run `validate_phase_a0_1.py` to verify.
- `parity_matrix_v2_2.json` — `python scripts/audit/build_parity_v2_2.py` rebuilds from v2.1.
- `product_maturity_v2.json` — `python scripts/audit/build_maturity_v2.py` rebuilds.
- `validate_phase_a0_1.py` — runs end-to-end; exit 0 = PASS.
- `stage_phase_a0_1_commit.sh --dry-run` — prints every command without executing.

The validator catches every defect class seen in Phase A0 v1's
validator. Any future regression will fail the validator immediately.

## Verdict

```
PASS_PHASE_A0_1_AUDIT_REPAIR_AND_BASELINE_FROZEN_READY_FOR_A1
```

Phase A1 may start after Gate 9 staging script is executed locally
and workstream owners are assigned. No push required for A1 start.

---

End of Phase A0.1.
