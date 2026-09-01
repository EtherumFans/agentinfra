# P1 数据库会话入口与连接池租户隔离审查报告

- 审查日期：2026-09-01
- 审查分支：`codex/p1-security-multitenant-gates`
- 审查起点：`e707e130402559bd42894dce1398e11a87a647cf`
- 范围：P1 后续开发第 1、2 项
  1. 审计 API、Worker、Scheduler、CLI、清理任务的数据库访问入口；
  2. 验证连接池在“租户 A → 无上下文 → 租户 B”复用序列中的隔离性。
- 结论等级：**本轮范围通过，但 P1 总发布闸门仍未通过**。

本轮可审查提交：

- `46588718` — `fix(p1): bind tenant authority across database sessions`
- `2709370e` — `test(p1): verify tenant reset across pooled connections`

## 1. 执行摘要

本轮完成了数据库会话入口的全量静态盘点、重点路径的动态验证、租户绑定修复，以及真实 PostgreSQL 上的连接池复用攻击测试。

主要结论：

1. 应用代码中共有 252 处 `Depends(get_db)` 注入入口，集中在 42 个 API 模块；这些入口的租户权威身份主要由认证依赖在同一事务内绑定。
2. 应用与脚本中共有 27 个文件直接使用异步会话工厂，另有同步 Trace/SDK 工具入口。直接会话绕开 FastAPI 依赖链，是本轮的主要风险面。
3. 已为 API 流式请求、A2A 调度与终态写入、Trace、Connector Graph、STT、租户模型路由、种子与清理脚本补齐显式事务级租户绑定。
4. 已收紧身份绑定顺序：必须先验证用户/客户端仍属于一个有效组织，再将该组织写入数据库事务上下文。仅相信令牌中的历史组织声明不再足够。
5. PostgreSQL 清理脚本不再允许默认全局扫描；必须显式传入 `--organization-id`，否则 fail closed。
6. 同步和异步 SQLAlchemy 连接池均用 `pool_size=1` 强制复用同一 PostgreSQL 后端连接。租户 A 事务提交后，`icoder.current_organization_id` 不残留；无上下文读取为 0；租户 B 只可读取 B。
7. Patient、Trace Event、Trace Run、Usage、Context、Memory Consent、Memory 七个已启用 FORCE RLS 的核心面完成真实跨租户攻击测试。
8. V2 Streams 独立测试暴露并修复了一项可信基线问题：会话工厂在模块导入时被复制，测试重绑定数据库后仍写入旧数据库；本地建表也依赖模型导入顺序。修复后 Streams 40 项测试可独立通过。

本轮没有证明整个 P1 已可发布。A2A/STT/Connector/Outbox 等更多租户表尚未全部纳入数据库 FORCE RLS，PgBouncer transaction-pooling 模式尚未验证，管理员/API Client/OAuth 滥用、KMS、审计不可抵赖、备份恢复等仍是后续闸门。

## 2. 审查标准

每个数据库入口被归入以下类别之一：

- **租户请求入口**：必须从已验证的用户、OAuth 客户端、运行令牌或持久化工作项取得组织身份，并在访问受保护表前调用事务级租户绑定。
- **租户后台入口**：允许先从不受 RLS 保护的工作索引发现任务；确定组织后，处理租户数据的事务必须绑定该组织。
- **受控维护入口**：只允许显式组织范围，或只访问系统级/目录级数据；全局操作必须具有单独的运维授权边界。
- **启动/迁移入口**：可以访问系统元数据和迁移状态，不得被普通请求触发。
- **待升级入口**：当前依靠应用层谓词或开发模式限制，尚未达到最终数据库级强制隔离标准。

租户绑定采用 PostgreSQL 事务局部设置：

```sql
SELECT set_config('icoder.current_organization_id', :organization_id, true)
```

第三个参数为 `true`，表示设置只在当前事务有效；事务提交或回滚后不可泄漏到池中的下一位租户。

## 3. 数据库入口盘点

### 3.1 统一 API 注入入口

- `Depends(get_db)`：252 处。
- 这些入口共享 `get_db()` 管理的事务生命周期。
- `get_current_user`、`get_current_client` 与混合身份依赖现在在实时组织成员关系验证后绑定租户。
- OAuth 客户端路径在校验客户端状态、所有者、组织成员关系、scope 与 delegation 后才绑定。
- Runtime Token 路径要求令牌主体仍是目标组织的有效成员；过期/撤销成员关系不再因令牌仍有效而获得数据库租户上下文。

### 3.2 直接会话入口分类

