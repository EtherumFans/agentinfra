# P1 Wave 5 Phase 3 — 软件 HSM、v1→v2 轮换与恢复工程审查报告

日期：2026-09-02  
分支：`codex/p1-security-multitenant-gates`  
输入基线：`4fae349dadf1fd6a07eba32f4adc2326c66e520c`

实现提交：

- `557109fa` — 软件 HSM 抽象与 v2 wrapped-DEK runtime
- `199b435c` — revision 072、在线轮换和 populated rollback
- `5058ea82` — 备份/WAL PHI canary scanner
- `b50c9478` — HSM、轮换、scanner、回退测试
- `0f8e809c` — 配置和操作手册

## 1. 结论

用户指定的四项工作已完成可重复的本机工程实现与 PostgreSQL 演练：

1. 软件 HSM 模拟接入；
2. v1→v2 在线、分批、可重跑轮换；
3. plain-format 备份与真实 WAL segment 明文 canary 扫描；
4. populated JSON 从 072 回到 070 的语义兼容回退，并验证重新前进到 072。

当前权威测试数据库为 `072 (head)`，保有 71 个同时接受 v1/v2 的 PHI 数据库约束。测试组织、canary 行、plain dump、WAL 副本、sentinel 文件和空库重建数据库均已清除。

软件 HSM 是接口和流程模拟，不是生产 HSM。它不能提供硬件不可导出、FIPS/国密认证、抗侧信道或独立故障域。真实 KMS/HSM provider 仍是生产发布阻断项。

## 2. v2 cryptographic envelope

### 2.1 数据路径

每个 PHI 值执行：

1. 生成一次性 256-bit DEK；
2. 使用 AES-256-GCM 和随机 96-bit nonce 加密 PHI；
3. 通过 `KeyWrappingProvider` 将 DEK 交给软件 HSM；
4. 软件 HSM 使用独立 KEK 和 AES-256-GCM 包装 DEK；
5. 数据库保存 `v2:`、algorithm/schema、KEK key ID、data nonce、ciphertext、wrapped DEK；
6. 明文 DEK 使用后执行 best-effort mutable-buffer overwrite。

算法、schema 和 key ID 形成 canonical AAD，同时绑定数据密文和 wrapped key。任意 ciphertext、wrapped DEK、nonce、metadata、KEK 或 key ID 错误都会认证失败。

### 2.2 双读单写

- 配置 `legacy_fernet` 时继续产生历史 v1，用于兼容与回退。
- 配置 `software_hsm` 时新写入只产生 v2。
- v2 runtime 可以同时读取 v1 和 v2；轮换窗口通过 `ICODER_PHI_ENCRYPTION_KEY_V1` 保留旧 key。
- ORM 收到“看起来像 envelope”的输入时会先认证，不能通过构造长 `v2:` 字符串绕过应用加密。
- PostgreSQL 仍拒绝普通明文和短伪 envelope。

### 2.3 软件 HSM 边界

`SoftwareHSM` 只暴露：

- `generate_data_key(context)`；
- `unwrap_data_key(wrapped_key, context)`；
- 非敏感 `key_id`。

API 不暴露 KEK。模拟 KEK 仍存在同一 Python 进程内并由环境 secret 注入，因此不能声称实现硬件隔离。未来真实 provider 应保持相同接口，改用 workload identity、KMS GenerateDataKey/Decrypt 或 HSM wrap/unwrap API。

## 3. revision 072

072 线性跟随 071，不增加业务表：

- 保持 83 张 base tables；
- 替换原 71 个 v1-only CHECK 为 v1/v2 dual-envelope CHECK；
- constraint 数量异常时拒绝迁移；
- downgrade 前逐租户绑定 FORCE RLS 上下文；
- 任一 HSM v2 值尚未反向轮换时拒绝降级到 071。

空库 `000 → 072`、`072 → 071 → 072` 均已通过。最终空库状态为 83 tables、71 PHI constraints、71 个包含 v2 规则的约束。

## 4. 在线 v1→v2 轮换

新增 operated raw-SQL 工具，避免旧 ORM helper 透明解密后丢失存储版本的问题。

实现属性：

- session advisory lock：阻止两个 operator 并发轮换；
- 逐租户绑定：遵守 FORCE RLS；
- 小批量独立事务；
- `FOR UPDATE SKIP LOCKED`；
- 默认 dry-run；
- v2 writer 与 v1/v2 reader 可持续在线服务；
- 已完成 v2 行自动跳过，进程中断后直接重跑；
- 输出只有组织、字段和数量，不输出 ID、明文、密钥或 URL；
- 反向 v2→v1 要求显式 maintenance confirmation。

有数据实测：

| 阶段 | 结果 |
|---|---|
| 创建 populated Encounter | 1 行，3 个 v1 PHI 值，其中 JSON 为非空 array |
| forward rotation，batch size 1 | 3 个值转为 v2 |
| 重复 forward dry-run | `values=0` |
| 带 v2 直接 downgrade 071 | 按预期拒绝 |
| reverse rotation | 3 个值恢复为 v1 |

## 5. populated JSON 生产兼容回退

071 的 downgrade 只把 opaque text 变成 JSON string；070 应用需要的是实际 array/object。新增兼容恢复工具在 070 中完成第二阶段语义恢复。

安全控制：

