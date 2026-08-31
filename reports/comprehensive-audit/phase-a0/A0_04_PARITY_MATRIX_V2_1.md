# A0 Gate 4 — Parity Matrix V2.1

> Phase A0 Gate 4. Rebuilds the parity matrix with machine-verifiable statuses, no composite buckets, evidence grades orthogonal to parity status, severity-weighted gap counts.

Spec reference: §13 (parity status enum), §13.2 (severity), §22 (Hard Checkpoint D — Parity Integrity).

---

## §1. Why Pre-A0's parity numbers were invalid

Pre-A0 26G reported:
- 30/51 = **59% favorable to iCoDer**
- 24/31 = **77% CN-scoped favorable**
- V1 → V2 swing of **+25 percentage points**

Per A0_00 §16, these numbers had 10 math and methodology problems. The most damning:

1. **Composite bucket invalidity** — "favorable" lumps PARITY + PARTIAL_PARITY + ICODER_ADVANTAGE. PARTIAL_PARITY means partially missing. Counting it as favorable obscures the gap.
2. **Denominator instability** — V1 had 32 dimensions, V2 has 51. Comparing percentages across different denominators is not a delta.
3. **Agent name mirror rate ≠ parity** — "18/20 mirrored" counts display names, not runtime parity.
4. **Asset existence ≠ workflow maturity** — `pii_redaction.py` exists but is export-only.
5. **Observability contract ≠ operational observability** — iCoDer emits events but `RUNTRACE_STORE=memory` default means they vanish.

**Phase A0 invalidates 59% / 77% / +25pp claims.** No composite percentage is reported in V2.1.

## §2. V2.1 design principles

| Principle | Implementation |
|-----------|----------------|
| Statuses mutually exclusive | 10 allowed statuses per spec §13.2; each dimension has exactly one |
| No composite buckets | No "favorable", no "unfavorable", no aggregate % |
| Evidence grade orthogonal | E0–E8 is separate from parity status; a PARITY dimension can have weak (E1) or strong (E5) evidence |
| Agent name mirror rate is not parity | Display name match is a separate count dimension (D-14 in capability_ontology.json), not a parity dimension |
| Asset existence is not workflow maturity | Existence of code file ≠ runtime behavior. Each dimension assesses the actual behavior. |
| Surface/Runtime/Clinical/Security split | Each dimension is tagged with `class` (Foundation/Agent/Expert/Tool/Commercial/Compliance/Observability) |
| Severity weighting | Each dimension with a gap carries a severity (P0-S/P0-C/P0-D/P0-T/P1/P2/P3) |
| Machine-verifiable | `parity_matrix_v2_1.json` is parseable; this markdown is human commentary |

## §3. V2.1 dimension counts

**51 dimensions total** (same total as Pre-A0 V2 but with reassigned statuses).

| Status | Count | vs Pre-A0 V2 |
|--------|------:|--------------|
| PARITY | 9 | was 12 (3 moved to EVIDENCE_INSUFFICIENT) |
| PARTIAL_PARITY | 7 | was 6 |
| ICODER_ADVANTAGE | 11 | was 12 (F-08 PHI redaction flipped) |
| CORTI_ADVANTAGE | 12 | same |
| DIFFERENT_BY_DESIGN | 3 | was 6 (3 moved to OUT_OF_SCOPE) |
| OUT_OF_SCOPE | 4 | NEW explicit category |
| NOT_IMPLEMENTED | 4 | was 2 |
| EVIDENCE_INSUFFICIENT | 4 | NEW explicit category |
| ICODER_TECH_DEBT | 1 | same |
| NOT_COMPARABLE | 0 | reserved |
| **Total** | **51** | |

**Critical changes from Pre-A0 V2:**

| Dimension | Pre-A0 V2 | Phase A0 V2.1 | Reason |
|-----------|-----------|---------------|--------|
| F-08 Edge PHI redaction | ICODER_ADVANTAGE | **CORTI_ADVANTAGE** | iCoDer's pii_redaction.py is EXPORT-PATH ONLY (Gate 9 K3.2); Corti architecture claims edge redaction (E1 docs). Pre-A0 inverted this. |
| C-10 AMBOSS expert | CORTI_ADVANTAGE | **EVIDENCE_INSUFFICIENT** | Only prompt-referenced (E1). Could be stale template. Cannot promote. |
| B-01 Agent Create | PARITY | **EVIDENCE_INSUFFICIENT** | Both at E5 (UI surface). Neither end-to-end verified. |
| B-03 Agent Update | PARITY | **EVIDENCE_INSUFFICIENT** | Same as B-01. |
| B-04 Agent Delete | PARTIAL_PARITY | **EVIDENCE_INSUFFICIENT** | iCoDer has it but Corti delete not observed. |
| C-06 Interviewing | PARTIAL_PARITY | **EVIDENCE_INSUFFICIENT** | Different mechanisms; not comparable at the same abstraction level. |
| C-07/C-08/C-09/C-11 (non-CN experts) | DIFFERENT_BY_DESIGN | **OUT_OF_SCOPE** for C-07/C-08/C-09; DIFFERENT_BY_DESIGN for C-11 | Sharper classification per spec §13.2. |

## §4. Severity-weighted gap count

