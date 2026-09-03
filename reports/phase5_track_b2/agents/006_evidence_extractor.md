# CP6 — evidence-extractor 深度走查报告 (Phase 5 Track B-2)

**Agent ID**: `evidence-extractor` (Hub ref `icoder/evidence-extractor@1.0.0`)
**Corti mapping**: `CORTI_BUNDLED_EQUIVALENT` (Corti 将 evidence anchoring 内嵌于 coding agent；iCoDer 拆分为独立 agent — Phase 5+ 路线建议转为 orchestrator 子 agent)
**Backend provider**: `icoder.pure-llm.v1` (PureLLMProvider — no tools)
**Output schema**: `icoder/CodingEvidenceOutput/v1` (coded_evidence + uncoded_findings + review_summary)
**Audit date**: 2026-07-11
**Walkthrough evidence**: 1 screenshot + 8 API envelopes + 1 embedded smoke log

---

## 关键发现

**evidence-extractor 真实运行 PureLLMProvider — 给定编码集，per-code 输出 evidence_text + char_span + evidence_strength + confidence，跨 4 个 fixture 全部 direct evidence + confidence ≥ 0.88：**

- **真实 LLM 调用**（latency 5.5-6.7s, cost ¥0.000218-0.000361）
- **per-code 评估准确**：fixture 09 (7 编码) 全部 direct + confidence 0.88-0.95
- **Chinese-native ICD-10-CN**：识别 `I10.x00` 6 位细分码并定位原文证据
- **同 CP4/CP5 P1 gap**：unified API 不解析 JSON-in-markdown 到 result.coded_evidence 结构化字段
- **vs CP5**：CP5 procedure-extractor 输出"编码集 + evidence"，CP6 evidence-extractor 输入"已有编码集"输出"per-code evidence 评估"——两 agent 是互补关系，**Phase 5+ 应通过 orchestrator 串联**（medical-coding → evidence-extractor → compliance-guardrail）

## 1. 产品定位

iCoDer evidence-extractor 是**编码证据定位智能体**。给定病历文本 + 已有编码集（≤20 codes），为每个编码：
1. 定位原文 evidence_text + char_span
2. 评估证据强度（direct / indirect / negated / none）
3. 输出 confidence（direct≥0.7, indirect 0.4-0.7, negated<0.3）
4. 否定发现必须显式输出

不分配新编码，仅评估已有编码。是 medical-coding-agent 的**质控下游** + compliance-guardrail 的**证据上游**。

## 2. 目标用户

- 编码质控员（每码 evidence 审核）
- DRG 结算合规员（high-cost 编码 evidence 强度验证）
- 临床编码审计（追溯编码依据）

## 3. 使用场景

| 场景 | 输入 | 期望输出 |
|---|---|---|
| Per-code evidence | 病历 + 编码集 | coded_evidence[] |
| Upcoding 检测 | 病历 + 高补偿码 | negated/indirect findings |
| 缺漏编码发现 | 病历 + 编码集 | uncoded_findings[] |

## 4. Corti 映射

| 维度 | iCoDer | Corti | 一致性 |
|---|---|---|---|
| Agent name | evidence-extractor (独立) | 内嵌于 medical-coding-icd-10-cpt-agent | DIFFERENT (iCoDer 拆分, Corti 合并) |
| Backend | PureLLMProvider | LLM 内嵌 | similar |
| Per-code evidence | ✓ 独立输出 | ✓ 内嵌于 coding 输出 | similar |
| Evidence strength (direct/indirect/negated) | ✓ 显式 | ✓ Corti 也有 strength 字段 | EXACT concept |
| char_span | ✓ 字符位置 | ✓ Corti 也有 char offset | EXACT |
| uncoded_findings | ✓ iCoDer 独有 | ✗ Corti 无 | ICODER_ADVANTAGE |

iCoDer 优势：**独立 evidence-extractor agent 可被多 agent 复用**（medical-coding / DRG-DIP / compliance），Corti 内嵌于 coding agent 不可复用。

但 **architecture gap**：iCoDer 当前 evidence-extractor 是独立 agent，**没有 orchestrator 串联** medical-coding → evidence-extractor → compliance。Phase 5+ 应补 orchestrator。

## 5. Card UI

Hub 卡片在 `/ai-studio/agents` → 浏览预置：
- 名称：证据提取智能体
- 版本：1.0.0
- maturity: mvp
- human_review: required

## 6. Detail UI

`04_detail.png`：
- 5 个 tab（Overview / Settings / Experts / Tools / Code）
- 1 个 expert（Evidence Extractor primary）
- 0 个 tools（PureLLM 无 tool_calling）
- backend_provider 显示 icoder.pure-llm.v1

## 7. 输入 UI

AgentDetailPage chat box。
**重要**：input 应含 (text + codes)，建议格式：
```
{emr_text}
---
待评估编码集:
- S22.000
- M80.900
- I10.x00
```

或通过 `input.extra.codes = ["S22.000", ...]` 传递。

## 8. 运行流程

