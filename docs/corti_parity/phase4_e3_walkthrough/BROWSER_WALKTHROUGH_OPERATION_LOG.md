# Browser Walkthrough Operation Log — iCoDer × Corti

**Date**: 2026-07-09
**Operator**: Claude Code (design-taste-frontend skill + Playwright MCP)
**Session**: bb12ff3b-eb44-4e55-bffb-788808846840
**Scope**: Full iCoDer × Corti browser walkthrough producing 5 output files

## Environment

- **iCoDer frontend**: http://localhost:3002 (Vite dev server, port 3002 alive)
- **iCoDer backend**: http://localhost:8000 (FastAPI uvicorn, started 14:45:38, 16 packs discovered, 9 registered)
  - Health: `GET /api/health` → 200 `{"status":"healthy","app":"iCoDer Medical Coding Agent","version":"1.0.0","environment":"development","medcoder_index_ready":true,"llm_provider":"deepseek","llm_model":"deepseek-chat"}`
- **Corti Console**: https://console.corti.app (authorized, user logged in via debug Chrome)
- **Chrome remote debugging**: port 9222 (profile: `C:/Users/huawei/AppData/Local/Temp/chrome-debug-profile`)
- **Playwright MCP**: connected to Chrome at port 9222
- **Test data**: 78yo male, T12 vertebral compression fracture, osteoporosis, hypertension, T2DM, percutaneous vertebroplasty

## Operation Timeline

### Phase 1 — Env Discovery + Page Map

| Time | Op | Result |
|------|----|--------|
| 14:46 | Check Chrome 9222 | 200 OK, 1 tab open (iCoDer fact-extraction) |
| 14:46 | Check Vite 3002 | 200 OK |
| 14:46 | Check backend 8000 | 000 (down) |
| 14:46 | Start backend `uvicorn app.main:app --port 8000` | Started PID b7wyxb28p, 16 packs discovered, 9 registered |
| 14:47 | Backend health `/health` | 404 (path is `/api/health`) |
| 14:47 | Backend health `/api/health` | 200 healthy, medcoder_index_ready=true |
| 14:47 | Open new tab → https://console.corti.app | Redirected to /auth (debug Chrome = fresh profile) |
| 14:53 | User confirmed: log in to Corti via debug Chrome | User logged in via Google OAuth |
| 14:54 | Corti URL: `/project/b8f8129a-c31d-407f-b723-6ecc592d31e4` (Console Home) | Captured |
| 14:55 | Screenshot corti_01_projects_landing.png | Saved |
| 14:55 | Screenshot corti_02_console_home.png | Saved |
| 14:55 | Dismiss survey popup | Closed |
| 14:55 | Capture Corti sidebar nav structure | 22 nav items documented (see PAGE_MAP) |

### Phase 2 — Corti Deep Walkthrough (23 screenshots)

| Time | Page | Screenshot | Key observations |
|------|------|-----------|-------------------|
| 14:56 | AI Studio Overview | corti_03 | 6 capability cards (Agents/STT/TextGen/Embedded/FactExtraction/MedicalCoding) |
| 14:56 | Agents list | corti_04 | Tabs: My agents / Corti built; New agent button; search bar |
| 14:57 | Agents prebuilt | corti_05 | 20 pre-built agents in 4 use cases; cards show name+description+use case+Corti built badge |
| 14:57 | Agent detail Medical Coding | corti_06 | Left chat + Right dual pane Settings/Code; 4 experts (coding-expert/pubmed/web-search/medical-calculator); top bar live cost $0.000000 + Reset + API Client dropdown |
| 14:58 | Agent detail Code tab | corti_07 | 3 SDK tabs (JavaScript/Python/curl); copy button |
| 14:58 | STT Dictation | corti_08 | Real-time dictation UI with mic button |
| 14:59 | STT Ambient | corti_09 | Background ambient recording UI |
| 14:59 | STT Pre-recorded | corti_10 | Audio file upload + transcript |
| 15:00 | Text Generation | corti_11 | Guided document generation with template picker |
| 15:00 | Embedded Assistant | corti_12 | Web Component SDK with embed snippet |
| 15:01 | Fact Extraction | corti_13 | Input + extracted facts list with evidence chips |
| 15:01 | Medical Coding | corti_14 | 2-pane layout (Input flex-1 + Output w-480) + top toolbar |
| 15:02 | API Clients | corti_15 | Client list + create button + scopes display |
| 15:02 | Team | corti_16 | Member list + invite + role badges |
| 15:03 | Billing | corti_17 | Payment methods + invoices + credits balance $48.78 |
| 15:03 | Usage | corti_18 | Daily credits chart + period filter + API client filter |
| 15:04 | Customers | corti_19 | Customer list + create button |
| 15:04 | Templates | corti_20 | Generic template list (Beta badge, 6 items) |
| 15:05 | Settings | corti_21 | Profile/API Keys/Notifications/Theme sections |
| 15:05 | Developer Quickstart | corti_22 | 3 use cases + 1 SDK install button + Docs link |
| 15:06 | Corti Models | corti_23 | Frontier LLM hosting page (EU infrastructure) |

