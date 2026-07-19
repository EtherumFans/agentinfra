# Phase A1A Gate 3R.2 — Material Audit Emit Wiring

**Date**: 2026-07-19
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 3R.1 (`A1A_GATE3R_1_AUTHORITATIVE_RUN_RESOLVER.md`)

Closes charter §3R.2 carry-over: the 11 audit actions declared in
the Gate 3.6 allowlist with no material emit sites.

After Gate 3R.2, every action in the allowlist either:
- has an emit site (tenant-scope, written via ``log_action``), OR
- has an explicit DEFERRED / N/A annotation in this report.

---

## §1. Action emit matrix

| Action | Scope | Emit site | Status |
|---|---|---|---|
| `run.cancel` | tenant | `app/api/runs.py::cancel_run` (after `request_cancel` succeeds) | ✅ wired |
| `run.complete` | tenant | `app/api/agent_run.py` (after `_persist_run_history`, COMPLETED branch) | ✅ wired |
| `run.failed` | tenant | `app/api/agent_run.py` (after `_persist_run_history`, FAILED branch) | ✅ wired |
| `idempotency.dedup` | tenant | `app/services/idempotency_service.py::acquire_or_replay` (replay branch) | ✅ wired |
| `api_client.rotate` | tenant | `app/api/platform_api_clients.py::rotate_secret` (after secret hash updated) | ✅ wired |
| `run.timeout` | (future) | — | ⚠️ **DEFERRED** (see §3) |
| `context.clear` | (future) | — | ⚠️ **N/A per charter §3.6** (see §4) |
| `security_admin.access` | system | `app/services/system_audit.py` (existing) | ✅ preserved |
| `sse.denied.*` | system | `app/api/runs.py::stream_run_events` (existing + Gate 3R.1) | ✅ preserved |
| `trace.read.denied.*` | system | `app/api/runs.py` + `app/api/run_trace.py` (existing + Gate 3R.1) | ✅ preserved |
| `sse.denied.orphan_run` | system | `app/api/runs.py::stream_run_events` (Gate 3R.1) | ✅ preserved |
| `trace.read.denied.orphan_run` | system | `app/api/runs.py::get_run_trace_partner` + `app/api/run_trace.py::_get_run_trace_impl` (Gate 3R.1) | ✅ preserved |

---

## §2. Tenant-scope emit pattern

All tenant-scope emits use ``app.middleware.audit.log_action`` with
the actor's ``organization_id``:

```python
from app.middleware.audit import log_action
await log_action(
    db,
    user_id=<actor user_id or None>,
    username=<actor username or None>,
    action=<action name>,
    resource_type=<"run_history" | "idempotency_record" | "oauth_client">,
    resource_id=<id>,
    details={<event-specific fields>},
    organization_id=<actor's org>,
)
await db.commit()
```

The row is written with ``organization_id`` populated and
``tenancy_classification = MODERN`` (via ``classify_modern_write``),
so it appears in the tenant's audit dashboard but is invisible to
other tenants (Gate 3.2 visibility filter).

The ``allow_null_org`` flag is NOT set — tenant-scope emits must
always carry a non-NULL org in cloud mode. In dev mode
(``ICODER_DEPLOYMENT_MODE != cloud``) the fail-closed guard permits
NULL org for backwards-compat with single-tenant fixtures.

### §2.1 Best-effort semantics

Every emit is wrapped in ``try / except`` with ``logger.warning`` /
``logger.error`` on failure. An audit emit failure MUST NEVER
downgrade a successful business operation to a 500. The tenant's
request succeeds even if the audit row couldn't be written (the
DB might be transiently unavailable, or the audit table might be
locked).

---

## §3. ``run.timeout`` DEFERRED

The ``run.timeout`` action is in the allowlist but has no emit site
today. Reason: there is no agent-run timeout watchdog.

The existing ``runtime_timeout_task`` in ``app/main.py`` checks the
``runtime_registry`` for stale **state-machine** cases (Phase 3-C0
concept), not agent runs. Agent runs currently rely on the SDK's
90s HTTP timeout, which surfaces as a generic provider error — not
a distinct "timeout" event the backend can audit.

Implementation required before ``run.timeout`` can be wired:

1. A background task that scans ``run_history`` for
   ``status IN (PENDING, RUNNING) AND created_at < now() - threshold``
2. A new ``RunStatus.TIMED_OUT`` state (or reuse ``FAILED`` with a
   ``timeout`` reason marker)
3. The watchdog emits ``run.timeout`` when it transitions a row

This is non-trivial and out of scope for Gate 3R.2. The action
remains in the allowlist so the future emit site doesn't need to
modify the classifier.

---

## §4. ``context.clear`` N/A per charter §3.6

The ``context.clear`` action is in the allowlist but has no backend
emit site, and never will. Reason: Phase 6 Gate 2 patient context
is a **widget-level** concept (``patient.context.cleared`` /
``session.cleared`` events fire in the browser, not the backend).

