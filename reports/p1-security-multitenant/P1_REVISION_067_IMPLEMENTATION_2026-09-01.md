# P1 Revision 067 实施与验证报告

日期：2026-09-01
范围：Batch 2 Wave 3 — Agent Connectors 三张租户表
数据库权威：PostgreSQL
目标 revision：`067`

## 1. 审查结论

Revision 067 已将 Agent Connector 配置、外部凭据引用元数据和执行审计纳入 PostgreSQL 数据库级租户发布闸门。三张表均启用 `ENABLE/FORCE ROW LEVEL SECURITY`，运行时在读取 Connector、解析 Credential 或写入 Execution Audit 前建立事务局部租户权威。

生产启动期望 revision 从 `066` 提升到 `067`，FORCE RLS 表从 22 张增加到 25 张。本轮没有授予应用角色 `SUPERUSER` 或 `BYPASSRLS`，也没有在迁移中写入生产角色名。

## 2. Wave 3 权威范围

本轮严格按租户表清单处理：

1. `agent_connectors`
2. `connector_credentials`
3. `connector_execution_audit`

`oauth_clients` 和 `oauth_tokens` 在权威清单中属于 Batch 2 Wave 4，存在 nullable/平台客户端分流问题。本轮不提前启用其 RLS，避免把需要拆分控制面的 OAuth 设计混入三张已经具备直接租户字段的 Connector 表。

## 3. 关键安全发现

### 3.1 单列外键不能证明租户一致

原 schema 同时保存 `organization_id` 和全局对象 id，但外键只检查 `agent_id` 或 `connector_id`。因此数据库能够接受下列组合：

- 本租户 `organization_id` + 他租户 `agent_id`
- 本租户 Credential/Audit + 他租户 `connector_id`
- Connector 的本租户 source Agent + 他租户 target Agent

应用查询虽然同时带组织条件，但单列外键无法在写入时证明父子租户一致。067 将这些关系替换为包含 `organization_id` 的复合外键。

### 3.2 Connector Executor 必须自行绑定租户

HTTP 管理 API 会由已验证的组织依赖建立租户事务，但 Connector Executor 也可从 Agent Run、A2A 或后台执行路径调用，不能假定调用者已经绑定数据库会话。067 在 Executor 入口以 `ConnectorInvocation.organization_id` 建立事务局部数据库权威；随后 Connector、Credential 和 Audit 共用同一事务边界。

### 3.3 凭据表不保存凭据密文本体

模型和校验逻辑只接受 Vault/KMS/Secret Manager 引用及指纹，不接受 bearer token、OAuth client secret 或授权头原文。原租户清单把敏感度标为 `credential_ciphertext`，与实现不符；067 已更正为 `credential_reference_metadata`。真实密钥的静态加密、轮换和 KMS 生命周期由外部密钥管理层负责。

## 4. 迁移前对账与失败关闭

067 在修改约束或开启 RLS 前检查：

- 三表不存在 `organization_id IS NULL`。
- 每个 Connector 的 source Agent 必须属于同一组织。
- 非空 target Agent 必须属于同一组织。
- Credential 必须指向同一组织的 Connector。
- Execution Audit 必须指向同一组织的 Connector。

发现孤儿或跨租户拼接时，迁移以 `migration 067 requires evidence-backed Connector tenant reconciliation` 中止并报告类别与数量。迁移不会写入默认租户、`unknown` 租户，也不会静默删除审计或凭据元数据。

## 5. 数据库所有权约束

067 新增：

- `uq_agents_org_id`
- `uq_agent_connectors_org_id`
- `fk_agent_connectors_agent_scope`
- `fk_agent_connectors_target_agent_scope`
- `fk_connector_credentials_connector_scope`
- `fk_connector_execution_audit_connector_scope`

同时移除四个只检查对象 id 的旧单列外键。最终所有权链为：

`organizations` → `(organization_id, agent_id)` → `agent_connectors` → `connector_credentials` / `connector_execution_audit`

Target Agent 也通过同一 `(organization_id, id)` 约束，防止内部 Agent 委派跨越租户边界。

## 6. RLS 策略

三张表统一使用策略 `icoder_tenant_isolation`：

- `USING` 限制读取、更新与删除可见行。
- `WITH CHECK` 限制插入和更新后的组织归属。
- 租户值来自事务局部 `icoder.current_organization_id`。
- 未绑定租户时查询三表均返回零。
- 事务结束后租户设置自动清除，连接池复用不继承上一请求的租户。

## 7. 运行时改造

