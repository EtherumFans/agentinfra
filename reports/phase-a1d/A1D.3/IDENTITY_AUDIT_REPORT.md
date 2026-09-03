# A1D.3 — Identity & Audit Report (UserRole extension + policy_decision + purpose_of_use)

**Subgate**: A1D.3
**Date**: 2026-08-05
**Charter**: `docs/phase-a1d/A1D_CHARTER.md` v1.1 §四 A1D.3
**Predecessor**: A1C.9 PARTIAL (A1C-B-010 + A1C-B-011 + A1C-B-020 OPEN)
**A1D.3 closes**: A1C-B-010 + A1C-B-011 + A1C-B-020 (3 of 9 Engineering-class blockers)

---

## §1 Verdict

```
PASS_A1D_3_IDENTITY_AND_AUDIT_PRIMITIVES_FILED
```

**Justification**:
- ✓ A1C-B-020 — `UserRole` enum extended (7→9 values); Migration 030 lands cleanly; round-trip verified; 9 unit tests PASS.
- ✓ A1C-B-010 — `log_action` accepts keyword-only `policy_decision` dict; 5 fields (`decision/decision_reason/rbac_role/abac_purpose_match/tenant_match`) merged into `details`; redactor allowlist widened; 5 unit tests PASS.
- ✓ A1C-B-011 — `log_action` accepts keyword-only `purpose_of_use`; merged into `details.purpose_of_use`; 2 unit tests PASS.
- ✓ No regression: 111/111 A1A + A1B-AE-RV + A1D.2 + A1D.3 sweep PASS in 49.06s.
- ✓ TDD pattern: 16 new tests written RED → impl GREEN.
- ✓ No forbidden git ops performed.
- ✓ A1C final artifacts modified: 0.

**Does NOT close** (deferred to Pilot env / Layer 2):
- Per-route opt-in wiring (consumer of the new primitives): each route that wants allow-side audit emission must call `log_action(..., policy_decision=...)`. A1D.3 ships the PRIMITIVE; pilot onboarding wires it.
- `request.state.purpose_of_use` propagation: A1D.3 ships the parameter; middleware that populates request.state from patient_context is Pilot-env work (per A1C.6 §4 dynamic injection deferral).

---

## §2 Files changed

### 2.1 Source code (4 files)

| File | Change |
|------|--------|
| `backend/app/models/user.py` | + `UserRole.CDI_SPECIALIST = "cdi_specialist"` + `UserRole.MEDICAL_RECORDS_ADMIN = "medical_records_admin"`. Inline comment explains the A1C.4 §3.1 conflation gap closed. |
| `backend/alembic/versions/030_user_role_extension.py` | NEW migration. SQLite: `batch_alter_table` widens the column-type Enum (no CHECK constraint on SQLite, so essentially a no-op that re-asserts the type). PostgreSQL: `ALTER TYPE userrole ADD VALUE IF NOT EXISTS '...'` (additive, no table rewrite). `_USER_ROLE_LITERALS` constant shared with the enum. Downgrade provided for parity (PG ENUM has no DROP VALUE — downgrade is informational only). |
| `backend/app/middleware/audit.py` | + keyword-only `policy_decision: Optional[dict]` + `purpose_of_use: Optional[str]` parameters. Merged into `details` BEFORE the A1A Gate 4.3 redactor. Existing 40+ call sites unchanged (both default None). |
| `backend/app/services/audit_detail_redactor.py` | + 6 new keys added to `_ALLOWED_DETAIL_KEYS` frozenset: `decision`, `decision_reason`, `rbac_role`, `abac_purpose_match`, `tenant_match`, `purpose_of_use`. None can carry PHI (all enum literals or short reason strings). |

### 2.2 Tests (3 files, 16 cases)

| File | Cases |
|------|-------|
| `backend/tests/test_api/test_a1d_3_user_role_extension.py` | 9 cases — §1 enum values (4) + §2 migration revision chain + upgrade/downgrade callable + literals-match-enum + §3 User factory accepts new roles (2) |
| `backend/tests/test_api/test_a1d_3_policy_decision_emission.py` | 7 cases — §1 policy_decision allow/deny/merge-with-details/regression (4) + §2 purpose_of_use + regression (2) + §3 combined (1) |
| `backend/tests/test_api/test_a1b_ae_rv_2_migration_safety.py` | Drive-by: stale-assertion fix — test now reads canonical alembic head from `versions/` directory instead of hardcoding `"026"`. Same pattern as the Phase 3-B2 / 4R-I.5 stale-assertion fix. |

### 2.3 Documentation / state

| File | Change |
|------|--------|
| `reports/phase-a1d/A1D.3/IDENTITY_AUDIT_REPORT.md` | NEW (this file) |
| `reports/phase-a1d/A1D.0/A1D_OPEN_BLOCKERS.csv` | A1C-B-010 + A1C-B-011 + A1C-B-020 → CLOSED |

