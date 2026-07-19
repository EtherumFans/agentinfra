# Phase A1A Gate 3.1 — Legacy Tenancy Attribution Reconciliation

**Date**: 2026-07-18
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3.0 (`A1A_GATE3_0_BASELINE_AND_GATE2_CARRYOVER.md`)
**Hard checkpoint**: B (Historical Tenant Attribution)

Closes charter §3.1 requirements: replace the Migration 016
"latest membership wins" heuristic with an evidence-based 7-class
taxonomy, add six attribution-provenance columns, and re-classify
every legacy row.

Migration 016 is **untouched** (charter §3.1 §1).

---

## §1. Deliverables

| Artifact | Path |
|---|---|
| 7-class constants | `backend/app/middleware/tenancy_guard.py` (added) |
| 6 attribution columns × 2 tables | `backend/app/models/run_history.py`, `backend/app/models/audit_log.py` |
| Evidence collector + classifier | `backend/app/services/legacy_tenancy_attribution.py` (new, ~400 LOC) |
| Migration 017 | `backend/alembic/versions/017_legacy_tenancy_reconciliation.py` |
| Classifier unit tests (17 cases) | `backend/tests/unit/app/test_legacy_tenancy_attribution.py` |
| Pre-migration report | inline below (§3) |
| Post-migration state | inline below (§5) |

---

## §2. 7-class taxonomy (charter §3.1 §3)

| Class | Meaning | Source strings |
|---|---|---|
| `MODERN` | Modern write path, non-NULL organization_id | `modern_write_path` |
| `MODERN_SYSTEM` | Intentional system-scope row (security events, system startup) | `security_event` |
| `LEGACY_TENANT_VERIFIED` | Strong request-level evidence pins to exactly 1 org | `api_client_binding` / `embedded_app_binding` / `session_binding` / `context_binding` / `request_correlation` |
| `LEGACY_TENANT_INFERRED` | Exactly 1 candidate org via membership, no strong evidence | `user_membership_at_time` / `user_membership_latest` / `user_single_membership_history` |
| `LEGACY_TENANT_AMBIGUOUS` | Multiple candidate orgs, no way to pick one with confidence | (membership source) |
| `LEGACY_TENANT_UNKNOWN` | No candidate org (NULL user_id, no correlation id) | `no_user_id_no_candidate` / `user_id_no_membership` |
| `QUARANTINED` | Operator-flagged for manual review (not auto-set) | n/a |

Confidence values: `verified | inferred | ambiguous | none`.

---

## §3. Pre-migration report (charter §3.1 §5)

State immediately before running Migration 017 (= state left by Migration 016):

| tenancy_classification | run_history | audit_logs |
|---|---:|---:|
| `MODERN` | 5 | 32 |
| `LEGACY_TENANT_KNOWN` | 230 | 200 |
| `LEGACY_TENANT_UNKNOWN` | 5 | 1 |
| `QUARANTINED` | 0 | 0 |
| **Total** | **240** | **233** |

### Pre-migration evidence inventory

| Evidence type | Available on legacy rows? |
|---|---|
| `api_client_id` non-NULL | 0 / 235 |
| `embedded_app_id` non-NULL | 0 / 235 |
| `session_id` non-NULL | 0 / 235 |
| `context_id` non-NULL | 0 / 235 (5 MODERN rows have context_id) |
| `request_id` non-NULL | 0 / 235 |
| User has multiple memberships (current) | 0 users |
| `membership.created_at > record.created_at` | 0 rows |

### Projected post-migration state (computed before running migration)

| tenancy_classification | run_history | audit_logs | Notes |
|---|---:|---:|---|
| `MODERN` | 5 | 32 | preserved (modern write path) |
| `MODERN_SYSTEM` | 0 | 1 | the `api_client.authentication_rejected` security event |
| `LEGACY_TENANT_INFERRED` | 230 | 200 | all single-membership users, inferred via `user_membership_at_time` |
| `LEGACY_TENANT_AMBIGUOUS` | 0 | 0 | no multi-org users currently |
| `LEGACY_TENANT_VERIFIED` | 0 | 0 | no request-level evidence available on legacy rows |
| `LEGACY_TENANT_UNKNOWN` | 5 | 0 | all 5 runs have NULL user_id |
| **Total** | **240** | **233** | |

### Caveat on `LEGACY_TENANT_INFERRED`

