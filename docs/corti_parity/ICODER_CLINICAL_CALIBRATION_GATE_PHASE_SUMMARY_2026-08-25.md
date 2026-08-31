# iCoDer CDI / Medical Coding 多病例校准门禁阶段总结（2026-08-25）

## 阶段结论

CDI 与 Medical Coding 已具备可在开发机上安全执行的受治理多病例真实模型门禁，但本轮没有新的临时 DeepSeek Key，因此只完成 runner、数据边界、评分、证据绑定和部署模拟，未产生新的模型质量结果。当前真实执行为 **0/50**，严格 26-Agent live-provider 语义仍为 **0/26**，临床质量、医院验收和生产就绪仍为 **0/26**。

## 已完成的工程能力

- 新增 `build_agent_hub_clinical_calibration_plan.py`，对 CDI 40、双语编码 5、CCL 1,800/201/100 及历史 CDI rc5 证据逐项盘点、哈希和分级。
- 允许的受控外发范围只有：40 条元数据声明无姓名/ID/电话/地址的 CDI 校准病例，以及 5 条明确 synthetic、PHI-free 的编码病例各跑中文和英文，共 **50 次串行调用**。
- CCL 1,800、validation 100、iCoDer 201 全部固定为 `external_provider_egress_allowed=false`；原因是商用/外部处理许可、来源独立核验和脱敏证书缺失，并且三者属于同一训练数据单一来源。
- 新增 `run_agent_hub_clinical_calibration_e2e.py`，仅允许 loopback 应用传输且要求显式确认外部 Provider egress；每条调用立即保存响应与 Trace，强制当前 Agent Pack、合同/安全、结果签名、Trace 签名、真实 provider/model、非 mock 和非降级。
- CDI 评分对最终公开 Query 再次调用当前 `evaluate_single_dimension`，因此可发现实际泄漏；不再相信历史 runner 中 `multi_dim_slipped = 0` 的硬编码结果。同时计算 query 数量范围、完整病历过问、清晰缺口漏问、逐字证据、四选项、escape hatch 和 NLQ gate。
- Medical Coding 对 5×2 输出计算严格 ICD-10-CN/ICD-9-CM-3 主诊断、次诊断集合、主要手术、逐字证据和中英代码集合一致性；所有结果继续要求人工复核。
- 报告把执行证据和质量结果分轴：50 条均有真实签名模型 Trace 才能 `execution_valid=true`；质量阈值不足则保留 `failed_targets`，发布脚本先写报告再失败退出。
- 严格 26-Agent PowerShell runner 新增 `-IncludeClinicalCalibration`，仍使用一次性 Key、临时 SQLite、隐藏 Uvicorn、泄漏扫描、精确进程/目录清理，并显式保留 `independent_clinical_gold_used=false`、`production_ready_proven=false`。

## 验证结果

- 聚焦语义 bundle、治理计划、校准评分/防篡改、部署预检：**24/24 passed**，40.68 秒。
- 26 个可见 Agent 离线示例/对抗安全矩阵：**78/78 passed**，27.06 秒。
- PowerShell AST：**0 errors**。
- 校准 runner 缺外发确认：在任何 HTTP/模型调用前失败。
- 部署静态预检：**92/92 passed**。
- 没有加载 Native MedCodER 或本地 STT，没有调用真实 LLM，没有修改受保护数据库。

机器证据：

- `reports/agent_hub/clinical_calibration_plan_20260825_v1/agent_hub_clinical_calibration_plan.json`
- `reports/deployment/clinical_calibration_gate_phase_20260825_v1/deployment_preflight.json`

## 历史基准审计结论

`reports/track_h/h4_benchmark_candidate_rc5` 的 40-case CDI 快照仍通过文件完整性校验，但只代表 2026-07-13 的合成教师校准：对 Corti query-count agreement 0.75、平均绝对差 1.0。重新按 fixture 允许区间审计后，真正越界的是 3 例：GAP-004 少 1 条、GAP-008 与 CONFLICT-032 各多 1 条；INSUF-025、NEG-027、LAB-036/037/038、CONFLICT-035 均在各自允许区间内，不能继续表述为“结构性欠问”。当前确定性门控已覆盖这 3 条历史路径，并增加 GAP-004 精确回归；但这只证明离线结构修复，仍须用新的真实模型 40 例校准验证。旧 runner 还存在固定开发登录凭据、绕过统一 Agent Hub endpoint、缺真实模型 Trace attestation、把多维 Query 泄漏直接写成 0 四项证据缺陷。因此它只能用于历史回归，不能作为当前发布质量证据。

## 对 Corti 的当前能力差距

Corti 当前 [Medical Coding Agent](https://corti.ai/agents/medical-coding-icd-10-cpt-agent) 公开覆盖单次就诊综合、逐字证据、ICD-10-CM 与 CPT/HCPCS 分配、顺序/modifier 校验、缺口和不可编码项；[Medical Coding 产品](https://corti.ai/medical-coding)还公开 ranked alternatives、规则理由、全球代码体系、审计轨迹与 API。iCoDer 当前中国编码合同和受治理校准 runner 已具备，但只有 5 条工程团队合成双语 seed，尚无 ≥100 条独立双语 gold、CPT/HCPCS/PCS 等全球覆盖、持续权威规则更新或医院分布质量证据。

Corti [CDI Outpatient 文档](https://docs.corti.ai/get_started/cdi-outpatient)公开支持实时、近实时和批处理，输入可为 transcript、结构化事实、草稿或终稿，并组合 Coding、Web Search、Clinical Reference/Calculator 等 Expert 生成有证据、非诱导的 query。iCoDer 已有证据 span、single-dimension/NLQ/necessity/claim-evidence gate、生命周期和人工审核，但历史 40-case 只达到 0.75 query-count agreement，且新的 50 次真实模型校准尚未执行；医院触发、来源许可和独立 CDI reviewer 仍是外部门禁。

## 下一步与外部门禁

开发机上的下一步是在用户可见 PowerShell 中设置一枚新的临时 Key，然后按操作手册启用 `-IncludeClinicalCalibration`。执行后按 `failed_targets` 逐项修复 CDI 欠问、编码精确度、证据锚定或双语一致性，并重新跑完整 50 条，不能只挑通过病例。

即使 50/50 达标，仍需：把双语编码集扩展到至少 100 条；由独立中英双语临床编码员盲评和裁决；在获批 DPA/数据处理范围下完成医院分布验证；取得数据许可/来源/脱敏证明；用同一获批输入做 Corti head-to-head；完成医院验收、云容量/SLA、法务、等保/监管和认证。
