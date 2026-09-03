# Phase 4-H §3.3 — Corti Browser Environment (Audit Record)

**Recorded:** 2026-07-10 14:28 local (06:28 UTC)
**Auditor:** Claude (Sonnet 4.5)
**Browser session:** Chrome 150.0.7871.101 via CDP on :9222 (dedicated user-data-dir at `C:/Users/huawei/AppData/Local/Google/Chrome/CDP-Profile`)
**Login method:** Google OAuth (user: songluhua@gmail.com, display: "Luhua Song", initials: "LS")
**Project selected:** "songluhua" (project_id: `b8f8129a-c31d-407f-b723-6ecc592d31e4`)

> **Audit-scoped record.** Per PDF §3.3, this document captures no secrets — no Cookie, Token, API key, JWT, or session value. All values below are public-derivable from page snapshot + DevTools Network panel observation.

---

## 1. Corti home URL

| Field | Value |
|-------|-------|
| Console SPA origin | `https://console.corti.app` |
| Project-scoped home | `https://console.corti.app/project/{project_id}` |
| Currently loaded URL | `https://console.corti.app/project/b8f8129a-c31d-407f-b723-6ecc592d31e4` |
| Sign-in entry | `https://console.corti.app/auth` (Google/GitHub/email) |
| Auth success redirect | `https://console.corti.app/auth/success?provider=google` |
| Project picker (root) | `https://console.corti.app/` (lists user's projects) |
| Page title pattern | `Console Home | Corti Console` (per-section suffix) |

## 2. Console entry

| Field | Value |
|-------|-------|
| Pre-login landing | `https://console.corti.app/auth` — "Welcome back / Log in to Corti Console" |
| Primary login methods | Continue with Google, Continue with GitHub, Email + Continue |
| Auth provider | Supabase GoTrue (sb-api-auth-token in localStorage) |
| OAuth callback | `https://api.console.corti.app/auth/v1/callback` (Authorization Code flow) |
| Post-login landing | Project picker at `/` — "Your Projects / Select a project to continue" |
| Project cards | 2 projects visible (both "Songluhua"; created 31-Dec-2025) |
| Project entry click | "Open Project" button → `/project/{project_id}` (Console Home) |

## 3. Current org / project

| Field | Value |
|-------|-------|
| Project name | `songluhua` |
| Project ID | `b8f8129a-c31d-407f-b723-6ecc592d31e4` |
| Project created | 31-Dec-2025 (visible on project card) |
| Secondary project | `4c4193c7-...` (also named "songluhua", same date) |
| Org model | Project-based (no separate "organization" entity — each project has its own API Clients / Team / Billing / Usage) |

## 4. Current role

| Field | Value |
|-------|-------|
| User display name | `Luhua Song` (from `/rest/v1/profiles?select=display_name`) |
| User email | `songluhua@gmail.com` |
| Corti user ID | `e2b1faae-5d7c-4340-b234-ea275761ece2` |
| Role determination | Backend calls `is_admin_user` + `is_limited_admin_user` RPC functions on every page load (observed in network panel) — role is server-side computed, not stored in JWT claim |
| Visible admin modules | All Manage modules accessible (API Clients, Team, Billing, Usage, Customers, Templates Beta, Settings) → implies project owner or admin role |
| Project membership | `/rest/v1/project_memberships?project_id=eq.{id}&user_id=eq.{user_id}` returns row → membership confirmed |

## 5. Accessible modules

**Sidebar IA (left rail):**

| Group | Module | URL path |
|-------|--------|----------|
| Top | Home | `/project/{id}` |
| Top | Developer quickstart | `/project/{id}/developer-quickstart` |
| AI Studio | Overview | `/project/{id}/ai-studio-overview` |
| AI Studio | Agents | `/project/{id}/ai-studio/agents` |
| AI Studio | Speech to Text → Dictation | `/project/{id}/ai-studio/speech-to-text/dictation` |
| AI Studio | Speech to Text → Ambient | `/project/{id}/ai-studio/speech-to-text/ambient` |
| AI Studio | Speech to Text → Pre-recorded | `/project/{id}/ai-studio/speech-to-text/pre-recorded` |
| AI Studio | Text Generation | `/project/{id}/ai-studio/text-generation` |
| AI Studio | Embedded Assistant | `/project/{id}/ai-studio/embedded-assistant` |
| AI Studio | Fact Extraction | `/project/{id}/ai-studio/fact-extraction` |
| AI Studio | Medical Coding | `/project/{id}/ai-studio/medical-coding` |
| Manage | API Clients | `/project/{id}/api-clients` |
| Manage | Team | `/project/{id}/team` |
| Manage | Billing | `/project/{id}/billing` |
| Manage | Usage | `/project/{id}/usage` |
| Manage | Customers | `/project/{id}/customers` |
| Manage | Templates (Beta) | `/project/{id}/templates` |
| Manage | Settings | `/project/{id}/settings` |
| Support | Get Help | `/project/{id}` (Intercom chat trigger) |
| Support | Tickets Portal | `https://help.corti.app/tickets-portal` (external) |

**Home dashboard top tabs:** `Transcribe | Document | Chat | Code (NEW)`

**Top bar (right side):** Theme toggle, Docs link (`https://docs.corti.ai/`), User profile dropdown

## 6. Language

| Field | Value |
|-------|-------|
| UI language | English (all labels in English) |
| User browser language | `zh-cn` (per Google Analytics `ul` param) |
| Google OAuth flow | `hl=zh-CN` (Chrome UI in Chinese) |
| Corti account email | `songluhua@gmail.com` |
| Self-XSS warning | Chinese ("警告！使用此控制台可能会导致攻击程序利用 Self-XSS...") — Chrome-native |
| Localized variants | Corti SPA appears to be English-only (no language switcher in sidebar/topbar visible) |

## 7. API domain

| Domain | Purpose | Examples |
|--------|---------|----------|
| `console.corti.app` | SPA frontend (React) | HTML/JS/CSS assets |
| `api.console.corti.app` | Supabase backend (GoTrue + PostgREST + Edge Functions) | `/auth/v1/user`, `/rest/v1/projects`, `/functions/v1/projects/{id}/billing/balance` |
| `api.eu.corti.app` | Region-prefixed runtime API (per prior memory, not exercised on dashboard) | `/v2/tools/coding`, `/v1/messages` (runtime calls) |
| `prp.corti.app` | PostHog analytics (feature flags + surveys + events) | `/flags/`, `/api/surveys/`, `/i/v0/e/`, `/s/` |
| `api-iam.intercom.io` | Intercom support messenger | `/messenger/web/ping`, `/messenger/web/metrics` |
| `help.corti.app` | Tickets portal (external helpdesk) | `/tickets-portal` |
| `docs.corti.ai` | Documentation site | `/authentication`, `/guides`, `/api-reference`, `/sdk/js-sdk`, `/sdk/postman`, `/quickstart/ai-coding-tools` |
| `consent.cookiebot.eu` | Cookie consent management (CMP) | `/consentconfig/{id}/settings.json` |
| `consentcdn.cookiebot.eu` | Cookie consent CDN | Same as above |
| `script.crazyegg.com` | Heatmaps/session recording | `/pages/data-scripts/...` |
| `www.google-analytics.com` / `analytics.google.com` | GA4 collect | `/g/collect?v=2&tid=G-Q902TDWF19...` |
| `pagead2.googlesyndication.com` / `ad.doubleclick.net` / `play.google.com/log` | Google Ads | Conversion tracking |
| `accounts.google.com` | Google OAuth (login only) | `/v3/signin/_/AccountsSignInUi/...` |

## 8. Auth/storage method

| Field | Value |
|-------|-------|
| Auth provider | Supabase GoTrue (v2.90.0 detected in console warning) |
| Storage key | `sb-api-auth-token` in `localStorage` (per GoTrue client warning) |
| Storage mechanism | `localStorage` (persisted across sessions) |
| Token model | JWT (HS256/RS256 — Supabase default) + refresh token |
| Login flow | OAuth Authorization Code → callback at `api.console.corti.app/auth/v1/callback` → swap code for session → GoTrue sets `sb-api-auth-token` |
| Auth validation | Frontend calls `/auth/v1/user` on every page load (observed 3× in trace) |
| Role validation | Backend RPCs `is_admin_user` + `is_limited_admin_user` called on every page transition (server-side role computation) |
| HMAC for Intercom | `/functions/v1/intercom-hmac` Edge Function computes HMAC of user ID for Intercom identity verification |
| Logout expectation | `localStorage.removeItem('sb-api-auth-token')` + `/auth/v1/logout` |
| Session refresh | GoTrue auto-refreshes JWT in background (Supabase SDK default) |

## 9. Multi-backend topology

```
┌─────────────────────────────────────────────────────────────────┐
│ Corti Console (browser)                                          │
│  https://console.corti.app  — React SPA                          │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ├─ Google OAuth ──> accounts.google.com (login only)
       │
       ├─ Auth + DB ───> api.console.corti.app (Supabase)
       │                   ├─ /auth/v1/* (GoTrue auth)
       │                   ├─ /rest/v1/* (PostgREST CRUD)
       │                   └─ /functions/v1/* (Edge Functions:
       │                       billing/balance, usage, onboarding,
       │                       intercom-hmac, ...)
       │
       ├─ Runtime API ─> api.eu.corti.app (region-prefixed)
       │                   (not exercised on dashboard; per prior
       │                    memory = /v2/tools/coding, /v1/messages)
       │
       ├─ Analytics ───> prp.corti.app (PostHog)
       │                   /flags/, /api/surveys/, /i/v0/e/, /s/
       │
       ├─ Support ────> api-iam.intercom.io (Intercom)
       │                help.corti.app (tickets portal)
       │
       ├─ Docs ───────> docs.corti.ai (separate docs domain)
       │
       ├─ Consent ────> consentcdn.cookiebot.eu + consent.cookiebot.eu
       │
       └─ 3rd-party ──> crazyegg.com (heatmaps)
                        google-analytics.com, doubleclick.net (Ads)
```

## 10. GraphQL vs REST

| Field | Value |
|-------|-------|
| Primary API style | **REST** (PostgREST) — `/rest/v1/{table}?select=...&{col}=eq.{val}` |
| RPC pattern | PostgREST RPC — `/rest/v1/rpc/{function_name}` (POST) |
| Auth API | Supabase GoTrue REST — `/auth/v1/*` |
| Server logic | Edge Functions (Deno-style) — `/functions/v1/{path}` |
| GraphQL | **Not observed** — no `/graphql` endpoint in network panel |
| WebSocket / SSE | **Not observed on dashboard** — only HTTP REST. (Runtime API on api.eu.corti.app may use SSE for streaming responses; not exercised here) |
| Realtime | Supabase Realtime (WSS) available but not active on dashboard |

## 11. Multi-region runtime API (per prior memory)

| Region | Domain | Confirmed in this audit? |
|--------|--------|--------------------------|
| EU | `api.eu.corti.app` | No (dashboard doesn't call runtime; only prior memory) |
| US | `api.us.corti.app` (presumed) | No |
| Console (global) | `api.console.corti.app` | **Yes** (Supabase backend, region-agnostic) |

**Note:** `api.console.corti.app` serves all regions for management-plane operations (auth, DB, edge functions). Region-prefixed `api.{region}.corti.app` serves runtime inference calls (per prior memory `project_corti_agent_architecture.md`).

## 12. Key observation — iCoDer parity gap candidates

Comparing this Corti environment record to iCoDer's current state (PHASE4H_BASELINE.md §2-§5):

| # | Capability | Corti | iCoDer | Parity gap |
|---|-------------|-------|--------|------------|
| 1 | Project picker | 2 projects, project-scoped URLs | Single org, no project picker | Med — iCoDer uses org/tenant not project; but Corti's "project = workspace" is simpler |
| 2 | Top-level tabs on Home | Transcribe / Document / Chat / Code (NEW) | (no equivalent; AIStudioOverview shows agents) | Small — Corti tabs hint at task-based entry, not feature-based |
| 3 | Sidebar IA | Home + Dev quickstart + AI Studio (7 items) + Manage (7 items) + Support (2 items) | Sidebar (240px) with AIStudio templates + Manage (Customers, Tickets, Usage, Templates) + RunTrace | Small — IA differs but covers similar surface |
| 4 | Theme toggle | Yes (dark/light) | Yes (theme store) | None |
| 5 | API Clients management | `/project/{id}/api-clients` | `/admin?tab=api_clients` | None — both have it |
| 6 | Billing + Usage | Both separate modules | `/admin?tab=billing` + `/admin?tab=usage` | None |
| 7 | Templates Beta | `/project/{id}/templates` (Beta badge) | `/ai-studio/templates` (Phase 3-B2 +) | None |
| 8 | Team | `/project/{id}/team` | (no equivalent — admin user list only) | Small — iCoDer doesn't have project-scoped team management |
| 9 | Tickets Portal | External `help.corti.app` | `/admin?tab=tickets` (in-app) | Diff — Corti uses external helpdesk, iCoDer in-app |
| 10 | Auth | Google + GitHub + Email (Supabase GoTrue) | Email/password only (JWT HS256) | Med — iCoDer lacks OAuth providers |
| 11 | Role check | Backend RPC `is_admin_user` / `is_limited_admin_user` per page | JWT claim `role=system_administrator` | Diff — Corti computes role server-side per request, iCoDer trusts JWT |
| 12 | Cookie consent | Cookiebot CMP | None | Small — GDPR consent not in iCoDer (CN-only deployment) |
| 13 | Heatmaps | Crazyegg | None | Small — not a parity concern |
| 14 | Feature flags | PostHog (`prp.corti.app`) | None | Small — not a parity concern |
| 15 | Intercom support | Intercom (with HMAC edge function for identity) | None | Small — not a parity concern |
| 16 | SDK docs | External `docs.corti.ai` (Authentication / Guides / API Reference / JS SDK / Postman / AI coding tools) | (in-repo docs only) | Med — iCoDer has no public docs site |

---

## 13. Audit scope reminder (carried from PDF §2.1)

Development is FROZEN during this audit. Findings above are record-only. Any code change must be:
- A separate commit
- Tagged `AUDIT_BLOCKER_FIX`
- Recorded with before/after evidence
- Not opportunistic refactoring
- Not Corti implementation copying

All non-blocking issues go to the diff backlog (Part 11 deliverable), not immediate development.
