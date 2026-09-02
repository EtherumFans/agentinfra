# P1 Wave 5 Phase 2 — revision 071 PHI Envelope Encryption 与明文清除门禁审查报告

日期：2026-09-02  
分支：`codex/p1-security-multitenant-gates`  
上游基线：`469d2b994a74ba32aaaae37136f532d842377ea0`  
运行时实现：`20455509`  
迁移与回填：`91e93183`  
验证测试：`030d3629`

## 1. 执行结论

revision 071 已完成并在本机权威 PostgreSQL 上落到 `071 (head)`。本阶段将 Wave 5 临床 PHI 的数据库表示从明文 `text/json` 转为版本化 Fernet 密文 envelope，并在应用写入、数据库约束、升级前预检和生产启动四个层面同时 fail closed。

最终门禁覆盖 14 张临床数据表、71 个字段：30 个文本字段、41 个 JSON 字段。数据库中存在任一遗留明文时，071 会在改变列类型前拒绝升级；应用绕过 ORM 直接写入明文或伪造的短 `v1:` 前缀时，数据库 CHECK 约束会拒绝；PostgreSQL 应用进程缺少加密密钥时，PHI 写入与生产启动均会拒绝。

本阶段未把 KMS 宣称为已完成。当前 envelope 使用版本化应用密钥和 Fernet 完整性保护；KMS/HSM 托管、DEK wrapping、在线轮换和历史密钥退役仍是下一阶段工作。

## 2. 实现范围

| 表 | 受保护字段数 | 主要数据 |
|---|---:|---|
| `clinical_facts` | 2 | fact 文本、evidence JSON |
| `guided_documents` | 4 | string/structured document、labels、classic sections |
| `guided_sections` | 1 | section definition |
| `encounters` | 4 | admission/discharge、诊断/手术 JSON |
| `documents` | 1 | 原始文档内容 |
| `clinical_evidences` | 1 | 临床证据原文 |
| `code_candidates` | 4 | finding、evidence、rules、人工理由 |
| `coding_review_runs` | 14 | encounter 文本、诊断/手术/证据/风险/人工复核载荷 |
| `coding_reviews` | 18 | reasoning、analysis、报告、人工备注、错误信息 |
| `cdi_cases` | 7 | encounter snapshot、draft codes、summary、risk/trace |
| `cdi_documentation_gaps` | 5 | gap 描述、证据引用、候选编码 |
| `cdi_provider_queries` | 6 | query 文本、选项、证据引用和 spans |
| `cdi_clinician_responses` | 3 | 选择、自由文本、响应 metadata |
| `cdi_document_versions` | 1 | 文档差异摘要 |
| **合计** | **71** | **30 text + 41 JSON** |

结构化租户标识、脱敏 patient/encounter reference、状态、时间戳、分类枚举和用于检索的代码目录字段未纳入随机密文列；它们继续由 FORCE RLS、最小权限和审计链保护。随机 Fernet 密文不支持数据库等值检索，因此不能直接替换仍承担索引/关联职责的字段。

## 3. 安全设计

### 3.1 运行时透明加密

- 新增 `EncryptedPHIText` 与 `EncryptedPHIJSON` SQLAlchemy 类型。
- JSON 先按稳定、无 NaN 的 canonical JSON 序列化，再整体加密为一个不透明 text envelope；数据库不再暴露 JSON 内部键和值。
- PostgreSQL 写入必须配置 `ICODER_PHI_ENCRYPTION_KEY`，且结果必须符合完整 envelope 结构。
- PostgreSQL 读取遇到明文或畸形 envelope 会抛错，不再沿用历史明文兼容路径。
- SQLite 保留无密钥本地开发兼容，以免破坏现有单元测试和轻量本地工作流。
- 已由 repository 显式加密的 Clinical Facts 和 Guided Document/Section 不重复改写业务路径，但加入同一数据库约束合同。

### 3.2 数据库明文清除门禁

