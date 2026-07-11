# CP3 — compliance-guardrail-agent 深度走查报告 (Phase 5 Track B-2)

**Agent ID**: `compliance-guardrail-agent` (Hub ref `icoder/compliance-guardrail-agent@1.0.0`)
**Corti mapping**: `compliance-guardrail-agent` (EXACT parity)
**Backend provider**: `icoder.rule-engine.v1`
**Audit date**: 2026-07-11
**Walkthrough evidence**: 1 screenshot + 4 chained API envelopes (medical-coding → compliance)

---

## 关键发现

**compliance-guardrail-agent 真实运行（非 skeleton）— 15 条规则全 fire — 但暴露 ICD-10-CN 本地化规则缺口：**

- **R002 规则验证 WHO ICD-10 格式**（字母+2位数字+可选 .1-4 位数字）
- **iCoDer medical-coding-agent 返回 ICD-10-CN 6 位细分码**（如 `I10.x00x002`）
- **结果**：CN 码被 R002 误判为格式无效（误报）

这是一个**规则本地化 P1 缺口** — iCoDer 编码端是 CN-native 但校验端用 WHO 格式。

## 1. 产品定位

iCoDer compliance-guardrail-agent 是**合规护栏智能体**。输入 medical-coding 输出 + 病案，按预设规则集（R001-R012 + DRG001/002 + DIP001）校验编码合规性，输出 issues + risk_flags + 人工复核标志。

是 medical-coding-agent 的**强制下游** — 编码 → 校验 → 合规门禁。

## 2. 目标用户

- 编码合规审计员
- 病案室主任（出科前审核）
- DRG 结算合规员

## 3. 使用场景

| 场景 | 输入 | 期望输出 |
|---|---|---|
| 编码集合规校验 | coding_output + 病案 | issues + severity |
| DRG 风险评估 | 多编码集 | DRG001/002 + DIP001 fired |
| 编码规则查询 | topic | KB lookup |

## 4. Corti 映射

| 维度 | iCoDer | Corti | 一致性 |
|---|---|---|---|
| Agent name | compliance-guardrail-agent | compliance-guardrail-agent | EXACT |
| Backend | RuleEngineProvider + CodingEngineAdapter | LLM + tools (per RE) | DIFFERENT (iCoDer pure rules, Corti LLM-augmented) |
| Rules | 15 hard-coded (R001-R012 + DRG + DIP) | Corti uses guideline RAG | DIFFERENT approach |

iCoDer 优势：**规则可审计 + 决定性**（同一输入永远同一输出）。Corti 用 LLM 可能给出不同解释。

## 5. Card UI

Hub card 在 Agents 页（screenshot captured via 04_detail navigation）。
- 名称：合规护栏智能体
- 版本：1.0.0
- runnable: true

## 6. Detail UI

`04_detail.png`：
- 标准 5 个 tab（Overview / Settings / Experts / Tools / Code）
- 1 个 expert（Rule Engine）
- 1 个 tool（evaluate_compliance）

## 7. 输入 UI

AgentDetailPage chat（无独立 page）。
**关键**：纯文本输入**不工作** — provider 返回 `"RuleEngineProvider: empty or unrecognized input."`

正确用法：
```json
{
  "input": {
    "text": "...",
    "extra": {
      "coding_output": {
        "primary_diagnosis": {"code": "M80.08", ...},
        "secondary_diagnoses": [...],
        "procedures": [...]
      }
    }
  }
}
```

**GAP-CP3-01 (P1)**：UI 没暴露"如何调用此 agent"的指引 — 用户用 chat 输入纯文本会得到无效响应。

## 8. 运行流程

```
POST /api/v1/agents/compliance-guardrail-agent/run
{input: {text: ..., extra: {coding_output: {...}}}}
↓
agent_run.py:run_agent
↓ agent_id NOT in _MEDICAL_CODING_AGENT_IDS
→ ProviderRegistry → RuleEngineProvider
→ _validate_coding_output(input_data)
→ MedicalCodingOutputSchema.from_dict(coding_output)
→ CodingEngineAdapter.validate(schema)
→ fires 15 rules: R001-R012 + DRG001/002 + DIP001
↓ envelope 13 字段
```

