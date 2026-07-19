# Phase A1A Gate 3R.0 — Baseline & Carry-over Re-audit

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor commit**: `d1447f3` (Gate 3 — `PASS_A1A_GATE3_TENANCY_TRUTH_CONTAINMENT_AND_TRACE_ISOLATION_VERIFIED`)
**Charter scope**: Trace, audit and tenant-read closure reconciliation. **Not** Gate 4 PHI.

This report is the 22-item deliverable required before any business
code changes. It records the as-is state of every surface Gate 3R
must touch, plus the explicit non-claims (PostgreSQL, browser scope)
so the closure reports in 3R.7+ stay honest.

---

## §1. Gate 3 final verdict and scope

| Field | Value |
|---|---|
| Verdict | `PASS_A1A_GATE3_TENANCY_TRUTH_CONTAINMENT_AND_TRACE_ISOLATION_VERIFIED` |
| Scope | Gates 3.0–3.9 (one bundled commit). 7-class taxonomy, tenant_read_policy, DB trace persistence, SSE+Console trace isolation, system_audit allowlist, DB CHECK+UNIQUE, 234-test regression, browser evaluate evidence. |
| Carry-over disclosed by Gate 3 | run_lifecycle/idempotency/api_client/context audit emits in allowlist only; F06 assert_org_scope refactor; CHECK constraints on encounters/cdi_cases deferred. |
| Honesty caveats | Browser evidence was Playwright MCP `evaluate` on /api/v1/runs/{id} point lookup + /api/runtime/runs/history list filter only — not the full RunHistory → RunTrace → restart → deep-link-denial path the charter asks for. PostgreSQL migration verification not performed. Migration interrupted-recovery behaviour not validated — the `_alembic_tmp_*` table was manually dropped during Gate 3.7 to unblock Migration 019. |

## §2. Gate 3 commit hash and date

```
d1447f3 audit/phase-a1a: Gate 3 — Tenancy truth, trace isolation, audit separation
        Date: Sun Jul 19 10:13:38 2026 +0800
        36 files changed, 6960 insertions(+), 7 deletions(-)
```

## §3. Branch name

```
phase-a1a/emergency-containment
```

Local-only. No push. No PR. No master commit. Gate 3R must not amend `d1447f3`.

## §4. Current `run_history` schema (post-Migration 019)

```sql
CREATE TABLE "run_history" (
    id VARCHAR(12) NOT NULL PRIMARY KEY,
    organization_id VARCHAR(12) FOREIGN KEY REFERENCES organizations(id),
    user_id VARCHAR(64),
    agent_id VARCHAR(128) NOT NULL,
    run_id VARCHAR(64) NOT NULL UNIQUE,
    trace_id VARCHAR(64) DEFAULT '' NOT NULL,
    runtime_mode VARCHAR(48) DEFAULT '' NOT NULL,
    latency_ms INTEGER DEFAULT 0 NOT NULL,
    cost_usd FLOAT DEFAULT 0.0 NOT NULL,
    input_text TEXT NOT NULL,
    output_summary TEXT NOT NULL,
    error BOOLEAN DEFAULT 0 NOT NULL,
    error_reason VARCHAR(128),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status VARCHAR(48) DEFAULT 'COMPLETED' NOT NULL,
    cancel_reason VARCHAR(255),
    cancelled_at DATETIME,
    cancelled_by_user_id VARCHAR(64),
    api_client_id VARCHAR(128),
    embedded_app_id VARCHAR(128),
    session_id VARCHAR(64),
    context_id VARCHAR(64),
    request_id VARCHAR(64),
    idempotency_key VARCHAR(255),
    tenancy_classification VARCHAR(32),
    tenancy_attribution_source VARCHAR(64),
    tenancy_attribution_confidence VARCHAR(16),
    tenancy_attribution_migration VARCHAR(8),
    tenancy_attributed_at DATETIME,
    tenancy_original_org_id VARCHAR(12),
    tenancy_candidate_count INTEGER,
    trace_capture_status VARCHAR(16),       -- 3R.3 will widen this
    trace_capture_failure_reason VARCHAR(255),
    CONSTRAINT chk_run_history_tenancy_cls
        CHECK (tenancy_classification IS NULL OR tenancy_classification IN
               ('MODERN','MODERN_SYSTEM','LEGACY_TENANT_VERIFIED',
                'LEGACY_TENANT_INFERRED','LEGACY_TENANT_AMBIGUOUS',
                'LEGACY_TENANT_UNKNOWN','LEGACY_TENANT_KNOWN','QUARANTINED')),
    CONSTRAINT chk_run_history_trace_cap
        CHECK (trace_capture_status IS NULL OR trace_capture_status IN
               ('PERSISTED','FAILED','FALLBACK_MEMORY'))
)
```

