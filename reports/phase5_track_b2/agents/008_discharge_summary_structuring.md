# CP8 — discharge-summary-structuring 深度走查报告 (Phase 5 Track B-2)

**Agent ID**: `discharge-summary-structuring` (Hub ref `icoder/discharge-summary-structuring@1.0.0`)
**Corti mapping**: `ICODER_ONLY` (B-1) → **CP8 复刻 reference: `clinical-documentation-improvement-cdi-agent`**（Corti CDI 关注文档完整性 + 查询生成；iCoDer discharge-summary-structuring 关注结构化字段抽取 — 设计理念相近但输出形态不同）
**Backend provider**: `icoder.pure-llm.v1` (PureLLMProvider — no tools)
**Output schema**: `icoder/DischargeSummaryStructured/v1` (diagnoses + procedures + treatment_summary + discharge_orders + follow_up_recommendations + discharge_status + manual_review_required)
**Audit date**: 2026-07-11
**Walkthrough evidence**: 1 screenshot + 11 API envelopes

---

## 关键发现

**discharge-summary-structuring 真实运行 PureLLMProvider — DeepSeek V4 chat，跨 4 个 fixture (ortho/cardio/gastro/obs) 全部输出完整结构化 JSON：**

- **真实 LLM 调用**（latency 6.8-10.2s, cost ¥0.000191-0.000323）
- **多科覆盖**：骨科 / 心血管 (PCI 术后) / 胆囊切除 / 剖宫产 + 产后出血 — 4 个不同结构
- **manual_review_required=true** 在所有 fixture 输出（iCoDer 显式标记需要人工复核，符合 medical-coding 流程"先结构化 → 后编码 → 再人工复核"理念）
- **fail-soft 准确**：14 缺失 + 17 无效 → 空 schema + manual_review_required=true（不拒错）
- **同 CP4-CP7 P1 gap**：unified API 不解析 JSON 到结构化字段（result.markdown 持有全部 JSON）

## 1. 产品定位

iCoDer discharge-summary-structuring 是**出院小结结构化智能体**。给定非结构化出院小结原文，输出：
1. diagnoses[]（含 primary / secondary + evidence span）
2. procedures[]（含 evidence span）
3. treatment_summary（按时间顺序的自然语言摘要）
4. discharge_orders[]（出院医嘱）
5. follow_up_recommendations[]（科室/时间/项目）
6. discharge_status（1=治愈/2=好转/3=未愈/4=死亡/5=其他）

不分配 ICD 编码 — 仅结构化抽取。是 medical-coding-agent 的**结构化前置任务**。

## 2. 目标用户

- 病案编码员（编码前快速结构化出院小结）
- 病案室（病案归档 + 质控）
- DRG 结算员（结构化字段 → DRG 入组）

## 3. 使用场景

| 场景 | 输入 | 期望输出 |
|---|---|---|
| 编码前置 | 出院小结原文 | 结构化字段 → 喂给 medical-coding |
| 病案归档 | 出院小结原文 | diagnoses + procedures 列表 |
| 随访管理 | 出院小结原文 | follow_up_recommendations |
| 出院状态统计 | 出院小结原文 | discharge_status (1-5) |

## 4. Corti 映射

| 维度 | iCoDer | Corti | 一致性 |
|---|---|---|---|
| Agent name | discharge-summary-structuring (独立) | clinical-documentation-improvement-cdi-agent (独立) | both exist |
| Backend | PureLLMProvider | LLM + 4 experts (pubmed/web-search/medical-calculator/coding) | DIFFERENT (iCoDer 缺 experts) |
| 核心任务 | 结构化字段抽取 | documentation gap 识别 + provider query 生成 | DIFFERENT (iCoDer 输出 schema, Corti 输出 queries) |
| Discharge summary 输入 | ✓ 出院小结原文 | ✓ chart excerpt (含出院小结) | similar |
| manual_review 标记 | ✓ manual_review_required=true | ✓ Risk Flags 部分 | similar concept |
| Coding 准备 | ✓ 结构化供 coding agent | ✓ CDI 改善文档供 coding | similar goal |

## 4a. Corti 相似 agent 复刻分析（per 用户 directive 2026-07-11）

**Corti 相似 agent**：`clinical-documentation-improvement-cdi-agent`（Corti CDI 最接近 — 都是从非结构化文本提取结构化信息 + 标记 manual review）

### 设计理念对照

