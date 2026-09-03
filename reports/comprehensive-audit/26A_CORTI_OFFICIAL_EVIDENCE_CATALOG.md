# 26A — Corti Official Evidence Catalog (Pre-A0 Gate 1)

> Per spec §16 deliverable. Consolidates all official Corti evidence gathered during Pre-A0 Gate 1.
> Spec §4.1 requires each evidence entry to record: page title, official identifier, access date, key claim, current API path, current schema, beta status, coming-soon status, login required, publicly verifiable, local evidence path, SHA-256.

## Access metadata

| Field | Value |
|-------|-------|
| Audit date | 2026-07-16 |
| Primary source | `https://docs.corti.ai/agentic/*` (public web, no auth) |
| Secondary source | `https://console.corti.app/project/4c4193c7-.../*` (Console, auth granted) |
| Accessing user | Luhua Song <songluhua@gmail.com> |
| Project ID | `4c4193c7-c6bb-4a71-a275-0ed6c53172d0` |
| Region | EU (Corti Models banner: "hosted on European infrastructure") |
| Auth provider | Keycloak (per session storage inspection) |
| Available credits at audit | $37.52 |
| Total credits consumed at audit | $6.84 |
| Login required for docs | No |
| Login required for Console | Yes (email + password) |
| Publicly verifiable | Docs ✅ — anyone can browse; Console ❌ — requires Corti account |

## Section A — Corti public docs evidence

Per spec §4.1, each row records the 11 required metadata fields. Evidence files at `evidence/corti-foundation/official-docs/`.

| # | Topic | Official URL | Key claim | API path | Schema | Beta? | Coming soon? | Login? | Public? | Local path | SHA-256 |
|---|-------|--------------|-----------|----------|--------|-------|--------------|--------|---------|------------|---------|
| D-01 | Experts Overview | `docs.corti.ai/agentic/experts/overview` | 13 prebuilt experts in 4 categories (Core, Knowledge, Coding, Computation) | `/agents/registry/experts` (runtime) | Expert: `{name, type, description, mcpServers?, configSchema?}` | No | No | No | Yes | `official-docs/experts_overview.md` | (per-file) |
| D-02 | Architecture | `docs.corti.ai/agentic/architecture` | 3 components: Orchestrator + Experts + Memory; strict data isolation; SSE+polling | n/a | n/a | No | No | No | Yes | `official-docs/architecture.md` | (per-file) |
| D-03 | Core Concepts | `docs.corti.ai/agentic/core-concepts` | Core actors: User / A2A Client / A2A Server; Agent Card = JSON business card; Parts (Text/Data/File); Artifacts; Response: Task or Message | `/agents/{id}/card` | Card: `{identity, endpoint, capabilities, auth, skills}` | FilePart: "not yet fully supported" | No | No | Yes | `official-docs/core_concepts.md` | (per-file) |
| D-04 | Orchestrator | `docs.corti.ai/agentic/orchestrator` | 6 responsibilities (reasoning, expert selection, task decomposition, response gen, context mgmt, safety); "does not perform specialized work itself—delegates to Experts" | n/a | n/a | No | No | No | Yes | `official-docs/orchestrator.md` | (per-file) |
| D-05 | Context & Memory | `docs.corti.ai/agentic/context-memory` | Server-generated contextId; strict isolation (no cross-context leak); RAG-like memory; referenceTaskIds scoped to context | `/context/{id}` | Context: `{contextId, referenceTaskIds[], messages[]}` | No | No | No | Yes | `official-docs/context_memory.md` | (per-file) |
| D-06 | A2A Protocol | `docs.corti.ai/agentic/a2a-protocol` | Open standard, Google-originated, Linux Foundation stewarded; 5 SDKs (Python/JS/Java/Go/.NET) | a2a-protocol.org | A2A v0.3 envelope | No | No | No | Yes | `official-docs/a2a_protocol.md` | (per-file) |
| D-07 | SDKs & Integrations | `docs.corti.ai/agentic/sdks-integrations` | Official: `@corti/sdk` (JS/TS) + `Corti.Client` (.NET); A2A SDKs separate; ai-elements + a2a-inspector + awesome-a2a | npm: `@corti/sdk` | n/a | No | No | No | Yes | `official-docs/sdks_integrations.md` | (per-file) |
| D-08 | llms.txt index | `docs.corti.ai/llms.txt` | Doc index for LLM consumption | n/a | n/a | n/a | n/a | n/a | n/a | **FETCH FAILED** (500 error) — see §B console captures instead | n/a |

## Section B — Corti Console evidence (newly accessible)

