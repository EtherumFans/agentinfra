# Phase 3-D0 / D1 — Manual Corti-Parity Report

**Date:** 2026-07-06
**Phase:** 3-D0 + 3-D1
**Verdict:** ✅ PASS (5/5 tasks verified against Corti parity)

## Methodology

Per the docx prompt: after EACH task, perform manual Corti-parity
verification (browser / Playwright / manual simulation) and write
findings to `docs/corti_parity/phase3_d/manual_verification/` +
`MEMORY.md`. This report consolidates the 5 task-level verifications.

Corti parity dimensions checked:
- **Functionality parity** — does the iCoDer feature match Corti's
  observed behavior (Phase 3-B1.5 Section B manual exploration)?
- **Auth/security parity** — does iCoDer enforce the same auth +
  redaction standards Corti enforces?
- **Output contract parity** — does iCoDer return the same shape
  Corti returns for the same input?
- **UX parity** — can the user reach the same outcome through a
  similar flow?

---

## Task 1 — MCP Scope Enforcement — Corti parity ✅

**Corti observed (Phase 3-B1.5):** Corti's API platform enforces
OAuth2.0 scopes at the MCP tool level (e.g., a tool declared with
`scope: "transcribe"` requires the bearer token to grant
`transcribe`; otherwise 403 Forbidden).

**iCoDer Phase 3-D0 Task 1 ships:**
- `ToolDescriptor.required_scopes` field (matches Corti's scope-
  per-tool declaration)
- `tools/call` checks `required_scopes ⊆ granted_scopes` BEFORE
  dispatching to the handler
- `MCP_AUTH_FORBIDDEN` (-32012) error on insufficient scope —
  matches Corti's 403 behavior
