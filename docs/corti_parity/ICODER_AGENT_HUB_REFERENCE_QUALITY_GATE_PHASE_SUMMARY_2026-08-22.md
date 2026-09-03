# iCoDer Agent Hub 26-Agent 参考质量门禁阶段总结（2026-08-22）

## 结论

本阶段关闭了“26 个 Agent 只有结构、安全和稳定性门禁，没有逐 Agent 语义判别基线”的开发环境缺口。当前每个 Hub 可见 Agent 都有且仅有一个 Pack 自有合成参考案例、至少三个断言和至少一个语义判别项；26/26 当前参考输出全部通过。该基线明确不是独立临床金标准、不是 Corti 私有模型质量，也不证明生产准确率。

相关宽矩阵最终为 **718 passed、5 skipped、0 failed、194 warnings**；26-Agent 运行矩阵为 **26/26 launch-candidate-ready**；部署候选静态预检由 76 项增至 **77/77**。本阶段未启动独立后端、未调用外部 LLM/ASR、未加载 Windows 原生 MedCodER。

## 本阶段完成的工程工作

1. 新增 `agent_hub_reference_quality_cases.json`，精确覆盖 26 个可见 Agent。断言只针对 Pack 合成输入中可验证的直接事实、治理常量和安全结论，scope 固定为 `pack_owned_synthetic_reference_semantics_not_independent_clinical_gold`。
2. 新增离线回放器 `run_agent_hub_reference_quality_replay.py`。它复用既有契约/安全评价，再执行参考断言；报告不复制响应正文或实际断言值，只保留 SHA-256、类型、非空状态和通过结果。
3. 来源 E2E 报告必须证明 26/26 成功、0 失败、逐行 evaluation 通过、Agent ID 唯一且与当前可见 Pack 完全一致，否则回放拒绝。
4. Evidence Extractor 现在要求 `extra.codes` 在 supported/uncertain/rejected 三组中形成逐字保留、一一完整且无新增/遗漏/重复的分区。示例不再把未输入的 `M81.0` 替换进结果，而是保留输入的 `M80.900` 并提示人工确认当前骨折因果关系。
5. Surgical Registry 现在把明确“全麻”作为麻醉直接事实，把“无胆管损伤”作为有来源的阴性并发症事实；`missing_fields` 只允许完全无来源字段，非空字段必须有同名 `evidence_spans` 引用。
6. Surgical Registry 的稀疏证据映射已发布不可变 `icoder/SurgicalRegistryOutput/v4`；七类登记字段均为允许的证据键且不被单一样例误推断为普遍必填。v1–v3 历史合同保持不变，当前注册表共 103 个引用。
7. 历史真实响应同步器新增语义门禁和原子写入。结构/安全已通过但不满足当前参考语义的旧响应会使整个同步失败，任何 Pack 都不会被部分覆盖；历史 E2E 不能再回灌已确认的语义错误。
8. 健康检查测试不再与本机 `.env` 的可配置应用名冲突；真实 Uvicorn 子进程显式使用临时 SQLite 和固定测试名称，避免触碰开发数据库。

## 历史真实响应回放

对 2026-08-15 的 26 条真实 Provider 快乐路径响应执行当前离线语义回放，结果为 **22/26 通过、4/26 失败**。原始来源报告自身为 26/26 契约/安全通过；以下差异因此是“旧响应与当前语义基线不一致”，不是传输失败：

| Agent | 当前回放差异 | 当前处置 |
|---|---|---|
| Diagnosis Extractor | 旧响应使用历史状态 `completed`，当前合同要求 `PASS` | 当前 Pack/合同已升级；需新模型实跑确认 |
| DRG Analyzer | 旧响应早于 `experimental_unverified` 与 `billing_authoritative=false` 治理字段 | 当前合同已确定性强制；需新模型实跑确认 |
| Evidence Extractor | 输入候选为 `S22.000/M80.900`，旧响应擅自输出 `M81.0` | 示例、提示词和同步门禁已修正 |
| Surgical Registry | 输入明确含“全麻/无胆管损伤”，旧响应把麻醉与并发症留空 | 示例、提示词及 v4 稀疏证据合同已修正 |

机器报告位于 `reports/agent_hub/reference_quality_replay_20260822_historical_real_20260815/`。该 22/26 只能标记为历史离线回放，不能写成当前模型成功率。当前 26-Agent Provider 语义结果仍需要轮换后的新临时凭证重新捕获。

## 验证结果

| 验证 | 结果 |
|---|---:|
| 新参考门禁、Pack loader、可见契约回环 | 62 passed |
| 来源防伪、递归 schema、同步原子性、部署预检定向 | 14 passed |
| 健康检查、真实 Uvicorn 临时库启动 | 3 passed |
| Agent Hub/runtime/A2A/Provider/契约相关宽矩阵 | 718 passed、5 skipped、0 failed |
| 26-Agent 运行矩阵 | 26/26 ready，0 blocker |
| 不可变合同注册 | 26/26 当前引用匹配，103 个历史引用 |
| 静态部署候选预检 | 77/77 |
| 历史真实响应参考回放 | 22/26；4 项差距保留 |

完整默认后端测试集首次在 213 passed、4 skipped 后暴露应用名称测试与本机 `.env` 冲突；该问题修复并定向通过。由于默认集合约含数千项且本阶段变更集中于 Agent Hub/契约/回放，最终权威结果采用上述 718 项相关宽矩阵，而不是把中途停止的全库运行计为通过。

## 对 Corti 的能力差距

本阶段把 iCoDer 从“只有 schema/安全通过”推进到“每个可见 Agent 都有可自动判别的 Pack 语义基线”，并能防止旧 Provider 输出覆盖修订后的参考真值。这提高了开发环境的可审计性和回归质量，但没有取得 Corti 私有模型、提示词、临床数据或临床准确率证据。

仍未关闭：

- 使用同一去标识病例集、相同输入与一致评分标准的 Corti/iCoDer 双边盲测；
- 独立临床编码员、CDI、外科、护理、药学和急诊专家金标准；
- 中国医院真实 ICD-10-CN、ICD-9-CM-3、CHS-DRG/DIP 版本与本地规则验证；
- 真实 Provider 的 26-Agent 快乐/对抗/重复稳定性、P50/P95、费用和失败归因；
- 医院互操作、生产云、KMS/Secret Manager、PostgreSQL 多副本、容量/SLA、渗透、法务、许可、认证和独立 reviewer 门禁。

因此所有用户可见 Agent 继续保持 `production_ready=false`。当前结论是开发上线候选，不是临床生产批准，也不是“完整复刻 Corti”完成声明。

## 下一步

使用从未在聊天、日志或版本库暴露的新临时 DeepSeek 凭证，在独立可见 PowerShell、临时 SQLite、随机 loopback 端口中依次运行 26-Agent 快乐、对抗、两轮稳定性和参考语义回放。运行手册见 `AGENT_HUB_STABILITY_BENCHMARK.md`。完成后必须停止精确进程、清除进程环境变量并在 Provider 控制台撤销临时凭证。
