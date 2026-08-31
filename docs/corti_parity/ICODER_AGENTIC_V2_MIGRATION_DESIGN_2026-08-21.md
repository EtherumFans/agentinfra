# iCoDer Agentic v2 兼容迁移设计（2026-08-21）

> 状态：设计基线 + Phase A/C/D/E/F 本地实现切片。A2A v1.0 canonical adapter、双 binding 的 Send/Stream/Get/List/Cancel、持久 `returnImmediately` Task、Subscribe/恢复、标准/租户动态 Agent Card、租户/Agent 隔离和签名游标已实现；五类 connector 的 `044` 持久资源、默认失败关闭执行器以及统一 Run/全部直接 A2A 的入口 graph 已完成，graph 支持结构化条件和依赖层有界并行。现行 Corti 契约的单数 `/trace`、统一 Task feedback、按 Agent usage 和自动评估专用机器 scope 已完成；TypeScript/Python SDK composition 也已覆盖。生产 transport/provider adapter、分布式控制面、独立训练授权与 .NET 本机编译仍未完成。

## 1. 目标与边界

本阶段的目标是以 Corti 当前公开的 Agentic v2 合同为外部对照，在不破坏 iCoDer
现有 A2A v0.3 客户端的前提下，补齐以下开发环境工程面：

1. A2A v1.0 的 JSON-RPC 与 HTTP+JSON 双绑定；
2. Send、Stream、Get、List、Cancel、Subscribe 完整任务生命周期；
3. `registry`、`mcp`、`agent`、`a2a`、`schema` 五类 connector；
4. context 一级资源、context task 集合与 OpenInference trace export；
5. task/message feedback 与按 Agent 用量归集；
6. JavaScript、Python、.NET SDK、OpenAPI 和端到端负向安全矩阵。

