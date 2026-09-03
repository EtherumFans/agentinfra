# P1 Batch 1：PostgreSQL 与多租户 RLS 真实验证审查报告

- 审查日期：2026-09-01（Asia/Shanghai）
- 分支：`codex/p1-security-multitenant-gates`
- 审查对象源码提交：`399a984d7032ba1082ba998bab5a1623cb2ad75d`
- 前置 P1 提交：`8b82e0c6`（RLS 发布闸门）、`3489fd56`（启动审查）
- 本轮提交：`dc0e675c`（迁移链兼容修复）、`399a984d`（七表攻击矩阵）
- 判定：**Batch 1 的本地真实 PostgreSQL 数据库闸门通过；P1 总发布闸门仍为 FAIL/进行中。**

## 1. 审查范围与边界

本轮继续冻结新产品能力，只验证 PostgreSQL 权威存储和数据库级租户隔离：

1. 从空 PostgreSQL 数据库执行完整 Alembic 链到 063。
2. 执行 063→064、064→063、063→064 升降级演练。
3. 核验应用/迁移角色无超级用户和 `BYPASSRLS` 权限。
4. 核验 Patient、Trace、Usage、Context、Memory 七张核心表的 `NOT NULL`、RLS、FORCE RLS 和对称策略。
5. 以真实应用角色执行跨租户读、改、删、租户字段篡改攻击。
6. 修复由真实 PostgreSQL 揭示、而 SQLite 契约测试未揭示的迁移链缺陷。

本报告不把本地 WSL PostgreSQL 等同于托管生产环境，也不覆盖 PHI/KMS、审计不可抵赖、OAuth/管理员滥用、PITR/RPO/RTO 等后续批次。

## 2. 验证环境

| 项目 | 实际值 |
|---|---|
| 宿主 | Windows + WSL Ubuntu 26.04 |
| PostgreSQL | 18.6，集群 `18/main`，page checksums 启用 |
| Python（PG 验证侧） | 3.14.4 |
| SQLAlchemy | 2.0.45 |
| Alembic | 1.18.4 |
| psycopg | 3.3.2 |
| pytest | 9.0.2 |
| 测试数据库 | `icoder_p1_gate`（本地隔离库） |
| 迁移角色 | `icoder_p1_migration`：非 superuser、非 BYPASSRLS、可建库、不可建角色 |
| 应用角色 | `icoder_p1_app`：非 superuser、非 BYPASSRLS、不可建库、不可建角色 |

Windows 项目虚拟环境继续用于锁定依赖下的回归；WSL 系统依赖只用于真实 PostgreSQL 语义验证，不构成仓库依赖变更。

应用角色没有获得全 schema 默认权限。一次拟议的全表/默认权限授权因范围过宽被拒绝，最终只授权 `public` schema 使用权、`alembic_version`/`organizations` 读取权及七张明确核心表的测试所需 CRUD 权限；没有修改未来对象默认权限。

## 3. 真实迁移链发现与修复

### 3.1 Alembic 异步驱动耦合

原在线迁移直接使用异步运行时 URL 和异步引擎，导致 Windows/WSL 驱动与事件循环行为不一致。Alembic 现使用短生命周期同步引擎，并确定性转换：

- `sqlite+aiosqlite` → `sqlite`
- `postgresql+asyncpg` / `postgresql` → `postgresql+psycopg`

运行时 API 仍可使用异步驱动；迁移工具与运行时驱动已解耦。

### 3.2 PostgreSQL 不接受布尔列 `DEFAULT 0/1`

完整空库升级首先在迁移 004 失败。对迁移链进行语法树扫描后，将涉及布尔列的数字字符串默认值统一改为 `sa.false()` / `sa.true()`，覆盖 004、005、010、011、032、058、061，并增加全迁移目录回归约束。

### 3.3 Trace 状态列长度不足

迁移 020 把 `NEVER_CAPTURED_LEGACY` 写入 `VARCHAR(16)`，真实 PostgreSQL 严格拒绝。迁移和 ORM 模型统一扩为 `VARCHAR(32)`；降级先规范化状态，再缩回 16。

### 3.4 临床历史数据被错误归入默认租户

迁移 021 原计划把 NULL/空 `organization_id` 无证据地写入 `org_default1`，这会制造跨租户 PHI 归属。现改为逐表计数并硬失败，错误信息要求 evidence-backed reconciliation；不再自动修改未知归属。

