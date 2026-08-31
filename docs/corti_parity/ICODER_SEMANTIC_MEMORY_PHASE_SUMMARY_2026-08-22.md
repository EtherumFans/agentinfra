# iCoDer Semantic Memory 阶段总结（2026-08-22）

## 阶段结论

持久 Memory 已从仅 lexical 的开发实现收敛为可运行、可审计、可测试的隔离 Semantic Memory 上线候选合同。开发环境完成了远程 HTTPS embedding 边界、出站再次脱敏、最小请求、加密向量、模型版本一致性、Cloud 失败关闭、真实 TCP 生命周期、API/健康状态、三 SDK 口径与部署预检。

这不是“患者长期病历记忆已上线”。当前 consent 仅是登录用户对本人工作偏好和去标识化上下文的自助授权；患者/监护人/医院权威授权与患者 PHI 持久化继续失败关闭。

## 已完成工程能力

- 新增 `icoder.memory-embedding.request/v1` / `response/v1` 固定合同；只允许服务端配置的 HTTPS endpoint 和 Vault 凭据。
- API 进程不加载 Torch、sentence-transformers、FAISS 或 PyArrow。测试专用 loopback HTTP 必须由构造参数显式开启，生产配置不能打开。
- 出站只发送 `contract + texts + normalize`；不发送组织、用户、患者、consent、Run、Task 或 Connector 标识。
- 文本在出站前再次执行 PHI/PII 检查；多行空白规范化；脱敏器异常转换为稳定的 `CONNECTOR_MEMORY_DEIDENTIFICATION_FAILED`，不继续落库或出站。
- 响应拒绝额外字段、非法 model/version、16–4096 以外维度、非有限值、异常幅值、零向量和长度不一致；向量在 API 侧归一化。
- `remember` 将 model、immutable version、dimensions 和 vector 写入现有加密 `key_facts`，不新增明文向量列，也不需要数据库迁移。
- `recall` 只比较 model/version/dimensions 完全一致的向量；Cloud/required 模式遇到旧索引或缺失向量时返回 `CONNECTOR_MEMORY_SEMANTIC_INDEX_INCOMPLETE`，不混用或静默降级。
- Local optional 模式保留 lexical fallback，但输出明确暴露 `retrieval_mode`、`semantic_coverage`、`semantic_degraded` 和原因，不能冒充 semantic 成功。
- consent 撤销硬删除内容与向量；retention 到期后不可召回并可物理 purge；返回内容始终标记非权威、需人工复核和用户记忆不可信。
- Cloud 启动强制要求 `ICODER_MEMORY_SEMANTIC_REQUIRED=true`、HTTPS 443 URL、32–512 字符凭据、精确 egress allowlist 主机和现有 at-rest encryption key。
- 应用健康状态、OpenAPI、TypeScript、Python 与 .NET 源码合同均明确 `authority_class=authenticated_user_self_service`、`patient_authority_verified=false`、`phi_storage_allowed=false`。
- Release Candidate CI 已纳入真实 TCP Semantic Memory 测试；静态部署预检新增对应检查。

## 真实 TCP E2E 证明范围

测试通过真实 loopback TCP 和 Bearer 认证执行完整 `ConnectorExecutor → Registry Adapter → Memory Store → HTTP embedding fixture` 链路，证明：

1. 去标识化内容可生成并加密保存向量；数据库密文不暴露 model 或向量。
2. “血糖/二甲双胍”记忆可由“糖尿病用药”语义查询召回，不依赖 lexical 字面相同。
3. 查询中的手机号码在出站前被移除，fixture 未观察到原始号码或身份字段。
4. Connector execution audit 同时覆盖 remember/recall 成功。
5. legacy Expert 的异步持久入口复用同一治理路径。
6. model version 被篡改为旧版本后 required 模式失败关闭。
7. consent 撤销后 Memory 行和向量为零残留。
8. 错误服务凭据返回稳定的上游 401；临时 Uvicorn fixture 在测试后关闭。
9. fixture readiness 证明进程未加载已知会在当前 Windows 主机触发 native 崩溃的 ML 模块。

该 fixture 是确定性 16 维同义概念映射，仅验证网络、认证、合同和治理，不验证真实 embedding 模型质量。

## 自动化证据

| 证据 | 结果 |
|---|---:|
| Semantic/Connector/Cloud/API/OpenAPI/legacy 联合后端回归 | 123/123 |
| 独立真实 TCP Semantic Memory E2E | 1/1 |
| Cloud 配置 + Semantic Provider 单测 | 59/59 |
| Memory consent/encryption/isolation/revoke API | 8/8 |
| 健康、OpenAPI、部署预检联合 | 9/9 |
| TypeScript SDK build + tests | 41/41 |
| Python SDK tests | 48/48 |
| 静态部署预检 | 54/54 |

机器可读证据位于 `reports/agent_hub/semantic_memory_phase_20260822/phase_evidence.json`；部署报告位于同目录的 `deployment/`。

## 与 Corti 的剩余差距

开发环境的 Semantic Memory 工程缺口已关闭，但下列事项没有证据，不能算 Corti 生产能力复刻完成：

- 尚无真实同区域 embedding 服务、固定模型资产/许可证、SBOM/镜像扫描和 Secret Manager 注入证据。
- 尚无中文临床检索金标准、召回/误召回阈值、偏差测试、对抗评估、容量、P95/P99、故障注入、灾备、多副本和索引回填/滚动升级证据。
- 当前授权不是患者权威 consent；患者主体解析、监护人/代理人授权、撤回跨系统传播、法定病历留存和 Break-glass 仍需医院、法务和隐私审批。
- 共享团队/科室 Memory、delegated machine subject Memory、训练用途授权和跨租户/跨区域复制继续禁止或未实现。
- 真实医院安全评审、独立渗透测试、临床 reviewer、等保/个保与监管认证仍未通过。

因此本阶段可记为“Semantic Memory 开发上线候选合同完成”，不能记为“患者 PHI Memory 已上线”或“Corti 托管 Semantic Memory 已完整复刻”。
