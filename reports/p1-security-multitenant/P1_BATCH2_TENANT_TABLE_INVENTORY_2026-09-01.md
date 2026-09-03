# P1 Batch 2 完整租户表清单与首批迁移决策

- 日期：2026-09-01
- 分支：`codex/p1-security-multitenant-gates`
- 数据库权威版本：Alembic revision `064`
- 机器可读清单：`backend/docs/security/tenant_table_inventory.json`
- 决策：Batch 2 首批迁移采用 **Context/A2A 闭环**，共 9 张表。
- 清单与验证提交：`241979f1` — `test(p1): govern the tenant table inventory`

## 1. 结论

实际 PostgreSQL schema 包含 82 张表；应用 ORM 同样声明 82 张表，但两者集合并不完全相同：

- `alembic_version` 只存在数据库，属于正常迁移元数据；
- `agent_accounts` 只存在 ORM，数据库 revision 064 中没有对应表，属于需要处理的 schema drift；
- 两侧并集为 83 张表，已经全部写入机器可读清单并逐表分类。

数据库现状：

| 指标 | 数量 |
|---|---:|
| PostgreSQL 实际表 | 82 |
| ORM 声明表 | 82 |
| 数据库与 ORM 并集 | 83 |
| 带 `organization_id` 的数据库表 | 67 |
| `organization_id NOT NULL` | 45 |
| `organization_id` 仍可为空 | 22 |
| 已 FORCE RLS | 7 |
| 实际属于租户但没有 `organization_id` | 9 |
| 平台/全局控制与 schema 表 | 6 |
| ORM-only drift | 1 |

目前的数据库级覆盖率不能用“67 张表已有组织字段”来代替：67 张直接租户表中只有 7 张已经 FORCE RLS，另外 60 张仍主要依赖应用层谓词；9 张间接租户表甚至没有可供 RLS 使用的组织字段。

## 2. 分类规则

清单使用以下范围类型：

- `tenant_direct`：每一行都直接属于一个组织。
- `tenant_legacy_nullable`：本质是租户数据，但保留了历史 NULL；必须回填、隔离或撤销。
- `tenant_indirect`：通过父表继承租户，目前缺少直接组织字段。
- `hybrid_catalog`：同时包含平台目录和租户覆盖项，不能把 NULL 简单回填为某个租户。
- `platform_control`：平台身份、安全、根组织或全局调度控制数据。
- `schema_metadata`：迁移元数据。

每张表记录：

- 租户解析路径；
- `organization_id` 状态；
- RLS 状态；
- 数据敏感度；
- 计划迁移波次；
- ORM/数据库存在状态。

## 3. 完整迁移波次

### 已完成 FORCE RLS：7 张

- `contexts`
- `conversation_memories`
- `memory_consents`
- `patient_contexts`
- `run_history`
- `run_trace_events`
- `transactions`

### Batch 2 Wave 1 — Context/A2A 闭环：9 张

- `context_messages`
- `context_task_refs`
- `context_artifact_refs`
- `original_input_audit`
- `a2a_task_executions`
- `a2a_task_events`
- `a2a_task_artifacts`
- `a2a_artifact_objects`
- `a2a_artifact_download_grants`

### Batch 2 Wave 2 — STT/Streams：6 张

- `stt_interactions`
- `stt_recordings`
- `stt_transcripts`
- `stt_stream_leases`
- `stt_stream_checkpoints`
- `stt_stream_checkpoint_chunks`

### Batch 2 Wave 3 — Connector：3 张

- `agent_connectors`
- `connector_credentials`
- `connector_execution_audit`

### Batch 2 Wave 4 — 身份、OAuth、成员关系和邀请：9 张

- `api_keys`
- `audit_logs`
- `oauth_clients`
- `oauth_tokens`
- `organization_members`
- `organization_invites`
- `organization_invite_deliveries`
- `team_members`
- `team_invites`

### Batch 2 Wave 5 — 临床/CDI/编码：17 张

- `agent_task_feedback`
- `feedback_training_authorizations`
- `encounters`
- `documents`
- `clinical_evidences`
- `clinical_facts`
- `coding_reviews`
- `coding_review_runs`
- `code_candidates`
- `guided_documents`
- `guided_sections`
- `cdi_cases`
- `cdi_documentation_gaps`
- `cdi_provider_queries`
- `cdi_clinician_responses`
- `cdi_document_versions`
- `cdi_notification_subscriptions`

### Batch 2 Wave 6 — Runtime、目录、业务配置：17 张

