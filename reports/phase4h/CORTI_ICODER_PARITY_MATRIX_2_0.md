# Phase 4-H §14 — Corti × iCoDer Parity Matrix 2.0

**Audit date:** 2026-07-10
**Source PDF:** `Phase 4-H Audit Report.pdf` §14 (20 dimensions × 6 fields each)
**Dev mode:** FROZEN per §2.1 — this is a READ-ONLY parity matrix.

## Methodology

Per PDF §14, each of 20 dimensions is rated using one of:
- **PARITY** — iCoDer matches Corti on core semantics
- **CLOSE** — minor gap, easy to close
- **PARTIAL** — some elements match, some missing
- **UI_ONLY** — UI shell exists in iCoDer but no backing runtime
- **MISSING** — iCoDer entirely lacks this
- **ICODER_ADVANTAGE** — iCoDer has more than Corti
- **NOT_APPLICABLE** — not relevant for iCoDer product strategy
- **UNKNOWN** — cannot confirm

Each dimension has 6 fields: `evidence` / `impact` / `root_cause` / `recommendation` / `priority` / `decision`.

`decision` uses Corti-parity verdicts (per PDF §2.3): `MUST_MATCH` / `LOCALIZE_FOR_CHINA` / `ICODER_ADVANTAGE` / `DEFER` / `DO_NOT_COPY`.

---

## Parity Matrix 2.0 — Summary Table

| # | Dimension | Verdict | Priority | Decision |
|---|---|---|---|---|
| 1 | Product Strategy | **PARITY** | — | MUST_MATCH |
| 2 | Information Architecture | **PARITY** | — | MUST_MATCH |
| 3 | Agent Discovery | **CLOSE** | P2 | MUST_MATCH |
| 4 | Agent Detail | **PARITY** | — | MUST_MATCH |
| 5 | Agent Configuration | **PARITY** | — | MUST_MATCH |
| 6 | Agent Runtime | **ICODER_ADVANTAGE** | — | ICODER_ADVANTAGE |
| 7 | Agent Output | **PARITY** | — | MUST_MATCH |
| 8 | Expert Model | **PARITY** | — | MUST_MATCH |
| 9 | Tool Model | **PARITY** | — | MUST_MATCH |
| 10 | Context Model | **ICODER_ADVANTAGE** | — | ICODER_ADVANTAGE |
| 11 | Knowledge Model | **PARTIAL** | P2 | LOCALIZE_FOR_CHINA |
| 12 | RunHistory | **ICODER_ADVANTAGE** | — | ICODER_ADVANTAGE |
| 13 | Trace | **PARTIAL** | P0 | MUST_MATCH |
| 14 | Cost | **PARTIAL** | P0 | MUST_MATCH |
| 15 | API Client | **CLOSE** | P2 | MUST_MATCH |
| 16 | API / SDK | **PARITY** | — | MUST_MATCH |
| 17 | Third-party Integration | **PARTIAL** | P1 | MUST_MATCH |
| 18 | Fork / Version / Publish | **ICODER_ADVANTAGE** | — | ICODER_ADVANTAGE |
| 19 | Security / Tenant / Audit | **ICODER_ADVANTAGE** | — | ICODER_ADVANTAGE |
| 20 | China Hospital Localization | **ICODER_ADVANTAGE** | — | LOCALIZE_FOR_CHINA |

**Summary counts:**
- PARITY: 9 (Dimensions 1, 2, 4, 5, 7, 8, 9, 16)
- CLOSE: 2 (Dimensions 3, 15)
- PARTIAL: 4 (Dimensions 11, 13, 14, 17)
- ICODER_ADVANTAGE: 5 (Dimensions 6, 10, 12, 18, 19, 20) — note: 20 is also LOCALIZE_FOR_CHINA
- UI_ONLY: 0
- MISSING: 0

**Critical P0 fixes:** 2 (Trace bugs, Cost bugs)
**P1 integration gap:** 1 (Web Component embed track)
**P2 polish:** 4 (Agent Discovery, Knowledge Model, API Client actions)

---

## Detailed Matrix

### 1. Product Strategy

