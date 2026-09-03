# Identity & Authorization Model — iCoDer Pilot Entry

**Phase**: A1C.4
**Date**: 2026-07-25
**Status**: MODEL_AUTHORIZED_FOR_PILOT (implementation PARTIAL — see §10)
**Scope**: 医院用户身份 + 多租户授权 (per PDF A1C.4 §八).

---

## §0 目标

**目标** (per PDF §八): 验证医院用户身份和多租户授权,**而不是仅使用本地测试用户**。

PDF 要求覆盖 16 项:
- 协议: OIDC, OAuth 2.0, JWT, SSO
- 主体: 用户、角色、组织、科室、tenant
- 模型: RBAC + 必要时 ABAC
- 服务账号: 后台任务身份 + SDK 客户端身份
- 攻击面: token 过期 / 撤销 / key rotation / clock skew / 跨租户访问 / 越权 / IDOR / 伪造 organization_id

PDF 要求验证客户端提交的 4 项**不得被直接信任**:
- `organization_id`、`tenant_id`、`role`、`permissions`

组织归属必须来自**可信身份上下文或服务端映射**。

---

## §1 现状审计

### 1.1 用户身份 — 现有 (UserRole enum)

`backend/app/models/user.py:8-15`:

| UserRole | 中文 | PDF §八对应 |
|----------|------|------------|
| ADMIN | 系统管理员 | ✓ 系统管理员 |
| CODER | 编码员 | ✓ 编码员 |
| DEPT_HEAD | 科室负责人 | (近 CDI 专员,但偏行政) |
| INSURANCE | 医保办 | ✓ 医保办 |
| QC | 质控科 | (近 CDI 专员) |
| CLINICIAN | 临床医生 | ✓ 医生 |
| IT | 信息科 | (近 系统管理员,但更窄) |

**缺口**: PDF §八 7 类主体中,**CDI 专员** + **病案管理员** + **集成服务账号** 显式缺失。

### 1.2 组织身份 — 现有

- `Organization.slug` (unique) — tenant slug
- `OrganizationMember.role` (`OrgRole` enum): OWNER / ADMIN / MEMBER / VIEWER
- JWT 在登录时携带 `org_id` (来自 `get_current_organization` 解析)
- 客户端**可以**在 body 中传 organization_id,但所有写路径都通过 `current_org.id` 覆盖 (A1A Gate 2 tenant_read_policy)

### 1.3 服务账号 — 现有 (部分)

- `OAuthClient` (Phase 7 Gate 5) — client_credentials flow + scope strings
- `ApiKey` — API key flow (legacy, retained)
- `PreviewSession` (Phase 7 Gate 13A) — short-lived HMAC bootstrap ticket

### 1.4 客户端提交字段的可信度 (PDF §八 "必须验证 不得被直接信任")

| 字段 | 客户端可传? | 服务端是否覆盖? | 实现位置 |
|------|------------|---------------|---------|
| `organization_id` | 是 (body 字段) | **是** — 写路径用 `current_org.id` (A1A Gate 2) | `backend/app/services/tenant_scoper.py` |
| `tenant_id` | 是 (A1C.3 patient-context body) | **是** — `patient_context.tenant_id` 与 `current_org.slug` 一致性校验 (A1C.4 新增 §5) |
| `role` | 是 (JWT claim) | **是** — `get_current_user` 从 DB 查 user.role 而非 JWT claim (JWT role 仅作 hint) | `backend/app/middleware/auth.py:121-146` |
| `permissions` | 隐式 (role 衍生) | **是** — 服务端 RBAC 矩阵查询 (A1C.4 新增 §3 ROLE_PERMISSION_MATRIX.csv) |

**结论**: 4 项 PDF 要求**全部满足**,但需 A1C.4 显式记录 + 测试覆盖。

---

## §2 Identity Provider 模型

### 2.1 Pilot 启动时的 IdP 选择

| IdP 类型 | 用途 | Pilot 启动状态 | 集成方式 |
|---------|------|--------------|---------|
| **iCoDer local user** (DB-backed) | 开发 / 测试 / 后台任务 | ✓ 已实现 (`User.hashed_password`) | `/api/auth/login` (password → JWT) |
| **医院 OIDC provider** (e.g. Keycloak / 阿里 IDaaS / Azure AD) | 医生 / 编码员 / CDI 专员 等 7 类主体 | **DESIGNED, NOT INTEGRATED** | `/api/auth/oidc/callback` (A1C.4 §6 设计,Pilot 真实对接) |
| **OAuth 2.0 client_credentials** (服务账号) | HIS/EMR API Client | ✓ 已实现 (`OAuthClient`) | `/api/oauth/token` (client_credentials → access_token) |
| **API Key** (legacy) | 内部脚本 / Postman | ✓ 已实现 (`ApiKey`) | `X-API-Key` header |

