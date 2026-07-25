# A1C.6 — Audit Completeness Report

**Phase**: A1C.6
**Date**: 2026-07-25
**Scope**: PDF §十 12 mandatory audit fields × every key operation × static + dynamic verification.

---

## §1 PDF §十 12 mandatory audit fields — coverage matrix

| # | Field | AuditLog column / source | Emit path | Coverage |
|---|-------|--------------------------|-----------|----------|
| 1 | **actor** | `user_id` + `username` + `agent_id` + `delegated_by_user_id` | `audit_middleware` writes pre-INSERT; populated from JWT decode (Phase 7 Gate 5) | **PASS** — every authenticated route |
| 2 | **organization** | `organization_id` + `tenancy_classification` + `tenancy_attribution_*` | A1A Gate 2 fail-closed guard (4 surfaces) + A1A Gate 3R 7-class taxonomy | **PASS** — fail-closed denies NULL-org writes in cloud mode |
| 3 | **patient context** | `details.patient_context_id` + `details.encounter_id` + `details.patient_id_redacted` + `details.department_id` | A1C.3 patient_context API; `audit_detail_redactor` redacts raw patient_id | **PARTIAL** — patient_id REDACTED via regex; A1C.3 add `patient_context_id` field (NEW) |
| 4 | **action** | `action` (verb.dotted) | `log_action(actor, action, resource_type, resource_id, ...)` caller | **PASS** — 17 actions in `system_audit.py` allowlist (A1A Gate 3) |
| 5 | **purpose** | `details.purpose_of_use` (ABAC) | Phase 7 `request.state.purpose_of_use` (DESIGN) — currently RBAC only; ABAC deferred | **DESIGN** — RBAC honored; ABAC purpose_of_use emission NOT in every audit row |
| 6 | **resource** | `resource_type` + `resource_id` | `log_action` signature + caller-provided | **PASS** |
| 7 | **result** | `status` + `error_message` + `details.http_status_code` | audit_middleware captures response status; error_message via central exception handler (Phase 4-D) | **PASS** — 4 status literals (success/failure/warning/denied) |
| 8 | **timestamp** | `created_at` (TimestampMixin) | DB server-side `now()` (A1A Gate 3R Migration 020 server_default) | **PASS** |
| 9 | **trace_id** | `details.trace_id` (non-run) OR `run_trace.trace_id` FK | Phase 3 trace capture; `agent_run.start` stamps trace_id on run row | **PARTIAL** — present for agent_run actions; NULL for user.login (acceptable per PDF) |
| 10 | **source_ip** | `ip_address` | audit_middleware `request.client.host` | **PASS** — every HTTP-initiated audit; NULL for system cron (acceptable) |
| 11 | **client** | `user_agent` + `details.client_kind` + `details.api_client_id` + `details.sdk_version` | audit_middleware User-Agent header; api_clients.id from Phase 7 Gate 5 OAuth client_credentials | **PASS** — api_client_id populated for client_credentials; NULL for browser SPA (acceptable) |
| 12 | **policy_decision** | `details.decision` + `details.decision_reason` + `details.rbac_role` + `details.abac_purpose_match` + `details.tenant_match` | DESIGN — currently only emit on DENY (403/401); allow-side decision not consistently logged | **PARTIAL** — deny-side decisions logged via HTTPException; allow-side decisions deferred |

**Aggregate**: 7/12 PASS + 3/12 PARTIAL + 2/12 DESIGN

---

## §2 Key operations × audit emit — coverage matrix

| # | Key operation (PDF §十) | Audit emit point | Coverage | Evidence |
|---|------------------------|-----------------|----------|----------|
| 1 | User login (success) | `user.login` | PASS | backend/app/api/auth.py + audit_middleware |
| 2 | User login (failure / invalid_client) | `api_client.authentication_rejected` | PASS | A1A Gate 1 OAuth audit event |
| 3 | User logout | `user.logout` | PASS | auth.py logout route |
| 4 | Patient context create | `patient_context.create` | PASS (A1C.3 NEW) | backend/app/api/patient_context.py |
| 5 | Patient context delete / expire | `patient_context.delete` | PASS (A1C.3 NEW) | patient_context.py + 24h TTL cron |
| 6 | Document submit (PHI write) | `documents.submit` | PASS | documents.py + phi_encryption pre-INSERT |
| 7 | Agent run start | `agent_run.start` | PASS | agent_run.py + trace_capture_status=CAPTURE_PENDING |
| 8 | Agent run complete | `agent_run.complete` | PASS | agent_run.py + CAPTURED_COMMITTED |
| 9 | Coding review generate | `review.generate` | PASS | reviews.py |
| 10 | Code confirm / reject | `code.confirm` / `code.reject` | PASS | reviews.py |
| 11 | Preview session created | `preview_session.created` | PASS (Phase 7 Gate 13A) | preview.py |
| 12 | API client secret rotated | `api_client.secret_rotated` | PASS (Phase 7 Gate 5) | clients.py |
| 13 | Webhook delivery succeed / fail | `webhook.delivered` / `webhook.dead_lettered` | DESIGN | A1C.3 RESULT_CALLBACK_SCHEMA — queue delivery events not yet wired to audit |
| 14 | Cross-tenant access denied | `tenant_isolation.violation_denied` | PASS | tenant_read_policy visibility filter (A1A Gate 3R) |
| 15 | Background cron run | `cron.<job_name>.executed` | PARTIAL | retention.py + cleanup_orphan_runs.py emit only on failure |

