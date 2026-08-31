# iCoDer CCL 2026 本地隔离预测评价器阶段总结（2026-08-27）

## 阶段结论

本阶段把已完成来源绑定的 CCL 2026 训练集变成了可执行的本地隔离评价门。新增评价器接收位于显式隔离目录内的 1,800 条代码预测，只输出聚合指标、数量与哈希；不会把病例正文、病案标识、逐例标签、逐例预测或错误样本复制到报告目录。

评价器本身已经用 1,800/1,800 oracle 合同自检证明计分和完整性绑定正确，但 oracle 不是模型运行，因此该结果明确固定为 `model_capability_proven=false`，不能解释为 iCoDer 准确率、Corti 等价、医院验收或生产就绪。

## 实现边界

- 预测包 schema：`icoder.ccl2026-local-prediction-packet/v1`。
- 聚合报告 schema：`icoder.ccl2026-local-aggregate-evaluation/v1`。
- 预测包必须位于调用方指定的隔离根目录；路径越界、缺失、重复、顺序变化、数据集哈希篡改或非精确 schema 均失败关闭。
- 每条预测只通过完整 canonical case digest 绑定，不携带病案标识或临床正文；输入包仍属于敏感的逐例代码预测，评价器不会复制或保留它。
- 正式指标的编码规范化只去除首尾空白并统一大小写；不删除点号、`x`、尾随位数，也不把父码、子码或临床扩展码视为相同。
- 完成状态必须给出主诊断且不得夹带失败原因；失败状态必须清空全部代码，只允许受限失败类别。失败病例进入分母，不允许静默 fallback 后记为成功。
- 所有预测代码必须是当前完整性验证目录的精确成员。目录外代码、重复代码或主次位置重复均使整份报告无可信指标。
- 输入声明必须为 `local_isolated`、`network_used=false`、`external_provider_used=false`、`clinical_text_included=false`、`raw_model_responses_persisted=false`。报告同时明确：这是预测生成方声明，尚未由独立网络观测验证。

## 聚合指标

有效的本地训练集测量会输出：

- 执行覆盖率与安全失败数；
- 主诊断精确准确率；
- 次要诊断 micro precision/recall/F1 与逐例 macro F1；
- 全诊断集合 micro precision/recall/F1；
- 主手术精确准确率；
- 其他手术 micro precision/recall/F1 与逐例 macro F1；
- 全手术集合 micro precision/recall/F1；
- 诊断与手术完整集合精确匹配率；
- 目录成员性、缺失/重复/越界/结构错误的聚合计数。

报告不输出代码字符串、case digest、逐例预测、逐例金标准、原文或错误示例。输入无效时 `metrics={}`，避免部分结果被误当作可信证据。

## 端到端自检证据

- 来源审计：`reports/agent_hub/ccl2026_local_dataset_audit_20260827_v2/ccl2026_local_dataset_audit.json`。
- 聚合自检：`reports/agent_hub/ccl2026_local_evaluator_selftest_20260827_v1/ccl2026_local_evaluator_selftest.json`。
- 自检覆盖：1,800/1,800；完整集合、主诊断、全诊断 F1、主手术和全手术 F1 均为 1.0；这只证明 oracle 计分器合同。
- 聚合报告内部 canonical digest：`3bf055fa70918fe67a02e4fa011fa0d5f2322078463382f845628d399cabfee3`。
- 聚合报告文件 SHA-256：`e175ff442d9bc182f03c734c943a8c2899a6cc6a60a7c9f15ec143ef3c779484`。
- 生成于 `C:\Temp\icoder-ccl-evaluator-*` 的逐例 oracle 包已在 wrapper 的已校验 `finally` 清理路径中删除；报告只保留其 SHA-256 和大小。
- 本阶段未调用 LLM、未访问外网、未读取 API Key；受保护开发数据库 SHA-256 保持 `2f1e5af01aac020cdd0eadac51b3ea65ba5b2e714d9f6ea3707992e829692877`。

## 真实本地确定性下界