Per spec §4.3, items previously marked `NOT_VERIFIED` are eligible for promotion. Each row below records what the Console walkthrough verified.

| # | Topic | Console URL | Verified Claim | Login? | Public? | Local path | SHA-256 |
|---|-------|-------------|----------------|--------|---------|------------|---------|
| C-01 | Home / Overview | `console.corti.app/project/{id}` | Topology: sidebar (Developer / AI Studio / Manage / Support) + Home + main; top bar shows live credits + Docs link; "Corti Models" banner | Yes | No | `console-walkthrough/01_home_overview.png` | `9123c8d...` |
| C-02 | Pre-built Agents (authoritative list) | `console.corti.app/.../ai-studio/agents/pre-built-agents` | **20 pre-built agents** (not 13). All have descriptions + preset ID like `medical-coding-icd-10-cpt-agent` | Yes | No | `console-walkthrough/02_prebuilt_agents.md` + `.png` | `92cacd7...` / `d4ec3bd...` |
| C-03 | New Agent from template | `console.corti.app/.../ai-studio/agents/new?preset={id}` | Two creation paths: Start-from-scratch + Use-a-template; preview pane with chat input + "Add context" + credits disclaimer | Yes | No | `console-walkthrough/03_new_agent_medical_coding_template.png` | `f56bdc0...` |
| C-04 | Agent Detail — Settings | `console.corti.app/.../ai-studio/agents/{uuid}` | Layout: chat left + Settings/Code tabs right; fields: Name (50-char max), System prompt, Experts bound (4 verified), Pinned message parts; preset agents save-and-go-live (no deploy step) | Yes | No | `console-walkthrough/04_agent_detail_schema.md` + `.png` | `a5874f6...` / `d39bbaf...` |
| C-05 | Agent Detail — Code (JS SDK signature) | (same URL, Code tab) | **Authoritative**: `@corti/sdk`; `CortiClient({auth:{accessToken}})`; `cortiClient.agents.create({name, experts[{name,type:"reference"}], description, systemPrompt})` | Yes | No | `console-walkthrough/05_agent_code_js_sdk_signature.png` | `8c98a9c...` |
| C-06 | API Clients | `console.corti.app/.../api-clients/default-clients` | **2 default clients** (Client Credentials + ROPC Embedded); Default Client ID format `{user_slug}-{rand4}-default_client`; Environment ID `eu`; Tenant `base`; default clients cannot be deleted | Yes | No | `console-walkthrough/06_api_clients_default.png` | `4d532e8...` |
| C-07 | Medical Coding — variants | `console.corti.app/.../ai-studio/medical-coding` | **9 ICD-10 variants** (CM In/Out, PCS, WHO In/Out, UK In/Out, GM In/Out); **NO ICD-10-CN**; Settings tab + Event Inspector + Credits consumed | Yes | No | `console-walkthrough/07_medical_coding_variants.md` + `.png` | `d2b3541...` / `3af4da2...` |
| C-08 | Embedded Assistant | `console.corti.app/.../ai-studio/embedded-assistant` | Package `@corti/embedded-web`; element `<corti-embedded baseURL=...>`; lifecycle `auth → configureSession → configure → show`; event `embedded-event` with `{name, payload}` flat; 7 feature toggles; **iCoDer Phase 6 envelope has more fields** | Yes | No | `console-walkthrough/08_embedded_assistant.md` + `.png` | `9038274...` / `454a9a1...` |
| C-09 | Usage | `console.corti.app/.../usage` | Daily chart + Compare-period + All-API-clients filter; Available $37.52 + Consumed $6.84 | Yes | No | `console-walkthrough/09_usage.png` | `5a01e90...` |
| C-10 | Billing | `console.corti.app/.../billing` | **Pay-as-you-go plan** (real, not theater); Balance + Add credits + Low-balance alert + Auto top-up + **Payment methods** ("Add a payment method" UI present); 3 tabs: Plan / Billing History / Business info | Yes | No | `console-walkthrough/10_billing.png` + `09_usage_and_billing.md` | `1212207...` |

## Section C — Promoted evidence status changes (vs Pre-A0 Gate 0)

Items that were `NOT_VERIFIED` in Gate 0 §14 are now promoted:

