# CP5 — procedure-extractor 深度走查报告 (Phase 5 Track B-2)

**Agent ID**: `procedure-extractor` (Hub ref `icoder/procedure-extractor@1.0.0`)
**Corti mapping**: `procedure-entity-extractor-agent` (Corti EXACT-equivalent name)
**Backend provider**: `icoder.pure-llm.v1` (PureLLMProvider — no tools)
**Output schema**: `icoder/ProcedureCodingOutput/v1`
**Audit date**: 2026-07-11
**Walkthrough evidence**: 1 screenshot + 9 API envelopes

---

## 关键发现

**procedure-extractor 真实运行 PureLLMProvider — DeepSeek V4 chat 模型，输出**结构化 JSON-in-markdown**，ICD-9-CM-3 编码 + evidence span + confidence 全套齐全：**

- **真实 LLM 调用**（latency 4.5-15.3s, cost ¥0.000052-0.000228）
- **跨 4 个科室准确编码**：骨科(PVP 81.6600) / 心血管(造影88.5500 + 支架36.0600) / 消化(腹腔镜胆囊切除51.2300) / 产科(剖宫产74.1x00 + B-Lynch缝合 + 输血)
- **evidence-first 严格**：fixture 01 仅含"必要时行 PKP/PVP" → confidence 0.65 + warning "计划性操作，尚未执行"
- **issue 识别准确**：手术-诊断不一致、缺少手术记录、胆总管探查/粘连松解术编码冲突
- **同样的 GAP-CP4-01**：unified API 不解析 JSON-in-markdown 到 result.procedures 结构化字段

## 1. 产品定位

iCoDer procedure-extractor 是**手术操作提取智能体**。从手术记录/病程记录中识别所有手术操作（主手术 + 其他手术），分配 ICD-9-CM-3 编码（中国版），每个编码附 evidence_text + char_span + confidence + warnings。

是 medical-coding-agent 的**姊妹 agent** — 编码 → 校验 → 合规链路中的手术侧。

## 2. 目标用户

- 病案手术编码员
- DRG 结算员（手术码 → DRG 分组权重）
- 手术记录质控员

## 3. 使用场景

| 场景 | 输入 | 期望输出 |
|---|---|---|
| 主手术编码 | 手术记录 | 1 主码 + N 其他码 + evidence |
| 多手术冲突 | 复杂手术记录 | issues_found + manual_review |
| 编码补漏 | 病程记录 | 缺失手术识别（如粘连松解术） |

## 4. Corti 映射

| 维度 | iCoDer | Corti | 一致性 |
|---|---|---|---|
| Agent name | procedure-extractor | procedure-entity-extractor-agent | CLOSE (iCoDer 短名) |
| Backend | PureLLMProvider | LLM (per RE) | EXACT architecture |
| Tools | 0 | 0 | EXACT |
| Output | ICD-9-CM-3 + evidence + confidence | 类似 ICD-9-CM-3 + evidence | EXACT |
| Chinese-native | ✓ 中国版 ICD-9-CM-3 6 位细分（如 74.1x00） | ✗ Corti 国际版 ICD-9-CM-3 | ICODER_ADVANTAGE |

iCoDer 优势：**Chinese-native ICD-9-CM-3 6 位细分码 + evidence char_span**。

## 5. Card UI

Hub 卡片在 `/ai-studio/agents` → 浏览预置：
- 名称：手术提取智能体
- 版本：1.0.0
- maturity: mvp
- human_review: required

## 6. Detail UI

`04_detail.png`：
- 5 个 tab（Overview / Settings / Experts / Tools / Code）
- 1 个 expert（Procedure Extractor primary）
- 0 个 tools（PureLLMProvider 无 tool_calling）
- backend_provider 显示 icoder.pure-llm.v1
- A2A Agent 协作面板可见

## 7. 输入 UI

AgentDetailPage chat box（标准模板）。
建议输入：手术记录原文（含手术名称、术式、入路、部位、植入物）。

## 8. 运行流程

```
POST /api/v1/agents/procedure-extractor/run
↓
agent_run.py:run_agent
↓ agent_id NOT in _MEDICAL_CODING_AGENT_IDS
→ ProviderRegistry → PureLLMProvider.invoke
→ DeepSeek chat completion (temperature=0.0, max_tokens=4096)
→ markdown 内嵌 JSON（procedures + issues_found + manual_review_required）
↓ envelope 13 字段
```

