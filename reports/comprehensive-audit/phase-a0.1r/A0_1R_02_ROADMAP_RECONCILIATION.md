# Phase A0.1R Gate 2 — Roadmap Reconciliation

> Produces `issue_ledger.v2_1.json` with the corrections prescribed
> by the Phase A0.1R charter §3.Gate2. Reconciles the drift between
> Phase A0.1's published roadmap and the underlying canonical issue
> array, splits Billing Theater into Product Truth + Commercial
> Capability, reframes npm as one-of-many distribution channels,
> and bounds CDI Research Mode.
>
> Verdict: `PHASE_A0_1_R_GATE_2_ROADMAP_RECONCILED`

Spec reference: Phase A0.1R charter §3.Gate2.

Source: `reports/comprehensive-audit/phase-a0.1/issue_ledger.v2.json`
Target: `reports/comprehensive-audit/phase-a0.1r/issue_ledger.v2_1.json`
Builder: `scripts/audit/build_issue_ledger_v2_1.py`

---

## §1. Drift sources closed

### §1.1 P0-S_open count drift

| Source | Value |
|---|---:|
| Phase A0.1 v2 ledger claim | 11 |
| Actual strict OPEN (computed from array) | **10** |
| Actual OPEN + MITIGATED (computed from array) | **12** |

**Resolution**: v2.1 reports both strict and open+mit. The charter
mandated `P0_aggregate_open` → strict count. v2.1's
`severity_counts_normalized.open_by_severity_strict_open.P0_aggregate_open_strict = 22`
is the authoritative figure.

### §1.2 P0_aggregate_open count drift

| Source | Value |
|---|---:|
| Phase A0.1 v2 ledger claim | 23 |
| Actual strict OPEN | **22** |
| Actual OPEN + MITIGATED | **24** |

The 23 figure was a hand-edited average — neither the strict-OPEN
count (22) nor the OPEN+MITIGATED count (24). v2.1 eliminates the
ambiguity.

### §1.3 primary_phase_mapping completeness

