# P1 Revision 065 实施与验证报告

日期：2026-09-01
范围：Batch 2 Wave 1 — Context / A2A 九张租户表
数据库权威：PostgreSQL
目标 revision：`065`

## 1. 实施结论

Revision 065 已实现九张表的租户字段回填、非空约束、数据库级租户一致性约束及 PostgreSQL `ENABLE/FORCE ROW LEVEL SECURITY`。生产启动门禁同步提升到 `065`，受保护表由 7 张增加到 16 张。

本轮没有授予应用角色 `SUPERUSER` 或 `BYPASSRLS`。所有策略继续使用事务局部的 `icoder.current_organization_id`，未绑定租户时查询结果为空，跨租户写入由 `WITH CHECK` 拒绝。

## 2. 纳入 065 的表

1. `context_messages`
2. `context_task_refs`
3. `context_artifact_refs`
4. `original_input_audit`
5. `a2a_task_executions`
6. `a2a_task_events`
7. `a2a_task_artifacts`
8. `a2a_artifact_objects`
9. `a2a_artifact_download_grants`

其中五张历史子表新增 `organization_id`：前三张 Context 子表、`original_input_audit` 和 `a2a_task_artifacts`。

## 3. 数据迁移与失败关闭

- Context 子表和原始输入审计从 `contexts.organization_id` 回填。
- Task Artifact 通过 `context_task_refs` 回填。
- 回填后逐表检查 `NULL`；发现无法归属的历史行会中止迁移并报告表级数量，不会写入“unknown”或默认租户。
- 对已有租户字段的 Execution、Event、Artifact Object 和 Download Grant 检查父子租户是否一致；不一致时中止迁移。
- PostgreSQL 将九张表的 `organization_id` 设为 `NOT NULL` 并建立组织索引。

## 4. 数据库级租户一致性

065 建立以下复合所有权链：

`contexts` → Context 子表 / Execution / Event → Task Artifact → Artifact Object → Download Grant。

父表增加必要的 `(organization_id, ...)` 唯一键，子表使用包含 `organization_id` 的复合外键，阻止应用层疏漏导致父子行跨租户拼接。

`original_input_audit` 是刻意的例外：它必须在 Context 按生命周期删除后继续保留，因此不建立指向 `contexts` 的外键；其归属由不可空 `organization_id` 与 FORCE RLS 独立维持。

## 5. 运行时改造

- Context Repository 新写入 Message、Task Ref、Artifact Ref 时，从已验证的父 Context 复制组织标识。
- Artifact Store 从父 Task Ref 复制组织标识。
- Context Audit 在父 Context 仍存在时继承其组织标识，也允许受控调用方显式传入组织标识。
- A2A 调度入口从创建时开始携带组织标识；Claim、Heartbeat、Lease Release、Finish 和 Fail 均在任何受保护查询前绑定租户。
- 服务启动恢复不再执行跨租户 Task 扫描，而是从平台控制表读取组织清单，随后逐租户绑定并扫描可恢复任务。

## 6. SQLite 兼容边界

SQLite 继续只用于本地和测试，不是生产权威。065 在 SQLite 中新增并回填五个字段，但不启用 PostgreSQL RLS，也不强制生产复合外键。ORM 保留旧单列级联关系，使历史本地夹具继续工作；生产约束只由 Alembic 065 建立。

## 7. 验证结果

- Python 编译与差异空白检查：通过。
- 静态租户清单与迁移契约：18 项中 17 项通过；余下一项首次因系统 Python 缺少 `aiosqlite` 而未加载，随后在完整临时环境中迁移契约 13/13 通过。
- Context Schema 与 Audit 回归：22/22 通过。
- A2A 后台任务回归：6/6 通过，覆盖提交、租约释放、恢复、分块结果、失败终态、取消和 Context 擦除。
- PostgreSQL 同步攻击矩阵：4/4 通过。
- PostgreSQL 异步连接池租户复用：1/1 通过。
- 真实 064→065：通过。
- 真实 065→064→065：通过，最终为 `065 (head)`。
- 机器清单与实时 PostgreSQL schema：一致，82 张数据库表。

## 8. 清单变化

- 含 `organization_id` 的数据库表：67 → 72。
- `organization_id NOT NULL`：45 → 50。
- FORCE RLS 表：7 → 16。
- 仍缺直接租户字段的间接租户表：9 → 4；剩余项属于后续 CDI 波次。

## 9. 环境与清理

- 临时 Python 测试环境和临时 SQLite 测试库已删除。
- 临时 PostgreSQL 验证库使用独立名称并在验证后删除。
- `.gitignore` 增加 SQLite `-wal` / `-shm` 侧车文件规则，避免运行时缓存污染工作树。
- 本机 P1 PostgreSQL 测试应用角色只补齐九张表的普通 DML/序列权限；这属于测试环境配置，不写入迁移，也不绑定生产角色名。

## 10. 后续建议

1. 在 CI 的独立 PostgreSQL 服务中固化“空库到 head”和“064→065”两个迁移作业。
2. 将九表攻击链加入必跑 PR gate，并使用 CI 创建的非 owner、非 BYPASSRLS 应用角色。
3. 启动 Batch 2 Wave 2 前，先处理剩余四张 CDI 间接租户表的直接租户字段设计。
4. 为全租户后台恢复增加分页和并发上限，避免组织数量增长后启动扫描时间线性放大。