---

## §3 Static analysis — every route decorated with audit

### 3.1 Audit middleware coverage

```python
# backend/app/middleware/audit.py (Phase A1A Gate 2 + Gate 3)
async def audit_middleware(request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if response.status_code < 500:
            log_action(
                actor=user_id_from_request(request),
                organization_id=request.state.organization_id,
                action=derive_action_name(request),
                ...
            )
    return response
```

**Verified via**: `backend/tests/audit/test_audit_emit_path.py` (A1A Gate 2 §F-012).

### 3.2 Fail-closed guard (4 write surfaces)

A1A Gate 2 §3 fail-closed guard fires BEFORE `log_action` writes:

| Surface | Guard call |
|---------|------------|
| `record_run_start` | `assert_not_cloud_or_has_org_id(...)` |
| `log_action` | `assert_not_cloud_or_has_org_id(...)` |
| `acquire_or_replay` (idempotency) | `assert_not_cloud_or_has_org_id(...)` |
| `create_preview_session` | `assert_not_cloud_or_has_org_id(...)` |

**Result**: NULL-organization audit writes impossible in cloud mode (`ICODER_DEPLOYMENT_MODE=cloud`).

### 3.3 PHI redaction pre-INSERT

`audit_detail_redactor.redact(details_dict)` is called in `audit_middleware` BEFORE `db.add(audit_log)`. Patterns verified in `REDACTION_TEST_RESULTS.json` §surface_coverage.logs.

---

## §4 Dynamic injection test — DEFERRED TO PILOT

PDF §十 requires "每次关键操作至少记录" — the static analysis above covers emit paths; the dynamic injection test (run a synthetic operation, query audit_logs table, assert all 12 fields populated) requires a live stack. This is **deferred to Pilot** per Charter §22 forbidden verdicts (PHI_BOUNDED / REDACTION_FULLY_VERIFIED not emit-able without runtime evidence).

**Pilot required actions**:

1. **Pilot env e2e audit injection**: Execute 15 key operations (login + patient_context.create + documents.submit + agent_run + ...); query `SELECT * FROM audit_logs WHERE created_at > now() - interval '1 hour'`; assert all 12 mandatory fields populated for every row.
2. **Pilot env ABAC purpose_of_use emission**: Wire `request.state.purpose_of_use` through to `audit_log.details.purpose_of_use` for every route.
3. **Pilot env policy_decision allow-side emission**: Emit `decision=allow` row for every successful authorized action (currently only deny-side emitted).
4. **Pilot env webhook delivery audit**: Wire `webhook.delivered` + `webhook.dead_lettered` to `log_action`.
5. **Pilot env cron success audit**: Emit `cron.<name>.executed` on every cron run (currently only failures).

---

## §5 Charter §22 forbidden verdicts honoured

This report does NOT emit:
- ❌ `AUDIT_COMPLETELY_VERIFIED` — would require dynamic injection test, deferred to Pilot
- ❌ `ALL_ACTIONS_AUDITED` — PDF §十 "每次关键操作" runtime assertion deferred
- ❌ `PRODUCTION_READY` — Charter §22 forbids
- ❌ `HOSPITAL_PILOT_DEPLOYED` — Charter §22 forbids

This report DOES emit (only):
- `PARTIAL_A1C_6_AUDIT_SCHEMA_AUTHORED_STATIC_ANALYSIS_VERIFIED_DYNAMIC_INJECTION_DEFERRED_TO_PILOT`

---

## §6 Verdict

**Coverage**: 12/12 mandatory fields have an AuditLog column mapping; 7/12 fully implemented; 5/12 partially implemented or DESIGN-only.

**Charter §22 honoured**: Forbidden verdicts not emitted; honest PARTIAL recorded.

**Pilot carry-forward**: 5 pilot_required_actions (above) tracked in `reports/phase-a1c/A1C.6/REDACTION_TEST_RESULTS.json:pilot_required_actions` + `reports/phase-a1c/A1C.9/PILOT_CARRY_FORWARD.md` (to be authored in A1C.9).
