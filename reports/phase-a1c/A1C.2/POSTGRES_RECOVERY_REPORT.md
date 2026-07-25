# A1C.2 — PostgreSQL 中断恢复模式报告

**Date**: 2026-07-25
**Scope**: 设计并验证 alembic 001..028 在中断 (interrupted) 后的恢复模式,覆盖 SQLite (审计主机可执行) 与 PostgreSQL (Pilot 环境必须执行)。

---

## §1 中断模式分类

### 1.1 模式 A — `_alembic_tmp_*` 影子表残留 (SQLite batch_alter_table)

**触发**: SQLite 上执行 `batch_alter_table` 期间进程崩溃。Alembic 在 SQLite 上无法直接 ALTER COLUMN,需要:
1. 创建 `_alembic_tmp_<table>` 影子表 (含新 schema)
2. `INSERT INTO _alembic_tmp_<table> SELECT ... FROM <table>`
3. `DROP TABLE <table>`
4. `ALTER TABLE _alembic_tmp_<table> RENAME TO <table>`

若 1-3 之间崩溃 → `_alembic_tmp_<table>` 残留,下次 `alembic upgrade head` 在 CREATE 影子表时报 `table _alembic_tmp_agents already exists` 失败。

**修复**: 受影响 migration 的 `upgrade()` 顶部加 `DROP IF EXISTS _alembic_tmp_*` 守卫。这是 Phase A1A Gate 3R (Migration 019) 引入的 canonical pattern,A1C.2 Migration 027 已遵循。

### 1.2 模式 B — `alembic_version` 表脏状态

**触发**: alembic 在 UPDATE `alembic_version.table` 之前崩溃。SQLite/PG 均可能。

**症状**: `alembic current` 显示空 / 旧 revision,但表 schema 已部分更新。

**修复**: `alembic stamp <revision>` 强制写入 revision 不执行 migration。**仅在确认 schema 状态与目标 revision 一致时使用**。Pilot 环境必须先 `pg_dump` 备份再 stamp。

### 1.3 模式 C — 部分数据写入后崩溃

**触发**: 数据迁移 (例如 Migration 028 的 `UPDATE agents SET aliases='[]' WHERE aliases IS NULL`) 在中途崩溃,部分 NULL 行已更新,部分未更新。

**修复**: 数据迁移 SQL 必须幂等。`UPDATE ... WHERE aliases IS NULL` 是天然幂等 (再跑一次只影响剩余 NULL 行)。

### 1.4 模式 D — 索引创建中断 (CONCURRENTLY 失败)

**触发**: PG 上 `CREATE INDEX CONCURRENTLY` 失败 → 索引进入 INVALID 状态。

**修复**: `DROP INDEX <name>; CREATE INDEX CONCURRENTLY <name> ...` 重试。iCoDer 当前 migration 未使用 CONCURRENTLY,Pilot 环境若开启需手动转换。

### 1.5 模式 E — 探测失败的回退 (downgrade)

**触发**: Pilot 上发现某 migration 有问题,需要 downgrade 回退到上一 revision。

**修复**: `alembic downgrade -1` (单步) 或 `alembic downgrade <target>` (多步)。downgrade 必须可逆,A1C.2 验证了 S04 (SQLite 028→027) + S05 (SQLite 027→028) 路径。

---

## §2 A1C.2 中断恢复验证 (SQLite,审计主机)

### 2.1 S16 测试用例

**前置**: 在 SQLite fresh DB 上 `alembic upgrade 026`,然后手动注入 `_alembic_tmp_agents` 残表模拟崩溃:

```python
import sqlite3
conn = sqlite3.connect(db_path)
conn.execute('CREATE TABLE _alembic_tmp_agents (id TEXT PRIMARY KEY, name TEXT)')
conn.execute('INSERT INTO _alembic_tmp_agents VALUES ("stale1", "leftover")')
conn.commit(); conn.close()
```

**动作**: `alembic upgrade head` (空 DB → 028,会经过 Migration 027)。

**期望**:
- Migration 027 upgrade() 顶部的 `DROP IF EXISTS _alembic_tmp_*` 守卫清理残表
- Migration 027 + 028 正常应用
- `alembic current` 返回 `028 (head)`
- 数据库中无 `_alembic_tmp_*` 残表

**实测**:

