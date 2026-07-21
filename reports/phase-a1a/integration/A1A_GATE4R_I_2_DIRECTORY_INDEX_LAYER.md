# Phase A1A Gate 4R-I.2 — Directory Index Layer

**Date**: 2026-07-21
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 4R-I.1 (`ca36c51` no-ff merge)
**Successor**: Gate 4R-I.3 (post-merge regression validation)

Charter §5 requires index-first reorganization: do NOT move historical
reports; add navigation layers on top. This sub-gate creates those
layers.

## §1. Files added (10, explicit list, no git add -A)

```
docs/governance/PROJECT_BRANCH_TOPOLOGY.md
docs/governance/CHARTER_INDEX.md
docs/governance/BASELINE_AND_TAG_REGISTRY.md
docs/governance/BRANCH_RETENTION_POLICY.md
docs/governance/WORKTREE_OPERATING_GUIDE.md
docs/corti-parity/README.md
reports/INDEX.md
reports/phase-a1a/INDEX.md
reports/phase-a1a/integration/README.md
reports/product-audit/README.md
```

Empty directory placeholders created (gitignored via .gitkeep):

```
reports/product-audit/evidence/        (Gate 4R-I.6 will populate)
reports/product-audit/parity/          (Gate 4R-I.7 will populate)
reports/product-audit/release-readiness/ (Gate 4R-I.9 will populate)
reports/product-audit/roadmap/         (Gate 4R-I.10 will populate)
docs/corti-parity/official-snapshot/   (Gate 4R-I.5 will populate)
docs/corti-parity/api-contract/        (Gate 4R-I.7 will populate)
docs/corti-parity/capability-matrix/   (Gate 4R-I.7 will populate)
docs/corti-parity/clean-room/          (Gate 4R-I.7 will populate)
```

## §2. What was NOT moved

Per charter §5.3 "整理原则":

- `reports/comprehensive-audit/` (historical PRE-A0/A0/A0.1 reports)
  — left untracked, NOT promoted to audit branch
- `reports/phase-a1a/adversarial-audit/` (Gate 4R reports)
  — already committed in the 4R branch + merged via 4R-I.1
- `reports/phase6/`, `reports/phase7/` (closed phase reports)
  — left in place
- `docs/audit/` — left untracked, NOT touched
- `docs/corti_parity/phase7_gate13a/` — left untracked
- Root-level `audit_*.xml` evidence files
  — NOT moved or deleted; will be addressed in §3 below

## §3. Scattered root-level evidence (charter §5.3 procedure)

Five evidence files remain at repository root, untracked, that predate
the 4R evidence freeze:

| Path | SHA-256 | Status | Canonical home |
|---|---|---|---|
| `audit_baseline_full.xml` | `5572105b...` | DUPLICATE (matches `reports/phase-a1a/adversarial-audit/evidence-freeze/audit_baseline_full.xml`) | Already canonical; root copy is redundant |
| `audit_gate4_full.xml` | `747c5d89...` | UNIQUE (pre-4R.2 880f49c re-run output; not in canonical evidence-freeze) | Needs promotion to `evidence-freeze/` |
| `audit_gate4_summary.txt` | `c0c54c8e...` | DUPLICATE (matches canonical) | Already canonical |
| `audit_gate4r2_run1.xml` | `e1f68fd3...` | DUPLICATE (matches canonical) | Already canonical |
| `audit_gate4r2_run2.xml` | `50cfd19d...` | DUPLICATE (matches canonical) | Already canonical |

**Disposition (deferred to Gate 4R-I.3 evidence promotion)**:

- The single unique file (`audit_gate4_full.xml`, hash `747c5d89`) is
  evidence of the pre-4R.2 880f49c gate4 full-suite run. The 4R.0
  correction notice references this file by name. Promoting it to
  `reports/phase-a1a/adversarial-audit/evidence-freeze/` and updating
  the canonical `SHA256SUMS` closes a pre-existing evidence gap.

- The 4 duplicates are safe to delete after promotion is verified.

This sub-gate does NOT perform the promotion; it is recorded for
Gate 4R-I.3 to action.

## §4. Worktree state (unchanged per Charter §5)

- `E:/Corti4C` — main worktree on `phase-a1a/emergency-containment` at `ca36c51`
- `E:/Corti4C-gate4r-remediation` — preserved; carries 4R branch at `24967da`

Pre-existing worktrees `E:/Corti4C-audit-baseline` and
`E:/Corti4C-audit-gate4` were removed in an earlier cleanup action
(2026-07-21, pre Gate 4R-I charter). Their evidence is captured in
the JUnit XML files now under `reports/phase-a1a/adversarial-audit/evidence-freeze/`.

## §5. Index-first principle applied

For every "what goes where" question, this sub-gate's answer is:

> If the artefact already exists in a tracked location, add a link in
> the appropriate index file. Do NOT move the artefact.

Examples:

- "Where is the Gate 4.9 closure?" → `reports/phase-a1a/INDEX.md` links to
  commit `b3ea064` (tag `audit/phase-a1a-gate4-pre4r-b3ea064`).
- "Where is the 4R closure?" → `reports/phase-a1a/INDEX.md` links to
  `adversarial-audit/A1A_GATE4R_P0_5_CLOSURE_NOTICE.md` (commit `24967da`).
- "Where is the Rate Limiter fix?" → `docs/governance/PROJECT_BRANCH_TOPOLOGY.md`
  links to commit `fa676b3` (Gate 4R.2).
- "What tags exist?" → `docs/governance/BASELINE_AND_TAG_REGISTRY.md`
  tabulates them.
- "What's the worktree policy?" → `docs/governance/WORKTREE_OPERATING_GUIDE.md`
  documents it.

## §6. Forbidden list for this sub-gate

| Forbidden action | Status |
|---|---|
| Move historical reports | NOT DONE ✓ |
| Rewrite old commits | NOT DONE ✓ |
| Delete audit branches or tags | NOT DONE ✓ |
| Use `git add -A` | NOT DONE ✓ (explicit file list) |
| Mix product code changes with index work | NOT DONE ✓ |
| Touch master / origin/master | NOT DONE ✓ |
| Push / create PR | NOT DONE ✓ |

## §7. Provisional verdict

```
PASS_A1A_GATE4R_I_2_DIRECTORY_INDEX_LAYER_FILED
```

Tier: FILED (not VERIFIED). This sub-gate filed the index layer as
required. It did not verify the underlying artefacts' correctness
(that is the job of sub-gates 4R-I.5 through 4R-I.10).

## §8. Next

Gate 4R-I.3 — post-merge regression validation:

1. Verify `git diff --name-status 24967da..HEAD` shows only docs/index/metadata
2. Run 14-category test sweep per charter §6
3. Compute delta table vs 24967da evidence
4. Promote the unique scattered evidence (`audit_gate4_full.xml`) to canonical evidence-freeze
