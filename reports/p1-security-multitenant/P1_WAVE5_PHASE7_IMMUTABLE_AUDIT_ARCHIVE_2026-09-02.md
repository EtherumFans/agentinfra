# P1 Wave 5 Phase 7：不可变审计归档生产化审查报告

- 日期：2026-09-02（Asia/Shanghai）
- 分支：`codex/p1-security-multitenant-gates`
- 前置基线：`4d03d20d969a95e4359a411c4a144abd1e6078d8`
- 核心实现：`0b173f4e`
- CI 门禁：`c66efc25`
- 云环境 fail-closed 加固：`870b3858`
- 候选标签：`p1-wave5-phase7-candidate-20260902`
- 数据库 schema：revision `072`（本阶段无 schema 变更）
- 阶段判断：不可变归档的 provider-neutral 契约、本地 WORM 模拟器和发布门禁已建立；真实云 WORM 适配器尚未选型和认证，因此结论是“工程基线完成、生产外部依赖未关闭”。

## 1. 审查结论

Phase 6 的本地 JSONL 密码学链只能发现内容篡改，并不能阻止有主机管理员权限的人删除整条链或
回滚链尾。Phase 7 把密钥库生命周期变更改为：本地 signed chain、逐记录 create-only archive
object、独立签名 checkpoint 三层证据，并在密钥库突变前强制完成归档和复验。

已完成的核心能力：

| 能力 | 结果 | 证据 |
|---|---|---|
| WORM/provider-neutral 接口 | 完成 | `AuditArchive` 契约隔离归档实现 |
| 本地 WORM 模拟器 | 完成 | create-only object、只读文件、拒绝覆盖 |
| 写前 fail closed | 完成 | started 未归档并复验时不调用密钥库 callback |
| 独立 chain-head checkpoint | 完成 | 独立 key/key ID 对 sequence 与 head hash 签名 |
| 审计 signing key 轮换 | 完成 | active writer + 最多 16 个历史 verifier keys |
| 16 MiB rollover | 完成 | 编号 segment，global sequence/hash 连续 |
| retention / Legal Hold | 完成 | 模拟器删除 API 在保留期或 hold 下拒绝 |
| 最小化证据导出 | 完成 | create-new-only export，不携带任何 key/PHI/ciphertext |
| operator/release 上下文 | 完成 | operator、environment、release version 纳入 event payload hash |
| 删除后恢复 | 完成 | 从 archive objects 重建本地 JSONL 并全链复验 |
| 跨区域恢复模拟 | 完成 | 复制归档到独立 root 后复验相同 chain head |

## 2. 安全设计

### 2.1 写入顺序

每次 `create`、`rotate`、`rotate-bootstrap` 或 `set-state`：

1. 校验 change ticket、active audit signer、historical keyring 和独立性；
2. 向本地链追加 `started/pending`；
3. 将从 genesis 到当前 head 的缺失记录幂等写入 WORM，并写独立 checkpoint；
4. 立即从 WORM 读取和验证全部 records 与最新 checkpoint；
5. 只有第 4 步成功才执行密钥库原子突变；
6. 失败时追加并归档 `failed/failure`；成功时追加并归档 `completed/success`；
7. completion 归档失败则命令失败，禁止把“密钥已改但证据未对账”报告为成功。

这保证归档不可用不会导致新的密钥库突变静默成功。它不能提供跨两个不同存储系统的严格原子
事务，因此突变完成而 completion 归档失败仍是需运维对账的显式状态，而不是被掩盖的成功。

### 2.2 对象与 checkpoint

归档 object 名称由 20 位 sequence 与 64 位 chain hash 构成。内容包括原始 signed record、归档
时间、retention deadline 和 Legal Hold，并由独立 checkpoint key 再签名。相同名称、相同记录
可幂等重放；相同名称、不同内容被拒绝。checkpoint 是按 sequence/head hash 命名的 create-only
对象，覆盖完整链头位置。

checkpoint key 被明确禁止与 ops-audit key、旧 bootstrap key 或新 bootstrap key 相同。由此，
攻陷单个密钥域不足以同时伪造本地记录签名和归档元数据/checkpoint。

### 2.3 签名轮换

记录继续使用 schema `icoder.software-hsm-ops-audit/v1`，不破坏 Phase 6 证据。验证器根据每条记录
的 `signing_key_id` 从历史 keyring 选择 key；writer 只使用当前 active key。测试链同时含 v1/v2
签名记录，并在本地文件、WORM 和恢复文件三个位置成功复验。

需要准确说明：HMAC 能证明“持有共享 key 的受控系统产生了记录”，但不能在多个共享 key 持有者
之间提供密码学意义上的公开不可抵赖。若合规要求严格 non-repudiation，下一阶段应改用 HSM 托管的
非对称签名和外部可信时间戳。

### 2.4 分段续链

单个 spool 文件上限保持 16 MiB。达到阈值后创建 `.000002`、`.000003` 等 segment。新 segment
不重置 sequence 或 previous hash；因此移动、遗漏、重复或重排 segment 都会在全局验证时失败。
本地全部 segment 总读取上限为 256 MiB，长期权威副本是逐记录 WORM objects。

## 3. 数据最小化

Phase 7 扩展事件仅加入严格格式的：

- operator identity；
- deployment environment；
- immutable release version。

仍只保存 key-store path 的 SHA-256 截断标识、generation、key ID/state、异常类名和 change ticket。
白名单结构拒绝额外字段、换行和不受控自由文本。归档与导出不包含绝对路径、异常消息、数据库
URL、audit/checkpoint/bootstrap key、KEK、DEK、PHI 或 ciphertext。

