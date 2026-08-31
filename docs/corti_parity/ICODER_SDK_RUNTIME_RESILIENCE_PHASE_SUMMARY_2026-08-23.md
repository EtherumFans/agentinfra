# iCoDer SDK 运行时韧性阶段总结（2026-08-23）

> 本阶段关闭可在本机验证的 SDK 鉴权刷新与 HTTP 重试差距，不代表 Corti 托管租户互操作、临床质量或生产批准。

## 官方对照基线

Corti 官方 SDK 文档明确列出自动 token refresh、并发安全刷新、可配置的 429/5xx 重试、typed errors、pagination 和 managed WebSockets：<https://docs.corti.ai/sdk/overview>；.NET 参考进一步公开客户端认证、重试与资源调用面：<https://docs.corti.ai/sdk/dotnet/reference>。Agentic SDK/集成范围见 <https://docs.corti.ai/agentic/sdks-integrations>。

本轮复核前，iCoDer JavaScript/Python SDK 只有单请求 401 refresh 雏形：client credentials 需手动换 token，并发 401 可能重复刷新；通用 429/5xx 没有统一有界策略。

## 已实现

- JavaScript 和 Python 均支持在客户端配置 OAuth client credentials，首请求前自动换 token，并按 `expires_in` 提前刷新。
- JavaScript 使用 single-flight Promise，Python 使用线程锁；并发首取 token 与并发 401 都只执行一次权威刷新。
- 401 只允许一次鉴权重放；旧 token 的并发失败若发现新 token 已安装，直接复用，不再次刷新。
- 429 与 5xx 使用可配置、指数、封顶的重试，并解析数值或 HTTP-date `Retry-After`。
- 默认只重试 GET/HEAD/OPTIONS/PUT/DELETE；POST/PATCH 必须携带 `Idempotency-Key`，防止非幂等临床或计费写入被静默重复。
- token 交换失败返回脱敏、类型化 `iCoDerAuthenticationError`，只暴露 HTTP status 和可选 request ID，不保留 client secret、Authorization 或请求正文。
- 原有静态 bearer 与 refresh-token 模式保持兼容；浏览器端仍禁止放置 client secret。

## 验证

| 门禁 | 结果 |
|---|---:|
| JavaScript SDK 全量与构建 | 58/58，TypeScript build 通过 |
| Python SDK 全量 | 59/59 |
| 新增韧性用例 | JS 4/4、Python 4/4 |

新增用例覆盖 8 路/6 路并发 token 获取与 401、单次刷新计数、429 `Retry-After` 上限、两次重试边界、无幂等键 POST 不重试、有幂等键 POST 可重试，以及 secret 不进入类型化异常。

## 仍未关闭（本阶段收尾时）

- Corti 文档所述的统一 API typed error taxonomy 与自动 pagination 尚未在 iCoDer 全资源面统一；当前只有鉴权错误及 A2A/Run 等资源自己的类型化错误。
- WebSocket 生命周期由 STT 资源处理，尚未形成与 Corti SDK 同等的跨语言 managed WebSocket 抽象。
- .NET 客户端未在本机编译或实跑；机器没有 dotnet/csc/msbuild。
- 未对 Corti 托管租户进行双向 SDK 互操作，也没有生产代理、网关故障注入、长时间连接或多副本压力证据。

因此本阶段把“自动 client-credentials、并发刷新安全、429/5xx 有界重试”从开放差距改为开发环境已闭环；typed errors、pagination、managed WebSockets、.NET CI 与托管互操作继续保留为后续项。

后续 [`ICODER_SDK_TYPED_ERROR_PAGINATION_PHASE_SUMMARY_2026-08-23.md`](ICODER_SDK_TYPED_ERROR_PAGINATION_PHASE_SUMMARY_2026-08-23.md) 已补齐统一 PHI-safe API 错误、408 重试和 Agentic cursor 自动分页；最新回归为 JavaScript 63/63、Python 64/64。managed WebSocket、请求级选项、旧分页合同、.NET CI 与托管互操作仍开放。
