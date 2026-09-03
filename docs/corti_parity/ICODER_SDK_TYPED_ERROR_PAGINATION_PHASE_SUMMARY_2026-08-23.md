# iCoDer SDK 类型化错误与自动分页阶段总结（2026-08-23）

> 本阶段证明 JavaScript/Python SDK 在本地 HTTP 合同下的错误分型、脱敏与 Agentic cursor 自动翻页，不代表 Corti 托管租户或生产网络等价。

## Corti 官方基线

Corti SDK Overview 明确承诺 typed exceptions、structured details、`for await` / `await foreach` pagination 和自动重试：<https://docs.corti.ai/sdk/overview>。Corti .NET Reference 进一步给出默认 `MaxRetries=2`，范围为 **408、429、5xx**，并公开 400/401/403/404/409/422/500/502/504 的错误子类及统一基类：<https://docs.corti.ai/sdk/dotnet/reference>。

复核发现上一阶段 iCoDer 仍有两个准确差距：重试遗漏 408；普通资源继续暴露 Axios/httpx 原生异常，且 Agentic Task/Context/Trace 只能手动推进 `pageToken`。

## 已实现

- JavaScript/Python 均新增统一 SDK/API 错误基类，以及与 Corti 公布状态码对应的九类异常。
- 错误只保留 HTTP status、可选 request/correlation ID，以及白名单 code、reason、field、location、type；原始 request、Authorization、response body、验证 `input` 与自由文本 `msg` 不进入异常。
- A2A JSON-RPC/google.rpc 只保留数字 code 与稳定枚举 reason，仍映射到既有 `A2AProtocolError`，没有被通用层降级。
- 408 纳入既有幂等感知、有界、封顶重试；POST/PATCH 仍须 `Idempotency-Key`。
- JavaScript `AsyncCursorPager` 和 Python `CursorPager` 均为惰性迭代，支持逐页访问、初始 cursor 和最大页数；重复、非法或无限 cursor 失败关闭。
- Agentic Task、Context、Context Task 和 OpenInference Trace 均新增自动迭代入口；原有单页方法保持兼容。

## 验证

| 门禁 | 结果 |
|---|---:|
| JavaScript SDK 全量与 TypeScript build | 63/63，0 failed |
| Python SDK 全量 | 64/64，0 failed |
| 新增错误/分页专项 | JS 5/5、Python 5/5 |

负向用例覆盖九个状态子类、PHI/secret 字段排除、408 恢复、惰性两页 cursor、重复 cursor、最大页数，以及通用 Axios 错误进入 A2A 后仍保留稳定 `TASK_NOT_FOUND` reason。

## 边界与剩余差距

- 自动分页已覆盖 Agent Hub/A2A 核心的四类 cursor 资源。旧 Reviews 的 page/page_size 和 Billing 的非分页/limit 合同仍保留单页方法，不能冒充 cursor pager；若服务端未来统一分页合同，应再接入同一安全迭代器。
- Corti 的 per-request timeout/retry/header override 尚未形成 iCoDer 资源级统一参数。
- STT WebSocket 已有资源专用连接与协议门禁，但没有 Corti 式跨语言 managed connection/reconnection/typed-event 抽象。
- .NET 本机仍缺 dotnet/csc/msbuild，无法编译或验证同等实现；Corti 托管租户互操作仍需外部环境。

因此统一类型化错误、408 重试和 Agentic cursor 自动分页已达到开发环境闭环；managed WebSocket、请求级选项、旧分页合同统一、.NET CI 与托管互操作继续保持开放。

后续 [`ICODER_SDK_MANAGED_STT_EGRESS_SAFETY_PHASE_SUMMARY_2026-08-23.md`](ICODER_SDK_MANAGED_STT_EGRESS_SAFETY_PHASE_SUMMARY_2026-08-23.md) 已关闭 JavaScript/Python 对当前 iCoDer STT 协议的 managed lifecycle 差距；最新 SDK 回归为 JavaScript 68/68、Python 69/69。请求级选项、旧分页合同、Corti wire 互操作、真实区域 STT、.NET 与生产长连接仍开放。
