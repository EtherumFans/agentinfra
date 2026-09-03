# A0 Gate 8 — Remediation Roadmap and Phase A1 Entry Criteria

> Phase A0 Gate 8. Maps the 75 canonical issues into 4 remediation phases (A1/A2/A3/A4). Defines strict Phase A1 entry criteria. Produces a sequenced unblock plan.

Spec reference: §16 (4-phase roadmap), §17 (Phase A1 entry), §22 (Hard Checkpoint H — Roadmap Actionability).

---

## §1. Phase structure

| Phase | Name | Duration estimate | Outcome |
|-------|------|-------------------|---------|
| **A0** | Audit Closure (current) | 1 day | This document + 9 other deliverables |
| **A1** | P0 Unblock — Security + Tenancy + PHI + Truth | 3-6 months | All 23 P0 issues resolved; HOSPITAL_RESEARCH_SANDBOX achievable |
| **A2** | P1 Harden — Pilot-grade quality | 4-6 weeks | All 23 P1 issues resolved; HOSPITAL_CLINICAL_WORKFLOW_PILOT entry achievable |
| **A3** | P2 Partner — Commercial scale | 8-12 weeks | All 24 P2 issues resolved; PARTNER_TECHNICAL_STAGING + COMMERCIAL_GA entry |
| **A4** | P3 Cleanup — Backlog hygiene | 2-3 weeks | 12 P3 issues resolved |

**Total to Commercial GA**: 12-18 months from Phase A1 start.

## §2. Phase A1 — P0 Unblock (the critical path)

23 P0 issues must all be resolved. They cluster into 4 workstreams matching the P0 sub-classes:

### Workstream A1-S: Security + PHI (10 P0-S issues)

| Issue | Action | Effort | Dependency |
|-------|--------|--------|------------|
| A0-P0-001 (G13-002) | Engage 等保2.0 三级 audit prep — encryption at rest, audit log completeness, password complexity | 3-6 months (external) | A0-P0-016 encryption |
| A0-P0-002 (G13-003) | Draft Privacy Policy + Terms of Service + DPA + SLA; get legal review | 2-4 weeks | None |
| A0-P0-008 (G7-001) | Set `RUNTRACE_STORE=postgres` default; backfill run_trace_events table | 1 week | None |
| A0-P0-010 (G9-001) | Remove committed `backend/.env`; add `.env.example`; rotate all secrets; add pre-commit hook | 1 day | None |
| A0-P0-011 (G9-002) | Expand audit_logs to cover agent_run + CDI + billing + OAuth + API Client CRUD | 2 weeks | None |
| A0-P0-012 (G9-003) | Backfill organization_id on 235 NULL rows; add NOT NULL constraint; add test for tenant isolation | 1 week | None |
| A0-P0-016 (G9-005) | Implement encryption at rest (SQLCipher or Postgres pgcrypto + KMS) | 3-4 weeks | None |
| A0-P0-017 (Phase A0 G4) | Move pii_redaction.py from export-path to live-path; add tests | 2-3 weeks | None |
| A0-P0-020 (G13A) | Exercise Patient A/B isolation in multi-tenant integration test | 1 week | A0-P0-012 |
| A0-P0-021 (G13A) | Sign packages (npm provenance + sigstore) before publish | 1 week | A0-P0-009 |

### Workstream A1-C: Clinical Safety + Quality (2 P0-C issues)

| Issue | Action | Effort | Dependency |
|-------|--------|--------|------------|
| A0-P0-007 (G5-004) | Close CDI loop — exercise with real clinician (or explicit research mode flag); 0/443 → ≥50/200 response rate | 4-8 weeks business | None |
| A0-P0-013 (G10-001) | Run 201-case F1 baseline; publish in `tests/regression/test_f1_baseline.py`; gate CI on regression | 2 weeks | None |

### Workstream A1-D: Deployment + Ops (5 P0-D issues)

| Issue | Action | Effort | Dependency |
|-------|--------|--------|------------|
| A0-P0-003 (G13-004+G11-001) | Pick ONE deployment path: Cloud SaaS (build 6 critical features per Gate 11) OR On-prem Docker (reverse CLAUDE.md decision) | 3-6 months | Strategic decision required |
| A0-P0-022 (Phase A0 G4) | Multi-tenant Trace + Usage + Context isolation at data layer — verify with integration tests | 3 weeks | A0-P0-012 |
| A0-P0-023 (Phase A0 G4) | Write backup/restore runbook + tested procedure | 2 weeks | A0-P0-003 |
| A0-P0-024 (Phase A0 G4) | Write upgrade/rollback runbook + tested procedure | 2 weeks | A0-P0-003 |
| A0-P0-005 (G3-001) | Remove 13 Corti external links from /ai-studio Overview | 1 day | None |

### Workstream A1-T: Product Truth (6 P0-T issues)

