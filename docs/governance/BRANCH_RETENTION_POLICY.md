# Branch Retention Policy

**Last updated**: 2026-07-21

## Permanent branches (NEVER delete)

| Branch | Head | Purpose |
|---|---|---|
| `master` | `c147d01` | Local product baseline (Phase 5/6/7 + Phase A0.1R audit) |
| `audit/phase-a0.1r-freeze` | `64590fa` | A0.1R immutable freeze; anchored by `audit/phase-a0.1r-baseline` tag |
| `phase-a1a/emergency-containment` | `ca36c51` | Active A1A work branch; carries Gate 0..4.9 + 4R-I.0/I.1 |
| `phase-a1a/gate4r-regression-reconciliation` | `24967da` | 4R carrier; superseded post-merge but preserved for audit trail |

## Branch operations forbidden on permanent branches

```bash
# FORBIDDEN on any permanent branch:
git push --force
git push --delete
git branch -D
git rebase
git commit --amend
git reset --hard <earlier-commit>
git checkout <earlier-commit> -- <file>   # to bring back pre-audit state
```

## Branch operations allowed

```bash
git merge --no-ff <branch>     # only into phase-a1a/* (never into master or audit/*)
git checkout <branch>
git log <branch>
git diff <branch>..<branch>
git worktree add <path> <branch>
git worktree remove <path>
```

## Worktree lifecycle

Worktrees may be added and removed freely; commits are preserved in the
shared `.git/objects`. Worktree removal is reversible:

```bash
git worktree add E:/Corti4C-<name> <branch-or-commit>
# ... work ...
git worktree remove E:/Corti4C-<name>
# later, if needed again:
git worktree add E:/Corti4C-<name> <branch-or-commit>
```

## Merging INTO master

Merging any branch into `master` is OUT OF SCOPE for all current Charters.
A future release Charter must explicitly authorize this. Current state:
`master` is 85 commits behind `phase-a1a/emergency-containment`.

## Merging INTO origin/master

`git push` is OUT OF SCOPE for all current Charters. `origin/master` is
unmodified by this project.

## Branch creation policy

New branches require:

1. An active Charter that names the branch in advance.
2. Branch point must be a Charter-named commit (typically a tag anchor).
3. Branch name format: `phase-<phase>/<scope>` or `audit/phase-<phase>-<scope>`.
4. Local-only; never push.

## Branch deletion policy

Branches may be deleted ONLY after:

1. All commits on the branch are ancestors of another permanent branch
   (verified by `git merge-base --is-ancestor`).
2. A Charter explicitly authorizes the deletion.
3. The branch's purpose has been documented in a closure notice.

No branches currently meet condition (1) alone for deletion: every
permanent branch has unique commits not carried elsewhere.
