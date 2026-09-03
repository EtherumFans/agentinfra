# Agent Hub 语义值约束阶段总结（2026-08-15）

## 阶段结论

本轮把 26 个面向用户的 Agent 从“顶层和嵌套结构正确”推进为“所有声明字段均具备机器可验证的结构和值约束”。统一 Agent Run、Provider A2A、Pack Loader、提示词、Hub、JavaScript/Python/.NET SDK、运行矩阵、离线 E2E 和部署预检现在共同识别枚举越界、置信度越界、字符串/数组超限、人工复核绕过及非法字符区间，并在公共边界失败关闭。

结论仍是开发环境上线候选，不是临床生产批准，也不代表 Corti 的私有模型、托管基础设施、商业 SLA 或全部受限功能已被复制。

## 本轮完成内容

1. 受控 schema 子集新增 `enum`、`const`、`minimum/maximum`、`minLength/maxLength`、`pattern`、`minItems/maxItems`、`uniqueItems` 与数字数组顺序约束 `x-order`。
2. `field_schemas` 从只覆盖顶层 object/array 扩展为精确覆盖全部必填和可选字段；26/26 Pack 均满足全字段 schema。
3. 所有字符串限制为最多 32768 字符，所有数组最多 100 项；所有数值 `confidence` 限制在 0–1。
4. `char_span` 统一为恰好两个非负整数且非递减，阻止负坐标、反向区间和错误长度作为成功结果发布。
5. `human_review=required` Pack 中所有声明的 `manual_review_required` 均以 `const:true` 固化；CDI 的专科复核和医师响应布尔字段也固定为 true。
6. Evidence Strength、Procedure Status、Diagnosis Assertion/Status/Confidence、CDI Review Priority 等明确值域写入 Pack。Diagnosis 的 `confidence` 保留 `high/medium/low` 枚举，没有把等级任意伪造为概率。
7. 诊断抽取器兼容旧捕获输出的 `completed/warning/requires_review`，在投影边界确定性归一为 `PASS/WARNING/REQUIRES_REVIEW`。
8. 校验错误只包含声明路径、关键字和抽象原因，不包含患者值、数组下标或 Provider 控制的未知 key。
9. JavaScript、前端和 .NET Hub schema 类型同步暴露全部新增关键字；Python SDK 保持原始字典无损透传并增加约束 fixture。
10. 缓存 E2E 评估器可在不登录、不调用后端的情况下，用当前 Pack 重新投影和验证旧版成功响应；示例同步器复用相同人工复核权威边界。

## 契约版本与兼容性

首轮全字段语义约束为 26 个当前契约显式升版。随后补齐 `char_span` 元素非负约束时，只有 Diagnosis Extraction、Discharge Summary Structuring、Coded Evidence、Principal Diagnosis Review 和 Procedure Coding 五个契约再次变化，因此只对这五个继续升版。

`output_contract_registry.json` 保留全部历史版本且不覆盖已有条目。最终状态：

- 当前可见契约：26；
- 注册表条目：57；
- 新引用：0；
- 静默变更：0；
- 非法引用：0；
- 重复引用：0。

新增维护命令 `bump_agent_pack_output_contract_versions.py` 支持 dry-run、全量升版和 `--agent` 选择性升版。

## 新门禁发现并修复的问题

### 四个必须复核 Pack 的示例与运行时策略漂移

Compliance Guardrail、Diagnosis Extractor、Principal Diagnosis Review 和 Procedure Extractor 的旧示例写成 `manual_review_required=false`，但 Pack 策略和运行时均要求 true。示例已归一，schema 以 `const:true` 阻止后续回退。

### Diagnosis 状态词漂移

字段定义要求 `PASS/WARNING/REQUIRES_REVIEW`，旧真实捕获输出使用 `completed`。投影器现做确定性兼容归一，Pack 示例和当前契约使用标准枚举，旧数据重放仍通过。

### 测试环境继承真实 Provider key

扩大回归发现一个“空 key”用例仍会继承机器级 `DEEPSEEK_API_KEY`，并产生一次 401 请求。测试现显式删除该变量；后续所有本轮命令同时清除 `ICODER_CREDENTIAL_LLM` 和 `DEEPSEEK_API_KEY`，使用 `LLM_PROVIDER=mock`。该请求没有成功调用模型，但作为隔离缺口已关闭。

### 历史 E2E 元数据不含新字段

旧响应的 `structured_extraction` 没有 `invalid_field_schemas` 和顶层 allowlist 元数据，不能直接证明当前契约。缓存评估器现使用当前 Pack 与历史 provider markdown 离线重算，26/26 通过；不把旧 `valid=true` 当作新门禁证据。