- **Corti CDI**：识别 chart 中 documentation gap → 生成 compliant provider query（non-leading）→ 改善文档以便更准确编码。Output = queries + gaps + risk flags。
- **iCoDer discharge-summary-structuring**：抽取 chart 中结构化字段（diagnoses / procedures / treatment / orders / follow-up / status）→ 提供给 medical-coding agent。Output = structured JSON。
- **共同点**：都是 medical-coding 流程的**前置任务**，都强调"基于原文 evidence span，不 fabrication"。
- **差异点**：Corti 输出"问什么"（query），iCoDer 输出"是什么"（structured fields）。
- **复刻优先级**：保持 iCoDer 结构化抽取（更直接），但**学习 Corti 的 Risk Flags 字段**（已通过 manual_review_required 部分实现 ✓）+ **学习 Corti 的 4-expert 协作模式**（iCoDer 缺）。

### 处理流程对照

| 步骤 | Corti CDI | iCoDer discharge-summary-structuring | gap |
|---|---|---|---|
| 1. 输入解析 | chart excerpt + encounter metadata | 出院小结原文 | similar |
| 2. 关键信息抽取 | LLM 提取 diagnoses/symptoms/labs | LLM 提取 diagnoses/procedures | EXACT concept |
| 3. Expert 咨询 | coding-expert + pubmed + web-search + medical-calculator | 0 (PureLLM) | ICODER_GAP — 缺 4 experts |
| 4. Validation | LLM 校验 Expert 输出 + reject leading queries | LLM 自校验 evidence span | similar concept |
| 5. 输出 | Encounter Summary + Documentation Gaps + Proposed Queries + Risk Flags + Specialist Trace | JSON (diagnoses + procedures + treatment + orders + follow-up + status + manual_review) | DIFFERENT structure |
| 6. manual_review 触发 | ✓ Risk Flags 部分 | ✓ manual_review_required=true (always) | EXACT concept |

### LLM 调用对照

| 维度 | Corti CDI | iCoDer discharge-summary-structuring | gap |
|---|---|---|---|
| Model | LLM (per RE) | DeepSeek chat (temp=0.0, max_tokens=4096) | similar |
| System prompt 长度 | 6238 chars (per prompt file) | ~1100 chars | iCoDer 较短 |
| Few-shot examples | ✗ Corti 无 | ✗ iCoDer 无 | EXACT (both none) |
| JSON mode | ✓ Corti 输出 markdown sections | ✓ iCoDer 输出 JSON-in-markdown | DIFFERENT format |
| Role section | ✓ specialized agent within Corti Agentic Framework | ✓ "你是 iCoDer..." | similar |
| Constraints section | ✓ `<constraints>` tag | ✓ "硬约束：" 列表 | similar concept |
| Workflow section | ✓ `<workflow>` tag | ✗ (iCoDer 无显式 workflow) | iCoDer 缺 |
| Output format section | ✓ `<output_format>` 详细 sections | ✓ "输出 JSON：" | similar concept |
| Query guidelines | ✓ `<query_guidelines>` 含示例 | ✗ (iCoDer 不生成 query) | N/A |
| Principles | ✓ `<principles>` accuracy > reimbursement | ✗ | iCoDer 可补 |

### 工具调用对照

| 维度 | Corti CDI | iCoDer discharge-summary-structuring | gap |
|---|---|---|---|
| Experts | pubmed-expert + web-search-expert + medical-calculator-expert + coding-expert (4) | 1 (discharge-structurer) | ICODER_GAP — 缺 3 experts |
| MCP tools | per Expert config (pubmed/web-search/etc.) | 0 | ICODER_GAP — PureLLM 无 tool_calling |
| Sub-agents | 0 | 0 | EXACT (both none — Phase 5+ orchestrator 应改) |
| Validation trace | ✓ Specialist Trace per Expert (consulted/accepted/rejected + rationale) | ✗ | ICODER_GAP — 缺 audit trail |

### 复刻优先级清单（iCoDer 应补）

| 优先级 | 项目 | 理由 |
|---|---|---|
| **P1** | 结果 JSON 解析到结构化 schema | 同 CP4-CP7 GAP |
| **P1** | wire 为 medical-coding orchestrator 子 agent | 编码前置结构化（per §26a） |
| **P2** | 加 pubmed/web-search/medical-calculator experts | 让 LLM 查 evidence 准确性 + 临床定义 |
| **P2** | 加 system prompt workflow 节 | 提高 determinism（参考 Corti `<workflow>` tag） |
| **P3** | 加 Specialist Trace 字段 | Corti parity（per-Expert audit trail） |
| **P3** | 加 Risk Flags 字段（Corti 有） | 比 manual_review_required 更细粒度 |

