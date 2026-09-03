# Worktree Operating Guide

**Last updated**: 2026-07-21

## Why worktrees

Git worktrees allow multiple parallel checkouts from a single `.git`
directory. They are used in this project for:

1. **Concurrent branch work** — e.g., 4R on `phase-a1a/gate4r-regression-reconciliation`
   while main work continued on `phase-a1a/emergency-containment`.
2. **Detached-HEAD evidence collection** — e.g., checking out `b737eab` and
   `880f49c` simultaneously to run pytest at both commits for JUnit XML
   comparison. No branch churn; no checkout thrash.
3. **Isolated audit environments** — e.g., a clean worktree for evidence
   freeze without disturbing the main working directory.

All worktrees share the same `.git/objects`. Commits made in any worktree
are immediately visible to all others.

## Current worktrees

```bash
$ git worktree list
E:/Corti4C                     ca36c51 [phase-a1a/emergency-containment]
E:/Corti4C-gate4r-remediation  24967da [phase-a1a/gate4r-regression-reconciliation]
```

## Past worktrees (removed; commits preserved)

| Path | Was at | Removed on | Reason |
|---|---|---|---|
| `E:/Corti4C-audit-baseline` | `b737eab` (detached) | 2026-07-21 | Gate 4R-I directory cleanup; evidence frozen in `audit_baseline_full.xml` |
| `E:/Corti4C-audit-gate4` | `880f49c` (detached) | 2026-07-21 | Gate 4R-I directory cleanup; evidence frozen in `audit_gate4_full.xml` |

## Creating a worktree

```bash
# Branch-bound worktree (commits land on the branch)
git worktree add E:/Corti4C-<name> <branch>

# Detached-HEAD worktree (for evidence collection; commits are orphaned by default)
git worktree add E:/Corti4C-<name> <commit-sha> --detach
```

## Removing a worktree

```bash
# Pre-check for uncommitted changes
cd E:/Corti4C-<name> && git status --short

# If clean:
git worktree remove E:/Corti4C-<name>

# If dirty and changes are known test artifacts (e.g., source-tree writes):
git worktree remove E:/Corti4C-<name> --force
```

## Common pitfalls

### Pitfall 1: dirty worktree blocks removal

Symptom:
```
error: cannot remove worktree: path is dirty
```

Cause: uncommitted modifications to tracked files.

Fix: either commit/discard the changes, or use `--force` if the changes
are known test artifacts (document the reason).

### Pitfall 2: relative paths break when cwd changes

The `backend/tests/conftest.py` uses `./data/test.db` which is relative
to the current working directory. Running pytest from a worktree root
fails with "unable to open database file".

Fix: always run pytest from inside `backend/`:
```bash
cd E:/Corti4C-<name>/backend
python -m pytest tests
```

### Pitfall 3: test writes to source tree

Some tests write to `backend/tests/fixtures/icoder_201.json` instead of
using `tmp_path`. This produces a dirty worktree after pytest runs.

Fix (when it happens): `git checkout backend/tests/fixtures/icoder_201.json`

Fix (permanent): convert the offending test to use `tmp_path`. This is
tracked as Gate 4R-I.4 engineering debt.

### Pitfall 4: pytest invocation with very long node lists

Passing 77 node IDs via bash command line may exceed Windows path length.

Fix: use Python subprocess with the node list as positional args:
```python
import subprocess
nodes = open('pass_to_fail.txt').read().splitlines()
subprocess.run(['python', '-m', 'pytest'] + nodes + [...])
```

## Worktree retention

Worktrees may be removed after their evidence is frozen. The underlying
commits remain in `.git/objects` indefinitely.

Evidence freeze files (JUnit XML, logs, SHA-256 manifests) must be
committed to a permanent branch before the worktree is removed. See
`reports/phase-a1a/integration/evidence/` for examples.
