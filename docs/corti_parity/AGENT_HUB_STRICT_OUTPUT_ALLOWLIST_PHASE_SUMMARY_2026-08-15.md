# Agent Hub 严格输出白名单阶段总结（2026-08-15）

## 阶段结论

本轮把 26 个面向用户的 Agent 从“字段存在且类型正确”继续收敛到“只允许契约声明的领域字段发布”。统一 Agent Run、Provider A2A、Pack Loader、模型提示、Hub 卡片、JavaScript/Python/.NET SDK、运行矩阵和部署预检现在共享 `required_fields + optional_fields + field_types` 边界。缺字段、错类型或出现未声明字段都会失败关闭，且不会把模型 markdown、未知调试字段、工具载荷或潜在 PHI 作为部分成功结果发布。

结论仍限定为开发环境上线候选，不等于临床生产批准，也不表示 Corti 私有模型、托管基础设施、商业 SLA 或全部受限功能已被复刻。

## 本轮关闭的问题

1. 修复传输元数据与领域输出混用：通用 `status`、`markdown`、`corrected_draft` 等默认值不再能错误满足同名的 Pack 必填字段。
2. 新增严格输出白名单：投影器或模型返回未声明顶层字段时记录 PHI-safe `undeclared_output_fields`，并触发 `output_contract_violation`。
3. 契约支持显式 `optional_fields`；Pack Loader 要求必填与可选字段唯一、互斥，`field_types` 精确覆盖二者并由示例提供类型证据。
4. 所有已声明且实际出现的必填/可选字段均做 JSON 顶层类型验证；`boolean` 不会被误判为整数或数值。
5. Pure LLM 提示明确要求精确键集合及类型，禁止额外顶层键；运行时仍以确定性验证为准，不信任模型自报。
6. 契约违规时，公共响应抑制 markdown、领域字段、issues、tool payload 和 evidence；Run/A2A 只保留传输及 PHI-safe 校验元数据并强制人工复核。
7. 纠正 8 个历史输出与 Pack 声明不一致的 Agent 契约。其中 dedicated runtime 元数据继续与领域契约分离；真实领域字段被补入 required/optional 声明。
8. 示例同步脚本改为经过当前结构化投影器归一化后再回写，避免通用默认值遮蔽真实模型字段，也避免把可确定归一化的数组误写成字符串契约。
9. JavaScript SDK 增加并导出强类型 Agent Hub 卡片及输出契约；Python SDK补齐 Hub 列表/卡片入口；.NET SDK 增加强类型 `OutputContract`、可选字段和人工复核策略。
10. 部署预检升级为严格白名单门禁，并修复检查器仍匹配旧两条件失败表达式造成的误报。

## 回归与证据

- 严格契约、Pack、投影、Hub、A2A、安全属性专项：`141 passed`（分两组串行执行：55 + 86）。
- Agent Hub、统一 Run、三类 A2A、端点和受控 native-provider stream 扩大回归：`130 passed`。
- JavaScript SDK：`20/20`；Python SDK：`28/28`。
- .NET SDK：源码与测试已更新，但当前 Windows 终端及工作区运行时均无 `dotnet`，本轮不能声称新测试已执行；需在具备 .NET 8/10 SDK 的 CI 补跑。
- 前端全量：`114/114`；生产构建通过。仅保留既有动态/静态导入分包警告。
- 运行矩阵：磁盘 Pack 32，Hub 可见 26；26/26 executable、provider resolvable、launch candidate、类型完整、示例类型有效、严格输出白名单；21 条 Provider Registry 路由、5 条 dedicated 路由、0 条 legacy default。
- 已捕获输出在当前投影与契约边界重放：`26/26`。
- OpenAPI `--check`：通过。
- 静态部署预检：`45/45`，失败项 0。

证据目录：

- [`runtime_regate_20260815_strict_contracts_final`](../../reports/agent_hub/runtime_regate_20260815_strict_contracts_final/)
- [`strict_contract_replay_20260815_final`](../../reports/agent_hub/strict_contract_replay_20260815_final/)
- [`development_preflight_20260815_strict_contracts_final`](../../reports/agent_hub/development_preflight_20260815_strict_contracts_final/)

本轮所有 Python/后端验证均先清除 `ICODER_CREDENTIAL_LLM` 并使用 `LLM_PROVIDER=mock`。未使用已暴露密钥，未启动 Corti 浏览器自动化，未加载 Torch、PyArrow、FAISS、BGE 或 sentence-transformers，未启动 8000 端口服务，测试期间未出现新的内存访问异常。

## 与 Corti 的阶段性能力差距

| 维度 | 本轮后的 iCoDer | 仍需关闭的差距 |
|---|---|---|
| Agent 公共输出 | 26/26 可发现必填/可选字段及顶层类型；未知字段、缺字段、错类型均失败关闭 | Corti 私有 schema、版本兼容政策、线上错误分布不可从公开控制台完整验证；嵌套 JSON Schema 约束仍需继续完善 |
| 执行与 SDK | 21 Provider + 5 dedicated 路由；Run/A2A/Hub 与 JS/Python/.NET 契约已对齐 | .NET 本轮新增测试待有 SDK 的 CI 执行；真实 Provider 长周期稳定性、限流、计费和 SLA 未验证 |
| 临床质量 | 输出边界、人工复核、证据约束与安全失败关闭已工程化 | 类型正确不等于临床正确；需在同一批去标识病例上做 Corti/iCoDer 双边盲评、编码准确率、召回率、证据一致性和诱导风险评价 |
| 中国场景 | ICD-10-CN、ICD-9-CM-3、中文病历、DRG/DIP、医保及中国安全边界已进入 Pack 和接口合同 | 地方目录与医保规则的授权、版本、真实 HIS/EMR/结算联调及医院 reviewer 验收仍是外部门禁 |
| 语音与 Ambient | 本轮未倒退，协议、工件生命周期和失败关闭仍有开发证据 | Corti 的实时医疗语音、多说话人、方言、噪声、长音频、现场延迟及真实 ASR 质量仍明显领先且需外部 Provider/医院场景验证 |
| 部署与合规 | 开发静态预检 45/45 | Docker/Linux 镜像运行、真实 PostgreSQL/Nginx、KMS、灾备、容量、SBOM/漏洞扫描/签名、等保/隐私/渗透与运营审批未完成 |

## 下一阶段

1. 在具备 .NET 8/10 SDK 的 CI 执行新增 Hub 契约测试，并将结果纳入发布门禁。
2. 继续把顶层类型合同推进为可版本化的嵌套 JSON Schema，并增加向后兼容/破坏性变更检测。
3. 只使用新建、短期、可注销的临时 LLM 凭证执行 26-Agent 多轮真实稳定性、P50/P95、成本和失败模式；不得复用已经暴露的密钥。
4. 使用同一批去标识病例和明确预算，对 Corti 与 iCoDer 的 Medical Coding、CDI、Facts、Text Generation 和 STT 做双边输出及独立专家盲评。
5. 在 Linux/Docker 隔离环境执行 BGE/FAISS worker、真实数据库/代理、故障注入、容量、安全供应链和镜像签名验证。
6. 把地方医保/DRG/DIP 规则、医院 HIS/EMR/FHIR 联调、临床金标准、法务与认证保持为明确外部门禁，不用开发模拟结果替代生产批准。

总目标继续进行。本轮完成的是 Agent Hub 公共输出白名单和多 SDK 发现契约，不应被解释为 Corti 全部能力已经复刻。
