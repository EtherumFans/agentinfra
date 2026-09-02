# P1 Wave 5 Phase 7.1：不可变审计发布闭环审查报告

- 日期：2026-09-02（Asia/Shanghai）
- 分支：`codex/p1-security-multitenant-gates`
- 前置候选基线：`p1-wave5-phase7-candidate-20260902` / `15352a04`
- RLS/OAuth 权限修复：`159fded4`
- S3 Object Lock 适配器：`a030b326`
- 审计对账与告警：`71266b5e`
- revision 073 PHI 轮换兼容：`d6439189`
- S3 控制面验证：`44d51143`
- CI 门禁：`7be5dcb7`
- 候选标签：`p1-wave5-phase7-1-candidate-20260902`
- 最终数据库：revision `073`，83 tables，9 public functions
- 结论：Phase 7.1 的代码、迁移、权限模板、自动门禁和本机 PostgreSQL 验证已完成；真实 AWS 账号上的写入与跨区域灾备仍是外部部署验收项。

## 1. 完成范围

| 工作项 | 状态 | 结果 |
|---|---|---|
| 既有 RLS 红项 | 已关闭 | 扩大回归由 1 failed 恢复为全绿 |
| 用户 membership bootstrap | 已完成 | 未验证 org claim 不再提前成为正式 RLS authority |
| OAuth credential bootstrap | 已完成 | token/client/org/owner/membership/active/expiry 一次性布尔校验 |
| revision 073 | 已完成 | 两个最小披露 SECURITY DEFINER 函数 |
| S3 Object Lock adapter | 已完成 | COMPLIANCE、VersionId、checksum、SSE-KMS、条件 PUT、写后复验 |
| 独立 IAM 边界 | 已完成模板 | writer 无 delete/bypass/bucket-policy/Legal-Hold 管理权限 |
| 控制面 verifier | 已完成 | STS identity、owner、versioning、retention、跨区复制 |
| reconcile worker/CLI | 已完成 | 修复 archive lag，检测 pending 和 head divergence |
| PR CI | 已更新 | revision 073、S3 contract、reconcile、真实 PG membership 测试 |
| 真实 AWS 演练 | 未执行 | 缺少用户提供的 AWS account、bucket、KMS、replica 和 credentials |

## 2. RLS 权限红项修复

### 2.1 原问题

Phase 7 扩大回归唯一失败为：

`test_stale_membership_never_becomes_database_authority`

旧实现先把 JWT `org_id` 写入 `icoder.current_organization_id`，再读取受 FORCE RLS 保护的
`organization_members`。该流程能够把查询范围限制到候选 tenant，但在 membership 被证明前已经调用
正式 tenant binder，与“JWT claim 是上下文提示而非数据库权限”的安全契约冲突。

OAuth client path 存在同类问题：先绑定 token 的 org claim，再验证 token、client、owner 和 membership。

### 2.2 revision 073

revision 073 新增：

- `icoder_user_has_active_membership(user_id, organization_id) -> boolean`；
- `icoder_oauth_credential_is_active(token_hash, client_id, organization_id, owner_id) -> boolean`。

两个函数均：

1. 由 migration role 所有；
2. 使用固定 `search_path=pg_catalog,public`；
3. 只返回 boolean，不返回 tenant ID、membership、token 或 client 行；
4. 在函数内部保存当前 tenant setting；
5. 临时设置候选 org，仅用于精确 FORCE RLS 查询；
6. 正常和异常路径都恢复原 setting；
7. app role 有 EXECUTE，PUBLIC 无 EXECUTE。

应用只有在 boolean 为真后才调用正式 `bind_tenant_to_transaction`。OAuth 校验同时覆盖 token hash、
revocation、expiry、client active、owner attribution、owner active、organization active 和实时 membership。

### 2.3 PostgreSQL 实证

真实 app/migration 角色测试证明：

- 有效 membership 和 credential 返回 true；
- forged user、forged org 返回 false；
- 调用前后 `current_setting('icoder.current_organization_id', true)` 仍为空；
- app role 在未绑定 tenant 时直接读取 `organization_members` 得到 0 行；
- 两个函数 owner 均为 `icoder_p1_migration`；
- `icoder_p1_app` EXECUTE=true；
- PUBLIC EXECUTE=false。

## 3. S3 Object Lock 生产适配器

### 3.1 写入安全属性

每条 audit record 和 checkpoint 使用确定性 object key。适配器调用 S3 `PutObject` 时强制：

- `IfNoneMatch="*"`；
- `ObjectLockMode="COMPLIANCE"`；
- retain-until 不低于配置保留期；
- SHA-256 checksum；
- `ServerSideEncryption="aws:kms"`；
- 完整 KMS key ARN；
- expected 12 位 bucket owner；
- 非空 S3 VersionId。

成功或幂等冲突后会 HEAD 精确 VersionId，复验 mode、retention、Legal Hold 和 SSE-KMS。verify/export
读取时会再次进行同样的远端保护校验，防止后来出现未锁定或错误 KMS key 的最新版本。

AWS 官方文档说明 Object Lock 依赖 Versioning，COMPLIANCE mode 在保留期内连 root user 也不能删除
受保护 object version；Legal Hold 与 retention 相互独立。PutObject 使用 retention 时需要 checksum，
`If-None-Match: *` 在 key 已存在时返回 412。参考：

