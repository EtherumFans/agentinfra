# Agent Hub 多文档证据与跨 Agent 可信链阶段总结（2026-08-15）

> 后续状态更正：Compliance Guardrail—Code Validation 可信链完成后，当前
> 跨 Agent 关系为 4 条、对抗检测 8/8；本文件中的 3 条/6 次是本阶段完成时
> 的历史快照。参见 `AGENT_HUB_COMPLIANCE_CODE_VALIDATION_CHAIN_PHASE_SUMMARY_2026-08-15.md`。

## 阶段结论

本轮完成了开发环境内可验证的多文档证据坐标、跨 Agent 一致性关系和防篡改上游结果链路。26 个 Hub 可见 Agent 继续全部满足工程上线候选门禁；这表示代码、契约、路由和离线回放可发布，不表示临床生产批准，也不表示已复刻 Corti 的私有模型质量、SLA 或托管基础设施。

## 本轮完成

- 统一 Run、Provider A2A、CDI 和 Medical Coding 支持版本化多文档输入；限制为 32 文档、64,000 字符/文档、256,000 字符总量，支持 `none/NFC/NFKC`。
- Evidence binding 同时校验文档 ID、版本、Unicode `[start,end)`、精确引文、边界和歧义，错误中不返回患者值。
- 6 个 Agent 共声明 15 条 evidence binding；错引文与越界对抗回放 30/30 检出。
- 3 个 Agent 共声明 3 条跨 Agent 关系，覆盖诊断抽取→主诊断复核、诊断抽取→证据提取、主诊断复核→医学编码；冲突与上游歧义回放 6/6 检出。
- 跨 Agent 代码比较支持 NFKC/大小写/空白规范化；不把字符串规范化冒充临床语义推理。
- 成功结果新增 `schema_ref` 和 `result_attestation`。HMAC 证明绑定组织、Agent、Run、Schema、完整结果 SHA-256 与 24 小时有效期；篡改、过期、跨租户和身份错配全部失败关闭。
- 统一 Run 在脱敏/模型调用前验证上游证明；A2A 在路由脱敏前验证原始上游结果，再向 Handler 传递服务器拥有的验证标记，避免脱敏改变摘要。
- JavaScript、Python、.NET 和前端类型同步；OpenAPI 已更新。Python wheel `icoder_sdk-1.0.0b13-py3-none-any.whl` 已构建。
- Pack 当前契约均与追加式注册表匹配。注册表共有 94 个历史引用；本轮开发过程中产生的中间版本引用继续保留且未被当前 Pack 使用，这是追加式不可变注册策略的结果，不应删除或覆盖。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| Hub 可见上线候选 | 26/26 |
| Provider Registry / 专用路由 | 21 / 5 |
| 当前契约注册匹配 | 26/26 |
| 跨字段关系 | 34 |
| Evidence binding | 15 |
| Evidence 对抗断言 | 30/30 |
| 跨 Agent 关系 | 3 |
| 跨 Agent 对抗断言 | 6/6 |
| 后端相关回归 | 128 passed, 4 skipped |
| JavaScript SDK | 21/21 |
| Python SDK | 29/29 |
| 前端 | 114/114 + production build |
| OpenAPI | `--check` 通过 |
| 部署静态预检 | 45/45 |

.NET 因本机没有 `dotnet` 未执行，保留给 CI。Python 的 `python -m build` 因环境内同名模块缺少 CLI 入口失败，已改用隔离构建依赖的 `pip wheel` 成功构建；这不是 SDK 源码失败。

## Corti 只读对照

使用已登录控制台进行了低风险只读检查，没有提交预测、没有消耗 credits、没有打开麦克风/音频流，也没有启动本机 Torch/FAISS。

- Corti 当前控制台展示 20 个 Pre-built Agents；iCoDer 的 26 个可见 Agent 覆盖这 20 个目录级用例，并额外提供 Claim Check、Discharge Summary Structuring、DRG/DIP Review、Evidence Ranker、Evidence Extractor、Principal Diagnosis Review。
- Corti Medical Coding Studio 可见 Coding systems、Include/Exclude code filters、Expand、Samples、Input/Output、Settings/Code、Event Inspector 与实时 cost。iCoDer 已具备双编码体系、过滤/展开契约、运行跟踪和成本字段，但本轮没有用同一病例执行双方真实预测，因此不能声明输出质量、延迟或成本等价。
- Corti 控制台公告显示 Corti Models 由 Corti 托管在欧洲基础设施；iCoDer 的中国场景部署、数据驻留和医院互操作仍需在中国生产环境验收，不能由开发机静态门禁替代。
- 浏览器控制在导航时发生两次第三方分析请求超时；页面与 Codex 未崩溃。为降低已知 Windows 原生栈风险，本轮没有继续打开 Builder 重交互，也没有执行 STT/实时流。

## 尚未关闭的能力差距

1. **真实临床质量**：缺少同一批去标识病例上的 Corti/iCoDer 双盲评分、编码金标准、CDI 可回答性与误导风险评估。
2. **完整跨 Agent 图**：目前只有 3 条高价值链路；其余 23 个 Agent 尚未声明语义级上游约束，代码系统版本、同义词、否定/历史/家族史冲突仍需专门规则和标注集。
3. **OCR/原始坐标**：当前坐标指向脱敏规范化文本，没有原始 EMR 字节、OCR 页/框或脱敏前后位置映射。
4. **Corti Builder/托管模型**：未完成同等 Builder 预览、私有模型、工具生态、用量计费、SLA 和事件可观测性的真实双边 E2E。
5. **中国生产适配**：真实 HIS/EMR/FHIR、医保、地方 ICD/DRG/DIP 规则授权、医院网络、等保/个保/数据出境、KMS/灾备/监控与医院验收仍是外部门禁。
6. **语音能力**：Dictation、Ambient、Pre-recorded 的真实中文医疗 ASR、方言、多说话人、噪声、长音频与断流恢复尚未完成。
7. **运行环境**：.NET 本机验证、Linux ML worker、PostgreSQL/Nginx 多实例和容量/SLA 尚未在本轮关闭。

## 证据

- `reports/agent_hub/multidoc_crossagent_matrix_final/`
- `reports/agent_hub/multidoc_evidence_replay_final/`
- `reports/agent_hub/cross_agent_replay_final/`
- `reports/deployment/development_preflight_20260815_multidoc_crossagent/`
- `docs/openapi/openapi.json`

## 密钥与安全

本轮所有 Python/后端命令都先清除 `ICODER_CREDENTIAL_LLM` 和 `DEEPSEEK_API_KEY`，并强制 `LLM_PROVIDER=mock`；没有使用此前聊天中暴露的真实 LLM Key。该 Key 已出现在会话明文中，应立即在 DeepSeek 控制台注销并创建新 Key，旧 Key 不应继续使用。
