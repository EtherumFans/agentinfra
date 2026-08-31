# PlatformAccessPage 平台访问控制操作指导

## 适用范围

该页面只对平台角色 `admin` 可见，用于平台级用户角色、账户状态、组织状态和套餐管理。它不同于 Team 页面：Team 管理单个组织内的 `owner/admin/member/viewer`，本页面管理跨组织的平台角色。

## 用户访问变更

1. 打开 **管理 → 平台访问控制 → 用户**。
2. 核对姓名、邮箱、当前平台角色、账户状态和显示的 token version。
3. 选择新角色或启用状态。
4. 选择固定原因代码；有审批/变更工单时填写仅含字母、数字、点、下划线或连字符的工单号。
5. 点击保存。服务端会校验页面提交的 token version；如果其他管理员已先行修改，返回 `STALE_USER_ACCESS_VERSION`，必须刷新后重新审核。

成功变更会立即撤销目标用户现有 JWT、refresh token 和其拥有的 OAuth token。停用账户还会禁用目标用户拥有的 API Client。目标用户必须重新登录；停用用户不能重新登录。

平台管理员不能修改自己的角色或停用自己，也不能移除最后一个有效平台管理员。这些拒绝和成功操作都会写入 `MODERN_SYSTEM` 审计。

## 组织控制面变更

1. 切换到 **组织** 标签。
2. 选择 `free/pro/enterprise` 套餐或组织启用状态。
3. 选择原因代码并填写可选工单号。
4. 点击保存。

停用组织会撤销所有成员的用户会话，禁用该组织的 API Client，并撤销已签发的 OAuth token。恢复组织不会自动恢复已禁用的 Client；平台管理员必须在完成安全复核后单独恢复所需 Client。

## 首个管理员

Cloud 禁止自动 seed 默认管理员。先通过普通注册建立一个最低权限 `coder` 用户，再由数据库/平台运维人员执行默认 dry-run 的一次性命令：

```bash
cd backend
python scripts/bootstrap_platform_admin.py --identifier ops@example.cn --ticket-id IAM-0001
python scripts/bootstrap_platform_admin.py --identifier ops@example.cn --ticket-id IAM-0001 --execute
```

只要已经存在一个有效平台管理员，该命令就会失败关闭。命令不接收、输出或重置用户密码。

## 上线前外部门禁

- 管理员 MFA 或 step-up authentication；
- privileged grant 双人审批；
- 企业 SSO/SCIM、离职自动回收和定期权限复核；
- 独立渗透、审计与医院信息安全验收。

开发页面和自动化测试不能替代上述治理流程。