本文不声称复刻 Corti 私有实现、模型质量、临床准确率、托管模型池、计费、SLA 或
医院生产能力。公开依据为 Corti 的 [Connectors](https://docs.corti.ai/agentic/connectors)、
[A2A protocol](https://docs.corti.ai/agentic/a2a-protocol)、
[Context and memory](https://docs.corti.ai/agentic/context-memory)、
[OpenInference trace export](https://docs.corti.ai/agentic/guides/export-traces) 和
[Task/message feedback](https://docs.corti.ai/agentic/guides/submit-feedback)。

## 2. 当前可复用资产与明确缺口

### 2026-08-21 Phase A 实施快照

- 新增 `/api/v2/agentic/agents/{agent_id}` 下 7 个 v1 路径，OpenAPI 总计 248 paths；
- v1 使用 `A2A-Version: 1.0`、PascalCase JSON-RPC method、ProtoJSON `ROLE_*`/
  `TASK_STATE_*` 和 google.rpc error details；旧 v0.3 路由及 header 保持不变；
- Send 支持 v1 text/data part、taskId→context 安全推断和 referenceTaskIds 租户/Agent 校验；
- 不支持的 raw/url、`returnImmediately`、push notification config、未知字段和非声明 tenant
  均明确失败关闭，不静默忽略；
- Task Get/List/Cancel 同时支持 JSON-RPC 和 HTTP+JSON；List 使用绑定租户、Agent 与查询条件的
  HMAC pageToken，Cancel 使用条件更新防止状态竞态；
- 新旧协议/OpenAPI 联合离线回归 87/87；未配置或调用真实 LLM；
- 尚未实现 Subscribe/持久事件、标准 `/.well-known/agent-card.json`、三 SDK 和异步
  `returnImmediately`，因此不得声称 A2A v1.0 完成。

| 资产 | 当前实现 | 迁移判断 |
|---|---|---|
| Agent | `agents` 已有租户、专家绑定、配置、版本、状态、canonical key、agent type | 复用主表；connector 不继续塞进 `config` JSON |
| A2A | 严格 v0.3；JSON-RPC；Send/Stream/Get/Cancel；缺失版本直接 400 | 保留兼容面，新增独立 v1 adapter；禁止原路由静默变义 |
| Agent Card | `/.well-known/agent.json` 和单 Agent card | 保留旧发现；新增 v1 `/.well-known/agent-card.json` |
| Context | `contexts`、message/task/artifact refs；过期时间、脱敏标记和租户范围 | 复用；补任务分页、trace 投影和稳定顺序 |
| Task | 持久 `context_task_refs`，状态机和租户 join 查询 | 复用状态机；补 List/Subscribe、历史、artifact 和 run/trace 关联 |
| RunTrace | DB 持久事件、稳定 `event_id`、`sequence_number`、`trace_id`，写入前 secret scan | 作为 OpenInference 只读来源；不直接暴露内部 JSON |
| Usage | `/api/usage/by-agent` 有成本、次数、平均延迟 | 复用聚合逻辑；补 v2 时间粒度、游标、租户/项目维度 |
| Expert/MCP | Expert 有 schema/capability/provenance；MCP Server 有 URL 和认证类型 | Expert 可供 registry connector 引用；现 MCP 明文 `auth_header` 不得沿用到 v2 |
| MCP client | 仅固定 PubMed/ClinicalTrials 适配，通用安全边界不足 | 只复用业务适配器；网络、凭据和策略层重建 |

关键结论：现有底座足以避免重写 Agent 运行时，但不能通过改路由名或改响应头把 v0.3
冒充 v1.0。尤其是 connector secret、通用外部 URL、任务订阅和 OpenInference 都需要
新的持久模型与安全门。

## 3. 目标 API 表面

建议将 Corti 兼容面统一放在 `/api/v2/agentic`，现有 `/api/icoder` 与
`/api/rest/v1/agent_definitions` 在兼容期继续服务。

### 3.1 Agent 与 Agent Card

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v2/agentic/agents` | 租户内 Agent 集合，游标分页 |
| POST | `/api/v2/agentic/agents` | 创建 Agent；connector 仅通过引用绑定 |
| GET/PATCH/DELETE | `/api/v2/agentic/agents/{agent_id}` | 读取、局部更新、归档/删除 |
| GET | `/.well-known/agent-card.json` | 默认或显式 host 对应的 v1 card |
| GET | `/api/v2/agentic/agents/{agent_id}/agent-card` | 租户可见的单 Agent card |

Agent Card 必须公开支持的 binding、skills、认证要求和 endpoint，不得宣称未启用的
Subscribe 或 connector 能力。跨租户 Agent 应表现为 404，而不是 403，以避免枚举。

### 3.2 A2A JSON-RPC binding

`POST /api/v2/agentic/agents/{agent_id}/a2a`

该单端点接收 JSON-RPC 2.0，并按 A2A v1.0 method 分派 Send、Stream、Get、List、
Cancel、Subscribe。响应使用 `A2A-Version: 1.0`；旧的
`A2A-Protocol-Version: 0.3` 只在旧路由返回。

### 3.3 A2A HTTP+JSON binding

| 方法 | 路径 | 操作 |
|---|---|---|
| POST | `/api/v2/agentic/agents/{agent_id}/message:send` | Send |
| POST | `/api/v2/agentic/agents/{agent_id}/message:stream` | Stream，SSE |
| GET | `/api/v2/agentic/tasks` | List，支持 `contextId`、`agentId` 和游标 |
| GET | `/api/v2/agentic/tasks/{task_id}` | Get |
| POST | `/api/v2/agentic/tasks/{task_id}:cancel` | Cancel |
| GET | `/api/v2/agentic/tasks/{task_id}:subscribe` | Subscribe，SSE 与恢复 |

两个 binding 必须调用同一应用服务和同一 canonical DTO，不能维护两套状态机。HTTP 状态、
A2A error code、JSON-RPC error 和 SSE terminal event 应由一张映射表生成。

### 3.4 Context、trace、feedback 与 usage

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/DELETE | `/api/v2/agentic/contexts/{context_id}` | 读取或删除上下文 |
| GET | `/api/v2/agentic/contexts/{context_id}/tasks` | context 下任务集合，游标分页 |
| GET | `/api/v2/agentic/contexts/{context_id}/trace` | 脱敏 OpenInference 投影；`pageSize/pageToken` |
| POST/GET/DELETE | `/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/feedback` | 调用方隔离的统一 Task feedback；消息目标放在 `target.messageId`；DELETE 删除调用方在该 Task 下的全部反馈 |
| GET | `/api/v2/agentic/agents/{agent_id}/usage` | 按可见 Agent、时间和粒度聚合；`from` inclusive、`to` exclusive，当前响应固定日粒度 |

DELETE context 延续现有级联/清理语义，但必须记录审计，并明确 trace/feedback 是否依据各自
retention 独立保留。默认不得为了导出 trace 恢复已删除的患者正文。

## 4. A2A v0.3 → v1.0 兼容策略

### 4.1 内部 canonical 层

新增协议无关的内部对象：`CanonicalMessage`、`CanonicalTask`、`CanonicalArtifact`、
`CanonicalTaskEvent` 和 `CanonicalError`。v0.3 adapter、v1 JSON-RPC adapter 与 v1
HTTP adapter 只负责解析、验证和序列化，运行时只接收 canonical 对象。

### 4.2 版本策略

- 旧路由继续严格要求 `A2A-Protocol-Version: 0.3`，不改变现有行为。
- v1 路由严格使用 `A2A-Version: 1.0`；不接受 `0.3`，也不把缺失版本解释为 v0.3。
- HTTP+JSON binding 的版本缺失规则按最终锁定的公开合同实现；未锁定前应失败关闭。
- 服务端只在 Agent Card 中声明实际启用的版本和 binding。
- 兼容期至少覆盖三 SDK 一个完整发布周期；下线条件是 v0.3 使用量为零、迁移指南发布、
  回滚演练通过且用户得到通知。

### 4.3 幂等与并发

- Send/Cancel 使用租户内唯一 idempotency key；同 key 同 payload 重放返回同结果。
- 同 key 不同 payload 返回 409，不重复调用 Provider、不重复计费。
- Task 状态更新使用版本号或条件更新，禁止 canceled 后被迟到结果改回 completed。
- List 固定按 `(created_at, task_id)` 或单调序号分页，游标带签名并绑定租户与过滤条件。
- Subscribe 以 RunTrace 稳定 `event_id`/`sequence_number` 为恢复点；未知、过期或跨任务
  `Last-Event-ID` 必须明确报错，不能从任意位置泄露事件。

## 5. Connector 资源模型

### 5.1 建议表

`agent_connectors`

| 字段 | 约束 |
|---|---|
| `id` | 服务端生成的 opaque string（当前实现 UUIDv4），主键 |
| `organization_id` | 必填、索引、所有读写首要过滤条件 |
| `agent_id` | 必填 FK；与 connector 同租户 |
| `type` | `registry|mcp|agent|a2a|schema`，创建后不可变 |
| `name`/`description` | 长度限制，display-only |
| `enabled` | 默认 false；验证通过后显式启用 |
| `config_json` | 类型化、限深/限大小、无 secret 的规范化配置 |
| `credential_ref` | 可空；只保存 vault/KMS 引用，不保存 secret |
| `target_agent_id` | `agent` 类型可用；强制同租户 |
| `normalized_url` | `mcp`/`a2a` 可用；入库和每次连接前重新验证 |
| `schema_ref`/`schema_digest` | `schema` 类型；内容寻址，防止无审计漂移 |
| `version` | 乐观锁 |
| `created_by`/`created_at`/`updated_at` | 审计字段 |

`connector_credentials`

- 保存 `organization_id`、provider、vault/KMS secret id、版本、状态、轮换时间、创建人；
- API 只返回存在性、类型、末次轮换和指纹，永不返回原值；
- 日志、trace、异常、数据库 dump、OpenAPI example 和 SDK `toString` 均不得出现 secret；
- 禁止沿用 `mcp_servers.auth_header` 的明文模式。旧数据迁移应先导入 secret store，验证后
  清空明文；任一步失败均保持 connector disabled。

`connector_execution_audit`

- 记录 connector、task、run、tenant、动作、策略决定、状态、耗时、重试次数、HTTP 类别、
  脱敏错误码与 trace span id；
- 不记录 Authorization、OAuth token、患者原文或完整第三方响应。

### 5.2 五类校验

| 类型 | 必需配置 | 关键约束 |
|---|---|---|
| `registry` | registry key、版本/能力 | 只允许服务端登记项；许可证和区域策略失败关闭 |
| `mcp` | HTTPS URL、transport、auth policy | MCP handshake、tool allowlist、SSRF/出境门禁、schema 限制 |
| `agent` | `target_agent_id`、允许能力 | 同租户、禁止自环；用有界 DFS 拒绝循环和过深 fan-out |
| `a2a` | HTTPS endpoint、agent card digest、auth policy | 远端 card 固定/刷新策略、版本/binding 交集、目标租户策略 |
| `schema` | 输入/输出 schema 或引用 | JSON Schema 方言白名单、限深/限节点/限正则、摘要固定 |

## 6. 安全与中国场景边界

### 6.1 租户、权限和凭据

- 所有 Agent、connector、task、context、message、trace、feedback 查询都必须以
  `organization_id` 为第一过滤条件；跨租户引用按 404 处理。
- connector CRUD、credential bind/rotate、trace export、feedback delete 分离 scope；
  不能用普通 Agent run 权限读取凭据元数据。
- `inherit` 认证默认禁止跨租户和公网转发用户 bearer；推荐显式 token-exchange 或
  connector 专用凭据。只有经过审批的同信任域目标可启用 bearer forwarding。
- secret redaction 同时覆盖结构化 key、Authorization 字符串、JWT/高熵 token 和异常链。

### 6.2 SSRF、DNS 重绑定与出境

- 只允许 `https`；禁止 userinfo、fragment、非规范端口和重定向到未验证 host。
- URL 保存前和每次连接前分别解析；解析后的所有 A/AAAA 地址均须通过 IP 策略。
- 拒绝 loopback、link-local、RFC1918、CGNAT、metadata、multicast、unspecified 和保留地址，
  除非 connector 明确属于经批准的院内部署 profile。
- 连接必须钉住已校验的目标地址/证书主机名，防 DNS rebinding；每次 redirect 重新校验。
- CN profile 继续默认拒绝未批准出境；目标域、数据类别、区域、法务依据和审批版本纳入
  policy decision 与审计，connector enabled 不代表允许传输患者数据。

### 6.3 资源限制与失败关闭

- 请求体、消息 parts、artifact、schema、tool count、fan-out、递归深度、响应大小均设硬上限；
- 每 connector 有 connect/read/total timeout、并发、速率、重试预算和 circuit breaker；
- 非幂等请求默认不重试；重试不得绕过预算或产生重复结算；
- schema bomb、压缩炸弹、无限 SSE、未知 content type 和超大错误正文提前截断；
- 下游不可用时 Task 明确 failed/incomplete，并保留人工复核信号，不以空成功降级。

## 7. Task、Context 与订阅持久化

现有 `context_task_refs` 只保存最小状态和时间。建议新增独立 `agentic_tasks` 作为 v1
权威表，并在兼容期通过同一事务维护旧 ref；或先以不破坏旧主键的增量列扩展。最终应具备：

- `organization_id`、`agent_id`、`context_id`、`task_id`；
- state、state version、created/started/completed/canceled timestamps；
- run_id、trace_id、request digest、idempotency key；
- last event sequence、result/artifact references、error code、manual-review flag；
- retention class 和 tombstone，不保存无需保留的患者原文。

`task_events` 使用 `(task_id, sequence_number)` 唯一约束和稳定 event id，写 task 状态与
terminal event 必须同事务提交。Subscribe 先重放持久事件，再切到实时流；重连不能漏掉
提交窗口内的事件。SSE 至少包含 `id`、`event`、`data`，心跳不推进业务序号。

## 8. OpenInference 脱敏投影

OpenInference export 是 RunTrace 的只读投影，不是把 `safe_metadata_json` 原样返回。

### 8.1 映射

| iCoDer 来源 | OpenInference 输出 |
|---|---|
| `trace_id` | trace id；与 task/context 关系可验证 |
| `event_id`/`sequence_number` | span/event stable id 与分页顺序 |
| step/status/duration | span name、status、start/end/duration |
| agent/tool/connector id | 受权限控制的 span attributes |
| token/cost/model metadata | 仅允许数值和已批准标识 |
| tool/connector 调度 | tool/connector span，参数与结果默认摘要/哈希 |

### 8.2 默认禁止导出

- 原始 prompt、患者文本、录音、完整模型输出、tool 原始参数/响应；
- Authorization、API key、OAuth token、cookie、credential ref；
- 内部异常堆栈、数据库主机、文件系统路径和策略敏感细节；
- 未经批准的第三方标识和可逆患者标识。

导出接口使用签名游标、固定最大页、时间范围上限和独立 `trace:export` scope。若未来允许
受控正文，必须由单独的高权限、保留策略、用途声明和审计开启，不能作为默认参数。

## 9. Feedback 模型

已实现统一 `agent_task_feedback` 表：

- `id`、`organization_id`、`context_id`、`task_id`，可选 `message_id`；
- 当前仅接受 Corti 已开放的 `binary` 0/1；最多五个现行白名单 label，`other` 强制 reason；
- reason 先过 PHI redaction 再按现有 key lifecycle 加密；metadata 只接受固定字段，外部 actor/client reference 仅保存 SHA-256；
- `actor_type/actor_id/target_key` 构成调用方/目标唯一边界，重复 POST 幂等更新，并发由数据库唯一约束收敛；
- GET 只返回当前调用方、按新到旧排序；DELETE 幂等软删除该调用方在 Task 下的全部反馈；
- `metadata.collectionMethod=automatedEvaluation` 仅接受持有 `feedback:evaluate` 的 OAuth/runtime 机器凭据；用户 JWT 和普通 `feedback:write` 均拒绝；
- 自动评估反馈只记录采集来源，审计明确 `training_authorized=false`，不产生任何训练数据授权；
- 90 天默认 retention job 物理清除；Context 硬删除立即物理清除，不恢复已删患者正文。

删除默认为 soft delete 并写审计；硬删除只由 retention job 完成。自动评估只能读取经过
权限和用途校验的反馈集合，不能把临床纠错直接转成模型训练授权。

## 10. 数据库迁移顺序

当前 Alembic 单 head 为 `046`。已保持小步、可回退：

1. `044_agentic_connectors`：connector、credential metadata、execution audit、索引和约束；
2. `045_a2a_async_tasks`：v1 持久 execution/event、租约、恢复与订阅；
3. `046_agent_task_feedback`：调用方隔离 feedback；trace 通过确定性 synthetic root span 投影现有 RunHistory/RunTrace，无需复制 trace 或新增 PHI 列；
4. 数据回填与 API 启用分离；新表先写 shadow、核对，再开放读取；
5. 凭据迁移单独执行并可中止，验证 secret store 成功前不删除旧值、不启用 connector。

每个 migration 必须有 upgrade/downgrade、SQLite 单元合同和 PostgreSQL 真机验证。新增唯一
约束前先生成冲突报告；生产回滚只关闭 feature flag 和读取面，不删除已经产生的审计数据。

## 11. SDK 与 OpenAPI 发布

三 SDK 同步增加：

- `agentic.agents`、`agentic.connectors`、`agentic.contexts`、`agentic.tasks`、
  `agentic.feedback`、`agentic.usage`；
- A2A v1 JSON-RPC 与 HTTP binding 客户端；SSE Subscribe 的取消、恢复和退避；
- 类型化五类 connector config，secret 只接受一次性输入，不出现在序列化/日志；
- opaque cursor，不允许客户端解析；
- per-Agent usage 的 inclusive/exclusive 时间窗口和 totals/daily buckets；
- TypeScript/Python 的 `workflow`、settled `parallel`、有界 `stateGraph` 与 Agent node 组合原语；
- v0.3 API 标记 deprecated，但兼容期内保持行为和测试。

OpenAPI 必须为两个 binding 使用不同 operation id，完整声明分页、SSE、错误、scope 和
secret write-only。生成 SDK 与手写 SSE 层都须有 drift gate；JavaScript/Python 本地打包、
.NET 双框架编译和 NuGet 打包进入发布门。

## 12. 开发环境验收矩阵

### 12.1 协议与兼容

- v0.3 现有 E2E 全量不回归；缺失/未知 header 仍失败；
- v1 JSON-RPC 与 HTTP binding 对同一输入产生同一 canonical task；
- Send/Stream/Get/List/Cancel/Subscribe 快乐、失败、重复、并发和恢复矩阵；
- terminal 状态不可逆、取消竞态、过期 task、错误码与 HTTP/JSON-RPC 映射；
- Agent Card 只发布实际能力，旧新发现地址并存。

### 12.2 Connector 安全负向矩阵

- 五类 CRUD、类型不可变、跨租户 agent/expert/credential 引用；
- loopback/private/link-local/metadata/IPv6/重定向/DNS rebinding/IDN 混淆；
- bearer/OAuth rotation、失效、错误 scope、日志/trace/OpenAPI/SDK secret scan；
- schema 递归/正则/节点/大小炸弹，agent 环、自环、深度和 fan-out；
- timeout、circuit breaker、幂等重试、预算、CN egress 拒绝与审计。

### 12.3 Context、Trace、Feedback

- context task 游标稳定性、并发插入、删除和 retention；
- OpenInference 分页、parent-child、token/tool/connector 属性和全链 secret/PHI 扫描；
- task/message feedback CRUD、重复、跨租户、已删除实体、DLP 和 retention；
- usage 按 Agent/时间/粒度聚合与当前 `/api/usage/by-agent` 对账。

### 12.4 E2E 分层

1. 纯内存/SQLite 合同测试：快速覆盖所有正负例；
2. PostgreSQL + Redis/事件总线集成：锁、游标、订阅恢复、跨进程；
3. 本地 mock connector E2E：不联网验证双 binding、MCP/A2A/schema 与失败关闭；
4. Docker Linux E2E：API、worker、PostgreSQL、Redis、反向代理/SSE；
5. 受控外网 connector/真实模型：仅在单独预算、凭据和出境授权后执行，不属于默认 CI。

本机无 Docker、.NET 和 PostgreSQL 服务，且浏览器重型测试存在原生内存崩溃风险。因此
第 1、3 层可在当前开发环境完成；第 2、4 层必须由具备对应依赖的 Linux/CI 环境证明。

## 13. Feature flags、上线与回滚

建议 flags：`AGENTIC_V2_API_ENABLED`、`A2A_V1_JSONRPC_ENABLED`、
`A2A_V1_HTTP_ENABLED`、`AGENTIC_CONNECTORS_ENABLED`、
`OPENINFERENCE_EXPORT_ENABLED`、`AGENTIC_FEEDBACK_ENABLED`。

阶段顺序：schema → shadow write → 管理 CRUD → mock execution → v1 read → v1 run → SDK beta →
租户 allowlist → 默认开启。任一阶段都可关闭新路由而保留已写审计。回滚不得把 v1 请求
静默送入 v0.3，也不得因关闭 connector 绕过失败关闭去调用默认 Provider。

## 14. 建议开发切片与完成定义

| 切片 | 可在当前开发环境完成 | 完成定义 |
|---|---|---|
| A | canonical DTO、v1 version、双 binding、旧版 adapter | **首个切片已完成**：Send/Stream/Get/List/Cancel + 87/87；Subscribe/持久事件仍转入 B |
| B | Task List/Subscribe、context tasks、稳定游标 | mock SSE 重连/竞态/租户矩阵 |
| C | connector 表、CRUD、五类型 validation | **已完成**：`044` 三表、251-path OpenAPI、五类型 CRUD/租户/环路/schema/secret 负向矩阵；专项 30/30 |
| D | credential adapter、SSRF/egress policy、mock executor | **全部当前 Agent 入口的 graph、动态 Agent Card、结构化条件和有界并行本地执行层已完成，生产部分仍开放**：统一 Run 专用分支和所有直接 A2A handler 都先执行租户 graph，服务端拥有 `_connector_results`；条件只读取脱敏结构化标量，依赖层有界并行并保持声明顺序；必需节点失败或内部异常均失败关闭并留 Run/Trace；URL/DNS/SSRF/CN 重验、数据策略、超时/重试/熔断/并发、独立节点审计和输出二次去标识/注入阻断已完成。仍缺生产凭据/OAuth transport、socket IP 钉住、redirect 逐跳复验和分布式控制面 |
| E | OpenInference 投影、feedback、usage v2 | **开发切片完成**：256-path OpenAPI；签名游标、确定性 root/child span、最小必要属性；binary feedback CRUD/调用方隔离/DLP/加密/retention/context hard delete；`automatedEvaluation` 限 `feedback:evaluate` 机器 scope 且默认不授权训练；per-Agent usage 做租户/可见性隔离、区间边界和日 bucket。仍缺生产账单对账、独立训练授权和多副本验证 |
| F | 三 SDK 与工件 | **TypeScript/Python composition、usage、Agent Card 和 Graph 类型本地实测，.NET 同步源码合同**：JS 41/41、Python 48/48；三套版本统一 `1.0.0-beta.21`，JS tgz、Python wheel/sdist 与 SHA-256 未发布清单已生成；.NET 仍由外部 CI 编译 |
| G | Docker/PostgreSQL/Redis/代理真实 E2E | 外部 Linux CI 证据，不由当前 Windows 主机冒充 |

只有 A–F 的开发证据和 G 的外部环境证据都通过，才可声称“Agentic v2 工程合同达到上线
候选”。这仍不等于 Corti 临床能力复刻；同病例双边盲评、医院接口、合法中国规则、法务、
安全认证、云容量、灾备与 SLA 仍是独立外部门禁。
