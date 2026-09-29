# 异步任务与结果通知

每批最多 20 份文书。POST `/api/v1/agents/{agent_id}/jobs`，请求头 `Authorization: Bearer …` 和 `Idempotency-Key`（最多 120 个 ASCII 字符）。同一批资料超时重试必须复用该键，不能因网络错误生成新键。请求体示例：

```json
{"inputs":[{"text":"合成文书 A"},{"text":"合成文书 B"}],"purpose_of_use":"quality_improvement","expected_agent_version":"1.0.0","expected_configuration_digest":"从集成配置获取的摘要"}
```

返回 202 及任务列表。GET `/api/v1/agent-jobs/{id}` 获取状态与结果；GET `/api/v1/agent-jobs?agent_id=…` 列出当前用户或客户端自己的任务。排队任务可以 POST `/{id}/cancel`（在 agent-jobs 路径下），运行中的任务不伪装为已取消。提交时冻结发布版本，之后的新发布不会替换排队任务版本。撤销客户端或用户组织权限会阻止尚未执行的任务。

状态依次为 queued、running、completed/failed。重启后排队任务继续；运行租约过期标记 interrupted，不自动重跑。该状态表示可能已经产生执行效果，必须核对运行记录。当前内置执行器每进程并发 2 个任务，每个任务最长 30 分钟；数据库原子领取防止多个进程同时领取同一任务。组织最多积压 100 个排队／执行中任务。

下载的用户服务端示例提供 `/icoder/jobs` 和 `/icoder/jobs/{id}`，接受本地用户认证；专用凭据与版本固定在服务端。它返回相同的异步状态，不向浏览器泄露 OAuth 凭据。

## 回调

部署管理员通过环境变量按组织配置：`ICODER_TASK_CALLBACK_URLS` 为组织 ID 到 HTTPS URL 数组的 JSON 映射，`ICODER_TASK_CALLBACK_SECRETS` 为组织 ID 到至少 32 字符签名密钥的 JSON 映射。密钥通过部署密钥管理提供。提交时可选 `callback_url` 必须精确匹配当前组织注册地址，不允许用户名、密码、查询串、跳转或非 443 端口。出站连接使用既有 DNS/IP 固定传输，拒绝内网和元数据地址。

通知仅含 event_id、job_id、agent_id、version、state、run_id、result_url，不含文书或结果内容。签名头 `X-iCoDer-Signature` 为 `UTC秒数.HMAC-SHA256`，签名原文为 `秒数 + "." + 原始请求体`。接收端使用 [verify_notification.py](../../frontend/public/integration/verify_notification.py) 验证签名和 5 分钟时间窗口，再以 event_id 的数据库唯一约束去重，最后处理事件。已处理事件应返回 2xx。

网络错误、429 与 5xx 最多自动尝试 5 次，指数退避；其他 4xx、3xx 或配置撤销进入 failed。通知可能重复，接收端必须去重。失败通知可以 POST `/api/v1/agent-jobs/{id}/retry-notification`，只重试通知，不重新执行任务。结果始终通过授权查询接口获取。

数据库迁移 082 新增任务及通知表，PostgreSQL 强制租户隔离和任务输入／结果加密。环境必须配置既有 PHI 加密密钥。该功能不构成自动医疗决策或业务写回授权。


## 工作进程容量（2026-09-08）

执行与通知使用独立并发池。`ICODER_JOB_CONCURRENCY` 默认 2，`ICODER_JOB_PER_ORG_CONCURRENCY` 默认 1，`ICODER_NOTIFICATION_CONCURRENCY` 默认 4；各值范围 1–32，非法配置在启动时拒绝。`ICODER_JOB_POLL_SECONDS` 默认 2，范围 1–60；空闲扫描指数退避到 30 秒。组织扫描分批轮转，慢回调不占执行槽位。上述容量是每个工作进程的上限，不是集群全局配额；多实例仍依赖数据库原子领取及租约防止重复领取。

## 浏览器登录（迁移 084）

SPA 使用 `/api/auth/browser/login|register|refresh|switch-org|logout`。刷新凭据仅保存在 HttpOnly、SameSite=Strict 的 cookie 中，路径 `/api/auth/browser`；生产环境要求 HTTPS 并设置 Secure。请求需精确匹配允许的 Origin，带 `X-iCoDer-Browser: 1`。访问令牌有效期 5 分钟，仅放在内存；刷新不会延长浏览器会话最初的到期时间。退出撤销当前会话，旧访问令牌和复制的刷新令牌均不能继续使用；其他浏览器会话与服务端 OAuth 客户端不受影响。

升级先执行 `alembic upgrade head`（084），确保应用角色对 `browser_sessions` 具有所需 DML 权限。该表属于用户认证状态，不是组织业务数据。存在会话记录时迁移拒绝直接降级，避免丢失撤销状态。浏览器会清除旧 localStorage 登录数据，升级后首次需要重新登录。原有 `/api/auth/*` 与 OAuth 服务端集成接口保持兼容。


## 第三方接入验收（2026-09-09）

在“集成到我的系统”中选择发布版本和用途，下载 `server.py`、`verify_notification.py` 及 `integration-config.json` 到同一目录。配置中的客户端应仅授权选定智能体与用途。安装已有运行要求 fastapi、uvicorn、httpx 后运行 `python server.py`；默认访问 `http://127.0.0.1:13010`，以 demo 和自己配置的 DEMO_PASSWORD 登录。该示例是本机集成验证工具，生产接入应替换为宿主系统的用户身份与权限校验。

“检查服务端接入”实际使用服务端 OAuth 凭据执行一次合成请求；报告包含时间、耗时、预期与实际版本、配置摘要、run_id 和检查状态。只有执行成功且版本、运行标识齐全才通过。下载报告不包含凭据和文书正文。认证、访问权限、绑定冲突、输入错误、限流和网络超时分别给出处理建议；超时不会自动重跑同步任务。

“提交合成异步任务”保留提交幂等键，在结果不确定时不得换键重发。页面轮询最多约两分钟，之后可通过“刷新任务与回调状态”继续检查。任务完成与回调收到分开展示，也可以下载异步验收报告。

需要真实回调时，在第三方配置增加 `ICODER_CALLBACK_URL`（指向其 `/icoder/notifications` 的公开 HTTPS 地址）和至少 32 字符的 `ICODER_CALLBACK_SECRET`。由部署管理员在 iCoDer 的组织回调白名单及签名密钥配置中登记相同信息。示例仅监听回环，公网入口需由实际部署提供正确的 TLS 与反向代理，并保留安全的 Host 配置；不要直接把本机演示服务暴露到公网。

接收器对原始请求体验签并验证 5 分钟时间窗口、智能体、版本及终态；使用 `notification-receipts.db` 的 event_id 主键实现持久去重。重复事件返回成功但不重复记账，错误签名返回 401。数据库只存回执元数据。处理业务结果时应通过授权结果接口读取，并在宿主系统中使用事务或 outbox 将去重与业务操作统一；当前示例没有自动业务写回。