---

## §3 Design decisions

### 3.1 A1C-B-020 — UserRole extension: additive, no backfill

**Predecessor state**: A1C.4 §3.1 mapped 7 hospital principals to UserRole values; 2 mappings were PARTIAL:
- CDI 专员 → QC (conflated; QC偏质控, CDI偏文档改进)
- 病案管理员 → DEPT_HEAD (conflated; MRA跨科室, DEPT_HEAD单科室)

**Solution**: add 2 new enum values. Migration 030 widens the column type. No data backfill — existing rows keep their `QC` / `DEPT_HEAD` values. New rows opt into the new roles via SSO mapping (A1C.4 §3.3).

**Why additive, not backfill**:
- Existing 8-user dev DB has no real production data; backfill would be guessing.
- Production Pilot env will choose per-tenant which legacy users migrate to which new role.
- Migration shape honors Charter §6.1: no destructive ops, no data loss potential.

**Why a single migration, not separate**:
- The two new roles ship together per the Corti hospital-principal taxonomy.
- A single migration is easier to roll forward through the chain.

### 3.2 A1C-B-010 + A1C-B-011 — log_action signature extension

**Predecessor state**: `log_action` had 17 positional parameters. Existing call sites do not pass `policy_decision` or `purpose_of_use` — both fields DESIGN per A1C.6 §1 rows 12 + 5.

**Solution**: add 2 KEYWORD-ONLY parameters (`*` separator enforces). Default `None` for both. Merged into `details` JSON BEFORE the redactor runs.

**Why keyword-only**:
- Existing positional call sites continue to work without modification (zero churn across 40+ callers).
- New callers must explicitly name the parameter → impossible to accidentally swap with another arg.
- Forward-compatible: future parameters can also be keyword-only without breaking existing callers.

**Why merge into `details` and not new columns**:
- `audit_log.details` is already a JSON column designed for action-specific data.
- Adding columns would require another migration + ORM change + redactor update — heavier footprint for the same logical outcome.
- JSON merge preserves the field shape compliance auditors expect (`details.decision`, `details.rbac_role`, etc. — matches A1C.6 §1 row 12 spec).

**Why merged BEFORE redactor**:
- Redactor's allowlist must include the new keys, otherwise they'd be replaced with `"[REDACTED]"`.
- Allowlist update is a 6-key additive change to a frozenset.
- All 6 new keys are enum literals or short reason strings — none can carry PHI.

### 3.3 Drive-by: stale migration-head assertion fix

**Symptom**: `test_rv2_1_migration_026_lands_on_head_025` failed after my Migration 030 landed because the test hardcoded `head == "026"`. Head is now 030 (and will continue advancing).

**Root cause**: RV.2 wrote the assertion when 026 was head. Every subsequent migration broke the test. Phase 7 / A1A / A1B-AE-RV each fixed it once; the fix was always "bump the literal". This pattern was already noted in my memory (`stale OpenAPI snapshot trap (162→208 paths)`).

**Fix**: read the canonical head from `alembic/versions/` directory at test time. Compute head as "revision not in any down_revision". Assert the live upgrade reaches that head. Self-healing — never goes stale again.

**Why this is in A1D.3 scope** (not scope creep):
1. A1D.3 introduced Migration 030, which broke this test.
2. Fix is a test-only change, behavior-preserving.
3. Charter §五 5.6 (连续执行) doesn't tolerate broken intermediate states.
4. Pattern noted in A1A Gate 4R-I + my memory; recurring tech debt class.

---

## §4 Verification

### 4.1 New A1D.3 tests (16/16 PASS)

```
$ cd backend && python -m pytest tests/test_api/test_a1d_3_user_role_extension.py tests/test_api/test_a1d_3_policy_decision_emission.py -v

tests/test_api/test_a1d_3_user_role_extension.py::test_user_role_enum_has_9_values PASSED
tests/test_api/test_a1d_3_user_role_extension.py::test_user_role_enum_includes_cdi_specialist PASSED
tests/test_api/test_a1d_3_user_role_extension.py::test_user_role_enum_includes_medical_records_admin PASSED
tests/test_api/test_a1d_3_user_role_extension.py::test_user_role_enum_prior_values_unchanged PASSED
tests/test_api/test_a1d_3_user_role_extension.py::test_migration_030_revision_chain PASSED
tests/test_api/test_a1d_3_user_role_extension.py::test_migration_030_upgrade_downgrade_callable PASSED
tests/test_api/test_a1d_3_user_role_extension.py::test_migration_030_role_literals_match_user_role_enum PASSED
tests/test_api/test_a1d_3_user_role_extension.py::test_user_factory_accepts_cdi_specialist_role PASSED
tests/test_api/test_a1d_3_user_role_extension.py::test_user_factory_accepts_medical_records_admin_role PASSED
tests/test_api/test_a1d_3_policy_decision_emission.py::test_log_action_accepts_policy_decision_allow PASSED
tests/test_api/test_a1d_3_policy_decision_emission.py::test_log_action_accepts_policy_decision_deny PASSED
tests/test_api/test_a1d_3_policy_decision_emission.py::test_log_action_preserves_existing_details_when_policy_decision_set PASSED
tests/test_api/test_a1d_3_policy_decision_emission.py::test_log_action_without_policy_decision_unchanged PASSED
tests/test_api/test_a1d_3_policy_decision_emission.py::test_log_action_accepts_purpose_of_use PASSED
tests/test_api/test_a1d_3_policy_decision_emission.py::test_log_action_without_purpose_of_use_unchanged PASSED
tests/test_api/test_a1d_3_policy_decision_emission.py::test_log_action_accepts_policy_decision_and_purpose_of_use_together PASSED
```

