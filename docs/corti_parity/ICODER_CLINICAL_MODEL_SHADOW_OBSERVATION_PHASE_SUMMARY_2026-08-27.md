# iCoDer 临床模型合成 shadow observation、停止与自动回滚阶段总结（2026-08-27）

## 结论

本阶段完成了开发/测试环境内、与患者请求及生产 Runtime 完全解耦的合成 shadow observation 状态机。已通过签名 attestation 绑定的仓库合成模型包会执行固定三轮隔离探针，只持久化哈希、计数和延迟聚合；门禁状态为 `not_evaluated`、`passed` 或 `stopped`。受控超时、畸形响应和模型摘要漂移都会失败关闭；存在一致的 previous binding 时原子交换当前/上一 package 与 attestation，并写入单独的自动回滚审计。

该结果证明的是开发状态机、停止策略和故障恢复合同，不是真实患者 shadow traffic、真实临床模型质量、Corti 托管 Models 等价或医院上线批准。接口仍固定声明不使用患者数据、不保存输入、不输出预测、不联网且不启用生产推理。

## 已实现

1. Alembic `060` 为 shadow binding 增加评估门禁和最近评估指针，并新增组织隔离的 `clinical_model_shadow_evaluations` 聚合记录；fresh Alembic head 与 ORM 无漂移。
2. 固定 observation suite 对已重新验签的 bundle 连续执行三轮 `python -I -S` 隔离合成探针，至少形成 6 个向量观察；模型摘要漂移、错误、结果不完整、观察不足或 P95 超限均停止。
3. observation 报告具有精确字段集、自哈希、suite/policy 哈希、64 位小写摘要校验，以及 source、fault mode 与 `artifact_reverified` 的互斥组合校验；篡改失败关闭。
4. 三种受控故障 `worker_timeout`、`malformed_response`、`model_hash_mismatch` 不执行 artifact、不接受病例或自由文本，并必须由 owner/admin 明确确认故障注入。
5. `POST /api/v1/clinical-model-packages/shadow-bindings/{use_case}/synthetic-evaluation` 采用两阶段乐观锁：隔离运行前捕获不可变绑定快照并释放读事务，完成后重新锁定组织与 binding；期间版本或 attestation 变化即拒绝写入。
6. 通过时门禁更新为 `passed`；停止时先标记 `stopped`。若存在且仍有效的 previous package/attestation，则原子交换并将新当前绑定重置为 `not_evaluated`；没有 previous 时保持停止，不伪造回滚成功。
7. 评估和自动回滚分别写入固定、无正文的组织审计；列表接口受成员权限与租户边界保护，跨租户返回 404。
8. 开关 `ICODER_CLINICAL_MODEL_SHADOW_EVALUATION_ENABLED` 默认关闭，且仅允许 local/development/dev/test；cloud/production 始终拒绝。
9. Console 明示三态门禁、受控故障与自动回滚边界；JavaScript、Python 和 .NET SDK 均增加评估与历史列表合同，候选版本为 JS/.NET `1.0.0-beta.46`、Python `1.0.0b46`，尚未发布。

## 验证证据

| 范围 | 结果 |
|---|---:|
| observation 服务、API 与 fresh schema drift 聚焦回归 | 13/13 |
| JavaScript SDK 全量 | 97/97 |
| Python SDK 全量 | 103/103 |
| .NET SDK net8.0 | 85/85 |
| .NET SDK net10.0 | 85/85 |
| 前端全量 | 166/166，production build passed |
| OpenAPI | 286 paths / 314 schemas；940,150 bytes；check passed |
| Alembic | 单 head `060`；fresh head 与 ORM 0 drift |
| 静态部署预检 | 114/114 |

合成 observation 证据：[`clinical_model_shadow_observation.json`](../../reports/deployment/clinical_model_shadow_observation_20260827_v1/clinical_model_shadow_observation.json)，文件 SHA-256 `a6be9e46e63ac3fe88eac19f179ed2868ea55f15ae65be06ad9c359568a44541`；内部 report SHA-256 `6bac4491707d8598611c2095b578f3f34aacf5683edcc3ecdd347e87fe02c2ec`。正常三轮观察为 `passed`，三类故障均为 `stopped`，证据明确 `real_shadow_traffic_used=false`、`production_inference_enabled=false`、`corti_capability_parity_proven=false`。

部署预检：[`deployment_preflight.json`](../../reports/deployment/development_preflight_20260827_shadow_observation/deployment_preflight.json)，SHA-256 `72e04b31a2d7a76395af6a3fd3bca19446e05c644113bb01c5f615d955c8694a`。OpenAPI SHA-256 为 `bb39e9506a217002f5208bcffd3b0a6d6fb854ace99ffa9fe7d34b26152548c2`。

## 数据、凭据与进程边界

- `backend/data/icoder.db` 保持 8,536,064 bytes、mtime `2026-08-22 17:16:22`、SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。
- `E:\iCoDerA\data\train.xlsx` 保持 6,890,295 bytes、mtime `2026-04-28 16:38:10`、SHA-256 `4c0461036016d1a05edfb565d8b639fd4429e7f48951803f8a4527197c1472d8`。本阶段没有解析 workbook、读取病例行或生成病例级 artifact，只复核终态哈希。
- 没有使用 LLM key、外部 Provider、Corti API、患者数据或真实模型；进程、用户和机器级 `ICODER_CREDENTIAL_LLM` 最终长度均为 0。

## 与 Corti 的剩余差距

1. 当前 observation 只使用仓库自有合成向量；没有同一真实病例分别流经 iCoDer 与 Corti 的盲法 head-to-head，也没有独立临床 gold/reviewer。
2. 没有患者请求镜像、实时去标识服务、consent/授权、生产 shadow queue、对象存储、分布式 worker、容量、长稳、告警或值班响应。
3. 当前延迟阈值验证的是本机合成子进程，不代表真实模型 P95、首 token、并发吞吐、成本或 SLA。
4. 自动回滚已在 API/数据库事务和合成故障中验证，但尚未在真实模型进程、容器编排、医院私有化或云多副本部署中演练。
5. 开发签名、scanner 与 `python -I -S` 仍不等于生产 HSM/KMS、独立 AV/OCR/DLP、seccomp/AppArmor/容器隔离或供应商 provenance。
6. 许可、再分发、独立临床验证、医院/云用途、法务伦理、生产变更和灾备批准仍是不可由开发环境替代的外部门禁。

## 下一阶段建议

开发环境内可继续完成生产适配接口：shadow traffic 的去标识证明与只读采样协议、分布式 observation worker/lease、对象存储和 KMS/AV/OCR/DLP adapter、指标告警与回滚控制面的故障注入，以及不含病例正文的容量/长稳模拟。真实模型、真实患者流量、独立临床 gold、Corti 同病例比较与医院上线仍必须等待合法资产和外部审批。
