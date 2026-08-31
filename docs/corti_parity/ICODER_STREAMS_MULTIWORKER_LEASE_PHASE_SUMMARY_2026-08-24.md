# iCoDer Streams 跨 Worker 租约阶段总结（2026-08-24）

## 阶段结论

Streams 的“同一 interaction 只能在单进程内防重”缺口已经关闭。iCoDer 现在用数据库持久租约在 API Worker 之间协调活跃会话：组织、主体和 interaction 构成租约主键，随机 session UUID 是 fencing token；活跃租约拒绝冲突，心跳续期，过期后允许新 Worker 原子接管，旧 Worker不能续租或删除后继租约。

该结论证明开发环境的跨进程唯一性和崩溃后重新建立会话，不证明旧会话的未发送音频、内存 buffer、转写或 Facts 状态能够恢复。

## 实现边界

| 能力 | 当前合同 |
|---|---|
| 数据模型 | Alembic `056` 新增 `stt_stream_leases`；复合主键为 `organization_id + owner_id + interaction_id`，`session_id` 全局唯一 |
| 获取 | 首次连接插入；唯一冲突后只在 `lease_expires_at <= now` 时执行单条 compare-and-set 更新 |
| 心跳 | 默认 TTL 30 秒，运行时严格限制 6–300 秒；每 TTL/3 续租；协调数据库异常或所有权丢失即关闭 WebSocket |
| fencing | renew/release 均要求 scope 和精确 `session_id`；旧 Worker 无法覆盖或删除接管者 |
| 副作用 | `flush` 与 `end` 在执行转写、Facts、留存、usage/end 前再次确认租约，失去所有权时不提交终态副作用 |
| 配置 | 本地 Compose 与云模板显式声明 `ICODER_STREAM_LEASE_SECONDS=30`；临时 E2E 使用 6 秒下限 |
| PHI | 租约表只保存租户/主体/interaction/session 标识和时间，不保存音频、转写或 Facts 正文 |

## 端到端证据

双 Worker 测试使用两个独立 Uvicorn、共享的临时 SQLite WAL 和真实注册得到的租户 access token：

1. Worker A 接受 interaction 并写入一条活跃租约；
2. Worker B 对同 scope/interaction 的并发连接被拒绝；
3. Worker A 被 `Stop-Process -Force` 强制终止，无法执行 finally/release；
4. 等待 6 秒 TTL 过期后，Worker B 以不同 session fence 原子接管；
5. 恢复会话按 `usage → ENDED` 完成，最终租约数为 0；数据库保留 2 次 configured、1 次 ended 审计，符合一次崩溃、一次成功完成。

机器证据：[`multiworker_e2e_evidence.json`](../../reports/sdk_streams_lease_phase_20260824/multiworker_e2e_evidence.json)。JavaScript、Python、.NET 原有真实 Streams E2E 也在新租约层上复跑通过，见 [`three_sdk_e2e_evidence.json`](../../reports/sdk_streams_lease_phase_20260824/three_sdk_e2e_evidence.json)。

## 验证结果

- 租约并发、租户/主体隔离、过期接管、stale-owner fencing、边界配置和路由失败关闭：包含在 Streams 定向与扩大回归中；扩大回归 **69/69**。
- fresh Alembic head、重复升级、降级/回升、`055` 状态约束、迁移链唯一/连续及 ORM 双向漂移：**10/10**。
- 发布/部署验证器：**6/6**；静态部署预检：**86/86**。
- 三 SDK 单 Worker 真实 WebSocket：3/3 会话通过；双 Worker 租约故障 E2E：1/1 场景通过。
- 受保护开发库未迁移、未写入，仍为 8,536,064 bytes，SHA-256 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。

测试显式移除 LLM key，关闭真实 LLM、STT、MedCoder，未发送患者数据或真实音频。临时 token 不进入子进程命令行；进程、临时库和环境变量均在 finally 回收。

## 与 Corti 的剩余差距

Corti 公开的 [Streams API](https://docs.corti.ai/api-reference/streams) 是绑定 interaction 的有状态 WSS 工作流，并把 transcript、Facts、留存、flush 和 usage 归于该 interaction；[Streams STT 指南](https://docs.corti.ai/stt/streams) 描述了实时临床会话与持久化行为。

当前仍缺：

- 未完成会话的音频 buffer、转写游标、Facts 去重状态与 Provider 调用状态的持久恢复；本阶段恢复的是所有权，不是内容；
- PostgreSQL 多副本的高并发争用、网络分区、时钟偏差、容量、延迟和故障注入证明；
- Redis/队列或专用协调服务、跨区域 session routing、生产告警和运维 runbook；
- 真实 ASR/Facts、audio events、diarization、多声道、计费与临床质量。

这些能力不能由 SQLite 双进程测试提升为生产完成。