Row count: **244** (243 COMPLETED + 1 FAILED).
Classification distribution: 230 LEGACY_TENANT_INFERRED / 7 MODERN / 5 LEGACY_TENANT_UNKNOWN / 2 QUARANTINED.

## §5. Current `run_trace_events` schema

```sql
CREATE TABLE run_trace_events (
    id VARCHAR(12) NOT NULL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    organization_id VARCHAR(12) FOREIGN KEY REFERENCES organizations(id),
    project_id VARCHAR(64),
    user_id VARCHAR(64),
    actor_id VARCHAR(64),
    agent_id VARCHAR(128),
    step VARCHAR(32) NOT NULL,
    status VARCHAR(16) DEFAULT 'ok' NOT NULL,
    duration_ms FLOAT DEFAULT 0 NOT NULL,
    ts FLOAT DEFAULT 0 NOT NULL,
    safe_metadata_json JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ux_run_trace_events_run_step_ts UNIQUE (run_id, step, ts)
)

-- Indexes:
--   sqlite_autoindex_run_trace_events_1 (PK)
--   sqlite_autoindex_run_trace_events_2 (UNIQUE run_id)
--   ix_run_trace_events_agent_id
--   ix_run_trace_events_org_created (organization_id, created_at)
--   ix_run_trace_events_run_id
```

