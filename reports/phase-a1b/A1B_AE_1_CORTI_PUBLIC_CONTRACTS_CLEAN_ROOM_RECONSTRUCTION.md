# A1B-AE.1 — Corti Public Agentic Contracts: Clean-Room Reconstruction

**Charter**: A1B-AE.0 (v1.0, 2026-07-22)
**Worktree**: `E:/Corti4C-agent-expert`
**Branch**: `phase-a1b/agent-expert-clean-room`
**Captured**: 2026-07-22 (UTC)
**Execution mode**: HUMAN_OPERATION_SIMULATION_REQUIRED — headed Chrome 150 via CDP port 9222, Playwright MCP driver
**Observation count**: 8 public pages, 0 access-control blocks, 0 captcha/Cloudflare blocks

---

## §1. Observation summary

| # | Page | URL | Status |
|---|---|---|---|
| 00 | Documentation welcome | `https://docs.corti.ai/get_started/welcome` | PASS |
| 01 | Agentic Framework overview | `https://docs.corti.ai/agentic/overview` | PASS |
| 02 | System Architecture | `https://docs.corti.ai/agentic/architecture` | PASS |
| 03 | Experts | `https://docs.corti.ai/agentic/experts` | PASS |
| 04 | Context & Memory | `https://docs.corti.ai/agentic/context-memory` | PASS |
| 05 | A2A Protocol | `https://docs.corti.ai/agentic/a2a-protocol` | PASS |
| 06 | Core Concepts | `https://docs.corti.ai/agentic/core-concepts` | PASS |
| 07 | Create Agent API | `https://docs.corti.ai/agentic/agents/create-agent` | PASS |

Per-page structured observations live in
`reports/phase-a1b/evidence/corti_observation/<NN_slug>/observation.json`.
Screenshots (where captured) live alongside as `after_*.png`.

### §1.1 Clean-room attestment

All contracts reconstructed below are derived **only** from:
- publicly visible text on the pages listed above;
- publicly visible request/response example bodies in the API reference;
- the public A2A protocol specification at `https://a2a-protocol.org`;
- the public MCP specification.

**No Corti-internal code, prompt, UI asset, trademark, login-gated content, or
customer traffic capture was used.** All example prompts authored downstream
from these contracts MUST declare `clean_room_authored: true` per Charter §7.

### §1.2 Pages NOT visited in this commit (deferred)

For context-budget discipline, the following visible sibling pages were NOT
visited in A1B-AE.1; they are queued for A1B-AE.2 or a follow-up sub-gate:

- `/agentic/beginners-guide` (tutorial; not contract-bearing)
- `/agentic/quickstart` (tutorial; not contract-bearing)
- `/agentic/orchestrator` (contract-bearing — queued)
- `/agentic/sdks-integrations` (SDK links; not contract-bearing)
- `/agentic/mcp-authentication` (contract-bearing — queued; needed for `authorizationType` enum)
- `/agentic/faq` (non-normative)
- `/agentic/available-experts` or equivalent (CRITICAL — needed for full Expert enumeration including coding-expert variants; queued for A1B-AE.2)
- Individual Expert reference pages (e.g. `/agentic/experts/memory-expert`) — CRITICAL for per-expert config requirements; queued for A1B-AE.2/3
- Agent API siblings: `/agentic/agents/list-agents`, `/agentic/agents/get-agent-by-id`, `/agentic/agents/{id}/v1/message:send` (CRITICAL; queued for A1B-AE.4)
- `/agentic/agents/delete-agent`, update, clone (if they exist — TBD)

These deferred pages are marked `UNKNOWN` in the contract tables below.

## §2. Agent contract (clean-room)

### §2.1 Agent resource shape (response 201)

```
{
  "id":            "<server-generated string>",
  "name":          "<string>",
  "description":   "<string>",
  "systemPrompt":  "<string>",
  "experts":       [<Expert>],
  "mcpServers":    [<McpServer>]
}
```

Source: `/agentic/agents/create-agent` 201 response example (page 07).

### §2.2 Agent create request