```
POST /api/v1/agents/evidence-extractor/run
↓
agent_run.py:run_agent
↓ agent_id NOT in _MEDICAL_CODING_AGENT_IDS
→ ProviderRegistry → PureLLMProvider.invoke
→ DeepSeek chat completion (temperature=0.0, max_tokens=4096)
→ markdown 内嵌 JSON（coded_evidence + uncoded_findings + review_summary）
↓ envelope 13 字段
```

Latency: **5.5-6.7s** ✓

## 9. 输出 UI

MessageBubble 渲染 markdown（JSON code block）。
coded_evidence 数组 + uncoded_findings 数组 + review_summary 字符串。

## 10. 正常输入（fixture 01 orthopedics + 3 gold codes）✓

**Input**: 病历 412 字 + 3 gold codes (S22.000 / M80.900 / I10.x00)
**Run**: `run-5145e59a-aeb0-4820-b99e-bf3dbf21283f`, latency 6.3s, cost ¥0.000218
**Output JSON**:
```json
{
  "coded_evidence": [
    {"code":"S22.000", "evidence_text":"MRI 显示 T12 椎体压缩性骨折", "evidence_strength":"direct", "char_span":[218,237], "confidence":0.95},
    {"code":"M80.900", "evidence_text":"骨密度 T 值 -3.2(骨质疏松)", "evidence_strength":"direct", "char_span":[238,256], "confidence":0.93},
    {"code":"I10.x00", ...}
  ]
}
```

**Verdict**: ✓ 3/3 codes direct evidence + confidence ≥ 0.91 + char_span 准确

## 11. 长输入（fixture 02 cardiology + 4 gold codes）✓

**Run**: `run-702f8bb8-c233-4ca7-9e72-e54f3b0beda6`, latency 6.7s, cost ¥0.000229
**Output**: 4 codes 全部 direct + confidence 0.88-0.95
- I21.001 急性前壁 STEMI — 0.95
- I25.100 冠状动脉单支病变 — 0.90
- Z95.500 PCI 术后状态 — 0.93/0.88

**Verdict**: ✓ 心血管复杂 case 全部 evidence 准确

## 12. fixture 03 respiratory + 4 codes ✓

**Run**: latency 5.5s, cost ¥0.000252
**Output**: 4 codes 全 direct, confidence 0.92-0.95（J44.100 / J18.900 / J96.000 / J90）

## 13. fixture 09 complex comorbidity + 7 codes ✓

**Run**: `run-f7f6f194-deb2-4af4-8e83-a9eaab44b893`, latency 6.6s, cost ¥0.000361
**Output**: 7 codes 全 direct, confidence 0.88-0.95（I50.900 / I25.100 / Z95.500 / E11.900 / E78.500 / N18.900 / I10.x00）
**Verdict**: ✓ 多病共存 7 编码全 evidence 准确

## 14. 冲突输入

未单独跑（fixture 11 走 medical-coding 已验证冲突）。

## 15. 无效输入（17 invalid）✓

**Input**: "今天天气不错。"
**Run**: latency 2.3s, cost ¥0.000068
**Verdict**: ✓ fail-soft LLM 引导

## 16. Repeatability ⚠

**3 次同输入（fixture 01 + 3 codes）**:
- run 1: 4.7s, md_hash=80aee178d5080e8c, md_len=1074
- run 2: 5.0s, md_hash=33cdd262b7d36bd8, md_len=1081
- run 3: 5.0s, md_hash=ccae042c904bb833, md_len=1096

3 次 hash 不同但 md_len 接近（差 22 字符）—— 比 CP4 (md_len 1545-1946 差 400) 更稳定。**GAP-CP6-01 (P2)** 同 GAP-CP4-02 但 severity 较低。

## 17. 配置变化

Fork UI 可用，未单独测试。

## 18. 错误恢复 ✓

- 不存在 agent: envelope.error=true, error_reason=unknown_agent
- 空输入: 422 Pydantic
- 无效文本: LLM 引导

## 19. Expert 实证 ✓

**配置**: 1 expert（Evidence Extractor primary）
**实际**: PureLLMProvider 真实调用 LLM 完成 per-code evidence 任务
**Verdict**: **EXPERT_INVOKED (LLM-level)** ✓

## 20. Tool 实证

**配置**: 0 tools（PureLLM 无 tool_calling）
**Verdict**: N/A

## 21. Context ✓

每次运行生成 context_id + run_id + trace_id。

## 22. Trace ⚠

仅 1 trace_event（completion）。
**GAP-CP6-02 (P3)** 同 GAP-CP4-03。

## 23. Cost ✓

¥0.000218-0.000361 / call（视编码数）。

## 24. Developer API ✓

API: `POST /api/v1/agents/evidence-extractor/run`
Backend: PureLLMProvider → DeepSeek chat
**GAP-CP6-03 (P1)** 同 GAP-CP4-01：consumer 需从 markdown 解析 JSON。

## 25. Embedded ✓

CP6 是 4 个 embedded-eligible agent 之一。

