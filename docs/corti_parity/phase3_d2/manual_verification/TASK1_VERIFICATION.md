# Phase 3-D2 Task 1 Verification — RunTrace Persistence

**Task:** RunTrace DB-backed store with org/project scoping + redaction-before-write
**Date:** 2026-07-07
**Status:** PASS
**Files affected:**
- `backend/app/models/run_trace.py` (NEW)
- `backend/alembic/versions/009_run_trace_events.py` (NEW)
- `backend/app/icoder/agent_runtime/orchestrator/run_trace.py` (MODIFIED — added DbRunTraceStore + redaction)
- `backend/app/api/run_trace.py` (MODIFIED — org-scoped read)
- `backend/app/config.py` (MODIFIED — RUNTRACE_STORE setting)
- `backend/tests/unit/icoder/agent_runtime/test_run_trace_db_store.py` (NEW — 7 tests)

## What was built

### DbRunTraceStore

A DB-backed RunTrace store that persists to the `run_trace_events` table via a sync SQLAlchemy engine. The in-memory `RunTraceStore` remains as a test/dev fallback (`settings.RUNTRACE_STORE == "memory"`).

Key design decisions:
- **Sync engine** (not async) — `emit_trace_event` is called from sync contexts (InboundHandler.handle is sync; `_SimpleAgentDispatchHandler._handle_simple` is sync). Stripping `+aiosqlite`/`+asyncpg` from the URL gives us a sync engine that works from sync code.
- **Lazy engine creation** — `_ensure_engine()` defers engine creation until the first emit. Tests that never touch DB don't pay the cost.
- **Org-scoped read** — `get_run_scoped(run_id, organization_id)` filters by `organization_id` column; returns `[]` for runs belonging to a different org (don't leak cross-org run existence).
- **Redaction-before-write** — `_redact_safe_metadata()` blanks known-secret keys (`token`, `secret`, `client_secret`, etc.) + token-blob values (Bearer prefix, JWT shape, long opaque credential). A `_SAFE_KEYS` whitelist (`redacted_view`, `granted_scopes`, etc.) skips the token-blob scan because those are the canonical redacted form, not raw credentials.

### Migration 009

Creates `run_trace_events` table with 3 indexes:
- `ix_run_trace_events_run_id` — point lookup by run_id (the primary access pattern for `GET /api/runtime/runs/{run_id}/trace`)
- `ix_run_trace_events_org_created` — org-scoped audit queries ("all traces for org X in the last hour")
- `ix_run_trace_events_agent_id` — per-agent analysis

### Org-scoped API

`GET /api/runtime/runs/{run_id}/trace` now reads from the configured store. Adds `org_id = get_request_tenant(request)` and calls `store.get_run_scoped(run_id, org_id)`. Returns 404 when org mismatch (don't leak cross-org run existence).

## Verification steps

- [x] V1: `DbRunTraceStore.append` + `get_run` round-trip — passes (`test_db_store_append_and_get_run`)
- [x] V2: Unknown run_id returns `[]` (not 404 at store layer) — passes (`test_db_store_unknown_run_returns_empty`)
- [x] V3: Org-scoped read filters cross-org — passes (`test_db_store_org_scoped_filters_cross_org`)
- [x] V4: Secret keys blanked before DB insert — passes (`test_db_store_redaction_blanks_secret_keys`)
- [x] V5: Token-blob values blanked before DB insert — passes (`test_db_store_redaction_blanks_token_blob`)
- [x] V6: API returns 404 for cross-org run (no leak) — passes (`test_api_returns_404_for_cross_org_run`)
- [x] V7: API returns 200 for same-org run — passes (`test_api_returns_200_for_same_org_run`)

## PASS/FAIL criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| DbRunTraceStore persistence works | PASS | V1, V2 |
| Org-scoped query works | PASS | V3, V6, V7 |
| Redaction-before-write enforced | PASS | V4, V5 |
| In-memory fallback preserved | PASS | `settings.RUNTRACE_STORE == "memory"` path covered by existing tests |
| No regression in RunTrace tests | PASS | 42/42 agent_runtime tests pass |

## Known limitations

- Sync DB writes are fire-and-forget (the test sweep confirms correctness; Phase 4 can add synchronous mode if audit trace needs stronger durability guarantees).
- The redaction scan uses a heuristic for token-blob detection (`_is_token_blob`). Long opaque credentials (≥40 chars, alphanumeric+dash/underscore) get blanked — this is intentional (defensive). The `_SAFE_KEYS` whitelist protects canonical redacted forms like `redacted_view`.

## Cross-reference

- Phase 3-D Task 4 (RunTrace in-memory) — preserved as `RunTraceStore` concrete class.
- Phase 3-D2 Task 2 (Complete Trace Emission) — depends on Task 1 persistence layer.