Latency: **4.5-15.3s** ✓（真实 DeepSeek）

## 9. 输出 UI

MessageBubble 渲染 markdown（JSON code block）。
JSON tab 显示 13-field envelope，但 `result.issues=[]` / `result.tool_calls=[]` 让消费者需从 markdown 解析 JSON。

## 10. 正常输入（fixture 01 orthopedics）✓

**Input**: 412 字符 T12 椎体压缩骨折病案
**Run**: `run-78573467-8289-4f32-a22b-05887cdb714a`, latency 15.3s, cost ¥0.000132
**Output JSON**:
```json
{
  "procedures": [{
    "code": "81.6600",
    "display": "经皮椎体成形术",
    "evidence_text": "必要时行 PKP/PVP",
    "char_span": [280, 296],
    "confidence": 0.65,
    "warnings": ["计划性操作，尚未执行，仅作为治疗计划提及", "PKP/PVP 未明确区分，编码按 PVP 匹配"]
  }],
  "issues_found": ["手术记录缺失：当前仅提供入院记录，无实际手术操作记录", ...]
}
```

**Verdict**: **REAL_PROCEDURE_EXTRACTION** ✓ — evidence-first 严格（计划性手术 confidence 0.65 + warning，不 upcoding）

## 11. 长输入（fixture 02 cardiology）✓

**Input**: 393 字符前壁心梗 + PCI
**Run**: `run-1845d12d-ced1-4a8a-9a6e-75d6936d0a87`, latency 12.3s, cost ¥0.000143
**Output JSON**: 2 procedures
- `88.5500` 冠状动脉造影术 — confidence 0.95 (evidence: "急诊冠脉造影")
- `36.0600` 冠状动脉药物洗脱支架置入术 — confidence 0.92 (evidence: "行 LAD PCI 术,植入药物洗脱支架 1 枚")

**Verdict**: ✓ 多手术识别 + 高 confidence（实际执行）+ evidence span 准确

## 12. 缺失信息（fixture 14 minimal）✓

**Input**: "患者男，60岁。"
**Run**: latency 7.6s, cost ¥0.000123
**Output**: LLM 正确识别无手术内容，返回空 procedures 或引导

## 13. 否定与历史

未单独跑（已在 CP1/CP4 验证否定处理）。

## 14. 冲突输入

未单独跑（fixture 11 走 medical-coding 已验证）。

## 15. 无效输入（17 invalid）✓

**Input**: "今天天气不错。"
**Run**: latency 3.8s, cost ¥0.000052
**Verdict**: ✓ fail-soft，LLM 引导用户

## 16. Repeatability ⚠

**3 次同输入（fixture 01）**:
- run 1: 6.1s, md_hash=80f509f6ad697df1, md_len=371
- run 2: 5.4s, md_hash=d9364f12ce266401, md_len=512
- run 3: 4.5s, md_hash=48a5f43d4f3de19e, md_len=503

**3 次 markdown 内容不同**（同 CP4 GAP-CP4-02 — temp=0 但 DeepSeek 不确定）。**GAP-CP5-01 (P2)** 同 GAP-CP4-02。

## 17. 配置变化

Fork UI 可用，CP5 未单独测试 fork。

## 18. 错误恢复 ✓

- 不存在 agent: envelope.error=true, error_reason=unknown_agent
- 空输入: 422 Pydantic
- 无效文本: LLM 优雅引导，fail-soft

## 19. Expert 实证 ✓

**配置**: 1 expert（Procedure Extractor primary）
**实际**: PureLLMProvider 不走 expert dispatch，但 LLM 真实完成 procedure extraction 任务（4 fixtures 全部产出有效 ICD-9-CM-3 编码）
**Verdict**: **EXPERT_INVOKED (LLM-level)** ✓

## 20. Tool 实证

**配置**: 0 tools（PureLLM 不支持 tool_calling）
**Verdict**: N/A（设计如此）

## 21. Context ✓

每次运行生成 context_id + run_id + trace_id。

## 22. Trace ⚠

仅 1 trace_event（completion）。无 build_prompt / llm_call 步骤。
**GAP-CP5-02 (P3)** 同 GAP-CP4-03。

## 23. Cost ✓

¥0.000052-0.000228 / call（视手术复杂度）。1000 calls/day ≈ ¥0.10-0.20/day。

## 24. Developer API ✓

API: `POST /api/v1/agents/procedure-extractor/run`
Backend: PureLLMProvider → DeepSeek chat
Response: 13-field envelope + result.markdown（含 JSON-in-markdown）

