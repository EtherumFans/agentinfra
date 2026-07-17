# Phase A1A Gate 0 Addendum — Sub-gate 0D
## Git Bundle Verify and Restore Test

> Confirms the bundle backup created in Gate 0 output 12 is a valid
> disaster-recovery artifact: it can be `git clone`d to a fresh repo,
> all refs and history are present, and the validator V3 passes 15/15
> in the restored repo.

Spec reference: Phase A1A charter §6.6 (Gate 0 Addendum sub-gate 0D).

Artifacts under `reports/phase-a1a/`:
- `A1A_GATE0D_BUNDLE_VERIFY_AND_RESTORE.md`  (this report)
- `bundle_restore_verification.json`           (machine-readable proof)

---

## §1. Bundle file

```
path:   C:\Users\huawei\Documents\icoder-audit-bundles\phase-a0.1r-baseline.bundle
size:   36,895,006 bytes (35.19 MB)
sha256: 5b851a55fd0f8722936696390496087763403ab456f71e87154bcdcef4627a45
```

Location is **outside the repository** per Phase A1A charter rule
(bundle must not be committed to the repo it backs up).

SHA-256 matches Gate 0 output 12 (`baseline_bundle_receipt.json`).

---

## §2. `git bundle verify`

```
$ git bundle verify phase-a0.1r-baseline.bundle
The bundle contains these 2 refs:
3cd1bece14a7f4564d14d630568697c48cfd8385 refs/tags/audit/phase-a0.1r-baseline
64590fa262b0fa9d56a47b1ec714be287f8e63e2 refs/heads/audit/phase-a0.1r-freeze
The bundle records a complete history.
The bundle uses this hash algorithm: sha1
C:/Users/huawei/Documents/icoder-audit-bundles/phase-a0.1r-baseline.bundle is okay
```

**Result**: bundle is well-formed, history complete, both refs advertised.

---

## §3. Restore test

### Clone

```
$ git clone phase-a0.1r-baseline.bundle restored-repo
Cloning into 'restored-repo'...
warning: remote HEAD refers to nonexistent ref, unable to checkout
```

The "remote HEAD" warning is benign — bundles don't carry a default-branch
hint. After clone, both refs are present; we just need to check out one.

### Refs restored

```
$ git for-each-ref
64590fa262b0fa9d56a47b1ec714be287f8e63e2 commit  refs/remotes/origin/audit/phase-a0.1r-freeze
3cd1bece14a7f4564d14d630568697c48cfd8385 tag     refs/tags/audit/phase-a0.1r-baseline
```

Both refs match the live repo:
- `audit/phase-a0.1r-baseline` → `3cd1bec` (tag object) ✅
- `audit/phase-a0.1r-freeze` → `64590fa` (Commit C) ✅

### Checkout

```
$ git checkout audit/phase-a0.1r-freeze
Switched to a new branch 'audit/phase-a0.1r-freeze'
$ git rev-parse HEAD
64590fa262b0fa9d56a47b1ec714be287f8e63e2
```

HEAD = Commit C ✅

### Lineage

```
$ git log --oneline -5
64590fa audit/phase-a0.1r: freeze receipt (Bucket C) — Phase A0.1R Gate 9
606dc5d audit/phase-a0.1r: audit package (Bucket B) — Phase A0.1R Gate 9
87754ab audit/phase-a0.1r: audited product snapshot (Bucket A) — Phase A0.1R Gate 8
c147d01 feat(track-h): Tier 2 Corti controlled probes — H1.2/H1.3/H1.4 close 4 UNKNOWN capability cells
79b2b03 feat(track-h): H4.2 freeze iter 7 baseline as icoder-cdi-agent-v1.0.0-rc5
```

A→B→C lineage intact. Commit A's parent is `c147d01` (master).

```
$ git rev-list --count c147d01..64590fa
3
```

Exactly 3 commits between master and freeze tip (A, B, C). ✅

---

## §4. Tag object in restored repo

```
$ git cat-file -t 3cd1bec
tag

$ git cat-file -p 3cd1bec
object 64590fa262b0fa9d56a47b1ec714be287f8e63e2
type commit
tag audit/phase-a0.1r-baseline
tagger SONG Luhua <30805278@qq.com> 1784285329 +0800

Phase A0.1R — Secure Freeze Reconciliation baseline.

Verdict: PASS_PHASE_A0_1_R_SECURE_FREEZE_RECONCILED_AND_BASELINE_IMMUTABLE
READY_FOR_PHASE_A1A_EMERGENCY_SECURITY_TENANCY_PHI_AND_TRUTH_CONTAINMENT
```