## 4. 攻击与恢复验证

新增测试覆盖：

- record 内容篡改；
- object 丢失/链尾删除；
- 重复 object；
- sequence/previous hash 重排或断裂；
- checkpoint 缺失、内容或签名不一致；
- active signing key 从 v1 在线切换到 v2，历史记录继续验证；
- 本地主机 journal 删除后从 WORM export 重建；
- 将完整 archive 复制到独立 root 的跨区域恢复模拟；
- retention deadline 未到时删除被拒绝；
- Legal Hold 在保留期后仍阻止删除；
- archive root 不存在时密钥库 callback 不执行；
- 单段容量达到阈值后自动 rollover，global chain 连续；
- export 不含测试 key 和 PHI 标记。

## 5. 验证结果

### 5.1 Phase 7 定向验证

```text
17 passed in 3.95s
Python compileall: passed
GitHub Actions YAML parse: passed
git diff --check: passed
```

### 5.2 Phase 6 灾备兼容

自包含灾备演练继续全部通过：

```text
status=passed
key_store_missing=passed
bootstrap_key_missing=passed
generation_floor_rollback=passed
bootstrap_key_rotation=passed
old_bootstrap_rejected=passed
phi_envelope_preserved=passed
audit_tamper_detected=passed
audit_tail_rollback_detected=passed
audit records=6; segments=1
```

### 5.3 扩大安全回归

PHI revision 071/072、应用审计、OAuth rejection、配置 fail-closed、artifact scanner、软件 HSM、
独立审计链和归档合计：`117 passed, 1 failed`。

失败项：

`tests/unit/app/test_p1_database_session_audit.py::test_stale_membership_never_becomes_database_authority`

该文件和 `app/middleware/auth.py` 均未被 Phase 7 修改。现实现为了查询受 RLS 保护的 membership，先调用
`bind_tenant_to_transaction` 再判定 membership；测试却断言 membership 不存在时 binder 从未调用。
失败可独立复现，属于 2026-09-01 以来的既有实现/测试语义不一致。本阶段不擅自改变认证/RLS 顺序。
因此不能把扩大回归描述为全绿，后续必须专门决定采用“两阶段受限 tenant context”还是调整测试
以区分“RLS 查询上下文”和“授权成功”。

### 5.4 未执行项

- GitHub 托管 CI：只有推送分支/创建 PR 后才能取得远端结果；本地只验证了 YAML 和等价 Python 测试。
- 真实 PostgreSQL 回归：本阶段无 schema/ORM 变更，未重复 revision 072 的 34 项数据库测试。
- 真实跨区域 Object Lock：当前只是两个本地 root 的恢复契约测试，不等同云厂商跨区复制演练。

## 6. CI 发布闸门

PR 的 `P1 PHI / Multi-tenant Release Gate` 现在生成彼此独立的一次性 bootstrap、ops-audit、archive
checkpoint 和 application-audit keys；创建 runner-temp WORM root；要求归档成功；同时验证本地链和
归档 checkpoint；生成 minimum-necessary export；然后继续数据库角色、迁移、PHI/RLS 和轮换测试。

CI 使用 `local_worm_simulator` 是为了验证契约和失败语义，不是声称 GitHub runner 提供生产 WORM。

## 7. 文件与目录卫生

本阶段未在仓库内生成测试输出、临时密钥、归档 objects、checkpoint 或 export。所有测试材料位于
pytest 临时目录或 CI `RUNNER_TEMP`，结束后可清理。新增入库文件只有一个服务模块、两个运维脚本、
一个测试模块、CI 修改、runbook 修改和本报告，没有新增缓存、截图、数据库、构建目录或重复报告。

## 8. 风险与剩余发布阻断项

1. **真实 WORM 适配器未完成。** 必须选定 AWS S3 Object Lock、Azure Immutable Blob、GCP Bucket
   Lock 或独立审计平台，完成 compliance mode、IAM separation、retention、Legal Hold 和跨区复制。
2. **HMAC 不等于严格公开不可抵赖。** 高等级合规需 HSM 非对称签名、证书生命周期和可信时间戳。
3. **completion 双写不是分布式原子事务。** 需建设 reconcile worker、告警和 runbook 演练。
4. **历史 verifier key 保管策略待落地。** 旧 key 必须覆盖最长证据保留期，且不能由普通应用读取。
5. **本地 simulator 可被管理员绕过。** 它只验证代码契约，不能用作生产控制证据。
6. **既有 RLS 测试红项。** 在建立最终 release baseline 前必须关闭或形成经审查的豁免。

## 9. 下一步任务

建议紧接 Phase 7 执行：

1. 选定真实 WORM provider，落地 adapter、独立 IAM/service account 和 compliance-mode policy；
2. 增加 reconcile/alerting，对 started 无终态、completion 未归档、checkpoint lag 实时告警；
3. 将 audit signer 升级为软件 HSM 中的独立非对称 signing key，并演练证书/key rotation；
4. 在真实跨区域 bucket 上执行 object loss、region loss、Legal Hold 和 restore 演练；
5. 专项处理现存 RLS membership test/implementation 语义冲突；
6. 随后执行 PostgreSQL base backup + WAL PITR、revision 072 升降级和密钥库/归档联合恢复演练。

## 10. 发布判断

Phase 7 已把“本地主机上的可篡改证据文件”提升为“可替换 WORM 契约、独立 checkpoint、写前阻断、
多签名 key 历史验证、分段续链、保留/Legal Hold/导出/恢复测试”的可信工程基线。由于真实 WORM
provider、真实跨区演练和严格非对称不可抵赖仍未落地，本阶段不得被表述为生产合规闭环已经完成。