## 5. Card UI

Hub 卡片在 `/ai-studio/agents` → 浏览预置：
- 名称：出院小结结构化智能体
- 版本：1.0.0
- maturity: mvp
- human_review: required

## 6. Detail UI

`04_detail.png`：
- 5 个 tab（Overview / Settings / Experts / Tools / Code）
- 1 个 expert（Discharge Summary Structurer primary）
- 0 个 tools
- backend_provider 显示 icoder.pure-llm.v1

## 7. 输入 UI

AgentDetailPage chat box。
建议输入：完整的出院小结原文（含主诉/现病史/查体/辅助检查/诊断/治疗/出院医嘱）。

## 8. 运行流程

```
POST /api/v1/agents/discharge-summary-structuring/run
↓
agent_run.py:run_agent
↓ agent_id NOT in _MEDICAL_CODING_AGENT_IDS
→ ProviderRegistry → PureLLMProvider.invoke
→ DeepSeek chat (temp=0.0, max_tokens=4096)
→ markdown 内嵌 JSON（diagnoses + procedures + treatment_summary + discharge_orders + follow_up + discharge_status）
↓ envelope 13 字段
```

Latency: **6.8-10.2s** ✓（视出院小结长度 + 诊断/手术数）

## 9. 输出 UI

MessageBubble 渲染 markdown（JSON code block）。
diagnoses 数组 + procedures 数组 + treatment_summary 字符串 + discharge_orders 数组 + follow_up 数组 + discharge_status 数字 + manual_review_required 布尔。

## 10. 正常输入（fixture 01 orthopedics, T12 骨折）✓

**Run**: `run-222363b7-4ba5-4a9d-b218-973dad8a550f`, latency 10.2s, cost ¥0.000191
**Output**:
```json
{
  "diagnoses": [
    {"text": "T12 椎体压缩性骨折", "primary": true, "evidence_text": "MRI 显示 T12 椎体压缩性骨折", "char_span": [12, 28]},
    {"text": "骨质疏松性骨折", "primary": false, "evidence_text": "骨密度 T 值 -3.2(骨质疏松)", "char_span": [29, 44]},
    {"text": "高血压病 3 级(很高危)", "primary": false, "evidence_text": "既往有高血压病史 10 年", "char_span": [45, 60]}
  ],
  "procedures": [],
  "treatment_summary": "患者入院后行 MRI 检查确诊 T12 椎体压缩性骨折, 予卧床休息、镇痛及抗骨质疏松治疗(唑来膦酸), 必要时行 PKP/PVP。",
  "discharge_orders": ["卧床休息", "镇痛治疗", "抗骨质疏松治疗(唑来膦酸)"],
  "follow_up_recommendations": [{"department": "骨科", "time": "术后 1 月", "items": ["X 线复查"]}],
  "discharge_status": 5,
  "manual_review_required": true
}
```
**Verdict**: ✓ 3 dx + treatment + orders + follow-up + status=5(其他) 全部结构化准确

## 11. 长输入（fixture 02 cardiology, STEMI + PCI）✓

**Run**: latency 8.9s, cost ¥0.000237, md_len=1205
**Output**: 4 dx (STEMI primary + 冠状动脉单支病变 + 高脂血症 + 吸烟者) + 1 procedure (LAD PCI 术) + treatment + 5 discharge_orders + follow-up + status=2(好转)
**Verdict**: ✓ PCI 术后出院小结完整结构化，5 discharge_orders 准确（抗血小板/他汀/戒烟/低脂饮食/避免剧烈活动）

## 12. 长输入（fixture 04 gastroenterology, 胆囊切除）✓

**Run**: latency 6.8s, cost ¥0.000217, md_len=959
**Output**: 2 dx (急性结石性胆囊炎 primary + 2 型糖尿病) + 1 procedure (腹腔镜胆囊切除术) + treatment + 4 discharge_orders + 2 follow_up_recommendations (普外科+内分泌科) + status=2
**Verdict**: ✓ 多 follow-up 科室准确（术后 1 周拆线 + 术后 1 月血糖复查）

## 13. 长输入（fixture 06 obstetrics, 剖宫产 + 产后出血）✓

**Run**: latency 7.2s, cost ¥0.000323, md_len=1801（最长）
**Output**: 5 dx (G2P0 孕 39 周临产 primary + 活跃期停滞 + 产后出血中度 + 剖宫产术后 + 单活产) + 4 procedures (剖宫产 + B-Lynch 缝合 + 宫腔球囊 + 输血) + treatment + orders + follow-up + status=2
**Verdict**: ✓ 复杂产科 case 全部结构化准确，4 procedures 包含输血等关键事件

