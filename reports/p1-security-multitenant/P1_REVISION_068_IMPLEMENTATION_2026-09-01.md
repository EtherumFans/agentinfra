# P1 Revision 068 实施与验证报告

日期：2026-09-01  
范围：Batch 2 Wave 4 — 身份、凭据、成员、邀请与审计边界  
数据库权威：PostgreSQL  
目标 revision：`068`  
实现提交：`08543485`  
测试提交：`07cc3a10`

## 1. 审查结论

Batch 2 Wave 4 已完成实现、升级、回滚、空库重建和真实非特权应用角色攻击验证。九张目标表全部启用 PostgreSQL `ENABLE/FORCE ROW LEVEL SECURITY`；其中八张表强制非空租户，`audit_logs` 使用租户/系统双分区策略。

生产启动期望 revision 从 `067` 提升到 `068`，受 FORCE RLS 保护的表由 25 张增加到 34 张。应用角色仍为 `NOSUPERUSER NOBYPASSRLS`，迁移没有硬编码生产数据库角色名，也没有给运行时角色授予 `BYPASSRLS`。

本机权威库 `icoder_p1_gate` 已升级至 `068`，应用启动校验通过。最终验证总计 110 项，全部通过：

- PostgreSQL 攻击矩阵、迁移与清单契约：29/29。
- Auth、Organization、OAuth、API Client、管理员滥用、邀请 outbox 与系统审计回归：81/81。

## 2. Wave 4 权威范围

| 表 | 最终租户契约 | RLS | 关键约束/控制 |
|---|---|---|---|
| `api_keys` | `organization_id NOT NULL` | FORCE | 创建、列表、撤销显式绑定当前组织 |
| `audit_logs` | 租户行非空；系统行允许 NULL | FORCE split policy | NULL 仅允许 verified `MODERN_SYSTEM`，经安全定义函数追加 |
| `oauth_clients` | `organization_id NOT NULL` | FORCE | `(organization_id, client_id)` 唯一；启动解析只返回组织 ID |
| `oauth_tokens` | `organization_id NOT NULL` | FORCE | 复合外键绑定同组织 OAuth Client |
| `organization_invite_deliveries` | `organization_id NOT NULL` | FORCE | 复合外键绑定同组织 Invite |
| `organization_invites` | `organization_id NOT NULL` | FORCE | token 启动解析只返回组织 ID |
| `organization_members` | `organization_id NOT NULL` | FORCE | 认证先缩小 RLS 分区，再验证实时成员关系 |
| `team_invites` | `organization_id NOT NULL` | FORCE | 旧兼容表保留但不再允许无组织行 |
| `team_members` | `organization_id NOT NULL` | FORCE | 必须能关联权威 OrganizationMember |

`organizations` 继续作为平台租户注册表，不纳入租户行 RLS；`users` 继续作为全局身份表，租户授权权威位于 `organization_members`。

## 3. 迁移前数据对账

在 revision 068 实施前，对本机 `icoder_p1_gate` 的九张目标表执行逐表审计：

- 九表总行数均为 0。
- nullable 五表的 NULL 租户数均为 0。
- `audit_logs` 不存在不合规 NULL 系统分区行。
- 不存在 OAuth token/client、invite/delivery、owner/member 或旧 Team/member 的跨租户孤儿关系。

本机空数据不能替代生产对账，因此 068 迁移自身继续执行失败关闭检查。任何下列情况都会中止迁移并报告类别和计数：

- 八张严格租户表存在 NULL `organization_id`。
- NULL `audit_logs` 不是 verified `MODERN_SYSTEM + security_event`。
- API Key 或 OAuth Client owner 不是同组织成员。
- OAuth Token 指向其他组织或不存在的 Client。
- Invite 的邀请人不属于同组织。
- Invite Delivery 指向其他组织或不存在的 Invite。
- 旧 Team Member 没有权威 OrganizationMember。
- 旧 Team Invite 的邀请人不属于同组织。

迁移不会猜测默认租户、不会建立 `unknown` 租户、不会静默撤销或删除历史凭据和审计行。生产发现存量异常时，必须先以可审计证据对账，再重试迁移。

## 4. 数据库所有权强化

068 新增以下关键约束：

- `uq_oauth_clients_org_client_id`
- `fk_oauth_tokens_client_scope`
- `uq_organization_invites_org_id`
- `fk_organization_invite_deliveries_invite_scope`

这使数据库在写入时就能拒绝：

- 本组织 OAuth Token 关联其他组织 Client。
- 本组织 Invite Delivery 关联其他组织 Invite。

原 `organization_invite_deliveries_invite_id_fkey` 单列外键被复合外键替代。降级时复合约束会被移除并恢复旧单列约束。

## 5. OAuth 启动阶段设计

### 5.1 问题

OAuth token endpoint 在签发 bearer token 前尚无经过验证的 JWT 租户声明，但 `oauth_clients` 已受 FORCE RLS 保护。如果直接按 `client_id` 查询，会在无租户上下文时看不到任何记录；如果相信请求头直接绑定，又会把未验证输入提升为数据库权威。

### 5.2 解决方案

