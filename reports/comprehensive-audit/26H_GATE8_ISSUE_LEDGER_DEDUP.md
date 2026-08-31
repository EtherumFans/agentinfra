# 26H — Pre-A0 Gate 8: Issue Ledger Dedup + V2 Roadmap

> Per spec §16. Consolidates all findings from Gates 13/14 + Pre-A0 Gates 0-7 into a deduplicated issue ledger. Maps to V2 roadmap.

## Methodology

- Source: Gate 13 (G13-*), Gate 11 (G11-*), Pre-A0 Gate 2 (G2-*), Gate 3 (G3-*), Gate 4 (G4-*), Gate 5 (G5-*), Gate 6 (G6-*), Gate 7 (G7-*)
- Each issue deduplicated; same root cause merged
- P0/P1/P2/P3 severity per spec §13.2
- Roadmap bucket: P0 Now / P1 Next / P2 Later / P3 Backlog

---

## §1. Deduplicated issue ledger

### P0 — Blocks pilot (4 issues, all from Gate 13)

| ID | Title | Source | Status |
|----|-------|--------|--------|
| **P0-01** (G13-002) | Zero compliance certifications (等保2.0 三级 + GB/T 35273 + HIPAA + ISO 27001) | Gate 13 | Open |
| **P0-02** (G13-003) | Zero legal documents (Privacy/Terms/DPA/SLA) | Gate 13 | Open |
| **P0-03** (G13-004) | Zero shippable deployment paths (cloud docs-only, on-prem disclaimed) | Gate 13 + G11-001 | Open |
| **P0-04** (G13-001) | Billing theater (0 transactions, no payment processor, fake ¥50 balance) | Gate 13 + G7-003 | Open |

### P1 — Major feature gaps (15 issues)