### Phase 3 — iCoDer Deep Walkthrough (15 screenshots)

| Time | Page | Screenshot | Key observations |
|------|------|-----------|-------------------|
| 15:10 | Login | (skipped — used debug Chrome login flow) | Logged in as admin@icoder.ai via debug Chrome |
| 15:12 | Home | icoder_02 | 4 hero tabs (转写/文书/对话/编码 NEW); $50.00 credits; no announcement banner; no survey popup |
| 15:13 | AI Studio Overview | icoder_03 | 6 capability cards matching Corti (with STT/TextGen/Embedded collapsed) |
| 15:13 | Agents list | icoder_04 | My agents tab + New agent button + search |
| 15:14 | Agents prebuilt | icoder_05 | 16 pre-built agents; richer metadata (status/mode/production_ready/date/author/category/version) |
| 15:14 | Agent chat Medical Coding | icoder_06 | Left chat + Right Settings/Code dual pane (Phase 4-D verified); A2A collaboration panel; no live cost counter |
| 15:15 | Medical Coding | icoder_07 | 2-pane + toolbar + Config drawer (Phase 3-F verified) |
| 15:16 | API Clients | icoder_08 | Match Corti layout |
| 15:16 | Team | icoder_09 | Match Corti layout |
| 15:17 | Billing | icoder_10 | Match Corti layout |
| 15:17 | Usage | icoder_11 | Match Corti layout + daily chart |
| 15:18 | Customers | icoder_12 | Match Corti layout |
| 15:18 | Templates | icoder_13 | 9 Chinese clinical categories (出院小结/入院记录/手术记录/查房记录/交接班记录/疑难病例讨论/术前讨论/术后讨论/死亡病例讨论) — LOCALIZATION_WIN |
| 15:19 | Settings | icoder_14 | Match Corti layout |
| 15:19 | Developer Quickstart | icoder_15 | 4 use cases + 4 AI tools (Claude Code/Cursor/Codex/Lovable) + API Playground — DEVEX_WIN |
| 15:20 | Sidebar 语音转录 link click | (no screenshot) | Redirects to / (route removed in Phase 3-B2, sidebar not synced) — IA_GAP G002 |

### Phase 4 — Scenario Compare (5 screenshots)

**Test data**: 78yo male, T12 vertebral compression fracture, osteoporosis, hypertension, T2DM, percutaneous vertebroplasty

**Corti input** (English): "78yo male presents with acute back pain after a fall. MRI shows T12 vertebral compression fracture. History of osteoporosis, hypertension, type 2 diabetes mellitus. Underwent T12 percutaneous vertebroplasty. Postoperative course uneventful."

**iCoDer input** (Chinese): "患者男性，78岁，因摔倒后腰背部剧痛入院。MRI 显示 T12 椎体压缩性骨折。既往有骨质疏松、高血压、2 型糖尿病病史。行 T12 经皮椎体成形术。术后过程平稳，无明显并发症。"

