# CP2 — code-validation-agent 深度走查报告 (Phase 5 Track B-2)

**Agent ID**: `code-validation-agent` (Hub ref `icoder/code-validation-agent@2.0.0`)
**Corti mapping**: `code-validation-agent` (EXACT parity — Corti also has this name)
**Backend provider**: `icoder.llm-with-tools.v1`
**Output schema**: `icoder/CodeValidationOutput/v2` (BREAKING from v1)
**Audit date**: 2026-07-11
**Walkthrough evidence**: 6 screenshots + 5 API envelopes + 1 UI-captured envelope

---

## ⚠ 重大发现 (CRITICAL FINDING)

**`LLMWithToolsProvider` 是 SKELETON（骨架实现）— 没有 wired LLM client，4 个 MCP 工具调用全部走 simulated pipeline。**

证据：
1. latency_ms = 3-8ms（vs 真实 DeepSeek 应 >3000ms）
2. `summary: "LLMWithToolsProvider skeleton: placeholder response (no llm_client wired)."`
3. `raw_provider_response.skeleton: true`
4. `result.markdown` 是固定模板 `# LLMWithToolsProvider — Skeleton Response`
5. 唯一的 tool_call 错误: `"ToolMCPCompatLayer.call requires request — pass it via invoke(..., request=...)"`
6. 后端源码 `backend/icoder_runtime/backends/llm_with_tools_provider.py:106-109, 151-152, 218, 281, 290`

**Since**: Phase 4-A Task 6 (2026-07-07) — 明确 deferred 到"Phase 4-C production"
**Phase 4-C 已 land** (commit `4a18a9c` per memory) 但 production wiring 仍未做
**当前状态**: agent 可以 invoke（不报错），返回 envelope（13 字段齐全），但**输出无临床价值**

## 1. 产品定位

iCoDer code-validation-agent 是**编码校验智能体**。输入病案 + 候选 ICD 编码集，按 ICD-10-CN/ICD-9-CM-3 编码规则校验，输出每码的 verify_code 结果、guidelines 引用、cross-code issues、风险标记、人工复核标志。

是 medical-coding-agent 的**下游伙伴** — 编码 → 校验。

## 2. 目标用户

- 病案编码员（自检）
- 编码审计员（复核）
- DRG 结算员（编码可信度评估）

## 3. 使用场景

| 场景 | 输入 | 期望输出 |
|---|---|---|
| 编码集校验 | 病案 + 候选码 | per-code verify + issues |
| 编码争议解决 | 病案 + 冲突码 | cross-code issues |
| 自动复核 | 多码集 | risk_flags + manual_review |

## 4. Corti 映射

| 维度 | iCoDer | Corti | 一致性 |
|---|---|---|---|
| Agent name | code-validation-agent | code-validation-agent | EXACT |
| Backend | LLMWithTools + 4 MCP tools | LLM + tools (Corti Reverse Engineering confirmed) | EXACT architecture |
| Tools | verify_code / get_guidelines / explore_code / search_codes | 类似 4 工具 (verify/get_guidelines/explore/search) | EXACT 4 工具 |
| Invocation | skeleton placeholder ❌ | real LLM ✓ | ICODER_GAP |

Corti 的 code-validation-agent 真实运行（memory project_phase3_b1_5_partb）。iCoDer v2 是 skeleton。

## 5. Card UI

Hub card 列在 Agents 页（screenshot `01_hub.png`）。
- 名称：编码校验智能体
- 版本：2.0.0
- runnable: true
- Run endpoint 可见

## 6. Detail UI

`04_detail.png` / `05_settings.png` / `06_tools.png` / `07_code.png`：
- 5 个 tab：Overview / Settings / Experts / Tools / Code
- Settings 显示：智能体名称（"编码校验智能体" 7/50）、系统提示词（"点击定义系统提示词"，未编辑）、Experts（"未绑定专家"）、编排策略（LLM 动态规划）、权限策略（医学编码）、置信度阈值（0.6）
- Tools tab：4 个 MCP 工具描述（verify_code / get_guidelines / explore_code / search_codes）
- Code tab：完整 SDK 代码示例
- A2A Agent 协作面板：5 个 agent 列表（MedCodER / 医学编码 / 编码校验 / 合规护栏 / 病历完整性）

## 7. 输入 UI

AgentDetailPage chat box（无独立 page）：
- textarea placeholder "输入问题...（回车发送）"
- 2 个建议提示按钮（"你能做什么？" / "建议提示"）
- "添加上下文" 按钮（DataPart 附件）
- Ctrl/Cmd+Enter 提交

**注意**: placeholder 写"回车发送"，但实际 AgentDetailPage:773 要求 Ctrl+Enter。**GAP-CP2-01 文案不一致**。

## 8. 运行流程

```
POST /api/v1/agents/code-validation-agent/run
↓
backend agent_run.py:run_agent
↓ agent_id NOT in _MEDICAL_CODING_AGENT_IDS
→ ProviderRegistry.resolve_from_agent_pack()
→ backend_provider = "icoder.llm-with-tools.v1"
→ LLMWithToolsProvider.invoke()
↓ if self._llm_client is None (always true at runtime):
  → _skeleton_pipeline (1 simulated tool call + placeholder markdown)
↓ envelope 13 字段 返回 (200 OK, error=false)
```

