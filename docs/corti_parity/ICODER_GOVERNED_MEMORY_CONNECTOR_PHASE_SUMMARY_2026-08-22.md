# 受治理持久 Memory Connector 阶段总结（2026-08-22）

本阶段把 Registry 中原有的线程内 `memory.retrieve` 扩展为可持久化的 `memory.remember`、`memory.recall` 与 `memory.forget`，并补齐用户身份、显式授权、用途、租户、加密和到期硬删除合同。结论限定为开发上线候选：这是用户本人对工作偏好和去标识化上下文的长期记忆，不是患者长期病历存储，也不代表医院、隐私、法务或临床准入已经通过。

## 完成内容

- 新增 `memory_consents`：授权固定绑定 `organization_id + user_id + agent_id + purpose_of_use`，合法依据固定为 `user-consent`。
- 只有已认证用户可以通过 `/api/v2/agentic/agents/{agent_id}/memory-consent` 显式授权；请求必须携带 `acknowledgement=true`。API Client、无身份 A2A 与 Agent 参数不能代用户授权。
- 用途仅开放 `treatment`、`healthcare_operations`、`quality_improvement`；授权与留存期限均限制为 1–90 天。
- 运行时 actor 类型与 actor ID 来自认证主体，不从 Agent 输入或请求体的归因字段推断。
- `remember` 在写入前再次执行 PHI/PII 脱敏和提示注入检测；只接受 `non_phi` 或 `deidentified`，拒绝持久化提示注入内容。
- 内容、摘要和 key facts 沿用 PHI Fernet 生命周期加密；条目保存 consent、actor、purpose、retention deadline 与内容摘要，不把原文写入审计。
- 同一用户/Agent/内容使用 SHA-256 摘要确定性去重；Agent 无法提交 consent ID、actor、retention deadline 或数据库 ID。
- `recall` 只查询同租户、同用户、同 Agent、同授权、同用途且未过期的记录；采用确定性 CJK bigram/英文 lexical 检索，不加载已知会导致 Windows native 崩溃的嵌入栈。
- 返回内容标记 `user_memory_untrusted`、非权威和需人工复核；Connector graph 的输出注入检测仍会在下游前再次执行。
- 撤销授权会立即硬删除该授权创建的全部记忆；逐条 `forget` 也使用同一 actor/tenant/agent 边界。
- 通用 retention CLI 已纳入 governed memory：到达每条记录的 `retention_until` 后可 dry-run 或审计化硬删除，同时把已到期授权标记为 `expired`。
- JavaScript、Python、.NET SDK 和 OpenAPI 均加入授权、查询和撤销合同。

## 安全验证

新增集成用例覆盖：显式授权、隐式授权拒绝、跨租户 Agent 拒绝、Fernet 密文落库、手机号脱敏、内容去重、同主体召回、跨租户召回拒绝、API Client 拒绝、提示注入拒绝、到期不可召回、retention dry-run/硬删除、撤销硬删除和授权状态更新。

迁移 `047` 完成两类隔离验证：

- 当前模型建库后，`047 → 046 → 047` 正反向通过；
- 全新空库 `001 → 047` 完整升级通过，最终 head 为 `047`。

开发库曾处于 `create_all` 已提前创建较新表、Alembic 版本仍为 `041` 的混合状态，因此直接执行后续迁移可能遇到“表已存在”。本轮验证期间误用环境变量造成的版本标记已恢复为原值 `041`，没有对开发库执行 047 表结构变更。上线前仍必须先对目标库做 schema/version reconcile，不应盲目运行 Alembic。

## 验证结果

| 范围 | 结果 |
|---|---:|
| Connector 单元/安全/OpenAPI 合同 | 74/74 |
| 共享数据库串行 Connector 集成 | 36/36 |
| Memory 专项集成 | 8/8 |
| Retention 既有回归 | 17/17 |
| 应用启动 E2E | 3/3 |
| JavaScript SDK | 41/41 |
| Python SDK | 48/48 |
| .NET SDK | 源码已同步；本机无 dotnet，待 CI |
| OpenAPI 漂移 | 通过，259 paths |
| Alembic 全新空库及 047 round-trip | 通过 |

全部自动化均显式清空 `ICODER_CREDENTIAL_LLM`，使用 mock/no external LLM；没有使用或输出真实 LLM 密钥。机器证据见 [`phase_evidence.json`](../../reports/agent_hub/governed_memory_connector_phase_20260822/phase_evidence.json)。

## 与 Corti 的剩余差距

- 当前持久记忆只适用于用户本人授权的去标识化工作偏好/上下文；患者 PHI 长期记忆仍缺患者/监护人或医院权威同意来源、撤回传播和病历保存规则，因此继续失败关闭。
- 后续 Semantic Memory 阶段已把受治理路径接到隔离 HTTPS embedding 合同，并完成真实 TCP、加密向量、版本匹配和失败关闭验证；确定性 lexical 仅保留为明确标记的 Local 降级。真实多语言模型质量、生产服务、索引回填和依赖供应链仍未验证，详见 `ICODER_SEMANTIC_MEMORY_PHASE_SUMMARY_2026-08-22.md`。
- 尚无 Console 授权管理 UI、患者级 consent ledger、delegated machine subject、共享团队记忆、分布式 purge 调度和多副本状态验证。
- 启动日志仍显示本地 MedCodER FAISS 索引缺失、部分 Pack 为 metadata-only；这些是 Agent Hub 整体上线差距，不应由 Memory 阶段掩盖。
- DrugBank、POSOS、Web Search、PubMed 合规邮箱实网、真实 Secret Manager、外部 A2A/MCP 互操作、生产队列/多副本仍开放。
- 医院安全、隐私、法务、临床 reviewer、云出口、等保/个保与认证门禁仍未通过。

## 下一开发优先级

下一项开发 P0 是 delegated machine subject/scope：让受控 API Client 只能代表明确用户和明确 Agent/用途调用，并保持不可自行授权。随后处理 MedCodER 索引/隔离 Worker E2E、metadata-only Agent 的真实执行接线，以及仍需许可或隐私合同的外部 Registry。
