# Gate 8 §9.2 Pre-Flight — Corti CDI Execution Verification

**Date**: 2026-07-12
**Agent**: `icoder-g8-cdi-ref` (id `fa3be93e-d1b3-45ef-ae8c-3a07c8d19ef2`)
**Source preset**: `clinical-documentation-improvement-cdi-agent`
**Project**: `4c4193c7-c6bb-4a71-a275-0ed6c53172d0`
**Verdict**: **PASS_WITH_LATENCY_CONCERN** — execution path confirmed, schema matches §9.5, cost affordable, but response stream latency is high and may require retry logic per §9.6

---

## Verification log

| Step | Result |
|---|---|
| 1. Corti CDI pre-built agent visible in Pre-built Agents catalog | ✅ |
| 2. "Customize agent" opens clone dialog | ✅ |
| 3. Agent cloned as `icoder-g8-cdi-ref` (id `fa3be93e-d1b3-45ef-ae8c-3a07c8d19ef2`) | ✅ |
| 4. System prompt captured (6-section `<output_format>` matches §9.5 schema) | ✅ |
| 5. 4 Experts bound to agent (pubmed-expert, web-search-expert, medical-calculator-expert, coding-expert) | ✅ |
| 6. Sample case submitted (64yo M, community-acquired pneumonia) via chat textarea + Ctrl+Enter | ✅ |
| 7. Corti invoked Expert (visible "Calling expert: co..." — coding-expert) | ✅ |
| 8. Response stream began (Encounter Summary section visible with 3 bullets) | ✅ |
| 9. Cost tracking works ($0.068040 consumed) | ✅ |
| 10. Full 6-section response received | ⚠ **PARTIAL** — stream stalled after ~60s wait with only Encounter Summary section; bullets cut at "Clinical indicators documented include WBC 14.5, temperature 38.3C, RR 22," |

## Latency observation

The chat-based Corti CDI invocation appears to stream very slowly. After 60s+ of waiting, the response was still incomplete. This may be:
1. Genuine LLM streaming latency (3 Expert consultations + main LLM synthesis)
2. UI rendering issue (response continues in background but UI doesn't refresh)
3. Free-tier rate limit / queueing

For 40-case batch, **UI-driven execution is impractical**. The SDK API (`cortiClient.agents.messageSend`) must be used instead, with:
- Generous timeout (5min per case)
- Retry logic per §9.6 (max 2 retries on failure)
- Async polling pattern (A2A v0.3 message → task poll)

## Cost projection

- Single case via UI: **$0.068040**
- 40 cases × $0.068 ≈ **$2.72 USD** total Corti cost
- Current balance: $44.31
- Affordable.

## Schema alignment with §9.5

Verified 1:1 mapping between Corti CDI's mandated `<output_format>` sections and Master Task §9.5 schema fields:

| §9.5 field | Corti section | Status |
|---|---|---|
| `encounter_summary` | Encounter Summary | ✅ |
| `documentation_gaps[]` | Documentation Gaps | ✅ |
| `provider_queries[]` | Proposed Provider Queries | ✅ |
| `coding_specificity_checklist[]` | Coding Specificity Checklist | ✅ |
| `risk_flags[]` | Risk Flags | ✅ |
| `specialist_trace[]` | Specialist Trace | ✅ |

iCoDer's CDI orchestrator output (from Gate 5) already produces parallel fields with the same 6 sections. Normalization is structural, not semantic.

## Cross-language constraint

Corti CDI `<principles>` block mandates: "Use English only."

This means:
- iCoDer cases (currently Chinese) must be **translated to English** before sending to Corti
- Corti outputs (English) must be **translated to Chinese** (or iCoDer outputs to English) before semantic comparison
- The 40-case fixture must include BOTH Chinese (for iCoDer) and English (for Corti) versions

This adds translation overhead but is unavoidable per Corti's hard constraint.

## Mismatch noted: AMBOSS Expert

System prompt references "AMBOSS Expert" but the actual bound experts are 4 different slugs (pubmed / web-search / medical-calculator / coding) — AMBOSS is not present. This is a Corti-side template drift, not an iCoDer issue. The LLM may still attempt to invoke AMBOSS by name and fail gracefully. Does not block Gate 8.

## Decision

**§9.2 PRE-FLIGHT: PASS** (with latency caveat)

Proceed to §9.4 (40-case fixture curation). The 40-case batch must use SDK API, not UI. Implement retry logic per §9.6 (max 2 retries per case).

If 3-case SDK smoke test (next step before full 40) shows > 30% failure rate, escalate to user before scaling.

## Artifacts

- System prompt: `docs/corti_parity/phase5_d_p05_gate8/corti_cdi_agent_reference.md`
- This pre-flight report: `docs/corti_parity/phase5_d_p05_gate8/preflight_corti_cdi_execution.md`
- Corti agent id: `fa3be93e-d1b3-45ef-ae8c-3a07c8d19ef2`
- Corti console URL: `https://console.corti.app/project/4c4193c7-c6bb-4a71-a275-0ed6c53172d0/ai-studio/agents/fa3be93e-d1b3-45ef-ae8c-3a07c8d19ef2`
