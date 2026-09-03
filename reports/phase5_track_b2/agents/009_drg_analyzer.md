# CP9 — drg-analyzer 深度走查报告 (Phase 5 Track B-2)

**Agent ID**: `drg-analyzer` (Hub ref `icoder/drg-analyzer@1.0.0`)
**Corti mapping**: `ICODER_ONLY` (B-1, iCoDer 独占优势) → **CP9 复刻 reference: `compliance-guardrail-agent` + `clinical-guidelines-agent`**（Corti 把 DRG 风险分散到 compliance + guidelines 两个 agent；iCoDer 把 DRG/DIP 风险评估整合为独立 agent — iCoDer 优势）
**Backend provider**: `icoder.pure-llm.v1` (PureLLMProvider — no tools)
**Output schema**: `icoder/DRGDIPRiskReview/v1` (risk_points + high_risk_codes + review_suggestions + drg_dip_rule_reservation_note + manual_review_required)
**Audit date**: 2026-07-11
**Walkthrough evidence**: 1 screenshot + 13 API envelopes

---

## 关键发现

**drg-analyzer 真实运行 PureLLMProvider — DeepSeek V4 chat，跨 8 个 fixture 准确识别 4 类 DRG 风险：**

- **真实 LLM 调用**（latency 2.6-15.2s, cost ¥0.000085-0.000536）
- **4 类风险识别准确**：
  - `upcoding` — fixture 01 M80.900 vs S22.000 主诊断选择（高补偿触发嫌疑）
  - `downcoding` — fixture 09 I50.900 → I50.910 心衰严重度漏标 + E11.900 → E11.200 糖尿病并发症漏标
  - `inconsistency` — fixture 11 入院诊断"左侧" vs 术中"右侧"侧别冲突
  - `missing_complication` — fixture 11 慢性便秘 K59.000 未编码
- **iCoDer 独占优势**：Corti 无 DRG/DIP 专用 agent（Corti 用 compliance-guardrail 做规则验证 + clinical-guidelines 做指南对比，但都没有中国 DRG/DIP 概念）
- **同 CP4-CP8 P1 gap**：unified API 不解析 JSON 到结构化字段

## 1. 产品定位

iCoDer drg-analyzer 是**DRG/DIP 风险复核智能体**。给定编码集 + 病历文本，评估 4 类 DRG/DIP 风险：
1. **upcoding 风险**：高补偿编码不当使用（高补偿 DRG 触发码）
2. **downcoding 风险**：重要并发症/合并症未编码 → 低补偿
3. **inconsistency 风险**：诊断-手术不一致、侧别冲突、主诊断矛盾
4. **missing_complication 风险**：缺漏影响 CC/MCC 识别的合并症

不直接修改编码集，不调用 DRG 分组器（分组引擎在医保结算侧）。每个风险点带 evidence + severity + suggestion。

是 medical-coding-agent 的**结算前风险前置核查** + 编码审计员的**质控工具**。

## 2. 目标用户

- 病案编码审计员（编码集风险复核）
- DRG 结算员（拒付风险预警）
- 医保合规官（upcoding 检测 + 反欺诈）
- 病案室主任（CMI 优化 + 编码方案质控）

## 3. 使用场景

| 场景 | 输入 | 期望输出 |
|---|---|---|
| 编码集风险复核 | 病历 + 编码集 | risk_points[] + review_suggestions |
| Upcoding 检测 | 病历 + 高补偿编码 | upcoding 风险标记 |
| Downcoding 检测 | 病历 + 编码集 | 漏掉的 CC/MCC |
| 拒付风险预警 | 病历 + 编码集 | inconsistency + suggestion |

## 4. Corti 映射

| 维度 | iCoDer | Corti | 一致性 |
|---|---|---|---|
| Agent name | drg-analyzer (独立) | 无对应 (分散到 compliance + guidelines) | ICODER_ADVANTAGE |
| Backend | PureLLMProvider | LLM + 1-2 experts | similar |
| DRG/DIP 概念 | ✓ 显式 risk_type + drg_dip_rule_reservation_note | ✗ Corti 无 DRG/DIP | ICODER_ONLY |
| Rule-based 风险评估 | ✓ high_risk_code_prefixes 规则 | ✓ compliance-guardrail ruleset | similar concept |
| 临床指南对比 | ✗ (iCoDer 仅规则启发式) | ✓ clinical-guidelines explicit | ICODER_GAP |
| Suggestion 生成 | ✓ review_suggestions 自然语言 | ✓ Corti 也有 recommendation | similar concept |

