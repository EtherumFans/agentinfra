# CDI / Medical Coding 真实模型语义 E2E 操作手册（2026-08-25）

## 目的与当前状态

此流程用于补齐 Agent Hub 最后两个外部模型必需 Agent：

- `clinical-documentation-improvement-agent`
- `medical-coding-agent`

runner 会在同一个临时后端进程和同一个一次性 attestation 信任域内，串行运行全部 26 个可见 Agent 的 happy、adversarial、reference 和三轮 stability。只有 CDI 与 Medical Coding 必须观察到真实 model provider/name；本地 24 个 Agent 继续执行各自确定性或受治理 Provider。最终直接生成严格 26-Agent bundle，不复用或重新签发已退出进程的旧 HMAC 证据。

可选的 `-IncludeClinicalCalibration` 会在同一受控后端中追加 50 次串行多病例调用：40 条已声明脱敏的中文 CDI 校准病例，以及 5 条明确 PHI-free 的合成 Medical Coding 病例各跑中文和英文。它重新执行最终 Query 的单维度门禁并计算证据锚定、非诱导、编码精确匹配和双语一致性；不会读取或外发 CCL 1,800/201/100 病例资产。

截至本文生成时，该真实模型流程尚未执行；严格语义门禁仍为 0/26，生产就绪仍为 0/26。

## 凭据安全要求

先前在聊天中公开过的 DeepSeek Key 必须视为泄露并在 DeepSeek 控制台撤销。不得再次使用，也不得把新 Key 粘贴到聊天、源码、`.env`、命令参数或报告文件中。

在用户可见的 PowerShell 7 窗口中执行：

```powershell
$env:ICODER_CREDENTIAL_LLM = Read-Host "输入新临时 DeepSeek API Key" -MaskInput
```

该命令把输入保存为当前 PowerShell 进程的临时环境变量，不进入 PowerShell 历史。确认变量存在但不要打印内容：

```powershell
[bool]$env:ICODER_CREDENTIAL_LLM
```

应只看到 `True`。

## 执行命令

从仓库根目录 `E:\Corti4C` 执行：

```powershell
& .\scripts\release\run-agent-hub-external-semantic-e2e.ps1 `
  -OutputRoot reports/agent_hub/external_semantic_e2e_phase_20260825_v1 `
  -IncludeClinicalCalibration
```

如果本次只验证严格 26-Agent 最小语义链，可省略 `-IncludeClinicalCalibration`。完整阶段验收应保留该开关；如果 50 条病例的执行证据有效但质量目标未达，runner 会先写出报告，再以失败状态退出，不能把“跑完”误报为“质量通过”。

runner 的安全行为：

- Key 只通过进程环境传给隐藏的临时 Uvicorn，不出现在命令行参数；
- 同时清除 `DEEPSEEK_API_KEY` 与 `OPENAI_API_KEY`，避免来源歧义；
- 使用 `C:\Temp\icoder-agent-external-e2e-*` 下的新临时 SQLite，不访问 `backend/data/icoder.db`；
- 禁用 Native MedCodER 与本地 STT，防止 Windows 原生模型内存崩溃；
- 只允许 DeepSeek HTTPS 出站，禁止无 Key 降级、mock 或 fallback 冒充成功；
- 无论成功或失败都停止临时后端、删除精确校验过的临时目录，并清除三个 Key 环境变量；
- 成功和失败路径都会扫描输出及临时日志，若出现 Key 原文则整轮证据失败；
- 只有 26/26 happy、26/26 adversarial、26/26 reference、156/156 stability，且所有签名、Trace、合同、语义和模型遥测通过时，严格门禁才可提升到 26/26。
- 启用临床校准后，还要求 50/50 均为 fresh HTTP、签名结果与 Trace 有效、真实 provider/model 可见、非 mock/非降级；CDI 和双语编码质量目标逐项记录，任何缺口保留为失败目标。
- CCL 派生的 1,800/201/100 病例因商用/外部处理许可、来源和脱敏证明缺失，runner 从设计上不读取这些文件，更不会发送给外部模型。

## 运行后检查

确认 Key 已被 runner 清除：

```powershell
[bool]$env:ICODER_CREDENTIAL_LLM
[bool]$env:DEEPSEEK_API_KEY
[bool]$env:OPENAI_API_KEY
```

三项均应为 `False`。随后在 DeepSeek 控制台撤销本次临时 Key；本地清除环境变量不能替代服务端撤销。

还必须检查：

- 没有残留 `python.exe` / `uvicorn`；
- `backend/data/icoder.db` 的大小、最后写入时间和 SHA-256 未变化；
- 输出 bundle 的 `valid=true`、`semantic_live_e2e_verified=26`；
- runtime matrix 的 `visible_semantic_live_e2e_pending=[]`；
- `production_ready_verified` 仍保持 0，不能用合成 E2E 替代临床、医院或生产验收。
- 若启用临床校准，`clinical-calibration/agent_hub_clinical_calibration_e2e.json` 必须为 50 行、`execution_valid=true`；`calibration_targets_passed` 可诚实为 false，并以 `failed_targets` 指导下一轮整改。

## Corti 当前对照与剩余门禁

Corti 当前公开 Medical Coding Agent 会从单次就诊文档综合上下文、抽取带原文证据的诊断/操作、分配 ICD-10-CM 与 CPT/HCPCS、校验顺序和 modifier，并输出缺口及不可编码项：<https://corti.ai/agents/medical-coding-icd-10-cpt-agent>。

Corti 当前公开 CDI 指南覆盖实时、近实时和批处理工作流，可使用 transcript、结构化事实、草稿或终稿，通过 Medical Coding/Web Search/Clinical Reference 等 Expert 识别 specificity gap，并生成有证据、非诱导的 provider query：<https://docs.corti.ai/get_started/cdi-outpatient>。

即使严格合成 E2E 达到 26/26，以下仍不能自动关闭：

- 中国 ICD-10-CN、ICD-9-CM-3、病案首页、医保结算及地方规则的权威来源与许可；
- 独立编码员/CDI 专家金标准、盲评、误导 query 审查和真实病例统计；
- 与 Corti Symphony 公布的全球代码体系、ranked alternatives、规则理由和临床质量基准的等价性；
- 医院角色、审批、HIS/EMR/医保接口、生产写回、审计归档和事故处置；
- 数据出境、隐私影响评估、云容量/SLA、渗透测试、法务、监管和认证。
