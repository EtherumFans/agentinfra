# P1 安全与多租户发布闸门：启动审查报告

- 审查日期：2026-08-31
- 开发分支：`codex/p1-security-multitenant-gates`
- 起始基线：`55804262b80336795ef1b83431b916ba8bbbe0bc`
- 起始标签：`baseline/development-2026-08-31-v2-candidate`
- 当前结论：P1 已启动；第一批 PostgreSQL 权威存储与核心 RLS 代码完成，但尚未通过真实 PostgreSQL 发布验收，禁止标记为生产就绪。

## 1. 本轮目标与范围

本轮只启动 P1 安全主线，不加入新产品能力。第一批聚焦：

1. PostgreSQL 成为云环境唯一权威存储。
2. 生产建模只允许通过 Alembic，不再由应用启动时 `create_all` 补表。
3. 对 Patient、Trace、Usage、Context、Memory 的核心表建立 PostgreSQL 数据库级 RLS。
4. 认证和实时成员关系校验通过后，才把租户写入事务级数据库上下文。
5. 把未回填租户、RLS 配置缺失和高权限应用角色转为启动硬失败。
6. 建立可在专用 PostgreSQL 实例执行的跨租户攻击测试。

PHI/KMS、审计不可抵赖、OAuth/管理员滥用、备份恢复与升级回滚保留为后续独立提交批次。

## 2. 审查发现

### 2.1 生产数据库权威性

审查前，云配置已经拒绝 SQLite URL，但应用 lifespan 仍无条件调用 `Base.metadata.create_all()`。这意味着生产启动仍存在绕过迁移链创建缺失表的路径，数据库版本不能作为可靠发布事实。

本轮已改为：

- local/test：允许 `Base.metadata.create_all()`，保留快速开发能力；
- cloud：禁止 `create_all`，只验证 Alembic 版本和 PostgreSQL 安全属性；
- 当前生产期望迁移版本：`064`；
- 版本不匹配时云服务启动失败。

### 2.2 租户字段与隔离现状

代码已有大量应用层 `organization_id == current_org.id` 过滤，也已有 016/017 等迁移对 `run_history` 和 `audit_logs` 做遗留归属分类。但以下问题仍存在：

- 若应用查询漏写租户条件，数据库此前不会统一阻止跨租户读取；
- `run_trace_events`、`run_history`、`transactions`、`conversation_memories` 等表仍允许历史 NULL 租户；
- NULL 行虽然常被应用层排除，但“不可见”不等于“已完成证据化回填”；
- PostgreSQL 应用角色是否具备 `SUPERUSER`/`BYPASSRLS` 此前没有启动校验。

本轮没有把未知归属记录写入默认租户。无法证明归属的数据必须经过对账；在完成前，生产提升会被硬阻断。

### 2.3 现有 P1 后续能力

仓库已存在部分实现和测试基础：

- PHI live-path 脱敏和 bypass 禁用配置；
- Fernet 静态加密、版本化密钥前缀和批量重加密辅助逻辑；
- KMS version token、缓存失效和管理员旋转端点；
- API Client rotation、OAuth delegation、部分管理员拒绝测试；
- RunTrace retention purge、审计写入和部分删除验证；
- SQLite 迁移暂存与局部迁移回滚测试。

但大量 KMS、云存储、扫描器和部署控制器验证仍是注入契约或模拟测试，不等于真实云 KMS、托管 PostgreSQL、对象锁、PITR 和跨区域恢复演练。

## 3. 本轮实现

### 3.1 PostgreSQL 生产启动预检

`backend/app/database.py` 新增 `verify_production_database()`，云启动会验证：

- 数据库方言必须是 PostgreSQL；
- `alembic_version` 必须等于 `064`；
- 当前应用角色不得是 PostgreSQL superuser；
- 当前应用角色不得带 `BYPASSRLS`；
- 七个核心表必须同时启用 `relrowsecurity` 和 `relforcerowsecurity`；
- 七个核心表必须存在同时带 `USING` 与 `WITH CHECK` 的 `icoder_tenant_isolation` 策略；
- 七个核心表的 `organization_id` 必须具有数据库 `NOT NULL` 约束。

### 3.2 数据库级 RLS

迁移 `064_postgresql_tenant_rls.py` 对以下表启用并强制 RLS：

| 攻击面 | 受保护表 |
|---|---|
| Patient | `patient_contexts` |
| Trace | `run_trace_events`, `run_history` |
| Usage | `transactions` |
| Context | `contexts` |
| Memory | `memory_consents`, `conversation_memories` |

统一策略读取事务级 `icoder.current_organization_id`，同时使用：

- `USING`：限制 SELECT/UPDATE/DELETE 可见行；
- `WITH CHECK`：阻止 INSERT/UPDATE 写入其他租户或 NULL 租户；
- `FORCE ROW LEVEL SECURITY`：表所有者也必须受策略约束；
- 缺少租户上下文时表达式不匹配任何行，默认拒绝。

迁移会在启用 RLS 前由迁移角色逐表统计 NULL 租户行；只要存在一行就整体失败并报告逐表数量。全部对账完成后，迁移对七张表统一执行 `organization_id SET NOT NULL`。这避免了应用角色受 RLS 过滤后误报“无 NULL 行”的假阴性。

SQLite 迁移保持 no-op，仅用于 local/test；它不构成生产隔离证据。

### 3.3 事务级租户绑定

新增 `database_tenancy.bind_tenant_to_transaction()`：

