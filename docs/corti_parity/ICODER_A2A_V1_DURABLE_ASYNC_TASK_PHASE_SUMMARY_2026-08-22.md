# A2A v1 持久化异步 Task 阶段总结（2026-08-22）

本阶段把 A2A v1 的 `returnImmediately` 从同步结果包装收敛为可恢复的持久化
Task：请求先提交，后台执行通过数据库租约认领，客户端可轮询、分页、取消未开始任务，
或通过可恢复 SSE 订阅持久事件。实现复用既有统一 Inbound/Provider/Connector graph 与安全门，
没有为异步路径建立绕过审计或输出校验的第二套执行链。

当前结论：**A2A v1 持久化异步 Task 已达到开发环境上线候选；这关闭了 Corti Agentic v2
对照中的真实异步 Task、Subscribe 和持久事件 P0 缺口，但不等于生产队列、多区域容灾或
全部 Corti Agent SDK/托管运行时等价。**

## 已完成

- HTTP+JSON `SendMessage` 和 JSON-RPC `SendMessage` 均支持
  `configuration.returnImmediately=true`，返回 `TASK_STATE_SUBMITTED`，不再等待 Provider。
- 新增 Alembic `045`：`a2a_task_executions` 保存加密的最小必要执行载荷/结果、租约、尝试次数和
  稳定错误码；`a2a_task_events` 保存单调序列、状态和事件类型。
- 后台运行时通过数据库条件更新认领 Task；租约心跳、过期租约恢复、进程优雅停止即时释放、
  启动扫描恢复均已实现。终态写入要求当前租约所有者并使用状态 CAS，旧 worker 不能覆盖新
  worker 或并发取消产生的状态。
- `GetTask`、`ListTasks`、`CancelTask`、HTTP
  `GET /tasks/{task_id}:subscribe` 和 JSON-RPC `SubscribeToTask` 已闭环；SSE 支持
  `Last-Event-ID` 与 `afterSequence` 恢复，事件来自数据库而非进程内缓存。
- 取消只允许尚未认领的 `SUBMITTED` Task；已进入 `WORKING` 的调用明确拒绝取消，避免把
  “客户端停止等待”伪装成 Provider 已被终止。
- Task 投影包含终态消息、artifact、时间戳和稳定 `errorCode`；必需 Connector 失败形成
  `TASK_STATE_FAILED/CONNECTOR_GRAPH_FAILED`，不发布临床结果。
- 原始请求与结果按现有 PHI 存储策略加密；租户/Agent 绑定、消息幂等、输入注入拒绝、
  跨 Agent 访问拒绝和 context 硬删除对新表的清除均有集成测试。
- OpenAPI 增加订阅路由，公开路径从 252 增至 253；运行时一致性测试现在要求所有 A2A v1
  运行时路径都进入导出契约，避免手工清单再次假阳性。
- JavaScript `1.0.0-beta.18`、Python `1.0.0b18` 和 .NET `1.0.0-beta.18` 均提供 v1
  send/get/list/cancel/wait/subscribe 源码合同；错误对象只保留稳定 google.rpc ErrorInfo
  `reason`，不保留可能含 PHI 的原始响应详情。

## 验证结果

所有自动化测试均显式清空 `ICODER_CREDENTIAL_LLM`、关闭外部 LLM 并禁用 Windows 原生
MedCodER；没有消耗用户密钥，也没有调用 Corti 或外部 Connector。

| 验证 | 结果 |
|---|---:|
| A2A v0.3/v1 + async + Connector/graph + SSRF + Agent Run 联合回归 | 228/228 |
| 真实 FastAPI lifespan 启动与路由 | 3/3 |
| Python SDK 全量 | 41/41 |
| JavaScript SDK 全量（包含 TypeScript build） | 34/34 |
| 前端 OpenAPI 路径合同 | 60/60 |
| 三 SDK 版本/候选发布验证 | 5/5；统一 `1.0.0-beta.18` |
| 本地候选制品 | JavaScript `.tgz` + Python `.whl`，SHA-256 已记录，未发布 |
| OpenAPI 导出漂移 | 253 paths，check 通过 |
| Alembic | 单 head `045`；升级后两表存在，降级 `044` 后两表消失 |
| Python compileall | 通过 |
| 本阶段 diff 真实密钥形状扫描 | 0 命中 |

.NET 源码和反例测试已静态审查，但本机没有 `dotnet`、`csc` 或 `msbuild`，因此 **没有**
把 .NET 记为编译或测试通过。

候选制品及哈希见
[`LOCAL_RELEASE_MANIFEST_BETA18.json`](../../reports/release-candidate/LOCAL_RELEASE_MANIFEST_BETA18.json)；
清单明确记录工作树为 dirty、制品为本机构建且 `publication.performed=false`。

## 仍未完成/不得宣称

- 当前调度器是应用内 worker 加数据库持久化/租约，不是 Kafka、RabbitMQ、云队列或独立
  worker fleet；PostgreSQL 多进程/多副本争抢、故障转移和容量尚无外部实跑证据。
- 运行中 Task 不能真实中止下游 Provider；`WORKING` 取消失败是诚实合同，不是 Corti
  托管运行时的强制取消等价。
- 条件/并行/循环 Planner、动态 Agent Card、生产 MCP/A2A/OAuth transport、逐跳 DNS/IP
  钉住、分布式熔断/并发控制仍未完成。
- OpenInference context trace export、task/message feedback 与自动评估入口仍是 P1。
- .NET 双框架编译测试、Linux/Docker、PostgreSQL 多副本、云 KMS/队列、医院接口、真实患者
  场景、合法编码资产、法务/等保/认证和独立临床 reviewer 均保持外部门禁未通过。

机器可读证据：[`phase_evidence.json`](../../reports/agent_hub/a2a_v1_durable_async_task_phase_20260822/phase_evidence.json)。
