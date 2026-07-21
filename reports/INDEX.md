# Reports Index

**Last updated**: 2026-07-21

This is a navigation index. Individual reports carry their own content.

## Active phases

| Path | Purpose | Status |
|---|---|---|
| `reports/phase-a1a/` | Phase A1A emergency security/tenant/PHI/truth containment | ACTIVE (Gate 4R-I in progress) |
| `reports/phase7/` | Phase 7 Corti embedded assistant parity | CLOSED (Phase 7 FINAL on 2026-07-14) |
| `reports/phase6/` | Phase 6 consolidation of embedded SDK | CLOSED (Phase 6 FINAL on 2026-07-13) |

## Phase A1A subdirectories

| Path | Purpose |
|---|---|
| `reports/phase-a1a/integration/` | Gate 4R-I integration + product audit + Corti gap (current) |
| `reports/phase-a1a/adversarial-audit/` | Gate 4R regression reconciliation (CLOSED via 24967da) |
| `reports/phase-a1a/A1A_GATE0_*.md` through `A1A_GATE4_*.md` | Gate-specific closure artefacts (Gates 0–4.9) |

## Historical phases (untracked, predates Phase A1A)

| Path | Purpose | Status |
|---|---|---|
| `reports/comprehensive-audit/` | PRE-A0 / A0 / A0.1 audit package | UNTRACKED; superseded by `audit/phase-a0.1r-freeze` branch |

These historical reports are currently untracked in `phase-a1a/emergency-containment`.
They predate the A0.1R freeze branch and have not been promoted into the
audit-trail commits. They are preserved as-is for reference. Promotion
into the audit branch is out of scope for Phase A1A Gate 4R-I.

## Audit evidence directories

| Path | Purpose |
|---|---|
| `reports/phase-a1a/integration/evidence/` | 4R-I evidence freeze (current) |
| `reports/phase-a1a/adversarial-audit/evidence-freeze/` | 4R evidence freeze (frozen post-24967da) |
| `reports/phase-a1a/screenshots/` | Browser E2E screenshots (Phase A1A Gate 3R + earlier) |

## Backlog directories

| Path | Purpose |
|---|---|
| `reports/product-audit/evidence/` | Product audit evidence (Gate 4R-I.6) — pending |
| `reports/product-audit/parity/` | Corti parity matrix artefacts (Gate 4R-I.7) — pending |
| `reports/product-audit/release-readiness/` | MVP/Pilot/GA tier verdicts (Gate 4R-I.9) — pending |
| `reports/product-audit/roadmap/` | Development backlog (Gate 4R-I.10) — pending |

## Corti parity analysis

| Path | Purpose |
|---|---|
| `docs/corti-parity/official-snapshot/` | Clean-room snapshot of Corti public docs (Gate 4R-I.5) — pending |
| `docs/corti-parity/api-contract/` | Corti API contract analysis (Gate 4R-I.7) — pending |
| `docs/corti-parity/capability-matrix/` | iCoder-vs-Corti capability matrix (Gate 4R-I.7) — pending |
| `docs/corti-parity/clean-room/` | Clean-room implementation notes (Gate 4R-I.7) — pending |

## Governance

| Path | Purpose |
|---|---|
| `docs/governance/PROJECT_BRANCH_TOPOLOGY.md` | Branch + worktree map |
| `docs/governance/CHARTER_INDEX.md` | Charter registry |
| `docs/governance/BASELINE_AND_TAG_REGISTRY.md` | Annotated tag registry |
| `docs/governance/BRANCH_RETENTION_POLICY.md` | Branch retention rules |
| `docs/governance/WORKTREE_OPERATING_GUIDE.md` | Worktree usage guide |

## Browsing tips

```bash
# List all phase-a1a reports (tracked + untracked)
find reports/phase-a1a -type f -name '*.md' | sort

# List audit-commit-touched files since Phase A1A began
git diff --name-only 64590fa..HEAD -- reports/

# Find evidence files in the integration freeze
ls reports/phase-a1a/integration/evidence/
```