- 先验证 organization ID 字符集与长度；
- 仅 PostgreSQL 执行 `set_config(..., true)`；
- `true` 表示事务级作用域，连接归还池后不会把租户状态泄漏给下一请求；
- 绑定发生在 JWT 类型、用户状态、token version、实时组织成员关系或 OAuth Client 所有权验证之后；
- JWT 中的 `org_id` 只是候选上下文，不能直接成为数据库权限。

## 4. 测试结果

### 4.1 已通过

- Alembic 单一迁移头：`064 (head)`；
- 新增租户上下文与 RLS 契约测试：12 项通过；
- SQLite 完整迁移升级、幂等、降级和恢复：8 项通过；
- 现有组织、Trace、SSE、Patient/Clinical、Context 跨租户回归：58 项通过；
- 本轮相关合并验证：78 项通过，耗时 109.93 秒；
- `git diff --check`：通过。

旧测试中有一项曾失败：测试把 SQLite fixture 临时切换为 cloud，只为验证 HTTP middleware。新生产闸门会更早拒绝 cloud+SQLite。测试现已显式模拟数据库预检通过，继续验证原有 middleware 语义；另有独立测试验证 cloud+SQLite 必须启动失败。

### 4.2 尚未执行/阻塞

`backend/tests/integration/test_p1_postgres_rls_attack.py` 已建立，覆盖：

- 无租户上下文读取返回零行；
- tenant A 只能读取 A 的 Trace；
- tenant A 删除 B 的 Trace 影响零行；
- tenant A 伪造 B 的 `organization_id` 写入由 `WITH CHECK` 拒绝；
- 测试角色若为 superuser/BYPASSRLS 直接失败。

本机没有可用 PostgreSQL 服务或 Docker，因此该测试结果为 `1 skipped`，不能计入发布通过。还没有对 Patient、Usage、Context、Memory 五类表逐一执行真实 PostgreSQL CRUD 攻击矩阵。

## 5. 风险与缺口

### P0：阻止 P1 发布

1. 未在专用 PostgreSQL 上执行迁移 063→064、全新建库和回滚恢复。
2. 未完成遗留 NULL 租户行的生产数据盘点、证据化回填和人工隔离处置。
3. 后台任务、定时清理和 worker 使用独立 session；启用 RLS 后必须逐条证明其显式绑定租户或使用受控维护角色，不能依赖隐式全局访问。
4. 未对七张表逐表执行真实跨租户 SELECT/INSERT/UPDATE/DELETE 攻击。
5. 尚未验证托管 PostgreSQL 应用角色权限、连接池事务复用和 pgbouncer 模式。

### P1：后续安全批次

1. PHI live-path 需要补全流式、异常、日志、第三方连接器和模型请求路径的污点测试。
2. 当前 PHI 加密主要基于环境注入的 Fernet key；真实 KMS envelope encryption、数据密钥生命周期和不可用故障模式未完成。
3. KMS rotation 端点当前侧重 version token/cache invalidation；需与真实 KMS key version、批量重加密、双读窗口、撤销旧密钥联动。
4. 审计日志需增加哈希链/签名、WORM/对象锁、保留策略、合法删除、导出完整性和断链检测。
5. OAuth delegation/API Client 需补 audience、scope/purpose narrowing、跨租户 client substitution、管理员横向/纵向越权矩阵。
6. 备份恢复需在真实 PostgreSQL 执行 PITR、密钥依赖恢复、跨版本迁移和失败回滚演练。

## 6. 后续开发批次

### Batch 1：PostgreSQL/RLS 闭环（当前进行中）

1. 启动专用 PostgreSQL 测试实例，使用独立 migration role 与 app role。
2. 执行全新建库、063→064 升级、064→063 回滚和重新升级。
3. 输出 NULL 租户逐表计数及证据来源；已确认归属的回填，未知归属的隔离并阻止发布。
4. 为 Patient、Trace、Usage、Context、Memory 建立参数化 CRUD 攻击矩阵。
5. 审计所有后台 worker/session，增加显式 tenant binding 或受控维护接口。

### Batch 2：PHI 与 KMS

1. 建立 PHI 字段/路径清单和 live-path 污点测试。
2. 接入真实云 KMS envelope encryption，分离 KEK/DEK。
3. 实现双版本解密、主动重加密、轮换进度和旧密钥撤销闸门。
4. 验证 KMS 超时、拒绝、限流和区域不可用时 fail-closed。

### Batch 3：审计不可抵赖与生命周期

1. 审计事件规范化、序列号和前序哈希。
2. 签名/时间戳和外部不可变存储。
3. 保留、法务保留、删除、导出、重放和断链检测。
4. 管理员对审计配置的篡改和绕过测试。

### Batch 4：身份与权限滥用

1. API Client/OAuth delegation 完整负面矩阵。
2. 管理员角色、组织管理员与平台管理员边界。
3. token rotation/revocation 并发与缓存失效。
4. confused-deputy、跨 audience、跨 purpose、跨 tenant 攻击。

### Batch 5：灾备和升级回滚

1. 基准备份、增量/WAL、PITR 和校验恢复。
2. KMS/密钥版本与数据库快照一致性恢复。
3. 向前迁移、失败中断、回滚和重新升级。
4. 形成 RPO/RTO 实测报告和演练证据。

## 7. 发布判定

当前状态：**P1 开发已启动；Release Gate = FAIL/BLOCKED**。

允许继续：P1 安全基础设施、测试、迁移、运行手册和演练。

禁止继续：把当前分支标记为生产基线、声称多租户数据库隔离已经通过、发布新产品能力、删除未知归属历史数据、用默认租户批量填充未知记录。

完成 Batch 1 的真实 PostgreSQL 验证并消除 P0 后，才可进入 P1 第一阶段候选标签评审。
