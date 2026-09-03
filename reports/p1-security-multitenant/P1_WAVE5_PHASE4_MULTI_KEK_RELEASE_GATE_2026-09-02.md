# P1 Wave 5 Phase 4：多 KEK 治理、DEK 在线重包裹与发布闸门审查报告

- 审查日期：2026-09-02（Asia/Shanghai）
- 分支：`codex/p1-security-multitenant-gates`
- Phase 4 源码候选：`62ab35fe`
- 前置基线：`da7a7c57`
- 数据库 schema：revision `072`（本阶段无 schema 变更）
- 结论：Phase 4 工程范围已完成；软件 HSM 仍仅用于集成和演练，不构成生产硬件安全边界。

## 1. 本阶段目标与完成状态

| 工作项 | 状态 | 结论 |
|---|---|---|
| 多 KEK resolver | 完成 | 支持一个 active KEK 和多个历史 KEK，配置严格校验 |
| KEK 状态机 | 完成 | `active`、`decrypt-only`、`retired`、`revoked` 四态，非法操作 fail closed |
| 在线 KEK 轮换 | 完成 | 仅解包和重包裹 32-byte DEK，不解密/重加密 PHI ciphertext |
| v2 兼容读取 | 完成 | 原六字段 v2 与重包裹后的七字段 v2 均可读取 |
| 密钥操作可观测性 | 完成 | generate/wrap/unwrap 按 key ID、状态、结果计数，不记录密钥或 PHI |
| 密钥生命周期审计 | 完成 | started/completed/failed/retirement verified 进入签名链和不可变归档 |
| PostgreSQL 角色治理 | 完成 | 增加 NOINHERIT 与 app 零父角色 membership 漂移门禁 |
| 自动发布闸门 | 完成 | PR 从空 PostgreSQL 建角色、迁移 072、执行 PHI/RLS/轮换/回退测试 |
| 本机专用测试库收敛 | 完成 | 旧权限漂移已修复，92 个对象、7 个函数复验零失败 |

## 2. 实现审查

### 2.1 多 KEK 注册表和状态机

`SoftwareHSMKeyring` 从 `ICODER_SOFT_HSM_KEYRING_JSON` 解析 KEK 注册表，并执行以下硬约束：

1. 顶层只能包含 `active_key_id` 和 `keys`；每个 key 只能包含 `key` 和 `state`。
2. key ID 必须符合受限字符集，KEK 必须解码为 32 bytes。
3. 必须且只能存在一个 `active`，并与 `active_key_id` 完全一致。
4. `active` 可 generate/wrap/unwrap；`decrypt-only` 只能 unwrap。
5. `retired`、`revoked` 和未知 key ID 均拒绝解包。
6. 旧的单 KEK 环境变量仍兼容，便于初次部署和现有 Phase 3 演练。
7. KEK 字节字段从对象 repr 中隐藏，防止异常诊断意外打印密钥。

### 2.2 只重包裹 DEK

原 v2 envelope 使用 `k` 同时确定 wrapped-DEK AAD 和 PHI data AAD。若直接修改 `k`，历史
PHI ciphertext 会认证失败。Phase 4 采用兼容扩展：

- 原六字段 envelope：data AAD 隐式使用 `k`；
- 首次重包裹：新增 `d=<原 k>` 固定 data AAD，`k=<新 active key>` 指向 wrapping KEK；
- 后续重包裹：保持 `d`、`c`、`n` 不变，只更新 `k` 和 `w`。

因此轮换期间不会把 PHI 明文交给重包裹工具，也不会生成新的 PHI ciphertext。工具内存中只
短暂存在 32-byte DEK，并在使用后 best-effort 覆盖。AES-GCM 对 wrapped DEK 和数据密文分别
完成认证；篡改 `d`、`c`、`n`、`k` 或 `w` 会在解包或读取时失败。

### 2.3 在线工具安全属性

`backend/scripts/rewrap_phi_deks.py` 具备：

- 默认 dry-run，只有显式 `--execute` 才写入；
- 仅允许 revision 072；
- session advisory lock 防止两个轮换进程并发；
- 逐租户设置数据库 tenant context，遵守 FORCE RLS；
- keyset pagination、小批事务和 `FOR UPDATE SKIP LOCKED`；
- 乐观条件更新，检测同一 PHI 值的并发修改；
- 可中断重跑，active key 行自动跳过；
- 输出仅包含 key ID、状态、计数和列名，不含 PHI、row ID、KEK、DEK 或数据库 URL；
- execute 后再次全量 dry-run，只有旧 KEK 引用为零才声明 `retirement_ready`。

### 2.4 审计签名链

新增四个显式 allowlist action：

- `phi.key_rewrap.started`
- `phi.key_rewrap.completed`
- `phi.key_rewrap.failed`
- `phi.key_retirement.verified`

execute 要求单独提供 app-role URL。事件先通过 `icoder_write_system_audit` 写为
`MODERN_SYSTEM`，再由现有 HMAC signer 形成 hash chain envelope，通过 security-definer
函数追加到 `audit_integrity_archive`。归档表的 UPDATE/DELETE trigger 继续提供数据库级不可变
保护。开始审计写入失败时轮换不会启动；完成审计或复验失败时命令以失败结束。