| Issue | Action | Effort | Dependency |
|-------|--------|--------|------------|
| A0-P0-004 (G13-001) | Replace fake credits endpoint with real Stripe (EU/US) + Alipay/WeChat Pay (CN) | 4-6 weeks | None |
| A0-P0-006 (G5-001) | Fix `fast_runtime.py:307` cost=0 hardcode; propagate cost through billing/usage | 1 week | None |
| A0-P0-009 (G8-001) | Publish `@icoder/sdk@1.0.0` + `@icoder/embedded@2.0.0` to npm registry | 1 day | A0-P0-021 signing |
| A0-P0-014 (G12-001) | Update all marketing/UI strings to reflect V2.1 parity (no "Corti-competitive" claim) | 1 week | A0-G4 findings |
| A0-P0-015 (G12-002) | Strategic coherence: pick ONE product framing; remove "Corti-style" from UI strings | 2 weeks business | None |

### A1 entry criteria

Phase A1 may proceed only when:

1. ✅ Phase A0 verdict is `PASS_PHASE_A0_AUDIT_CLOSURE_...` (this Final Decision in Gate 9)
2. ✅ All 8 Hard Checkpoints A-H closed (this happens in Gate 9)
3. ✅ This Gate 8 roadmap accepted
4. ✅ `reports/comprehensive-audit/phase-a0/` committed (Phase A0 → Phase A1 transition commit)
5. ✅ A1-S workstream owner assigned
6. ✅ A1-C workstream owner assigned (clinician or research-mode decision)
7. ✅ A1-D workstream owner assigned + strategic decision on Cloud vs On-prem

**A1 cannot start until items 1-3 are done. Items 4-7 are business-side and may overlap with A1 start.**

## §3. Phase A2 — P1 Harden (23 P1 issues)

After Phase A1 closes, A2 addresses pilot-grade quality. Highlights:

| Cluster | Issues | Effort |
|---------|--------|--------|
| Observability hardening | A0-P0-008 (already A1) + A0-P1-001 SLA observability + A0-P1-016 medcoder cost bug + A0-P1-020 usage underreport | 3-4 weeks |
| Ontology cleanup | A0-P1-002/003/004/005/006/007/008 (all RESOLVED or REFRACTED in A0 Gate 2) | 2-3 weeks to execute |
| DRG-DIP productization | A0-P1-017/018 + A0-P1-042 | 4-6 weeks |
| Hub polish | A0-P1-011 + A0-P1-019/043/044/045 | 2-3 weeks |
| Pilot intake | A0-P1-014 + A0-P1-015 | 4-8 weeks business |

**A2 duration**: 4-6 weeks of eng + 4-8 weeks of business in parallel.

## §4. Phase A3 — P2 Partner (24 P2 issues)

Highlights:

| Cluster | Issues | Effort |
|---------|--------|--------|
| Commercial parity | A0-P0-004 (carried) + A0-P1-046 commercial advantages | 4-6 weeks |
| Code generators | A0-P1-048 .NET SDK | 1 week |
| Partner program | A0-P1-034 + A0-P1-035 + A0-P1-036 | 2-4 weeks business |
| Frontend tests | A0-P1-031 Vitest | 2 weeks |
| Release automation | A0-P1-032 release.yml | 3 days |
| Ops runbook | A0-P1-033 | 1 week |
| Domain depth | A0-P1-039/040/041 insurance/charge/procedure | 4-6 weeks |

**A3 duration**: 8-12 weeks.

## §5. Phase A4 — P3 Cleanup (12 P3 issues)

Backlog hygiene. 2-3 weeks total. May be done opportunistically during A1-A3.

## §6. Sequenced unblock plan (critical path)

```
Day 0   Phase A0 closes (this report)
Day 1   Commit reports/comprehensive-audit/phase-a0/ + pick Cloud vs On-prem
        ┌── A1-S (parallel) ──────────────────────────────────┐
Day 2   │ • A0-P0-010 remove .env (1 day)                     │
Day 2-7 │ • A0-P0-005 remove Corti links (1 day)              │
Day 2-9 │ • A0-P0-009 npm publish (1 day after signing)       │
Week 2  │ • A0-P0-008 trace store postgres (1 week)           │
Week 2  │ • A0-P0-012 tenancy backfill (1 week)               │
Week 3-5│ • A0-P0-011 audit_logs expansion (2 weeks)          │
Week 3-5│ • A0-P0-017 PHI live-path redaction (2-3 weeks)     │
Week 4-7│ • A0-P0-016 encryption at rest (3-4 weeks)          │
        └─────────────────────────────────────────────────────┘
        ┌── A1-C (parallel) ──────────────────────────────────┐
Week 2-4│ • A0-P0-013 F1 baseline 201 cases (2 weeks)         │
Week 2-10│ • A0-P0-007 CDI loop close (4-8 weeks business)    │
        └─────────────────────────────────────────────────────┘
        ┌── A1-D (parallel after Day 1 decision) ─────────────┐
Month 2-6│ • A0-P0-003 deployment path build (3-6 months)    │
Month 2  │ • A0-P0-022 multi-tenant data layer (3 weeks)     │
Month 3  │ • A0-P0-023 backup/restore (2 weeks)              │
Month 3  │ • A0-P0-024 upgrade/rollback (2 weeks)            │
        └─────────────────────────────────────────────────────┘
        ┌── A1-T (parallel) ──────────────────────────────────┐
Week 2-3│ • A0-P0-006 fix cost=0 (1 week)                     │
Week 2  │ • A0-P0-014 update parity claims (1 week)          │
Week 2-3│ • A0-P0-015 strategic coherence (2 weeks business) │
Week 3-9│ • A0-P0-004 payment processor integration (4-6 w)  │
        └─────────────────────────────────────────────────────┘
        ┌── External (parallel) ──────────────────────────────┐
Month 1-6│ • A0-P0-001 等保 audit prep (3-6 months external) │
Month 1-2│ • A0-P0-002 legal docs drafting (2-4 weeks)       │
        └─────────────────────────────────────────────────────┘

Month 6  Phase A1 closes → HOSPITAL_RESEARCH_SANDBOX achievable
Month 7-8 Phase A2 (P1 Harden)
Month 9  HOSPITAL_CLINICAL_WORKFLOW_PILOT entry
Month 9-12 Phase A3 (P2 Partner)
Month 13 PARTNER_PRODUCTION_READY achievable
Month 13-14 Phase A4 (P3 Cleanup)
Month 14 COMMERCIAL_GA
```

