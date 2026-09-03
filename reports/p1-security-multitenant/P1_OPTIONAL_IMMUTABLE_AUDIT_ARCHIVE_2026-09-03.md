# P1 不可抵赖审计归档可选化审查报告

- 日期：2026-09-03
- 范围：PostgreSQL 链式审计归档、软件 HSM 外部 WORM 复制、启动门禁、CI 和部署文档
- 决策：不可抵赖审计归档调整为默认关闭的部署级高级合规功能

## 1. 变更前问题

变更前，软件 HSM 管理脚本会在 `ICODER_DEPLOYMENT_MODE=cloud` 时隐式要求 WORM 后端。这使普通
云部署即使不购买或不需要合规级归档，也必须提供 adapter、checkpoint key 和归档存储。PostgreSQL
生产启动同样无条件检查 `audit_integrity_archive` 的 RLS/触发器并解析签名密钥，产品能力边界与部署
要求耦合。

## 2. 产品决策

新增唯一主开关：

```text
ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED=false
```

默认产品继续提供标准审计日志、字段脱敏、租户隔离和软件 HSM 本地签名操作链。高级模式增加
PostgreSQL 链式副本、外部 WORM、独立 checkpoint、归档对账/恢复/导出。此开关为部署级能力，
本轮没有伪造尚不存在的租户套餐 entitlement。

## 3. 实现变更

1. `Settings` 增加默认值为 false 的高级功能开关；云模式不改变该默认值。
2. `archive_audit_log` 在开关关闭时立即返回，不查询归档表、不生成 envelope、不解析签名密钥。
3. PostgreSQL 启动只在开关开启时检查归档表 RLS、不可变触发器和 signer。
4. 软件 HSM 管理不再把 cloud 模式视为自动启用条件。
5. 高级模式仍保持写前复制与复验失败即阻止密钥库突变的 fail-closed 语义。
6. 旧 `ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED=true` 保留为显式兼容入口，但不再推荐。
7. CI 显式开启高级能力，继续覆盖其归档、对账和导出路径。

## 4. 数据与迁移影响

- 不新增数据库迁移。
- 不删除 revision 070 的表、函数、触发器或任何历史证据。
- 关闭功能只停止创建新的链式归档 envelope 和外部 WORM 副本。
- `audit_logs` 的标准写入路径保持不变。
- PHI revision 071/072、租户 RLS、revision 073 membership bootstrap 与数据库角色模型不受影响。

## 5. 安全边界

默认模式不能对外宣称具备生产 WORM 或不可抵赖归档。高级功能也只有在真实云/独立 WORM 后端、
独立身份、保留策略和恢复演练通过后才能作此声明。本地 simulator 只验证接口和失败语义。

高级功能关闭不会关闭：

- 审计日志；
- 审计字段 PHI 脱敏；
- 软件 HSM 运维签名链；
- PHI 静态加密；
- 多租户数据库强制隔离；
- 管理员和 OAuth 安全控制。

## 6. 验证标准

本轮测试必须证明：

1. 未设置开关时默认 false；
2. cloud 模式不会隐式启用外部 WORM；
3. 默认模式的软件 HSM 突变成功且仍产生可验证的 started/completed 签名记录；
4. 开启高级模式后，归档不可用仍阻断突变；
5. 开启高级模式后，写前/写后复制、checkpoint 和归档复验仍通过；
6. 既有本地和 S3 adapter 契约测试保持通过。

实际验证结果：

- 可选开关、数据库归档、local/S3 adapter、reconcile 与 RLS 静态契约：45 passed；
- 云配置 fail-closed 与默认值组合回归：80 passed；
- 标准/系统/OAuth/保留删除审计调用路径：44 passed；
- 真实 PostgreSQL 下 PHI、RLS、membership、角色、轮换与归档组合：64 passed，2 skipped；
- 最终聚合定向回归（配置、审计、adapter、对账、数据库契约）：114 passed；
- Python `compileall`：通过；
- GitHub Actions YAML 解析：通过；
- `git diff --check`：通过。

两项 skip 的准确原因分别是未提供 `P1_POSTGRES_ADMIN_DATABASE_URL` 和该用例要求的完整 PostgreSQL
角色 URL 集合，不是断言失败；其余 12 项真实 PostgreSQL 集成测试通过。本轮未连接真实 AWS 或
阿里云 WORM 服务，因此没有新增任何云环境合规声明。

## 7. 后续工作

阿里云支持应作为独立后续阶段实现 `AliyunOssWormAuditArchive`。在没有真实阿里云 OSS BucketWorm、
KMS、RAM 和跨区域复制环境之前，仓库只能标记 adapter 工程完成，不能标记生产合规验收完成。
