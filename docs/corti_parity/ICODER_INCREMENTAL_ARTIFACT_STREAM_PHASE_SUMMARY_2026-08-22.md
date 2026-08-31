# iCoDer 增量 Artifact 流阶段总结（2026-08-22）

## 结论

本阶段把 A2A v1 `SendStreamingMessage` 从“完成后一次性响应”升级为真实 Task 流：服务端先持久化 Task，再在同一个 SSE 响应中发送 Task 快照、working、一个或多个 `artifactUpdate`，最后发送 completed/failed。每个 Artifact chunk 都有独立密文、明文大小和 SHA-256，断线恢复读取事件当时的精确 payload，不再把历史事件错误投影成最终 Artifact。

输出安全优先于未经验证的低延迟 token：只有 Agent 响应通过输出合同、PHI、审计和 Context 持久化边界后，才会被拆成公开 Artifact chunks。Provider 原生 delta 仍是内部 provisional telemetry，不能被误当成临床有效输出。

## 已实现

- Alembic `052` 为 `a2a_task_events` 增加 `artifact_payload_json`、`artifact_payload_sha256` 和 `artifact_payload_size_bytes`。
- 每个 `artifactUpdate` 保存规范 Artifact JSON 的 PHI 密文、大小与摘要；字段缺失、解密失败、大小/摘要/Artifact ID 不一致均失败关闭。
- `append=false` 开始或重置一个流，后续 `append=true` 追加 Part，`lastChunk=true` 才允许组装为终态 Artifact。
- 租约恢复时，新的 `append=false` 会重置上一次中断的未完成流；终态后继续追加、首事件 `append=true`、超过 256 个事件或缺失 `lastChunk` 都被拒绝。
- 长文本相邻 Part 在 256 KiB 单 Part 上限内合并，超过后安全拆分；完整 Artifact 继续受 1 MiB 总上限约束。
- 最终 Task 同时保存：
  - 原有可机读结果 Artifact（`*-result`）；
  - 验证后公开 Message Parts 的增量 JSON Artifact（`*-validated-stream`）。
- HTTP+JSON `message:stream` 和 JSON-RPC `SendStreamingMessage` 对新消息都创建持久 Task，并从 submitted sequence 开始流式重放，避免调度竞态跳过早期 chunk。
- TypeScript 新增 `messageStreamV1`，Python 新增 `message_stream_v1`，.NET 新增 `MessageStreamV1Async` / `MessageStreamV1TextAsync`。

## 安全边界

本实现不会公开 Provider 原生 token。原生 delta 可能尚未满足 Agent Pack 必填字段、嵌套 schema、跨字段关系、人工复核策略、结果签名和审计终态；提前公开会制造“后续失败但临床内容已经泄露”的不可撤回状态。

因此当前流是验证后立即分块发布，具备标准多块协议、精确重放和 SDK 消费能力，但不声称具有模型生成过程中的首 token 低延迟。后者必须先具备增量结构验证、可撤回 UI 语义和明确的非临床 provisional 展示合同。

## 验证

- Artifact/Task/Provider 专项：58/58。
- 完整 A2A、迁移、schema 与预检回归：312/312，9 条既有弃用警告。
- 静态部署预检：62/62。
- JavaScript SDK：42/42，TypeScript build 通过。
- Python SDK：49/49。
- 16K+ 中文响应验证为 3 个精确 chunks：`append=[false,true,true]`、`lastChunk=[false,false,true]`，组装内容与持久 Message Parts 完全一致。
- 事件密文篡改测试确认 SHA-256 不一致时拒绝重放。
- OpenAPI：265 paths，重新生成并通过 drift check。
- Agent Hub：26/26 用户可见 Agent 为开发环境 launch candidate。
- `.NET` 源码和测试合同已更新；本机没有 `dotnet` CLI，未声称编译通过。

## 迁移安全

当前开发源库仍保持 Alembic `041`，未迁移、未切换、未重启。独立影子候选已升级到单 head `052`：

- 6,090 行源数据全部保留；
- 961 个候选列与 ORM 零 schema 漂移；
- 候选 0 个外键违规；
- 源库前后 SHA-256 均为 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；
- `cutover_performed=false`。

## 仍开放的差距

1. 未经终态合同验证的 Provider 原生 token 不作为公开 Artifact；因此尚无模型生成过程中的首 token 低延迟临床流。
2. 没有托管对象上传、签名下载授权、恶意文件扫描、DLP 文件流水线和对象生命周期证据。
3. 没有 Corti 私有租户或独立第三方 A2A v1 客户端的线上互操作证明。
4. `.NET` CI、PostgreSQL 多副本、生产队列、跨进程取消和真实 Provider 物理中止仍需外部环境。
5. 当前开发数据库仍在 `041`；受控切换需要维护窗口、备份恢复演练和明确审批。
6. 26-Agent 真实模型质量、医院接口、患者授权、云基础设施、法务、认证和独立临床验收仍未通过。

机器证据目录：`reports/agent_hub/incremental_artifact_stream_phase_20260822/`。
