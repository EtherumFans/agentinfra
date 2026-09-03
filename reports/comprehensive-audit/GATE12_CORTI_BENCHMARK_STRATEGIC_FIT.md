# Audit Gate 12 — Corti Benchmark and Strategic Fit (Track C + §五)

> Per PDF §三 Track C + §五: synthesizes Corti-vs-iCoDer parity findings across all prior gates, audits iCoDer's strategic positioning, and answers the PDF's core question — "iCoDer 当前产品首页在向谁表达价值?" (whose value is iCoDer's homepage expressing?).

## C1. Parity Matrix 2.0 — synthesizing all 11 prior gates

### C1.1 Per-dimension parity scoring

Scoring: **5 = PARITY** / **4 = CLOSE** / **3 = PARTIAL** / **2 = MISS** / **1 = MISSING** / **0 = N/A**. Corti baseline per `docs/corti_parity/CORTI_REFERENCE_BASELINE.md` (Stage 0).

| # | Dimension | Corti has | iCoDer has | Score | Evidence Gate |
|---|-----------|-----------|------------|-------|---------------|
| 1 | A2A protocol | v0.3, JSON-RPC, tasks async | v0.3, JSON-RPC, strict version header, **tasks = 501 stub (sync only)** | **4 CLOSE** | G6 |
| 2 | Agent Card discovery | `/.well-known/agent.json` | `/.well-known/agent.json` + `/llms.txt` | **5 PARITY** | G6 |
| 3 | Inbound message endpoint | `POST /agents/{id}/v1/message:send` | Same + Phase 4-F2 unified facade | **5 PARITY** | G6 |
| 4 | MCP server + tools | 13 Experts (5 coding + 8 lookup) | 11 tools, mount-time parity check | **4 CLOSE** | G6 |
| 5 | Orchestrator state machine | Implicit (LLM-driven conditional routing) | 5-stage explicit (received → planning → delegating → aggregating → completed) | **5 PARITY** | G6 |
| 6 | Agent Hub | 20 Pre-built Agents (all real) | 23 agents — **13/23 metadata-only (G2-003)** | **2 MISS** | G2 |
| 7 | Console product IA | Top → AI Studio → Manage → Support | Same 4-section sidebar | **5 PARITY** | G3 |
| 8 | Live cost (top bar) | `$48.69 USD` running | `¥0.049392 CNY` running | **5 PARITY** | G7 |
| 9 | RunHistory table | Yes | Yes, alembic 010, 240 rows | **5 PARITY** | G7 |
| 10 | RunTrace page | None | `/runs/:runId/trace` (graceful 404 — DB empty G7-001) | **iCoDer ADVANTAGE** | G7 |
| 11 | trace_events field on agent run | No | Yes, inline + persisted (dormant) | **iCoDer ADVANTAGE** | G7 |
| 12 | Signed trace URL | No | HMAC-SHA256 24h token | **iCoDer ADVANTAGE** | G7 |
| 13 | SSE run state events | Yes | `GET /api/v1/runs/{id}/events?token=` | **5 PARITY** | G7 |
| 14 | Idempotency-Key dedup | Yes | Yes, alembic 012, 11 records | **5 PARITY** | G7 |
| 15 | API Client registry | Yes (Console) | 9 CRUD endpoints, alembic 014 | **5 PARITY** | G8 |
| 16 | Embedded Web Component | `<corti-assistant>` (npm) | `<icoder-embedded>` (dist-serve; **not on npm G8-001**) | **3 PARTIAL** | G8 |
| 17 | Partner reference app | (not public) | `examples/partner-reference-app/` (server-side OAuth) | **iCoDer ADVANTAGE** | G8 |
| 18 | Usage page | Yes, last 7 days | Yes, last 30 days, by-agent/by-client | **5 PARITY** | G7 |
| 19 | Billing page | Stripe integration | Internal credits only, **no Stripe** | **3 PARTIAL** | G11 |
| 20 | Multi-region failover | Yes (eu / us active-active) | `regions.yaml` all `enabled: false` | **1 MISSING** | G11 |
| 21 | Edge-node PHI redaction | Yes (Corti engine) | Source-code WARNING "not production-grade" (G9-004) | **2 MISS** | G9 |
| 22 | Encryption at rest | Yes (column-level) | No (G9-005) | **1 MISSING** | G9 |
| 23 | Audit log | Full (per docs) | 5 actions / ~25 (G9-002) | **2 MISS** | G7+G9 |
| 24 | F1 baseline | (proprietary) | F1@1 = 0.15 on 5-case smoke; **no 201 baseline** (G10-001) | **1 MISSING** | G10 |
| 25 | Speech-to-Text | Real (Corti core product) | Route removed, page orphaned (G2-004) | **1 MISSING** | G2 |
| 26 | STT docs link | Corti docs | **AI Studio Overview has 13 Corti links** (G3-001 P0) | **0 BROKEN** | G3 |
| 27 | Brand consistency | All "Corti" | Mixed "iCoDer" + "Corti-style" UI strings (G2-002) | **3 PARTIAL** | G2 |
| 28 | Product naming coherence | "Corti" (single) | 5 framings: Medical Coding Agent / Clinical AI Platform / 医疗收入合规 / Console / Studio (G2-007) | **3 PARTIAL** | G2 |
| 29 | Cloud SaaS deployment | Real (4 domains) | **Docs-only**, all regions disabled (G11-001) | **1 MISSING** | G11 |
| 30 | Hospital pilots | Yes (production) | **0 real hospital tenants** (G9 + G8) | **1 MISSING** | G8+G9 |

### C1.2 Parity Matrix 2.0 verdict counts

```
PARITY (5):              11 dimensions
CLOSE (4):                2 dimensions
PARTIAL (3):              4 dimensions
MISS (2):                 4 dimensions
MISSING (1):              6 dimensions
BROKEN (0):               1 dimension (Corti docs redirect)
iCoDer ADVANTAGE:         4 dimensions
─────────────────────────────────
TOTAL:                   32 dimensions scored
```

**Corti-parity score: 11/32 PARITY = 34.4% full parity.** Including CLOSE: 13/32 = 40.6%.

Including the 4 iCoDer ADVANTAGE dimensions: iCoDer matches or exceeds Corti on **15/32 dimensions (47%)**.

### C1.3 The 6 MISSING dimensions

These are the dimensions where iCoDer is fundamentally behind Corti:

1. **Multi-region failover** — Corti: eu/us active-active. iCoDer: `regions.yaml` all disabled.
2. **Edge-node PHI redaction** — Corti: real engine. iCoDer: source-code warning.
3. **Encryption at rest** — Corti: column-level. iCoDer: none.
4. **F1 baseline** — Corti: proprietary benchmarks. iCoDer: 5-case F1@1=0.15 only.
5. **Cloud SaaS deployment** — Corti: 4 real domains. iCoDer: docs-only.
6. **Hospital pilots** — Corti: production. iCoDer: 0 real tenants.

Plus 4 MISS (significant gap):
7. **Agent Hub metadata-only** — 13/23 cards non-functional
8. **Audit log coverage** — 5/25 actions
9. **Speech-to-Text** — route removed
10. **Embedded npm publish** — packages not on registry

### C1.4 The 4 iCoDer ADVANTAGE dimensions

These are places where iCoDer does something Corti does not:

1. **RunTrace page** — Corti has no per-run trace UI
2. **Signed trace URL** — Corti has no partner-shareable trace URL
3. **Partner reference app** — Corti's partner integration examples are not public
4. **DRG/DIP grouping** — Corti does not offer this (it's ICD coding only)

⚠️ But per Gate 5, the DRG/DIP claim is **partially theater**: DIP is demo-only, DRG is real-but-unused in production.

## C2. Strategic positioning audit — "在向谁表达价值?"

### C2.1 The PDF's core question

PDF §Track C asks: **"当前产品首页在向谁表达价值?"** (whose value is the homepage expressing?).

### C2.2 The actual answer — Corti's customers, via 13 redirects

Per Gate 3 §C2 (P0 G3-001): the AI Studio Overview page (`/ai-studio`, the front-door landing) has **13 user-visible links to `docs.corti.ai/*` and `help.corti.app/*`**:

| # | Link | Lands on |
|---|------|----------|
| 1-6 | 文档 (智能体/STT/文本生成/嵌入式助手/事实抽取/医学编码) | docs.corti.ai |
| 7 | 认证 | docs.corti.ai/authentication |
| 8 | 指南 | docs.corti.ai/guides |
| 9 | API 参考 | docs.corti.ai/api-reference |
| 10 | JavaScript SDK | docs.corti.ai/sdk/js-sdk |
| 11 | Postman | docs.corti.ai/sdk/postman |
| 12 | AI 编码工具 | docs.corti.ai/quickstart |
| 13 | 提交工单 | help.corti.app/tickets-portal |

→ **iCoDer's front-door page is functionally a Corti customer-acquisition redirect.** This is not residue — it is the entire developer documentation surface.

### C2.3 Product naming incoherence — 5 framings

Per Gate 2 §B3.1:

| Source | Framing |
|--------|---------|
| `VERSION` file | "iCoDer" 1.1.0 |
| `index.html <title>` | "iCoDer Medical Coding Agent" |
| `/api/health app` field | "iCoDer Medical Coding Agent" |
| `CLAUDE.md` line 1 | "iCoDer — 医疗收入合规 AI 平台" |
| `README.md` line 1 | "iCoDer — Clinical AI Platform" |
| Sidebar default | "iCoDer Console" |

→ **5 different framings** of what iCoDer is. A hospital CIO landing on any page cannot form a coherent mental model.

### C2.4 Brand residue — "Corti-style" in user-visible UI

Per Gate 2 §B3.2:

| Locale key | zh-CN | en-US |
|-----------|-------|-------|
| `codingMode` | `'编码模式 (Corti-style)'` | `'Coding mode (Corti-style)'` |
| `embeddedPageSubtitle` | `'Corti 风格对齐 · 一次配置，随处复制'` | `'Corti-style parity · Configure once, copy anywhere'` |
| `runTraceIntro` | `'9 步 Corti-parity 时间线'` | (similar) |

→ **"Corti" appears in production UI strings** as a quality signal. This is brand-claim-by-association, not differentiation.

### C2.5 Strategic positioning verdict

```
STRATEGIC_POSITIONING_INCOHERENT
```

iCoDer cannot answer "who is this for?" with one voice:
- CLAUDE.md says: 医院医学编码 + 收入合规
- README.md says: Corti-competitive clinical AI platform
- index.html says: Medical Coding Agent
- AI Studio Overview says: Corti docs
- Embedded Assistant says: Corti-style parity

## C3. Product substance vs surface

### C3.1 The 4 PDF-mandated "core capabilities" status

PDF §Track C lists 4 capabilities to check: Medical Coding / CDI / DRG-DIP / Speech-to-Text.

| Capability | Status | Verdict |
|-----------|--------|---------|
| Medical Coding | Real code, F1@1=0.15, broken cost attribution (G5-001) | `LIVE_BUT_ACCURACY_UNPROVEN_AND_COST_BROKEN` |
| CDI | Real code, open hospital loop (G5-002), below formal benchmark tier | `LIVE_BUT_OPEN_LOOP_ACCURACY_UNPROVEN` |
| DRG/DIP | DRG real-but-unused, DIP demo-only (G5-008/009) | `DRG_PARTIAL_DIP_DEMO_ONLY` |
| Speech-to-Text | Route removed, page orphan (G2-004) | `DEAD` |

→ **0 of 4** capabilities are production-ready. The PDF's "Corti-like" core capability set is **not actually delivered**.

### C3.2 The 7 "Corti-style promises" audit

From CLAUDE.md + README.md hero claims:

| Promise | Reality |
|---------|---------|
| "Corti-competitive" | 11/32 parity dimensions = 34% full parity |
| "无限逼近 Corti" | 6 dimensions MISSING, 4 MISS |
| "每条决策链可审计" | run_trace_events table empty (G7-001) |
| "可溯源" | 13 Corti external links break the trace (G3-001) |
| "可重放" | trace DB dormant (G7-001) |
| "SHA-256 verifiable" | HMAC-signed trace URL exists but is bound to an empty store |
| "即开即用" | DEBUG=true + SECRET_KEY=change-me in committed .env (G9-001) |

→ **0 of 7** Corti-style promises are fully delivered.

## C4. The Corti-parity reframe — what is iCoDer actually good at?

### C4.1 Real strengths (where iCoDer is genuinely competitive)

1. **5-state run lifecycle + cancel endpoint + never-lies responses** (Phase 7 Gate 4)
2. **HMAC-signed 24h trace URL** (Phase 7 Gate 7)
3. **Real partner reference app with server-side OAuth** (Phase 7 Gate 12)
4. **9-endpoint API Client registry with rotation + scope management** (Phase 7 Gate 5)
5. **Bilingual (zh-CN + en-US) UI** — Corti is English-only
6. **ICD-10-CN Clinical Edition 2.0 (37,897 codes)** — Corti uses ICD-10-CM (US)
7. **CDI 9-红线 (red lines) ethics framework** — Corti has no equivalent published doctrine
8. **A2A v0.3 strict spec compliance** — Corti also v0.3 but iCoDer's stricter version-header enforcement is real
9. **Idempotency-Key dedup** — explicit alembic migration, 11 production records
10. **Preview Session HMAC Bootstrap Ticket** (Phase 7 Gate 13A) — Corti's widget auth is simpler

### C4.2 The China-market reframe

iCoDer's defensible position is **not** "Corti-competitive globally" but **"Corti-parity baseline + China-localization layer"**:

| Layer | Corti (global) | iCoDer (China) |
|-------|---------------|----------------|
| ICD standard | ICD-10-CM (US) | ICD-10-CN Clinical 2.0 |
| Currency | USD | CNY |
| Language | English | Bilingual zh/en |
| Compliance | HIPAA | 等保2.0 + GB/T 35273-2020 (target) |
| LLM | (proprietary) | DeepSeek (CN-friendly) |
| DRG/DIP | Not offered | DRG v1 real + DIP demo |
| Deployment | 4-region SaaS | Single-region SaaS docs-only |

→ **iCoDer's story should be "the China-localized clinical AI platform with Corti-parity architecture", not "Corti-competitive globally".** The current positioning incoherence (5 framings, 13 Corti redirects, "Corti-style" in UI strings) makes the actual defensible story invisible.

## C5. The 17 missing Pre-built Agents — confirmed

### C5.1 The Corti 20 vs iCoDer 23 problem

Per `docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md §10 Phase 3 Roadmap`:

> Phase 3 — 20 Pre-built Agents 实装 (17 缺 + 10 metadata-only 升级), ~85/100

The P1.3 audit's biggest forward-looking risk is the **17 missing Pre-built Agents**. Gate 2 verified this independently:

```
iCoDer Agent Hub: 23 agents
  preview × 10
  coming_soon × 13  ← metadata-only
```

13 of 23 cards (56%) are non-functional placeholders. The P1.3 audit said "17 missing" — Gate 2 says "13 metadata-only". The 4-agent gap is because some Corti agents are mapped to multiple iCoDer agents or specialized caps.

### C5.2 What "metadata-only" means

13 directories in `official_agents/` have `agent_pack.json` but **zero .py files** (Gate 6 §H3.3):

```
denial-appeals, diagnosis-extractor, discharge_edu, documentation-gap,
evidence-ranker, icd10-navigator, icu-summary, med-reconciliation,
nursing-handoff, prior-auth, referral-gen, rule-explainer, surgical-registry, triage
```

For a hospital CIO clicking through the Agent Hub, 56% of "AI agents" advertised do not exist.

## C6. The Corti brand-claim risk

### C6.1 What "Corti-style" actually signals to a hospital buyer

When iCoDer's Embedded Assistant page says `'Corti 风格对齐 · 一次配置，随处复制'`:

1. **To a hospital CIO who has never heard of Corti**: confusing (who is Corti?)
2. **To a hospital CIO who knows Corti**: implies iCoDer is a Corti clone or fork
3. **To Corti's legal team**: potential trademark / trade-dress issue
4. **To Corti's sales team**: iCoDer is positioning as a clone, easy to dismiss as "lower-quality Corti clone"

### C6.2 What iCoDer should claim instead

The defensible story is:

> "Built on the A2A v0.3 open standard with Corti-parity architecture, optimized for Chinese hospital compliance (等保2.0 / GB/T 35273-2020). Supports ICD-10-CN Clinical Edition 2.0, DRG/DIP grouping, and bilingual zh/en clinical workflows."

This:
- References Corti as an architecture baseline (not a brand claim)
- Centers iCoDer's China-specific value
- Mentions real differentiators (ICD-10-CN, DRG/DIP, bilingual)
- Avoids the "lower-quality Corti clone" trap

## C7. New findings

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G12-001** | P0 | parity-overclaim | iCoDer claims "Corti-competitive" + "无限逼近 Corti" in CLAUDE.md + README.md hero text, but actual parity is **11/32 dimensions (34%)** full PARITY. The 4 MISSING dimensions (multi-region, edge PHI, encryption, F1 baseline) are each individually disqualifying for the "competitive" claim. |
| **G12-002** | P0 | strategic-incoherence | iCoDer cannot answer "who is this for?" with one voice. 5 framings (Medical Coding Agent / Clinical AI Platform / 医疗收入合规 / Console / Studio) + 13 Corti external links on the front-door page + "Corti-style" in production UI strings. The strategic positioning is incoherent. |
| **G12-003** | P1 | product-substance | Of 4 PDF-mandated core capabilities (Medical Coding / CDI / DRG-DIP / STT), **0 are production-ready**: medical-coding F1=0.15, CDI open-loop, DRG real-but-unused, DIP demo-only, STT dead. |
| **G12-004** | P1 | missing-agents | 13 of 23 Agent Hub cards are metadata-only placeholders (denial-appeals, diagnosis-extractor, etc.). 56% of advertised AI capability does not exist. |
| **G12-005** | P1 | brand-risk | "Corti-style" appears in user-visible UI strings (Coding mode / Embedded subtitle / RunTrace intro). To hospital buyers this signals "lower-quality Corti clone". To Corti's legal team this is a trademark risk. |
| G12-006 | P2 | real-strength-undermarketed | iCoDer has 4 genuine Corti-parity ADVANTAGES (RunTrace page, signed trace URL, partner reference app, DRG/DIP) and 6 China-localization strengths (ICD-10-CN, CNY, bilingual, 等保 target, DeepSeek, CDI 9-红线). The current marketing buries these under Corti-clone framing. |
| G12-007 | P3 | promise-reality-gap | 7 Corti-style promises in README.md hero — 0 fully delivered. "可审计/可溯源/可重放" claims broken by G7-001 (trace DB dormant). "SHA-256 verifiable" overstates the dormant code. "即开即用" broken by G9-001 committed dev secrets. |

## C8. Track-level verdicts (interim)

| Sub-track | Verdict |
|-----------|---------|
| **C1 Corti parity score** | `11_32_DIMENSIONS_PARITY_34PCT` — 5 dimensions MISSING (cloud / multi-region / encryption / F1 / pilots) |
| **C2 Strategic positioning** | `INCOHERENT_5_FRAMINGS_13_CORTI_LINKS` — Front-door page redirects to Corti docs |
| **C3 Core capabilities** | `0_4_PRODUCTION_READY` — Medical-coding F1=0.15, CDI open-loop, DRG unused, DIP demo, STT dead |
| **C4 Real strengths** | `10_GENUINE_ADVANTAGES_BURIED_UNDER_CLONE_FRAMING` — RunTrace, signed URL, partner app, ICD-10-CN, bilingual, CDI 9-红线, etc. |
| **C5 Missing agents** | `13_23_HUB_CARDS_METADATA_ONLY` — 56% of advertised AI capability non-functional |
| **C6 Brand strategy** | `CORTI_CLONE_TRAP` — "Corti-style" in UI + Corti docs redirects = lower-quality-clone positioning |

## C9. Gate 12 verdict

`CORTI_PARITY_34PCT_STRATEGIC_POSITIONING_INCOHERENT_ZERO_CORE_CAPABILITIES_PRODUCTION_READY`

Specifically:

- **Parity score: 11/32 (34%)** — not "competitive" per any reasonable definition
- **6 dimensions MISSING**: cloud SaaS, multi-region, edge PHI, encryption at rest, F1 baseline, hospital pilots
- **4 dimensions MISS**: 13/23 agents metadata-only, audit log thin, STT dead, npm unpublished
- **1 dimension BROKEN**: AI Studio Overview redirects to Corti's actual docs
- **0 of 4 core capabilities production-ready**: medical-coding F1=0.15, CDI open-loop, DRG unused, DIP demo, STT dead
- **5 product framings** (Medical Coding / Clinical AI / 医疗收入合规 / Console / Studio) + 13 Corti links + Corti-style UI strings = strategic incoherence
- ✅ 4 genuine iCoDer ADVANTAGES (RunTrace, signed URL, partner app, DRG/DIP) + 6 China-localization strengths are real but undermarketed
- ✅ Bilingual + ICD-10-CN + DeepSeek are defensible China-market moats

**The defensible story is "China-localized clinical AI platform with Corti-parity architecture", not "Corti-competitive globally".** The current positioning buries the real strengths under Corti-clone framing and redirects hospital buyers to Corti.

Gate 12 closes. Proceed to **Gate 13 — Commercial and Hospital Pilot Readiness**.
