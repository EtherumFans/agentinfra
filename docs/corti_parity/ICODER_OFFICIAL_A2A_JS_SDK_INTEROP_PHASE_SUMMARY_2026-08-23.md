# 官方 A2A JavaScript SDK 包级互操作阶段总结（2026-08-23）

本阶段把 iCoDer AI SDK Adapter 从“与 Corti/A2A 结构相似”推进到使用官方稳定包的真实
互操作。审计基线为 `@a2a-js/sdk@1.0.1` 和公开的
`@corti/ai-sdk-adapter@0.4.0`；后者当前要求 `@a2a-js/sdk >=1.0.0`、
`@corti/sdk ^5`、`ai >=6`。iCoDer JavaScript `1.0.0-beta.26` 已使用官方
`ClientFactory`、ProtoJSON codec、JSON-RPC request-ID 校验和 SSE parser。

当前结论：**官方 A2A JavaScript SDK 与 iCoDer 本地真实服务的开发环境互操作缺口已关闭；
这不等于已通过 Corti 托管租户、生产网络或医院环境的双向验收。**

## 已完成

- `createA2AClientFactory()` 现在返回官方 `ClientFactory`，默认使用官方
  `DefaultAgentCardResolver` 和 `JsonRpcTransportFactory`；v0.3 compatibility 只用于
  Agent Card 明确声明旧协议时，v1.0 Card 使用稳定 v1 transport。
- `convertToParams()` 返回官方 `SendMessageRequest` 和 numeric `Role`，Part 使用官方
  protobuf oneof 内存表示；发送时由官方 codec 生成服务端接受的 `ROLE_USER`、`text/data`
  ProtoJSON，而不是 Adapter 手写 wire JSON。
- `toUIMessageStream()` 直接接受官方 `Client.sendMessageStream()` 返回值，处理
  `task`、`message`、`statusUpdate`、`artifactUpdate` oneof，输出 Vercel AI SDK 7 可消费的
  start/text/data/file/message-metadata/finish chunks。
- Corti Adapter 0.4.0 当前公开的泛型 UI message/data/metadata、ResponseMetadata、
  StreamCallbacks 和四个函数面已同步；JavaScript peer 范围收敛为
  `@a2a-js/sdk >=1 <2` 与 `ai >=6 <8`。
- 同源 fetch 继续覆盖调用方 Authorization、删除 Cookie/Proxy-Authorization、禁止 URL
  凭据和重定向、要求 HTTPS（回环开发例外）；官方 resolver/transport 的每次请求都经过
  该 fetch。
- UI file conversion 增加 10 MB 上限、MIME 一致性、URL userinfo 拒绝和 JSON UTF-8
  校验；iCoDer Agent Card 当前仍只声明受支持的 text/json 输入，服务端不支持的 raw/url
  Part 会继续返回 `CONTENT_TYPE_NOT_SUPPORTED`，没有暗中扩大文件处理能力。
- 集成 CI 现在安装 Node 22 与锁定的官方包，再运行后端 integration；固定 SQLite 文件的
  CHECK 测试已改为检查实际测试引擎，因此随机 SQLite 与 PostgreSQL CI 都不会被旧
  `data/test.db` 制造假失败。

## 真实端到端路径

隔离测试启动一个随机回环端口的真实 FastAPI A2A app，并从独立 Node 进程执行：

1. 官方 resolver 获取租户 Agent Card；
2. 官方 ClientFactory 选择 JSONRPC v1.0 interface；
3. blocking `SendMessage` 经过官方 ProtoJSON 序列化和响应反序列化；
4. `SendStreamingMessage` 创建持久 Task，官方 SSE parser 校验 JSON-RPC ID；
5. Adapter 消费 Task/status/artifact 事件，返回 Context/Task 可续跑 metadata 和 settled
   Vercel UI stream；
6. 服务器、Node 子进程和随机端口全部退出。

该路径不是 mock fetch。业务 Agent 使用确定性测试 handler，外部 LLM、Corti、外部 MCP
和临床 Provider 均未调用。

## 验证结果

| 验证 | 结果 |
|---|---:|
| 官方包 → 真实 iCoDer blocking + streaming E2E | 1/1，无告警 |
| A2A 单元/集成/API 扩大回归 | 331/331 |
| JavaScript SDK 全量（含 TypeScript build） | 50/50 |
| Python SDK 全量 | 51/51 |
| 三 SDK 发布候选一致性 | 5/5；统一 beta.26 |
| 静态部署预检 | 81/81 |
| npm 官方 registry audit | 0 vulnerabilities |

JavaScript dry pack 为 `@icoder/sdk@1.0.0-beta.26`，50 entries，shasum
`a49b5d099cde318ce85495a2c1d2d9ac259ac15f`，integrity
`sha512-3xbkfTE1hyDUGHJY6f7OimUsmFFaJ/lSbFwbB9c8u8pFEYjTrv745LGZquujJooy7NoGtXXObw8GorM3SG4fTg==`。
Python 临时 wheel 为 `icoder_sdk-1.0.0b26-py3-none-any.whl`，SHA-256
`99400a11f529d390b69dedf48c6a14f272e71e52b557a16f60c4cb1a40ac8860`。
两者均未发布。

所有后端/Python 测试显式清空 LLM Key、设置 mock、禁止外部 LLM 并禁用 Windows 原生
MedCodER。受保护数据库未写入，SHA-256 保持
`9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；8000/18022 未监听。

## 仍未完成/不得宣称

- 没有使用 Corti 已认证租户向 iCoDer 发起请求，也没有让 iCoDer 调用 Corti 托管 Agent；
  因而“官方 A2A 包互操作”不能扩大为“Corti 托管运行时互操作”。
- 没有把 `@corti/sdk` 当作 iCoDer 客户端替代品；两家认证、租户和产品 API 不应通过伪造
  nominal 类型混用。对标的是公开 Adapter 行为面和共同的官方 A2A 协议层。
- 本机没有 .NET SDK，beta.26 的 .NET 源码/测试合同未在本机编译；Linux CI 的
  net8.0/net10.0 job 仍是运行证据来源。
- 尚未完成 PostgreSQL 多 worker 恢复竞争、故障转移、容量/SLA、Corti 托管域、真实临床
  Provider、医院 SSO/MCP 授权、云 KMS/队列和医院网络验收。
- 本阶段没有重跑完整 5000 项后端基线；331 项是 A2A 扩大矩阵，不是全仓本轮通过。

机器可读证据：
[`phase_evidence.json`](../../reports/agent_hub/official_a2a_js_sdk_interop_phase_20260823/phase_evidence.json)。
