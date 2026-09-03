# P1 Batch 2 Wave 5、审计完整性与数据库角色工程化报告

日期：2026-09-01  
分支：`codex/p1-security-multitenant-gates`  
代码/测试候选哈希：`63c62745`  
数据库权威：PostgreSQL 18.6  
最终 revision：`070`

## 1. 审查结论

本轮完成三个相互关联、但已按可审查主题拆分的增量：

1. revision `069` 将 CDI、Encounter、Document、Coding Review、Clinical
   Evidence/Facts、Guided Document/Section 和 Agent Feedback 共 17 张临床 PHI
   表纳入数据库级租户隔离。
2. revision `070` 增加逐租户/系统独立的审计签名链和 PostgreSQL 内不可变归档。
3. 将 migration/app PostgreSQL 角色的创建、收紧、对象所有权、授权、默认权限和
   漂移验证工程化，并加入 CI。

本机权威库 `icoder_p1_gate` 最终位于 `070`，生产启动数据库闸门通过。数据库中
FORCE RLS 表由 34 张增加到 52 张；其中 Wave 5 新增保护 17 张，070 另增加一张
不可变审计归档表。

本轮实现满足“Wave 5 数据库租户边界候选门禁”，但不代表整个 P1 发布闸门完成。
真实云 KMS 非导出密钥、跨账户 Object Lock、全部临床自由文本列的静态加密，以及
备份恢复/升级回滚演练仍是后续发布阻断项。

## 2. Revision 069 权威范围

| 表 | 最终租户契约 | 关键数据库控制 |
|---|---|---|
| `agent_task_feedback` | 必填直接租户 | FORCE RLS；复合 FK 到 Context |
| `cdi_cases` | 必填直接租户 | FORCE RLS；CDI 租户根 |
| `cdi_documentation_gaps` | 新增必填租户 | 从 Case 确定性回填；复合 Case FK |
| `cdi_provider_queries` | 新增必填租户 | 复合 Case/Gap FK，强制同 Case、同租户 |
| `cdi_clinician_responses` | 新增必填租户 | 复合 Case/Query FK |
| `cdi_document_versions` | 新增必填租户 | 复合 Case/可选 Query FK |
| `cdi_notification_subscriptions` | 必填直接租户 | FORCE RLS |
| `encounters` | 必填直接租户 | FORCE RLS；临床 Encounter 根 |
| `documents` | 必填直接租户 | 复合 Encounter FK |
| `coding_reviews` | nullable 收紧为必填 | 从 Encounter 回填；复合 Encounter FK |
| `clinical_evidences` | nullable 收紧为必填 | 从 Review 回填；复合 Review/Document FK |
| `code_candidates` | nullable 收紧为必填 | 从 Review 回填；复合 Review FK |
| `coding_review_runs` | nullable 收紧为必填 | 仅允许唯一 Trace→Run History 证据回填 |
| `clinical_facts` | 必填直接租户 | 组织 ID 收敛到 12 字符并增加 Organization FK |
| `guided_documents` | 必填直接租户 | 同上；内容列已使用加密封装 |
| `guided_sections` | 必填直接租户 | 独立租户 Section library；不伪造 Document 关系 |
| `feedback_training_authorizations` | 必填直接租户 | 复合 Context/Feedback FK |

`guided_sections` 当前模型没有 `document_id`，因此原清单中“通过 guided_documents
解析租户”的描述不成立。069 将它按现有事实治理为独立租户资源；若产品未来要求
Section 必须属于 Document，应先建立明确产品关系，再增加对应数据库约束。

## 3. 迁移前数据审计与回填原则

本机 17 张目标表在迁移前均为 0 行，因此本机升级不存在历史歧义，但也不能据此推断
生产数据正确。069 将存量检查写入迁移并失败关闭：

- CDI 四张间接子表只从 `cdi_cases.organization_id` 回填。
- `coding_reviews` 只从 Encounter 回填。
- Evidence/Candidate 只从 Coding Review 回填。
- `coding_review_runs` 只在 `trace_id` 唯一对应一个 Run History 租户时回填。
- 已有租户与父级租户冲突、孤儿关系、NULL 残留、Evidence 的 Review/Document 不同
  Encounter、Feedback 的 Context/Task 不一致，都会中止迁移。
