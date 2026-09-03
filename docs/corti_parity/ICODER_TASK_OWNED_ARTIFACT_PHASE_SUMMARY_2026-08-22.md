# iCoDer Task 归属 Artifact 持久化阶段总结（2026-08-22）

## 结论

本阶段把 Agentic v2 Artifact 从“完成消息的临时投影”收敛为真实持久资源。新完成的 A2A Task 会在同一终态事务中写入由 Context、Task、Artifact 三元组唯一定位的 Artifact；读取时验证密文、规范 JSON 大小、SHA-256 和 Artifact 身份，任何不一致均失败关闭。

开发环境验证通过，但不代表 Corti 全能力或临床生产就绪。对象存储上传、短期下载授权、恶意文件扫描、生产多副本、Corti 托管互操作、医院/云/法务/认证和独立临床 reviewer 仍是开放门禁。

## 已实现

- Alembic `050` 新增 `a2a_task_artifacts`，主键为 `(context_id, task_id, artifact_id)`，并以 `(context_id, task_id)` 复合外键绑定 `context_task_refs`。
- Artifact 的规范 JSON 使用现有 PHI 加密密钥生命周期保存；Cloud 继续要求密钥，本地开发保留既有透明模式。
- 每条记录保存规范明文的 `size_bytes` 和 SHA-256；解密、大小、摘要、JSON 合同或 Artifact ID 任一异常都不返回内容。
- 异步 `returnImmediately` Task 在 Task 终态、加密结果、Artifact 和完成事件的同一数据库事务中提交。
- 使用既有 `taskId` 的同步完成路径也会持久化 Artifact；无有效结果或无有效 Part 不会生成伪完成资源。
- Task 与 Context 资源投影优先读取持久 Artifact。仅对迁移 `050` 前已经完成的旧 Task 保留 `${taskId}-result` 兼容投影；旧 Context 级引用仍不会被当作 Task Artifact。
- Context 硬删除显式先删 `a2a_task_artifacts`，即使 SQLite 未启用外键也不会残留。

## Part 合同

持久 Artifact 支持有界、严格的 A2A v1 输出 Part：

- `text`：文本输出；
- `data`：任意合法 JSON 结构；
- `raw`：严格 base64 的内联文件，解码后最多 768 KiB；
- `url`：最长 2,048 字符、无嵌入凭证的 HTTPS 引用。

每个 Part 只能有一个内容字段；可带 `mediaType`、`filename` 和 JSON metadata。单 Artifact 最多 64 个 Part，规范载荷最多 1 MiB；单 Task 最多 16 个 Artifact。服务端保存并返回 URL，但绝不主动下载该 URL，因此不引入服务端 SSRF 请求路径。

这已经关闭“Task 归属的文本/数据/文件引用持久化”缺口，但不是完整文件平台：尚无 iCoDer 托管对象上传、一次性下载令牌、病毒/恶意内容扫描、DLP 文件流水线和对象生命周期证明。

## 迁移安全

当前开发源库仍保持 Alembic `041`，未迁移、未切换、未重启。只读源库通过 SQLite backup 在独立目录重建候选：

- 源库迁移前后 SHA-256 相同；
- 候选到单 head `050`；
- 6,090 行源数据全部保留；
- 候选 0 个外键违规、0 个 ORM schema 漂移；
- 原有 827 个组织外键孤儿只在候选副本中由 6 个停用隔离父记录收容；
- `cutover_performed=false`。

候选数据库不是发布物，也未替换开发数据库。真实租户归属、维护窗口、备份恢复和切换审批仍需人工处理。

## 验证

- Artifact/Context/异步运行时专项：10/10。
- 完整 A2A、迁移与 schema 回归：310/310，9 条既有弃用警告。
- 静态部署预检：60/60。
- JavaScript SDK：42/42；`A2AV1Part` 已类型化 `raw`、`url`、`filename`。
- Python SDK：49/49；资源方法保持通过。
- OpenAPI：265 paths，已提交文件无漂移。
- Agent Hub 运行矩阵：26/26 用户可见 Agent 为开发环境 launch candidate。
- .NET：Artifact Part 仍由 `JsonElement` 完整承载；本机无 `dotnet`，未声称编译通过。

## 仍开放的差距

1. 当前 Corti 公开文档和 A2A v1 只要求服务端生成的 opaque string ID；此前“Corti 要求类型前缀 UUIDv7”的判断证据不足，已从差距矩阵撤回。
2. 没有生产对象存储、上传/下载授权、病毒扫描、DLP、保留期和跨区域复制证据。
3. 迁移 `050` 前旧 Task 使用兼容投影，不是经 `a2a_task_artifacts` 回填的持久记录。
4. 没有 Corti 私有租户或第三方 A2A SDK 的线上互操作证明。
5. `.NET`、PostgreSQL 多副本、生产队列、跨进程取消和真实 Provider 物理中止仍需外部环境。
6. 26-Agent 真实模型质量、医院接口、患者授权、云基础设施、法务、认证和独立临床验收仍未通过。

机器证据目录：`reports/agent_hub/task_owned_artifacts_phase_20260822/`。
