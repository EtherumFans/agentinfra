# Corti 3 Agents Reverse Engineering — Research / Audit Plan

**Date:** 2026-07-07
**Lead:** Claude (glm-5.2) + SONG Luhua
**Source prompt:** `C:\Users\huawei\Downloads\Corti 3 Agents Reverse Engineering.docx`
**Phase:** Corti-3-Agents-RE

---

## 0. Goal

Answer the docx's two open questions:

1. **Part A — Corti 3 Agents backend technical form**: For each of Corti's Code Validation Agent / Compliance Guardrail Agent / Note Completeness Agent, what is the backend most likely to be? Pure rule? LLM? LLM + tools? Symphony / medical capability layer? Multi-stage pipeline? What does iCoDer already have, what's missing?
2. **Part B — iCoDer Agent Backend Compatibility Architecture**: Based on Part A findings, design iCoDer's Agent backend to be replaceable / composable / configurable / auditable / versionable / able to accept external capabilities / local models / rule engines / LLMs / future Symphony-like medical capability layers.

**Hard constraint from docx:** Cannot speculate about Corti internal source code. All conclusions must be graded CONFIRMED / LIKELY / POSSIBLE / UNKNOWN.

**Hard constraint from user:** Must use browser to simulate manual operations for detailed analysis.

---

## 1. Scope (8 input types × 3 agents × 14 fields)

### 1.1 Three Corti agents under test

| # | Agent | Corti console URL pattern |
|---|-------|----------------------------|
| 1 | Corti Code Validation Agent | `console.corti.app/.../agents/code-validation-...` |
| 2 | Corti Compliance Guardrail Agent | `console.corti.app/.../agents/compliance-guardrail-...` |
| 3 | Corti Note Completeness Agent | `console.corti.app/.../agents/note-completeness-...` |

### 1.2 Eight input types per agent (24 probes total)

| # | Input type | Purpose |
|---|------------|---------|
| 1 | Standard complete input | Baseline happy-path behavior |
| 2 | Missing key field input | Test required-field enforcement + error message shape |
| 3 | Fuzzy natural language input | Test whether LLM kicks in for free-text parsing |
| 4 | Structured JSON input | Test whether backend accepts JSON-typed parts |
| 5 | Obviously wrong coding input | Test detection of invalid codes (e.g. ICD-10 with extra digit) |
| 6 | Boundary case input | Edge: empty / very long / Unicode-only / extreme specialty |
| 7 | Mixed Chinese-English input | Test language detection + translation layer |
| 8 | Adversarial / prompt injection input | Test whether LLM follows injection vs rule path wins |

### 1.3 Fourteen fields recorded per probe (24 × 14 = 336 data points)

For each of the 24 probes, record:

1. Input sample (verbatim)
2. Output structure (top-level keys + types)
3. Response time (ms — wall clock from send to first response chunk)
4. LLM-style explanation present? (yes/no — does output contain natural-language explanation that could only come from a generative model?)
5. Stable reproduction? (yes/no — run same input twice, compare byte-for-byte)
6. Format-sensitive? (yes/no — does adding/removing whitespace change output shape?)
7. Handles natural language? (yes/no — probe 3 succeeded?)
8. Handles structured JSON? (yes/no — probe 4 succeeded?)
9. Rule template traces? (yes/no — fixed strings / lookup-table patterns in output?)
10. Model reasoning traces? (yes/no — chain-of-thought / hedging / "I think" / explanations that vary across runs?)
11. Tool / API calls? (yes/no — DevTools Network shows additional XHR beyond message:send?)
12. Network response shape (status code + body envelope: result / error / id / metadata)
13. Returns run_id / trace / hidden metadata? (yes/no + which fields)
14. Diff vs iCoDer current implementation (3-bullet summary)

---

## 2. Confidence grading (mandatory per docx)

Every claim about Corti's backend must be graded:

| Grade | Meaning | Evidence standard |
|-------|---------|-------------------|
| **CONFIRMED** | Browser / network / response directly evidences it | E.g. seen in DevTools Network response body, or output text directly contains the marker |
| **LIKELY** | Multi-run output behavior strongly supports it | E.g. identical output across 3 runs + fixed string template → likely rule-based; cannot confirm without source |
| **POSSIBLE** | Some sign but evidence insufficient | E.g. slightly varied phrasing across runs could be LLM OR could be template branching |
| **UNKNOWN** | Cannot judge from external observation | E.g. whether Corti uses Symphony internally — opaque |

---

## 3. Ten key questions to answer (per docx)

For each of the 3 agents, answer:

1. Pure rule-based implementation?
2. LLM-dependent?
3. Multi-stage pipeline?
4. Tool calling / function calling?
5. Backend medical capability layer (e.g. Symphony)?
6. Unified output schema?
7. Unified agent runtime contract?
8. Distinguishes deterministic validation vs generative reasoning?
9. Evidence extraction / validation / explanation layered?
10. Which capabilities does iCoDer already have, which are missing?

Plus the cross-cutting question:
- What is the *most likely backend technical form* for Corti's 3 agents as a group?

---

## 4. Part B — iCoDer Agent Backend Compatibility Architecture (10 design items)

Based on Part A findings, design:

| # | Item | Notes |
|---|------|-------|
| 1 | `AgentBackendProvider` interface | The pluggable seam |
| 2 | Capability Adapter layer | Wraps provider-specific I/O into a uniform capability surface |
| 3 | Tool / MCP compatibility layer | Allows providers to expose MCP tools uniformly |
| 4 | `OutputContract` standardization | Schema every provider must satisfy |
| 5 | RunTrace / Tool Dispatch Detail recording spec | How providers emit trace events |
| 6 | Provider registry | Discovery + instantiation by name |
| 7 | Agent config `backend_provider` field | Per-agent override |
| 8 | Fallback / ensemble / hybrid strategies | Multi-provider composition |
| 9 | Deterministic agent + LLM agent unified execution model | One runner, many backends |
| 10 | Medical Coding Agent backend decoupling plan | Specifically unbundle the BGE-M3 + FAISS + DeepSeek re-rank from the agent runner |

### 4.1 Eight provider types to spec

For each: use case / I/O / pros / cons / fit-for-purpose per agent.

1. `rule_based_provider`
2. `llm_provider`
3. `retrieval_augmented_provider`
4. `local_finetuned_model_provider`
5. `external_api_provider`
6. `symphony_like_provider`
7. `hybrid_pipeline_provider`
8. `mock_provider`

---

## 5. Execution order

1. **Step 1 — Plan output (this document).** Done before any execution.
2. **Step 2 — iCoDer baseline.** Read iCoDer's 3 agent source files + handlers + tests. Record current architecture summary.
3. **Step 3 — Browser session setup.** Verify Corti login (user pre-logged-in per session memory), navigate to Corti Agent Library, locate the 3 agents.
4. **Step 4 — Probe matrix (24 probes).** For each agent × each input type: type input → send → capture DevTools Network response → record latency → screenshot output → save to `network_capture/` and `screenshots/`.
5. **Step 5 — Per-agent analysis.** Aggregate 8 probes per agent into a 14-field table + 10-question answers + 4-grade confidence.
6. **Step 6 — Cross-agent inference matrix.** Compare the 3 agents' patterns, look for shared runtime contract.
7. **Step 7 — Part B architecture design.** Write `ICODER_AGENT_BACKEND_COMPATIBILITY_ARCHITECTURE.md` + `ICODER_AGENT_BACKEND_PROVIDER_SPEC.md` + `ICODER_MEDICAL_CODING_BACKEND_DECOUPLING_PLAN.md`.
8. **Step 8 — Final summary.** Answer 5 summary questions.

---

## 6. Output documents (6 total, per docx)

| # | Path | Content |
|---|------|---------|
| 1 | `docs/reverse_engineering/corti_3_agents/CORTI_3_AGENTS_BACKEND_RE_REPORT.md` | Part A full report — per-agent 8-probe × 14-field findings + 10-question answers + confidence grades |
| 2 | `docs/reverse_engineering/corti_3_agents/CORTI_3_AGENTS_PROBING_LOG.md` | Verbatim probe log — input + output + latency + screenshot index + network capture index, 24 rows |
| 3 | `docs/reverse_engineering/corti_3_agents/CORTI_3_AGENTS_TECHNICAL_INFERENCE_MATRIX.md` | 14 fields × 3 agents matrix + cross-cutting inference + 10 key questions answered |
| 4 | `docs/architecture/agent_backend/ICODER_AGENT_BACKEND_COMPATIBILITY_ARCHITECTURE.md` | Part B architecture — 10 design items + sequence diagrams + provider registry + agent config schema |
| 5 | `docs/architecture/agent_backend/ICODER_AGENT_BACKEND_PROVIDER_SPEC.md` | 8 provider types × 7 fields (use case / I/O / pros / cons / fit 4 agents) |
| 6 | `docs/architecture/agent_backend/ICODER_MEDICAL_CODING_BACKEND_DECOUPLING_PLAN.md` | Concrete unbundling plan for medical-coding-agent (BGE-M3 / FAISS / DeepSeek re-rank extracted behind providers) |

---

## 7. Risk / known limits

- **Corti login state** — assumes user pre-logged-in. If session expired, will pause and ask user to re-login.
- **Corti rate limits / abuse detection** — 24 probes in one session may trigger throttling. Will space probes ~5-10s apart.
- **Prompt injection probes** — purely defensive research; no harmful payloads, just instruction-style strings ("Ignore previous instructions..." style). No attempt to extract Corti system prompts or training data.
- **Output variation across runs** — if LLM-backed, output will vary. Will run each probe 2× to check stability.
- **iCoDer comparison baseline** — iCoDer's 3 agents are deterministic rule-based (verified in Phase 3-D2). The "diff" column will be straightforward.
- **Symphony inference** — Corti's healthcare-specific capability layer is opaque from outside. We can only grade UNKNOWN unless output text contains Symphony-style markers.
- **Network capture format** — Playwright MCP `browser_network_requests` returns URL list; `browser_network_request` retrieves full headers+body per request. Will save full bodies for the `message:send` + `tasks/get` responses per probe.

---

## 8. Acceptance

This plan is ready to execute. No open questions. Proceeding to Step 2 (iCoDer baseline).
