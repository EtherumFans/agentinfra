# Auth Audit Report — iCoDer Pilot Entry

**Phase**: A1C.4
**Date**: 2026-07-25
**Scope**: A1C.4 §9 audit coverage of identity events + review of A1A Gate 2/3 audit infrastructure reuse for HIS/EMR Pilot.

---

## §1 Audit infrastructure (existing — A1A Gate 2/3)

### 1.1 AuditLog model

`backend/app/models/audit_log.py`:
- `id` VARCHAR(12) PK
- `organization_id` FK to organizations (NOT NULL — A1A Gate 2 Migration 016 backfill)
- `user_id` VARCHAR(12) (nullable for system events)
- `action` String(64) — e.g. `auth.login`, `patient_context.create`
- `resource_type` String(64)
- `resource_id` String(64)
- `ip_address` String(45) (IPv6-capable)
- `metadata_` JSON
- `created_at` DateTime server_default now()

### 1.2 Audit emit pipeline

- `log_action(db, user_id, username, action, resource_type, resource_id, ip_address, details=None, allow_null_org=False)` (backend/app/middleware/audit.py)
- A1A Gate 2 fix: `allow_null_org=False` default closes F03 (17 callers skipping org_id)
- A1A Gate 3: `system_audit.py` allowlist (close F04/F05 boolean escape hatch)

---

## §2 Identity-event audit coverage (per A1C.4 §9)

| Event | Action string | Emit location | Coverage status |
|-------|--------------|---------------|----------------|
| Login success | `auth.login` | `backend/app/api/auth.py:login()` | ✓ PASS |
| Login failed | `auth.login_failed` | `backend/app/api/auth.py:login()` | ✓ PASS |
| Token revoked (token_version increment) | `auth.token_revoked` | `backend/app/api/auth.py:logout()` | ✓ PASS |
| Single-token blacklist (TokenBlacklist.jti) | `auth.jti_blacklisted` | `backend/app/api/auth.py:logout()` | ✓ PASS |
| OIDC callback success | `auth.oidc.callback` | DESIGN — A1C.4 §6 endpoint (Pilot) | ✗ DESIGN (Pilot) |
| OIDC callback failure | `auth.oidc.callback_failed` | DESIGN — Pilot | ✗ DESIGN (Pilot) |
| OIDC refresh | `auth.oidc.refresh` | DESIGN — Pilot | ✗ DESIGN (Pilot) |
| OAuth client_credentials grant | `oauth.client_credentials_grant` | `backend/app/api/oauth.py` | ✓ PASS (Phase 7 Gate 5) |
| Patient context create | `patient_context.create` | `backend/app/api/patient_context.py:create_patient_context()` | ✓ PASS (A1C.3) |
| Patient context delete | `patient_context.delete` | `backend/app/api/patient_context.py:delete_patient_context()` | ✓ PASS (A1C.3) |
| Patient context extend | `patient_context.extend` | `backend/app/api/patient_context.py:extend_patient_context()` | ✓ PASS (A1C.3) |
| Cross-tenant deny | `auth.cross_tenant_denied` | DESIGN — Pilot (A1C.4 §3 CT-01) | ✗ DESIGN (Pilot) |
| Permission denied | `auth.permission_denied` | DESIGN — Pilot (A1C.4 §3 CT-02) | ✗ DESIGN (Pilot) |
| API Key used | `api_key.used` | `backend/app/api/keys.py` | ✓ PASS |
| API Key rotated | `api_key.rotated` | `backend/app/api/keys.py` | ✓ PASS |
| OAuth client created | `oauth_client.created` | `backend/app/api/platform_api_clients.py` | ✓ PASS (Phase 7 Gate 5) |
| Preview session created | `preview_session.created` | `backend/app/api/preview_sessions.py` | ✓ PASS (Gate 13A) |
| Preview session exchanged | `preview_session.exchanged` | `backend/app/api/preview_sessions.py` | ✓ PASS (Gate 13A) |

