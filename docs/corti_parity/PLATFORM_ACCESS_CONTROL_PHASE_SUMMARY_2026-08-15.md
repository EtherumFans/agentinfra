# 平台访问控制与凭证撤销阶段总结（2026-08-15）

## 阶段结论

本阶段把平台角色从“公共注册已禁止自助提权，但没有正式赋权/回收流程”推进为可运行、可审计、可测试的开发上线候选。平台 `admin/coder/dept_head/insurance/qc/clinician/it/cdi_specialist/medical_records_admin` 与组织 `owner/admin/member/viewer` 明确分离；前端新增仅平台 admin 可进入的访问控制页面。

该能力不等同于 Corti 企业 IAM。Corti 控制台本轮未重新操作，以避免此前 Windows/Codex 原生内存崩溃；对标只沿用此前登录态只读证据和公开可访问资料，不推断 Corti 未公开的管理员审批、IdP 或令牌实现。

## 完成内容

1. 新增 `PATCH /api/admin/users/{user_id}`：可更新平台角色和账户启用状态，请求必须携带当前 `expected_token_version`、固定 reason code 和可选安全工单号。
2. 乐观版本不一致返回 `STALE_USER_ACCESS_VERSION`，避免两个管理员基于陈旧页面互相覆盖；成功响应返回新 token version。
3. 平台管理员不能修改或停用自己，不能移除最后一个有效平台管理员；成功和拒绝均写入 `MODERN_SYSTEM` 审计。
4. 角色或账户状态变化立即撤销目标用户的 access/refresh token 及其拥有的 OAuth token；账户停用同时禁用其 API Client。
5. 修复原 `_revoke_user_tokens` 通过猜测 client_id 查找 OAuth token 的错误逻辑，现按 `OAuthClient.owner_id` 权威关联撤销。
6. 修复修改密码后旧会话仍有效的问题：密码变更现同步撤销 JWT、refresh 和用户拥有的 OAuth token。
7. 平台组织更新改为 JSON 合同，套餐只允许 `free/pro/enterprise`，必须携带固定 reason code；停用组织会撤销全部成员会话、禁用该组织 API Client 并撤销已签发 OAuth token。
8. 平台组织变化使用租户归属的 `MODERN_SYSTEM` 审计；平台用户权限变化使用无单一租户的系统审计，普通租户审计读者不可见。
9. 新增一次性首管理员 CLI：默认 dry-run、必须提供工单号、只接受已有有效用户，并在任何有效平台 admin 已存在时失败关闭；不接收或输出密码。
10. 新增 PlatformAccessPage，普通用户无导航入口且路由强制跳转；页面明确区分平台角色与组织角色，支持用户/组织变更、版本冲突提示和凭证撤销反馈。
11. 前端 UserRole 补齐 `cdi_specialist` 与 `medical_records_admin`，不再丢失后端已支持的中国医院岗位角色。
12. Cloud 部署文档和操作手册补齐首次引导、平台权限变更、组织停用和外部门禁流程。

## 验证证据

- 最终后端组合回归：**126 passed**。覆盖平台访问、首管理员引导、组织 RBAC、真实 JWT、OAuth/API Client、密码撤销、CDI 租户归属、指标鉴权、Run 保留、Cloud 失败关闭与系统审计。
- 新增平台访问目标测试：**4/4**，包括非管理员拒绝、自我修改拒绝、陈旧版本冲突、角色赋权、管理员赋权、账户停用、组织停用、OAuth Client/token 撤销、密码变化撤销、一次性 bootstrap 及审计分类。
- 前端 TypeScript + Vite 生产构建通过，生成独立 `PlatformAccessPage` chunk。
- OpenAPI 已重新导出并通过 `--check`；前端 API 合同 **54/54** 通过。
- 静态部署预检 [development_preflight_20260815_platform_access](../../reports/deployment/development_preflight_20260815_platform_access/) 为 **39/39 checks pass**。
- bootstrap CLI `--help` 可执行；默认没有 `--execute` 时只输出 dry-run 计划，自动测试证明第二次引导失败关闭。
- 安全收尾：变更/报告范围内真实 key 命中 **0**，原始凭证日志命中 **0**，8000 监听 **0**，pytest/uvicorn 遗留进程 **0**，`git diff --check` 无空白错误。
- 所有 Python 测试在启动前删除 `ICODER_CREDENTIAL_LLM` 并设置 `LLM_PROVIDER=mock`；没有调用真实 LLM、ASR、Corti 预测或 credits。

测试环境仍报告既有的本地短 JWT 测试密钥、Pydantic 字段命名和 Starlette/httpx 弃用警告。Cloud 已对强密钥失败关闭；警告不影响本轮断言，但属于后续依赖治理工作。

## 与 Corti 的当前差距

| 能力 | iCoDer 当前证据 | 尚未关闭的差距 |
|---|---|---|
| 平台角色赋权 | 真实 JWT 管理 API、版本冲突、自我修改保护、系统审计 | 尚无 MFA/step-up、双人审批、临时权限到期和 privileged access management |
| 企业身份生命周期 | 用户停用、角色回收与凭证撤销可运行 | 尚无 SAML/OIDC SSO、SCIM、IdP 组映射、离职自动回收和定期 access review |
| 首管理员 | 零管理员条件下默认 dry-run 的一次性运维 CLI | 仍需云数据库权限隔离、break-glass 保管、双人执行及真实审计接收器验证 |
| 组织停用 | 成员 JWT 与组织 Client/token 同步撤销 | 当前用户 token version 为全局版本，停用一个组织会影响用户其他组织会话；后续需每组织 membership version |
| 管理 Console | admin-only 页面、用户与组织变更均接真实 API | 尚无审批队列、变更 diff 复核、审计检索、批量 SCIM 状态和像素级 Corti 等价证据 |
| Corti 对标 | 已知公开控制面具备 Project/API Client/能力配置结构 | Corti 企业 IAM、内部角色矩阵、令牌撤销和审批 SLA 不公开，无法通过控制台逆向证明等价 |

## 密钥与运行环境收尾

Windows 用户级和机器级 `ICODER_CREDENTIAL_LLM` 均未设置。当前 Codex 父进程仍可能保留启动时继承的旧值，必须重启 Codex/相关终端才能清除进程环境。此前在对话中暴露的 DeepSeek key 仍必须在供应商控制台注销/轮换；本阶段没有使用它。

## 下一阶段优先级

1. 实现生产邀请 outbox/Provider 抽象、Cloud 未配置失败关闭、医院域名策略、退信/重试和投递审计；真实邮件账号属于外部联调。
2. 为平台角色增加双人审批数据模型、有效期和 break-glass 恢复演练候选；真正 MFA/SSO/SCIM 仍需真实 IdP。
3. 在 Linux/PostgreSQL 多 worker 环境验证同时赋权、陈旧版本冲突、停用期间在途请求和跨进程撤销。
4. 继续 26 Agent 统一去标识病例真实质量基准、Corti 双边输出、中国 ASR/地方规则包和医院 reviewer 门禁。

总目标继续进行中；本阶段不能标记 `production_ready`、Corti 等价、企业 IAM 完成或医院可上线。
