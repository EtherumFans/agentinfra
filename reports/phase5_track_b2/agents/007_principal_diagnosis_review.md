# CP7 — principal-diagnosis-review 深度走查报告 (Phase 5 Track B-2)

**Agent ID**: `principal-diagnosis-review` (Hub ref `icoder/principal-diagnosis-review@1.0.0`)
**Corti mapping**: `ICODER_ONLY` (B-1) → **CP7 复刻 reference: `medical-coding-icd-10-cpt-agent`**（Corti 把 principal dx logic 内嵌于 coding agent；iCoDer 拆为独立 agent）
**Backend provider**: `icoder.pure-llm.v1` (PureLLMProvider — no tools)
**Output schema**: `icoder/PrincipalDxReviewOutput/v1` (candidates + recommended + not_recommended + rationale + manual_review_prompt)
**Audit date**: 2026-07-11
**Walkthrough evidence**: 1 screenshot + 10 API envelopes + 1 embedded smoke log

---

## 关键发现

**principal-diagnosis-review 真实运行 PureLLMProvider — DeepSeek V4 chat，多诊断病例中准确识别主诊断候选 + 推荐主诊断 + 冲突解决：**

- **真实 LLM 调用**（latency 4.8-16.8s, cost ¥0.000071-0.000503）
- **fixture 11 冲突解决**：左/右侧别冲突 → LLM 用术中记录作 ground truth，正确选择 K40.900 + 解释笔误原因
- **fixture 09 多病共存 (7 dx)**：正确推荐 I50.900 心衰（最严重 + 资源消耗最大 + 主要治疗）
- **fixture 02 心血管 case**：5 候选 → I21.0 STEMI 正确作主诊断
- **同 CP4/CP5/CP6 P1 gap**：unified API 不解析 JSON 到结构化字段

## 1. 产品定位

iCoDer principal-diagnosis-review 是**主诊断复核智能体**。给定含 2+ 诊断的出院小结 / 病程记录，按主诊断选择准则评估每个候选，输出推荐主诊断 + 不推荐列表 + rationale + 复核提示。

主诊断选择准则（按优先级）：
1. 对患者健康危害最严重的诊断
2. 消耗医疗资源最多的诊断
3. 住院期间主要治疗的诊断
4. 凡病因住院，第一诊断 = 病因

是 medical-coding-agent 的**质控伙伴** — 编码员提交前复核主诊断是否合理。

## 2. 目标用户

- 病案编码员（主诊断 self-check）
- 编码审计员（主诊断 dispute resolution）
- DRG 结算员（主诊断决定 DRG 组 → 决定补偿）

## 3. 使用场景

| 场景 | 输入 | 期望输出 |
|---|---|---|
| 主诊断选择 | 多诊断出院小结 | recommended + rationale |
| 主诊断冲突 | 入院/出院诊断不一致 | conflict resolution |
| DRG 高权重核查 | 高补偿主诊断 | upcoding 检测 |

## 4. Corti 映射

| 维度 | iCoDer | Corti | 一致性 |
|---|---|---|---|
| Agent name | principal-diagnosis-review (独立) | 内嵌于 medical-coding-icd-10-cpt-agent | DIFFERENT (iCoDer 拆分) |
| Backend | PureLLMProvider | LLM 内嵌于 coding agent | similar |
| 主诊断选择 | ✓ 独立评估 + 推荐 | ✓ 内嵌于 Code Assignment → Primary Diagnosis 部分 | similar concept |
| Candidates + rationale | ✓ 显式 candidates 数组 + per-candidate rationale | ✓ Primary Diagnosis Rationale | EXACT concept |
| Not recommended + reason | ✓ 独有 | ✗ Corti 只显示推荐 | ICODER_ADVANTAGE |
| Manual review prompt | ✓ 独有 | ✗ | ICODER_ADVANTAGE |

## 4a. Corti 相似 agent 复刻分析（per 用户 directive 2026-07-11）

**Corti 相似 agent**：`medical-coding-icd-10-cpt-agent`（Corti 把 principal dx 内嵌于 coding agent 的 Code Assignment → Primary Diagnosis 部分）

### 设计理念对照
- **Corti**：编码 agent 一体化 — 输入病历 → 输出全部编码（含 primary + secondary + procedures + gaps + rationale）。Primary dx 选择是 coding 流程的一个 step。
- **iCoDer**：拆分为独立 agent — principal-diagnosis-review 专注主诊断评估，可被 medical-coding / DRG / 编码审计员独立调用。
- **复刻优先级**：保持 iCoDer 拆分（更灵活，可独立调用），但**学习 Corti 的 rationale 字段**（已实现 ✓）

### 处理流程对照