- `agents`
- `billing_run_settlements`
- `code_tables`
- `code_mappings`
- `customers`
- `experts`
- `gold_cases`
- `idempotency_records`
- `mcp_servers`
- `preview_sessions`
- `runtime_sessions`
- `runtime_transitions`
- `runtime_audit_records`
- `runtime_duc_decisions`
- `templates`
- `template_versions`
- `tickets`

### Batch 2 Wave 7 — Clinical Model Shadow 控制面：8 张

- `clinical_model_packages`
- `clinical_model_activations`
- `clinical_model_artifact_attestations`
- `clinical_model_shadow_bindings`
- `clinical_model_shadow_evaluations`
- `clinical_model_shadow_evaluation_jobs`
- `clinical_model_shadow_dead_letters`
- `clinical_model_shadow_alert_states`

### 平台/全局豁免：6 张

- `alembic_version`：迁移元数据。
- `organizations`：根租户注册表。
- `users`：平台身份；租户关系通过 `organization_members` 表达。
- `token_blacklist`：全局 token identifier 撤销表。
- `password_reset_tokens`：平台身份恢复服务数据。
- `clinical_model_shadow_scheduler_leases`：全局 Scheduler lease。

“豁免”不等于普通应用可以任意访问。这些表需要独立控制面权限、最小化查询和审计，但不能强行套用普通租户 RLS，否则会破坏登录、组织解析、迁移和调度发现。

### Schema 决策项：1 张

- `agent_accounts`：ORM 声明了机器身份和 credential reference，但数据库没有迁移。它通过 `agents` 间接归属租户或平台目录。进入数据库之前必须决定：
  1. 是否仍是产品需要的持久化能力；
  2. 若需要，增加 `organization_id`，并区分平台 Agent 与租户 Agent；
  3. 若不需要，删除 ORM 和所有死代码，不能继续保留自动 `create_all` 才会出现的影子表。

## 4. 为什么首批选择 Context/A2A

### 4.1 现有 FORCE RLS 边界存在子表缺口

`contexts` 已经 FORCE RLS，但它的以下子表没有 `organization_id`、没有 RLS：

- `context_messages`：包含会话 parts JSON，可能携带临床信息；
- `context_artifact_refs`：包含文件名、类型与 URL；
- `context_task_refs`：暴露任务 ID 和状态；
- `original_input_audit`：保存原始输入，属于最高敏感 PHI，而且当前连指向 `contexts` 的外键都没有。

因此，保护父表不能自动保护对子表的直接查询。应用层通过 context_id 校验只能降低风险，不能满足数据库级强制隔离。

### 4.2 A2A 与 Context 使用同一所有权链

A2A 执行、事件和 Artifact 均通过 `context_id` / `task_id` 与 Context 相连。一次迁移同时封闭这条链，能避免出现一半受 RLS、一半仍靠谓词的中间状态。

### 4.3 访问入口已经具备事务级绑定

上一轮已经为 A2A task runtime、streaming routes、artifact processing 和 context recovery 的直接会话增加租户事务绑定。因此可以先启用数据库策略，再通过攻击测试发现遗漏；不需要先赋予应用角色 BYPASSRLS。

## 5. 首批迁移设计

建议下一 revision：`065_context_a2a_tenant_rls`。

### 5.1 新增组织字段

向以下表增加临时可空的 `organization_id VARCHAR(12)`：

- `context_messages`
- `context_task_refs`
- `context_artifact_refs`
- `original_input_audit`
- `a2a_task_artifacts`

其余四张 A2A 表已经具有非空组织字段：

- `a2a_task_executions`
- `a2a_task_events`
- `a2a_artifact_objects`
- `a2a_artifact_download_grants`

### 5.2 回填来源

| 表 | 权威回填来源 |
|---|---|
| `context_messages` | `context_messages.context_id = contexts.id` |
| `context_task_refs` | `context_task_refs.context_id = contexts.id` |
| `context_artifact_refs` | `context_artifact_refs.context_id = contexts.id` |
| `original_input_audit` | `original_input_audit.context_id = contexts.id` |
| `a2a_task_artifacts` | `context_task_refs(context_id, task_id) -> contexts.organization_id` |

对已有组织字段的四张表执行一致性校验：

- execution/event 的 `organization_id` 必须等于其 context 的组织；
- artifact object 的组织必须等于 task artifact/context 的组织；
- download grant 的组织必须等于 artifact object 的组织。

任何找不到父记录或组织不一致的行必须进入隔离报告，迁移不得猜测归属。

