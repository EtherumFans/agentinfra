# iCoDer API Client Model (2026-06-27)

> **Status**: Design intent (Phase 1 cloud-flip). API Client 是 Tenant 接入 iCoDer
> 的唯一凭证。与 Corti 的 backend-service / ROPC embedded 两类 client 对齐。
> 详细架构见 [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md)。

## 1. Two Client Types

### 1.1 backend-service (server-to-server)

**用途**: HIS / EMR 后端 → iCoDer 控制面 server-to-server 调用。

**凭证**:
```
client_id:     32-char hex (例: ic_c1f3e8a90b2d4f5e...)
client_secret: 64-char base64 (例: 7XkP9vN2qM4tR8wY3jL6hF0sB5dC1aE...)
```

**获取流程**:
1. Tenant admin 在 iCoDer Console → Settings → API Clients → Create
2. 选择 "Backend Service" 类型
3. 配置 scopes (`codes:read`, `codes:write`, `encounters:write`, `reviews:read` 等)
4. 系统生成 `client_id` + `client_secret`,secret **只在创建时显示一次**
5. Tenant admin 把 secret 存入己方 secret manager (HashiCorp Vault / 云 KMS)

**Token 流程**:
```
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=ic_c1f3e8a90b2d4f5e...
&client_secret=7XkP9vN2qM4tR8wY3jL6hF0sB5dC1aE...
&scope=codes:read codes:write encounters:write

→ 200 OK
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "codes:read codes:write encounters:write"
}
```

后续所有 API 调用:
```
POST /api/icoder/agents/{id}/v1/message:send
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
X-Tenant-Id: <tenant_id>
```

### 1.2 ROPC embedded (browser)

**用途**: Web Component `<icoder-embedded>` 嵌入到 HIS Web 前端,医生浏览器
直接调 iCoDer。

**凭证**: 不使用 client_secret,改走 ROPC (Resource Owner Password Credentials)
用户名密码 flow (仅适用于受控内部部署,Corti 同款)。

**Token 流程**:
```
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=password
&username=doctor@hospital.cn
&password=<用户密码>
&client_id=ic_embedded_web_<tenant_id>
&scope=coding:review encounters:read

→ 200 OK
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "...",
  "token_type": "Bearer",
  "expires_in": 900,        # ROPC token 较短 (15 min)
  "refresh_expires_in": 86400,  # refresh 24h
  "scope": "..."
}
```

ROPC token 短 (15min),通过 refresh_token 自动续期。

## 2. Scopes (权限粒度)

| Scope | 用途 | 典型 client |
|---|---|---|
| `codes:read` | 读 ICD 码 catalog / synonyms | backend-service + ROPC |
| `codes:write` | 提交 / 修正编码 | backend-service |
| `encounters:write` | 提交新 encounter | backend-service |
| `encounters:read` | 读 encounter | 全部 |
| `reviews:read` | 读 coding review | 全部 |
| `reviews:write` | 创建 / 推进 coding review | backend-service + ROPC |
| `agents:read` | 列 / 查 Agent | 全部 |
| `agents:invoke` | 触发 Agent run | backend-service + ROPC |
| `audit:read` | 读 audit log | backend-service (admin scope) |

每个 client 创建时指定 scope 集合;**最小权限原则**。

## 3. Token Lifecycle

| 类型 | access_token TTL | refresh_token TTL | 备注 |
|---|---|---|---|
| backend-service | 1h | N/A (no refresh) | 过期重发 client_credentials |
| ROPC embedded | 15min | 24h | refresh 自动续;登出 → revoke refresh |

## 4. Client Management API (Phase 1 stub)

```
GET    /api/clients                  → 501 (Phase 1 stub;see CLOUD_DEPLOYMENT.md §7)
POST   /api/clients                  → 501
GET    /api/clients/{id}/scopes      → 501
PATCH  /api/clients/{id}/scopes      → 501
DELETE /api/clients/{id}             → 501
POST   /oauth/token                  → 501
POST   /oauth/revoke                 → 501
```

Phase 1 stub 端点返 `501 Not Implemented` + 设计意图 doc-link。Phase 2 实装。

## 5. Security Boundaries

- **Tenant 隔离**: Token claims 必含 `tenant_id`,控制面验证每个请求的
  `tenant_id` 跟 URL 资源 `tenant_id` 一致,**阻止跨 tenant 越权**。
- **Region 隔离**: Token claims 必含 `env` / `region`,防止 token 在 Environment 间复用。
- **Client_secret 加密**: Tenant 创建 secret 时立即 AES-256-GCM 加密存 DB,
  `ICODER_SECRET_KEY` 作为 KEK (Key Encryption Key) 从云 KMS 注入,不入文件。
- **Audit log**: 所有 token 签发 / refresh / revoke 写 audit log,redacted PHI 字段。

## 6. Migration from "JWT for everyone"

Phase 1 之前,`backend/app/config.py` 默认 `JWT_ALGORITHM=HS256` + 单 secret,
全部 endpoint 用同一 JWT (不论 backend 集成还是 Web Component)。这是
**on-prem 时代的简化假设,不适合云**。

Phase 1 (cloud-flip) 范围:
- ❌ 不改 JWT 实现 — 仍 HS256 单 secret (`SECRET_KEY`)
- ❌ 不实装 OAuth / scope 系统

Phase 2+:
- ✅ 改 RS256 / EdDSA 配 JWKS endpoint
- ✅ 引入 OAuth 2.1 (client_credentials + ROPC + PKCE for embedded)
- ✅ 引入 scope 系统 + per-tenant JWT signing

## 7. References

- [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) — 三层架构总览
- [MULTI_REGION.md](MULTI_REGION.md) — region 隔离 / token claims
- Corti reference: Web Component 一等交付物 + stateless token + 事件总线