Latency: **15-25ms**（纯 Python 规则匹配，无 LLM call）

## 9. 输出 UI

envelope.result.issues 数组 + raw_provider_response.fired_rules + quality_flags。UI 显示在 MessageBubble 的 Rendered/JSON 双 tab。

## 10. 正常输入（fixture 01 orthopedics chained）⚠

**Input**: medical-coding-agent(fix 01) → 2 codes (M80.08 + I10.x00x002)
**Run**: `run-f21c20cf-5cf7-44b7-ac63-c43edec1119b`, latency 15-25ms
**Fired**: 15/15 rules
**Issues**: 1 (R002 error: "编码格式无效: I10.x00x002")
**Verdict**: 规则引擎工作，但 R002 误判 CN 码 — **RULE_LOCALIZATION_GAP**

## 11. 长输入（fixture 02 cardiology chained）✓

**Input**: medical-coding-agent(fix 02) → 7 codes (I21.0 + I25.103 + E78.500 + Z72.000 + 3 PCI procedures)
**Run**: chained, 15 rules fired
**Issues**: **0** ✓
**Verdict**: 心血管 case 全过 — codes 用 ICD-10 标准格式（.1-3 位数字）

## 12-15. 其他 fixtures

- 03_respiratory: 1 R002 issue（I10.x00x002）
- 09_complex_comorbidity: 1 R002 issue（I10.x00x002）

模式一致：只要编码集含 `I10.x00x002` 就会触发 R002。

## 16. Repeatability ✓

确定性 100% — 同一 coding_output 输入永远同一 issues 输出（规则引擎无随机性）。

## 17. 配置变化

n/a（无 LLM 调整空间，规则硬编码）

## 18. 错误恢复 ✓

- 空文本输入（无 extra）：返回 warning "empty or unrecognized input"（不报错，fail-soft）
- coding_output schema 不匹配：返回 fail + parse error message
- 不存在的 agent：standard 404 unknown_agent

## 19. Expert 实证 ✓

配置：1 个 expert（Rule Engine）
实际：**真实 invoke** — 15 规则全部 fire（trace_events + raw_provider_response.fired_rules 双证据）
**Verdict**: **EXPERT_INVOKED** ✓（vs CP2 LLMWithTools skeleton）

## 20. Tool 实证 ✓

配置：1 个 tool（evaluate_compliance）
实际：通过 CodingEngineAdapter（Python 函数）执行，无 MCP JSON-RPC dispatch
**Verdict**: PROVIDER_LEVEL_INVOKED（非 MCP-level，但实际工作）

## 21. Context ✓

每次运行生成 context_id + run_id + trace_id，写入 envelope。

## 22. Trace ⚠

仅 1 个 trace_event（`completion`）。无 per-rule trace，无 fired_rules 时序。
**GAP-CP3-02 (P3)**：trace_events 应包含每规则 fire 记录（R001: pass / R002: fail / ...）。

## 23. Cost ✓

`cost: {}` — 纯规则无 LLM，零成本。生产部署也是 0 成本。

## 24. Developer API ✓

API: `POST /api/v1/agents/compliance-guardrail-agent/run`
Backend: `RuleEngineProvider.invoke` → `_validate_coding_output` → `MedicalCodingOutputSchema.from_dict` → `CodingEngineAdapter.validate`
Response: 13-field envelope + issues + fired_rules + quality_flags

## 25. Embedded

CP3 不做 embedded smoke（不在 4 个 embedded-eligible 列表中）。

## 26. 医院集成路径

| 路径 | 状态 | 说明 |
|---|---|---|
| Backend Service Integration | **READY** | 规则引擎确定性，可作为编码后强制门禁 |
| ROPC Embedded | N/A | |
| 规则配置 UI | **MISSING** | 当前规则硬编码在 Python，医院无法自定义 |

## 27. UX 评分

12 dimension：

