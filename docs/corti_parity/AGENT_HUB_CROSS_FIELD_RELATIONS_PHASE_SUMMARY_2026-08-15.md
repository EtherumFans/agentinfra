# Agent Hub 跨字段临床不变量阶段总结（2026-08-15）

## 阶段结论

本轮把 Agent Hub 输出契约从“单字段结构和值合法”推进到“字段组合也必须满足声明关系”。9 个高风险 Agent 共声明 11 条关系、15 个必须满足断言；统一 Agent Run、Provider A2A、Pack Loader、模型提示、Hub 发现、SDK、不可变注册表、离线重放和部署预检共享同一失败关闭边界。

这证明的是开发环境中的组合一致性，不是临床正确性或生产批准。未使用真实 LLM、Corti credits、浏览器自动化、Torch、PyArrow、FAISS 或本机原生 ML。

## 实现范围

`field_relations` 使用受控蕴含规则：每条规则只有稳定 `id`、`when` 和 `must`。路径只能访问契约声明的顶层字段或嵌套对象字段；没有任意表达式、数组通配、反射或代码执行。运行时只返回声明路径、`fieldRelation`、关系 ID 和抽象失败原因，不记录患者值。

支持的运算为：

- 常量比较：`equals`、`not_equals`；
- 存在及空值：`present`、`absent`、`empty`、`non_empty`；
- 路径比较：`equals_path`、`not_equals_path`；
- 数组计数：`length_equals`。

定义门禁限制为每个契约最多 32 条关系、每组最多 8 个谓词，并校验关系 ID、路径、运算符、常量类型和双路径类型。

## 已声明关系

| Agent | 关系 |
|---|---|
| Claim Check | 支付规则缺失或证据不足时必须人工复核 |
| CDI | 查询被门禁留置并要求人工处理时，CDI 专员与临床响应标志必须为真 |
| Clinical Education | 来源不足时必须给出限制并人工复核 |
| Clinical Guidelines | `NOT_MET` 时必须列出偏差并人工复核 |
| Code Validation | `FAIL` 时必须人工复核 |
| Medical Coding | 规则校验未通过时必须进入人工复核 |
| Principal Diagnosis Review | 初稿冲突时必须给出冲突原因并人工复核 |
| Procedure Extractor | `total_count` 必须等于手术项目数；存在问题时必须人工复核 |
| Rule Explainer | `REQUIRES_REVIEW` 状态必须对应人工复核 |

没有给没有可靠产品规则的 Agent 强行增加关系，也没有从单个示例推导临床阈值。Evidence Strength 与置信度的临床映射、诊断/手术可编码性等仍需金标准和 reviewer 决定。

## 契约与 SDK 演进

9 个受影响契约分别升级一版：

- Claim Check、CDI、Clinical Education、Clinical Guidelines、Medical Coding、Rule Explanation 当前为 `/v3`；
- Code Validation、Principal Diagnosis Review、Procedure Coding 当前为 `/v4`。

不可变注册表从 57 条增加到 66 条，旧引用保留，当前 26 个引用均匹配。Structured Output Projector 和前端 Code Validation renderer 保留旧版本别名。

SDK 版本更新为 JavaScript `1.0.0-beta.11`、Python `1.0.0b10`、.NET `1.0.0-beta.11`。JavaScript、前端和 .NET 暴露关系类型；Python 原样无损透传。字段保持可选，使没有关系的旧 Agent Card 仍可被客户端解析。

## 验证证据

- 后端关系、Run/A2A、Pack、Hub、版本、投影和离线 E2E 专项：`215/215`；
- 全关系对抗重放：9 个 Agent、11 条关系、`15/15` 断言被正确拒绝；
- 当前契约重放：`26/26`；
- 缓存 Provider 输出按当前 Pack 重新评估：`26/26`；
- 运行矩阵：26/26 可执行、Provider 可解析、上线候选、Schema/关系有效且注册匹配；
- JavaScript SDK：`20/20`，构建及 `npm pack --dry-run` 成功；
- Python SDK：`28/28`，`1.0.0b10` wheel 成功；
- 前端：`114/114`，TypeScript/Vite 生产构建成功；
- OpenAPI `--check`：通过；
- 静态部署预检：`45/45`；
- .NET 源码和反序列化 fixture 已更新，但本机没有 `dotnet`，不能声称已执行。

权威文件：

- [`field_relation_replay_20260815_final`](../../reports/agent_hub/field_relation_replay_20260815_final/)
- [`runtime_regate_20260815_field_relations_final`](../../reports/agent_hub/runtime_regate_20260815_field_relations_final/)
- [`field_relation_typed_replay_20260815_final`](../../reports/agent_hub/field_relation_typed_replay_20260815_final/)
- [`examples_e2e_20260813`](../../reports/agent_hub/examples_e2e_20260813/)
- [`development_preflight_20260815_field_relations_final`](../../reports/agent_hub/development_preflight_20260815_field_relations_final/)

## 与 Corti 的剩余差距

| 维度 | 本轮关闭 | 仍未证明 |
|---|---|---|
| 组合一致性 | 9 个高风险 Agent 的确定性对象级关系可发现、可审计并失败关闭 | 数组项目量词、主诊断候选唯一性、编码集合互斥、Evidence Strength/Confidence 分层 |
| 证据锚定 | `char_span` 本身的形状、非负和顺序已校验 | span 与原始输入长度、引用文本内容及文档版本的一致性 |
| 多版本 | 66 条不可变记录、旧投影别名、三 SDK 可选字段兼容 | 正式弃用窗口、旧客户端升级演练、.NET CI 实跑 |
| 临床质量 | 矛盾组合不再作为成功结果发布 | 与 Corti 同病例盲测、独立专家金标准、准确率/可行动性/诱导风险 |
| 中国场景 | 中国编码、CDI、医保/DRG/DIP 输出关系已有工程门禁 | 地方规则授权与版本、医院接口、结算联调和临床 reviewer 验收 |

## 下一阶段

1. 为数组项目增加受控量词关系，覆盖候选唯一性、编码集合互斥和每项证据状态一致性。
2. 将输入文档摘要绑定到运行上下文，在不回显 PHI 的情况下校验 evidence quote/span 与输入边界。
3. 增加当前版与上一版的三 SDK 升级 fixture、弃用声明和 .NET CI 门禁。
4. 只使用新建、短期、可注销凭证执行真实 Provider 稳定性与成本测试；完成后立即注销。
5. 使用同一批去标识病例和明确预算，对 Corti Medical Coding、CDI、Facts、Text Generation、STT 做双边盲评。

总目标继续进行，`production_ready` 仍保持 `false`，真实医院、云、法务、认证和独立 reviewer 门禁不作虚假关闭。