| 文件/入口 | 类别 | 本轮状态 | 说明 |
|---|---|---|---|
| `app/api/run_trace.py` | 租户请求 | 已绑定 | Trace/RunHistory 查询和同步列表均绑定请求组织。 |
| `app/api/runs.py` | 租户请求 | 已绑定 | Trace URL、SSE 首查和持续状态轮询绑定签名令牌组织；云模式拒绝空组织令牌。 |
| `app/api/v2_tools_streams.py` | 租户请求 | 已绑定 | 认证后所有 checkpoint、持久化和审计新会话绑定 principal 组织；改为运行时读取统一会话工厂。 |
| `app/icoder/agent_runtime/a2a/v1/routes.py` | 租户请求 | 已绑定 | 流式 A2A 新会话绑定组织。 |
| `app/icoder/agent_runtime/a2a/v1/task_runtime.py` | 租户后台 | 已绑定 | dispatch、claim、context recovery、artifact、settle、fail 均绑定 execution 组织；heartbeat/release 先发现工作项再绑定。 |
| `connector_graph_dispatch_handler.py` | 租户后台 | 已绑定 | 已知组织后绑定再执行图调度。 |
| `provider_a2a_handler.py` | 租户后台 | 已绑定 | Run 创建、Provider 失败与成功终态均显式传入并绑定组织。 |
| `tenant_clone_a2a_dispatch_handler.py` | 租户后台 | 已绑定 | 克隆运行路径绑定目标组织。 |
| `services/connector_graph.py` | 租户后台 | 已绑定 | 图执行/状态写入绑定组织。 |
| `services/stream_session_lease.py` | 租户请求 | 已绑定 | 获取、续租、释放会话租约均绑定 scope 组织。 |
| `services/stt_jobs.py` | 租户后台 | 已绑定 | 已知 STT 工作项组织后的事务绑定。 |
| `services/tenant_model_routing.py` | 租户请求/后台 | 已绑定 | 租户模型路由读取绑定目标组织。 |
| `app/seed.py` | 启动/种子 | 已绑定 | 写入受保护 Billing Transaction 前绑定默认组织。 |
| `scripts/purge_retention.py` | 受控维护 | 已收紧 | PostgreSQL 必须显式 `--organization-id`；不再允许无范围清理。 |
| `scripts/purge_agent_feedback.py` | 受控维护 | 已收紧 | PostgreSQL 必须显式 `--organization-id`。 |
| `scripts/sdk_sse_fixture.py` | 租户测试工具 | 已绑定 | 同步 RunHistory/Trace 写入、更新和清理均绑定 fixture 组织。 |
| `app/database.py` | 中央工厂/启动 | 已修复 | 生产启动校验 PostgreSQL、迁移版本、运行角色与 FORCE RLS；本地建表先注册全部模型。 |
| `app/main.py` | 启动/恢复发现 | 受控 | 生产数据库校验、启动恢复扫描；租户工作处理在后续路径绑定。 |
| `middleware/partner_cors.py` | 请求前发现 | 待升级 | 认证前按 partner 配置发现允许来源；目前是全局配置读取，不应读取受保护 PHI。需要独立系统配置表/缓存边界。 |
| `services/clinical_model_shadow_job.py` | 租户后台发现 | 部分受控 | Shadow job 调度依赖应用谓词；开发/影子模式使用。其表尚未纳入核心 FORCE RLS。 |
| `scripts/clinical_model_shadow_job_worker.py` | Worker | 部分受控 | 全局发现待处理任务；任务执行需要按组织收口。建议纳入下一批 RLS。 |
| `scripts/clinical_model_shadow_scheduler.py` | Scheduler | 部分受控 | 聚合/生成影子任务；当前属于开发验证面，不是生产租户强隔离完成项。 |
| `scripts/process_invite_outbox.py` | Worker | 部分受控 | 全局发现 outbox；需证明 claim 与处理不会跨租户混淆，并为 outbox 增加 RLS/系统队列边界。 |
| A2A 启动恢复扫描 | 后台发现 | 部分受控 | 允许发现未完成 execution；确定 execution.organization_id 后已绑定。execution/event 表仍建议纳入 FORCE RLS。 |
| STT 启动恢复扫描 | 后台发现 | 部分受控 | 允许发现未完成 job；处理已知组织时绑定。STT artifact/checkpoint 表仍建议纳入 FORCE RLS。 |
| `app/api/runtime_platform.py` | 开发管理入口 | 待升级 | 开发安装接口与 Agent 目录查询当前不属于七表 RLS；需要管理员滥用与生产禁用验证。 |
| `scripts/bootstrap_platform_admin.py` | 启动/管理 | 受控维护 | 平台管理员引导，不应在普通请求进程执行；需由部署权限控制。 |
| `phase5_d_p05_gate7_seed_roles.py` | 迁移/种子 | 受控维护 | 角色种子与修复，要求离线运维权限。 |
| `phase5_d_p05_repair_inconsistent_cases.py` | 数据修复 | 受控维护 | 跨记录修复脚本；不能交给应用运行角色。 |
| `scripts/seed_agents.py` | 系统目录种子 | 受控维护 | 预置 Agent 是系统目录数据；需保持与租户实例数据分离。 |