- [AWS S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [AWS PutObject API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html)
- [AWS S3 API required permissions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-with-s3-policy-actions.html)

### 3.2 IAM 分离

writer policy template 只允许指定 bucket/prefix 的读、条件写、retention 以及指定 KMS key 的
GenerateDataKey/Decrypt，并显式 Deny：

- DeleteObject / DeleteObjectVersion；
- BypassGovernanceRetention；
- DeleteBucket；
- 修改 bucket policy、versioning 或 Object Lock configuration。

writer 不具有 `PutObjectLegalHold`。Legal Hold 必须由独立合规身份管理，防止日常归档身份同时具有
解除 hold 的能力。模板包含部署占位符，不能不经替换和云安全审查直接应用。

### 3.3 控制面验证

`verify_soft_hsm_s3_archive.py` fail closed 核对：

- 当前 STS ARN 与配置精确一致；
- expected bucket owner；
- Versioning=Enabled；
- ObjectLockEnabled=Enabled；
- bucket default mode=COMPLIANCE；
- default retention 不短于应用保留期；
- 至少一个 Enabled replication rule 指向指定跨区域 bucket ARN。

## 4. Reconcile 与告警

`reconcile_soft_hsm_ops_audit.py` 使用本地 signed spool 作为待复制输入，WORM 仍是长期权威副本：

- archive 落后时幂等补齐 records/checkpoint，并做强制 post-verify；
- archive 与 local 同序号不同 head 时拒绝自动覆盖；
- archive 超前时要求从权威归档恢复本地 spool；
- 超过阈值的 `started` 无 `completed/failed` 输出
  `HSM_AUDIT_STARTED_WITHOUT_TERMINAL`，退出码 2；
- 报告只包含 sequence、age、operation、path hash 和 change ticket，不包含 PHI、key 或异常文本。

CI 使用阈值 0 验证正常 create 的 started/completed 已闭合且 checkpoint lag 为 0。生产建议每分钟执行，
将退出码和 JSON alerts 接入独立监控系统。

## 5. PHI 轮换兼容

新增 revision 073 后，`rotate_phi_envelopes.py` 和 `rewrap_phi_deks.py` 已从“只接受 072”调整为接受
兼容的 `072/073`。populated rollback 测试仍经过 `073 → 072 → 070 → 073`，并确保结束时数据库恢复
到 head，而不是遗留在 072。

## 6. 验证结果

### 6.1 本地安全扩大回归

```text
128 passed in 6.59s
```

覆盖 PHI revision 071/072、revision 073、AWS IAM contract、应用审计、OAuth rejection、配置
fail-closed、软件 HSM、local/S3 WORM、checkpoint、reconcile 和原 RLS 红项。Phase 7 的
`117 passed, 1 failed` 已恢复为全绿。

### 6.2 真实 PostgreSQL 联合回归

```text
12 passed in 22.02s
revision=073
tables=83
public_functions=9
```

覆盖 PHI envelope、HSM online rotation、073→070→073 populated rollback、P1 RLS attack 和新的
membership/OAuth bootstrap 攻击测试。

### 6.3 角色权限核验

```text
icoder_oauth_credential_is_active | owner=icoder_p1_migration | app_execute=true | public_execute=false
icoder_user_has_active_membership | owner=icoder_p1_migration | app_execute=true | public_execute=false
public functions=9
```

### 6.4 兼容性与静态验证

- Phase 6 软件 HSM 灾备演练：全部场景通过；
- Python compileall：通过；
- boto3 `1.43.84` 安装和导入：通过；
- CI YAML parse：通过；
- IAM template JSON parse：通过；
- `git diff --check`：通过。

## 7. 未执行与不可伪造的证据边界

本机没有可由用户授权使用的 AWS account、Object-Lock-enabled bucket、KMS key、replica bucket 或
AWS credentials，因此没有进行真实 PutObject、retention delete denial、Legal Hold、region loss 或
cross-region restore。单元测试使用严格假客户端验证参数、返回值和故障语义，但不能替代 AWS 账单中
的 CloudTrail、object version、replication status 和恢复证据。

GitHub 托管 PR CI 也必须在推送分支或创建 PR 后才会产生远端执行结果。本报告不会把本地 YAML 解析
描述成远程 CI 已通过。

## 8. 目录与敏感数据卫生

- 没有把 AWS credential、测试 key、audit object、checkpoint 或 export 写入仓库；
- boto3 安装在已有 `.venv`，该目录保持 git ignored；
- PostgreSQL 测试使用随机 ID，并在 finally 清理 user/org/member/client/token；
- 新增入库内容限于 migration、services、scripts、tests、IAM template、runbook 和本报告；
- 未新增截图、缓存、数据库文件、构建目录或重复测试报告。

## 9. 剩余发布门禁

1. 在目标 AWS account 创建独立 source/replica buckets，启用 Versioning、Object Lock COMPLIANCE 和
   KMS；部署经审查的 writer policy。
2. 使用部署 writer 运行 `verify_soft_hsm_s3_archive.py`，保存 STS/bucket/replication 输出。
3. 写入一次性 canary audit lifecycle，验证 CloudTrail、VersionId、checksum、retention 和 replica。
4. 用无 delete 权限 writer 与独立合规身份分别验证删除拒绝和 Legal Hold。
5. 模拟 source region 不可用，从 replica 重建 spool 并验证多代 signing key 历史。
6. 将 reconcile JSON/exit code 接入 PagerDuty、CloudWatch 或既有监控平台；当前仓库没有选定告警平台。
7. 若法规要求严格公开不可抵赖，将共享 HMAC audit signer 升级为 HSM 非对称签名和可信时间戳。

## 10. 发布判断

Phase 7.1 已关闭代码层和本机数据库层的发布红项，并提供可实际调用的 S3 Object Lock 生产适配器、
最小权限模板、控制面 verifier、reconcile/alert contract 和 PR 门禁。由于真实 AWS 资源与凭据不在
本工作区，最终生产发布仍必须由第 9 节的环境证据解除；在取得这些证据前，状态应标记为
“implementation ready / environment gate pending”，而非“production verified”。