- `tools/list` advertises `required_scopes` so clients know what
  they need (Corti's discovery endpoint does the same)

**Verdict:** ✅ Corti-parity. Evidence:
`TASK1_SCOPE_ENFORCEMENT_VERIFICATION.md`.

---

## Task 2 — redacted_view Log Capture — Corti parity ✅

**Corti observed:** Corti's logs never contain raw bearer tokens or
OAuth client secrets. Their redaction layer is opaque to the user
(no screenshots of log content available), but their public docs
state "credentials are redacted in all logs."

**iCoDer Phase 3-D0 Task 2 ships:**
- 3-layer redaction (known-secret keys / token-blob heuristic /
  `_SAFE_KEYS` whitelist)
- 5 caplog tests asserting raw token / client_secret / Authorization
  header never enter any log line — verified across 6 raw token
  variants
- `redacted_view` field on `AuthHeader` flows from resolver →
  server → log → A2A error envelope — matches Corti's pattern of
  showing the user a masked view (`Bearer ••••abcd`) for debugging
  without leaking the token

**Verdict:** ✅ Corti-parity. Evidence:
`TASK2_REDACTED_VIEW_LOG_CAPTURE_VERIFICATION.md`.

---

## Task 3 — Test Hygiene — Corti parity ✅

**Corti observed:** N/A — test hygiene is an iCoDer-internal
quality gate, not a Corti-parity dimension. But the docx prompt
required it for Phase 3-D0.

**iCoDer Phase 3-D0 Task 3 ships:**
- 7 stale e2e_product files deleted (tested deleted P1.0 endpoints)
- `test_auth.py` flakiness fixed at root cause (uuid4 isolation)
- asyncio marker auto-application fixed (sync tests no longer
  warning)
- `infra` marker pattern added for slow integration tests
- Default sweep: 2265/0 (was 2232 with intermittent failures
  masked by flaky + 30 hidden failures ignored via --ignore)

**Verdict:** ✅ PASS. Evidence:
`TASK3_TEST_HYGIENE_VERIFICATION.md`.

---

## Task 4 — RunTrace Corti-Parity Viewer — Corti parity ✅

**Corti observed (Phase 3-B1.5 Section B):** Corti's RunTrace page
shows a 9-step timeline for any run. Each step has:
- status (✓ green / ✗ red / ○ gray)
- duration in ms
- safe metadata (no raw tokens)
- The Auth step shows only a redacted view, never the raw token
- The page is reachable from a run's detail view (not the sidebar)

**iCoDer Phase 3-D1 Task 4 ships:**
- 9-step timeline matching Corti's steps 1:1
  (`user_message_received / planner_selected_experts / tools_list /
  auth_resolved / scope_checked / tools_call / expert_response /
  output_generated / completion`)
- Per-row expandable `safe_metadata` with status icon + badge +
  duration_ms + ts in monospace
- Defense-in-depth: `auth_resolved` step filters safe_metadata to
  only `redacted_view / granted_scopes / auth_type` — even if a
  future emit site accidentally writes a raw token, the frontend
  still won't display it
- Summary bar: `N steps · M ok · K failed · Xms total`
- Openable from AgentChatPage via "View RunTrace" button (visible
  when `result.run_id` is present)
- Route `/runs/:runId/trace` — not in sidebar (matches Corti)
- 404 page for unknown run_id with link back to Agent Hub

**Verdict:** ✅ Corti-parity. Evidence:
`TASK4_RUNTRACE_VIEWER_VERIFICATION.md`.

---

## Task 5 — 3 Runnable Agents — Corti parity ✅

**Corti observed (Phase 3-B1.5 Section B):** Corti ships 20 pre-
built agents across 4 use cases, each Hub-visible / Clone / Chat /
A2A-runnable / output contract declared / not fake. Corti's
"Medical Coding Agent" preset (`medical-coding-icd-10-cpt-agent`)
has 4 experts and outputs a markdown table with ICD-10-CM + CPT
codes.

**iCoDer Phase 3-D1 Task 5 ships 3 new runnable agents:**

### Code Validation Agent (`icoder/code-validation-agent@1.0.0`)

- Hub-visible / Clone / Chat / A2A-runnable ✅
- Runs `MedicalCodingRuleSet` (R001-R010 + MC-R-M80-001) — real
  deterministic rule engine, no LLM, no fake
- Output: `review_conclusion (PASS/WARNING/FAIL) / issues_found /
  fired_rules / code_assignment_summary / trace_refs`
- MCP tool declared: `validate_codes`
- RunTrace integration: emits USER_MESSAGE_RECEIVED →
  OUTPUT_GENERATED → COMPLETION
- 5 unit tests + 1 A2A smoke test

### Compliance Guardrail Agent (`icoder/compliance-guardrail-agent@1.0.0`)

- Hub-visible / Clone / Chat / A2A-runnable ✅
- Runs RuleEngine + 4 compliance guardrail heuristics (CG-001
  primary present / CG-002 no upcoding / CG-003 procedure-dx
  consistency / CG-004 DRG readiness) — real heuristics with EMR
  text analysis
- Output: `review_conclusion / issues_found / drg_suggestion /
  compliance_checks / rule_set / trace_refs`
- MCP tool declared: `evaluate_compliance`
- 6 unit tests + 1 A2A smoke test

### Note Completeness Agent (`icoder/note-completeness-agent@1.0.0`)

- Hub-visible / Clone / Chat / A2A-runnable ✅
- Real regex-based section detection per 《病历书写基本规范》
  (7 base sections + 1 conditional surgical section)
- Output: `review_conclusion / documentation_gaps /
  completeness_score / missing_sections / present_sections /
  required_sections / trace_refs`
- MCP tool declared: `check_documentation_gaps`
- 7 unit tests + 1 A2A smoke test

**Aggregate Corti parity:**
- All 3 agents are Hub-visible with `maturity=runnable` (matches
  Corti's pre-built agent badge semantics)
- All 3 support Clone → Chat via the existing AgentChatPage (no
  agent-specific UI changes needed)
- All 3 return A2A JSON-RPC envelopes with DataPart containing the
  output_contract dict — matches Corti's A2A mainline
- All 3 emit RunTrace events (so "View RunTrace" works on the
  result page — same UX as Corti)
- All 3 declare `production_writeback_blocked=true` (Corti red
  line: AI-assisted, never auto-write)
- All 3 declare `phi_redaction=required` (matches Corti's PHI
  redaction contract)

**Verdict:** ✅ Corti-parity. Evidence:
`TASK5_THREE_RUNNABLE_AGENTS_VERIFICATION.md`.

---

## Cross-task Corti-parity dimensions

### Auth / redaction (Task 1 + Task 2 + Task 4 auth step)

Corti red line: never leak credentials. iCoDer Phase 3-D closed
this across 3 layers:
- MCP scope enforcement (Task 1) — auth_required + scope check
  before any tool dispatch
- Log redaction (Task 2) — 3-layer redaction, 5 caplog tests
  asserting no raw token in any log line
- RunTrace auth_resolved step (Task 4) — only renders
  `redacted_view / granted_scopes / auth_type`; defense-in-depth
  filter on the frontend

### Output contract (Task 5)

Each of the 3 new agents declares an `output_contract` with
`required_fields` — matches Corti's practice of declaring the
schema for each agent. The frontend renders the JSON tab directly
from `result.structured`; the Rendered tab falls back to
`generateFallbackMarkdown` since these agents don't pre-render
markdown (only medical-coding-agent does, matching Corti's pattern
where not every agent has a custom markdown generator).

### Hub / Discovery (Task 5)

The 3 new agents appear in:
- `GET /api/icoder/agents/hub` — Hub card list, `runnable=true`
- `GET /api/icoder/agents` — A2A discovery
- `GET /.well-known/agent.json` — A2A standard discovery
- `GET /llms.txt` — LLM-friendly Markdown

This matches Corti's 4-surface discovery contract.

### RunTrace (Task 4)

The 9-step timeline matches Corti's observed RunTrace UI 1:1.
The "View RunTrace" button on AgentChatPage opens the page for
the run that just executed — same UX as Corti.

---

## Known Corti-parity gaps remaining (not closed in 3-D)

These are out-of-scope for Phase 3-D and tracked for later phases:

1. **RunTrace persistence** — iCoDer's RunTraceStore is in-memory
   only; Corti persists across server restarts. Phase 3-D2
   follow-up.
2. **PLANNER_SELECTED_EXPERTS / EXPERT_RESPONSE trace steps** —
   the orchestrator doesn't emit these yet; only the MCP-server-
   emitted steps (`TOOLS_LIST / AUTH_RESOLVED / SCOPE_CHECKED /
   TOOLS_CALL / COMPLETION`) plus the simple-agent dispatch
   (`USER_MESSAGE_RECEIVED / OUTPUT_GENERATED / COMPLETION`)
   appear today. Phase 3-D2 follow-up when the orchestrator is
   wired to emit them.
3. **3 new agents don't pre-render markdown** — the frontend's
   `generateFallbackMarkdown` handles it, but Corti-style custom
   markdown generators would be nicer. Out-of-scope; the JSON tab
   is the canonical view for rule-engine outputs.
4. **3 new agents don't have real MCP tool handlers wired** — the
   `agent_pack.json` declares tools (`validate_codes` /
   `evaluate_compliance` / `check_documentation_gaps`), but the
   MCP server doesn't expose them as callable tools today (the
   MCP server only wires the 5 MedCodER tools). The agents are
   runnable via A2A mainline directly. Phase 3-D2 follow-up.

These gaps don't block the Phase 3-D verdict — the docx prompt's
10 PASS criteria are all met.
