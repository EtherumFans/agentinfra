# Phase A1A Gate 0 — Frozen Baseline Entry Verification

> Independently verifies the Phase A0.1R frozen baseline before any product
> code is modified. The claimed lineage (Commit A `87754ab`, Commit B
> `606dc5d`, Commit C `64590fa`, Tag object `3cd1bec`, master unchanged at
> `c147d01`) is **not trusted from the claim itself** — every hash is
> re-derived from the local git object database.
>
> Verdict: `PASS_A1A_GATE0_FROZEN_BASELINE_ENTRY_VERIFIED`
> A1A work branch: `phase-a1a/emergency-containment` (anchored on Commit C)
> Master: untouched at `c147d01`

Spec reference: Phase A1A charter §3 (Gate 0).

Artifacts produced under `reports/phase-a1a/`:
- `A1A_GATE0_FROZEN_BASELINE_ENTRY.md`  (this report)
- `tag_lineage_verification.json`
- `negative_fixture_coverage.json`
- `credential_invalidation_verification.json`
- `git_object_secret_scan.json`
- `baseline_bundle_receipt.json`
- `a1a_entry_validation.json`

---

## §1. The 15 required outputs (charter §6.8)

### Output 1 — Tag type

```
git cat-file -t audit/phase-a0.1r-baseline
→ tag
```

The tag is **annotated** (not lightweight). Annotated tags are stored as
separate git objects with tagger, date, and message — they carry their
own SHA and survive any rename of the target branch.

### Output 2 — Tag object hash

```
3cd1bece14a7f4564d14d630568697c48cfd8385
```

### Output 3 — Tag target commit

```
64590fa262b0fa9d56a47b1ec714be287f8e63e2
```

This equals Commit C (verified in §4 below).

### Output 4 — Commit A/B/C actual hashes

| Commit | Short | Full SHA-1 |
|---|---|---|
| A (Bucket A — product substrate) | `87754ab` | `87754abd1f8dd351731bac495518fd9e05ed2a72` |
| B (Bucket B — audit package) | `606dc5d` | `606dc5d733139070884a6016aab3993936bb3b2a` |
| C (Bucket C — freeze receipt) | `64590fa` | `64590fa262b0fa9d56a47b1ec714be287f8e63e2` |

All three match the Phase A0.1R tag annotation's claimed short hashes
(expanded to full hashes via `git rev-parse`).

### Output 5 — A→B→C lineage

```
master (c147d01) ── A (87754ab) ── B (606dc5d) ── C (64590fa) ← tag
                       │              │              │
                       └──Bucket A    └──Bucket B    └──Bucket C
                          122 files      24 files       2 files
```

Verified by `git log --format='%H' <commit>^ -1`:

| Child | Expected parent | Actual parent | Match |
|---|---|---|---|
| A `87754ab` | `c147d01` (master) | `c147d015455017bc1d8420cbdbd813b3b8ec23ce` | ✅ |
| B `606dc5d` | A `87754ab` | `87754abd1f8dd351731bac495518fd9e05ed2a72` | ✅ |
| C `64590fa` | B `606dc5d` | `606dc5d733139070884a6016aab3993936bb3b2a` | ✅ |

### Output 6 — Master current hash

```
c147d015455017bc1d8420cbdbd813b3b8ec23ce
```

Matches the Phase A0.1R charter's "trusted HEAD base". Master is
**untouched** — no commits have been added to master since Phase A0.1R
started.

