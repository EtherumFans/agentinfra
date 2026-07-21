# Baseline and Tag Registry

**Last updated**: 2026-07-21

All annotated tags in this project are local-only. None are pushed.
Tags are immutable; `git tag -d` on any audit tag is FORBIDDEN.

## Annotated tags

| Tag | Tag object SHA | Commit pointed | Tagger date | Purpose |
|---|---|---|---|---|
| `audit/phase-a0.1r-baseline` | `3cd1bec...` | `64590fa` | 2026-07-17 | A0.1R Secure Freeze Reconciliation baseline; immutable anchor for all downstream A1A work |
| `audit/phase-a1a-gate4-pre4r-b3ea064` | `fa0d461...` | `b3ea064` | 2026-07-21 | Phase A1A Gate 4.9 closure snapshot, pre-4R; immutable reference for what Gate 4R superseded |
| `audit/phase-a1a-gate4r-closure-24967da` | `43c2395...` | `24967da` | 2026-07-21 | Phase A1A Gate 4R P0-5 closure snapshot; immutable reference for the 5-commit 4R chain |

## Lightweight tags

| Tag | Commit | Notes |
|---|---|---|
| `v1.0.0` | `c779bdf...` | Pre-existing product tag from earlier phase; not audit-related |

## Verification commands

```bash
git tag --list "audit/*" -n1
git show-ref --tags
git cat-file -p audit/phase-a1a-gate4-pre4r-b3ea064
git cat-file -p audit/phase-a1a-gate4r-closure-24967da
git cat-file -p audit/phase-a0.1r-baseline
```

## Tag addition policy

New audit tags require:

1. An active Charter that names the tag in advance.
2. Annotated (not lightweight) via `git tag -a`.
3. Tag message must cite the Charter and the immutability guarantee.
4. Commit must already exist (no tag of unborn commits).
5. Tag is local-only; never push.

## Tag verification policy

Any audit work that references a tag MUST verify the tag's commit SHA
matches the recorded baseline before relying on it. Use:

```bash
git rev-parse refs/tags/<tag>^{commit}
```

and compare against this registry.