```
POST /agents
Host: https://api.{environment}.corti.app
Headers:
  Authorization: Bearer <token>
  Tenant-Name: <tenant-name>      (required; multi-tenant routing)
  Content-Type: application/json
Query:
  ephemeral: boolean (default false)
Body:
{
  "name":         "<string, required>",
  "description":  "<string, required>",
  "agentType":    "<enum: expert | orchestrator | interviewing-expert>",   // optional
  "systemPrompt": "<string, optional; default orchestrator prompt when omitted>",
  "experts":      [<Expert>],     // optional
  "mcpServers":   [<McpServer>]   // optional; if omitted, agent cannot call any MCP servers
}
```

### §2.3 Agent type enum (PUBLIC, exactly 3 values)

| Value | Corti-listed semantics |
|---|---|
| `expert` | (one of the three Corti public agent types; semantics not elaborated on observed pages) |
| `orchestrator` | default multi-expert compose-and-delegate agent (architecture page §1) |
| `interviewing-expert` | structured-questionnaire driver ( Experts page §3 — `interviewing-expert` registry entry) |

**iCoDer implication**: Any iCoDer Preset Agent whose type is NOT one of these
three values MUST be tagged `origin = ICODER_CLEAN_ROOM` and `official_corti_preset = false`
per Charter §17.

### §2.4 Agent ephemeral flag

`ephemeral=true` query param → agent is:
- NOT listed in `agents_list`
- still fetchable by ID
- deleted periodically by Corti

### §2.5 Agent error envelope

```
{
  "code":        "<string>",
  "description": "<string>",
  "howToFix":    "<string>",
  "details":     {},
  "cause":       {}
}
```

Validation-error extension adds a `detail[]` array with field-level
`{location, reason}` pairs.

Status codes observed: `201` (created), `400` (bad request), `401` (auth),
`422` (validation).

## §3. Expert contract (clean-room)

### §3.1 Expert definition (Corti public, verbatim)

> "An Expert is an LLM-powered capability that an AI agent can utilize. Experts
> are designed to complete small, discrete tasks efficiently, enabling the
> Orchestrator to compose complex workflows by chaining multiple experts
> together."

**iCoDer alignment verdict**: **ALIGNED**. iCoDer Charter §9 definition is a
stricter superset (adds declared dependencies, data egress, citations, failure
modes, deterministic / licence / maturity flags). Corti's looser public
definition is consistent with iCoDer's.

### §3.2 Expert Registry — 9 PUBLIC KEYS (Corti-listed, "frequently-used sample")

| Key | Corti-listed purpose (verbatim) | iCoDer A1B-AE implementation target |
|---|---|---|
| `memory-expert` | Recall and analyze content from large in-request contexts and files | A1B-AE.5 Memory Expert (lexical baseline; semantic tier optional) |
| `coding-expert` | Assign diagnosis and procedure codes from notes | A1B-AE.7 Coding Expert wrapper (delegates to `icoder/medical-coding-agent`) |
| `medical-calculator-expert` | Compute BMI, HbA1c, glucose conversions, etc. | A1B-AE.6 Calculator Expert (deterministic, no LLM arithmetic) |
| `drugbank-expert` | Drug information and interaction lookups | A1B-AE.7 DrugBank stub (LICENSE_REQUIRED; no LLM fallback) |
| `posos-expert` | Medication guidance and prescribing decision support | A1B-AE.7 POSOS stub (LICENSE_REQUIRED; no LLM fallback) |
| `pubmed-expert` | PubMed literature search and abstracts | A1B-AE.6 PubMed Expert (NCBI E-utilities; synthetic queries only) |
| `clinical-trials-expert` | Search clinical trial registries | A1B-AE.6 Clinical Trials Expert (clinicaltrials.gov; synthetic queries only) |
| `web-search-expert` | Search and retrieve up-to-date web content | A1B-AE.7 Web Search (DISABLED_BY_POLICY default; opt-in per Provider) |
| `interviewing-expert` | Drive structured questionnaire interviews | A1B-AE.7 Interviewing Expert (schema-driven) |

