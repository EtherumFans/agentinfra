# 组织邀请投递运维手册

> 声明：开发环境上线候选操作说明，不代表生产邮件服务已开通  
> 日期：2026-08-15  
> 阶段：Invitation Delivery Outbox  
> 状态：开发环境验证通过，外部邮件与云调度门禁未关闭

## 1. 工作模式

- `manual`：仅供本地开发。创建邀请时原始凭证只返回一次，响应带 `Cache-Control: no-store`，数据库只保存 SHA-256 摘要。
- `webhook`：Cloud 必选。创建邀请只返回 `delivery=queued`，不返回原始凭证；收件人、组织与接受链接作为 Fernet 密文写入 outbox。

Cloud 启动会拒绝手工模式、HTTP/localhost webhook、弱 bearer、空域名白名单、缺少 PHI 加密密钥以及越界的重试/超时配置。

## 2. 必需配置

从 Secret Manager/KMS 注入以下秘密，禁止写入仓库、工单或命令历史：

```text
ICODER_PHI_ENCRYPTION_KEY
ICODER_INVITE_WEBHOOK_BEARER_TOKEN
```

其余配置：

```text
ICODER_INVITE_DELIVERY_MODE=webhook
ICODER_INVITE_WEBHOOK_URL=https://notification.example.cn/invitations
ICODER_INVITE_ALLOWED_EMAIL_DOMAINS=["hospital.example.cn"]
ICODER_INVITE_MAX_ATTEMPTS=5
ICODER_INVITE_RETRY_BASE_SECONDS=30
ICODER_INVITE_CLAIM_TIMEOUT_SECONDS=120
ICODER_INVITE_WEBHOOK_TIMEOUT_SECONDS=10
```

域名策略是精确匹配，不接受通配符。前端接受链接的 origin 取 `CORS_ORIGINS` 第一项，因此第一项必须是正式 Console origin。

## 3. Webhook 合同

请求使用 JSON，包含 schema version、邀请/组织标识、组织名、收件地址、角色、过期时间和 fragment 形式的接受链接。每次请求携带：

- `Authorization: Bearer ...`
- `Idempotency-Key: invite-delivery-{delivery_id}`
- `X-iCoDer-Timestamp`
- `X-iCoDer-Signature: sha256=...`

签名输入为 `timestamp + "." + raw_body`，密钥为 webhook bearer。Provider 必须验证时间窗、HMAC 与幂等键，且不得把接受链接或 token 写入日志。

## 4. 处理 outbox

默认命令只读，不发送邮件：

```powershell
python scripts/process_invite_outbox.py
```

显式处理最多 20 条：

```powershell
python scripts/process_invite_outbox.py --execute --limit 20
```

处理器使用条件更新抢占任务；崩溃后超过 claim timeout 的任务可以被另一 worker 回收。408/425/429/5xx 与网络错误按有界指数退避重试；其他 4xx 或达到最大次数进入 `dead_letter`。

成功、接受、撤销或过期都会擦除 outbox 密文。死信保留密文以允许管理员在修复 Provider 后调用 retry API；邀请过期后不能重排。

## 5. 监控与处置

审计动作：

- `org.invite.delivery_succeeded`
- `org.invite.delivery_retry_scheduled`
- `org.invite.delivery_dead_letter`
- `org.invite.delivery_requeued`

推荐告警：死信数量大于 0、最老 queued/retry 超过两个调度周期、连续 5xx、处理器无心跳。当前仓库没有生产 scheduler、邮件 Provider dashboard、退信/投诉 webhook 或 SLA 告警投递，这些必须由目标云与邮件服务完成。

## 6. 安全事故

若邀请或 webhook 凭证疑似泄露：

1. 撤销对应邀请；
2. 轮换 webhook bearer，并同步 Provider；
3. 检查成功/重试/死信审计，不在工单中粘贴原始 payload；
4. 必要时轮换 Fernet key，并按加密密钥轮换流程重加密仍保留的死信；
5. 对已暴露的邀请链接按 bearer credential 处理，不依赖“尚未被使用”判断安全。

## 7. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-08-15 | 新增加密 outbox、签名 webhook、有界重试、死信重排与浏览器接受流程 | Corti 对标阶段优化 |
