# Agent Hub 专用 A2A 与真实 LLM 阶段总结（2026-08-15）

## 阶段结论

本阶段把 Agent Hub 的 5 条专用执行路径与 21 条 Provider Registry 路径统一到当前 Agent Pack 公共合同边界。当前 26 个 Hub 可见 Agent 均可解析 Provider、可执行、具有严格输出白名单、嵌套字段 schema、字段关系、证据绑定或跨 Agent 关系（适用时），并通过开发候选静态门禁。

这不等于已经复刻 Corti 的临床质量或生产托管能力。Corti 目录映射、开发验证和中国场景声明为 20/20；临床质量验证与生产就绪验证仍为 0/20。没有同一去标识金标准病例集上的 Corti/iCoDer 双边预测、盲评、准确率、召回率、严重错误率和医院编码员验收，因此不能宣称临床等价或可直接上线。

## 本阶段完成

1. Code Validation、Compliance Guardrail、Note Completeness 三条简单专用路由改为动态读取当前 Pack，按 Pack 白名单投影，执行必填、嵌套 schema、证据和跨 Agent 校验；合同失败时 503/错误信封失败关闭，成功结果签发租户绑定 attestation。
2. Medical Coding 统一运行和 A2A 输出只公开 Pack 的 8 个领域字段；运行时详情与渲染文本移到 DataPart metadata；Provider、投影和合同异常均失败关闭；agent_ref/schema_ref 从当前 Pack 动态取得。
3. CDI A2A 输出只公开 9 个 Pack 字段，补齐嵌套、证据、跨 Agent 校验和租户绑定 attestation；内部 query gate 拒绝/延迟状态不再进入公共领域对象。
4. 数据库从 Alembic 039 升到 040，补齐 `run_history.trace_events_purged_at` 与 `trace_events_purged_count`，解除真实运行的审计持久化失败。未执行包含无关不可逆 token 摘要迁移的 041/042。
5. Diagnosis Extractor 的条件工具预检改为独立 `tool_eligibility` 布尔合同。只有明确 JSON boolean `false` 才可撤回工具；缺失、字符串或畸形判定一律暴露受 MCP 权限边界约束的工具。预检结果不再冒充最终 Agent 输出。
6. Medical Coding 发现并修复 v7 合同漂移：主诊断 evidence 序列化器会输出 char span、doc_id、doc_type、confidence，但 v7 schema 仅允许 kind/text。当前合同按不可变版本规则升为 `icoder/MedicalCodingAgentOutputV2/v8`，v7 保留在历史注册表，注册表现有 100 个引用。
7. Medical Coding 合同失败新增 PHI-safe 审计事件，只记录声明路径、校验关键字和数量，不记录被拒值或病历文本。
8. 中文姓名规则对“利尿治疗”的误脱敏已修复并加入回归；真实姓名仍按原规则脱敏。
9. Windows 原生 Torch/FAISS 栈保持禁用；仅当健康原因明确为已知 Windows 原生访问冲突时，`search_icd` 才使用 37,897 条只读 ICD-10-CN 目录的精确词法回退。索引缺失、损坏或未知降级仍失败关闭，不会静默降级。
10. Medical Coding v8 的强制人工复核策略同时写入 `validation_summary.manual_review_required=true`、`human_review.review_required=true` 和统一响应信封，修复 Provider 清洁结果与嵌套合同不一致。
11. 通用 Provider 投影会在引证文本于去标识源文档中恰好出现一次时，确定性校准证据坐标；缺失或重复引证不修补并继续失败关闭。通用合同失败追踪只保存字段路径、关键字和计数，不保存被拒值或病历内容。

## 真实 DeepSeek 证据

真实服务状态确认默认 Provider 为 DeepSeek、模型为 `deepseek-chat`、中国区严格出口和 PII redaction 开启。有效中文请求全部由仅含 ASCII 的 Python 源码通过 `\uXXXX` 构造并在发送前断言不存在 `?`，再以 UTF-8 提交；PowerShell 5 直接构造中文时产生的乱码请求不作为中文能力证据。

- Diagnosis Extractor：`run-350d896d-4674-4fc4-b8af-301dcfa4118c`。Provider 为真实、非确定性、未 fallback、合同有效且签名成功；但 0 次工具调用，模型报告本轮没有工具，未输出编码。这暴露了已在本阶段修复的条件预检死锁。
- Note Completeness：`run-778ad1e4-aae8-499f-b0b1-4e64eca8114c`。合同与签名成功，返回 6 条中文 incomplete sections，证明有效中文理解；同时暴露“利尿治疗”可能被姓名规则误脱敏，已修复。
- Medical Coding：`run-6ca51f34-2171-4d0e-b1d3-5eea430be34d`。DeepSeek 调用成功、解析出 2 个候选、成本 USD 0.000228、耗时 4595 ms，但被 v7 公共合同拒绝；旧运行只持久化通用错误，具体路径未保存。代码审计定位到主诊断 span evidence 与 v7 schema 漂移，已升版为 v8 并补充 PHI-safe 失败路径审计。
- Code Validation：`run-38bea64f-97e0-40b9-9db2-8c4efedac942`。2 个编码完成目录验证，6 次工具调用，结构化提取与签名成功，耗时 21008 ms。其编码和工具参数为 ASCII，可作为真实工具链证据；该次请求中的中文部分不作为语言质量证据。
- `run-0504c63a-72a9-40a0-b179-7738c91e51dd` 仅用于证明真实 Provider、非确定性、无 fallback、成本记录（约人民币 0.000236）；输入中文被 PowerShell 损坏，不用于质量结论。
- Medical Coding 最终复验：`run-4d77ca73-6dc1-4127-80dd-f187d0142f52`。v8 合同有效并签名成功，返回 `I50.101` 与 `I10.x09`，嵌套人工复核为 true，2 条证据，Provider token usage 为 1184 input / 301 output，服务端耗时 5739 ms，成本人民币 0.000250。
- Diagnosis Extractor 最终复验：`run-9ee8a62d-3d74-4ec6-921e-14bbf013a4c3`。v6 合同有效并签名成功，返回 `I50.101` 与 `I10`；2 次 `search_icd`、2 次 `verify_code` 全部成功，4 条证据，必填、类型、嵌套 schema、证据绑定和跨 Agent 校验均无错误；服务端耗时 12479 ms，成本人民币 0.001407。

