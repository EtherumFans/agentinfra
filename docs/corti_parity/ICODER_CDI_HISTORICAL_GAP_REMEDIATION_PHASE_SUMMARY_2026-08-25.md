# iCoDer CDI 历史差距收口阶段总结（2026-08-25）

## 阶段结论

历史 CDI 40 例报告的 query-count 差距已完成重新计算与离线结构修复。旧结果中实际落在 fixture 允许区间外的只有 3 例：`G8-CDI-GAP-004` 为 0、期望 1–2；`G8-CDI-GAP-008` 和 `G8-CDI-CONFLICT-032` 均为 3、期望 1–2。此前列出的 `INSUF-025`、`NEG-027`、`LAB-036/037/038`、`CONFLICT-035` 均未越界。

本阶段为 `GAP-004` 增加了确定性安全兜底：只有病历同时明确急性胰腺炎和胆石症史、尚未记录具体病因、且存在相应病因 documentation gap 时，才生成一条开放、单维度的病因澄清。询问同时绑定两段逐字证据，包含“其他病因”和“无法确定”，不把胆石症史推断成胆源性诊断。已明确胆源性病因时不会重复生成。

`GAP-008` 的 DKA 诊断聚焦和已记录糖尿病类型抑制、`CONFLICT-032` 的病程冲突保留及类型/重复控制指标抑制，均由现有门控覆盖；新增精确历史三草稿回归，验证只保留病程冲突询问。

## 验证结果

- CDI 编排精确回归：41/41 passed。
- necessity、single-dimension、eligibility、semantic necessity 与 CDI 编排组合：153/153 passed。
- 26 个可见 Agent 离线示例/对抗/契约安全矩阵：78/78 passed。
- 临床校准计划、评分、防篡改、语义 bundle 与部署预检：24/24 passed。
- 部署静态预检：92/92 passed；PowerShell runner AST：0 errors。
- 所有测试串行执行，禁用 Native MedCodER、本地 STT 和外部 LLM，并同时将 `ICODER_DATABASE_URL`、`DATABASE_URL` 指向 `C:\Temp` 临时 SQLite。

## 证据边界

本阶段没有执行 DeepSeek 或其他真实模型，CDI 40 例真实校准仍是 0/40，CDI + Medical Coding 总校准仍是 0/50。上述结果只证明确定性门控、编排和回归资产可重复，不证明真实模型质量、独立临床金标准、Corti 对等或生产就绪。

下一步仍须使用一枚新的临时密钥运行受治理的 26-Agent live-provider E2E 与 50 次串行临床校准，再依据真实 `failed_targets` 继续修复；曾在对话中披露的旧密钥不得再次使用，并应在服务端注销。

机器证据：

- `reports/agent_hub/cdi_historical_gap_remediation_phase_20260825_v1/phase_evidence.json`
- `reports/deployment/cdi_historical_gap_remediation_phase_20260825_v1/deployment_preflight.json`
