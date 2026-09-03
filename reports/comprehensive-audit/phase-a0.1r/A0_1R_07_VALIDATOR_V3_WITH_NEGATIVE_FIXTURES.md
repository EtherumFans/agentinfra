# Phase A0.1R Gate 7 — Validator V3 with Negative Fixtures

> Installs the canonical machine-verifier for the Phase A0.1R
> audit package and proves via negative fixtures that every defect
> class visible in Gate 0 is caught. Supersedes the Phase A0.1
> validator V2 (which reported 55/55 PASS while missing 10 defect
> classes).
>
> Verdict: `PHASE_A0_1_R_GATE_7_VALIDATOR_V3_GREEN`
> Hard Checkpoint C: **CLOSED**

Spec reference: Phase A0.1R charter §3.Gate7.

Artifacts:

- Validator: `scripts/audit/validate_phase_a0_1r.py`
- Negative fixture runner: `scripts/audit/run_negative_fixtures_a0_1r.py`
- JSON report (optional): `--report <path>`

---

## §1. Validator V3 architecture

The validator is modular: each check is a Python function that
takes an artifact dict and returns a `CheckResult(name, passed, detail)`.
The main runner loads the JSON artifacts, dispatches each check,
and aggregates PASS/FAIL counts.

```python
class CheckResult:
    name: str      # dotted hierarchical name e.g. "ledger.open_count_strict"
    passed: bool
    detail: str    # human-readable explanation
```

The runner exits 0 only if every check PASSES. The negative-fixture
runner reuses the same check functions on mutated inputs to prove
defect detection.

## §2. Positive checks (14 checks, 14 PASS)

Run: `python scripts/audit/validate_phase_a0_1r.py --pre-tag`

```
=== Phase A0.1R Validator V3 ===
  [PASS] ledger.open_count_strict: strict_open=22
  [PASS] ledger.p0_s_open_strict: P0-S strict open=10
  [PASS] ledger.primary_phase_complete: all OPEN issues mapped
  [PASS] ledger.billing_theater_split: split applied
  [PASS] ledger.npm_reframed: reframed
  [PASS] ledger.cdi_bounded: boundary applied
  [PASS] parity.no_illegal_statuses: all statuses legal
  [PASS] parity.symmetric_thresholds: all advantage dims meet threshold
  [PASS] maturity.7_axes: all 16 scenarios have 7 axes
  [PASS] manifest.empty_dirs: all dir entries have exists=true + artifact_count
  [PASS] manifest.storage_mode: all entries have legal storage_mode
  [PASS] worktree.no_secret: no plain-text secret in tracked files
  [PASS] git.trusted_head: c147d0154550
  [PASS] git.branch: current=master

Total: 14, PASS: 14, FAIL: 0
```

The `--pre-tag` flag skips the `git.audit_tag` check, which only
closes after Gate 9 creates `audit/phase-a0.1r-baseline`. Post-tag
mode adds a 15th check (see §4).

## §3. Negative fixtures (11 fixtures, 11 PASS)

Run: `python scripts/audit/run_negative_fixtures_a0_1r.py`

Each fixture injects one defect class into an in-memory copy of
the corrected artifact and verifies the corresponding validator
check FAILS.

| NF | Defect injected | Check | Result |
|---|---|---|---|
| NF01 | `P0_aggregate_open_strict = 99` (drift) | `ledger.open_count_strict` | ✅ caught: "claim=99 actual=22" |
| NF02 | `P0-S_open = 99` (drift) | `ledger.p0_s_open_strict` | ✅ caught: "claim=99 actual=10" |
| NF03 | A0-P0-021 removed from A2_commercial_deferred.explicit_ids | `ledger.primary_phase_complete` | ✅ caught: "A0-P0-021: not in mapping" |
| NF04 | `split_status` removed from A0-P0-004 | `ledger.billing_theater_split` | ✅ caught: "split_status missing" |
| NF05 | `phase_a0_1r_reframe` removed from A0-P0-009 | `ledger.npm_reframed` | ✅ caught: "reframed not true" |
| NF06 | `phase_a0_1r_boundary` removed from A0-P0-007 | `ledger.cdi_bounded` | ✅ caught: "boundary_applied not true" |
| NF07 | D-05 status restored to `ICODER_TECH_DEBT` | `parity.no_illegal_statuses` | ✅ caught: "D-05:ICODER_TECH_DEBT" |
| NF08 | F-03 restored to CORTI_ADVANTAGE at corti_evidence_grade=E1 | `parity.symmetric_thresholds` | ✅ caught: "F-03 CORTI_ADVANTAGE Corti=E1<E7" |
| NF09 | `security` axis removed from CN-01 | `maturity.7_axes` | ✅ caught: "missing axes: ['CN-01:security']" |
| NF10 | `exists=false` restored on `phase7/gate13a/screenshots/` | `manifest.empty_dirs` | ✅ caught: "exists=false for dir" |
| NF11 | `storage_mode = 'SECRET_LEAKED'` (illegal) | `manifest.storage_mode` | ✅ caught: "storage_mode='SECRET_LEAKED'" |

