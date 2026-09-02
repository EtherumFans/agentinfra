# P1 Wave 5 Phase 5：软件 HSM 安全增强审查报告

- 审查日期：2026-09-02（Asia/Shanghai）
- 分支：`codex/p1-security-multitenant-gates`
- 前置基线：`bb953149`
- 安全实现提交：`3a97133f`
- CI/集成提交：`f9088197`
- 数据库 schema：revision `072`（本阶段不新增表或迁移）
- 结论：软件 HSM 已从明文环境变量 keyring 升级为可用于受控阶段部署的加密密钥库；仍不等同于硬件 HSM。

## 1. 开发目标与结果

| 目标 | 状态 | 结果 |
|---|---|---|
| KEK 静态保护 | 完成 | keyring 使用 AES-256-GCM 认证加密文件保存 |
| bootstrap 分离 | 完成 | 文件解密 key 只从独立 secret injection 读取 |
| cloud fail closed | 完成 | cloud 模式拒绝单 KEK和明文 JSON keyring |
| 防历史文件回放 | 完成 | monotonic generation + 外部 minimum generation |
| 文件加载安全 | 完成 | 绝对路径、普通文件、大小、owner/mode、no-follow 检查 |
| 运维写入安全 | 完成 | operator lock、期望代数、临时文件 fsync、原子替换 |
| 密钥状态治理 | 完成 | 单向退役/撤销转换和显式授权口令 |
| 运行时性能 | 完成 | 按文件 identity/mtime/size/mode/bootstrap/floor 安全缓存 |
| CI 与 PostgreSQL | 完成 | PR 使用真实加密密钥库；真实 072 生命周期通过 |

## 2. 威胁模型变化

### 2.1 已降低的风险

Phase 4 的软件 HSM 支持多 KEK，但 KEK 仍直接存在环境变量 JSON 中。环境快照、错误诊断、
编排配置导出或支持人员误操作可能一次性暴露全部历史 KEK。本阶段改变为双组件：

1. `software-hsm.keys`：只保存认证加密 document；文件字节中不可搜索 key ID 和 KEK。
2. `ICODER_SOFT_HSM_BOOTSTRAP_KEY`：独立的 256-bit bootstrap key，由 workload secret 注入。

攻击者只取得文件或只取得 bootstrap key 均不能直接得到 keyring。AES-GCM 同时保护机密性和
完整性；salt、nonce、ciphertext、schema、generation、KDF 和 cipher 元数据均受到结构与认证
校验。bootstrap key 先经过带固定 domain separation info 和随机 256-bit salt 的 HKDF-SHA256，
派生出的文件加密 key 使用后执行 best-effort zeroize。

### 2.2 cloud 启动门禁

当 `ICODER_DEPLOYMENT_MODE=cloud` 且选择 `software_hsm` 时：

- 未设置绝对 `ICODER_SOFT_HSM_KEYSTORE_PATH`：拒绝启动；
- 未设置 bootstrap key或不是严格 base64url 32 bytes：拒绝启动；
- 未显式设置正整数 `ICODER_SOFT_HSM_MIN_GENERATION`：拒绝启动；
- 试图回退到 `ICODER_SOFT_HSM_MASTER_KEY` 或 `ICODER_SOFT_HSM_KEYRING_JSON`：拒绝启动。

本地开发仍保留旧配置兼容性，但可设置
`ICODER_SOFT_HSM_REQUIRE_ENCRYPTED_KEYSTORE=true` 主动采用生产型门禁。

## 3. 加密密钥库格式与加载约束

外层 document schema 为 `icoder.software-hsm-keystore/v1`，固定使用：

- KDF：HKDF-SHA256；
- cipher：AES-256-GCM；
- salt：32 bytes；
- nonce：12 bytes；
- generation：正整数；
- ciphertext：完整 keyring 的认证密文。

加载器设置 1 MiB 硬上限，拒绝相对路径、symbolic link、目录和其他非普通文件。POSIX 使用
`O_NOFOLLOW` 单文件句柄完成 fstat/read，避免检查后替换的 symlink race；要求 runtime user
拥有文件且 group/other 无任何权限。Windows 仍需部署平台配置 service identity 专用 ACL，
Python 层不能把 POSIX mode 当作 Windows ACL 证明。

keyring 解密后继续执行 Phase 4 结构门禁：最多 64 个 key、严格 key ID、严格 32-byte KEK、
四态白名单、恰好一个 matching active key。配置对象不可变，key mapping 使用只读 proxy，
KEK 字节从 repr 隐藏。明文 JSON parser 额外拒绝重复 key，避免 last-key-wins 配置歧义。

## 4. 防回滚和并发运维

每次 create/rotate/set-state 都生成更高 generation。部署系统把已批准 generation 保存在密钥库
之外的 `ICODER_SOFT_HSM_MIN_GENERATION`；加载低代数历史文件会报 rollback 并失败。这个设计
避免攻击者单独恢复旧密钥库文件后让应用静默重新接受已退役配置。

`manage_soft_hsm_keystore.py` 的突变操作具备：

- 持有同目录 operator lock，第二个协作进程立即失败；
- rotate/set-state 必须提供 `--expected-generation`，陈旧 operator 不能覆盖新版本；
- create 使用 hard-link no-clobber，目标在竞态中出现时也不覆盖；
- 更新写入随机临时文件，执行 file fsync、0600、atomic replace 和 POSIX directory fsync；
- 输出仅包含 operation、active key ID、generation、source 和 key states。

