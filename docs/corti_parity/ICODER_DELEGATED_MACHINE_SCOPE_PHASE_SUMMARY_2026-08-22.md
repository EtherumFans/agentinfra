# 委托机器主体与受限 Medical Coding Connector 阶段总结（2026-08-22）

本阶段关闭了 Agent Run 中“客户端请求体可自报 API Client 身份”的高风险旧合同，并把已验证的 OAuth Client 身份、委托用户和 scope 传入 Connector Graph。结论限定为开发上线候选：机器身份与三项医疗工具的最小权限链已闭环，但还没有每个 API Client 独立的 Agent allowlist、purpose grant、医院生产审批或临床质量证明。

## 完成内容

- `client_credentials` token 不再只依赖签名 JWT：每次使用都会复核 token hash/撤销状态、当前 OAuth Client 的租户和启用状态、owner 一致性、owner 用户启用状态、owner 当前租户成员关系，以及 token scope 是否仍是 Client 当前 scope 的子集。
- 已签发 token 对应的 Client 被禁用、scope 被缩减或 owner 被移出租户后立即失败关闭，不等待五分钟 token 自然到期。
- `AgentRunRequest.api_client_id` 只保留弃用期解析兼容，身份、归属、计费、RunHistory、Trace 和 partner 签名均忽略它；权威 `api_client_id` 只来自验证后的 Bearer token。
- Console runtime preview token 继续按用户会话处理，不再被误分类为机器 API Client。
- 浏览器 Agent Chat 删除 API Client 归属下拉框；TypeScript、前端 Runtime API 和 .NET SDK 删除可自报字段。Python SDK 本来就没有该便捷字段。
- `ConnectorInvocation` 和 Graph 增加服务端 `delegated_subject_id` 与 `granted_scopes`，机器调用以 OAuth Client 为 actor、Client owner 为委托主体。
- `medical-coding` Registry 的 `validate_codes`、`evaluate_compliance`、`check_documentation_gaps` 分别强制 `coding:validate`、`compliance:evaluate`、`documentation:check`；错误 scope 拒绝，精确 scope 可执行。
- Client 创建/更新与 OAuth capability allowlist 已加入上述三项 scope。
- 持久 Memory 仍拒绝机器 actor，即使请求带委托主体或伪造 Memory scope；机器不能代用户授予、写入、召回或删除长期记忆。
- `connector_execution_audit` 通过迁移 `048` 持久保存 actor type/ID、delegated subject 和排序后的 granted scopes，不保存输入正文、输出正文、token 或 secret。
- 修复 `evaluate_compliance` 的 MCP 注册表契约：真实 Agent 返回 `review_conclusion/issues_found/compliance_checks`，其中 checks 是命名布尔映射；Markdown 同时兼容真实映射和旧列表渲染。

## 安全验证

新增或更新的反例覆盖：请求体客户 ID 伪造、runtime preview 身份混淆、Client 禁用、scope 缩减、owner 租户成员撤销、错误医疗 scope、三个精确医疗 scope、机器访问 Memory、权威身份/委托主体/scope 进入 Graph，以及上述授权上下文持久审计。

迁移在固定隔离临时库中完成：

- 全新空库升级至 `047`，再升级 `048`；
- 核对四个授权审计列存在；
- `048 → 047 → 048` 正反向通过；
- 临时数据库已删除。

当前开发库 `backend/data/icoder.db` 只读检查仍为 Alembic `041`，且没有 048 审计列。本阶段没有修改或 stamp 该库。该库存在历史 `create_all` 与 Alembic 版本混合状态，上线或重启到新源码前必须先做 schema/version reconcile，不能直接盲目执行 `upgrade head`。

## 验证结果

| 范围 | 结果 |
|---|---:|
| 后端相关单元/API/集成/启动回归 | 137/137 |
| Connector Graph 全量数据库集成 | 16/16 |
| OAuth live-state/membership | 16/16 |
| 前端专项测试 | 2/2 |
| 前端生产构建 | 通过 |
| JavaScript SDK | 41/41 |
| Python SDK | 48/48 |
| .NET SDK | 源码已同步；本机无 `dotnet`，待 CI |
| OpenAPI 漂移 | 通过，259 paths，802,027 bytes |
| Alembic 空库及 048 round-trip | 通过 |

全部自动化都显式清空 `ICODER_CREDENTIAL_LLM`，使用 mock/no external LLM；本阶段没有使用或输出真实 LLM 密钥。机器证据见 [`phase_evidence.json`](../../reports/agent_hub/delegated_machine_scope_phase_20260822/phase_evidence.json)。

## 与 Corti 的剩余差距

- 当前委托主体固定为 OAuth Client owner，scope 对租户内该 Client 全局生效；仍缺每个 Client 的 Agent allowlist、明确 purpose-of-use grant、委托授权撤销台账和管理员 UI。
- 当前只为三个本地 Medical Coding Registry 操作打通 scoped execution；外部 MCP/A2A 的对端 token exchange、Corti 托管运行时互操作和分布式策略状态仍未实测。
- 患者长期 PHI Memory 仍失败关闭；本阶段没有放宽用户 consent、患者/医院权威授权、用途或留存边界。
- 正在监听的可见后端是本轮修改前启动的旧进程，且开发库未迁移；在 reconcile 与受控重启前不能把本阶段能力视为该进程已生效。
- 本地原生 MedCodER FAISS/隔离 Worker E2E、部分 metadata-only Pack 的真实执行接线、DrugBank/POSOS/Web Search、真实 Secret Manager、生产队列/多副本仍开放。
- 医院安全、隐私、法务、临床 reviewer、云出口、等保/个保和认证门禁仍未通过。

## 下一开发优先级

下一项开发 P0 是为 OAuth Client 增加显式 Agent allowlist 与 purpose-of-use delegation，并保持 Memory consent 不可委托；随后闭环隔离 MedCodER Worker 的索引/API E2E 和剩余 metadata-only Agent 的真实执行接线。开发库 reconcile、.NET CI、PostgreSQL 多副本与医院/云/法务门禁分别保留为部署或外部任务。
