# Agent Capability Matrix B-2 Report

**Generated**: 2026-07-11 (Phase 5 Track B-2 Phase 11)
**Source**: `outputs/phase5_track_b2/agent_capability_matrix_b2.csv`
**Layers**: 5 (PLATFORM_AVAILABLE → AGENT_CONFIGURED → RUNTIME_INVOKED → RESULT_CONSUMED → QUALITY_VALIDATED) + TOP_LAYER

---

## 1. Capability Matrix (5 layers × 9 agents)

| Capability Layer | CP1 medical-coding | CP2 code-validation | CP3 compliance-guardrail | CP4 note-completeness | CP5 procedure-extractor | CP6 evidence-extractor | CP7 principal-dx-review | CP8 discharge-summary | CP9 drg-analyzer |
|---|---|---|---|---|---|---|---|---|---|
| PLATFORM_AVAILABLE | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| AGENT_CONFIGURED | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| RUNTIME_INVOKED | Y (DeepSeek 4-8s) | **SKELETON** (provider raises NotImplementedError) | Y (DeepSeek + RuleEngine) | Y (DeepSeek 8.9-10.9s) | Y (DeepSeek) | Y (DeepSeek 5.5-6.7s) | Y (DeepSeek 4.8-16.8s) | Y (DeepSeek 6.8-10.2s) | Y (DeepSeek 7.2-15.2s) |
| RESULT_CONSUMED | Y (structured) | N/A | Partial (markdown JSON) | Partial (JSON-in-markdown) | Partial (JSON-in-markdown) | Partial (JSON-in-markdown) | Partial (JSON-in-markdown) | Partial (JSON-in-markdown) | Partial (JSON-in-markdown) |
| QUALITY_VALIDATED | Y | N/A | Y | Partial (repeatability 400 delta) | Y (per-dept accurate) | Partial (repeatability 22 delta) | Y (conflict resolution accurate) | Y (repeatability delta < 90) | Partial (run 3 shorter) |
| **TOP_LAYER** | QUALITY_VALIDATED | AGENT_CONFIGURED | RESULT_CONSUMED | RESULT_CONSUMED | RESULT_CONSUMED | RESULT_CONSUMED | RESULT_CONSUMED | RESULT_CONSUMED | RESULT_CONSUMED |

---

## 2. Distribution

| Top Layer | Count | Agents |
|---|---|---|
| QUALITY_VALIDATED | 1 | medical-coding-agent |
| RESULT_CONSUMED | 7 | compliance-guardrail, note-completeness, procedure-extractor, evidence-extractor, principal-dx-review, discharge-summary-structuring, drg-analyzer |
| AGENT_CONFIGURED | 1 | code-validation-agent (SKELETON) |
| RUNTIME_INVOKED | 0 | — |
| PLATFORM_AVAILABLE | 0 | — |

---

## 3. Pattern analysis

### 3.1 medical-coding-agent 唯一 QUALITY_VALIDATED
- 唯一走 `icoder.medical-coding.v1` (HybridCodingAdapter + MedCodER 5-stage)
- 唯一有 multi-step trace_events（其他 agent 仅 1 event）
- 唯一支持 structured output（diagnoses 数组直接消费）
- 唯一进入 Phase 6 quality benchmark

### 3.2 7 个 PureLLM agents 卡 RESULT_CONSUMED
共同 gap：
- unified API 不解析 JSON-in-markdown → result.issues / result.risk_points / result.coded_evidence 全空
- trace_events 仅 1 event（completion）
- repeatability temp=0 但 md_len 非确定性

Track C Gate 1（StructuredOutputProjector）+ Gate 6（trace enrichment）修复。

### 3.3 CP2 SKELETON 是 P0 blocker
LLMWithToolsProvider registry 实例化未注入 llm_client → skeleton_pipeline 永远触发。Track C Gate 1 P0 修复（lazy-resolve like PureLLM）。

---

## 4. 影响 Track C

| Capability gap | Track C Gate | Fix |
|---|---|---|
| CP2 SKELETON | Gate 1 | lazy-resolve llm_client in registry |
| 7× JSON-in-markdown | Gate 1 | StructuredOutputProjector shared layer |
| 7× trace_events 1 event | Gate 6 | Parent-child run tree + 16 event types |
| 7× orchestrator wiring | Gate 4 | 7-stage coding compliance mainline |
| Repeatability non-det | Gate 1 | few-shot + temperature tuning |

Track C Gate 7 验收：所有 9 agent 至少 RESULT_CONSUMED，medical-coding 保持 QUALITY_VALIDATED。
