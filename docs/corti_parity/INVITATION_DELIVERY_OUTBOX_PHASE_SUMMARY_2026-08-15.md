# 组织邀请投递 Outbox 阶段总结（2026-08-15）

## 阶段结论

本阶段把上一轮“管理员手工传递一次性邀请凭证”推进为开发环境可运行、可审计、可恢复、可测试的 Cloud 上线候选：邀请载荷加密持久化，通过签名且幂等的 webhook 交给区域通知服务，支持并发抢占、崩溃恢复、有界重试、死信重排和生命周期擦除。Cloud 未安全配置时失败关闭；本地仍保留兼容的 manual 模式。

这不等同于生产邮件已经上线，也不证明与 Corti 企业邀请、IAM 或托管 SLA 等价。本轮没有重新操作 Corti 控制台，避免此前 Windows/Codex 原生内存崩溃链；差距判断沿用已登录只读证据和公开可访问产品边界，不推测 Corti 私有实现。

## 已完成能力

1. 新增 `organization_invite_deliveries` 持久化 outbox 与 Alembic 042；载荷包含收件人、组织、角色、过期时间和接受链接，但数据库只保存 Fernet 密文。
2. Webhook 模式创建邀请不返回原始 token；邀请表继续只保存 SHA-256 摘要。成功、接受、撤销和过期会擦除 outbox 密文。
3. Cloud 强制 webhook、HTTPS、32–512 字符 bearer、精确邮箱域名白名单、PHI 加密以及受限的最大尝试、重试、claim 与 HTTP 超时。
4. Webhook 请求具有 bearer 鉴权、timestamp/body HMAC、稳定幂等键、禁止重定向和不持久化响应正文的边界。
5. 条件更新实现多 worker 至多一次抢占；陈旧 processing lock 可恢复。网络错误、408/425/429/5xx 进入确定性抖动的指数退避，达到上限或永久失败进入死信。
6. owner/admin 可查看 `delivery_status`，可对仍有效的死信重排；响应与审计不暴露收件 token、密文或 Provider message ID，后者只保存 SHA-256。
7. 新增默认 dry-run、显式 `--execute`、最大 100 条批次的处理器 CLI，输出仅有聚合计数。
8. 新增 `/accept-invite` 前端闭环：token 始终保留在 URL fragment，不写 local/session storage；认证后先从浏览器历史清除，再接受邀请并切换组织。
9. 投递成功、重试、死信与人工重排均进入租户归属审计；运维手册补齐配置、Provider 合同、处理器、监控与事故处置。

## 验证证据

- 新邀请投递专项：**6/6**。覆盖真实 localhost webhook、bearer/HMAC/幂等键、密文不可见、投递后擦除、真实 JWT 接受、永久失败、死信重排、撤销、双 worker 并发抢占、陈旧锁恢复、有界重试、域名拒绝和 CLI dry-run。
- 扩大后端串行回归：**106/106**。覆盖邀请、组织 RBAC、平台访问、OAuth、指标、审计、保留期、Cloud 失败关闭和系统审计。
- 既有密钥轮换测试的“数据库仅一行”顺序依赖已修复为按轮换前实际 eligible 行数断言；独立测试与扩大组合均通过。
- 前端全量：**113/113**；TypeScript + Vite 生产构建通过。
- OpenAPI 已重新导出，`python scripts/export_openapi.py --check` 通过；Alembic 单 head 为 `042`。
- Alembic 独立临时库实际完成 `041 → 042 → 041 → 042`，建表与回滚结果正确，临时库已删除。
- 静态部署预检 [development_preflight_20260815_invite_delivery](../../reports/deployment/development_preflight_20260815_invite_delivery/) 为 **44/44**。
- 安全收尾：变更文件中实时 key 形态命中 0，8000 监听 0，项目 pytest/uvicorn/python 遗留进程 0，`git diff --check` 无空白错误。
- 所有 Python 测试均先清除子进程 `ICODER_CREDENTIAL_LLM` 并固定 `LLM_PROVIDER=mock`；未调用真实 LLM/ASR、未发送真实邮件、未消耗 Corti credits。

## 与 Corti 的当前能力差距

| 能力 | iCoDer 当前证据 | 尚未关闭的差距 |
|---|---|---|
| 邀请创建与接受 | 摘要凭证、邮箱匹配、一次性接受、过期/撤销、防重放、fragment 前端闭环 | 未以同一租户逐像素验证 Corti 当前成员邀请 UI、通知模板与管理员状态展示 |
| 投递可靠性 | 加密 outbox、并发 claim、陈旧锁、有界重试、死信重排、幂等 webhook | 只对本地 receiver 做 E2E；缺真实区域邮件 Provider、生产 scheduler、多副本 PostgreSQL、退信/投诉回调、容量与 SLA |
| 安全 | Cloud 失败关闭、域名精确白名单、HMAC、token/密文不出 API 与审计、生命周期擦除 | 缺真实 KMS/HSM、邮件网关反钓鱼模板审批、独立渗透、密钥轮换演练和医院安全验收 |
| 企业身份 | 组织 owner/admin/member/viewer 与平台角色分离 | 仍缺 SAML/OIDC SSO、SCIM、MFA/step-up、IdP 组映射、条件访问和离职自动回收 |
| 中国场景 | 支持医院精确域名策略、CN 区域 webhook 配置与中文接受页 | 仍需真实医院邮箱网关、国产邮件/短信服务合规评估、模板备案、等保/个保流程和医院审批 |
| Corti 等价性 | 可复现的开发环境工程合同与失败模式 | Corti 私有 IAM、邮件基础设施、监控、计费和 SLA 不公开，不能通过控制台逆向证明等价 |

## 外部门禁与下一阶段

必须由外部环境完成：真实邮件 Provider 接入、生产 scheduler/CronJob、PostgreSQL 多副本竞争与故障注入、退信/投诉闭环、模板与域名审批、KMS、容量/灾备/SLA、独立安全评估以及医院验收。

下一开发阶段优先处理企业身份候选中的双人审批/临时权限数据模型，或回到 26 Agent 的统一去标识真实病历质量基准、Corti 双边输出与中国医疗规则包。总目标继续进行中；本阶段不能标记 `production_ready`、Corti 等价或医院可上线。
