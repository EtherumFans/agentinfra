# Phase 4-F3 — 4 P0 Agent Inventory

**Date:** 2026-07-10
**Scope:** 4 P0 non-Medical-Coding agents per prompt §2.1. Each agent documents: agent_id / name / description / use_case / runtime_mode / experts / input_schema / output_schema / api endpoint / status / demo case.

---

## 1. evidence-extractor (证据提取智能体)

| Field | Value |
|---|---|
| **agent_id** | `evidence-extractor` |
| **agent_ref** | `icoder/evidence-extractor@1.0.0` |
| **name** | 证据提取智能体 / Coding Evidence Agent |
| **description** | iCoDer Coding Evidence Agent (Corti-style). 给定病历文本 + 编码集, 为每个编码定位原文证据 span 并评估证据强度 (直接/间接/否定)。AI-assisted — 不分配新编码, 仅评估已有编码的证据。 |
| **use_case** | `coding_revenue_cycle` |
| **default_runtime_mode** | `a2a_pure_llm` |
| **available_runtime_modes** | `[a2a_pure_llm]` |
| **backend_provider** | `icoder.pure-llm.v1` (DeepSeek V4 via LLMGatewayAdapter) |
| **expert_ids** | `["evidence-extractor"]` |
| **built_by** | `icoder` |
| **version** | `1.0.0` |
| **maturity** | `mvp` |
| **production_ready** | `false` |
| **human_review** | `required` |
| **red_lines** | `no_upcoding: true, evidence_required: true, production_writeback_blocked: true` |
| **api_endpoint** | `POST /api/v1/agents/evidence-extractor/run` |
| **a2a_endpoint** | `POST /api/icoder/agents/evidence-extractor/v1/message:send` (alternative) |
| **status** | ✅ PASS — smoke run via real DeepSeek returns structured envelope with coded_evidence/uncoded_findings/review_summary |

### Input schema (request)

```json
{
  "input": {
    "text": "<病案文本>",
    "extra": {"codes": ["S22.000", "M80.900"]}
  },
  "include_trace": true,
  "include_evidence": true
}
```

### Output schema (result.markdown parsed as JSON)

```json
{
  "coded_evidence": [
    {
      "code": "S22.000",
      "evidence_text": "MRI 显示 T12 椎体压缩性骨折",
      "evidence_strength": "direct",
      "char_span": [12, 28],
      "confidence": 0.92,
      "manual_review_prompt": ""
    }
  ],
  "uncoded_findings": [
    {
      "finding": "骨质疏松病史 5 年",
      "evidence_text": "既往骨质疏松病史 5 年",
      "suggested_code": "M80.900",
      "note": "建议追加为 secondary dx"
    }
  ],
  "review_summary": "1 code 有直接证据, 1 个未编码发现建议追加"
}
```

### Demo case (fixture)

- **Title:** "T12 骨折 + 已知编码集"
- **Input:** `患者男性,78岁,MRI 显示 T12 椎体压缩性骨折。既往骨质疏松病史 5 年。`
- **Expected:** `coded_evidence` for S22.000 with `direct` strength; `uncoded_findings` for M80.900 suggestion
- **Run result:** `run-7ebd90c5-6c1b-4b25-b7a2-16b7257563b3` / latency 2275ms / runtime_mode `a2a_pure_llm` ✅

---

## 2. principal-diagnosis-review (主诊断复核智能体)

