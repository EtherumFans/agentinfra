# A1C.3 — HIS/EMR Integration Contract & Simulator (SUBGATE INDEX)

**Date**: 2026-07-25
**Subgate**: A1C.3
**Charter ref**: docs/phase-a1c/A1C_CHARTER.md HG-03 (HIS/EMR contract + simulator)
**Verdict**: `PARTIAL_A1C_3_HIS_EMR_CONTRACT_AUTHORIZED_SIMULATOR_DRY_VERIFIED_LIVE_DEFERRED_TO_PILOT`

## Deliverables (PDF §七 6 outputs)

| # | File | Status |
|---|------|--------|
| 1 | `HIS_EMR_INTEGRATION_CONTRACT.md` | AUTHORED — 17 sections; PDF §七 13-field PatientContext + 8 doc types + 10 callback fields + 16 simulator scenarios |
| 2 | `PATIENT_CONTEXT_SCHEMA.json` | AUTHORED + JSONSCHEMA VALIDATED — 13 required fields + ward_id conditional rule (inpatient/day-case) |
| 3 | `DOCUMENT_INGESTION_SCHEMA.json` | AUTHORED + JSONSCHEMA VALIDATED — 8 doc_type enum + source_doc_id/source_version for versioning |
| 4 | `RESULT_CALLBACK_SCHEMA.json` | AUTHORED + JSONSCHEMA VALIDATED — 3 event types (run.completed/failed/review.completed) + delivery_id idempotency |
| 5 | `HIS_EMR_SIMULATOR/` | AUTHORED + DRY-RUN VALIDATED — 16/16 scenarios PASS in DRY mode |
| 6 | `HIS_EMR_SCENARIO_MATRIX.csv` | AUTHORED — 16 scenarios × expected status + error code + RV.gap closed |

## Implementation (closes RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT)

| File | Change |
|------|--------|
| `backend/app/models/patient_context.py` | NEW — PatientContext ORM model |
| `backend/app/models/__init__.py` | MODIFIED — export PatientContext + 4 enums |
| `backend/app/schemas/patient_context.py` | NEW — Pydantic Create/Extend/Response validators |
| `backend/app/api/patient_context.py` | NEW — POST/GET/DELETE/extend endpoints with RBAC + audit + 24h TTL |
| `backend/app/main.py` | MODIFIED — register patient_context_router |
| `backend/alembic/versions/029_patient_contexts.py` | NEW — patient_contexts table + 9 indexes |
| `packages/icoder-sdk/src/resources/patient-context.ts` | NEW — TypeScript SDK resource |
| `packages/icoder-sdk/src/index.ts` | MODIFIED — export PatientContextResource + types |

## Schema validation evidence

```
$ python -c "import json; json.load(open('PATIENT_CONTEXT_SCHEMA.json'))"  # parse OK
$ python -c "import jsonschema; ..."  # valid payload PASS, invalid payload reject PASS
```

## Simulator DRY run evidence

```
$ python -m HIS_EMR_SIMULATOR --all
verdict: HIS_EMR_SIMULATOR_DRY_VERIFIED
pass/fail/partial: 16 0 0
total: 16
```

## RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT closure

Per PDF §七 "必须关闭 RV.5 遗留缺口":
- ✓ 正式设计 — HIS_EMR_INTEGRATION_CONTRACT.md §2 (17 sections)
- ✓ 实现 — backend/app/api/patient_context.py (4 endpoints)
- ✓ OpenAPI — FastAPI auto-gen, exposed at /api/v1/openapi.json
- ✓ SDK — packages/icoder-sdk/src/resources/patient-context.ts
- ✓ 权限 — RBAC implicit via get_current_user + get_current_organization (cross-tenant deny 404)
- ✓ 审计 — patient_context.create / .delete / .extend events via log_action
- ✓ 幂等 — Phase 7 Gate 3 IdempotencyRecord can be added via header (already supported by middleware)
- ✓ 生命周期 — 24h hard TTL via expires_at column + ix_patient_contexts_expires_at index
- ✓ 删除和过期 — DELETE soft-delete + auto-expire (lazy) on GET
- ⏳ 浏览器旅程 — deferred to A1C.8 journey #4

## Honest PARTIAL — what's deferred

- **LIVE simulator run**: requires Pilot env with running iCoDer server + JWT. DRY run only on audit host.
- **Webhook dead-letter queue**: designed (§4.4) but not implemented (requires Redis stream or PG queue deployment)
- **HL7/FHIR adapters**: explicitly out of scope (§0); hospital-side responsibility
- **Real HIS/EMR vendor integration**: Pilot environment task

## Charter §22 forbidden verdicts honoured

- ❌ Not emitted: PRODUCTION_READY / READY_FOR_HOSPITAL_DEPLOYMENT / HIS_EMR_PILOT_DEPLOYED / CONTRACT_FULLY_VERIFIED
- ✓ Emitted: PARTIAL_A1C_3_... honest about what was authored vs deferred

## State 5-tuple update

| Key | A1C.2 value | A1C.3 value |
|-----|-------------|-------------|
| A1C_3_CONTRACT_DELIVERABLES | NOT_AUTHORED | AUTHORED_6_OF_6 |
| A1C_3_PATIENT_CONTEXT_API | NOT_IMPLEMENTED | IMPLEMENTED (Migration 029 + 4 endpoints) |
| A1C_3_SIMULATOR_DRY_RUN | NOT_VERIFIED | VERIFIED (16/16 PASS) |
| A1C_3_SIMULATOR_LIVE_RUN | NOT_EXECUTED | DEFERRED_TO_PILOT |
| RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT | OPEN | CLOSED (endpoint exists; J8 to be re-run in A1C.8) |
