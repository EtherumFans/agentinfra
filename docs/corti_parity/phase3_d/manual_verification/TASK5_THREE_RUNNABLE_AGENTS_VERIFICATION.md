# Task 5 — 3 Runnable Agents — Manual Verification

**Date:** 2026-07-06
**Phase:** 3-D1 Task 5
**Verdict:** ✅ PASS

## What was built

3 simple runnable agents upgraded from `metadata-only` v1.1 stubs to
`runnable` v1.2 packs with real Python implementations:

### 1. Code Validation Agent (`icoder/code-validation-agent@1.0.0`)

- `official_agents/code_validation/__init__.py` — module docstring
- `official_agents/code_validation/agent.py` — `async def run(input_text, *, run_id="")`
  - Parses input as JSON (preferred) or free text (regex extracts ICD-10
    codes + ICD-9-CM-3 procedure codes)
  - Runs `MedicalCodingRuleSet` (R001-R010 + MC-R-M80-001) via the
    `RuleEngine`
  - Returns `CodeValidationOutput` schema:
    `review_conclusion / issues_found / manual_review_required / rule_set /
    fired_rules / code_assignment_summary / trace_refs`
- `official_agents/code-validation/agent_pack.json` — format_version 1.2,
  maturity `runnable`, `output_contract` declaring 7 required fields,
  `a2a.endpoint = /api/icoder/agents/code-validation-agent/v1/message:send`

### 2. Compliance Guardrail Agent (`icoder/compliance-guardrail-agent@1.0.0`)

- `official_agents/compliance_guardrail/__init__.py` — module docstring
- `official_agents/compliance_guardrail/agent.py` — `async def run(...)`
  - Reuses `code_validation._normalize_input` to parse the coding set
  - Runs `MedicalCodingRuleSet` (same as Code Validation Agent)
  - Runs 4 compliance guardrail heuristics:
    - **CG-001** primary dx present (critical if missing)
    - **CG-002** no upcoding (osteoporosis + vertebral fracture + M48.x
      primary → high risk, should be M80.x)
    - **CG-003** procedure-dx consistency (procedure without primary dx)
    - **CG-004** DRG readiness (primary dx + at least 1 valid procedure
      for surgical cases)
  - Returns `ComplianceGuardrailOutput` schema:
    `review_conclusion / issues_found / manual_review_required /
    drg_suggestion / compliance_checks / rule_set / trace_refs`
- `official_agents/compliance-guardrail/agent_pack.json` — format 1.2,
  maturity `runnable`, `human_review: required`

### 3. Note Completeness Agent (`icoder/note-completeness-agent@1.0.0`)

- `official_agents/note_completeness/__init__.py` — module docstring
- `official_agents/note_completeness/agent.py` — `async def run(...)`
  - Detects required sections per 《病历书写基本规范》:
    主诉 / 现病史 / 既往史 / 体格检查 / 辅助检查 / 诊断 / 治疗经过
  - For surgical cases (text mentions 手术/切除术/etc.), adds
    手术记录 to the required list
  - Computes `completeness_score = present / total`
  - Returns `NoteCompletenessOutput` schema:
    `review_conclusion / documentation_gaps / completeness_score /
    missing_sections / present_sections / required_sections /
    manual_review_required / is_surgical_case / trace_refs`
- `official_agents/note-completeness/agent_pack.json` — format 1.2,
  maturity `runnable`

### Wiring

- `app/icoder/agent_runtime/a2a/agent_card.py` — 3 new card factories
  (`code_validation_agent_card`, `compliance_guardrail_agent_card`,
  `note_completeness_agent_card`) declaring skills, output contracts,
  and metadata.icoder non_goals
- `app/icoder/agent_runtime/a2a/routes_discovery.py` — `_list_all_cards`
  now enumerates 5 agents (was 2)