在不加载神经模型、不调用 LLM、不访问网络的前提下，新增 `catalog-exact-name-frequency-recency-v1`：它只从病例 `text` 中查找当前目录精确名称，以出现频次、最后出现位置和名称长度做确定性排序。测试证明修改所有 expected/gold 字段不会改变预测代码；完整 case 只用于生成顺序绑定 digest。该方法明确登记为 `local_deterministic_baseline`，不是本地模型。

1,800 例训练集聚合结果：执行覆盖 100%；主诊断精确率 **9.0556%**；全诊断 micro F1 **22.4958%**；有主手术 gold 的 937 例中主手术精确率 **16.1153%**；全手术 micro F1 **16.2697%**；完整诊断+手术集合精确匹配 **0%**。这形成了一个诚实的纯目录基线，也证明词名匹配无法达到上线质量。

聚合证据：`reports/agent_hub/ccl2026_local_baseline_evaluation_20260827_v1/ccl2026_local_baseline_evaluation.json`；内部 canonical digest `20c48083685e08d51685e0e4cf2111c6cd7c253c3dabd7a23ad603b676699810`，文件 SHA-256 `bc6b33841f4027cd20ab2ff0cd50558915fbe9d5d0a1fee009c3530dd04826dc`。临时逐例预测包已清除。

## 本地模型运行时阻断

只读审计未导入原生 ML 模块。4 个 FAISS/metadata 资产共 220,238,288 bytes 且全部通过 manifest SHA-256；BGE-M3 权重存在，大小 2,271,145,830 bytes，但它仅是 embedding 检索器。当前宿主恰为已记录会产生访问冲突的 Windows `torch 2.11.0 + sentence-transformers 3.2.1`，同时 `pyarrow 24.0.0` 也被宿主安全策略阻断；项目还没有获批准的本地生成式临床编码模型。因此未设置危险 override、未加载 BGE、未伪造本地模型结果。

阻断证据：`reports/agent_hub/ccl2026_local_model_runtime_readiness_20260827_v1/ccl2026_local_model_runtime_readiness.json`；内部 canonical digest `64cf41cee933f2e6f55c7b60816fd8a9178fa518622ebf88f292154e0699a4cd`，文件 SHA-256 `e5650fed1aa5a34430d38f9231063b7b031f09378fc657cc20d638e52129636b`。

## 验证

- oracle、错误预测、父子码不折叠、篡改/重复/缺失、敏感字段注入、目录外代码、外发声明、路径越界、安全失败和报告篡改单测全部通过。
- 目录、Dictionary RAG、DeepSeek 编码适配器离线合同、Medical Coding schema/worker/retriever、Code Validation、Medical Coding A2A、CCL 审计/评价/确定性基线/本地模型就绪审计、双语盲审、临床计划/runner、Agent 语义 bundle、Runtime Matrix 与部署门扩大回归：**139 passed**。
- 静态部署预检：**110/110 passed**；证据为 `reports/deployment/ccl2026_local_baseline_phase_20260827_v3/deployment_preflight.json`，文件 SHA-256 `67ee72e68aad5764e34af8911f7aee650f9954ca68f6d24b3007879f07c1e755`。

## 仍然开放的差距

1. 还没有获批准的本地临床编码模型生成 1,800 条真实预测；oracle 1.0 只是计分器自检，纯目录基线的低分也不是模型成绩。
2. CCL 是训练集单一来源，不是独立 held-out、多医院、双语或双编码员裁决的临床 gold。
3. 还没有 Corti 对同一批合法可处理病例的输出，无法计算 head-to-head 差距。
4. 预测生成的无网络声明尚未通过 OS/容器级网络隔离与独立流量观测证明。
5. 目录许可、权威版本审批、真实 Docker/SBOM/签名、医院工作流、容量/SLA 与监管验收仍是生产门。

下一开发切片应在隔离 Linux/容器中换用经过验证的检索依赖，并提供获批准、来源和许可明确的本地生成式临床编码模型，再把该 Runtime 接到预测包合同做小批烟测和 1,800 例测量。当前 Windows 依赖不得通过危险 override 绕过，也不能用 oracle、mock 或纯目录基线替代模型质量。