| Time | Step | Screenshot | Result |
|------|------|-----------|--------|
| 16:10 | Corti input | scenario_01_corti_input | Medical Coding Agent input pane filled |
| 16:11 | Corti run | scenario_02_corti_result | SUCCESS — 7 ICD codes returned in ~8s: M54.9 / M54.89 / W19.XXXA / S22.089A / M81.0 / I10 / E11.9 / Z47.89; $0.060820 consumed |
| 16:12 | iCoDer input | scenario_03_icoder_input | MedicalCodingPage input pane filled |
| 16:12 | iCoDer run start | scenario_04_icoder_result | "分析中..." spinner shown; Event Inspector logged "16:12:09 开始预测" |
| 16:13 | iCoDer run timeout | scenario_05_icoder_timeout | FAILURE — "timeout of 60000ms exceeded"; Event Inspector logged "16:13:09 失败: timeout of 60000ms exceeded" |

**Backend log analysis** (iCoDer failure):
- 16:12:10 — DeepSeek API call 1 (Stage 1: Extraction) — 200 OK
- 16:12:15 — DeepSeek API call 2 (Stage 4: Re-rank) — 200 OK
- 16:13:09 — Frontend timeout fired (60s exceeded)
- Stage 2 (BGE-M3 retrieval) + Stage 3 (merge) + Stage 5 (compliance) ran between/after LLM calls but did not complete within 60s

**Critical gap matrix finding**: iCoDer MedCodER 5-stage pipeline (extract/retrieve/merge/rerank/compliance) exceeds 60s frontend timeout, while Corti's simpler single-stage prediction returns in ~8 seconds. Classified as **G001 RUNTIME_GAP S1 P0**.

### Phase 5 — Gap Matrix Construction

| Time | Op | Result |
|------|----|--------|
| 16:30 | Build 15-field gap matrix CSV | 60 rows written covering 12 gap type categories + S0-S3 severity + P0-P3 priority |
| 16:30 | 17-dimension scoring pass | Per-dimension analysis embedded in each row's `dimension` field |

### Phase 6 — Output Files Written

| File | Status |
|------|--------|
| ICODER_CORTI_PAGE_MAP.md | Finalized (24 modules with parity status) |
| BROWSER_WALKTHROUGH_OPERATION_LOG.md | This file (Phase 1-6 timeline) |
| ICODER_CORTI_GAP_MATRIX.csv | Written (60 rows × 15 fields) |
| ICODER_CORTI_BROWSER_WALKTHROUGH_REPORT.md | Written (11 sections) |
| ICODER_REDESIGN_BACKLOG.md | Written (P0-P3 prioritized) |

## Findings (raw, per-page observations)

### Corti Console Home (`/project/{id}`)