- `app/main.py`:
  - Imports the 3 agent `run()` functions
  - `_SimpleAgentDispatchHandler` wraps the existing
    `_MedicalCodingV2ProjectingHandler`. For agent_ids in
    `{"code-validation-agent", "compliance-guardrail-agent",
    "note-completeness-agent"}`, it short-circuits the orchestrator
    and calls `run()` directly. For all other agent_ids, it falls
    through to the inner handler (medical-coding-agent still goes
    through Planner/Delegator/Aggregator + v1→v2 projection).
  - Emits RunTrace events: USER_MESSAGE_RECEIVED → OUTPUT_GENERATED →
    COMPLETION (ok/failed)
  - Builds an `InboundResponse` with a single DataPart containing the
    agent's output dict + `metadata.run_id` (so the frontend
    "View RunTrace" button works)
  - `_phase1_agent_provider` returns the 3 new cards for A2A discovery

## Verification

### V1: Each agent's run() function works (unit tests)

```
cd backend && pytest tests/unit/icoder/agent_runtime/test_three_runnable_agents.py -v
```

Result: **18/18 PASS.** Coverage:
- Code Validation: 5 tests (PASS / FAIL on missing primary / free-text
  parsing / low confidence triggers manual review / run_id propagates)
- Compliance Guardrail: 6 tests (PASS / CG-001 / CG-002 / CG-002
  negative / CG-003 / DRG suggestion)
- Note Completeness: 7 tests (PASS / FAIL on missing / surgical adds
  手术记录 / surgical missing 手术记录 / empty input / documentation_gaps
  have suggestion / run_id propagates)

### V2: A2A mainline end-to-end smoke tests

```
cd backend && pytest tests/integration/icoder/test_phase3d1_three_agents_a2a_smoke.py -v
```

Result: **5/5 PASS.** Each test posts a JSON-RPC 2.0 `message/send`
envelope to `POST /api/icoder/agents/{agent_id}/v1/message:send` and
asserts the response shape. Also verifies:
- `run_id` is in `result.metadata` (so RunTrace page can be opened)
- After running, `GET /api/runtime/runs/{run_id}/trace` returns the
  timeline with `user_message_received` + `completion` events
- Unknown agent_id → HTTP 404 with JSON-RPC error envelope

### V3: Hub visibility

```
GET /api/icoder/agents/hub
```

Returns 11 cards. 4 are now `runnable=true` (was 1):
- `medical-coding-agent` (existing MVP)
- `code-validation-agent` (new)
- `compliance-guardrail-agent` (new)
- `note-completeness-agent` (new)

Verified by `test_phase3d1_three_simple_agents_visible_and_runnable`
in `tests/integration/icoder/test_phase3b1_agent_hub.py`.

### V4: A2A discovery

```
GET /api/icoder/agents
```

Returns 5 cards: `medcoder-coding-review` + `medical-coding-agent` +
3 new agents. The 7 metadata-only certified packs (cdi-review /
denial-appeals / diagnosis-extractor / documentation-gap / drg-analyzer /
evidence-ranker / procedure-extractor) correctly stay out of A2A
discovery.

### V5: Clone / Chat path

The Hub already wires `clone_url` / `chat_url` for any pack with
`runnable=true`. The 3 new packs inherit this automatically:
- `clone_url = /api/icoder/agents/{agent_id}/clone`
- `chat_url = /agents/{project_agent_id}/chat` (after clone)

The existing `AgentChatPage.tsx` (Phase 3-B2 Loop 2) handles any
runnable agent_id via `runtimeAgentApi.runAgentViaA2A(runtimeAgentId,
input)`. The `_mapA2AResultToRunResult` projection in
`runtimeApi.ts` already handles arbitrary DataPart shapes — it extracts
`v2` from `dataPart.data` and exposes it as `result.structured`. The
frontend "JSON" tab renders it; "Rendered" tab falls back to
`generateFallbackMarkdown` since these agents don't pre-render
markdown (only medical-coding-agent does).

### V6: RunTrace integration

Each agent's run path emits 3 trace events via `emit_trace_event`:
1. `USER_MESSAGE_RECEIVED` with `{agent_id, input_parts}` (display-safe)
2. `OUTPUT_GENERATED` with `{review_conclusion, issues_count}`
3. `COMPLETION` with `status=ok` or `status=failed`

