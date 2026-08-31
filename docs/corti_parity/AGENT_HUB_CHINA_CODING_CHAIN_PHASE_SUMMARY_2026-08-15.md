# Agent Hub 中国编码可信主链阶段总结（2026-08-15）

## 阶段结论

本轮把诊断/手术抽取、主诊断复核、Medical Coding、Code Validation、
Compliance Guardrail 和 DRG/DIP Risk Review 从若干相邻 Agent 收敛为一条
可由机器验证、可签名传递、可构造冲突反例的中国编码可信主链。

这证明了“下游使用的编码来自哪个已认证上游结果”，不证明编码临床正确、
地方医保规则完整或与 Corti 的临床质量等价。所有可见 Agent 继续保持
`production_ready=false` 和人工复核门禁。

## 本轮完成

1. Medical Coding 公共契约升至
   `icoder/MedicalCodingAgentOutputV2/v7`：
   - 主诊断编码必须属于 Principal Diagnosis Review 候选；
   - 其他诊断编码必须是 Diagnosis Extractor 已提取编码的子集；
   - 手术操作编码必须是 Procedure Extractor 已执行操作编码的子集；
   - 其他诊断或手术数组为空时可显式通过，不把“本例无此类编码”误判为冲突。
2. Code Validation 公共契约升至 `icoder/CodeValidationOutput/v6`：
   - 新增受控 `local_items_subset_upstream_values` 运算符；
   - 它将 Medical Coding 的主诊断标量、其他诊断数组和手术数组合并成一个
     只读上游编码集合；
   - `validated_codes[].code` 必须来自该集合。
3. DRG/DIP Risk Review 公共契约升至 `icoder/DRGDIPRiskReview/v3`：
   - `risk_points[].code` 必须是 Compliance Guardrail 已审查编码的子集；
   - 无风险点时允许空集合，避免为了满足关系而伪造风险。
4. 关系 DSL 新增多来源集合并集和 `allow_empty_local`，定义层限制最多 8 个
   上游来源，路径仍只允许声明式字段路径，错误仍只公开路径、稳定关系 ID
   和抽象原因，不回显患者值。
5. 三个新 schema_ref 以追加方式登记；不可变注册表当前 99 个历史引用，旧版
   没有被覆盖。
6. 新增统一 Run HTTP 正反测试：4 条主链边界各包含一个匹配成功和一个冲突
   失败关闭案例；全部上游结果都使用租户、Run、Agent、Schema 和完整结果摘要
   绑定的 HMAC 证明。
7. 扩大回归发现并关闭两个既有专用 A2A 阻断：
   - Code Validation/Compliance/Note Completeness 的 A2A schema_ref 改为从
     当前 Pack 读取，不再硬编码历史版本；
   - Note Completeness 确定性降级路径显式返回空的 `incomplete_sections`、
     `conflicts` 和 `corrected_draft`，不把未评估内容伪造成临床发现；
   - 三个专用 Agent 的 discovery 卡片也从当前 Pack 读取 schema_ref、版本、
     必填字段和成熟度。

## 可验证主链

```text
Diagnosis Extractor ──> Principal Diagnosis Review ──┐
        │                                             │
        └────────────> Medical Coding <──── Procedure Extractor
                              │
                              v
                       Code Validation
                              │
                              v
                    Compliance Guardrail
                              │
                              v
                    DRG/DIP Risk Review
```

当前 6 个 Agent 共声明 8 条跨 Agent 关系。关系保持 optional，单 Agent 仍可独立
运行；一旦调用方提供上游结果，就必须通过证明校验、唯一性检查和关系校验。

## 验证结果

