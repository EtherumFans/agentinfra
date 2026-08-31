# 组织角色、邀请与令牌安全阶段总结（2026-08-15）

## 阶段结论

本阶段关闭了组织权限链中的四类高风险缺口：旧 Team API 全局读写、JWT 当前组织与路径组织错配、刷新令牌未执行版本撤销、组织成员变更后旧令牌继续有效。组织角色现统一为 `owner/admin/member/viewer`，平台角色与组织角色不再混用；旧 `/api/team` 保留为基于权威组织模型的租户内兼容门面。

本阶段达到开发环境中的上线候选安全合同，但不宣称已经等同于 Corti 的企业身份与组织治理。Corti 控制台本轮未再次操作，以避免此前 Windows/Codex 原生内存崩溃；差距判断沿用此前登录态只读证据和公开可访问能力，不新增无法验证的 Corti 内部实现断言。

## 完成内容

1. `get_current_user` 只接受 access token；refresh、runtime 与 client-credentials token 不能冒充普通用户访问令牌。
2. `get_current_organization` 将 `org_id` 视为上下文而非授权证明，并验证用户状态、`token_version`、组织成员关系；OAuth client 同时验证凭证未撤销及组织绑定。
3. 所有路径带 `org_id` 的组织读写必须与 JWT 当前组织严格一致；错配统一返回 404，避免确认其他租户是否存在。
4. 刷新端点执行精确 `token_version` 校验；切换组织签发的 access token 携带当前版本。角色变化、成员移除和组织停用会撤销相关用户的旧 access/refresh token。
5. 公开创建组织只能选择 `free`，不能自助声明 `pro/enterprise`；组织管理员不能通过通用 settings 写入 `verified`、环境已部署、环境分配或 plan 等保留控制面字段。
6. 管理员可管理普通成员，但只有 owner 可以邀请、授予、调整或移除 admin；owner 角色不可由普通成员接口变更或删除。
7. 邀请实现创建、管理员列表、一次性接受、邮箱主体匹配、七天过期、撤销、防重放和已是成员冲突处理。
8. 原始邀请凭证只在创建响应中显示一次，响应 `Cache-Control: no-store`；数据库只保存 SHA-256 摘要，041 迁移会把历史明文邀请凭证原地转换为摘要，日志和审计均不记录原始凭证。
9. 组织创建、更新、停用、邀请创建/接受/撤销、成员移除和角色变更均写入租户审计；审计允许的字段仅包含组织、邀请、目标用户 ID 和枚举角色等运维元数据。
10. Team 页面与兼容 API 已统一展示/提交 `admin/member/viewer`，不再把平台 `coder/dept_head` 当作组织角色。

## 验证证据

- 最终后端组合回归：**82 passed**。覆盖真实 JWT、组织边界、邀请生命周期、令牌撤销、OAuth、API Client、CDI 真实租户归属、指标授权、Run 保留和审计脱敏。
- 新增组织安全测试：**6/6**，覆盖跨租户路径、refresh 冒充、摘要存储、错误邮箱、一次性消费、角色最小权限、旧 Team 门面隔离、付费计划自助提权、撤销、过期、组织停用与重新登录上下文。
- 前端 TypeScript + Vite 生产构建通过；生成物成功包含 Team 页面。
- OpenAPI 已重新导出并通过 `python scripts/export_openapi.py --check`；前端 API 合同 **50/50** 通过。
- Alembic 只有一个 head：`041`。
- 静态部署预检 [development_preflight_20260815_org_rbac](../../reports/deployment/development_preflight_20260815_org_rbac/) 为 **35/35 checks pass**。
- 静态安全收尾：变更及报告范围内真实 key 命中 **0**，原始邀请/重置凭证日志命中 **0**，8000 监听 **0**，pytest/uvicorn 遗留进程 **0**，`git diff --check` 无空白错误。
- 本轮所有 Python 测试在启动前删除 `ICODER_CREDENTIAL_LLM` 并设置 `LLM_PROVIDER=mock`；没有调用真实 LLM、ASR、Corti 预测或 credits。

测试环境仍报告既有的本地短 JWT 测试密钥警告、Pydantic 字段命名警告和 Starlette/httpx 弃用警告；Cloud 配置已有强密钥失败关闭，这些警告不影响本轮断言，但应在依赖治理阶段消除。

## 与 Corti 的当前差距

| 能力 | iCoDer 当前证据 | 尚未关闭的差距 |
|---|---|---|
| 项目/组织租户边界 | 真实 JWT 跨租户负向测试、路径绑定和成员校验通过 | Corti 内部租户实现和运维隔离不可见；仍需独立渗透与云数据面验证 |
| 成员角色 | owner/admin/member/viewer 最小权限、owner 保护、令牌撤销 | 尚无企业自定义角色、权限模板、定期访问复核和医院审批工作流 |
| 邀请生命周期 | 摘要存储、一次性接受、邮箱匹配、过期、撤销、防重放 | 当前开发模式为管理员手工传递一次性凭证；尚未接生产邮件、医院域名限制、反钓鱼模板和投递审计 |
| 企业身份 | 本地账号、JWT、OAuth client 可运行 | 尚无 SAML/OIDC 企业 SSO、SCIM、MFA、条件访问、IdP 组映射和离职自动回收 |
| 令牌撤销 | 角色变化/成员移除/组织停用触发全局版本撤销 | 全局撤销会影响用户其他组织会话；后续可引入每组织 membership version 以减少影响面 |
| 计划与控制面 | 普通用户不能自助声明付费计划或写入环境已部署/verified | 真实 billing、合同、credits、平台审批、环境供应和商业运营仍未接通 |

## 密钥与运行环境收尾

Windows 用户级 `ICODER_CREDENTIAL_LLM` 已清除，机器级未设置。但当前 Codex 父进程仍可能保留启动时继承的旧值，必须重启 Codex/相关终端后才会从进程环境消失。此前在对话中暴露过的 DeepSeek key 必须到供应商控制台立即注销/轮换；本轮没有使用它，不能因此视为仍然安全。

## 下一阶段优先级

1. 增加受审计的平台角色赋权/回收 API，要求平台 admin、禁止自我提权，并与组织角色界面彻底分离。
2. 设计生产邀请 outbox 与邮件 Provider 接口，接入医院域名策略、重试/退信、模板签名和安全告警；在 Provider 未配置时 Cloud 必须失败关闭。
3. 在 Linux/PostgreSQL 环境执行并发邀请消费、唯一约束竞争、角色变更期间的请求竞争和多 worker 令牌撤销测试。
4. 补齐 SSO/SCIM/MFA/条件访问的产品与安全设计；真实 IdP、医院目录和审批属于外部联调门禁。
5. 继续总目标中的 26 Agent 真实临床质量、统一去标识病例 Corti 双边对比、中国 ASR/规则包、云基础设施与医院 reviewer 门禁。

总目标继续进行中；本阶段不能标记 `production_ready`、Corti 等价、医院可上线或企业身份治理完成。
