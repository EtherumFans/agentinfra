# iCoDer 专用临床运行时遥测阶段总结（2026-08-22）

## 阶段结论

本阶段关闭了专用 Medical Coding 与 CDI Agentic 执行链缺少真实 Provider/model/token 汇总的问题，并为 ASR 建立了独立、无音频和无转写正文的推理遥测。只有实际观察到的字段才会输出；mock、预检失败、降级和缺失 usage 不会被补零或伪装成成功 LLM span。ASR 不冒充 LLM，也不虚构 token、credits 或美元成本。

最终宽矩阵为 **1041 passed、0 failed、178 warnings**，部署候选静态预检为 **76/76**。测试期间未调用真实 LLM/ASR、未加载 Windows 原生 MedCodER、未启动 8000 端口。

## 官方边界复核

- 2026-08-22 重新获取 Corti 官方 [`Export OpenInference traces`](https://docs.corti.ai/agentic/guides/export-traces.md)：HTTP 200，UTF-8 3,708 bytes，SHA-256 `c0185cd104d29e71638863841a3b0c21d2949e0b2200a2b86530bb725d0a76cd`。Agentic trace 仍是 Context 级 OpenInference 导出。
- 同日获取 Corti 官方 [`Speech to Text overview`](https://docs.corti.ai/stt/overview)：HTTP 200，UTF-8 6,241 bytes，SHA-256 `982389c5b45dd3e8760ff037a083c8f35cdbc006b3629be8adfde0864e3556a5`。其公开面把实时 dictation、ambient stream 与预录音 transcript 作为独立 STT 产品链，而不是把 ASR 伪装为 Agentic LLM 调用。
- 同日获取 OpenTelemetry GenAI 官方 [`semantic conventions overview`](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md)：HTTP 200，UTF-8 1,352 bytes，SHA-256 `4145af3ec45572af5e539b6c778019b3d82561f355995d2ec1ba14722b165f39`。当前公开 GenAI 约定不能为本地 ASR 提供可据此推断的 token/credits 账单合同，因此本阶段选择独立的 ASR 推理遥测，而不是发明 LLM 属性。

## 已实现

### Medical Coding

- Fast/Deep 共用的专用 A2A dispatch 在隐藏 inline trace 时仍写入一次租户、用户、Run 和 Trace 归属明确的 Provider 事件。
- 从真实结果中提取 provider、model、input/output/total token、显式 USD cost 和实际 LLM 调用数；字段缺失即省略。
- mock、预检失败或 degraded 结果不生成伪 LLM usage，临床输入、候选编码、证据和输出正文均不进入该事件。

### CDI

- 汇总实际执行的 stage call 与确实被调用的 expert call；`SKIPPED_NOT_NEEDED` 等未执行专家不计入调用数。
- 任一实际调用缺失 usage 时，整体 token 汇总被省略，避免用部分 token 制造低估；安全门禁降级或 trace 失败会标记为失败事件。
- 不接收 chart、prompt、query、输出正文或 tool arguments，仅保存有界运行属性。

### ASR

- FunASR batch、FunASR streaming 与 Whisper fallback 记录真实 engine/model、latency、`complete|empty|failed`、fallback 和 streaming 状态。
- 同步 transcript、异步 job 与重启恢复共享 `icoder/stt-inference-telemetry/v1`；持久化前再次执行严格 allowlist，并保存到加密内部请求状态。
- 音频字节、路径、转写文本、异常详情、设备信息、虚构 credits/token/cost 均不写入遥测；公开 Corti 兼容响应未被扩展成自定义账单字段。

### A2A 结构化标识符安全修复

首次宽矩阵在 1,040 项中发现 1 个真实缺陷：随机 Task UUID 恰好包含 `13800138000` 形态时，内部 `_a2a_v1_task_id` 被自由文本电话规则脱敏，进而破坏 `artifactId` 与可恢复 SSE 关联。现已在递归 PHI 脱敏前剥离任何客户端保留字段，只在脱敏后附加 v1 传输层显式提供的可信 Task ID。固定手机号样式 UUID 和客户端关联字段伪造均有负向回归。

## 验证结果

- Medical Coding/CDI/RunTrace 聚焦回归：**50/50**。
- STT 服务、作业、恢复和真实 API 生命周期扩大回归：**100/100**。
- Connector graph 污染序列与后续 Medical Coding/Agent Run 精确复现：**19/19**，测试会恢复官方 Agent 配置。
- A2A 结构化 ID 聚焦验证：**6/6**。
- 修复前权威宽矩阵：**1039 passed、1 failed**；失败即上述手机号样式 UUID 误脱敏。
- 修复后同范围并加入伪造关联字段负向用例：**1041 passed、0 failed、178 warnings**，耗时 309.20 秒。
- 部署候选静态预检：**76/76**；新增门禁同时检查专用临床遥测和结构化 Task/Artifact ID 的脱敏边界。

## 仍未关闭的差距

1. 本阶段没有真实 Provider 调用，不能证明 26 个 Agent 的临床语义质量、稳定性、P50/P95、真实成本或 Corti 双边一致率。
2. ASR 仍缺授权中文医疗音频上的方言、多人、噪声、长音频、断流、词级时间戳、diarization、准确率、延迟和成本验证。
3. ASR 遥测目前是加密内部审计合同，不等同于公开标准、OTLP Collector、第三方 APM 或 Corti credits 账单。
4. Medical Coding/CDI 的 Provider 遥测已接入 Agentic trace，但真实多 Provider、多轮失败、跨服务 W3C trace context 和生产多副本仍需外部环境验证。
5. 医院数据授权、临床 reviewer、法务、商用许可、等保/认证、云基础设施、Secret Manager 和生产可用性仍是外部门禁，不能由本机测试替代。

## 证据

- 机器证据：[`reports/agent_hub/dedicated_clinical_telemetry_phase_20260822/phase_evidence.json`](../../reports/agent_hub/dedicated_clinical_telemetry_phase_20260822/phase_evidence.json)
- 部署预检：[`reports/agent_hub/dedicated_clinical_telemetry_phase_20260822/deployment-preflight/deployment_preflight.json`](../../reports/agent_hub/dedicated_clinical_telemetry_phase_20260822/deployment-preflight/deployment_preflight.json)
- 当前差距矩阵：[`CORTI_ICODER_LIVE_GAP_MATRIX_2026-08-21.md`](CORTI_ICODER_LIVE_GAP_MATRIX_2026-08-21.md)
