# PHI 软件 HSM、v1→v2 轮换、备份/WAL 扫描与回退手册

适用 schema：revision 073（PHI envelope 存储契约由 revision 072 建立）。本文中的 `software_hsm` 只模拟 KMS/HSM 的
wrapped-DEK 接口，不提供硬件隔离、抗侧信道、密钥不可导出认证或正式合规证明。

## 1. v2 envelope

每个非空 PHI 值使用独立随机 256-bit DEK 和 AES-256-GCM 加密。DEK 由软件
HSM 的 KEK 再次使用 AES-256-GCM 包装。数据库只保存：

- `v2:` 版本前缀；
- 算法与 schema 标识；
- KEK key ID；
- 数据 nonce、PHI ciphertext、wrapped DEK。

KEK 不进入数据库 envelope。v2 metadata、key ID 和算法作为 AAD 参与认证。
明文 DEK 使用后进行 best-effort 内存覆盖；Python 软件进程不能提供硬件级内存保证。

## 2. 演练配置

单 KEK 环境变量只允许本地开发和兼容测试，不得用于 cloud 模式：

```dotenv
ICODER_PHI_KEY_PROVIDER=software_hsm
ICODER_SOFT_HSM_KEY_ID=soft-hsm-kek-v1
ICODER_SOFT_HSM_MASTER_KEY=<base64url encoded 32 bytes>
ICODER_PHI_ENCRYPTION_KEY_V1=<legacy Fernet key, rotation window only>
P1_POSTGRES_MIGRATION_DATABASE_URL=<migration-role URL>
```

cloud 模式使用第 7 节的加密密钥库。bootstrap key 必须通过独立 secret injection 提供，
不得与密钥库文件保存在同一 volume、备份或配置对象中。

生产接入真实 KMS/HSM 时应保留 `KeyWrappingProvider` 边界，将
`generate_data_key`/`unwrap_data_key` 替换为供应商 API，并使用 workload identity、
精确 key policy、独立审计日志和区域内密钥。

## 3. 在线 v1→v2

部署顺序不可调换：

1. 备份并完成第 5 节的明文 canary 扫描。
2. 升级数据库到 072；此时 71 个约束同时接受 v1 和 v2。
3. 部署 dual-reader/v2-writer 应用，确认生产启动门禁通过。
4. dry-run：`python scripts/rotate_phi_envelopes.py --target v2`。
5. 执行：`python scripts/rotate_phi_envelopes.py --target v2 --execute --batch-size 200`。
6. 重复 dry-run，直至 `values=0`。
7. 用原始 SQL 抽样确认目标列为 v2，应用仍能读取；不得输出明文。
8. 观察完整发布窗口后移除 `ICODER_PHI_ENCRYPTION_KEY_V1`。

轮换使用数据库 advisory lock 防止两个 operator 同时运行，逐租户遵守 FORCE RLS，
以小事务和 `FOR UPDATE SKIP LOCKED` 更新。进程中断后可直接重跑；已完成的 v2 行会跳过。
在轮换开始前必须先部署 v2 writer，否则仍写 v1 的旧实例会使轮换无法收敛。

## 4. populated JSON 生产兼容回退

revision 070 应用不能读取 071/072 的 opaque encrypted JSON。回退必须进入维护窗口，
不能把 schema downgrade 当作完整应用回退。

1. 停止所有应用 writer，确认任务队列、worker 和连接中的事务均已排空。
2. 保留软件 HSM 配置和 legacy v1 key。
3. 将 v2 反向转为 v1：
   `python scripts/rotate_phi_envelopes.py --target v1 --execute --maintenance-confirm REVERSE_TO_V1`。
4. dry-run 确认 v2 `values=0`。
5. 执行 `alembic downgrade 070`。072 在仍有 v2 时会拒绝降级。
6. 预检：`python scripts/prepare_phi_070_compatibility.py`。工具会解密并解析全部目标值，但不写入。
7. 明确批准临时恢复 PHI 明文后执行：
   `python scripts/prepare_phi_070_compatibility.py --execute --maintenance-confirm RESTORE_070_SEMANTICS --acknowledge-plaintext-at-rest`。
8. 验证 JSON 顶层类型恢复为 object/array，文本字段恢复旧应用语义。
9. 重新运行备份/WAL 扫描；此回退状态预期含 PHI 明文，备份必须进入受控隔离并缩短保留期。

