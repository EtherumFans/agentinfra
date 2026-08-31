# Audit Gate 2 — Product Surface and Route Inventory (Track B1 + B3)

## B1. Page & route inventory

### B1.1 Frontend route graph (47 routes)

| Route | Page | Loaded | Source | Notes |
|-------|------|--------|--------|-------|
| `/login` | `LoginPage` | ✅ | tracked | unauth |
| `/` | `HomePage` | ✅ | tracked | 4-tab IA, **2 of 4 CTAs broken** (see §B1.4) |
| `/reset-password` | `ResetPasswordPage` | ✅ | tracked | unauth |
| `/developer-quickstart` | `DeveloperQuickstartPage` | ✅ | tracked | |
| `/docs` | `DocsPage` (lazy) | ✅ | tracked | |
| `/release-notes` | `ReleaseNotesPage` (lazy) | ✅ | tracked | |
| `/ai-studio` | `AIStudioOverviewPage` | ✅ | tracked | **has external Corti link** (G2-001) |
| `/ai-studio/agents` | `AgentsPage` | ✅ | GET `/api/icoder/agents/hub` | returns 23 agents, 13 metadata-only |
| `/ai-studio/agents/new` | `NewAgentPage` | ✅ | tracked | |
| `/ai-studio/agents/:agentId` | `AgentDetailPage` | ✅ | tracked | 1305 LOC — largest page |
| `/ai-studio/agents/:agentId/chat` | `AgentChatPage` | ✅ | POST `/api/v1/agents/{id}/run` | |
| `/agents/:project_agent_id/chat` | `AgentChatPage` | ✅ | (alias) | legacy |
| `/runs/:runId/trace` | `RunTracePage` | ✅ | GET `/api/runtime/runs/{id}/trace` | |
| `/ai-studio/text-generation` | `<Navigate to="/ai-studio/agents">` | n/a | redirect | TextGenerationPage.tsx exists but orphan |
| `/ai-studio/embedded-assistant` | `EmbeddedAssistantPage` | ✅ | tracked | 614 LOC, Phase 7 Gate 13 |
| `/ai-studio/fact-extraction` | `FactExtractionPage` | ✅ | tracked | 454 LOC |
| `/ai-studio/medical-coding` | `MedicalCodingPage` | ✅ | POST `/api/v1/coding/predict` + others | 1250 LOC |
| `/ai-studio/coding-compliance` | `CodingComplianceWorkbenchPage` | ✅ | POST `/api/v1/coding-compliance/run` | 304 LOC |
| `/ai-studio/cdi` | `CDIWorkbenchPage` | ✅ | POST `/api/v1/cdi/*` | 918 LOC |
| `/studio/*` | (10 alias routes) | ✅ | various | v3.0 alias — Navigate or actual |
| `/runtime/agents` | `AgentsPage` | ✅ | alias | legacy runtime IA |
| `/runtime/coding-review` | `MedicalCodingPage` | ✅ | alias | legacy |
| `/manage/*` | (8 alias routes) | ✅ | aliases | legacy manage IA |
| `/api-clients` | `APIClientsPage` (lazy) | ✅ | GET `/api/clients/*` | Phase 7 Gate 5 |
| `/team` | `TeamPage` (lazy) | ✅ | GET `/api/team/*` | |
| `/billing` | `BillingPage` | ✅ | GET `/api/billing/*` | |
| `/usage` | `UsagePage` | ✅ | GET `/api/usage/*` | |
| `/customers` | `CustomersPage` | ✅ | GET `/api/customers/*` | |
| `/templates` | `TemplatesPage` | ✅ | GET `/api/templates/*` | |
| `/settings` | `SettingsPage` | ✅ | tracked | |
| `/support` | `SupportPage` (lazy) | ✅ | tracked | duplicate route (declared twice in App.tsx:130,140) |
| `/tickets` | `TicketsPage` | ✅ | GET `/api/tickets/*` | |
| `*` | `<Navigate to="/">` | n/a | catchall | |

### B1.2 Orphan page components (not routed)

| File | LOC | Status |
|------|-----|--------|
| `frontend/src/pages/SpeechToTextPage.tsx` | 596 | **Orphan** — not imported by `App.tsx`. The HomePage "Transcribe" tab still links to `/ai-studio/speech-to-text`, which falls through to the `*` catchall and redirects to `/`. |
| `frontend/src/pages/TextGenerationPage.tsx` | 527 | **Orphan** — explicitly de-listed in App.tsx comment "Phase 3-B2 Loop 0: TextGeneration removed". File preserved on disk. |

