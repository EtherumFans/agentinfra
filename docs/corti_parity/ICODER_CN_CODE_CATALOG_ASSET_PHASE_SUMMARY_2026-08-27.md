# iCoDer 中国编码目录资产内置阶段总结（2026-08-27）

## 阶段结论

本阶段已关闭“开发机依赖仓库外 `E:\iCoDerA\data`，容器缺失时静默退化为两个示例码”的工程缺口。经用户明确授权，本项目把当前运行时使用的目录及 CCL 2026 标签覆盖补充目录原字节复制到后端 Docker 构建上下文，并建立代码内信任锚、资产清单、SHA-256、文件大小、原始记录数和有效记录数校验。任一文件缺失、替换、截断、清单漂移或 JSON 损坏均抛出 `CatalogIntegrityError`，不再伪装为完整目录继续启动。

这使目录在开发环境和源码构建上下文中自包含，但不等于生产发布授权已经完成：用户授权范围是本项目内部使用，本阶段不主张这些源数据具有公开再分发许可。由于本机没有 Docker CLI，本轮也没有实际构建、启动或扫描镜像。

## 固定资产

资产目录：`backend/data/code_dicts/assets`

| 文件 | 用途 | 大小 | SHA-256 | 记录 |
|---|---|---:|---|---:|
| `icd10_opendrg_v1.json` | ICD-10-CN 诊断目录 | 11,417,099 bytes | `3edb02423b30fa408f983a02941979955a3c0a36950974d52d1ff7e99b3dba09` | 33,304 |
| `icd10_cn_standard_names.json` | 国家临床版诊断名称补充 | 5,990,261 bytes | `7aa0c2acab61596eb5e8b304ee891b06b94d788f87a17b97660ab1043806f0f9` | 37,897；向运行时净增 6,452 |
| `procedure_icd9cm3_knowledge_v8_with_opendrg.json` | ICD-9-CM-3 术式名称 | 4,644,580 bytes | `59d0accce8660da9d98e933b50b391cebb9c29357ee767148c878d834f42ac87` | 17,436；有效 16,561；唯一代码 14,353 |
| `surgery_to_drg_mapping.json` | 术式到 DRG 映射 | 12,692,746 bytes | `e9f5b3a1c7a23b6063f336930f3d59c7def1b9ef5fbbc947f30982a64fe1675b` | 23,165 |
| `icd9cm3_code_catalog.json` | 国家临床版手术名称补充 | 5,658,170 bytes | `4d0af72f8d5c3da5008741378ab97373f87f13775487cf5adcee6974cb4bca69` | 13,617；向运行时净增 5,229 |

清单版本为 `icoder.code-catalog-assets/v1`，目录发布标识为 `icoder-cn-runtime-2026-08-27.2`。清单明确记录来源为本轮获授权的 `E:\iCoDerA\data`，并明确不据此声称公开再分发权。

## 实现边界

- `backend/data/code_dicts/icd_data.py` 只从仓内 `assets` 加载，不再计算或访问相邻 `iCoDerA` checkout。
- 代码常量保存独立于清单的可信大小、摘要和计数，防止同时修改清单与数据绕过校验。
- 加载完成后公开 `CODE_CATALOG_STATUS`，当前为 39,756 个诊断代码、28,394 个术式代码且 `integrity_verified=true`；补充目录只填补原目录缺项，不覆盖原有名称和 DRG 数据。
- 删除极小 hardcoded fallback；目录不可验证时应用失败关闭。
- 后端 Dockerfile 的 `COPY --chown=icoder:icoder . .` 包含上述资产，`.dockerignore` 未排除该目录。
- 部署候选预检新增目录自包含、摘要、Docker 上下文和失败关闭联合门禁。

## 验证证据

- 新增目录资产测试、dictionary RAG、DeepSeek 编码适配器：32 passed。
- 目录资产、dictionary RAG、DeepSeek adapter、G001 coding runtime、Medical Coding A2A、公共投影、CDI 公开合同和临床校准门组合：115 passed、5 skipped。
- 部署静态预检：105/105 passed。
- 预检证据：`reports/deployment/code_catalog_assets_phase_20260827_v1/deployment_preflight.json`
- 预检文件 SHA-256：`c11ad28021236df145697d5c0f14d0cb5f565c6d0c4d0ab8bb74ec07e3a599f3`
- 受保护数据库保持 size 8,536,064、mtime `2026-08-22 17:16:22`、SHA-256 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。
- 未调用真实 LLM，未读取或保存新 API Key，未发现运行中的 Python/Uvicorn 工作进程。

后续 CCL 2026 本地数据就绪增量又验证：获授权 `train.xlsx` 的 1,800 条记录与仓内 fixture 按完整规范化 case digest 逐条、顺序完全一致；9,442 次诊断标签分配（960 个唯一代码）和 2,172 次手术标签分配（48 个唯一代码）对 `2026-08-27.2` 目录均为 0 未匹配。聚焦回归 63/63、最新静态预检 107/107。聚合报告位于 `reports/agent_hub/ccl2026_local_dataset_audit_20260827_v2/ccl2026_local_dataset_audit.json`，不含病例文本、病案标识或逐条标签。

## 仍开放的门

1. 在具备 Docker 的受控 CI/构建机实际 build、启动镜像，并验证容器内目录状态、SBOM、漏洞扫描和镜像签名。
2. 在任何对外分发或商业生产发布前，取得并归档目录数据的正式许可、权威版本说明和更新/撤回机制；当前用户授权只关闭本项目内部开发使用问题。
3. 由独立编码专家裁决 `S22.000` 与目录子码 `S22.000x003` 的 gold 层级，并扩展双语病例集。
4. 使用新临时 Key 运行修复后的 50 次真实临床校准；目录自包含不会自动提升临床准确率、双语一致性或 Corti 等价状态。
