# Agent Capability Comparison (B-1.5)

**Date:** 2026-07-11
**Source data:** `outputs/phase5_track_b/agent_capability_matrix.csv`
**Agents scored:** 20 Corti + 24 iCoDer (44 total)
**Capabilities:** 23 per PDF §9

## Coverage summary

| Capability | Corti (20 agents) | iCoDer runnable (9) | iCoDer metadata (15) | Diff (runnable - Corti) |
|---|---|---|---|---|
| fact_extraction | 4/20 | 4/9 | 0/15 | = |
| normalization | 4/20 | 4/9 | 0/15 | = |
| validation | 2/20 | 2/9 | 0/15 | = |
| documentation_completeness | 3/20 | 2/9 | 0/15 | = |
| code_search | 4/20 | 4/9 | 0/15 | = |
| compliance_rules | 4/20 | 4/9 | 0/15 | = |
| evidence_anchoring | 4/20 | 4/9 | 0/15 | = |
| risk_scoring | 2/20 | 1/9 | 0/15 | = |
| **drg_dip_grouping** | **0/20** | **1/9** | 0/15 | **+1 iCoDer** |
| coding_guidelines | 20/20 | 4/9 | 0/15 | = |
| multi_language | 20/20 | 0/9 | 0/15 | **-20 Corti** |
| phi_redaction | 20/20 | 9/9 | 0/15 | = |
| audit_trail | 20/20 | 9/9 | 0/15 | = |
| streaming | 20/20 | 0/9 | 0/15 | **-20 Corti** |
| tool_calls | varies | 1/9 | 0/15 | = |
| expert_routing | 20/20 | 0/9 | 0/15 | **-20 Corti** |
| config_schema | 20/20 | 9/9 | 0/15 | = |
| output_schema | 20/20 | 9/9 | 0/15 | = |
| **manual_review_gate** | **0/20** | **9/9** | 0/15 | **+9 iCoDer** |
| **trace_events** | **0/20** | **9/9** | 0/15 | **+9 iCoDer** |
| cost_tracking | 20/20 | 9/9 | 0/15 | = |
| **latency_tracking** | **0/20** | **9/9** | 0/15 | **+9 iCoDer** |
| api_key_auth | 20/20 | 9/9 | 0/15 | = |

## iCoDer ADVANTAGE capabilities (3)

1. **drg_dip_grouping**: iCoDer has `drg-analyzer` with CN-DRG + DIP risk review. Corti has zero DRG/DIP support (US-focused). China hospital buyers require this.
2. **manual_review_gate**: All 9 iCoDer runnable agents enforce `human_review=required` hard gate via `red_lines` + `manual_review_required` boolean. Corti prompt mentions "Compliance confidence" but no hard gate.
3. **trace_events**: All 9 iCoDer runnable agents emit structured trace_events (inline + persisted RunTrace). Corti doesn't expose per-run trace.

## Corti ADVANTAGE capabilities (3)

1. **multi_language**: Corti supports multiple languages (English/Spanish/etc). iCoDer is CN-only currently. P1 gap for international expansion.
2. **streaming**: Corti agents support SSE streaming output. iCoDer agents return single envelope (capabilities.streaming=false). P2 gap.
3. **expert_routing**: Corti uses LLM-driven conditional routing across 4 experts per coding agent. iCoDer uses deterministic pipeline (more auditable but less adaptive). Architectural choice, not a gap.

## Metadata-only gap (15 agents)

15 iCoDer metadata-only agents have ALL capabilities at 0 (cannot run). 10 of these are the GAP-13-02 fix (metadata placeholder for Corti equivalent). 5 are pre-existing metadata agents (denial-appeals / diagnosis-extractor / cdi-review / documentation-gap / evidence-ranker).

**Action:** Promote 3 PARTIAL_MATCH agents (diagnosis-extractor / denial-appeals / cdi-review) to runnable per B-1.3 plan — closes 3 of 5 metadata gaps with Corti-equivalent agents.

## Capability density (per agent)

| Cohort | Avg capabilities / agent |
|---|---|
| Corti | 17/23 (74%) |
| iCoDer runnable | 13/23 (57%) |
| iCoDer metadata | 0/23 (0%) |

iCoDer runnable agents have LOWER capability density than Corti because:
- No multi_language
- No streaming
- No expert_routing

These are architectural choices (compliance-first vs flexibility-first), not bugs.

## Recommendation

For Phase 5 Track B-2:
- **P1**: Promote 3 PARTIAL_MATCH metadata agents to runnable (closes 3 capability gaps)
- **P2**: Add streaming support (closes 1 capability gap, but adds compliance risk)
- **P2**: International expansion multi-language (defer until CN market secured)

Full data: `outputs/phase5_track_b/agent_capability_matrix.csv` (44 rows × 26 columns).