The backend has no DB row representing "current patient context"
because context is intentionally **in-memory only** (Phase 6
constraint: PHI doesn't persist server-side beyond the run).

The allowlist entry remains for the case where a future server-side
context store is added (e.g. a session-scoped cache for multi-turn
conversations). That work is not currently planned.

---

## §5. ``idempotency.dedup`` service-layer emit

The dedup emit lives in ``app.services.idempotency_service.acquire_or_replay``
(service layer), NOT at the API layer. Reason: any caller of the
service (HTTP ``/api/v1/agents/{id}/run``, A2A ``message/send``,
programmatic callers in tests) should get the emit. Putting it in
the API layer would miss non-HTTP callers.

The service layer doesn't have access to the actor's ``user_id``;
the emit therefore writes ``user_id=None``. The actor's identity is
preserved on the ``run_history`` row that the eventual run writes
(``record_run_start`` captures ``user_id``). The audit row's
``resource_id`` points to the ``idempotency_records.id``, so the
two can be joined for forensic analysis.

---

## §6. Test results

```
tests/test_api/test_a1a_gate3r_2_audit_emit_wiring.py    7 passed

  §1 run.cancel
    test_run_cancel_emits_audit                            1
    test_run_cancel_audit_carries_outcome                  1
    test_run_cancel_not_found_does_not_emit                1

  §2 idempotency.dedup
    test_idempotency_dedup_emits_on_replay                 1

  §3 api_client.rotate
    test_api_client_rotate_emits_audit                     1

  §4 Allowlist invariants
    test_run_lifecycle_actions_in_allowlist                1
    test_legacy_classifier_recognizes_lifecycle_actions    1
                                                          ──
                                                          7 passed
```

### §6.1 Regression sweep

```
tests/test_api/test_phase7_gate3_agent_run_idempotency.py    14 passed
tests/test_api/test_phase7_gate4_run_cancel.py                7 passed
tests/test_api/test_phase7_gate5_api_clients.py              15 passed
tests/test_api/test_phase7_gate7_trace_token.py              13 passed
tests/test_api/test_phase7_gate9_sse_run_events.py           10 passed
tests/test_api/test_a1a_gate3_5_console_trace_isolation.py   11 passed
tests/test_api/test_a1a_gate3_4_sse_tenant_isolation.py       7 passed
tests/test_api/test_a1a_gate3r_1_orphan_run_denial.py        12 passed
                                                            ──
                                                            89 passed
```

No regressions.

### §6.2 Test fixture updates for Gate 3R.1 compatibility

Two existing test files were updated to seed an authoritative
``run_history`` row alongside trace events — Gate 3R.1's orphan-run
guard otherwise refuses trace reads that previously fell through:

- ``tests/test_api/test_phase7_gate7_trace_token.py``
  ``test_get_trace_with_valid_token_returns_timeline``: now inserts
  a MODERN ``run_history`` row for ``run-abc``.

- ``tests/test_api/test_phase7_gate9_sse_run_events.py``
  ``_seed_events`` helper: now seeds a MODERN ``run_history`` row
  alongside trace events; ``_clear_events`` removes both.

These updates reflect the new contract: trace reads require an
authoritative ``run_history`` row (Gate 3R.1).

---

## §7. Charter §3R.2 requirements — closure

| Charter §3R.2 item | Status |
|---|---|
| Wire ``run.cancel`` emit | ✅ |
| Wire ``run.complete`` emit | ✅ |
| Wire ``run.failed`` emit | ✅ |
| Wire ``idempotency.dedup`` emit | ✅ |
| Wire ``api_client.rotate`` emit | ✅ |
| Mark ``run.timeout`` deferred with reason | ✅ §3 |
| Mark ``context.clear`` N/A with reason | ✅ §4 |
| Tenant-scope emits use ``log_action`` | ✅ |
| Service-layer dedup emit covers all callers | ✅ §5 |
| Best-effort semantics (no audit failure → 500) | ✅ §2.1 |

---

## §8. Forbidden list — re-confirmation

Charter §22 forbidden verdicts remain forbidden; this gate does NOT
issue any of them.

Forbidden actions NOT taken in this gate:

- No ``git push`` (local-only branch)
- No PR opened
- No master commit
- No amend of Gate 3 commit (``d1447f3``) or Gate 3R.1 work
- No new Agent / Expert / Tool / Runtime added
- No Medical Coding / CDI prompt changes
- No ``git add -A`` (explicit file list in Gate 3R.9)
- No falsification of historical data

---

## §9. Verdict

```
PASS_A1A_GATE3R_2_MATERIAL_AUDIT_EMIT_WIRING_VERIFIED
```

Forbidden verdicts (charter §22) remain forbidden.

Gate 3R.3 (Trace capture status semantics + deployment profiles)
follows.