Corti notes "this is a minimal sample" — full list (including coding-expert
variants like icd-10-cm / icd-10-pcs / icd-10-uk / icd-10-int) lives on the
deferred `available-experts` page (UNKNOWN until crawled).

### §3.3 Expert inline-create payload (nested inside Agent create)

```
{
  "type":         "new",                    // literal for inline creation
  "name":         "<string>",
  "description":  "<string>",
  "systemPrompt": "<string>",
  "mcpServers":   [<McpServer>]
}
```

Source: `/agentic/agents/create-agent` body example, "Option 1" for experts[].

### §3.4 Expert reference payload (response shape)

```
{
  "type":         "expert",                 // literal in responses
  "id":           "<server-generated>",
  "name":         "<string>",
  "description":  "<string>",
  "systemPrompt": "<string>",
  "mcpServers":   [<McpServer>]
}
```

### §3.5 "Bring Your Own Expert" pattern

A custom Expert is created by:
1. Implementing an MCP server that complies with the public MCP spec
   (tools/list, tools/call endpoints).
2. Registering it; Corti wraps the MCP server in a custom LLM agent with a
   caller-controlled system prompt.
3. Once registered, the Expert is available to the Orchestrator alongside
   built-in Experts.

## §4. MCP Server contract (clean-room)

### §4.1 MCP server request shape (write path — token included)

```
{
  "name":              "<string>",
  "url":               "<string>",
  "description":       "<string>",
  "authorizationScope":"<string>",
  "redirectUrl":       "<string>",
  "token":             "<string, write-only>"
}
```

### §4.2 MCP server response shape (read path — token NEVER returned)

```
{
  "id":                "<server-generated>",
  "name":              "<string>",
  "url":               "<string>",
  "authorizationScope":"<string>",
  "redirectUrl":       "<string>"
}
```

### §4.3 MCP server requirements (Corti-listed)

1. Implement the public MCP specification.
2. Expose tools via standard `tools/list` and `tools/call` endpoints.
3. Handle authentication.

### §4.4 Charter §6.4 compliance

iCoDer `McpServerRegistry` MUST:
- store `secret_reference` (lookup key into SecretProvider) instead of plaintext `token`;
- never return the token in any read path;
- record transport / URL / authorization type / allowed tools / egress classification.

This is **stricter than Corti's public contract** (Corti accepts plaintext
`token` on write). iCoDer will accept `token` on write but immediately vault
it and persist only a `secret_reference`, returning the same response shape.

## §5. Agent Card contract (clean-room)

### §5.1 Definition (Corti public, verbatim)

> "The Agent Card is a JSON document that serves as a digital business card for
> initial discovery and interaction setup."

### §5.2 Listed key fields

- identity
- service endpoint (URL)
- A2A capabilities
- authentication requirements
- list of skills

### §5.3 iCoDer scope

The detailed Agent Card schema is already specified in iCoDer
`docs/ICODER_V1_AGENT_CARD_SPEC.md`. A1B-AE.4 will verify alignment with
these Corti-public fields and add the iCoDer-specific extensions (skills
enumeration, signed trace_url, region).

## §6. Message / Part / Artifact / Task / Context (clean-room)

### §6.1 Message

- Fields: `role` (`"user"` | `"agent"`), `messageId` (unique), `parts[]`
- Design: modality-independent; mixes text + structured data + files

### §6.2 Part kinds (3, publicly enumerated)

| Kind | Carries | Corti support status |
|---|---|---|
| `TextPart` | plain textual content | supported |
| `DataPart` | structured JSON (clinical facts, EHR IDs, workflow params) | supported |
| `FilePart` | file (inline Base64 OR URI; has `name` + `mimeType`) | **NOT YET FULLY SUPPORTED** by Corti (flagged on page 06) |

### §6.3 Artifact

- Fields: `artifactId`, `name`, `parts[]`
- Tied to Task lifecycle; can be streamed incrementally
- Typical Corti-listed examples: SOAP notes, discharge summaries, coding suggestions