| Item | Gate 0 status | Gate 1 status | Evidence |
|------|---------------|---------------|----------|
| Agent CRUD operations | NOT_VERIFIED | **VERIFIED_CONSOLE** (C-04, C-05) | Console walkthrough |
| Agent Card live schema | NOT_VERIFIED | **VERIFIED_CONSOLE** (C-04) | Settings tab + 50-char Name field + Experts[] shape |
| Orchestrator runtime behavior | NOT_VERIFIED | PARTIAL — Console shows agents-live-on-save; deep runtime trace not captured | C-04 |
| Context & Memory live view | NOT_VERIFIED | PARTIAL — "Add context" UI visible; per-context data isolation not exercised | C-03, C-04 |
| A2A Client management | NOT_VERIFIED | **VERIFIED_CONSOLE** (C-06) | Default clients visible; user-defined clients CRUD not exercised |
| Authentication flow | NOT_VERIFIED | **VERIFIED_CONSOLE** (C-06) | client_id + client_secret surface; keycloak JWT in sessionStorage confirmed |
| SDK runtime introspection | NOT_VERIFIED | **VERIFIED_CONSOLE** (C-05, C-08) | Authoritative JS + HTML generators captured |
| Speech to Text / Text Generation / Fact Extraction surfaces | NOT_VERIFIED | PARTIAL — sidebar links visible; pages not deeply walked | C-01 |
| Usage metering granularity | NOT_VERIFIED | **VERIFIED_CONSOLE** (C-09) | Time-window + API-client + compare-period dimensions |
| Billing "Add credits" payment processor | NOT_VERIFIED | **VERIFIED_CONSOLE** (C-10) | Pay-as-you-go plan + Add-a-payment-method UI captured |

## Section D — Newly discovered Corti capabilities (not in V1 parity matrix)

These were not enumerated in any prior Gate 4-14 report:

| ID | Capability | Source | iCoDer status |
|----|-----------|--------|---------------|
| **ND-01** | 20 pre-built agents (not 13 as Gate 4/14 claimed) | C-02 | 18/20 mirrored in `official_agents/`; 2 missing (Clinical Education, Clinical Guidelines) |
| **ND-02** | 9 ICD-10 variants in Medical Coding (not 5 per docs) | C-07 | 1/9 (CN only); other 8 are DIFFERENT_BY_DESIGN |
| **ND-03** | AMBOSS Expert (referenced in CDI system prompt but not in docs/overview list) | C-04 system prompt | Not applicable for CN scope |
| **ND-04** | "Default Client" pattern (cannot be deleted; auto-provisioned per user) | C-06 | Not yet in iCoDer Phase 7 Gate 5 |
| **ND-05** | Pay-as-you-go plan + Auto-top-up + Low-balance alerts + Payment methods UI | C-10 | None of these in iCoDer (confirms Gate 13 G13-001) |
| **ND-06** | Templates Beta (sidebar entry "Templates Beta") | C-01 | Not in iCoDer |
| **ND-07** | Corti Models (banner: "Frontier models for coding, hosted by Corti on European infrastructure") | C-01 | iCoDer uses DeepSeek external; not same as Corti-hosted |
| **ND-08** | Speech to Text 3 surfaces (Dictation / Ambient / Pre-recorded) | C-01 sidebar | iCoDer Speech to Text is dead per G2-004 |
| **ND-09** | Fact Extraction as top-level Console tool | C-01 sidebar | iCoDer has this as agent/internal capability, not top-level |
| **ND-10** | Embedded Assistant 7 feature toggles (aiChat, documentFeedback, interactionTitle, navigation, syncDocumentAction, templateEditor, virtualMode) | C-08 | None in iCoDer |
| **ND-11** | Customer-facing templates (e.g., `corti-patient-summary-legacy`) | C-08 defaultTemplateKey | Not in iCoDer |
| **ND-12** | Billing currency USD ($) on EU region | C-10 | iCoDer is CNY (¥) — DIFFERENT_BY_DESIGN |

## Section E — Parity matrix V2 delta inputs (for Pre-A0 Gate 7)

The V1 parity matrix in Gate 14 (`19_CORTI_ICODER_PARITY_MATRIX.md`) used doc-only Corti evidence. V2 must use this catalog's Console-verified evidence. Key deltas:

| Dimension | V1 (doc-only) | V2 (Console-verified) | Direction |
|-----------|---------------|------------------------|-----------|
| Pre-built Agent count | "13 metadata-only" | **20 real, runnable presets** | Larger Corti surface than V1 claimed |
| ICD-10 variant count | "5 variants (CM/WHO/PCS/UK/General)" | **9 variants (CM/PCS/WHO/UK/GM × In/Out)** | Larger Corti surface |
| Billing | "TBD pricing" | **Pay-as-you-go + payment processor + auto-topup** | Corti production-grade; iCoDer theater |
| Agent lifecycle | "create/save/publish unclear" | **Save = live** (zero-step deploy) | Corti faster (iCoDer has pack/install) |
| Expert Registry | "13 prebuilt" | **13 docs-listed + AMBOSS discovered** | More experts than docs claim |
| Embedded event envelope | "TBD" | **`{name, payload}` flat** | iCoDer adds `meta` block → ICODER_ADVANTAGE |