允许的状态变化是：

- rotate：原 active 自动转为 decrypt-only，新 key 成为唯一 active；
- decrypt-only → retired：必须提供 `ZERO_REFERENCES_VERIFIED`；
- decrypt-only/retired → revoked：必须提供 `EMERGENCY_REVOKE`；
- active 不能直接 retired/revoked；retired/revoked 不能恢复为可用状态。

显式授权短语是防误操作门槛，不是数据库引用证明本身。正式退役仍必须先由
`rewrap_phi_deks.py` 完成权威库零引用验证，并检查备份、WAL、延迟副本和离线导出。

## 5. 与 PHI 轮换链路集成

`rewrap_phi_deks.py` 的报告和签名审计事件新增 keyring source 与 generation。运维人员可以将
数据库的 `phi.key_rewrap.*`、`phi.key_retirement.verified` 与密钥库 generation 对齐，避免只凭
key ID 推断操作使用了哪个配置版本。

真实 PostgreSQL 生命周期现在覆盖：

1. legacy Fernet v1 → software-HSM v2；
2. 建立 generation 1 加密密钥库；
3. 原子 rotate 到 generation 2；
4. 旧 KEK decrypt-only、新 KEK active；
5. 全表只重包裹 DEK，确认 PHI ciphertext/nonce 不变；
6. 旧 key 数据仍可读，新写入使用新 key；
7. populated 072 → 070 兼容回退并重新前进到 072。

## 6. CI 和配置变化

PR 的 `P1 PHI / Multi-tenant Release Gate` 不再注入明文软件 HSM KEK。每个 job：

1. 随机生成一次性 bootstrap key；
2. 在 runner 临时目录创建 generation 1 加密密钥库；
3. 强制 `ICODER_SOFT_HSM_REQUIRE_ENCRYPTED_KEYSTORE=true`；
4. 完成角色 provisioning、072 迁移、PHI/RLS/审计/轮换/回退测试。

`.env.cloud.example` 已删除 cloud 使用 raw master key 的示例，改为 encrypted key store、独立
bootstrap key 和 minimum generation。

## 7. 验证证据

### 7.1 本地安全与回归测试

- 软件 HSM、PHI、cloud config、审计、scanner、role provisioning：`105 passed`。
- Python compileall：通过。
- PR workflow YAML：解析通过。
- `git diff --check`：通过，仅有既有 Windows CRLF 转换提示。

负向测试包括：

- ciphertext tamper；
- 错误 bootstrap key；
- generation rollback；
- cloud 缺失加密库或 generation floor；
- 未授权 retired；
- 陈旧 expected generation；
- 重复 JSON key；
- create 覆盖已有密钥库；
- KEK 出现在对象 repr 或加密文件字节中。

### 7.2 真实 PostgreSQL

- PHI/RLS/审计/迁移联合套件：`34 passed`。
- 当前专用测试库保持 revision `072`、83 张表、71 项 PHI 约束。
- 前一阶段已收敛的 migration/app 数据库角色继续保持零权限漂移。

## 8. 残余风险与必须执行的运行条件

软件 HSM 的安全性已显著提高，但以下风险不能被软件设计消除：

1. 应用进程同时可访问 bootstrap key 和解密后的 KEK；进程控制权丢失即视为密钥泄露。
2. Python、OpenSSL、崩溃转储、swap 和虚拟机快照可能保留密钥副本；zeroize 不是硬件保证。
3. Windows 文件 ACL 必须由部署工程验证；当前代码不能证明 ACL 正确。
4. bootstrap key 与 key store 若进入同一备份、volume 或配置导出，会失去双组件隔离收益。
5. generation floor 必须保存在独立、受变更控制的配置源；与 key store 一起回滚无法防重放。
6. key-store create/rotate/set-state 的 metadata 输出需要由部署系统保存为变更证据；数据库中的
   不可变审计链目前覆盖 PHI DEK rewrap，而非离线文件创建本身。
7. 软件 HSM 不提供 FIPS 140 认证、硬件抗提取、远程 attestation、双人控制或供应商级审计。

阶段性生产使用至少应配置：service identity 专用主机/容器、禁用 core dump、加密 swap/磁盘、
bootstrap 与文件分离注入、只读 runtime mount、独立备份、generation 外部持久化、变更审批和
定期恢复演练。

## 9. 下一步建议

1. 执行软件 HSM 灾备演练：分别丢失 key store、bootstrap key、generation floor，验证恢复和
   fail-closed 行为。
2. 将离线 key-store lifecycle metadata 接入独立不可变运维审计链，补 operator identity 和
   change-ticket 关联。
3. 增加进程级保护基线：core dump 禁用、memory/swap policy、容器只读挂载和 Windows ACL
   自动预检。
4. 设计 bootstrap key 轮换（重新 seal keyring、不重包裹数据库 DEK）及双版本恢复窗口。
5. 保留 `KeyWrappingProvider` 接口，后续可无缝替换为真实 KMS/HSM。

## 10. 发布判断

本阶段可作为“强化软件 HSM”开发候选基线。它适合用户当前选择的软件 HSM 路径，并为受控
阶段部署提供比环境变量 keyring 更强的静态保护、回滚检测和运维防误操作能力。正式发布必须
把第 8 节运行条件纳入部署验收；不得将本实现描述为硬件 HSM 或宣称硬件级密钥不可导出。
