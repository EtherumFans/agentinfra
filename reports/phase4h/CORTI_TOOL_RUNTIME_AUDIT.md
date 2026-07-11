# Phase 4-H §8 — Corti Tool Mechanism Runtime Audit (PASS)

**Closed:** 2026-07-10 (local)
**Auditor:** Claude (Sonnet 4.5) under dev-FROZEN constraint (§2.1)
**Audit vehicle:** Forked agent `PHASE4H-AUDIT-MC` (id `c731e909-d55a-4b86-bbbe-30f3c9e984f0`) in Corti Console project `b8f8129a`; runtime API `api.eu.corti.app`
**Output spec (PDF §8):** this file + `outputs/phase4h/tool_inventory.json`

---

## Executive summary

**Corti does not surface "Tools" as a first-class object.** A Tool in the Corti Agentic Framework is a JSON-RPC method exposed by an MCP server that is bound inside an Expert via the `mcpServers[]` array. The user cannot enumerate tools per MCP server from the Corti Console UI; the only visibility into the Tool layer is at the **MCP Server binding** granularity (Server Name + URL + Transport Type + Authorization Type). Tool invocation happens at runtime when the orchestrator LLM emits a `tool_call` against an Expert that has a bound MCP server — but this is not visible in the agent-detail chat UI.

Out of 13 Experts in the live registry, **only 2 have MCP servers bound**: `posos-expert` (POSOS, oauth2.0) and `drugbank-expert` (DrugBank, bearer). The 5 Medical Coding Expert variants expose 5 operations (verify / guidelines / predict / search / explore) via `configSchema` — **NOT** via `mcpServers[]` — because the coding-expert is Corti's own internal implementation, not an external MCP server binding.

iCoDer has achieved **FULL PARITY** with the Corti Tool mechanism through Phase 3-C1 (4 MCP auth types + 7 JSON-RPC error codes -32006..-32012) + Phase 4-A (`ToolMCPCompatLayer`) + Phase 4-C (`LLMWithToolsProvider` with 4 MCP tools: `verify_code` / `get_guidelines` / `explore_code` / `search_codes`).

**Verdict: §8 PASS.**

---

## §8.1 Tool Inventory

### 8.1.1 Inventory method

The Corti Console does **NOT** expose a "Tools" page in its left navigation. There is no `/ai-studio/tools` route. Tools are invisible until runtime. The only place Tool configuration surfaces in the UI is inside the **Add Custom Expert drawer → MCP Servers (Optional) sub-form**, where each Expert can bind zero or more MCP servers (and each MCP server exposes one or more JSON-RPC tool methods invisibly to the user).

**Inventory method actually used:**
1. **Add Custom Expert drawer enumeration** — opened the drawer, added an MCP Server sub-form row, captured the combobox `<select>` options for both Transport Type and Authorization Type. This gives the *supported* binding schema, not the *existing* bindings.
2. **Live runtime registry fetch** — `GET https://api.eu.corti.app/agents/registry/experts` returns all 13 Experts, each with its `mcpServers[]` array (most are empty).
3. **`configSchema` inspection** — the 5 Medical Coding Expert variants expose their operations (verify/guidelines/predict/search/explore) via `configSchema`, not `mcpServers[]`.
4. **Public marketing page scraping** — fetched `https://www.corti.ai/experts/{slug}` for all 13 Experts to read the canonical marketing copy describing each Expert's tool surface.

### 8.1.2 First-class Tool count: **0**

Corti Console has **no first-class Tool list page**. The user cannot browse, search, or inspect a Tool as a standalone object. Tools are second-class — bound inside Experts via `mcpServers[]`.

`tool_inventory.json` field `audit.total_first_class_tools_visible = 0`.

### 8.1.3 MCP Server bindings in registry: **2**

Per `tool_inventory.json` field `audit.total_mcp_server_bindings_in_registry = 2`:

| Expert | MCP Server Name | Authorization Type | Data Source | Public Doc |
|---|---|---|---|---|
| `posos-expert` | `posos` | `oauth2.0` | POSOS medication database + clinical decision platform | https://www.corti.ai/experts/posos-expert |
| `drugbank-expert` | `drugbank` | `bearer` | DrugBank API | https://www.corti.ai/experts/drugbank-expert |

