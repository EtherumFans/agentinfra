# Corti Console Agent 只读核对（2026-08-26）

## 结论

在用户已登录的 Corti Console 中，以只读方式核对了当前 AI Studio / Agents 产品面。控制台显示 **20 个 Pre-built Agents**；iCoDer 当前 Agent Hub 对这 20 个名称均有对应可见 Pack，并另外提供 6 个自有 Pack。因此，当前可以确认的是“**Corti 可见预置 Agent 目录映射 20/20**”，不能据此确认行为、临床质量、外部工具、数据源、时延、成本或生产 SLA 等价。

本次没有创建 Agent、运行 Agent、录音、上传病例、调用 Corti API、创建 API Client、改变项目设置或消耗测试额度。未采集患者数据、临床正文、账号身份信息或项目标识。

## 当前控制台可见产品面

项目导航中可见以下能力入口：Home；Developer 下的 Quickstart 与 Corti Models；AI Studio Overview 与 Agents；Speech-to-Text 下的 Dictation、Ambient、Pre-recorded；Text Generation；Embedded Assistant；Fact Extraction；Medical Coding；以及 API Clients、Team、Billing、Usage、Customers、Templates、Settings。

Home 页面可见 Transcribe、Document、Chat、Code 四类入口，以及 SDK、Postman 和 AI coding tools 的开发接入引导。以上只证明当前控制台的信息架构和入口存在，不证明相关后端能力已通过本项目的互操作测试。

## 20 个 Pre-built Agents

1. ICD-10 Index Navigator Agent
2. Rule Explainer Agent
3. Compliance Guardrail Agent
4. Code Validation Agent
5. Procedure Entity Extractor Agent
6. Diagnostic Entity Extractor Agent
7. Surgical Registry Intelligence Agent
8. ICU Admission Summary Agent
9. Triage and Initial Assessment Agent
10. Note Completeness Agent
11. Medication Reconciliation Agent
12. Denial Appeals Agent
13. Patient Discharge Education Agent
14. Nursing Shift Handoff Agent
15. Prior Authorization Agent
16. Referral Generator Agent
17. Clinical Education Agent
18. Medical Coding Agent
19. Clinical Guidelines Agent
20. Clinical Documentation Improvement (CDI) Agent

## CDI 模板页只读观察

从 Pre-built Agents 列表进入 CDI Agent 后，控制台打开的是带 CDI preset 的 Agent 创建/预览页。可见能力包括：从模板开始、Agent 定制入口、对话试用区、添加上下文、能力询问和建议提示。没有进入提交创建或运行步骤。

这说明 Corti 的当前用户路径把预置 Agent 作为可定制模板暴露，而不只是静态能力卡。iCoDer 已有 Hub→项目 Clone→统一 Runtime/Run/A2A/Trace 的开发闭环，但仍需在相同用户任务、相同输入和独立评分协议下进行 head-to-head，才能证明其定制语义、工具调用、回答质量和失败行为与 Corti 等价。

## 与 iCoDer 的当前差距口径

| 维度 | 当前可确认 | 仍不能确认 |
| --- | --- | --- |
| 目录覆盖 | iCoDer 对 Corti 当前 20 个可见预置 Agent 名称映射 20/20，并有 6 个自有 Pack | 名称或卡片覆盖不等于行为复刻 |
| 模板与定制 | Corti CDI 页面可见模板、定制、上下文和对话试用入口；iCoDer 已有项目 Clone 与运行链 | 相同定制输入下的语义、权限、工具和状态行为等价 |
| 真实模型工程 | iCoDer 最新源级真实 Provider 回归 happy/adversarial/reference 为 26/26，stability 为 156/156 | 该回归使用自有合成用例，不是 Corti 同病例盲测或临床金标准 |
| 临床能力 | iCoDer 各 Pack 已固定安全边界、证据约束和人工复核 | Corti 卡片所宣称的广义临床推理、最终编码/分诊、权威知识与工作流集成尚未被 iCoDer 证明 |
| 中国场景 | iCoDer 已有 ICD-10-CN / ICD-9-CM-3 受治理目录、中文合同与本地化字段 | 目录来源/许可、医院规则、真实中文病历与语音质量、医保/DRG/DIP 权威性和医院验收仍开放 |
| 性能与成本 | iCoDer 已测得开发环境的真实 Provider P50/P95 和配置价格估算 | 未获得 Corti 相同任务的可比时延、成本或 SLA，不能宣称性能/成本等价 |
| 生产上线 | iCoDer 有隔离回归、Trace、签名、失败关闭和部署预检证据 | 临床校准、医院试点、生产容量、合规/法务、Provider 账单对账和生产审批仍是外部门禁 |

## 关键能力差距

- Triage：iCoDer 当前是受治理问卷规则候选，不进行对话字段推断、临床计算或最终 acuity 分配；这与 Corti 卡片呈现的广义分诊能力仍有实质差距。
- Clinical Guidelines / Education：iCoDer 只使用调用方明确提供且批准的来源，不执行开放 Web、PubMed、药物库或医学计算器检索，也不验证来源的真实性与最新性。
- Medical Coding / CDI：iCoDer 已具有真实 Provider、证据、Trace、安全门和成本/时延观测，但独立临床金标准、完整规则链、同病例 Corti 盲评及医院编码员验收仍未完成。
- Surgical Registry / Revenue Cycle：iCoDer 可生成受治理的 review-only 结果，但真实登记库、Claims、payer 工作流、提交/写回和结果分析集成尚未完成。
- Speech-to-Text：iCoDer 已覆盖多种媒体合同、恢复和合成音频 E2E，但真实中国医疗音频、diarization、词级时间戳、长音频与生产容量仍未与 Corti head-to-head。

## 审计限制

本次是已登录控制台的界面级只读观察，不是 Corti API 测试，也没有用同病例执行 Corti Agent。为避免此前浏览器/桌面进程出现内存异常，页面在第二次语义读取超时后停止继续遍历。因此该证据只用于更新产品面与 Agent 目录，不用于推断 Corti 私有实现、质量、成本、时延或生产 SLA。

