# Charter Index

**Last updated**: 2026-07-21

Each Charter is a scope-bounded authorization. Work outside a Charter
requires a new Charter. Charters are append-only: a later Charter may
supersede an earlier one but may not rewrite its record.

## Phase A0 / A0.1 Charters

| Charter | Scope | Closure artefact | Status |
|---|---|---|---|
| Phase A0 Audit Repair | Reproduce and document 11 baseline failures | `reports/comprehensive-audit/PRE_A0_*` | SUPERSEDED by A0.1 |
| Phase A0.1 Audit Repair | 10 gates, validator repair, baseline freeze | `audit/phase-a0.1r-freeze` branch + tag `audit/phase-a0.1r-baseline` | CLOSED (immutable) |

## Phase A1A Charters (emergency security/tenant/PHI/truth containment)

| Charter | Scope | Closure artefact | Status |
|---|---|---|---|
| Phase A1A Gates 0/1 | Secrets + authentication fail-closed | commits `f6bbd60`, `06624b4` | CLOSED |
| Phase A1A Gate 2 | Tenancy + data isolation | commit `de2feaa` | CLOSED |
| Phase A1A Gate 3 | Tenancy truth + trace isolation + audit separation | commit `d1447f3` | CLOSED (carried into 3R) |
| Phase A1A Gate 3R | 10-sub-gate reconciliation of Gate 3 | commit `b737eab` | CLOSED |
| Phase A1A Gate 4 | PHI boundary + at-rest encryption + regional residency + browser storage + retention | commit `880f49c` + closure `b3ea064` | REOPENED (4R found 77 new pass→fail regressions) |
| Phase A1A Gate 4R | 5-sub-gate regression reconciliation + Rate Limiter hermeticity | commits `a2613b7`..`24967da` on `phase-a1a/gate4r-regression-reconciliation` | CLOSED (P0-5 only; Gate 4 itself stays REOPENED) |
| **Phase A1A Gate 4R-I** | Integration + repo reconciliation + product audit + Corti gap | THIS charter; commits `777d96d`, `ca36c51`, plus sub-gates 4R-I.2..4R-I.11 | IN PROGRESS |

## Phase A1A Gate 4R-I sub-charter plan

| Sub-gate | Subject | Status |
|---|---|---|
| 4R-I.0 | Integration Charter + evidence freeze + pre-merge tags | COMPLETED (`777d96d`) |
| 4R-I.1 | `--no-ff` merge into `phase-a1a/emergency-containment` | COMPLETED (`ca36c51`) |
| 4R-I.2 | Worktree / directory / index reorganization | IN PROGRESS |
| 4R-I.3 | Post-merge regression validation | IN PROGRESS |
| 4R-I.4 | Engineering debt liquidation | PENDING |
| 4R-I.5 | Corti official snapshot (clean-room) | PENDING |
| 4R-I.6 | iCoder capability inventory | PENDING |
| 4R-I.7 | Clean-room parity matrix | PENDING |
| 4R-I.8 | Security/compliance release re-audit | PENDING |
| 4R-I.9 | Release tier verdicts (MVP / Controlled Pilot / GA) | PENDING |
| 4R-I.10 | Development backlog + roadmap | PENDING |
| 4R-I.11 | Final verdict + closure notice | PENDING |

## Charter state machine

```
PROPOSED → AUTHORIZED → IN_PROGRESS → REVIEW → CLOSED
                                       ↓
                                    DEFERRED
                                       ↓
                                 SUPERSEDED
```

A Charter is only CLOSED when its acceptance conditions are MET and a
closure notice is committed. SUPERSEDED Charters are preserved unchanged;
their closure notices are not amended.

## Forbidden verdicts (apply to ALL Charters)

Issuing any of these verdict strings is FORBIDDEN by §22 of every
Phase A1A Charter:

```
PRODUCTION_READY
FULLY_VERIFIED
PHI_BOUNDED
CORTI_PARITY_VERIFIED
PASS_A1A_GATE4_FINAL
READY_FOR_HOSPITAL_DEPLOYMENT
CLINICAL_GRADE_VERIFIED
```

## Allowed verdicts (Phase A1A Gate 4R-I)

Only this verdict may be signed at Gate 4R-I.11:

```
PASS_A1A_GATE4R_INTEGRATION_REPOSITORY_RECONCILIATION_AND_PRODUCT_GAP_AUDIT_FILED
```

This verdict attests ONLY that:
- 4R was integrated per Charter 4R-I
- Directory and worktree state was reconciled under control
- Current product state and Corti gap were filed as evidence-backed reports

It does NOT attest Gate 4 closure, Corti parity, production readiness,
clinical quality, or comprehensive PHI bounding.