### 2.5 数据库角色 provisioning

既有 provisioning 已覆盖对象归属、PUBLIC 撤权、默认权限和幂等修复。本阶段新增：

- `verify` 必须确认 migration/app 均为 `NOINHERIT`；
- app 角色不得属于任何父角色，避免通过显式 `SET ROLE` 绕过 NOINHERIT；
- PR 在迁移前 provision、迁移后 verify，任何权限漂移均阻断。

本机 `icoder_p1_gate` 首次复验准确发现旧状态：migration 仍有 CREATEDB/INHERIT，app 仍有
INHERIT，public schema ownership、PUBLIC privilege 和 default ACL 未收敛。使用本机 PostgreSQL
管理身份修复专用测试库后，复验结果为 `ok=true`、`failures=[]`、92 objects、7 functions。

## 3. 自动发布闸门

PR 工作流新增 `P1 PHI / Multi-tenant Release Gate`，执行顺序为：

1. 启动一次性 PostgreSQL 16；
2. 生成 job-scoped 软件 HSM KEK 和审计签名 key，不写入仓库或 artifact；
3. provisioning 身份创建/收紧 migration 与 app 身份；
4. migration 身份从空库升级到 Alembic head（072）；
5. provisioning verifier 拒绝角色、对象、函数、PUBLIC 或默认权限漂移；
6. app 身份执行 PHI envelope、71 项约束、跨租户攻击、审计归档、在线轮换、populated
   rollback 和 artifact scanner 测试。

Windows 本机真实异步池测试必须使用 `postgresql+asyncpg` app URL；同步测试会自动转换为
`psycopg`。CI 已统一采用该配置，避免 psycopg async 与 Windows Proactor event loop 的环境性
不兼容被误判为产品缺陷。

## 4. 验证证据

### 4.1 单元、契约和配置验证

- PHI/keyring/system-audit/legacy-classifier/migration/scanner/provisioning：`41 passed`。
- PR workflow YAML：解析成功。
- Python compileall：通过。
- `git diff --check`：通过。

新增测试明确验证：

- 重包裹前后 `c` 与 `n` 完全相同，`w` 和 `k` 改变，`d` 保留原 key ID；
- 新 envelope 可读取；旧 KEK 为 decrypt-only 时可读但不可写；
- retired/unknown KEK fail closed；
- 操作指标不含 PHI 或密钥字段；
- role provisioning 生成 NOINHERIT 身份。

### 4.2 真实 PostgreSQL

- populated 生命周期单测：`1 passed`，覆盖 v1→v2、KEK-v1→KEK-v2 DEK rewrap、
  072→070 受控回退、重新前进到 072。
- PHI/RLS/audit/contract 联合套件：`32 passed`。
- 角色漂移最终复验：`ok=true`，`failures=[]`。

联合套件覆盖 Patient/Trace/Usage/Context/Memory 及 Wave 5 临床表的 RLS 攻击面、应用连接池
tenant context 清除、PHI 数据库约束、不可变审计归档和签名链契约。

## 5. 提交拆分

1. `7f0779c8 feat(security): add multi-KEK DEK rewrap lifecycle`
2. `62ab35fe ci(security): enforce PHI and database role release gate`
3. 本报告和运行手册作为独立 docs 提交，不与安全实现混合。

## 6. 风险、边界和后续任务

### 6.1 当前明确边界

- 软件 HSM 的 KEK 存在应用进程内存和环境注入面，不能声称 FIPS、密钥不可导出或硬件隔离。
- Python 的 zeroize 是 best-effort，解释器、底层库和崩溃转储仍可能保留副本。
- v2 data AAD 绑定算法、schema 和原 key ID；尚未绑定 tenant/table/column/record identity。若增强
  这些维度，需要设计 v3 envelope 和可恢复迁移，不能原地破坏 v2。
- `retirement_ready` 只证明当前权威库无旧 key 引用；退役前还必须覆盖备份、WAL、延迟副本、
  导出、灾备环境和离线任务。
- 当前审计 signer 仍是软件 HMAC bootstrap；生产应迁移到独立 KMS MAC 或非对称签名 key。

### 6.2 下一阶段建议顺序

1. 实现真实 KMS/HSM provider adapter、workload identity、超时/重试/熔断和 provider 审计对账。
2. 执行一次有数据的“旧 KEK→新 KEK→备份恢复→旧 KEK 退役”灾备演练，并保存无敏感信息证据。
3. 将审计 signer 迁移到独立 KMS/HSM key，补签名 key rotation 和多 signer 历史验证。
4. 设计 v3 contextual AAD（tenant/table/column/record）和跨版本迁移/回滚方案。
5. 补充生产监控：unwrap error、unknown/retired key、旧 key 引用不收敛、审计归档失败和发布门禁
   artifact 留存。

## 7. 发布判断

Phase 4 可作为“软件 HSM 多 KEK 在线轮换与自动安全门禁”候选基线。它已经满足开发/集成环境
的可复现和可阻断要求，但不能据此解除 P1 总体生产发布闸门。正式生产放行仍依赖真实 KMS/HSM、
灾备恢复演练、旧 key 全域引用清零、外部审计策略和 v3 contextual AAD 决策。
