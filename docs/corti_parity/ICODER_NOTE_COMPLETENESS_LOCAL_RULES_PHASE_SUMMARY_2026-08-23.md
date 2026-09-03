# iCoDer Note Completeness 本地规则阶段总结（2026-08-23）

> 声明：本文件记录开发环境工程证据，不是临床、生产、监管或医院上线批准。
>
> 阶段：Note Completeness deterministic local runtime
>
> 状态：开发门禁通过；语义质量与外部上线门禁仍开放

## 阶段结论

本阶段将 `note-completeness-agent` 从统一 Run 强依赖 `PureLLMProvider`、A2A 失败后隐式 regex 回退的矛盾状态，收敛为一个明确、可审计的本地执行能力。统一 Run、A2A、Agent Pack、Hub readiness 和运行矩阵现在共同声明 `icoder.documentation-rule-engine.v1`；外部 LLM 关闭或没有密钥时，该 Agent 仍能执行中国病历 7+1 必填章节检查。

当前能力边界是“章节级结构完整性”，不是语义病历质控：

- 识别主诉、现病史、既往史、体格检查/查体、辅助检查/实验室检查、入院/出院/初步诊断、治疗/诊疗经过，以及真实手术病例的手术记录。
- 区分“完全缺失”和“存在标题但正文为空”，`completeness_score` 只按存在且正文非空的章节计算。
- 对“否认手术史、未行手术”等否定表述不误加手术记录要求。
- 不调用外部网络或 LLM，Provider 成本为 0；统一 Run 和 A2A 都返回严格 `icoder/NoteCompletenessOutput/v2` 数据。
- Pack 将人工复核设为 required。空 `conflicts` 只表示确定性规则没有检测语义冲突，不表示病历经临床证明一致。

旧 LLM 解析实现保留为显式 `run_llm_enhanced` 评估入口，不再决定用户默认路径的可用性；其失败仍回到同一确定性实现。

## 运行、审计与产品状态

- 新 Provider 具有独立健康检查、确定性 capability、严格输出合同、零成本和 backend metadata trace。
- 既有通用 `RuleEngineProvider` 同步补齐 backend metadata trace，因此 Compliance Guardrail 的统一 Run 也不再缺少 Provider 归因事件。
- A2A DataPart 现在同时带 `backend_provider` 与 `backend_type=rule_engine`；外层 metadata、领域结果、attestation 和 trace 使用同一 run/provider 身份。
- Hub 租户 readiness 在无模型配置时将 Compliance Guardrail 与 Note Completeness 两个 Agent 标为 `local_ready`，其余 24 个模型依赖 Agent 继续失败关闭。
- HTTP/OpenAPI/SDK 的响应结构没有变化，因此本阶段不需要版本升级或重新生成 SDK。

## 验证结果

| 门禁 | 结果 | 说明 |
|---|---:|---|
| 定向单元与 Pack/矩阵 | 97/97 | 章节解析、LLM 显式增强兼容、两个规则 Provider、注册表、Pack 与运行矩阵 |
| Run/A2A 定向入口 | 3/3 | Note Completeness happy、adversarial 与 A2A，均为本地 Provider、严格契约和可查询 trace |
| 失败复测 | 8/8 | readiness 24/2 分类及 Compliance backend trace |
| 扩展单次回归 | 602/602 | unit runtime/backends、Hub/readiness、可见性/发现、A2A 与完整 26-Agent 双场景 E2E |
| 26-Agent 离线双场景 | 52/52（包含在 602） | 每个可见 Agent 一条 Pack 示例和一条对抗输入；2 个本地成功、24 个模型依赖安全失败关闭、0 个不安全响应 |
| Pack 防篡改 | 通过 | Note Completeness canonical SHA-256 `4afaf8b5b33df3a18ae419cd160c5a429f43aa824578938028368bfe872aa5cc` |
| 运行矩阵 | 通过 | 26/26 visible/executable/provider-resolvable/launch-candidate；24 external-LLM、2 local deterministic、0 legacy default |
| 部署候选静态预检 | 81/81 | `deployment_preflight.json` 失败项 0；预检脚本单测 1/1 |

机器证据位于 `reports/agent_hub/local_note_completeness_phase_20260823/`。

## 对 Corti 的差距增量

本阶段关闭的是“无模型时病历完整性入口只能失败、Run/A2A 执行真相不一致”的开发差距。它同时提供适合中国院内环境的隐私与可用性优势：不出网、延迟稳定、无 token 成本、规则边界可解释。

与已归档的 Corti Note Completeness/Agent 能力基线相比，仍有以下实质差距：

- 本地规则只验证章节存在和非空，不能可靠判断内容是否充分、时间/否定/归属、入院与出院诊断冲突、诊疗逻辑或事实一致性。
- 尚无医院科室/病种/文书类型的可配置模板规则、规则版本治理和国家/地区规范更新证据。
- 尚无当前 Corti 控制台同题双向实测、真实 Provider 重复回归、P50/P95/错误率或成本比较。
- 尚无独立临床金标准、盲评 reviewer、一致性统计、灵敏度/特异度或误报漏报阈值。
- 尚无真实 EMR/HIS 工作流、医院权限、写回审批、云基础设施、法务、监管、安全认证和生产运维批准。

因此 Note Completeness 可计为第二个“开发环境本地能力成功”的 Hub Agent，但不能计为 Corti 语义质量等价，也不能将 Pack 的 `production_ready` 提升为 true。26-Agent 静态语义验证和生产批准继续保持 0/26。

## 安全与环境状态

- 验证使用空 `ICODER_CREDENTIAL_LLM` / `DEEPSEEK_API_KEY`、`LLM_PROVIDER=mock`、`ICODER_ALLOW_EXTERNAL_LLM=false` 和禁用原生 MedCodER；未读取或使用真实密钥。
- 未启动浏览器或 TCP Uvicorn；测试仅通过进程内 ASGI 和隔离 SQLite 运行。
- 受保护开发数据库未用于测试；最终 SHA-256 另记录在阶段机器证据中。
- 测试数据库由 pytest teardown 删除表；宿主策略禁止删除测试数据库文件，未绕过该限制。

## 下一步

继续按可在开发环境关闭的价值排序推进：优先评估 Code Validation 能否接入有来源、版本和可分配性证据的本地 ICD 目录，而不是把格式规则或“全部人工复核”伪装成编码有效性成功。其后仍需对 24 个模型依赖 Agent 执行受控真实 Provider 快乐/对抗/重复矩阵，并保持医院、云、法务、认证和独立临床门禁为外部未完成项。
