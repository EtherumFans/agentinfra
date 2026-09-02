# PHI 软件 HSM、v1→v2 轮换、备份/WAL 扫描与回退手册

适用 schema：revision 072。本文中的 `software_hsm` 只模拟 KMS/HSM 的
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

以下变量必须由进程级 secret injection 提供，不写入 `.env`、报告或命令历史：

```dotenv
ICODER_PHI_KEY_PROVIDER=software_hsm
ICODER_SOFT_HSM_KEY_ID=soft-hsm-kek-v1
ICODER_SOFT_HSM_MASTER_KEY=<base64url encoded 32 bytes>
ICODER_PHI_ENCRYPTION_KEY_V1=<legacy Fernet key, rotation window only>
P1_POSTGRES_MIGRATION_DATABASE_URL=<migration-role URL>
```

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

