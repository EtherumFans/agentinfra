# iCoDer 临床模型包治理阶段总结（2026-08-27）

## 结论

本阶段完成了可在开发环境内闭环的临床模型控制面，但没有把 CCL 数据、病例、模型文件或预测器接入 Runtime。iCoDer 现在可以按组织登记不可变模型包版本，执行提交、不同用户四眼审批、带乐观锁的激活、切换和严格回滚，并对不满足许可、独立金标准、独立 reviewer、医院或云授权的包失败关闭。

这是一套 **metadata-only 治理选择**，不是模型部署器。API、数据库、SDK 和 Console 都明确返回 `runtime_loading_enabled=false`；模型二进制、训练行、病例文本、患者标识、凭据和本地路径均不被该控制面接受或保存。

## 已实现

1. Alembic `058` 新增 `clinical_model_packages` 与 `clinical_model_activations`：模型包以组织、package key 和版本唯一，激活以组织和 use case 唯一。
2. 模型包登记只接受固定结构的 manifest：包/训练数据/评价证据 SHA-256、聚合病例数、用途、运行合同、许可及外部门禁布尔状态；Pydantic `extra=forbid` 阻断 artifact path、模型内容和自由病例字段。
3. 生命周期为 `draft → submitted → approved/rejected → active`；不存在修改 manifest 的接口，生命周期变更使用 `record_version` 乐观锁。
4. 创建者不能审批自己的包。审批只接受固定 reason code 与 review evidence SHA-256，不接受自由文本意见；平台四眼与外部独立临床 reviewer 仍是两个不同门禁。
5. 激活前统一检查：workflow approval、许可 verified、再分发授权、独立 gold、独立 reviewer、review evidence、四眼；医院私有或云部署还必须有医院使用授权，云部署另需云授权。
6. 激活首写先锁组织行，避免尚无 activation row 时的并发竞态；后续切换锁 activation row 并使用 expected version。
7. 回滚只能指向 activation 当前记录的 `previous_package_id`，不能把任意已批准包伪装成 rollback。
8. create/submit/approve/reject/activate/rollback 均写组织级、无病例正文的审计事件。
9. OpenAPI、JavaScript/Python/.NET SDK 与 Console Models 页面同步到该控制面；三 SDK 版本提升至 `beta.44/b44`，尚未发布。
10. Console 只读展示每个包的许可、再分发、医院、云、独立 gold 和独立 reviewer 门禁，并明确“运行时模型装载：关闭”。

## 对 CCL 2026 本地监督基线的实际影响

先前 CCL 五折 OOF 基线可登记其聚合证据摘要，但按已知事实必须保持：

- `license_status=external_review_required`
- `redistribution_authorized=false`
- `cloud_use_authorized=false`
- `hospital_use_authorized=false`
- `independent_gold_validated=false`

API 回归证明，即使另一个组织管理员完成 workflow review，这类同工作簿 OOF 包仍会得到 `CLINICAL_MODEL_PACKAGE_ACTIVATION_BLOCKED`，至少包含 license、redistribution、independent gold、hospital use 和 cloud use 五项阻断原因。因此本阶段没有通过“登记”绕过此前安全结论。

## 验证证据

| 范围 | 结果 |
|---|---:|
| 临床模型包、Models、组织角色、迁移漂移、OpenAPI、预检聚焦后端 | 24 passed |
| JavaScript SDK 全量 | 96/96 |
| Python SDK 全量 | 102/102 |
| .NET SDK net8.0 | 83/83 |
| .NET SDK net10.0 | 83/83 |
| .NET Framework 4.6.2 最低消费者 | 0 warnings / 0 errors |
| 前端 Models + OpenAPI 合同 | 77/77，production build passed |
| OpenAPI | 280 paths / 306 schemas；临床模型包 6 paths / 8 operations |
| Alembic | 单 head `058`；fresh head 与 ORM 0 drift |
| 静态部署预检 | 112/112 |

部署预检证据：[`deployment_preflight.json`](../../reports/deployment/clinical_model_package_governance_20260827_v1/deployment_preflight.json)，文件 SHA-256 `c1d3e19c62379d8ac178a15b4d8d2a1b0ccb5e7756ad8218599493a9a59721e3`。

提交的 OpenAPI 文件为 909,934 bytes，SHA-256 `fed0f28bb167b6ca28a21a6a9424964723bd9e4dd2e7daa3e42c98db11eba744`。

## 数据与凭据复核

- `backend/data/icoder.db`：8,536,064 bytes；mtime `2026-08-22 17:16:22`；SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`，未迁移、未切换、未改变。
- `E:\iCoDerA\data\train.xlsx`：6,890,295 bytes；mtime `2026-04-28 16:38:10`；SHA-256 `4c0461036016d1a05edfb565d8b639fd4429e7f48951803f8a4527197c1472d8`，未改变。
- 本阶段没有读取或输出病例正文，没有调用外部 Provider；`ICODER_CREDENTIAL_LLM` 在终态不存在。

## 尚未完成且不能在代码中伪造

1. CCL 或其他数据的正式许可、再分发、云处理和医院用途授权。
2. 与训练工作簿完全独立的临床 gold、双盲 reviewer、误差/偏差和亚组评估。
3. 模型 artifact 的安全构建、签名、SBOM、恶意文件扫描、对象存储、KMS、下载与加载隔离。
4. Runtime predictor 接口、影子流量、canary、自动回滚、容量、延迟、长期稳定性和生产故障演练。
5. 相同授权病例的 Corti head-to-head，以及 Corti 私有模型治理语义验证。
6. 医院 IT、临床、法务、伦理、等保/个保、采购与生产变更审批。

因此本阶段关闭的是“缺少组织级临床模型治理控制面”的开发差距；临床模型 Runtime、Corti 托管 Models 等价和中国医院生产准入仍保持开放。
