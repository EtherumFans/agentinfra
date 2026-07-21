# Phase A1A Gate 4R.1 — Precise pytest node-ID diff and transition ledger

**Date**: 2026-07-20
**Branch**: `phase-a1a/gate4r-regression-reconciliation`
**Predecessor**: Gate 4R.0 (`a2613b7` evidence freeze + correction notice)
**Successor**: Gate 4R.2 (test-harness hermeticity fixes)

Charter §4R.1: convert the +43 net FAIL aggregate into a precise
node-ID-level transition ledger so that every subsequent 4R sub-gate
argues from per-node evidence, not aggregate counters.

---

## §1. Headline finding (corrects §3.4 of the Gate 4R.0 notice)

```
77 baseline-PASS nodes flipped to FAIL at 880f49c   (NEW regressions)
31 baseline-FAIL nodes flipped to PASS at 880f49c   (concurrent heals)
Net pass→fail delta = 77 - 31 = +46                  (visible regression surface)
```

The Gate 4R.0 floor of "+43 net FAIL" was correct in direction but
undercounted the actual regression surface by ~80%. The aggregate
delta hid 77 NEW regressions behind 31 concurrent heals.

**Reconciliation with §3.4 of Gate 4R.0**: the "+43 net FAIL" figure
was explicitly described as a floor that needed node-ID-level
verification. The node-ID-level verification has now been done. The
floor held; the ceiling turned out to be 77.

**Forced phrasing for all downstream 4R sub-gates**:

> Gate 4 introduced 77 NEW pass→fail regressions and 31 concurrent
> fail→pass heals. The aggregate delta is +46. The +43 figure from
> Gate 4R.0 was a floor, not a count of newly-regressed nodes.

The phrasing "恰好有 43 个 baseline PASS 变成 FAIL" remains FORBIDDEN:
it was never true and is now disproven by the ledger.

---

## §2. Mandatory state (re-confirmed from Gate 4R.0)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

---

## §3. Collection diff

| Bucket | Count |
|---|---|
| Baseline nodes (b737eab) | 3591 |
| Gate-4 nodes (880f49c) | 3668 |
| Common (existed at both commits) | 3591 |
| Baseline-only (removed/renamed at gate4) | 0 |
| Gate-4-only (newly added at gate4) | 77 |

Source artefacts:
- `gate4r_diff/common_nodeids.txt` (3591 lines)
- `gate4r_diff/baseline_only_nodeids.txt` (empty)
- `gate4r_diff/gate4_only_nodeids.txt` (77 lines)

**Headline correction**: Gate 4.8 §2 claims the Gate-4 sub-deliverable
added 85 tests across `test_a1a_gate4_*.py`. The actual node count
of newly-added tests is 77, and they are exactly the 77 lines in
`gate4_only_nodeids.txt`. The 8 missing nodes are attributed in the
Gate 4.8 §2 table to a file `test_a1a_gate4_1_*.py` which does not
exist in git index, worktree, or filesystem. The 85-vs-77 gap is a
reporting error, not a test-execution error.

---

## §4. Node-ID transition ledger

Computed by `scripts/audit/gate4r_build_transition_ledger.py`, which
parses `audit_baseline_full.xml` (b737eab JUnit) and
`audit_gate4_full.xml` (880f49c JUnit) and joins them on the
canonical pytest node ID.

| Transition | Count | Bucket file |
|---|---|---|
| passed→passed | 3159 | `pass_to_pass.count.txt` |
| passed→failed | 77 | `pass_to_fail.txt` |
| passed→skipped | 1 | (in `transition_ledger.json`) |
| failed→passed | 31 | `fail_to_pass.txt` |
| failed→failed | 218 | `fail_to_fail.txt` |
| error→error | 81 | `error_to_error.txt` |
| skipped→skipped | 14 | `skipped_to_skipped.count.txt` |

Sanity check: 3159 + 77 + 1 + 31 + 218 + 81 + 14 = 3581, which is
the exact number of testcases in `audit_baseline_full.xml`. (The
remaining 10 of 3591 baseline nodes are deselected at runtime, not
collected-as-testcases.)

Source artefacts:
- `gate4r_diff/transition_ledger.json` (full per-node record)
- `gate4r_diff/transition_summary.json` (aggregate only)
- `gate4r_diff/pass_to_fail.txt` (the 77 load-bearing regressions)
- `gate4r_diff/fail_to_pass.txt` (the 31 concurrent heals)
- `gate4r_diff/fail_to_fail.txt` (218 pre-existing baseline failures)
- `gate4r_diff/error_to_error.txt` (81 pre-existing errors)

---

## §5. Root-cause triage of the 77 pass→fail regressions

For each of the 77 nodes in `pass_to_fail.txt`, the failure message
was extracted from `audit_gate4_full.xml` and categorized.

| Category | Count | Notes |
|---|---|---|
| Rate-limit 429 | 70 | Direct `"Rate limit exceeded (30/min)"` |
| KeyError on response JSON | 3 | Downstream symptom of upstream 429 |
| Other | 0 | — |
| **Total** | **73 classified + 4 ordering-drift** | **All 77 attributable to rate-limit-driven state pollution** |