同一迁移原先通过捕获重复索引异常实现“幂等”。PostgreSQL 中 DDL 异常会使整个事务进入 aborted 状态，因此改为执行 DDL 前用 SQLAlchemy inspector 判断对象是否存在。

### 3.5 SQLite 专用 introspection 与吞异常

迁移 022/023 使用 `PRAGMA table_info`，在 PostgreSQL 上失败；约束/索引 DDL 还会捕获异常后继续。现统一改为跨数据库 inspector，并在执行前检查列、索引和约束。

### 3.6 Context 表使用 SQLite 专用类型

迁移 024 的原始 SQL 使用 `DATETIME` 和 `BOOLEAN DEFAULT 1`，PostgreSQL 无法执行。现用 Alembic/SQLAlchemy 创建表、外键、索引、日期和布尔默认值，并在表已存在时安全跳过。

### 3.7 状态约束替换会破坏 PostgreSQL 外键

迁移 055 使用 `batch_alter_table(recreate="always")` 重建 `context_task_refs`。真实升级到 055 时，PostgreSQL 因 `a2a_task_artifacts` 依赖其主键而拒绝删除主键约束。

现行为：

- PostgreSQL：只删除并重建目标 CHECK 约束，不重建表或主键；
- SQLite：保留 batch recreation 兼容路径。

## 4. 升级、降级和目录状态验证

### 4.1 空库升级

修复上述缺陷后，空数据库从根迁移完整升级到 063 成功，再升级到 064 成功。最终 `alembic_version = 064`，且 064 是单一 head。

### 4.2 064 回滚与恢复

执行 064→063 成功。降级后：

- `icoder_tenant_isolation` 策略数量为 0；
- 七表 `relrowsecurity = false`；
- 七表 `relforcerowsecurity = false`。

随后执行 063→064 再升级成功，版本恢复为 064。该结果证明本次闸门迁移自身可逆，但不代表所有未来生产数据都天然可降级；实际发布仍需在生产快照上验证数据兼容性。

### 4.3 064 最终数据库属性

七张表均满足：

- `organization_id IS NOT NULL`（catalog 显示 `is_nullable = NO`）；
- `relrowsecurity = true`；
- `relforcerowsecurity = true`；
- 存在 `icoder_tenant_isolation`、命令范围 `ALL`；
- `USING` 与 `WITH CHECK` 表达式相同；
- 租户上下文来自事务级 `icoder.current_organization_id`。

## 5. 跨租户攻击矩阵

攻击测试由 `icoder_p1_app` 执行；测试首先断言当前角色不是 superuser 且没有 BYPASSRLS。每张表预置 tenant A/B 合法记录，然后执行相同攻击。

| 业务面 | 表 | 无上下文读取 | A 读取 B | A 修改/删除 B | A 把自身行改成 B |
|---|---|---:|---:|---:|---:|
| Patient | `patient_contexts` | 0 行 | 不可见 | 0 行 | DB 拒绝 |
| Trace | `run_trace_events` | 0 行 | 不可见 | 0 行 | DB 拒绝 |
| Trace | `run_history` | 0 行 | 不可见 | 0 行 | DB 拒绝 |
| Usage | `transactions` | 0 行 | 不可见 | 0 行 | DB 拒绝 |
| Context | `contexts` | 0 行 | 不可见 | 0 行 | DB 拒绝 |
| Memory | `memory_consents` | 0 行 | 不可见 | 0 行 | DB 拒绝 |
| Memory | `conversation_memories` | 0 行 | 不可见 | 0 行 | DB 拒绝 |

结果：真实 PostgreSQL 集成测试 `1 passed`。测试结束后检查 organization/user/agent 临时依赖，残留计数为 0。

该矩阵同时验证 `USING`（读、改、删可见性）和 `WITH CHECK`（租户字段篡改）。当前测试尚未覆盖连接池/pgbouncer 事务复用及所有后台 worker。

## 6. 回归结果