→ **~1,123 lines of orphan React code in `pages/`**. Should either be re-routed or deleted.

### B1.3 Sidebar nav (from `Layout.tsx:46-91`)

```
Top items:        Home, Developer Quickstart
AI Studio:        Overview, Agents, Speech-to-Text (BROKEN), Fact Extraction,
                  Medical Coding, Coding Compliance, CDI, Embedded Assistant
Manage:           API Clients, Team, Billing, Usage, Customers, Templates, Settings
Support:          Get Help, Tickets
```

The sidebar still shows "Speech to Text" (icon Mic) but the route was removed. **Clicking it falls through to the catchall redirect to `/`.** Register as P2 dead-link.

### B1.4 HomePage 4-tab IA (per `console.corti.app` parity claim)

| Tab | CTA destination | Status |
|-----|-----------------|--------|
| Transcribe | `/ai-studio/speech-to-text` | **Dead** — route removed, falls to catchall |
| Document | `/ai-studio/medical-coding` | Live (but semantically wrong — Medical Coding ≠ Document) |
| Chat | `/ai-studio/agents` | Live |
| Code | `/ai-studio/medical-coding` | Live |

**Only 2 of 4 tabs land on their semantically-intended destination.** This breaks the Corti-parity claim for HomePage.

## B2. Backend route surface (38 routers, 204 paths)

| Prefix | Path count | Owner router | Maturity |
|--------|-----------|--------------|----------|
| `/api/v2/tools/*` | 26 | `v2_tools_{coding,facts,streams,guided_document,sections_templates,documents_classic,stt}_router` | Phase 1.x — most paths are **stub data** per main.py comments |
| `/api/rest/v1/*` | 17 | `agents_router` (Corti §2.1) | Phase 2.1-C |
| `/api/clients/{client_id}/*` | 7 | `platform_api_clients_router` | Phase 7 Gate 5 |
| `/api/v1/cdi/*` | 6 | `cdi_router` | Phase 5 Track D |
| `/api/icoder/agents/*` | 5 | `icoder_agents_hub_router` | Phase 3-B1 |
| `/api/runtime/runs/*` | 4 | `run_trace_router` | Phase 3-D1 |
| `/api/organizations/{org_id}/*` | 4 | `organizations_router` | |
| `/api/runtime/agents/*` | 4 | `runtime_platform_router` | |
| `/api/embedded/preview-sessions/*` | 4 | `preview_sessions_router` | Phase 7 Gate 13A |
| `/api/v1/runs/*` | 4 | `runs_router` | Phase 7 Gate 4 |
| `/api/admin/organizations/*` | 3 | `admin_router` | |
| `/api/runtime-platform/{registry,agents}/*` | 6 | `runtime_platform_router` | back-compat alias |
| `/api/runtime/{registry,rule-engine}/*` | 6 | `standard_runtime_router` | |
| `/api/team/members/*` | 2 | `team_router` | |
| `/api/oauth/{token,realms,clients}/*` | 6 | `oauth_router` | |
| `/api/admin/runtime/*` | 2 | `admin_router` | |
| `/api/v1/coding-compliance/*` | 2 | `coding_compliance_router` | Phase 5 Track C Gate 5 |
| `/api/tools/permission-presets/*` | 2 | `tools_router` | |
| `/api/runtime/observability/*` | 2 | `runtime_platform_router` | |
| `/api/runtime/medical-coding/*` | 2 | `runtime_platform_router` | |
| `/api/medical-docs/templates/*` | 2 | `medical_docs_router` | |
| `/api/icoder/tasks/*` | 2 | (legacy) | |
| `/mcp/v1/tools/*` | 1 | MCP router | |
| `/api/health` | 1 | static | |
| `/api/auth/register` | 1 | `auth_router` | |

→ **At least 6 generations of API surface** (legacy `/api/*`, Corti `/api/rest/v1/*`, Corti `/api/v2/tools/*`, Runtime `/api/runtime/*` + `/api/runtime-platform/*`, Phase 5+ `/api/v1/*`, Phase 6+ `/api/embedded/*` + `/api/clients/*`, MCP `/mcp/v1/*`). Fragmentation is real.