All 430 inferred rows rest on the user-membership snapshot. With the
current dataset this is unambiguous (every user has exactly 1
membership), but the classification name (`_INFERRED`) honestly
represents the evidence quality: if any user gains a second membership
in the future, the historical rows should be re-examined, not silently
re-attributed. The new `tenancy_attribution_source` /
`tenancy_attribution_confidence` /
`tenancy_attribution_migration` columns preserve the audit trail so
that re-examination is possible.

---

## §4. Migration 017 — mechanics

### DDL

Adds six columns to both `run_history` and `audit_logs`:

```python
tenancy_attribution_source     VARCHAR(64)  NULL
tenancy_attribution_confidence VARCHAR(16)  NULL
tenancy_attribution_migration  VARCHAR(8)   NULL
tenancy_attributed_at          DATETIME     NULL
tenancy_original_org_id        VARCHAR(12)  NULL
tenancy_candidate_count        INTEGER      NULL
```

### Backfill — three phases

1. **Stamp MODERN provenance**. Every existing `MODERN` row gets
   `source=modern_write_path, confidence=verified, migration=016,
   original_org_id=organization_id, candidate_count=1`.
2. **Run the classifier on every legacy row**. The classifier reads
   each row + all join-able strong evidence (api_client /
   embedded_app / session / context / request) plus the user
   membership snapshot (at-time + full history), then assigns one of
   the 7 classes.
3. **Preserve MODERN / MODERN_SYSTEM**. The reclassify driver
   short-circuits rows that are already `MODERN` or `MODERN_SYSTEM`
   so the classifier never overrides a row whose organization_id was
   set by the modern write path.

### Idempotency

Re-running Migration 017 produces identical final state. MODERN rows
are short-circuited; legacy rows receive the same classification on
every run (the classifier is deterministic per row + schema state).
The classifier does write the same values back to the row on
re-runs — this is acceptable for a migration that runs at most a
few times in the platform's lifetime.

### Downgrade

Drops the six new columns. **Does not** undo the classification
changes (LEGACY_TENANT_INFERRED → LEGACY_TENANT_KNOWN,
MODERN_SYSTEM → LEGACY_TENANT_UNKNOWN) because the more specific
classification is strictly more informative and reverting would
re-create the over-stated "KNOWN" claim that Gate 3 was created to
fix.

---

## §5. Post-migration state — actual

Migration 017 ran successfully against `backend/data/icoder.db`:

```
[alembic 017] run_history reclassification: {'LEGACY_TENANT_INFERRED': 230, 'preserved_modern': 5, 'LEGACY_TENANT_UNKNOWN': 5}
[alembic 017] audit_logs reclassification:  {'LEGACY_TENANT_INFERRED': 200, 'preserved_modern': 32, 'MODERN_SYSTEM': 1}
```

### Final 7-class state — `run_history`

| tenancy_classification | tenancy_attribution_source | confidence | migration | count |
|---|---|---|---|---:|
| `MODERN` | `modern_write_path` | `verified` | `016` | 5 |
| `LEGACY_TENANT_INFERRED` | `user_membership_at_time` | `inferred` | `017` | 230 |
| `LEGACY_TENANT_UNKNOWN` | `no_user_id_no_candidate` | `none` | `017` | 5 |
| **Total** | | | | **240** |

### Final 7-class state — `audit_logs`

| tenancy_classification | tenancy_attribution_source | confidence | migration | count |
|---|---|---|---|---:|
| `MODERN` | `modern_write_path` | `verified` | `016` | 32 |
| `LEGACY_TENANT_INFERRED` | `user_membership_at_time` | `inferred` | `017` | 200 |
| `MODERN_SYSTEM` | `security_event` | `verified` | `017` | 1 |
| **Total** | | | | **233** |

### Counts reconciliation

| Metric | Pre-017 | Post-017 | Δ |
|---|---:|---:|---|
| `run_history` total | 240 | 240 | 0 |
| `audit_logs` total | 233 | 233 | 0 |
| `LEGACY_TENANT_KNOWN` | 430 | **0** | -430 (split into VERIFIED/INFERRED/AMBIGUOUS) |
| `LEGACY_TENANT_INFERRED` | n/a | **430** | +430 |
| `LEGACY_TENANT_UNKNOWN` | 6 | **5** | -1 (the security event moved to MODERN_SYSTEM) |
| `MODERN_SYSTEM` | 0 | **1** | +1 |
| `MODERN` | 37 | **37** | 0 |

Numbers match the pre-migration projection (§3) exactly.

### Spot checks

- 5 UNKNOWN runs all carry `source=no_user_id_no_candidate`,
  `confidence=none`, `candidate_count=0`, `organization_id=NULL`.