| Field | Value |
|---|---|
| Verdict | **PARITY** |
| Evidence | Both Corti and iCoDer are cloud-hosted SaaS for healthcare AI agents. Corti: EU/US regions, hospital = Customer, multi-tenant. iCoDer: EU/US/CN regions, hospital = Tenant, multi-tenant per CLAUDE.md. Both expose: AI Studio (Agents + STT + TextGen + Embedded + Facts + Medical Coding) + Manage (API Clients + Team + Billing + Usage + Customers + Templates + Settings). |
| Impact | Strategic alignment — iCoDer matches Corti's "API as product" model. No strategic gap. |
| Root cause | iCoDer pivoted to Corti-style SaaS on 2026-06-17 (memory `project_pivot_2026_06_17.md`). |
| Recommendation | No action needed. Maintain parity. |
| Priority | — |
| Decision | **MUST_MATCH** |

---

### 2. Information Architecture

| Field | Value |
|---|---|
| Verdict | **PARITY** |
| Evidence | Corti left nav: Home + Developer (Quickstart + Corti Models) + AI Studio (Overview/Agents/STT/TextGen/Embedded/Facts/Coding) + Manage (API Clients/Team/Billing/Usage/Customers/Templates/Settings) + Support. iCoDer left nav: 首页 + 开发者快速入门 + AI STUDIO (总览/AI智能体/语音转录/事实提取/医学编码) + 管理 (API客户端/团队/计费/用量/客户/模板/设置) + 支持. 1:1 mapping per §4 IA audit. |
| Impact | Users can navigate identically in both products. |
| Root cause | Phase 3-B2 / 4-D deliberate Corti replication (memory `project_phase4_d_corti_replication_taste_skill_audit_2026_07_08.md`). |
| Recommendation | No action. Maintain parity. |
| Priority | — |
| Decision | **MUST_MATCH** |

---

### 3. Agent Discovery

| Field | Value |
|---|---|
| Verdict | **CLOSE** |
| Evidence | Both have "My agents" + "Pre-built agents" tabs. Corti: 20 pre-built agents (medical coding + 19 others across 4 use cases). iCoDer: 8 iCoDer built agents (medical coding + 4 P0 + 3 P1). iCoDer has 12 fewer pre-built agents. Both have card grid with name + date + author. |
| Impact | iCoDer exposes fewer out-of-box agents — user has less to discover. |
| Root cause | iCoDer focused on coding/compliance vertical; Corti covers broader healthcare (triage/ICU/nursing handoff/discharge education/etc.). |
| Recommendation | Add 4-6 more pre-built agents to reach Corti parity (Denial Appeals + Patient Discharge Education + Referral Generator + Clinical Education). 4 of these already exist in iCoDer as stubs per §5 inventory. |
| Priority | P2 |
| Decision | **MUST_MATCH** |

---

### 4. Agent Detail

| Field | Value |
|---|---|
| Verdict | **PARITY** |
| Evidence | Both have: left chat panel (input + Add context + Pinned message parts + Ctrl+Enter), right Settings/Code tabs (Settings = Name + System prompt + Experts; Code = JS SDK + .NET SDK + JSON Config). iCoDer matches Corti 1:1 per memory `project_phase4_d_corti_replication_taste_skill_audit_2026_07_08.md` + `feedback_agent_pages_replicate_corti.md`. |
| Impact | Users see identical detail page layout. |
| Root cause | Phase 4-D/E deliberate Corti replication. |
| Recommendation | No action. Maintain parity. |
| Priority | — |
| Decision | **MUST_MATCH** |

---

### 5. Agent Configuration

