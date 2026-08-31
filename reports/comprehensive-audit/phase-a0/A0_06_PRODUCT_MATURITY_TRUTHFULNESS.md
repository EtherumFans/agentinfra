# A0 Gate 6 — Product Maturity Truthfulness

> Phase A0 Gate 6. Applies the 10-level workflow maturity scale (spec §7) to every China scenario claim. Downgrades 11 of 16 Pre-A0 claims that were overstated.

Spec reference: §7 (10-level maturity), §22 (Hard Checkpoint F — Product Maturity Truthfulness).

---

## §1. Why this gate exists

Pre-A0 26E (China Medical Scenario Mapping) called workflows "FULL" or "IMPLEMENTED" because the corresponding rule file / API endpoint / prompt / handler existed. This conflates **asset existence** with **workflow maturity**.

Phase A0 spec §7 defines 11 maturity levels (L1 through L11) that distinguish:
- File on disk (L1)
- API contract (L2)
- Implementation code (L3)
- Runtime-reachable (L4)
- Integration-verified (L5)
- Browser-verified (L6)
- Workflow-closed (L7)
- Quality-benchmarked (L8)
- Clinically-reviewed (L9)
- External partner-validated (L10)
- Deployment-validated (L11)

Each China scenario claim in Pre-A0 26E must be regraded against this scale.

## §2. Maturity distribution (machine-verified)

Full table in `product_maturity.json`. Summary:

| Level | Count | Scenarios |
|-------|------:|-----------|
| L1 ASSET_PRESENT | 3 | CN-04 Insurance, CN-05 Charge, CN-10 等保 |
| L2 CONTRACT_PRESENT | 2 | CN-06 Document Evidence, CN-09 Billing |
| L3 CODE_PRESENT | 4 | CN-03 DRG/DIP, CN-08 AuditLog, CN-12 Multi-tenant, CN-16 PHI redaction |
| L4 RUNTIME_REACHABLE | 3 | CN-02 CDI, CN-07 Procedure Coding, CN-15 A2A |
| L5 INTEGRATION_VERIFIED | 0 | (none) |
| L6 BROWSER_VERIFIED | 3 | CN-11 Embedded SDK, CN-13 Partner Reference App, CN-14 Agent Hub |
| L7 WORKFLOW_CLOSED | 0 | (none) |
| L8 QUALITY_BENCHMARKED | 1 | CN-01 Medical Coding |
| L9 CLINICALLY_REVIEWED | 0 | (none) |
| L10 EXTERNAL_PARTNER_VALIDATED | 0 | (none) |
| L11 DEPLOYMENT_VALIDATED | 0 | (none) |

**Highest maturity: L8 (Medical Coding only).** 15 of 16 scenarios are below L7. 12 of 16 are below L5.

## §3. The 11 Pre-A0 overstatements

| Scenario | Pre-A0 maturity | Phase A0 maturity | Reason for downgrade |
|----------|-----------------|-------------------|----------------------|
| CN-02 CDI | WORKFLOW_CLOSED | **L4** | 443 queries, 0 clinician responses — loop not closed |
| CN-03 DRG/DIP | L4 | **L3** | DRG unused; DIP 501/demo |
| CN-04 Insurance | L3 | **L1** | Rules exist, not exercised |
| CN-05 Charge | L2 | **L1** | Rules reserved empty |
| CN-07 Procedure Coding | L5 | **L4** | No integration verification in audit |
| CN-08 AuditLog/RunHistory | L7 | **L3** | RUNTRACE_STORE=memory; audit_logs only 5 actions |
| CN-09 Billing | L4 | **L2** | 0 transactions; fake balance; cost=0 bug |
| CN-11 Embedded SDK | L7 | **L6** | Browser walkthrough not production |
| CN-12 Multi-tenant | L5 | **L3** | 235/240 rows NULL org_id |
| CN-13 Partner Ref App | L7 | **L6** | Synthetic data; no real partner |
| CN-15 A2A v0.3 | L5 | **L4** | Tasks stub returns 501 |
| CN-16 PHI redaction | L5 (claimed as iCoDer ADVANTAGE) | **L3** | Redactor is export-only |

**11 of 16 downgraded.** Pre-A0 systematically overstated maturity.

