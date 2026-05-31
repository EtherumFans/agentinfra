# Runtime Persistence Model — 最终交付文档

**日期**: 2026-05-12
**范围**: Runtime 持久化、审计形式化、Alembic 迁移、状态同步、重启恢复

---

## 1. Runtime ER 图

```
┌──────────────────────────────────────────────────────────────┐
│                    runtime_sessions                          │
├──────────────────────────────────────────────────────────────┤
│ PK  id              VARCHAR(12)                              │
│ UK  runtime_id      VARCHAR(64)    ◄── 1:N ──────────────┐  │
│ IDX pipeline_id     VARCHAR(64)                           │  │
│ IDX review_id       VARCHAR(64)    (FK→coding_reviews)    │  │
│ IDX agent_id        VARCHAR(64)    (FK→agents)            │  │
│     current_state   VARCHAR(32)                           │  │
│     previous_state  VARCHAR(32)                           │  │
│     state_entered_at DATETIME                             │  │
│     timeout_at      DATETIME                              │  │
│     escalated       BOOLEAN                               │  │
│     failed          BOOLEAN                               │  │
│     archived        BOOLEAN                               │  │
│     execution_path  VARCHAR(32)                           │  │
│     content_hash    VARCHAR(32)  ← SHA-256 seal           │  │
│     created_at / updated_at                               │  │
└──────────────────────────────────────────────────────────────┘
         │                    │                    │
         │ 1:N                │ 1:N                │ 1:N
         ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│runtime_transitions│ │runtime_audit_    │ │runtime_duc_      │
│                  │ │records           │ │decisions         │
├──────────────────┤ ├──────────────────┤ ├──────────────────┤
│PK id             │ │PK id             │ │PK id             │
│FK runtime_id     │ │FK runtime_id     │ │FK runtime_id     │
│   from_state     │ │   event_type     │ │   action         │
│   to_state       │ │   action         │ │   reviewer       │
│   transition_type│ │   actor          │ │   decision       │
│   actor          │ │   current_state  │ │   reason         │
│   reason         │ │   guard_result   │ │   current_state  │
│   payload (JSON) │ │   post_check_res │ │   decision_hash  │
│   payload_hash   │ │   payload (JSON) │ │   created_at     │
│   created_at     │ │   immutable_hash │ │   updated_at     │
└──────────────────┘ │   created_at     │ └──────────────────┘
                     └──────────────────┘

All 3 child tables have FOREIGN KEY → runtime_sessions.runtime_id
All tables have immutable content hashing (SHA-256, prefix 16 chars)
```

## 2. Runtime ↔ Domain State Unified Mapping

| Runtime State | CodingReview.human_review_status | CodeCandidate.status | Trigger Sync? |
|--------------|----------------------------------|---------------------|---------------|
| INGESTED | pending | pending | |
| CONTEXT_READY | pending | pending | |
| FACTS_EXTRACTED | pending | pending | |
| CANDIDATES_READY | pending | pending | |
| RULES_VALIDATED | in_review | pending | |
| RISK_IDENTIFIED | in_review | needs_review | |
| **REVIEW_REQUIRED** | **pending_review** | **needs_review** | ✅ |
| **DECISION_CONFIRMED** | **confirmed** | **confirmed** | ✅ |
| DOC_FEEDBACK_READY | confirmed | confirmed | |
| WRITEBACK_PENDING | confirmed | confirmed | |
| WRITTEN_BACK | completed | confirmed | |
| **ARCHIVED** | **archived** | **supported** | ✅ |
| **FAILED** | **failed** | (unchanged) | ✅ |
| **ESCALATED** | **escalated** | **needs_review** | ✅ |

**Auto-sync 规则**（触发状态 transition 时自动执行）:
- REVIEW_REQUIRED → `review.human_review_status = "pending_review"`
- DECISION_CONFIRMED → `review.human_review_status = "confirmed"`
- ARCHIVED → `review.human_review_status = "archived"`
- FAILED → `review.human_review_status = "failed"`
- ESCALATED → `review.human_review_status = "escalated"`

## 3. Audit Persistence 结构

### 数据流
```
DeterministicRuntime
  │
  ├── transition() ──→ _enqueue_persist("state_transition", ...)
  ├── guard() ────────→ _enqueue_persist("audit", ...)
  ├── guard_post() ───→ _enqueue_persist("audit", ...)
  ├── human_confirm() → _enqueue_persist("duc_decision", ...)
  ├── force_transition→ _enqueue_persist("state_transition", ...)
  │
  └── flush_to_db(db) ──→ INSERT/UPDATE all queued events
                           └── RuntimeSession (upsert)
                           └── RuntimeTransition (insert)
                           └── RuntimeAuditRecord (insert)
                           └── DUCDecision (insert)
                           └── All sealed with SHA-256 hash
```

### 不可篡改保证
- 每条 record 在写入时计算 `content_hash` / `payload_hash` / `immutable_hash` / `decision_hash`
- `verify_integrity()` 方法可随时校验记录未被修改
- Hash 覆盖所有不可变字段（event_type、action、actor、guard_result、payload 等）
- 使用 SHA-256（前缀 16 字符），确定性生成（JSON keys sorted）

## 4. Migration 文件

| 文件 | 用途 |
|------|------|
| `alembic/env.py` | Alembic 环境配置（async SQLAlchemy + all models metadata） |
| `alembic/versions/001_runtime_persistence.py` | 创建 4 张表的 migration |

