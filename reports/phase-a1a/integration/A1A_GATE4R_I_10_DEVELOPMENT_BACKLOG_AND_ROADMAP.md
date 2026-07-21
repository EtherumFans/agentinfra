# Phase A1A Gate 4R-I.10 — Development Backlog + Roadmap

**Date**: 2026-07-21
**Branch**: `phase-a1a/emergency-containment` at `a2a1136` (post Gate 4R-I.9)
**Predecessor**: Gate 4R-I.9 (`a2a1136` release tier verdicts)
**Successor**: Gate 4R-I.11 (final verdict + closure notice)

Charter §14 requires promoting all findings into a P0/P1/P2/P3 issue
ledger with dependency ordering and effort estimates. This sub-gate
consolidates 4R-I.3..4R-I.9 findings into the canonical development
backlog.

## §1. Issue grading scale

| Grade | Meaning | SLO |
|---|---|---|
| P0 | Blocks MVP release | Resolve before MVP ship |
| P1 | Blocks Controlled Pilot release | Resolve before Pilot ship |
| P2 | Blocks GA release | Resolve before GA ship |
| P3 | Quality / tech debt; does not block release | Schedule freely |

## §2. P0 — MVP-blocking issues

| ID | Title | Source | Effort | Depends on |
|---|---|---|---|---|
| P0-001 | Encrypt 5 direct PHI identifier columns (`users.username/email/full_name`, `encounters.patient_id`, `cdi_cases.patient_ref`) | 4R-I.8 §2.2 | 1 day | — |
| P0-002 | Integrate real STT provider (Alibaba Cloud / Tencent / iFlytek) | 4R-I.7 §6, 4R-I.6 §5.1 | 1 week | — |
| P0-003 | Wire provider egress audit emit on every LLMGateway call | 4R-I.8 §4.2 | 2 days | — |
| P0-004 | Close provider egress hot-path coverage gaps (non-LLMGateway bypass paths) | 4R-I.8 §4.2, §8 P2-10 | 3 days | P0-003 |

**P0 total effort**: ~2-3 weeks.

## §3. P1 — Controlled-Pilot-blocking issues

| ID | Title | Source | Effort | Depends on |
|---|---|---|---|---|
| P1-001 | Encrypt ~25 P1 quasi-identifier PHI columns | 4R-I.8 §2.2 | 3 days | P0-001 |
| P1-002 | KMS / HSM integration | 4R-I.8 §3.2 | 1 week | — |
| P1-003 | Per-tenant encryption keys | 4R-I.8 §3.2 | 1 week | P1-002 |
| P1-004 | Explicit unknown-provider fail-closed | 4R-I.8 §5.2 | 1 day | — |
| P1-005 | Provider egress audit emit | 4R-I.8 §4.2 | (same as P0-003) | P0-003 |
| P1-006 | Clinical quality benchmark on 201 gold cases (finish Phase 5 Track H) | 4R-I.9 §4.1 | 2 weeks | — |
| P1-007 | Monitoring + alerting infrastructure | 4R-I.9 §4.1 | 1 week | — |
| P1-008 | Backup/restore runbook | 4R-I.9 §4.1 | 3 days | — |
| P1-009 | Incident response procedure | 4R-I.9 §4.1 | 3 days | — |
| P1-010 | Support ticket workflow | 4R-I.9 §4.1 | 3 days | — |
| P1-011 | Legal/compliance review (China PIPL) | 4R-I.9 §4.1 | 2 weeks (external) | — |

**P1 total effort**: ~3-4 months (parallelizable).

## §4. P2 — GA-blocking issues

| ID | Title | Source | Effort | Depends on |
|---|---|---|---|---|
| P2-001 | Retention auto-scheduling (cron / K8s CronJob) | 4R-I.8 §7 | 2 days | — |
| P2-002 | Ciphertext → tenant binding enforcement | 4R-I.8 §3.2 | 1 week | P1-003 |
| P2-003 | LLM bypass paths gating | 4R-I.8 §4.2 | 1 week | P0-004 |
| P2-004 | PostgreSQL migration verification in CI | 4R-I.3 §3 cat 10 | 3 days | — |
| P2-005 | Multi-instance horizontal scaling | 4R-I.9 §5.1 | 3 weeks | — |
| P2-006 | Region failover | 4R-I.9 §5.1 | 2 weeks | P2-005 |
| P2-007 | SLO definition and adherence | 4R-I.9 §5.1 | 1 week | P1-007 |
| P2-008 | Support process with SLA | 4R-I.9 §5.1 | 1 week | P1-010 |
| P2-009 | SDK public release (`@icoder/sdk@1.0.0` stable) | 4R-I.9 §5.1 | 2 weeks | — |
| P2-010 | Public documentation site | 4R-I.9 §5.1 | 2 weeks | — |
| P2-011 | Billing system production-grade | 4R-I.9 §5.1 | 2 weeks | — |
| P2-012 | Compliance evidence package | 4R-I.9 §5.1 | 2 weeks | P1-011 |
| P2-013 | Real hospital customer acceptance | 4R-I.9 §5.1 | external | P1-* |

**P2 total effort**: ~3-4 months (after Pilot complete).

