# Phase A1A Gate 4R.0 — Evidence Freeze & Correction Notice

**Date**: 2026-07-20
**Branch**: `phase-a1a/gate4r-regression-reconciliation`
**Commit (this artefact)**: see Gate 4R.0 commit at the end of this file
**Predecessor**: `b3ea064` (Phase A1A Gate 4.9 closure report)
**Successor**: Gate 4R.1 (precise pytest node-ID diff between `b737eab` and `880f49c`)

Charter §4R.0: freeze the evidence, then publish a 7-point
correction notice that supersedes the most load-bearing claims made by
the Gate 4.8 and Gate 4.9 reports. The original Gate 4.8 and Gate 4.9
reports are NOT silently rewritten — they remain in the tree as
frozen-in-time historical evidence. Their claims are formally
superseded by this notice, not edited in place.

---

## §1. Mandatory state for Gate 4R

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

These five values are the load-bearing state of Gate 4R. They must
appear verbatim in every Gate 4R.x sub-gate report that follows, and
they MUST NOT be weakened (e.g. to `PARTIAL` or `REOPENED_FOR_REVIEW`)
without an explicit superseding gate that re-runs the regression
evidence from scratch.

---

## §2. Frozen evidence artefacts

All artefacts sit under
`reports/phase-a1a/adversarial-audit/evidence-freeze/`. SHA-256 hashes
are recorded in `SHA256SUMS` and reproduced in
`GATE4R_TEST_ENVIRONMENT_MANIFEST.json`.

| File | SHA-256 (prefix) | Role |
|---|---|---|
| `audit_baseline_full.xml` | `5572105b...` | pytest JUnit XML for full suite at `b737eab` (Phase A1A Gate 3R, pre-Gate-4) |
| `audit_baseline_full.log` | `ba00d202...` | stdout/stderr tail of the same run |
| `audit_gate4_full.log` | `eeea222c...` | stdout/stderr tail for full suite at `880f49c` |
| `audit_gate4_summary.txt` | `c0c54c8e...` | 2 ERROR lines + final totals line for `880f49c` |
| `GATE4R_GIT_STATE.txt` | (recorded inline) | `git status`, HEAD, branch, worktree list snapshot |
| `GATE4R_TEST_ENVIRONMENT_MANIFEST.json` | (recorded inline) | Python, OS, package, env var manifest |
| `A1A_GATE4R_0_EVIDENCE_FREEZE_CORRECTION_NOTICE.md` | (this file) | 7-point correction notice |

The Git state snapshot and manifest are first-class evidence, not
metadata: the regression numbers in §3 below are only reproducible if
the reader uses the same Python 3.12.3 + package set + worktree
arrangement documented here.

---

## §3. The 7-point correction notice

The following 7 corrections are formal and load-bearing. Each one
names the original claim, the observed truth, and the artefact that
proves the contradiction.

### §3.1 Correction 1 — Gate 4.8 §1.2 stash method does NOT produce a b737eab baseline

**Original claim** (`A1A_GATE4_8_FULL_SECURITY_REGRESSION_EVIDENCE_CLOSURE.md` §1.2):

> Verification method: `git stash --include-untracked --keep-index`
> ran the suite on the committed baseline (Gate 4.0–4.5 + Gate 3R
> without Gate 4.6/4.7). The 49 failures reproduced on that baseline,
> confirming they predate Gate 4.6/4.7 work.

**Observed truth**: `git stash --include-untracked --keep-index`
applied to a tree that had Gate 4.0–4.7 already layered on top of
Gate 3R does NOT roll the tree back to `b737eab`. It only removes
whatever was uncommitted at the moment of stashing. The resulting
state is "Gate 4.0–4.5 committed + Gate 4.6/4.7 stashed", which is
still far ahead of `b737eab`. The 49 failures observed from that
state are therefore "Gate 4.0–4.5 baseline failures", NOT
"pre-Gate-4 baseline failures".

**Evidence**: `GATE4R_GIT_STATE.txt` shows `b3ea064` as HEAD with
`880f49c` and `b737eab` as ancestors; there is no path by which
`git stash` on this HEAD can produce a `b737eab` worktree. The only
correct way to establish the `b737eab` baseline is the detached-HEAD
worktree at `E:/Corti4C-audit-baseline`, which the present freeze
uses.

