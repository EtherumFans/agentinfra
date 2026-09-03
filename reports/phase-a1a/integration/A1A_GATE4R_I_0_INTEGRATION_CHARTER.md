# Phase A1A Gate 4R-I — Integration Charter (Gate 4R-I.0)

**Date**: 2026-07-21
**Branch target**: `phase-a1a/emergency-containment`
**Branch source**: `phase-a1a/gate4r-regression-reconciliation` (HEAD `24967da`)
**Predecessor immutable anchors**:
- `audit/phase-a0.1r-baseline` (tag, obj `3cd1bec`, on `64590fa`)
- `b3ea064` (Phase A1A Gate 4.9 closure — final verdict artefact for Gate 4)
- `24967da` (Phase A1A Gate 4R P0-5 closure)

---

## §1. Why this Charter exists

Phase A1A Gate 4R closed a sub-charter (P0-5 regression reconciliation +
test-harness hermeticity) but did NOT close Gate 4 itself. The 4R work lives
on a local-only branch `phase-a1a/gate4r-regression-reconciliation` (5 commits,
`a2613b7`..`24967da`). The integration back into `phase-a1a/emergency-containment`
must be:

- explicit (no fast-forward);
- auditable (annotated tags + evidence freeze + pre-merge diff snapshot);
- non-destructive (no amend of `b3ea064`, `880f49c`, `b737eab`, `24967da`,
  or any ancestor);
- Charter-bounded (does not reopen Gate 4, does not assert Corti parity,
  does not claim production readiness).

Without integration, the 4R hermeticity fix (Rate Limiter per-app-state binding
+ conftest autouse fixture + `asyncio_default_fixture_loop_scope = session`)
cannot flow into the main A1A work branch, and every future pytest run on
`phase-a1a/emergency-containment` inherits the pre-4R.2 hermeticity defect.

## §2. Authorization (in scope)

This Charter authorizes, and only authorizes:

A. Local Git branch integration via `git merge --no-ff` of
   `phase-a1a/gate4r-regression-reconciliation` into
   `phase-a1a/emergency-containment`.
B. Worktree and project directory reorganization (index-first; no large-scale
   moves of historical reports).
C. Test, API, product, clinical quality, operations, and release gap audit.
D. Generation of indexes, reports, evidence, and follow-on development backlog.
E. Repair of mechanical issues introduced by the reorganization itself
   (broken paths, stale references, missing manifests).
F. Repair of pre-existing mechanical issues explicitly listed in §7 of the
   originating task brief (wrong-DB tests, source-tree-writes, schema drift,
   broken paths, stale product-name assertions).

## §3. Out of scope (NOT authorized)

This Charter does NOT authorize:

- Merge to `master`; modify `origin/master`; push; create PR; deploy.
- Use of real patient data; calls to real Corti API; calls to real LLM Provider.
- Rewrite of `b737eab`, `880f49c`, `b3ea064`, `24967da`, or any ancestor.
- Rebase or squash of audit history.
- Deletion of audit branches or audit tags.
- Modification of Medical Coding / CDI / DRG-DIP clinical prompts
  (requires a separate clinical quality Charter).
- Weakening of JWT, tenant boundary, encryption, redaction, egress, retention,
  or fail-closed controls to pass tests.
- Marketing-style Corti parity claims.
- Copy of Corti proprietary code, prompts, UI assets, trademarks, or
  non-public material.

## §4. Snapshots preserved by this Charter

| Object | Role | Mutability after this Charter |
|---|---|---|
| `audit/phase-a0.1r-baseline` (tag `3cd1bec`) | A0.1R immutable anchor | IMMUTABLE |
| `audit/phase-a0.1r-freeze` (branch `64590fa`) | A0.1R freeze branch | NOT DELETED |
| `b3ea064` | Phase A1A Gate 4.9 closure snapshot | IMMUTABLE (anchored by new tag) |
| `24967da` | Phase A1A Gate 4R P0-5 closure snapshot | IMMUTABLE (anchored by new tag) |
| `phase-a1a/gate4r-regression-reconciliation` (branch) | 4R carrier | NOT DELETED |
| `phase-a1a/emergency-containment` (branch) | A1A main work | APPENDED via merge (no rewrite) |

New annotated tags created by this Charter (local-only, never pushed):

- `audit/phase-a1a-gate4-pre4r-b3ea064` on `b3ea064`
- `audit/phase-a1a-gate4r-closure-24967da` on `24967da`

## §5. Merge mechanics

The integration MUST use:

```
git -C E:/Corti4C merge --no-ff --no-commit phase-a1a/gate4r-regression-reconciliation
```

followed by a verification pass and then a single merge commit. The merge
commit message MUST cite this Charter and explicitly state:

- The merge does NOT re-accept Gate 4.
- The merge does NOT assert Corti parity.
- The merge does NOT claim production readiness.
- The 4R branch and tags remain intact.

Conflicts, if any, trigger `git merge --abort`. Auto-selection of
`ours`/`theirs` is FORBIDDEN.