## §5. P3 — Quality / tech debt

| ID | Title | Source | Effort |
|---|---|---|---|
| P3-001 | Full-suite Windows asyncio hang (TestClient startup) | 4R-I.3 §5.1 | 3 days |
| P3-002 | Gate 4.7 retention test state-pollution hermeticity (GATE4R_REG_008, 2 nodes) | 4R-I.3 §5.2 | 1 day |
| P3-003 | Migration direct invocation MemoryError on Windows | 4R-I.3 §5.3 | 2 days |
| P3-004 | OpenAPI / frontend SDK regeneration CI check | 4R-I.4 §3.2 | 1 day |
| P3-005 | Phase A0 / A0.1 historical report index promotion | 4R-I.2 §2 | 2 days |
| P3-006 | Legacy root-level `audit_*.xml` cleanup (after evidence-freeze canonicalization) | 4R-I.2 §3 | 0.5 day |
| P3-007 | Frontend bundle size chunking (currently 704 KB main chunk) | 4R-I.4 §1 (build warning) | 2 days |
| P3-008 | Add explicit OpenAPI test that path count matches live app | 4R-I.4 §3.2 | 0.5 day |

**P3 total effort**: ~2 weeks.

## §6. Dependency graph

```
P0-001 ──┐
          ├─→ P1-001 ──→ P2-002
P1-002 ──→ P1-003 ────────┘

P0-003 ──→ P0-004 ──→ P2-003
         └─→ P1-005 (same)

P0-002 (STT integration) — independent

P1-006 (clinical quality) — independent
P1-007 (monitoring) ──→ P2-007 (SLO)
P1-008 (backup) — independent
P1-009 (IR) — independent
P1-010 (support) ──→ P2-008 (SLA)
P1-011 (PIPL) ──→ P2-012 (compliance evidence)

P2-005 (scaling) ──→ P2-006 (region failover)
```

## §7. Recommended sequencing

### Phase A1B (MVP path, ~2-3 weeks)

1. P0-001 Encrypt direct PHI identifiers (1 day)
2. P0-003 + P0-004 Provider egress audit + hot-path coverage (1 week)
3. P0-002 Real STT provider integration (1 week)
4. Regression: re-run 77-node 4R suite + full-suite on Linux CI
5. MVP ship

### Phase A1C (Controlled Pilot path, ~3-4 months)

1. P1-001 Quasi-identifier encryption (3 days)
2. P1-002 + P1-003 KMS + per-tenant keys (2 weeks)
3. P1-004 Explicit unknown-provider fail-closed (1 day)
4. P1-006 Clinical quality benchmark (2 weeks)
5. P1-007..P1-010 Monitoring/backup/IR/support (3 weeks)
6. P1-011 PIPL review (2 weeks, external)
7. Controlled Pilot ship

### Phase A2 (GA path, ~12-18 months)

1. P2-001 Retention auto-scheduling
2. P2-002 Ciphertext binding
3. P2-003 LLM bypass gating
4. P2-004 PostgreSQL CI verification
5. P2-005 + P2-006 Scaling + region failover
6. P2-007 SLO definition
7. P2-008 SLA process
8. P2-009 SDK stable release
9. P2-010 Public docs site
10. P2-011 Billing production-grade
11. P2-012 Compliance evidence package
12. P2-013 Hospital acceptance

### Phase A0.2 / debt liquidation (parallel)

- P3-001 through P3-008: pick up in slack cycles.

## §8. Effort summary

| Phase | Effort estimate | Calendar time (with parallelism) |
|---|---|---|
| A1B (MVP path) | ~3 person-weeks | 2-3 weeks |
| A1C (Pilot path) | ~3 person-months | 3-4 months |
| A2 (GA path) | ~12 person-months | 12-18 months |
| A0.2 (P3 debt) | ~2 person-weeks | parallel |
| **Total to GA** | **~18 person-months** | **~18 months** |

## §9. Forbidden list for this sub-gate

| Forbidden action | Status |
|---|---|
| Issue a verdict beyond FILED | NOT DONE ✓ |
| Schedule clinical prompt changes | NOT DONE ✓ (no clinical prompts touched) |
| Touch master / origin/master | NOT DONE ✓ |
| Push / PR | NOT DONE ✓ |

## §10. Provisional verdict

```
PASS_A1A_GATE4R_I_10_DEVELOPMENT_BACKLOG_AND_ROADMAP_FILED
P0_COUNT = 4 issues
P1_COUNT = 11 issues
P2_COUNT = 13 issues
P3_COUNT = 8 issues
TOTAL = 36 issues
EFFORT_TO_GA = ~18 person-months / ~18 calendar months
```

Tier: FILED (not VERIFIED). Backlog is the canonical input to the
release planning process; it does NOT assert any work is complete.

## §11. Next

Gate 4R-I.11 — final verdict + closure notice:

- Aggregate all sub-gate verdicts
- Issue the single allowed final verdict
  `PASS_A1A_GATE4R_INTEGRATION_REPOSITORY_RECONCILIATION_AND_PRODUCT_GAP_AUDIT_FILED`
- Confirm forbidden verdicts and forbidden actions respected throughout
- Output the closure notice
