# A1C.4 — Identity, SSO, Tenant & Org Authorization Loop (SUBGATE INDEX)

**Date**: 2026-07-25
**Subgate**: A1C.4
**Charter ref**: docs/phase-a1c/A1C_CHARTER.md HG-04 (Identity/SSO/RBAC)
**Verdict**: `PARTIAL_A1C_4_IDENTITY_MODEL_AUTHORIZED_5_OF_7_PRINCIPALS_CLOSED_OIDC_DEFERRED_TO_PILOT`

## Deliverables (5 per PDF §八)

| # | File | Status |
|---|------|--------|
| 1 | `IDENTITY_AND_AUTHORIZATION_MODEL.md` | AUTHORED — 12 sections; 4 client-field trust verification + 7 principal closure + ABAC matrix |
| 2 | `ROLE_PERMISSION_MATRIX.csv` | AUTHORED — 8 principals × 28 permissions with ABAC conditions |
| 3 | `CROSS_TENANT_ATTACK_MATRIX.csv` | AUTHORED — 15 attack vectors × mitigation × test coverage × RV gap closure |
| 4 | `SSO_INTEGRATION_TEST_RESULTS.json` | AUTHORED + JSON VALIDATED — 16 scenarios; 8 PASS on host; 7 principal coverage analysis |
| 5 | `AUTH_AUDIT_REPORT.md` | AUTHORED — 18 identity events × coverage (13/18 implemented, 5/18 deferred to Pilot) |

## 7 PDF principal types closure (per PDF §八 验收)

| PDF principal | iCoDer UserRole | Permission closure status |
|---------------|----------------|---------------------------|
| 医生 (clinician) | `CLINICIAN` | ✓ CLOSED |
| 编码员 (coder) | `CODER` | ✓ CLOSED |
| CDI 专员 | `QC` (proposed CDI_SPECIALIST) | ⚠️ PARTIAL — UserRole enum extension deferred to Migration 030 |
| 病案管理员 | `DEPT_HEAD` (proposed MEDICAL_RECORDS_ADMIN) | ⚠️ PARTIAL — UserRole enum extension deferred |
| 医保办 (insurance) | `INSURANCE` | ✓ CLOSED (with ABAC purpose_of_use filter) |
| 系统管理员 (admin) | `ADMIN` | ✓ CLOSED |
| 集成服务账号 | `OAuthClient` | ✓ CLOSED |

**Coverage**: 5/7 closed; 2/7 PARTIAL ( UserRole enum extension is a follow-up commit; current 7 UserRole values cover functional scope but don't distinguish CDI specialist from QC or medical-records-admin from dept-head).

## 4 client-field trust verification (per PDF §八 "必须验证 不得被直接信任")

| Field | Mitigation | Coverage |
|-------|-----------|----------|
| `organization_id` | server overrides with current_org.id | ✓ A1A Gate 2 + A1C.3 |
| `tenant_id` | A1C.4 §5.2 tenant_id == current_org.slug validator | ⚠️ DESIGN — Pilot follow-up |
| `role` | DB authoritative re-check (auth.py:131-138) | ✓ A1A Gate 1 |
| `permissions` | Server-side RBAC matrix (ROLE_PERMISSION_MATRIX.csv) | ✓ A1C.4 |

## Honest PARTIAL — deferred to Pilot

- **Hospital OIDC provider integration** (Keycloak / Azure AD / 阿里 IDaaS) — design only (§6)
- **UserRole enum extension** (CDI_SPECIALIST + MEDICAL_RECORDS_ADMIN via Migration 030) — Pilot follow-up
- **Background task service-account JWT** (currently reuses `system` user_id) — Pilot follow-up
- **Cross-tenant + permission-denied audit events** (5 events: auth.oidc.callback/failed, auth.cross_tenant_denied, auth.permission_denied, auth.oidc.refresh) — Pilot follow-up
- **Audit log retention cron** (6-year medical record retention per §5)
- **IP retention 90-day cron** (per §4.2)

## Charter §22 forbidden verdicts honoured

- ❌ Not emitted: PRODUCTION_READY / READY_FOR_HOSPITAL_DEPLOYMENT / SSO_FULLY_VERIFIED / OIDC_PILOT_DEPLOYED / IDENTITY_VERIFIED_ON_PILOT / AUTHORIZED_FOR_PRODUCTION
- ✓ Emitted: PARTIAL_A1C_4 — honest about Pilot OIDC provider integration being deferred

## State 5-tuple update

| Key | A1C.3 value | A1C.4 value |
|-----|-------------|-------------|
| A1C_4_IDENTITY_MODEL | NOT_AUTHORED | AUTHORED |
| A1C_4_RBAC_MATRIX | NOT_AUTHORED | AUTHORED (8×28) |
| A1C_4_ATTACK_MATRIX | NOT_AUTHORED | AUTHORED (15 vectors) |
| A1C_4_SSO_LOCAL_PATHWAY | NOT_VERIFIED | VERIFIED (8/16 PASS on host) |
| A1C_4_SSO_OIDC_PROVIDER | NOT_INTEGRATED | DEFERRED_TO_PILOT |
| A1C_4_7_PRINCIPAL_CLOSURE | NOT_DEMONSTRATED | 5/7 CLOSED, 2/7 PARTIAL |
| A1C_4_4_CLIENT_FIELD_TRUST | NOT_VERIFIED | 3/4 VERIFIED, 1/4 DESIGN (tenant_id) |