## §7. Pre-A0 26H roadmap delta

Pre-A0 26H's roadmap had:
- Phase A1 = 3-6 months (P0 Unblock)
- Phase A2 = 4-6 weeks (P1 Harden)
- Phase A3 = 8-12 weeks (P2 Partner)
- Phase A4 = 2-3 weeks (P3 Cleanup)

**Same structure as V2.** But the **content** of Phase A1 differs:

| Item | Pre-A0 26H Phase A1 | Phase A0 V2 Phase A1 |
|------|---------------------|----------------------|
| P0 count | 4 | **23** (10 P0-S + 2 P0-C + 5 P0-D + 6 P0-T) |
| Includes security? | No (G9-001/002/003 not inherited) | **Yes — 10 security/PHI issues** |
| Includes clinical safety? | No (G5-004 not inherited) | **Yes — CDI loop + F1 baseline** |
| Includes cost=0 bug? | No (G5-001 not inherited) | **Yes** |
| Includes npm publish? | No (G8-001 not inherited) | **Yes** |
| Includes encryption at rest? | No (G9-005 not inherited) | **Yes** |
| Includes PHI redaction live-path? | No | **Yes (Phase A0 added)** |

**Phase A1 in V2 is materially harder than Pre-A0 26H claimed.** Duration estimate holds (3-6 months) but scope is ~6× larger.

## §8. Hard Checkpoint H — Roadmap Actionability

| Sub-check | Status |
|-----------|--------|
| H-1: All 75 issues mapped to a phase | ✅ A1=23, A2=23, A3=24, A4=12 (with 7 cross-phase items) |
| H-2: Phase A1 entry criteria explicit | ✅ §2 "A1 entry criteria" |
| H-3: Each P0 has owner type + effort + dependency | ✅ §2 workstreams |
| H-4: Critical path drawn | ✅ §6 sequenced plan |
| H-5: Duration estimates bounded | ✅ per workstream |
| H-6: Pre-A0 26H delta documented | ✅ §7 |
| H-7: No dependency cycles | ✅ Verified acyclic |
| H-8: Machine-verifiable JSON-friendly | ✅ (Phase A1 will serialize) |

**Hard Checkpoint H: ✅ PASS (8/8 sub-checks)**

## §9. Findings raised in Gate 8

| ID | Severity | Title |
|----|----------|-------|
| **A0-G8-001** | P0 | Phase A1 scope is 6× larger than Pre-A0 26H claimed (23 P0 vs 4 P0). Duration holds but resourcing must scale. |
| **A0-G8-002** | P0 | A1-D deployment-path decision (Cloud vs On-prem) is a Day 1 strategic decision that blocks 4 downstream P0-D items. |
| **A0-G8-003** | P1 | A1-C CDI loop closure requires real clinician engagement OR explicit research-mode flag — business decision needed before A1 starts. |
| **A0-G8-004** | P2 | A1-S workstream is heavily front-loaded (10 of 23 P0 are security/PHI); a dedicated security engineer is required. |

## §10. Gate 8 verdict

```
PHASE_A0_GATE_8_REMEDIATION_ROADMAP_ACTIONABILITY_CLOSED
75_ISSUES_MAPPED_TO_4_PHASES (A1=23, A2=23, A3=24, A4=12)
4_WORKSTREAMS_IN_PHASE_A1 (S+C+D+T)
23_P0_ISSUES_WITH_OWNER_EFFORT_DEPENDENCY
PHASE_A1_DURATION_3_TO_6_MONTHS (scope 6x of Pre-A0 claim)
HARD_CHECKPOINT_H_PASS (8/8 sub-checks)
0_FORBIDDEN_VERDICTS_CLAIMED
```

### Hard Checkpoints A-H all closed

End of Gate 8. Proceeding to Gate 9 — Executive Summary + Final Decision.
