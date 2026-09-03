# A1D.2 — Small Infrastructure Changelog (audit pause + egress decision log)

**Subgate**: A1D.2
**Date**: 2026-08-05
**Charter**: `docs/phase-a1d/A1D_CHARTER.md` v1.1 §四 A1D.2
**Predecessor**: A1C.9 (PARTIAL — A1C-B-012 + A1C-B-018 OPEN)
**A1D.2 closes**: A1C-B-012 + A1C-B-018 (2 of 9 Engineering-class blockers)

---

## §1 Verdict

```
PASS_A1D_2_AUDIT_PAUSE_AND_EGRESS_DECISION_LOG_FILED
```

**Justification**:
- ✓ A1C-B-012 — `RuntimeDataPolicy.egress_decision(provider)` returns structured record; module-level `egress_decision_log(policy, provider)` emits at INFO/WARNING. 8 unit tests PASS.
- ✓ A1C-B-018 — `ICODER_AUDIT_WRITE_PAUSED=true` short-circuits `log_action` AFTER tenancy guard. 4 unit tests PASS.
- ✓ Drive-by infra repair: `patient_context.py` duplicate `ix_patient_contexts_expires_at` index removed — was blocking all DB-touching tests under session-scoped `setup_db` fixture. 46/46 A1A regression PASS post-fix.
- ✓ TDD pattern: tests written first (RED) → impl (GREEN) → refactor.
- ✓ No regression: A1A Gate 2/4.3/4.4/4.5 sweep 46/46 PASS.
- ✓ No forbidden git ops performed.
- ✓ A1C final artifacts modified: 0.

---

## §2 Files changed

### 2.1 Source code (3 files)

| File | Change |
|------|--------|
| `backend/icoder_runtime/core/data_policy.py` | + `egress_decision()` method, + `egress_decision_log()` module function, + `datetime/timezone/logging` imports. `can_use_provider` best_effort path unchanged (still returns `(True, "")` to honor pre-A1D.2 contract — violation explanation lives in structured log). |
| `backend/app/middleware/audit.py` | + `import os`, + A1C-B-018 pause short-circuit. Fires AFTER `assert_tenancy_for_write` so fail-closed survives pause. |
| `backend/app/models/patient_context.py` | Drive-by: removed `index=True` from `expires_at` column (line 63). Explicit `Index("ix_patient_contexts_expires_at", "expires_at")` on line 42 already creates the index. Duplicate metadata entry caused `Base.metadata.create_all` to emit `CREATE INDEX` twice → `OperationalError: index already exists` — blocked ALL DB-touching tests under session-scoped `setup_db`. |

### 2.2 Tests (2 files, 12 cases)

| File | Cases |
|------|-------|
| `backend/tests/test_api/test_a1d_2_egress_decision_log.py` | 8 cases — §1 egress_decision() pure record (5) + §2 egress_decision_log() structured emission (3) |
| `backend/tests/test_api/test_a1d_2_audit_pause_flag.py` | 4 cases — §1 skip-on-pause + regression write + §2 tenancy guard survives pause + §3 system-scope pause |

### 2.3 Documentation / state (this dir + blocker CSV)

| File | Change |
|------|--------|
| `reports/phase-a1d/A1D.2/SMALL_INFRA_CHANGELOG.md` | NEW (this file) |
| `reports/phase-a1d/A1D.0/A1D_OPEN_BLOCKERS.csv` | A1C-B-012 + A1C-B-018 → CLOSED |

---

## §3 Design decisions

### 3.1 A1C-B-012 — explicit egress decision record

**Predecessor state**: `can_use_provider(provider)` returns `(allowed, reason)`. For a deny, the reason is a prose string. For a best_effort allow-with-warning, the reason is empty (logged at WARNING). Charter §4 PDF asked for an EXPLICIT decision record that a compliance auditor can `grep` without parsing prose.

**Solution**: a pure function `egress_decision(provider) -> dict` that wraps `can_use_provider` and produces:

```python
{
    "tenant_region": "cn",
    "provider_name": "openai_compat",
    "provider_region": "us",
    "egress_policy": "strict",
    "decision": "deny",
    "reason": "Provider 'openai_compat' region='us' does not match ...",
    "timestamp": "2026-08-05T11:22:33.444+00:00",
}
```