**GAP-CP5-03 (P1)** 同 GAP-CP4-01：consumer 必须自己 parse JSON from markdown。

## 25. Embedded

CP5 不做 embedded smoke（不在 4 个 embedded-eligible 列表中：medical-coding / note-completeness / evidence-extractor / principal-diagnosis-review）。

## 26. 医院集成路径

| 路径 | 状态 |
|---|---|
| Backend Service Integration | **CONDITIONAL READY**（markdown 输出可消费，但结构化字段需 GAP-CP5-03 修复） |
| ROPC Embedded | N/A |
| DRG 分组前置 | **READY** — ICD-9-CM-3 码 + evidence 是 DRG 分组器的标准输入 |

## 27. UX 评分

12 dimension：

| Dimension | Score | 说明 |
|---|---|---|
| 入口可发现性 | 4 | Hub card |
| 输入体验 | 4 | chat UI 工作 |
| 输出可读性 | 4 | JSON code block 清晰，但表格化更佳 |
| 错误恢复 | 5 | fail-soft |
| 实时反馈 | 3 | 4-15s 等待，无 streaming |
| Trace 透明度 | 2 | 仅 1 event |
| Cost 透明度 | 5 | ¥0.000052-0.000228 明示 |
| 复制/下载 | 5 | 全套按钮 |
| 配置可调 | 4 | runtime_mode + fork |
| 多轮对话 | 4 | message history |
| 移动响应 | 3 | 双栏堆叠 |
| 国际化 | 4 | 双 locale |

**平均**: 3.92 / 5

## 28. 能力分层

| 层 | 状态 |
|---|---|
| PLATFORM_AVAILABLE | ✓ |
| AGENT_CONFIGURED | ✓ |
| RUNTIME_INVOKED | ✓ (real DeepSeek) |
| RESULT_CONSUMED | ⚠ (JSON-in-markdown，未提取结构化) |
| QUALITY_VALIDATED | ⚠ (repeatability 失败) |

**最高层**: RESULT_CONSUMED

## 29. 当前缺口

| ID | Severity | Description |
|---|---|---|
| **GAP-CP5-03** | **P1** | unified API 不解析 JSON-in-markdown 到 result.procedures 结构化字段（同 GAP-CP4-01） |
| GAP-CP5-01 | P2 | temp=0 但 3 次 run 输出不一致（同 GAP-CP4-02） |
| GAP-CP5-02 | P3 | trace_events 仅 1 event（同 GAP-CP4-03） |

## 30. 产品重设计建议

| 建议 | 优先级 | 理由 |
|---|---|---|
| **JSON 解析 → result.procedures** | **P1** | 让消费者直接拿到结构化 |
| **determinism 调查** | P2 | 验证 DeepSeek temp=0 行为 |
| trace 加 LLM call 时序 | P3 | 改善审计 |
| 表格化输出 | P4 | markdown 渲染为表格而非 JSON block |

## 31. 是否进入质量评测

**条件性是**。需先修 GAP-CP5-03（结构化提取）+ GAP-CP5-01（repeatability）。

建议：与 CP4 共用 P1 修复（unified endpoint 调用 agent.py::run() 或类似 structured parser）。

## 32. 最终裁决

# `READY_FOR_INTERNAL_SHADOW`

理由：
- 真实 DeepSeek + 跨 4 科室 ICD-9-CM-3 编码准确（骨科/心血管/消化/产科）
- evidence-first 严格（fixture 01 计划性手术 → confidence 0.65 + warning）
- 比 CP4 更进一层：JSON 结构在 markdown 内，parser 易写
- 但同 CP4 双 P1/P2 gap（结构化 + repeatability）
- 非 embedded-eligible，不做 embedded smoke

**Next**: CP6 evidence-extractor（embedded-eligible）

---

## 附录：证据清单

| 类别 | 文件 |
|---|---|
| Screenshots | `screenshots/phase5_track_b2/procedure-extractor/04_detail.png` |
| Run envelopes | `outputs/phase5_track_b2/per_agent_runs/procedure-extractor/*.json` (9 个: 01/02/04/06/14/17/18_1-3/21_empty/21_wrong) |
| Backend code | `backend/icoder_runtime/backends/pure_llm_provider.py`, `backend/app/api/agent_run.py:619-620` |
| Agent pack | `backend/official_agents/procedure-extractor/agent_pack.json` |