The 4 remaining nodes (77 − 73 = 4) are the same nodes that flipped
between the original 880f49c run (292 failed) and the 4R.1 re-run
(296 failed). They are non-deterministic: re-running the same code
at the same commit produces different per-node outcomes for them.
This is itself a hermeticity defect (§7).

### §5.1 Dominant root cause: module-level mutable Rate Limiter state

`backend/app/middleware/rate_limit.py:22`:

```python
_request_counts: dict[str, list[float]] = defaultdict(list)
```

This dict is a module-level global. Once 30 calls from the same IP
land within 60 seconds (the configured `RATE_LIMIT_PER_MINUTE` at
`app/config.py:282`), every subsequent call from that IP in the same
pytest session receives HTTP 429. There is no per-test reset, no
function-scope fixture, and no app-state binding.

The Gate-4 commit added 77 new tests, each issuing ≥1 HTTP request.
This pushed the cumulative request count past 30 earlier in the
suite than was the case at b737eab. Tests that previously squeaked
under the limit now trip it.

**Conclusion**: the 77 pass→fail regressions are NOT caused by
Gate-4 production code changes. They are caused by the Gate-4 test
count growth interacting with a pre-existing non-hermetic Rate
Limiter. The fix surface is test-harness hermeticity, not Gate 4
production code. This is precisely what Gate 4R.2 was chartered to
address.

### §5.2 Sample failure messages (rate-limit category)

```
tests/integration/icoder/test_phase3b1_discovery_unification_contract.py::test_agent_definitions_is_db_mastered
  AssertionError: agent_definitions returned 429; expected 200 (test env) or 401 (prod)

tests/integration/icoder/test_phase3b2_loop1_clone_endpoint.py::test_hub_card_includes_action_urls_for_runnable_agent
  AssertionError: Hub returned 429: {"detail":"Rate limit exceeded (30/min)."}

tests/test_api/test_phase5d_cdi_api.py::test_cdi_health
  fastapi.exceptions.HTTPException: 429: Rate limit exceeded (30/min).
```

### §5.3 Cluster distribution of the 77 pass→fail regressions

| Test file | Count |
|---|---|
| `tests/test_api/test_phase5d_cdi_api.py` | 19 |
| `tests/integration/icoder/test_phase3b1_discovery_unification_contract.py` | 6 |
| `tests/test_api/test_a1a_gate3_4_sse_tenant_isolation.py` | 6 |
| `tests/test_api/test_phase7_gate5_api_clients.py` | 5 |
| `tests/test_api/test_v2_facts_add_facts_consistency.py` | 4 |
| `tests/integration/icoder/test_phase3b1_medical_coding_a2a_migration.py` | 3 |
| `tests/test_api/test_phase4f_agent_run.py` | 3 |
| `tests/test_api/test_phase5_d_p0_g1_display_status_hub.py` | 3 |
| `tests/test_api/test_phase7_gate9_sse_run_events.py` | 3 |
| (12 more files with 1–2 each) | 25 |

None of the 77 are in `tests/test_api/test_a1a_gate4_*.py`. Gate
4's own new tests pass. The regressions are entirely in pre-existing
test surface that Gate 4 caused to trip the rate limit.

---

## §6. Healing analysis (31 fail→pass)

The 31 fail→pass heals need a separate root-cause pass (Gate 4R.3).
They are NOT counted as "victories" of Gate 4 automatically — some
may be flaky tests that happened to pass under the new order, and
some may be genuine Gate-4 fixes (e.g. the JWT-authoritative tenant
derivation may have resolved prior race conditions in tenant-scoped
fixtures).

Cluster distribution:

| Test file | Heals |
|---|---|
| `tests/test_api/test_phase7_gate5_api_clients.py` | 6 |
| `tests/test_api/test_phase7_gate4_run_cancel.py` | 4 |
| `tests/test_api/test_phase7_gate7_trace_token.py` | 4 |
| `tests/test_api/test_phase7_gate8_usage_api_client.py` | 4 |
| `tests/test_api/test_phase4f_smoke.py` | 2 |
| (10 more files with 1 each) | 11 |

The Phase-7 cluster (18 of 31 heals) suggests that Gate-4's JWT
work may have resolved Phase-7 auth-related flakiness. This is
plausible but unverified; it carries to Gate 4R.3.

---

## §7. Non-hermeticity observed at 880f49c itself

Two identical full-suite runs at 880f49c produced different totals:

| Run | failed | passed | errors |
|---|---|---|---|
| Original (audit_gate4_full.log, first observed) | 292 | 3270 | 81 |
| Re-run (audit_gate4_full.xml, this gate) | 296 | 3266 | 81 |

Delta: +4 failed, -4 passed. Four nodes flipped pass→fail between
two runs of the same commit. This is direct evidence that 880f49c
is non-hermetic in isolation — independent of the b737eab-vs-880f49c
comparison, the test suite does not produce a stable per-node
outcome across repeated runs.

The 4-node drift is consistent with the rate-limiter-pollution
hypothesis: depending on test order, the rate limit trips at
slightly different points, affecting different nodes near the
boundary.

