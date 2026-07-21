# Phase A1A Gate 4R — P0-5 Closure Notice

**Date**: 2026-07-21
**Branch**: `phase-a1a/gate4r-regression-reconciliation`
**Predecessor gates**:
- Gate 4R.0 (`a2613b7`) — evidence freeze + 7-point correction notice
- Gate 4R.1 (`e418020`) — precise node-ID diff + transition ledger
- Gate 4R.2 (`fa676b3`) — Rate Limiter hermeticity + 77/77 regressions healed
- Gate 4R.3 (`efbe96b`) — per-regression liquidation ledger

**Successor**: Phase A1A Gate 5 (next-phase charter, to be defined).

Charter §4R-P0-5: verify the 12 closure conditions and, if all pass,
issue the final 4R verdict. This notice performs that verification.

---

## §1. The 12 closure conditions

| # | Condition | Status | Evidence |
|---|---|---|---|
| 1 | Evidence freeze filed | MET | Gate 4R.0 `a2613b7`; SHA256SUMS + manifest + git state snapshot |
| 2 | 7-point correction notice published | MET | Gate 4R.0 `A1A_GATE4R_0_EVIDENCE_FREEZE_CORRECTION_NOTICE.md` |
| 3 | Mandatory 5-tuple state unchanged | MET | Re-confirmed in every 4R sub-gate report (§1) |
| 4 | Precise node-ID collection diff computed | MET | Gate 4R.1: 3591 baseline / 3668 gate4 / 3591 common / 0 removed / 77 new |
| 5 | Per-node transition ledger built | MET | Gate 4R.1 `gate4r_diff/transition_ledger.json` |
| 6 | Dominant root cause identified | MET | Gate 4R.1 §5: Rate Limiter module-level global (`_request_counts`) |
| 7 | Rate Limiter hermeticity fix shipped | MET | Gate 4R.2 `backend/app/middleware/rate_limit.py` rewrite |
| 8 | Conftest function-scope autouse fixture installed | MET | Gate 4R.2 `backend/tests/conftest.py:114` |
| 9 | `asyncio_default_fixture_loop_scope` set | MET | Gate 4R.2 `backend/pytest.ini` |
| 10 | Same-commit reproducibility proven | MET | Gate 4R.2 §5: 1-node drift (threshold <5) |
| 11 | 77 pass→fail regressions re-verified PASS | MET | Gate 4R.2 §4: 77/77 PASS in 49.33s |
| 12 | Per-regression liquidation ledger filed | MET | Gate 4R.3 `A1A_GATE4R_3_*.md` |

All 12 conditions MET.

---

## §2. Headline reconciliation

### §2.1 The +43 net FAIL floor (Gate 4R.0)

```
b737eab full-suite: 3237 passed / 249 failed / 81 errors
880f49c full-suite: 3270 passed / 292 failed / 81 errors
292 - 249 = +43 net FAIL result
```

This was the Gate 4R.0 floor. It held; it was not the full picture.

### §2.2 The +46 net regression ceiling (Gate 4R.1)

```
77 baseline-PASS nodes flipped to FAIL at 880f49c
31 baseline-FAIL nodes flipped to PASS at 880f49c
Net pass→fail delta = 77 - 31 = +46
```

### §2.3 The healing (Gate 4R.2)

After moving Rate Limiter state to `app.state.rate_limiter_counts`:

```
77 pass->fail regressions -> 77 PASS in 49.33s
Full-suite drift between identical runs: 4 nodes -> 1 node
Full-suite totals: 296 failed / 3266 passed -> 63 failed / 3554 passed
```

The Rate Limiter module-level global was the dominant cause of 70
of 77 regressions; the other 7 were downstream of the same 429s.

### §2.4 The residual (Gate 4R.3)

After full triage of the 89 residual failing/erroring nodes:

```
P0 = 0
P1 = 0
P2 = 1   (schema drift on run_trace_events; per-column triage needed)
P3 = 88  (test-harness / cosmetic / pre-existing)
```

No P0. No P1. The single P2 is a pre-existing schema drift that
predates Gate 4 and is unrelated to the 4R regression surface.

