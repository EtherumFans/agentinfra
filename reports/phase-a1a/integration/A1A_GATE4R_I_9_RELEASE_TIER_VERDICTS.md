# Phase A1A Gate 4R-I.9 — Release Tier Verdicts

**Date**: 2026-07-21
**Branch**: `phase-a1a/emergency-containment` at `4fda130` (post Gate 4R-I.8)
**Predecessor**: Gate 4R-I.8 (`4fda130` security re-audit)
**Successor**: Gate 4R-I.10 (development backlog + roadmap)

Charter §13 requires computing three release-tier verdicts:
`ICODER_MVP_READINESS`, `ICODER_CONTROLLED_PILOT_READINESS`,
`ICODER_GA_READINESS`. Each is one of: `NOT_READY`, `BLOCKED`,
`READY_WITH_GAPS`, `READY`. This sub-gate aggregates evidence from
4R-I.3 through 4R-I.8 into the consolidated tier verdicts.

## §1. Tier definitions (charter §13)

| Tier | Scope |
|---|---|
| MVP | Minimum Viable Product — single hospital, single region (CN), synthetic + real DeepSeek, no production PHI |
| Controlled Pilot | 1-3 pilot hospitals, real PHI, controlled consent, on-call coverage during business hours |
| GA | General Availability — multi-region, multi-tenant, self-service sign-up, 24/7 ops |

## §2. Evidence aggregation

| Gate | Surface verified | Surface gap |
|---|---|---|
| 4R-I.3 | 77/77 4R regression PASS post-merge; no NEW delta | full-suite Windows asyncio hang (pre-existing) |
| 4R-I.5 | 8 Corti public-doc snapshots captured (395 entries) | trust.corti.ai + compliance.md HTTP 403 |
| 4R-I.6 | 234 backend routes audited | 51% IMPLEMENTED_BUT_PARTIALLY_TESTED; 6% BLOCKED_BY_EXTERNAL_DEPENDENCY |
| 4R-I.7 | 30-row parity matrix; 52.6% weighted | STT, textgen, SDK, legal all weak |
| 4R-I.4 | 5 of 8 deferred test categories evidenced; 1 stale assertion fixed; OpenAPI refreshed | Playwright, PG migration, full examples runtime deferred |
| 4R-I.8 | Gate 4 surface preserved | 1 P0 + 6 P1 + 3 P2 security blockers |

## §3. MVP readiness assessment

### 3.1 MVP-blocking items

| Item | Severity | Status |
|---|---|---|
| 5 direct PHI identifier columns unencrypted (4R-I.8 §8 P0) | P0 | OPEN |
| Real STT provider integration (4R-I.7 §6) | P0 | OPEN (STUB_OR_MOCK_ONLY) |
| Real LLM provider egress runtime proof (4R-I.7 §6) | P0 | PARTIAL |

### 3.2 MVP-acceptable gaps

These are gaps an MVP scope can ship without:

| Item | Reason acceptable for MVP |
|---|---|
| Full-suite Windows asyncio hang | Env-specific; CI on Linux passes |
| PostgreSQL migration verification | MVP can ship on SQLite for single-hospital scope |
| KMS / per-tenant keys | MVP single-tenant; global Fernet key acceptable if key custody is audited |
| Retention auto-scheduling | MVP can run retention manually via runbook |
| Playwright browser suite re-run | Phase 7 Gate 11/12/13 evidence still valid |
| Corti-complete-non-MVP gaps (ACHI/CCAM/CCI/CHOP, EU models, projects) | Different product positioning |

### 3.3 Verdict

```
ICODER_MVP_READINESS = BLOCKED
BLOCKERS = 3 (see §3.1)
PATH_TO_READY = ~2-3 weeks of engineering
  1. Encrypt 5 direct PHI identifier columns (~1 day, follow Gate 4.4 pattern)
  2. Integrate real STT provider (Alibaba Cloud / Tencent / iFlytek — ~1 week)
  3. Wire provider egress audit emit on every LLMGateway call (~2 days)
  4. Close provider egress hot-path coverage gaps (~3 days)
```

## §4. Controlled Pilot readiness assessment

### 4.1 Pilot-blocking items (in addition to MVP blockers)