- `clinical_facts`、`guided_documents`、`guided_sections` 中超过组织主键长度或无法关联
  Organization 的值会中止迁移。

迁移不会创建 `unknown` 组织，不会使用用户默认组织猜测归属，不会删除异常历史行，
也不会为了通过 NOT NULL 而填入占位值。

## 4. 运行时租户边界修复

### 4.1 CDI persistence

- Case、Gap、Query 的持久化现在强制接收组织 ID。
- Gap/Query 新行直接保存组织 ID。
- Case、Gap、Query 的读取和 Query lifecycle 更新均显式过滤组织 ID。
- 移除了 FORCE RLS 下不可可靠执行、且可能形成跨租户存在性侧信道的全局 Case ID
  预探测。

### 4.2 Usage 和 Runtime State Sync

- Usage Summary 现在显式依赖当前 Organization，并对 Audit、Run History、Coding
  Review 平均耗时均增加组织条件。
- Runtime State Sync 的 Review/Candidate 更新强制传入组织 ID，并同时过滤 Review
  和 Candidate。

### 4.3 Retention、Context scrub 和 Seed

- PostgreSQL Feedback retention 禁止无组织的全表清理；必须逐租户绑定并执行。
- Training Authorization 删除同时带组织条件。
- Context hard-delete 对 Feedback/Authorization 同时使用 Context 和 Organization。
- Demo Encounter seed 的幂等查询同时过滤 Organization。

### 4.4 已修复的静态加密缺口

`POST /api/encounters/text` 原先将粘贴病历原文直接写入 `documents.content`，与普通
Encounter 创建路径不一致。本轮已统一在写入前调用 PHI encryption，避免该 live path
成为明文旁路。

## 5. Revision 070 审计完整性归档

070 新增 `audit_integrity_archive`。每个租户以 Organization ID 为 stream，系统事件以
`system` 为独立 stream。每个归档记录包含：

- 规范化审计载荷和 SHA-256 `payload_hash`；
- `previous_hash`、`chain_hash` 和严格递增 sequence；
- 签名、签名算法和 `signing_key_id`；
- 源 Audit Log ID 和归档时间。

数据库使用事务级 advisory lock 串行化同一 stream 的追加，并验证源审计存在、租户
一致、链头/序号连续及摘要格式。`log_action()`、`system_audit()`、
`tenant_owned_system_audit()` 在 PostgreSQL 上将热审计与签名归档置于同一事务；任一
失败会回滚，避免静默出现“有审计、无完整性证明”。

归档启用 FORCE RLS：租户只能读取当前绑定组织的归档，不能直接插入。UPDATE/DELETE
由数据库触发器无条件拒绝，包括对象 owner。归档故意不对热审计建立删除级联外键，
因此热表按保留策略清理后完整性证明仍可保留。

离线验证器能检测载荷篡改、重排、缺失、previous hash 断裂、错误 key ID 和签名失败。
云启动现在会在接受流量前解析签名器；缺少审计签名密钥时失败关闭。

## 6. PostgreSQL 角色 Provisioning

新增工具要求部署显式传入 migration/app 角色名，不硬编码生产身份。它会：

1. 以 advisory lock 串行化 provisioning。
2. 创建或收紧两个 LOGIN 角色，禁止 SUPERUSER、BYPASSRLS、CREATEDB、CREATEROLE
   和 REPLICATION。
3. 将目标 schema、表、分区、序列、视图和函数归 migration 角色所有。
4. app 仅获得 schema USAGE、表 CRUD、序列 USAGE/SELECT 和函数 EXECUTE，无 schema
   CREATE。
5. 撤销 PUBLIC 的 schema/表/序列/函数权限。
6. 配置 migration 角色默认 ACL，使后续 Alembic 对象继承相同边界。
7. `verify` 输出无数据库 URL/密码的稳定 JSON 漂移报告，任一不合规项返回失败。

真实 PostgreSQL 18.6 集成测试使用临时非超级 CREATEROLE 管理身份，连续执行两次
provision，并验证新增 table、identity sequence、function 的 owner、默认 ACL、app
权限和 PUBLIC revoke。随机 schema、角色和临时身份全部清理，残留为 0。

## 7. 数据库演练记录

### 7.1 权威库升级与回滚

