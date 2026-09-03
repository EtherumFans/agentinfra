# 受治理 Connector HTTP Transport 阶段总结（2026-08-22）

本阶段关闭了远程 `mcp` 与 `a2a` Connector 在开发环境中的生产形态 transport 缺口，并把执行器接入应用启动生命周期。结论限定为“开发切片通过”：没有调用真实 LLM、Corti 或外部 Connector，也没有通过云、医院、临床、法务、认证或独立 reviewer 门禁。

## Corti 当前公开合同

2026-08-22 复核 Corti 官方公开文档后，采用以下基线：

- [Connectors](https://docs.corti.ai/agentic/connectors)：五类 Connector 为 `registry`、`mcp`、`agent`、`a2a`、`schema`；远程 MCP 与 A2A 均是现行合同。
- [Connector authentication](https://docs.corti.ai/agentic/guides/connector-auth)：MCP 公开 `none`、bearer 与 OAuth2；Corti A2A 会转发调用方 bearer。
- [A2A protocol](https://docs.corti.ai/agentic/a2a-protocol)：只支持 A2A 1.0，覆盖 JSON-RPC 与 HTTP+JSON，以及 Send/Stream/Get/List/Cancel/Subscribe。
- [Core concepts](https://docs.corti.ai/agentic/core-concepts)：远程 Agent 由 Agent Card 声明认证、合规与协议能力。

## 本阶段完成

- MCP Streamable HTTP 完成 `initialize`、session、`notifications/initialized` 与 `tools/call`；session 按租户、Connector、版本隔离，凭据或版本变化不会复用旧 session。未实现的旧 SSE transport 不再对外宣称支持。
- A2A 1.0 完成 JSON-RPC 与 HTTP+JSON 双 binding、六类任务操作和有界 SSE 事件解析。
- 持久 A2A Connector 在业务调用前获取 Agent Card，校验规范化 JSON 的 SHA-256、协议版本、binding 和精确 endpoint；缓存仍按租户 Connector 版本与 digest 隔离。
- DNS 审核结果钉住到实际 TCP socket；TLS SNI 与 HTTP Host 保留原始主机名。禁止系统代理继承，避免 Clash 等本机代理绕过 Connector 出境策略。
- 默认拒绝 redirect；可选模式仅允许最多两次同源 307/308，并在每一跳重新校验。跨源跳转在 DNS 查询前拒绝。
- 对 URL、超时、状态码、解压后响应大小、JSON/SSE Content-Type 和 OAuth2 client-credentials token exchange 实施有界失败关闭；错误只返回稳定、脱敏的错误码。
- local 允许 SSRF 校验后的公网 HTTPS；cloud/CN 必须命中精确主机 allowlist。PHI/restricted 默认拒绝，显式 PHI 开关还必须命中更窄的 PHI allowlist。
- Connector 凭据只通过 CredentialVault 引用解析；启动健康信息不探测外网、不回显目标地址或密钥。
- JavaScript、Python、.NET 源码合同统一到 `1.0.0-beta.22`；JavaScript 与 Python 本地候选包已生成并校验，未发布。.NET 因本机没有 `dotnet`、`csc` 或 `msbuild`，只能记录源码合同，不能记为编译通过。

## 验证结果

所有后端数据库测试串行执行，避免共享 SQLite 并发污染：

| 范围 | 结果 |
|---|---:|
| Connector transport/runtime/schema/config/SSRF 单元与合同 | 128/128 |
| Connector executor/resource/graph 共享数据库集成 | 75/75 |
| 应用启动、runtime state、健康信息 E2E | 6/6 |
| JavaScript SDK | 41/41 |
| Python SDK | 48/48 |
| 前端 OpenAPI 合同 | 60/60 |
| 前端生产构建 | 通过，1,702 modules |
| OpenAPI 漂移 | 通过，258 paths，765,977 bytes |

安全用例覆盖真实的受治理 MCP 握手/session/call 和 A2A Agent Card/GetTask 路径，但远程端均由内存 MockTransport 与受控 resolver 代替，不构成外部互操作证明。机器证据见 [`phase_evidence.json`](../../reports/agent_hub/governed_connector_transport_phase_20260822/phase_evidence.json)，候选包清单见 [`LOCAL_RELEASE_MANIFEST_BETA22.json`](../../reports/release-candidate/LOCAL_RELEASE_MANIFEST_BETA22.json)。

## 与 Corti 的剩余差距

- `registry` 与内部 `agent` Connector 的启动 adapter 已在后续 [`ICODER_LOCAL_REGISTRY_INTERNAL_AGENT_CONNECTOR_PHASE_SUMMARY_2026-08-22.md`](ICODER_LOCAL_REGISTRY_INTERNAL_AGENT_CONNECTOR_PHASE_SUMMARY_2026-08-22.md) 接线；PubMed/ClinicalTrials.gov 又在 [`ICODER_GOVERNED_PUBLIC_REGISTRY_PHASE_SUMMARY_2026-08-22.md`](ICODER_GOVERNED_PUBLIC_REGISTRY_PHASE_SUMMARY_2026-08-22.md) 进入受治理 Provider，其中 ClinicalTrials.gov 单次实网最小验证通过。当前剩余为 PubMed 合规联系邮箱后的实网验证、三个许可/隐私 Provider、持久语义 Memory 身份合同、delegated scope 和分布式状态。
- Corti A2A 自动转发调用方 bearer；iCoDer 有意不直接转发入站 token，而要求绑定独立 Connector 凭据。若要协议等价，需要设计显式、最小 scope、可审计的 delegated-token 合同，不能降低隔离边界。
- CredentialVault 现阶段仍以统一引用和环境/KMS ingress 抽象为主，尚无已验证的 HashiCorp、阿里云、腾讯云或 AWS Secret Manager provider adapter/轮换实测。
- 熔断、并发和 session 状态仍是进程内实现，尚未完成 Redis/多 worker 一致性和故障恢复验证。
- 尚未对 Corti 托管运行时或独立真实 MCP/A2A 服务做互操作；本阶段也未验证代理网络可达性。Connector transport 主动忽略操作系统代理是安全设计，不是连通性证明。
- .NET 未编译；PostgreSQL、Redis、Docker/Linux、云与医院环境仍是外部门禁。

## 下一开发优先级

后续已完成本地 `registry`/内部 `agent` 启动 adapter 和 PubMed/ClinicalTrials.gov 公共 Provider。下一 P0 转为持久 Memory 身份/retention、delegated scope、分布式 Connector 控制面和原生 MedCodER Worker E2E；PubMed 实网复测等待合规运营联系邮箱。26-Agent 真实模型质量矩阵需要单独的密钥、预算和数据授权；国家/地区/医院规则、合法许可和临床质量不能由开发测试替代。
