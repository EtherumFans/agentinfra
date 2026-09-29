# PostgreSQL 环境统一与部署验收

## 当前状态

UI 地址仍为 `http://127.0.0.1:13000`，后端仍为 `127.0.0.1:18000`。
该后端现在连接 PostgreSQL 17.11 的 `icoder_ui` 数据库（`127.0.0.1:15432`），运行账号为受限的 `delivery_app`。SQLite 不再接受当前 UI 后端的业务写入。

`icoder_delivery` 保留为独立自动化验收库；`icoder_ui_recovery` 是本次备份恢复验证库，均不与 UI 库自动同步。当前是本地部署验收，不代表已发布到外部生产环境。

## 数据迁移

停止后端写入后，通过 SQLite backup API 保存一致性备份 `unified-ui-source.db`。从已验证的 PostgreSQL 087 结构创建空审核库，执行 088 升级后，在一个事务内导入 22 张有数据的表，并逐表验证记录数量与完整业务内容摘要。迁移保留外键检查，没有禁用数据库约束。

包括 7 个账号、2 个组织、53 个智能体、3 个发布快照、5 个评测报告、21 条运行记录、4 个异步任务、18 个模板、22 个文档及原有 OAuth 客户端和 DeepSeek 配置。验收随后增加了明确命名的合成测试智能体、报告和运行记录。

临床字段和异步任务 payload/result 从 SQLite 本地明文表示转成已有 PHI 加密封装；采用加解密后的业务内容核对，不比较随机密文。保留原 `ICODER_SECRET_KEY`，组织 DeepSeek 密钥和登录签名不因数据库切换失效。运行服务同时配置 PHI 解密密钥。密钥仍从现有本地忽略文件读取，没有进入产品源码或报告。

新增 `scripts/release/migrate_sqlite_to_postgresql.py`：默认只做兼容性盘点，显式 `--apply` 才导入；拒绝非 PostgreSQL、错误版本、非空目标、缺少表或额外源字段；任一写入或内容校验失败，整个数据事务回滚。重复导入拒绝测试已通过。迁移目标连接由 `ICODER_MIGRATION_TARGET_URL` 注入。

## 本次发现并修复

- 早期 PostgreSQL 原生枚举标签与 ORM 的枚举名称不一致，影响模板、客户、工单以及新增用户角色。Alembic **088** 重命名相关标签，原有值在数据库中随枚举重命名保留；SQLite 无需修改。
- schema-only 恢复后，枚举类型未随表转移到迁移角色。角色配置工具现在显式转移枚举所有权，使迁移可由迁移账号完成。
- PostgreSQL 本地启动也执行数据库版本、受限角色、RLS 与加密预检，不再调用开发用 `create_all`。SQLite 开发启动流程保留。
- 两项旧测试直接查表时漏绑组织上下文，被 PostgreSQL RLS 正确拦截；已修复测试上下文，没有放宽产品权限。

## 验证结果

- 受限应用账号 PostgreSQL 回归：**42 项通过**。覆盖枚举契约、业务评测、复核、发布、固定版本、回滚、组织隔离、任务、运营、模型配置、用量和第三方 HTTP 流程。
- 独立合成智能体 `3b99381450eb`：真实 DeepSeek 文书套件 2/2 通过；未经复核发布返回 409；测试夹具复核后发布 1.0.0。复核意见明确标记仅用于自动化部署流程，不能作为实际业务或临床批准。上一阶段三份真实报告仍保留待复核状态。
- 独立第三方 HTTP 客户端：OAuth 获取令牌，成功调用发布版本；错误配置摘要返回 409。运行 `run-7cb2a84b-4d60-44fc-85e2-dfc0a3ded031` 已持久化并显示真实 `deepseek-v4-flash` 用量。
- 浏览器确认：现有会话可读发布版本、关联评测和门禁状态。重启后通过 UI 调试草稿成功，运行 `run-7dcd4991-f38d-4e8f-875e-4a81a22fdba8` 返回 200，真实 DeepSeek 用量完整。
- 重启后再次登录、读取发布版本和运营台，重启前后两条运行记录均可见。
- PostgreSQL 完整备份恢复：**90 张表、299 条记录**的完整行摘要一致；恢复库用受限应用账号执行预检通过。该备份是重启前的时间点快照，不包含后续 UI 调试新增记录。

## 启动与恢复

本地审核启动脚本：`artifacts/product-review-2026-09-07/start_postgresql_ui.py`。它绑定回环地址、使用应用账号、禁止自动种子写入，并沿用 DeepSeek 组织连接。不要再使用旧 `start_model_config_ui.py` 启动 SQLite 审核服务。

备份文件：`artifacts/product-review-2026-09-07/unified-ui-backup.dump`；已验证恢复到 `icoder_ui_recovery`。恢复时应使用新目标库，保留原库，使用相同的密钥材料，并先执行应用角色预检，再切换服务连接。数据库 dump 不包含外部密钥文件，需要分别安全备份。

SQLite 原库与一致性备份继续保留。切换后产生的新记录仅在 PostgreSQL 中，直接退回旧 SQLite 会丢失这些新记录在 UI 中的可见性，因此不能把回切当成无数据损失的恢复方案。

生产环境应通过 Alembic 升至 088，并采用生产账号、密钥管理、TLS、外部备份与监控配置；本次没有宣称完成这些外部生产基础设施工作。

证据目录：`artifacts/product-review-2026-09-07/`，主要文件为 `unify-inventory.json`、`unified-live.json`、`unified-restart.json`、`unified-ui-preflight.json`、`unified-recovery.json`、`unified-recovery-preflight.json`、`unified-tests-final.log`。`unify-transfer.json` 最后记录的是重复导入被拒绝的防覆盖测试。