068 创建 `icoder_resolve_oauth_client_tenant(client_id)` 安全定义函数。函数只返回一个活动 Client 的组织 ID，并同时确认组织仍为活动状态；不返回名称、secret hash、scope、owner、allowed origins 或其他租户数据。

运行时流程为：

1. 以公开 `client_id` 调用窄解析函数。
2. 将返回的组织 ID写入事务局部 `icoder.current_organization_id`。
3. 在 FORCE RLS 后重新查询 Client。
4. 验证 secret、scope、owner、组织归属及活动状态。
5. 写入同组织 OAuth Token。

Realm URL 仍是描述性路由标签，不覆盖 Client 的权威组织声明，保持现有 SDK 合同。

### 5.3 OAuth bearer 验证

`get_current_client` 现在先用 token 中的组织声明缩小 RLS 可见范围，再用数据库中的 token hash、Client、owner、实时 membership 和当前 scope 验证该声明。伪造组织声明最多选择一个不可见分区，不能越权读取；验证失败返回拒绝。

## 6. 成员身份启动与组织切换

将 `organization_members` 纳入 FORCE RLS 后，认证流程不能在无租户上下文中全表查询成员关系。调整后的顺序是：

1. JWT 组织声明先用于缩小 RLS 分区，不直接视为授权。
2. 在该分区内验证 Organization 活动状态、User 活动状态、token version 和实时 membership。
3. membership 不存在即拒绝。

登录、refresh、`/me` 和组织列表需要返回用户的多个组织。实现不增加全局成员读取函数，而是遍历公开 Organization 注册表，逐组织绑定 RLS，并只查询指定用户的 membership。组织切换同样先绑定目标分区，再验证成员关系。

创建组织、公共注册、平台 Tenant 创建和接受邀请在写入新组织 membership 前都会重新绑定新组织分区，避免沿用旧组织事务上下文。

## 7. 邀请和后台 outbox

邀请接受使用 `icoder_resolve_invite_tenant(token_digest)` 窄函数，只解析 bearer invite digest 对应的组织 ID。随后绑定租户并在 RLS 后重新读取、锁定和验证 Invite。

Invite Delivery worker 不再无租户扫描 outbox。它遍历 Organization，逐组织绑定并认领到期任务；`DeliveryClaim` 携带 `organization_id`，处理阶段在读取 Delivery/Invite 前恢复同一租户上下文。每个租户认领结果在换租户前提交，避免一个 session 同时 flush 多个 RLS 分区的脏对象。

## 8. 审计日志拆分策略

### 8.1 租户审计

非 NULL `organization_id` 行使用标准 `icoder_tenant_isolation` 策略：只有事务局部组织 ID 相同才能 SELECT/INSERT/UPDATE/DELETE，且 `WITH CHECK` 阻止把行移动到其他租户。

### 8.2 系统审计

NULL 组织只允许：

- `tenancy_classification = MODERN_SYSTEM`
- `tenancy_attribution_source = security_event`
- `tenancy_attribution_confidence = verified`

普通运行时 SQL 无法直接插入、读取、修改或删除该分区。`system_audit()` 在 PostgreSQL 上调用 `icoder_write_system_audit(jsonb)` 安全定义函数追加事件；SQLite 单元测试继续使用 ORM 路径。

数据库函数本身再次执行动作白名单，只接受当前治理的系统动作或 `security_admin.*` 命名空间。即使绕过应用服务直接调用函数，也不能把任意租户动作伪装为系统事件。

本轮建立的是“隔离 + 窄追加”基础，不等同于最终不可抵赖性。签名链、WORM/外部归档、保留删除冲突处理和导出证明仍属于后续 P1 审计专项。

## 9. API Key 与管理员路径修复

### 9.1 API Key

发现旧创建路径没有写入 `organization_id`。068 已修复为：

- 列表同时过滤 owner 与当前组织。
- 创建强制写入当前组织。
- 撤销同时过滤 key ID 与当前组织。

### 9.2 平台管理员

平台管理员跨组织禁用 User 的 OAuth Clients 时，不再执行无租户全表查询。流程逐 Organization 绑定、查询、修改并在切换前 flush。全局 Client 列表也逐组织读取，并明确返回 `organization_id`。

暂停 Organization 时，先绑定目标组织，再读取 members、clients 和 tokens；Client 与 OAuth Token 的撤销保持在同一组织分区内。现有 self-modification、最后一名管理员、stale token version 和 token revocation 测试继续通过。

## 10. Partner CORS 控制面

旧 Partner CORS middleware 会读取所有 OAuth Client 的 `allowed_origins`。068 将 PostgreSQL 路径替换为 `icoder_partner_origin_allowed(origin)` 布尔函数：只回答一个 Origin 是否属于活动组织的活动 Client，不返回全局 allowlist 或 Client 行。SQLite 本地测试仍使用原兼容实现。

## 11. 生产启动校验

`PRODUCTION_SCHEMA_REVISION` 已更新为 `068`。生产启动会验证：