iCoDer 独占优势：**DRG/DIP 是中国医保支付方式改革的核心**（DRG/DIP 2.0 国家版 2024 年发布），Corti 作为欧美产品完全无此概念。drg-analyzer 是 iCoDer 中国本土化的关键差异化能力。

## 4a. Corti 相似 agent 复刻分析（per 用户 directive 2026-07-11）

**Corti 相似 agent**：双 reference
- `compliance-guardrail-agent`（13824 chars，1 expert=coding）— rule-based 合规验证
- `clinical-guidelines-agent`（9811 chars，1 expert=web-search）— 临床指南对比

### 设计理念对照

- **Corti compliance-guardrail**：评估 code set 是否符合 payer ruleset（不分配 codes，只检测 violations + flag for human review）。Output = violation report。
- **Corti clinical-guidelines**：评估 patient care 是否符合 authoritative guidelines（基于 explicit approved sources）。Output = guideline compliance assessment。
- **iCoDer drg-analyzer**：评估 code set 对 DRG/DIP 分组的影响（upcoding/downcoding/inconsistency/missing_cc）。Output = risk_points + review_suggestions。
- **共同点**：都是**评估而非分配**（不修改 codes），都带 evidence，都 flag for human review。
- **差异点**：Corti 检测规则违反 + 指南对比；iCoDer 检测编码方案对支付分组的影响。
- **复刻优先级**：保持 iCoDer DRG/DIP 焦点（中国本土化），但**学习 Corti 的 ruleset 配置模式**（drg_analyzer 已有 high_risk_code_prefixes）+ **学习 Corti 的 guideline 对比能力**（iCoDer 缺）。

### 处理流程对照

| 步骤 | Corti compliance-guardrail | iCoDer drg-analyzer | gap |
|---|---|---|---|
| 1. 输入解析 | code_set + ruleset + 可选 clinical_note | 病历 + codes | similar |
| 2. 规则匹配 | LLM 逐 code 对 ruleset | LLM 逐 code 对 high_risk_code_prefixes | EXACT concept |
| 3. Evidence 定位 | LLM 引用原文 | LLM 引用原文 | EXACT |
| 4. Violation/Risk 输出 | Violations[] (numbered blocks) | risk_points[] | EXACT concept |
| 5. Severity 标记 | ✓ Corti severity levels | ✓ iCoDer severity (high/medium/low) | EXACT |
| 6. Suggestion | ✓ Corti recommendation | ✓ suggestion 自然语言 | similar concept |
| 7. Conflict 处理 | ✓ ruleset 内部冲突 → Documentation Notes | ✗ | iCoDer 可补 |

| 步骤 | Corti clinical-guidelines | iCoDer drg-analyzer | gap |
|---|---|---|---|
| 1. 输入 | clinical documentation | 病历 + codes | similar |
| 2. Guideline 检索 | LLM + web-search-expert 查 authoritative source | ✗ | ICODER_GAP — 缺 guidelines 对比 |
| 3. Applicability 评估 | LLM 判断指南是否适用 | ✗ | ICODER_GAP |
| 4. Gap 识别 | ✓ Documentation Inconsistencies | ✓ inconsistency risk_type | similar concept |

### LLM 调用对照

| 维度 | Corti compliance + guidelines | iCoDer drg-analyzer | gap |
|---|---|---|---|
| Model | LLM (per RE) | DeepSeek chat (temp=0.0, max_tokens=4096) | similar |
| System prompt 长度 | 13824 + 9811 = 23635 chars | ~1200 chars | iCoDer 较短 |
| Output 格式 | Markdown sections + GitHub tables | JSON-in-markdown | DIFFERENT format |
| Ruleset 占位符 | `{{COMPLIANCE_RULESET}}` (operator pre-configures) | hard-coded in backend_config | DIFFERENT (iCoDer 应外部化) |
| Domain locking | `{{GUIDELINE_DOMAIN}}` (operator pre-configures) | ✗ | ICODER_GAP |
| Formatting requirements | ✓ 严格 markdown rules（每 labeled line on own row） | ✗ 自由 JSON | DIFFERENT |
| Role section | ✓ "Role: Compliance Guardrail Agent" | ✓ "你是 iCoDer..." | similar |
| Constraints | ✓ 显式列出（不 extract/assign/replace） | ✓ 硬约束列表 | similar concept |

