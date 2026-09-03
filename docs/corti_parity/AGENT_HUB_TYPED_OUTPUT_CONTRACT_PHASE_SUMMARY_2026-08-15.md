# Agent Hub 机器可读输出契约阶段总结（2026-08-15）

## 阶段结论

本轮关闭了 26 个可见 Agent 共用的高风险工程缺口：此前统一运行时只检查输出字段是否存在，Provider 即使把字符串返回成数组、把对象返回成文本，也可能被标记为有效。现在 26/26 Pack 均声明顶层 `field_types`，统一 Agent Run、21 个 Provider A2A 路由、Hub 卡片、模型提示词、发布门禁、运行矩阵和部署预检使用同一类型边界。

该结论是“开发环境工程上线候选”，不是临床生产批准，也不是 Corti 私有模型、托管基础设施或服务 SLA 的完整复刻。

## 已完成优化

1. 新增 PHI-safe 契约校验器，支持 `string/boolean/integer/number/object/array`；明确拒绝 Python 中 `bool` 被当作整数或数值。
2. 公共响应新增 `invalid_field_types`。错误项只记录字段、期望类型和实际类型，不记录患者值；契约违规时公共响应会抑制模型 markdown、领域字段、issue、tool payload 与 evidence，避免部分发布畸形内容。
3. 缺字段或错类型均触发 `output_contract_violation`、公共错误和强制人工复核；A2A 返回 `OUTPUT_CONTRACT_VIOLATION`/503。
4. Pure LLM 与 LLM-with-tools 共用的 Pack 指令现在向模型声明精确 JSON 类型；运行时仍以确定性验证为准，不信任模型自报。
5. Agent Hub 卡片公开 `field_types`；开发发布门禁要求每个必填字段都有受支持类型，且至少一个契约完整示例的类型全部正确。
6. 26 个可见 Pack 已持久化类型声明；维护脚本支持 dry-run、冲突拒绝、幂等写入和已声明完整性摘要刷新。
7. 运行矩阵新增完整类型契约与类型有效示例计数，并把缺失项纳入 `--assert-visible-ready`。
8. 部署预检新增全量 Pack 类型声明、示例一致性和运行时失败关闭检查。

## 回放发现并修复的问题

首次把 2026-08-13 已捕获的 26 个真实 Provider 快乐路径结果重放到新边界时，结果为 25/26。`icd10-navigator` 的历史 Provider 输出把 `hierarchy_notes` 和 `inclusion_exclusion_notes` 返回为数组，而 Pack 示例曾把二者写成字符串。

这不是缺字段问题，旧运行时会将其误判为有效。结合该 Agent 的列表型导航语义和既有真实输出，本轮将两字段统一为数组，并同步 Pack 示例；再次重放为 26/26。该修复证明类型门禁能够发现此前字段存在性检查看不到的契约漂移。

## 验证结果

- 类型契约专项、对抗、Pack、Hub、Provider/A2A 与离线 E2E 评价：`103 passed`。
- Agent Run、Agent Hub、A2A 端点及专用 Agent 扩大回归：`105 passed`。
- 前端全量：`113 passed`；生产构建通过。
- 运行矩阵：32 个磁盘 Pack，26 个可见 Agent；26/26 executable、Provider 可解析、开发候选、类型声明完整、示例类型有效；21 个 Provider Registry 路由、5 个专用路由、0 个 legacy default。
- 已捕获 Provider 输出的当前运行边界重放：`26/26`。
- OpenAPI `--check`：通过。
- 静态部署预检：`45/45`，失败项 0。

证据：

- `reports/agent_hub/runtime_regate_20260815_typed_contracts/`
- `reports/agent_hub/typed_contract_replay_20260815/`
- `reports/deployment/development_preflight_20260815_typed_contracts/`

本轮未使用真实 LLM 凭证，未启动浏览器自动化，未加载 Torch、PyArrow、FAISS、BGE 或 sentence-transformers，也未启动 API 服务。

## 与 Corti 的阶段性差距

| 维度 | 本轮后的 iCoDer | 与 Corti 的剩余差距 |
|---|---|---|
| Agent 输出合同 | 26/26 可见 Agent 顶层字段和类型可发现、可失败关闭、可审计 | Corti 私有输出 schema、版本兼容策略和线上错误率不可从公开控制台完整验证 |
| Agent 执行链 | 21 个 Provider 路由 + 5 个专用路由均有开发证据 | 真实云 Provider、区域限流、计费、长周期稳定性和 Corti 托管 SLA 未证明 |
| 临床质量 | 保留人工复核、证据约束、禁止生产写回和中国编码边界 | 类型正确不等于临床正确；统一病例的诊断/编码/CDI 质量仍需双边真实模型与独立专家评审 |
| 中国适配 | ICD-10-CN、ICD-9-CM-3、中文病历、DRG/DIP/医保字段和安全策略已进入工程合同 | 地方目录、医保规则授权/版本、真实医院 HIS/EMR 与结算联调仍是外部门禁 |
| 语音与 Ambient | 不受本轮倒退 | 与 Corti 的实时医疗语音、多人/方言/噪声/长音频和现场 SLA 仍有明显差距 |

## 仍未关闭的总目标门禁

1. 201 例及扩展临床金标准的真实模型准确率、F1、证据一致性和错误分层；Windows 主进程仍禁止加载已知会触发访问冲突的原生 ML 栈。
2. 使用新建、短期、可注销的 LLM 凭证重新执行 26 个 Agent 快乐/对抗多轮稳定性、P50/P95 和成本报告；不得复用已暴露密钥。
3. Corti 与 iCoDer 使用同一批去标识病例的双边 Medical Coding、CDI、FactsR、Text Generation 和 STT 比较。
4. Linux/Docker 中真实 BGE/FAISS worker 构建、预热、质量、容量、故障注入、SBOM、漏洞扫描和镜像签名。
5. 医院互操作、地方规则、独立临床复核、等保/隐私/渗透、云 KMS/灾备/监控和运营审批。

因此总目标仍在继续：本轮关闭的是所有可见 Agent 的公共输出类型可靠性，不应被解释为 Corti 能力已经全部复刻。
