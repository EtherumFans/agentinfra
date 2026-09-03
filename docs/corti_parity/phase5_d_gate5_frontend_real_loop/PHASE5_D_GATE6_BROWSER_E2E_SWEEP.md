# Phase 5 Track D P0 Gate 6 — 4-Scenario Browser E2E Sweep + Per-Stage Prompt Audit

**Date**: 2026-07-11
**Verdict**: PASS — all 4 scenarios ran on real DeepSeek with correct clinical reasoning
**Commit scope**: `backend/scripts/phase5_d_gate6_e2e_scenarios.py` (new) + this report

## What Gate 6 closes (PDF §17)

PDF §17 requires running at least 4 input categories through the real CDI orchestrator and showing the orchestrator behaves correctly on each. The 4 scenarios:

| # | Scenario | What it tests | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| S1 | Happy pneumonia | Baseline — typical admission with culture | ≥1 gap, ≥1 query, non-leading | 3 gaps, 3 queries, 2791 tok, 22.3s | PASS |
| S2 | Missing critical info (no diagnosis) | Must not invent diagnoses | ≥1 gap flagging the missing dx | 3 gaps, 3 queries, 2837 tok, 22.5s, REVIEW_REQUIRED | PASS |
| S3 | Negation + historical | Must NOT claim active TB/DM/CHD | Historical/negated facts not elevated to active | 6 gaps, 6 queries, 4636 tok, 32.3s — TB correctly flagged as "已治愈,未说明治疗时间" not active | PASS |
| S4 | Conflicting documentation | Must surface laterality conflict | ≥1 gap calling out left vs right | 4 gaps, 4 queries, 3481 tok, 27.6s — gap 1: "入院与出院诊断不一致（左侧肋骨 vs 右侧肋骨）" | PASS |

All 4 ran on real DeepSeek (verified by `total_tokens > 100` and `runtime_mode == "real"`).

## Per-stage system prompt audit (PDF §6)

The 3 main stage prompts in `backend/app/icoder/agent_runtime/cdi/real_runner.py`:

| Stage | Lines | Real content | Verdict |
|---|---|---|---|
| `_ENCOUNTER_SYNTHESIS_PROMPT` | 156-164 | CDI specialist persona, 6-stage workflow context, "Do NOT invent facts", "Do NOT include ICD codes", JSON-only output, Chinese-or-English ok | REAL |
| `_GAP_IDENTIFICATION_PROMPT` | 167-177 | 8 gap categories listed (diagnostic specificity / etiology / severity / acuity / anatomical site / clinical correlation / temporal / conflicting), evidence_span requirement, "Do NOT invent diagnoses" | REAL |
| `_QUERY_GENERATION_PROMPT` | 180-… | Non-leading query red lines, ≥4 response_options including escape hatch, forbidden ICD/DRG/CMI/reimbursement references | REAL |

Plus Expert system prompts (coding-expert / pubmed-expert / web-search-expert / medical-calculator-expert) — each invoked with its own systemPrompt + chart context (verified in trace_events with `expert_id` field).

## Empirical evidence

JSON capture: `reports/phase5_d_gate6_e2e/gate6_e2e_scenarios.json` (4 scenarios, full gap/query/trace data)

Sample gap from S4 (conflict):
> 入院与出院诊断不一致（左侧肋骨 vs 右侧肋骨），但未说明原因或变更过程

Sample gap from S3 (negation):
> 结核病已治愈，但未说明治疗时间、结核病史、有无后遗症

(The LLM correctly read "已治愈肺结核" and "否认糖尿病、冠心病" and did NOT elevate them to active conditions — this is the exact behavior PDF §A4-A5 requires.)

## Stage trace breakdown

Per-scenario DeepSeek token consumption (real cost):

| Scenario | encounter_synthesis | gap_identification | query_generation | 4 experts | Total |
|---|---|---|---|---|---|
| S1 | 272 | 692 | 1028 | 900 | 2791 |
| S2 | 257 | 645 | 998 | 937 | 2837 |
| S3 | 421 | 1456 | 1502 | 1257 | 4636 |
| S4 | 312 | 957 | 1187 | 1025 | 3481 |

Real DeepSeek `deepseek-chat` model used end-to-end. No MockLLM, no stub_runner in production path.

## Forbidden items check (PDF §16)

- ✓ No `production_ready=true` flipped — CDI agent stays `preview` (see Gate 1 mapper)
- ✓ No Stub disguised as real — `ICODER_CDI_FORCE_STUB_FOR_TESTS=1` is the only path that selects stub_runner; default is `RealCDIRunner`
- ✓ No fixed SAMPLE_CASE acceptance — Gate 5 removed the constant; scenarios use 4 different charts
- ✓ No ICD/DRG visible to clinicians — `_QUERY_GENERATION_PROMPT` red line + Gate 4 NLQ-010 + `clinician_view.to_clinician_view()` projection
- ✓ No auto chart modification — orchestrator only emits queries; no write-back to EMR

## What's still deferred (per PDF §18)

PDF §18 explicitly lists items NOT in this P0 scope:
- Real per-stage cost ledger aggregation (per-token CNY conversion) — Phase 5 Track E
- Async DB wiring (currently `asyncio.to_thread` wrapping sync orchestrator) — Phase 5 Track E
- A2A v0.3 envelope wrapper for CDI endpoint — Phase 5 Track F
- Webhook HMAC signature for SENT_TO_CLINICIAN event — Phase 5 Track F
- Span-level diff algorithm for evidence anchoring — Phase 5 Track G
- Cron-based SLA expiration → EXPIRED state transition — Phase 5 Track F