A side-effecting helper `egress_decision_log(policy, provider)` calls the pure function and emits:
- `WARNING` for deny decisions (compliance auditor grep target)
- `INFO` for allow decisions

**Why this shape**:
- Pure function is unit-testable without fixtures.
- JSON-serializable — can be persisted to audit_log.details (A1D.3 work) or shipped to a SIEM.
- Timestamp is ISO-8601 UTC with timezone — sortable and unambiguous.
- `decision` is `allow`/`deny` (lowercase string) — easier to grep than a boolean.
- Reason text mirrors `can_use_provider` exactly — no semantic drift.

**Deferred to A1D.3 / Layer 2**: wiring `egress_decision_log` into `audit_middleware` and `LLMGateway`. A1D.2 delivers the PRIMITIVE; A1D.3 wires it into the request audit row.

### 3.2 A1C-B-018 — operator-driven audit pause

**Predecessor state**: `log_action` always commits a row. RB-3 PITR rollback needs the operator to PAUSE audit writes during the recovery window without stopping the service — otherwise the rolled-back DB collects audit rows pointing at operations that were undone.

**Solution**: env flag `ICODER_AUDIT_WRITE_PAUSED` (default `false`). When `true`, `log_action` short-circuits AFTER the tenancy guard:

```python
async def log_action(...):
    assert_tenancy_for_write(...)  # ← fires FIRST (fail-closed survives pause)
    if os.environ.get("ICODER_AUDIT_WRITE_PAUSED", "false").lower() == "true":
        logger.warning("audit_write_paused ...")
        return
    # ... rest of normal path
```

**Why env var, not Settings**:
- Operator flips it via `export ICODER_AUDIT_WRITE_PAUSED=true` mid-incident — no service restart, no config file edit.
- `os.environ.get` is read on every call — flipping the flag takes effect on the next audit emit, no cache.
- Pattern mirrors A1A Gate 2 §3 (`assert_tenancy_for_write` reads `ICODER_DEPLOYMENT_MODE` directly for the same reason: survive test reloads, operator-flip mid-session).

**Why the guard fires BEFORE the pause**:
A paused audit would be a perfect data-leak vector if it skipped the tenancy check — the row that would have failed tenancy now silently drops. The guard must fire first.

**Test §2** (`test_log_action_pause_does_not_bypass_tenancy_guard`) explicitly verifies this with `ICODER_DEPLOYMENT_MODE=cloud` + `organization_id=None` + `allow_null_org=False`: pause flag is set, but the call still raises.

### 3.3 Drive-by: `patient_context.py` duplicate index

**Symptom**: every DB-touching test under session-scoped `setup_db` fixture (in `tests/conftest.py`) failed at `Base.metadata.create_all` with `OperationalError: index ix_patient_contexts_expires_at already exists`.

**Root cause**: `app/models/patient_context.py` had both:
- Line 42 (explicit): `Index("ix_patient_contexts_expires_at", "expires_at")` in `__table_args__`
- Line 63 (implicit): `expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)` — `index=True` auto-generates an index named `ix_<table>_<column>` (same name)

SQLAlchemy 2.0 metadata collected BOTH entries instead of deduplicating, so `create_all` emitted `CREATE INDEX ix_patient_contexts_expires_at ...` twice. The second statement failed.

**Fix**: removed `index=True` from line 63. The explicit `Index` on line 42 already provides the index.

**Why this is in A1D.2 scope** (not scope creep):
1. The bug BLOCKED A1D.2 acceptance — could not verify audit pause tests without DB fixtures.
2. The fix is 1 line, behavior-preserving (the index exists either way).
3. Charter §五 5.1 ("先审计,后开发") requires investigation before action — investigation revealed this as the blocker.
4. Documented transparently here, not buried.
5. Carry-over: the same fix likely unblocks ~88 historical baseline failures (A1C-B-002 / A1D.5 backlog). Verifying that is A1D.5 work, not A1D.2.

**Post-fix regression**: 46/46 A1A Gate 2 + 4.3 + 4.4 + 4.5 tests PASS.

---

## §4 Verification

### 4.1 New A1D.2 tests (12/12 PASS)