| Item | Severity | Status |
|---|---|---|
| ~25 P1 quasi-identifier PHI columns unencrypted | P1 | OPEN |
| KMS / HSM integration | P1 | OPEN |
| Per-tenant encryption keys | P1 | OPEN |
| Explicit unknown-provider fail-closed | P1 | OPEN |
| Provider egress audit emit | P1 | OPEN |
| corti-reverse-engineered fixture gap | P0 (was wrongly claimed — actually 0) | RESOLVED in 4R-I.4 §2.1 |
| Clinical quality benchmark on 201 gold cases | P1 | OPEN (Phase 5 Track H incomplete) |
| Monitoring + alerting infrastructure | P1 | OPEN |
| Backup/restore runbook | P1 | OPEN |
| Incident response procedure | P1 | OPEN |
| Support ticket workflow | P1 | OPEN |
| Legal/compliance review (China PIPL) | P1 | OPEN |

### 4.2 Verdict

```
ICODER_CONTROLLED_PILOT_READINESS = BLOCKED
BLOCKERS = 6 P0/P1 security + 6 P1 ops/compliance = 12 total
PATH_TO_READY = ~3-4 months of engineering + compliance review
```

## §5. GA readiness assessment

### 5.1 GA-blocking items (in addition to Pilot blockers)

| Item | Severity | Status |
|---|---|---|
| Retention auto-scheduling | P2 | OPEN |
| Ciphertext → tenant binding enforcement | P2 | OPEN |
| LLM bypass paths (non-LLMGateway) gating | P2 | OPEN |
| Production database (PostgreSQL verified) | P2 | OPEN |
| Multi-instance horizontal scaling | P2 | OPEN |
| Region failover | P2 | OPEN |
| SLO definition and adherence | P2 | OPEN |
| Support process with SLA | P2 | OPEN |
| SDK public release | P2 | OPEN |
| Public documentation site | P2 | OPEN |
| Billing system production-grade | P2 | OPEN |
| Compliance evidence package | P2 | OPEN |
| Real hospital customer acceptance | P2 | OPEN |

### 5.2 Verdict

```
ICODER_GA_READINESS = BLOCKED
BLOCKERS = 12 Pilot blockers + 13 GA-specific = 25 total
PATH_TO_READY = ~12-18 months of engineering + commercial / legal work
```

## §6. Forbidden verdicts check (charter §22)

| Forbidden verdict | Status |
|---|---|
| PRODUCTION_READY | NOT ISSUED ✓ |
| FULLY_VERIFIED | NOT ISSUED ✓ |
| CORTI_PARITY_VERIFIED | NOT ISSUED ✓ |
| PASS_A1A_GATE4_FINAL | NOT ISSUED ✓ |
| READY_FOR_HOSPITAL_DEPLOYMENT | NOT ISSUED ✓ |
| CLINICAL_GRADE_VERIFIED | NOT ISSUED ✓ |
| PHI_BOUNDED | NOT ISSUED ✓ |

## §7. Provisional verdict

```
PASS_A1A_GATE4R_I_9_RELEASE_TIER_VERDICTS_FILED
ICODER_MVP_READINESS              = BLOCKED   (3 blockers)
ICODER_CONTROLLED_PILOT_READINESS = BLOCKED   (12 blockers)
ICODER_GA_READINESS               = BLOCKED   (25 blockers)
CORTI_PARITY_VERDICT              = NOT_DEMONSTRATED  (52.6% weighted; carried from 4R-I.7)
PRODUCTION_READINESS              = NOT_VERIFIED      (unchanged from charter §1)
```

Tier: FILED (not VERIFIED). The release-tier verdicts are filed for
backlog use; they do NOT certify any tier as ready.

## §8. Forbidden list for this sub-gate

| Forbidden action | Status |
|---|---|
| Issue READY verdict for any tier | NOT DONE ✓ (all 3 BLOCKED) |
| Issue any §22 forbidden verdict | NOT DONE ✓ |
| Touch master / origin/master | NOT DONE ✓ |
| Push / PR | NOT DONE ✓ |
| Modify clinical prompts | NOT DONE ✓ |

## §9. Next

Gate 4R-I.10 — development backlog + roadmap:

- Promote §3.1/§4.1/§5.1 items into a P0/P1/P2/P3 issue ledger
- Sequence MVP-path items in dependency order
- Output the consolidated roadmap with estimated effort
