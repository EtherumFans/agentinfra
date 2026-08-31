# OAuth Client Agent 与用途委托阶段总结（2026-08-22）

本阶段关闭了 OAuth `client_credentials` 可在租户内调用任意 Agent、且 Connector 节点用途没有与 Client 授权绑定的缺口。结果限定为开发环境上线候选：API Client 现在必须同时拥有运行 scope、精确 Agent 白名单和明确用途授权；已签发 token 不能保留被撤销的权限，也不能通过请求体扩大授权。

## 已完成

- `oauth_clients` 持久保存 `allowed_agent_ids` 与 `allowed_purposes`；空列表默认拒绝 Agent Run，不支持通配符。
- Agent 白名单只接受当前可执行官方 Agent 或同租户自定义 Agent 的精确 ID；未知或跨租户 ID 以非枚举方式拒绝。
- 可委托用途限定为 `treatment`、`payment`、`healthcare_operations`、`quality_improvement`、`research`、`public_health`；内部 `system_operations` 不可授予外部 Client。
- Agent Run 对机器 Client 强制要求顶层 `purpose_of_use`，先检查精确 Agent，再检查用途；Console 用户运行继续使用服务端默认 `treatment`。
- 每次 Bearer token 使用都从数据库重新读取 Client 的 Agent/用途授权，因此授权替换、清空、Client 禁用、scope 缩减或 owner 成员撤销立即生效，不等待 token 到期。
- Connector Executor 再次检查机器调用的委托主体与用途授权，防止绕过 Agent Run 直接调用 Graph；每个 Graph 节点仍使用服务端持久配置的用途，客户端不能覆盖。
- `run_history` 记录权威 `api_client_id`、`delegated_subject_id` 和 `purpose_of_use`；`connector_execution_audit` 记录排序后的 `granted_purposes`，不记录正文、token 或 secret。
- 持久 Memory 继续只接受用户 actor；机器 Client 即使有委托主体、scope 和 `treatment` 用途也不能代用户访问长期记忆。
- Console API Client 页面可在创建时填写精确 Agent ID 和用途，并明确显示授权缺失时“运行默认拒绝”；JavaScript、Python、.NET SDK 与 OpenAPI 已同步。

## 安全反例

自动化覆盖了通配符、未知 Agent、保留用途、跨 Agent 调用、缺失用途、伪造未授权用途、已签发 token 后撤销 Agent、已签发 token 后撤销用途、Client scope/启用状态变化、owner 成员撤销、Connector 缺少委托主体、Connector 用途不匹配、请求体伪造 Client ID，以及机器访问 Memory。

成功的机器 Run 会在 `run_history` 中保存 Client、委托用户和用途；失败调用在 Provider/Connector 执行前拒绝。Connector 拒绝以稳定错误码和 `policy_decision=deny` 进入审计。

## 数据库迁移

源码 Alembic head 为 `049`：

- `oauth_clients.allowed_agent_ids`、`oauth_clients.allowed_purposes`；
- `run_history.delegated_subject_id`、`run_history.purpose_of_use` 及索引；
- `connector_execution_audit.granted_purposes`。

迁移只在 `reports/agent_hub/oauth_delegation_phase_20260822` 下的固定隔离临时 SQLite 库验证，完成 `048 → 049 → 048 → head`，列增删与 revision 均符合预期，随后删除临时库。没有修改开发库。开发库仍是历史 `041`/`create_all` 混合状态，受控重启新源码前必须先做 schema/version reconcile。

## 验证结果

| 范围 | 结果 |
|---|---:|
| OAuth/API Client、Run、Connector、Graph、Memory 相关后端回归 | 87/87 |
| OpenAPI 运行时/快照合同 | 7/7 |
| JavaScript SDK | 41/41 |
| Python SDK | 48/48 |
| 前端测试 | 134/134 |
| 前端生产构建 | 通过 |
| .NET SDK | 源码已同步；本机无 `dotnet`，待 CI |
| OpenAPI | 260 paths，807,143 file bytes，漂移检查通过 |
| Alembic 049 round-trip | 通过，临时库已删除 |

全部自动化均显式清空 `ICODER_CREDENTIAL_LLM`，使用 `LLM_PROVIDER=mock` 且禁止外部 LLM。本阶段没有调用真实 DeepSeek，也没有把密钥写入测试、日志或阶段证据。机器证据见 [`phase_evidence.json`](../../reports/agent_hub/oauth_client_delegation_phase_20260822/phase_evidence.json)。

## 后台退出诊断

用户提供的日志中，最后一次 HTTP trace 查询已返回 `200 OK`；SQLAlchemy 的 `ROLLBACK` 是只读事务结束，不是故障。真正异常是随后 `uvicorn exited with code -1`，启动脚本因非零退出码抛出异常。核对时可见 PowerShell 仅停留在 `iCoDer backend shell ready`，没有 `uvicorn` 进程，也没有 `8000` 监听。mock 回归连续运行未复现内存访问异常。

因此当前证据只能确认旧进程异常退出，不能仅凭这段日志判定是“内存不可读”或“内存不可写”。Windows 原生 BGE 栈仍按已知风险禁用；在开发库 reconcile 前不重启新源码或真实 LLM 后端。

## 与 Corti 的剩余差距

- 每 Client Agent/用途的本地授权与审计已闭环，但尚无 Corti 托管身份系统、对端 token exchange、云 KMS/Secret Manager、策略多副本一致性和生产撤销 SLA 证据。
- 患者 PHI 的权威 consent 仍未开放给机器委托；医院身份、患者授权、用途证明、留存与法务依据必须由外部系统提供。
- DrugBank/POSOS/Web Search、经验证 semantic Memory、原生 MedCodER Worker/FAISS API E2E、生产队列/多副本和真实远端互操作仍未完成。
- 26-Agent 真实模型质量矩阵、临床 reviewer、医院验收、中国权威编码/DRG-DIP 数据授权、等保/个保/法务/云/SRE/认证门禁仍未通过。

下一项开发优先级保持为隔离 MedCodER Worker 的索引/API E2E 与剩余真实 Connector/Agent 执行接线；开发库 reconcile、.NET CI、PostgreSQL 多副本和医院/云/法务门禁分别保留为部署或外部任务。