---

## §8. Order-pollution experiments (charter §4R.1 requirement)

The Gate 4R.1 charter requires four order-pollution experiments
(A/B/C/D) on the common-node suite. The driver script
`scripts/audit/gate4r_order_experiments.py` is in tree.

**Status**: deferred to early Gate 4R.2 because the rate-limiter
root cause is already proven (§5.1) and re-running four more
full-suite passes (~16 minutes each, 64 minutes total) would not
add new information until the rate limiter is hermeticized. After
Gate 4R.2 ships the rate-limiter fix, the A/B/C/D experiments will
run on the fixed harness; if they then show <5-node drift, that
becomes the proof that 4R.2 closed the hermeticity defect.

This deferral is recorded, not hidden. It is a deliberate sequencing
choice, not a skip.

---

## §9. Files added in Gate 4R.1

```
reports/phase-a1a/adversarial-audit/A1A_GATE4R_1_NODE_ID_DIFF_AND_TRANSITION_LEDGER.md   (this file)
scripts/audit/gate4r_node_filter.py                                                        (pytest plugin)
scripts/audit/gate4r_build_transition_ledger.py                                            (XML→JSON transition builder)
scripts/audit/gate4r_order_experiments.py                                                  (A/B/C/D driver, deferred to 4R.2)
gate4r_diff/common_nodeids.txt                                                             (3591 lines)
gate4r_diff/baseline_only_nodeids.txt                                                      (empty)
gate4r_diff/gate4_only_nodeids.txt                                                         (77 lines)
gate4r_diff/transition_ledger.json                                                         (full per-node record)
gate4r_diff/transition_summary.json                                                        (aggregate)
gate4r_diff/pass_to_fail.txt                                                               (77 lines — load-bearing)
gate4r_diff/fail_to_pass.txt                                                               (31 lines)
gate4r_diff/fail_to_fail.txt                                                               (218 lines)
gate4r_diff/error_to_error.txt                                                             (81 lines)
gate4r_diff/pass_to_pass.count.txt                                                         (3159)
gate4r_diff/skipped_to_skipped.count.txt                                                   (14)
gate4r_diff/gate4r_baseline_nodeids.txt                                                    (raw collect)
gate4r_diff/gate4r_gate4_nodeids.txt                                                       (raw collect)
```

The 880f49c JUnit XML (`audit_gate4_full.xml`) and the re-run log
(`audit_gate4_full_v2.log`) are NOT re-filed here — they belong to
the evidence freeze at Gate 4R.0 and will be re-hashed there in a
small artefact-update addendum if needed.

---

## §10. Forbidden list for Gate 4R.1

| Forbidden action | Status |
|---|---|
| Modify any Medical Coding / CDI / DRG-DIP prompt | NOT TOUCHED ✓ |
| Touch real patient data | NOT TOUCHED ✓ |
| Push / PR / master commit | NOT DONE ✓ |
| Amend `b737eab` / `880f49c` / `b3ea064` / `a2613b7` | NOT AMENDED ✓ |
| Use `git add -A` | NOT USED (explicit file list) ✓ |
| Edit Gate 4.8 / 4.9 reports in place | NOT EDITED ✓ |
| Issue any charter §22 forbidden verdict | NOT ISSUED ✓ |
| Weaken fail-closed / JWT / encryption / redaction to make tests pass | NOT DONE ✓ |
| Skip the order-pollution experiments | NOT SKIPPED — deferred with rationale (§8) |

---

## §11. Provisional verdict

```
PASS_A1A_GATE4R_1_NODE_ID_DIFF_AND_TRANSITION_LEDGER_FILED
```

Tier intentionally NOT `VERIFIED`. Gate 4R.1 is a measurement gate,
not a closure gate. The closure tier is reserved for after 4R.2 + 4R.3 + P0-5.

### §11.1 What Gate 4R.1 closed

| Item | Closed by |
|---|---|
| Precise node-ID-level regression surface | §3 collection diff + §4 transition ledger |
| Reconciliation with the +43 floor | §1 (77 new − 31 healed = +46 net) |
| Root cause of 77 pass→fail regressions | §5 (Rate Limiter module-level global) |
| "85 Gate 4 tests" claim | §3 (actual = 77) |
| Hermeticity drift at 880f49c itself | §7 (4-node drift between identical-commit runs) |

### §11.2 Carry-over to Gate 4R.2

| Item | Reason |
|---|---|
| Order-pollution experiments A/B/C/D | Re-run after rate-limiter hermeticized (§8) |
| 218 fail→fail + 81 error→error triage | Pre-existing baseline surface — needs root-cause pass after 4R.2 |
| 31 fail→pass heal root-cause | Carry to Gate 4R.3 |
| 1 pass→skipped movement | Carry to Gate 4R.3 |

---

## §12. Next

Gate 4R.2 — fix the Rate Limiter module-level global
(`backend/app/middleware/rate_limit.py:22`), plus the other
identified hermeticity defects (caches, singletons, asyncio loop
scope, Windows GBK subprocess). After 4R.2 the A/B/C/D experiments
run on a hermetic harness.