### §6.4 Task (per Corti-listed semantics; full state machine lives in A2A spec)

- Long-running operation handle
- Response mode alternative to immediate Message
- Streaming updates supported (SSE)
- Polling endpoint for status + result retrieval
- Full state machine (submitted / working / input_required / completed / failed / canceled) lives in public A2A spec at `a2a-protocol.org`; iCoDer Charter §6 honours these 6 states exactly.

### §6.5 Context

- Server-generated `contextId` ONLY (never client-generated)
- Logical grouping of Messages + Tasks + Artifacts
- Strict isolation: data NEVER leaks across contexts
- Cross-context sharing requires explicit `DataPart` in messages
- Recommended pattern: one fresh context per interaction

### §6.6 Memory

- RAG-like pipeline
- Auto-indexes every TextPart + DataPart + Artifact in the context
- Semantic retrieval (not just keyword)
- Just-in-time injection into agent prompt

**iCoDer Charter §13.1 baseline**: lexical-only retrieval (`MEMORY_RUNTIME=LEXICAL_ONLY`).
This is **strictly weaker** than Corti public memory. iCoDer must NOT claim
semantic parity until an embedding tier is wired behind Provider egress policy.

### §6.7 referenceTaskIds

- Optional list of past Task IDs within the SAME context
- Acts as explicit input / background hint to the agent
- Scoped per-context (cannot reference tasks in other contexts)

## §7. Orchestrator contract (clean-room)

From the System Architecture page (page 02):

> Orchestrator — The central coordinator that receives user requests and
> delegates tasks to specialized Experts via the A2A protocol.

Properties:
- Receives user requests
- Delegates to Experts via A2A
- Stateless reasoning (composition is protocol-based)
- Strict data isolation

The dedicated `/agentic/orchestrator` page (deferred) is expected to contain
deeper detail; flagged UNKNOWN here.

## §8. Interaction patterns (clean-room)

| Pattern | Use |
|---|---|
| Request/Response (Polling) | synchronous APIs; long-running tasks polled via task endpoint |
| Streaming SSE | real-time experiences (ambient notes, live guidance); incremental tokens/events/status |

iCoDer already ships SSE at `/api/v1/runs/{id}/events?token=…` (Phase 7 Gate 9).

## §9. Corti-side status flags (PUBLICLY ANNOUNCED, NOT YET SHIPPED)

These capabilities appear on Corti's public docs as "coming soon". iCoDer
 MAY implement them clean-room, but must NOT claim Corti parity.

| Capability | Corti status | iCoDer A1B-AE target |
|---|---|---|
| Multi-Agent Composition (direct A2A agent-to-agent endpoints) | COMING SOON | OUT of A1B-AE scope |
| Direct Expert Calls (API access to individual experts without Orchestrator) | COMING SOON | OPTIONAL — iCoDer MAY ship as clean-room lead |
| FilePart full support | NOT YET FULLY SUPPORTED | iCoDer will support FilePart in Message envelope from A1B-AE.5 onwards |

## §10. Public SDKs (Corti-listed, for reference)

Per page 05 (A2A Protocol): Python, JavaScript/TypeScript, Java, Go, .NET.
Corti also ships its own SDK (`@corti/sdk` for JS, `Corti.Sdk` for .NET).

iCoDer SDK (`@icoder/sdk`, Phase 6 Gate 4) is independent.

## §11. What is NOT publicly verifiable (UNKNOWN)

The following items are NOT determinable from the 8 pages observed. They are
recorded as `UNKNOWN` and must NOT be inferred:

- The full list of Experts beyond the 9 "frequently-used" keys (until
  `available-experts` page is crawled).
- Per-Expert configuration requirements (until individual Expert reference
  pages are crawled).
- The full `authorizationType` enum (until `mcp-authentication` is crawled).
- The detailed Agent Card schema (Corti-public list is high-level only).
- The full Agent update / delete / clone contract (siblings of create-agent
  not yet crawled).
- The full Message send / Task state transition contract (the
  `/agents/{id}/v1/message:send` endpoint not yet crawled).