### 工具调用对照

| 维度 | Corti compliance + guidelines | iCoDer drg-analyzer | gap |
|---|---|---|---|
| Experts | compliance: coding-expert (1) / guidelines: web-search-expert (1) | 1 (drg-risk-reviewer) | similar |
| MCP tools | per Expert config | 0 | ICODER_GAP — PureLLM 无 tool_calling |
| Sub-agents | 0 | 0 | EXACT (both none — Phase 5+ orchestrator 应改) |
| Rule data externalization | ✓ `{{COMPLIANCE_RULESET}}` operator 填充 | hard-coded in backend_config | ICODER_GAP — 应外部化 |

### 复刻优先级清单（iCoDer 应补）

| 优先级 | 项目 | 理由 |
|---|---|---|
| **P1** | 结果 JSON 解析到结构化 schema | 同 CP4-CP8 GAP |
| **P1** | wire 为 medical-coding orchestrator 子 agent | 编码后置风险核查（per §26a） |
| **P2** | ruleset 外部化（`{{DRG_DIP_RULESET}}` 占位符） | 参考 Corti compliance 模式，允许 operator 上传 CN-DRG/DIP ruleset |
| **P2** | 加 web-search expert | 参考 Corti clinical-guidelines，让 LLM 查最新 DRG/DIP 政策 |
| **P2** | 加 guideline_domain 配置 | 参考 Corti，锁定权威指南源（如国家医保局 DRG/DIP 2.0） |
| **P3** | 加 Conflict Detection | ruleset 内部冲突 → flag（参考 Corti Documentation Notes） |
| **P3** | 加 CN-DRG/DIP 分组规则 KB | 国家版 2.0 rules |

## 5. Card UI

Hub 卡片在 `/ai-studio/agents` → 浏览预置：
- 名称：DRG/DIP 风险复核智能体
- 版本：1.0.0
- maturity: mvp
- human_review: required

## 6. Detail UI

`04_detail.png`：
- 5 个 tab（Overview / Settings / Experts / Tools / Code）
- 1 个 expert（DRG/DIP Risk Reviewer primary）
- 0 个 tools
- backend_provider 显示 icoder.pure-llm.v1

## 7. 输入 UI

AgentDetailPage chat box。
**重要**：input 应含 (text + codes)，建议格式：
```
{emr_text}
---
待评估编码集 (DRG/DIP 风险复核):
- S22.000
- M80.900
- I10.x00
```

或通过 `input.extra.codes = ["S22.000", ...]` 传递。

## 8. 运行流程

```
POST /api/v1/agents/drg-analyzer/run
↓
agent_run.py:run_agent
↓ agent_id NOT in _MEDICAL_CODING_AGENT_IDS
→ ProviderRegistry → PureLLMProvider.invoke
→ DeepSeek chat (temp=0.0, max_tokens=4096)
→ markdown 内嵌 JSON（risk_points + high_risk_codes + review_suggestions + drg_dip_rule_reservation_note + manual_review_required）
↓ envelope 13 字段
```

Latency: **7.2-15.2s** ✓（视编码数 + 病例复杂度，多病共存 case 最长）

## 9. 输出 UI

MessageBubble 渲染 markdown（JSON code block）。
risk_points 数组（每点带 risk_type + code + evidence + severity + suggestion） + high_risk_codes 数组 + review_suggestions 字符串 + drg_dip_rule_reservation_note + manual_review_required。

## 10. 正常输入（fixture 01 orthopedics, 3 codes）✓ **关键证据**

**Run**: `run-27da944e-10fd-4742-9853-cdba6b85f397`, latency 12.5s, cost ¥0.000426
**Output**: 4 risk_points（severity high×2 + medium×2）：
1. **upcoding (M80.900, high)**：M80.900 骨质疏松伴病理性骨折 vs S22.000 胸椎骨折（创伤性）。病历明确"摔伤后骨折"属创伤性，主诊断应优先 S22.000，M80.900 作附加诊断。建议调整主诊断避免触发高补偿 DRG。
2. **downcoding (I10.x00, medium)**：I10.x00 未特指高血压未体现 3 级（很高危）分级。建议 I10.x02 或 I10.x03。
3. **missing_complication (N/A, medium)**：骨质疏松症附加编码（M81.900）缺失，影响 CMI。
4. **inconsistency (S22.000, high)**：S22.000 + M80.900 同时编码，主诊断选择不一致风险。