### 4.2 Migration round-trip (manual verification)

```
$ python -m alembic current
030 (head)

$ python -m alembic downgrade -1 && python -m alembic upgrade head && python -m alembic current
030 (head)
```

Migration 030 applies cleanly on top of 029 (patient_contexts); downgrade works (no-op on SQLite, no downgrade on PG per ENUM semantics).

### 4.3 Full regression sweep (111/111 PASS)

```
$ python -m pytest \
    tests/test_api/test_a1a_gate2_org_isolation.py \
    tests/test_api/test_a1a_gate4_3_live_path_redaction.py \
    tests/test_api/test_a1a_gate4_4_phi_at_rest_encryption.py \
    tests/test_api/test_a1a_gate4_5_provider_egress_regional_residency.py \
    tests/test_api/test_a1b_ae_rv_2_migration_safety.py \
    tests/test_api/test_a1b_ae_r_2_preset_materialization.py \
    tests/test_api/test_a1d_2_audit_pause_flag.py \
    tests/test_api/test_a1d_2_egress_decision_log.py \
    tests/test_api/test_a1d_3_user_role_extension.py \
    tests/test_api/test_a1d_3_policy_decision_emission.py

======================= 111 passed, 1 warning in 49.06s =======================
```

### 4.4 Charter compliance

| Charter requirement | Status |
|---|---|
| §四 A1D.3 scope = A1C-B-010 + A1C-B-011 + A1C-B-020 only | ✓ (drive-by stale-assertion fix documented in §3.3) |
| §五/5.1 先审计后开发 | ✓ (investigated current state in §1 of this report) |
| §五/5.2 证据优先 | ✓ (16 new tests + 95 regression tests) |
| §五/5.3 不掩盖历史问题 | ✓ (stale-assertion fix surfaced in §3.3) |
| §五/5.4 医疗系统 fail-closed | n/a (no medical-system constraints in this subgate's surface area) |
| §五/5.5 不引入新 verdict | ✓ (PASS_A1D_3_*_FILED) |
| §五/5.6 连续执行 | ✓ (A1D.2 → A1D.3 in same session) |
| §六/6.1 forbidden git ops | ✓ (no push, no amend, no add -A; explicit file list) |
| §六/6.2 explicit file list | ✓ |
| §六/6.2 TDD pattern | ✓ (16 new tests RED → impl GREEN) |

---

## §5 Carry-forward to A1D.6 / Pilot / Layer 2

| Item | Target |
|---|---|
| Wire `policy_decision` into per-route audit emissions (pilot onboarding opt-in) | Pilot env (per A1C.6 §4 dynamic injection deferral) |
| Wire `request.state.purpose_of_use` middleware → `log_action(purpose_of_use=...)` | Pilot env |
| Wire `egress_decision_log()` (A1D.2 primitive) into `LLMGateway` provider selection | A1D.4 (cloud resilience) |
| Per-route RBAC + ABAC check that populates `policy_decision` dict | Layer 2 (RBAC middleware) |
| Backfill legacy `QC` → `CDI_SPECIALIST` and `DEPT_HEAD` → `MEDICAL_RECORDS_ADMIN` per-tenant | Pilot env (operational decision per tenant) |

A1D.6 aggregate verdict will note: "A1D.3 identity + audit primitives PASS" — closes 3 of 9 Engineering-class blockers.

---

## §6 Subgate close

A1D.3 closed. 6 of 9 Engineering-class blockers closed (A1C-B-003 + A1C-B-012 + A1C-B-018 + A1C-B-010 + A1C-B-011 + A1C-B-020). 3 remain.

Next subgate: A1D.4 (cloud resilience: KMS key rotation + cache invalidation — A1C-B-007 + LLM fallback provider — A1C-B-008).