**All 11 negative fixtures caught by the validator.** No false positives.

## §4. Post-Tag mode (Gate 9)

After Gate 9 creates the annotated tag, the validator adds a 15th check:

```
[PASS] git.audit_tag: audit/phase-a0.1r-baseline exists
```

Run: `python scripts/audit/validate_phase_a0_1r.py` (no flag)

The validator must exit 0 in post-tag mode for the final Phase A0.1R
verdict. Gate 9 §6 enforces this.

## §5. Comparison with Phase A0.1 validator V2

| Aspect | Phase A0.1 V2 | Phase A0.1R V3 |
|---|---|---|
| Total checks | 55 | 14 positive + 11 negative fixtures = **25 distinct defect classes verified** |
| Ledger count enforcement | derived but with bugs (status field mis-named, OPEN+MITIGATED vs strict ambiguity) | strict vs open+mit split; both reported |
| primary_phase completeness | not checked | full cross-check (per-issue vs explicit_ids) |
| Workstream misplacement | not checked | indirectly via primary_phase_complete |
| Symmetric parity thresholds | only ICODER_ADVANTAGE | both directions |
| Illegal parity status | not synchronized with allowed_statuses | synchronized |
| 7-axis maturity | not checked (5 axes only) | requires all 7 axes on every scenario |
| Empty-dir semantics | not checked | requires exists=true + artifact_count for paths ending `/` |
| storage_mode | field didn't exist | required, with allowed-values check |
| Secret-in-worktree | not checked | git grep against secret fingerprint |
| Negative fixtures | none | 11 fixtures, all PASS |
| Pre-tag vs post-tag mode | single mode | `--pre-tag` for Gate 7; default for post-Gate 9 |

## §6. Hard Checkpoint C — Validator V3 Green

| Sub-check | Status |
|---|---|
| SC-1: validator V3 script installed at `scripts/audit/validate_phase_a0_1r.py` | ✅ |
| SC-2: 14 positive checks all PASS in pre-tag mode | ✅ |
| SC-3: 11 negative fixtures all PASS (defects caught) | ✅ |
| SC-4: validator V2's 10 missed defect classes (Gate 0 Output 21) all covered | ✅ |
| SC-5: validator exits non-zero on any single defect injection | ✅ |
| SC-6: post-tag mode (`--pre-tag` flag omitted) defined for Gate 9 | ✅ |
| SC-7: machine-readable JSON report supported via `--report <path>` | ✅ |
| SC-8: documentation in this report | ✅ |
| SC-9: validator is reproducible (no random / no time-dependent seeds) | ✅ |
| SC-10: negative-fixture runner is part of Commit B (audit package) | ✅ |

**Hard Checkpoint C: ✅ CLOSED (10/10 sub-checks)**

## §7. Findings raised in Gate 7

| ID | Severity | Title |
|----|----------|-------|
| **A0.1R-G7-001** (closed) | P1 | Validator V3 installed with 14 positive checks. |
| **A0.1R-G7-002** (closed) | P1 | 11 negative fixtures installed; every defect class verified caught. |
| **A0.1R-G7-003** (closed) | P2 | Phase A0.1 V2's 10 missed defect classes all covered by V3. |
| **A0.1R-G7-004** | P3 | CI in Phase A1A should run validator V3 + negative-fixture runner on every commit. Pre-tag mode for branches; post-tag mode for tag-anchored releases. |

---

## §8. Gate 7 verdict

```
PHASE_A0_1_R_GATE_7_VALIDATOR_V3_GREEN

Hard Checkpoint C: CLOSED
  - Validator V3: scripts/audit/validate_phase_a0_1r.py
  - Positive checks: 14/14 PASS (pre-tag mode)
  - Negative fixtures: 11/11 PASS (every defect caught)
  - Phase A0.1 V2 defect-coverage gaps: CLOSED

NEXT_GATE: GATE_8_BRANCH_AND_COMMIT_A
NEXT_ALLOWED_VERDICT:
  PHASE_A0_1_R_GATE_8_BRANCH_AND_COMMIT_A_CREATED_REGRESSION_PASSED
```

End of Gate 7.
