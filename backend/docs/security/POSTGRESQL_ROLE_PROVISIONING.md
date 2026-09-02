# PostgreSQL 生产角色 Provisioning

## 安全边界

生产数据库使用三个彼此独立的身份：

- provisioning 身份：由云数据库或 DBA 管理，仅在部署准备阶段使用；必须具备
  `CREATEROLE`，并能接管目标 schema 内已有对象。
- migration 身份：Alembic 专用，拥有目标 schema 和其中的表、序列及函数。
- app 身份：API 和后台任务专用，只拥有运行所需的数据访问与函数执行权限。

工具会显式将 migration 和 app 角色设置为 `NOSUPERUSER NOBYPASSRLS
NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT LOGIN`。应用角色不能在目标
schema 中创建对象，因此不能通过自建函数或对象覆盖迁移边界。

云托管数据库常提供 `CREATEROLE` 但非 superuser 的管理身份。该身份可以创建安全
角色，却不能修改 `SUPERUSER/BYPASSRLS/REPLICATION` 属性；工具发现既有目标角色带有
任何禁止属性时会硬失败，要求 DBA 先修复，不会以部分成功掩盖特权漂移。

角色名没有产品默认值。部署系统必须显式注入名称，避免把测试名称或某一家云厂商的
身份约定固化到产品中。密码也只从环境变量读取，不接受命令行参数，避免出现在进程
列表和任务日志中；采用 IAM、证书或外部密码管理时可以不设置密码变量。

## 首次建立或修复权限

从 `backend` 目录运行：

```text
ICODER_POSTGRES_ADMIN_URL=<管理员 PostgreSQL URL>
ICODER_POSTGRES_MIGRATION_ROLE=<迁移角色名>
ICODER_POSTGRES_APP_ROLE=<应用角色名>
ICODER_POSTGRES_MIGRATION_PASSWORD=<可选，由 Secret Manager 注入>
ICODER_POSTGRES_APP_PASSWORD=<可选，由 Secret Manager 注入>
python scripts/provision_postgresql_roles.py provision
```

SQLAlchemy 风格的 `postgresql+asyncpg://`、`postgresql+psycopg://` URL 均可使用。
默认目标 schema 为 `public`；非 public 部署需设置 `ICODER_POSTGRES_SCHEMA`。

`provision` 可重复运行。它会：

1. 使用事务级 advisory lock 防止并发部署互相覆盖。
2. 创建或收紧两个登录角色的安全属性。
3. 将 schema、已有表、分区表、序列、视图和函数归 migration 角色所有。
4. 授予 app 角色 schema `USAGE`，表 `SELECT/INSERT/UPDATE/DELETE`，序列
   `USAGE/SELECT`，函数 `EXECUTE`。
5. 撤销 PUBLIC 对 schema、既有表、序列和函数的权限；函数默认执行权在 migration 角色
   全局撤销，因为 PostgreSQL 的 schema 级默认权限不能覆盖全局默认授予。
6. 配置 migration 角色的默认权限，使后续 Alembic 新建的表、序列和函数自动获得
   相同边界。

对象归属接管是有意操作。首次接入现有数据库前应在预生产环境运行 `verify` 并由 DBA
确认目标 schema；不得将工具指向包含其他应用对象的共享 schema。

## 部署顺序

1. provisioning 身份运行 `provision`。
2. 使用 migration 角色的同步 URL 运行 `python -m alembic upgrade head`。
3. provisioning 身份再次运行 `provision`，补齐本次迁移中新对象的现有权限；默认
   权限同时保证此步骤具备幂等性。
4. provisioning 身份运行 `verify`。
5. API 只接收 app 角色的 `postgresql+asyncpg://` URL，然后执行生产启动校验。

建议把第 3、4 步合并为发布门禁：

```text
python scripts/provision_postgresql_roles.py provision --json-output <受控报告路径>
python scripts/provision_postgresql_roles.py verify --json-output <受控报告路径>
```

命令返回非零表示权限漂移。JSON 报告不包含数据库 URL 或密码，可作为发布证据保存。

## 验证覆盖

`verify` 会检查：

- 两个角色存在、可登录，且均无 superuser、BYPASSRLS、建库、建角色和 replication
  能力，同时必须为 `NOINHERIT`；
- app 角色不存在任何父角色 membership，避免通过显式 `SET ROLE` 获得额外权限；
- migration 角色拥有 schema 及其中的表、序列、视图和函数；
- app 角色有 schema 使用权、无创建权；
- app 对所有现有表、序列和函数拥有准确的运行权限；
- PUBLIC 不能直接执行应用 schema 内函数；
- migration 角色的新表、新序列、新函数默认权限完整，且新函数不会重新向 PUBLIC
  开放。

集成测试 `tests/integration/test_postgresql_role_provisioning.py` 使用随机 schema 和随机
角色验证重复 provisioning 与新对象默认权限。运行它需要临时、可创建角色的测试库：

```text
P1_POSTGRES_ADMIN_DATABASE_URL=<临时测试库管理员 URL>
python -m pytest tests/integration/test_postgresql_role_provisioning.py -v
```

测试只删除自己随机创建的 schema 和角色，禁止对生产数据库执行该测试。

## 密钥轮换与撤销

密码轮换时由 Secret Manager 注入新的对应密码变量，再执行 `provision`。工具不会输出
密码。若部署采用 IAM，角色创建后由平台侧绑定 IAM 身份，应用仍必须使用 app 角色，
迁移任务仍必须使用 migration 角色。退役环境应由 DBA 在确认连接全部停止后执行角色
撤销；本工具不会自动删除角色或数据库对象。