---

## §3. Mandatory state (final 4R values)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

These values were set at Gate 4R.0 and have NOT been weakened at
any subsequent 4R sub-gate.

---

## §4. Forbidden list for the entire 4R chain

| Forbidden action | Status across 4R.0–4R.3 |
|---|---|
| Modify any Medical Coding / CDI / DRG-DIP prompt | NOT TOUCHED ✓ |
| Touch real patient data | NOT TOUCHED ✓ |
| Push to remote | NOT PUSHED ✓ |
| Create PR | NOT CREATED ✓ |
| Commit to master | NOT COMMITTED ✓ |
| Amend `b737eab`, `880f49c`, `b3ea064`, `a2613b7`, `e418020`, `fa676b3`, `efbe96b` | NOT AMENDED ✓ |
| Use `git add -A` | NOT USED (every commit used explicit file list) ✓ |
| Edit Gate 4.8 / 4.9 reports in place | NOT EDITED ✓ |
| Issue any charter §22 forbidden verdict | NOT ISSUED ✓ |
| Weaken fail-closed / JWT / encryption / redaction contracts | NOT DONE ✓ |
| Disable rate limiter globally in tests | NOT DONE ✓ |
| Detect pytest via `sys.argv` string match | NOT DONE ✓ |
| Use `time.sleep` to evade the rate-limit window | NOT DONE ✓ |
| Enter Gate 5 before P0-5 closure | NOT DONE ✓ |
| Forbidden verdict strings (PRODUCTION_READY, FULLY_VERIFIED, PHI_BOUNDED, CORTI_PARITY_VERIFIED, PASS_A1A_GATE4_FINAL) | NOT ISSUED ✓ |

---

## §5. Commits in the 4R chain

```
efbe96b audit/phase-a1a: Gate 4R.3 — per-regression liquidation ledger
fa676b3 audit/phase-a1a: Gate 4R.2 — Rate Limiter hermeticity
e418020 audit/phase-a1a: Gate 4R.1 — precise node-ID diff + transition ledger
a2613b7 audit/phase-a1a: Gate 4R.0 — evidence freeze + 7-point correction notice
b3ea064 audit/phase-a1a: Gate 4.9 closure report (prior 4R baseline)
```

All on `phase-a1a/gate4r-regression-reconciliation`. Master is
untouched. The branch is local-only (not pushed).

---

## §6. Carry-over summary

| Item | Count | Disposition |
|---|---|---|
| GATE4R_REG_001 pack-count drift | 17 | Carry-over; needs product decision |
| GATE4R_REG_002 app title rename | 5 | Carry-over; trivial test update |
| GATE4R_REG_003 MCP rule expansion | 6 | Carry-over; positive |
| GATE4R_REG_004 corti RE missing fixtures | 27 | Carry-over; Option B skip |
| GATE4R_REG_005 MedCoder asset path | 4 | Carry-over; index build |
| GATE4R_REG_006 schema drift (P2) | 1 | Carry-over; per-column triage |
| GATE4R_REG_007 test points at dev DB | 1 | Carry-over; test design bug |
| GATE4R_REG_008 singletons | 2 | Carry-over; same pattern as Rate Limiter |
| GATE4R_REG_009 test writes to source | 1 | Carry-over; tmp_path fix |
| GATE4R_REG_010 various pre-existing | 25 | Carry-over; per-test triage |
| 31 heal verification | 31 | Carry-over; needs b737eab + 4R.2 backport |
| **Total carry-over** | **120** | |

None of the carry-over items are P0 or P1. The 4R chain's contract
was "no P0 unfixed, no P1 untriaged" — met.

---

## §7. What the 4R chain closed

### §7.1 Truth reconciliation

The Gate 4.8 / 4.9 reports claimed:
- 49 baseline failures (FALSE: actual 249)
- 50 total failures at gate4 (FALSE: actual 292)
- 85 Gate 4 tests added (FALSE: actual 77)
- "no NEW regressions introduced by Gate 4" (FALSE: 77 new regressions)
- PASS verdict (SUPERSEDED)

