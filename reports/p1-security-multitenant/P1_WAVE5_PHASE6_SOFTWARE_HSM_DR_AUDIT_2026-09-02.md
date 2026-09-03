# P1 Wave 5 Phase 6：软件 HSM 灾备演练与独立运维审计链报告

- 日期：2026-09-02（Asia/Shanghai）
- 分支：`codex/p1-security-multitenant-gates`
- 前置基线：`2ac050f3`
- 安全实现：`b7cb0645`
- 演练与 CI：`47797fdc`
- 数据库 schema：revision `072`（无 schema 变更）
- 结论：四类软件 HSM 灾备场景均按预期 fail closed 或恢复成功；离线密钥库突变已接入独立密码学追加链。

## 1. 完成范围

| 项目 | 状态 | 结果 |
|---|---|---|
| 密钥库丢失 | 通过 | runtime 拒绝继续运行，不回退到环境变量 KEK |
| bootstrap key 丢失 | 通过 | runtime 因缺少独立 bootstrap secret 拒绝解封 |
| generation floor 回滚 | 通过 | generation 1 文件在 minimum=2 时被识别为 rollback |
| bootstrap key 轮换 | 通过 | keyring 重新 seal 到 generation 3，数据库 DEK/PHI envelope 不变 |
| 旧 bootstrap 撤出 | 通过 | 旧 bootstrap authentication failed，新 bootstrap 可读取历史 PHI |
| 离线运维审计链 | 完成 | create/rotate/rotate-bootstrap/set-state 写 started + completed/failed |
| 审计篡改检测 | 通过 | event、时间、ID、序号、hash 或 signature 变化均失败 |
| 审计尾部回滚 | 通过 | 外部 minimum sequence 阻断被截短审计文件 |
| PR 自动门禁 | 完成 | CI 创建并验证独立审计链，运行自包含灾备演练 |

## 2. bootstrap key 轮换实现

新增 `rotate-bootstrap`。操作过程：

1. 使用当前 bootstrap key 认证并解封 keyring；
2. 校验 operator lock 和 `expected-generation`；
3. 保持所有 KEK bytes、active key ID 和 key states 不变；
4. generation 加一；
5. 使用新 bootstrap key、随机 salt 和 nonce 重新 seal；
6. fsync 后原子替换密钥库；
7. 旧、新 bootstrap key 的可变内存副本执行 best-effort zeroize。

因此 bootstrap 轮换与 KEK 轮换相互独立。它不调用数据库、不扫描 PHI 列、不解包数据库 DEK，
也不改变任何 v2 envelope。真实 PostgreSQL 测试直接比较轮换前后的存储字符串完全一致，并使用
新 bootstrap 解密历史 PHI。

安全门禁：

- 新旧 bootstrap 必须不同；
- audit key 必须同时不同于旧、新 bootstrap；
- 新 bootstrap 仅从 `ICODER_SOFT_HSM_NEW_BOOTSTRAP_KEY` 读取，不接受命令行参数；
- 必须提供 expected generation 和 change ticket；
- 完成后部署系统必须更新 bootstrap secret 和 minimum generation。

## 3. 独立运维审计链

### 3.1 独立性

审计链不依赖应用数据库，因此 PostgreSQL 不可用、首次创建 key store 或灾难恢复期间仍能记录。
它使用独立的：

- audit JSONL path；
- HMAC-SHA256 signing key；
- signing key ID；
- 外部 minimum sequence checkpoint。

代码明确拒绝 audit path 与 key-store path 相同，也拒绝 audit key 等于任一 bootstrap key。

### 3.2 事件最小化

事件 schema 是严格白名单，只允许：

- operation：create、rotate、rotate-bootstrap、set-state；
- phase/outcome：started/pending、completed/success、failed/failure；
- key-store path 的 SHA-256 截断标识；
- expected/resulting generation；
- active key ID 和 key states；
- 异常类型名称；
- change ticket。

不会记录绝对路径、KEK、DEK、bootstrap key、PHI、ciphertext、数据库 URL 或异常文本。失败事件
只写异常类名，避免底层异常意外携带敏感内容。

### 3.3 链和签名

每条记录包含 sequence、event ID、UTC timestamp、event payload、payload hash、previous hash、
chain hash、HMAC signature、algorithm 和 signing key ID。payload hash 同时覆盖 event、event ID 和
timestamp；chain hash 覆盖 schema、sequence、previous hash 和 payload hash。

验证器拒绝：

- JSON 解析失败或重复字段；
- 字段增删、布尔值伪装 sequence、非法时间/ID/hash；
- sequence gap、previous hash 断裂、payload mutation；
- signing key ID 或 HMAC 不匹配；
- 当前记录数低于外部 minimum sequence。

