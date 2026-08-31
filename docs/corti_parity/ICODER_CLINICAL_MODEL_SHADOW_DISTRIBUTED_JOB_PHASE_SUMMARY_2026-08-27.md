# iCoDer 临床模型分布式 shadow 作业控制面阶段总结（2026-08-27）

## 结论

本阶段已把上一轮同步合成 shadow observation 扩展为开发/测试环境可运行的持久化异步作业控制面。作业创建强制使用幂等键，同一 shadow binding 同时只能有一个活动作业；worker 通过有期限的随机 fencing token 领取和续租，租约过期后可由另一 worker 接管，原 worker 的迟到结果不能写入终态。尝试耗尽会失败关闭并释放活动槽位，受控故障只执行一次受审计回滚。

这证明的是仓库合成 fixture、临时测试数据库和开发 worker 下的控制面语义，不是真实患者 shadow traffic、真实临床模型质量、生产消息队列或 Corti Models 等价。所有接口仍固定声明 `aggregate_only=true`、`patient_data_used=false`、`predictions_emitted=false`、`network_used=false` 和 `production_inference_enabled=false`。

## 已实现

1. Alembic `061` 新增组织隔离的 `clinical_model_shadow_evaluation_jobs`：状态为 `queued/running/passed/stopped/failed/cancelled`，保存不可变 binding/package/attestation 快照、请求摘要、尝试上限、租约、评估和回滚指针；唯一活动槽位阻止同一 binding 并发执行。
2. 创建 API 强制合法 `Idempotency-Key`。相同 key 与相同请求返回同一作业；相同 key 与不同请求返回 409；并发唯一约束冲突也按请求摘要失败关闭。
3. claim/renew/settle 均使用 worker ID、随机 lease token 和未过期时间窗进行条件更新。续租前其他 worker 不能接管；过期接管产生新 token；旧 worker 的完成、失败或回滚写入均被 fence 拒绝。
4. worker 崩溃后允许恢复；超过 `max_attempts` 的过期或排队作业由 sweeper 终态化为 `failed`，清除租约并释放 binding 活动槽位，不形成永久卡死。
5. 结算前重新锁定组织与 binding 并核对不可变版本、package 与 attestation。绑定变化时写入安全失败审计，不接受旧快照的结果。
6. 正常作业重新验签仓库 fixture 并执行固定三轮 observation；受控 `worker_timeout`、`malformed_response`、`model_hash_mismatch` 仍按停止策略处理。需要回滚时只恢复一致 previous binding 一次。
7. 新增开发 worker CLI。默认只读 dry-run；只有 local/dev/test、显式模拟开关和 `--execute` 同时成立才处理队列。标准输出只包含聚合 outcome 数，不输出租户、作业、artifact、token 或患者标识。
8. 作业读取按组织隔离，跨租户返回 404。审计保留服务器生成的 ID、摘要、枚举与计数；幂等键、lease token、bundle、输入和患者正文均不进入审计，redactor 对误传字段继续失败关闭。
9. JavaScript、Python 和 .NET SDK 已加入 create/list/get/development-execute 合同；Console 明示异步幂等、租约恢复、旧 worker 拒绝和尝试耗尽边界。候选版本为 JS/.NET `1.0.0-beta.47`、Python `1.0.0b47`，尚未发布。

## 验证证据

| 范围 | 结果 |
|---|---:|
| 分布式作业完整 API/数据库契约及证据重放 | 1/1 |
| clinical package API + observation 服务 | 11/11 |
| bundle、observation、作业、schema drift、审计聚焦回归 | 24/24 |
| fresh Alembic head 与 ORM schema drift | 2/2；单 head `061` |
| JavaScript SDK 全量 | 97/97 |
| Python SDK 全量 | 103/103 |
| .NET SDK net8.0 | 86/86 |
| .NET SDK net10.0 | 86/86 |
| 前端全量 | 170/170；production build passed |
| OpenAPI | 289 paths / 317 schemas；954,300 bytes；check passed |
| 静态部署预检 | 115/115 |

分布式作业证据：[`clinical_model_shadow_job.json`](../../reports/deployment/clinical_model_shadow_job_20260827_v1/clinical_model_shadow_job.json)，文件 SHA-256 `4d0d6633b8dbdaca486cce0d9e3b0da4c848f3043eff346b50a5f1f5425fb389`，内部 report SHA-256 `c39fa8f83fea4b628dae6584bdcab952a8eb3f107e59092767ffeeb4d8d9f4ec`。证据明确 `stale_worker_terminal_mutation_blocked=true`、`active_slot_released_after_exhaustion=true`、`real_shadow_traffic_used=false` 和 `corti_capability_parity_proven=false`。

部署预检：[`deployment_preflight.json`](../../reports/deployment/development_preflight_20260827_shadow_job/deployment_preflight.json)，SHA-256 `0f205b133c194f5cf4134189f44f2525a1a86d8505baa605c61691376d2fd215`。OpenAPI SHA-256 为 `90f5df49fc16ebbd3f8543a4c612db46b3d1344a9852e63f93af8f32f48a0032`。

## 数据、凭据与进程边界

- `backend/data/icoder.db` 保持 8,536,064 bytes、mtime `2026-08-22 17:16:22`、SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。
- `E:\iCoDerA\data\train.xlsx` 保持 6,890,295 bytes、mtime `2026-04-28 16:38:10`、SHA-256 `4c0461036016d1a05edfb565d8b639fd4429e7f48951803f8a4527197c1472d8`。本阶段没有解析 workbook 或读取任何病例行；只在 release runner 前后计算整文件哈希。
- 没有使用 LLM Key、外部 Provider、Corti API、患者数据或真实模型。进程、用户和机器级 `ICODER_CREDENTIAL_LLM` 最终长度均为 0；本阶段未留下持久 worker 或测试服务进程。

## 与 Corti 的剩余差距

1. 当前 job payload 不能接收患者数据，只能解析仓库合成 fixture；没有合法授权、去标识、consent、采样和数据保留证明下的真实 shadow 流量。
2. 当前持久队列使用业务数据库状态机；没有生产 broker、独立 worker deployment、跨主机/跨区域一致性、死信、优先级、backpressure、autoscaling、容量或长稳证明。
3. 已验证 token fence 和崩溃接管语义，但尚未做真实进程 kill、网络分区、数据库 failover、时钟偏差、重复投递风暴和区域灾备演练。
4. 自动回滚只改变 shadow binding 元数据；尚未联动真实模型容器、流量路由、对象存储、KMS/HSM、监控告警、变更审批或医院私有化编排。
5. 没有真实临床模型、独立临床 gold/reviewer、同病例 Corti 盲法 head-to-head，也没有质量、严重错误、遗漏、延迟、吞吐、成本或 SLA 结论。
6. Corti Models 的托管模型池、模型供应商生命周期、真实健康探针、计费/配额、区域部署和商业支持仍未复刻；医院、法务、伦理、认证与云批准仍是外部门禁。

## 下一阶段建议

开发环境下一步应实现不含病例正文的生产适配层：可替换 queue/object-store/KMS/AV-DLP adapter、作业取消与死信/重放、指标与告警状态机、时钟偏差和多进程 kill/网络故障注入、聚合容量与长稳测试。真实 patient shadow、临床质量和 Corti 同病例对标必须在合法资产、独立 reviewer 与医院审批到位后单独执行。
