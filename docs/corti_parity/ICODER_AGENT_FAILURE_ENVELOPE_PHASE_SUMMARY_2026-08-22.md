# iCoDer Agent 失败封装与证据分轴阶段总结（2026-08-22）

## 阶段结论

本阶段关闭了一个会造成临床误导的 P0：Agent Provider 或输出合同失败时，后端不再发布任何投影后的临床域默认值，统一只返回 `contract_output_suppressed=true`、稳定错误原因并强制人工复核；Medical Coding 页面也不会再从顶层失败响应缺失的复核字段推导 `PASS`。

26 个用户可见 Agent 已在隔离临时 SQLite、空 LLM 凭据、mock provider 的真实 TCP 服务上完成示例与对抗两套矩阵。两套结果均为：1 个确定性能力通过、25 个依赖模型的入口安全失败关闭、0 个不安全或无效响应。runner 仍以“能力通过”决定退出码，因此两次命令按预期返回非零；安全失败没有被冒充为模型能力成功。

## 发现与整改

修复前有两条危险路径：

1. `clinical-documentation-improvement-agent` 在 Provider 不可用时可能返回 `error=true`，但没有强制 `manual_review_required=true`。
2. `medical-coding-agent` 在 schema/Provider 失败时可能把投影默认值发布到 `result`，其中包括 `validation_summary.passed=true` 和 `human_review.review_conclusion=PASS`。

当前整改：

- 统一 Run 的所有通用错误响应只发布 `{ "contract_output_suppressed": true }`，清空公开 evidence、warnings 和 markdown，并强制人工复核。
- Medical Coding 专用运行时在 projection error、Provider error 和 degraded 路径同样抑制全部临床域输出。
- E2E evaluator 将 `capability_passed`、`safe_fail_closed`、`unsafe_or_invalid` 分开统计；对抗矩阵另保留 `semantic_capability_passed`，fail-closed 不计入语义能力。
- fail-closed 必须同时满足 HTTP 合同、顶层错误、稳定原因、显式抑制、只含失败元数据、无公开 markdown/evidence、人工复核、安全/grounding 以及 Run/Trace ID。
- 前端以顶层 `error` 为发布边界；失败 envelope 即使携带恶意或旧版嵌套 `PASS`，也不渲染复核结论卡片。
- 静态部署预检新增失败输出、证据分轴和前端失败优先检查，当前 55/55。

## 端到端证据

隔离服务：`127.0.0.1:18022`，临时 SQLite，`LLM_PROVIDER=mock`，`ICODER_CREDENTIAL_LLM` 为空，`ICODER_ALLOW_EXTERNAL_LLM=false`，`ICODER_DISABLE_NATIVE_MEDCODER=true`。服务已按精确 PID 停止，端口不再监听。

| 矩阵 | 完成 | 能力通过 | 安全失败关闭 | 不安全/无效 |
|---|---:|---:|---:|---:|
| Agent 示例 | 26/26 | 1 | 25 | 0 |
| Agent 对抗 | 26/26 | 1 | 25 | 0 |

隔离后台日志中 FAISS loader、Torch、PyArrow 导入计数均为 0；`operator_disabled_native_medcoder` 出现 2 次，符合显式禁用策略。报告位于 [`mock_failure_envelope_e2e_20260822`](../../reports/agent_hub/mock_failure_envelope_e2e_20260822/)。

## 回归结果

- 当前 Pack 矩阵重建：32 packs、26 个 Hub 可见、6 个隐藏；26/26 executable、provider-resolvable、launch-candidate-ready，5 个隐藏 metadata-only Pack 未被冒充为用户能力。
- 后端联合专项：125/125 passed。
- 前端 Vitest：23 files、137/137 passed。
- 前端 TypeScript + Vite production build：通过，1703 modules transformed。
- 静态部署候选预检：55/55 passed；本机无 Docker，因此该预检不等于镜像构建、扫描或云部署证明。
- OpenAPI 响应结构未增加或删除字段，本阶段只收紧既有 `result` 字典的错误语义，因此无需变更 OpenAPI schema。

## 真实模型证据边界

历史 2026-08-13 的 26 条 DeepSeek 对抗响应按当前合同离线重放后只有 10/26 完整通过；26/26 场景语义断言和注入 canary 检查仍通过，但 16 条存在当前 schema 漂移。这批缓存不能证明当前发布候选的真实模型质量。

本阶段没有读取或调用用户的真实 DeepSeek 密钥。当前仍缺使用轮换后新凭据、明确预算生成的 26-Agent 快乐/对抗/重复真实模型矩阵，以及 P50/P95、成本、合同和独立临床质量证据。此前在对话中暴露过的旧密钥仍应注销/轮换。

## 保留的门禁

- 当前开发数据库仍是历史 `041`/`create_all` 混合状态；本阶段没有迁移、重启或修改该库。
- 因本机浏览器曾造成内存崩溃，本阶段没有强行启动 Chromium；Corti 对照继续使用 2026-08-21 已访问/公开证据。
- Docker、Linux 原生 MedCodER、.NET 双框架、PostgreSQL 多副本、云 Secret Manager、镜像/SBOM/漏洞扫描仍需对应环境。
- 真实医院互操作、合法中国编码/DRG-DIP 规则、患者 PHI 权威 consent、商业 Provider 许可、法务/等保/认证、独立临床 reviewer 和生产运维验收仍未通过。

机器可核验证据位于 [`agent_failure_envelope_phase_20260822/phase_evidence.json`](../../reports/agent_hub/agent_failure_envelope_phase_20260822/phase_evidence.json)。