### 3.3 入口审计的自动防回归

新增静态契约测试 `tests/unit/app/test_p1_database_session_audit.py`：

- 扫描直接核心会话文件，要求出现租户绑定；
- 校验通过认证依赖间接绑定的关键路径；
- 校验 PostgreSQL 清理脚本必须要求显式组织参数；
- 动态验证实时成员关系成功后才绑定；
- 动态验证失效/不存在的成员关系被拒绝。

该测试不是对代码审查的替代，但能阻止后续新增直接会话时悄悄绕过租户绑定。

## 4. 本轮修复详情

### 4.1 同步与异步事务绑定

- 保留异步 `bind_tenant_to_transaction`。
- 新增 `bind_tenant_to_sync_session`，供同步 Trace Store 和 SDK fixture 使用。
- 两者共享组织 ID 格式校验，拒绝空值与不安全字符。
- 均使用事务局部 `set_config(..., true)`，不使用连接级持久设置。

### 4.2 认证权威链

新增实时成员关系绑定步骤：

1. 校验令牌签名、类型和主体；
2. 查询 User / API Client 当前状态；
3. 查询 OrganizationMember 与 active Organization；
4. 校验 scope、delegation 与所有者关系；
5. 最后绑定组织到当前数据库事务。

Runtime Token 的租户声明不再单独构成授权。成员被移除、组织失效或客户端失效后，即使旧令牌尚未过期，也不能获得租户上下文。

### 4.3 Trace Token 兼容与 fail-closed

- 有组织声明的签名 Trace Token：直接使用签名内组织。
- 旧版空组织 Token：只在 `ICODER_DEPLOYMENT_MODE=local` 且配置了唯一 `ICODER_SINGLE_TENANT_ORG_ID` 时映射到该唯一组织。
- Cloud：空组织 Token 返回 `401 TRACE_TOKEN_MALFORMED`。
- SSE 的首次 RunHistory 读取和后续轮询使用相同组织绑定。

### 4.4 清理任务

在 PostgreSQL 上，Retention 与 Agent Feedback 清理必须指定组织。理由：

- 普通应用角色在无租户上下文时应看到 0 行；
- 为清理方便而给予 BYPASSRLS 会破坏发布闸门；
- 全局清理应由显式的运维控制面按租户迭代，而不是由普通脚本隐式跨租户扫描。

### 4.5 测试数据库可复现性

发现两个顺序相关问题：

1. `init_db()` 在模型尚未导入时读取 `Base.metadata`，部分表可能不创建；
2. V2 Streams 在模块导入时复制 `AsyncSessionLocal`，测试重绑定数据库后仍使用旧工厂。

修复后：

- `init_db()` 先导入完整 `app.models`；
- V2 Streams 运行时从 `app.database` 读取当前会话工厂；
- 生产仍不调用 `create_all`，生产结构继续由 Alembic 独占管理。

## 5. 连接池复用攻击测试

### 5.1 环境

- PostgreSQL：本机 WSL PostgreSQL 18.6。
- 数据库：迁移到 Alembic revision `064` 的一次性 P1 gate 数据库。
- 应用角色：非 superuser、无 BYPASSRLS。
- 受保护表：启用 RLS、FORCE RLS、`organization_id NOT NULL`。
- 同步驱动：psycopg。
- 异步驱动：asyncpg。

### 5.2 强制复用序列

同步池和异步池分别执行同一序列，池大小固定为 1：

1. 获取连接并记录 `pg_backend_pid()`；
2. 开始租户 A 事务，设置事务局部组织，确认只能看到 A；
3. 提交并归还连接；
4. 再次获取连接，确认 `pg_backend_pid()` 相同；
5. 不设置组织，确认 `current_setting(..., true)` 为空且受保护表读取为 0；
6. 开始租户 B 事务，设置组织 B，确认只能看到 B；
7. 回滚/提交并清理测试数据。

### 5.3 结果

| 检查 | 同步池 | 异步池 |
|---|---:|---:|
| 强制同一 PostgreSQL backend PID | 通过 | 通过 |
| A 事务内只见 A | 通过 | 通过 |
| A 提交后组织设置为空 | 通过 | 通过 |
| 无上下文读取为 0 | 通过 | 通过 |
| B 事务内只见 B | 通过 | 通过 |
| A 数据未泄漏给 B | 通过 | 通过 |

这证明当前 `SET LOCAL` 等价实现与 SQLAlchemy 默认事务归还行为配合时，不会把租户上下文留在连接池中。

### 5.4 七表攻击矩阵

真实 PostgreSQL 测试覆盖：

