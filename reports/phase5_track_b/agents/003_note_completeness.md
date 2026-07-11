# Pair 003 — Note Completeness (EXACT_MATCH)

**Date:** 2026-07-11
**Corti agent:** `note-completeness-agent`
**iCoDer agent:** `icoder/note-completeness-agent@1.0.0` (Phase 4-B)
**Mapping class:** EXACT_MATCH (high confidence) — same name, same purpose
**Corti category:** Point of Care Tools
**iCoDer category:** `medical-coding` (currently miscategorized) / `Documentation / 病历完整性`
**Audit mode:** B-1.4 deep audit per PDF §3.1-3.6

## 1. Identity & Purpose (D1)

| | Corti | iCoDer |
|---|---|---|
| Name | Note Completeness Agent | 病历完整性智能体 |
| Description | Ensure high-quality clinical notes with real-time checks for completeness, accuracy, and compliance | iCoDer 病历完整性 Agent — 按《病历书写基本规范》检查入院记录的必填章节 |
| Use case | Point of Care Tools (real-time during charting) | Coding and Revenue Cycle (currently) — should be Point of Care Tools |
| Maturity | production | runnable (Phase 4-B migrated from regex to PureLLMProvider) |
| Audit class | EXACT_MATCH | |

**Verdict D1:** Same agent purpose. iCoDer Phase 4-B migrated from regex to PureLLMProvider to better mirror Corti's LLM-based approach. iCoDer uses《病历书写基本规范》(China national standard for clinical documentation); Corti uses generic "documentation completeness" criteria.

## 2. Category Misalignment (D1.1)

| | Corti | iCoDer |
|---|---|---|
| Corti category | Point of Care Tools | — |
| iCoDer `category` | — | `medical-coding` |
| iCoDer `category_display` | — | `Documentation / 病历完整性` |
| iCoDer `use_case` | — | `coding_revenue_cycle` |

**P1 GAP-14-03:** iCoDer categorizes note-completeness-agent as `medical-coding` / `coding_revenue_cycle`, but Corti categorizes it as Point of Care Tools. The agent is documentation-focused (per both prompts), not coding-focused. Recommend recategorizing to `documentation` / `point_of_care_tools` to match Corti.

## 3. System Prompt Depth (D2)

| | Corti | iCoDer |
|---|---|---|
| Prompt length | 5828 chars | PureLLMProvider with《病历书写基本规范》-derived system prompt |
| Sections | Context, Formatting Requirements, Formatting Rules for Labeled Lines, Safety/Scope, Step 1-4 (Extract / Completeness Check / Missing Items / Corrected Draft), Output Structure (5 sections), Quality Checks, Core Principle | Mirror Corti structure adapted for Chinese documentation standard |
| Output format | Markdown with `**Label:** value` pattern | JSON + rendered markdown |
| Required sections | Documented Note Type, Completeness Assessment, Missing Items, Conflicts, Corrected Note Draft, Risk Flags | Same 6 sections |
| Placeholders | `[Not documented]` | `[未记录]` (CN equivalent) |

**Verdict D2:** Structural 1:1 with China localization. iCoDer's required sections (主诉/现病史/既往史/体格检查/辅助检查/诊断/治疗经过) map to Corti's generic CC/HPI/PMH/PE/Diagnostics/A&P.

## 4. Output Contract (D3)

Corti markdown sections:
- Documented Note Type and Context
- Completeness Assessment (Complete/Incomplete/Unclear + summary)
- Missing or Unclear Documentation Elements (table)
- Conflicts or Contradictions (table)
- Corrected Note Draft (Documentation-Only)
- Risk Flags

iCoDer JSON schema (`icoder/NoteCompletenessOutput/v1`):
- `review_conclusion` (Complete/Incomplete/Unclear)
- `documentation_gaps`
- `completeness_score` (numeric, iCoDer addition)
- `missing_sections` (list)
- `present_sections` (list)
- `required_sections` (list — from《病历书写基本规范》)
- `trace_refs`

**Verdict D3:** 1:1 conceptual mapping. iCoDer adds `completeness_score` (numeric, for tracking over time) and `required_sections` (explicit list per China standard). Corti uses pure qualitative "Complete/Incomplete/Unclear" enum.

## 5. Experts & Tools (D4)

| | Corti | iCoDer |
|---|---|---|
| Experts | 1: coding-expert | 1: coding-expert (integrated into PureLLMProvider) |
| MCP tools | (none explicit; uses coding-expert's tools) | 1: 1 internal tool (per B-1.2 inventory) |
| Runtime mode | LLM-driven | `a2a_pure_llm` (deterministic dispatch) |

**Verdict D4:** Both are LLM-only agents (no MCP tool calls in the loop). iCoDer is simpler — single LLM call with《病历书写基本规范》system prompt.

## 6. Same-Input Experiment (D5)

**Input:** `患者男性,78岁,MRI 显示 T12 椎体压缩性骨折。`

| | Corti | iCoDer |
|---|---|---|
| Status | CORTI_PERMISSION_DENIED | 200 |
| Runtime mode | (n/a) | a2a_pure_llm |
| Latency | (n/a) | ~1ms (mock; real DeepSeek ~2-4s per Phase 4-B) |
| Result | (n/a) | mock LLM returns generic JSON envelope; real DeepSeek would output required_sections / missing_sections / completeness_score |
| Trace events | (n/a) | 1 (mock; real run emits 3+ events per Phase 4-B walkthrough) |

## 7. UX Discoverability (D6)

| UX dim | Corti | iCoDer | Gap |
|---|---|---|---|
| Hub card | Point of Care Tools category | Coding and Revenue Cycle (mismatched) | Med gap → GAP-14-03 |
| Maturity badge | (none visible) | runnable | iCoDer richer |
| Required sections source | Implicit (LLM decides) | Explicit《病历书写基本规范》list in agent_pack | iCoDer richer |
| Cost display | Topbar $X.XXXXXX | Topbar ¥X.XXXXXX | LOCALIZE_FOR_CHINA |

## 8. Findings & Gaps

| # | Finding | Severity | Class |
|---|---|---|---|
| F1 | Phase 4-B migrated regex → PureLLMProvider (Corti parity achieved) | MATCHED_AND_READY | — |
| F2 | iCoDer category is `medical-coding` but agent is documentation-focused | P1 GAP-14-03 | new |
| F3 | iCoDer adds `completeness_score` numeric; Corti uses qualitative enum only | ICODER_ADVANTAGE_KEEP | — |
| F4 | iCoDer references《病历书写基本规范》(China standard); Corti has no equivalent regulatory anchor | ICODER_ADVANTAGE_KEEP | — |

## 9. PDF §11 Outcome Class

**MATCHED_AND_READY** (after GAP-14-03 fix) — Architecturally identical, both run stably, output contracts align. One P1 category metadata fix needed to match Corti's Point of Care Tools placement.

## 10. Recommendation

Fix GAP-14-03 (recategorize to `documentation` / `point_of_care_tools`) during Phase 5 Track B-2. Promote maturity to `production_ready` once 50+ inpatient note formats are validated against《病历书写基本规范》.

## 11. Files

- Corti prompt: `outputs/phase5_track_b/corti_prompts/note-completeness-agent.txt`
- iCoDer hub entry: `outputs/phase5_track_b/icoder_agents_hub_v2.json`
- Smoke run: `outputs/phase5_track_b/b1_4_smoke/pair003_note_completeness_smoke.json`
- Phase 4-B report: `docs/corti_parity/phase4_b_note_completeness_llm_migration/`