- revision：`071`，线性下游：`070`。
- Alembic 不读取、不接收、不打印 PHI 加密密钥。
- 升级前逐租户绑定 `icoder.current_organization_id`，在 FORCE RLS 下扫描全部目标列。
- 检测到遗留明文时抛出 `migration 071 refuses plaintext PHI`，并报告字段级计数，不输出行 ID 或数据内容。
- 41 个 JSON 列从 PostgreSQL `json` 转为 opaque `text`；原有 `{}`/`[]` server default 被删除，防止数据库自行生成明文 JSON。
- 71 个 CHECK 约束只接受 NULL、空值或结构完整的版本化 Fernet envelope。
- envelope 正则要求 `vN:gAAAAA...` 和最低 token 长度，短伪前缀不能绕过门禁。

### 3.3 生产启动门禁

生产数据库验证现在同时要求：

1. Alembic revision 必须等于 `071`；
2. 必须存在 71 个 `ck_phi_envelope_%` 约束；
3. PostgreSQL 运行时必须配置 PHI 加密密钥；
4. 既有非 superuser、无 BYPASSRLS、FORCE RLS、审计不可变归档和签名器门禁继续通过。

## 4. 受控回填工具

新增 `backend/scripts/backfill_phi_envelopes.py`，用于 070 → 071 前置处理：

- 默认 dry-run，只统计，不改数据；
- 只有显式 `--execute` 才写入；
- 要求 migration URL 和 PHI 密钥；
- 逐组织绑定 FORCE RLS 租户上下文；
- 输出只有组织数、字段计数和更新数，不输出数据库 URL、密钥、明文、行 ID；
- 可重复执行，已符合 envelope 格式的值会跳过；
- JSON 在 070 schema 下写成 JSON string，071 再安全转换为 opaque text。

标准顺序：

```text
1. 冻结写流量或进入维护窗口
2. 在 070 上执行 dry-run
3. 审核 plaintext_values 和字段清单
4. 使用受控密钥执行 --execute
5. 再次 dry-run，确认 plaintext_values = 0
6. 执行 alembic upgrade 071
7. 启动应用并执行生产数据库验证
```

## 5. 实际演练结果

### 5.1 遗留数据回填

在 070 schema 创建一次性 Clinical Fact 夹具，包含 2 个明文值：

| 操作 | plaintext_values | updated_values | 结果 |
|---|---:|---:|---|
| 默认 dry-run | 2 | 0 | 未修改数据 |
| `--execute` | 2 | 2 | 精确更新 2 个值 |
| 071 升级后原始 SQL 检查 | 0 | — | 两列均为 `v1:` 密文，不含 sentinel |

测试组织、Clinical Fact 行和临时密钥均在演练后清除。

### 5.2 明文升级阻断

在 070 插入明文后执行升级，071 按预期拒绝，错误包含字段级明文门禁信息。清除夹具后可正常升级到 071。

本演练发现并修复了一个重要问题：最初预检未绑定租户，migration owner 在 FORCE RLS 下看不到目标行，导致预检漏报而在建约束阶段才失败。最终实现改为逐组织绑定租户上下文，负向演练已证明会在结构修改前拒绝。

### 5.3 约束绕过测试

真实 PostgreSQL 已验证拒绝：

- 直接写入 `plaintext`；
- 写入 `v1:not-a-fernet-token` 伪 envelope；
- 无密钥的 ORM PostgreSQL PHI 写入；
- PostgreSQL 读取历史明文。

同时验证：持正确密钥的 ORM 可透明读回原值；migration role 原始 SQL 只看到密文；另一租户看不到该行。

### 5.4 升级、回滚与空库重建

- 权威测试库：`070 → 071 → 070 → 071` 成功，最终 `071 (head)`。
- 全新临时 PostgreSQL 数据库：从空库执行全部 Alembic 迁移到 071 成功。
- 空库最终状态：83 张 base tables、71 个 PHI CHECK constraints、revision 071。
- 临时重建数据库在验证后已删除。
- 071 downgrade 会移除 envelope 约束，并把 opaque JSON text 还原为 JSON string 表示；它不会解密数据。对有数据环境的回退是 schema/二进制回退演练，不等于恢复旧版应用对 JSON 内容的语义兼容。生产回退需要保持新读路径或另行执行受控解密回退，不得直接让旧应用读取密文 JSON string。

