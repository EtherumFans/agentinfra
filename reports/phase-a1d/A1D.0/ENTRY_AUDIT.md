# A1D.0 — Entry Audit

**Subgate**: A1D.0
**Date**: 2026-08-05
**Auditor**: Codex (Claude Code) + SONG Luhua
**Charter**: `docs/phase-a1d/A1D_CHARTER.md` v1.0 → v1.1 (this subgate, see §八 finding IC-A1D-1)

---

## 1. Repository state at A1D.0 entry

| Field | Value |
|---|---|
| Working directory | `E:/Corti4C` (primary worktree) |
| Branch | `phase-a1a/emergency-containment` (local-only, never pushed) |
| HEAD at A1D.0 start | `0a7bb11` (RELEASE_ROADMAP v1.0) |
| HEAD at A1D.0 end | (populated at commit time — see A1D_FINAL_COMMIT_MANIFEST.json) |
| A1C.9 terminal commit | `209f25a` (2026-07-25, PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN) |
| Predecessor of A1C.9 | A1B-AE-RV terminal `0f107d0` |
| Predecessor of A1B-AE-RV | A1B-AE-R terminal `8546184` |
| Predecessor of A1B-AE-R | A1B-AE terminal `85a5c9a` |
| Remote tracking | none (no upstream, never pushed — Charter §6.1 honoured) |
| Working tree | dirty — large number of untracked screenshots / audit reports from prior phases (NOT in A1D scope, NOT added by A1D commits) |

---

## 2. Runtime versions

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12.3 | `Python 3.12.3` |
| Node | 22.20.0 | `v22.20.0` |
| npm | 10.9.3 | `10.9.3` |
| git | 2.50.1.windows.1 | Windows build |
| OS | Windows 10 Home China 10.0.19045 (MINGW64_NT-10.0-19045 3.6.3) | MSYS2 environment |
| Shell | bash (Unix syntax) | per CLAUDE.md |

---

## 3. Worktree inventory at A1D.0 entry

| Path | Branch | Status |
|---|---|---|
| `E:/Corti4C` | `phase-a1a/emergency-containment` | primary, active |
| (all prior A1*/research worktrees) | — | REMOVED 2026-08-05 (see worktree cleanup commit; 10 branches preserved) |

10 phase/research branches preserved per Charter §6 (no branch deletion). 8 worktree directories removed (their work was already committed to branches).

---

## 4. A1C.9 inheritance check

| A1C.9 deliverable | Exists | SHA-256 (entry fingerprint) |
|---|---|---|
| `reports/phase-a1c/A1C.9/A1C_FINAL_VERDICT.md` | ✓ | `2a6d0d49...66ba7` |
| `reports/phase-a1c/A1C.9/A1C_FINAL_STATE.json` | ✓ | `f2f62d15...87b3a2` |
| `reports/phase-a1c/A1C.9/A1C_FINAL_COMMIT_MANIFEST.json` | ✓ | `3ff384e6...20ecaf` |
| `reports/phase-a1c/A1C.9/A1C_OPEN_BLOCKERS.csv` | ✓ | `1818629c...e8fd8a` |
| `reports/phase-a1c/A1C.9/A1C_PILOT_READINESS_MATRIX.csv` | ✓ | (computed in manifest) |
| `docs/phase-a1c/A1C_CHARTER.md` | ✓ | `775d3203...250a21` |

A1C.9 21 hard gates verdict distribution: **6 PASS + 1 PRIOR_PASS + 8 PARTIAL + 6 BLOCKED_BY_ENV = 21** (matches A1C_FINAL_VERDICT §2).

A1C.9 open blockers count: **20 rows** in CSV (Pilot env=11, A1D=8, A1D or Pilot prep=1). **9 Engineering-class** blockers in A1D scope (B-002/003/007/008/010/011/012/018/020).

---

## 5. Annotated tag inventory

| Tag | Target commit | Notes |
|---|---|---|
| `audit/phase-a0.1r-baseline` | (carried forward) | Phase A0.1R freeze receipt |
| `audit/phase-a0.1r-freeze` | (carried forward) | Phase A0.1R branch tip |
| `audit/phase-a1a-gate4-pre4r-b3ea064` | (carried forward) | A1A Gate 4 baseline |
| `audit/phase-a1a-gate4r-closure-24967da` | (carried forward) | A1A Gate 4R closure |
| `audit/phase-a1b-ae-rv-baseline-8546184` | `0f107d0` | A1B-AE-RV terminal baseline |
| `audit/phase-a1b-agent-expert-clean-room-final-85a5c9a` | `85a5c9a` | A1B-AE terminal baseline |

**Observation (not finding)**: No `audit/phase-a1c-*` annotated tag exists. A1C charter did not require a phase-terminal tag (unlike A0.1R / A1A Gate 4 / Gate 4R / A1B-AE / A1B-AE-RV). Not an inconsistency — charter-dependent.

