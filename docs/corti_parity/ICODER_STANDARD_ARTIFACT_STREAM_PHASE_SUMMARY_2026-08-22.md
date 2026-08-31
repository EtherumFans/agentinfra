# iCoDer A2A 标准 Artifact 流事件阶段总结（2026-08-22）

## 结论

本阶段把 Task 订阅从 iCoDer 自定义事件包络收敛为 A2A v1 的标准流响应：初次订阅返回 Task 快照，后续持久事件分别使用 `statusUpdate` 和 `artifactUpdate`。成功 Task 会先发布可恢复的完整 Artifact 更新，再发布 `completed` 状态，断线恢复沿用持久 sequence，不会丢失 Artifact 与终态的顺序。

开发环境验证全部通过，但这只关闭标准事件形状和完整 Artifact 发布缺口。当前 Provider 仍一次生成完整结果，尚未提供真实多块输出的生产链；对象文件安全、生产多副本、第三方互操作和临床上线门禁仍开放。

## 已实现

- Alembic `051` 为 `a2a_task_events` 增加 `artifact_id`、`artifact_append`、`artifact_last_chunk`，使 Artifact 事件身份和分块语义可持久恢复。
- 新订阅先返回 `{task: ...}` 快照；从 `afterSequence` 或 `Last-Event-ID` 恢复时，状态行返回 `{statusUpdate: ...}`，Artifact 行返回 `{artifactUpdate: ...}`。
- SSE 使用 `task`、`status-update`、`artifact-update` 事件名，SSE `id` 使用数据库持久 sequence；JSON-RPC 流在 `result` 下返回相同标准对象。
- 同步与异步成功路径均先写 Artifact 事件，再写终态事件；失败与取消路径不伪造 Artifact。
- 当前完整结果事件明确返回 `append=false`、`lastChunk=true`。合同和持久层已能表达分块语义，但未虚构尚不存在的增量 Provider 生产能力。
- Artifact 增加有界 `description` 和绝对 URI `extensions`；既有 text/data/base64 raw/HTTPS URL Part、PHI 加密、规范 JSON 大小和 SHA-256 完整性保持不变。
- TypeScript、Python 和 .NET 源合同同步了 Task 快照、状态更新、Artifact 更新、`append` / `lastChunk`、Artifact description/extensions 与文件 Part。

## ID 证据更正

复核 [Corti Core Concepts](https://docs.corti.ai/agentic/core-concepts)、[A2A v1 specification](https://a2a-protocol.org/dev/specification/) 与 [A2A v1 changes](https://a2a-protocol.org/latest/whats-new-v1/) 后，没有找到“类型前缀 UUIDv7”这一公开要求。当前公开合同将 Context、Task、Artifact ID 定义为服务端生成的不透明字符串（可使用 UUID）。因此 iCoDer 的 UUIDv4/`task-` 标识不是已证实的协议差距，旧矩阵中的相反表述已经撤回。

## 迁移安全

当前开发源库继续保持 Alembic `041`，未迁移、未切换、未重启。只读源库在独立目录重建候选并升级到单 head `051`：

- 6,090 行源数据全部保留；
- 958 个候选列与 ORM 零 schema 漂移；
- 候选 0 个外键违规；
- 源库迁移前后 SHA-256 均为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；
- 原有 827 个组织外键孤儿仅在候选副本中由 6 个停用隔离父记录收容；
- `cutover_performed=false`。

候选数据库不是发布物，也未替换正在监听的开发数据库。

## 验证

- 完整 A2A、迁移、schema 与预检回归：310/310，9 条既有弃用警告。
- 静态部署预检：61/61。
- JavaScript SDK：42/42。
- Python SDK：49/49。
- OpenAPI：265 paths，已重新生成并通过 drift check。
- Agent Hub 运行矩阵：26/26 用户可见 Agent 为开发环境 launch candidate。
- 影子迁移：head `051`、6,090 行、958 列、0 FK 违规、0 ORM 漂移、源库未变。
- `.NET` 源合同已更新；本机没有 `dotnet` CLI，因此未声称编译或测试通过。

## 仍开放的差距

1. 当前只发送一次完整 Artifact 更新（`append=false`、`lastChunk=true`）；真实 Provider 驱动的多块增量生成、重试和分块合并质量尚未验证。
2. 没有托管对象上传、签名下载授权、恶意文件扫描、DLP 文件流水线和对象生命周期证据。
3. 没有 Corti 私有租户或独立第三方 A2A v1 客户端的线上互操作证明。
4. `.NET` CI、PostgreSQL 多副本、生产队列、跨进程取消和真实 Provider 物理中止仍需外部环境。
5. 当前开发数据库仍在 `041`；生产迁移需要维护窗口、备份恢复演练和明确切换审批。
6. 26-Agent 真实模型质量、医院接口、患者授权、云基础设施、法务、认证和独立临床验收仍未通过。

机器证据目录：`reports/agent_hub/standard_artifact_stream_phase_20260822/`。