## §6. Acceptance conditions (verified post-merge in Gate 4R-I.1)

1. All 5 Gate 4R commits (`a2613b7`, `e418020`, `fa676b3`, `efbe96b`,
   `24967da`) preserve their original SHA in the merged history.
2. No squash occurred (merge commit has 2 parents: `b3ea064` and `24967da`).
3. `b3ea064` was not rewritten (SHA preserved in `git log`).
4. `master` was not modified.
5. No unexpected untracked databases, logs, or secret files entered the merge
   commit (verified by `git diff --cached --name-only`).
6. The merge diff equals `b3ea064..24967da` (no extra deltas).
7. No real patient data in the merge.
8. No unauthorized clinical prompt modifications in the merge.

## §7. Forbidden verdicts (per originating task §22)

This Charter forbids signing:

- `PRODUCTION_READY`
- `FULLY_VERIFIED`
- `PHI_BOUNDED`
- `CORTI_PARITY_VERIFIED`
- `PASS_A1A_GATE4_FINAL`
- `READY_FOR_HOSPITAL_DEPLOYMENT`
- `CLINICAL_GRADE_VERIFIED`

## §8. Sole allowed final verdict

```
PASS_A1A_GATE4R_INTEGRATION_REPOSITORY_RECONCILIATION_AND_PRODUCT_GAP_AUDIT_FILED
```

This verdict attests ONLY:
- The 4R branch was integrated per this Charter.
- Directory and worktree state was reconciled in a controlled manner.
- Current product state and Corti gap were filed as evidence-backed reports.

This verdict does NOT attest:
- Gate 4 is closed.
- Corti parity is achieved.
- The product is deployable.
- Clinical quality is verified.
- PHI is comprehensively bounded.

## §9. Sub-gate plan

| Sub-gate | Subject | Status |
|---|---|---|
| 4R-I.0 | Charter + evidence freeze + pre-merge tags | THIS FILE |
| 4R-I.1 | Execute `--no-ff` merge into `emergency-containment` | pending |
| 4R-I.2 | Reorganize worktrees/directories/indexes | pending |
| 4R-I.3 | Post-merge regression validation | pending |
| 4R-I.4 | Liquidate known engineering debt | pending |
| 4R-I.5 | Corti official snapshot (clean-room) | pending |
| 4R-I.6 | iCoder capability inventory | pending |
| 4R-I.7 | Clean-room parity matrix | pending |
| 4R-I.8 | Security/compliance release re-audit | pending |
| 4R-I.9 | Release tier verdicts (MVP/Pilot/GA) | pending |
| 4R-I.10 | Development backlog + roadmap | pending |
| 4R-I.11 | Final verdict + closure notice | pending |

## §10. Evidence freeze

Five evidence files under `reports/phase-a1a/integration/evidence/`:

- `PRE_MERGE_GIT_STATE.txt` — current branch, HEAD SHA, recent log
- `PRE_MERGE_WORKTREE_STATE.txt` — `git worktree list --porcelain`
- `PRE_MERGE_BRANCH_REFS.txt` — `git branch -vv`, tags, `show-ref`
- `PRE_MERGE_DIFF_B3EA064_TO_24967DA.txt` — `git diff --stat` and `--name-status`
- `PRE_MERGE_SHA256SUMS.txt` — hashes of evidence files + key refs

All five are committed together with this Charter.

## §11. Pre-merge state summary

```
master                                     c147d01 (origin/master, ahead 85)
audit/phase-a0.1r-freeze                   64590fa  (tag: audit/phase-a0.1r-baseline @ 3cd1bec)
phase-a1a/emergency-containment            b3ea064  (HEAD, main worktree E:/Corti4C)
phase-a1a/gate4r-regression-reconciliation 24967da  (remediation worktree E:/Corti4C-gate4r-remediation)
```

4R diff vs `b3ea064`: 44 files changed, +83205/-32 lines. 5 commits.
0 Medical Coding / CDI / DRG-DIP prompt modifications.
0 JWT / encryption / redaction / fail-closed weakening.

## §12. Forbidden list for this Charter

| Forbidden action | Status |
|---|---|
| Merge to master | NOT AUTHORIZED |
| Modify origin/master | NOT AUTHORIZED |
| Push / create PR | NOT AUTHORIZED |
| Rewrite b3ea064 / 880f49c / b737eab / 24967da / a2613b7 / e418020 / fa676b3 / efbe96b | NOT AUTHORIZED |
| Rebase / squash | NOT AUTHORIZED |
| Delete audit branches or tags | NOT AUTHORIZED |
| Modify clinical prompts | NOT AUTHORIZED |
| Weaken JWT/encryption/redaction/egress/retention/fail-closed | NOT AUTHORIZED |
| Use real patient data | NOT AUTHORIZED |
| Copy Corti proprietary assets | NOT AUTHORIZED |
| Issue forbidden verdicts (§7) | NOT AUTHORIZED |
