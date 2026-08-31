# Corti 20 Agent 目录门禁阶段总结（2026-08-15）

> 后续状态更正：Compliance Guardrail—Code Validation 可信链完成后，当前
> 跨 Agent 关系为 4 条、对抗检测 8/8；本文件中的 3 条/6 次是本阶段完成时
> 的历史快照。参见 `AGENT_HUB_COMPLIANCE_CODE_VALIDATION_CHAIN_PHASE_SUMMARY_2026-08-15.md`。

## 阶段结论

本轮把 Corti Console 登录态只读观察到的 20 个 Pre-built Agents，
从人工维护的“20/20 对照表”升级为可自动失败的发布门禁。当前结果为：

- 目录映射：20/20；
- 开发环境验证：20/20；
- 中国场景适配声明：20/20；
- 临床质量验证：0/20，外部门禁；
- 生产就绪验证：0/20，外部门禁。

这里的 20/20 只证明对应 iCoDer Agent 在当前开发仓库中可发现、可执行、
可路由、契约完整、有示例证据、禁止生产写回且声明了中国适配边界。
它不等于 Corti 私有模型质量、托管平台、临床效果或生产 SLA 等价。

## 本轮完成

1. 新增固定目录 `corti_prebuilt_agent_catalog.json`，记录 Corti 名称、稳定 ID、
   一对一 iCoDer Agent、关键输出字段、中国适配标记和逐 Agent 剩余差距。
2. 新增离线校验器 `validate_corti_prebuilt_agent_parity.py`：
   - 固定校验登录态观察到的 20 个名称和顺序，防止静默删项或改名；
   - 禁止两个 Corti Agent 映射到同一个 iCoDer Agent；
   - 复用权威运行矩阵，校验 Hub 可见、executable、Provider 可解析、
     launch candidate、类型/递归 schema、示例、关系、证据绑定和契约注册；
   - 校验关键 Corti 对标输出字段和中国场景标记；
   - 强制临床质量与生产就绪保持 false，并要求明确列出外部门禁。
3. 将该校验接入 `validate_deployment_candidate.py`，目录漂移、Agent 退化、
   关键输出字段丢失或中国适配标记丢失都会阻断开发部署候选。
4. 增加正向与负向测试，覆盖临床/生产误提升、目录身份漂移、重复映射、
   中国适配标记漂移。
5. 修正历史 Gate 5 文档中仍显示“18/20”的时态歧义；保留历史审计，
   同时明确 Clinical Education 与 Clinical Guidelines 已使当前状态达到 20/20。
6. 在操作手册发布步骤中加入新的 20-Agent 门禁。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| Corti 目录映射 | 20/20 |
| iCoDer 开发验证 | 20/20 |
| 中国适配声明 | 20/20 |
| Hub 可见上线候选 | 26/26 |
| Provider Registry / 专用路由 | 21 / 5 |
| 类型契约历史 E2E 重放 | 26/26 |
| 跨字段关系 | 34；对抗检测 59/59 |
| Evidence binding | 15；对抗检测 30/30 |
| 跨 Agent 关系 | 3；对抗检测 6/6 |
| 本轮后端/API/Hub 回归 | 112 passed |
| 新门禁专项 | 4 passed |
| JavaScript SDK | 21/21 |
| Python SDK | 29/29 |
| 前端 | 114/114 + production build |
| 部署静态预检 | 46/46 |

.NET 本机没有 `dotnet`，本轮没有执行，继续保留为 CI 门禁。前端构建只有
既有的动态/静态 import 分块警告，没有构建错误。

## 与 Corti 的当前能力差距

### 开发环境还能继续关闭

- 扩充高价值跨 Agent 语义图，尤其是 Compliance Guardrail、Code Validation、
  诊断/手术抽取、Medical Coding 与 DRG/DIP 之间的一致性关系；
- 建立更多中国专科与地方规则的版本化测试集，包括 ICD-9-CM-3 手术深度、
  医保拒付、预授权和收费合规；
- 完善 Builder、Agent 配置、Event Inspector、成本展示和失败模式的产品 E2E；
- 在安全 Linux/容器环境验证检索 worker、PostgreSQL/Nginx 多实例和故障恢复；
- 使用新的临时凭证和去标识病例生成真实模型稳定性、延迟和成本报告。

### 不能仅在开发机关闭

- 同一批去标识病例上的 Corti/iCoDer 双边预测、盲评和临床金标准；
- 真实 HIS/EMR/FHIR、药库、医保、转诊、护理、ICU 与登记平台集成；
- 医院病案、编码、医保、临床、护理、药学、法务和伦理验收；
- 等保、个保、数据驻留、渗透测试、KMS、灾备、容量、SLA 和独立认证；
- Corti 的全球编码体系、托管 Experts/MCP 生态、语音产品深度、计费与云运维等价。

## 证据

- `reports/corti_parity/corti_prebuilt_agent_parity_round/`
- `reports/agent_hub/corti20_catalog_gate_round/`
- `reports/agent_hub/corti20_typed_replay_round/`
- `reports/agent_hub/corti20_field_relation_round/`
- `reports/agent_hub/corti20_evidence_binding_round/`
- `reports/agent_hub/corti20_cross_agent_round/`
- `reports/deployment/development_preflight_20260815_corti20_catalog/`

## 安全与密钥

本轮每个 Python/后端命令都先移除 `ICODER_CREDENTIAL_LLM` 和
`DEEPSEEK_API_KEY`，并强制 `LLM_PROVIDER=mock`。没有使用真实 LLM Key、
没有提交 Corti 预测、没有消耗 Corti credits，也没有加载已知危险的 Windows
Torch/FAISS/sentence-transformers/PyArrow 原生栈。此前在聊天中明文暴露的
DeepSeek Key 仍应立即注销，不能继续作为测试或生产凭证。