- 当前角色不是 superuser 且没有 BYPASSRLS。
- 33 张严格租户表均为 RLS enabled、RLS forced、organization_id NOT NULL。
- `audit_logs` 为 RLS enabled、RLS forced，但允许受治理的 NULL 系统分区。
- 34 张表均存在完整 `icoder_tenant_isolation` ALL policy。

本机以真实 `icoder_p1_app` 运行 `verify_production_database()`，结果通过。

## 12. 验证证据

### 12.1 真实 PostgreSQL 攻击矩阵（29/29）

覆盖：

- inventory 与 live schema 一致。
- revision 064–068 合同。
- Wave 1–4 全部 FORCE RLS 攻击链。
- 无租户读取为 0。
- Tenant A 只看 A、Tenant B 只看 B。
- 跨租户 INSERT/UPDATE 被 RLS 拒绝。
- OAuth Client bootstrap 只暴露组织 ID，绑定错误租户后仍不可见。
- 任意系统审计动作伪造被数据库白名单拒绝。
- 系统审计行对运行时 SELECT 不可见。
- 同步和异步连接池事务结束后不泄漏租户设置。

### 12.2 应用回归（81/81）

覆盖：

- 注册、登录、refresh、组织切换和组织角色安全。
- OAuth legacy/realm token、scope、secret、禁用与审计拒绝。
- API Client 创建、读取、更新、secret rotation 与 delegation。
- 管理员 User/Organization 权限滥用防护与凭据撤销。
- Invite Delivery 加密 outbox、认领、重试、死信和恢复。
- System Audit allowlist 与 tenant-owned system audit。

### 12.3 迁移演练

- 本机权威库执行 `067 → 068`：通过。
- 本机权威库执行 `068 → 067 → 068`：通过。
- 独立空库 `icoder_p1_wave4_4d82e1` 从 base 全量迁移至 `068`：通过。
- 空库核验九张目标表均 ENABLE/FORCE RLS：9/9。
- 空库核验四个控制面函数存在：4/4。
- 临时验证库验证完成后已删除。

## 13. 本机角色与权限

本机测试应用角色原先只授予前三个 Wave 的目标表 DML 权限，导致 Wave 4 首次攻击运行出现 `permission denied`。已对本机 `icoder_p1_app` 补齐九张既有 Wave 4 表的 SELECT/INSERT/UPDATE/DELETE，用于模拟真实运行时。

此授权未写入迁移，因为生产角色名不应硬编码。部署/CI provisioning 必须在迁移后授予应用角色所需表权限，同时继续强制 `NOSUPERUSER NOBYPASSRLS`。生产启动校验会阻止特权角色启动服务。

## 14. 回滚行为

降级至 067 会：

- 删除四个窄控制面函数。
- 删除系统审计和控制面 owner 策略。
- 删除九表标准租户策略并关闭 FORCE/ENABLE RLS。
- 恢复 Invite Delivery 单列外键。
- 删除 OAuth Token/Client 复合约束。
- 对原本 nullable 的五张表恢复 nullable。

组织成员和邀请三表原本已 NOT NULL，降级不改变其列属性。降级是 schema 回滚，不会自动恢复因管理员操作已撤销的业务凭据。

## 15. 已知剩余风险与后续任务

1. **审计不可抵赖性尚未完成**：下一阶段需实现签名链、KMS 签名/验证、外部不可变归档、retention/delete/export 证明。
2. **数据库角色 provisioning 未代码化**：CI/部署需建立可移植的 migration/app role 脚本，迁移后统一授权并验证无 BYPASSRLS。
3. **历史生产数据需独立对账**：本机九表为空，无法证明真实生产存量均满足 owner/member 和复合外键关系。
4. **旧 Team 表应最终退役**：API 已使用 OrganizationMember/Invite 作为权威，但 schema 兼容表仍存在；后续需制定导出、保留和 drop 计划。
5. **跨组织管理员读取成本**：当前以逐组织绑定实现安全的控制面访问，组织数量较大时需评估分页/批处理，而不能退回无 RLS 全表读取。
6. **API Key 认证消费路径**：本轮加固管理与存储边界；若后续启用 API Key 作为请求身份，必须按 OAuth 相同模式先解析最小租户映射、再绑定、再验证。
7. **Wave 5 临床 PHI 表**：CDI、Document、Encounter、Coding Review 与 clinical evidence/facts 仍处于待迁移状态，是下一批高敏目标。

## 16. 完成判定

Revision 068 满足 Batch 2 Wave 4 的当前完成标准：

- 权威范围九表全部具备数据库级租户隔离。
- OAuth、成员与邀请启动阶段不需要开放全表访问。
- 系统审计 NULL 分区与租户审计分离，并以窄追加函数和双层白名单保护。
- 跨租户 OAuth Token/Client、Invite/Delivery 关系由复合约束证明。
- 真实非特权角色攻击、应用回归、回滚和空库重建全部通过。
- 清单、启动 revision、ORM nullable 契约与 live schema 一致。

因此 Batch 2 Wave 4 可标记为 **实现完成并通过本机候选门禁**。它不是 P1 全部安全发布闸门完成；下一阶段应进入 Batch 2 Wave 5 的 PHI/临床数据表，同时并行启动审计不可抵赖性和角色 provisioning 工程化。
