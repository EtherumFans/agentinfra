# Agent Hub 合规护栏—编码校验可信链阶段总结（2026-08-15）

## 阶段结论

本轮关闭了 Compliance Guardrail 与 Code Validation 之间“只是目录上相邻、
运行时无法证明审查了同一编码集合”的缺口。Compliance Guardrail 现在公开
本次规则实际审查的编码、编码体系和角色；当调用方提交经过服务器签名认证的
Code Validation 上游结果时，统一 Run/A2A 会验证护栏审查集合必须是上游
`validated_codes` 的子集。集合冲突、上游篡改、跨租户复用或多个同 Agent
上游结果歧义均失败关闭。

这提升了工程可审计性和跨 Agent 一致性，不表示编码准确率、医保政策质量或
临床生产等价已经得到验证。

## 本轮完成

1. Compliance Guardrail 确定性运行结果新增必填 `reviewed_codes`：
   - `code`：实际送入规则检查的非空编码；
   - `code_system`：`ICD-10-CN` 或 `ICD-9-CM-3`；
   - `role`：主诊断、其他诊断或手术操作。
2. 输入编码按角色、大小写规范化身份去重；空编码不会进入审查清单，且不会
   由模型或规则引擎新增输入中不存在的编码。
3. 新增跨 Agent 关系 `reviewed_codes_match_code_validation`：
   `reviewed_codes[].code` 必须是已认证 Code Validation
   `validated_codes[].code` 的子集，比较只执行 NFKC、空白和大小写规范化，
   不伪装成临床同义词推理。
4. 关系保持 optional，使 Compliance Guardrail 可以独立运行；但一旦提供
   Code Validation 上游结果，就必须先通过租户/Run/Agent/Schema/结果摘要
   绑定的 HMAC 证明和集合一致性检查。
5. 公共契约最终提升到 `icoder/ComplianceGuardrailOutput/v4`，投影器、
   schema 生成器、Corti 20-Agent 目录门禁、不可变注册表和 Pack 示例同步。
   开发过程中登记的 v3 保留为未被当前 Pack 使用的追加式历史引用。
6. 新增统一 API 正反 E2E：匹配上游返回成功结果与结果证明；不匹配上游
   返回 `output_contract_violation`，抑制领域结果，只公开 PHI-safe 关系元数据。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| Hub 可见上线候选 | 26/26 |
| 当前契约 E2E/重放 | 26/26 |
| Compliance 当前真实临时 uvicorn 增量 E2E | 1/1 |
| 上游匹配/冲突统一 API E2E | 2/2 |
| 跨字段关系 | 34；对抗检测 59/59 |
| Evidence binding | 15；对抗检测 30/30 |
| 跨 Agent 关系 | 4；对抗检测 8/8 |
| 后端/API/Hub 扩大回归 | 181 passed |
| JavaScript SDK | 21/21 |
| Python SDK | 29/29 |
| 前端 | 114/114 + production build |
| Corti 20-Agent 开发门禁 | 20/20 |
| 部署静态预检 | 46/46 |

组合 E2E 使用 25 个未变 Agent 的冻结成功 Provider 响应，并按当前契约重新
评估；Compliance Guardrail 则在本轮临时 uvicorn、临时 SQLite 和真实开发
登录下重新执行。证据来源由 `evidence_provenance.json` 明确记录，没有把旧
响应静默改写成新响应。

.NET 因本机无 `dotnet` 未执行，继续由 CI 承担。前端构建仅有既有模块分块
警告，没有错误。

## 与 Corti 的剩余差距

- Corti Compliance Guardrail 的真实支付方/机构规则覆盖、规则更新治理和
  同数据集质量没有可访问的双边预测证据；本轮只证明 iCoDer 工程契约。
- iCoDer 当前关系验证的是“审查集合来自已验证集合”，不证明 Code Validation
  的编码临床正确，也不证明所有支付/DRG/DIP 规则完备。
- 诊断抽取、手术抽取、Medical Coding、DRG/DIP 与 Compliance 之间仍需要
  更完整的版本化编码体系、主次诊断、手术—诊断和分组一致性关系。
- 地方医保政策、收费合规、真实结算接口、医院金标准和独立编码员盲评仍未完成。

## 证据

- `reports/agent_hub/examples_e2e_20260815_compliance_cross_agent/`
- `reports/agent_hub/compliance_typed_replay_final/`
- `reports/agent_hub/compliance_cross_agent_final/`
- `reports/agent_hub/compliance_code_validation_final/`
- `reports/corti_parity/compliance_code_validation_final/`
- `reports/deployment/development_preflight_20260815_compliance_cross_agent_final/`

## 安全与资源回收

所有 Python/后端命令均先移除 `ICODER_CREDENTIAL_LLM` 和
`DEEPSEEK_API_KEY`，并强制 `LLM_PROVIDER=mock`。本轮没有调用真实 LLM、
没有提交 Corti 预测或消耗 credits，也没有加载 Torch、FAISS、
sentence-transformers 或 PyArrow。临时 uvicorn 仅运行新增的确定性
Compliance Agent，完成后按确认的测试 PID 停止，18765 端口已关闭；无关训练
进程未被触碰。