### 5.3 约束强化

1. 回填完成后将五个新增字段改为 `NOT NULL`。
2. 为 `contexts` 增加 `(organization_id, id)` 唯一约束，供复合租户外键引用。
3. Context 子表使用 `(organization_id, context_id)` 复合外键。
4. `context_task_refs` 为 `(organization_id, context_id, task_id)` 提供唯一约束。
5. `a2a_task_artifacts` 的父外键扩展为包含 `organization_id`。
6. `a2a_artifact_objects` 的 Artifact 外键扩展为包含 `organization_id`。
7. `a2a_artifact_download_grants` 使用 `(organization_id, object_id)` 复合外键，阻止 grant 与 object 组织不一致。
8. `original_input_audit` 增加 Context 外键并保持受控级联/保留策略；删除行为需要与审计保留要求明确一致。

### 5.4 RLS 策略

九张表统一：

```sql
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <table> FORCE ROW LEVEL SECURITY;

CREATE POLICY icoder_tenant_isolation ON <table>
FOR ALL
USING (
  organization_id = current_setting(
    'icoder.current_organization_id', true
  )
)
WITH CHECK (
  organization_id = current_setting(
    'icoder.current_organization_id', true
  )
);
```

无租户上下文时必须读取 0 行，且 INSERT/UPDATE 失败。迁移角色用于结构与受控回填；应用角色不得是 superuser、不得有 BYPASSRLS。

### 5.5 ORM 与代码同步

- 五个间接表模型增加 `organization_id`。
- 所有创建这些行的服务从已验证 Context/Execution 对象取得组织，禁止从客户端 payload 复制。
- 所有复合 `db.get()` 主键和查询继续携带 context/task ID，但安全性由 RLS 和复合外键双重保障。
- Context retention/purge 先绑定单一组织，再删除该组织的 Context 链。
- `OriginalInputAuditRepository.purge_expired()` 不能继续全局无范围清理；应改成按组织迭代的受控维护入口。

## 6. 首批攻击测试

将现有 live PostgreSQL 测试扩展到九张表，每张表验证：

1. 无组织上下文 SELECT 为 0；
2. A 只能读取 A；
3. A 无法读取、更新、删除 B；
4. A 无法插入 `organization_id=B`；
5. A 无法通过跨组织 context/task/object 外键建立关系；
6. B 对称成立；
7. 同步池和异步池在 A → 空上下文 → B 复用时不泄漏；
8. 删除 Context 后的级联行为符合 Artifact 与审计保留政策；
9. 测试完成后无组织、Context、Task、Artifact、Grant 残留。

特别攻击用例：

- 使用 Org A 的 `context_id` 与 Org B 的 `task_id` 构造 Artifact；
- 使用 Org A 的 grant 指向 Org B 的 object；
- 直接以已知 `context_id` 查询 `context_messages`；
- 无组织上下文执行 `original_input_audit` retention purge；
- Worker 在系统发现任务后忘记开启租户处理事务。

## 7. 完成标准

Batch 2 Wave 1 只有满足以下条件才算完成：

- revision 065 可从空 PostgreSQL 数据库升级到 head；
- 现有 revision 064 测试数据可以迁移且生成零歧义报告；
- 五张补字段表全部 `organization_id NOT NULL`；
- 九张表全部 ENABLE RLS + FORCE RLS + 统一 policy；
- 复合外键阻止跨组织关系；
- 应用角色无 superuser/BYPASSRLS；
- 九表 A/B 攻击矩阵通过；
- A → 空 → B 同步/异步池复用通过；
- Context/A2A/Artifact/审计回归通过；
- 清单自动校验通过；
- 干净 checkout 可复现上述验证。

## 8. 清单治理

新增静态测试会检查：

- 清单名称唯一且按字母排序；
- 清单覆盖所有 ORM `__tablename__`；
- `alembic_version` 和 `agent_accounts` drift 被显式声明；
- 7 张已保护表与代码约束一致；
- 9 张首批表与批准范围一致；
- 每个租户/混合表都有租户解析、敏感度、RLS 状态和迁移波次。

后续新增 ORM 表时，如果没有同步更新清单，CI 应立即失败。

本轮验证结果：

- 清单静态完整性、集合、汇总和波次契约：`5 passed`；
- 清单与真实 PostgreSQL revision 064 表/字段/RLS 状态对照：`1 passed`；
- 真实数据库验证确认 82 张数据库表、67 张带组织字段、45 张组织字段非空、7 张 FORCE RLS，与清单完全一致。