Clinical Facts 和 Guided Document/Section 在 070 已有显式 repository 加密，兼容工具会保留
这 7 列的密文。其余 revision 071 才引入透明类型的文本与 JSON 会恢复为旧版表示。

重新前进到 072：

1. 在 070 上运行 `backfill_phi_envelopes.py --execute`，固定恢复为 v1 envelope；
2. 升级到 072；
3. 部署 v2 writer；
4. 再次执行在线 v1→v2；
5. 完成备份/WAL 零命中扫描。

## 5. 备份与 WAL 明文扫描

使用非真实患者的唯一 canary 走完整 PHI 写路径。canary 文件是受控敏感操作输入，扫描器
只输出其 SHA-256 截断标识、文件 offset 和 artifact digest，不回显 canary。

```text
1. 创建一次性 canary JSON 数组文件
2. 通过应用写入 canary PHI，确认数据库原始值为 v2
3. 生成 plain-format pg_dump；custom/compressed dump 必须先在隔离目录展开
4. 切换 WAL，并复制包含 canary 事务的已完成 WAL segment
5. 执行：python scripts/scan_phi_artifacts.py <dump> <wal> --sentinel-file <json>
6. 只有 status=passed 且 finding_count=0 才能继续发布
7. 安全删除 canary 行、输入文件、展开的 dump 和 WAL 副本
```

scanner 会搜索 UTF-8、UTF-16LE、UTF-16BE，并处理跨 1 MiB 分块边界的匹配。退出码 2
表示发现明文。加密或压缩前的 staging 文件、`pg_restore` 输出、逻辑复制落地文件和导出报告
也必须纳入路径。canary 零命中证明目标写路径没有把该 canary 写入 artifact；它不能替代
DLP、访问控制、备份加密、WAL 归档加密和定期人工审查。

## 6. 发布阻断条件

- 072 约束数不是 71；
- v2 writer 无法读取 v1；
- forward dry-run 在稳定窗口持续出现新的 v1；
- 任意目标行无法认证或解密；
- 备份/WAL finding count 非零；
- 反向轮换后仍有 v2；
- 070 compatibility dry-run 无法解析任一 JSON；
- 未排空 writer 就请求 plaintext compatibility execute；
- 软件 HSM 被误称为真实生产 HSM。

## 7. v2 KEK 在线轮换（只重包裹 DEK）

Phase 4 使用一个受严格校验的 keyring 管理多个 KEK。配置必须恰好有一个 `active`，旧 KEK
只能是 `decrypt-only`；`retired` 和 `revoked` 均拒绝解包。Phase 5 将 keyring 保存为
AES-256-GCM 认证加密文件，文件中不出现可搜索的 key ID 或 KEK。运行时配置：

```dotenv
ICODER_SOFT_HSM_KEYSTORE_PATH=/run/secrets/icoder/software-hsm.keys
ICODER_SOFT_HSM_BOOTSTRAP_KEY=<base64url 32 bytes, injected separately>
ICODER_SOFT_HSM_MIN_GENERATION=1
ICODER_SOFT_HSM_REQUIRE_ENCRYPTED_KEYSTORE=true
ICODER_SOFT_HSM_OPS_AUDIT_PATH=/var/lib/icoder-audit/software-hsm-ops.jsonl
ICODER_SOFT_HSM_OPS_AUDIT_KEY=<independent base64url 32+ bytes>
ICODER_SOFT_HSM_OPS_AUDIT_KEY_ID=soft-hsm-ops-audit-v1
```

初始化必须在离线或受控 operator 环境执行：

```text
python scripts/manage_soft_hsm_keystore.py create \
  --path /run/secrets/icoder/software-hsm.keys --key-id soft-hsm-kek-v1 \
  --change-ticket CHANGE-12345
```

密钥库文件和 bootstrap key 必须分别备份。文件权限在 POSIX 上必须为当前 runtime owner 的
`0600` 或更严格；符号链接、非普通文件、超过 1 MiB 的文件均拒绝加载。Windows 部署必须由
平台配置仅 service identity 可读写的 ACL；Python 的 POSIX mode 检查不能替代 Windows ACL。