**Verdict**: Gate 4.8 §1.2's verification method is INVALID. The
"49 pre-existing failures" triage built on top of it is also invalid.

---

### §3.2 Correction 2 — b737eab 真实完整测试结果是 3237 passed / 249 failed / 81 errors

**Original claim** (implicit in Gate 4.8 §1.2): the pre-Gate-4
baseline failure count is 49.

**Observed truth**: the actual full-suite result at `b737eab` is

```
3237 passed, 249 failed, 81 errors, 12 skipped, 10 deselected, 3 xfailed
```

captured in `audit_baseline_full.xml` (SHA-256 prefix `5572105b...`)
and `audit_baseline_full.log` (SHA-256 prefix `ba00d202...`).

**Interpretation**: the real baseline failure surface is 249 + 81 =
330 failing-or-erroring nodes, NOT 49. This means Gate 4 inherited a
much larger pre-existing test-degradation surface than was reported,
and any "no NEW regression introduced by Gate 4" claim needs to be
evaluated against THIS baseline, not the 49-failure figure.

**Verdict**: b737eab baseline = 3237 passed / 249 failed / 81 errors.
Frozen. Not subject to reinterpretation in later sub-gates.

---

### §3.3 Correction 3 — 880f49c 真实完整测试结果是 3270 passed / 292 failed / 81 errors

**Original claim** (Gate 4.8 §1): total FAILED=50, of which 49 are
"pre-existing" and 1 is a Gate 4.4 cascade already fixed.

**Observed truth**: the actual full-suite result at `880f49c` is

```
3270 passed, 292 failed, 81 errors, 12 skipped, 10 deselected, 3 xfailed
```

captured in `audit_gate4_full.log` (SHA-256 prefix `eeea222c...`)
and `audit_gate4_summary.txt` (SHA-256 prefix `c0c54c8e...`).

**Interpretation**: Gate 4 has 242 more failing nodes and the same
81 errors as the b737eab baseline. Even before a node-ID level
comparison, the raw totals make the Gate 4.8 "no NEW regression"
claim mathematically impossible unless 242 of the baseline failures
concurrently healed — which would itself be a regression event worth
investigating.

**Verdict**: 880f49c full-suite = 3270 passed / 292 failed / 81
errors. Frozen. The Gate 4.8 §1 totals (3576 passed / 50 failed)
are contradicted.

---

### §3.4 Correction 4 — 当前只能确认 +43 net FAIL，不能确认精确新增失败节点数

**Original claim** (Gate 4.8 §1): Gate 4 introduces "no NEW
regressions outside the Gate 4 surface".

**Observed truth**: the difference between §3.2 and §3.3 is

```
292 - 249 = +43 个净 FAIL 结果
```

This is a NET figure: it is the difference between two aggregate
counts. It does NOT say "43 baseline-PASS nodes became FAIL at
Gate 4". To assert that, we need a pytest node-ID set comparison
(baseline_pass ∩ gate4_fail), which is the Gate 4R.1 deliverable.

What the +43 net figure DOES establish is a floor: Gate 4 has at
least 43 more failing nodes than b737eab, after the same full-suite
treatment. The actual number of newly-regressed baseline-PASS nodes
may be higher (if some baseline-FAIL nodes also healed) or lower (if
many baseline-FAIL nodes healed and the new regressions were even
more numerous). The node-ID comparison will resolve this.

**Phrasing rule (load-bearing)**: until Gate 4R.1 closes, every
report in this branch MUST use the phrasing
"292 - 249 = +43 个净 FAIL 结果" and MUST NOT use the phrasing
"恰好有 43 个 baseline PASS 变成 FAIL". The two phrasings describe
different sets; the latter asserts a fact that has not been
verified.

**Verdict**: +43 net FAIL is the current truth. Anything stronger
is deferred to Gate 4R.1.

---

### §3.5 Correction 5 — Gate 4.8 "no NEW regressions introduced by Gate 4" is CONTRADICTED