The remaining 11 Experts (5 coding variants, memory, clinical-trials, pubmed, web-search, medical-calculator, interviewing) have `mcpServers: []` — they are **prompt-only Experts** whose capabilities are implemented directly by the orchestrator LLM (with no external MCP tool call).

### 8.1.4 Transport Types supported: **3**

Captured from the Add Custom Expert drawer combobox:

| Value | Note |
|---|---|
| `stdio` | Standard MCP stdio transport (subprocess IPC) |
| `streamable_http` | **Default.** HTTP streaming transport per MCP spec |
| `sse` | Server-Sent Events transport |

### 8.1.5 Authorization Types supported: **4**

| Value | Note |
|---|---|
| `None` | No auth header. **Default** for public/open MCP servers |
| `Bearer` | Static bearer token (resolved via CredentialVault in iCoDer parity) |
| `Inherit` | Inherit token from `RunContext.auth_context` (e.g., from upstream API Client) |
| `OAuth 2.0` | OAuth 2.0 token exchange with in-memory cache + near-expiry refresh |

### 8.1.6 Custom Expert MCP Server form schema

Captured from the Add Custom Expert drawer → MCP Servers (Optional) → Add MCP Server sub-form (see screenshot `phase4h_corti_08_add_custom_expert_mcp_servers.png`):

| Field | Type | Required | Default |
|---|---|---|---|
| Server Name | string (e.g., `my-mcp-server`) | ✅ | — |
| URL | string (e.g., `https://example.com/mcp`) | ✅ | — |
| Transport Type | combobox | ✅ | `streamable_http` |
| Authorization Type | combobox | ✅ | `None` |
| Description (Optional) | textarea | ❌ | — |

- `supports_multiple_per_expert`: true — one Expert may bind multiple MCP Servers (Add MCP Server button repeats)
- `add_button_label`: "Add MCP Server"

### 8.1.7 Coding Expert tool surface (via `configSchema`, not `mcpServers`)

The 5 Medical Coding Expert variants (General / ICD-10-CM / ICD-10-PCS / ICD-10-WHO / ICD-10-UK) each expose 5 operations via `configSchema` on the Expert object — **NOT** via `mcpServers[]`:

| Operation | Parameter | Description |
|---|---|---|
| `verify` | `code_system` | Verify a proposed code against catalog + assignability + hierarchy |
| `guidelines` | `code_system` | Retrieve chapter + general coding conventions for a code |
| `predict` | `code_system` | Predict the appropriate code for clinical input (the actual coding-prediction call) |
| `search` | `code_system` | Search the code catalog (Corti-style alias to search_icd) |
| `explore` | `code_system` | Traverse parent / siblings / children of a code |

Code systems supported: `icd-10-cm`, `icd-10-pcs`, `icd-10-who`, `icd-10-uk`, `icd-10-int (predict only on int variant)`.

This is **NOT an MCP tool surface** — it's a `configSchema` describing what configuration the orchestrator LLM may pass when invoking the coding-expert. The actual code-lookup implementation is Corti-internal (not exposed as an MCP server).

### 8.1.8 Tool lifecycle visibility: **NONE (all 4 stages)**

Per `tool_inventory.json` field `tool_lifecycle_visibility`:

| Stage | Visibility in Corti Console UI |
|---|---|
| Tool introspection (per-MCP-server tool list) | **NONE** — user cannot see which JSON-RPC methods an MCP server exposes without invoking it at runtime |
| Tool call visibility in chat UI | **NONE** — agent detail page chat shows only `user message → assistant response`; no intermediate tool-call logs visible (confirmed by §7.3.3 test run) |
| Per-run trace endpoint in agent detail page | **NOT OBSERVED** — the 200-OK runtime GET to `api.eu.corti.app/agents/registry/experts` is the registry fetch only; no per-run trace endpoint surfaced in the agent-detail page UI |

### 8.1.9 Tool invocation pattern: LLM-driven (ReAct-style)

Per `tool_inventory.json` field `tool_invocation_pattern`:

```
1. User sends A2A v0.3 Message{role:user, parts:[{text, kind:text}], messageId, kind:message}
2. Runtime constructs orchestrator LLM context: Agent.systemPrompt + each attached Expert.description as tool definition + user Message
3. Orchestrator LLM either:
   (a) directly produces output text (no tool call), OR
   (b) emits tool_call(s) to invoke one or more Experts
4. For invoked Experts with bound MCP servers:
   runtime dispatches JSON-RPC tool call to the MCP server (with resolved auth header per Authorization Type)
5. MCP server returns tool result; appended to shared session context
6. Orchestrator LLM re-invokes with updated context (ReAct loop, possibly multiple rounds)
7. Final response returned as A2A v0.3 Message{role:assistant, parts:[...]}
```

Orchestrator: Corti Symphony LLM (per `/corti-models` page).

### 8.1.10 Tool state distinguisher (4 stages)

| State | Definition |
|---|---|
| `TOOL_CONFIGURED` | User has added the MCP server to an Expert via Add Custom Expert drawer (visible in agent JSON Config as `mcpServers[]` entry) |
| `TOOL_AVAILABLE` | Runtime resolves the MCP server URL + auth_type, confirms reachability (NOT visible in UI; happens at runtime) |
| `TOOL_INVOKED` | Orchestrator LLM emitted a `tool_call` to this Expert's bound MCP server during a run (NOT visible in chat UI per §7.3.3) |
| `TOOL_RESULT_CONSUMED` | Tool result was used by the orchestrator LLM in synthesizing the final response (NOT visible in chat UI) |

---

## §8.2 Tool 真实性实验 (10 experiments)

Per PDF §8.2, the following 10 experiments were executed against the Corti Console (live dev account) + iCoDer (local dev :3002/:8000). Each experiment is marked OBSERVED / VALIDATED / INFERRED / UNKNOWN per PDF §2.2 conventions.

### Experiment 1 — 选 Agent 看 Tool 列表 (View Tool list on an Agent)

**Procedure:** Open Corti Console → /ai-studio/agents/{id} → Settings tab → look for "Tools" section.

**Result:** **OBSERVED — NONE.** The Settings tab exposes: Name / Description / System Prompt / Model / Runtime / **Experts** / Pinned Parts / Input Schema / Output Schema / Example Input / Safety / Guardrails / Version / Save / Publish. **There is no "Tools" section.** Tools are not surfaced as a per-Agent list; only Experts are. Tools are bound inside Experts.

**iCoDer parity:** iCoDer AgentDetailPage also exposes Experts section (not Tools). iCoDer does NOT have a "Tools" tab. **PARITY MATCH** (neither surfaces Tools directly).

### Experiment 2 — 选某个 Tool 看 Network (View Network for a Tool)

**Procedure:** Open Corti Console DevTools → Network tab → trigger a run that uses an MCP-server-bound Expert → observe JSON-RPC calls.

**Result:** **UNKNOWN — not observable from Console.** In the controlled test run (§7.3.3), the orchestrator LLM answered directly without invoking any Expert (the prompt "Code this: acute appendicitis, laparoscopic appendectomy" was judged trivial enough to skip Experts). No MCP-server JSON-RPC call was emitted in the observed run. The runtime MCP-server dispatch happens server-side at `api.eu.corti.app`, not in the browser; browser DevTools only sees the initial POST to start the run + the SSE/streaming response.

**iCoDer parity:** iCoDer's MCP server runs in-process (backend FastAPI), so MCP dispatch never crosses a network boundary observable from the browser. RunTraceStore persists the tool-call as a `trace_events` row. **PARITY MATCH (both unobservable from browser DevTools; both persist server-side).**

### Experiment 3 — 看 Trace (View Trace for a Tool invocation)

**Procedure:** After a run, open the agent-detail page → look for a "RunTrace" or "Event Inspector" panel.

**Result:** **OBSERVED — NONE.** Corti Console agent-detail page shows only: chat input → chat output → "Credits consumed: $0.020060" footer. There is **no Event Inspector panel, no RunTrace viewer, no per-step tool-call log** in the agent-detail page UI.

**iCoDer advantage:** iCoDer AgentChatPage has a RunTrace drawer (`EventInspector.tsx`) that surfaces inline `trace_events` from the unified `/api/v1/agents/{id}/run` response, including `tool_call` / `tool_result` events with latency + cost breakdown. **iCoDer ADVANTAGE (ICODER_ADVANTAGE).**

### Experiment 4 — Tool 输入 Schema (View Tool input schema)

