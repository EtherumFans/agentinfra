# Pair 004 — DRG/DIP Risk Review (ICODER_ONLY)

**Date:** 2026-07-11
**iCoDer agent:** `icoder/drg-analyzer@1.0.0`
**Corti equivalent:** NONE (Corti is US-focused, has no DRG/DIP)
**Mapping class:** ICODER_ONLY (high confidence)
**iCoDer category:** `medical-coding` / `Coding and Revenue Cycle / 编码与收入周期`
**Audit mode:** B-1.4 deep audit (iCoDer-only profile per PDF §3.6)

## 1. Identity & Purpose (D1)

| Field | Value |
|---|---|
| Name | DRG/DIP 风险复核智能体 |
| Description | iCoDer DRG/DIP Risk Review Agent (Corti-style). 给定编码集 + 病历文本, 评估 DRG/DIP 风险: 高补偿编码 (upcoding 风险)、低补偿编码 (downcoding 漏费)、CMI 影响因子、医保结算拒付风险 |
| Maturity | MVP (production_ready=false) |
| Use case | Coding and Revenue Cycle (medical-coding) |
| iCoDer-only rationale | Corti is US-focused (ICD-10-CM + CPT/HCPCS). DRG/DIP is the China reimbursement model (CN-DRG + DIP). Corti has no equivalent. |

## 2. Strategic Value (D2)

**HIGH** — DRG/DIP is the dominant China hospital reimbursement model since 2022 national rollout. Without this agent, iCoDer cannot serve the #1 hospital financial workflow in China.

Corti's nearest equivalent (CDI Agent) focuses on documentation quality, not reimbursement risk. The two are non-substitutable.

## 3. Workflow (D3)

```
Input: 编码集 + 病历文本
   ↓
[Rule-based screening]
   - high_risk_codes 列表 (upcoding history)
   - CMI 影响因子
   -医保结算拒付规则
   ↓
[LLM 解释层]
   - review_suggestions 自然语言生成
   - 风险点定位 + 编码建议
   ↓
Output: risk_points, high_risk_codes, review_suggestions,
       drg_dip_rule_reservation_note, manual_review_required
```

Runtime mode: `a2a_pure_llm` (deterministic dispatch through PureLLMProvider).

## 4. Output Contract (D4)

Schema `icoder/DRGDIPRiskReview/v1`:
- `risk_points` (list of {code, risk_type, severity, evidence_span})
- `high_risk_codes` (subset of input codes flagged as upcoding risk)
- `review_suggestions` (natural language review)
- `drg_dip_rule_reservation_note` (regulatory citation)
- `manual_review_required` (bool — hard gate)

Red lines preserved:
- `no_upcoding: true`
- `no_inference: true`
- `evidence_required: true`
- `production_writeback_blocked: true`

## 5. Same-Input Experiment (D5)

**Input:** `主诊断=S22.000 (T12 椎体压缩性骨折), 其他诊断=[M80.900], 手术=[], 性别=男, 年龄=78`

| Field | Value |
|---|---|
| Status | 200 |
| Runtime mode | a2a_pure_llm |
| Latency (mock) | 5ms |
| Real DeepSeek latency | 2275-6784ms (per Phase 4-F3 smoke) |
| Envelope | 13-field standard |
| Manual review required | false (default; real DeepSeek may flip based on rule hits) |
| Trace events | 1 (mock); 3+ persisted (real DeepSeek per Phase 4-F3) |

## 6. UX Discoverability (D6)

| UX dim | Status |
|---|---|
| Hub card visible | Yes (Coding and Revenue Cycle) |
| Maturity badge | MVP / AI-assisted / Human review required |
| Tags | drg, dip, risk-review, no-upcoding, insurance-audit, corti-style |
| Chat page | Standard AgentChatPage (Phase 4-F1 unified) |
| Output rendering | risk_points table + review_suggestions markdown |
| Corti equivalent | NONE — this is iCoDer's competitive moat |

## 7. Findings

| # | Finding | Severity | Class |
|---|---|---|---|
| F1 | iCoDer-only — Corti has no DRG/DIP equivalent | ICODER_ADVANTAGE_KEEP | — |
| F2 | MVP maturity; rule coverage thin (high_risk_codes list not yet comprehensive) | P2 GAP-14-04 | new |
| F3 | No CN-DRG groupor integration yet (rules are heuristic, not groupor-driven) | P2 GAP-14-05 | new |
| F4 | No DIP scoring (DIP 分值付费) integration yet | P2 GAP-14-06 | new |
| F5 | A2A card not in `.well-known/agent.json` (only 5 hardcoded agents exposed) | P1 GAP-13-01 (existing) | — |

## 8. PDF §11 Outcome Class

**ICODER_ADVANTAGE_KEEP** — iCoDer has a unique agent that Corti cannot offer. China hospital buyers require DRG/DIP risk review for insurance compliance. This agent alone can be a deal-maker in China RFPs.

## 9. Recommendation

For Phase 5 Track B-2 / Track C:
- **P1**: Add drg-analyzer to `.well-known/agent.json` A2A discovery (close GAP-13-01)
- **P2**: Integrate CN-DRG groupor + DIP scoring engine (close GAP-14-05, GAP-14-06)
- **P2**: Promote from MVP → runnable once 100+ case smoke completes

## 10. Files

- iCoDer hub entry: `outputs/phase5_track_b/icoder_agents_hub_v2.json`
- Smoke run: `outputs/phase5_track_b/b1_4_smoke/pair004_drg_analyzer_smoke.json`
- Phase 4-F3 report: `docs/corti_parity/phase4_f3_core_agent_smoke/`