**Original claim**: Gate 4.8 §1.2 closing paragraph —

> The pre-existing failures are acknowledged as carry-over to a
> future phase (not a Gate 4 deliverable to fix). Gate 4's contract
> is "no NEW regressions introduced by Gate 4 work" — that contract
> holds.

**Observed truth**: per Corrections 2 and 3, the full-suite
aggregate failure count went from 249 to 292. Regardless of which
specific nodes flipped, the aggregate cannot have grown by 43 and
simultaneously have had "no NEW regressions". The two propositions
are mutually exclusive.

**Verdict**: `GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED`. This
is a frozen verdict — it can only be re-opened by an explicit
superseding gate that reproduces the b737eab and 880f49c full-suite
runs under a different environment AND shows the +43 figure
disappearing. Gate 4R.1–4R.3 will not attempt this; they take the
+43 as the starting point.

---

### §3.6 Correction 6 — Gate 4.9 final PASS is SUPERSEDED

**Original claim** (`A1A_GATE4_9_COMMIT_FINAL_VERDICT.md` §4):

```
PASS_A1A_GATE4_PHI_BOUNDARY_LIVE_PATH_TENANT_ISOLATION_AT_REST_RESIDENCY_BROWSER_RETENTION_VERIFIED
```

…and §4.2 lists 10 threats (T-CC-1/2/3/4/5/10/11 +
GATE3R_011/014/015) as "closed".

**Observed truth**:

1. The PASS verdict rests on Gate 4.8's regression evidence, which
   Correction 5 has just marked CONTRADICTED. A verdict that rests
   on a contradicted evidence base cannot itself stand.
2. Several of the 10 "closed" threats have known open contradictions
   at the code level (e.g. `data_policy.can_use_provider` has zero
   call sites; `audit_detail_redactor` is only wired through
   `log_action`, not through `system_audit` / `tenant_owned_system_audit`;
   `phi_redactor`'s "fail-closed" actually returns a
   `[REDACTION_FAILED]` placeholder and the request continues). The
   full threat-by-threat re-reconciliation is the Gate 4R.3 and
   later sub-gates' job; for Gate 4R.0, the aggregate verdict
   correction is sufficient.

**Verdict**: `GATE4_9_FINAL_PASS = SUPERSEDED`. The PASS_A1A_GATE4_*
verdict string is NOT to be cited as a current truth anywhere in the
4R sub-gates. It remains in `A1A_GATE4_9_COMMIT_FINAL_VERDICT.md` as
frozen historical evidence.

---

### §3.7 Correction 7 — 原始 Gate 4.8 和 Gate 4.9 报告必须保持原样，不得静默改写

**Rule**: the following two files are FROZEN historical evidence and
must NOT be edited in place to reflect the corrections above:

- `reports/phase-a1a/A1A_GATE4_8_FULL_SECURITY_REGRESSION_EVIDENCE_CLOSURE.md`
- `reports/phase-a1a/A1A_GATE4_9_COMMIT_FINAL_VERDICT.md`

Any correction, supersession, or refutation MUST live in a NEW file
under `reports/phase-a1a/adversarial-audit/` (this notice and its
siblings) and MUST cite the original report by relative path.

**Why**: in-place edits would destroy the audit trail. A future
auditor reading Gate 4.8 in 2027 needs to see what was claimed in
2026-07-20 even if the claim was wrong. The CORRECTION LAYER is the
authoritative current truth; the CLAIMED LAYER is the frozen
historical position.

**Verdict**: the two original reports are preserved. Their claims
are formally superseded by this notice. Any future edit to either
file requires a new superseding gate AND an explicit
"superseeded-by" pointer added to the top of the original — never
a content rewrite.

---

## §4. What Gate 4R.0 does NOT do

For avoidance of doubt, Gate 4R.0 explicitly does NOT:

- Identify which specific nodes regressed (→ Gate 4R.1)
- Identify which specific nodes healed (→ Gate 4R.1)
- Fix any test infrastructure non-hermeticity (→ Gate 4R.2)
- Fix any specific regression (→ Gate 4R.3)
- Re-adjudicate any of the 10 "closed" threats at the code level
  (→ later 4R sub-gates, after 4R.1–4R.3 close)