## 6. 验证矩阵

| 验证组 | 结果 |
|---|---|
| revision 071 契约、字段清单漂移、TypeDecorator 单元测试 | 通过 |
| Coding Review、CDI persistence/API、Guided Document、JWT tenant 回归 | 76 passed |
| PHI 真实 PostgreSQL envelope/RLS/绕过攻击 | 通过 |
| P1 RLS、角色 provisioning、审计 archive 组合回归 | 最终 17 passed, 1 environment-dependent test skipped；异步池测试以规定的 asyncpg URL 单独复跑通过 |
| Python compileall | 通过 |
| `git diff --check` | 通过 |
| 生产数据库启动验证 | 通过 |
| 070 遗留明文回填 | 通过 |
| 071 明文升级拒绝 | 通过 |
| 空库 000 → 071 重建 | 通过 |
| 071 → 070 → 071 回滚复升 | 通过 |

一次组合测试最初把同步 psycopg URL 传给 Windows 异步池，触发 ProactorEventLoop 驱动不兼容；改用项目规定的 `postgresql+asyncpg` URL 后通过。该失败是测试环境参数错误，不是产品回归。

## 7. 审查中发现并关闭的问题

1. **FORCE RLS 导致预检盲区（已关闭）**：改为逐租户绑定后扫描。
2. **SQLAlchemy 将正则中的冒号解析为 bind marker（已关闭）**：CHECK DDL 改用 driver-level SQL；实库确认 71 个约束定义中不存在被替换的 `NULL` 片段。
3. **仅检查 `vN:` 前缀可伪造（已关闭）**：运行时和数据库都收紧为 Fernet 结构与最小长度验证。
4. **既有显式加密字段缺少 DB 约束（已关闭）**：Clinical Facts、Guided Documents、Guided Sections 共 7 列加入 071，总数由 64 增至 71。
5. **回填脚本直接执行时导入路径错误（已关闭）**：脚本现在可从仓库根目录或 backend 目录直接运行。

## 8. 未关闭风险与后续任务

### P1 下一优先级

1. 接入 KMS/HSM：用 KEK 包装数据密钥，禁止长期主密钥直接驻留普通环境变量。
2. 实现并演练 v1 → v2 在线密钥轮换：双读单写、批量重加密、历史 key retirement、失败续跑和指标告警。
3. 建立 PHI 列注册表为单一事实源，由其生成 ORM/迁移/回填/启动校验清单，减少三份清单漂移风险。
4. 将真实 PostgreSQL PHI 门禁加入 PR CI 和发布前 CI，使用 disposable database 与临时密钥。
5. 增加备份介质验证：确认逻辑备份、物理快照、WAL 和导出文件中不出现 sentinel 明文。
6. 对 Patient、Trace、Usage、Context、Memory 继续执行同类“应用加密 + DB 约束 + 原始备份扫描”覆盖审查。
7. 为 populated JSON downgrade 设计明确的兼容回退方案；在方案完成前，将数据库回退标记为仅限 schema rehearsal。

### 发布判定

revision 071 可以作为 Wave 5 Phase 2 候选基线，但尚不能把整个 P1 安全发布闸门标记为完成。KMS、完整密钥轮换、备份恢复/升级回滚演练和跨域 PHI 静态扫描仍是发布阻断项。

## 9. 工作树与可追溯性

实现按三个可审查主题提交：运行时加密模型、数据库迁移/回填、测试。报告作为独立提交。测试数据库中的临时组织、PHI 夹具和空库重建数据库均已删除；未把测试密钥、连接密码、数据库 URL 或 PHI sentinel 写入报告和 Git。
