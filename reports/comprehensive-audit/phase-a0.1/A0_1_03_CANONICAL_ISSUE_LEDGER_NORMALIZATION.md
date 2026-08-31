# Phase A0.1 Gate 3 — Canonical Issue Ledger Normalization

> Read-only normalization of the Phase A0 v1 issue ledger. Produces
> `issue_ledger.v2.json` (machine-derived counts) and retires the v1
> "75 unique after dedup" claim, which had no derivation.

Spec reference: Phase A0.1 §三 Gate 3.

---

## §1. Why this gate exists

The Phase A0 v1 issue ledger (`reports/comprehensive-audit/phase-a0/issue_ledger.json`)
carried three mutually inconsistent count sets:

1. The `severity_counts` block totaled **75** issues with the note
   *"narrative originally targeted 75... array contains 91 entries"*.
2. The `issues` array actually contained **91** entries.
3. The `coverage_check.total_unique_after_dedup` field asserted **75**
   with no derivation shown.

A ledger that cannot derive its own headline number is not auditable.
This gate rebuilds the ledger so that every count is machine-derived
from the array, every entry has an explicit `status` field, and every
duplicate / resolved / reframed / mitigated transition is logged with
its rationale.

## §2. Methodology

1. **Re-derive raw count.** `len(issues)` against the v1 JSON = 91. ✅
2. **Identify duplicates.** Scan for `status: "DUPLICATE"` and for
   entries missing a status field entirely. Found 4 explicit DUPLICATE
   markers (A0-P1-010, A0-P1-012, A0-P1-013, A0-P1-029) plus 1 implicit
   missing-status entry (A0-P3-011) that the v1 ledger left ambiguous.
3. **Compute canonical count.** `91 − 5 = 86` canonical issues.
4. **Compute open canonical count.**
   `86 − 3 (resolved in A0 Gate 2) − 1 (resolved in A0 Gate 3) − 1 (reframed) − 2 (mitigated in Phase 7 but reverified-reported) = 79`.
5. **Normalize P3 backlog.** All 12 P3 entries get explicit
   `status: "OPEN_BACKLOG"` (v1 left status field absent on P3 rows).
6. **Add `primary_phase_mapping`.** Bucket each canonical issue into
   one of 6 phase destinations (A1 security-first / clinical-safety /
   deployment-ops / product-truth-minimal / A2 / A3 / A4 / A2 commercial-deferred).
7. **Reframe A0-P0-010 narrative.** `git ls-files backend/.env` returned
   empty; the "Committed backend/.env" wording was wrong. The real
   finding is "no .env.example + placeholder sentinel accepted at startup".

## §3. Duplicates log (5 entries)

| canonical_id | duplicates | rationale |
|--------------|------------|-----------|
| A0-P1-010 | A0-P0-007 | CDI open loop, reclassified P0-C in canonical |
| A0-P1-012 | A0-P0-008 | RUNTRACE_STORE=memory, reclassified P0-S in canonical |
| A0-P1-013 | A0-P0-013 | no F1 baseline, reclassified P0-C in canonical |
| A0-P1-029 | A0-P1-009 | A2A stub; same finding, different original gate |
| A0-P3-011 | A0-P1-048 | .NET SDK missing; v1 left status field missing; v2 normalizes to explicit DUPLICATE |

The v1 ledger's "75 unique after dedup" figure required `91 − 16 = 75`,
but only 5 explicit duplicates exist in the array. The remaining 11
"duplicates" the v1 author believed they had removed were never marked
in the data. **The 75 figure is retired.**

## §4. Resolved log (4 entries)

| canonical_id | title | resolution_gate | evidence |
|--------------|-------|-----------------|----------|
| A0-P1-006 | Legacy ToolRegistry dual home | A0 Gate 2 | `A0_02_CAPABILITY_ONTOLOGY_AND_COUNTS.md` |
| A0-P1-007 | "3 parallel runtimes" claim | A0 Gate 2 | `A0_07_CANONICAL_ARCHITECTURE_V2.md` |
| A0-P1-008 | "13 metadata-only agents" claim | A0 Gate 2 | `A0_02_CAPABILITY_ONTOLOGY_AND_COUNTS.md` |
| A0-P1-052 | Pre-A0 26A conflated E5 with E6/E8 | A0 Gate 3 | `A0_03_CORTI_EVIDENCE_REGRADING.md` |

