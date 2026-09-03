# A1D.0 — A1C Predecessor Consistency Report

**Subgate**: A1D.0
**Date**: 2026-08-05
**Subject**: Verify A1C.9 terminal artifacts are consistent, immutable, and correctly inherited by A1D.
**Method**: Read-only inspection of A1C.9 deliverables + cross-reference with A1D charter v1.0.

---

## 1. A1C.9 three-file consistency

| Field | `A1C_FINAL_VERDICT.md` | `A1C_FINAL_STATE.json` | `A1C_FINAL_COMMIT_MANIFEST.json` | Consistent? |
|---|---|---|---|---|
| `phase` | A1C | A1C | A1C | ✓ |
| `final_verdict` | `PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN` | `PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN` | (n/a) | ✓ |
| `predecessor_terminal_commit` | `0f107d0` | `0f107d0` | (n/a) | ✓ |
| `head_branch` | `phase-a1a/emergency-containment` | `phase-a1a/emergency-containment` | `phase-a1a/emergency-containment` | ✓ |
| `head_commit` | (in §5 commit stack `209f25a`) | `(populated at commit time — see MANIFEST)` | (not present in keys) | ⚠ IC-A1D-2 |

**Verdict**: A1C.9 three files are substantively consistent. The `head_commit` field is a placeholder in STATE.json (noted in A1C §八 IC-1 as a known pattern: file written inside the commit can only know parent SHA, not the commit's own SHA).

---

## 2. A1C.9 vs A1D charter v1.0 — blocker count cross-reference

### A1C.9 OPEN_BLOCKERS.csv distribution

```
target_phase           count
---------------------------------
Pilot env              11
A1D or Pilot prep       1   (A1C-B-002 — 88 baseline failures)
A1D                     8   (B-003/007/008/010/011/012/018/020)
                       ---
Total                  20
```

**Engineering-class in A1D scope**: 8 + 1 = **9 blockers**.

### A1D charter v1.0 §二 claim

> "9 个 Engineering 类 (A1D 范围): A1C-B-002/003/007/008/010/011/012/**015**/018/020"

**Counting**: prefix says "9" but the ID list contains **10 IDs** (B-015 included erroneously).

### IC-A1D-1 — Charter v1.0 §二 / §四 internal number error

| ID | Field | Written | Truth | Reason |
|---|---|---|---|---|
| IC-A1D-1a | charter v1.0 §二 list | `A1C-B-002/003/007/008/010/011/012/015/018/020` (10 IDs) | `A1C-B-002/003/007/008/010/011/012/018/020` (9 IDs) | A1C-B-015 target_phase = `Pilot env`, NOT `A1D` per `A1C_OPEN_BLOCKERS.csv` |
| IC-A1D-1b | charter v1.0 §四 A1D.2 scope | `A1C-B-012, A1C-B-015, A1C-B-018` (3 blockers) | `A1C-B-012, A1C-B-018` (2 blockers) | Same root cause — A1C-B-015 was incorrectly placed in A1D.2 |
| IC-A1D-1c | charter v1.0 §一 / §八 number claim | "9 个" | 9 (correct) | Coincidentally correct count, but conflicts with §二 list |

**Severity**: P2 — internal inconsistency only. Does NOT affect 5-tuple immutability, forbidden verdicts, or any external commitment. A1D scope size is 9 in both v1.0 (intent) and v1.1 (corrected list).

**Resolution**: Charter v1.0 → v1.1 amendment in this subgate (A1D.0). Per Charter §十二, charter amendment requires new commit with version bump. v1.1 edits in-place:
- §二 list: remove `A1C-B-015`
- §四 A1D.2 scope: `A1C-B-012, A1C-B-018`
- §四 A1D.2 title unchanged ("小基础设施: audit pause + egress decision log + webhook queue") — actually retitle to drop "+ webhook queue" since A1C-B-015 not in scope

**Carry-forward**: A1C-B-015 (webhook queue: Postgres LISTEN/NOTIFY vs Redis Stream decision + wire) remains in `A1C_OPEN_BLOCKERS.csv` with target_phase=Pilot env. Not closed by A1D. Will be re-evaluated at Layer 2 phase boundary.

---

## 3. A1C.9 OPEN_BLOCKERS.csv — internal consistency

| Check | Result |
|---|---|
| Total rows (excl. header) | 20 |
| Unique blocker IDs | 20 (B-001..B-020) ✓ no gaps, no duplicates |
| Severity distribution | 7 P1 + 13 P2 = 20 ✓ |
| Verdict at A1C.9 §2 (12 open blockers claim) | ⚠ numeric mismatch — see IC-A1D-3 below |

### IC-A1D-3 — A1C.9 §7 "12 open blockers" vs actual 20 rows

A1C_FINAL_VERDICT.md §7 writes:
> "⚠️ 12 open blockers require Pilot env provisioning or live infrastructure"

A1C_OPEN_BLOCKERS.csv has **20 rows** (not 12).

**Reconciliation**: A1C.9 §2 lists 12 blockers in the table ("12 carry open blockers") but the CSV has 20 because:
- The "12" in §2 refers to "blockers requiring Pilot env provisioning or live infrastructure" = 11 Pilot-env + 1 ambiguous (A1C-B-002 A1D-or-Pilot-prep) = 12
- The "8" A1D-target blockers are technically "open" in CSV but resolution path is engineering, not Pilot env

So:
- A1C_FINAL_VERDICT §7 "12 open blockers" = Pilot-env-class count (12)
- A1C_OPEN_BLOCKERS.csv 20 rows = all open blockers (12 Pilot-env + 8 A1D)
- A1C_FINAL_VERDICT §2 "(Precise tally: 6 PASS + 1 PRIOR_PASS + 8 PARTIAL + 6 BLOCKED = 21)" refers to **hard-gate verdict distribution**, not blocker count

**Severity**: P3 — terminology overlap ("open blockers" vs "Pilot-env blockers"). Not an inconsistency in truth, just in shorthand.

**Resolution**: No charter amendment needed. A1D.0 documents the distinction explicitly:
- A1C "12 open blockers" (Pilot-env-class, awaiting Pilot env)
- A1C "20 total open blockers" (all rows in CSV)
- A1D scope = 9 Engineering-class (subset of the 20)

---

## 4. A1C final artifacts SHA-256 (immutability guardians)

| File | SHA-256 | A1D.0 verification |
|---|---|---|
| `reports/phase-a1c/A1C.9/A1C_FINAL_VERDICT.md` | `2a6d0d494bf7b95ed43b46d0da4d29062426b73d4213f7eeffe7de61aa966ba7` | ✓ unmodified during A1D.0 |
| `reports/phase-a1c/A1C.9/A1C_FINAL_STATE.json` | `f2f62d1593fe252f8e9b40ab58c31b209d6b77372412329bf97714555587b3a2` | ✓ unmodified |
| `reports/phase-a1c/A1C.9/A1C_FINAL_COMMIT_MANIFEST.json` | `3ff384e6b4e79c22ec3797e3a2656afbb9213a1c5fc51bce0d8b36959320ecaf` | ✓ unmodified |
| `reports/phase-a1c/A1C.9/A1C_OPEN_BLOCKERS.csv` | `1818629cccee6451984bdb71cc71f5b9fc767c8a94955d4d5368534c04e8fd8a` | ✓ unmodified |
| `docs/phase-a1c/A1C_CHARTER.md` | `775d3203cd215bf6b912701f9fd0bcd001636c7a5be77aea8111396531250a21` | ✓ unmodified |

**A1D.0 commits did NOT modify any A1C final artifact** — Charter §6.1 honoured.

Future A1D subgates (A1D.1..A1D.6) MUST preserve these SHA-256 values. Any drift indicates A1C final artifact tampering — fail-closed.

---

## 5. A1B-AE-RV predecessor (carried forward via A1C.9)

| Field | Value | Source |
|---|---|---|
| Terminal commit | `0f107d0` | A1C final state |
| Terminal verdict | `PASS_A1B_AE_RV_TERMINAL_EVIDENCE_REPAIR_FULL_REGRESSION_MIGRATION_CONTEXT_SCRUB_PUBLIC_EXPERT_LIVE_AND_HEADED_WORKFLOWS_VERIFIED` | A1C final state |
| Annotated tag | `audit/phase-a1b-ae-rv-baseline-8546184` → `0f107d0` | `git tag -l` confirmed |

**Status**: A1B-AE-RV predecessor chain intact. No carry-forward inconsistency from A1C §八 IC-1..IC-5 (those were resolved by A1C.0 closeout commit per A1C §八).

---

## 6. Findings summary

| ID | Severity | Title | Resolution |
|---|---|---|---|
| IC-A1D-1 | P2 | Charter v1.0 §二/§四 internal number error (A1C-B-015 mis-listed) | Charter v1.0 → v1.1 amendment (this subgate) |
| IC-A1D-2 | observation | A1C.9 STATE.json `head_commit` placeholder | No action (A1C IC-1 pattern, expected; not a truth defect) |
| IC-A1D-3 | P3 observation | A1C.9 "12 open blockers" vs 20 CSV rows terminology overlap | Documented in §3 above; no charter change |

**No P0 / P1 findings.** A1C.9 predecessor truth intact. A1D.0 may close.

---

## 7. Sign-off

A1D.0 predecessor consistency check complete. 1 P2 finding resolved via charter v1.1 amendment. 2 observations documented. No blockers for A1D.1 kickoff.

```
A1C_PREDECESSOR_CONSISTENCY: VERIFIED
A1C_FINAL_ARTIFACTS_IMMUTABLE: VERIFIED
A1D.0_PROCEED: APPROVED
```