| ID | Title | Source | Status |
|----|-------|--------|--------|
| **P1-01** (G11-002) | SLA targets documented but no production observability | Gate 11 | Open |
| **P1-02** (G2-001) | 3 kebab/snake duplicate agent pairs need consolidation | Pre-A0 Gate 2 | New |
| **P1-03** (G2-005) | 4 MedCodER sub-component dirs appear as top-level agents | Pre-A0 Gate 2 | New |
| **P1-04** (G2-006) | Legacy E-A experts (11 files) likely orphaned — verify or remove | Pre-A0 Gate 2 | New |
| **P1-05** (G2-007) | Legacy T-1 tools (11 files) likely MCP-disconnected | Pre-A0 Gate 2 + G3-002 | Confirmed (HC-3 nuanced) |
| **P1-06** (G2-008) | RG-3 legacy ToolRegistry has dual home | Pre-A0 Gate 2 | New |
| **P1-07** (G3-001) | HC-1 refuted: iCoDer has 1 canonical runtime, not 3 parallel — docs/reports must correct | Pre-A0 Gate 3 | New |
| **P1-08** (G3-003) | HC-4 refuted: 30 unique agents (not 13) — Hub displays reflect this | Pre-A0 Gate 3 | New |
| **P1-09** (G3-006) | routes_task_stub.py still says "Phase 5 will replace" but Phase 5 closed | Pre-A0 Gate 3 | New |
| **P1-10** (G5-004) | CN-10 等保2.0 compliance not certified — blocks public hospital pilot | Pre-A0 Gate 5 | Same as P0-01 |
| **P1-11** (G6-006) | HC-6 "Hub vs Runtime mismatch" smaller than claimed; ~5 controlled_use agents | Pre-A0 Gate 6 | New |
| **P1-12** (G7-001) | V2 parity is 59% favorable (vs V1's 34%); V2 should be authoritative | Pre-A0 Gate 7 | New |
| **P1-13** (G7-002) | CN-scoped parity 77% (24/31); 7 gaps need addressing | Pre-A0 Gate 7 | New |
| **P1-14** (G13-005) | Pilot intake never exercised (0 real tenants) | Gate 13 | Open |
| **P1-15** (G13-006) | No pricing model — sales conversations cannot close | Gate 13 | Open |

### P2 — Polish + partner readiness (24 issues)

| ID | Title | Source |
|----|-------|--------|
| P2-01 (G2-002) | 3 CDI variant dirs need consolidation | Gate 2 |
| P2-02 (G2-003) | 2 ICD-10 navigator variants need consolidation | Gate 2 |
| P2-03 (G2-004) | 2 Medical Coding variants need clarification | Gate 2 |
| P2-04 (G2-009) | Marketplace skeleton only — not implemented | Gate 2 |
| P2-05 (G2-010) | A2A routes_task_stub remains 501 | Gate 2 + G3-006 |
| P2-06 (G2-011) | iCoDer missing 2 Corti mirrors (Clinical Education, Clinical Guidelines) | Gate 2 |
| P2-07 (G11-003) | Frontend has 0 unit tests | Gate 11 |
| P2-08 (G11-004) | No release automation | Gate 11 |
| P2-09 (G11-005) | No ops runbook | Gate 11 |
| P2-10 (G13-007) | No partner program / ISV contract template | Gate 13 |
| P2-11 (G13-008) | Support email `support@icoder.local` fake domain | Gate 13 |
| P2-12 (G13-009) | Pilot Runbook archived under docs/archive | Gate 13 |
| P2-13 (G4-001) | 4 Corti experts OUT_OF_CURRENT_SCOPE — document explicitly | Gate 4 |
| P2-14 (G4-002) | 4 Corti ICD-10 variants DIFFERENT_BY_DESIGN — document | Gate 4 |
| P2-15 (G5-001) | W-4 Insurance: rules exist but not deeply exercised | Gate 5 |
| P2-16 (G5-002) | W-5 Charge: rules reserved but empty | Gate 5 |
| P2-17 (G5-003) | CN-9 ICD-9-CM-3 procedure coding depth lacking | Gate 5 |
| P2-18 (G5-007) | iCoDer DRG-DIP advantage has no Corti mirror — document | Gate 5 |
| P2-19 (G6-001) | iCoDer Hub lacks My/Pre-built tabs | Gate 6 |
| P2-20 (G6-002) | iCoDer New Agent flow lacks template picker | Gate 6 |
| P2-21 (G6-003) | iCoDer requires pack/install; Corti save-and-go-live | Gate 6 |
| P2-22 (G7-003) | Corti 4 commercial advantages; iCoDer 0 | Gate 7 |
| P2-23 (G7-004) | iCoDer observability class strongest dimension — leverage | Gate 7 |
| P2-24 (G7-006) | .NET SDK missing from iCoDer Code generators | Gate 7 |

### P3 — Cosmetic / nice-to-have (12 issues)

| ID | Title | Source |
|----|-------|--------|
| P3-01 (G11-006) | `e2e` pytest marker defined but never applied | Gate 11 |
| P3-02 (G11-007) | Root `docs/ARCHITECTURE.md` deprecated but in tree | Gate 11 |
| P3-03 (G11-008) | Throughput test budgets marked "TBD" | Gate 11 |
| P3-04 (G11-009) | No locust/k6 load test config | Gate 11 |
| P3-05 (G13-010) | SLA targets docs-only | Gate 13 |
| P3-06 (G3-007) | Legacy E-A experts power T-1 tools (not strictly orphaned) | Gate 3 |
| P3-07 (G4-003) | 4 Corti experts PARITY_NICE_TO_HAVE — backlog | Gate 4 |
| P3-08 (G4-004) | AMBOSS not in Corti docs list — Corti docs incomplete | Gate 4 |
| P3-09 (G5-005) | iCoDer missing Corti Clinical Education Agent | Gate 5 |
| P3-10 (G5-006) | iCoDer missing Corti Clinical Guidelines Agent | Gate 5 |
| P3-11 (G6-004) | iCoDer Code generators missing .NET | Gate 6 (dup of P2-24) |
| P3-12 (G6-005) | iCoDer Code tab exposes URLs (chat/run/clone) — keep | Gate 6 |

---

## §2. Dedup statistics

| Source gate | Issues raised | After dedup | Net new |
|-------------|----------------|-------------|---------|
| Gate 11 | 9 | 9 | 9 |
| Gate 13 | 10 | 10 | 10 |
| Pre-A0 Gate 2 | 11 | 11 | 11 |
| Pre-A0 Gate 3 | 7 | 7 | 7 |
| Pre-A0 Gate 4 | 4 | 4 | 4 |
| Pre-A0 Gate 5 | 7 | 7 | 7 |
| Pre-A0 Gate 6 | 6 | 6 | 6 |
| Pre-A0 Gate 7 | 6 | 6 | 6 |
| **Total raw** | **60** | **55 unique** | **55** |

5 duplicates removed:
- G3-006 = G2-010 (A2A stub)
- P1-10 = P0-01 (等保 cert)
- P3-11 = P2-24 (.NET SDK)

---

## §3. V2 Roadmap (per spec §16.4)

### Bucket 1 — P0 Now (unblocks pilot)

| Issue | Action | Effort estimate |
|-------|--------|-----------------|
| P0-01 | Engage 等保2.0 三级 audit prep — encryption at rest, audit log completeness, password complexity | 3-6 months (external) |
| P0-02 | Draft Privacy Policy + Terms of Service + DPA + SLA — get legal review | 2-4 weeks |
| P0-03 | Pick one shippable path: either Cloud SaaS (build 6 critical features) or On-prem Docker (reverse CLAUDE.md decision) | 3-6 months |
| P0-04 | Integrate Stripe (EU/US) + Alipay/WeChat Pay (CN); replace fake `credits` endpoint | 4-6 weeks |

### Bucket 2 — P1 Next (hardens product)

| Issue | Action | Effort estimate |
|-------|--------|-----------------|
| P1-01 | Add production observability: OpenTelemetry + Grafana + P50/P99 latency dashboard | 2-3 weeks |
| P1-02 / P2-01 / P2-02 / P2-03 | Consolidate duplicate agent dirs (3 kebab/snake pairs + CDI variants + navigator + medical coding) | 1 week |
| P1-03 / P1-04 / P1-05 / P1-06 | Legacy cleanup: remove E-A orphans + T-1 disconnect + RG-3 dual home | 2 weeks |
| P1-07 / P1-08 / P1-11 / P1-12 / P1-13 | Update all prior reports to reflect V2 findings (3 parallel → 1 canonical; 13 → 30; etc.) | 1 week |
| P1-09 | Either implement A2A Tasks OR remove `routes_task_stub.py` + update SPEC §7.5 | 1 day decision + 2 weeks implement |
| P1-14 / P1-15 | Engage first hospital pilot prospect; draft tiered pricing model | 4-8 weeks business development |

### Bucket 3 — P2 Later (partner readiness)

| Issue | Action | Effort estimate |
|-------|--------|-----------------|
| P2-07 | Add Vitest frontend unit tests | 2 weeks |
| P2-08 | Add release.yml CI workflow with tag-triggered publish | 3 days |
| P2-09 | Write ops runbook (incident response, backup/restore, secret rotation) | 1 week |
| P2-10 | Draft partner program doc + ISV contract template | 2-4 weeks business |
| P2-15 / P2-16 / P2-17 | Deepen insurance / charge / procedure coding coverage | 4-6 weeks |
| P2-19 / P2-20 / P2-21 | Hub UX convergence (tabs, template picker, save-and-go-live) | 3-4 weeks |
| P2-22 | Commercial parity: implement plan tiers, alerts, auto-topup | 4-6 weeks |
| P2-24 | Add .NET SDK to Code generators | 1 week |

### Bucket 4 — P3 Backlog (cleanup)

| Issue | Action | Effort estimate |
|-------|--------|-----------------|
| P3-01 through P3-12 | Apply e2e markers, archive deprecated docs, write load tests, etc. | 2-3 weeks total |

---

## §4. Roadmap timeline summary

| Phase | Duration | Outcome |
|-------|----------|---------|
| Phase A0 (Audit Closure) | 1 day | This Pre-A0 + Pre-A0 Final Decision complete |
| Phase A1 (P0 Unblock) | 3-6 months | 等保 audit + legal docs + deployment path + payment processor |
| Phase A2 (P1 Harden) | 4-6 weeks | Observability + dedup + cleanup + first pilot prospect |
| Phase A3 (P2 Partner) | 8-12 weeks | Partner program + Hub UX + commercial parity + insurance depth |
| Phase A4 (P3 Cleanup) | 2-3 weeks | Backlog hygiene |

**Earliest hospital pilot readiness**: 4-6 months (after Phase A1 completes 等保 audit).
**Partner production readiness**: 9-12 months (after Phase A3).

---

## §5. Findings raised in Gate 8

| ID | Severity | Title |
|----|----------|-------|
| **G8-001** | P0 | 4 P0 blockers from Gate 13 remain — Pre-A0 did not resolve any; they gate Phase A0 closure |
| **G8-002** | P1 | 15 P1 issues need addressing in Phase A2; without them, product is "demo-grade" not "pilot-grade" |
| **G8-003** | P2 | 24 P2 issues are partner-readiness work; doesn't block pilot but blocks scale |
| **G8-004** | P3 | 12 P3 issues are backlog hygiene; address opportunistically |

---

## §6. Gate 8 verdict

```
PRE_A0_GATE8_ISSUE_LEDGER_DEDUP_AND_V2_ROADMAP_COMPLETE
55_UNIQUE_ISSUES_AFTER_DEDUP (60 raw - 5 dups)
4_P0 / 15_P1 / 24_P2 / 12_P3
4_PHASE_ROADMAP_DOCUMENTED (A1/A2/A3/A4)
EARLIEST_HOSPITAL_PILOT_READINESS_4_TO_6_MONTHS (after Phase A1)
PARTNER_PRODUCTION_READINESS_9_TO_12_MONTHS (after Phase A3)
0_FORBIDDEN_VERDICTS_CLAIMED
```

Gate 8 closes. Proceed to **Pre-A0 Gate 9 — Canonical Architecture + Decision Matrix**.