| Dimension | Score | 说明 |
|---|---|---|
| 入口可发现性 | 4 | Hub card（扣 1：纯文本输入不工作，用户困惑） |
| 输入体验 | 2 | chat UI 不能用，必须 API + structured extra |
| 输出可读性 | 4 | issues + fired_rules + quality_flags 清晰 |
| 错误恢复 | 5 | fail-soft 设计 |
| 实时反馈 | 5 | <25ms |
| Trace 透明度 | 2 | 仅 1 event，无 per-rule 时序 |
| Cost 透明度 | 5 | 永远 0 |
| 复制/下载 | 5 | 全套按钮 |
| 配置可调 | 1 | 无运行时可调参数 |
| 多轮对话 | 1 | 无状态 |
| 移动响应 | 3 | 双栏堆叠 |
| 国际化 | 4 | 双 locale |

**平均**: 3.42 / 5（输入体验 + trace 是主要扣分项）

## 28. 能力分层（5 层）

| 层 | 状态 | 证据 |
|---|---|---|
| PLATFORM_AVAILABLE | ✓ | Hub |
| AGENT_CONFIGURED | ✓ | pack + 1 expert + 1 tool + 15 rules |
| RUNTIME_INVOKED | ✓ | 真实 invoke，15 规则 fire |
| RESULT_CONSUMED | ✓ | issues + fired_rules + quality_flags |
| QUALITY_VALIDATED | ⚠ | R002 误报 CN 码，规则集需本地化升级 |

**最高层**: RESULT_CONSUMED（差一步到 QUALITY_VALIDATED）

## 29. 当前缺口

| ID | Severity | Description |
|---|---|---|
| **GAP-CP3-01** | **P1** | R002 规则验证 WHO ICD-10 格式，拒绝 ICD-10-CN 6 位细分码（I10.x00x002）— 规则本地化 |
| GAP-CP3-02 | P2 | UI 无指引告诉用户 chat 纯文本不工作，必须 API + coding_output |
| GAP-CP3-03 | P3 | trace_events 无 per-rule fire 记录 |
| GAP-CP3-04 | P3 | 规则硬编码 Python，医院无法自定义 |

## 30. 产品重设计建议

| 建议 | 优先级 | 理由 |
|---|---|---|
| **R002 升级为 ICD-10-CN 格式** | **P1** | 接受 `.x00x002` 6 位细分，否则永远误报 |
| 加 coding_output template 到 UI | P2 | 用户点 sample 看到"如何调用此 agent" |
| trace 加 per-rule fire 事件 | P3 | 审计透明度 |
| 规则配置 UI（YAML 编辑器） | P3 | 医院自定义 |
| 规则版本管理 | P4 | ICD-10-CN 升版时迁移 |

## 31. 是否进入质量评测

**条件性是**。规则引擎本身工作，但 R002 本地化 bug 必须先修。
建议：先关闭 R002（或升级 regex）→ 进入 shadow 模式 → 累积 1 周生产数据 → 正式 benchmark。

## 32. 最终裁决

# `READY_FOR_INTERNAL_SHADOW`

理由：
- 5 层能力达 RESULT_CONSUMED（vs CP2 仅 RUNTIME_INVOKED）
- 15 规则全部 fire + deterministic（同输入永远同输出）
- 心血管 case（fixture 02）0 issues，证明规则集对标准 ICD-10 码工作正常
- **但** R002 误判 CN 码需修 → 进入 shadow 累积数据后再 benchmark
- Corti 用 LLM-augmented compliance，iCoDer 用纯规则 — iCoDer 更可审计但需 CN 规则集

**Next**: CP4 note-completeness-agent

---

## 附录：证据清单

| 类别 | 文件 |
|---|---|
| Screenshots | `screenshots/phase5_track_b2/compliance-guardrail-agent/04_detail.png` |
| Run envelopes | `outputs/phase5_track_b2/per_agent_runs/compliance-guardrail-agent/*.json` (5 个) |
| Fixture | `fixtures/phase5_track_b2/01_orthopedics.json` 等 |
| Backend code | `backend/icoder_runtime/backends/rule_engine_provider.py:112-152` (invoke), `:239-290` (_validate_coding_output), `:395-422` (CodingEngineAdapter.validate + R001) |
| Rule set | `compliance_services/medical_coding_rule_set.py` (R001-R012 definitions) |
| Chained runner | `scripts/phase5_track_b2_cp3_coding_output_runner.py` |
