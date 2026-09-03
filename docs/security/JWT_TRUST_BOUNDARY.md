# JWT issuer/audience 信任边界

## 目标

iCoDer API 不把“签名可验证”等同于“token 是为本 API 签发”。所有标准三段式 JWT 必须同时满足：

- 使用固定允许的算法；
- HS256 生产签名密钥不少于 32 字节；
- `iss` 精确匹配 `JWT_ISSUER`；
- `aud` 是单一字符串且精确匹配 `JWT_AUDIENCE`；
- 存在 `sub`、`exp`、`iat` 和 `type`；
- token 类型满足调用端点的身份要求；
- 用户、成员关系、组织、API Client、scope 和 delegation 继续以数据库当前状态为准。

这遵循 RFC 7519 的 issuer/audience 语义，以及 RFC 8725 对同一 issuer 面向多个 relying party 时必须
使用 audience 防止 token substitution 的要求。

## 配置

```text
JWT_ISSUER=https://auth.example.icoder.cloud
JWT_AUDIENCE=https://api.example.icoder.cloud
```

二者不能为空且不能相同。不同环境或不同 API 如果共享签名基础设施，必须使用不同 audience。生产值
应是部署拥有并稳定管理的标识，不应从请求 Host、Tenant-Name 或用户输入动态生成。

OAuth realm discovery 返回与实际 token 完全相同的 issuer 和 audience。realm 和 org_id 仍用于租户
定位，但不能替代 audience；audience 识别接收 API，org_id 识别租户数据边界。

## 覆盖的 token

| token 类型 | `iss`/`aud` | 数据库实时撤销 |
|---|---:|---:|
| 用户 access | 强制 | 用户状态、token_version、成员关系、组织状态 |
| 用户 refresh | 强制 | token_version 与用户状态 |
| Agent delegation | 强制 | 由使用端点继续限制类型与权限 |
| OAuth client_credentials | 强制 | token hash、Client、owner、成员关系、scope、Agent/purpose grant |

Console preview 的两段式 Runtime Token 不是 JWT，继续由 `preview_ticket` 独立验证；本轮没有改变其格式。

## 上线影响

此前签发且不含 `iss`/`aud` 的 JWT 会在部署后立即失效。这是有意的安全切换，不能开启兼容性降级。
上线前应：

1. 为环境配置稳定、互不相同的 issuer 和 audience；
2. 从 KMS/Secret Manager 注入至少 32 字节的随机 HS256 密钥；
3. 先部署能够签发并校验新 claims 的一致版本，避免混合版本实例；
4. 让用户重新登录，并让 API Client 重新获取短期 token；
5. 验证 discovery document、HTTP API 和 WebSocket 均拒绝旧 token；
6. 不复用旧 token 延长窗口，也不关闭 audience 校验。

## 不包含的能力

本轮没有把共享 HMAC 改为非对称签名，也没有实现外部 OIDC federation/JWKS。后续接入独立身份提供方
时，应增加算法/密钥用途隔离、`kid` allowlist、JWKS 缓存与轮换，并保持 issuer/audience 严格校验。