**Gap**: no `event_id` UUID, no `trace_id` (run_history has trace_id column but events don't carry it), no `sequence_number`. Identity = `(run_id, step, ts)` which is brittle under microsecond-collision + doesn't support event replay.

Row count: **0** on the dev DB (no real runs since the data was migrated; the migration 019 `data/icoder.db.gate3-prerelease` snapshot was saved before any runs were captured post-migration).

## §6. Current `audit_logs` schema

```sql
CREATE TABLE audit_logs (
    id VARCHAR NOT NULL PRIMARY KEY,
    user_id VARCHAR(64),
    username VARCHAR(64),
    action VARCHAR(128) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_id VARCHAR(64),
    details JSON,
    ip_address VARCHAR(45),
    user_agent VARCHAR(256),
    status VARCHAR(32) NOT NULL,
    error_message TEXT,
    model_input_summary TEXT,
    model_output_summary TEXT,
    model_version VARCHAR(64),
    tool_calls_made JSON,
    tokens_used INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    organization_id VARCHAR(12) FOREIGN KEY REFERENCES organizations(id),
    agent_id VARCHAR(128),
    agent_account_id VARCHAR(12),
    delegated_by_user_id VARCHAR(64),
    tenancy_classification VARCHAR(32),
    tenancy_attribution_source VARCHAR(64),
    tenancy_attribution_confidence VARCHAR(16),
    tenancy_attribution_migration VARCHAR(8),
    tenancy_attributed_at DATETIME,
    tenancy_original_org_id VARCHAR(12),
    tenancy_candidate_count INTEGER,
    CONSTRAINT chk_audit_logs_tenancy_cls
        CHECK (tenancy_classification IS NULL OR tenancy_classification IN
               ('MODERN','MODERN_SYSTEM','LEGACY_TENANT_VERIFIED',
                'LEGACY_TENANT_INFERRED','LEGACY_TENANT_AMBIGUOUS',
                'LEGACY_TENANT_UNKNOWN','LEGACY_TENANT_KNOWN','QUARANTINED'))
)
```

Row count: **236**. Action distribution: `user.login` (161), `user.register` (41), `preview_session.*` (32), `api_client.authentication_rejected` (1), and **0 rows for run.cancel/timeout/complete/failed, idempotency.dedup, context.clear, api_client.rotate** — confirming the Gate 3.6 §7 carry-over.

Classification distribution: 200 LEGACY_TENANT_INFERRED / 32 MODERN / 1 MODERN_SYSTEM / 2 NULL.

## §7. Current `tenancy_guard` constants

```python
CLASS_MODERN_SYSTEM        = "MODERN_SYSTEM"
CLASS_LEGACY_VERIFIED      = "LEGACY_TENANT_VERIFIED"
CLASS_LEGACY_INFERRED      = "LEGACY_TENANT_INFERRED"
CLASS_LEGACY_AMBIGUOUS     = "LEGACY_TENANT_AMBIGUOUS"
CLASS_LEGACY_KNOWN         = "LEGACY_TENANT_KNOWN"   # deprecated alias

# NOT in this module (string literals only):
#   "MODERN"
#   "LEGACY_TENANT_UNKNOWN"
#   "QUARANTINED"
#   "NEVER_CAPTURED_LEGACY"  (3R.3 will add this here)
```

`assert_tenancy_for_write` + `classify_modern_write` are the only public write-path guards. They read `ICODER_DEPLOYMENT_MODE` directly from env to survive test `importlib.reload`.

## §8. Current `tenant_read_policy`

```python
TENANT_VISIBLE_CLASSIFICATIONS = frozenset({
    "MODERN", CLASS_LEGACY_VERIFIED, CLASS_LEGACY_INFERRED,
})
TENANT_INVISIBLE_CLASSIFICATIONS = frozenset({
    "LEGACY_TENANT_UNKNOWN", CLASS_LEGACY_AMBIGUOUS,
    "QUARANTINED", CLASS_MODERN_SYSTEM,
})

# Helpers:
is_tenant_visible(classification)           # None → False (strict)
apply_tenant_visibility_filter(stmt, col)   # WHERE col IN visible AND col IS NOT NULL
enforce_tenant_visible_or_404(...)          # raise HTTPException(404) generic msg
assert_security_admin_access(user, db, ...)  # role check + audit emit
```

The visibility filter excludes NULL by default — this is correct but caused 14 test regressions during Gate 3.2 that required fixture updates (every test INSERT must now stamp `tenancy_classification='MODERN'`).

## §9. SSE lacking RunHistory current behaviour

File: `app/api/runs.py::stream_run_events` (line 547–602).

```python
async with AsyncSessionLocal() as db:
    sse_row = await get_run_status(db, run_id=run_id)
if sse_row is not None:
    # org-mismatch check
    # visibility classification check
    # (both raise 404 on deny)
# ── FALLTHROUGH when sse_row IS None ──
# → continues to read trace store directly
store = get_default_store()
events = await asyncio.to_thread(store.get_run_scoped, run_id, org_id)
if not events:
    raise HTTPException(404, ...)
# proceeds to stream events
```

**Gap**: if the signed trace token is valid but the RunHistory row is missing (deleted, never written, or write failed mid-run), the SSE endpoint still streams whatever is in the trace store. This is the orphan-run attack surface Gate 3R.1 must close.

## §10. Console Trace lacking RunHistory current behaviour

File: `app/api/run_trace.py::_get_run_trace_impl` (line 76–170).

Identical fall-through pattern:

```python
async with AsyncSessionLocal() as db:
    console_row = await get_run_status(db, run_id=run_id)
if console_row is not None:
    # org-mismatch check
    # visibility classification check
    # (both raise 404 on deny)
# ── FALLTHROUGH when console_row IS None ──
# → reads trace store directly
events = await asyncio.to_thread(store.get_run_scoped, run_id, org_id)
```

Same gap. Same fix.

## §11. Partner Trace lacking RunHistory current behaviour

File: `app/api/runs.py::get_run_trace_partner` (line 300–441).

The partner path is slightly better: it gates the visibility check inside `if claims.organization_id:`, so tokens without an org claim skip the RunHistory read entirely. But for tokens that DO carry org_id (the common case), the same fall-through exists — if `row is None`, execution proceeds to `store.get_run_scoped`.

## §12. Current real Audit Emit Coverage

| Allowlist action | Actual emit sites | Status |
|---|---|---|
| `api_client.authentication_rejected` | `app/api/oauth.py` (pre-Gate 3.6) | ✅ wired |
| `system.startup` / `system.shutdown` / `system.config_change` / `system.migration` / `system.secret_rotation` | (defined in allowlist; emits not located in code grep — believed stub-only) | ⚠️ allowlist-only |
| `security_admin.access` | `app/services/tenant_read_policy.py::assert_security_admin_access` | ✅ wired |
| `sse.denied.org_mismatch` / `sse.denied.invisible_classification` | `app/api/runs.py::stream_run_events` | ✅ wired (Gate 3.4) |
| `trace.read.denied.org_mismatch` / `trace.read.denied.invisible_classification` | `app/api/run_trace.py::_get_run_trace_impl` + `app/api/runs.py::get_run_trace_partner` | ✅ wired (Gate 3.5) |
| `run.cancel` | (no caller located) | ❌ allowlist-only |
| `run.timeout` | (no caller located) | ❌ allowlist-only |
| `run.complete` | (no caller located) | ❌ allowlist-only |
| `run.failed` | (no caller located) | ❌ allowlist-only |
| `idempotency.dedup` | (no caller located) | ❌ allowlist-only |
| `context.clear` | (no caller located — Phase 6 Gate 2 widget postMessage event, backend doesn't see) | ❌ N/A on backend side |
| `api_client.rotate` | (no caller located — Phase 7 Gate 5 endpoint stubbed but rotate endpoint not exercised in current tests) | ❌ allowlist-only |

DB row counts confirm: 0 audit rows exist for any of the ❌ / ⚠️ actions. Gate 3R.2 must close this.

## §13. Current Allowlist-only Actions (no emit)

From §12 — the **eight** actions currently in the allowlist without real emit wiring:

1. `system.startup`
2. `system.shutdown`
3. `system.config_change`
4. `system.migration`
5. `system.secret_rotation`
6. `run.cancel`
7. `run.timeout`
8. `run.complete`
9. `run.failed`
10. `idempotency.dedup`
11. `api_client.rotate`

(`context.clear` is documented as N/A on backend side — Phase 6 Gate 2 widget event only.)

Gate 3R.2 must wire each of these or document why it's deferred (with a clear deferral record, not a silent miss).

## §14. Current Trace Capture Status distribution

```
SELECT trace_capture_status, COUNT(*) FROM run_history GROUP BY trace_capture_status;
  None: 244
```

**All 244 rows have NULL trace_capture_status.** This is the conflation Gate 3R.3 must fix:

- NULL today means: (a) pre-Gate-3.3 row, (b) Gate 3.3 row that hasn't emitted any event yet, (c) Gate 3.3 row whose first emit is in-flight, (d) row that will never have trace events (memory-mode dev test).
- After 3R.3: NULL must mean exactly one thing. Add `NEVER_CAPTURED_LEGACY` for (a), `CAPTURE_PENDING` for (b)/(c), and document (d) as "memory-mode dev only, never reaches production cloud".

## §15. Historical NULL Trace Status count

**244 rows.** All historical rows.

## §16. Current Trace Event Schema

From `app/models/run_trace.py::RunTraceEventModel`:

```python
class RunTraceEventModel(Base):
    __tablename__ = "run_trace_events"
    id              = Column(String(12), primary_key=True)  # random hex, NOT UUID
    run_id          = Column(String(64), nullable=False)
    organization_id = Column(String(12), FK organizations.id)
    project_id      = Column(String(64))
    user_id         = Column(String(64))
    actor_id        = Column(String(64))
    agent_id        = Column(String(128))
    step            = Column(String(32), nullable=False)
    status          = Column(String(16), default="ok")
    duration_ms     = Column(Float, default=0)
    ts              = Column(Float, default=0)         # epoch seconds float
    safe_metadata_json = Column(JSON)
    created_at      = Column(DateTime, default=now)
    updated_at      = Column(DateTime, default=now)
```

No `event_id` (UUID). No `trace_id`. No `sequence_number`. No `identity_source`.

## §17. Current Event uniqueness constraint

```sql
CONSTRAINT ux_run_trace_events_run_step_ts UNIQUE (run_id, step, ts)
```

This is the **only** identity authority today. `ts` is `time.time()` (float seconds with microsecond precision). Collision risk is negligible per-run, but:

- Floats are not sortable across process restarts (NTP slew, monotonic vs wall).
- Two events for the same step at the same microsecond collide and the second raises IntegrityError.
- Cross-trace replay is impossible: events from a re-run can't be distinguished from original events.

Gate 3R.4 introduces `event_id` (UUID) + `sequence_number` (int per trace_id).

## §18. Migration 017–019 current state

```
alembic_version: 019 (head)

Migration 017 (legacy_tenancy_reconciliation):
  - Applied: yes
  - Downgrade: written but NOT verified (idempotent re-run tested, not downgrade round-trip)
  - Postgres: NOT verified

Migration 018 (run_history_trace_capture_status):
  - Applied: yes
  - Adds: trace_capture_status, trace_capture_failure_reason columns + ix_run_history_trace_capture_status index
  - Downgrade: written but NOT verified
  - Postgres: NOT verified

Migration 019 (db_constraints_tenant_classification):
  - Applied: yes (after manual cleanup of stale `_alembic_tmp_run_history` table)
  - Adds: 3 CHECK constraints + 1 UNIQUE constraint via batch_alter_table
  - Downgrade: written but NOT verified
  - Postgres: NOT verified (batch_alter_table is no-op ALTER on PG but untested)
```

**Gap**: no Fresh SQLite / no Existing SQLite upgrade / no Downgrade/Upgrade round-trip / no Postgres verification has been run as a documented test. Gate 3R.5 closes this.

## §19. PostgreSQL verification environment availability

| Tool | Status |
|---|---|
| `psql` CLI | ❌ not installed |
| Docker | ❌ not installed |
| `testcontainers` Python lib | ❌ not installed |
| `asyncpg` | ❌ not installed |
| `psycopg2` / `psycopg` | ❌ not installed |

**Conclusion**: PostgreSQL migration verification is **environment-blocked**. Gate 3R.5 will use the partial verdict `PARTIAL_BLOCKED_BY_POSTGRES_MIGRATION_NOT_VERIFIED` for that specific sub-check, and document the Fresh SQLite + Existing SQLite + Downgrade/Upgrade + Interrupted Recovery verifications on SQLite only.

To unblock Postgres in a future gate: install Docker Desktop or `pip install testcontainers[postgres]` + `pip install asyncpg` or `psycopg[binary]`.

## §20. Current browser Evidence coverage and gaps

Gate 3.8 (commit d1447f3) delivered:

- ✅ Playwright MCP login to Console (real user, real JWT in localStorage)
- ✅ Real `fetch()` from browser context to `/api/v1/runs/{id}` — 200 for MODERN row, 404 for QUARANTINED row
- ✅ Real `fetch()` to `/api/runtime/runs/history` — list excludes QUARANTINED row
- ✅ Response body assertions (no run_id / classification leak)

Gate 3.8 did NOT cover:

- ❌ **RunHistory page** (UI) — never navigated to `/ai-studio` and verified the row appears in the table
- ❌ **RunTrace page** (UI) — never opened the trace timeline view for a specific run
- ❌ **Backend restart recovery** — never killed and restarted uvicorn mid-session to verify trace events survive
- ❌ **Cross-org deep-link denial** — never logged in as Org B user and tried to open Org A's RunTrace URL
- ❌ **SSE same-org stream** — never opened `/api/v1/runs/{id}/events` in browser to verify event stream flows
- ❌ **SSE cross-org denial** — never verified cross-org SSE returns no stream + no event bytes
- ❌ **Artifact persistence** — screenshot was not retained in repo tree (Playwright MCP saved to environment path outside repo)

Gate 3R.6 must cover **all seven** of the above via real A2A-compatible runtime (not DB shortcut).

## §21. Specific files Gate 3R needs to modify

**Source code**:
- `app/api/runs.py` — close orphan-run fall-through in SSE + partner trace; add run.cancel/timeout/complete/failed emit calls
- `app/api/run_trace.py` — close orphan-run fall-through in Console trace
- `app/services/run_lifecycle.py` — emit run.complete / run.failed / run.cancel / run.timeout from `record_run_*` helpers
- `app/services/idempotency_service.py` — emit `idempotency.dedup` on replay
- `app/api/platform_api_clients.py` — emit `api_client.rotate` on secret rotation endpoint
- `app/middleware/tenancy_guard.py` — add `CLASS_LEGACY_NEVER_CAPTURED` constant
- `app/services/trace_capture_state.py` (new) — state machine module (CAPTURE_PENDING / CAPTURED / FAILED / FALLBACK_MEMORY / NEVER_CAPTURED_LEGACY)
- `app/services/deployment_profile.py` (new) — MEMORY_DEV / BEST_EFFORT_DB / REQUIRED_DB resolution
- `app/icoder/agent_runtime/orchestrator/run_trace.py` — write `event_id` (UUID) + `sequence_number`; consult deployment profile before fall-through
- `app/models/run_trace.py` — add event_id, trace_id, sequence_number, identity_source columns
- `app/models/run_history.py` — widen `trace_capture_status` CHECK constraint
- `app/config.py` — add `ICODER_DEPLOYMENT_PROFILE` env var; tighten cloud-mode validation
- `app/services/system_audit.py` — mark `context.clear` as N/A with explicit docstring; remove from active allowlist if no emit path will exist
- `app/main.py` — startup audit emit (`system.startup`)

**Migrations**:
- `alembic/versions/020_trace_event_identity_and_capture_state.py` (new) — adds event_id, trace_id, sequence_number, identity_source; widens trace_capture_status CHECK; backfills NULL trace_capture_status to NEVER_CAPTURED_LEGACY

**Tests**:
- `tests/test_api/test_a1a_gate3r_*.py` (new) — orphan-run denial, run lifecycle audit, trace identity stability, deployment profile matrix
- `tests/unit/app/test_deployment_profile.py` (new)
- `tests/unit/app/test_trace_capture_state.py` (new)
- `tests/unit/icoder/agent_runtime/test_run_trace_identity.py` (new)

**Reports**:
- `reports/phase-a1a/A1A_GATE3R_{0..9}_*.md` (10 new closure reports; this file is 0)
- `reports/phase-a1a/A1A_GATE3_ADDENDUM.md` (corrections to Gate 3 maturity claims)
- `reports/phase-a1a/A1A_GATE3_EVIDENCE_MANIFEST.md` (consolidated evidence index)
- `reports/phase-a1a/A1A_GATE3R_ISSUE_LEDGER.md` (canonical issue status)

## §22. Current tentative verdict

```
IN_PROGRESS_A1A_GATE3R_BASELINE_AND_CARRYOVER_RE_AUDIT_COMPLETE
```

This is an **intermediate** verdict — Gate 3R is not yet closed. It records that:

1. Gate 3R.0 has produced the required 22-item baseline.
2. No business code changes have been made yet (only this report).
3. No Migration 020 has been executed.
4. No Gate 3 historical reports have been modified.
5. Gate 4 PHI work has not started.
6. Gate 3's bundled verdict is **inherited but not extended** — Gate 3R will issue its own scoped verdict after Gate 3R.9.

Forbidden verdicts (charter §22) remain forbidden. The final Gate 3R verdict will be drawn from the charter allowlist only.

---

## §23. Open questions (must resolve during 3R.1–3R.9)

1. **Deployment profile resolution order**: env var only? env var + ICODER_DEPLOYMENT_MODE cross-check? File-based profile for hospital-on-prem where env vars are unreliable?
2. **REQUIRED_DB run-state semantics**: when a trace DB write fails inside `DbRunTraceStore.append`, what `run_history.status` value reflects "trace-failed but run-otherwise-OK"? Add `COMPLETED_WITH_TRACE_GAP`? Reuse `PARTIAL`? Per charter: "依据现有 Run State Contract 明确设计" — must NOT introduce ad-hoc states.
3. **Legacy rows with NULL trace_capture_status**: Migration 020 must backfill all 244 to `NEVER_CAPTURED_LEGACY` in one pass. Verify idempotent re-run.
4. **Postgres environment**: confirmed blocked. Document partial verdict for 3R.5 and do not claim PG verification in 3R.7 addendum.
5. **system_audit `context.clear` action**: backend genuinely never sees this event (Phase 6 widget postMessage). Either remove from allowlist (and document removal) or keep with explicit `# N/A on backend` comment + zero emit sites. Gate 3R.2 decides.

---

## §24. Pre-3R.1 confirmation

Per charter §13:

> Gate 3R.0 完成前:
> - 不修改业务代码;
> - 不执行 Migration 020;
> - 不修改 Gate 3 历史报告;
> - 不启动 Gate 4 PHI 工作;
> - 不继承 Gate 3 的宽泛全闭环 Verdict.

All five hold at the time of this report's authorship. Proceeding to Gate 3R.1.