## 验证结果

- 语义校验、Pack、Run/A2A、兼容性和 26 Pack 往返专项：`98/98`。
- Structured Output Projector：`26/26`。
- 扩大后端/Hub/A2A/E2E 回归：首次 `676 passed, 3 failed`；三项均定位为环境继承、同进程 Torch 安全自检和旧 E2E 汇总，修复后分别在干净进程 `1/1`、`12/12`、`3/3` 通过。未并行运行 pytest。
- 运行矩阵：32 个磁盘 Pack、26 个可见 Agent；26/26 executable、provider resolvable、launch candidate、全字段 schema、示例有效和注册表匹配。
- 历史捕获输出按当前边界重放：`26/26`。
- 缓存 Agent E2E 按当前 schema 离线重评：`26/26`。
- JavaScript SDK：`20/20`；Python SDK：`28/28`。
- 前端：`114/114`，生产构建通过；只保留既有动态/静态导入分包警告。
- .NET 源码与反序列化测试已更新；当前机器没有 `dotnet`，不能声称已执行，继续保留为 CI 门禁。
- OpenAPI `--check`：通过。
- 静态部署预检：`45/45`。

证据：

- [`runtime_regate_20260815_semantic_constraints_final`](../../reports/agent_hub/runtime_regate_20260815_semantic_constraints_final/)
- [`semantic_constraint_replay_20260815_final`](../../reports/agent_hub/semantic_constraint_replay_20260815_final/)
- [`agent_hub_examples_e2e.json`](../../reports/agent_hub/examples_e2e_20260813/agent_hub_examples_e2e.json)
- [`development_preflight_20260815_semantic_constraints_final`](../../reports/agent_hub/development_preflight_20260815_semantic_constraints_final/)
- [`output_contract_registry.json`](../../backend/official_agents/output_contract_registry.json)

## 与 Corti 的阶段性能力差距

| 维度 | 本轮后的 iCoDer | 仍需关闭的差距 |
|---|---|---|
| 输出契约 | 26/26 全字段可发现；结构、枚举、常量、范围、长度和区间顺序可失败关闭 | 尚缺条件 schema、字段依赖及更完整的跨字段临床不变量，例如 evidence strength 与置信度/输出分层的一致性 |
| 版本演进 | 57 个版本不可变登记，破坏性变化必须新 `/vN` | 尚缺正式弃用窗口、迁移指南、旧客户端适配器和真实多版本客户端升级演练 |
| 临床质量 | 合法形状但值域非法的输出不再作为成功发布 | 值域合法仍不等于临床正确；需同一批去标识病例、Corti 双边输出和独立专家盲评 |
| 中国场景 | ICD-10-CN/ICD-9-CM-3、否定/既往/手术状态、证据区间、DRG/DIP/医保字段已有值约束 | 地方规则授权与版本、医院接口、结算联调和 reviewer 验收仍是外部门禁 |
| 托管与合规 | 开发门禁、SDK、缓存重放和静态预检对齐 | 真实云、KMS、灾备、容量、SBOM/扫描/签名、渗透、等保/隐私、法务和运营审批未完成 |
| 真实 Provider | 本轮 mock/离线路径稳定且不需要真实密钥 | 26 Agent 多轮真实稳定性、P50/P95、成本、限流和失败分布仍需新建短期凭证；已暴露凭证不得复用 |

## 下一阶段开发环境优先级

1. 增加跨字段临床不变量：Evidence Strength/Confidence/输出分层、Procedure Status/计费集合、Diagnosis Assertion/可编码集合、char span 与证据文本边界一致性。
2. 为当前/上一版 schema 增加 JS/Python/.NET 多版本迁移 fixture、弃用声明和客户端升级演练。
3. 在具备 .NET 8/10 SDK 的 CI 执行新增 Hub 契约测试。
4. 仅使用新建、短期、可注销的临时 Provider 凭证和去标识病例，串行生成 26 Agent 多轮稳定性、成本、延迟和失败模式报告；完成后立即注销。
5. 使用同一批去标识病例和明确 Corti credits 预算，对 Medical Coding、CDI、Facts、Text Generation、STT 做双边盲评。
6. 在 Linux/Docker 隔离环境执行 BGE/FAISS worker、真实 PostgreSQL/Nginx、故障注入、容量与供应链验证；Windows 主进程继续禁止加载已知会崩溃的原生 ML 栈。

本轮未启动 8000 端口服务，未使用 Corti 浏览器自动化，未成功调用真实 LLM，也未提交 Corti 预测或消耗 credits。总目标继续进行。
