# Run SSE 断线续传阶段总结（2026-08-15）

## 阶段结论

本轮关闭了上一阶段保留的 `Last-Event-ID`/断线续传缺口。Run trace 现在从持久化层到 SSE 和三套 SDK 使用同一个稳定事件身份；客户端确认某条事件后断线，可从下一条 trace 恢复，不需要重放已经处理的事件。

该能力证明开发环境的恢复合同可运行，不代表已经获得 Corti 托管环境、多可用区或生产容量 SLA 的等价证据。

## 实现内容

1. `RunTraceEvent` 贯穿 `event_id`、`sequence_number` 和 `trace_id`。数据库读取保留既有 UUID；内存存储在追加时生成同形 UUID；迁移前的旧行使用稳定 `legacy:<row_id>` 回退身份。
2. 数据库读取按事件时间、创建时间、序号和主键形成确定性顺序，避免多进程测试中进程内序号重复造成重排。
3. Run SSE 为每条 trace 输出标准 `id:`、`event:` 和 `data:` 帧；envelope 的 `meta.event_id` 与 SSE `id:` 完全一致。
4. `Last-Event-ID` 从指定事件之后恢复。游标不属于当前 Run 时返回 `409 SSE_CURSOR_NOT_FOUND`；超长或非法游标返回 `400 SSE_CURSOR_INVALID`，均在开始流式响应前失败。
5. 最后一条 trace 已确认时，重连只返回无 ID 的 `stream.completed`，不会重复业务 trace；最终事件数仍是完整 trace 总数。
6. Partner CORS 预检显式允许 `Last-Event-ID`，OpenAPI 显式声明该请求头以及 400/409 响应。
7. JavaScript、Python、.NET SDK 均公开恢复参数并做客户端长度/控制字符校验；.NET 继续保留原有重载兼容调用。

## SDK 版本与构建

- JavaScript `1.0.0-beta.8`：15/15，TypeScript 构建和 `npm pack --dry-run` 通过。
- Python `1.0.0b7`：22/22，wheel `icoder_sdk-1.0.0b7-py3-none-any.whl` 构建通过。
- .NET `1.0.0-beta.8`：net8.0/net10.0 各 27/27；NuGet 与 symbol 包生成成功，并同时包含两套框架资产。

## 后端与端到端证据

- SSE、CORS、TraceStore 与持久化身份专项组合回归：45/45；扩大到 trace token、租户隔离、orphan-run、DB 持久化的最终串行回归为 84/84。
- 三 SDK 真实断线重连：[local_e2e_20260815_sse_resume.json](../../reports/sdk/local_e2e_20260815_sse_resume.json)。每套 consumer 均执行“接收 `run.ingest` → 主动断开 → 保存 UUID → 携带 `Last-Event-ID` 重连 → 仅接收 `run.completion` 与 `stream.completed`”。
- E2E 使用真实临时 uvicorn、SQLite DB TraceStore、组织绑定 OAuth form-token、随机环回端口和独立 Run；没有真实 LLM/ASR 调用或音频发送。
- OpenAPI 已导出并通过 `--check`，624686 bytes；Schema 包含 `Last-Event-ID`、400、409。
- 部署静态预检：[development_preflight_20260815_sse_resume](../../reports/deployment/development_preflight_20260815_sse_resume/)，无失败项。

## 与 Corti 的剩余差距

- 三 SDK 目前提供可控的恢复参数，但尚未提供带指数退避、抖动、最大重试时间和 token 续期策略的自动重连器。
- 未区分“未知游标”和“因保留期清理而过期的游标”；当前统一失败关闭为 409。
- 尚未在 PostgreSQL、多 API worker、反向代理、负载均衡、进程重启和时钟偏差下验证顺序、去重、背压及容量。
- 仍缺 Corti 托管环境的限流、跨区域、可用性、计费和支持 SLA 对比，以及真实医院/临床/法务/安全外部门禁。

下一开发优先项应是 PostgreSQL 多 worker + 反向代理恢复矩阵及 SDK 自动重连策略；这两项完成前不能把本轮的一次性恢复合同描述为生产级长连接可靠性。
