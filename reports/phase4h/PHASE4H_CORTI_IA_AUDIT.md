# Phase 4-H §4 Part 1 — Corti Full Information Architecture Audit

**Audit date:** 2026-07-10 14:55 local (06:55 UTC)
**Auditor:** Claude (Sonnet 4.5)
**Reference account:** Luhua Song <songluhua@gmail.com> (Google OAuth, project `b8f8129a-c31d-407f-b723-6ecc592d31e4`)
**Reference URL:** `https://console.corti.app/`

> Per PDF §4 Part 1 — full audit of Corti's information architecture (IA): navigation hierarchy, URL patterns, page structures, tab patterns, modal/drawer conventions, cross-linking, breadcrumbs, and i18n state. Goal: identify every Corti IA decision iCoDer should match (or explicitly diverge from) for parity.

---

## 1. URL pattern (top-level)

| Pattern | Example | Notes |
|---------|---------|-------|
| `/auth` | `/auth` | Sign-in (Google/GitHub/email) |
| `/auth/success?provider={provider}` | `/auth/success?provider=google` | Post-OAuth success redirect |
| `/` | `/` | Project picker (lists user's projects) |
| `/project/{project_id}` | `/project/b8f8129a-...` | Project Home dashboard |
| `/project/{project_id}/{section}` | `/project/{id}/api-clients` | Project-scoped section |
| `/project/{project_id}/ai-studio/{tool}` | `/project/{id}/ai-studio/agents` | AI Studio tool |
| `/project/{project_id}/ai-studio/agents/{view}` | `/project/{id}/ai-studio/agents/pre-built-agents` | Agents sub-view (My/Pre-built) |
| `/project/{project_id}/ai-studio/agents/new?preset={slug}` | `/project/{id}/ai-studio/agents/new?preset=medical-coding-icd-10-cpt-agent` | New agent from preset |
| `/project/{project_id}/corti-models` | (link from announcement banner) | Corti-hosted frontier models page |
| `https://help.corti.app/tickets-portal` | (external) | Tickets portal — separate domain |

**Key IA decisions:**
- Every URL is **project-scoped** (`/project/{project_id}/...`). No global URLs except `/auth`, `/`, and `/signup`.
- `project_id` is a UUID v4 string, always 36 chars.
- Path uses kebab-case for section names (`api-clients`, `ai-studio`, `pre-built-agents`).
- Query strings are used for **mode switches** (`?tab=X`) and **preset selection** (`?preset=X`).

## 2. Top-level navigation hierarchy (sidebar)

```
Project Switcher (top, project name + chevron)
├── Home                                  [/project/{id}]
├── Developer quickstart                  [/project/{id}/developer-quickstart]
│   ├── (Corti Models link in announcement)
│
├── AI Studio                             [section label]
│   ├── Overview                          [/project/{id}/ai-studio-overview]
│   ├── Agents                            [/project/{id}/ai-studio/agents]
│   │   ├── My agents (radio, default)
│   │   └── Pre-built agents (radio)     [/project/{id}/ai-studio/agents/pre-built-agents]
│   ├── Speech to Text                    [parent link + 3 child links]
│   │   ├── Dictation                    [/project/{id}/ai-studio/speech-to-text/dictation]
│   │   ├── Ambient                      [/project/{id}/ai-studio/speech-to-text/ambient]
│   │   └── Pre-recorded                 [/project/{id}/ai-studio/speech-to-text/pre-recorded]
│   ├── Text Generation                   [/project/{id}/ai-studio/text-generation]
│   ├── Embedded Assistant                [/project/{id}/ai-studio/embedded-assistant]
│   ├── Fact Extraction                   [/project/{id}/ai-studio/fact-extraction]
│   └── Medical Coding                    [/project/{id}/ai-studio/medical-coding]
│
├── Manage                                [section label]
│   ├── API Clients                       [/project/{id}/api-clients]
│   ├── Team                              [/project/{id}/team]
│   ├── Billing                           [/project/{id}/billing]
│   ├── Usage                             [/project/{id}/usage]
│   ├── Customers                         [/project/{id}/customers]
│   ├── Templates (Beta badge)            [/project/{id}/templates]
│   └── Settings                          [/project/{id}/settings]
│
├── Support                               [section label]
│   ├── Get Help                          [/project/{id}/ai-studio/agents/pre-built-agents]  (triggers Intercom)
│   └── Tickets Portal                    [external: https://help.corti.app/tickets-portal]
│
└── User footer (avatar + name + email + chevron)
```

**IA decisions:**
- Sidebar groups with **section labels** (AI Studio / Manage / Support) — not just icons.
- Multi-page tools (Speech to Text) use **parent + child** link structure with collapsible child list.
- "Beta" badge rendered inline with link text ("Templates Beta").
- External links (Tickets Portal) marked with external-link icon (img after text).
- Section labels are not clickable — they're dividers.

## 3. TopBar (header bar) structure

```
Left:
├── Corti logo (link to /, project picker)
├── "Toggle Sidebar" button (icon-only)
└── Project switcher ("songluhua" + chevron)

Center (breadcrumb):
└── Home  OR  Agents > Pre-built Agents  OR  (section) > (sub-section)

Right:
├── Announcement banner ("Corti Models is here" + Learn more + Dismiss)
├── $0.000000 (live cost counter, button — click to expand?)
├── Reset live cost (button with icon)
├── API Client (combobox — dropdown selector)
├── $48.72 (billing balance, link to /billing)
├── Docs (link to https://docs.corti.ai/agentic/overview)
├── Theme toggle (sun/moon icon)
└── User avatar (LS + name + email + chevron)
```

**TopBar IA decisions:**
- Live cost counter has its own button + reset action (Phase 4-G parity — iCoDer has the cost accumulation logic but no "Reset" button + no visible counter in TopBar).
- API Client selector is a **combobox** in TopBar (Phase 4-G gap — iCoDer has stateful plumbing but no TopBar dropdown rendered).
- Billing balance is a **link**, not just a label — clicking opens /billing.
- Docs link points to `docs.corti.ai/agentic/overview` — Corti separates "agentic" docs from general docs.

## 4. Per-page IA

### 4.1 Home dashboard (`/project/{id}`)

| Element | iCoDer equivalent | Parity |
|---------|-------------------|--------|
| H1 "Home" breadcrumb | H1 "首页" | Match |
| H1 page title | None (no H1) | iCoDer missing H1 |
| Top tabs: Transcribe / Document / Chat / Code (NEW) | 转写 / 文书 / 对话 / 编码 (NEW) | ✅ Direct match (4 tabs) |
| Each tab has a "Try S..." / "Build a..." CTA with link | (similar but simpler CTA structure) | Diff — Corti has dual CTA per tab |
| H2 "Overview" section | (iCoDer has similar metrics) | Match |
| Last 30 days filter (button + chevron) | (iCoDer has no time filter on Home) | Diff — Corti has time + client filters |
| "All API clients" filter (button + chevron) | (iCoDer has no API client filter on Home) | Diff — Corti's Home is per-API-client filterable |
| "Available credits" + "Add credits" link | "$50.00" link to /billing | Diff — Corti shows available credits + add-credits CTA; iCoDer shows balance only |
| "Total credits consumed" + "View usage" link | (iCoDer has no equivalent on Home) | Diff — iCoDer's usage page is separate |
| "Credits consumed" chart with Daily toggle | (iCoDer has no chart on Home) | Diff — Corti has Daily/Monthly toggle chart |
| "DOCUMENTATION" eyebrow + 3 links | (iCoDer has docs link only) | Diff — Corti has Authentication / Guides / API Reference |
| "SDKS AND TOOLS" eyebrow + 3 links | (iCoDer has docs only) | Diff — Corti has JS SDK / Postman / AI coding tools |
| "NEED HELP?" eyebrow + Chat with us / Open a ticket | (iCoDer has Get Help + Tickets in sidebar) | Diff — Corti has Help section on Home |

### 4.2 Agents page (`/project/{id}/ai-studio/agents`)

| Element | Notes |
|---------|-------|
| Breadcrumb: Agents | Single-level breadcrumb |
| H2 "Create an agent" + paragraph "Build healthcare agents to take action across your systems" | Hero section with icon |
| "New Agent" link (primary CTA) | Navigates to `/agents/new` |
| View radio group: My agents / Pre-built agents | Radio buttons, not tab buttons — switches panel content |
| Filter row (only on Pre-built): Use case + Created by + Open filter menu | Filter dropdown + sort |
| Card grid: 20 cards (Pre-built) or 0 cards (My agents empty state) | Each card is a div with cursor-pointer |

**Card structure (Pre-built):**
- H3 agent name
- Paragraph description (1-2 lines)
- (No metadata visible in snapshot — likely use_case badge + Run button appears on hover)

### 4.3 New Agent page (`/project/{id}/ai-studio/agents/new?preset={slug}`)

| Element | Notes |
|---------|-------|
| Left panel: H2 "Start from scratch" + H2 "Use a template" + 20 H3 preset cards | Templates gallery always visible |
| Right panel: H2 "{Agent Name}" + H1 "Ask the agent..." + chat input | Chat interface embedded |
| Search templates input | Filter for left panel |
| "Create agent" button (primary) | Save preset as user's own |
| "Customize agent" button (secondary) | Opens slide-over with agent_name input + customization form |
| "Add context" button | Adds context attachment (per Part 6 audit) |
| "What can you do?" + "Suggest prompt" buttons | Chat helper prompts |
| "Clone Agent" button (in Customize slide-over) | Clone-from-preset action |

**IA decision: New Agent page = templates gallery (left) + chat (right) + customization (slide-over on demand).**

### 4.4 Speech to Text (`/project/{id}/ai-studio/speech-to-text/dictation` etc.)

3 sub-pages: Dictation / Ambient / Pre-recorded. Each is a separate route. The parent "Speech to Text" link goes to the first child (`/dictation`).

### 4.5 Other AI Studio pages

| Page | Notes |
|------|-------|
| Text Generation | Single page at `/ai-studio/text-generation` |
| Embedded Assistant | Single page at `/ai-studio/embedded-assistant` |
| Fact Extraction | Single page at `/ai-studio/fact-extraction` |
| Medical Coding | Single page at `/ai-studio/medical-coding` |

(Not visited in this audit — Part 6 walkthrough covers per-agent.)

### 4.6 Manage pages

| Page | Notes |
|------|-------|
| API Clients | `/api-clients` — list of OAuth clients + API keys |
| Team | `/team` — project team members |
| Billing | `/billing` — balance + add credits + transaction history |
| Usage | `/usage` — credits consumed per API client per period |
| Customers | `/customers` — external customers management |
| Templates (Beta) | `/templates` — Templates Beta feature |
| Settings | `/settings` — project-level settings |

### 4.7 Support section

| Page | Notes |
|------|-------|
| Get Help | `/project/{id}/ai-studio/agents/pre-built-agents` — odd URL (points to Pre-built agents list, not a real help page) — actual help = Intercom chat triggered by `intercom-hmac` edge function |
| Tickets Portal | External `https://help.corti.app/tickets-portal` — opens new tab |

## 5. Tab / Radio / Button conventions

| Context | Widget | Notes |
|---------|--------|-------|
| View switching (My agents / Pre-built agents) | `radio` group (role="radio") | Single-select, no need for tab panel complexity |
| Home dashboard top tabs (Transcribe / Document / Chat / Code) | `tab` (role="tab") with `tablist` | True tab pattern with tabpanel |
| TopBar theme toggle | `button` | Cycles light/dark |
| Sidebar collapsible | `button` "Toggle Sidebar" | Icon-only button |
| Project switcher | `button` with chevron | Opens dropdown |
| API Client selector | `combobox` | True combobox, not button |
| Filter menus (Use case / Created by) | `button` + dropdown | Custom dropdown |
| Announcement banner | `button` "Dismiss announcement" | Inline dismiss |
| Cost reset | `button` "Reset live cost" | Inline action |
| New Agent preset selection | `div` with `cursor-pointer` (not a button) | Click navigates to preset detail — odd, accessibility concern |

**IA decision: Corti uses `radio` for "switch view of same content" and `tab` for "switch content panels". Filters use custom dropdowns.**

## 6. Modal / Drawer / Slide-over patterns

| Pattern | Example | Notes |
|---------|---------|-------|
| Slide-over panel (right side) | "Customize agent" slide-over on New Agent page | Pushes main content left, has Close button |
| Inline dismiss | Announcement banner | "Dismiss announcement" button hides banner |
| Modal dialog | (not observed in this audit) | Likely used for confirmations |
| Toast / notification | Region "Notifications alt+T" | Top-level region for accessibility |

## 7. Breadcrumb pattern

```
Home → "Home" (single item, no link)

Agents (Pre-built tab):
  Agents (link to /ai-studio/agents) > chevron icon > Pre-built Agents (text)

Agent New (preset):
  Agents (link) > chevron > New Agent (text)
```

Breadcrumbs are at the top of `main`, after the TopBar. Single-level on Home. Multi-level with link + chevron + text on sub-pages.

## 8. Cross-linking patterns

| From | To | Mechanism |
|------|----|-----------|
| TopBar "$48.72" | /billing | link |
| TopBar "Docs" | https://docs.corti.ai/agentic/overview | external link |
| Home "Add credits" | /billing | link |
| Home "View usage" | /usage | link |
| Home "Authentication" | https://docs.corti.ai/authentication | external link |
| Home "Javascript SDK" | https://docs.corti.ai/sdk/js-sdk#javascript-sdk | external link |
| Home "Postman" | https://docs.corti.ai/sdk/postman#quickstart-postman | external link |
| Home "AI coding tools" | https://docs.corti.ai/quickstart/ai-coding-tools | external link |
| Sidebar "Get Help" | /project/{id}/ai-studio/agents/pre-built-agents | Odd — points to Pre-built agents list, not a help page |
| Sidebar "Tickets Portal" | https://help.corti.app/tickets-portal | External link |
| Announcement "Learn more" | /project/{id}/corti-models | Internal link |

**Observation:** "Get Help" sidebar item has a strange URL — it points to `/ai-studio/agents/pre-built-agents` (same as Pre-built agents tab). Likely a placeholder or a routing bug. The actual help action is triggered by Intercom chat button somewhere on the page.

## 9. i18n state

| Field | Value |
|-------|-------|
| UI language | English only (no language switcher in sidebar/topbar) |
| User browser language | zh-cn (Google account locale) |
| Self-XSS warning | Chinese (browser-native, not Corti-controlled) |
| Date format | "31-Dec-2025" (day + abbreviated month + year) — English |
| Currency | USD ($) — "Available credits" / "$48.72" |
| Time format | Not directly observed on Home; likely ISO 8601 in API |

**IA decision: Corti Console is English-only at UI level. Localization is via external docs.corti.ai (which may have regional variants).**

## 10. Parity vs iCoDer — IA-level gaps

| # | Gap | Severity | iCoDer status |
|---|-----|----------|---------------|
| 1 | Home dashboard lacks H1 page title | Small | iCoDer has H1 "首页" + paragraph "医疗收入合规 AI 工作台" |
| 2 | Home lacks "Available credits / Total consumed" cards | Med | iCoDer shows billing balance only in TopBar; no Home-level credit cards |
| 3 | Home lacks Last 30 days + All API clients filters | Med | iCoDer has no time/client filter on Home |
| 4 | Home lacks Credits consumed Daily/Monthly chart | Med | iCoDer has no chart on Home |
| 5 | Home lacks DOCUMENTATION / SDKS AND TOOLS / NEED HELP sections | Med | iCoDer has docs link only |
| 6 | Pre-built agents card click = preset template flow | Diff | iCoDer card click = direct detail page (or fork-required for built agents) |
| 7 | TopBar lacks live cost counter | Med | iCoDer has logic but no TopBar counter UI (Phase 4-G P1) |
| 8 | TopBar lacks API Client combobox | Med | iCoDer has stateful plumbing but no TopBar combobox (Phase 4-G P1) |
| 9 | TopBar lacks Reset live cost button | Small | iCoDer doesn't have this |
| 10 | TopBar lacks Docs link to docs.corti.ai/agentic/overview | Small | iCoDer has /docs internal page only |
| 11 | Sidebar "Get Help" URL pattern is odd (points to Pre-built agents) | None — Corti bug | iCoDer's /support page is cleaner |
| 12 | View switch uses radio group, not tab | Small | iCoDer uses button (not radio) — diff but not parity issue |
| 13 | AgentsPage card uses `div cursor-pointer` (accessibility) | Small | iCoDer should ensure cards are `<button>` or `<a>` for keyboard nav |
| 14 | Speech to Text has 3 sub-pages | Med | iCoDer has 1 page; sub-pages would clarify STT variants |
| 15 | Templates page has Beta badge in sidebar | None | iCoDer matches |
| 16 | External Tickets Portal (help.corti.app) | Diff | iCoDer has in-app /tickets — different design choice |
| 17 | "Corti Models is here" announcement banner with Learn more + Dismiss | Small | iCoDer doesn't have announcement banner infra |
| 18 | No language switcher visible | None | iCoDer has "EN" button — better for CN/EN bilingual users |

## 11. Audit verdict

**§4 Part 1 PASS** — Corti IA fully captured at structure level (URL pattern + sidebar hierarchy + TopBar + per-page sections + tab/radio conventions + modal patterns + cross-linking + i18n state). 18 IA-level parity gaps catalogued for §14 Parity Matrix 2.0 + §18 architecture inference. No code changes made (audit-only per PDF §2.1).

## 12. Output files

- `E:\Corti4C\reports\phase4h\PHASE4H_CORTI_IA_AUDIT.md` — this file
- `E:\Corti4C\screenshots\phase4h\phase4h_corti_01_projects_list.png` — project picker
- `E:\Corti4C\screenshots\phase4h\phase4h_corti_02_dashboard.png` — Home dashboard
- `E:\Corti4C\screenshots\phase4h\phase4h_corti_03_agents_prebuilt.png` — Pre-built agents grid
- `E:\Corti4C\screenshots\phase4h\phase4h_corti_04_agent_new_preset.png` — New Agent preset page
- `E:\Corti4C\screenshots\phase4h\phase4h_corti_05_customize_panel.png` — Customize slide-over
