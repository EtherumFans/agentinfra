# iCoDer 受治理外科质控登记 Agent 阶段总结（2026-08-23）

> 声明：本阶段证明的是开发环境中的保守提取、运行、审计和安全边界，不是医院登记口径认证、临床有效性、生产就绪或 Corti 语义质量对等。

## 阶段结论

`surgical-registry` 已从依赖外部 LLM 的 PureLLM 路径收敛为本地、确定性、零模型成本的受治理 Provider。它只复制已脱敏原文中明确出现且规则边界足够窄的手术、麻醉、术中所见、并发症、指征、合并症和转归字段；每个非空字段都携带可在输入中逐字找到的 evidence quote，未知字段保持为空并进入 `missing_fields`。所有结果强制 `manual_review_required=true`，且生产写回继续被 Pack 权限阻断。

本阶段同时定位并修复了历史真实运行中的根因：中文姓名规则曾把“全麻下”误判为“全姓 + 两字姓名”，在 Agent 运行前破坏麻醉事实。当前脱敏器只在明确手术语境中保护麻醉短语；“患者全麻”这类可能的人名仍会被脱敏，避免为语义修复扩大 PHI 泄漏面。

这关闭了 2026-08-15 真实 HTTP E2E 参考回放中 `surgical-registry` 漏提“全麻”和“无胆管损伤”的已知缺陷。当前运行时对当时另外三项失败也已有可重复证据：Diagnosis Extractor 规范化历史 `completed` 为合同状态 `PASS`；DRG Analyzer 由服务端注入不可被模型省略或反转的非结算权威常量；Evidence Extractor 已由本地受治理精确提及 Provider 取代旧 PureLLM 路径。

上述四项是“历史已知缺陷的当前开发回归闭合”，不是新鲜真实 LLM E2E。当前矩阵仍诚实保持 `semantic_live_e2e_verified=0/26`。

## 实现边界

- Provider：`icoder.governed-surgical-registry.v1`，`backend_type=rule_engine`，确定性执行，不需要网络、LLM 或工具。
- 提取策略：只接受显式标签或窄范围原文模式，不根据检查、用药、手术名称或上下文推断未记录事实。
- 证据策略：`evidence_spans` 中每个值都是输入原文的逐字子串；不产生伪造 offset、来源或临床结论。
- 缺失策略：未明确记录的字段写空字符串，并且只进入 `missing_fields`；不得把缺失事实转换为阴性事实。
- 并发症策略：只捕获带常见并发症名词的明确阴性表达，诸如“无胆管损伤”；不会把任意“无……”句子提升为并发症判断。
- 治理策略：所有结果必须人工审核，生产写回阻断，Pack 使用当前内容的 canonical SHA-256 完整性证明。
- Trace：仅记录 Provider ID、确定性标志、耗时、零成本、LLM 调用数和提取字段计数，不记录病历或 evidence quote。

## 验证证据

| 门禁 | 结果 | 说明 |
|---|---:|---|
| Provider/PHI/Registry/Pack/Matrix/Reference/Offline 组合回归 | 229/229 | 覆盖 Provider、姓名脱敏反向测试、注册、Pack 装载、运行矩阵、合同注册表、历史四项缺陷和 26-Agent 离线矩阵 |
| 26-Agent 离线 E2E | 78/78 | 26 个原始 Agent + 26 个项目克隆 + 26 个对抗输入；真实 FastAPI 应用内执行、Run/Trace/attestation 校验 |
| 历史四项语义缺陷回归 | 4/4 | Diagnosis/DRG 使用不可变历史响应重放当前规范化；Evidence/Surgical 使用当前本地 Provider；不计为 live LLM |
| 参考质量测试 | 8/8 | 26 个参考用例覆盖、mutation fail-closed、历史响应/current provider 回归 |
| 运行矩阵 | 26/26 | launch candidate；外部 LLM 必需 19，本地确定性 6，本地基线总计 7 |
| 静态部署预检 | 81/81 | `static_without_docker_cli`，失败项 0 |
| 输出合同兼容 | 通过 | 当前 26 个可见合同均匹配 append-only 注册表；无新引用、漂移或重复 |
| OpenAPI 漂移 | 通过 | 当前应用与 `docs/openapi/openapi.json` 一致 |
| Pack 完整性 | 通过 | Surgical Registry declared/actual canonical SHA-256 一致 |

机器证据：

- `reports/agent_hub/governed_surgical_registry_phase_20260823/phase_evidence.json`
- `reports/agent_hub/governed_surgical_registry_phase_20260823/runtime_matrix/agent_hub_runtime_matrix.json`
- `reports/agent_hub/governed_surgical_registry_phase_20260823/preflight/deployment_preflight.json`

## 对 Corti 与中国场景的差距

| 能力 | 当前 iCoDer 证据 | 仍需关闭 |
|---|---|---|
| Surgical Registry 结构化提取 | 本地确定性、逐字证据、缺失字段、人工审核、Run/Trace/项目克隆均已验证 | 尚未覆盖 Corti 可能使用的完整术式/专科登记字段、跨文档合并和复杂语义消歧 |
| 中国医院登记适配 | 支持中文手术、麻醉和阴性并发症显式表达；不依赖境外模型 | 缺国家/省级/医院专科质控数据字典、必填规则、字段映射版本和权威 reviewer 签署 |
| 语义质量 | 已关闭一个历史真实缺陷，合成参考断言通过 | 没有当前真实模型 26-Agent 全量 E2E；本地规则也没有真实医院盲评的召回率/精确率证据 |
| Corti 式 Agent 定制 | 项目 Clone、A2A、Trace、附加策略和 Connector Graph 已有 | 本地规则 Provider 当前不允许租户通过 prompt 改写安全边界；自定义登记 schema 生命周期仍不足 |
| 生产运行 | 零外部依赖、81/81 静态预检 | 0/26 production verified；缺 PostgreSQL 多 worker、容器/云、容量、SLA、灾备和真实异构对端 |

## 当前开放门禁

- 19 个可见 Agent 仍依赖外部 LLM 才能产生语义结果；无密钥离线时只能失败关闭。
- `semantic_live_e2e_verified=0/26`，不得声称已达到 Corti 输出质量。
- `production_ready_verified=0/26`，不得将 launch candidate 等同于生产上线。
- E 盘当前仅约 73 MB 可用；最近一次全量后端运行得到 5224 passed、0 failed，但在最后 SQLite teardown 因 `database or disk is full` 留下 1 个环境错误。相同测试单独复验通过；释放至少 1–2 GB 后仍须重跑完整套件。
- 真实医院数据、编码员/临床/质控专家盲评、本地登记字典确认、医保/DRG/DIP 权威规则、法务授权、个保/数安/等保、独立渗透测试和医院验收只能保留为外部门禁。