密钥库包含单调递增 `generation`。部署系统必须把成功操作返回的 generation 更新到独立的
`ICODER_SOFT_HSM_MIN_GENERATION`；低于该值的历史文件会被判定为 rollback 并拒绝启动。
轮换步骤：

1. 执行 `python scripts/manage_soft_hsm_keystore.py rotate --path <absolute-path>
   --new-key-id soft-hsm-kek-v2 --expected-generation 1 --change-ticket CHANGE-12345`。
   工具在 operator lock 内原子替换文件，
   自动把旧 KEK 改为 `decrypt-only`、新 KEK 改为唯一 `active`。
2. 将返回的 generation 更新到部署系统的 minimum generation，滚动部署并确认新写入引用新 key ID。
3. 运行 `python scripts/rewrap_phi_deks.py`；dry-run 必须能解析所有旧 key ID。
4. 设置 `P1_POSTGRES_APP_DATABASE_URL` 和审计签名密钥后，运行
   `python scripts/rewrap_phi_deks.py --execute --batch-size 200`。
5. 命令会再次全量扫描；只有 `post_verification.retirement_ready=true` 才会写入
   `phi.key_retirement.verified`。
6. 保留旧 KEK 为 `decrypt-only` 至少一个完整回滚窗口；确认无备份恢复、延迟副本或离线任务
   仍引用旧 key ID 后，执行 `set-state --state retired --authorization ZERO_REFERENCES_VERIFIED`
   并更新 minimum generation。紧急撤销使用 `--state revoked --authorization EMERGENCY_REVOKE`。

重包裹不会解密 PHI ciphertext。它只在内存中短暂解包 32-byte DEK，再由新 KEK 包裹。
envelope 的 `c`（数据密文）和 `n`（数据 nonce）保持不变；新增 `d` 固定原数据 AAD，`k`
指向当前 wrapping KEK。每次 generate/wrap/unwrap 只产生 key ID、操作、结果和计数指标，
不会记录 DEK、KEK、PHI、row ID 或 AAD 内容。

execute 命令必须能使用 app 角色写入 `phi.key_rewrap.started/completed/failed` 和
`phi.key_retirement.verified`。这些事件由现有签名链封装并追加到不可变审计归档；审计写入失败
会阻断命令。PR 的 `P1 PHI / Multi-tenant Release Gate` 会从空库完成角色 provisioning、
迁移到 072，并执行 PHI、RLS、在线轮换、回退和 artifact scanner 测试。

## 8. bootstrap key 轮换

bootstrap key 只负责加密 key store，不包装数据库 DEK。因此它可以在不扫描或更新数据库的
情况下轮换：

1. 从独立 secret manager 注入当前 `ICODER_SOFT_HSM_BOOTSTRAP_KEY`。
2. 临时注入一次性 `ICODER_SOFT_HSM_NEW_BOOTSTRAP_KEY`，不得写入命令参数或日志。
3. 执行：
   `python scripts/manage_soft_hsm_keystore.py rotate-bootstrap --path <absolute-path>
   --expected-generation <current> --change-ticket <ticket>`。
4. 工具使用旧 bootstrap 解封，在内存中保持相同 KEK/key state，以新 bootstrap 重新 seal，
   generation 加一后原子替换。
5. 更新 secret manager 中的 active bootstrap 和独立 minimum generation，再滚动重启。
6. 验证旧 bootstrap 报 authentication failed、新 bootstrap 能读取历史 PHI envelope。
7. 保留旧 bootstrap 的受控恢复副本至完整回滚窗口结束，之后按双人审批销毁。

bootstrap 轮换不改变数据库 v2 envelope 的任何字节，也不改变 active KEK ID。若 completed
审计写入失败，密钥库可能已经原子更新，命令会返回失败；operator 必须依据 started 事件和
密钥库 generation 执行对账，禁止盲目重跑旧 expected-generation。

## 9. 独立不可变运维审计链

所有 CLI 突变命令强制要求独立的 audit path、audit key、audit key ID 和 change ticket。每次
操作写入 `started`，随后写入 `completed` 或 `failed`。事件只允许以下元数据：operation、phase、
outcome、key-store 路径哈希标识、expected/result generation、active key ID、key states、异常类型
和 change ticket。结构白名单阻止把 KEK、bootstrap key、PHI、ciphertext 或数据库 URL 写入。