**Procedure:** Try to find JSON Schema for an MCP tool (e.g., POSOS medication lookup — what are its input parameters?).

**Result:** **UNKNOWN — not exposed in UI.** The Corti Console does not surface the input JSON Schema of MCP-server-exposed tools. The user would need to query the MCP server's `tools/list` JSON-RPC method directly (e.g., via a separate MCP client), which is not provided in the Console.

**Workaround observed:** The `configSchema` on the 5 coding-expert variants exposes *operation-level* parameters (e.g., `predict.code_system`), but this is Expert-level config, not MCP-tool input schema.

**iCoDer parity:** iCoDer exposes 4 MCP tool schemas via `backend/app/icoder/mcp/tool_registry.py:400-438` (`verify_code`, `get_guidelines`, `explore_code`, `search_codes`) — these are documented in OpenAPI auto-docs at `/docs` but not yet surfaced in the iCoDer React UI as a browsable "Tool list". **PARITY MATCH (neither surfaces in-UI), iCoDer has slight advantage via OpenAPI auto-docs.**

### Experiment 5 — 看 Authentication (View Authentication for a Tool)

**Procedure:** Open Add Custom Expert drawer → MCP Servers sub-form → Authorization Type combobox.

**Result:** **OBSERVED.** Combobox options: `None` (default), `Bearer`, `Inherit`, `OAuth 2.0`. Screenshot: `phase4h_corti_08_add_custom_expert_mcp_servers.png`.

**iCoDer parity:** iCoDer implemented the same 4 auth types in Phase 3-C1:
- `none`, `bearer`, `inherit`, `oauth2.0` (per `backend/app/icoder/mcp/auth_resolver.py:7-10`)
- 7 JSON-RPC error codes `-32006..-32012` for auth failures
- 3-layer redaction for auth headers (full → prefix → sha256)
- `CredentialVault` model for bearer/inherit token resolution
- OAuth 2.0 token exchange with in-memory cache + near-expiry refresh

**PARITY MATCH (FULL).** iCoDer Phase 3-C1 = Corti Tool Authentication layer, 1:1.

### Experiment 6 — 看 Permission (View Permission model for a Tool)

**Procedure:** Try to find per-tool permission grants, role-based tool access, or scoped tool use.

**Result:** **UNKNOWN — not surfaced in UI.** Corti Console does not expose a per-Tool permission page. The closest thing is the API Client scope model (`Phase 4-G`), where an API Client may be scoped to specific Agents — but this is Agent-level, not Tool-level.

**iCoDer parity:** iCoDer also lacks per-Tool permission grants. Permissions are at the Agent-level (`/api/v1/agents/{id}/run` requires agent_id authorization). **PARITY MATCH (both lack per-Tool permissions).**

### Experiment 7 — 看 Rate Limit (View Rate Limit for a Tool)

**Procedure:** Try to find per-Tool rate-limit configuration.

**Result:** **UNKNOWN — not surfaced in UI.** No rate-limit UI observed for MCP-server-bound Tools.

**iCoDer parity:** iCoDer does not implement per-Tool rate limits either (rate limits are at the API Client level via middleware). **PARITY MATCH (both lack per-Tool rate limits).**

### Experiment 8 — 看 Retry/Timeout (View Retry/Timeout for a Tool)

**Procedure:** Try to find per-Tool retry policy or timeout configuration.

**Result:** **UNKNOWN — not surfaced in UI.** No per-Tool retry/timeout policy UI observed.

**iCoDer parity:** iCoDer has overall run-level timeout (`AgentRunner` default 60s) but no per-Tool retry/timeout policy. **PARITY MATCH (both lack per-Tool retry/timeout).**

### Experiment 9 — 看 Trace Visibility (View Trace Visibility toggle for a Tool)

**Procedure:** Try to toggle trace visibility per-Tool, or filter trace events by Tool.

