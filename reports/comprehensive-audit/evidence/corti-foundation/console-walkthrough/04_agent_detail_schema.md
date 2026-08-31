# Corti Agent Detail Page — Card Schema + SDK Signature (Verified)

> Source: `https://console.corti.app/project/4c4193c7-.../ai-studio/agents/fa3be93e-d1b3-45ef-ae8c-3a07c8d19ef2`
> Agent slug: `icoder-g8-cdi-ref` (user-created, CDI Documentation and Query Orchestrator)
> Evidence: `04_agent_detail_settings.png` + `05_agent_code_js_sdk_signature.txt`

## Layout (matches prior memory from Phase 4-D)

- Left pane: chat surface — "Ask the agent..." input + "Add context" + "Messaging an agent consumes credits" disclaimer
- Right pane: 2 tabs — **Settings** | **Code**
- Top right: API Client selector + live $0.000000 cost counter (per-run, resets on select)

## Settings tab — what's configurable

| Field | Type | Constraints |
|-------|------|-------------|
| Name | text | **50 char limit** (this agent used 17/50) |
| System prompt | textarea | Free-form; Corti uses XML-tagged sections (`<constraints>...</constraints>`) |
| Experts (bound) | list | 4 experts bound here; type=`reference` for all |
| Custom experts | list | "Add expert" button — bring-your-own MCP server |
| Pinned message parts | list | Context pinning across messages |

## Experts bound to this agent (live snapshot)

| Expert slug | Type | Category (per docs/overview) |
|-------------|------|------------------------------|
| `pubmed-expert` | reference | Knowledge & clinical reference |
| `web-search-expert` | reference | Knowledge & clinical reference |
| `medical-calculator-expert` | reference | Computation & structured workflows |
| `coding-expert` | reference | Medical coding (general) |

"Browse Expert Library" CTA appears below — confirms expert is a Corti-managed library, not user-uploaded.

## Code tab — three generators

1. **JavaScript (SDK)** — `@corti/sdk`
2. **.NET (SDK)** — `Corti.Client` (C#)
3. **JSON Config** — raw API payload

## Authoritative JS SDK signature (verified from Console)

```typescript
import { CortiClient } from "@corti/sdk";

const cortiClient = new CortiClient({
  auth: {
    accessToken: "<access-token>", // provide an access token retrieved by your authentication flow
  },
});

const agent = await cortiClient.agents.create({
  name: "icoder-g8-cdi-ref",
  experts: [
    { name: "pubmed-expert",            type: "reference" },
    { name: "web-search-expert",        type: "reference" },
    { name: "medical-calculator-expert", type: "reference" },
    { name: "coding-expert",            type: "reference" },
  ],
  description: "Identify documentation gaps in clinical charts and generates compliant provider queries to improve coding accuracy",
  systemPrompt: "You are the CDI Documentation and Query Orchestrator..."
});
```

### SDK shape observations

- Package: `@corti/sdk` (only on Corti side; iCoDer equivalent is `@icoder/sdk` per Gate 8 of Phase 4)
- Constructor takes `auth.accessToken` directly (no client_id/secret at SDK construction — auth is upstream)
- Method chain: `cortiClient.agents.create({...})` — flat namespace
- Expert shape: `{ name: string, type: "reference" }` (other types not exercised here but enum is open)
- `description` and `systemPrompt` are both required string fields
- No `agentId`, no `tenantId`, no `region` in the create payload — those come from the access token's claims (project scoping)

## System prompt — structural observations

The agent's system prompt (CDI orchestrator) reveals Corti's prompt conventions:

1. **Persona framing**: "You are the CDI Documentation and Query Orchestrator, a specialized agent within the Corti Agentic Framework."
2. **Inputs/outputs**: "You receive chart excerpts containing clinical notes, labs, imaging impressions, and orders. You may also receive optional encounter metadata such as setting, specialty, and dates."
3. **Expert enumeration**: "You have access to three specialized Experts." → then names them:
   - Medical Coding Expert (coding specificity, query targets, ICD-10)
   - AMBOSS Expert (clinical criteria, diagnostic definitions, staging)
   - CDI Web Search Expert (current guidelines, compliance, official definitions)
4. **Authority chain**: "You are the final authority. Any Expert output that violates your constraints must be rejected and omitted from your response."
5. **XML-tagged constraints block**: `<constraints>...</constraints>` containing hard rules:
   - Use only explicitly-present chart info
   - Never infer missing facts
   - No treatment advice
   - All queries must be non-leading

### Staleness observation

The system prompt references "AMBOSS Expert" but the bound experts list shows `pubmed-expert`, `web-search-expert`, `medical-calculator-expert`, `coding-expert` — none of which is `amboss-expert`. This is a **prompt-binding mismatch** (stale template text). Implications:

- Corti's CDI preset template was drafted against an older expert set that included AMBOSS.
- The current binding swapped AMBOSS → Pubmed + Medical Calculator + Web Search + Coding, but the prompt text was not updated.
- This means Corti's preset prompts are **not auto-synced with bindings** — a finding relevant for iCoDer's preset design.

## AMBOSS expert (new discovery)

Although not bound to this agent, **AMBOSS is a Corti Expert** (clinical knowledge base, German-origin, used in European medical education). Not in the 13 prebuilt list from `experts/overview` page (which lists Memory, POSOS, DrugBank, PubMed, Clinical Trials, Web Search, 5 ICD variants, Medical Calculator, Interviewing).

This suggests Corti has **more experts than the docs page lists** — either:
- AMBOSS is GA but missing from the docs overview page, OR
- AMBOSS is in limited preview (EU only), OR
- AMBOSS was deprecated between doc-publish and agent-creation

Pre-A0 Gate 4 (Prebuilt Expert Business Relevance) must account for AMBOSS.

## Agent run state surface

The chat pane shows the agent is "ready to message" — no separate "deployment" or "publish" step. **Agents are live immediately upon save** in Corti's model. This differs from iCoDer where AgentPackageV1 has a `pack → publish → install` lifecycle.

Implications for parity:
- Corti = agents live on save (zero-step deploy)
- iCoDer = agents require pack/install (matches Corti's doc-described model but adds friction for console-created agents)

## Card / agent ID format

- UUID v4: `fa3be93e-d1b3-45ef-ae8c-3a07c8d19ef2`
- Project ID (tenant): `4c4193c7-c6bb-4a71-a275-0ed6c53172d0` (also UUID v4)
- Agent slug is not separately stored — the `name` field is the user-facing identifier; the UUID is the canonical handle
- Preset ID (from earlier URL `?preset=medical-coding-icd-10-cpt-agent`): kebab-case string identifier