`GET /api/runtime/runs/{run_id}/trace` returns the timeline. The
RunTracePage renders it. The "View RunTrace" button on AgentChatPage
links to it (Phase 3-D1 Task 4 wired this — works for all agents
uniformly since `result.run_id` is set).

### V7: Markdown + JSON output

- **JSON tab**: `result.structured` is the agent's output dict;
  rendered as pretty-printed JSON.
- **Rendered tab**: `result.markdown` is absent for these agents
  (only medical-coding-agent pre-renders). The frontend's
  `generateFallbackMarkdown(result.structured || result)` auto-
  generates a minimal markdown from the structured output. Verified
  by code path inspection (no agent-specific markdown generator
  added — the fallback is sufficient for these simple deterministic
  outputs).

### V8: No fake / no stub

All 3 agents have real, deterministic implementations:
- Code Validation: runs the actual `MedicalCodingRuleSet` (12 rules)
- Compliance Guardrail: runs the rule set + 4 real guardrail heuristics
  with EMR text analysis for upcoding risk detection
- Note Completeness: real regex-based section detection with 7
  base sections + 1 conditional surgical section

No LLM is called. No mocks. No `ICODER_PHASE1_STUB_LLM` short-circuit.
The agent_card factories declare `maturity: "runnable"` and the
`DictAgentProvider` registers them with real `AgentDefinition`s.

## PASS criteria (Task 5)

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Code Validation Agent runnable (Hub visible / Clone / Chat / A2A) | ✅ |
| 2 | Compliance Guardrail Agent runnable (same) | ✅ |
| 3 | Note Completeness Agent runnable (same) | ✅ |
| 4 | Each supports markdown + JSON output | ✅ (JSON pre-rendered; markdown via fallback) |
| 5 | Each emits RunTrace events | ✅ (3 events per run) |
| 6 | Each has tests (unit + A2A smoke) | ✅ (18 unit + 5 smoke) |
| 7 | No fake / no stub | ✅ (real RuleEngine + heuristics + regex) |
| 8 | MCP tools declared in agent_pack.json | ✅ (1 tool per agent) |
| 9 | output_contract with required_fields | ✅ (7/7/7 fields) |
| 10 | No regressions in default sweep | ✅ (see below) |

## Files touched

- `backend/official_agents/code_validation/__init__.py` — NEW
- `backend/official_agents/code_validation/agent.py` — NEW (~150 LOC)
- `backend/official_agents/compliance_guardrail/__init__.py` — NEW
- `backend/official_agents/compliance_guardrail/agent.py` — NEW (~130 LOC)
- `backend/official_agents/note_completeness/__init__.py` — NEW
- `backend/official_agents/note_completeness/agent.py` — NEW (~110 LOC)
- `backend/official_agents/code-validation/agent_pack.json` — v1.1 → v1.2, maturity runnable
- `backend/official_agents/compliance-guardrail/agent_pack.json` — v1.1 → v1.2, maturity runnable
- `backend/official_agents/note-completeness/agent_pack.json` — v1.1 → v1.2, maturity runnable
- `backend/app/icoder/agent_runtime/a2a/agent_card.py` — +3 card factories
- `backend/app/icoder/agent_runtime/a2a/routes_discovery.py` — 3 agents in `_list_all_cards`
- `backend/app/main.py` — `_SimpleAgentDispatchHandler` + 3 agent imports + 3 cards in provider
- `backend/tests/unit/icoder/agent_runtime/test_three_runnable_agents.py` — NEW, 18 tests
- `backend/tests/integration/icoder/test_phase3d1_three_agents_a2a_smoke.py` — NEW, 5 tests
- `backend/tests/integration/icoder/test_phase3b1_agent_hub.py` — updated metadata-only list + added runnable test
- `backend/tests/integration/icoder/test_phase3b2_loop4_hub_use_case_filter.py` — updated runnable count 1→4
- `backend/tests/integration/icoder/test_phase3b1_discovery_unification_contract.py` — updated metadata-only + pack_refs lists
- `backend/tests/unit/icoder_runtime/test_agent_pack_loader.py` — v1.1 count 10→7, v1.2 cert count 1→4
- `backend/tests/unit/icoder_runtime/test_registry_status.py` — v1.1 count 10→7