| Field | Value |
|---|---|
| **agent_id** | `principal-diagnosis-review` |
| **agent_ref** | `icoder/principal-diagnosis-review@1.0.0` |
| **name** | 主诊断复核智能体 / Principal Diagnosis Review Agent |
| **description** | iCoDer Principal Diagnosis Review Agent (Corti-style). 给定多诊断出院小结, 识别主诊断候选 + 冲突 + 风险, 给出主诊断建议。规则启发式 (主诊断三原则) + LLM 解释。 |
| **use_case** | `coding_revenue_cycle` |
| **default_runtime_mode** | `a2a_pure_llm` |
| **available_runtime_modes** | `[a2a_pure_llm]` |
| **backend_provider** | `icoder.pure-llm.v1` |
| **expert_ids** | `["principal-diagnosis-review"]` (preset — Phase 5) |
| **built_by** | `icoder` |
| **version** | `1.0.0` |
| **maturity** | `mvp` |
| **production_ready** | `false` |
| **human_review** | `required` |
| **red_lines** | `no_upcoding: true, evidence_required: true, production_writeback_blocked: true` |
| **api_endpoint** | `POST /api/v1/agents/principal-diagnosis-review/run` |
| **status** | ✅ PASS — smoke run via real DeepSeek returns structured envelope with candidates/recommended/not_recommended/rationale/manual_review_prompt |

### Input schema

```json
{
  "input": {"text": "<多诊断出院小结>"}
}
```

### Output schema

```json
{
  "candidates": [
    {
      "code": "S22.000",
      "display": "T12 椎体压缩性骨折",
      "evidence_text": "MRI 显示 T12 椎体压缩性骨折",
      "severity": "high",
      "resource_usage": "high",
      "primary_treatment": true,
      "recommended": true,
      "rationale": "..."
    },
    {...3 more candidates...}
  ],
  "recommended": "S22.000",
  "not_recommended": [
    {"code": "M80.900", "reason": "..."},
    {"code": "I10", "reason": "..."},
    {"code": "E11.900", "reason": "..."}
  ],
  "rationale": "...",
  "manual_review_prompt": "..."
}
```

### Demo case

- **Title:** "多诊断出院小结 — 主诊断冲突"
- **Input:** `出院诊断: 1. T12 椎体压缩性骨折; 2. 骨质疏松伴病理性骨折; 3. 原发性高血压; 4. 2 型糖尿病。患者男性,78岁,因腰背痛入院, MRI 显示 T12 椎体压缩性骨折, 行切开复位内固定术, 术后恢复良好。`
- **Expected:** `recommended="S22.000"` with `candidates` array and `not_recommended` array
- **Run result:** `run-cb2009ea-6505-4e26-bea0-dd52fe29c958` / latency 6348ms / runtime_mode `a2a_pure_llm` ✅

---

## 3. drg-analyzer (DRG/DIP 风险复核智能体)

| Field | Value |
|---|---|
| **agent_id** | `drg-analyzer` |
| **agent_ref** | `icoder/drg-analyzer@1.0.0` |
| **name** | DRG/DIP 风险复核智能体 / DRG/DIP Risk Review Agent |
| **description** | iCoDer DRG/DIP Risk Review Agent (Corti-style). 给定编码集 + 病案, 评估 upcoding/downcoding/不一致风险, 给出复核建议。LLM-only — 实际 DRG 分组由医保结算侧引擎完成。 |
| **use_case** | `coding_revenue_cycle` |
| **default_runtime_mode** | `a2a_pure_llm` |
| **available_runtime_modes** | `[a2a_pure_llm]` |
| **backend_provider** | `icoder.pure-llm.v1` |
| **expert_ids** | `["drg-analyzer"]` (preset — Phase 5) |
| **built_by** | `icoder` |
| **version** | `1.0.0` |
| **maturity** | `mvp` |
| **production_ready** | `false` |
| **human_review** | `required` |
| **red_lines** | `no_upcoding: true, evidence_required: true, production_writeback_blocked: true` |
| **api_endpoint** | `POST /api/v1/agents/drg-analyzer/run` |
| **status** | ✅ PASS — smoke run via real DeepSeek returns structured envelope with risk_points/high_risk_codes/review_suggestions/drg_dip_rule_reservation_note/manual_review_required |

### Input schema

```json
{
  "input": {
    "text": "<病案文本>",
    "extra": {"codes": ["M80.900"]}
  }
}
```

