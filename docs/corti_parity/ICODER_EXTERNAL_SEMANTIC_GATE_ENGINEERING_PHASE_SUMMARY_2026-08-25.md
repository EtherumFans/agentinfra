# iCoDer 外部模型语义门禁工程阶段总结（2026-08-25）

## 结论

在不使用真实 Key 的前提下，CDI 与 Medical Coding 的外部语义验证基础设施已从“缺少可执行入口”推进为可审计、可失败关闭的严格 26-Agent runner，并追加受治理的 50 次多病例校准门禁。真实模型质量尚未执行，因此本阶段只完成工程门禁，不把严格语义、临床质量或生产状态提升为已通过。

## 已完成

- 修复 24-Agent 本地 bundle 中机器计数为 2、限制文字却残留 3 的真实性漂移，并增加回归断言。
- 新增外部两 Agent 专用 bundle 验证器：必须是当前 CDI/Medical Coding Pack，四类证据完整，且每个外部 Run 都观察到非 mock、非降级的真实 model provider/name。
- 新增 24+2 组合 bundle 验证器，用于同一信任域内的分片证据；范围必须不重叠且并集严格等于当前 26 个可见 Agent，任一源哈希或内容变化均失败关闭。
- Runtime Matrix 可识别组合 bundle；只有验证器返回当前 26 个 Agent 才会提升严格语义计数。
- 新增 `run-agent-hub-external-semantic-e2e.ps1`：在单个一次性服务器信任域中串行跑完整 26-Agent，直接生成严格 bundle；Key 不进入命令行/报告，成功或失败都执行精确泄漏扫描、环境清除、进程回收和临时库清理。
- 新增受治理临床校准计划和 runner：仅允许外发 CDI 40 条声明脱敏病例与 5 条 PHI-free 合成双语编码病例（合计 50 次串行调用）；CCL 1,800/201/100 全部标记为 `external_provider_egress_allowed=false`。最终 CDI Query 使用当前 deterministic gate 重新判定单维度，不再采用旧 runner 的硬编码零泄漏指标。
- 校准报告绑定 fixture、Pack、响应和 Trace 哈希，强制真实 provider/model、结果/Trace 签名、非 mock、非降级及人工复核；质量目标与证据有效性分轴，执行完整但质量不足仍写出 `failed_targets` 并使发布命令失败。
- 无 Key 探针按预期在启动后端前失败；校准 runner 无外发确认也在网络调用前失败；PowerShell AST 解析 0 错误；部署静态预检扩展为 92/92。
- 重新运行本地 24-Agent 新鲜签名 HTTP：happy/adversarial/reference 各 24/24、stability 144/144，P50 0.527 秒、P95 1.025 秒。bundle 正确记录仅 2 个外部模型 Agent 未评估。
- 离开原服务器进程后对旧 v2 证据的离线重建被 HMAC 验签拒绝；未绕过、未伪造，旧目录已标注失效，权威证据切换到 v3。

## 当前量化状态

- Hub 可见、可执行、Provider-resolvable、结构性 launch candidate：26/26。
- 本地语义基线：24/26。
- 外部模型必需：CDI、Medical Coding，共 2 个。
- 严格新鲜 live-provider 合成语义：0/26（等待新临时 Key 实跑）。
- 多病例校准：计划 50 次，真实执行 0/50；当前只证明 runner/数据边界/评分器就绪。
- 临床质量、医院验收、生产就绪：0/26。
- 本阶段真实 LLM 使用：否；外网模型调用：否；受保护数据库修改：否。

本轮新增聚焦回归 24/24、全可见 Agent 离线安全 78/78；治理计划自身 3 项、评分/遥测/防篡改 5 项和部署预检均包含在上述聚焦回归中。机器计划见 `reports/agent_hub/clinical_calibration_plan_20260825_v1/`，部署报告见 `reports/deployment/clinical_calibration_gate_phase_20260825_v1/`。

## Corti 当前差距

Corti 当前 Medical Coding Agent 公开覆盖单次就诊综合、精确证据抽取、ICD-10-CM/CPT/HCPCS 分配、顺序和 modifier 校验、缺口与不可编码项；Symphony 还公开 ranked alternatives、规则理由、全球代码体系和真实/学术/合成基准。iCoDer 当前重点是 ICD-10-CN/ICD-9-CM-3、中国病案与人工复核，但仍缺权威持续更新规则库、CPT/HCPCS/PCS 等全球覆盖、独立大规模质量证据和托管服务能力。

Corti CDI 公开工作流支持 transcript、结构化事实、草稿/终稿，以及实时、近实时和批处理触发，组合 Coding、Web Search、Clinical Reference/Calculator 等 Expert 生成有证据的非诱导 query。iCoDer 已有专用编排、证据 span、non-leading gate、query lifecycle、租户审计与人工审核，但真实 DeepSeek 语义稳定性、外部知识来源许可/真实性、医院触发工作流和独立 CDI reviewer 质量仍未验证。

操作步骤见 [`ICODER_EXTERNAL_AGENT_SEMANTIC_E2E_RUNBOOK_2026-08-25.md`](ICODER_EXTERNAL_AGENT_SEMANTIC_E2E_RUNBOOK_2026-08-25.md)。
