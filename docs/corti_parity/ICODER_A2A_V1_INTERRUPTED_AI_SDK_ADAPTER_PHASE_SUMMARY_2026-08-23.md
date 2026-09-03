# A2A v1 中断续跑与 AI SDK Adapter 阶段总结（2026-08-23）

本阶段关闭了两个可在开发环境完成的 Corti 对标缺口：A2A v1 的中断/拒绝 Task
语义，以及 JavaScript Vercel AI SDK Adapter。实现保持既有租户、Agent、Context、
Task、加密存储和审计边界，没有为续跑或前端流式响应建立旁路。

当前结论：**A2A v1 中断 Task 续跑与 JavaScript AI SDK Adapter 已达到开发环境上线候选；
这不等于已经证明与 Corti 托管包、生产队列、真实临床 Provider 或医院环境完全互操作。**

## 已完成

- A2A Task 状态补齐 `rejected`、`input-required`、`auth-required`；`completed`、
  `failed`、`canceled`、`rejected` 为终态，输入/鉴权请求为可恢复中断态。
- 新增 Alembic `055`，将数据库 CHECK 扩为八状态；含历史约束反射兼容和降级保护，
  存在 v1-only 状态时拒绝破坏性降级。
- 同步与异步运行时均按处理器返回的精确状态持久化。中断 Task 保存加密提示、释放租约、
  不写 `completed_at`；下一条同租户、同 Agent、同 Task ID 消息通过状态 CAS 恢复
  `working`。终态 Task 不可恢复。
- `GetTask`、blocking send 和 Subscribe 均把中断态视为本轮已 settled；Task status
  message/history 可投影给客户端，artifact 只允许在 `completed` 返回。
- JavaScript、Python、.NET SDK 均增加 A2A v1 `taskId` 续跑参数和新状态；wait 在中断态
  返回，避免客户端无期限轮询。
- JavaScript `1.0.0-beta.25` 新增 Corti-compatible Adapter 子路径，公开
  `convertToParams`、`toUIMessageStream`、`createA2AClientFactory`、
  `createFetchImplementation`，并提供 Corti UI message、credential、status 和 stream
  option 类型。
- Adapter 仅从最后一条 assistant 消息恢复 context；只有最后状态为
  `input-required` 时携带 taskId；专家凭据只允许首轮发送，并进行数量、重复、长度和
  bearer/OAuth2 类型校验。
- Adapter fetch 强制 SDK 同源、覆盖 Authorization 与 A2A version、删除 Cookie 和代理
  Authorization、禁止重定向；UI stream 错误只返回稳定通用信息，不泄漏上游响应。
- Adapter 已用正式 `ai@7.0.77` 类型编译，并由真实
  `createUIMessageStreamResponse` 完整消费 start/text/data/status/finish 流。

## 验证结果

所有本阶段 Python/后端验证均显式清空 `ICODER_CREDENTIAL_LLM` 和
`DEEPSEEK_API_KEY`，设置 `LLM_PROVIDER=mock`，禁止外部 LLM，并禁用 Windows 原生
MedCodER。没有使用用户提供的密钥，没有调用 Corti 或外部临床 Provider。

| 验证 | 结果 |
|---|---:|
| A2A 单元/集成/API 扩大回归 | 329 passed，1 skipped |
| A2A 状态与协议专项 | 31/31 |
| 中断 Task 持久化/续跑专项 | 6/6 |
| Alembic fresh/roundtrip/八状态专项 | 3/3 |
| JavaScript SDK 全量（含 TypeScript build） | 50/50 |
| JavaScript 正式 AI v7 response 消费 | 1/1（包含于 50） |
| Python SDK 全量 | 51/51 |
| 静态部署预检 | 81/81 |
| npm 官方 registry audit | 0 vulnerabilities |

JavaScript dry pack 为 `@icoder/sdk@1.0.0-beta.25`，shasum
`53e5717c90c1a53d275282f37677c94a87ab0d70`；Python 临时 wheel 为
`icoder_sdk-1.0.0b25-py3-none-any.whl`，SHA-256
`29bcb53908014435ae1b3799d356af6a122752765bb8f2a6119260540a4c8bc0`。
两者均未发布。

受保护开发库未迁移或写入，SHA-256 保持
`9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；独立后端未启动，
8000/18022 均未监听。

.NET 源码、测试合同和 CI 双框架配置已同步，但本机没有 `dotnet`、`csc` 或
`msbuild`，因此 **没有** 将 .NET 记为编译或测试通过。

## 与 Corti 的当前差距

- 尚未用 Corti 已认证租户和官方包完成双向 package-level 互操作；本阶段对标依据是
  Corti 当前公开 Adapter/A2A 文档与 A2A v1 规范。
- `createA2AClientFactory` 已实现相同公开职责和安全边界，但尚未证明与 Corti 内部实现或
  `@a2a-js/sdk` 的全部边界行为逐字节一致。
- 尚无 PostgreSQL 多 worker 抢租约/续跑竞争、进程故障转移和容量实压；当前证据主要是
  SQLite 隔离测试、状态 CAS 和静态部署合同。
- 尚未实测医院 SSO/鉴权挑战、真实 MCP 外部授权、Provider 原生首 token、费用中止语义、
  真实 DeepSeek 临床质量、云 KMS/队列或医院网络。
- 本阶段未重跑 5000 项全仓后端基线；329 项是扩大后的 A2A 相关回归，不应扩大表述为全仓
  本轮通过。

机器可读证据：
[`phase_evidence.json`](../../reports/agent_hub/a2a_v1_ai_sdk_adapter_phase_20260823/phase_evidence.json)。

