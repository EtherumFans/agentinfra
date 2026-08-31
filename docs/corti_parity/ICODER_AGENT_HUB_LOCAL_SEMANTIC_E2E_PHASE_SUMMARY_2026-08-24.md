# iCoDer Agent Hub 本地语义 HTTP E2E 阶段总结（2026-08-24）

> **后续状态更新（2026-08-24）**：Procedure Extractor 已加入受治理本地基线，当前数量为
> 8 个本地基线、18 个外部模型强依赖，最新 happy/adversarial/reference 为 8/8、stability
> 为 48/48。请以
> [`ICODER_GOVERNED_PROCEDURE_EXTRACTOR_PHASE_SUMMARY_2026-08-24.md`](ICODER_GOVERNED_PROCEDURE_EXTRACTOR_PHASE_SUMMARY_2026-08-24.md)
> 和权威差距矩阵为当前口径；本文保留首次 7-Agent 门禁形成时的历史证据。

## 阶段结论

iCoDer Agent Hub 的 26 个用户可见 Pack 继续全部满足 executable、Provider-resolvable、
非 MVP、结构性 launch-candidate-ready；21 个经 Provider Registry 路由，5 个经专用适配器，
0 个落入 legacy default。运行依赖的权威分类为：19 个外部 LLM 必需、1 个可选 LLM 增强、
6 个纯本地，因此共有 7 个具备无需外部模型的本地基线。

本阶段为这 7 个本地 Agent 建立并实跑了独立证据门禁：

- `code-validation-agent`
- `compliance-guardrail-agent`
- `evidence-extractor`
- `evidence-ranker`
- `icd10-navigator`
- `note-completeness-agent`
- `surgical-registry`

该门禁只接受新鲜 loopback HTTP Run、Pack/schema 快照、响应与 Trace 文件哈希、服务器结果
签名、租户 Trace 签名、真实 Provider completion 遥测，以及 happy、adversarial、reference、
stability 四类全部通过。它不能标记任何外部模型 Agent，不能替代严格的 26-Agent live-provider
门禁，也不能证明临床准确率、Corti 等价或生产审批。

最终矩阵为：本地受限语义证据 **7/7**；完整 26-Agent live-provider 证据仍为 **0/26**；
19 个外部模型 Agent 仍待真实模型验证；生产就绪仍为 **0/26**。

## E2E 暴露并关闭的真实缺口

第一次运行在 `icd10-navigator` 的“只有一个歧义术语且未提供目录版本”对抗场景失败。
原因不是目录不可用，而是中文查询解析把“未提供病因、急慢性、分期”等否定说明误拆成多个
检索词；同时旧断言错误地要求系统实际使用的固定目录版本也显示为缺失。修复后只提取引号内
的“肾功能异常”，输出实际 `cn.icd10cn.catalog@observed-local-2026-05-19` 及
`source_unverified` / `external_review_required` 治理状态，并继续强制人工复核。

第二次运行在 `note-completeness-agent` 的 Pack reference 回放失败。Pack 已声明能识别诊断
`L1` 与治疗/手术 `T12` 的显式节段冲突和章节不完整，但原本地 Provider 只检查 7+1 标题
存在性，把缺少手术记录的病例判为 `PASS`。本阶段增加有边界的确定性规则：

- 手术病例缺少独立手术记录时列入 `missing_sections`；
- 手术场景中未区分入院/出院诊断，以及缺少术前或术中信息时列入
  `incomplete_sections`；
- 只在诊断与治疗/手术两个章节均出现显式 `C/T/L/S + 数字` 字面量时比较脊柱节段；
  不推断诊断、手术适用性或其他临床一致性；
- 任一明确缺口或冲突都不得返回 `PASS`。

Pack 示例、参考断言和完整性哈希同步到运行真值：该病例现在为 `WARNING`、完整度 0.875、
缺少手术记录、两项不完整章节和一项 `L1/T12` 显式冲突。普通非手术完整记录不会被这一
规则误判。

## 真实 HTTP 证据与回归

