# A2A 1.0 Agent Card 与条件/并行 Connector Graph 阶段总结（2026-08-22）

本阶段关闭两个可在当前开发环境完成的缺口：标准/动态 A2A 1.0 Agent Card，以及服务端
Connector Graph 的确定性条件和依赖层有界并行执行。实现对照 A2A 官方
[规范](https://github.com/a2aproject/A2A/blob/main/docs/specification.md)与
[Proto](https://github.com/a2aproject/A2A/blob/main/specification/a2a.proto)，并保持 Corti 当前
Agentic Connector/SDK composition 的边界：本地协议和编排合同完成，不把它表述成 Corti
托管运行时、生产网络或临床质量等价。

## 已完成

- 新增公开 `GET /.well-known/agent-card.json`，只发布默认官方 Agent；返回
  `application/a2a+json`、`A2A-Version: 1.0`、ETag 和公共缓存合同。
- 新增认证租户路径
  `GET /api/v2/agentic/agents/{agent_id}/.well-known/agent-card.json`；官方 Agent 和租户内
  自定义 Agent 均动态投影，跨租户、未知、归档或未启用 A2A 的 Agent 统一不可见。
- Card 声明准确的 `JSONRPC` 与 `HTTP+JSON` 1.0 接口、MIME modes、capabilities、skills 和
  bearer security；不投影 system prompt、Connector ID、凭据或内部 metadata。
- Cloud 使用受校验的 `ICODER_HOSTED_URL`，不信任请求 Host 生成公开 URL；含用户信息、查询或
  fragment 的配置失败关闭。
- Connector Graph 新增 `exists|equals|not_equals|in` 条件。条件只能读取已经脱敏的结构化
  标量，不能检查自由文本、对象/数组或执行表达式。
- Graph 支持 `sequential|parallel` 和 `max_concurrency=1..8`。并行模式按 DAG 依赖层执行，
  每个节点使用独立会话和审计事务，结果恢复为图声明顺序；必需节点失败仍在 Provider 前失败关闭。
- JavaScript、Python、.NET SDK 源码合同同步 Agent Card 和 Graph 类型，版本统一为
  `1.0.0-beta.21`（Python 为 `1.0.0b21`）。候选制品只在本地生成，未发布。

## 验证结果

所有自动测试均清空 `ICODER_CREDENTIAL_LLM`、使用 mock Provider、关闭外部 LLM 并禁用原生
MedCodER；本阶段没有读取、打印或调用用户提供的真实密钥。

| 验证 | 结果 |
|---|---:|
| Agent Card、Graph Schema/运行时单元合同 | 44/44 |
| A2A/OpenAPI 运行时、根目录调用与导出一致性 | 7/7 |
| 完整 A2A endpoint 套件 | 43/43 |
| 完整 Connector Graph A2A 集成 | 15/15 |
| 最终顺序修复后并行 + 动态 Card 定向集成 | 2/2 |
| JavaScript SDK + TypeScript build | 41/41 |
| Python SDK | 48/48 |
| 前端 OpenAPI 路径合同 | 60/60 |
| 三 SDK 版本/发布门 | 5/5；统一 `1.0.0-beta.21` |
| OpenAPI | 258 paths、764,797 bytes、快照无漂移 |
| 本地候选制品 | JS tgz + Python wheel/sdist；3 个 SHA-256；未发布 |

真实并行集成不是仅检查配置字段：两个独立 Connector 节点通过 barrier 证明适配器调用发生
重叠，随后验证两条成功 `ConnectorExecutionAudit`。条件/顺序组合另由单元测试证明跳过节点
不发送未选择输入且结果仍按声明顺序返回。

候选清单：
[`LOCAL_RELEASE_MANIFEST_BETA21.json`](../../reports/release-candidate/LOCAL_RELEASE_MANIFEST_BETA21.json)。
机器可读阶段证据：
[`phase_evidence.json`](../../reports/agent_hub/a2a_agent_card_parallel_graph_phase_20260822/phase_evidence.json)。

## 尚存差距

- 本地 Connector adapter 仍不是生产 OAuth/credential transport；socket IP 钉住、逐跳 redirect
  复验、分布式熔断/并发和多副本控制面未完成。
- Windows 本机没有 `dotnet`、`csc` 或 `msbuild`；.NET Agent Card 源码与测试合同已更新，但
  不能记为编译通过，必须由 Linux/Windows CI 验证双目标框架。
- 本阶段不需要真实 LLM，因此未重复消耗 DeepSeek；此前真实 Run 只能证明单个合成最小链路，
  不能外推 26-Agent 临床质量。
- 受治理 ICD 检索、26-Agent 真实模型矩阵、Corti 同病例盲评、生产队列/PostgreSQL 多副本、
  医院互操作、合法中国编码资产、法务/等保/认证和独立临床 reviewer 仍未通过。