- Re-issue any PASS verdict (forbidden by charter §22 for the
  duration of the 4R work)
- Touch master, push, open a PR, amend any prior commit, or use
  `git add -A`

---

## §5. Forbidden list for Gate 4R.0

| Forbidden action | Status |
|---|---|
| Modify any Medical Coding / CDI / DRG-DIP prompt | NOT TOUCHED ✓ |
| Touch real patient data | NOT TOUCHED ✓ |
| Push to remote | NOT PUSHED ✓ |
| Create PR | NOT CREATED ✓ |
| Commit to master | NOT COMMITTED ✓ |
| Amend `b737eab`, `880f49c`, or `b3ea064` | NOT AMENDED ✓ |
| Use `git add -A` | NOT USED (explicit file list below) ✓ |
| Edit Gate 4.8 or Gate 4.9 reports in place | NOT EDITED ✓ |
| Issue any charter §22 forbidden verdict | NOT ISSUED ✓ |
| Weaken fail-closed contracts to make tests pass | NOT DONE ✓ |
| Modify JWT/encryption/PHI redaction to make tests pass | NOT DONE ✓ |

---

## §6. Files in this Gate 4R.0 commit

Explicit file list (no `git add -A`):

```
reports/phase-a1a/adversarial-audit/evidence-freeze/SHA256SUMS
reports/phase-a1a/adversarial-audit/evidence-freeze/GATE4R_GIT_STATE.txt
reports/phase-a1a/adversarial-audit/evidence-freeze/GATE4R_TEST_ENVIRONMENT_MANIFEST.json
reports/phase-a1a/adversarial-audit/evidence-freeze/A1A_GATE4R_0_EVIDENCE_FREEZE_CORRECTION_NOTICE.md
reports/phase-a1a/adversarial-audit/evidence-freeze/audit_baseline_full.xml
reports/phase-a1a/adversarial-audit/evidence-freeze/audit_baseline_full.log
reports/phase-a1a/adversarial-audit/evidence-freeze/audit_gate4_full.log
reports/phase-a1a/adversarial-audit/evidence-freeze/audit_gate4_summary.txt
```

---

## §7. Provisional verdict

```
PASS_A1A_GATE4R_0_EVIDENCE_FREEZEN_AND_CORRECTION_NOTICE_FILED
```

Tier intentionally NOT `VERIFIED` and NOT `PRODUCTION_READY` —
Gate 4R.0 is an evidence-and-correction gate, not a closure gate.
The closure tier (`PASS_A1A_GATE4R_P0_5_REGRESSION_RECONCILIATION_TEST_HARNESS_HERMETICITY_VERIFIED`)
is reserved for after Gate 4R.1, 4R.2, 4R.3 and the 12 P0-5 closure
conditions have all closed.

### §7.1 What Gate 4R.0 closed

| Item | Closed by |
|---|---|
| Evidence base for every subsequent 4R sub-gate | Frozen artefacts in §2 |
| Mandatory 5-tuple state for 4R | §1 |
| Method-of-record contradiction against Gate 4.8 §1.2 stash | §3.1 |
| True b737eab baseline numbers | §3.2 |
| True 880f49c numbers | §3.3 |
| Net-FAIL figure floor | §3.4 (+43 net) |
| `GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED` | §3.5 |
| `GATE4_9_FINAL_PASS = SUPERSEDED` | §3.6 |
| In-place-edit prohibition on Gate 4.8 / 4.9 reports | §3.7 |

### §7.2 Carry-over to Gate 4R.1

| Item | Reason |
|---|---|
| Per-node PASS→FAIL flips | Requires pytest node-ID set comparison |
| Per-node FAIL→PASS heals | Same |
| Order-pollution experiments A/B/C/D | Same |
| Node transition ledger | Same |

---

## §8. Next

Gate 4R.1 — precise pytest node-ID diff between `b737eab` and
`880f49c`, with collection-only runs in both worktrees, a shared
node filter plugin, 4 order-pollution experiments, and the node
transition ledger.