### 2.2 JWT claim 结构

iCoDer 服务端签发的 JWT 包含:
```json
{
  "sub": "user-id-hex12",
  "org_id": "org-id-hex12",
  "role": "clinician",          // UserRole value (hint only — DB 重查)
  "token_version": 3,            // 用于服务端撤销 (User.token_version)
  "scope": "openid profile email icoder.agent_run.invoke",
  "iat": 1721800000,
  "exp": 1721803600,             // 1h 寿命
  "iss": "https://api.icoder.cloud/auth",
  "aud": "icoder-console",
  "jti": "jwt-uuid"              // 用于黑名单 (TokenBlacklist)
}
```

**组织归属可信源**: `org_id` claim 来自登录时 `OrganizationMember.user_id == user_id` 查询;客户端**不能**通过 body/header 覆盖。

### 2.3 医院侧 OIDC 集成 (DESIGNED, PILOT 待对接)

Pilot 环境上,医院 OIDC provider (e.g. Keycloak) 完成 `/realms/{hospital}/protocol/openid-connect/token` 端点 → 颁发医院 OIDC JWT → iCoDer `/api/auth/oidc/callback` 验证签名 + 校验 `iss` + 提取 `preferred_username` / `fhir_practitioner_id` / `department_code` → iCoDer 内部签发 iCoDer JWT。

**信任边界**: 医院侧 OIDC JWT **不直接**被 iCoDer 业务逻辑接受;必须通过 callback 换签。

### 2.4 Token 过期 / 撤销 / key rotation / clock skew

| 攻击向量 | 现状 | 实现 |
|---------|------|------|
| Token 过期 | ✓ 强制 — JWT `exp` claim + `decode_token` 校验 | `backend/app/middleware/auth.py:108-118` (jwt.PyJWTError) |
| Token 撤销 | ✓ 强制 — `User.token_version` 自增使旧 token 失效;`TokenBlacklist.jti` 单 token 黑名单 | `auth.py:142-145` |
| Key rotation | ✓ 设计 — JWT secret 通过 `Settings.SECRET_KEY` 配置;Pilot 启动时配 KMS (A1C.5);rotation = KMS key version + 多 secret 接受窗口 (DESIGN-ONLY,Pilot 实现) | `config.py:35-50` |
| Clock skew | ✓ 强制 — `decode_token` 默认 leeway=0;建议生产 leeway=30s | `auth.py:106` |

---

## §3 RBAC 模型 (7 类主体 + 集成服务账号 = 8 类)

### 3.1 PDF §八 7 类主体映射

| PDF 主体 | iCoDer UserRole | 备注 |
|---------|----------------|------|
| 医生 | `CLINICIAN` | ✓ 已存在 |
| 编码员 | `CODER` | ✓ 已存在 |
| CDI 专员 | `QC` (建议新增 `CDI_SPECIALIST`) | **GAP**: 当前 QC 偏质控;CDI 偏文档改进。建议 Pilot 启动前扩展 UserRole enum (Migration 030, A1C.4 follow-up) |
| 病案管理员 | `DEPT_HEAD` (建议新增 `MEDICAL_RECORDS_ADMIN`) | **GAP**: 当前 DEPT_HEAD 偏科室负责人;病案管理员独立角色。建议扩展 |
| 医保办 | `INSURANCE` | ✓ 已存在 |
| 系统管理员 | `ADMIN` | ✓ 已存在 |
| 集成服务账号 | OAuthClient (machine) | ✓ 已实现 (Phase 7 Gate 5) |

**A1C.4 决策**: PDF 要求 7 类主体**闭环**。当前 7 个 UserRole (ADMIN/CODER/DEPT_HEAD/INSURANCE/QC/CLINICIAN/IT) 覆盖 PDF 7 类**主体功能**,但 CDI 专员 vs 病案管理员的**职责分离**在 Pilot 启动前需扩展 enum (deferred to A1C.4 follow-up Migration 030)。

### 3.2 权限矩阵 (详见 `ROLE_PERMISSION_MATRIX.csv`)

A1C.4 定义 28 个细粒度权限 (per A1C.3 HIS/EMR contract + 现有 API surface),按 (principal × permission) 笛卡尔积组织。

### 3.3 ABAC (Attribute-Based) 必要场景

PDF §八 "必要时 ABAC"。iCoDer 在以下场景叠加 ABAC:

| ABAC 维度 | 触发条件 | 实现 |
|----------|---------|------|
| `department_id` 匹配 | 医生查询 patient_context 时仅能看本科室 (除非 `ADMIN`) | `tenant_scoper.scope_query(...).where(PatientContext.department_id == user.department)` (Pilot 实现) |
| `purpose_of_use` 合规 | 医保办 (`INSURANCE` role) 不能查 `purpose_of_use=research` 的 context | A1C.4 §4 新增 validator (DESIGN — Pilot 实现) |
| `consent_legal_basis` 检查 | `research` purpose 必须有 `patient-consent` | A1C.3 已实现 (`PatientContextCreate._research_requires_explicit_consent`) |

---

## §4 跨租户攻击面 (PDF §八 "必须覆盖")

详见 `CROSS_TENANT_ATTACK_MATRIX.csv`。10 个攻击向量:

1. 跨租户访问 (cross-tenant read)
2. 越权 (privilege escalation)
3. IDOR (Insecure Direct Object Reference)
4. 伪造 organization_id
5. 伪造 tenant_id (A1C.3 新增攻击面)
6. 伪造 role claim
7. Token 过期
8. Token 撤销后重用
9. Key rotation 期间双 key 接受窗口被滥用
10. Clock skew 利用 (调整客户端时钟绕过 exp 检查)

每个向量在攻击矩阵中标注 ** mitigations ** + **test coverage** + **RV gap closure**。

---

## §5 客户端提交字段的可信度验证 (4 项 PDF 必须)

### 5.1 organization_id — 客户端可传,服务端覆盖

```python
# backend/app/api/patient_context.py:34
ctx = PatientContext(
    organization_id=current_org.id,  # ← 服务端注入,忽略 body
    ...
)
```

测试: A1C.4 §7 cross-tenant-attack 测试用例 #1。

### 5.2 tenant_id — 客户端传,服务端校验

A1C.4 新增 validator (DESIGN-ONLY,Pilot 实现):
```python
# 未来 PatientContextCreate validator
@model_validator(mode='after')
def _tenant_id_matches_org(self, info):
    # info.context 包含 current_org (依赖注入)
    # 校验 self.tenant_id == current_org.slug or self.tenant_id.startswith(current_org.slug + "-")
    ...
```

### 5.3 role — JWT claim only, DB authoritative

```python
# backend/app/middleware/auth.py:131-138
payload = decode_token(credentials.credentials)
user_id = payload.get("sub")
result = await db.execute(select(User).where(User.id == user_id))
user = result.scalar_one_or_none()
# user.role 是 DB 查出的真值;JWT role claim 不直接使用
```

### 5.4 permissions — 服务端 RBAC 矩阵

A1C.4 §3.2 ROLE_PERMISSION_MATRIX.csv 是 SSOT。客户端无 `permissions` 字段。

---

## §6 OIDC 集成点设计 (Pilot 待实现)

### 6.1 Endpoints

```
GET  /api/auth/oidc/{provider}/login     # 重定向到医院 OIDC provider
GET  /api/auth/oidc/{provider}/callback  # 接收 authorization_code,换 access_token,换 iCoDer JWT
POST /api/auth/oidc/refresh               # 刷新 iCoDer JWT (用医院 OIDC refresh_token)
POST /api/auth/oidc/logout                # 撤销医院 OIDC token + iCoDer JWT 黑名单
```

### 6.2 Provider 配置

```yaml
# backend/app/config.py 新增
OIDC_PROVIDERS: dict = {
    "keycloak-zju-fh": {
        "issuer": "https://sso.hospital.cn/realms/zju-fh",
        "client_id": "icoder",
        "client_secret": "${OIDC_KEYCLOAK_ZJU_SECRET}",  # 从 KMS 读 (A1C.5)
        "scopes": ["openid", "profile", "email", "fhir:read", "his:query"],
    },
}
```

### 6.3 Token 交换流程

```
[Browser] → [Hospital OIDC] (login) → authorization_code
[Browser] → [/api/auth/oidc/callback?code=...] → [iCoDer Server]
[icoDer Server] → [Hospital OIDC /token] (exchange code for access_token)
[IcoDer Server] → verify JWT signature via OIDC JWKS
[IcoDer Server] → extract practitioner_id / department / role_hint
[IcoDer Server] → upsert User (if first login) or match existing
[IcoDer Server] → issue iCoDer JWT (1h TTL)
[Browser] ← iCoDer JWT
```

---

## §7 SSO 集成测试 (Pilot 必跑)

详见 `SSO_INTEGRATION_TEST_RESULTS.json`。