## B3. Product consistency

### B3.1 Product naming — drift detected

| Where | Says |
|-------|------|
| `VERSION` file | `iCoDer` 1.1.0 |
| `<title>` in `index.html` | "iCoDer Medical Coding Agent" |
| `/api/health` `app` field | "iCoDer Medical Coding Agent" |
| `CLAUDE.md` line 1 | "iCoDer — 医疗收入合规 AI 平台" |
| `README.md` line 1 | "iCoDer — Clinical AI Platform" |
| Sidebar logo / project slug | "icoder-medical-coding" |
| Sidebar default project name | "iCoDer Console" |

→ At least **5 different product framings**: "Medical Coding Agent", "Clinical AI Platform", "医疗收入合规 AI 平台", "iCoDer Console", "AI Studio + Medical Coding". PDF §Track C asks "当前产品首页在向谁表达价值?" — the answer is **incoherent**.

### B3.2 Corti name residue in user-visible UI strings

**`frontend/src/i18n/locales.ts`:**

| Key | zh-CN | en-US |
|-----|-------|-------|
| `codingMode` / `medcoderMode` | `'编码模式 (Corti-style)'` | `'Coding mode (Corti-style)'` |
| `embeddedPageSubtitle` | `'Corti 风格对齐 · 一次配置，随处复制'` | `'Corti-style parity · Configure once, copy anywhere'` |
| `runTraceIntro` | `'9 步 Corti-parity 时间线'` | (similar) |

→ The **Embedded Assistant page subtitle explicitly says "Corti 风格对齐"** in production. This is a Corti brand residue in user-visible UI. PDF §B3 "识别: Corti 名称残留" — **CONFIRMED, register as P1**.

### B3.3 External link to Corti (P1)

`frontend/src/pages/AIStudioOverviewPage.tsx:281`:

```tsx
<a href="https://help.corti.app/tickets-portal" target="_blank" rel="noopener noreferrer">
  <LifeBuoy size={14} />
  {t.aiStudioOverviewFooterHelp}
</a>
```

The AI Studio Overview page footer has a **"Tickets Portal" link pointing to Corti's actual help site**. iCoDer has its own `/tickets` route — this should be an internal link. **This is a P1 product residue.** Evidence saved to `evidence/architecture/corti_external_link.md`.

### B3.4 Term drift

| Concept | Terms in use |
|---------|--------------|
| Code artifact | `Agent` / `Agent Pack` / `Capability` / `Expert` / `Tool` |
| Runtime layer | `CodingRuntime` / `RuntimeAgent` / `PlatformRuntime` / `StandardRuntime` / `EmbeddedRuntime` / `AgentRuntime` |
| Auth identity | `User` / `Organization` / `Tenant` / `Project` / `APIClient` / `EmbeddedApp` / `Partner` |
| Coding output | `MedicalCodingOutputSchema` / `CodingResult` / `CodingReviewRun` / `CodingComplianceResult` / `AgentRunResponse` |

No single canonical vocabulary. PDF Track C explicitly asks if Medical Coding/CDI/DRG-DIP form a unified narrative — at the term level they do not.

## B4. Agent hub inventory (live from `/api/icoder/agents/hub`)

```
Total: 23 agents (source: official_agents/agent_pack.json, schema v1.1)
Display status: preview × 10, coming_soon × 13
Maturity:        mvp × 8, runnable × 2, metadata-only × 13
```

### B4.1 The 10 `preview` (visible) agents

| Agent ID | Display status | Maturity | Real impl? |
|----------|---------------|----------|------------|
| clinical-documentation-improvement-agent (CDI) | preview | **mvp** | TBD Gate 5 |
| drg-analyzer | preview | **mvp** | TBD Gate 5 |
| principal-diagnosis-review | preview | **mvp** | TBD Gate 5 |
| discharge-summary-structuring | preview | **mvp** | TBD Gate 5 |
| medical-coding-agent | preview | **mvp** | TBD Gate 5 (this is supposed to be the **core product**) |
| compliance-guardrail-agent | preview | **mvp** | TBD Gate 5 |
| procedure-extractor | preview | **mvp** | TBD Gate 5 |
| note-completeness-agent | preview | **runnable** | TBD |
| code-validation-agent | preview | **runnable** | TBD |
| evidence-extractor | preview | **mvp** | TBD Gate 5 |