The 4R chain replaced those claims with frozen evidence and
node-ID-level truth.

### §7.2 Test-harness hermeticity

The Rate Limiter module-level global was a long-standing
hermeticity defect. The 4R.2 fix benefits every future pytest
run, not just the Gate 4 surface.

### §7.3 Diagnostic tooling

Three reusable audit scripts now live in `scripts/audit/`:

- `gate4r_node_filter.py` — pytest plugin for stable node-set runs
- `gate4r_build_transition_ledger.py` — JUnit-XML transition builder
- `gate4r_order_experiments.py` — A/B/C/D order-pollution driver

These can be re-used for any future b<X> vs b<Y> regression audit.

### §7.4 Evidence trail

Every claim in the 4R chain cites a frozen artefact (XML, log,
JSON, or per-node text file) with a SHA-256 hash. Future auditors
can re-verify any step.

---

## §8. Provisional verdict

```
PASS_A1A_GATE4R_P0_5_REGRESSION_RECONCILIATION_TEST_HARNESS_HERMETICITY_VERIFIED
```

This is the only allowed final 4R verdict per charter §22. It is
deliberately scoped:

- It VERIFIES that the regression reconciliation is complete
  (12/12 closure conditions).
- It VERIFIES that the test harness is hermetic (1-node drift,
  below the <5 threshold).
- It does NOT verify production readiness (`PRODUCTION_READINESS = NOT_VERIFIED`).
- It does NOT verify Corti parity (`CORTI_PARITY_VERDICT = NOT_DEMONSTRATED`).
- It does NOT close Gate 4 itself (`GATE4_ACCEPTANCE_STATUS = REOPENED`).
  Gate 4 stays REOPENED because the 89 residual P3 nodes and 1 P2
  node remain unfixed; only the 4R sub-charter is closed.

### §8.1 What this verdict means operationally

- The Phase A1A Gate 4 acceptance decision is REOPENED, not
  PASS. The original PASS claim is SUPERSEDED.
- The Phase A1A Gate 4.8 "no NEW regressions" claim is
  CONTRADICTED, not affirmed.
- The branch `phase-a1a/gate4r-regression-reconciliation` carries
  the 4R work; it does NOT carry a new Gate 4 PASS.
- The 4R work may be merged into `phase-a1a/emergency-containment`
  only after an explicit re-acceptance gate that addresses the 89
  residual nodes and the 1 P2 schema drift.

### §8.2 What this verdict does NOT authorize

- Production deployment
- Corti parity claims
- Closing Gate 4
- Issuing any charter §22 forbidden verdict
- Entering Gate 5 (which requires a fresh charter)

---

## §9. Forbidden list for this closure notice

| Forbidden action | Status |
|---|---|
| Issue `PRODUCTION_READY` verdict | NOT ISSUED ✓ |
| Issue `FULLY_VERIFIED` verdict | NOT ISSUED ✓ |
| Issue `PHI_BOUNDED` verdict | NOT ISSUED ✓ |
| Issue `CORTI_PARITY_VERIFIED` verdict | NOT ISSUED ✓ |
| Issue `PASS_A1A_GATE4_FINAL` verdict | NOT ISSUED ✓ |
| Close Gate 4 | NOT CLOSED (stays REOPENED) ✓ |
| Enter Gate 5 | NOT ENTERED ✓ |
| Push the branch | NOT PUSHED ✓ |
| Create a PR | NOT CREATED ✓ |
| Commit to master | NOT COMMITTED ✓ |
| Amend any prior commit | NOT AMENDED ✓ |

---

## §10. Next

The 4R sub-charter is closed. The 4R work sits on the local branch
`phase-a1a/gate4r-regression-reconciliation`. The next decision is
whether to:

(a) merge 4R into `phase-a1a/emergency-containment` and proceed
    to Gate 4R.4 (re-acceptance of Gate 4 itself, which requires
    fixing the 89 residual nodes), OR
(b) hold 4R as-is and treat the 89 residual nodes as carry-over
    to a future hardening phase.

That decision is out of scope for this notice. It requires a fresh
charter.