- 1 MODERN_SYSTEM audit row (`api_client.authentication_rejected`
  on 2026-07-17) carries `source=security_event`,
  `confidence=verified`, `organization_id=NULL`.
- 5 MODERN run_history rows all carry `source=modern_write_path`
  with their original organization_id preserved.
- 230 + 200 = 430 LEGACY_TENANT_INFERRED rows all carry
  `source=user_membership_at_time`, `confidence=inferred`,
  `migration=017`. Their `tenancy_original_org_id` is NULL (the
  organization_id was originally NULL before Migration 016
  backfilled it).

---

## §6. Test results

### Gate 3.1 classifier unit tests

```
tests/unit/app/test_legacy_tenancy_attribution.py
  17 passed
```

Coverage of charter §8 A items 1–15:

| # | Charter item | Test |
|---|---|---|
| 1 | User has only 1 org | `test_1_single_org_user_is_inferred` |
| 2 | User has 2 orgs | `test_2_multi_org_user_is_ambiguous` |
| 3 | Latest membership time mismatch | `test_3_latest_membership_time_mismatch` |
| 4 | Membership created after run | `test_4_membership_created_after_run` |
| 5 | API Client matches membership | `test_5_api_client_evidence_matches_membership` |
| 6 | API Client conflicts with membership | `test_6_api_client_evidence_conflicts_with_membership` |
| 7 | Session evidence | `test_7_session_evidence` |
| 8 | Context evidence | `test_8_context_evidence` |
| 9 | No evidence | `test_9_no_evidence_no_user` |
| 10 | System user / security event | `test_10_system_user_security_event` |
| 11 | Platform admin (multi-org) | `test_11_platform_admin_multi_org_ambiguous` |
| 12 | Multi-candidate ambiguous | `test_12_multiple_candidates_no_strong_evidence` |
| 13 | Unknown candidate | `test_13_unknown_candidate_zero` |
| 14 | Migration idempotency | `test_14_reclassify_idempotent` |
| 15 | Counts closure | `test_15_counts_closure` |

Plus 2 extras:
- `test_collect_evidence_skips_missing_runtime_sessions_context_id` —
  schema-defensive (production `runtime_sessions` lacks `context_id`
  today).
- `test_system_audit_actions_allowlist_includes_reject_event` —
  guard against accidentally removing the security-event allowlist
  entry.

### Gate 2 regression

```
tests/unit/app/test_tenancy_guard.py                  11 passed
tests/test_api/test_a1a_gate2_org_isolation.py        16 passed
                                                     27 passed
```

The 6 new nullable columns + the new classifier module do not break
any Gate 2 invariant. MODERN rows continue to be classified MODERN
via the existing `classify_modern_write` helper; the fail-closed
write guard is unchanged.

---

## §7. Charter requirements — closure

| Charter §3.1 item | Status |
|---|---|
| §1 Migration 016 not modified | ✅ file unchanged |
| §2 Per-row evidence-based attribution | ✅ `legacy_tenancy_attribution.py` |
| §3 7-class taxonomy | ✅ implemented (constants + classifier) |
| §4 Attribution source/confidence/migration/attributed_at/original_org_id/candidate_count columns | ✅ added to both tables |
| §5 Pre-migration report | ✅ §3 above |
| (No PHI stored as evidence) | ✅ — provenance columns store only org_id + source string, never note text / names / tokens |

---

## §8. Open carry-over (closed by later gates)

- The 5 `LEGACY_TENANT_UNKNOWN` runs and 0 (formerly 1) audit rows
  must be hidden from normal tenant reads — Gate 3.2 (Quarantine &
  tenant read policy).
- The schema additions in this gate do NOT add DB-level constraints
  preventing future NULL org writes — that's Gate 3.7.
- Runtime write paths still call the legacy 4-class
  `classify_modern_write` helper; nothing changes for new writes
  (they continue to stamp `MODERN` / `MODERN_SYSTEM`). The new
  taxonomy only changes how historical rows are labeled.

---

## §9. Verdict

```
PASS_A1A_GATE3_1_LEGACY_TENANT_ATTRIBUTION_RECONCILED
```

Hard checkpoint B (Historical Tenant Attribution) — **CLOSED**.

Forbidden verdicts (charter §22) remain forbidden: this gate does
NOT certify production readiness, hospital deployment, partner
production readiness, security certification, clinical validation,
"all tenant isolation complete", "all audit gaps resolved", or
"zero defects".

Gate 3.2 (Quarantine & tenant read policy) follows.
