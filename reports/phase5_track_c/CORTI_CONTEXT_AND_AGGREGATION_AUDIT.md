# Corti Context + Aggregation Audit (Track C Gate 0B)

**Captured**: 2026-07-11
**Source**: PHASE4H-AUDIT-MC SSE streams + chat request bodies

---

## 1. Context model — Corti has 3 weak context layers

### 1.1 Layer 1: System Prompt (set once at agent creation)

Captured from PHASE4H-AUDIT-MC Settings tab (full text in `outputs/phase5_track_c/corti_network/corti_medical_coding_agent_sdk_code.ts`):

```xml
<role>You are a Medical Coding Agent...</role>
<output_format>...markdown structure...</output_format>
<constraints>
- Code ONLY what is explicitly documented
- Do not infer diagnoses, procedures, or clinical findings
- Do not apply clinical judgment beyond what is documented
- Do not optimize for reimbursement or suggest upcoding
- Quote exact documentation as evidence for every code assigned
- Flag all documentation gaps, ambiguities, and contradictions
- ...
</constraints>
<workflow>1. Synthesize Encounter 2. Extract Clinical Elements ... 7. Flag Uncodable Items</workflow>
<required_configurations>...</required_configurations>
<quality_standards>...</quality_standards>
```

**XML-tagged sections**, no variable substitution, no per-tenant override mechanism at runtime.

→ **iCoDer differentiator**: iCoDer's `ContextBuilder` (Gate 3) should support per-tenant system prompt fragments + per-encounter variable substitution (patient_id, encounter_type, region).

### 1.2 Layer 2: Message History (conversation_id)

Chat request body (Exp A, B, C, E all show same shape):

```json
{
  "agentDefinitionId": "c731e909-...",
  "id": "4c2f06c9-...",   // conversation_id (URL path param)
  "messages": [
    {"parts": [{"text": "...", "type": "text"}], "id": "O3fJADTjRQdfuBMT", "role": "user"}
  ],
  "projectId": "b8f8129a-...",
  "trigger": "submit-message"
}
```

→ **No first-class context fields**. No `patient_id`, `encounter_id`, `tenant_id`, `source_system`, `api_client_id`, `idempotency_key`.

The server returns `contextId` + `taskId` in `messageMetadata`, but these are server-generated per-message UUIDs, NOT user-supplied context.

### 1.3 Layer 3: File attachments (via "Drop JSON files here")

UI supports drag-and-drop JSON files into chat. Translation: the file content is appended to the message as additional `parts[]` entries (likely `type: "file"` or `type: "data"` parts per A2A v0.3 spec).

**Not exercised in Gate 0B** (Playwright file upload limitation). But the UI region `aria-label="Drop JSON files here to add them as context"` confirms this is the only structured-context channel.

---

## 2. Aggregation model — LLM is the aggregator

### 2.1 What Corti does NOT have

- No `aggregator.py` module
- No "Aggregator" Expert
- No `aggregation.started` / `aggregation.completed` events in SSE stream
- No `ConflictResolver` step

### 2.2 What Corti DOES have

For multi-tool calls (Exp B = 3 tools, Exp E = 2 experts), the LLM receives all `data-json` results in its conversation history and synthesizes a single markdown answer in `text-delta` chunks.

The "aggregation logic" lives entirely in the LLM's reasoning, guided by:
- System prompt's `<output_format>` template (strict markdown structure)
- System prompt's `<quality_standards>` (e.g., "When documentation contradicts itself, flag the contradiction")

### 2.3 Implication for iCoDer Gate 3 Aggregator

For **Corti-parity single-agent runs** (medical-coding-agent alone):
- **No Aggregator needed**. LLM's own reasoning suffices.

For **7-stage coding compliance mainline** (Gate 4):
- **Aggregator needed** because 7 sub-agents produce 7 separate outputs that must be merged.
- ConflictResolver needed because: medical-coding says "use I21.1", code-validation says "I21.19 wrong", compliance-guardrail says "denial risk".
- This is **iCoDer differentiator**, not Corti-parity work.

---

## 3. iCoDer Context spec alignment

Per memory `E--Corti4C-docs-ICODER_V1_CONTEXT_SPEC.md`, iCoDer planned Context spec has:
- `contextId` UUID v4 server-generated
- `patient_id`, `encounter_id`, `tenant_id`, `source_system`, `api_client_id`, `idempotency_key`
- PHI redaction layer
- 24h active + 7d physical delete + 90d audit GC

**Corti parity status**:
| iCoDer Context field | Corti equivalent | Status |
|---|---|---|
| contextId | messageMetadata.contextId (server-generated UUID) | PARITY |
| patient_id | (none) | iCoDer DIFFERENTIATOR |
| encounter_id | (none) | iCoDer DIFFERENTIATOR |
| tenant_id | project_id (Corti equivalent) | PARITY |
| source_system | (none) | iCoDer DIFFERENTIATOR |
| api_client_id | (none — Corti console uses Supabase JWT) | iCoDer DIFFERENTIATOR |
| idempotency_key | (none — Corti allows duplicate sends) | iCoDer DIFFERENTIATOR |
| PHI redaction | (none visible at API surface) | iCoDer DIFFERENTIATOR |

→ **iCoDer Context spec is strictly richer than Corti's**. Hospital integration scenarios (backend-service API Client + ROPC embedded Web Component) require these differentiators.

---

## 4. Track C Gate mapping

| Gate | Work item | Source: this audit |
|---|---|---|
| Gate 1 | StructuredOutputProjector — mirror Corti's `data-json` payload schemas (search_codes, verify, explore) | §3 of AGENT_EXPERT_TOOL_CALL_GRAPH.md |
| Gate 3 | CortiLikeOrchestrator — single LLM + function calling + SSE Vercel AI SDK v1 protocol | §1 of CORTI_ORCHESTRATOR_RUNTIME_AUDIT.md |
| Gate 3 | ContextBuilder — first-class context object (patient/encounter/tenant/source/api_client/idempotency) | §3 above |
| Gate 4 | Aggregator + ConflictResolver — only for 7-stage mainline, NOT for single-agent Corti-parity runs | §2 above |
| Gate 6 | SSE event projector — emit `Calling expert: <name>` + `data-json` + `text-delta` events | §1.1 of CORTI_ORCHESTRATOR_RUNTIME_AUDIT.md |

---

## 5. Verdict

**`PASS_CORTI_CONTEXT_AND_AGGREGATION_MODEL_SUFFICIENTLY_UNDERSTOOD`**

iCoDer's planned Context spec is strictly richer than Corti's. The Aggregator module should be scoped to the 7-stage mainline (Gate 4) only; for Corti-parity single-agent runs, the LLM's own synthesis suffices.