- Patient：`patient_contexts`
- Trace Event：`run_trace_events`
- Trace Run：`run_history`
- Usage：`transactions`
- Context：`contexts`
- Memory consent：`memory_consents`
- Memory：`conversation_memories`

对每个表验证：

- 无上下文 SELECT 返回 0；
- A 不能 SELECT B；
- A 不能 UPDATE B；
- A 不能 DELETE B；
- A 不能伪造插入 organization_id=B；
- A 只能读取/修改 A；
- B 对称成立。

结果：3 个真实 PostgreSQL 测试全部通过，其中包含七表攻击矩阵、同步池复用、异步池复用。

### 5.5 测试残留

测试完成后对组织表及七个受保护表执行只读残留统计，所有 `p1a_*` / `p1b_*` 测试组织与数据计数均为 0。

## 6. 验证证据

| 验证批次 | 结果 |
|---|---:|
| 数据库绑定、入口审计、组织角色、Runtime Token、Context 清除、临床边界、Connector/STT/Lease、RLS 契约、迁移可移植性 | 76 passed |
| A2A clone/provider/v1 runtime、Trace capture、Trace persistence | 47 passed |
| Trace retention、Console 隔离、orphan-run denial | 26 passed |
| V2 Streams 独立执行 | 40 passed |
| 数据库绑定 + 静态入口审计 + V2 Streams 复跑 | 53 passed |
| 真实 PostgreSQL 七表攻击 + 同步/异步池复用 | 3 passed |
| Python `compileall` | 通过 |
| `git diff --check` | 通过 |
| PostgreSQL 测试残留 | 0 |
| 工作区验证产物清理 | 3 个临时虚拟环境、50 个 Python/pytest 缓存目录、1 个测试数据库已删除 |

说明：上述批次存在测试重叠，因此不将数字简单相加为“唯一测试总数”。

## 7. 风险与未完成项

### P0/P1 发布阻断

1. **RLS 覆盖仍不完整**：A2A executions/events、STT artifacts/checkpoints/jobs、Connector 运行记录、Shadow jobs、Invite outbox 等租户拥有表尚未全部纳入 FORCE RLS。
2. **生产代理池未验证**：本轮验证 SQLAlchemy 同步/异步本地池；若生产使用 PgBouncer transaction pooling，仍需在同拓扑、同参数下复测。
3. **维护控制面未完成**：跨租户 retention、审计导出、删除与备份操作需要独立运维角色、审批、审计和按租户迭代器。
4. **Runtime Platform 管理边界**：开发安装接口必须证明云模式关闭，并完成管理员权限滥用测试。
5. **Partner CORS 发现**：认证前全局配置读取需要独立系统配置边界，不能与租户 PHI 数据共用宽权限路径。

### P1 后续闸门

1. API Client、OAuth delegation 与管理员权限滥用矩阵；
2. PHI live-path 脱敏与数据库静态加密覆盖；
3. KMS 接入、密钥轮换、旧密文读取与撤销演练；
4. 审计日志不可抵赖、保留、删除、导出验证；
5. 备份恢复、迁移升级与回滚演练；
6. 将本轮新增测试纳入 PR CI 的 PostgreSQL job，而不是只在本机手动执行。

### 环境基线风险

`requirements.txt` 声明 Python 3.11+，但固定版本中的 asyncpg、NumPy、PyYAML、RapidFuzz 等并不完整支持 Python 3.14 的二进制安装。本轮最终使用 Python 3.12.13 重建固定依赖并完成应用回归。建议将受支持版本明确为 3.11/3.12/3.13 的 CI 矩阵，或升级锁定依赖后再宣称支持 3.14。

## 8. 建议的下一开发顺序

1. 建立“租户拥有表清单”，为剩余 A2A/STT/Connector/Outbox 表增加 `organization_id NOT NULL + FORCE RLS + 同一策略名`。
2. 将后台任务拆成“系统级发现事务”和“租户级处理事务”；处理事务必须先绑定组织，禁止一个事务处理多个租户。
3. 在 CI 启动 PostgreSQL 应用角色与迁移角色，执行本轮三项 live gate；增加 PgBouncer transaction-mode job。
4. 执行 API Client/OAuth/Admin 攻击矩阵，特别验证撤销成员关系、撤销 delegation、客户端失效后的旧令牌。
5. 随后进入 PHI 加密/KMS 与审计不可抵赖性工作；最后做备份恢复和升级回滚演练。

## 9. 本轮完成判定

- 第 1 项“数据库入口审计”：**完成**。已形成入口分类、完成关键直接会话修复并增加防回归测试。
- 第 2 项“连接池租户隔离”：**完成（本地 SQLAlchemy 同步/异步池）**。A → 空上下文 → B 复用序列通过。
- P1 总发布闸门：**未完成**。必须关闭第 7 节中的发布阻断项后才能候选发布。
