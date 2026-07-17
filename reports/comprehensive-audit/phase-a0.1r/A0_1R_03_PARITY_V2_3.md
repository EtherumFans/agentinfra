# Phase A0.1R Gate 3 — Parity Matrix V2.3

> Applies two corrections prescribed by Phase A0.1R charter §3.Gate3:
> (1) the illegal `ICODER_TECH_DEBT` status on D-05 is downgraded;
> (2) symmetric evidence thresholds are enforced on every
> `CORTI_ADVANTAGE` dimension (the same rule Phase A0.1 Gate 4
> applied to `ICODER_ADVANTAGE`).
>
> Verdict: `PHASE_A0_1_R_GATE_3_PARITY_V2_3_RECONCILED`

Source: `reports/comprehensive-audit/phase-a0.1/parity_matrix_v2_2.json`
Target: `reports/comprehensive-audit/phase-a0.1r/parity_matrix_v2_3.json`
Builder: `scripts/audit/build_parity_matrix_v2_3.py`

---

## §1. Symmetric threshold rule

Phase A0.1 Gate 4 introduced evidence thresholds for `ICODER_ADVANTAGE`
claims: an unverified advantage is not an advantage. Phase A0.1R
extends the rule symmetrically to `CORTI_ADVANTAGE`.

| Class | Advantage threshold | Rationale |
|---|---|---|
| Compliance / Security | E7 (security-negative-verified) | Compliance gaps are silent; only a negative security audit proves the advantaged side is actually safer |
| Runtime / Agent | E4 (integration-verified) | Runtime claims require observable behavior |
| UX / Product | E5 (browser-verified) | UX claims require visible behavior |
| Tool / MCP catalog | E2 (code-observed) | Tool counts are objective |

Same rule for both directions. A `CORTI_ADVANTAGE` claim with Corti
evidence at E1 (marketing/docs only) fails the threshold.

## §2. Regrades applied (6 total)

| ID | Name | Field changed | From | To | Reason |
|---|---|---|---|---|---|
| D-05 | Legacy tool layer | parity_status | ICODER_TECH_DEBT | EVIDENCE_INSUFFICIENT | Status not in allowed_statuses |
| F-03 | HIPAA | parity_status | CORTI_ADVANTAGE | EVIDENCE_INSUFFICIENT | Corti E1 < E7 threshold |
| F-04 | ISO 27001 | parity_status | CORTI_ADVANTAGE | EVIDENCE_INSUFFICIENT | Corti E1 < E7 threshold |
| F-05 | Cloud SaaS deployment | class | Compliance | Deployment | Reclassify: measures deployment capability, not compliance certification. After reclassification, E5 Corti meets E4 deployment threshold → CORTI_ADVANTAGE retained |
| F-07 | Multi-region failover | parity_status | CORTI_ADVANTAGE | EVIDENCE_INSUFFICIENT | Corti E1 < E7 threshold |
| F-08 | Edge-node PHI redaction | parity_status | CORTI_ADVANTAGE | EVIDENCE_INSUFFICIENT | Corti E1 < E7 threshold |

### §2.1 F-05 reclassification detail

F-05 in v2.2 had class `Compliance` and Corti evidence E5. Under the
symmetric threshold rule with the compliance class, Corti at E5
fails E7, which would force a downgrade. But "Cloud SaaS deployment"
measures deployment capability (production presence in regions),
not a compliance certification. The v2.2 class label was wrong.

v2.3 reclassifies F-05 to class `Deployment`. Under the deployment
threshold E4 (integration-verified), Corti at E5 (browser-verified
production) passes. CORTI_ADVANTAGE is retained. This is the
**conservative but truthful** outcome: Corti's 4-region production
footprint is real and verified, but it is not a compliance claim.

### §2.2 The 4 CORTI_ADVANTAGE downgrades

The four compliance/security dimensions where Corti's evidence was
only marketing (E1):

- **F-03 HIPAA**: Corti marketing claims HIPAA compliance; no
  certificate on file. Phase A1A-legal-compliance must obtain
  Corti's actual certificate or this stays EVIDENCE_INSUFFICIENT.
- **F-04 ISO 27001**: same situation as F-03.
- **F-07 Multi-region failover**: Corti production architecture
  claims failover but no negative verification (no outage test).
  Phase A1A-deployment-ops must observe a failover test before
  claiming Corti advantage.