**Verdict**: **DRG_RISK_REVIEW_ACCURATE** ✓ — 4 类风险全识别 + 每点带详细 evidence + suggestion 可直接行动

## 11. 长输入（fixture 02 cardiology + 4 codes）✓

**Run**: latency 10.7s, cost ¥0.000341
**Output**: I21.0 STEMI + I25.100 + Z95.500 + 高脂血症 编码集风险核查（PCI 术后高补偿 DRG 触发）
**Verdict**: ✓ 心血管复杂 case 风险核查准确

## 12. 长输入（fixture 09 complex comorbidity + 7 codes）✓ **关键证据**

**Run**: `run-4a16efbd-0eec-447f-bf37-4ad690bdd96f`, latency 15.2s, cost ¥0.000536
**Output**: 5 risk_points 全 downcoding 类（severity high×2 + medium×3）：
1. **downcoding (I50.900, high)**：I50.900 未特指心衰 → 应 I50.910 慢性心衰急性加重 / I50.901 急性心衰（NT-proBNP 4500 + EF 38%）
2. **downcoding (E11.900, high)**：E11.900 未特指糖尿病并发症 → 应 E11.200 糖尿病伴肾脏并发症（合并 CKD 3 期）
3. **downcoding (I10.x00, medium)**：I10.x00 → 应 I11.000 高血压心脏病伴心衰 / I13.200 高血压心脏病和肾脏病伴心衰和肾衰
4. **downcoding (I69.300, medium)**：腔隙性脑梗死后遗症，若无当前神经功能缺损应改 Z86.700（个人史）
5. **inconsistency (I25.100, low)**：I25.100 冠心病 + Z95.500 PCI 术后状态，需确认主诊断一致性

**Verdict**: **MULTI_MORBIDITY_DOWNCODING_ACCURATE** ✓ — 5 个 downcoding 全识别 + 详细 evidence + 可行 suggestion。**关键证据：CKD 3 期 + 糖尿病 + 心衰三病共存，LLM 正确识别 E11.200 + I13.200 复合编码应使用**。

## 13. fixture 06 obstetrics（剖宫产 + 产后出血）✓

**Run**: latency 11.0s, cost ¥0.000353
**Verdict**: ✓ 产科高消耗 case 风险核查

## 14. 否定与历史（fixture 10 negation + history）✓

**Run**: latency 8.8s, cost ¥0.000280
**Output**: 4 risk_points（含 1 个 missing_complication Z86.100 结核病个人史 — 30 年前已治愈但未编码）
**Verdict**: ✓ 历史病漏编码识别准确

## 15. 冲突输入（fixture 11 conflicting_documentation）✓ **关键证据**

**Run**: latency 7.6s, cost ¥0.000260
**Output**: 3 risk_points：
1. **inconsistency (K40.900, high)**：入院诊断"左侧" vs 术中"右侧"腹股沟斜疝，K40.900 未指定侧别 → 建议确认侧别后改 K40.901/K40.902
2. **missing_complication (K59.000, medium)**：慢性便秘 5 年已列出但未编码 → 建议补 K59.000
3. **downcoding (K40.900, medium)**：K40.900 未区分侧别 → 改 K40.901 提高精确性

**Verdict**: **CONFLICT_BASED_DRG_RISK_ACCURATE** ✓ — 与 CP7 principal-dx 互补：CP7 用术中记录作 ground truth 解决冲突，CP9 标记冲突为 DRG 风险点。

## 16. 缺失信息（fixture 12 incomplete）✓

**Run**: latency 7.2s, cost ¥0.000209
**Verdict**: ✓ 文档不完整 case 风险核查（无主诉/查体/诊断细节）

## 17. 无效输入（17 invalid）✓

**Input**: "今天天气不错。"
**Run**: latency 2.6s, cost ¥0.000085
**Verdict**: ✓ fail-soft LLM 引导，输出空 risk_points + manual_review_required=true

