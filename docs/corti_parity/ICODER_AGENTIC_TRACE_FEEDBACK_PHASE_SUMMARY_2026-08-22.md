# Agentic Context Trace 与 Task Feedback 阶段总结（2026-08-22）

本阶段依据 2026-08-22 再次可访问的 Corti 官方文档，完成当前契约的 Context trace export
和调用方隔离 feedback。核验纠正了旧本地设计：官方路径是单数
`GET /v2/agentic/contexts/{context_id}/trace`；消息反馈不使用独立 message 路径，而是在统一
`/contexts/{context_id}/tasks/{task_id}/feedback` 资源中用 `target.messageId` 指定目标消息。

当前结论：**这两项能力已达到开发环境上线候选，并关闭 Agentic v2 对照中的 OpenInference
Context trace 与 task/message feedback 开发 P1 缺口；它不代表 Corti 全能力、临床质量、云
生产或医院上线等价。**

官方对照：
[Export traces](https://docs.corti.ai/agentic/guides/export-traces)、
[Submit feedback](https://docs.corti.ai/agentic/guides/submit-feedback)。

## 已完成

- `GET /api/v2/agentic/contexts/{context_id}/trace`：租户隔离、最新优先、`pageSize` 1–200、
  HMAC 签名且拒绝非 canonical 编码的 opaque `pageToken`。
- 每个 Run 确定性投影为 32 位 OpenTelemetry trace ID、一个 16 位 synthetic root span 和
  parent-linked 事件 spans；可输出已有的 tool/connector/model 标识、时延和 token 数值，绝不
  伪造不存在的 token 数据。
- 中国医疗最小必要策略默认不导出原始 prompt、病历正文、模型完整输出、tool 参数/结果、
  credential reference、异常栈或任意内部 metadata。与 Corti 示例可包含 `input.value` 相比，
  这是有意保留的更严格隐私差异，而不是能力遗漏。
- `POST/GET/DELETE /api/v2/agentic/contexts/{context_id}/tasks/{task_id}/feedback`：当前 Corti
  已开放的 binary 0/1、官方 label 白名单、最多五个 label、重复拒绝、`other` 强制 reason、
  `target.messageId` 所属 Task 校验、GET 仅返回当前调用方、DELETE 幂等删除调用方在 Task 下
  的全部反馈。
- 同一 actor/target 重复 POST 幂等更新；数据库唯一约束与并发冲突重读阻止重复活跃记录。
- reason 先做 PHI redaction，再使用既有 versioned Fernet key lifecycle 加密；metadata 固定
  schema，外部 actor/client reference 只保存 SHA-256，不保存姓名、邮箱、MRN 或原始标识。
- 新增 `feedback:read`、`feedback:write` 与既有 `traces:read` OAuth 能力 scope；用户 JWT
  维持组织成员校验，API Client/runtime token 按 scope 失败关闭。
- 新增 Alembic `046` 的 `agent_task_feedback`；默认 90 天 retention，dry-run-by-default
  operator CLI；Context 硬删除会立即物理清除反馈，独立于 SQLite FK pragma。
- trace export 与 feedback create/update/list/delete 均进入最小必要审计；审计不记录 reason、
  原始 label 或外部标识。
- OpenAPI 由 253 增至 255 paths；运行时/导出合同明确禁止旧 `/traces` 和独立 message
  feedback 假路径。
- JavaScript `1.0.0-beta.19`、Python `1.0.0b19`、.NET `1.0.0-beta.19` 均加入 trace 和
  feedback 类型化源码合同。本机仅对 JS/Python 执行；.NET 保持外部 CI 编译门禁。

## 验证结果

所有测试显式清空 `ICODER_CREDENTIAL_LLM`、关闭外部 LLM 并禁用原生 MedCodER；未使用用户
DeepSeek 密钥、未调用 Corti 写接口、未调用外部 Connector。

| 验证 | 结果 |
|---|---:|
| A2A/Connector/Run/retention/OpenAPI 联合回归 | 363/363 |
| 新 trace/feedback 集成矩阵 | 4/4（已包含在联合回归） |
| 真实 FastAPI lifespan 启动 | 3/3 |
| Python SDK 全量 | 42/42 |
| JavaScript SDK 全量 + TypeScript build | 35/35 |
| 前端 OpenAPI 路径合同 | 60/60 |
| 三 SDK 版本/候选发布门 | 5/5；统一 `1.0.0-beta.19` |
| OpenAPI | 255 paths；`/trace` GET、feedback GET/POST/DELETE；无漂移 |
| Alembic | `046 → 045` 表消失；`045 → 046` 表恢复；单 head `046` |
| 本地候选制品 | JS `.tgz` + Python `.whl`，SHA-256 清单，未发布 |
| Python compileall / 密钥形状扫描 | 通过 / 0 个文件命中 |
| 收尾进程检查 | 端口 8000 listener 0；uvicorn 进程 0 |

候选清单：
[`LOCAL_RELEASE_MANIFEST_BETA19.json`](../../reports/release-candidate/LOCAL_RELEASE_MANIFEST_BETA19.json)。
清单明确记录 dirty 工作树和 `publication.performed=false`。

## 仍未完成/不得宣称

- Corti 文档示例可导出 `input.value`；iCoDer 中国医疗默认禁止正文出 trace。未来若确需受控
  正文，必须新增高权限、用途声明、独立 retention 与审计，不能弱化当前默认值。
- token、connector、reasoning span 只投影真实已捕获事件；当前不伪造缺失 telemetry，仍需
  扩大所有 Provider/Connector 的标准 OpenInference 属性覆盖率。
- 自动评估入口、feedback 聚合/训练授权、usage v2 对账尚未完成；临床纠错绝不自动等同训练授权。
- .NET `net8.0/net10.0` 本机无 `dotnet/csc/msbuild`，源码与测试已补但未记为编译通过。
- PostgreSQL 多副本、Linux/Docker、生产 KMS/队列、云容量/SLA、医院 HIS/EMR、合法编码资产、
  法务/等保/认证、独立临床 reviewer 和 Corti 同病例盲评仍是外部门禁。

机器可读证据：
[`phase_evidence.json`](../../reports/agent_hub/agentic_trace_feedback_phase_20260822/phase_evidence.json)。