| 步骤 | Corti medical-coding | iCoDer principal-diagnosis-review | gap |
|---|---|---|---|
| 1. 输入 | 病历 + 编码员初稿 | 病历（无初稿） | iCoDer 缺初稿输入 |
| 2. 候选识别 | LLM 自动提取 dx | LLM 自动提取 | EXACT |
| 3. 候选评估 | LLM 内嵌（severity / resource / treatment） | LLM 显式 candidates[] | EXACT concept |
| 4. 推荐 | LLM 输出 Primary + Rationale | LLM 输出 recommended + rationale | EXACT |
| 5. 不推荐 | ✗ 不显式 | ✓ not_recommended[] + reason | ICODER_ADVANTAGE |
| 6. Validation | ✓ Total codes count + compliance confidence | ✗ | iCoDer 缺 validation summary |

### LLM 调用对照

| 维度 | Corti | iCoDer | gap |
|---|---|---|---|
| Model | LLM (per RE) | DeepSeek chat (temp=0.0, max_tokens=4096) | similar |
| System prompt 长度 | 5539 chars (per prompt file) | ~800 chars | iCoDer 较短 |
| Few-shot examples | ✓ Corti 有 | ✗ iCoDer 无 | iCoDer 缺 |
| JSON mode | ✓ Corti 输出 markdown table | ✓ iCoDer 输出 JSON-in-markdown | similar |
| Role section | ✓ `<role>` tag | ✓ "你是 iCoDer..." | similar |

### 工具调用对照

| 维度 | Corti | iCoDer | gap |
|---|---|---|---|
| Experts | coding-expert + pubmed-expert + web-search-expert + medical-calculator-expert | 1 (pdx-reviewer) | ICODER_GAP — 缺 pubmed/web-search |
| MCP tools | verify_code / get_guidelines / explore_code / search_codes / clinical_calculator | 0 | ICODER_GAP — PureLLM 无 tool_calling |
| Sub-agents | 0 | 0 | EXACT (both none — Phase 5+ orchestrator 应改) |

### 复刻优先级清单（iCoDer 应补）

| 优先级 | 项目 | 理由 |
|---|---|---|
| **P1** | 结果 JSON 解析到结构化 schema | 同 CP4-CP6 GAP |
| **P2** | 加 pubmed/web-search experts（LLMWithTools migration） | 让 LLM 查 ICD-10-CN 编码指南 |
| **P2** | 加 system prompt few-shot examples | 提高 determinism + accuracy |
| **P3** | 加 validation summary（codes count + confidence） | Corti parity |
| **P3** | 加 ICD-10-CN principal dx selection KB | 中国指南 specific rules |

## 5. Card UI

Hub 卡片在 `/ai-studio/agents` → 浏览预置：
- 名称：主诊断复核智能体
- 版本：1.0.0
- maturity: mvp

## 6. Detail UI

`04_detail.png`：
- 5 个 tab（Overview / Settings / Experts / Tools / Code）
- 1 个 expert（Principal Dx Reviewer primary）
- 0 个 tools
- backend_provider 显示 icoder.pure-llm.v1

## 7. 输入 UI

AgentDetailPage chat box。
建议输入：含 2+ 诊断的出院小结 / 病程记录。

## 8. 运行流程

```
POST /api/v1/agents/principal-diagnosis-review/run
↓
agent_run.py:run_agent
↓ agent_id NOT in _MEDICAL_CODING_AGENT_IDS
→ ProviderRegistry → PureLLMProvider.invoke
→ DeepSeek chat (temp=0.0, max_tokens=4096)
→ markdown 内嵌 JSON（candidates + recommended + not_recommended + rationale）
↓ envelope 13 字段
```

Latency: **4.8-16.8s** ✓（视诊断复杂度，多诊断 case 更长）

## 9. 输出 UI

MessageBubble 渲染 markdown（JSON code block）。
candidates 数组 + recommended + not_recommended + rationale + manual_review_prompt。

## 10. 正常输入（fixture 01 orthopedics, 3 dx）✓

**Run**: latency 6.7s, cost ¥0.000278
**Output**: candidates 3 个（S22.000 / M80.900 / I10），recommended=S22.900，rationale 详细
**Verdict**: ✓ 准确识别 T12 骨折为主诊断（最严重 + 主要治疗）

## 11. 长输入（fixture 02 cardiology, 5 dx）✓

**Run**: latency 12.0s, cost ¥0.000370
**Output**: 5 候选，recommended=I21.0 (STEMI)，rationale 引用 MRI/CT/PCI 多 evidence
**Verdict**: ✓ STEMI 正确为主诊断

## 12. 缺失信息（fixture 14 minimal）✓