- Connector Executor 在第一条 Connector 查询前绑定 invocation 组织。
- `require_agent_in_tenant` 在 Agent/Connector 图验证前绑定组织。
- Connector Graph binding 校验在读取 Connector 前绑定组织。
- Connector 管理 API 的单项读取和 Credential 查询辅助函数显式绑定组织。
- 生产启动受保护表清单加入三张 Wave 3 表，预期 revision 更新为 `067`。

现有管理员写操作仍要求组织 `owner/admin`；普通读取保持认证用户 + 当前组织范围。067 没有放宽角色授权，也没有允许 OAuth Client 调用 Connector 管理端点。

## 8. 测试夹具审查发现

完整 Connector Graph 回归最初有 10 项被现有 Agent 发布闸门提前拒绝。原因是测试声称构造“可运行 Agent”，但夹具仍使用默认 `draft / is_published=false`。产品代码正确地失败关闭为 `agent_not_published`。

夹具现已明确创建 `published / is_published=true` 的测试 Agent，并在共享 Medical Coding Agent 被测试临时修改时保存和恢复原发布状态。该修正只恢复测试前提，没有放宽生产发布闸门。

为完整执行既有套件，本机 `.venv` 补装 `jsonschema` 和 `asgi-lifespan`；虚拟环境被 Git 忽略，未产生入库文件。

## 9. 验证结果

### 9.1 静态与功能回归

- Python 编译：通过。
- 租户清单、迁移契约和数据库会话审计：24/24 通过；另 1 项 cloud SQLite 用例按本组目标排除。
- Connector 服务、Runtime 和管理 API：42/42 通过。
- Connector Executor：16/16 通过。
- Connector Graph HTTP/A2A 运行路径：16/16 通过。
- 差异空白检查：通过。

### 9.2 真实 PostgreSQL 攻击矩阵

完整同步/异步攻击矩阵：7/7 通过，包括此前核心面、Wave 1、Wave 2、连接池复用，以及新增 Wave 3：

- 未绑定租户时三表不可见。
- 租户 A 只能看到自己的 Connector、Credential 和 Execution Audit。
- 租户 B 无法读取租户 A 数据。
- 在租户 A 事务中写入租户 B 行被 RLS 拒绝。
- 在租户 B 的合法事务中引用租户 A Agent 被复合外键拒绝，证明隔离不仅依赖查询过滤。

攻击使用真实 `NOSUPERUSER NOBYPASSRLS` 应用角色执行，而不是只检查策略文本。

## 10. 迁移、回滚与重建演练

- 现有测试库 `066 → 067`：通过。
- 同一数据库 `067 → 066 → 067`：通过，最终 `067 (head)`。
- 专用空库从初始 revision 全量迁移到 head：通过。
- 空库结果：82 张表，25 张启用并强制 RLS 的表。
- 实际 PostgreSQL catalog 确认六个新增唯一/复合所有权约束全部存在。
- 生产启动门禁（revision、角色、NOT NULL、策略、FORCE RLS）：通过。
- 临时数据库 `icoder_p1_067_verify` 已在验证后删除。

## 11. 权威清单变化

- 权威 revision：`066 → 067`
- 数据库表：82（不变）
- 含 `organization_id` 的数据库表：72（不变）
- `organization_id NOT NULL`：50（不变）
- FORCE RLS 表：`22 → 25`
- 间接租户但尚无直接 `organization_id` 的表：4（不变）

清单新增 `batch_2_third_wave_tables`，三张表标记为 `batch2_wave3_complete`。

## 12. 本机环境变更

本机 `icoder_p1_app` 测试角色仅增加三张 Wave 3 表的普通 DML 权限，用于真实应用角色攻击测试。这是本机验证配置，不写入迁移；生产权限仍应由基础设施层以最小权限配置。

## 13. 风险与下一步

1. Batch 2 Wave 4 需处理 `oauth_clients`、`oauth_tokens`、`api_keys`、团队身份表和审计表的 nullable 归属与平台控制面拆分，不能直接套用本轮单一租户策略。
2. OAuth Client 的 delegated subject、allowed Agent、purpose 和 scope 必须在 token 签发与每个敏感入口同时验证，并增加管理员越权/撤销竞态攻击测试。
3. Connector Credential 目前是外部密钥引用；应继续验证 KMS/Vault 轮换、缓存失效、吊销后并发请求和审计导出行为。
4. CI 应固定运行 `066→067`、`067→066→067`、空库迁移和三表攻击矩阵，并使用独立 migration/app 角色。

## 14. 完成判定

Batch 2 Wave 3 的迁移、数据库约束、运行时绑定、RLS、防跨租户攻击、相关回归、升降级、空库重建、生产门禁和权威清单均已完成验证。Revision 067 可作为下一候选开发基线。
