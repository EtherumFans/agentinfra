# iCoDer 临床模型 shadow 作业运营韧性阶段总结（2026-08-27）

## 结论

本阶段已在上一轮持久化分布式 shadow 作业控制面之上，补齐可治理取消、取消 fencing、租户级聚合健康、确定性告警判定和受限维护清扫。开发环境中的创建、领取、续租、结算、取消、过期恢复、尝试耗尽与维护路径现在形成闭环；JavaScript、Python、.NET SDK、Console 和 OpenAPI 使用同一契约。

本阶段达到的是“开发环境运营控制面发布候选”，不证明真实临床模型质量、真实患者 shadow traffic、生产队列、多区域韧性或 Corti Models 整体能力等价。证据继续固定声明 `aggregate_only=true`、`patient_data_used=false`、`predictions_emitted=false`、`network_used=false`、`production_inference_enabled=false` 和 `corti_capability_parity_proven=false`。

## 已完成

1. Alembic `062` 为 shadow job 增加取消原因、取消时间和操作人，数据库约束保证取消字段与 `cancelled` 状态一致；当前只有单一 migration head `062`。
2. owner/admin 可取消 `queued` 或 `running` 作业。取消会原子清除活动 binding、lease token、worker 和过期时间；已取消作业重复请求保持幂等，终态作业返回 409，跨租户请求返回不透明 404。
3. 取消与 worker 结算共享条件更新和 token fence。运行中作业被取消后，持有旧 lease 的 worker 不能再写入 passed、stopped、failed 或触发回滚。
4. 新增组织级健康摘要，输出固定六态计数、到期排队数、活动/过期租约数、尝试耗尽数和最老排队年龄，不输出 job ID、binding ID、租户 ID、输入或患者字段。
5. 健康状态按配置阈值确定性产生 `queue_backlog`、`queue_age_exceeded`、`expired_leases` 和 `exhausted_jobs` 告警码；测试覆盖 degraded 状态和恢复后的 healthy 状态。
6. 新增 owner/admin 维护入口，对当前组织执行有上限的 exhausted-job 终态化；仅在 local/dev/test 且显式允许模拟时可执行，不会跨租户清扫。
7. worker 启动时先执行有界 exhausted-job sweep；标准输出仍只有聚合计数，不包含凭据、患者数据或作业标识。
8. 取消审计只允许取消枚举和服务器生成的操作人 ID；lease token、幂等键、输入和 bundle 即使误传也会被 redactor 移除。
9. JavaScript、Python 和 .NET Models SDK 已加入 cancel、health、maintenance 合同；Console Models 页面展示聚合健康和告警。候选版本为 JavaScript/.NET `1.0.0-beta.48`、Python `1.0.0b48`，尚未发布。
10. 修复了开发中发现的路由歧义：健康与维护端点采用 `/shadow-evaluation-jobs/health/summary` 和 `/shadow-evaluation-jobs/maintenance/run`，避免被 package 通配路由吞掉。

## 验证结果

| 范围 | 结果 |
|---|---:|
| 运营控制面 API/数据库证据重放 | 1/1 |
| bundle、observation、作业、schema drift、审计聚焦回归 | 24/24 |
| fresh Alembic head 与 ORM schema drift | 2/2；单 head `062` |
| JavaScript SDK 全量 | 97/97 |
| Python SDK 全量 | 103/103 |
| .NET SDK net8.0 | 87/87 |
| .NET SDK net10.0 | 87/87 |
| 前端全量 | 173/173 |
| 前端 production build | passed；仅保留既有动态/静态 import chunk 提示 |
| OpenAPI | 292 paths / 320 schemas；963,020 bytes；export check passed |
| 静态部署预检 | 116/116 |

运营证据：[`clinical_model_shadow_job_operations.json`](../../reports/deployment/clinical_model_shadow_job_operations_20260827_v1/clinical_model_shadow_job_operations.json)，文件 SHA-256 `c55f4ce33588294048c3bf0f9f106aed40bc1dcafe452a82a8f252b690d3a66d`，内部 report SHA-256 `99dea7b2b13f2c393349fec56cd6906a96b74b1ebb30af6d31a27b6e5daf3f26`。

部署预检：[`deployment_preflight.json`](../../reports/deployment/development_preflight_20260827_shadow_job_operations/deployment_preflight.json)，SHA-256 `5105ef7fdd7768a6ae3d0ee81a861ec67002dea911ad949cbc70ce9ccf8090b9`。OpenAPI SHA-256 为 `d24cf076443748373d8fffdd10f1bb1980bbc8ac7039798d9615f366fc4b69c0`。

## 数据、凭据和进程边界

- `backend/data/icoder.db` 保持 8,536,064 bytes、mtime `2026-08-22 17:16:22`、SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。
- `E:\iCoDerA\data\train.xlsx` 保持 6,890,295 bytes、mtime `2026-04-28 16:38:10`、SHA-256 `4c0461036016d1a05edfb565d8b639fd4429e7f48951803f8a4527197c1472d8`。本阶段没有解析 workbook 或读取病例行；runner 只计算整文件哈希。
- 没有使用 LLM Key、外部 Provider、Corti API、真实模型或患者数据。进程、用户和机器级 `ICODER_CREDENTIAL_LLM` 最终长度均为 0。
- 本阶段 11 个核心源文件与证据文件的通用 API Key 形态扫描为 0 命中；没有留下 shadow worker、uvicorn 或测试 Python 进程。

## 与 Corti 的剩余能力差距

1. 当前队列仍是业务数据库状态机，不是生产 broker；缺少死信队列、受治理重放、优先级、backpressure、autoscaling、容量模型和跨区域投递证明。
2. 当前健康接口提供聚合状态与确定性告警码，但尚未接 Prometheus/OpenTelemetry exporter、PagerDuty/企业微信等告警投递、SLO burn-rate、值班升级和告警抑制。
3. 取消 fencing 已在数据库竞争条件下验证，但尚未进行真实多进程 kill、网络分区、数据库主备切换、时钟偏差、重复投递风暴和区域灾备演练。
4. maintenance 仅提供组织级、有界 exhausted sweep；尚无生产 scheduler、leader election、dead-letter replay 审批、批次签名和跨服务补偿事务。
5. 自动回滚仍只改变 shadow binding 元数据，没有联动真实模型容器、流量路由、对象存储、KMS/HSM、变更审批和医院私有化编排。
6. 没有真实患者 shadow traffic、真实临床模型、独立 gold/reviewer 或与 Corti 的同病例盲法 head-to-head，因此不能给出质量、严重错误、遗漏、延迟、吞吐、成本或 SLA 等价结论。

## 下一阶段

开发环境可继续完成 queue/object-store/KMS/AV-DLP adapter 接口、dead-letter 与受治理重放、OpenTelemetry 指标导出、告警状态机、独立 scheduler/leader lease，以及隔离子进程中的 kill/重复投递/时钟偏差故障注入和聚合容量长稳测试。真实 patient shadow、临床质量和 Corti 同病例对标仍必须等待合法数据资产、独立 reviewer、医院审批和生产基础设施。