- 只接受 revision 070；
- transaction advisory lock；
- 检查其他 active database sessions，未排空则拒绝；
- dry-run 会完整解密和 JSON parse，但不写入；
- execute 同时要求固定 maintenance confirmation 和 plaintext-at-rest acknowledgement；
- 单事务、字段级计数和 manifest SHA-256；
- 任何解密、JSON parse 或并发状态异常时整体回滚；
- 保留 Clinical Facts、Guided Document/Section 这 7 个在 070 已显式加密字段的密文。

完整实测顺序：

```text
072/v2 → reverse to v1 → downgrade 070
→ compatibility dry-run → compatibility execute
→ 验证 text 为旧明文、JSON 为真实 array
→ 070 backfill to v1 → upgrade 072 → rotate to v2
```

结果：3 个 populated 值全部恢复旧语义，并成功重新前进到 v2。必须强调：070 兼容 execute 会有意识地恢复部分 PHI 明文，仅能用于已审批、隔离、排空 writer 的紧急维护窗口。

## 6. 备份与 WAL 明文扫描

scanner 对 operator 提供的 canary 搜索以下表示：

- UTF-8；
- UTF-16LE；
- UTF-16BE；
- 跨 1 MiB chunk boundary。

结果只包含 artifact 路径、大小、SHA-256、offset 和 canary 的截断 SHA-256 标识，不回显 canary。

### 真实演练

通过 v2 应用路径写入一次性非真实患者 canary，随后：

- 生成 PostgreSQL plain-format dump：344,570 bytes；
- 切换 WAL 并复制包含测试事务的 16,777,216-byte segment；
- 合计扫描：17,121,786 bytes；
- `finding_count=0`；
- status：`passed`。

负向测试证明 scanner 能发现 UTF-8、UTF-16 和跨 chunk boundary 明文，并且报告不包含 canary 原文。

该结果只证明指定 canary 与路径。它不能替代全量 DLP、备份加密、WAL archive 加密、对象存储访问控制和定期人工抽查。custom/compressed dump 必须先在隔离目录展开后扫描。

## 7. 验证结果

| 验证组 | 结果 |
|---|---|
| HSM/envelope/071/072/scanner/既有 key lifecycle 单元与契约回归 | 47 passed |
| Clinical/CDI/Guided Document/Coding Review 回归组合 | 纳入最终本地组合，共 116 passed |
| 真实 PostgreSQL PHI、HSM rotation、RLS、角色、审计组合 | 20 passed, 1 skipped |
| skip 原因 | 未配置 `P1_POSTGRES_ADMIN_DATABASE_URL`；角色 provisioning 的管理员连接测试未运行 |
| populated 072→070→072 生命周期 | passed |
| 备份/WAL 17,121,786 bytes canary 扫描 | passed, 0 findings |
| 空库 000→072 与 072↔071 | passed |
| 软件 HSM 模式 production database verifier | passed |
| Python compileall | passed |
| Git whitespace check | passed；仅 `.env.cloud.example` 有 Windows CRLF checkout 提示 |

## 8. 审查中发现并修复的问题

1. **旧 ORM rotation helper 不适合透明 PHI 类型**：读取时版本已被解密，不能可靠判断 v1/v2。新增 raw storage rotation tool。
2. **psycopg 把 SQL LIKE 中 `%` 当 placeholder**：migration/tool 中 literal percent 改为正确转义，实库通过。
3. **JSON 类型没有 `=` operator**：070 compatibility 的 optimistic equality 条件会失败；在已排空、单事务模型下改用主键更新并检查 rowcount。
4. **070→071 backfill 在软件 HSM 模式会错误地产生 v2**：backfill 现在固定生成 v1，确保先通过 071，再由 072 在线轮换。
5. **结构相似 envelope 可绕过 ORM 加密**：PostgreSQL bind path 对已有 envelope 先认证后接受。
6. **直接 downgrade 无法恢复 populated JSON 语义**：新增两阶段 reverse rotation + 070 compatibility restore。
7. **压缩备份不能做可靠 byte canary scan**：操作手册强制 plain dump 或隔离展开后扫描。

## 9. 发布风险和后续工作

仍未完成：

1. 真实云 KMS/HSM adapter 与 workload identity；
2. HSM/KMS 独立审计日志接入不可变审计归档；
3. 多 KEK key ID resolver 和 HSM KEK 自身轮换；
4. 高并发/千万级行轮换性能与长时间 soak；
5. 真实归档服务中的连续 WAL、base backup、PITR 恢复扫描；
6. 配置 `P1_POSTGRES_ADMIN_DATABASE_URL` 后重跑管理员 provisioning integration；
7. 将 canary scanner、rotation dry-run 和 v1 residual count 纳入发布 CI；
8. 070 plaintext emergency window 的审批、自动过期和事后再加密 SLA。

发布判定：`072` 可作为软件 HSM 和恢复流程的工程候选基线；不得把它标记为真实 KMS/HSM 生产就绪。真实 provider、PITR/归档链验证和管理员 provisioning 测试仍为 P1 发布阻断项。

## 10. 清理与可追溯性

- 权威本机数据库：072 head；
- 71 个 PHI constraints 完整；
- HSM/rotation/WAL 测试组织：0；
- 一次性 empty rebuild database：已删除；
- canary database row：已删除；
- plain dump、WAL segment、sentinel JSON：已删除；
- 未提交密钥、密码、数据库 URL、canary 原文或 PHI 测试数据。