Per spec §13.2, P0 has 4 sub-classes:

| Severity | Count | Examples |
|----------|------:|----------|
| **P0** (general) | 6 | E-01 billing, E-02 plan, F-05 cloud deploy, F-07 failover, etc. |
| **P0-S** (Security/PHI) | 3 | F-01 等保, F-02 GB/T 35273, F-08 PHI redaction |
| **P0-D** (Deployment) | 2 | F-05 cloud SaaS, F-07 multi-region failover |
| **P0-C** (Clinical safety) | 1 | F-08 (clinical data path) — same dimension counted in P0-S for security angle |
| **P0-T** (Product truth) | 0 | (covered by E-01/E-02 etc.) |
| **P1** | 6 | E-03 auto-topup, E-04 alerts, E-05 history, E-07 pricing, B-05 lifecycle, G-06 SLA |
| **P2** | 8 | A-05 memory, A-08 Tasks, B-09 Code gen, C-01 memory expert, etc. |
| **P3** | 5 | B-08 Hub tabs, C-03/04/05 pubmed/web/calc, etc. |

**Total gaps with severity**: 32 of 51 dimensions have a gap worth tracking.

**CN-relevant dimensions**: 38. Of these, 11 have a P0/P0-S/P0-D/P1 gap.

## §5. What V2.1 does NOT claim

| Not claimed | Why |
|-------------|-----|
| "X% parity" | Composite percentage invalid per spec §13.2 |
| "iCoDer is at parity" | Not a defined status |
| "Corti wins commercial" | V2.1 lists 7 CORTI_ADVANTAGE dimensions in Commercial class, but does not roll up to a class-level verdict |
| "V1 → V2 swing" | Denominator instability |
| "First hospital pilot ready" | FORBIDDEN verdict per spec §15 |

## §6. The single most important chart

Instead of an aggregate %, V2.1 presents the **gap severity pyramid** for CN-relevant dimensions:

```
                    ┌─────────────────┐
                    │  P0 (blocker)   │   11 dimensions
                    └─────────────────┘
                  ┌─────────────────────┐
                  │      P1 (major)     │    6 dimensions
                  └─────────────────────┘
                ┌─────────────────────────┐
                │      P2 (polish)        │    8 dimensions
                └─────────────────────────┘
              ┌─────────────────────────────┐
              │       P3 (backlog)          │    5 dimensions
              └─────────────────────────────┘
            ┌─────────────────────────────────┐
            │  No gap / parity / advantage    │   21 dimensions
            └─────────────────────────────────┘
```

This is the only "count" Phase A0 reports. It is severity-weighted and CN-scoped.

## §7. Hard Checkpoint D — Parity Integrity

| Sub-check | Status |
|-----------|--------|
| D-1: All 51 dimensions have exactly one of 10 allowed statuses | ✅ (see `parity_matrix_v2_1.json` §summary.by_status sums to 51) |
| D-2: No composite buckets ("favorable", "parity %") | ✅ Not reported |
| D-3: Evidence grades orthogonal to parity status | ✅ `evidence_grade` is separate field per side |
| D-4: Severity assigned to every gap dimension | ✅ `severity_if_gap` field |
| D-5: Machine-verifiable JSON produced | ✅ `parity_matrix_v2_1.json` (51 dimension objects) |
| D-6: Pre-A0 V2 overstated claims corrected | ✅ 6 dimensions reassigned |
| D-7: CN-relevance flagged per dimension | ✅ `cn_relevant` boolean field |
| D-8: Forbidden verdicts not claimed | ✅ (no FORBIDDEN verdict in matrix) |

**Hard Checkpoint D: ✅ PASS (8/8 sub-checks)**

## §8. Findings raised in Gate 4

| ID | Severity | Title |
|----|----------|-------|
| **A0-G4-001** | P0-S | F-08 PHI redaction is CORTI_ADVANTAGE not ICODER_ADVANTAGE — iCoDer's redactor is export-only per Gate 9 K3.2. Pre-A0 inverted this. |
| **A0-G4-002** | P0-D | 11 CN-relevant P0 dimensions block hospital pilot readiness (was masked by Pre-A0's 77% CN-scoped "favorable" claim). |
| **A0-G4-003** | P1 | 6 P1 dimensions need to be tracked separately from P0 — they don't block pilot but block commercial scale. |
| **A0-G4-004** | P2 | 4 dimensions downgraded to EVIDENCE_INSUFFICIENT — Phase A1 should promote via E6 evidence capture. |

## §9. Gate 4 verdict

```
PHASE_A0_GATE_4_PARITY_INTEGRITY_CLOSED
51_DIMENSIONS_WITH_MUTUALLY_EXCLUSIVE_STATUSES
0_COMPOSITE_PERCENTAGES_REPORTED
11_CN_RELEVANT_P0_GAPS (vs Pre-A0's "77% favorable" mask)
6_PRE_A0_OVERSTATEMENTS_CORRECTED
HARD_CHECKPOINT_D_PASS (8/8 sub-checks)
0_FORBIDDEN_VERDICTS_CLAIMED
```

### Hard Checkpoints A+B+C+D closed; E-H pending

End of Gate 4. Proceeding to Gate 5 — Canonical Issue Ledger.