Latency: **3-8ms** ❌（vs 真实 LLMWithTools 应 >3000ms with multiple tool rounds）

## 9. 输出 UI

`11_skeleton_output.png`：
- Output panel: 渲染 skeleton markdown
- Markdown 模板：`# LLMWithToolsProvider — Skeleton Response\n## User Input (truncated)\n...`
- 显示 1 个 tool_call（verify_code），result=null，error 字符串

## 10. 正常输入（fixture 01 orthopedics）⚠

**Input**: 412 字符 T12 椎体压缩骨折病案
**Run**: `run-ae8b1ccd-055f-41da-abd5-7912c80efad3`, 8ms, runtime_mode=a2a_pure_llm
**Output**: skeleton placeholder（同 §9）
**Verdict**: **NO_REAL_VALIDATION** — agent returned a placeholder, no codes validated, no ICD-10-CN rules checked.

## 11. 长输入（fixture 02 cardiology）⚠

**Input**: 393 字符前壁心梗 + PCI
**Run**: `run-12a936a5-9eaf-4c2f-9c68-6494d5f6668a`, 3ms
**Output**: skeleton placeholder
**Verdict**: **NO_REAL_VALIDATION**

## 12. 缺失信息 ⚠

未单独跑 — 已确认 skeleton 对所有输入返回相同 placeholder（system_prompt_chars + user_input_chars 是仅有的变化字段）。

## 13. 否定与历史 ⚠

未单独跑 — 同 §12。

## 14. 冲突输入 ⚠

未单独跑 — 同 §12。

## 15. 无效输入 ⚠

未单独跑 — skeleton 不区分有效/无效输入，总是返回 placeholder。

## 16. Repeatability ⚠

3 个不同 fixture (01/02/03)，**全部 3-8ms 返回 skeleton placeholder**。100% "consistent" but only because output is hardcoded.

## 17. 配置变化（Fork + modify）

Fork UI 在 detail 页可用，但因 skeleton 状态，fork 后的 agent 仍是 skeleton。无意义测试。

## 18. 错误恢复 ✓

- 不存在的 agent_id：返回 envelope error=true, error_reason=unknown_agent（CP1 已验证）
- 空输入：422 Pydantic 校验（CP1 已验证）
- Skeleton 自身的 tool_call 错误（ToolMCPCompatLayer.call requires request）：被 swallow 到 tool_calls[0].error，不影响 envelope.error=false

## 19. Expert 实证

**配置**: 2 个 expert（LLM With Tools primary + Rule Engine Legacy Fallback）
**实际**: 既未 invoke LLM With Tools，也未触发 Rule Engine fallback。Skeleton 路径完全绕过 expert dispatch。
**Verdict**: **EXPERT_NOT_INVOKED** ❌

## 20. Tool 实证

**配置**: 4 个 MCP 工具（verify_code / get_guidelines / explore_code / search_codes）
**实际**: skeleton 模拟 1 次 `verify_code` 调用，但**返回错误**：
`"ToolMCPCompatLayer.call requires request — pass it via invoke(..., request=...)"`

错误原因：skeleton pipeline 用了旧的 `ToolMCPCompatLayer.call(args)` API，但 Phase 4-C 升级后必须用 `invoke(..., request=request)`。Skeleton 代码未跟随升级。

**Verdict**: **TOOL_INVOCATION_BROKEN** ❌ — 既无真实 LLM tool-calling，skeleton 模拟也 broken。

## 21. Context ✓

每次运行服务端生成 context_id + run_id + trace_id。PHI 边缘脱敏（DataPolicy）。

## 22. Trace ⚠

仅 1 个 trace_event:
```
{step: "completion", status: "ok", duration_ms: 3, metadata: {agent_id, runtime_mode, latency_ms}}
```

无 build_prompt / llm_call / tool_call / parse_response 步骤（因为 skeleton 不走这些）。

## 23. Cost

`cost: {}` — 空 dict。Schematic 表示"未计费"（无 token 消耗因为无真实 LLM call）。
Dev 模式 + skeleton = 永远 0 成本。

## 24. Developer API

API 路径：`POST /api/v1/agents/code-validation-agent/run`（已验证）
Backend provider lookup: `ProviderRegistry.resolve_from_agent_pack()` (Phase 4-A)
Response shape: 13-field `AgentRunResponse` envelope（结构合法）

**但 API 内容无临床价值** — 调用方会拿到一个"成功"的 envelope 但内容是 placeholder。

## 25. Embedded

CP2 **不**做 embedded smoke（PDF §9.2 列出 4 个 embedded-eligible agent，code-validation 不在内）。

## 26. 医院集成路径

| 路径 | 状态 |
|---|---|
| Backend Service Integration | **NOT READY** — 返回 placeholder，无法用于生产校验 |
| ROPC Embedded | N/A |
| Streaming | DEFER |

## 27. UX 评分

12 dimension：

