# iCoDer SQLite 迁移对账阶段总结（2026-08-22）

## 阶段结论

本阶段完成了开发 SQLite 的**只读审计和独立候选重建**。当前源库没有被迁移、替换、重启或写入；源库仍是 Alembic `041`。在独立副本上重建出的候选达到单 head `049`，并通过完整性、外键、源数据指纹和 ORM 结构漂移门禁。

这不是数据库切换完成声明。候选中的六个停用隔离租户只用于收容历史孤儿外键，不构成真实医院、租户或数据所有权判断。

## 发现与修复

- 源库 `PRAGMA integrity_check=ok`，但有 827 条外键违规，全部指向六个缺失的 `organizations` 父标识。
- 源库 revision 为 `041`，而部分 042 之后的表已由历史 `create_all` 行为创建；直接执行 `alembic upgrade head` 会发生表冲突。
- 新增 `backend/scripts/stage_sqlite_migration.py`：默认只读、拒绝覆盖、SQLite backup 快照、从空库迁移到 head、按共同列复制、逐表 PHI-safe 指纹、显式停用隔离、源库二次哈希验证、无自动 cutover。
- 新建 Alembic head 时发现 `memory_consents.retention_days` 的迁移默认值为 30、ORM 缺少对应 `server_default`。现已按 API/迁移既有契约统一为 30； fresh-head 漂移恢复为 0。
- 旧恢复手册中“直接重建/删除数据、固定 33 表、生产使用 create_all”等陈旧指引已被安全的只读影子流程替换。
- 静态部署预检新增 SQLite 对账门禁，当前为 57/57。

## 真实开发库副本验证

| 项目 | 结果 |
|---|---:|
| 源 revision | `041` |
| 候选 revision | `049` |
| 源 SHA-256 前后 | 完全一致 |
| 源表复制 | 58 表、6,090 行 |
| 数据指纹不一致 | 0 |
| 候选完整性 | `ok` |
| 候选外键违规 | 0 |
| 停用隔离父租户 | 6 |
| ORM 漂移 | 0（65 表、948 列） |
| 自动切换 | `false` |

为防止开发数据副本进入报告目录，验证结束后已删除本轮生成的 source snapshot、候选 DB 及 WAL/SHM 文件；只保留不含行值的机器报告。删除的均为本轮可重建副本，源库未删除或变更。

## 测试证据

- fresh Alembic schema drift + staged reconciliation：4/4。
- schema drift、staged reconciliation、部署预检、Memory Connector 联合回归：23/23。
- 静态部署候选预检：57/57。
- 迁移机器报告：`reports/agent_hub/sqlite_reconciliation_phase_20260822/staged/sqlite_migration_stage_report.json`。
- 阶段证据：`reports/agent_hub/sqlite_reconciliation_phase_20260822/phase_evidence.json`。

## 尚未关闭的门禁

- 源库仍为 `041`，没有切换到候选，也没有重启后端。
- 六个隔离租户的真实归属必须由授权数据所有者复核；尤其空标识历史行不能自动归属。
- 最终切换需要明确维护窗口、双人/授权审批、源/候选哈希确认、可恢复备份和回滚演练。
- SQLite 候选验证不能替代 PostgreSQL 多副本迁移、医院环境验证或云变更审批。
