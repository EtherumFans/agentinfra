# Project Branch Topology

**Last updated**: 2026-07-21 (Phase A1A Gate 4R-I.2)
**Authoritative source**: `git show-ref` + `git tag --list` on local clone

This document is a human-readable index. The Git refs themselves are the
authoritative record. If this document disagrees with `git show-ref`,
the Git output wins.

---

## Current topology (as of 2026-07-21 post Gate 4R-I.1 merge)

```
origin/master (fe198825) ← external canonical; never rewritten by this project
  │
  └─ master (c147d01, local, 85 ahead of origin)
       │
       └─ audit/phase-a0.1r-freeze (64590fa)
            │ tag: audit/phase-a0.1r-baseline (obj 3cd1bec)
            │
            └─ phase-a1a/emergency-containment (ca36c51)
                 │ tag: audit/phase-a1a-gate4-pre4r-b3ea064 (obj fa0d461) on b3ea064
                 │ tag: audit/phase-a1a-gate4r-closure-24967da (obj 43c2395) on 24967da
                 │
                 └─ (no children branches; future Phase A1A work continues here)

phase-a1a/gate4r-regression-reconciliation (24967da)
  superseded; preserved indefinitely; ancestor of phase-a1a/emergency-containment via ca36c51 merge
```

## Worktrees

| Path | HEAD | Branch | Purpose |
|---|---|---|---|
| `E:/Corti4C` | `ca36c51` | `phase-a1a/emergency-containment` | Main A1A work area |
| `E:/Corti4C-gate4r-remediation` | `24967da` | `phase-a1a/gate4r-regression-reconciliation` | 4R carrier (post-merge; held for audit trail) |

The `E:/Corti4C-audit-baseline` and `E:/Corti4C-audit-gate4` worktrees were
removed on 2026-07-21 (Phase A1A Gate 4R-I directory cleanup) after their
detached-HEAD pytest runs were captured as frozen JUnit XML evidence.

## Immutable anchors (NEVER rewrite, NEVER delete)

| Object | Tag | Branch/Commit | Set by |
|---|---|---|---|
| `64590fa` | `audit/phase-a0.1r-baseline` (obj `3cd1bec`) | `audit/phase-a0.1r-freeze` | Phase A0.1R Gate 9 |
| `b3ea064` | `audit/phase-a1a-gate4-pre4r-b3ea064` (obj `fa0d461`) | ancestor of `phase-a1a/emergency-containment` | Phase A1A Gate 4R-I.0 |
| `24967da` | `audit/phase-a1a-gate4r-closure-24967da` (obj `43c2395`) | `phase-a1a/gate4r-regression-reconciliation` | Phase A1A Gate 4R-I.0 |
| `777d96d` | — | ancestor of `phase-a1a/emergency-containment` | Phase A1A Gate 4R-I.0 (Charter) |
| `ca36c51` | — | `phase-a1a/emergency-containment` HEAD | Phase A1A Gate 4R-I.1 (merge) |

## Commit chain on phase-a1a/emergency-containment (ca36c51 → earliest)

```
ca36c51  Gate 4R-I.1 merge — integrate phase-a1a/gate4r-regression-reconciliation via --no-ff
777d96d  Gate 4R-I.0 — integration charter + pre-merge evidence freeze + annotated tags
b3ea064  Gate 4.9 closure report (final verdict artefact for 880f49c)  ← tag pre4r-b3ea064
880f49c  Gate 4 — PHI boundary + live-path redaction + at-rest encryption + ...
b737eab  Gate 3R — Trace, audit, tenant-read reconciliation
d1447f3  Gate 3 — Tenancy truth, trace isolation, audit separation
de2feaa  Gate 2 — Tenancy and Data Isolation
06624b4  Gate 1 deliverables
f6bbd60  Gate 0 + Gate 0 Addendum + Gate 1 steps 1/4/5/6
64590fa  audit/phase-a0.1r: freeze receipt (Bucket C) — A0.1R Gate 9  ← tag baseline
606dc5d  audit/phase-a0.1r: audit package (Bucket B) — A0.1R Gate 9
87754ab  audit/phase-a0.1r: audited product snapshot (Bucket A) — A0.1R Gate 8
c147d01  feat(track-h): Tier 2 Corti controlled probes (master tip)
```

## 4R superseded branch (preserved for audit trail)

`phase-a1a/gate4r-regression-reconciliation` (24967da) carries:

```
24967da  Gate 4R P0-5 closure — 12/12 closure conditions MET
efbe96b  Gate 4R.3 — per-regression liquidation ledger (89 residual; 1 P2, 88 P3)
fa676b3  Gate 4R.2 — Rate Limiter hermeticity + asyncio_default_fixture_loop_scope
e418020  Gate 4R.1 — precise node-ID diff + transition ledger
a2613b7  Gate 4R.0 — evidence freeze + 7-point correction notice
```

All 5 commits are ancestors of `phase-a1a/emergency-containment` HEAD via
the `ca36c51` no-ff merge. The branch is kept for traceability but is no
longer the active development tip.

## Forbidden actions (apply to all branches and tags above)

- `git push` to any remote
- `git rebase` or `git commit --amend` on any audit commit
- `git tag -d` on any audit/* tag
- `git branch -D` on any audit/* or phase-a1a/* branch
- `git reset --hard` to a commit earlier than the current branch HEAD
- `git checkout b3ea064 -- ...` to bring back pre-4R file states as current

## Retention policy

| Object class | Retention |
|---|---|
| Annotated tags (`audit/phase-*`) | Permanent (project lifetime) |
| Audit branches (`audit/phase-*`, `phase-a1a/*`) | Permanent |
| Audit commits referenced by tags or branches above | Permanent |
| Worktree directories | May be removed after evidence freeze; commits preserved |
| Background pytest JUnit XML + logs | Permanent under `reports/phase-a*/adversarial-audit/evidence-freeze/` or `reports/phase-a*/integration/evidence/` |

See [BRANCH_RETENTION_POLICY.md](./BRANCH_RETENTION_POLICY.md) for full policy.