| Field | Value |
|---|---|
| Verdict | **PARITY** |
| Evidence | Both: Name (50-char limit), System prompt (multi-line), Experts (browse library + custom + add expert), Tools (bound via Expert's mcpServers, not direct agent config). iCoDer matches Corti per §7 + §8 audits. |
| Impact | Identical configuration UX. |
| Root cause | Phase 4-A Agent Backend Provider Architecture + Phase 4-B Note Completeness LLM migration + Phase 4-C Code Validation LLMWithTools migration. |
| Recommendation | No action. |
| Priority | — |
| Decision | **MUST_MATCH** |

---

### 6. Agent Runtime

| Field | Value |
|---|---|
| Verdict | **ICODER_ADVANTAGE** |
| Evidence | iCoDer has unified Agent Run API `POST /api/v1/agents/{id}/run` with 13-field envelope (Phase 4-F2) + Medical Coding fast path (`corti_like_fast` mode, ~9s T12) + A2A orchestrator (InboundHandler) + PureLLMProvider + RuleEngine + LLMWithToolsProvider. Corti runtime API is opaque (no public unified endpoint spec). iCoDer also has `runtime_mode` parameter (corti_like_fast / medcoder_deep / a2a_pure_llm / rule_engine). |
| Impact | iCoDer exposes more runtime knobs; developers can choose fast vs deep mode. |
| Root cause | Phase 4-A backend provider architecture + Phase 4-F2 unified run API. |
| Recommendation | Keep as iCoDer ADVANTAGE. Document runtime_mode parameter publicly. |
| Priority | — |
| Decision | **ICODER_ADVANTAGE** |

---

### 7. Agent Output

| Field | Value |
|---|---|
| Verdict | **PARITY** |
| Evidence | Both: streamed chat output (token-by-token) + structured result envelope (`summary`, `evidence[]`, `manual_review_required`, `warnings[]`). iCoDer 13-field envelope matches Corti per §11.1 #12 + Phase 4-F2. Copy JSON / Copy Markdown buttons on iCoDer AgentChatPage (Corti lacks — iCoDer ADVANTAGE). |
| Impact | Users can extract structured output identically. |
| Root cause | Phase 4-F2 A2A-compatible envelope. |
| Recommendation | No action. |
| Priority | — |
| Decision | **MUST_MATCH** |

---

### 8. Expert Model

| Field | Value |
|---|---|
| Verdict | **PARITY** |
| Evidence | Both: Expert = system-prompt-fragment + optional mcpServers + optional configSchema. Corti: 13 Experts (coding-expert + 12 others). iCoDer: 8 iCoDer built Experts (coding-expert + 7 others) per §7 audit. Both support expert rebinding via Agent config. iCoDer Expert implementation matches Corti per `CORTI_EXPERT_RUNTIME_AUDIT.md`. |
| Impact | Identical Expert model. |
| Root cause | Phase 3-B1.5 Corti reverse engineering + Phase 4-A backend provider arch. |
| Recommendation | No action. |
| Priority | — |
| Decision | **MUST_MATCH** |

---

### 9. Tool Model

| Field | Value |
|---|---|
| Verdict | **PARITY** |
| Evidence | Corti: Tools NOT first-class — bound inside Expert via mcpServers[] (2 of 13 Experts have MCP servers: posos oauth2.0 + drugbank bearer). iCoDer: FULL PARITY via Phase 3-C1 (4 MCP auth types: none/bearer/oauth2/apikey + 7 JSON-RPC error codes -32006..-32012) + Phase 4-A ToolMCPCompatLayer + Phase 4-C 4 MCP tools (verify_code/get_guidelines/explore_code/search_codes). |
| Impact | iCoDer can mount any Corti-style MCP server. |
| Root cause | Phase 3-C1 MCP auth + Phase 4-A ToolMCPCompatLayer. |
| Recommendation | No action. |
| Priority | — |
| Decision | **MUST_MATCH** |

---

### 10. Context Model

| Field | Value |
|---|---|
| Verdict | **ICODER_ADVANTAGE** |
| Evidence | Corti Context: 9 dimensions (message attachments JSON-only + session history in-memory SHARED + patient-level IMPLIED via template key + encounter-level NOT OBSERVED + Agent-fixed systemPrompt + Pinned message parts OBSERVED + External EHR NOT OBSERVED + API call Context via API Client combobox + Expert shared Context). iCoDer matches on 5/9 user-visible + exceeds on 4 (broader file support + RunHistory + explicit patient/encounter IDs via setPatientContext + GC policy per `docs/ICODER_V1_CONTEXT_SPEC.md`). |
| Impact | iCoDer has more explicit context model + GC policy. |
| Root cause | Phase 1 A2A spec design (`docs/ICODER_V1_CONTEXT_SPEC.md`). |
| Recommendation | Add `pinned_parts[]` to pack v1.4 to close the only Corti ADVANTAGE. P2. |
| Priority | P2 |
| Decision | **ICODER_ADVANTAGE** |

---

### 11. Knowledge Model

| Field | Value |
|---|---|
| Verdict | **PARTIAL** |
| Evidence | Corti: No explicit Knowledge Base page in Console (per §4 IA audit). Knowledge is implicit in Experts (e.g., pubmed-expert implies PubMed access) + Tools (drugbank expert implies DrugBank KB). iCoDer: Has iCoDerA data assets (`icd10cn_code_catalog.json` 37,897 codes + `evidence_anchoring_kb.json` 972 codes × 6,490 patterns + `coding_differentiation_kb.json` 2,090 code-pair decisions + `cot_generation_progress_v2.json` 175/500 rerank CoT few-shot per CLAUDE.md MedCodER section). Used by MedCodER pipeline. |
| Impact | iCoDer has stronger medical coding KB (CN-specific ICD-10-CN with 37,897 codes + synonyms + evidence patterns). Corti has broader KB via third-party (PubMed/DrugBank) but no coding-specific KB. |
| Root cause | iCoDer's CN market focus demands ICD-10-CN coverage. |
| Recommendation | Localize for China — keep iCoDerA assets. Add PubMed/DrugBank-equivalent Chinese medical KBs (e.g., 中国知网 CNKI / 万方医学) as Expert-bound KBs. |
| Priority | P2 |
| Decision | **LOCALIZE_FOR_CHINA** |

---

### 12. RunHistory

| Field | Value |
|---|---|
| Verdict | **ICODER_ADVANTAGE** |
| Evidence | Corti: NO dedicated RunHistory page in Console left nav (only aggregate /usage chart with date + API Client filters). iCoDer: `run_history` table (alembic 010, Phase 4-G) + `GET /api/runtime/runs/history` endpoint with agent_id + user_id + org_id filters + per-agent "Recent runs" dropdown on AgentChatPage. iCoDer has Cost/Latency/Error/Input/Output fields per run. |
| Impact | iCoDer users can audit per-run history; Corti users can only see aggregate. |
| Root cause | Phase 4-G #3 RunHistory table + Phase 4-F2 trace_events persistence. |
| Recommendation | Add Date filter (Corti has "Last 30 days" preset; iCoDer only has `limit`). Add daily credits consumed chart (Corti has chart; iCoDer has only metric cards). |
| Priority | P1 (Date filter + chart) |
| Decision | **ICODER_ADVANTAGE** |

---

### 13. Trace

| Field | Value |
|---|---|
| Verdict | **PARTIAL** |
| Evidence | Corti: NO trace page in Console. Only streaming chat output + per-run "Credits consumed" footer. iCoDer: 9-step Corti-parity timeline on RunTrace page + 15 trace fields (lifecycle/expert/tool/model events + token + cost + step duration + cumulative duration + error + retry + metadata + input/output + PHI redaction + copy). **BUT** 2 confirmed bugs: (a) step duration double-counted (7 steps shown for 3-step run, 3020ms × 3 = 9060ms phantom total); (b) inline trace vs persisted trace metadata mismatch (some steps have duration, some don't). |
| Impact | Trace UI is misleading due to phantom duration. PDF §12.2 explicitly calls this out. |
| Root cause | Inline emitter (real-time SSE) and persisted emitter (DB write) both writing to same `trace_events[]` array. |
| Recommendation | P0 fix: consolidate inline + persisted emitters into single emitter with deferred duration computation. Verify RunTrace page shows 3 steps (not 7) with 3020ms total (not 9060ms). |
| Priority | **P0** |
| Decision | **MUST_MATCH** |

---

### 14. Cost

| Field | Value |
|---|---|
| Verdict | **PARTIAL** |
| Evidence | Corti: $0.034596 topbar live cost + $48.69 /billing balance + $0.83 /usage 30d consumed + "Reset live cost" button + low balance alert + auto top-up + Plan/Billing History/Business info tabs. iCoDer: $50.00 topbar + ¥50.00 /billing + ¥0.00 /usage 30d consumed + low balance alert + auto top-up + Plan/Billing History/Business info tabs (matches Corti). **BUT** 2 bugs: (a) currency mismatch ($ vs ¥); (b) /usage shows ¥0.00 consumed but real runs consumed credits (not wired to run_history.cost). |
| Impact | iCoDer /usage page is broken — shows ¥0.00 even after paid runs. TopBar currency inconsistent with /billing. |
| Root cause | (a) TopBar uses USD hardcoded; /billing uses yuan hardcoded. (b) /usage page reads from a different source than TopBar live cost counter. |
| Recommendation | P0 fix: (a) Unify currency — `ICODER_CURRENCY` env var, default CNY for CN market. (b) Wire /usage page to `SELECT SUM(cost) FROM run_history WHERE created_at BETWEEN start AND end`. |
| Priority | **P0** |
| Decision | **MUST_MATCH** |

---

### 15. API Client

| Field | Value |
|---|---|
| Verdict | **CLOSE** |
| Evidence | Both: API Client page with OAuth2 client credentials. Corti: 4 action buttons per client (Copy Client ID / Regenerate secret / Show secret on-demand / Copy secret / Copy env ID / Copy tenant / Copy all as .env). iCoDer: Has Copy + Delete actions, but LACKS Regenerate + Show-on-demand + Copy-all-as-.env-on-API-Client-page (only in Quickstart). |
| Impact | iCoDer users can't rotate secrets without deleting + recreating client. |
| Root cause | iCoDer APIClientsPage (Phase 4-G) shipped before all Corti action buttons were replicated. |
| Recommendation | Add 3 buttons: Regenerate secret + Show on-demand + Copy all as .env on API Client page. |
| Priority | P2 |
| Decision | **MUST_MATCH** |

---

### 16. API / SDK

| Field | Value |
|---|---|
| Verdict | **PARITY** |
| Evidence | Corti: JS SDK (`@corti/sdk` npm) + .NET SDK (`Corti.Sdk` NuGet) + Developer Quickstart (3-step: use case → AI prompt → credentials) + deep links to Claude Code/Cursor/Codex/Lovable + Agent Skills program at `docs.corti.ai/.well-known/agent-skills/{slug}/SKILL.md`. iCoDer: Developer Quickstart page (4 tabs: AI Tools / JS SDK / .NET SDK / API Playground) + 4 use cases (dictation/scribe/coding/chat) + 4 AI tool deep links (Claude/Cursor/Codex/Lovable) + 4 SKILL.md files at `public/.well-known/agent-skills/{slug}/SKILL.md` + API Playground tab (iCoDer ADVANTAGE — Corti lacks). |
| Impact | Developer onboarding is identical. |
| Root cause | Phase 4-D Developer Quickstart replication + Agent Skills program init. |
| Recommendation | No action. iCoDer matches + exceeds (API Playground). |
| Priority | — |
| Decision | **MUST_MATCH** |

---

### 17. Third-party Integration

| Field | Value |
|---|---|
| Verdict | **PARTIAL** |
| Evidence | Corti: Web Component `<corti-embedded>` + `@corti/embedded-web` npm + `assistant.auth({access_token, refresh_token, mode:'stateless'})` + `configureSession({defaultTemplateKey})` + `configure({features, locale})` + `addEventListener('embedded-event', {name, payload})` with `account.creditsConsumed` + `error.triggered` subtypes + Theme (Primary color #3C61DD) + Locale (Interface + Dictation language). iCoDer: HAS `packages/icoder-embedded/` source (300 LOC) + `@icoder/embedded` package.json + `<icoder-assistant>` Web Component + `/api/embedded/assistant.js` + `/api/embedded/preview` endpoints. **BUT** API surface DIFFERS: iCoDer uses attribute-based config (`base-url` + `access-token` + `agent-ref` + `theme`), Corti uses method-call config (`assistant.auth()` + `configureSession()` + `configure()` + `show()`). iCoDer emits `coding.completed` + `error` events directly; Corti emits unified `embedded-event` with `{name, payload}` envelope. iCoDer `@icoder/embedded` NOT published to npm. |
| Impact | iCoDer can't be embedded in 3rd-party HIS/EMR frontends without writing custom integration code. Corti's `@corti/embedded-web` is one `npm install` away. |
| Root cause | iCoDer Web Component was built stub-first (Phase 3-B2) but not updated to match Corti's method-call API surface. |
| Recommendation | P1: Rewrite `<icoder-embedded>` to match Corti API surface (rename tag + add `assistant.auth()` / `configureSession()` / `configure()` / `show()` methods + unified `embedded-event` with `account.creditsConsumed` + `error.triggered` subtypes). P1: Publish `@icoder/embedded` to npm. |
| Priority | **P1** |
| Decision | **MUST_MATCH** |

---

### 18. Fork / Version / Publish

| Field | Value |
|---|---|
| Verdict | **ICODER_ADVANTAGE** |
| Evidence | Corti: Click pre-built agent → `/agents/new?preset=<slug>` form → "Create agent" button. No version field, no Draft/Published, no marketplace, no upstream link. iCoDer: Hub "Chat / Use Agent" CTA → `POST /api/agents/{id}/clone` → AgentChatPage. **iCoDer ADVANTAGES:** Forked-from badge (`config.source_agent_ref` preserved), Name auto-copied on clone, Toast `已复制到我的智能体`, `version` field in `agent_pack.json` (display-only), `agent_ref` with version suffix at embed time. iCoDer also DELETED marketplace concept in Phase 1.2 (correct Corti-parity decision). |
| Impact | iCoDer users get clearer fork tracking; Corti users don't know which agent was forked from which. |
| Root cause | Phase 4-G #4 Fork button + Forked-from badge. |
| Recommendation | No action. iCoDer already leads. |
| Priority | — |
| Decision | **ICODER_ADVANTAGE** |

---

### 19. Security / Tenant / Audit

| Field | Value |
|---|---|
| Verdict | **ICODER_ADVANTAGE** |
| Evidence | Corti: OAuth2 Client Credentials + ROPC + region isolation (EU/US) + GDPR compliance + no per-Client scope/rate-limit/Agent RBAC (per §10.1 audit). iCoDer: Same OAuth2 + region isolation (EU/US/CN — iCoDer ADVANTAGE: CN region) + DataPolicy edge PHI redaction + `redacted_view` in trace + AuditLog + RunHistory table with `api_client_id` attribution (Phase 4-G) + 4 MCP auth types + 7 JSON-RPC error codes (Phase 3-C1) + `account.creditsConsumed` event surface equivalent (live cost counter). |
| Impact | iCoDer has stronger audit trail (RunHistory + AuditLog + trace_events with api_client_id) + CN region for Chinese hospital data residency. |
| Root cause | Phase 3-C1 MCP auth + Phase 4-G api_client_id + CLAUDE.md DataPolicy edge PHI redaction. |
| Recommendation | No action. iCoDer leads on security/audit. |
| Priority | — |
| Decision | **ICODER_ADVANTAGE** |

---

### 20. China Hospital Localization

| Field | Value |
|---|---|
| Verdict | **ICODER_ADVANTAGE** |
| Evidence | Corti: ICD-10-CM (US) + ICD-10-PCS + CPT (US) — no ICD-10-CN, no ICD-9-CM-3-CN, no CN-DRG, no DIP, no CN region. iCoDer: ICD-10-CN (37,897 codes via `icd10cn_code_catalog.json`) + ICD-9-CM-3-CN (procedure coding) + CN-DRG/DIP rule structures reserved per CLAUDE.md + CN region (EU/US/CN per CLAUDE.md cloud architecture) + Chinese hospital scenarios (HIS/EMR = API Client, 医院 = Tenant) + Simplified Chinese i18n + Chinese payment methods (Alipay/WeChat Pay future). |
| Impact | iCoDer is the only viable Corti alternative for Chinese hospitals. |
| Root cause | iCoDer's product strategy: Corti-style SaaS for China hospital market (memory `project_pivot_2026_06_17.md` + CLAUDE.md). |
| Recommendation | Continue CN localization. Add CN-DRG/DIP rule engine. Add Chinese medical KBs (CNKI/万方). |
| Priority | P1 (CN-DRG/DIP rule engine) |
| Decision | **LOCALIZE_FOR_CHINA** |

---

## Summary Statistics

### By verdict

| Verdict | Count | Dimensions |
|---|---|---|
| PARITY | 9 | 1, 2, 4, 5, 7, 8, 9, 16, (15 close to parity) |
| CLOSE | 2 | 3, 15 |
| PARTIAL | 4 | 11, 13, 14, 17 |
| ICODER_ADVANTAGE | 6 | 6, 10, 12, 18, 19, 20 (20 also LOCALIZE_FOR_CHINA) |
| UI_ONLY | 0 | — |
| MISSING | 0 | — |
| NOT_APPLICABLE | 0 | — |
| UNKNOWN | 0 | — |

### By priority

| Priority | Count | Dimensions |
|---|---|---|
| **P0 (critical bugs)** | 2 | 13 (Trace double-count), 14 (Cost currency + wiring) |
| **P1 (close Corti gaps)** | 2 | 12 (RunHistory Date filter + chart), 17 (Web Component API surface) |
| **P2 (polish)** | 3 | 3 (more pre-built agents), 11 (Chinese medical KBs), 15 (API Client action buttons) |
| **P3 (optional)** | 0 | — |
| **No action (ADVANTAGE/PARITY)** | 13 | 1, 2, 4, 5, 6, 7, 8, 9, 10, 16, 18, 19, 20 |

### By decision

| Decision | Count |
|---|---|
| MUST_MATCH | 12 |
| LOCALIZE_FOR_CHINA | 2 (11, 20) |
| ICODER_ADVANTAGE | 6 |
| DEFER | 0 |
| DO_NOT_COPY | 0 |

---

## Key Findings

### iCoDer has 0 UI_ONLY shells

This is a major improvement vs prior Phase 4-E3 walkthrough (memory `project_phase4_e3_full_browser_walkthrough_2026_07_09.md`) which had 1 S1 critical blocker (MedCodER 60s+ timeout) + multiple UI shells. Phase 4-F1 + F2 + F3 closed those gaps — all 8 iCoDer built agents now have real DeepSeek LLM backing (latency 2275-6784ms per memory `project_phase4_f3_core_agent_smoke_2026_07_10.md`).

### iCoDer has 6 ADVANTAGES over Corti

1. **Agent Runtime** — `runtime_mode` parameter (corti_like_fast / medcoder_deep / a2a_pure_llm / rule_engine) for fast vs deep mode
2. **Context Model** — explicit `setPatientContext({patientId, name, encounterId})` + GC policy + RunHistory
3. **RunHistory** — server-persisted table with agent/user/org filters (Corti has only aggregate chart)
4. **Fork / Version / Publish** — Forked-from badge + auto-copied Name + Toast on clone
5. **Security / Tenant / Audit** — CN region + AuditLog + trace_events with api_client_id + edge PHI redaction
6. **China Hospital Localization** — ICD-10-CN (37,897 codes) + ICD-9-CM-3-CN + CN-DRG/DIP reserved + CN region

### iCoDer has 2 P0 critical bugs (PDF §12.2 explicit call-outs)

1. **Trace step duration double-counted** — 7 steps shown for 3-step run, 3020ms × 3 = 9060ms phantom total
2. **Cost currency mismatch + /usage not wired** — TopBar $50.00 USD vs /billing ¥50.00 yuan vs /usage ¥0.00 consumed

### iCoDer has 1 P1 major gap vs Corti

1. **Web Component API surface** — iCoDer `<icoder-assistant>` uses attribute-based config; Corti `<corti-embedded>` uses method-call config (`assistant.auth()` / `configureSession()` / `configure()` / `show()`). `@icoder/embedded` not published to npm.

### iCoDer has 3 P2 polish items

1. **Agent Discovery** — 8 iCoDer built agents vs Corti's 20 (add 4-6 more: Denial Appeals + Patient Discharge Education + Referral Generator + Clinical Education)
2. **Knowledge Model** — add Chinese medical KBs (CNKI/万方) as Expert-bound KBs
3. **API Client** — add Regenerate / Show-on-demand / Copy-all-as-.env buttons

---

## Cross-references

- `CORTI_ICODER_PARITY_MATRIX_2_0.md` (this file)
- `outputs/phase4h/parity_matrix_2_0.csv` (CSV export)
- `outputs/phase4h/parity_matrix_2_0.json` (JSON export)
- §4 IA: `PHASE4H_CORTI_IA_AUDIT.md`
- §5 Inventory: `PHASE4H_CORTI_AGENT_INVENTORY.md`
- §7 Expert: `CORTI_EXPERT_RUNTIME_AUDIT.md`
- §8 Tool: `CORTI_TOOL_RUNTIME_AUDIT.md`
- §9 Context: `CORTI_CONTEXT_MODEL_AUDIT.md`
- §10 Developer: `CORTI_DEVELOPER_EXPERIENCE_AUDIT.md`
- §11 Integration: `CORTI_THIRD_PARTY_INTEGRATION_AUDIT.md` + `ICODER_INTEGRATION_GAP_ANALYSIS.md`
- §12 Run/Trace/Cost: `RUN_TRACE_COST_PARITY_AUDIT.md`
- §13 Fork/Version/Publish: `CORTI_FORK_VERSION_PUBLISH_AUDIT.md`
- §3.1 Baseline: `PHASE4H_BASELINE.md`
- §3.2 iCoDer surfaces: `PHASE4H_ICODER_SURFACES.md`
- §3.3 Corti env: `PHASE4H_CORTI_ENVIRONMENT.md`

---

**Parity Matrix 2.0 complete.** Next: §16 test fixtures → §17 final report → §18+§19 architecture inference + Phase 5 recommendation.