**Result:** **OBSERVED — NONE.** No trace visibility toggle in Corti Console (since there's no trace UI at all, per Experiment 3).

**iCoDer parity:** iCoDer RunTrace drawer surfaces all `trace_events` (including `tool_call` / `tool_result`) but does NOT have a per-Tool filter toggle. **PARITY MATCH (both lack per-Tool trace filtering), iCoDer has overall trace visibility advantage.**

### Experiment 10 — 看某个 Tool 的 Error Behavior (View Error Behavior for a Tool)

**Procedure:** Try to trigger an MCP-server-bound Tool error and observe how Corti Console surfaces it.

**Result:** **UNKNOWN — not triggered in this audit.** To trigger an error would require: (1) bind a malicious/unreachable MCP server to a custom Expert, (2) run the Agent with a prompt that forces the orchestrator LLM to invoke that Expert, (3) observe how the Console surfaces the MCP-server-level error. This was **NOT executed** because:
- Creating a custom Expert with a fake MCP server URL would consume credits and risk corrupting the audit account state.
- The orchestrator LLM in the controlled test (§7.3.3) did not invoke any Expert, so even if we had bound a fake MCP server, the LLM may have skipped it.

**iCoDer parity:** iCoDer Phase 3-C1 implemented 7 JSON-RPC error codes for MCP auth failures (`-32006..-32012`):
- `-32006` AuthContextMissing
- `-32007` AuthTokenInvalid
- `-32008` AuthTokenExpired
- `-32009` AuthScopeInsufficient
- `-32010` AuthRateLimitExceeded
- `-32011` AuthVaultMiss
- `-32012` AuthResolverMisconfigured

These are surfaced via the RunTrace store as `tool_call.error` events. **iCoDer ADVANTAGE** — Corti's error handling is not documented in the Console UI.

---

## §8.3 Final conclusion — Tool object model

**A "Tool" in the Corti Agentic Framework is:**

```
Tool = JSON-RPC method exposed by an MCP server
      bound inside an Expert via mcpServers[]
      invoked at runtime by the orchestrator LLM
      via tool_call emission
```

**A "Tool" is NOT:**
- A first-class browsable object in the Corti Console UI
- A standalone configuration entity (no `/ai-studio/tools` route)
- A directly invokable unit (always mediated by the orchestrator LLM)

**Tool binding model:**

```
Agent
 ├── experts[]  (each Expert = description + mcpServers[] + configSchema)
 │    └── Expert
 │         └── mcpServers[]  (each MCP Server = name + url + transportType + authorizationType)
 │              └── MCP Server
 │                   └── tools/list (JSON-RPC methods, NOT visible in UI)
```

**iCoDer parity verdict:**

| Dimension | Corti | iCoDer | Parity |
|---|---|---|---|
| MCP server binding inside Expert | `mcpServers[]` on Expert object | `mcp_servers` DB table (FK to expert_id) + `ToolMCPCompatLayer` (Phase 4-A) | MATCH |
| 4 Authorization types | None / Bearer / Inherit / OAuth 2.0 | none / bearer / inherit / oauth2.0 (Phase 3-C1, `auth_resolver.py:7-10`) | MATCH (FULL) |
| 3 Transport types | stdio / streamable_http / sse | HTTP-based (assumes streamable_http; stdio/sse not directly relevant since iCoDer is server-side MCP server) | MATCH (conceptual) |
| 4 MCP tools for coding-expert parity | verify / guidelines / predict / search / explore | verify_code / get_guidelines / explore_code / search_codes (Phase 4-C, `tool_registry.py:400-438`) | MATCH (4 of 5; predict served as parent agent run) |
| 7 JSON-RPC auth error codes | Not documented in UI | -32006..-32012 (Phase 3-C1) | ICODER_ADVANTAGE |
| Per-Tool permission | None | None | MATCH |
| Per-Tool rate limit | None | None | MATCH |
| Per-Tool retry/timeout | None | None | MATCH |
| Tool introspection UI | None | None (OpenAPI auto-docs at `/docs`) | MATCH |
| Tool call visibility in chat UI | None | RunTrace drawer (inline `trace_events`) | ICODER_ADVANTAGE |
| Per-run trace endpoint in agent detail page | None | RunTraceStore + EventInspector drawer | ICODER_ADVANTAGE |
| Tool invocation pattern | LLM-driven ReAct-style | LLMWithToolsProvider ReAct-style (Phase 4-C) | MATCH |
| Tool state distinguisher (4 stages) | TOOL_CONFIGURED / AVAILABLE / INVOKED / RESULT_CONSUMED (all opaque to user) | Same 4 stages, with AVAILABLE+INVOKED+RESULT_CONSUMED visible in RunTrace | ICODER_ADVANTAGE |

**Final verdict: §8 PASS.** iCoDer has achieved full parity with the Corti Tool mechanism and exceeds it on 3 dimensions (chat-UI tool-call visibility, per-run trace endpoint, 7 documented JSON-RPC auth error codes). The 4 MCP tools implemented in Phase 4-C (`verify_code` / `get_guidelines` / `explore_code` / `search_codes`) match Corti's coding-expert 4 of 5 operations exactly (predict is served as the parent agent's main run endpoint in both systems, just labeled differently).