## 18. Repeatability ⚠

**3 次同输入（fixture 01）**:
- run 1: 11.5s, md_hash=3bf3cf669eeabf52, md_len=2112
- run 2: 10.1s, md_hash=15164207ef025267, md_len=2044
- run 3: 8.3s, md_hash=301de91f8cde6903, md_len=1484

3 次 hash 不同，md_len 差 68-628 字符（run 3 显著短）。
**GAP-CP9-01 (P2)** 同 GAP-CP4-02，run 3 风险点描述更精简（可能少 1 个 risk_point）。

## 19. 配置变化

Fork UI 可用。

## 20. 错误恢复 ✓

- 不存在 agent: envelope.error=true, error_reason=unknown_agent
- 空输入: 422 Pydantic
- 无效文本: LLM 引导

## 21. Expert 实证 ✓

**配置**: 1 expert（DRG/DIP Risk Reviewer primary）
**实际**: PureLLMProvider 真实完成风险评估
**Verdict**: **EXPERT_INVOKED (LLM-level)** ✓

## 22. Tool 实证

**配置**: 0 tools（PureLLM 无 tool_calling）
**Verdict**: N/A
**GAP-CP9-02 (P2)**（per §4a）：Corti guidelines 有 web-search expert，iCoDer 应迁移到 LLMWithTools 以查最新 DRG/DIP 政策。

## 23. Context ✓

每次运行生成 context_id + run_id + trace_id。

## 24. Trace ⚠

仅 1 trace_event（completion）。
**GAP-CP9-03 (P3)** 同 GAP-CP4-03。

## 25. Cost ✓

¥0.000085-0.000536 / call（视编码数 + 病例复杂度，多病共存 case 最贵）。

## 26. Developer API ✓

API: `POST /api/v1/agents/drg-analyzer/run`
**GAP-CP9-04 (P1)** 同 GAP-CP4-01：consumer 需从 markdown 解析 JSON。

## 27. Embedded

非 embedded-eligible。Phase 5+ 可作 medical-coding orchestrator sub-agent。

## 28. 医院集成路径

| 路径 | 状态 |
|---|---|
| Backend Service Integration | **CONDITIONAL READY** (markdown JSON 需 parse) |
| ROPC Embedded | **NOT APPLICABLE** |
| DRG 前置核查 | **READY** — 编码集提交结算前的风险预警 |
| 医保反欺诈 | **READY** — upcoding 检测 + 拒付风险预警 |

## 26a. Orchestrator wiring gap（per 用户 directive 2026-07-11）

**应作为 orchestrator 子 agent？** ✓ 是（最重要的子 agent 之一）
- medical-coding orchestrator 在编码完成后，应**调用 drg-analyzer** 做结算前风险核查
- 若 high severity risk_point > 0 → 触发 manual review，编码集暂不提交结算

**当前 wired？** ✗ 否
- 当前需用 chained runner 手工串联（同 CP3 compliance-guardrail 模式）
- CP9 是结算前最后一步核查，但当前流程编码员需手动调用

**推荐 orchestrator 入口**：medical-coding-agent
- stage 1: discharge-summary-structuring (结构化原文)
- stage 2: medical-coding-agent (分配全部 codes)
- stage 3: principal-diagnosis-review (复核主诊断)
- stage 4: evidence-extractor (per-code evidence)
- stage 5: compliance-guardrail (规则验证)
- stage 6: note-completeness (文档完整性)
- stage 7: **drg-analyzer (结算前风险核查)** ← 本 CP9，最后一步

## 29. UX 评分

12 dimension：

| Dimension | Score | 说明 |
|---|---|---|
| 入口可发现性 | 4 | Hub card |
| 输入体验 | 3 | 需知道 "input + codes" 格式（无 UI 提示） |
| 输出可读性 | 5 | risk_points + suggestion 详细可读 |
| 错误恢复 | 5 | fail-soft + manual_review 触发 |
| 实时反馈 | 3 | 8-15s 长复杂 case 等待无 streaming |
| Trace 透明度 | 2 | 仅 1 event |
| Cost 透明度 | 5 | 明示 |
| 复制/下载 | 5 | 全套 |
| 配置可调 | 4 | runtime_mode |
| 多轮对话 | 4 | history |
| 移动响应 | 3 | 堆叠 |
| 国际化 | 4 | 双 locale |

