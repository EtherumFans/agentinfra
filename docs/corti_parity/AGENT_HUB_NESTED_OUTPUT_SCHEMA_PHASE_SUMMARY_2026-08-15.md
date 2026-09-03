# Agent Hub 递归输出 Schema 阶段总结（2026-08-15）

## 阶段结论

本轮把 26 个面向用户的 Agent 从顶层字段/类型白名单推进为递归结构合同。所有 `object` 和 `array` 字段现在必须声明受控 `field_schemas`，统一 Agent Run 与 Provider A2A 会递归验证属性、必填项、数组元素和动态映射类型；未知嵌套属性、嵌套错类型或嵌套缺字段均失败关闭。

同时建立追加式公共契约注册表：同一个版本化 `schema_ref` 一旦登记便不可静默修改，破坏性调整必须使用新的 `/vN` 引用。该结论是开发环境上线候选证据，不是临床生产批准。

## 本轮完成内容

1. 新增递归 schema 验证器，支持 `type/properties/required/additionalProperties/items`，最大深度 8；拒绝无类型数组 item、空对象 schema 和 `additionalProperties: true`。
2. 验证错误只暴露声明路径、关键字和类型，不包含患者值、数组下标或未知属性名。
3. 顶层未知属性名也不再回显；公共元数据使用 `<redacted>` 和 `undeclared_output_field_count`，关闭“把患者值放进 JSON key”造成的旁路泄露。
4. Pack Loader 要求 `field_schemas` 精确覆盖全部顶层 object/array 字段，并要求示例同时通过顶层和递归验证。
5. 26 个可见 Pack 全部写入递归 schema；空数组必须使用人工维护的 item schema，不允许生成 `{}` 通配。
6. Pure LLM 提示加入当前 Pack 的紧凑递归 schema；运行时仍以确定性验证为准。
7. Hub 卡片、JavaScript SDK、Python Hub 原始响应和 .NET SDK 均传播递归 schema；前端定义可递归消费。
8. 运行矩阵、离线重放、E2E 评估、示例同步和部署预检均加入递归 schema 门禁。
9. 新增 `output_contract_registry.json` 和追加式兼容性检查器：已有引用不可覆盖，新版本引用可显式登记。

## 新门禁发现并修复的问题

### Note Completeness 嵌套类型漂移

`documentation_gaps[].description` 的大部分值是字符串，但冲突项被投影成完整对象。顶层只看到 `documentation_gaps=array`，此前无法发现。现在投影器从冲突对象提取 `note/description` 为稳定字符串，Pack 示例同步为统一形状。

### trace_refs 路由间漂移

dedicated Agent 示例包含丰富的 Agent 专用 trace 字段，而统一 Run 会注入通用 `run_id/trace_id/provider_trace_refs`。递归门禁首次暴露两条路由的对象形状不一致。当前合同使用“已声明 Agent 专用属性 + 通用运行属性”并集，`run_id` 为共同必填项，未知属性仍禁止。

### 测试假实现仍输出旧形状

Provider A2A streaming 与 native stream 的 Claim Check 假响应仍使用空 `evidence_consistency`，被新 schema 正确拒绝。假实现已改为读取 Pack 当前示例，不再维护易漂移的手写 JSON。

## 验证结果

- 递归 schema、Run/A2A、Pack、投影、矩阵、兼容性和安全专项：`144/144`。
- 统一 Run、Hub、A2A、端点及 native-provider stream 综合回归：`130/130`。
- JavaScript SDK：`20/20`；Python SDK：`28/28`。
- 前端：`114/114`，生产构建通过；保留既有动态/静态导入分包警告。
- .NET SDK 已增加递归类型及反序列化断言；当前机器没有 .NET 8/10 SDK，本轮仍不能声称已执行。
- 运行矩阵：32 个磁盘 Pack、26 个可见 Agent；26/26 executable、provider resolvable、launch candidate、顶层类型完整、递归 schema 完整、示例递归有效、不可变注册表匹配、严格输出白名单。
- 历史捕获输出按当前边界重放：`26/26`。
- 契约兼容性：26 个当前引用全部登记，新增 0、静默变更 0、无效引用 0、重复引用 0。
- OpenAPI `--check`：通过。
- 静态部署预检：`45/45`。

证据：

- [`runtime_regate_20260815_nested_schemas_final`](../../reports/agent_hub/runtime_regate_20260815_nested_schemas_final/)
- [`nested_schema_replay_20260815_final`](../../reports/agent_hub/nested_schema_replay_20260815_final/)
- [`development_preflight_20260815_nested_schemas_final`](../../reports/agent_hub/development_preflight_20260815_nested_schemas_final/)
- [`output_contract_registry.json`](../../backend/official_agents/output_contract_registry.json)

## 与 Corti 的剩余差距

| 维度 | 本轮后的 iCoDer | 仍需关闭的差距 |
|---|---|---|
| 输出结构 | 26/26 顶层及嵌套结构可发现、可验证、可版本化、可失败关闭 | 当前子集尚未表达 enum、数值范围、字符串格式、数组长度、条件分支和跨字段临床不变量 |
| 契约演进 | 已登记引用不可静默改变，破坏性变更要求新版本 | 尚缺 SDK 多版本迁移指南、弃用窗口、兼容性适配器和真实客户端升级演练 |
| 临床质量 | 结构畸形和未知字段不能作为成功结果发布 | 合法 JSON 仍可能包含临床错误；需同一批去标识病例、Corti 双边输出和独立专家盲评 |
| 中国适配 | 中国编码、DRG/DIP、医保及中文病历字段均有递归机器合同 | 地方规则授权/版本、医院接口、结算联调和 reviewer 验收仍为外部门禁 |
| 托管与合规 | 开发门禁、SDK、预检和审计元数据对齐 | 真实云、KMS、灾备、容量、供应链扫描、渗透、等保/隐私、法务和运营审批未完成 |

## 下一阶段开发环境优先级

1. 扩展受控 schema 子集，支持 enum、minimum/maximum、minItems/maxItems、字符串格式和安全的条件约束。
2. 为编码置信度、char span、人工复核、证据强度、状态枚举等高风险字段建立跨字段临床不变量。
3. 增加 schema v1→v2 SDK 兼容性 fixture、弃用声明和客户端迁移测试。
4. 在具备 .NET 8/10 SDK 的 CI 执行新增递归 Hub 契约测试。
5. 仅使用新建短期凭证和去标识病例执行真实 Provider 多轮稳定性、成本、延迟和 Corti 双边盲评；不得复用已暴露密钥。

本轮未使用真实 LLM 密钥、浏览器自动化或高风险原生 ML，也未启动 8000 端口服务。总目标继续进行。