Tag is annotated, points to Commit C, carries the canonical verdict
string. ✅

---

## §5. Validator V3 in restored repo

```
$ python scripts/audit/validate_phase_a0_1r.py

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
  [PASS] git.trusted_head: c147d0154550 is ancestor of 64590fa262b0
  [PASS] git.branch: current=audit/phase-a0.1r-freeze
  [PASS] git.audit_tag: audit/phase-a0.1r-baseline exists

Total: 15, PASS: 15, FAIL: 0
```

**15/15 PASS in the restored repo.** The frozen baseline is reproducible
from the bundle alone.

---

## §6. Negative fixtures in restored repo

```
$ python scripts/audit/run_negative_fixtures_a0_1r.py
[NF01] … [NF11] — all PASS
=== Negative fixture summary ===
  All fixtures passed: True
```

**11/11 PASS** in the restored repo.

### Why 11, not 12?

The bundle is the **Phase A0.1R Gate 9** frozen baseline. NF12 was
added later in **A1A Gate 0 Addendum sub-gate 0A**; it lives only on
the `phase-a1a/emergency-containment` branch, not in Commit B
(`606dc5d`).

```
$ grep -c NF12 scripts/audit/run_negative_fixtures_a0_1r.py  # in restored repo
0
```

This is correct behavior: the bundle reflects the state at freeze time.
If NF12 must be reproduced in a disaster recovery scenario, copy the
A1A-branch version of the script or re-apply the +21-line patch
documented in sub-gate 0C.

---

## §7. Object counts

```
$ git cat-file --batch-all-objects --batch-check | awk '{print $2}' | sort | uniq -c
   3599 blob
    281 commit
      1 tag
   2835 tree

$ git rev-list --all --count
281
```

281 commits reachable from all refs. 6716 total objects in pack.
Bundle reports `complete history` — verified.

---

## §8. Disaster recovery scenario

**Question**: if the local repo is corrupted or deleted, can the frozen
baseline be reconstructed from the bundle alone?

**Answer**: **YES**.

| Step | Command | Result |
|---|---|---|
| 1. Restore | `git clone <bundle> restored-repo` | working repo at HEAD=64590fa |
| 2. Verify tag | `git cat-file -t 3cd1bec` | tag |
| 3. Verify lineage | `git log --oneline -5` | A→B→C lineage intact |
| 4. Run validator | `python scripts/audit/validate_phase_a0_1r.py` | 15/15 PASS |
| 5. Run negative fixtures | `python scripts/audit/run_negative_fixtures_a0_1r.py` | 11/11 PASS (bundle's pre-A1A state) |

The bundle is a complete, self-contained disaster-recovery artifact.

---

## §9. Cleanup

```
$ rm -rf /tmp/a1a-bundle-restore-test
temp restore dir removed
```

Temp restore dir removed. Bundle file remains at
`C:\Users\huawei\Documents\icoder-audit-bundles\phase-a0.1r-baseline.bundle`.

---

## §10. Verdict

```
============================================================================
SUB-GATE 0D: BUNDLE_VERIFY_AND_RESTORE_PROVEN
============================================================================

  Bundle file       : C:/Users/huawei/Documents/icoder-audit-bundles/
                      phase-a0.1r-baseline.bundle (35.19 MB)
  Bundle SHA-256    : 5b851a55fd0f8722936696390496087763403ab456f71e87154bcdcef4627a45
  git bundle verify : complete history, 2 refs advertised, "is okay"
  Clone test        : 6716 objects, 281 commits, 1 tag, 2835 trees restored
  Tag in bundle     : 3cd1bec (annotated, target 64590fa, canonical verdict)
  Validator V3      : 15/15 PASS in restored repo
  Negative fixtures : 11/11 PASS in restored repo (pre-A1A state, by design)
  Disaster recovery : PROVEN — bundle alone reproduces working repo
  Cleanup           : temp restore dir removed; bundle retained

NEXT: Sub-gate 0E — Secret Fingerprint Migration Plan
============================================================================
```

End of Sub-gate 0D.