- `068 → 069`：通过。
- `069 → 068 → 069`：通过。
- `069 → 070`：通过。
- `070 → 068 → 070`：通过。
- 最终 `icoder_p1_gate` revision：`070 (head)`。
- 最终非特权 app role 生产启动校验：通过。

### 7.2 干净空库重建

创建精确临时库 `icoder_p1_wave5_0901a`，owner 为 migration 测试角色，从 base 全量
迁移至 `070`。迁移完成后：

- 生产启动数据库闸门通过。
- 完整 Wave 1–5 RLS 攻击矩阵与 070 审计不可变测试 10/10 通过。
- 临时库已删除，并再次查询确认残留计数为 0。

### 7.3 最终 schema 统计

| 指标 | 最终值 |
|---|---:|
| 数据库表 | 83 |
| ORM 表 | 83 |
| 清单 union | 84 |
| 含 organization_id 的数据库表 | 77 |
| organization_id NOT NULL | 63 |
| organization_id nullable | 14 |
| 无 organization_id 的数据库表 | 6 |
| ENABLE + FORCE RLS 表 | 52 |

## 8. 测试证据

- 临床 API、CDI、Facts、Guided Documents、Usage、Retention、Feedback 回归：
  `450 passed`。
- 069/070 迁移合同、CDI persistence、CodingReviewRun、审计链和 provisioning 单元测试：
  `53 passed`。
- 权威库和干净重建库上的 live PostgreSQL RLS/审计攻击矩阵：每轮 `10 passed`。
- Provisioning 真实 PostgreSQL 集成：`1 passed`。
- Python compileall：通过。
- `git diff --check`：通过。

攻击覆盖包括无租户读取、错误租户 INSERT、A/B 可见性、复合 FK 跨租户攻击、连接池
租户上下文清除、审计链断裂、Tenant/System 追加、归档 UPDATE/DELETE 拒绝，以及 app
角色危险属性和对象权限漂移。

## 9. 尚未关闭的发布风险

1. **真实 KMS 尚未接入**：当前有可替换 signer 接口和 HMAC-SHA256 实现，云模式强制
   注入密钥，但尚不是云 KMS 非导出密钥，也缺少完整旧 key verifier registry。
2. **外部 WORM 尚未完成**：数据库 trigger 是强不可变控制层，但不等同于跨账户对象
   存储 Object Lock、legal hold、外部时间戳或监管导出证明。
3. **PHI 静态加密仍有缺口**：`clinical_evidences.text`、Coding Review 报告/部分 JSON、
   `code_candidates.finding`、CDI evidence/query/response 自由文本，以及
   `coding_review_runs.encounter_text` 仍需统一 envelope encryption 和读取解密适配。
4. **同租户跨 Encounter Evidence 永久约束**：069 会在升级时失败关闭验证 Review 和
   Document 属于同 Encounter，但现有 Evidence schema 没有 `encounter_id`，暂时无法用
   FK 永久表达；后续需先做 schema 设计。
5. **生产存量对账**：本机 Wave 5 表为空。部署前必须在生产副本运行 069 preflight，
   对异常行建立可审计归属证据后再升级。
6. **备份恢复与监管导出**：仍需执行加密备份恢复、升级回滚、恢复后全链验证、保留/
   删除冲突和审计导出验签演练。

## 10. 提交拆分

- `eaf50cc1` — Wave 5 revision 069 与临床运行时租户/PHI 修复。
- `4b4a7576` — revision 070 审计签名链与不可变归档。
- `b5bed1e6` — PostgreSQL least-privilege role provisioning 与 CI 门禁。
- `63c62745` — Wave 5、审计链与 provisioning 测试证据。

## 11. 完成判定

Batch 2 Wave 5 的 17 张临床 PHI 表已经完成 PostgreSQL FORCE RLS、租户 NOT NULL、
确定性回填、父子复合所有权和主要运行时作用域加固，并在权威库及干净空库上通过攻击
验证。审计签名链、数据库内不可变归档和角色 provisioning 工程化也已形成可运行、
可验证的增量。

因此本轮可标记为 **Wave 5 数据库租户隔离候选门禁完成，审计完整性与角色工程化第一
阶段完成**。P1 整体仍不可标记为发布完成，下一阶段应优先关闭第 9 节列出的 PHI 静态
加密、真实 KMS/Object Lock 和备份恢复/监管导出阻断项。
