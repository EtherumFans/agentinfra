# Corti 官方公开文档增量复核（2026-08-21）

本复核使用 Corti 当日公开文档，不使用登录态、患者数据或浏览器自动化。它验证公开产品与协议表面，不能证明 Corti 私有实现、准确率、SLA，也不能替代同病例双盲对照。

## 官方来源

- [平台总览](https://docs.corti.ai/get_started/welcome)
- [Agentic Framework](https://docs.corti.ai/agentic/overview)
- [Connectors](https://docs.corti.ai/agentic/connectors)
- [A2A protocol](https://docs.corti.ai/agentic/a2a-protocol)
- [Context and memory](https://docs.corti.ai/agentic/context-memory)
- [OpenInference trace export](https://docs.corti.ai/agentic/guides/export-traces)
- [Task/message feedback](https://docs.corti.ai/agentic/guides/submit-feedback)
- [Medical Coding](https://docs.corti.ai/coding/overview) 与 [Encounter Coding](https://docs.corti.ai/get_started/encounter-coding)
- [Speech to Text](https://docs.corti.ai/stt/overview)、[Text Generation](https://docs.corti.ai/textgen/overview)、[Embedded Assistant](https://docs.corti.ai/assistant/introduction)
- [Corti Models](https://docs.corti.ai/models/welcome) 与 [SDKs](https://docs.corti.ai/sdk/overview)

## 增量结论

| 能力面 | Corti 当前公开能力 | iCoDer 当前权威证据 | 结论 |
|---|---|---|---|
| Agentic v2 Connector 模型 | `registry`、`mcp`、`agent`、`a2a`、`schema` 五种统一 connector；独立增删查与认证模型 | OpenAPI 现有 7 个 A2A 路径和 3 个 Connector 路径；`044` 持久资源、五类类型化安全 CRUD、secret reference 和本地失败关闭执行器已完成，Agent Planner/生产 adapter/三 SDK 未完成 | **资源与本地执行层缺口已关闭、产品接线仍为 P0**；历史 Agent 目录映射仍不能替代 v2 connector 协议 |
| A2A | Corti 仅支持 A2A v1.0；同时支持 JSON-RPC 与 HTTP+JSON，包含 Send/Stream/Get/List/Cancel/Subscribe 和 agent card | 后端/OpenAPI 已实现 v1 双 binding 的 Send/Stream/Get/List/Cancel、Agent Card、ProtoJSON adapter 和签名分页；v0.3 保持兼容 | **部分完成**；缺 Subscribe/持久恢复、well-known card 和三 SDK |
| Context/Task | context 为一级资源；可 get/delete、列 context tasks、按 task 获取，并支持 context trace export | `045` 已完成持久 Task/List/Get/Subscribe；`046` 已增加现行 Context `/trace` | 开发合同覆盖；生产多副本仍缺 |
| 可观测性 | Context 可导出分页 OpenInference traces，含 LLM、connector、tool spans 和 token 属性 | 已实现签名分页、确定性 root/child span 与最小必要属性；中国医疗默认不导出 Corti 示例中的 `input.value`，且只输出真实已捕获 token/connector 字段 | **开发互操作缺口已关闭；全 Provider 属性覆盖仍需扩大** |
| 反馈闭环 | Task/message feedback 支持提交、列表、删除，可用于点赞/点踩、case review 与自动评估 | 已实现统一 Task feedback 与 `target.messageId`、调用方隔离、binary/label 校验、DLP/加密、幂等、审计和 retention；自动评估/训练授权未实现 | **CRUD 产品闭环已关闭；自动评估仍为 P1** |
| Agent usage | Corti 可按 Agent、时间范围、粒度查看 usage bucket | iCoDer 有 `/api/usage/by-agent` 和逐 Run 成本归集 | 部分对齐；仍需按 v2 维度与游标合同核验 |
| Registry | 当前公开 registry 为 Memory、Clinical Trials、DrugBank、Medical Calculator、Medical Coding、POSOS、PubMed、Interviewing、Web Search | iCoDer 的 26 个可见医疗 Agent 是本地运行 Pack；不等价于上述第三方/权威数据 connector 与许可 | 旧“20/20 目录映射”只保留历史意义 |
| Medical Coding 请求/输出 | text/documentId、include/exclude/expand、codes/candidates、evidence、alternatives | iCoDer v2 schema 与确定性边界已覆盖这些合同 | 工程合同对齐 |
| Medical Coding 范围 | Corti 公开多国诊断/操作体系及 SNOMED CT、LOINC、ICD-11；部分功能分 stable/beta/alpha | iCoDer Corti-compatible 端点为历史 15-system enum；另有 ICD-10-CN、ICD-9-CM-3 与 DRG/DIP 风险治理 | 国际广度落后；中国适配是差异化优势，但权威数据与真实检索仍未闭环 |
| STT 与 Web Components | Transcribe/Streams/Transcripts，以及 Dictation/Ambient 两个正式 Web Component | iCoDer 有录音/转写 REST 与流式基础设施；旧 dictation component 已废弃，正式 `@icoder/embedded` 只导出 Assistant | **P1 前端集成缺口**；语言、术语准确率和音频可靠性仍无对等证据 |
| Text Generation | FactsR、Guided Documents、typed schema、多源输入、Templates/Sections | iCoDer 已有 Facts、Classic/Guided Documents、Templates/Sections 和三路径生成合同 | 工程面接近；临床质量与生产吞吐未证明 |
| Embedded Assistant | 会话、录音、interaction、文档/转写、实时事件、Web Component/PostMessage/Window、多区域 | `@icoder/embedded` 有 Corti-compatible method API，但未覆盖 Corti 当前全部事件、可靠性和区域托管面；本机浏览器重型 E2E 有原生崩溃风险 | 部分覆盖 |
| Models | Corti 托管 EU sovereign OpenAI-compatible 文本/推理/embedding 模型 | iCoDer 是外部/本地 Provider 路由与受控 Canary，没有自营托管模型池、embedding 服务、容量或 SLA | 外部平台级缺口 |
| SDK | Corti 正式 JS/.NET；Agent SDK 的 TypeScript/Python 多 Agent composition 处于 private preview | iCoDer 有 JS/Python/.NET 资源 SDK，但没有 v2 connector graph/fan-out/state-graph Agent SDK；本机 .NET 工件未编译 | 通用资源面较全，Agent SDK 代差明显 |

## 对原结论的修正

1. `20/20 mapped` 仅证明 2026-08-15 控制台/旧目录快照的名称与本地 Agent Pack 映射，不再代表当前 Corti Agentic v2 等价。
2. v2 connector、A2A v1.0 双绑定、持久 task/context lifecycle、OpenInference trace export 与 feedback CRUD 已完成开发切片；下一优先级是专用 Agent 全入口 graph、usage/自动评估授权边界和生产多副本验证，而不是继续堆预置 Agent 名称。
3. Coding 的 include/exclude、documentId、evidence/candidates 已覆盖，不应重复建设；应优先修复隔离 MedCodER Worker 接线并补权威中国编码检索证据。
4. Corti 文档自身也标注若干 private-preview/未持久化/501 行为；对标时应复刻稳定公开合同，不把尚未实现的文档声明冒充生产能力。

## 下一开发阶段验收顺序

详细实现基线见 [`ICODER_AGENTIC_V2_MIGRATION_DESIGN_2026-08-21.md`](ICODER_AGENTIC_V2_MIGRATION_DESIGN_2026-08-21.md)。

1. A2A v0.3→v1.0 设计与首个双协议不回归切片已完成；继续补 Subscribe/持久事件和三 SDK。
2. 新增五类 connector 的类型、租户隔离、认证、CRUD 与负向安全矩阵。
3. 补 List/Get/Cancel/Subscribe task、context task 集合和流恢复合同。
4. 将现有 RunTrace 投影为脱敏 OpenInference 导出；禁止泄露原始患者输入和 connector secret。
5. 扩展 feedback 的自动评估、显式训练授权和聚合治理；不得把临床纠错自动转为训练许可。
6. 修复 Compose/CI 的隔离检索 Worker 接线后，再扩展 26-Agent 真实模型质量矩阵。