**Coverage tally**: 13/18 ✓ implemented; 5/18 DESIGN deferred to Pilot (OIDC + cross_tenant + permission_denied).

---

## §3 Audit log integrity

### 3.1 INSERT path (A1A Gate 3R — DbRunTraceStore pattern)

- AuditLog INSERT goes through `log_action` → `db.add()` → flush
- A1A Gate 3R trace_capture_status state machine ensures emit failure surfaces loudly (not silent)

### 3.2 Read path (system_audit.py allowlist)

- `system_audit.py` allowlist gates which audit_action values can be logged without org_id
- A1A Gate 3 closure: `log_action allow_null_org=True` escape hatch closed (only `run_lifecycle.*` actions still allowed null_org for system events)

### 3.3 Tamper evidence

- AuditLog 没有 hash chain (one-way INSERT-only). **GAP**: Pilot 启动前应考虑区块链锚定或 signed sequence (DESIGN — Pilot enhancement)

---

## §4 Privacy & PHI in audit log

### 4.1 当前 redaction (A1A Gate 4)

- `audit_detail_redactor.py` 自动 redacts:
  - patient_id (含 EMPI)
  - 手机 / 邮箱 / 身份证
  - 详细地址
  - 病历原文片段 (超过 N 字符)
- 审计 metadata JSON 在 `log_action` 调用前已 redacted

### 4.2 IP address (审计列)

- IP 存储在 AuditLog.ip_address — 不属于 PHI 但属于个人数据 (GDPR/PIPL)
- 中国 PIPL: IP 属于个人信息,需在隐私政策中告知
- Pilot 启动前应 (a) 评估 IP 是否进入审计列 (b) 设置 IP 保留期 (建议 90 天)

---

## §5 Audit log retention

| 数据 | 保留期 | 法规依据 | 实现 |
|------|-------|---------|------|
| AuditLog | 6 年 (医疗法规) | 《医疗机构病历管理规定》 + 《数据安全法》 | DESIGN — Pilot 实现 cron 删除 |
| TokenBlacklist | 90 天 (JWT exp + 1 月) | 内部安全策略 | ✓ 已实现 (Phase 7 cron) |
| OAuthToken | 30 天 | OAuth 2.0 RFC 6749 | ✓ 已实现 |
| PreviewSession | 24h | Phase 7 Gate 13A | ✓ 已实现 (Phase 7) |
| PatientContext | 24h | A1C.3 §2.3 | ✓ 已实现 (A1C.3) |

---

## §6 Charter §22 forbidden verdicts honoured

未输出 AUDIT_VERIFIED_ON_PILOT / AUDIT_TRAIL_IMMUTABLE / PHI_LEAK_ZERO_VERIFIED (后者属 A1C.6 范围)。Honest PARTIAL。

---

## §7 Verdict

**AUTH_AUDIT_COVERAGE_VERIFIED_13_OF_18_OIDC_AND_PERMISSION_DENIED_DEFERRED_TO_PILOT**:

- 13/18 identity events 已在代码中 emit (登录/登出/token 撤销/Patient Context CRUD/OAuth/Preview/API Key)
- 5/18 events 设计完成,实现延后到 Pilot OIDC 真实对接 (含 `auth.oidc.callback` / `auth.cross_tenant_denied` / `auth.permission_denied`)
- A1A Gate 2/3 基础设施可复用,无需新建模型

**Pilot 启动前必须补**:
1. 实现 `auth.oidc.callback` + `auth.oidc.callback_failed` emit (A1C.4 §6 endpoint)
2. 实现 `auth.cross_tenant_denied` emit 在 patient_context.get/delete cross-tenant 404 路径 (defense-in-depth; 不向客户端泄露)
3. 实现 `auth.permission_denied` emit 在 RBAC 拒绝路径 (CT-02)
4. IP 保留期 90 天 cron (§4.2)
5. AuditLog 6 年保留期 cron (§5)