**Sidebar nav** (3 sections + 1 sub-section):
- Top: Home
- Developer (collapsible): Quickstart, Corti Models
- AI Studio (7 items): Overview, Agents, Speech to Text (3 sub: Dictation, Ambient, Pre-recorded), Text Generation, Embedded Assistant, Fact Extraction, Medical Coding
- Manage (7 items): API Clients, Team, Billing, Usage, Customers, Templates (Beta badge), Settings
- Support (2 items): Get Help, Tickets Portal (external https://help.corti.app/tickets-portal)

**Top header**: Corti logo + project switcher ("Songluhua songluhua" dropdown)
**Top breadcrumb bar**: breadcrumb + $48.78 credits link + Toggle theme + Docs link (https://docs.corti.ai/)
**Hero section**: 4 tabs — Transcribe / Document / Chat / Code NEW — each with 2 CTA cards
**Overview section**: "Compare period" checkbox + "Last 30 days" range + "All API clients" filter + 2 metric cards ($48.78 Available credits / $0.73 Total consumed) + Daily credits chart (09-Jun → 09-Jul, $0-$0.36)
**Documentation column**: Authentication / Guides / API Reference
**SDKS AND TOOLS**: Javascript SDK / Postman / AI coding tools
**NEED HELP?**: Chat with us button + Open a ticket link
**Announcement banner**: "Corti Models is here — Frontier models for coding, hosted by Corti on European infrastructure"
**Survey popup**: $30 gift card feedback survey (Ben, Product Designer)

### iCoDer Home (`/`)

**Sidebar nav** (3 sections):
- Top: 首页
- AI Studio (5 items): 总览/AI智能体/语音转录/事实提取/医学编码 (语音转录 link broken — G002)
- Manage (7 items): API 客户端/团队/计费/用量/客户/模板/设置
- Support (2 items): 获取帮助/工单

**Top header**: logo + 文档 + EN + Test + dark mode + ?? + ?? (6 controls, 2 unlabelled — G020)
**Hero section**: 4 tabs (转写/文书/对话/编码 NEW) — matches Corti
**No announcement banner** (G049)
**No survey popup** (G050 — iCoDer exceeds)

### Corti Agent Detail vs iCoDer Agent Chat

**Corti** (`/project/{id}/ai-studio/agents/{agent}`):
- Top breadcrumb bar: Console Home > Agents > [name] + **live cost $0.000000** + **Reset live cost** + **API Client dropdown** + theme + Docs
- Left: chat pane with Add context button + Ctrl+Enter submit + message history
- Right: dual pane — Settings tab (System prompt/Model/Experts/Context) + Code tab (JavaScript/Python/curl SDK)
- 4 experts expandable: coding-expert / pubmed-expert / web-search-expert / medical-calculator-expert

**iCoDer** (`/ai-studio/agents/{id}/chat`):
- Top breadcrumb bar: 首页 > AI智能体 > [name] + tabs — **NO live cost counter** (G007)
- Left: chat pane with Add context + Ctrl+Enter + message history (Phase 4-D verified parity)
- Right: dual pane Settings/Code (Phase 4-D verified parity)
- Experts list with version + capability chips (Phase 4-D verified parity)
- A2A Collaboration panel at bottom showing discovered agents (Phase 4-D v2 A2A dispatch verified)

**Gap**: iCoDer missing live cost counter (G007 S2 P2).

### Corti Templates vs iCoDer Templates

**Corti**: 6 generic templates with Beta badge (e.g. "Clinical Note Template", "Discharge Summary Template")
**iCoDer**: 9 Chinese clinical document categories natively matching Chinese hospital document standards:
- 出院小结 (Discharge Summary)
- 入院记录 (Admission Record)
- 手术记录 (Surgical Record)
- 查房记录 (Ward Round Record)
- 交接班记录 (Shift Handover Record)
- 疑难病例讨论 (Difficult Case Discussion)
- 术前讨论 (Pre-operative Discussion)
- 术后讨论 (Post-operative Discussion)
- 死亡病例讨论 (Death Case Discussion)

**Verdict**: iCoDer exceeds Corti for China clinical workflow (G014 LOCALIZATION_WIN S0).

### Corti Developer Quickstart vs iCoDer Developer Quickstart

**Corti**: 3 use cases + 1 SDK install button + Docs link
**iCoDer**: 4 use cases + 4 AI coding tools (Claude Code/Cursor/Codex/Lovable) + API Playground + SDK install

**Verdict**: iCoDer exceeds Corti for developer onboarding (G015 DEVEX_WIN S0).

### Corti Medical Coding Run (success)

**Input**: "78yo male presents with acute back pain after a fall. MRI shows T12 vertebral compression fracture. History of osteoporosis, hypertension, type 2 diabetes mellitus. Underwent T12 percutaneous vertebroplasty. Postoperative course uneventful."

**Output** (7 codes, ~8 seconds, $0.060820 consumed):
- M54.9 Dorsalgia, unspecified (Evidence: "presenting with acute back pain after a fall")
- M54.89 Other dorsalgia (Alternative)
- W19.XXXA Unspecified fall (initial encounter)
- S22.089A Unspecified fracture of T11-T12 vertebra (initial encounter for closed fracture)
- M81.0 Age-related osteoporosis without current pathological fracture
- I10 Essential (primary) hypertension
- E11.9 Type 2 diabetes mellitus without complications
- Z47.89 Encounter for other orthopedic aftercare

### iCoDer Medical Coding Run (failure)

**Input**: "患者男性，78岁，因摔倒后腰背部剧痛入院。MRI 显示 T12 椎体压缩性骨折。既往有骨质疏松、高血压、2 型糖尿病病史。行 T12 经皮椎体成形术。术后过程平稳，无明显并发症。"

**Output**: TIMEOUT after 60s — no codes returned

**Backend log**:
- 16:12:10 — DeepSeek Stage 1 (Extraction) 200 OK
- 16:12:15 — DeepSeek Stage 4 (Re-rank) 200 OK
- 16:13:09 — Frontend 60s timeout fired

**Verdict**: Critical gap (G001 RUNTIME_GAP S1 P0) — MedCodER 5-stage pipeline exceeds 60s frontend timeout.
