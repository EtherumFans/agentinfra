# iCoDer Feedback 训练用途独立授权阶段总结（2026-08-22）

> 声明：本阶段建立的是训练用途的独立、默认拒绝授权门禁，不是训练数据导出或模型训练能力。Task、Message、模型输入/输出、临床正文和 feedback reason 均不在授权范围；真实患者/医院授权、法务依据、去标识质量和模型训练治理仍未通过。

## 结论

普通 Task/message feedback 与 `automatedEvaluation` 现在都明确不构成训练许可。只有当前组织的 owner/admin 能对一条反馈的精确存储快照创建独立授权；授权固定为 `quality_improvement`、固定为 `feedback_metadata_only`、最长 30 天，并要求显式 `acknowledgement=true` 和不含患者标识的审批引用。审批引用只保存 SHA-256，公共响应不回显引用或 reason。

授权记录绑定反馈摘要；反馈更新、软删除、Context 硬删除和 retention purge 会撤销或物理删除授权。授权与撤销使用 tenant-owned、失败关闭审计：审计写入失败会使同一事务回滚。项目仍没有训练导出端点，因此不存在通过该授权读取 Task、Message、prompt、output 或 reason 的路径。

## 实现

- Alembic `054` 新增 `feedback_training_authorizations`，包含 tenant/context/task/feedback 归属、固定用途/数据范围、反馈摘要、审批引用哈希、授权人、版本、状态、到期和撤销时间。
- `PUT/GET/DELETE .../feedback/{feedback_id}/training-authorization` 提供 owner/admin 专用授权生命周期。
- 授权只对未删除且属于同一 tenant/context/task 的精确 feedback 生效；非 owner/admin 返回 403，缺失/跨租户反馈统一 404。
- `expiresAt` 必须含时区、至少晚于当前五分钟且不超过 30 天。
- feedback 更新即撤销现有授权，避免旧审批覆盖新评分、标签或 reason；feedback 删除、Context 删除和 retention 同步清理。
- JavaScript、Python、.NET SDK 源码同步 authorize/get/revoke 调用面；三套 README 明确授权范围和非训练声明。
- 部署预检新增 `feedback_training_requires_independent_bounded_owner_authorization`，同时检查模型、迁移、API、失败关闭测试、tenant audit 和三 SDK 源码。

## 验证

- 后端授权、生命周期与部署预检聚焦：**8/8**。
- Feedback、Context、retention、组织角色、OAuth/API Client 与预检扩大串行回归：**96/96**，3 条为测试客户端/日期 API 弃用警告。
- JavaScript SDK：**43/43**，TypeScript build 通过。
- Python SDK：**50/50**。
- .NET SDK 源码与合同测试已同步；本机无 `dotnet/csc/msbuild`，不记为编译通过。
- 临时空库迁移：`053→054→053→054`；精确临时候选文件已删除。
- 当前 `041` 开发库只读影子重建至 `054`：6,090 行既有数据全保留，候选完整性通过、外键错误 0、69 张数据表/1,008 列 ORM 漂移 0；首次 staging 捕获 `created_at/updated_at` server default 漂移 2 项，修复后最终通过。源库 SHA-256 不变，未 cutover。
- OpenAPI：**270 paths、290 schemas、851,708 file bytes**，drift check 通过。
- 静态部署候选预检：**73/73**。
- 未启动独立后端，未使用真实 LLM/ASR，未加载 Windows 原生 MedCodER。

## 对 Corti 与中国场景的判断

Corti 的公开 feedback 能力不应被推断为数据训练许可。本阶段补的是 iCoDer 中国医疗治理增强：把产品质量反馈与模型改进用途拆成两个可撤销资源，并默认禁止临床内容进入训练链。这降低了“点击反馈即默认同意训练”的合规风险，但不能替代《个人信息保护法》/医院制度下的合法性基础、患者或数据控制者授权、伦理审批和不可逆训练后的删除影响评估。

## 仍开放

1. 没有训练数据导出、去标识临床语料包、训练流水线或模型权重更新；当前授权仅允许 feedback metadata eligibility。
2. 若未来需要输入/输出或 reason，必须另建患者/医院权威授权、独立 DLP/去标识验证、用途与保留期、导出审批、不可逆训练影响说明和完整 lineage，不能扩大本合同。
3. PostgreSQL 多副本并发、Cloud Secret Manager/KMS、生产 audit sink、.NET CI、真实医院/法务/伦理/认证及独立 reviewer 仍是外部门禁。

机器证据目录：`reports/agent_hub/feedback_training_authorization_phase_20260822/`。