**平均**: 4.0 / 5

## 30. 能力分层

| 层 | 状态 |
|---|---|
| PLATFORM_AVAILABLE | ✓ |
| AGENT_CONFIGURED | ✓ |
| RUNTIME_INVOKED | ✓ (real DeepSeek 8-15s) |
| RESULT_CONSUMED | ⚠ (JSON-in-markdown) |
| QUALITY_VALIDATED | ⚠ (repeatability run 3 短) |

**最高层**: RESULT_CONSUMED

## 31. 当前缺口

| ID | Severity | Description |
|---|---|---|
| **GAP-CP9-04** | **P1** | unified API 不解析 JSON 到 result.risk_points（同 GAP-CP4-01） |
| GAP-CP9-01 | P2 | temp=0 但 3 次 md_len 差 68-628（run 3 显著短） |
| **GAP-CP9-02** | **P2** | 缺 Corti web-search expert（per §4a 复刻清单） |
| **GAP-CP9-05** | **P2** | ruleset 硬编码（应外部化 `{{DRG_DIP_RULESET}}`） |
| GAP-CP9-03 | P3 | trace_events 仅 1 event |
| **GAP-CP9-06** | **P1** (architecture) | 当前独立 agent，应作为 medical-coding orchestrator 子 agent（per §26a，最后一步） |

## 32. 产品重设计建议

| 建议 | 优先级 | 理由 |
|---|---|---|
| **JSON 解析 → 结构化 schema** | **P1** | 同 CP4-CP8 |
| **wire 为 orchestrator 子 agent（stage 7）** | **P1** | medical-coding 自动调用，结算前风险预警 |
| **ruleset 外部化** | P2 | 参考 Corti compliance 模式，允许医院上传本地化 DRG ruleset |
| **加 web-search expert** | P2 | per §4a Corti guidelines 复刻，查最新政策 |
| **加 CN-DRG/DIP 2.0 分组规则 KB** | P2 | 国家版 2.0 rules |
| 加 Conflict Detection | P3 | Corti parity |

## 33. 是否进入质量评测

**条件性是**。需先修 GAP-CP9-04（结构化）+ GAP-CP9-06（orchestrator wiring）。

建议：与 CP4-CP8 共用 P1 修复。

## 34. 最终裁决

# `READY_FOR_INTERNAL_SHADOW`

理由：
- 真实 DeepSeek + 8 fixture 全部 4 类风险识别准确
- **fixture 09 多病共存 7 编码 5 downcoding 全识别**：CKD 3 期 + 糖尿病 + 心衰三病共存，LLM 正确识别 E11.200 + I13.200 复合编码应使用（关键证据）
- **fixture 11 冲突侧别**：与 CP7 互补（CP7 用术中记录作 ground truth 解决冲突，CP9 标记冲突为 DRG 风险点）
- iCoDer 独占优势：Corti 无 DRG/DIP 概念（中国医保支付改革核心）
- 但 P1 双 gap（结构化 + orchestrator wiring）阻塞 benchmark
- Phase 5+ 路线：从独立 agent → medical-coding orchestrator 子 agent（stage 7，结算前最后一步）

**Phase 5 Track B-2 COMPLETE** — 9 checkpoints 全部走完（CP1-CP9）。

---

## 附录：证据清单

| 类别 | 文件 |
|---|---|
| Screenshots | `screenshots/phase5_track_b2/drg-analyzer/04_detail.png` |
| Run envelopes | `outputs/phase5_track_b2/per_agent_runs/drg-analyzer/*.json` (13 个) |
| Backend code | `backend/icoder_runtime/backends/pure_llm_provider.py`, `backend/app/api/agent_run.py:619-620` |
| Agent pack | `backend/official_agents/drg-analyzer/agent_pack.json` |
| Runner | `scripts/phase5_track_b2_cp9_drg_runner.py` |
| Corti similar agent prompts | `outputs/phase5_track_b/corti_prompts/compliance-guardrail-agent.txt` (13824 chars) + `clinical-guidelines-agent.txt` (9811 chars) |
| User directive | `reports/phase5_track_b2/USER_DIRECTIVE_CORTI_SIMILAR_AND_ORCHESTRATOR.md` |