JSONL 每条记录绑定 event、recorded_at、event_id、sequence、previous hash 和 payload hash，使用
独立 HMAC-SHA256 key 签名。写入使用 `O_APPEND`、文件锁、0600、fsync 和链头复验。验证：

```text
ICODER_SOFT_HSM_OPS_AUDIT_MIN_SEQUENCE=<外部保存的最小序号>
python scripts/verify_soft_hsm_ops_audit.py \
  --minimum-sequence "$ICODER_SOFT_HSM_OPS_AUDIT_MIN_SEQUENCE"
```

## Phase 7：不可变归档与签名轮换

生产环境的密钥库突变必须设置 `ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED=true`。
当前仓库提供 `local_worm_simulator` 用于 CI 和开发验收；它验证 create-only object、保留期、
Legal Hold、独立 checkpoint、恢复和导出契约，但不能抵抗拥有主机管理员权限的人直接修改磁盘，
不得作为真实生产 WORM 的替代品。

```text
ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED=true
ICODER_SOFT_HSM_AUDIT_ARCHIVE_ADAPTER=local_worm_simulator
ICODER_SOFT_HSM_AUDIT_ARCHIVE_ROOT=/var/lib/icoder-audit-worm
ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY=<independent base64url 32+ bytes>
ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY_ID=checkpoint-v1
ICODER_SOFT_HSM_AUDIT_RETENTION_DAYS=2555
ICODER_SOFT_HSM_AUDIT_LEGAL_HOLD=false
ICODER_OPERATOR_IDENTITY=deployment-service
ICODER_DEPLOYMENT_ENVIRONMENT=production
ICODER_RELEASE_VERSION=<immutable release identifier>
```

checkpoint key 必须不同于 ops-audit key、当前 bootstrap key 和待轮换 bootstrap key。归档不可用、
checkpoint 无法写入或归档复验失败时，started 事件之后、密钥库突变之前 fail closed。若突变完成后
completed 事件归档失败，命令仍返回失败，值班人员必须按 generation、local chain 和 WORM objects
执行对账。

审计签名密钥轮换采用 active writer + historical verifier keyring：

```text
ICODER_SOFT_HSM_OPS_AUDIT_KEY=<active key bytes>
ICODER_SOFT_HSM_OPS_AUDIT_KEY_ID=ops-audit-v2
ICODER_SOFT_HSM_OPS_AUDIT_KEYS={"ops-audit-v1":"<old>","ops-audit-v2":"<active>"}
```

旧 key 必须保留在只读验证 keyring，直到其签名记录超过全部法定保留期且对应归档已依法处置。
单个本地 JSONL segment 达到 16 MiB 时自动创建六位编号 segment；sequence、previous hash 和
chain hash 跨 segment 连续。所有 segment 的总读取上限为 256 MiB；WORM object 是长期权威副本，
本地 segment 只是可恢复 spool。

验证本地链和不可变归档：

```bash
python scripts/verify_soft_hsm_ops_audit.py \
  --minimum-sequence "$ICODER_SOFT_HSM_OPS_AUDIT_MIN_SEQUENCE" \
  --verify-archive
```

导出工具只创建新文件，不覆盖既有证据；导出包含经签名的最小化运维记录，不包含 archive
checkpoint key、audit key、bootstrap key、KEK、DEK、PHI、密文或数据库 URL：

```bash
python scripts/export_soft_hsm_ops_audit.py --output /secure/export/hsm-audit-evidence.json
```

真实生产适配器必须由选定云厂商或独立归档平台提供 compliance-mode object lock、独立 IAM、
服务端 retention/Legal Hold 和跨区域复制，并通过与本地模拟器相同的契约测试。未完成真实适配器
认证前，Phase 7 只能判定为“工程基线完成”，不能宣称生产 WORM 已上线。

## Phase 7.1：AWS S3 Object Lock 生产适配器

首个真实归档适配器为 `aws_s3_object_lock`。它只支持 AWS SDK 默认凭据链，不接受 access key 命令行
参数或自定义 HTTP endpoint。bucket 必须启用 Versioning 和 Object Lock，默认 retention 必须是
COMPLIANCE，并使用独立的 SSE-KMS customer-managed key。

