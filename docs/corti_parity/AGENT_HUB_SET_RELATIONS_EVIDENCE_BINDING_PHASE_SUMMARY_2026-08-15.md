# Agent Hub 集合关系与证据绑定阶段总结（2026-08-15）

## 阶段结论

本轮关闭了上一阶段明确列出的两个开发环境差距：集合级不变量，以及 evidence quote/span 对运行输入的真实绑定。

当前 26 个 Hub 可见 Agent 仍全部为可执行、Provider 可解析、可审计、可测试的开发上线候选。11 个 Agent 共声明 34 条关系、59 个必须满足断言；4 个高风险 Agent 声明 9 条 evidence binding。集合关系对抗回放 59/59、证据错引文/越界对抗回放 18/18 均被失败关闭。

这仍不是临床生产批准。本轮未使用真实 LLM、Corti credits、浏览器自动化、Torch、PyArrow、FAISS 或本机原生 ML。

## 已完成能力

### 集合级关系

- `count_where_equals`：Principal Diagnosis 的 `candidates[]` 必须恰好一个 `recommended=true`。
- `contains_field_equals_path`：根对象 `recommended.code` 必须等于被标记推荐的候选编码。
- `disjoint_fields`：
  - 可编码诊断与不可编码提及的证据不能同时出现；
  - 可计费手术与非计费手术提及的证据不能同时出现；
  - supported、uncertain、rejected evidence code 三个集合两两互斥。
- 集合操作只允许根作用域、已声明对象数组和已声明项目字段；`where` 禁止嵌套集合表达式。

### 输入证据绑定

新增版本化 `evidence_bindings`：

- Diagnosis Extractor：`diagnoses`、`non_codable_mentions`；
- Evidence Extractor：`supported_codes`、`uncertain_candidates`、`rejected_candidates`、`coded_evidence`；
- Principal Diagnosis Review：`candidates`；
- Procedure Extractor：`procedures`、`non_billable_mentions`。

统一 Agent Run 与 Provider A2A 都使用已脱敏输入检查：span 必须是非空、边界内的 `[start,end)`，且输入切片必须与 `evidence_text` 完全一致。失败元数据只含声明路径、`evidenceBinding`、稳定 ID 与抽象原因，不含患者值、引文或数组下标；畸形输出整体被抑制。

## 合同与 SDK

当前引用为 Diagnosis Extraction `/v6`、Coded Evidence `/v7`、Principal Diagnosis Review `/v7`、Procedure Coding `/v8`。旧 projector 引用继续保留。

追加式注册表由 75 增至 83 条；其中四个 set-only 中间版本和四个最终 evidence-binding 版本均按不可变策略保留，26 个当前引用全部匹配，静默变更、非法引用与重复引用均为 0。

SDK 当前版本：JavaScript `1.0.0-beta.13`、Python `1.0.0b12`、.NET `1.0.0-beta.13`。JavaScript、前端和 .NET 暴露集合谓词字段及 evidence binding；Python 原样无损透传。

## 验证证据

- 安全扩大后端回归：`451/451`；真实 Provider 和 Windows 原生 embedding 测试未纳入。
- 集合/逐项/根关系对抗：11 个 Agent、34 条关系、`59/59`。
- evidence binding 对抗：4 个 Agent、9 条绑定、错引文与越界合计 `18/18`。
- Provider A2A 合成输入合同往返：21 个通用 Provider Agent 全部通过；绑定 Agent 使用与运行输入一致的 quote/span。
- 运行矩阵：`26/26` 可执行、Provider 可解析、上线候选、关系/绑定定义有效且注册表匹配。
- 当前合同重放：`26/26`；缓存 Provider 输出合同重评：`26/26`。
- JavaScript SDK：`20/20`，构建和 `npm pack --dry-run` 成功。
- Python SDK：`28/28`，`1.0.0b12` wheel 成功。
- 前端：`114/114`，生产构建成功。
- OpenAPI `--check`：通过；静态部署预检：`45/45`。
- .NET：源码和 fixture 已更新；本机无 `dotnet`，未声称执行，继续由 CI 门禁承担。

证据文件：

- [`field_relation_replay_20260815_set_evidence_final`](../../reports/agent_hub/field_relation_replay_20260815_set_evidence_final/)
- [`evidence_binding_replay_20260815_final`](../../reports/agent_hub/evidence_binding_replay_20260815_final/)
- [`runtime_regate_20260815_set_evidence_final`](../../reports/agent_hub/runtime_regate_20260815_set_evidence_final/)
- [`set_evidence_typed_replay_20260815_final`](../../reports/agent_hub/set_evidence_typed_replay_20260815_final/)
- [`set_evidence_cached_e2e_20260815_final`](../../reports/agent_hub/set_evidence_cached_e2e_20260815_final/)
- [`development_preflight_20260815_set_evidence_final`](../../reports/agent_hub/development_preflight_20260815_set_evidence_final/)

## 与 Corti 的剩余差距

| 维度 | 本轮关闭 | 仍未证明 |
|---|---|---|
| 主诊断集合 | 恰好一个推荐候选，根推荐码与该候选一致 | 与 Corti/独立专家金标准的一致率、复杂多病因场景的临床选择质量 |
| 分类集合 | 诊断/手术互斥，Evidence 三分类按 code 两两互斥 | 同义词归一化后的语义重复、跨编码系统等价码冲突、跨 Agent 集合一致性 |
| 证据锚定 | 9 类 `evidence_text + char_span` 对已脱敏运行输入精确绑定 | CDI/Medical Coding 的分离 `char_start/char_end` 对象、OCR/Unicode 归一化 offset map、多文档版本和 document_id 绑定 |
| Corti 质量 | 错误结构和伪证据无法作为成功输出发布 | 同一批脱敏病例双边盲测、临床可行动性、诱导风险、准确率、延迟与成本 |
| 中国场景 | 中国编码/手术/CDI 语义进入确定性门禁 | 地方规则合法授权、医保/DRG/DIP 版本与回滚、医院接口和临床 reviewer 验收 |

## 下一阶段

下一优先级是扩展多文档证据绑定：支持对象形式 `quote + char_start + char_end + document_id`，绑定运行输入中的明确文档边界，并为 OCR/Unicode 归一化保存安全 offset map；随后建立跨 Agent 的诊断、主诊断、手术与证据集合一致性门禁。

总目标继续进行，所有 Agent 的 `production_ready` 保持 `false`，真实医院、云、法务、认证和独立 reviewer 门禁不作虚假关闭。
