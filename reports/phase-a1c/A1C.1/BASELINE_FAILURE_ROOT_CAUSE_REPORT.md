# A1C.1 — Baseline Failure Root Cause Report

**Run date**: 2026-07-25
**HEAD at run**: `926536f` (post-A1C.0 merge)
**Suite**: `backend/tests/` via `python -m pytest tests/ --tb=no -q --junit-xml=...`
**Total runtime**: 16:23 (983.63s)

---

## §1 Headline numbers

| Metric | Value |
|--------|-------|
| Tests collected | 3963 (3972 with 10 deselected) |
| Tests passing | **3895** |
| Tests failing | **53** |
| Tests erroring | **1** |
| Tests skipped | 14 |
| Net passing rate | 98.3% (3895 / 3963) |

### Run-to-run stability
| Run | Duration | Failed | Passed | Notes |
|-----|----------|--------|--------|-------|
| Run 1 (14:19–14:38) | 18:37 (1117s) | **87** | 3861 | First-pass baseline; 10 deselected |
| Run 2 (14:38–14:55) | 16:23 (984s) | **53** | 3895 | Second-pass baseline; same collection |

**Flaky estimate**: 87 − 53 = **34 tests fail-then-pass** on immediate retry. Indicates state leakage between tests (DB file pollution, fixture caching, async teardown ordering).

---

## §2 Classification distribution (54 nodes = 53 failures + 1 error)

| Classification | Count | % | Severity | Pilot impact |
|----------------|-------|---|----------|--------------|
| `SPEC_DRIFT` | 27 | 50.0% | P2 | YES — tests stale vs evolved product contract |
| `TEST_DEFECT` | 23 | 42.6% | P3 | NO — test mock/fixture drift, product works |
| `UNKNOWN` | 3 | 5.6% | P2 | TBD — needs manual triage |
| `PRODUCT_DEFECT` | 1 | 1.9% | P1 | YES — schema drift between ORM and alembic head |
| **TOTAL** | **54** | 100% | | |

---

## §3 Root cause by class

### 3.1 SPEC_DRIFT (27 nodes) — tests stale vs evolved product

**Examples**:

| Node | Drift kind | Fix |
|------|-----------|-----|
| `tests.integration.icoder.a2a.test_endpoints::test_well_known_agent_json_lists_cards` | Agent name localized: `'MedCodER 编码审核智能体'` (production) vs `'MedCodER Coding Review Agent'` (test expects EN) | Update test to expect CN name (consistent with CLAUDE.md §货币约定 / Phase 5 A2 CN localization) |
| `tests.integration.icoder.a2a.test_endpoints::test_agent_card_returns_full_card` | Same localization drift | Same fix |
| `tests.unit.icoder_runtime.test_registry_status::*` (8 nodes) | Pack count expectation (16) outdated — registry evolved with new expert stubs and metadata-only packs | Update count expectation; align with current `official_agents/` count |
| `tests.unit.icoder_runtime.test_agent_pack_loader::*` (3 nodes) | Same — pack loader count drift | Same |
| `tests.integration.icoder.test_phase3b1_agent_hub::test_metadata_only_packs_visible_but_not_runnable` | Hub pack list evolved (`icoder/cdi-review` removed; `icoder/claim-check`, `icoder/compliance-guardra...` added) | Update hub fixture list |
| `tests.integration.icoder.test_mcp_agent_tools_lifecycle::test_dispatch_tool_validate_codes_with_scopes_succeeds` | Rule set expanded from R001-only to R001-R010 (+MC-R-M80-001); test asserts old scope | Update rule scope assertion |

**Common pattern**: iCoDer product evolved through Phases 3–7 + A1B-AE + A1B-AE-R + A1B-AE-RV with deliberate contract changes (CN localization, expanded rule set, agent pack roster). Tests written against earlier contracts are stale but the product behaviour is correct.

**Fix strategy**: Update test expectations to current product contract. Most fixes are 1-line assertion updates. Bulk fix feasible in one focused commit.

### 3.2 TEST_DEFECT (23 nodes) — test mock/fixture drift

**Examples**:

| Node | Drift kind | Fix |
|------|-----------|-----|
| `tests.unit.icoder.backends.test_pure_llm_provider::*` (4 nodes) | `placeholder markdown API` shape changed; mock returns different shape | Update mock fixture |
| `tests.unit.icoder.backends.test_llm_with_tools_provider::*` (4 nodes) | Tool-call event shape evolved; skeleton mock out of date | Update mock event sequence |
| `tests.unit.app.test_run_trace_persistence::*` (5 nodes) | Memory store API signature changed | Update test calls |
| `tests.unit.icoder.agent_runtime.test_run_trace_store::*` (2 nodes) | Same — run_trace store API evolution | Same |
| `tests.unit.icoder.agent_runtime.test_run_trace_db_store::*` (1 node) | DB-backed store API drift | Same |
| `tests.test_api.test_oauth_audit_rejection::*` (3 nodes) | JWT test token fixtures expired or scope set changed | Regenerate fixtures |
| `tests.unit.app.test_config_fail_closed::*` (1 node) | Env var or default changed; test contract drift | Update env setup |

**Common pattern**: Backend internal APIs (LLM provider mocking, run trace store, OAuth fixtures) evolved without test maintenance. Product works (other tests pass against same APIs); tests are stale mocks.

**Fix strategy**: Refresh mocks/fixtures against current API. Most fixes are mechanical.

### 3.3 PRODUCT_DEFECT (1 node) — real schema drift

