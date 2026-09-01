# P1 Revision 066 实施与验证报告

日期：2026-09-01
范围：Batch 2 Wave 2 — STT / Streams 六张租户表
数据库权威：PostgreSQL
目标 revision：`066`

## 1. 审查结论

Revision 066 已将 STT 录音、转录任务和可恢复流状态纳入 PostgreSQL 数据库级租户发布闸门。六张表均已有非空 `organization_id`，本轮补齐了可验证的父子所有权链、`ENABLE/FORCE ROW LEVEL SECURITY`、事务局部租户策略和运行时租户绑定。

生产启动期望 revision 已从 `065` 提升到 `066`，受 FORCE RLS 保护的表从 16 张增加到 22 张。应用测试角色保持 `NOSUPERUSER`、`NOBYPASSRLS`；未绑定租户时六表读取均为零，跨租户写入由 RLS 或复合外键拒绝。

此前 065 报告中“Wave 2 前先处理 CDI”的建议与已批准租户清单的波次定义不一致。本报告以权威清单为准：Wave 2 是 STT / Streams；CDI 仍属于 Wave 5。

## 2. 纳入 revision 066 的表

1. `stt_interactions`
2. `stt_recordings`
3. `stt_transcripts`
4. `stt_stream_leases`
5. `stt_stream_checkpoints`
6. `stt_stream_checkpoint_chunks`

六张表的 `organization_id` 均已是 `NOT NULL`，因此本轮不做猜测性回填，也不引入默认或 `unknown` 租户。

## 3. 迁移前对账与失败关闭

066 在建立约束和 RLS 前执行以下检查：

- 六表逐表检查 `organization_id IS NULL`。
- `stt_interactions.organization_id` 必须指向真实 `organizations.id`。
- Recording、Transcript、Stream Lease、Stream Checkpoint 必须存在同一 `(organization_id, owner_id, interaction_id)` 的 Interaction。
- Checkpoint Chunk 继续使用既有的 Checkpoint 复合外键。

任何孤儿或无法归属的数据都会使迁移中止，并以 `migration 066 requires evidence-backed STT tenant reconciliation` 报告表级类别和数量。迁移不会自动猜测归属，也不会静默丢弃、隔离或改写数据。

## 4. 数据库所有权链

066 建立并验证以下完整链路：

`organizations` → `stt_interactions` → `stt_recordings` / `stt_transcripts` / `stt_stream_leases` / `stt_stream_checkpoints` → `stt_stream_checkpoint_chunks`

新增五个外键：

- `fk_stt_interactions_organization`
- `fk_stt_recordings_interaction_scope`
- `fk_stt_transcripts_interaction_scope`
- `fk_stt_stream_leases_interaction_scope`
- `fk_stt_stream_checkpoints_interaction_scope`

除组织根外，子关系均把 `organization_id` 放进复合键，数据库因此能阻止不同租户之间拼接相同 owner 或 interaction 标识。Interaction 删除对子资源使用级联；组织删除仍受根外键限制，避免无意清除临床语音产物。

## 5. RLS 策略

六张表统一执行：

- `ENABLE ROW LEVEL SECURITY`
- `FORCE ROW LEVEL SECURITY`
- 策略名 `icoder_tenant_isolation`
- `USING` 与 `WITH CHECK` 均比较 `organization_id` 和事务局部的 `icoder.current_organization_id`

租户值通过 `set_config(..., true)` 绑定到当前事务，事务提交或回滚后自动清除。应用层的组织条件仍保留以表达查询意图，但最终边界由 PostgreSQL 强制执行。

## 6. 运行时修正

### 6.1 STT Artifact Repository

Repository 的读取、创建、更新、删除及转录状态/遥测写入，在首次接触受保护表前统一绑定已验证的组织标识。`list_processing` 不再允许全局扫描，调用者必须显式传入 `organization_id`。

### 6.2 启动恢复

审查发现原有 `recover_pending_stt_jobs()` 会在一次未绑定租户的事务中全表扫描 processing transcript。启用 FORCE RLS 后该查询会安全地返回零，但也会导致所有待恢复任务被遗漏。