| 验证组 | 结果 |
|---|---:|
| P1 RLS 契约 + SQLite 完整迁移可移植性 | 20 passed（最终重复验证） |
| 上述 20 项 + 租户绑定、临床边界、组织隔离 | 56 passed / 50.12s |
| Trace 控制台、SSE、Context 跨租户回归 | 29 passed / 56.93s |
| 真实 PostgreSQL 七表攻击矩阵 | 1 passed / 0.51s |
| Python 编译检查 | passed |
| `git diff --check` | passed |
| 测试数据残留检查 | 0 |

不重复计数时，本轮覆盖 85 项 Windows 锁定环境测试 + 1 项真实 PostgreSQL 参数化攻击矩阵。`ruff` 未安装，因此没有把 lint 标记为已执行；这不是测试失败，但应由标准 PR CI 补齐。

## 7. 代码与报告变更清单

### 7.1 迁移执行基础

- `backend/alembic/env.py`
- `backend/alembic/versions/004_coding_review_run.py`
- `backend/alembic/versions/005_context_tables.py`
- `backend/alembic/versions/010_run_history.py`
- `backend/alembic/versions/011_cdi_models.py`
- `backend/alembic/versions/020_trace_event_identity_and_capture_state.py`
- `backend/alembic/versions/021_clinical_tables_tenant_not_null.py`
- `backend/alembic/versions/022_expert_registry_provenance.py`
- `backend/alembic/versions/023_agent_canonical_key_and_alias.py`
- `backend/alembic/versions/024_context_task_state_check.py`
- `backend/alembic/versions/032_cdi_notification_subscriptions.py`
- `backend/alembic/versions/055_a2a_v1_interrupted_task_states.py`
- `backend/alembic/versions/058_clinical_model_package_governance.py`
- `backend/alembic/versions/061_clinical_model_shadow_evaluation_jobs.py`
- `backend/app/models/run_history.py`

### 7.2 验证资产

- `backend/tests/test_api/test_p1_postgresql_tenant_rls_contract.py`
- `backend/tests/test_api/test_a1a_gate3r_5_migration_portability.py`
- `backend/tests/integration/test_p1_postgres_rls_attack.py`

旧可移植性测试中“PostgreSQL 环境阻塞”的过时断言已移除，改为验证真实集成闸门存在、需要双角色 URL、检查角色能力并覆盖七个攻击面。

## 8. 当前风险与发布判定

### 8.1 本轮已关闭

1. 空 PostgreSQL 数据库无法完整执行旧迁移链。
2. 063→064 没有真实执行证据。
3. 064 自身没有降级/再升级证据。
4. 七表 RLS 只存在代码契约、没有真实数据库攻击证据。
5. 旧迁移可能把未知临床数据归入默认租户。

### 8.2 仍阻止 P1 发布

1. 生产/候选数据的 NULL、空值和错误租户归属尚未完成证据化盘点与人工对账；迁移现在会正确阻止，但阻止不等于数据已修复。
2. 后台任务、清理任务、队列 worker、迁移维护脚本尚未逐一证明显式 tenant binding 或受控维护角色。
3. 尚未验证 pgbouncer/连接池事务复用时租户上下文不会泄漏。
4. 尚未在托管 PostgreSQL、生产等价网络/身份权限中重演。
5. PR CI 全量矩阵、Node/.NET/SDK/前端构建不属于本次局部 P1 代码验证，仍需在候选集成点执行。
6. PHI、KMS、审计不可抵赖、OAuth/管理员滥用、备份恢复仍是 P1 后续主批次。

因此：**允许继续 P1 安全开发；禁止把当前提交标记为生产发布基线。**

## 9. 建议的下一开发内容

下一步应继续 Batch 1 的运行路径闭环，而不是进入新产品能力：

1. 枚举所有创建数据库 session 的 API、worker、scheduler、CLI 和清理任务。
2. 对每条路径标注“租户用户流 / 系统维护流”，租户流强制事务级绑定，维护流使用独立最小权限角色和显式审计。
3. 增加连接复用测试：tenant A 事务结束后，同一池连接在无上下文及 tenant B 下均不可读取 A。
4. 在生产数据副本上输出七表和临床表的 NULL/空/非法组织 ID 计数及可追溯对账清单。
5. 在完成上述 P0 项后，再进入 PHI live-path 与 KMS envelope encryption 批次。

本地 WSL PostgreSQL 服务、测试库和两个测试角色暂时保留，便于下一步连接池与 worker 验证；它们不在项目目录、不包含生产数据或生产密钥。