运行器使用临时迁移 SQLite、随机 loopback 端口、真实 Bearer 租户、真实 Run/Trace API，
并删除 `ICODER_CREDENTIAL_LLM`、`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`。原生 MedCodER、
真实 STT、Models Canary 和外部 LLM 均关闭；全部输入均为 Pack 自带合成用例。

| 验证面 | 结果 |
|---|---:|
| happy HTTP Run | 7 / 7 passed |
| adversarial HTTP Run | 7 / 7 passed |
| Pack-owned reference replay | 7 / 7 passed |
| stability（3 轮 × happy/adversarial × 7） | 42 / 42 passed，全部 fresh HTTP |
| 本地语义证据包 | 7 / 7 valid |
| 完整 26-Agent live-provider 门禁 | 0 / 26，未被窄范围证据抬高 |
| 外部模型 Agent 待验证 | 19 |
| 组合回归 | 264 passed，0 failed |
| 部署预检 | 90 / 90 passed |

机器证据：[`reports/agent_hub/local_semantic_e2e_phase_20260824`](../../reports/agent_hub/local_semantic_e2e_phase_20260824/)；
阶段证据：[`phase_evidence.json`](../../reports/agent_hub/local_semantic_e2e_phase_20260824/phase_evidence.json)。

## Corti 当前公开对照与仍有差距

Corti 当前公开 [Agent Library](https://corti.ai/agents) 列出 20 个 ready-to-use Agent，包含
Medical Coding、Note Completeness、Surgical Registry、Code Validation、ICD-10 Index
Navigator、Compliance Guardrail 等，并宣称这些 Agent 面向受监管医疗环境、具备 guardrails、
audit trails 和 predictable execution。该页面还把 Agent 定义为端到端复杂任务执行，把
Expert 定义为医疗编码、药物相互作用、文档生成和检索等专门能力，并支持多 Agent composition。
这些是 Corti 的官方公开产品声明，不等于本项目对其临床质量或生产实现进行了独立验证。

Corti [Agentic Framework](https://docs.corti.ai/agentic/overview) 当前公开的基线还包括 LLM
推理与规划、受信任 Connector 检索、受控工具执行、人工批准与恢复、类型化输入输出、
可回放 Trace、结构化日志、持久 Context/Memory，以及 registry/MCP/agent/A2A/schema 五类
Connector。iCoDer 已有对应工程合同和审计骨架，但本阶段只证明 7 个确定性/受治理本地基线；
19 个 LLM Agent 的真实规划、工具语义、质量、费用和稳定性仍没有新鲜证据。

具体能力仍不等价：

- iCoDer Code Validation 的本地基线只验证未获权威许可的 ICD-10-CN/ICD-9-CM-3 目录成员
  与可分配性；Corti 公开 Agent 覆盖 ICD-10-CM、ICD-10-PCS、CPT 等，并声明 Verify、
  Guidelines、instructional notes、sequencing、combination code 等更完整检查。
- iCoDer Note Completeness 只增加章节结构和显式脊柱节段字面量规则，没有证明 Corti 所称
  real-time note completeness、跨全文临床一致性或医院工作流质量。
- Evidence Extractor/Ranker 是 iCoDer 的治理拆分能力，Corti Library 没有同名一一对应 Agent；
  邻近 Medical Coding 的 supporting evidence、模型推理和替代编码仍未复刻。
- 现有目录 authority/license 未获独立验证，不能用于医保结算、自动写回或替代编码员。
- 尚未执行独立临床 gold set、真实医院集成、生产云/KMS/Secret Manager、多副本 PostgreSQL、
  容量/SLA、法务合规与认证验收。

## 安全与环境复核

- 受保护数据库未迁移：8,536,064 bytes，SHA-256
  `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`；其数据库版本仍为
  `041`，源码 Alembic 单 head 为 `056`。
- E2E 临时数据库已迁移后删除；残留 Uvicorn/Python/ffmpeg 进程 0，阶段临时目录 0。
- 当前进程中的三类 LLM key 环境变量均不存在；本阶段没有调用真实 LLM。
- Docker CLI 不可用，因此没有构建、启动或扫描 Linux 镜像，也没有 SBOM/CVE/签名证据。
- 此阶段没有真实患者数据、独立临床 gold、Corti 托管租户互操作或医院验收。