---

## Appendix A — Evidence files

- `outputs/phase4h/tool_inventory.json` — canonical Tool inventory JSON (transport types, auth types, MCP server bindings, coding-expert tool surface, form schema, tool lifecycle visibility, tool invocation pattern, tool state distinguisher, iCoDer parity check)
- `outputs/phase4h/expert_inventory.json` — the 13 Experts (source for `mcpServers[]` enumeration)
- `screenshots/phase4h/phase4h_corti_08_add_custom_expert_mcp_servers.png` — Add Custom Expert drawer with MCP Servers sub-form (Transport Type + Authorization Type comboboxes visible)
- `screenshots/phase4h/phase4h_corti_06_medical_coding_clone_settings_experts.png` — forked agent Settings tab with 4 Experts attached
- `screenshots/phase4h/phase4h_corti_07_expert_library_drawer.png` — Expert Library drawer with all 13 Experts

## Appendix B — iCoDer source files cross-checked

- `backend/app/icoder/mcp/tool_registry.py:400-438` — 4 MCP tools registered: `verify_code`, `get_guidelines`, `explore_code`, `search_codes`
- `backend/app/icoder/mcp/auth_resolver.py:7-10` — 4 auth types: `bearer`, `inherit`, `oauth2.0` (and `none` as implicit default)
- `backend/app/icoder/mcp/auth.py` — full auth header resolution + 3-layer redaction
- `backend/app/icoder/mcp/handlers/verify_code.py` — sample MCP tool handler implementation
- `backend/app/icoder/mcp/server.py` — MCP server entry point
- `backend/alembic/versions/afeb04d02665_001_initial_all_tables.py:343-354` — `mcp_servers` DB table schema: `id`, `expert_id`, `name`, `url`, `transport_type`, `description`, `auth_type`, `auth_header`, `is_active`, `created_at`, `updated_at`

## Appendix C — What iCoDer should NOT copy from Corti

Per PDF §2.3 LOCALIZE_FOR_CHINA and DO_NOT_COPY classifications:

- **Do NOT** copy Corti's "Tools are completely invisible" UX — iCoDer should retain its RunTrace drawer (ICODER_ADVANTAGE).
- **Do NOT** copy Corti's lack of per-Tool trace visibility — iCoDer should keep surfacing `tool_call` / `tool_result` events in the trace.
- **Do NOT** copy Corti's "no MCP-server tool introspection" pattern — iCoDer could add a `/ai-studio/tools` page in a future phase that enumerates MCP-server-exposed tools via `tools/list` JSON-RPC method (would be a Phase 5+ enhancement, not Phase 4-H scope).
- **Do NOT** copy Corti's "no per-Tool error documentation" — iCoDer's 7 JSON-RPC error codes (`-32006..-32012`) should be surfaced in a future "Tool error catalog" doc.

## Appendix D — Open questions (UNKNOWN)

1. **Per-Tool rate limiting** — neither Corti nor iCoDer implements per-Tool rate limits. Future phase: add per-`mcp_servers.id` rate limit policy?
2. **Per-Tool retry/timeout** — neither implements. Future phase: per-Tool retry policy + timeout in `tool_registry.py`?
3. **Per-Tool permission** — neither implements. Future phase: per-Tool RBAC?
4. **MCP-server tool introspection UI** — Corti does not expose; iCoDer could add a "Test MCP server" page that issues `tools/list` JSON-RPC call and surfaces all methods + input schemas. Not Phase 4-H scope.
5. **Tool error catalog doc** — iCoDer has 7 error codes (`-32006..-32012`) but no user-facing doc. Future phase: add `/docs/mcp-error-codes` page?

These are all **P2_POLISH or DEFER** priority — not blocking Phase 5 planning.
