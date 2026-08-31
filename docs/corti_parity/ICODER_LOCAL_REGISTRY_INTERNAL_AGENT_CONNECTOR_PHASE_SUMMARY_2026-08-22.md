# 本地 Registry 与内部 Agent Connector 阶段总结（2026-08-22）

本阶段把五类 Connector 中剩余的 `registry` 和内部 `agent` 从“executor 预留注入点”接入应用启动 runtime。结论限定为开发切片通过：未使用真实 LLM 密钥、未访问外部 registry provider，真实云、医院、临床、法务和认证门禁仍未通过。

## 完成内容

- 新增上下文化 adapter 合同，使适配器获得租户、源 Agent、Connector、Run、Task 和数据用途，而不是沿用缺少身份信息的三参数旧函数。
- 启动 runtime 绑定受治理 registry adapter。当前可执行的本地 key 为：
  - `medical-calculator`：六个确定性计算器，输出强制标记非权威并要求持证临床人员复核；
  - `medical-coding`：复用现有 MCP 单一工具注册表、输入/输出 JSON Schema 和 PHI 再脱敏边界；当前允许无 delegated scope 的 ICD 检索/校验类操作；
  - `interviewing`：有界问题集、状态序列化、推进和 transcript；禁止可执行表达式或调用方 predicate；
  - `memory`：有界、非持久的线程内 lexical retrieval，明确不声称语义 RAG 等价。
- `clinical-trials`、`drugbank`、`posos`、`pubmed`、`web-search` 不再落入“adapter 未配置”模糊错误，而是稳定失败关闭为外部 provider 不可用；不会返回旧 stub 的空结果冒充成功。
- 启用 registry/agent Connector 必须显式配置 capability allowlist；启用 MCP 必须配置 tool allowlist。重复或非法操作名在配置/执行边界拒绝。
- 内部 Agent adapter 通过现有 Provider A2A handler 执行租户目标 Agent，创建独立 child Run、沿用父 trace、保留结果签名与人工复核标记。
- 内部委派仅允许 `run`、`delegate`、`SendMessage`；运行时再次校验目标租户，最大深度 8，并通过 context-local 调用链阻断递归环。
- 调用方不能伪造 `_dependencies` 等服务端通道；只有 Connector Graph 标记的可信 channel 可进入 adapter，并在传给目标 Agent 前改写为普通 `connector_dependencies`。
- 修复云配置边界：显式注入空 `ICODER_SECRET_KEY` 现在会覆盖本地 `.env` 并拒绝启动，不再自动生成随机值后误过云模式校验。

## 验证结果

| 范围 | 结果 |
|---|---:|
| 扩大单元/安全/合同/Corti parity | 188/188 |
| 共享数据库串行集成 | 76/76 |
| 应用启动与健康信息 E2E | 6/6 |
| JavaScript SDK `beta.22` | 41/41 |
| Python SDK `b22` | 48/48 |
| OpenAPI 漂移 | 通过，258 paths，765,977 bytes |
| 变更运行时 `compileall` | 通过 |

串行集成包含真实 ConnectorExecutor、数据库资源、审计、实际本地 BMI registry 调用，以及内部 `claim-check` Agent 的 child Run、输出投影和结果签名。Agent provider 为测试注入的确定性 Provider，不是外部 LLM，因此它证明运行链和失败边界，不证明模型质量。机器证据见 [`phase_evidence.json`](../../reports/agent_hub/local_registry_internal_agent_phase_20260822/phase_evidence.json)。

## 与 Corti 的剩余差距

- 后续 [`ICODER_GOVERNED_PUBLIC_REGISTRY_PHASE_SUMMARY_2026-08-22.md`](ICODER_GOVERNED_PUBLIC_REGISTRY_PHASE_SUMMARY_2026-08-22.md) 已为 PubMed/ClinicalTrials.gov 接入固定官方主机、DNS-to-socket pin、响应上限和去标识化查询。ClinicalTrials.gov 单次无患者数据实网最小验证通过；PubMed 仍等待合规运营联系邮箱后的实网验证。DrugBank/POSOS 必须先有合法许可证和服务合同；web search 还需要双重 opt-in 与隐私供应商。
- `memory` 当前 registry path 只有 thread-local lexical retrieval。项目另有租户加密的持久 Memory 服务和可选本地 embedding，但 Connector 缺少权威 actor/retention 同意字段，不能在未设计身份合同前直接接入。
- `medical-coding` 中声明 `required_scopes` 的 Agent-backed MCP 操作仍默认拒绝；需要机器凭据 delegated scope，而不能复用或扩大用户入站 token。
- 内部 Agent 实际真实模型质量、本地多 Agent 成本和延迟矩阵尚未执行；本阶段没有使用用户曾提供的真实 Key。
- recursion/circuit/concurrency/session 仍为进程内状态，Redis/多 worker 一致性和恢复未验证。
- Agent Hub 尚无 Connector 管理前端；当前有 API、OpenAPI 和 SDK 合同，但不等于 Corti Console 交互等价。

## 下一开发优先级

公共 Registry transport 已在后续阶段完成。下一项可在开发环境完成的 P0 是：为持久 Memory 增加 actor、用途、同意和 retention 合同；设计最小 delegated machine scope。受治理 ICD 检索已能经本地 `medical-coding` registry 调用，但原生 MedCodER Worker/索引服务的独立进程 E2E 仍需继续闭环。