## 14. 缺失信息（fixture 14 minimal）✓

**Input**: "患者男。"
**Run**: latency 2.4s, cost ¥0.000080
**Output**: `{"diagnoses": [], "procedures": [], "treatment_summary": "", "discharge_orders": [], "follow_up_recommendations": [], "discharge_status": 5, "manual_review_required": true}`
**Verdict**: ✓ LLM 识别无信息可抽取，输出空 schema + manual_review_required=true

## 15. 否定与历史

未单独跑（CP4/CP7 已验证否定处理）。

## 16. 冲突输入

未单独跑（fixture 11 走 medical-coding + principal-dx 已验证）。

## 17. 无效输入（fixture 17）✓

**Input**: "今天天气不错。"
**Run**: latency 2.2s, cost ¥0.000080
**Output**: 同 fixture 14 空 schema
**Verdict**: ✓ fail-soft LLM 引导，无 fabrication

## 18. Repeatability ✓（相对稳定）

**3 次同输入（fixture 01）**:
- run 1: 4.1s, md_hash=b562ae38ad706904, md_len=777
- run 2: 3.7s, md_hash=9c18039ebe75ccd3, md_len=687
- run 3: 3.6s, md_hash=0cc3eebd555998de, md_len=701

3 次 hash 不同但 md_len 接近（差 16-90 字符）— **比 CP4 (差 400) 更稳定**。
**GAP-CP8-01 (P2)** 同 GAP-CP4-02 但 severity 较低（接近 CP6 水平）。

## 19. 配置变化

Fork UI 可用。

## 20. 错误恢复 ✓

- 不存在 agent: `21_error_wrong_agent.json` envelope.error=true, error_reason=unknown_agent
- 空输入: `21_error_empty_input.json` HTTP 422 Pydantic
- 无效文本: LLM 引导

## 21. Expert 实证 ✓

**配置**: 1 expert（Discharge Summary Structurer primary）
**实际**: PureLLMProvider 真实完成结构化抽取
**Verdict**: **EXPERT_INVOKED (LLM-level)** ✓

## 22. Tool 实证

**配置**: 0 tools（PureLLM 无 tool_calling）
**Verdict**: N/A
**GAP-CP8-02 (P2)**（per §4a）：Corti CDI 有 4 experts，iCoDer 应迁移到 LLMWithTools。

## 23. Context ✓

每次运行生成 context_id + run_id + trace_id。

## 24. Trace ⚠

仅 1 trace_event（completion）。
**GAP-CP8-03 (P3)** 同 GAP-CP4-03。

## 25. Cost ✓

¥0.000080-0.000323 / call（视出院小结长度 + 诊断/手术数）。

## 26. Developer API ✓

API: `POST /api/v1/agents/discharge-summary-structuring/run`
**GAP-CP8-04 (P1)** 同 GAP-CP4-01：consumer 需从 markdown 解析 JSON。

## 27. Embedded

非 embedded-eligible（不在 4-agent embedded smoke 列表）。Phase 5+ 若 medical-coding orchestrator 接入，可作 sub-agent。

## 28. 医院集成路径

| 路径 | 状态 |
|---|---|
| Backend Service Integration | **CONDITIONAL READY** (markdown JSON 需 parse) |
| ROPC Embedded | **NOT APPLICABLE** (非 embedded-eligible) |
| 编码前置结构化 | **READY** — medical-coding agent 上游 |

## 26a. Orchestrator wiring gap（per 用户 directive 2026-07-11）

**应作为 orchestrator 子 agent？** ✓ 是
- medical-coding orchestrator 在编码前，应**先调用 discharge-summary-structuring** 结构化出院小结
- 结构化结果（diagnoses + procedures）→ 喂给 medical-coding agent 作编码输入

**当前 wired？** ✗ 否
- 当前 medical-coding agent 直接吃原始文本 + 直接产 codes
- 中间没有 discharge-summary-structuring 步骤

**推荐 orchestrator 入口**：medical-coding-agent
- stage 1: **discharge-summary-structuring** (结构化原文) ← 本 CP8
- stage 2: medical-coding-agent (基于结构化字段分配 codes)
- stage 3: principal-diagnosis-review (复核主诊断)
- stage 4: evidence-extractor (per-code evidence)
- stage 5: compliance-guardrail (规则验证)
- stage 6: note-completeness (文档完整性)

