# Pair 005 — Coding Evidence Extractor (ICODER_ONLY)

**Date:** 2026-07-11
**iCoDer agent:** `icoder/evidence-extractor@1.0.0`
**Corti equivalent:** BUNDLED (Corti folds evidence extraction into coding-expert; no standalone agent)
**Mapping class:** ICODER_ONLY (high confidence)
**iCoDer category:** `medical-coding` / `Coding and Revenue Cycle / 编码与收入周期`
**Audit mode:** B-1.4 deep audit (iCoDer-only profile per PDF §3.6)

## 1. Identity & Purpose (D1)

| Field | Value |
|---|---|
| Name | 证据提取智能体 |
| Description | iCoDer Coding Evidence Agent (Corti-style). 给定病历文本 + 编码集, 为每个编码定位原文证据 span 并评估证据强度 (直接/间接/否定). AI-assisted — 不分配新编码, 仅评估已有编码的证据 |
| Maturity | MVP (production_ready=false) |
| Use case | Coding and Revenue Cycle (medical-coding) |
| iCoDer-only rationale | Corti bundles evidence extraction into the coding-expert (the LLM does it inline as part of code assignment). iCoDer separates this as a standalone agent for traceability + reuse. |

## 2. Strategic Value (D2)

**HIGH** — Standalone evidence extraction enables:
- Per-code evidence anchoring (audit trail for denial appeals)
- Reuse across agents (DRG Analyzer, Code Validation, CDI Review all consume evidence)
- Compliance with China《病历书写基本规范》evidence-span requirements
- Faster debugging (engineering team can rerun evidence extraction without re-running full coding pipeline)

Corti's bundled approach couples evidence to code assignment — extracting evidence for audit means rerunning the whole coding agent. iCoDer's separation is a clean architectural advantage.

## 3. Workflow (D3)

```
Input: 病历文本 + 编码集 (already assigned)
   ↓
[Per-code evidence scan]
   - For each code, scan text for direct/indirect/negated evidence
   - Use rapidfuzz.partial_ratio ≥ 0.85 to snap sentences to char spans
   - Use evidence_anchoring_kb (972 codes × 6,490 patterns) for pattern matching
   ↓
[Evidence strength scoring]
   - 直接 (direct): explicit code description in text
   - 间接 (indirect): synonym/related term in text
   - 否定 (negated): code explicitly ruled out
   ↓
Output: coded_evidence, uncoded_findings, review_summary
```

Runtime mode: `a2a_pure_llm` (deterministic dispatch).

## 4. Output Contract (D4)

Schema `icoder/CodedEvidence/v1`:
- `coded_evidence` (list of `{code, evidence_span, strength, char_start, char_end}`)
- `uncoded_findings` (clinical findings mentioned in text but not in code set)
- `review_summary` (natural language)

Red lines preserved:
- `no_upcoding: true`
- `no_inference: true`
- `evidence_required: true` (per-code evidence mandatory)
- `production_writeback_blocked: true`

## 5. Same-Input Experiment (D5)

**Input:** `患者男性,78岁,MRI 显示 T12 椎体压缩性骨折。`

| Field | Value |
|---|---|
| Status | 200 |
| Runtime mode | a2a_pure_llm |
| Latency (mock) | 6ms |
| Real DeepSeek latency | 2275-6784ms (per Phase 4-F3 smoke) |
| Envelope | 13-field standard |
| Manual review required | false (default) |
| Trace events | 1 (mock); 3+ persisted (real DeepSeek per Phase 4-F3) |

## 6. UX Discoverability (D6)

| UX dim | Status |
|---|---|
| Hub card visible | Yes (Coding and Revenue Cycle) |
| Maturity badge | MVP / AI-assisted / Human review required |
| Tags | icd-10-cn, evidence-anchoring, per-code-evidence, no-upcoding, evidence-first, corti-style |
| Chat page | Standard AgentChatPage (Phase 4-F1 unified) |
| Output rendering | coded_evidence table with quote chips + uncoded_findings list |
| Corti equivalent | NONE — Corti bundles into coding-expert (no standalone reuse) |

## 7. Findings

| # | Finding | Severity | Class |
|---|---|---|---|
| F1 | iCoDer-only — Corti bundles evidence into coding-expert | ICODER_ADVANTAGE_KEEP | — |
| F2 | Enables reuse across agents (DRG, CodeVal, CDI consume evidence) | ICODER_ADVANTAGE_KEEP | — |
| F3 | MVP maturity; evidence_anchoring_kb only covers 972 of 37,897 ICD-10-CN codes | P2 GAP-14-07 | new |
| F4 | A2A card not in `.well-known/agent.json` (only 5 hardcoded agents) | P1 GAP-13-01 (existing) | — |
| F5 | Per-code evidence strength scoring (direct/indirect/negated) is more granular than Corti's bundled approach | ICODER_ADVANTAGE_KEEP | — |

## 8. PDF §11 Outcome Class

**ICODER_ADVANTAGE_KEEP** — iCoDer's standalone evidence agent is architecturally cleaner than Corti's bundled approach. Key reuse benefits for compliance audit trail and downstream agent composition.

## 9. Recommendation

For Phase 5 Track B-2 / Track C:
- **P1**: Add evidence-extractor to `.well-known/agent.json` A2A discovery (close GAP-13-01)
- **P2**: Expand evidence_anchoring_kb coverage from 972 → 5,000+ codes
- **P2**: Wire evidence-extractor as the upstream feeder for code-validation + drg-analyzer + cdi-review (currently each agent does its own evidence scan)
- **P2**: Promote from MVP → runnable once 100+ case smoke completes

## 10. Files

- iCoDer hub entry: `outputs/phase5_track_b/icoder_agents_hub_v2.json`
- Smoke run: `outputs/phase5_track_b/b1_4_smoke/pair005_evidence_extractor_smoke.json`
- Phase 4-F3 report: `docs/corti_parity/phase4_f3_core_agent_smoke/`