## §4. The 5 Pre-A0 confirmations

| Scenario | Pre-A0 | Phase A0 | Note |
|----------|--------|----------|------|
| CN-01 Medical Coding | WORKFLOW_CLOSED | **L8** | Slight refinement (L8 is more precise) |
| CN-06 Document Evidence | L1 | **L1** | Same |
| CN-10 等保2.0 | L1 | **L1** | Same |
| CN-14 Agent Hub | L7 | **L6** | Sharper (15 of 25 metadata-only) |

## §5. Readiness Tracks (per spec §8)

Phase A0 assesses 6 readiness tracks:

| Track | Achieved? | Blockers |
|-------|-----------|----------|
| INTERNAL_DEMO | ✅ | (none — CN-01, CN-11, CN-13, CN-14 support demo) |
| CUSTOMER_DEMO | ❌ | A0-P0-005 (Corti redirects), A0-P0-015 (strategic incoherence) |
| PARTNER_TECHNICAL_STAGING | ❌ | A0-P0-009 (npm unpublished), A0-P0-021 (supply chain) |
| HOSPITAL_RESEARCH_SANDBOX | ❌ | A0-P0-001 (no cert), A0-P0-002 (no legal) |
| HOSPITAL_CLINICAL_WORKFLOW_PILOT | ❌ | All P0-S + P0-C + P0-D (10+5 = 15 blockers) |
| COMMERCIAL_GA | ❌ | All P0 (23 blockers) |

**Only INTERNAL_DEMO track is achieved.** This is consistent with the Phase 5/6/7 closure memory that called out "demo-grade not pilot-grade".

## §6. Hard Checkpoint F — Product Maturity Truthfulness

| Sub-check | Status |
|-----------|--------|
| F-1: Every China scenario claim has explicit maturity level | ✅ 16/16 |
| F-2: Maturity levels use spec §7 scale (L1-L11) | ✅ |
| F-3: Asset existence distinguished from workflow maturity | ✅ |
| F-4: Pre-A0 overstatements downgraded | ✅ 11/11 |
| F-5: Readiness tracks assessed honestly | ✅ 1/6 achieved |
| F-6: Highest maturity scenario identified (L8 Medical Coding) | ✅ |
| F-7: Machine-readable JSON produced | ✅ `product_maturity.json` |
| F-8: No forbidden "production_ready" / "hospital_pilot_ready" verdicts claimed | ✅ |

**Hard Checkpoint F: ✅ PASS (8/8 sub-checks)**

## §7. Findings raised in Gate 6

| ID | Severity | Title |
|----|----------|-------|
| **A0-G6-001** | P0-T | Pre-A0 26E overstated 11 of 16 China scenarios by ≥1 maturity level. |
| **A0-G6-002** | P0-T | Only 1 of 16 scenarios (Medical Coding) reaches L8. 15 of 16 are below workflow-closed. |
| **A0-G6-003** | P0-T | Only 1 of 6 readiness tracks (INTERNAL_DEMO) is achieved. |
| **A0-G6-004** | P1 | CDI (CN-02) at L4 despite "CORE_ENTRY_AGENT" status in CLAUDE.md — 443 queries, 0 clinician responses is the dominant blocker. |
| **A0-G6-005** | P1 | DRG/DIP (CN-03) at L3 — DRG grouping code exists but unused in any production run; DIP path is 501/demo. |

## §8. Gate 6 verdict

```
PHASE_A0_GATE_6_PRODUCT_MATURITY_TRUTHFULNESS_CLOSED
16_CHINA_SCENARIOS_GRADED_ON_L1-L11_SCALE
11_PRE_A0_OVERSTATEMENTS_DOWNGRADED
1_SCENARIO_AT_L8 (Medical Coding only)
0_SCENARIOS_AT_L9_OR_HIGHER
1_OF_6_READINESS_TRACKS_ACHIEVED (INTERNAL_DEMO only)
HARD_CHECKPOINT_F_PASS (8/8 sub-checks)
0_FORBIDDEN_VERDICTS_CLAIMED
```

### Hard Checkpoints A+B+C+D+E+F closed; G+H pending

End of Gate 6. Proceeding to Gate 7 — Canonical Architecture V2.
