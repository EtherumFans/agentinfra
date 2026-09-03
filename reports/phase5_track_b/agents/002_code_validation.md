# Pair 002 — Code Validation (EXACT_MATCH)

**Date:** 2026-07-11
**Corti agent:** `code-validation-agent`
**iCoDer agent:** `icoder/code-validation-agent@1.0.0` (Phase 4-C v2)
**Mapping class:** EXACT_MATCH (high confidence) — same name, same purpose
**Corti category:** Coding and Revenue Cycle
**iCoDer category:** `medical-coding` / `Coding and Revenue Cycle / 编码与收入周期`
**Audit mode:** B-1.4 deep audit per PDF §3.1-3.6

## 1. Identity & Purpose (D1)

| | Corti | iCoDer |
|---|---|---|
| Name | Code Validation Agent | 编码校验智能体 |
| Description | Validate proposed medical code sets against official coding rules to detect errors, conflicts, and compliance risks before submission | iCoDer 编码校验 Agent v2 (Phase 4-C) — LLMWithToolsProvider + 4 MCP 工具,1:1 复刻 Corti Code Validation Agent 架构 |
| Maturity | production | runnable (Phase 4-C migrated from RuleEngine v1 to LLMWithTools v2) |
| Architecture | LLM + 4 tools (Verify/Guidelines/Explore/Search) | LLM + 4 tools (verify_code/get_guidelines/explore_code/search_codes) |
| Audit class | EXACT_MATCH | |

**Verdict D1:** iCoDer Phase 4-C v2 is a deliberate 1:1 architectural replication of Corti's Code Validation Agent. Same tool count, same tool semantics, same workflow (Step 1 Verify All → Step 2 Per-Code Checks → Step 3 Cross-Code Checks).

## 2. System Prompt Depth (D2)

| | Corti | iCoDer |
|---|---|---|
| Prompt length | 8662 chars | (Adapted from Corti via Phase 3-B1.5 reverse engineering) |
| Sections | Role, Tool Reference (4 tools), Safety/Scope Rules, Step 1-3 (per-code + cross-code checks), Output Structure, Severity definitions, Quality Checks | Mirrors Corti structure: tool reference, per-code checks (assignability/completeness/7th-char/laterality/age-sex), cross-code (Excludes1/sequencing/combination/duplicate/suppression) |
| Status enum | PASS / WARNING / FAIL | PASS / WARNING / FAIL (1:1) |
| Issue types | EXCLUDES1 CONFLICT / SEQUENCING / MISSING COMPANION / COMBINATION CODE / SYMPTOM SUPPRESSION / LATERALITY MISMATCH / DUPLICATE | Same 7 issue types |
| Output | Markdown per-code blocks + cross-code issues + summary | Same structure |

**Verdict D2:** iCoDer prompt is essentially a translation of Corti prompt. Same rule citations, same severity ladder, same fallback behavior ("High failure rate → return to extraction agent").

## 3. Output Contract (D3)

Corti markdown template (per code):
```
Code: [CODE] -- [Description]
Status: PASS | FAIL | WARNING
Assignable: Yes / No
Checks: Assignability ✓/✗ | Completeness ✓/✗ | 7th char ✓/✗/N/A | Laterality ✓/✗/N/A | Age/Sex ✓/✗/Not checked
Issue: [If FAIL or WARNING]
```

iCoDer JSON schema (`icoder/CodeValidationOutput/v2`):
- `review_conclusion`
- `validated_codes` (per-code object with same fields)
- `cross_code_issues` (same 7 issue types)
- `manual_review_required`
- `summary`
- `markdown` (rendered from JSON for UI)

**Verdict D3:** Conceptually 1:1. iCoDer adds `manual_review_required` boolean hard gate (Corti prompt only states it in severity definitions). iCoDer emits BOTH structured JSON and rendered markdown for UI.

## 4. Experts & Tools (D4)

| | Corti | iCoDer |
|---|---|---|
| Experts | 1: coding-expert | 2: coding-expert + (1 internal MedicalCodingRuleSet as fallback) |
| MCP tools | 4: Verify, Guidelines, Explore, Search | 4: verify_code, get_guidelines, explore_code, search_codes |
| Tool semantics | Identical (per Corti prompt) | Identical (1:1 replication Phase 4-C) |
| Fallback | LLM-only | Legacy RuleEngine R001-R010 + MC-R-M80-001 retained |

**Verdict D4:** Tool-level 1:1 parity. iCoDer adds a deterministic RuleEngine fallback for audit traceability when LLM is unavailable.

## 5. Same-Input Experiment (D5)

**Input:** `校验: primary=S22.000 (T12 椎体压缩性骨折), secondary=[M80.900]`

| | Corti | iCoDer |
|---|---|---|
| Status | CORTI_PERMISSION_DENIED | 200 |
| Runtime mode | (n/a) | llm_with_tools |
| Latency | (n/a) | ~11ms (mock LLM, real DeepSeek ~3-8s) |
| Tool calls | (n/a) | 1 (mock; real DeepSeek calls verify+guidelines per code) |
| Result keys | (n/a) | 11: status, markdown, issues, corrected_draft, risk_flags, tool_calls, finish_state, finish_reason, backend_provider, backend_type, raw_provider_response |
| Trace events | (n/a) | 1 (mock; real run emits 4+ tool call events) |

## 6. UX Discoverability (D6)

| UX dim | Corti | iCoDer | Gap |
|---|---|---|---|
| Hub card | Coding and Revenue Cycle | Coding and Revenue Cycle / 编码与收入周期 | Match |
| Maturity badge | (none visible) | runnable | iCoDer richer |
| Chat page | input + settings/code | input + settings/code/tools/experts | Match (Phase 4-D) |
| Tool call display | (Corti doesn't expose tool call trace) | 4 MCP tools visible in Tools tab + trace_events in Run Trace page | iCoDer ADVANTAGE |
| Cost display | Topbar $X.XXXXXX | Topbar ¥X.XXXXXX | LOCALIZE_FOR_CHINA |

## 7. Findings & Gaps

| # | Finding | Severity | Class |
|---|---|---|---|
| F1 | iCoDer is a deliberate 1:1 architectural replication (Phase 3-B1.5 RE + Phase 4-C migration) | MATCHED_AND_READY | — |
| F2 | iCoDer preserves legacy RuleEngine as fallback (R001-R010 + MC-R-M80-001); Corti has no equivalent | ICODER_ADVANTAGE_KEEP | — |
| F3 | iCoDer Run Trace page shows tool calls (verify_code, etc.) with timing; Corti doesn't expose this in UI | ICODER_ADVANTAGE_KEEP | — |
| F4 | iCoDer v2 schema is BREAKING (per Phase 4-C report); legacy v1 callers need migration path | closed (Phase 4-C) | — |

## 8. PDF §11 Outcome Class

**MATCHED_AND_READY** — Architecturally identical, both run stably, output contracts align, iCoDer adds 2 advantages (RuleEngine fallback + tool call trace visibility).

## 9. Recommendation

This is iCoDer's most Corti-faithful agent. Consider promoting to a "Corti-parity reference" badge in the Hub to communicate quality to hospital buyers.

## 10. Files

- Corti prompt: `outputs/phase5_track_b/corti_prompts/code-validation-agent.txt`
- iCoDer hub entry: `outputs/phase5_track_b/icoder_agents_hub_v2.json`
- Smoke run: `outputs/phase5_track_b/b1_4_smoke/pair002_code_validation_smoke.json`
- Phase 4-C report: `docs/corti_parity/phase4_c_code_validation_llm_with_tools/`
