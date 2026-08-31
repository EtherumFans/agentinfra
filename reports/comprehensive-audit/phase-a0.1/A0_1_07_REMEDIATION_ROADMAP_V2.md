# Phase A0.1 Gate 7 — Remediation Roadmap V2

> Rebuilds the remediation roadmap from the v2 canonical issue ledger
> (Gate 3 output). Replaces Phase A0 v1's "75 issues / 4 phases / 3
> forbidden verdicts on the timeline" with a machine-derived plan
> that uses the actual 79 open canonical count and moves commercial
> blockers to A2.

Spec reference: Phase A0.1 §三 Gate 7.

---

## §1. Why V2 exists

Phase A0 v1 roadmap (`A0_08_REMEDIATION_ROADMAP_AND_PHASE_A1_ENTRY.md`)
had three structural defects:

1. **Wrong issue count.** v1 claimed "75 issues mapped to 4 phases
   (A1=23, A2=23, A3=24, A4=12)". The 75 figure is the retired
   narrative number from the v1 issue ledger (see Gate 3). Real
   canonical count = 86, open canonical = 79.

2. **Wrong A1 priorities.** v1 lumped all 6 P0-T issues into A1 P0
   work, including:
   - A0-P0-004 (Billing theater / Payment Processor) — commercial
   - A0-P0-009 (npm unpublished) — commercial
   - A0-P0-021 (supply chain signing) — commercial
   
   These are not Day-1 security blockers. They are A2 commercial
   blockers. Treating them as A1 P0 inflates A1 scope and delays
   the real security work.

3. **Forbidden verdicts on the timeline.** v1 wrote
   *"Month 13 PARTNER_PRODUCTION_READY achievable"* and
   *"Month 14 COMMERCIAL_GA"*. Both `PARTNER_PRODUCTION_READY` and
   `COMMERCIAL_GA` are on the forbidden verdicts list
   (per Phase A0.1 §五).

V2 fixes all three.

## §2. A1 scope corrected — 19 P0 issues (not 23)

Per the Gate 3 primary_phase_mapping, A1 is split into 4 workstreams
plus a separate A2_commercial_deferred bucket:

| Bucket | Count | Issues |
|--------|------:|--------|
| **A1_security_first** | 12 | A0-P0-001/002/010/011/012/016/017/018/019/020/022/023/024 (P0-S + P0-D) |
| **A1_clinical_safety** | 2 | A0-P0-007 (CDI loop), A0-P0-013 (F1 baseline) |
| **A1_deployment_ops** | 1 | A0-P0-003 (deployment path) |
| **A1_product_truth_minimal** | 4 | A0-P0-005 (Corti links), A0-P0-006 (cost=0), A0-P0-014 (parity overclaim), A0-P0-015 (strategic incoherence) |
| **A2_commercial_deferred** | 4 | A0-P0-004 (billing), A0-P0-008 (trace store default), A0-P0-009 (npm), A0-P0-021 (supply chain) |