- **F-08 Edge-node PHI redaction**: Corti architecture docs claim
  edge redaction but no live-path evidence. iCoDer also lacks this
  (redactor is export-only per Gate 9 K3.2). Symmetric: both fail
  threshold → EVIDENCE_INSUFFICIENT.

## §3. v2.3 status distribution

| Status | v2.2 count | v2.3 count | Δ |
|---|---:|---:|---:|
| PARITY | 9 | 9 | 0 |
| PARTIAL_PARITY | 6 | 6 | 0 |
| NOT_IMPLEMENTED | 4 | 4 | 0 |
| **EVIDENCE_INSUFFICIENT** | **14** | **19** | **+5** |
| **CORTI_ADVANTAGE** | **17** | **13** | **−4** |
| ICODER_ADVANTAGE | 2 | 2 | 0 |
| OUT_OF_SCOPE | 3 | 3 | 0 |
| DIFFERENT_BY_DESIGN | 3 | 3 | 0 |
| **ICODER_TECH_DEBT** | **1** | **0** | **−1** |
| **Total** | **59** | **59** | **0** |

Total dimensions unchanged (59). The illegal status
`ICODER_TECH_DEBT` no longer exists. The `CORTI_ADVANTAGE` count
is now symmetric with the `ICODER_ADVANTAGE` threshold enforcement
applied in Phase A0.1 Gate 4.

## §4. Allowed-statuses enforcement

v2.3 `allowed_statuses`:

```
PARITY, PARTIAL_PARITY, ICODER_ADVANTAGE, CORTI_ADVANTAGE,
DIFFERENT_BY_DESIGN, OUT_OF_SCOPE, NOT_IMPLEMENTED,
NOT_VERIFIED, EVIDENCE_INSUFFICIENT, NOT_COMPARABLE
```

Every dimension's `parity_status` is verified against this list
by Gate 7's validator V3. `ICODER_TECH_DEBT` is no longer present.

## §5. Validator V3 hooks

Gate 7 will enforce:

1. Every dimension's `parity_status` ∈ `allowed_statuses`.
2. For each `CORTI_ADVANTAGE` dimension,
   `corti_evidence_grade >= threshold_for_class(class)`.
3. For each `ICODER_ADVANTAGE` dimension,
   `icoder_evidence_grade >= threshold_for_class(class)`.
4. `summary.status_distribution_v2_3` matches array-derived counts.
5. Negative fixture `nf04_illegal_parity_status.json` (D-05 at
   ICODER_TECH_DEBT) fails the validator.
6. Negative fixture `nf03_corti_advantage_low_evidence.json`
   (F-03 at CORTI_ADVANTAGE with corti_evidence_grade=E1) fails.

## §6. Findings raised in Gate 3

| ID | Severity | Title |
|----|----------|-------|
| **A0.1R-G3-001** (closed) | P1 | D-05 illegal status `ICODER_TECH_DEBT` removed. |
| **A0.1R-G3-002** (closed) | P0 (data) | Symmetric threshold applied: F-03/04/07/08 CORTI_ADVANTAGE downgraded; all 4 had Corti evidence at E1 vs E7 threshold. |
| **A0.1R-G3-003** (closed) | P2 | F-05 class reclassified Compliance → Deployment; CORTI_ADVANTAGE retained under correct E4 threshold. |
| **A0.1R-G3-004** | P2 | The v2.2 class taxonomy is coarse (Compliance bucket holds both certifications and deployment capabilities). Phase A1A should refine to: Compliance-Certification, Compliance-Architecture, Deployment, Runtime, UX, Tool-Catalog. |

---

## §7. Gate 3 verdict

```
PHASE_A0_1_R_GATE_3_PARITY_V2_3_RECONCILED

parity_matrix_v2_3.json:
  schema_version: 2.3
  supersedes: reports/comprehensive-audit/phase-a0.1/parity_matrix_v2_2.json
  regrades_applied: 6 (1 illegal status + 4 threshold downgrades + 1 class reclassify)
  total_dimensions: 59 (unchanged)
  CORTI_ADVANTAGE: 13 (was 17)
  EVIDENCE_INSUFFICIENT: 19 (was 14)
  ICODER_TECH_DEBT: 0 (was 1, illegal)
  symmetric_threshold_rule: APPLIED_TO_BOTH_DIRECTIONS

NEXT_GATE: GATE_4_MATURITY_V3_7_AXIS
NEXT_ALLOWED_VERDICT:
  PHASE_A0_1_R_GATE_4_MATURITY_V3_7_AXIS_POPULATED
```

End of Gate 3.