- Orchestrator internal selection policy (page deferred).
- A2A protocol schemas themselves (lives at `a2a-protocol.org`, NOT on
  Corti docs; out of clean-room scope for this commit).

No assumption may be made about these items in downstream A1B-AE commits
without re-observation.

## §12. iCoDer Preset Agent type mapping (PRELIMINARY)

Per Charter §17, iCoDer will assemble 5 clean-room Preset Agents. Each maps
to a Corti-public `agentType` value or declares a non-Corti type:

| Preset Agent (iCoDer) | Corti agentType | origin tag |
|---|---|---|
| Clinical Research Assistant | `orchestrator` | ICODER_CLEAN_ROOM |
| Medication Reference Assistant | `orchestrator` | ICODER_CLEAN_ROOM |
| Coding Assistant | `expert` (or `orchestrator` — TBD in A1B-AE.8) | ICODER_CLEAN_ROOM |
| Structured Intake Assistant | `interviewing-expert` | ICODER_CLEAN_ROOM |
| Trial Matching Research Assistant | `orchestrator` | ICODER_CLEAN_ROOM |

`official_corti_preset = false` for ALL five (Corti does not publicly
enumerate any preset Agents).

## §13. Browser evidence manifest

```
reports/phase-a1b/evidence/corti_observation/
  00_welcome/
    observation.json          # sidebar taxonomy + 5 core capabilities
    after_00_welcome_navigate.png
  01_agentic_overview/
    observation.json          # design principles + agent vs workflow
  02_agentic_architecture/
    observation.json          # 3 components + interaction patterns
  03_agentic_experts/
    observation.json          # 9-key Expert list + Expert/MCP schemas
  04_agentic_context_memory/
    observation.json          # Context + Memory RAG + referenceTaskIds
  05_agentic_a2a_protocol/
    observation.json          # A2A overview; full spec at a2a-protocol.org
  06_agentic_core_concepts/
    observation.json          # 6 elements + 3 Part kinds + Task vs Message
  07_agentic_agents_create/
    observation.json          # Agent CRUD + agentType enum + MCP schemas
    after_07_create_agent.png
```

The auto-generated Playwright MCP YML snapshots (accessibility tree per page)
remain in `E:/Corti4C/.playwright-mcp/page-2026-07-22T*.yml` and are
referenced from each observation.json. They are not copied into the worktree
to keep the evidence tree compact; they remain available for audit via the
original worktree path.

## §14. Verdict for A1B-AE.1

```
A1B_AE_1_CORTI_PUBLIC_CONTRACTS_PARTIALLY_RECONSTRUCTED
```

**Partial** because:
- 8 of ~15 contract-bearing pages observed (§1.2 lists the deferred set).
- Detailed per-Expert reference pages not yet observed.
- Agent update / delete / clone / list / get-by-id / message-send endpoints not yet observed.
- MCP authentication enum not yet observed.

**Reconstructed** because the 8 observed pages provide:
- the canonical Agent / Expert / MCP Server schemas (write + read paths);
- the canonical 9-key Expert enumeration;
- the canonical `agentType` 3-value enum;
- the canonical 6-element communication model + 3-Part-kind model;
- the canonical Context + Memory + referenceTaskIds semantics;
- the canonical Orchestrator + A2A + interaction-pattern architecture;
- the publicly-announced "coming soon" flags for Multi-Agent + Direct Expert Calls + FilePart.

This is sufficient clean-room ground truth to proceed with A1B-AE.2
(taxonomy + catalogs) and A1B-AE.3 (Expert Registry). It is NOT sufficient
to claim Corti parity for any Expert implementation (deferred to A1B-AE.11).

Forbidden verdicts NOT emitted:
`PRODUCTION_READY`, `FULLY_VERIFIED`, `PHI_BOUNDED`, `CORTI_PARITY_VERIFIED`,
`PASS_A1A_GATE4_FINAL`, `READY_FOR_HOSPITAL_DEPLOYMENT`,
`CLINICAL_GRADE_VERIFIED`, `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED`.

---

End of A1B-AE.1.