写入使用 `O_APPEND`、`O_NOFOLLOW`（平台支持时）、独占文件锁、0600、单句柄复验和 fsync。
每次突变先写 started；操作失败写 failed；成功写 completed。completed audit 写入失败时命令失败，
但原子密钥库更新可能已完成，operator 必须依据 generation 和 started 事件对账。

## 4. 灾备演练过程与结果

自包含工具只使用临时目录、一次性随机 key 和字符串
`SYNTHETIC-DR-PHI-NOT-A-PATIENT`，结束后由临时目录清理，不接触真实患者数据。

执行结果：

```text
status=passed
synthetic_data_only=true
key_store_missing=passed
bootstrap_key_missing=passed
generation_floor_rollback=passed
bootstrap_key_rotation=passed
old_bootstrap_rejected=passed
phi_envelope_preserved=passed
audit_tamper_detected=passed
audit_tail_rollback_detected=passed
generation: create=1, KEK rotate=2, bootstrap rotate=3
audit records=6, head verification=passed
final keys: drill-kek-v1=decrypt-only, drill-kek-v2=active
```

演练工具不输出生成的 key、PHI envelope、临时路径或审计 signing key。

## 5. 真实 PostgreSQL 验证

真实 revision 072 生命周期新增 bootstrap 轮换检查：

1. v1 → v2；
2. encrypted key store generation 1 → KEK rotation generation 2；
3. 全临床 PHI 列只重包裹 DEK；
4. bootstrap rotation generation 2 → 3；
5. 旧 bootstrap 被拒绝；
6. 新 bootstrap 可读取数据库历史 PHI；
7. 数据库原始 envelope 字符串在 bootstrap 轮换前后完全一致；
8. populated 072 → 070 → 072 回退恢复继续通过。

联合验证结果：`34 passed`。当前测试库仍为 revision 072、83 张表、71 项 PHI 约束。

## 6. 回归与工程验证

- 软件 HSM、审计链、cloud config、PHI、审计、scanner、role provisioning：`109 passed`。
- 真实 PostgreSQL PHI/RLS/audit/migration：`34 passed`。
- 独立灾备演练：全部场景通过。
- Python compileall：通过。
- GitHub Actions YAML：解析通过。
- Git diff whitespace：通过，仅保留 Windows CRLF 提示。
- 数据库部署角色：上一基线的 92 objects / 7 functions / zero drift 保持不变。

## 7. CI 发布闸门

PR `P1 PHI / Multi-tenant Release Gate` 现在：

1. 生成彼此不同的一次性 bootstrap、ops-audit 和 application-audit keys；
2. 在 runner temp 建立 encrypted key store 和独立 ops audit；
3. create 必须带 CI run/attempt change ticket；
4. 验证 ops audit 至少包含 started/completed 两条记录；
5. 运行完整自包含灾备演练；
6. 执行 PostgreSQL provisioning、migration、PHI、RLS 和轮换测试。

GitHub 托管远程执行需在分支推送或建立 PR 后发生；本地已完成 YAML 解析和同等 Python/
PostgreSQL 测试。

## 8. 生产运行要求

本地 cryptographic append chain 是 tamper-evident，不是对 privileged host administrator 的绝对
物理不可变存储。生产必须：

1. 持续复制每条 JSONL record 和 chain head 到 Object Lock/WORM 或独立审计平台；
2. 将 minimum sequence checkpoint 保存在不同的受控系统；
3. audit key、bootstrap key、key store 和审计文件分别存储、分别授权；
4. 更新 generation/minimum sequence 采用 change-ticket 和双人复核；
5. 设置 audit file 容量监控；16 MiB 上限触发前必须进行受控链续接和归档；
6. 禁止 core dump，使用加密磁盘/swap，并验证 Linux ownership/mode 或 Windows service ACL；
7. 定期在 disposable restore database 重复演练，而不只运行纯文件模拟。

## 9. 已知剩余工作

- 将 ops audit 实时复制到真正 WORM sink，并验证 retention/legal hold/export。
- 设计独立 audit signing key 的轮换与多 signer 历史验证；当前一条链使用一个 key ID。
- 增加审计链容量 rollover/continuation record，避免达到 16 MiB 后只能 fail closed。
- 自动关联 operator identity；当前 change ticket 由调用方提供，身份需由 CI/IAM/WORM sink 补充。
- 执行主机级故障演练：容器重建、磁盘只读、ACL 漂移、secret manager 短暂不可用和多副本滚动。

## 10. 发布判断

软件 HSM 文件级灾备和离线生命周期审计已经形成可重复、可阻断、可验证的开发基线。四个用户
指定场景全部通过，bootstrap 轮换不触碰数据库密文。阶段性发布仍须满足第 8 节的独立 WORM、
外部 checkpoint 和主机保护条件；不能把本地 JSONL 链描述为能抵抗主机管理员删除的物理 WORM。