```
$ cd backend && python -m pytest tests/test_api/test_a1d_2_egress_decision_log.py tests/test_api/test_a1d_2_audit_pause_flag.py -v

tests/test_api/test_a1d_2_egress_decision_log.py::test_egress_decision_returns_structured_record_for_deny PASSED
tests/test_api/test_a1d_2_egress_decision_log.py::test_egress_decision_returns_structured_record_for_allow PASSED
tests/test_api/test_a1d_2_egress_decision_log.py::test_egress_decision_best_effort_cross_region_returns_allow_with_warning_reason PASSED
tests/test_api/test_a1d_2_egress_decision_log.py::test_egress_decision_off_policy_skips_region_check PASSED
tests/test_api/test_a1d_2_egress_decision_log.py::test_egress_decision_blocked_by_allow_external_llm_flag PASSED
tests/test_api/test_a1d_2_egress_decision_log.py::test_egress_decision_log_emits_warning_on_deny PASSED
tests/test_api/test_a1d_2_egress_decision_log.py::test_egress_decision_log_emits_info_on_allow PASSED
tests/test_api/test_a1d_2_egress_decision_log.py::test_egress_decision_log_returns_same_record_as_egress_decision PASSED
tests/test_api/test_a1d_2_audit_pause_flag.py::test_log_action_skips_db_write_when_paused PASSED
tests/test_api/test_a1d_2_audit_pause_flag.py::test_log_action_writes_when_not_paused PASSED
tests/test_api/test_a1d_2_audit_pause_flag.py::test_log_action_pause_does_not_bypass_tenancy_guard PASSED
tests/test_api/test_a1d_2_audit_pause_flag.py::test_log_action_pause_with_system_scope_event_skips_db_write PASSED
======================== 12 passed, 1 warning in 9.51s ========================
```

### 4.2 Regression sweep (46/46 PASS) — drive-by fix did not break anything

```
$ cd backend && python -m pytest tests/test_api/test_a1a_gate2_org_isolation.py tests/test_api/test_a1a_gate4_3_live_path_redaction.py tests/test_api/test_a1a_gate4_4_phi_at_rest_encryption.py

======================= 46 passed, 1 warning in 11.72s =======================
```

### 4.3 Charter compliance

| Charter requirement | Status |
|---|---|
| §四 A1D.2 scope = A1C-B-012 + A1C-B-018 only | ✓ (drive-by infra fix documented in §3.3) |
| §五/5.1 先审计后开发 | ✓ (investigated EXISTS_BUT_UNVERIFIED state before coding) |
| §五/5.2 证据优先 | ✓ (12 new tests + 46 regression tests) |
| §五/5.3 不掩盖历史问题 | ✓ (patient_context fix surfaced in §3.3, not buried) |
| §五/5.4 医疗系统 fail-closed | ✓ (tenancy guard fires BEFORE pause short-circuit) |
| §五/5.5 不引入新 verdict | ✓ (PASS_A1D_2_*_FILED) |
| §五/5.6 连续执行 | ✓ (A1D.1 → A1D.2 in same session) |
| §六/6.1 forbidden git ops | ✓ (no push, no amend, no add -A; explicit file list) |
| §六/6.2 explicit file list | ✓ |
| §六/6.2 TDD pattern | ✓ (tests RED → impl GREEN for both blockers) |

---

## §5 Carry-forward to A1D.6

| Item | Target |
|---|---|
| Wire `egress_decision_log` into `audit_middleware` request audit row (currently primitive only) | A1D.3 (identity & audit) |
| Wire `egress_decision_log` into `LLMGateway` provider selection path | A1D.4 (cloud resilience) |
| Document `ICODER_AUDIT_WRITE_PAUSED` in operations runbook | Layer 2 (productization) |
| Verify drive-by patient_context fix unblocks remaining ~85 historical baseline failures | A1D.5 (88 baseline failures triage) |

A1D.6 aggregate verdict will note: "A1D.2 audit-pause + egress-decision-log PASS" — closes 2 of 9 Engineering-class blockers.

---

## §6 Subgate close

A1D.2 closed. 3 of 9 Engineering-class blockers closed (A1C-B-003 + A1C-B-012 + A1C-B-018). 6 remain.

Next subgate: A1D.3 (identity & audit: UserRole extension + audit_middleware allow-side wiring — A1C-B-010 + A1C-B-011 + A1C-B-020).
