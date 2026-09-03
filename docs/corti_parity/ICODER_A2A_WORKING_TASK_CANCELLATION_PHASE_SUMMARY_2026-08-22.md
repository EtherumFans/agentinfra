# iCoDer A2A 运行中 Task 取消阶段总结（2026-08-22）

## 结论

本阶段补齐 A2A v1 `CancelTask` 对本机运行时持有的 `working` Task 的协作取消。取消成功前，运行时必须确认并停止对应 asyncio dispatch；随后释放租约，并以数据库 compare-and-set 写入唯一 `canceled` 终态。同步工作线程即使稍后返回，也失去结果落库路径，不能覆盖取消状态或生成 Artifact。

该能力遵循 A2A 的“尽力取消”语义，不扩大成外部 Provider 物理中止承诺：任务由其他进程持有、缺少本机 asyncio Task，或已进入终态时，仍返回 `TASK_NOT_CANCELABLE`。同步线程或远端 Provider 可能已经产生计算或费用，生产级跨进程中止仍是外部门禁。

## 实现与审计不变量

- `A2ATaskRuntime.cancel_running()` 只操作本机任务表中的活动协程，并等待取消处理及租约释放完成。
- JSON-RPC `CancelTask` 与 HTTP+JSON `POST .../tasks/{taskId}:cancel` 共享同一逻辑。
- 运行中取消后事件序列为 `submitted → working → canceled`。
- `result_json` 保持为空，租约 owner/expiry 清空。
- 外部 lease owner 不会被伪报为 canceled。
- 取消入口继续执行租户和 Agent 范围的任务查找，不扩大任务可见性。

## 验证

- A2A durable runtime + endpoint 专项回归：47/47。
- 完整 A2A integration 目录 + 部署预检测试：95/95。
- 静态部署预检：58/58。
- Agent Hub 运行矩阵：26/26 executable、provider-resolvable、development launch-candidate-ready，0 个 visible blocker。
- 无真实 LLM 凭据、无外部 Provider 调用、无浏览器启动。

## Corti/A2A 对标

2026-08-22 的 Corti 文档索引将 v2 JSON-RPC 的 `CancelTask` 和 HTTP+JSON 的 Cancel endpoint 列为公开能力；A2A 1.0 规范要求服务器尝试取消，但允许在当前阶段不可取消。iCoDer 现覆盖本机持有任务的可证明取消，并对其他情况失败关闭。Corti 托管运行时的真实跨进程取消、费用结算和 Provider 终止行为没有公开证据，不能推定等价。