**Upgrade**: 创建 `runtime_sessions`, `runtime_transitions`, `runtime_audit_records`, `runtime_duc_decisions`
**Downgrade**: 逆序删除 4 张表

运行方式:
```bash
cd backend
alembic upgrade head    # 升级到最新
alembic downgrade -1    # 回退一个版本
```

## 5. Recovery 流程

```
App Startup (main.py lifespan)
  │
  ├── 1. await init_db()           # 创建/验证表结构
  │
  ├── 2. await _recover_runtime_sessions()
  │       │
  │       ├── SELECT * FROM runtime_sessions
  │       │   WHERE current_state NOT IN ('ARCHIVED', 'FAILED', 'ESCALATED')
  │       │
  │       ├── For each session:
  │       │   ├── Create DeterministicRuntime(case_id, pipeline_id, ...)
  │       │   ├── force_transition(target_state, reason="Recovered from DB")
  │       │   ├── Restore state_entered_at (for timeout continuity)
  │       │   ├── Restore escalated/failed/archived flags
  │       │   ├── rt.check_timeout() — check if timed out during downtime
  │       │   └── Register in runtime_registry
  │       │
  │       └── Log: "Runtime recovery: N active session(s) restored"
  │
  ├── 3. Start timeout checker (background, every 5 min)
  │
  └── 4. Ready for requests
```

**Stale scan**: 启动后立即扫描 `runtime_registry.stale_cases(max_age_hours=4)`
**Timeout 连续性**: `state_entered_at` 从 DB 恢复，确保 downtime 时间计入超时窗口

## 6. 修改文件列表

| 文件 | 类型 | 内容 |
|------|------|------|
| `app/models/runtime_persistence.py` | 新增 | 4 个 SQLAlchemy 模型 + SHA-256 hash 工具函数 |
| `app/models/__init__.py` | 修改 | 无（模型通过 import 自动注册 metadata） |
| `app/services/runtime.py` | 修改 | DeterministicRuntime 增加 `_enqueue_persist()` / `flush_to_db()` / persistence metadata；transition/guard/guard_post/human_confirm 增加 persistence enqueue |
| `app/services/runtime_state_sync.py` | 新增 | RuntimeStateSync 服务 + RUNTIME_TO_REVIEW_STATUS / RUNTIME_TO_CANDIDATE_STATUS 映射表 |
| `app/main.py` | 修改 | lifespan 增加 `_recover_runtime_sessions()` 调用 |
| `app/api/reviews.py` | 修改 | create_review / review_candidate / complete_review 增加 `flush_to_db()` |
| `app/services/agent_runner.py` | 修改 | run() / stream() 所有返回路径增加 `flush_to_db()` |
| `app/agents/orchestrator.py` | 修改 | Runtime 创建时传入 pipeline_id / execution_path / review_id |
| `alembic/env.py` | 新增 | Alembic 环境配置 |
| `alembic/versions/001_runtime_persistence.py` | 新增 | Migration 脚本 (upgrade/downgrade) |

## 7. 新增测试列表

| 文件 | 用例数 | 覆盖范围 |
|------|--------|----------|
| `test_runtime_persistence.py` | **35** | 持久化 flush (5)、审计不可篡改 (10)、状态同步 (11)、迁移结构 (5)、恢复流程 (4) |

**测试明细**:
- Flush writes RuntimeSession ✓
- Flush includes transitions ✓
- Flush includes audit records ✓
- Flush includes DUC decisions ✓
- Empty queue returns 0 ✓
- Content hash deterministic ✓
- Content hash different input ✓
- Session seal/verify ✓
- Session tamper detection ✓
- Transition seal/verify ✓
- Transition tamper detection ✓
- Audit record seal/verify ✓
- Audit record tamper detection ✓
- DUC decision seal/verify ✓
- DUC decision tamper detection ✓
- All states have review mapping ✓
- All states have candidate mapping ✓
- Trigger states include key 5 ✓
- Non-trigger states excluded ✓
- REVIEW_REQUIRED → pending_review ✓
- DECISION_CONFIRMED → confirmed ✓
- ARCHIVED → archived ✓
- FAILED → failed ✓
- ESCALATED → escalated ✓
- sync updates DB ✓
- sync ignores non-triggers ✓
- Migration columns correct (4 models) ✓
- All models have timestamps ✓
- Force transition audited ✓
- Pending persist collects ✓
- Queue clears after get ✓
- Flush then empty ✓

## 8. 全量测试结果

**140 passed, 2 pre-existing failures, 0 regressions**

## 9. 当前剩余技术债

| # | 项目 | 严重度 |
|---|------|--------|
| 1 | Runtime API 无前端消费者 | P1 |
| 2 | WebSocket STT 不可用 | P0 |
| 3 | CodingWorkbench 导出按钮死按钮 | P1 |
| 4 | 4/11 Expert 未在固定 pipeline | P1 |
| 5 | 前端单元测试 0 | P1 |
| 6 | CI/CD 不存在 | P1 |
| 7 | test_oauth / test_code_dictionary 预存在失败 | P2 |
| 8 | guard_post 在 stream 路径无法做完整结构化验证 | P2 |
| 9 | runtime_state_sync 仅在 flush 时同步（非实时） | P2 |
| 10 | Recovery 不恢复 in-memory AuditChain（仅恢复状态） | P3 |