**Input**: "患者男。"
**Run**: latency 12.8s, cost ¥0.000382
**Verdict**: ✓ LLM 识别无诊断可评估

## 13. 否定与历史

未单独跑（已在 CP1/CP4 验证否定处理）。

## 14. 冲突输入（fixture 11 left/right discrepancy）✓ **关键证据**

**Input**: 入院诊断"左侧" vs 术中"右侧"腹股沟斜疝
**Run**: `run-2a188d8...`, latency 9.2s, cost ¥0.000279
**Output JSON**:
```json
{
  "candidates": [
    {
      "code": "K40.900",
      "display": "单侧腹股沟疝",
      "evidence_text": "出院诊断:右侧腹股沟斜疝;术中记录:见右侧腹股沟斜疝...",
      "recommended": true,
      "rationale": "右侧腹股沟斜疝是本次住院主要原因...尽管入院诊断和病程记录有笔误（写为左侧），但术中记录和出院诊断明确为右侧，应以实际手术侧为准。"
    },
    {"code": "K59.000", "display": "慢性便秘", "recommended": false, "reason": "既往史，非本次住院主因"}
  ],
  "recommended": "K40.900"
}
```

**Verdict**: **CONFLICT_RESOLUTION_ACCURATE** ✓ — LLM 用术中记录作 ground truth，正确解决左侧/右侧冲突，并显式说明 rationale。

## 15. 无效输入（17 invalid）✓

**Input**: "今天天气不错。"
**Run**: latency 4.8s, cost ¥0.000071
**Verdict**: ✓ fail-soft LLM 引导

## 16. Repeatability ⚠

**3 次同输入（fixture 01）**:
- run 1: 8.8s, md_hash=0aaafc6ee6ab7d27, md_len=1524
- run 2: 8.7s, md_hash=87075af89dce3f62, md_len=1532
- run 3: 9.7s, md_hash=2e13bc39012cc722, md_len=1712

3 次 hash 不同，md_len 差 8-188 字符。**GAP-CP7-01 (P2)** 同 GAP-CP4-02。

## 17. 配置变化

Fork UI 可用。

## 18. 错误恢复 ✓

- 不存在 agent: envelope.error=true, error_reason=unknown_agent
- 空输入: 422 Pydantic
- 无效文本: LLM 引导

## 19. Expert 实证 ✓

**配置**: 1 expert（Principal Dx Reviewer primary）
**实际**: PureLLMProvider 真实完成主诊断评估
**Verdict**: **EXPERT_INVOKED (LLM-level)** ✓

## 20. Tool 实证

**配置**: 0 tools（PureLLM 无 tool_calling）
**Verdict**: N/A
**GAP-CP7-02 (P2)**（per §4a）：Corti medical-coding 有 4 experts + 4 MCP tools，iCoDer 应迁移到 LLMWithTools。

## 21. Context ✓

每次运行生成 context_id + run_id + trace_id。

## 22. Trace ⚠

仅 1 trace_event（completion）。
**GAP-CP7-03 (P3)** 同 GAP-CP4-03。

## 23. Cost ✓

¥0.000071-0.000503 / call（视诊断数 + 复杂度）。

## 24. Developer API ✓

API: `POST /api/v1/agents/principal-diagnosis-review/run`
**GAP-CP7-04 (P1)** 同 GAP-CP4-01：consumer 需从 markdown 解析 JSON。

## 25. Embedded ✓

CP7 是 4 个 embedded-eligible agent 之一。

**Smoke evidence** (`22_embedded_smoke.json`):
- 13 events: full chain (auth → configureSession → setPatientContext → configure → show → ask → run.completed → account.creditsConsumed)
- **AUDIT_BLOCKER_FIX #3 verified**: templateKey `icoder/principal-diagnosis-review@1.0.0` 正确 strip 为短 agent_id

**Verdict**: EMBEDDED_CHAIN_VALIDATED ✓

## 26. 医院集成路径

| 路径 | 状态 |
|---|---|
| Backend Service Integration | **CONDITIONAL READY** (markdown JSON 需 parse) |
| ROPC Embedded | **READY** |
| DRG 前置核查 | **READY** — 主诊断决定 DRG 组，本 agent 是 DRG 入口核查 |

## 26a. Orchestrator wiring gap（per 用户 directive 2026-07-11）

**应作为 orchestrator 子 agent？** ✓ 是
- medical-coding orchestrator 在编码完成后，应**调用 principal-diagnosis-review** 复核主诊断
- 若 recommended ≠ coding agent 输出的 primary_diagnosis → 触发 manual review

**当前 wired？** ✗ 否
- 当前需用 chained runner 手工串联（同 CP3 compliance-guardrail 模式）