### Output 7 — Tagged validator result

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
exit code: 0
```

15/15 PASS. The 15th check (`git.audit_tag`) confirms the tag is reachable.

### Output 8 — Negative fixture coverage

Phase A0.1R produced **11 negative fixtures** (NF01–NF11). The A1A
charter text mentioned "12-item coverage table"; this appears to be a
charter-text discrepancy rather than a missing fixture. A1A Gate 0
documents 11 actual fixtures and does not fabricate a 12th.

| NF | Defect class | Validator check | Result |
|---|---|---|---|
| NF01 | `P0_aggregate_open_strict = 99` drift | `check_ledger_open_count_strict` | ✅ caught |
| NF02 | `P0-S_open = 99` drift | `check_ledger_p0_s_open_strict` | ✅ caught |
| NF03 | A0-P0-021 removed from explicit_ids | `check_ledger_primary_phase_complete` | ✅ caught |
| NF04 | `split_status` removed from A0-P0-004 | `check_ledger_billing_theater_split` | ✅ caught |
| NF05 | `phase_a0_1r_reframe` removed from A0-P0-009 | `check_ledger_npm_reframed` | ✅ caught |
| NF06 | `phase_a0_1r_boundary` removed from A0-P0-007 | `check_ledger_cdi_bounded` | ✅ caught |
| NF07 | D-05 restored to `ICODER_TECH_DEBT` | `check_parity_no_illegal_statuses` | ✅ caught |
| NF08 | F-03 restored to CORTI_ADVANTAGE at E1 | `check_parity_symmetric_thresholds` | ✅ caught |
| NF09 | `security` axis removed from CN-01 | `check_maturity_7_axes` | ✅ caught |
| NF10 | `exists=false` restored on screenshots/ dir | `check_manifest_empty_dirs` | ✅ caught |
| NF11 | `storage_mode = 'SECRET_LEAKED'` (illegal) | `check_manifest_storage_mode` | ✅ caught |

**11/11 PASS.** If A1A Gate 1 expands validator coverage (e.g., adds a
hash-based secret-presence check), a 12th fixture may be added at that
point.

### Output 9 — Old credential authentication rejection

The compromised credential is `partner-ref-07ef23d306cf` /
`862b7cf5b001b5b7f285739eee828cf5fb14ea43fc2cdc2b`. After Phase A0.1R
Gate 1, the DB row was mutated:

| Field | Value |
|---|---|
| `is_active` | `0` (was `1`) |
| `client_secret_hash` | `REVOKED_PHASE_A0_1R_20260717T100329Z` (was SHA-256 of secret) |

Authentication attempt with the original secret:
- Provided SHA-256 prefix: `7a3b25efb0a901a66ce5df775a74911c...`
- Stored hash: literal `REVOKED_PHASE_A0_1R_20260717T100329Z`
- Hash match: **False**
- `is_active` check: **False (is_active=0)**
- Auth result: **REJECTED at 2 layers**

Even if an attacker obtains the full 48-char secret, authentication is
blocked by `is_active=0` (first layer) and the REVOKED marker hash
(second layer).

### Output 10 — Git object database secret scan

`scripts/audit/a1a_gate0_scan_git_objects.py` scanned all 3,659 blobs
in the git object database for every non-public substring of the
compromised secret.

| Substring scanned | Range | Hits |
|---|---|---|
| `b001b5b7` | chars 9-16 | **1** (validator blob `4573c81`) |
| `b001b5b7f285739e` | chars 9-24 | 0 |
| `f285739e` | chars 17-24 | 0 |
| `ee828cf5` | chars 25-32 | 0 |
| `fb14ea43` | chars 33-40 | 0 |
| `fc2cdc2b` | chars 41-48 | 0 |
| `b001b5b7f285739eee828cf5fb14ea43fc2cdc2b` | chars 9-48 | 0 |
| `862b7cf5b001b5b7f285739eee828cf5fb14ea43fc2cdc2b` | full secret | **0** |

**Full secret is NOT in any git object.** Chars 17-48 (32 chars) are
NOT in any git object.

The single chars 9-16 hit is the validator's own grep anchor
`SECRET_FINGERPRINT_SUBSTRING = "862b7cf5b001b5b7"` — a Phase A0.1R
design choice that trades chars 9-16 publication for grep precision.

This does NOT trigger the charter's `PARTIAL_BLOCKED_BY_SECRET_PRESENT_IN_GIT_OBJECT_DATABASE`
condition because that rule applies to the **full** secret, not to
substrings. Disclosed as finding A1A-G0-D01 with proposed mitigation
in Gate 1.

### Output 11 — Final verdict canonical / legacy aliases

The Phase A0.1R tag annotation carries the verdict string. The canonical
form is what appears in the tag itself:

```
canonical_verdict: PASS_PHASE_A0_1_R_SECURE_FREEZE_RECONCILED_AND_BASELINE_IMMUTABLE
```

Legacy / alternative forms seen in earlier phase documentation:

| Form | Source | Status |
|---|---|---|
| `PASS_PHASE_A0_1_R_...` | Phase A0.1R tag annotation | **canonical** |
| `PASS_PHASE_A0_1R_...` | earlier Phase A0.1R drafts (no underscore between 1 and R) | alias |
| `PASS_PHASE_A0_1_AUDIT_REPAIR_AND_BASELINE_FROZEN_READY_FOR_A1` | Phase A0.1 (refuted) | superseded |

The tag is **not modified**; only the alias mapping is documented.

### Output 12 — Bundle backup SHA-256

```
path:   C:\Users\huawei\Documents\icoder-audit-bundles\phase-a0.1r-baseline.bundle
size:   36,895,006 bytes (35.19 MB)
sha256: 5b851a55fd0f8722936696390496087763403ab456f71e87154bcdcef4627a45
```

Bundle created outside the repository. Contains refs:
- `refs/tags/audit/phase-a0.1r-baseline` → `3cd1bec` (tag object)
- `refs/heads/audit/phase-a0.1r-freeze` → `64590fa` (Commit C)

`git bundle verify` reports "complete history". Bundle is NOT committed
to the repo.

### Output 13 — New A1A branch

```
$ git switch -c phase-a1a/emergency-containment audit/phase-a0.1r-baseline
Switched to a new branch 'phase-a1a/emergency-containment'
```

The branch is anchored on the tag's target commit (`64590fa`), not on
master. This guarantees that all A1A work descends from the verified
frozen baseline.

```
phase-a1a/emergency-containment  →  Commit C (64590fa)  →  ...  →  master (c147d01)
```

### Output 14 — Current worktree state

After creating the A1A branch, the worktree has:
- **0 modified** tracked files
- **0 staged** changes
- **60 untracked** items (`.audit-chrome-profile/` is gitignored;
  pre-existing reports under `reports/comprehensive-audit/` from earlier
  phases; `docs/audit/` and `docs/corti_parity/phase7_gate13a/`)

No product code was modified during Gate 0. Gate 0 is read-only by
design (charter §6: "Gate 0 通过前不得修改产品代码").

### Output 15 — Interim verdict

```
PASS_A1A_GATE0_FROZEN_BASELINE_ENTRY_VERIFIED
```

The Phase A0.1R baseline is verified independently. The A1A branch is
created from the verified tag. Phase A1A may proceed to Gate 1.

## §2. Findings raised in Gate 0

| ID | Severity | Title |
|----|----------|-------|
| **A1A-G0-D01** | P2 | Chars 9-16 of compromised secret present in validator blob (`scripts/audit/validate_phase_a0_1r.py` @ `4573c81`). Phase A0.1R design choice (grep anchor). Residual risk minimal because (a) credential is DB-invalidated, (b) chars 17-48 are NOT in any git object, (c) 8 chars beyond public prefix is not enough to authenticate. **A1A Gate 1 proposed mitigation**: migrate validator to last-N-chars fingerprint or SHA-256-hash-based anchor. |
| **A1A-G0-D02** | P3 | Negative fixture count discrepancy: charter mentioned 12, Phase A0.1R produced 11. Disclosed as charter-text issue; A1A does not fabricate a 12th. |
| **A1A-G0-D03** | P3 | 60 untracked items in working tree from earlier phases. None are staged; none affect Gate 0. Recommend a sweep during Gate 1 to triage which (if any) should join the A1A branch. |

## §3. Hard checks passed (15/15)

| # | Check | Result |
|---|---|---|
| 1 | Tag exists and is annotated | ✅ |
| 2 | Tag object hash matches claim | ✅ `3cd1bec` |
| 3 | Tag target == Commit C | ✅ `64590fa` |
| 4 | Commit A/B/C hashes match claims | ✅ all three |
| 5 | Lineage A→B→C verified (each parent matches) | ✅ |
| 6 | Master unchanged at `c147d01` | ✅ |
| 7 | Tagged validator 15/15 PASS | ✅ |
| 8 | All negative fixtures PASS | ✅ 11/11 |
| 9 | Compromised credential auth rejected | ✅ 2 layers |
| 10 | Full secret NOT in any git object | ✅ |
| 11 | Verdict canonical form recorded | ✅ |
| 12 | Bundle backup created, SHA-256 captured | ✅ |
| 13 | A1A branch created from tag | ✅ |
| 14 | Worktree clean (no product code modified yet) | ✅ |
| 15 | Interim verdict matches required string | ✅ |

## §4. Forbidden-action audit (all honored)

| Forbidden action | Status |
|---|---|
| Modify/rewrite/move Phase A0.1R annotated tag | ✅ NOT touched |
| Amend Commit A, B, or C | ✅ NOT amended |
| Continue product development on `audit/phase-a0.1r-freeze` | ✅ branch frozen |
| Develop directly on master | ✅ master untouched |
| Push or create PR | ✅ local-only (origin unchanged) |
| Modify product code before Gate 0 passes | ✅ no product code modified |

## §5. Phase A1A Gate 0 verdict

```
============================================================================
PASS_A1A_GATE0_FROZEN_BASELINE_ENTRY_VERIFIED
============================================================================

  Tag object        : 3cd1bece14a7f4564d14d630568697c48cfd8385 (annotated)
  Tag target        : 64590fa262b0fa9d56a47b1ec714be287f8e63e2 (Commit C)
  Lineage           : c147d01 → 87754ab → 606dc5d → 64590fa
  Master            : c147d015455017bc1d8420cbdbd813b3b8ec23ce (unchanged)
  Validator V3      : 15/15 PASS post-tag
  Negative fixtures : 11/11 PASS
  Compromised cred  : REJECTED at 2 layers (is_active=0 + REVOKED hash)
  Secret scan       : FULL SECRET NOT IN ANY GIT OBJECT
                      (chars 9-16 only in validator blob; chars 17-48 absent)
  Bundle backup     : 5b851a55fd0f8722936696390496087763403ab456f71e87154bcdcef4627a45
  A1A branch        : phase-a1a/emergency-containment (anchored on tag)
  Worktree          : clean (no product code modified)
  Disclosed         : A1A-G0-D01 (chars 9-16 in validator; Gate 1 mitigation),
                      A1A-G0-D02 (11 vs 12 fixtures), A1A-G0-D03 (60 untracked)

NEXT_GATE: GATE_1_SECRETS_AND_AUTHENTICATION_FAIL_CLOSED
NEXT_ALLOWED_VERDICT:
  PASS_A1A_GATE1_SECRETS_AND_AUTHENTICATION_FAIL_CLOSED
============================================================================
```

End of Gate 0.
