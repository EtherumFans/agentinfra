# iCoDer 临床模型 artifact 供应链与 shadow-only 阶段总结（2026-08-27）

## 结论

本阶段完成了一个严格限定在开发/测试环境的签名合成模型包供应链：仓库自有合成 bundle 可以经过不可变清单、Ed25519 签名、CycloneDX SBOM、内容扫描、恶意 ZIP 防护和隔离子进程探针，随后只把哈希与聚合结果登记为组织级 attestation，并通过乐观锁绑定到 `shadow_only` 选择。

这不是生产模型部署，也不是实际影子流量。上传 ZIP 与模型内容不持久化；绑定不接收患者数据、不发出预测、不改变现有 Runtime 路由。接口固定返回 `production_inference_enabled=false`、`runtime_inference_enabled=false` 与 `predictions_emitted=false`。

## 已实现

1. 定义 `icoder.clinical-model-bundle/v1`：canonical JSON manifest 精确声明 bundle/version、use case、runtime contract、合成训练集摘要、entrypoint 和文件 SHA-256/大小。
2. 仓库仅保存开发测试公钥 trust anchor；私钥未进入仓库。验证器校验 Ed25519 detached signature、key 状态、artifact class 与 environment scope，开发 key 在 production 环境失败关闭。
3. ZIP/目录读取器限制 bundle 8 MiB、单文件 4 MiB、64 个文件、解压总量 16 MiB、压缩比 100，并拒绝路径穿越、隐藏路径、Unicode 归一化变化、反斜线/盘符、symlink、大小写折叠重复、额外文件和完整性不匹配。
4. SBOM 必须是精确 CycloneDX 1.5 inventory；manifest、SBOM 和 synthetic JSON model 均要求 canonical JSON 且拒绝重复 key。
5. 复用现有 managed Artifact 内容扫描器，拒绝 EICAR、可执行文件、archive/media、可疑 PHI/DLP 内容。该扫描器是开发门，不冒充生产 AV/OCR/DLP。
6. 已验证的 data-only synthetic model 在 `python -I -S`、最小环境、无 stdin、丢弃 stderr、有界 stdout/超时的独立子进程运行固定合成向量；只返回模型哈希和 2/2 聚合计数。它不是 OS/container sandbox。
7. Alembic `059` 新增组织级 `clinical_model_artifact_attestations` 和 `clinical_model_shadow_bindings`。前者只保存签名/SBOM/扫描/探针摘要；后者按组织和 use case 唯一，并保留 previous package/attestation 以支持严格 rollback。
8. 合成探针开关 `ICODER_CLINICAL_MODEL_SYNTHETIC_PROBE_ENABLED` 默认关闭；即使显式开启，cloud/production 环境仍拒绝。只有 `synthetic-shadow-fixture` 包可以调用，包 key/version/content digest/use case/runtime/training digest/count 必须与已登记 manifest 精确一致。
9. attestation 和 shadow binding 都受租户边界、owner/admin 写权限、已审批包、组织行锁和 expected version 控制；审计只记录 ID、哈希、计数和固定布尔边界，不记录 bundle、模型内容、预测或患者数据。
10. OpenAPI、Console 与 JavaScript/Python/.NET SDK 已同步；候选版本为 JavaScript/.NET `1.0.0-beta.45`、Python `1.0.0b45`，尚未发布。

## 验证证据

| 范围 | 结果 |
|---|---:|
| 恶意包、签名、SBOM、scanner、隔离 worker 单测 | 10/10 |
| 临床模型包/attestation/shadow API | 5/5 |
| Alembic fresh head 与 ORM drift | 2/2 |
| 聚焦后端（含 OpenAPI 与预检） | 23/23 |
| JavaScript SDK 全量 | 97/97 |
| Python SDK 全量 | 103/103 |
| .NET SDK net8.0 | 84/84 |
| .NET SDK net10.0 | 84/84 |
| 前端全量 | 164/164，production build passed |
| OpenAPI | 284 paths / 311 schemas；927,606 bytes |
| Alembic | 单 head `059`；fresh head 与 ORM 0 drift |
| 静态部署预检 | 113/113 |

合成供应链证据：[`clinical_model_shadow_supply_chain.json`](../../reports/deployment/clinical_model_shadow_supply_chain_20260827_v1/clinical_model_shadow_supply_chain.json)，文件 SHA-256 `0a06a009039aa1a563ff43247c49d9667ec1f757bcb2dd62e8cfc07e97feef1f`；内部自校验 report SHA-256 为 `68fad072ee49a1581a6f87418c5b297705f49ab13a2b77c25df57af2b3673f88`。

部署预检：[`deployment_preflight.json`](../../reports/deployment/clinical_model_shadow_supply_chain_20260827_v1/deployment_preflight.json)，SHA-256 `df335b4c67aa3905ff9a989d281d9cc82d35769c3110637398bb186b8502e2fe`。

OpenAPI SHA-256 为 `842395934bace84873e2c9df9f3a3713cb900b1970deadb4cc1c86cabd4e696f`。

## 数据与凭据边界

- `backend/data/icoder.db` 保持 8,536,064 bytes、mtime `2026-08-22 17:16:22`、SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。
- `E:\iCoDerA\data\train.xlsx` 保持 6,890,295 bytes、mtime `2026-04-28 16:38:10`、SHA-256 `4c0461036016d1a05edfb565d8b639fd4429e7f48951803f8a4527197c1472d8`。本阶段只做终态完整性哈希复核，没有解析 workbook、读取病例行或生成病例级 artifact。
- 未使用 LLM key、外部 Provider、Corti 调用或患者数据；证据不含 bundle/model bytes 或逐向量预测。

## 与 Corti 的剩余差距

1. 当前 key/trust anchor 只服务仓库开发 fixture，没有生产 HSM/KMS、证书轮换、签名服务、撤销发布流程或供应商 provenance。
2. 当前 scanner 是代码级开发扫描，不是独立 AV/OCR/DLP 服务，也没有生产隔离对象存储、quarantine bucket、一次性下载和审计保留验收。
3. `python -I -S` 子进程是依赖隔离与进程边界，不是 Windows Job Object、Linux seccomp/AppArmor、容器、VM 或硬件级 sandbox。
4. 没有加载真实临床模型，没有对 CCL 或患者流量执行预测，没有 shadow traffic、临床 reviewer、自动回滚、容量/延迟/稳定性和故障演练。
5. 没有 Corti 托管 Models 的相同 artifact、相同病例、相同策略 head-to-head；本阶段不能提升 Corti 能力复刻或临床质量等价结论。
6. 真实模型仍受许可、再分发、独立 gold/reviewer、医院/云用途、法务伦理和生产变更审批门禁约束。

## 下一阶段建议

开发环境内可继续完成：定义与现有 Runtime 完全解耦的 `shadow observation` 聚合合同、输入去标识证明、无预测正文的比较指标、自动停止/回滚策略模拟，以及生产 sandbox/object-store/AV/KMS 的接口与故障注入测试。

在获得合法真实模型、独立临床 gold、医院许可和生产基础设施前，不应把合成 attestation 替换为真实模型加载，也不应把 `shadow_only` 绑定接入患者请求路径。