### Output schema

```json
{
  "risk_points": [
    {
      "risk_type": "upcoding",  // upcoding | downcoding | inconsistency | missing_complication
      "code": "M80.900",
      "evidence_text": "...",
      "char_span": [0, 60],
      "severity": "high",  // high | medium | low
      "suggestion": "..."
    }
  ],
  "high_risk_codes": ["M80.900"],
  "review_suggestions": "...",
  "drg_dip_rule_reservation_note": "DRG 分组由医保结算侧引擎完成, 本 Agent 仅评估编码方案对分组的影响。",
  "manual_review_required": true
}
```

### Demo case

- **Title:** "T12 骨折 + 骨质疏松 — upcoding 风险"
- **Input:** `患者女性,68岁,腰背部疼痛 3 月。X 线示 L1 椎体压缩性骨折,既往骨质疏松病史 5 年。`
- **Expected:** `risk_points` with `upcoding` on M80.900; `high_risk_codes=[M80.900]`; `manual_review_required=true`
- **Run result:** `run-fd0fbc42-e1a5-43ff-9170-5c8f5493b2b1` / latency 6784ms / runtime_mode `a2a_pure_llm` ✅ (4 risk_points: upcoding/downcoding/inconsistency/missing_complication)

---

## 4. discharge-summary-structuring (出院小结结构化智能体)

| Field | Value |
|---|---|
| **agent_id** | `discharge-summary-structuring` |
| **agent_ref** | `icoder/discharge-summary-structuring@1.0.0` |
| **name** | 出院小结结构化智能体 / Discharge Summary Structuring Agent |
| **description** | iCoDer Discharge Summary Structuring Agent (Corti-style). 给定非结构化出院小结原文, 输出结构化字段: 诊断列表/手术操作列表/治疗经过/出院医嘱/随访建议/出院状态。 |
| **use_case** | `coding_revenue_cycle` |
| **default_runtime_mode** | `a2a_pure_llm` |
| **available_runtime_modes** | `[a2a_pure_llm]` |
| **backend_provider** | `icoder.pure-llm.v1` |
| **expert_ids** | `["discharge-summary-structuring"]` (preset — Phase 5) |
| **built_by** | `icoder` |
| **version** | `1.0.0` |
| **maturity** | `mvp` |
| **production_ready** | `false` |
| **human_review** | `required` |
| **red_lines** | `no_upcoding: true, evidence_required: true, production_writeback_blocked: true` |
| **api_endpoint** | `POST /api/v1/agents/discharge-summary-structuring/run` |
| **status** | ✅ PASS — smoke run via real DeepSeek returns structured envelope with diagnoses/procedures/treatment_summary/discharge_orders/follow_up_recommendations/discharge_status/manual_review_required |

### Input schema

```json
{
  "input": {"text": "<出院小结原文>"}
}
```

### Output schema

```json
{
  "diagnoses": [
    {
      "text": "T12 椎体压缩性骨折",
      "primary": true,
      "evidence_text": "MRI 显示 T12 椎体压缩性骨折",
      "char_span": [24, 40]
    },
    {...3 more secondary diagnoses...}
  ],
  "procedures": [
    {"text": "T12 椎体切开复位内固定术", "evidence_text": "...", "char_span": [84, 102]}
  ],
  "treatment_summary": "...",
  "discharge_orders": ["腰背支具佩戴 3 个月", "避免负重活动 1 个月", "抗骨质疏松药物治疗"],
  "follow_up_recommendations": [
    {"department": "骨科", "time": "术后 1 月", "items": ["X 线复查"]}
  ],
  "discharge_status": 2,
  "manual_review_required": true
}
```

### Demo case

