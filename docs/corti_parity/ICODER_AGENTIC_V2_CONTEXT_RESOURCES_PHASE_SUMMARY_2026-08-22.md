# iCoDer Agentic v2 Context / Task / Artifact 阶段总结（2026-08-22）

## 结论

本阶段把此前仅有 trace/feedback 的 Agentic v2 Context 表面补齐为真实资源接口。实现直接读取既有租户归属 Context、持久 Task、加密脱敏消息和异步结果，不建立第二套伪状态。

开发环境验证通过；但这不是“Corti 全能力完成”的结论。文件/URI Artifact、标准 Artifact 增量事件、生产多副本、外部 Provider 物理中止和 .NET CI 仍为开放项。

## 当日 Corti 基线

Corti 当日公开文档把 Context 定义为可独立读取和删除的一等资源。Context 详情包含按最早优先排列的 Task，每个 Task 带消息历史并支持 `historyLength`；删除不可逆；Artifact 必须同时由 Context、Task、Artifact 三个 ID 定位。文档同时明确 Context 列表仍处于 private preview，当前返回空页并忽略过滤条件。

本阶段以官方 `llms.txt`、`llms-full.txt` 和当前 A2A 规范为机读基线。iCoDer 的列表实现是真实的租户内分页列表，功能上超过 Corti 当前 preview；差距矩阵中明确记录，不把它描述为线上互操作证明。

## 已实现

- `GET /api/v2/agentic/contexts`
- `GET /api/v2/agentic/contexts/{context_id}`
- `DELETE /api/v2/agentic/contexts/{context_id}`
- `GET /api/v2/agentic/contexts/{context_id}/tasks`
- `GET /api/v2/agentic/contexts/{context_id}/tasks/{task_id}`
- `GET /api/v2/agentic/contexts/{context_id}/tasks/{task_id}/artifacts/{artifact_id}`

资源读取具备以下约束：

- Context 查询始终绑定认证组织；跨租户和不存在统一返回 404。
- OAuth Client 分离 `contexts:read` / `contexts:write`，并兼容平台 `api:read` / `api:write`。
- Context 和 Task 列表使用签名、租户绑定、资源绑定、过滤条件绑定的游标；篡改或跨查询复用返回 400。
- Context 详情返回 Task 最早优先；历史只来自已脱敏、加密保存的消息，内部 run/correlation metadata 不公开。
- `historyLength` 对每个 Task 截取最近消息；Context 详情默认返回完整历史，Task 列表默认不批量返回历史。
- 删除调用现有跨存储硬删除流程，完成后写入不含临床正文的稳定审计 reason code。
- Artifact 只返回当前持久 Task 可证明归属的 `${taskId}-result`。旧 Context 级 Artifact 表没有 `task_id`，因此绝不以“同 Context 即同 Task”的方式弱化隔离。

## SDK 与 OpenAPI

JavaScript、Python、.NET 均新增六个 v2 方法，旧 v0.3 Context 方法保持不变。JavaScript 与 .NET 新增强类型 Context/Page/Task/Artifact 合同；Python 增加输入范围和响应形状验证。

- JavaScript：构建通过，42/42。
- Python：全套 49/49。
- .NET：源码和合同测试已同步；本机无 `dotnet`，未声称编译通过。
- OpenAPI：265 paths，826,049 bytes；新六个资源操作均由真实 FastAPI 路由导出。

## 验证结果

- 新增后端专项：3/3。
- 完整 A2A 集成目录 + OpenAPI 一致性 + 部署预检测试：103/103，9 条既有弃用警告。
- 静态部署预检：59/59。
- Agent Hub 运行矩阵：26/26 用户可见 Agent 为 launch candidate，0 个可见 blocker。

专项验证覆盖：完整双消息历史、`historyLength`、Artifact 读取、跨 Task Artifact 404、列表过滤和双向分页、游标过滤绑定、跨租户 404、OAuth scope、不可逆删除和删除后审计。

## 仍开放的真实差距

1. 当前 Artifact 是持久异步结果投影；尚无 Task 归属的文件/URI Artifact 表、对象存储、病毒扫描、内容完整性和下载授权链。
2. 当前 Corti 公开文档和 A2A v1 都将 Context、Task、Artifact ID 定义为服务端生成的 opaque string（可为 UUID），没有公开类型前缀 UUIDv7 约束；iCoDer 的 UUIDv4/`task-` ID 不据此记录为协议差距。
3. 本阶段没有证明 Corti 私有 preview 列表、真实租户 API 或第三方 A2A SDK 的线上互操作。
4. `.NET` 必须在 Linux CI 安装 SDK 后编译并执行合同测试。
5. 生产队列、多副本租约、跨进程取消、外部 Provider 物理中止及费用停止仍需真实基础设施。
6. 医院接口、患者授权、真实云、法务、认证和独立临床 reviewer 门禁继续保持未通过。

机器可读证据：`reports/agent_hub/agentic_v2_context_resources_phase_20260822/phase_evidence.json`。