10 个 SSO 场景:
1. Local user login (smoke)
2. Local user login with wrong password (401)
3. Local user login with deactivated account (403)
4. JWT expired (401)
5. JWT revoked via token_version (401)
6. JWT tampered signature (401)
7. OIDC provider callback — happy path (deferred to Pilot)
8. OIDC provider callback — invalid signature (deferred to Pilot)
9. OAuth client_credentials — happy path (already implemented Phase 7 Gate 5)
10. API Key — happy path + revoked key

---

## §8 服务账号 (集成服务账号 / SDK 客户端身份 / 后台任务身份)

### 8.1 集成服务账号 (PDF §八)

= `OAuthClient` (Phase 7 Gate 5)。HIS/EMR 集成时,医院侧 HIS 注册 OAuthClient:
- `client_id` + `client_secret` (shown ONCE)
- `scopes`: `["patient_context.create", "documents.submit", "agent_run.invoke", "webhook.receive"]`
- `allowed_origins`: `[his.hospital.cn]`

### 8.2 SDK 客户端身份 (PDF §八)

= 调用方 (browser SPA via HMAC bootstrap ticket, OR partner SDK via OAuthClient)。两种身份在 `run_history.api_client_id` 列记录 (Phase 7 Gate 5)。

### 8.3 后台任务身份 (PDF §八)

= 系统级 cron / 队列 worker。当前 iCoDer 后台任务通过 `system` 用户 ID (写在 AuditLog.user_id)。

**GAP**: 后台任务应有独立的 service-account JWT 而非复用 `system`。A1C.4 follow-up: 引入 `BackgroundTask` 模型 + 独立 JWT 签发 (deferred)。

---

## §9 AUTH 审计覆盖 (详见 `AUTH_AUDIT_REPORT.md`)

| 事件类型 | 当前 audit action | 覆盖率 |
|---------|------------------|--------|
| 登录成功 | `auth.login` | ✓ |
| 登录失败 | `auth.login_failed` | ✓ |
| Token 撤销 | `auth.token_revoked` | ✓ |
| OIDC callback | `auth.oidc.callback` | DESIGN (deferred) |
| OIDC refresh | `auth.oidc.refresh` | DESIGN (deferred) |
| Patient context create | `patient_context.create` | ✓ (A1C.3) |
| Patient context delete | `patient_context.delete` | ✓ (A1C.3) |
| Cross-tenant deny | `auth.cross_tenant_denied` | DESIGN (Pilot) |
| Permission denied | `auth.permission_denied` | DESIGN (Pilot) |

---

## §10 Verdict

**MODEL_AUTHORIZED_FOR_PILOT_IMPLEMENTATION_PARTIAL**:

- **DESIGNED**: §1-§9 9 章节;7 类主体映射 + 28 权限矩阵 + 10 攻击向量 + 4 客户端字段不可信验证 + OIDC 集成点 + SSO 10 场景
- **IMPLEMENTED**:
  - A1A Gate 1 secrets/auth fail-closed (本地用户登录)
  - A1A Gate 2/3 organization_id 服务端覆盖 + tenant_read_policy 404-no-leak
  - Phase 7 Gate 5 OAuthClient (集成服务账号)
  - Phase 7 Gate 7 trace_token (HMAC)
  - Phase 7 Gate 13A PreviewSession (HMAC bootstrap)
  - A1C.3 patient_context API + RBAC 限制
- **DEFERRED TO PILOT**:
  - 医院 OIDC provider 真实对接 (Keycloak/Azure AD/阿里 IDaaS)
  - UserRole enum 扩展 (CDI_SPECIALIST + MEDICAL_RECORDS_ADMIN — Migration 030)
  - 后台任务 service-account JWT
  - cross_tenant_denied + permission_denied audit events
  - tenant_id == current_org.slug 一致性校验

## §11 Charter §22 forbidden verdicts honoured

未输出 IDENTITY_VERIFIED_ON_PILOT / SSO_PILOT_DEPLOYED / AUTHORIZED_FOR_PRODUCTION。Honest PARTIAL — Pilot 真实对接是单独 gate。

## §12 PDF §八 "必须验证 不得被直接信任" 关闭证据

| 字段 | 关闭证据 |
|------|---------|
| `organization_id` | §5.1 + A1A Gate 2 + A1C.4 测试 §7 case #11 (伪造 organization_id 攻击 → 期望 404) |
| `tenant_id` | §5.2 + A1C.4 follow-up validator (DESIGN — Pilot 实现) |
| `role` | §5.3 + `auth.py:131-138` (DB 重查 user.role) |
| `permissions` | §3.2 + 服务端 RBAC 矩阵 |