| 门禁 | 结果 |
|---|---:|
| Hub 可见上线候选 | 26/26 |
| 当前契约/类型重放 | 26/26 |
| 跨字段关系 | 34；59/59 对抗检测 |
| Evidence binding | 15；30/30 对抗检测 |
| 跨 Agent 关系 | 8；16/16 冲突/歧义检测 |
| 签名上游统一 Run HTTP 正反测试 | 8/8 |
| 后端/API/Hub/Agent runtime 扩大回归 | 572 passed |
| JavaScript SDK | 21/21 |
| Python SDK | 29/29 |
| 前端 | 114/114 + production build |
| Corti 20-Agent 开发目录门禁 | 20/20 |
| 中国适配声明门禁 | 20/20 |
| Corti 同数据集临床质量 | 0/20 |
| 生产就绪外部门禁 | 0/20 |
| 部署静态预检 | 46/46 |

26-Agent 组合 E2E 使用上一阶段 26 个未修改的成功 HTTP 响应，并对当前 Pack
重新计算所有契约门禁；响应文件没有改写。新增关系的真实 HTTP 边界证据来自
8 个 FastAPI TestClient 正反案例。该轮没有启动真实 Provider，也没有把缓存
响应描述成新模型实跑，来源记录见 `evidence_provenance.json`。

.NET 因本机没有 `dotnet` 未执行，继续由 CI 的双目标门禁承担。前端构建只有
既有静态/动态 import 分块警告，无编译或构建错误。

## 与 Corti 的能力差距

### 本轮已缩小

- 编码工作流不再只是多个独立 Agent：主次诊断、手术、编码校验、合规审查和
  DRG/DIP 风险码之间有运行时可证明的数据血缘。
- 中国 ICD-10-CN / ICD-9-CM-3 角色区分、人工复核、禁止自动写回和
  DRG/DIP 风险预留继续作为 Pack 级硬约束。
- 签名上游、防篡改、重复上游歧义和 PHI-safe 失败元数据超过了单纯 UI
  目录对齐，具备工程审计价值。

### 仍未关闭

- 没有 Corti 与 iCoDer 在同一去标识金标准数据集上的双边预测、盲评、准确率、
  召回率、一致性和错误严重度证据；临床质量仍为 0/20。
- DRG/DIP Agent 仍是风险复核，不是经授权规则库驱动的真实分组器；缺各省/市
  版本、有效期、政策来源、回滚、费用清单和结算联调。
- 缺合法授权且版本冻结的 ICD/手术/医保目录，以及医院编码员和临床专家的
  独立复核。
- 缺真实 HIS/EMR/病案首页/医保接口、生产 PostgreSQL/队列/对象存储、并发与
  长稳、灾备、监控告警、等保/隐私/法务和医院验收。
- Windows 本机原生 Torch/FAISS 检索仍因已知访问冲突禁用；生产方案需要隔离
  Linux 检索服务和经验证资产，而不是在当前桌面进程中放开。
- Corti 托管 SLA、规则治理、真实支付方覆盖和同场景输出质量仍不可由开发
  环境或控制台只读观察证明。

## 证据

- `reports/agent_hub/examples_e2e_20260815_china_coding_chain/`
- `reports/agent_hub/cross_agent_replay_20260815_china_coding_chain/`
- `reports/agent_hub/field_relations_20260815_china_coding_chain/`
- `reports/agent_hub/evidence_bindings_20260815_china_coding_chain/`
- `reports/agent_hub/typed_contracts_20260815_china_coding_chain/`
- `reports/agent_hub/runtime_matrix_20260815_china_coding_chain/`
- `reports/corti_parity/china_coding_chain_20260815/`
- `reports/deployment/development_preflight_20260815_china_coding_chain/`

## 安全与资源回收

所有 Python/后端命令均先移除 `ICODER_CREDENTIAL_LLM` 和
`DEEPSEEK_API_KEY`，并强制 `LLM_PROVIDER=mock`。没有使用用户曾暴露的真实
LLM 密钥、没有调用真实 LLM、没有提交 Corti 预测或消耗 credits，也没有加载
Torch、FAISS、sentence-transformers 或 PyArrow。未启动临时 uvicorn，18765
端口保持关闭；无关 Python 训练进程 PID 1804 保持运行且未被触碰。
