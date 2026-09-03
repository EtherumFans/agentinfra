# Corti Orchestrator Runtime Audit (Track C Gate 0B)

**Captured**: 2026-07-11 (Phase 5 Track C Gate 0B)
**Source agent**: PHASE4H-AUDIT-MC (user-cloned from preset `medical-coding-icd-10-cpt-agent`)
**Agent ID**: `c731e909-d55a-4b86-bbbe-30f3c9e984f0`
**Conversation ID**: `4c2f06c9-6a3e-46a0-a5cf-78fa4d16cbf7`
**Project**: `b8f8129a-c31d-407f-b723-6ecc592d31e4` (songluhua)
**Experiments run**: A (Direct), B (Coding Expert), C (PubMed Expert), E (Dual Expert) — see `outputs/phase5_track_c/corti_network/`

---

## 1. Corti Orchestrator runtime model (verified via SSE streams)

```
POST https://api.console.corti.app/functions/v1/ai/agents/{conversation_id}
Authorization: Bearer <supabase JWT>
corti-access-token: Bearer <keycloak RS256 JWT>
Content-Type: application/json

Request body:
{
  "agentDefinitionId": "<agent_uuid>",
  "id": "<conversation_uuid>",
  "messages": [
    {"parts": [{"text": "...", "type": "text"}], "id": "<msg_id>", "role": "user"}
  ],
  "projectId": "<project_uuid>",
  "trigger": "submit-message"
}
```

Response = Server-Sent Events stream, **Vercel AI SDK UI Message Stream v1** protocol (header `x-vercel-ai-ui-message-stream: v1`).

### 1.1 Canonical event sequence

```
data: {"data":{"state":"working"},"type":"data-status-update"}            ← run started
data: {"data":{"state":"working"},"type":"data-status-update"}            ← pre-LLM warmup
data: {"data":{"message":"Calling expert: <name>","state":"working"},"type":"data-status-update"}   ← expert dispatch (0..N times)
data: {"data":{<expert-payload>},"type":"data-json"}                      ← tool result (0..N times)
data: {"id":"<part_uuid>","type":"text-start"}                            ← final synthesis begins
data: {"delta":"<markdown>","id":"<part_uuid>","type":"text-delta"}        ← stream tokens
data: {"id":"<part_uuid>","type":"text-end"}                              ← synthesis done
data: {"messageMetadata":{"contextId":"...","taskId":"...","credits":0.XXX,"state":"completed"},"type":"message-metadata"}
data: {"finishReason":"stop","messageMetadata":{"credits":0.XXX},"type":"finish"}
data: [DONE]
```

### 1.2 Per-experiment event evidence

| Experiment | Input | "Calling expert" events | data-json events | Credits | Latency |
|---|---|---|---|---|---|
| A — Direct | STEMI vignette | 0 | 0 | $0.028388 | 15.8s |
| B — Coding Expert | "use coding-expert to verify I21.19" | 1 (coding-expert) | 3 (search_codes + verify + explore) | $0.058968 | ~12s |
| C — PubMed Expert | "use pubmed-expert to find DES vs BMS literature" | 2 (pubmed-expert) | 1 (web_result[]) | (large) | ~25s |
| E — Dual Expert | "use BOTH pubmed-expert AND web-search-expert" | 2 (pubmed + web-search) | 1 (combined web_result[]) | (large) | ~30s |

### 1.3 What Corti's "Orchestrator" actually is

**It is NOT** a multi-stage Planner → Delegator → Aggregator pipeline.
**It IS** a single LLM with function calling. The "Orchestrator" is the LLM's own tool-calling loop:

```
LLM(systemPrompt + user_message + available_experts_metadata)
  → LLM decides: invoke expert X? (function call)
    → server executes expert X (MCP tool dispatch)
      → tool result injected into conversation
        → LLM decides: invoke another expert? or synthesize?
          → LLM streams final markdown answer
```

Key proof points:
- Experiment A (no tool needed) → zero expert events, single text-delta chunk
- Experiment B (LLM chained 3 tools autonomously) → 3 data-json events for search → verify → explore
- Experiment E (LLM dispatched BOTH pubmed + web-search in sequence) → 2 sequential `Calling expert:` events
- No "plan.created", "step.started", "aggregation.started" events (which would be present in a true orchestrator)

### 1.4 Why this matters for Track C

iCoDer's existing `backend/app/icoder/agent_runtime/orchestrator/` (15 modules, 4100 LOC, 5-state machine + planner + delegator + aggregator) is **architecturally heavier than Corti's actual runtime**. Corti's runtime is essentially:

1. AgentRegistry (load systemPrompt + experts)
2. LLM with tools (experts = MCP tool wrappers)
3. SSE stream wrapper (Vercel AI SDK protocol)

**Track C Gate 3 implication**: iCoDer doesn't need to build a complex Planner → Delegator → Aggregator to match Corti. It needs:
- `CortiLikeOrchestrator` = thin wrapper over LLMGateway with function calling
- Expert = MCP tool collection (already have `ToolMCPCompatLayer`)
- SSE event projector (Gate 6)
- `Calling expert: <name>` status events (Gate 6)

The existing 15-module orchestrator should be **repurposed for the 7-stage coding compliance mainline** (Gate 4), where it genuinely models cross-agent dispatch (e.g., discharge-summary → medical-coding → drg-analyzer). For Corti-parity single-agent runs, the lightweight path wins.