### B4.2 The 13 `coming_soon` agents — **metadata-only**

```
discharge-edu, nursing-handoff, referral-gen, icd10-navigator, rule-explainer,
prior-auth, icu-summary, triage, med-reconciliation, surgical-registry,
denial-appeals, evidence-ranker, diagnosis-extractor
```

**All 13 are `metadata-only`** — they exist as `agent_pack.json` files but have **no Python implementation** and **no runtime**. They render as cards in the Hub marked "coming soon". PDF §D1 asks "是否应当下线" — for a Corti-parity AI Studio, 13 of 23 visible cards being unimplemented is a major credibility issue.

→ Register as P1: **56% of Hub cards (13/23) are non-functional placeholders.**

### B4.3 Status-label inconsistency

The Hub claims `medical-coding-agent` is `maturity: mvp`. The codebase has at least 3 substantial implementations of medical coding (FastCodingRuntime / MedCoderRuntime / app/agents/experts/diagnosis_expert+procedure_expert), plus Phase 5 Track C closed a 7-stage compliance orchestrator (`READY_FOR_FORMAL_QUALITY_BENCHMARK`). Either:

- `maturity` field is **stale** (set long ago, never updated as the agent matured), OR
- The Hub's labeling scheme doesn't reflect actual capability depth.

Either way, the Hub misleads users. **PDF §D1 "Agent ID; ... 是否核心 Agent"** — Medical Coding is the canonical core agent, but its hub metadata says `mvp`.

## B5. New findings

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G2-001** | P1 | product-residue | `AIStudioOverviewPage.tsx:281` links user-visible "Tickets Portal" footer to `https://help.corti.app/tickets-portal` (Corti's actual help site) instead of `/tickets` |
| **G2-002** | P1 | product-residue | User-visible UI strings brand the product as "Corti-style" — `embeddedPageSubtitle: 'Corti 风格对齐 · 一次配置，随处复制'` (zh) + `'Corti-style parity'` (en) on the Embedded Assistant page; `'编码模式 (Corti-style)'` on Medical Coding |
| **G2-003** | P1 | dead-surface | **13 of 23 Agent Hub cards are `metadata-only` with `coming_soon` status** — no implementation, no runtime, no LLM call. Represents 56% of Hub surface as placeholders. |
| **G2-004** | P2 | dead-link | HomePage "Transcribe" tab + sidebar "Speech to Text" link both target `/ai-studio/speech-to-text` which was removed; falls to `*` catchall → redirect to `/` |
| **G2-005** | P2 | orphan | `SpeechToTextPage.tsx` (596 LOC) + `TextGenerationPage.tsx` (527 LOC) = 1,123 lines of orphan page components, not routed but still on disk |
| **G2-006** | P2 | inconsistency | `medical-coding-agent` labeled `maturity: mvp` in Hub despite being the core product with 3+ runtime implementations and Phase 5 Track C closure reports |
| **G2-007** | P2 | inconsistency | 5+ different product framings across VERSION, index.html, /api/health, CLAUDE.md, README — "Medical Coding Agent" / "Clinical AI Platform" / "医疗收入合规 AI 平台" / "iCoDer Console" |
| **G2-008** | P2 | term-drift | No canonical vocabulary for Agent / Capability / Expert / Tool / Runtime / Tenant / Organization / Output contract |
| **G2-009** | P2 | duplicate-route | `/support` route is declared twice in App.tsx (line 130 and line 140) |
| **G2-010** | P3 | nav-residue | Sidebar lists "Speech to Text" nav item but no destination; should be removed |

## B6. Gate 2 verdict

`SURFACE_INVENTORY_COMPLETE_WITH_P1_PRODUCT_RESIDUE_AND_56PCT_PLACEHOLDER_AGENTS`

- All 47 frontend routes mapped ✅
- All 38 backend routers grouped by API generation ✅
- **3 P1 findings**: Corti external link, Corti brand residue in UI strings, 13/23 Hub agents are metadata-only placeholders
- **7 P2 findings**: dead links, orphan pages, label drift, term drift
- Real product IA has **3 generations of URL schemes** (`/ai-studio/*`, `/studio/*`, `/manage/*`) co-existing via aliases

Gate 2 closes. Proceed to **Gate 3 — Full Browser Walkthrough**.
