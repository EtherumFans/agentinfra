# Phase 3-B0 Section A — Corti Agent Reference Checklist

**Date**: 2026-07-04
**Status**: COMPLETE

## A.1 Purpose

Establish the canonical 17-dimension checklist against which every iCoDer Agent / Agent-like feature will be audited in Sections B (inventory), C (per-agent parity), and D (manual QA simulation). The checklist encodes Corti-style product expectations: Agents are user-facing, task-oriented, honestly labeled, runtime-integrated, and human-review-required — not internal technical jargon or silent stubs.

## A.2 The 17 Corti Parity Dimensions

| # | Dimension | Question | Pass criterion | Fail signals |
|---|---|---|---|---|
| 1 | **Naming parity** | Is the Agent name task-oriented and user-facing? | Noun phrase describing the user's task (e.g. "Medical Coding Agent", "Fact Extraction") | Internal technical name ("MedCodER", "HybridCodingAdapter", "Stage1Extractor"); jargon suffix ("-v2", "-engine"); abbreviation |
| 2 | **Category parity** | Does the Agent belong to a clear, Corti-style category? | Category slug + display name (e.g. `medical-coding` / "Coding and Revenue Cycle") | No category; category is internal jargon; category mismatch with Corti §13 |
| 3 | **Agent Card completeness** | Does the Agent Card describe purpose, input, output, constraints, risks? | All 5 fields present in `agent_pack.json` manifest: description, inputs, outputs, constraints, risks | Missing description; no input/output contract; no constraints; no risks |
| 4 | **Maturity labeling** | Is maturity explicitly labeled? | `maturity` field set: `metadata-only` / `mvp` / `runnable` / `production-ready` | No maturity field; stub labeled "MVP"; experimental labeled "production-ready" |
| 5 | **Human review** | Is human review explicitly required? | `human_review: required` for MVP/runnable; clear "human-in-the-loop" language | Silent automation; "fully automated" language; no review flag |
| 6 | **Safety / no overclaim** | Does the Agent avoid overclaiming? | No F1 display; no accuracy %; no "outperforms" claims; honest degraded/error states | F1 score in UI; "AI-powered" superlatives; fake confidence values |
| 7 | **Workflow clarity** | Does the Agent expose a clear workflow? | 5-7 step workflow documented in system_prompt + visible in Agent Card | No workflow; workflow is internal pipeline jargon; workflow steps undefined |
| 8 | **Output contract** | Does the Agent have a structured output contract? | `output_contract.schema_ref` pointing to a named schema; required_fields list | No schema; free-text output; schema exists but not referenced |
| 9 | **Agent Hub visibility** | Can the Agent be discovered from the Agent Hub? | Listed in Hub with card, status, run button (if runnable) | Not in Hub; in Hub but missing card; in Hub but no run path for runnable |
| 10 | **Runnability honesty** | Is the Agent actually runnable? | `status: EXECUTABLE` + has experts[] + has tools[] + run path returns 200 | status=EXECUTABLE but no experts; runnable label but endpoint 410/501 |
| 11 | **RunTrace integration** | Does the Agent generate RunTrace on run? | Run appears in `/api/runtime/runs`; trace_refs in v2 output | No run history; no trace_refs field; run_id missing |
| 12 | **Tool / Expert calls** | Does the Agent call tools/experts? | tool_calls or expert_invocations visible in trace | Silent LLM call; no tool wiring; "AI" without tools |
| 13 | **Honest degraded/error** | Does the Agent fail honestly? | 503 when not configured; clear error message; no silent fallback to mock | Silent mock; 200 with fake data; degraded mode hidden |
| 14 | **Requirements disclosure** | Does the Agent disclose requirements? | `requirements` field listing capabilities (llm, retriever, rule_set) + missing config | No requirements; missing config silent; "works without LLM" when LLM required |
| 15 | **UI consistency** | Is the UI consistent with Corti IA? | 3-column layout (Input \| Output \| Settings/Code); banners; Review Summary panel | Different layout per agent; no MVP/AI-assisted banner; no review panel |
| 16 | **API consistency** | Is the API consistent with Corti §13? | `/api/v2/tools/{family}` or `/api/icoder/agents/{id}/v1/message:send` | Ad-hoc endpoints; legacy `/api/runtime/agents/{ref}/run` for non-medical-coding; mixed shapes |
| 17 | **Platform alignment** | Is the Agent a Corti-style Agent Runtime platform citizen? | Uses A2A InboundHandler for execution; MCP tools for capabilities; RunHistory for observability | Bypasses A2A; standalone script; no MCP integration; no audit trail |

## A.3 Scoring rubric (Section C uses this)

For each dimension, score 0-5:

- **5** — Fully aligned, exceeds Corti bar
- **4** — Aligned, minor gap
- **3** — Partially aligned, clear gap but not blocking
- **2** — Misaligned, significant gap
- **1** — Mostly misaligned, fundamental issue
- **0** — Missing or contradicts Corti-style

## A.4 Verdict categories (Section C uses this)

After scoring all 17 dimensions, assign one verdict per Agent:

| Verdict | Criteria | Action |
|---|---|---|
| **ALIGNED** | Average score ≥ 4.0; no dimension ≤ 1 | Keep as-is |
| **PARTIALLY_ALIGNED** | Average score 3.0-3.9; ≤ 2 dimensions at 1-2 | Keep + quick fix in Section F |
| **MISALIGNED** | Average score 2.0-2.9; or any dimension at 1 | Rename / migrate in Phase 3-B |
| **LEGACY** | Average score < 2.0; agent_type=reference or deprecated | Hide from Hub; mark deprecated |
| **STUB_ONLY** | agent_type=expert-stub or status=METADATA_ONLY | Mark "Coming soon"; no Run button |
| **DELETE_CANDIDATE** | Duplicate, orphan, or fundamentally broken | Delete in Phase 3-B |

## A.5 Mandatory honesty rules (Section F enforces)

1. **metadata-only ≠ runnable**: Agent with `agent_type=expert-stub` or `status=METADATA_ONLY` MUST NOT show Run button; MUST display "Coming soon" or "Not yet implemented" badge.
2. **stub ≠ MVP**: Agent with no real expert impl MUST NOT be labeled `maturity: mvp`; MUST be `maturity: metadata-only` or `maturity: stub`.
3. **no trace ≠ mainline**: Agent with no RunTrace integration MUST NOT be labeled "mainline-complete"; MUST be flagged as `trace_missing`.
4. **legacy ≠ visible**: Agent marked `hidden_from_hub: true` or `deprecated` MUST NOT appear in Agent Hub or navigation.
5. **production_ready=false MUST surface**: If `production_ready: false`, UI MUST show MVP banner + AI-assisted banner + human_review=required language.

## A.6 Scope of audit (Section B uses this)

The inventory must cover EVERY agent-like surface in the project:

- `official_agents/**/agent_pack.json` (the canonical Agent Packs)
- `generated_agents/` (if any)
- `app/icoder/agent_runtime/` (A2A + orchestrator + experts + MCP)
- `app/api/**` (every router — active, 410, 501, deprecated)
- `app/services/**` (agent-related services)
- `app/tools/` (if any)
- `frontend/src/pages/**` (every page — routed or orphan)
- `frontend/src/components/**` (agent-related components)
- `frontend/src/services/**` (every API client)
- `docs/**` (every doc mentioning agents)
- OpenAPI paths
- Agent Hub data source
- A2A discovery (`/api/icoder/agents`)
- MCP tools/list (`/mcp/v1/tools/list`)
- Runs/Trace (`/api/runtime/runs`)
- Navigation/sidebar config

## A.7 What this checklist is NOT

- Not a feature spec: doesn't tell Agents what to do, only how to be honest about what they are.
- Not a Corti reverse-engineering: doesn't copy Corti private code/prompts/data.
- Not a maturity judgment: an Agent can be metadata-only and still PASS — as long as it's honestly labeled.
- Not a performance bar: F1 / accuracy / latency are out of scope (Phase 3-A red line).

## A.8 Cross-references

- Phase 3-A Final Report: `docs/phase3/PHASE3A_FINAL_REPORT.md` — Medical Coding Agent MVP baseline (PASS).
- Phase 2.1-A: `agent_runner` deletion — `PlatformRuntime.run_agent` raises NotImplementedError; A2A mainline is the only execution path.
- P1.3 Corti parity audit: `docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md` — direction lock.
- Corti live login spec: `feedback_corti_live_login_as_spec` memory — Corti account login is the spec source when ambiguous.

## A.9 Next sections

- **B** (`PHASE3B0_FULL_AGENT_INVENTORY.md`) — apply this checklist's scope (A.6) to discover every agent-like feature.
- **C** (`PHASE3B0_AGENT_CORTI_PARITY_AUDIT.md`) — score each discovered agent on dimensions 1-17 (A.2) using rubric A.3, assign verdict per A.4.
- **D** (`PHASE3B0_MANUAL_QA_SIMULATION_MATRIX.md`) — simulate user testing for each visible agent, verify honesty rules A.5.
- **E** — automated tests codifying A.5 rules.
- **F** — quick fixes for any A.5 violations found in B-E.
- **G** — 5 verification rounds confirming A.5 holds.
- **H** — final report with PASS/FAIL verdict.