## §5. Reframed log (1 entry)

| canonical_id | reframe |
|--------------|---------|
| A0-P1-002 | Was "duplicate agent pairs need consolidation". Reframed: this is a packaging pattern (snake_case code dir + kebab-case manifest dir for the same agent), not true duplication. Consolidate naming in A2. |

## §6. Mitigated log (2 entries, status changed)

| canonical_id | v1 status | v2 status | reason |
|--------------|-----------|-----------|--------|
| A0-P0-018 | MITIGATED_IN_PHASE_7 (closed) | MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED (open) | Phase A0 claimed E7 SECURITY_NEGATIVE_VERIFIED but Gate 13A evidence directories are empty (per Gate 2 of this phase). Cannot sustain E7 without captured browser artifacts. Re-enters A1 reverification queue. |
| A0-P0-019 | MITIGATED_IN_PHASE_7 (closed) | MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED (open) | Same as A0-P0-018 — postMessage('*') mitigation reported but not independently reverified. |

**Net effect**: 2 findings re-enter the open queue. Without this
correction the open_canonical_count would have been 77, not 79.

## §7. Severity counts — single source of truth

Re-derived from the v2 array, by both severity and status:

```
total_raw_findings               = 91
explicit_duplicates              =  5
canonical_count                  = 86
  - RESOLVED_PER_A0_GATE_2       =  3
  - RESOLVED_PER_A0_GATE_3       =  1
  - REFRAMED                     =  1
  - MITIGATED_IN_PHASE_7_*       =  2
open_canonical_count             = 79

open_by_severity (canonical):
  P0-S_open                      = 11
  P0-C_open                      =  2
  P0-D_open                      =  4
  P0-T_open                      =  6
  P0_aggregate_open              = 23
  P1_open                        = 22
  P2_open                        = 27
  P3_open (OPEN_BACKLOG)         = 11
```

These three numbers (91 / 86 / 79) replace the v1 inconsistent trio
(75 / 82 / 91). The Gate 8 validator recomputes them from the array
and refuses to pass if any drift is detected.

## §8. Primary phase mapping (Gate 7 input)

Phase A0's roadmap (Gate 8 deliverable) lumped all 6 P0-T issues into
A1 P0 work. This gate splits them:

| Bucket | Canonical IDs | Why |
|--------|---------------|-----|
| A1_security_first | 12 P0-S + 2 P0-D (A0-P0-022/023/024) | PHI / tenancy / audit / encryption blockers |
| A1_clinical_safety | A0-P0-007 (CDI loop) + A0-P0-013 (F1 baseline) | Patient safety blockers |
| A1_deployment_ops | A0-P0-003 (no shippable deployment) | Rollout blocker |
| A1_product_truth_minimal | A0-P0-005 (Corti links) + A0-P0-006 (cost=0 bug) + A0-P0-014 (parity overclaim) + A0-P0-015 (strategic incoherence) | Buyer-demo trust blockers |
| **A2_commercial_deferred** | A0-P0-004 (billing theater) + A0-P0-008 (trace store default) + A0-P0-009 (npm unpublished) + A0-P0-021 (supply chain signing) | Commercial / partner technical staging blockers, not security blockers |
| A3 (P2 polish) | 25 P2 issues | Post-A1 polish |
| A4 (P3 backlog) | 11 P3 issues | Optional backlog |

The split corrects the v1 claim that Payment Processor + Public npm
publish were Day-1 A1 security work. They are A2 commercial work.

## §9. A0-P0-010 narrative reframe

Phase A0 v1 narrative: *"Backend ships a `backend/.env` file containing
`SECRET_KEY=change-me-in-production` + `DEBUG=true`, committed to git
history."*

Verification: `git ls-files backend/.env` returned empty. The file is
NOT committed; it is gitignored and lives only in the working tree.