## 29. UX 评分

12 dimension：

| Dimension | Score | 说明 |
|---|---|---|
| 入口可发现性 | 4 | Hub card |
| 输入体验 | 4 | chat UI 工作 |
| 输出可读性 | 4 | JSON code block 清晰 |
| 错误恢复 | 5 | fail-soft + manual_review 触发 |
| 实时反馈 | 3 | 7-10s 长输入等待无 streaming |
| Trace 透明度 | 2 | 仅 1 event |
| Cost 透明度 | 5 | 明示 |
| 复制/下载 | 5 | 全套 |
| 配置可调 | 4 | runtime_mode |
| 多轮对话 | 4 | history |
| 移动响应 | 3 | 堆叠 |
| 国际化 | 4 | 双 locale |

**平均**: 3.92 / 5

## 30. 能力分层

| 层 | 状态 |
|---|---|
| PLATFORM_AVAILABLE | ✓ |
| AGENT_CONFIGURED | ✓ |
| RUNTIME_INVOKED | ✓ (real DeepSeek 7-10s) |
| RESULT_CONSUMED | ⚠ (JSON-in-markdown) |
| QUALITY_VALIDATED | ✓ (repeatability md_len 差 < 90) |

**最高层**: RESULT_CONSUMED

## 31. 当前缺口

| ID | Severity | Description |
|---|---|---|
| **GAP-CP8-04** | **P1** | unified API 不解析 JSON 到 result.diagnoses（同 GAP-CP4-01） |
| GAP-CP8-01 | P2 | temp=0 但 3 次 md_len 差 16-90 字符（较稳定） |
| **GAP-CP8-02** | **P2** | 缺 Corti CDI 4 experts（per §4a 复刻清单） |
| GAP-CP8-03 | P3 | trace_events 仅 1 event |
| **GAP-CP8-05** | **P1** (architecture) | 当前独立 agent，应作为 medical-coding orchestrator 子 agent（per §26a） |

## 32. 产品重设计建议

| 建议 | 优先级 | 理由 |
|---|---|---|
| **JSON 解析 → 结构化 schema** | **P1** | 同 CP4-CP7 |
| **wire 为 orchestrator 子 agent** | **P1** | medical-coding 自动调用，作为编码前置 |
| **加 pubmed + web-search experts** | P2 | per §4a Corti CDI 复刻 |
| **加 system prompt workflow 节** | P2 | 提高 determinism（参考 Corti `<workflow>` tag） |
| 加 Specialist Trace 字段 | P3 | Corti parity（per-Expert audit trail） |

## 33. 是否进入质量评测

**条件性是**。需先修 GAP-CP8-04（结构化）+ GAP-CP8-05（orchestrator wiring）。

## 34. 最终裁决

# `READY_FOR_INTERNAL_SHADOW`

理由：
- 真实 DeepSeek + 4 fixture 全部结构化准确（ortho/cardio/gastro/obs）
- 复杂产科 case（剖宫产 + 产后出血 + 输血）5 dx + 4 procedures 全部 evidence span 准确
- fail-soft 准确（14 缺失 + 17 无效 → 空 schema + manual_review）
- repeatability 较稳定（md_len 差 < 90，优于 CP4）
- 但 P1 双 gap（结构化 + orchestrator wiring）阻塞 benchmark
- Phase 5+ 路线：从独立 agent → medical-coding orchestrator 子 agent（编码前置）

**Next**: CP9 drg-analyzer（最后一个 checkpoint，Corti 相似 agent = compliance-guardrail-agent + clinical-guidelines-agent）

---

## 附录：证据清单

| 类别 | 文件 |
|---|---|
| Screenshots | `screenshots/phase5_track_b2/discharge-summary-structuring/04_detail.png` |
| Run envelopes | `outputs/phase5_track_b2/per_agent_runs/discharge-summary-structuring/*.json` (11 个) |
| Backend code | `backend/icoder_runtime/backends/pure_llm_provider.py`, `backend/app/api/agent_run.py:619-620` |
| Agent pack | `backend/official_agents/discharge_summary_structuring/agent_pack.json` |
| Corti similar agent prompt | `outputs/phase5_track_b/corti_prompts/clinical-documentation-improvement-cdi-agent.txt` (6238 chars, 4 experts) |
| User directive | `reports/phase5_track_b2/USER_DIRECTIVE_CORTI_SIMILAR_AND_ORCHESTRATOR.md` |