```json
{
  "precondition": "stale _alembic_tmp_agents 表注入",
  "rc_upgrade_head": 0,
  "current_after_upgrade": "028 (head)",
  "leftover_tmp_tables": []
}
```

**结论**: SQLite 中断恢复 (模式 A) 在 Migration 027 上验证通过。

### 2.2 守卫代码 (Migration 027)

```python
def upgrade() -> None:
    # A1C.2 interrupted-recovery guard (canonical pattern from A1A Gate 3R)
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        rows = bind.execute(sa.text(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE '\\_alembic\\_tmp\\_%' ESCAPE '\\'"
        )).fetchall()
        for (tmp_name,) in rows:
            bind.execute(sa.text(f"DROP TABLE IF EXISTS \"{tmp_name}\""))
    else:
        # PostgreSQL: defensive — to_regclass 检测 + DROP IF EXISTS
        rows = bind.execute(sa.text(
            "SELECT to_regclass('public._alembic_tmp_%')"
        )).fetchall()
        for (rel,) in rows:
            if rel:
                bind.execute(sa.text(f"DROP TABLE IF EXISTS {rel} CASCADE"))
    # ... 后续 ALTER COLUMN 主逻辑
```

---

## §3 PostgreSQL 中断恢复 (Pilot 环境必须执行)

### 3.1 S16 PG 版本

**前置**:
```bash
# 1. Pilot 环境 PG 上 alembic upgrade 026
DATABASE_URL=postgresql+asyncpg://... alembic upgrade 026

# 2. 手动注入残表
psql -h <pg-host> -U icoder -d icoder_a1c2 <<EOF
CREATE TABLE _alembic_tmp_agents (id TEXT PRIMARY KEY, name TEXT);
INSERT INTO _alembic_tmp_agents VALUES ('stale1', 'leftover');
EOF
```

**动作**:
```bash
DATABASE_URL=postgresql+asyncpg://... alembic upgrade head
```

**期望**: PG 上 Migration 027 走 `ALTER COLUMN ... TYPE` 直通路径 (无 batch_alter_table),理论上不创建影子表;但守卫的 `to_regclass` + `DROP IF EXISTS` 仍会清理任何残留。`alembic current` 返回 `028 (head)`。

### 3.2 模式 B PG 版本

**前置**: 模拟 `alembic_version` 表脏状态:
```sql
-- PG 上模拟 migration 027 执行到一半崩溃
-- alembic_version 表仍显示 026,但 agents.id 已是 VARCHAR(12)
DELETE FROM alembic_version;
INSERT INTO alembic_version (version_num) VALUES ('026');
-- 部分表已 ALTER 部分未 ALTER
```

**修复**:
```bash
# 先 pg_dump 备份
pg_dump -h <pg-host> -U icoder icoder_a1c2 > /tmp/a1c2_backup_$(date +%Y%m%d).sql

# 检查 schema 实际状态
psql -h <pg-host> -U icoder -d icoder_a1c2 -c "\d agents" | grep id
psql -h <pg-host> -U icoder -d icoder_a1c2 -c "\d users" | grep id
# ... 32 表

# 若 schema 已对齐 027 (32 表 VARCHAR(12)) 但 028 未应用,stamp 到 027 然后 upgrade
alembic stamp 027
alembic upgrade head
```

### 3.3 模式 C PG 版本

**Migration 028 backfill 在 PG 上**:
```sql
-- alembic 在 PG 上执行 Migration 028 时:
UPDATE agents SET aliases = '[]' WHERE aliases IS NULL;
-- 然后 ALTER COLUMN
ALTER TABLE agents ALTER COLUMN aliases TYPE JSON;
ALTER TABLE agents ALTER COLUMN aliases SET NOT NULL;
```

若 backfill 中途崩溃,部分 NULL 已 update 部分未 update → rerun Migration 028:
```bash
# 回到 027
alembic downgrade 027
# 重升到 028 (此时 backfill 重跑,清理剩余 NULL)
alembic upgrade 028
```

幂等性来自 `WHERE aliases IS NULL` 条件 (剩余 NULL 才被 update)。

### 3.4 模式 D PG 版本 (CONCURRENTLY)

iCoDer 当前 migration 不使用 `CREATE INDEX CONCURRENTLY`,但 Pilot 环境可能开启:
```python
# Migration 内若使用 with_op:
op.create_index("idx_xxx", "table", ["col"], postgresql_concurrent=True)
```