```text
ICODER_DEPLOYMENT_MODE=cloud
ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED=true
ICODER_SOFT_HSM_AUDIT_ARCHIVE_ADAPTER=aws_s3_object_lock
ICODER_SOFT_HSM_AUDIT_S3_REGION=ap-east-1
ICODER_SOFT_HSM_AUDIT_S3_BUCKET=<dedicated audit bucket>
ICODER_SOFT_HSM_AUDIT_S3_PREFIX=software-hsm/v1
ICODER_SOFT_HSM_AUDIT_S3_EXPECTED_OWNER=<12 digit AWS account ID>
ICODER_SOFT_HSM_AUDIT_S3_KMS_KEY_ID=<full KMS key ARN>
ICODER_SOFT_HSM_AUDIT_S3_EXPECTED_WRITER_ARN=<exact STS caller ARN>
ICODER_SOFT_HSM_AUDIT_S3_REPLICA_BUCKET_ARN=<cross-region bucket ARN>
```

每次 PUT 必须同时满足：

- `IfNoneMatch="*"`，拒绝已存在 object key；
- `ObjectLockMode="COMPLIANCE"` 和不少于配置天数的 retain-until；
- SHA-256 SDK checksum；
- SSE-KMS 且返回的 KMS key ARN 与配置完全一致；
- expected bucket owner 匹配；
- 返回非空 VersionId；
- 立即 HEAD 同一 VersionId，复验 retention、mode、Legal Hold（适用时）和加密信息。

控制面验证：

```bash
python scripts/verify_soft_hsm_s3_archive.py
```

该命令验证精确 STS writer ARN、bucket owner、Versioning、默认 COMPLIANCE retention 和指定跨区域
复制规则。仓库提供
`deploy/security/aws-s3-object-lock-audit-writer-policy.template.json`；部署时必须替换占位符并由云安全
团队审查。writer 显式拒绝 DeleteObject、DeleteObjectVersion、BypassGovernanceRetention、修改 bucket
policy/versioning/Object Lock configuration，也不持有 `PutObjectLegalHold`。Legal Hold 由独立合规身份
管理，不能与日常 writer 共用权限。

归档对账命令：

```bash
python scripts/reconcile_soft_hsm_ops_audit.py --max-pending-seconds 900
```

输出 `checkpoint_lag_before/after`、是否修复、local/archive records、head hash 和告警代码。发现超过阈值
的 `started` 无 `completed/failed` 时返回退出码 2 和
`HSM_AUDIT_STARTED_WITHOUT_TERMINAL`。archive 超前于本地 spool 或双方同序号不同 head 时不会自动覆盖，
必须进入恢复流程。

revision 073 另增加两个最小披露 PostgreSQL bootstrap 函数：

- `icoder_user_has_active_membership(...) -> boolean`；
- `icoder_oauth_credential_is_active(...) -> boolean`。

它们只在函数内部临时安装候选 tenant context，精确查询 FORCE RLS 表，然后在正常或异常返回前恢复
原 setting。只有布尔验证成功后，应用层才调用 `bind_tenant_to_transaction`。函数归 migration role
所有，app role 仅有 EXECUTE，PUBLIC 无 EXECUTE。

本地文件能检测插入、修改、重排、中段删除和错误签名；外部 minimum sequence 检测尾部回滚。
它不能抵抗 privileged host administrator 同时删除文件和外部 checkpoint。生产必须持续将记录与
chain head 复制到 object-lock/WORM 或独立审计系统，且 audit key 不能与 bootstrap key 相同。

## 10. 灾备演练

运行 `python scripts/rehearse_soft_hsm_disaster_recovery.py`。工具只使用一次性随机 key、临时目录
和明确标记的 synthetic PHI，不连接生产数据库、不保留密钥或明文 artifact。通过条件：

- key store 丢失时 fail closed；
- bootstrap key 丢失时 fail closed；
- generation 1 文件在 floor=2 时被识别为 rollback；
- bootstrap generation 2→3 后旧 bootstrap 失败、新 bootstrap 能读取历史 PHI；
- 审计链 mutation 和 tail rollback 均被识别；
- 审计记录数和 head hash 通过独立验证。

除自包含演练外，发布前还需在 disposable PostgreSQL 恢复库执行真实备份恢复测试。当前集成
测试已验证 bootstrap 轮换不改变数据库 PHI envelope，并覆盖 072→070→072 populated 回退。