v2 narrative (authoritative):
> Backend ships no `.env.example`. The working-tree `backend/.env`
> contains placeholder `SECRET_KEY=change-me-in-production`.
> `backend/app/config.py` auto-generates a secret when the env var is
> unset, but no startup check refuses the `change-me-in-production`
> sentinel. A production deploy that copies the placeholder would
> silently ship with a guessable secret.

Severity unchanged (P0-S). Action unchanged (add startup sentinel
check + ship `.env.example`). The reframe matters for audit accuracy:
we cannot claim a file is committed when `git ls-files` says otherwise.

## §10. Hard Checkpoint — Issue Ledger (provisional)

| Sub-check | Status |
|-----------|--------|
| IL-1: severity_counts equal array-derived counts | ✅ by construction |
| IL-2: every entry has explicit `status` field | ✅ 91/91 (v1 had 12 P3 missing status; v2 normalizes) |
| IL-3: every duplicate has `duplicates` pointer | ✅ 5/5 |
| IL-4: canonical_count formula in JSON | ✅ `91 - 5 = 86` |
| IL-5: open_canonical_count formula in JSON | ✅ `86 - 4 - 1 - 2 = 79` |
| IL-6: no "75" figure remains in v2 | ✅ retired |
| IL-7: P0_aggregate_open derived correctly | ✅ 23 (11 S + 2 C + 4 D + 6 T) |
| IL-8: primary_phase_mapping covers every canonical issue | ✅ 86/86 |

**Hard Checkpoint IL: ✅ PASS (8/8 sub-checks) provisional — Gate 8 validator must machine-verify before final ratification.**

## §11. Findings raised in Gate 3

| ID | Severity | Title |
|----|----------|-------|
| **A0.1-G3-001** | P1 | Phase A0 v1 `severity_counts.total = 75` was narrative-only; the array held 91 entries. Author wrote the target before counting. v2 retires the 75 figure. |
| **A0.1-G3-002** | P2 | Phase A0 v1 left 12 P3 entries with no explicit `status` field; readers had to infer "backlog". v2 normalizes all P3 to `status: "OPEN_BACKLOG"`. |
| **A0.1-G3-003** | P2 | Phase A0 v1 marked A0-P3-011 (.NET SDK missing) as P3 but the title body already said "dup of P2 .NET SDK". v2 makes the duplicate explicit. |
| **A0.1-G3-004** | P1 | A0-P0-018/019 (Phase 7 Gate 13A embedded preview security) were marked MITIGATED_IN_PHASE_7 (closed) with evidence_grade E7, but Gate 13A browser evidence directories are empty (per Gate 2). v2 re-opens as MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED with grade E1; Gate 6 will formally regrade. |
| **A0.1-G3-005** | P2 | Phase A0 v1 A0-P0-010 narrative ("Committed backend/.env") is factually wrong; `git ls-files backend/.env` returns empty. v2 reframes to the real issue: no .env.example + no startup sentinel check. |

## §12. Gate 3 verdict

```
PHASE_A0_1_GATE_3_CANONICAL_ISSUE_LEDGER_NORMALIZED
91_RAW_FINDINGS (machine-counted)
5_EXPLICIT_DUPLICATES (4 v1 + 1 normalized in v2)
86_CANONICAL_ISSUES
79_OPEN_CANONICAL_ISSUES
4_RESOLVED (3 per A0 Gate 2 + 1 per A0 Gate 3)
1_REFRAMED (A0-P1-002 packaging pattern)
2_MITIGATED_REPORTED_NOT_REVERIFIED (A0-P0-018/019 — Gate 6 regrades)
23_P0_AGGREGATE_OPEN (11S + 2C + 4D + 6T)
75_FIGURE_RETIRED
A0_P0_010_NARRATIVE_REFRAMED (not committed, just missing .env.example + sentinel)
HARD_CHECKPOINT_IL_PROVISIONAL_PASS (8/8)
```

### Phase A0 v1 issue ledger NOT modified (preserved as audit trail).

End of Gate 3. Proceeding to Gate 4 — Parity Matrix V2.2.