| Dimension | Score | 说明 |
|---|---|---|
| 入口可发现性 | 5 | Hub card + Agents page |
| 输入体验 | 3 | placeholder 文案误导（GAP-CP2-01） |
| 输出可读性 | 2 | skeleton markdown 难看，无临床结构 |
| 错误恢复 | 4 | envelope 结构化 |
| 实时反馈 | 5 | <10ms 响应（虚假快速） |
| Trace 透明度 | 1 | 仅 1 event，无法观测 tool dispatch |
| Cost 透明度 | 5 | 0 成本（因为无 LLM） |
| 复制/下载 | 5 | 全套按钮 |
| 配置可调 | 4 | runtime_mode 下拉 |
| 多轮对话 | 4 | message bubble history |
| 移动响应 | 3 | 双栏堆叠 |
| 国际化 | 4 | 双 locale |

**平均**: 3.75 / 5（虚高 — UX 看起来 OK 但内容无价值）

## 28. 能力分层（5 层）

| 层 | 状态 | 证据 |
|---|---|---|
| PLATFORM_AVAILABLE | ✓ | Hub 列表 |
| AGENT_CONFIGURED | ✓ | agent_pack.json + 2 expert + 4 tool |
| RUNTIME_INVOKED | ✓ | envelope 返回 |
| RESULT_CONSUMED | ✗ | result 是 placeholder，无消费价值 |
| QUALITY_VALIDATED | ✗ | 无法质量评测（skeleton） |

**最高层**: RUNTIME_INVOKED only（B-1 误判为 RESULT_CONSUMED）

## 29. 当前缺口

| ID | Severity | Description |
|---|---|---|
| **GAP-CP2-01** | **P0** | LLMWithToolsProvider skeleton 未 wire LLM client — 整个 agent 无临床输出 |
| **GAP-CP2-02** | **P0** | Skeleton pipeline 中 ToolMCPCompatLayer.call API 升级后未跟随，所有 tool_call 都报错 |
| **GAP-CP2-03** | P1 | LLMWithToolsProvider 无 lazy-resolve gateway fallback（PureLLMProvider 有，LLMWithTools 应镜像） |
| GAP-CP2-04 | P3 | UI placeholder 文案 "回车发送" 与实际 Ctrl+Enter 行为不一致 |
| GAP-CP2-05 | P3 | trace_events 仅 1 步 completion，无法观测 tool dispatch / LLM call |

## 30. 产品重设计建议

| 建议 | 优先级 | 理由 |
|---|---|---|
| **Wire LLMGatewayAdapter into LLMWithToolsProvider** | **P0** | 镜像 PureLLMProvider 的 lazy-resolve 模式 |
| **修复 skeleton ToolMCPCompatLayer.call → invoke** | **P0** | 至少让 skeleton 给出真实的 verify_code 返回（catalog 查表） |
| 暴露 tool_call trace_events | P1 | UI 显示 tool dispatch round + latency + result |
| UI placeholder 改"Ctrl+Enter 发送" | P3 | 修 GAP-CP2-04 |
| 在 Hub card 上加 "skeleton" badge | P4 | 防止用户误以为可用 |

## 31. 是否进入质量评测

**否**。code-validation-agent 当前是 METADATA_ONLY — 配置存在但运行无临床输出。
不进入质量评测基准。

## 32. 最终裁决

# `METADATA_ONLY`

理由：
- Agent 配置齐全（pack + experts + tools + ICD-10-CN catalog）
- API endpoint 工作（envelope 13 字段合法返回）
- **但**实际运行是 skeleton placeholder：
  - 无真实 LLM call（latency 3-8ms 证据）
  - 无真实 tool invocation（tool_call 错误证据）
  - 输出 markdown 是固定模板（vs 真实校验报告）
- 修复路径明确（wire LLMGatewayAdapter + 修复 ToolMCPCompatLayer.invoke），但**不在 CP2 范围**

**B-1 错误修正**: B-1 静态分析误判此 agent 为 RUNTIME_INVOKED + RESULT_CONSUMED。B-2 通过实际运行 + envelope 检查发现是 SKELETON。**这是 B-2 vs B-1 的核心增量价值**。

**Next**: CP3 compliance-guardrail-agent

---

## 附录：证据清单

| 类别 | 文件 |
|---|---|
| Screenshots | `screenshots/phase5_track_b2/code-validation-agent/*.png` (6 张) |
| Run envelopes | `outputs/phase5_track_b2/per_agent_runs/code-validation-agent/*.json` (6 个) |
| Fixture | `fixtures/phase5_track_b2/01_orthopedics.json` 等 |
| Backend code | `backend/icoder_runtime/backends/llm_with_tools_provider.py:106-109` (skeleton check), `:218` (_skeleton_pipeline), `:281` (placeholder summary) |
| Backend wiring | `backend/icoder_runtime/backends/registry.py:397` (LLMWithToolsProvider() no args) |
| Agent pack | `backend/official_agents/code-validation/agent_pack.json` |
| Deferred since | Phase 4-A Task 6 (2026-07-07) — memory `project_phase4_a_agent_backend_provider_foundation_2026_07_07.md` |