**Smoke evidence** (`22_embedded_smoke.json`):
- 13 events: page.ready → auth.ok → configureSession.ok (templateKey=`icoder/evidence-extractor@1.0.0`) → setPatientContext.ok → configure.ok → ready → show.ok → ask.start → message.received (user) → message.received (agent) → **run.completed** → **account.creditsConsumed** (¥0.000218) → ask.done
- **AUDIT_BLOCKER_FIX #3 verified**: templateKey 正确 strip 为短 agent_id（URL `/api/v1/agents/evidence-extractor/run`）

**Verdict**: EMBEDDED_CHAIN_VALIDATED ✓

## 26. 医院集成路径

| 路径 | 状态 |
|---|---|
| Backend Service Integration | **CONDITIONAL READY** (markdown JSON-in-block 需 parse) |
| ROPC Embedded | **READY** |
| Orchestrator 子 agent | **NOT WIRED** — Phase 5+ 应让 medical-coding orchestrator 调用 evidence-extractor 作 evidence sub-task |

## 27. UX 评分

12 dimension：

| Dimension | Score | 说明 |
|---|---|---|
| 入口可发现性 | 4 | Hub card |
| 输入体验 | 3 | 需要知道 "input + codes" 格式（无 UI 提示） |
| 输出可读性 | 4 | JSON code block 清晰 |
| 错误恢复 | 5 | fail-soft |
| 实时反馈 | 4 | 5-7s，可接受 |
| Trace 透明度 | 2 | 仅 1 event |
| Cost 透明度 | 5 | 明示 |
| 复制/下载 | 5 | 全套 |
| 配置可调 | 4 | runtime_mode |
| 多轮对话 | 4 | history |
| 移动响应 | 3 | 堆叠 |
| 国际化 | 4 | 双 locale |

**平均**: 3.92 / 5

## 28. 能力分层

| 层 | 状态 |
|---|---|
| PLATFORM_AVAILABLE | ✓ |
| AGENT_CONFIGURED | ✓ |
| RUNTIME_INVOKED | ✓ (real DeepSeek 6s) |
| RESULT_CONSUMED | ⚠ (JSON-in-markdown) |
| QUALITY_VALIDATED | ⚠ (repeatability 差 22 字符) |

**最高层**: RESULT_CONSUMED

## 29. 当前缺口

| ID | Severity | Description |
|---|---|---|
| **GAP-CP6-03** | **P1** | unified API 不解析 JSON 到 result.coded_evidence（同 GAP-CP4-01） |
| GAP-CP6-01 | P2 | temp=0 但 3 次 md_len 差 22 字符（同 GAP-CP4-02 但较轻） |
| GAP-CP6-02 | P3 | trace_events 仅 1 event |
| **GAP-CP6-04** | **P1** (architecture) | 当前独立 agent，应作为 orchestrator 子 agent（medical-coding → evidence-extractor → compliance） |

## 30. 产品重设计建议

| 建议 | 优先级 | 理由 |
|---|---|---|
| **wire evidence-extractor as orchestrator sub-agent** | **P1** | medical-coding agent orchestrator 调用 evidence-extractor 作 evidence 子任务（per memory: orchestrator 5 态状态机） |
| **JSON 解析 → result.coded_evidence** | **P1** | 消费者直接拿结构化 |
| **input UI helper** | P2 | 添加 codes 输入框（不只 extra） |
| trace 加 LLM call 时序 | P3 | 审计 |

## 31. 是否进入质量评测

**条件性是**。需先修 GAP-CP6-03（结构化）+ GAP-CP6-04（orchestrator 集成）。

建议：与 CP4/CP5 共用 P1 修复。

## 32. 最终裁决

# `READY_FOR_INTERNAL_SHADOW`

理由：
- 真实 DeepSeek + 4 fixture 全部 evidence 准确（3-7 codes 全 direct）
- Chinese-native ICD-10-CN 6 位码 evidence 准确
- Embedded smoke 全链路 + AUDIT_BLOCKER_FIX #3 verified
- 但 P1 双 gap（结构化提取 + orchestrator wiring）阻塞 benchmark
- Phase 5+ 路线：从独立 agent → orchestrator 子 agent

**Next**: CP7 principal-diagnosis-review（embedded-eligible，最后 1 个 embedded checkpoint）

---

## 附录：证据清单

| 类别 | 文件 |
|---|---|
| Screenshots | `screenshots/phase5_track_b2/evidence-extractor/04_detail.png` |
| Run envelopes | `outputs/phase5_track_b2/per_agent_runs/evidence-extractor/*.json` (8 个: 01/02/03/09/17/18_1-3/21_empty/21_wrong/22_smoke) |
| Backend code | `backend/icoder_runtime/backends/pure_llm_provider.py`, `backend/app/api/agent_run.py:619-620` |
| Agent pack | `backend/official_agents/evidence_extractor/agent_pack.json` |
| Chained runner | `scripts/phase5_track_b2_cp6_evidence_runner.py` |
| Embedded smoke | `packages/icoder-embedded/examples/phase5_b2_cp6_smoke.html` |