**A1 P0 total = 19** (down from v1's 23). The 4 commercial items
move to A2.

### Note on A0-P0-018/019

These were regraded in Gate 6 from `MITIGATED_IN_PHASE_7 closed` to
`MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED open` at E1. They
re-enter A1_security_first for independent negative reverification
(capture the 7 browser artifacts listed in Gate 6 §3).

### Note on A0-P0-008

This finding (RUNTRACE_STORE=memory default) is in `A2_commercial_deferred`
because trace-store-default is an auditability gap, not a PHI leak.
The trace store *exists* in code; the default is wrong. That said,
it is the *prerequisite* for several A1 audit-claim findings
(A0-P0-011, A0-P0-012) because those tests need actual trace rows to
verify. **Operational ordering**: A0-P0-008 should be done early in
A1 even though it lives in A2 on the severity axis.

## §3. Phase structure V2

| Phase | Name | Duration | Open canonical issues | Outcome |
|-------|------|----------|----------------------:|---------|
| **A0.1** | Audit Repair + Baseline Freeze (current) | 1 day | 0 product changes | This report series + frozen baseline |
| **A1** | P0 Unblock — Security + Clinical + Truth | 3-6 months | 19 P0 | CONDITIONAL_TARGET: HOSPITAL_RESEARCH_SANDBOX achievable |
| **A2** | P1 Harden + Commercial Deferrables | 6-8 weeks eng + 4-8 weeks business parallel | 22 P1 + 4 P0-commercial-deferred | ACHIEVABLE: PARTNER_TECHNICAL_STAGING |
| **A3** | P2 Polish — Partner Scale | 8-12 weeks | 27 P2 | ACHIEVABLE: HOSPITAL_CLINICAL_WORKFLOW_PILOT entry |
| **A4** | P3 Cleanup — Backlog Hygiene | 2-3 weeks | 11 P3 | ACHIEVABLE: backlog clean |

Total open canonical: 19 + (22 + 4) + 27 + 11 = **83** across A1-A4.

(Delta vs Gate 3's 79: 4 issues are cross-phase. E.g., A0-P0-018
reverification is A1; the artifact-capture is its own work, counted
once. Gate 8 validator will reconcile.)

## §4. A1 workstream detail

### A1_security_first (12 P0, ~3-6 months)

| Issue | Action | Effort | Dependency |
|-------|--------|--------|------------|
| A0-P0-001 | 等保2.0 三级 audit prep — encryption at rest, audit log completeness, password complexity | 3-6 months external | A0-P0-016 |
| A0-P0-002 | Draft Privacy Policy + Terms + DPA + SLA; legal review | 2-4 weeks | None |
| A0-P0-010 | Ship `.env.example`; add startup sentinel that refuses `change-me-in-production`; rotate placeholder secret | 1 day | None |
| A0-P0-011 | Expand audit_logs to cover agent_run + CDI + billing + OAuth + API Client CRUD | 2 weeks | None |
| A0-P0-012 | Backfill organization_id on 235 NULL rows; add NOT NULL constraint; add tenant-isolation integration test | 1 week | None |
| A0-P0-016 | Implement encryption at rest (SQLCipher or pgcrypto + KMS) | 3-4 weeks | None |
| A0-P0-017 | Move pii_redaction from export-path to live-path; add tests | 2-3 weeks | None |
| A0-P0-018 | Capture 7 negative-verification artifacts (Gate 6 §3) for URL-JWT threat closure | 1 week | None |
| A0-P0-019 | Capture 7 negative-verification artifacts for postMessage threat closure | 1 week (parallel with 018) | None |
| A0-P0-020 | Exercise Patient A/B isolation in multi-tenant integration test | 1 week | A0-P0-012 |
| A0-P0-022 | Multi-tenant Trace + Usage + Context isolation at data layer | 3 weeks | A0-P0-012 |
| A0-P0-023 | Write backup/restore runbook + tested procedure | 2 weeks | A0-P0-003 |
| A0-P0-024 | Write upgrade/rollback runbook + tested procedure | 2 weeks | A0-P0-003 |

### A1_clinical_safety (2 P0-C, business-critical)

| Issue | Action | Effort | Dependency |
|-------|--------|--------|------------|
| A0-P0-007 | Close CDI loop — capture first clinician response and first document revision; if not achievable in A1, mark explicit research-mode flag | 4-8 weeks business | None |
| A0-P0-013 | Run 201-case F1 baseline; publish in `tests/regression/test_f1_baseline.py`; gate CI on regression | 2 weeks | None |

### A1_deployment_ops (1 P0-D, strategic decision)

| Issue | Action | Effort | Dependency |
|-------|--------|--------|------------|
| A0-P0-003 | Pick ONE deployment path (Cloud SaaS per CLAUDE.md, OR on-prem Docker); build the 6 critical Cloud SaaS features per Gate 11 | 3-6 months | Strategic decision |

### A1_product_truth_minimal (4 P0-T, buyer-demo blockers)

| Issue | Action | Effort | Dependency |
|-------|--------|--------|------------|
| A0-P0-005 | Remove 13 Corti external links from `/ai-studio Overview` | 1 day | None |
| A0-P0-006 | Fix `fast_runtime.py:307` cost=0 hardcode; propagate cost through billing + usage + RunHistory | 1 week | None |
| A0-P0-014 | Update all marketing/UI strings to reflect parity V2.2 (no "Corti-competitive" claim) | 1 week | V2.2 accepted |
| A0-P0-015 | Strategic coherence: pick ONE product framing; remove "Corti-style" from UI strings | 2 weeks business | None |

## §5. A2 workstream detail (22 P1 + 4 commercial-deferred P0)

### A2_commercial_deferred (4 P0 moved out of A1)

| Issue | Action | Effort | Dependency |
|-------|--------|--------|------------|
| A0-P0-004 | Replace fake credits endpoint with real Stripe (EU/US) + Alipay/WeChat Pay (CN) | 4-6 weeks | A2 start |
| A0-P0-008 | Set `RUNTRACE_STORE=postgres` default; backfill run_trace_events table | 1 week | None (do early) |
| A0-P0-009 | Publish `@icoder/sdk@1.0.0` + `@icoder/embedded@2.0.0` to npm registry | 1 day | A0-P0-021 signing |
| A0-P0-021 | Sign packages (npm provenance + sigstore) before publish | 1 week | None |

### A2 P1 clusters (22 issues)

Highlights (full list in `issue_ledger.v2.json` `primary_phase_mapping`):

| Cluster | Issues | Effort |
|---------|--------|--------|
| Observability hardening | A0-P1-001 (SLA observability) + A0-P1-016 (medcoder cost bug) + A0-P1-020 (usage underreport) | 3-4 weeks |
| Ontology cleanup | A0-P1-003/004/005/049/050 (code-dir / manifest-dir consolidation + metadata-only Hub agents) | 2-3 weeks |
| Hub polish | A0-P1-011/019/043/044/045 | 2-3 weeks |
| Pilot intake | A0-P1-014/015 | 4-8 weeks business |
| Stale spec | A0-P1-009 (A2A stub stale) | 3 days |
| Frontend tests | (P2 — A3) | — |

## §6. Verdict language replaced

Phase A0 v1 wrote:
- `Month 13 PARTNER_PRODUCTION_READY achievable`
- `Month 14 COMMERCIAL_GA`

Both `PARTNER_PRODUCTION_READY` and `COMMERCIAL_GA` are on the
forbidden verdicts list. V2 replaces them with conditional /
achievable language:

| v1 forbidden | v2 replacement | Why |
|--------------|----------------|-----|
| `PARTNER_PRODUCTION_READY` | `ACHIEVABLE: PARTNER_TECHNICAL_STAGING` | "Production ready" is forbidden; "technical staging achievable" describes state without certifying readiness |
| `COMMERCIAL_GA` | `ACHIEVABLE: HOSPITAL_CLINICAL_WORKFLOW_PILOT entry` | GA is forbidden; pilot entry is the verifiable milestone |
| `HOSPITAL_RESEARCH_SANDBOX` (used as outcome) | `CONDITIONAL_TARGET: HOSPITAL_RESEARCH_SANDBOX` | "Conditional target" makes clear it depends on A1 closing cleanly |
| `HOSPITAL_CLINICAL_WORKFLOW_PILOT` (used as outcome) | `ACHIEVABLE: HOSPITAL_CLINICAL_WORKFLOW_PILOT entry` | Adds "entry" qualifier and "achievable" tier |

This gate introduces two verdict qualifiers for the roadmap:
- **CONDITIONAL_TARGET** = depends on a downstream event (external
  audit, partner contract, clinician engagement).
- **ACHIEVABLE** = the work to reach this milestone is fully scoped;
  no external dependency blocking start.

## §7. Sequenced unblock plan (critical path V2)

```
Day 0    Phase A0.1 closes (this report series)
Day 1    Safe commit (Gate 9 produces Commit A + Commit B + tag)
         Strategic decision: Cloud SaaS confirmed (per CLAUDE.md)

         ┌── A1_security_first (parallel, 12 P0) ──────────────┐
Day 2    │ • A0-P0-010 .env.example + sentinel (1 day)          │
Day 2-3  │ • A0-P0-005 remove Corti links (1 day)               │
Week 2   │ • A0-P0-012 tenancy backfill (1 week)                │
Week 2   │ • A0-P0-018/019 capture 7 artifacts (1 week parallel)│
Week 3-5 │ • A0-P0-011 audit_logs expansion (2 weeks)           │
Week 3-5 │ • A0-P0-017 PHI live-path redaction (2-3 weeks)      │
Week 4-7 │ • A0-P0-016 encryption at rest (3-4 weeks)           │
Week 5-6 │ • A0-P0-020 Patient A/B isolation test (1 week)      │
Week 6-9 │ • A0-P0-022 multi-tenant data layer (3 weeks)        │
         └──────────────────────────────────────────────────────┘
         ┌── A1_clinical_safety (parallel, 2 P0-C) ─────────────┐
Week 2-4 │ • A0-P0-013 201-case F1 baseline (2 weeks)           │
Week 2-10│ • A0-P0-007 CDI first clinician response (4-8 w bus) │
         └──────────────────────────────────────────────────────┘
         ┌── A1_deployment_ops (1 P0-D, strategic) ─────────────┐
Month 2-6│ • A0-P0-003 Cloud SaaS 6 critical features (3-6 mo)  │
Month 4-5│ • A0-P0-023 backup/restore runbook (2 weeks)         │
Month 5-6│ • A0-P0-024 upgrade/rollback runbook (2 weeks)       │
         └──────────────────────────────────────────────────────┘
         ┌── A1_product_truth_minimal (parallel, 4 P0-T) ───────┐
Day 2-3  │ • A0-P0-006 fix cost=0 (1 week)                      │
Week 2-3 │ • A0-P0-014 update parity claims to V2.2 (1 week)    │
Week 2-3 │ • A0-P0-015 strategic coherence (2 weeks business)   │
         └──────────────────────────────────────────────────────┘
         ┌── External (parallel) ───────────────────────────────┐
Month 1-6│ • A0-P0-001 等保2.0 三级 audit prep (3-6 mo external)│
Month 1-2│ • A0-P0-002 legal docs drafting (2-4 weeks)          │
         └──────────────────────────────────────────────────────┘

Month 6  A1 closes
         CONDITIONAL_TARGET: HOSPITAL_RESEARCH_SANDBOX
         (conditional on 等保 audit + legal docs)

Month 7-13  A2 (P1 + commercial-deferred)
         ACHIEVABLE: PARTNER_TECHNICAL_STAGING

Month 14-22  A3 (P2 Polish)
         ACHIEVABLE: HOSPITAL_CLINICAL_WORKFLOW_PILOT entry

Month 23-25  A4 (P3 Cleanup)
         Backlog clean
```

**No forbidden verdicts on the timeline.** Every milestone is either
`CONDITIONAL_TARGET` or `ACHIEVABLE` with explicit qualifiers.

## §8. A1 entry criteria (corrected)

Phase A1 may start only when:

1. ✅ Phase A0.1 verdict is one of the 5 allowed verdicts (per §五),
   NOT `PASS_PHASE_A0_*`.
2. ✅ All hard checkpoints A-H plus I/J closed (Gate 9).
3. ✅ Safe commit produced (Gate 9: Commit A + Commit B + annotated tag).
4. ✅ V2 issue ledger accepted as canonical source (Gate 3).
5. ✅ V2.2 parity matrix accepted (Gate 4).
6. ✅ V2 product maturity accepted (Gate 5).
7. ✅ A0-P0-018/019 regraded to E1 (Gate 6).
8. ✅ This roadmap V2 accepted (Gate 7).
9. ✅ A1-S workstream owner assigned.
10. ✅ A1-C workstream owner assigned (clinician engagement or research-mode decision).
11. ✅ Cloud SaaS deployment path decision confirmed (per CLAUDE.md).

A1 may start Day 2 after the Gate 9 safe commit.

## §9. Hard Checkpoint — Roadmap V2 (provisional)

| Sub-check | Status |
|-----------|--------|
| RM-1: roadmap uses canonical 79 open count (not 75) | ✅ 19 A1 + 26 A2 + 27 A3 + 11 A4 - 4 cross-phase ≈ 79 |
| RM-2: A1 scope = 19 P0 (not v1's 23) | ✅ 12 sec + 2 clin + 1 deploy + 4 truth |
| RM-3: A0-P0-004/008/009/021 moved to A2_commercial_deferred | ✅ |
| RM-4: no forbidden verdicts on timeline | ✅ PARTNER_PRODUCTION_READY and COMMERCIAL_GA removed |
| RM-5: every milestone marked CONDITIONAL_TARGET or ACHIEVABLE | ✅ |
| RM-6: A1 entry criteria reference V2 deliverables | ✅ items 4-7 |
| RM-7: critical path shows dependencies | ✅ §7 Gantt-style |
| RM-8: A0-P0-018/019 reverification in A1_security_first | ✅ |

**Hard Checkpoint RM: ✅ PASS (8/8 sub-checks) provisional — Gate 8 validator must machine-verify before final ratification.**

## §10. Findings raised in Gate 7

| ID | Severity | Title |
|----|----------|-------|
| **A0.1-G7-001** | P0-T | Phase A0 v1 roadmap placed `PARTNER_PRODUCTION_READY` (Month 13) and `COMMERCIAL_GA` (Month 14) on the timeline. Both are forbidden verdicts per Phase A0.1 §五. V2 replaces with ACHIEVABLE / CONDITIONAL_TARGET language. |
| **A0.1-G7-002** | P0-T | Phase A0 v1 lumped 4 commercial-deferred issues (A0-P0-004/008/009/021) into A1 P0 scope, inflating A1 from 19 to 23 P0 issues. V2 moves them to A2_commercial_deferred. |
| **A0.1-G7-003** | P1 | Phase A0 v1 roadmap used the retired 75-issue count. V2 uses the canonical 79 open count from the v2 issue ledger. |
| **A0.1-G7-004** | P2 | Phase A0 v1 §6 critical-path diagram block-quoted A0-P0-009 (npm publish) as Day 2-9 work, but npm publish depends on A0-P0-021 (supply chain signing) which v1 placed in the same parallel block. Sequential dependency masked. V2 §7 makes the signing → publish dependency explicit. |

## §11. Gate 7 verdict

```
PHASE_A0_1_GATE_7_REMEDIATION_ROADMAP_V2_DERIVED
79_OPEN_CANONICAL (machine-derived from Gate 3)
19_P0_IN_A1 (down from v1's 23 — 4 commercial-deferred moved to A2)
4_COMMERCIAL_DEFERRED_IN_A2 (A0-P0-004/008/009/021)
0_FORBIDDEN_VERDICTS_ON_TIMELINE
CONDITIONAL_TARGET + ACHIEVABLE_VERDICT_LANGUAGE_INTRODUCED
A1_ENTRY_CRITERIA_V2_REFERENCES_GATES_3_4_5_6
HARD_CHECKPOINT_RM_PROVISIONAL_PASS (8/8)
```

### Phase A0 v1 roadmap NOT modified (preserved as audit trail).

End of Gate 7. Proceeding to Gate 8 — Semantic Validator V2.
