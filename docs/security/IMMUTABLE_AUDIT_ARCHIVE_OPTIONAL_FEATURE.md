# 不可抵赖审计归档：可选高级功能边界

## 产品定位

不可抵赖审计归档是部署级高级合规功能，默认关闭。它不属于产品基本运行、PostgreSQL 权威存储、
租户隔离、PHI 脱敏或 PHI 信封加密的必要前置条件。

开关：

```text
ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED=false
```

该开关是部署级能力开关，不是当前 `organization.plan` 的租户级计费授权判断。若将来需要按套餐售卖，
应由独立 entitlement 服务控制配置下发，不能允许租户通过 API 自行开启基础设施归档。

## 默认能力与高级能力

| 能力 | 默认产品 | 高级归档开启后 |
|---|---:|---:|
| 标准数据库审计日志 | 是 | 是 |
| PHI 最小化与审计字段脱敏 | 是 | 是 |
| 软件 HSM 本地签名操作链 | 是 | 是 |
| PostgreSQL 加密链式归档副本 | 否 | 是 |
| 外部 WORM 复制与独立 checkpoint | 否 | 是 |
| WORM 对账、恢复和最小化证据导出 | 否 | 是 |
| “不可抵赖/合规级不可变归档”声明 | 否 | 仅在真实后端验收后 |

关闭开关不会删除 revision 070 创建的表、函数或历史归档数据，也不会降低现有租户 RLS、数据库角色、
PHI 加密或标准审计日志要求。系统仅停止生成新的链式归档副本及强制连接外部 WORM。

## 启用条件

高级功能开启时必须同时满足：

1. PostgreSQL revision 070 归档表、FORCE RLS、追加函数和不可变触发器通过启动检查；
2. 注入独立审计签名密钥及 key ID；
3. 软件 HSM 运维命令配置受支持的外部归档 adapter；
4. checkpoint key 与 bootstrap key、KEK、ops-audit key 分离；
5. 生产 adapter 具备真实 WORM、最小权限身份、保留策略和恢复验证；
6. 供应商控制面验收通过后，才允许对外声明不可抵赖归档能力。

启用状态下维持 fail-closed：归档不可用或复验失败时，软件 HSM 密钥库突变不会继续执行。

## 兼容性

`ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED=true` 暂时作为旧部署的显式启用别名保留。它不再因
`ICODER_DEPLOYMENT_MODE=cloud` 自动变为 true。新部署统一使用
`ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED=true`。

CI 会显式开启高级功能来持续验证其实现；这不改变产品默认关闭状态。本地 WORM simulator 仅用于
开发和 CI，不能作为生产合规证明。