- **Title:** "T12 骨折出院小结"
- **Input:** `患者男性,78岁,因腰背部疼痛 3 月入院。入院后 MRI 显示 T12 椎体压缩性骨折...出院诊断: 1. T12 椎体压缩性骨折; 2. 骨质疏松伴病理性骨折; 3. 原发性高血压; 4. 2 型糖尿病。出院医嘱: 腰背支具佩戴 3 个月, 避免负重活动 1 个月, 抗骨质疏松药物治疗。随访: 术后 1 月骨科门诊 X 线复查。`
- **Expected:** 7 output fields including `discharge_status` (integer) and `manual_review_required`
- **Run result:** `run-242ae78d-95d4-4b49-9560-3952e4b50852` / latency 3598ms / runtime_mode `a2a_pure_llm` ✅ (4 diagnoses, 1 procedure, full treatment_summary + 3 discharge_orders + follow_up + discharge_status=2)

---

## Cross-agent summary

| Agent | Latency (real DeepSeek) | Trace events inline | Trace steps persisted | Output fields match |
|---|---|---|---|---|
| evidence-extractor | 2275ms | 3 | 7 | ✓ all 3 expected |
| principal-diagnosis-review | 6348ms | 3 | 7 | ✓ all 5 expected (recommended=S22.000) |
| drg-analyzer | 6784ms | 3 | 7 | ✓ all 5 expected (manual_review_required=true) |
| discharge-summary-structuring | 3598ms | 3 | 7 | ✓ all 7 expected |

All 4 agents:
- Route through `ProviderRegistry → PureLLMProvider → LLMGatewayAdapter → DeepSeek V4`
- Emit 3 lifecycle trace events inline (USER_MESSAGE_RECEIVED, OUTPUT_GENERATED, COMPLETION)
- Persist 7-step timeline to `RunTraceStore` (3 lifecycle + 4 internal)
- Return the 13-field envelope per prompt §9.1
- Have `backend_provider: "icoder.pure-llm.v1"` and `backend_type: "pure_llm"` in result
- Cost is `{}` (placeholder, real cost tracking is Phase 4-G #11)

---

## Common envelope shape (all 4 agents)

```json
{
  "agent_id": "<agent_id>",
  "run_id": "run-<uuid>",
  "trace_id": "trace-<hex>",
  "runtime_mode": "a2a_pure_llm",
  "latency_ms": <int, <30000>,
  "cost": {},
  "summary": "<first chunk of result.markdown>",
  "result": {
    "status": "complete",
    "markdown": "<json-encoded output_contract fields>",
    "issues": [],
    "corrected_draft": null,
    "risk_flags": [],
    "tool_calls": [],
    "finish_state": "completed",
    "finish_reason": null,
    "backend_provider": "icoder.pure-llm.v1",
    "backend_type": "pure_llm",
    "raw_provider_response": {
      "content": "<raw LLM output>",
      "model": "deepseek-v4-flash",
      "usage": {"input_tokens": <int>, "output_tokens": <int>},
      "latency_ms": <int>
    }
  },
  "evidence": [],
  "warnings": [],
  "manual_review_required": false,
  "trace_events": [
    {"step": "user_message_received", "status": "ok", ...},
    {"step": "output_generated", "status": "ok", ...},
    {"step": "completion", "status": "ok", ...}
  ],
  "error": false,
  "error_reason": ""
}
```

---

## Future agent expansion (not in F3 scope)

Per Phase 4-F prompt §2.2, the remaining 4 of 8 iCoDer built agents are NOT P0 for F3 but are standardized with v1.3 spec:

- `procedure-extractor` (v1.3, a2a_pure_llm) — ICD-9-CM-3-CN procedure extraction
- `note-completeness` (v1.2, a2a_pure_llm) — Medical record quality control
- `compliance-guardrail` (v1.2, rule_engine + a2a_pure_llm) — Coding compliance explanation
- `medical-coding` (v1.2, corti_like_fast + medcoder_deep) — Already production-ready MVP

These are not smoke-tested in F3 (only the 4 P0 per prompt §2.1).