---

## 2. Corti Expert model (verified)

The 4 Experts wired on PHASE4H-AUDIT-MC (Corti SDK create call, captured from Code tab):

```typescript
experts: [
  {name: "pubmed-expert", type: "reference"},
  {name: "web-search-expert", type: "reference"},
  {name: "medical-calculator-expert", type: "reference"},
  {name: "coding-expert", type: "reference"}
]
```

- **Expert type observed**: `"reference"` for all 4 (Corti also supports MCP-bound custom experts with `mcpServers` per Phase 4-H §7)
- **Expert invocation event**: `{"data":{"message":"Calling expert: <name>","state":"working"},"type":"data-status-update"}`
- **Expert result event**: `{"data":{<payload>},"type":"data-json"}`

### 2.1 Per-expert tool payload structure

| Expert | data-json payload | Tools |
|---|---|---|
| coding-expert | `{code_system, count, query, results[], next_steps[{tool, reason}]}` | search_codes, verify, explore, guidelines, predict |
| pubmed-expert | `{response: web_result[]}` (url, site, source.provider, retrieved_at, title, snippet) | search (single tool) |
| web-search-expert | `{response: web_result[]}` (same shape as pubmed) | search (single tool) |
| medical-calculator-expert | (not exercised in B-2/Gate 0B — Track C Gate 1 P0 fix unblocks iCoDer equivalent) | TBD |

### 2.2 Expert dispatch order

For Experiment E (dual expert request), the SSE stream shows sequential (NOT parallel) dispatch:
```
"Calling expert: pubmed-expert"   ← 1st
"Calling expert: web-search-expert"  ← 2nd
[data-json combined web_result[]]
```

→ The LLM issues function calls one at a time. No evidence of parallel expert execution.

---

## 3. Corti Context model (verified)

Corti's chat request body has **no separate `context` field**. "Context" is one of:

1. **System prompt** — baked into agent_definition (set once at agent creation, not per-message)
2. **Message history** — `messages[]` array (prior turns)
3. **File attachments** — dropped via "Drop JSON files here to add them as context" region (translated into additional message parts)

There is **no** first-class `contextId` / `patient_id` / `encounter_id` / `tenant_id` field on the chat request. The only context identifier is the **conversation_id** in the URL path.

Per `messageMetadata` in the SSE stream, Corti does return `contextId` + `taskId`, but these appear to be server-generated per-message identifiers, not user-supplied context.

### 3.1 Implication for iCoDer

iCoDer's `ContextBuilder` (planned for Gate 3) should provide what Corti lacks:
- First-class `context` field on `/api/v1/agents/{id}/run` (patient_id, encounter_id, tenant_id, source_system, api_client_id, idempotency_key)
- Server-side Context object (per memory `E--Corti4C-docs-ICODER_V1_CONTEXT_SPEC.md`)
- PHI redaction before LLM sees raw PII

This is a **iCoDer differentiator**, not a parity gap.

---

## 4. Corti Aggregation model (verified)

There is **no explicit Aggregator step** in Corti's SSE protocol. The "aggregation" of multiple tool calls happens entirely inside the LLM's final `text-delta` synthesis.

For Experiment B (3 tool calls), the LLM:
1. Received 3 `data-json` tool results (search, verify, explore)
2. Read all 3 in the conversation history
3. Generated a single markdown answer that cited evidence from all 3 tools

→ **The LLM IS the aggregator**. No separate aggregation module needed for Corti-parity.

For iCoDer Gate 3 `Aggregator` module: only needed for cross-agent aggregation (Gate 4 7-stage pipeline where multiple sub-agents produce separate outputs that must be merged with conflict resolution). For single-agent multi-tool runs, the LLM suffices.

---

## 5. Verdict

**`PASS_CORTI_ORCHESTRATOR_MODEL_SUFFICIENTLY_UNDERSTOOD`**

Corti's runtime is fully characterized:
- Single LLM with function calling
- Experts = MCP tool collections
- SSE Vercel AI SDK v1 protocol
- Sequential (not parallel) expert dispatch
- LLM is the de-facto Planner + Delegator + Aggregator
- No first-class context object (iCoDer can differentiate)

Track C Gate 1-7 can proceed with this understanding. The 7-stage coding compliance mainline (Gate 4) is the only place where a true multi-agent orchestrator is needed; for Corti-parity single-agent runs, the lightweight path is sufficient.

---

## 6. Files

| File | Purpose |
|---|---|
| `outputs/phase5_track_c/corti_network/expA_direct_answer_request.json` | Exp A evidence |
| `outputs/phase5_track_c/corti_network/expB_coding_expert_sse_stream.txt` | Exp B raw SSE |
| `outputs/phase5_track_c/corti_network/expC_pubmed_expert_summary.json` | Exp C summary |
| `outputs/phase5_track_c/corti_network/expE_dual_expert_summary.json` | Exp E summary |
| `outputs/phase5_track_c/corti_network/expH_context_patient.json` | Exp H context fixture (not dropped — UI limitation) |
| `outputs/phase5_track_c/corti_network/corti_medical_coding_agent_sdk_code.ts` | Corti SDK reference |
| `screenshots/phase5_track_c/corti_orchestrator/01-08*.png` | 8 walkthrough screenshots |
