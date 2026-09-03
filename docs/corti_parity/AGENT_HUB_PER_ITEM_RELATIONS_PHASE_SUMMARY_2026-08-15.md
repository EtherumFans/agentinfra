# Agent Hub 数组逐项关系阶段总结（2026-08-15）

## 阶段结论

本轮把 Agent Hub 输出门禁从“对象整体字段组合一致”推进到“数组中的每一个临床项目都必须满足声明关系”。当前 26 个 Hub 可见 Agent 仍全部是开发环境上线候选；其中 11 个 Agent 共声明 27 条跨字段关系、52 个 `must` 断言。离线对抗回放逐一破坏每个断言，52/52 被运行边界拒绝。

这证明的是确定性的工程合同、失败关闭和可审计性，不证明临床正确性、真实模型稳定性或生产批准。本轮没有使用真实 LLM 密钥、Corti credits、浏览器自动化、Torch、PyArrow、FAISS 或本机原生 ML。

## 已完成优化

- 关系 DSL 新增可选 `for_each`，仅允许指向契约声明的对象数组；`when`/`must` 路径相对于单个数组项。
- 新增 `in`、`not_in` 以及 `gt`、`gte`、`lt`、`lte`；定义门禁验证路径、类型、有限阈值、集合非空与唯一性。
- Run/A2A 返回的逐项错误只包含 `array[].field`、`fieldRelation`、稳定关系 ID 与抽象失败原因，不包含数组下标或患者值。
- 依据 Pack 明示规则增加逐项约束：Code Validation 的可赋码性；Diagnosis Extractor 的当前确诊与不可编码提及；Evidence Extractor 的 direct/置信度/复核提示；Procedure Extractor 的实施状态；以及 Principal Diagnosis、Clinical Guidelines、CDI 查询的逐项可追溯性。
- 修复 schema 生成器的可变对象别名污染：空数组模板中给 `evidence_strength` 或 `status` 添加枚举时，不再把枚举传播到 `code`、`evidence_text` 等兄弟字段。
- 修复测试隔离：无密钥流式回退测试同时清除 canonical credential，避免被其他测试模块的伪凭证污染并意外访问外网。

## 合同与 SDK

当前升版引用：CDI `/v4`、Clinical Guidelines `/v4`、Code Validation `/v5`、Diagnosis Extraction `/v4`、Coded Evidence `/v5`、Principal Diagnosis Review `/v5`、Procedure Coding `/v6`。旧 projector 别名保留。

不可变注册表由 66 增至 75 条；26 个当前引用全部匹配，新引用、静默变更、非法引用和重复引用均为 0。

SDK 当前版本：JavaScript `1.0.0-beta.12`、Python `1.0.0b11`、.NET `1.0.0-beta.12`。JavaScript、前端与 .NET 暴露 `for_each` 和新操作符；Python 保持原样无损透传。

## 验证证据

- 安全扩大后端回归：`443/443`；真实 Provider 专项和 Windows 原生 embedding 测试未纳入，避免真实网络与已知本机崩溃链。
- 全关系对抗回放：11 个 Agent、27 条关系、`52/52` 断言被拒绝。
- 运行矩阵：`26/26` 可执行、Provider 可解析、上线候选、递归 schema/关系有效、注册表匹配。
- 当前契约重放：`26/26`；缓存 Provider E2E 输出按当前契约重新评估：`26/26`。
- JavaScript SDK：`20/20`，构建与 `npm pack --dry-run` 成功。
- Python SDK：`28/28`，`1.0.0b11` wheel 构建成功。
- 前端：`114/114`，TypeScript/Vite 生产构建成功。
- OpenAPI `--check`：通过；静态部署预检：`45/45`。
- .NET：模型和反序列化 fixture 已更新；本机没有 `dotnet`，未声称执行，继续由 CI 门禁承担。

权威产物：

- [`field_relation_replay_20260815_item_relations_final`](../../reports/agent_hub/field_relation_replay_20260815_item_relations_final/)
- [`runtime_regate_20260815_item_relations_final`](../../reports/agent_hub/runtime_regate_20260815_item_relations_final/)
- [`item_relation_typed_replay_20260815_final`](../../reports/agent_hub/item_relation_typed_replay_20260815_final/)
- [`item_relation_cached_e2e_revalidation_20260815_final`](../../reports/agent_hub/item_relation_cached_e2e_revalidation_20260815_final/)
- [`development_preflight_20260815_item_relations_final`](../../reports/agent_hub/development_preflight_20260815_item_relations_final/)

## 与 Corti 的剩余能力差距

| 维度 | 本轮关闭 | 仍未证明 |
|---|---|---|
| 数组逐项一致性 | 逐诊断、逐手术、逐编码、逐指南标准、逐 CDI 查询和 evidence 分层可发现、可审计、失败关闭 | 跨数组集合互斥/并集、恰好一个主诊断、根字段与候选集合一致性 |
| 证据锚定 | 每项证据字段、状态和置信度组合受合同约束 | quote/span 与本次输入原文、文档版本和字符边界的真实绑定 |
| 临床质量 | 错误组合不能作为成功输出发布 | 与 Corti 同病例双盲、独立专家金标准、准确率、可行动性与诱导风险 |
| 中国场景 | ICD-10-CN、ICD-9-CM-3、CDI、医保/DRG/DIP 语义进入逐项门禁 | 地方规则合法授权与版本、医院接口、结算联调、方言/专科语料和临床验收 |
| 生产工程 | 26 个 Agent 的开发候选合同与离线 E2E 通过 | 真实临时 LLM 凭证稳定性/成本、.NET 实跑、Linux ML worker、云运维、法务和认证 |

## 下一阶段

下一优先级是“集合级不变量与输入证据绑定”：主诊断候选恰好一个、根推荐码必须存在于候选集合、可编码与不可编码集合互斥，以及 PHI-safe 的 quote/span 对当前输入边界校验。真实 Provider 与 Corti 同病例对比仍需新建、短期、可注销凭证和明确预算；完成后必须立即关闭进程并注销凭证。

总目标继续进行，`production_ready` 保持 `false`，外部医院、云、法务、认证和独立 reviewer 门禁不作虚假关闭。
