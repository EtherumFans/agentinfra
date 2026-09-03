# P1 身份门禁：JWT issuer/audience 与跨服务 token substitution 防护

- 日期：2026-09-03
- 范围：用户 access/refresh、Agent delegation、OAuth client_credentials、HTTP/WebSocket 共用解码路径
- 结论：本地工程门禁完成；外部 IdP/JWKS 不在本轮范围

## 1. 风险发现

此前 JWT 只验证 HMAC 签名和时间，没有签发者 `iss` 与接收方 `aud`。如果两个服务错误地复用签名
密钥，另一个服务签发的 token 可能被 iCoDer 当作本 API token 处理。现有 `type`、租户、实时成员
关系和 OAuth 数据库校验能限制后续权限，但不能完整表达 token 的签发与接收信任边界。

RFC 7519 定义 `iss` 为签发主体、`aud` 为预期接收方；RFC 8725 要求同一 issuer 面向多个 relying
party 时使用 audience 防止 token substitution。本轮把两项从可选 claim 提升为本产品强制契约。

## 2. 实现

1. 新增 `JWT_ISSUER` 和 `JWT_AUDIENCE`，本地默认分别为 `urn:icoder:auth`、`urn:icoder:api`。
2. cloud 启动拒绝空 issuer、空 audience 或二者相同。
3. access、refresh、delegation、client_credentials 四类 JWT 统一写入 `iss`、`aud` 和 `iat`。
4. 解码时固定算法，并要求 `iss`、`aud`、`sub`、`exp`、`iat`、`type` 全部存在。
5. 使用 PyJWT strict audience 模式，只接受单一且精确匹配的 audience；包含正确值的多 audience
   数组也拒绝，避免扩大接收面。
6. OAuth realm discovery 改为公布实际配置的 issuer/audience，不再返回与 token 不一致的占位 issuer。
7. 两段式 Runtime Token 保持独立验证路径，不被误当成 JWT。
8. cloud 启动额外拒绝短于 32 字节的 HS256 `SECRET_KEY`；本地开发行为保持兼容。

## 3. 攻击矩阵

新增测试覆盖：

- 正确密钥、错误 audience；
- 正确密钥、错误 issuer；
- 多 audience 混淆；
- 分别删除 iss、aud、iat、exp、sub、type；
- issuer 与 audience 配置成同一值；
- 云生产使用任意短于 32 字节的 HS256 key；
- 四种本地签发 JWT claims 完整性；
- OAuth discovery 与实际 token 配置一致；
- 既有 scope narrowing、Agent/purpose delegation、成员撤销、Client 禁用、管理员 token 撤销；
- WebSocket access/refresh 类型隔离与 Runtime Token 兼容。

## 4. 兼容性和上线要求

旧 JWT 因缺少强制 claims 将立即失效。该行为是安全修复，不提供接受旧 token 的降级开关。生产上线
必须使用一致版本滚动边界或停机切换，随后要求用户重新登录、API Client 重新取 token。数据库中的
OAuthToken 旧 hash 即使尚未到期也无法通过 JWT 解码。

本轮无数据库迁移，不修改用户、组织、成员、Client 或 token 表结构。

## 5. 验证结果

- JWT、OAuth、API Client、平台管理员、组织角色、WebSocket、租户边界、revision 073 契约和
  cloud fail-closed 扩大回归：`167 passed`；
- Python `compileall`：通过；
- 后续还需执行完整 PR CI 和真实 PostgreSQL 身份矩阵。

## 6. 剩余身份工作

1. 在真实 PostgreSQL app/migration 角色下执行 API Client/OAuth/Admin HTTP 攻击矩阵；
2. 对 token rotation/revocation 的并发竞争执行压力与缓存失效测试；
3. 若接入外部 IdP，增加非对称算法、`kid` allowlist、JWKS 轮换及 issuer 分区；
4. 完成身份批次后进入 PostgreSQL base backup、WAL/PITR、密钥联合恢复与升级回滚演练。