现实现先从平台控制表 `organizations` 读取组织标识，再为每个组织创建独立事务、绑定租户并读取待恢复任务。SQLite 本地开发模式额外兼容早于组织外键的历史 STT 数据；该兼容分支不会用于 PostgreSQL 生产权威路径。

### 6.3 ORM 一致性

新增数据库外键已同步写入 ORM 元数据，避免通过 ORM 创建的测试 schema 与 Alembic 生产 schema 漂移。

## 7. 攻击与回归验证

### 7.1 静态与功能测试

- Python 编译检查：通过。
- 生产启动数据库门禁（revision、角色属性、NOT NULL、策略和 FORCE RLS）：通过。
- 租户清单与迁移静态契约：18/18 通过（另有 1 项 cloud SQLite 测试按本组验证目标排除）。
- STT 恢复、Artifact Repository、遥测、Stream Lease、Checkpoint Repository、STT HTTP 与 WebSocket API 回归：165/165 通过（同一 cloud SQLite 项排除）。
- 差异空白检查：通过。

### 7.2 真实 PostgreSQL 攻击矩阵

完整同步与异步矩阵：6/6 通过，包含：

- 实时 schema 与租户表清单一致。
- Patient、Trace、Usage、Context、Memory 核心面保持隔离。
- revision 065 Context / A2A 九表保持隔离。
- revision 066 STT / Streams 六表在未绑定、租户 A、租户 B 三种上下文中行为正确。
- 错误租户写入被 RLS 或外键拒绝。
- 同步连接池 A → 未绑定 → B 复用无租户泄漏。
- 异步连接池 A → 未绑定 → B 复用无租户泄漏。

STT / Streams 攻击用例通过非超级用户、非 `BYPASSRLS` 的应用角色实际插入六层数据，并逐表验证可见性，不是仅检查策略定义。

## 8. 迁移、回滚与重建演练

- 现有本机 P1 数据库 `065 → 066`：通过，最终 `066 (head)`。
- 同一数据库 `066 → 065 → 066`：通过，最终 `066 (head)`。
- 专用空库从 revision 000 全量迁移到 head：通过。
- 空库重建结果：82 张业务/迁移表，22 张表启用并强制 RLS。
- 实际查询确认六个 STT 所有权外键均存在（含既有 Chunk → Checkpoint 外键）。
- 专用验证数据库 `icoder_p1_066_verify` 已在验证结束后删除。

## 9. 权威清单变化

- 权威 revision：`065 → 066`
- 数据库表：82（不变）
- 含 `organization_id` 的数据库表：72（不变）
- `organization_id NOT NULL`：50（不变）
- FORCE RLS 表：`16 → 22`
- 间接租户但尚无直接 `organization_id` 的表：4（不变，留待 CDI Wave 5）

清单新增 `batch_2_second_wave_tables`，六张表均标记为 `batch2_wave2_complete`；汇总数字由表行自动派生的测试保持通过。

## 10. 本机环境变更

本机 `icoder_p1_app` 测试角色仅增加六张表的普通 DML 权限以及三个自增序列的 `USAGE/SELECT` 权限，以便用真实应用角色执行攻击矩阵。角色名和授权没有写入 Alembic，生产部署仍应由基础设施层按最小权限管理。

## 11. 风险与后续任务

1. 组织数增长后，启动恢复目前按组织串行扫描；应增加分页、并发上限和启动耗时指标，不能恢复为无租户全表查询。
2. CI 应固定创建独立的 owner/migration role 与 `NOSUPERUSER NOBYPASSRLS` app role，并把空库迁移、065→066、066→065→066 和六表攻击矩阵设为 PR 必跑门禁。
3. 下一波应按权威清单进入 Batch 2 Wave 3（Agent Connector / OAuth 相关租户表），开始前先确认其凭据引用、管理员委派和撤销语义。
4. PHI 加密本轮验证了 STT 数据列继续存储密文和哈希，但 KMS 接入、密钥轮换及历史密文重包仍是独立 P1 工作项，不能因 066 完成而视为关闭。

## 12. 完成判定

Batch 2 Wave 2 的代码、迁移、所有权约束、运行时绑定、攻击测试、升降级演练、空库重建和权威清单均已完成验证。revision 066 可作为下一候选开发基线；合并或发布时仍应由 CI 在独立 PostgreSQL 环境重跑上述发布闸门。