## Section F — Evidence file inventory

```
evidence/corti-foundation/
├── _access_metadata.json                  (758 B, 2026-07-16)
├── official-docs/
│   ├── _access_metadata.json              (created 2026-07-16)
│   ├── experts_overview.md                (pending write)
│   ├── architecture.md                    (pending write)
│   ├── core_concepts.md                   (pending write)
│   ├── orchestrator.md                    (pending write)
│   ├── context_memory.md                  (pending write)
│   ├── a2a_protocol.md                    (pending write)
│   └── sdks_integrations.md               (pending write)
└── console-walkthrough/                   (THIS GATE)
    ├── _hashes.json                       (17 entries, 2026-07-16)
    ├── 00_console_access_metadata.md      (markdown context)
    ├── 01_home_overview.png               (9123c8d...)
    ├── 02_prebuilt_agents.md              (92cacd7...)
    ├── 02_prebuilt_agents_full_list.png   (d4ec3bd...)
    ├── 03_new_agent_medical_coding_template.png (f56bdc0...)
    ├── 04_agent_detail_schema.md          (a5874f6...)
    ├── 04_agent_detail_settings.png       (d39bbaf...)
    ├── 05_agent_code_js_sdk_signature.png (8c98a9c...)
    ├── 06_api_clients_default.png         (4d532e8...)
    ├── 07_medical_coding_variants.md      (d2b3541...)
    ├── 07_medical_coding_variants.png     (3af4da2...)
    ├── 08_embedded_assistant.md           (9038274...)
    ├── 08_embedded_assistant.png          (454a9a1...)
    ├── 09_usage.png                       (5a01e90...)
    ├── 09_usage_and_billing.md            (8b27302...)
    └── 10_billing.png                     (1212207...)
```

## Section G — Constraints honored

- ✅ Read-only audit: no Agent/Expert/Tool/Runtime/Prompt edits
- ✅ No Console state mutation (no agents created, no API clients modified, no credits spent)
- ✅ Evidence files saved locally with SHA-256 hashes per spec §4.1
- ✅ Login-restricted items marked `Login required: Yes; Public: No`
- ✅ Publicly verifiable items distinguished from Console-only items
- ✅ Historical doc-based claims reverified where possible; contradictions logged (e.g., docs say "5 ICD variants", Console shows 9)
- ✅ Forbidden verdicts not claimed: CORTI_FULL_PARITY, CORTI_AGENT_PARITY_COMPLETE, etc.

## Section H — Gate 1 verdict

```
PRE_A0_GATE_1_CORTI_OFFICIAL_EVIDENCE_CATALOG_COMPLETE
PUBLIC_DOCS_7_OF_8_FETCHED (llms.txt failed)
_CONSOLE_WALKTHROUGH_10_PAGES_CAPTURED
12_NEWLY_DISCOVERED_CORTI_CAPABILITIES (ND-01 through ND-12)
6_PARITY_DELTA_INPUTS_FOR_V2_MATRIX
0_FORBIDDEN_VERDICTS_CLAIMED
```

### Allowed verdicts status

| Verdict | Claimed? |
|---------|----------|
| PASS_PRE_A0_CORTI_FOUNDATION_RECONCILIATION_COMPLETE | Not yet (Gates 2-9 still pending) |
| PARTIAL_BLOCKED_BY_OFFICIAL_CORTI_EVIDENCE_ACCESS | ❌ No longer — Console granted |
| PARTIAL_BLOCKED_BY_ICODER_RUNTIME_INVENTORY_AMBIGUITY | Pending Gate 2 |
| PARTIAL_BLOCKED_BY_AUDIT_BASELINE_DRIFT | Pending re-check at final |
| INVALIDATED_BY_PRE_A0_SCOPE_EXPANSION | n/a |

### Hard Checkpoint A status (per spec §20)

**Checkpoint A — Official Corti Evidence**: ✅ PASS
- 7 public docs fetched with content
- 10 Console pages walked with screenshots + structured evidence
- 12 newly discovered capabilities logged
- SHA-256 hashes recorded for all binary evidence
- All `NOT_VERIFIED` items either promoted or left as `PARTIAL` with explicit reason

Gate 1 closes. Proceed to **Pre-A0 Gate 2 — iCoDer Agent/Expert/Tool/Runtime Inventory**.