| Phase | v2 explicit IDs | v2.1 explicit IDs | Δ |
|---|---:|---:|---|
| A1_security_first | 12 | 11 | −1 (A0-P0-022 stays; A0-P0-023/024 out to ops; A0-P0-001/002 out to legal; A0-P0-008 in from A2) |
| A1_legal_compliance | 0 (didn't exist) | 2 | +2 (new workstream) |
| A1_clinical_safety | 2 | 2 | 0 |
| A1_deployment_ops | 1 | 3 | +2 (A0-P0-023/024 in from security) |
| A1_product_truth_minimal | 4 | 4 | 0 |
| A2_commercial_deferred | 3 | 3 | 0 (A0-P0-008 out; A0-P0-021 added explicitly) |
| A2 (P1) | — | 17 | (P1 bucket) |
| A3 (P2) | — | 28 | (P2 bucket) |
| A4 (P3) | — | 11 | (P3 bucket) |
| **Total workstreams** | **12** | **13** | **+1** |

The v2 ledger undercounted workstreams by 1 (no legal separation)
and listed A0-P0-021 only in the per-issue field, not in the
mapping's `explicit_ids`. v2.1 fixes both.

### §1.4 79 vs 83 phase-count drift

Phase A0.1's Final Summary reported `A1=19 P0 / A2=22 P1 + 4 P0-commercial-deferred / A3=27 P2 / A4=11 P3`.

Re-derived from v2.1:

| Phase | Issues | v2 claim | Δ |
|---|---:|---:|---|
| A1 P0 (security + legal + clinical + deployment + product_truth) | 22 | 19 | +3 |
| A2 P0-commercial-deferred | 3 | 4 | −1 |
| A2 P1 | 17 | 22 | −5 |
| A3 P2 | 28 | 27 | +1 |
| A4 P3 | 11 | 11 | 0 |

The total open canonical count remains **79** (matches Phase A0.1
v2's canonical count). The drift was in distribution, not in
total — caused by:

- A0-P0-008 returning from A2 to A1 (P0)
- A0-P0-001/002 splitting out as legal (still P0, still A1)
- A0-P0-023/024 staying in A1 but moving workstream security→ops (no phase change)
- A0-P0-004 Billing Theater split creates 2 derived issues; the original is marked `SPLIT_INTO_A0-P0-004a_AND_A0-P0-004b`

---

## §2. Corrections applied

### §2.1 Workstream reassignment (5 issues)

| ID | Severity | v2 primary_phase | v2.1 primary_phase | Reason |
|---|---|---|---|---|
| A0-P0-001 | P0-S | A1_security_first | A1_legal_compliance | Compliance certifications (等保2.0 三级 + GB/T 35273) are legal work |
| A0-P0-002 | P0-S | A1_security_first | A1_legal_compliance | Privacy Policy / Terms / DPA / SLA are legal work |
| A0-P0-008 | P0-S | A2_commercial_deferred | A1_security_first | RUNTRACE_STORE=memory default is a security gap (audit trail integrity) |
| A0-P0-023 | P0-D | A1_security_first | A1_deployment_ops | Backup/restore runbook is operations work |
| A0-P0-024 | P0-D | A1_security_first | A1_deployment_ops | Upgrade/rollback runbook is operations work |

Each issue carries a `primary_phase_history` entry recording the
change, timestamp, and reason — preserving the audit trail.

### §2.2 Billing Theater split (A0-P0-004)

Original single issue: "Billing Theater — fake balance/credits + no payment model"

Phase A0.1R charter §3.Gate2 mandates splitting into:

- **A0-P0-004a** (Product Truth portion): fake balance/credits
  displayed without underlying ledger. UI dishonesty.
  - Severity: P0-T
  - primary_phase: **A1_product_truth_minimal**
  - Why: any user who sees a fabricated balance is being deceived,
    regardless of whether the platform accepts payment. This must
    be fixed before the next user sees the UI.

- **A0-P0-004b** (Commercial Capability portion): no payment model.
  - Severity: P0-T
  - primary_phase: **A2_commercial_capability_parallel** (new parallel track)
  - Why: A2 commercial track must not default to Stripe / Alipay /
    WeChat. Hospital procurement in CN often requires invoice-based,
    contract-based, or public-cloud-billing models. The commercial
    design is a separate decision flow.

Original A0-P0-004 stays in the ledger with `split_status =
SPLIT_INTO_A0-P0-004a_AND_A0-P0-004b` for audit-trail continuity.

### §2.3 npm reframing (A0-P0-009)

Original framing: `PUBLIC_NPM_NOT_PUBLISHED` (iCoDer SDK not on public npm)

Reframed: `NO_REPRODUCIBLE_SIGNED_EXTERNAL_DISTRIBUTION_CHANNEL`

The reframing corrects two implicit assumptions in the v2 framing:

1. **Public npm is not the default P0 distribution channel**.
   Charter constraint: public npm must not be the assumed
   distribution mechanism. Acceptable alternatives include:
   - Private npm registry (authenticated partner access)
   - Direct partner distribution with signed `.tgz` + SHA-256 + SBOM
   - GitHub Packages with provenance attestations
   - Corporate artifact registry (JFrog, Nexus)

2. **The actual gap is reproducibility + signing + external-channel
   cleanliness**, not "not on npm". Even if iCoDer published to npm
   tomorrow, the underlying issue (no signed provenance, no SBOM,
   no reproducible build) would remain.

### §2.4 CDI Research Mode boundary (A0-P0-007)

A0-P0-007 (CDI loop) now carries explicit
`phase_a0_1r_boundary.boundary_applied = true` with:

- **research_mode_definition**: restricted-scope, no-auto-send,
  no-auto-writeback
- **closure_requirement**: real clinician engagement loop
  (Provider Query → Clinician Response → Document Revision → CDI
  Re-review → Medical Coding with audit trail)
- **research_mode_does_not_close_loop**: true

This prevents a Phase A1A team from claiming "CDI Research Mode
shipped, therefore the CDI Clinical Loop is closed." The loop is
closed only by real clinician engagement.

### §2.5 A0-P0-021 explicit listing

A0-P0-021 (supply chain signing) was tagged `primary_phase =
A2_commercial_deferred` in the per-issue field but missing from
`primary_phase_mapping.A2_commercial_deferred.explicit_ids` in v2.
v2.1 rebuilds the explicit_ids lists from the per-issue field, so
A0-P0-021 now appears in both places consistently.

---

## §3. v2.1 ledger summary

Authoritative counts (machine-derived in
`scripts/audit/build_issue_ledger_v2_1.py`):

```
total_raw_findings:           91
canonical_count:              86
open_canonical_count:         79

by_severity_from_array:
  P0-S: 12, P0-C: 2, P0-D: 4, P0-T: 6, P0_aggregate: 24
  P1: 27, P2: 28, P3: 12

by_status_from_array:
  OPEN: 68, OPEN_BACKLOG: 11,
  MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED: 2,
  RESOLVED_PER_A0_GATE_2: 3, RESOLVED_PER_A0_GATE_3: 1,
  REFRAMED: 1, DUPLICATE: 5

open_by_severity_strict_open:
  P0-S_open: 10  (v2 claimed 11)
  P0-C_open: 2
  P0-D_open: 4
  P0-T_open: 6
  P0_aggregate_open_strict: 22  (v2 claimed 23)
  P1_open: 22
  P2_open: 27
  P3_open: 11

open_by_severity_open_plus_mitigated:
  P0-S_open_plus_mit: 12
  P0_aggregate_open_plus_mit: 24
```

Workstream count: **13** (v2 claimed 12).

A1 P0 breakdown by workstream (strict OPEN):

```
A1_security_first:        9 P0-S + 1 P0-D (tenancy isolation A0-P0-022) = 10
A1_legal_compliance:      2 P0-S (A0-P0-001/002)                        = 2
A1_clinical_safety:       2 P0-C (A0-P0-007/013)                        = 2
A1_deployment_ops:        1 P0-D (A0-P0-003)                            = 1
                          + 2 P0-D (A0-P0-023/024) = 3
A1_product_truth_minimal: 4 P0-T (A0-P0-005/006/014/015 + 004a)         = 5
A1 P0 aggregate:          22 (strict OPEN)
```

A2 P0-commercial-deferred: 3 (A0-P0-004 original, A0-P0-009 reframed,
A0-P0-021 explicit). The original A0-P0-004 carries `split_status`
pointing to its 004a/004b derivatives.

---

## §4. A1 P0 workstream map (corrected)

```
A1 (22 P0 strict OPEN, was claimed 19)
├── A1_security_first (10 P0)
│   ├── P0-S: A0-P0-010 (.env.example), A0-P0-011 (audit_logs),
│   │        A0-P0-012 (NULL org_id), A0-P0-016 (encryption at rest),
│   │        A0-P0-017 (PHI redactor EXPORT-PATH), A0-P0-020 (Patient A/B),
│   │        A0-P0-008 (RUNTRACE_STORE, returned from A2),
│   │        A0-P0-018/019 (MITIGATED, kept for audit trail)
│   └── P0-D: A0-P0-022 (multi-tenant Trace+Usage+Context isolation)
├── A1_legal_compliance (2 P0, NEW)
│   └── P0-S: A0-P0-001 (compliance certs), A0-P0-002 (legal docs)
├── A1_clinical_safety (2 P0)
│   └── P0-C: A0-P0-007 (CDI loop, Research Mode bounded),
│             A0-P0-013 (F1 baseline)
├── A1_deployment_ops (3 P0)
│   └── P0-D: A0-P0-003 (shippable deployment),
│             A0-P0-023 (backup/restore runbook, moved from security),
│             A0-P0-024 (upgrade/rollback runbook, moved from security)
└── A1_product_truth_minimal (5 P0)
    └── P0-T: A0-P0-005 (Corti links), A0-P0-006 (cost bug),
              A0-P0-014 (parity overclaim), A0-P0-015 (strategic incoherence),
              A0-P0-004a (Billing Theater Product Truth portion, NEW via split)
```

A2-commercial-deferred + parallel-commercial:

```
A2 P0-commercial-deferred (3 P0)
├── A0-P0-004 (original, split into 004a/004b)
├── A0-P0-009 (reframed: NO_REPRODUCIBLE_SIGNED_EXTERNAL_DISTRIBUTION_CHANNEL)
└── A0-P0-021 (supply chain signing; explicit_ids now lists this)

A2 commercial_capability_parallel (1 P0)
└── A0-P0-004b (Commercial Capability portion of Billing Theater split)
```

---

## §5. Validator V3 hooks (preview)

The Phase A0.1R Gate 7 validator will enforce:

1. `severity_counts_normalized.open_by_severity_strict_open.P0_aggregate_open_strict`
   must equal the array-derived strict-OPEN P0 count.
2. Every issue's `primary_phase` value must appear as a key in
   `primary_phase_mapping`, and the issue's canonical_id must
   appear in that key's `explicit_ids` list.
3. `primary_phase_mapping.workstream_count.phase_a0_1_r_v2_1_actual`
   must equal `len(primary_phase_mapping.workstream_count.workstreams)`.
4. Any issue with `canonical_id == "A0-P0-004"` must carry
   `split_status == "SPLIT_INTO_A0-P0-004a_AND_A0-P0-004b"`.
5. Any issue with `canonical_id == "A0-P0-009"` must carry
   `phase_a0_1r_reframe.reframed == true`.
6. Any issue with `canonical_id == "A0-P0-007"` must carry
   `phase_a0_1r_boundary.research_mode_does_not_close_loop == true`.

Negative fixtures for each rule will be produced in Gate 7.

---

## §6. Findings raised in Gate 2

| ID | Severity | Title |
|----|----------|-------|
| **A0.1R-G2-001** (closed) | P0 (data) | P0-S_open count drift (11→10 strict) and P0_aggregate_open drift (23→22 strict). v2.1 records both strict and open+mit counts. |
| **A0.1R-G2-002** (closed) | P0 (data) | primary_phase_mapping explicit_ids undercount; rebuilt from per-issue field. |
| **A0.1R-G2-003** (closed) | P1 | A0-P0-001/002 workstream misplacement (security→legal). New `A1_legal_compliance` workstream. |
| **A0.1R-G2-004** (closed) | P1 | A0-P0-008 workstream misplacement (commercial-deferred→security). |
| **A0.1R-G2-005** (closed) | P1 | A0-P0-023/024 workstream misplacement (security→deployment-ops). |
| **A0.1R-G2-006** (closed) | P1 | A0-P0-004 Billing Theater split into 004a (Product Truth) + 004b (Commercial Capability). |
| **A0.1R-G2-007** (closed) | P1 | A0-P0-009 reframed to NO_REPRODUCIBLE_SIGNED_EXTERNAL_DISTRIBUTION_CHANNEL. |
| **A0.1R-G2-008** (closed) | P1 | A0-P0-007 CDI Research Mode explicitly bounded; cannot be used to claim Clinical Loop closed. |
| **A0.1R-G2-009** | P2 | Roadmap narrative (Phase A0.1 Final Summary) needs updating to reflect v2.1 numbers. Deferred to Phase A0.1R Commit B. |

---

## §7. Gate 2 verdict

```
PHASE_A0_1_R_GATE_2_ROADMAP_RECONCILED

issue_ledger.v2_1.json:
  schema_version: 2.1
  supersedes: reports/comprehensive-audit/phase-a0.1/issue_ledger.v2.json
  corrections_applied: 10
  P0_aggregate_open_strict: 22 (was 23)
  workstream_count: 13 (was 12)
  billing_theater_split: A0-P0-004a + A0-P0-004b
  npm_reframed: NO_REPRODUCIBLE_SIGNED_EXTERNAL_DISTRIBUTION_CHANNEL
  cdi_research_mode_bounded: true

NEXT_GATE: GATE_3_PARITY_V2_3
NEXT_ALLOWED_VERDICT:
  PHASE_A0_1_R_GATE_3_PARITY_V2_3_RECONCILED
```

End of Gate 2.
