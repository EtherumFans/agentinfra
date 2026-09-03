# iCoDer CDI 必需安全门禁失败关闭阶段总结（2026-08-22）

> 声明：本报告证明开发环境中的 CDI 门禁失败关闭、审计和公共传输合同，不代表真实模型临床质量、Corti 私有 CDI 实现等价或医院生产批准。

## 结论

CDI 的主 `stub_runner` 已确认只在 `ICODER_CDI_FORCE_STUB_FOR_TESTS=1` 且当前进程实际加载 pytest 时可启用，部署环境无法通过变量单独打开。REST 与 A2A 也已经拒绝主 RealCDIRunner stage/expert trace 中的降级。

本阶段关闭的是更深一层缺口：主模型阶段之后，claim-evidence extraction 和 semantic-necessity review 会再次调用 LLM。调用失败时，旧逻辑为了继续运行而保留 query，并把门禁结果降级为 PASS/DEGRADED；该失败不属于 RealCDIRunner 的 stage trace，因此 REST/A2A 可能把 query 当作已完成全部安全审查的非降级结果发布。

## 实现

- `CDICase.degraded_safety_gates` 结构化记录必需安全门禁失败，只保存门禁名与聚合数量，不保存病历、query 或模型正文。
- claim-evidence gate 对每个 `ClaimEvidenceGateResult.degraded=true` 计数；semantic-necessity gate 对批量异常、单 query 异常和非 JSON 结果统一计数。
- 内部 orchestrator 仍可保留 query 供本地审计和后续确定性 NLQ 检查，但任何公共 REST/A2A adapter 发现该字段非空都会返回 503，不能持久化 CDI case、生成 attestation 或返回临床 `result`。
- REST 在返回 503 前写入 tenant-owned `cdi.run.failed.required_gate_degraded` 审计，仅包含门禁聚合、`manual_review_required=true` 和 `clinical_result_published=false`。审计提交失败时回滚并返回 `audit_persistence_failed`，仍不发布临床结果。
- A2A 失败 metadata 只公开降级门禁名称与 PHI-safe stage trace，不输出被拦截的 query 内容。

## 验证结果

- 首轮 orchestrator/A2A/RealRunner/门禁聚焦回归：**95/95**。
- CDI 全单元、真实 API 生命周期、JWT 租户、claim/semantic gate、系统审计和预检扩大回归：**341/341**，仅 1 条 Starlette 测试客户端弃用警告。
- 新增专项证明：claim gate 降级结构化、semantic gate 降级结构化、A2A 无结果、REST 不持久化 case、REST 失败审计成功提交、审计失败仍无结果。
- 静态部署候选预检：**67/67**，新增 `cdi_required_safety_gate_degradation_is_structured_and_unpublished`。
- OpenAPI `--check` 通过，仍为 269 paths、288 schemas、842,015 bytes。
- 未使用真实 LLM、未允许外部 LLM、未加载 Windows 原生 MedCodER、未启动独立后端。
- 开发主库 `backend/data/icoder.db` SHA-256 保持 `9547e301cca78695f983d837c91ab45819db5440c0f90a3b3bc80f34cb71bb3e`。

## 对 Corti 的差距判断

本阶段关闭了 CDI 公共结果的一个安全与审计缺口，但没有提高真实模型的查询质量。Corti 与 iCoDer 在统一病例上的 query 必要性、非诱导性、临床有用性、query 数量、延迟和费用仍需新凭据双边运行及独立 CDI reviewer。现有 40 例历史指标也不能由失败关闭门禁替代。

## 仍开放的门禁

1. 26-Agent 全新真实模型快乐/对抗/重复矩阵与 Corti 同病例对照。
2. 独立 CDI/编码/临床 reviewer 对必要性、可回答性、诱导风险和编码影响的双盲验收。
3. 真实医院病历工作流、HIS/EMR/FHIR、医生响应生命周期和生产写回审批。
4. Docker/Linux MedCodER、生产 KMS、PostgreSQL 多副本、队列、云、法务、认证、渗透和 SLA。

机器证据目录：`reports/agent_hub/cdi_required_gate_fail_closed_phase_20260822/`。