| Node | Drift kind | Fix |
|------|-----------|-----|
| `tests.unit.scripts.test_schema_drift::test_no_schema_drift_against_fresh_alembic_db` | Multiple `server_default_mismatch` and `type_mismatch` between ORM models and fresh alembic DB | Reconcile ORM models with alembic head via targeted Migration OR add missing server_defaults + String lengths to ORM |

**Drift detail** (excerpt from test failure):
```
DRIFT [server_default_mismatch] run_trace_events.status       ORM=None  DB=ok
DRIFT [server_default_mismatch] run_trace_events.duration_ms  ORM=None  DB=0
DRIFT [server_default_mismatch] run_trace_events.ts           ORM=None  DB=0
DRIFT [type_mismatch]          run_trace_events.id            ORM=varchar       DB=varchar(12)
DRIFT [type_mismatch]          run_history.id                 ORM=varchar       DB=varchar(12)
DRIFT [server_default_mismatch] idempotency_records.status    ORM=None  DB=pending
DRIFT [server_default_mismatch] idempotency_records.created_at ORM=None DB=current_timestamp
DRIFT [server_default_mismatch] preview_sessions.single_use   ORM=None  DB=1
DRIFT [server_default_mismatch] preview_sessions.token_version ORM=None DB=1
DRIFT [server_default_mismatch] preview_sessions.status       ORM=None  DB=pending
DRIFT [server_default_mismatch] preview_sessions.issued_at    ORM=None  DB=current_timestamp
```

**Diagnosis**:
- ORM `String` columns without explicit length → SQLAlchemy emits `varchar` (unbounded); migrations declare `varchar(12)` etc. → type mismatch.
- ORM `Column` without `server_default` but migration declares one (`server_default=text('ok')`, `0`, `pending`, etc.) → default mismatch.

**Fix strategy**: Add explicit `String(N)` lengths and `server_default=...` to ORM model column definitions for the 11 columns listed above. Single file likely (`backend/app/database.py` or per-model files).

**Severity**: P1 — affects pilot deployment because fresh DB installs (via alembic) will have constraints/defaults that ORM doesn't expect, causing runtime IntegrityErrors when ORM inserts NULL.

**Affects pilot**: **YES** — must be fixed before A1C.9 PASS.

### 3.4 UNKNOWN (3 nodes) — needs manual triage

Will be triaged in a follow-up commit. Listed in `BASELINE_FAILURE_LEDGER.csv` with `classification=UNKNOWN`.

### 3.5 FLAKY (~34 nodes) — test isolation failure

**Symptom**: Fail in run 1, pass in run 2 with identical command. Implies state leak between tests.

**Likely root cause**:
- Shared SQLite file `data/icoder.db` mutated by one test, observed by next
- Module-level cache (e.g., `tenant_extractor.JWT_CACHE`) populated by one test, not reset for next
- Async event loop / fixture scope (`asyncio_default_fixture_loop_scope`) — known SQLAlchemy warning

**Fix strategy**: A1C.1 must ship DevDbSessionGuard refactor (per PDF A1C.1 "DevDbSessionGuard 修复") + per-test DB isolation. See `DEV_DB_ISOLATION_REPORT.md`.

---

## §4 Pilot-blocking priority

| Priority | Count | Block pilot? |
|----------|-------|--------------|
| P1 (PRODUCT_DEFECT) | 1 | **YES** — schema drift |
| P2 (SPEC_DRIFT + UNKNOWN) | 27 + 3 = 30 | YES in aggregate — signals CI is not trustworthy |
| P3 (TEST_DEFECT) | 23 | NO individual, YES in aggregate |

**Pilot-blocking total**: 54 nodes; P1=1, P2=30, P3=23. All must be either FIXED or explicitly quarantined with rationale before A1C.9 PASS verdict.

---

## §5 Fix plan (ordered)

1. **P1 fix** (this sub-gate): ORM ↔ alembic reconciliation for the 11 drifted columns. Single Migration OR single ORM patch.
2. **P2 SPEC_DRIFT bulk fix** (this sub-gate): Update test expectations for CN-localized names, expanded rule set, evolved agent pack roster. Estimated 27 nodes fixable in 1–2 commits.
3. **P2 UNKNOWN triage** (this sub-gate): Manual classification of 3 unknowns.
4. **P3 TEST_DEFECT bulk fix** (this sub-gate): Refresh mocks/fixtures for LLM providers, run_trace store, OAuth fixtures.
5. **FLAKY remediation** (this sub-gate): DevDbSessionGuard refactor for per-test DB isolation; see `DEV_DB_ISOLATION_REPORT.md`.
6. **ESLint introduction** (this sub-gate): Add eslint dev-dependency + `.eslintrc.cjs` config; see `ESLINT_INTRODUCTION_REPORT.md`.
7. **CI gate policy** (this sub-gate): Document hard CI gates; see `CI_GATE_POLICY.md`.

---

## §6 Re-run expectation

After applying §5 fixes 1–6, expected re-run baseline:
- P1 fix → −1 failure (schema drift resolved)
- P2 SPEC_DRIFT fix → −27 failures
- P3 TEST_DEFECT fix → −23 failures
- UNKNOWN triage → −3 failures (best case)
- FLAKY remediation → −34 flaky tests stabilised

**Target post-fix**: 0 failed / 0 errors / ~3963 passing (modulo DEV_DB_GUARD noise).

If any of §5 fixes slips to A1C.2+, it must be logged in `A1C_OPEN_BLOCKERS.csv` at A1C.9 with explicit deferral reason.