**推荐 orchestrator 入口**：medical-coding-agent
- stage 1: medical-coding-agent (分配全部 codes)
- stage 2: **principal-diagnosis-review** (复核主诊断) ← 本 CP7
- stage 3: evidence-extractor (per-code evidence)
- stage 4: compliance-guardrail (规则验证)
- stage 5: note-completeness (文档完整性)

## 27. UX 评分

12 dimension：

| Dimension | Score | 说明 |
|---|---|---|
| 入口可发现性 | 4 | Hub card |
| 输入体验 | 4 | chat UI 工作（多诊断 case 自然） |
| 输出可读性 | 5 | candidates + rationale 详细可读 |
| 错误恢复 | 5 | fail-soft + 冲突解决 |
| 实时反馈 | 3 | 5-17s，长 case 等待无 streaming |
| Trace 透明度 | 2 | 仅 1 event |
| Cost 透明度 | 5 | 明示 |
| 复制/下载 | 5 | 全套 |
| 配置可调 | 4 | runtime_mode |
| 多轮对话 | 4 | history |
| 移动响应 | 3 | 堆叠 |
| 国际化 | 4 | 双 locale |

**平均**: 4.0 / 5

## 28. 能力分层

| 层 | 状态 |
|---|---|
| PLATFORM_AVAILABLE | ✓ |
| AGENT_CONFIGURED | ✓ |
| RUNTIME_INVOKED | ✓ (real DeepSeek) |
| RESULT_CONSUMED | ⚠ (JSON-in-markdown) |
| QUALITY_VALIDATED | ⚠ (repeatability) |

**最高层**: RESULT_CONSUMED

## 29. 当前缺口

| ID | Severity | Description |
|---|---|---|
| **GAP-CP7-04** | **P1** | unified API 不解析 JSON 到结构化（同 GAP-CP4-01） |
| GAP-CP7-01 | P2 | temp=0 但 3 次 md_len 差 188 字符 |
| **GAP-CP7-02** | **P2** | 缺 Corti 4 experts + 4 MCP tools（per §4a 复刻清单） |
| GAP-CP7-03 | P3 | trace_events 仅 1 event |
| **GAP-CP7-05** | **P1** (architecture) | 当前独立 agent，应作为 medical-coding orchestrator 子 agent（per §26a） |

## 30. 产品重设计建议

| 建议 | 优先级 | 理由 |
|---|---|---|
| **JSON 解析 → 结构化 schema** | **P1** | 同 CP4-CP6 |
| **wire 为 orchestrator 子 agent** | **P1** | medical-coding 自动调用，无需 chained runner |
| **加 pubmed + web-search experts** | P2 | per §4a Corti 复刻 |
| **加 system prompt few-shot** | P2 | 提高 determinism |
| 加 ICD-10-CN principal dx selection KB | P3 | 中国指南 |

## 31. 是否进入质量评测

**条件性是**。需先修 GAP-CP7-04（结构化）+ GAP-CP7-05（orchestrator wiring）。

## 32. 最终裁决

# `READY_FOR_INTERNAL_SHADOW`

理由：
- 真实 DeepSeek + 4 fixtures 全部主诊断准确
- **fixture 11 冲突解决**：LLM 用术中记录作 ground truth 正确解决左/右冲突，并显式说明 rationale（关键证据）
- Embedded smoke 全链路 + AUDIT_BLOCKER_FIX #3 verified
- 但 P1 双 gap（结构化 + orchestrator wiring）阻塞 benchmark
- Phase 5+ 路线：从独立 agent → medical-coding orchestrator 子 agent

**Next**: CP8 discharge-summary-structuring（Corti 相似 agent = clinical-documentation-improvement-cdi-agent）

---

## 附录：证据清单

| 类别 | 文件 |
|---|---|
| Screenshots | `screenshots/phase5_track_b2/principal-diagnosis-review/04_detail.png` |
| Run envelopes | `outputs/phase5_track_b2/per_agent_runs/principal-diagnosis-review/*.json` (10 个 + 22_smoke) |
| Backend code | `backend/icoder_runtime/backends/pure_llm_provider.py` |
| Agent pack | `backend/official_agents/principal_diagnosis_review/agent_pack.json` |
| Embedded smoke | `packages/icoder-embedded/examples/phase5_b2_cp7_smoke.html` |
| Corti similar agent prompt | `outputs/phase5_track_b/corti_prompts/medical-coding-icd-10-cpt-agent.txt` (5539 chars) |
| User directive | `reports/phase5_track_b2/USER_DIRECTIVE_CORTI_SIMILAR_AND_ORCHESTRATOR.md` |