**Recommendation for A1D**: Consider creating `audit/phase-a1d-baseline-<charter-commit>` annotated tag at A1D.0 close. Out of scope for A1D.0 (no charter requirement); defer to A1D.6 final.

---

## 6. 5-tuple inheritance verification

| Field | A1C.9 value | A1D.0 read-back | Match? |
|---|---|---|---|
| `GATE4_8_NO_NEW_REGRESSION_CLAIM` | `CONTRADICTED` | `CONTRADICTED` | ✓ |
| `GATE4_9_FINAL_PASS` | `SUPERSEDED` | `SUPERSEDED` | ✓ |
| `GATE4_ACCEPTANCE_STATUS` | `REOPENED` | `REOPENED` | ✓ |
| `CORTI_PARITY_VERDICT` | `NOT_DEMONSTRATED` (52.6%) | `NOT_DEMONSTRATED` (52.6%) | ✓ |
| `PRODUCTION_READINESS` | `NOT_VERIFIED` | `NOT_VERIFIED` | ✓ |

5-tuple immutable per Charter §二. A1D.0 confirms no mutation.

---

## 7. Charter §三 forbidden verdicts honoured

11 forbidden verdicts (8 from Charter §22 + 3 A1D-specific) — none emitted during A1D.0:

| # | Forbidden verdict | Honoured in A1D.0? |
|---|---|---|
| 1-8 | (Charter §22, inherited) | ✓ NOT emitted |
| 9 | `A1C_REASSESSED_PASS` | ✓ NOT emitted |
| 10 | `PILOT_ENV_READY` | ✓ NOT emitted |
| 11 | `LAYER1_COMPLETE` | ✓ NOT emitted |

---

## 8. Charter §6.1 forbidden git ops honoured

12 forbidden git operations — none performed during A1D.0:

| # | Forbidden op | Honoured? |
|---|---|---|
| 1 | `git push` to remote | ✓ |
| 2 | `gh pr create` | ✓ |
| 3 | Deploy to real hospital | ✓ |
| 4 | amend A1C history | ✓ |
| 5 | rebase A1C history | ✓ |
| 6 | squash A1C history | ✓ |
| 7 | Delete any annotated tag | ✓ |
| 8 | Real secrets to repo | ✓ |
| 9 | `git add -A` / `git add .` | ✓ (explicit file lists only) |
| 10 | `git commit -a` | ✓ |
| 11 | Skip failing tests via `pytest.mark.skip` | ✓ (no test changes in A1D.0) |
| 12 | `--no-verify` bypass | ✓ |

---

## 9. A1D.0 deliverables status

| Deliverable | Status | Path |
|---|---|---|
| Charter v1.0 | ✓ filed | `docs/phase-a1d/A1D_CHARTER.md` (commit c81d49a) |
| Charter v1.1 amendment | ✓ filed | `docs/phase-a1d/A1D_CHARTER.md` (this subgate, fixes IC-A1D-1) |
| ENTRY_AUDIT | ✓ filed | `reports/phase-a1d/A1D.0/ENTRY_AUDIT.md` (this file) |
| BASELINE_STATE | ✓ filed | `reports/phase-a1d/A1D.0/A1D_BASELINE_STATE.json` |
| PREDECESSOR_CONSISTENCY_REPORT | ✓ filed | `reports/phase-a1d/A1D.0/A1C_PREDECESSOR_CONSISTENCY_REPORT.md` |
| Entry SHA manifest | ✓ filed | `reports/phase-a1d/A1D.0/A1D_ENTRY_SHA256SUMS.detached.txt` |
| A1D_OPEN_BLOCKERS.csv (initial) | ✓ filed | `reports/phase-a1d/A1D.0/A1D_OPEN_BLOCKERS.csv` |

---

## 10. A1D.0 verdict

```
PASS_A1D_0_CHARTER_V1_1_AND_ENTRY_AUDIT_FILED
```

**Justification**:
- ✓ Charter v1.0 frozen (commit c81d49a)
- ✓ Charter v1.1 amendment filed (this subgate, fixes §二/§四 internal number error per IC-A1D-1)
- ✓ ENTRY_AUDIT filed with full env / runtime / worktree / 5-tuple / forbidden-check
- ✓ BASELINE_STATE.json populated with 5-tuple immutable + 7 subgate placeholders
- ✓ A1C.9 predecessor consistency checked (3 findings: 1 IC + 2 observations)
- ✓ Entry SHA manifest generated as `.detached.txt` (per A1C IC-5 lesson, excludes self)
- ✓ A1D_OPEN_BLOCKERS.csv seeded with 9 Engineering-class blockers from A1C open blockers
- ✓ No source code changes (A1D.0 is pure audit subgate)
- ✓ 11 forbidden verdicts honoured
- ✓ 12 forbidden git ops honoured

**Preconditions for A1D.1**:
- Charter v1.1 in effect (this subgate)
- A1D.1 scope: A1C-B-003 (ESLint introduction) only
- A1D.1 must use TDD pattern per Charter §6.2
- A1D.1 must NOT modify A1C final artifacts
