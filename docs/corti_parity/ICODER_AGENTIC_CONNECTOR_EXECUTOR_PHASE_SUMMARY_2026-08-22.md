# Agentic v2 Connector 执行层阶段总结（2026-08-22）

> 后续状态：本文记录执行器初始切片。远程 MCP/A2A transport、DNS 到 socket 钉住、redirect 逐跳复验和 OAuth2 client-credentials 已在 [`ICODER_GOVERNED_CONNECTOR_TRANSPORT_PHASE_SUMMARY_2026-08-22.md`](ICODER_GOVERNED_CONNECTOR_TRANSPORT_PHASE_SUMMARY_2026-08-22.md) 完成开发环境闭环；云 Secret Manager provider、分布式控制面和外部互操作仍未验证。

本阶段在五类 Connector 持久资源之上完成了本地可执行、默认失败关闭的统一执行器。
没有调用真实 LLM、Corti 或外部 Connector。当前结论是“本地执行引擎完成、产品运行时接线
仍部分”，不能扩大为生产 MCP/A2A transport 或 Corti 托管服务等价。

## 已完成

- `ConnectorExecutor` 统一调度 `registry`、`mcp`、`agent`、`a2a`、`schema`；transport、
  credential、registry、Agent 和 data-policy 全部是显式 adapter。
- Registry/MCP/A2A 没有 data-policy authorizer 时拒绝；MCP/A2A 没有 transport 时拒绝；
  认证策略需要凭据但没有 resolver 时拒绝。启用资源不再等于允许出网或传输患者数据。
- 每次执行重新按租户、源 Agent、Connector id、enabled/tombstone 加载，并重新执行配置、
  URL、DNS/SSRF、CN 出境和目标 Agent 租户校验。
- MCP tool allowlist、A2A operation allowlist、Registry/Agent capability allowlist、Schema
  input/output validation 均失败关闭。
- invocation 64 KiB、response 1 MiB 上限；每 Connector 并发 1–32、total timeout、
  idempotent retry 1–3 和 circuit breaker；非幂等调用固定单次。
- `connector_execution_audit` 记录成功、失败、拒绝、耗时、重试次数、HTTP 类别和稳定错误码；
  不记录 arguments、output、header、credential reference 或异常原文。
- operation、run/task/span id、adapter error code 和 HTTP status class 全部限制为结构化标识，
  自由文本无法借审计字段落库。

## 验证

- 纯本地 mock executor E2E：10/10；覆盖五类型快乐路径、凭据 adapter 不泄漏、数据策略
  缺失、执行时 SSRF、target Agent 重验、超时、幂等重试、熔断、非幂等不重试、大小限制、
  Schema 失败、审计注入防护和并发上限。
- Connector 资源/执行/OpenAPI 专项：40/40。
- A2A v0.3/v1 + Connector + 既有 SSRF 联合回归：158/158；唯一警告为测试框架弃用提示。
- OpenAPI：251 paths，漂移检查通过；新增 timeout/retry/response/concurrency 类型约束。

## 尚未完成

- Agent Planner/运行时尚未根据持久 Connector 图选择并调用执行器；目前是可复用执行服务，
  不是新增一个不属于 Corti 合同的公开直调端点。
- 生产 MCP handshake/A2A transport、DNS 校验 IP 到 socket 的钉住、redirect 逐跳复验；
- Vault/KMS provider adapter、OAuth2 client-credentials token exchange/rotation；
- 跨 worker 的持久熔断、分布式并发/速率限制；
- 三语言 Connector SDK、PostgreSQL/Redis/Docker Linux 与受控外网验证。

后续受控 graph 接线已完成于
[`ICODER_AGENTIC_CONNECTOR_GRAPH_RUNTIME_PHASE_SUMMARY_2026-08-22.md`](ICODER_AGENTIC_CONNECTOR_GRAPH_RUNTIME_PHASE_SUMMARY_2026-08-22.md)。
当前剩余重点已转为专用/A2A/异步入口共享、条件/并行 Planner、生产 adapter 与 Task Subscribe/
持久事件；仍须避免在这台 Windows 主机上引入未隔离的外网和原生崩溃风险。

机器可读证据：[`phase_evidence.json`](../../reports/agent_hub/connector_executor_phase_20260822/phase_evidence.json)。