一次尝试重放失败幂等键时，因系统对 FAILED 键采用重新执行语义而产生了额外真实调用；后续不再重放失败键。最终复验均使用新的幂等键且各限一次，未重放失败键。

## 回归与门禁

- 专项后端/API/Agent runtime：120 passed。
- 最终修复后聚焦回归：98/98 passed；覆盖条件工具预检、工具词法回退、严格输出合同、唯一引证坐标校准、PHI-safe 失败追踪和 Medical Coding v8 嵌套人工复核。
- LLM-with-tools 条件预检与真实调用模拟：25 passed（包含在上述 120 中）。
- 前端：114/114；TypeScript 与 Vite 生产构建通过。
- JavaScript SDK：21/21。
- Python SDK：29/29。
- 当前 typed contract 重放：26/26。
- 34 条字段关系：59/59 对抗断言被检测。
- 15 条证据绑定：30/30 对抗断言被检测。
- 8 条跨 Agent 关系：16/16 对抗断言被检测。
- Hub 运行矩阵：26/26 可见 Agent 可执行、Provider 可解析、开发 launch candidate ready。
- Corti 固化目录：目录映射 20/20、开发验证 20/20、中国适配声明 20/20、临床质量 0/20、生产就绪 0/20。
- 不可变合同注册表、Pack integrity、开发部署预检和 `git diff --check` 通过。
- 未运行 .NET SDK：当前阶段没有新的 .NET 代码变更，且本机可用性未重新确认。

证据目录：

- `reports/agent_hub/typed_contracts_20260815_real_llm_final/`
- `reports/agent_hub/field_relations_20260815_real_llm_final/`
- `reports/agent_hub/evidence_bindings_20260815_real_llm_final/`
- `reports/agent_hub/cross_agent_20260815_real_llm_final/`
- `reports/agent_hub/runtime_matrix_20260815_real_llm_final/`
- `reports/corti_parity/real_llm_final_20260815/`
- `reports/corti_parity/real_llm_final_20260815/real_deepseek_postfix_e2e.json`
- `reports/deployment/development_preflight_20260815_real_llm_final/`
- `reports/deployment/development_preflight_20260815_postfix/`

## 相对 Corti 的剩余差距

1. 缺 Corti 与 iCoDer 在相同去标识病例、相同目录版本和相同人工金标准上的双边真实输出与盲评；当前只能证明工程合同和部分真实链路，不能证明准确率等价。
2. Windows 桌面进程内 Torch/FAISS/sentence-transformers/PyArrow 因已知原生访问冲突继续禁用。Diagnosis/Medical Coding 的本机检索不能作为上线架构；需要隔离 Linux 检索服务、版本冻结资产和健康门禁。
3. 缺合法授权并可审计回滚的 ICD-10-CN、ICD-9-CM-3、医保、DRG/DIP 省市版本资产。DRG Agent 仍是风险复核，不是权威分组与结算引擎。
4. 缺真实 HIS/EMR/病案首页/医保接口、生产 PostgreSQL/队列/对象存储、灾备、长稳压测、监控告警、等保/隐私/法律与医院验收。
5. Corti 的托管 SLA、企业 IAM、规则治理、全球编码覆盖、支付方覆盖和真实临床输出质量不能通过控制台只读观察反推。
6. Corti 控制台本阶段仅沿用已登录只读目录/配置证据；由于此前自动化曾触发 Windows/Codex 原生内存崩溃，本阶段没有启动新的重型浏览器自动化或在 Corti 提交病例、消耗 credits、修改项目。

## 凭证与资源回收

真实密钥只存在于用户启动的 PowerShell/后端进程环境。本阶段的所有本地 Python 测试命令在启动前删除 `ICODER_CREDENTIAL_LLM`、`DEEPSEEK_API_KEY` 并固定 `LLM_PROVIDER=mock`；真实调用只通过 `127.0.0.1:8000` 访问用户启动的后端。测试结束后必须停止后端、删除 PowerShell 中的临时变量、关闭该 PowerShell，并在 DeepSeek 控制台注销/轮换该测试密钥。此前在对话中明文暴露的旧密钥不得继续使用。
