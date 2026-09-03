# Run SSE 实时尾随与持久化租户归属阶段总结（2026-08-15）

## 阶段结论

本轮关闭了一个会把运行中 Agent 错报为已完成的公共契约缺口。`GET /api/v1/runs/{run_id}/events` 不再在重放已有 trace 后无条件发送 `stream.completed`；现在会持续读取追加事件、在空闲时发送心跳、在客户端断开时退出，并且只在权威 `RunHistory` 进入真实终态后刷新最后一批事件、发送一次终态事件并关闭。

这是一项开发环境上线候选能力，不等同于 Corti 托管服务的生产 SLA 或临床生产批准。

## 本轮完成的能力

1. 已有 trace 立即重放，之后以追加前缀游标读取新事件，避免重复发送。
2. 非终态 Run 保持连接；`CANCEL_NOT_SUPPORTED` 与 `CLIENT_ABORTED` 不会触发假完成。
3. 运行中尚无首个 trace 的 Run 可提前订阅，不再出现客户端创建 Run 后立即订阅的 404 竞态。
4. 空闲 15 秒发送标准 SSE comment 心跳；断连检测会停止轮询。
5. 终态关闭前再次读取 TraceStore，覆盖 trace 与 RunHistory 分别提交时的可见性竞态。
6. `stream.completed.payload` 现在包含真实终态、最终事件数和 Run ID。
7. 长连接期间持续复核组织归属和租户可见性；归属或分类发生变化时失败关闭。
8. 修复 OAuth Agent Run 持久化 trace 缺少 `organization_id`、`user_id`、`actor_id` 与稳定 `trace_id` 归属的问题。内存存储此前不做组织过滤，曾掩盖该缺陷。
9. JavaScript、Python、.NET 三套 SDK 均增加心跳与多事件流回归，并在真实临时 HTTP 服务、SQLite 持久化 TraceStore 和组织绑定 OAuth token 上消费独立的延迟长流。

## 验证证据

- 后端 SSE、租户隔离与 orphan-run 防护：31/31。
- 后端 trace 双计数与 SSE 组合回归：14/14。
- 持久化 trace 租户/用户/actor/trace ID 传播单元回归：1/1。
- JavaScript SDK：15/15。
- Python SDK：22/22。
- .NET SDK：net8.0 27/27，net10.0 27/27。
- 三 SDK 真实本地 E2E：[local_e2e_20260815_sse_live_tail.json](../../reports/sdk/local_e2e_20260815_sse_live_tail.json)。三者均验证 `run.ingest → 延迟 run.completion → stream.completed`，终态为 `COMPLETED`、事件数为 2；同时验证组织绑定 OAuth form-token。未调用真实 LLM/ASR，未发送音频。
- OpenAPI 已重新导出并通过 `--check`，大小 623725 bytes。
- 部署静态预检：[development_preflight_20260815_sse_live_tail](../../reports/deployment/development_preflight_20260815_sse_live_tail/)，无失败项。
- E2E 使用随机环回端口、临时数据库、临时 JWT/OAuth secret，结束后关闭服务并回收临时目录。

## 与 Corti 的阶段差距

本轮后，iCoDer 的开发合同已具备 Corti/A2A 类实时 Run 事件所需的基本尾随、心跳和真实终态语义。但仍不能宣称托管能力等价：

- 尚未实现 `Last-Event-ID`/游标恢复、断线续传和跨网关重连契约；当前连接内使用追加前缀游标。
- 尚未在多 API worker、PostgreSQL、反向代理和真实负载均衡环境验证事件顺序、连接迁移、背压与并发容量。
- 15 秒生产心跳已由加速回归验证语义，但尚未经过真实云代理 idle-timeout、移动网络和长时运行测试。
- 尚无 Corti 托管环境的长任务、限流、跨区域、可用性、计费与支持 SLA 对比证据。
- 真实 LLM/ASR、医院 HIS/EMR/FHIR、地方医保/DRG/DIP、临床 reviewer、独立安全审查及云生产批准仍属于外部门禁。

## 下一阶段建议

开发环境下一优先项应是可恢复 SSE：公开稳定事件 ID、支持 `Last-Event-ID`、建立断线重连/去重测试，并在 PostgreSQL 多 worker 与反向代理环境验证顺序和背压。真实模型质量、Corti 双边病例比较和医院验收必须使用新临时凭据与去标识数据，不能复用本轮已暴露的密钥。