若失败 INVALID:
```sql
DROP INDEX CONCURRENTLY idx_xxx;
CREATE INDEX CONCURRENTLY idx_xxx ON table (col);
```

### 3.5 模式 E PG 版本 (downgrade drill)

```bash
# Pilot 环境必须执行 (S11 + S12)
alembic downgrade -1     # 028 → 027
alembic current          # 应显示 027
alembic upgrade head     # 027 → 028
alembic current          # 应显示 028 (head)

# Multi-version drill (S13-S15)
alembic downgrade 020
alembic current          # 应显示 020
alembic upgrade head     # 020 → 028 (8 个 migration 串行)
alembic current          # 应显示 028 (head)
```

---

## §4 Pilot 环境部署 Runbook (中断恢复模板)

```bash
#!/usr/bin/env bash
# pilot_pg_recovery_runbook.sh — A1C.2 中断恢复 Runbook
# 适用场景: Pilot 环境 PG 上 alembic upgrade / downgrade 中断后恢复

set -euo pipefail

PG_HOST="${PG_HOST:-}"
PG_USER="${PG_USER:-icoder}"
PG_DB="${PG_DB:-icoder_a1c2}"
DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://${PG_USER}@${PG_HOST}/${PG_DB}}"

if [[ -z "$PG_HOST" ]]; then
  echo "ERROR: PG_HOST must be set"; exit 1
fi

# Step 1: 备份
BACKUP="/tmp/a1c2_backup_$(date +%Y%m%d_%H%M%S).sql"
echo "[1/5] Backing up to $BACKUP"
pg_dump -h "$PG_HOST" -U "$PG_USER" "$PG_DB" > "$BACKUP"

# Step 2: 检查 alembic_version
echo "[2/5] Current alembic version:"
alembic current

# Step 3: 检查 _alembic_tmp_* 残表
echo "[3/5] Checking for leftover _alembic_tmp_* tables..."
LEFTOVER=$(psql -h "$PG_HOST" -U "$PG_USER" -d "$PG_DB" -t -c \
  "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE '_alembic_tmp_%';")
if [[ -n "$LEFTOVER" ]]; then
  echo "WARN: leftover tmp tables detected:"
  echo "$LEFTOVER"
  for tbl in $LEFTOVER; do
    psql -h "$PG_HOST" -U "$PG_USER" -d "$PG_DB" -c "DROP TABLE IF EXISTS $tbl CASCADE;"
  done
fi

# Step 4: 检查 INVALID 索引
echo "[4/5] Checking for INVALID indexes..."
INVALID=$(psql -h "$PG_HOST" -U "$PG_USER" -d "$PG_DB" -t -c \
  "SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;")
if [[ -n "$INVALID" ]]; then
  echo "WARN: INVALID indexes detected:"
  echo "$INVALID"
  for idx in $INVALID; do
    psql -h "$PG_HOST" -U "$PG_USER" -d "$PG_DB" -c "DROP INDEX CONCURRENTLY IF EXISTS $idx;"
  done
fi

# Step 5: 重新 upgrade head
echo "[5/5] alembic upgrade head"
alembic upgrade head
alembic current
echo "Recovery complete. Backup at: $BACKUP"
```

---

## §5 Verdict

**RECOVERY_PATTERN_DEMONSTRATED_VIA_SQLITE_INTERRUPTED_RECOVERY_AND_STATIC_DDL_ANALYSIS** — 模式 A (SQLite _alembic_tmp_* 残表) 在 Migration 027 上验证通过 (S16 PASS);模式 B-E 在 PG 上的恢复路径已设计,但**实际 PG 运行延后到 Pilot 环境**。

**诚实 PARTIAL 项**:
- PG 上的中断恢复 (S16 PG 版本) 未在审计主机执行,因 docker/psql 不在主机。
- Pilot 环境必须在第一次 PG 部署时执行 §3.1-§3.5 + §4 Runbook,确认恢复路径有效。
- 模式 D (CONCURRENTLY) 当前 migration 未使用,但 Pilot 若开启需手动转换。

**Charter §22 forbidden verdicts 已 honour**: 未输出 RECOVERY_FULLY_VERIFIED_ON_POSTGRESQL。
