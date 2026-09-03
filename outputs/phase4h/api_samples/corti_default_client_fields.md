# Corti API Client — Default Client Fields (no Secret plaintext)

Source: Corti Console > Manage > API Clients > Default clients > Default client (EU Region, Client credentials)
URL: https://console.corti.app/project/b8f8129a-c31d-407f-b723-6ecc592d31e4/api-clients/default-clients

## Per PDF §10.1 — DO NOT record or output Secret plaintext

The following fields were observed in the expanded Default client panel. Per audit PDF §10.1 step 5 ("不记录或输出 Secret 原文"), the Client Secret is NOT captured in this file — only the masked form (first 4 chars + dots) is recorded.

## Captured fields

| Field | Value (sanitized) | Source |
|---|---|---|
| Client display name | "Default client" | h3 in expanded panel |
| Client ID (slug format) | `songluhua-default_client` | code/mono element in panel |
| Client Secret (masked) | `tFV5••••••••••••••••` | code/mono element in panel (default masked state) |
| Region | EU Region | heading "Default client EU Region Client credentials" |
| Authentication method | Client credentials | heading + subheading |
| Tenant name | (visible in panel — value not captured here to avoid PII) | label "Tenant name" + Copy button |
| Environment ID | (visible in panel — value not captured here) | label "Environment ID" + Copy button |
| Billing balance | $48.69 | breadcrumb link |

## Action buttons (per aria-label)

| Button aria-label | Purpose | Per §10.1 question |
|---|---|---|
| "Copy Client ID" | Copy Client ID to clipboard | — |
| "Regenerate client secret" | Rotate the secret (new secret generated, old invalidated) | #7 判断是否可轮换 → **YES** |
| "Show client secret" | Reveal the masked secret as plaintext | #6 判断 Secret 是否只显示一次 → **NO, shown on-demand (reveals when clicked, NOT one-time-only at creation)** |
| "Copy client secret" | Copy secret to clipboard (works when shown) | — |
| "Copy environment ID" | Copy env ID | — |
| "Copy Tenant name" | Copy tenant name | — |
| "Copy all as .env variables" (visible button) | Export all credentials as `.env` format | — |

## Per-§10.1 question answers

| # | Question | Answer | Evidence |
|---|---|---|---|
| 1 | Find API Client page | YES — `/api-clients` under Manage nav | URL captured |
| 2 | Create test Client | NOT EXECUTED (audit account is read-only-friendly; dialog captured at `phase4h_corti_12_create_api_client_dialog.png`) | Screenshot |
| 3 | Configurable fields | Client display name + How will this client be used? (Direct API access / Embedded Assistant) + Authentication method (Client credentials, locked) + Region (US / EU) | Dialog fields |
| 4 | Auth method | **Client credentials** (OAuth2 flow for Direct API access) OR **ROPC (Resource Owner Password)** for Embedded Assistant | Two default clients observed |
| 5 | Record Client ID | `songluhua-default_client` (slug format: username + client-name) | Captured |
| 6 | Secret shown only once? | **NO** — secret is masked by default (`tFV5••••••••••••••••`), can be revealed on-demand via "Show client secret" button (re-masked after) | Action button |
| 7 | Rotatable? | **YES** — "Regenerate client secret" button present | Action button |
| 8 | Disableable? | **UNKNOWN** — no "Disable" or "Revoke" button observed on default client (default clients cannot be deleted per UI text: "Default clients are ready to use... They can't be deleted but you can create and configure more") | UI text |
| 9 | Has Scope? | **NO** — no per-Client scope field observed in panel or dialog | Not in dialog |
| 10 | Has Rate Limit? | **NO** — no per-Client rate-limit field observed | Not in dialog |
| 11 | Has Agent permissions? | **NO** — no per-Client Agent-RBAC field observed | Not in dialog |
| 12 | Org isolation? | **IMPLIED** via `tenantName` + `environmentId` (multi-tenant model: Environment → Tenant → API Client) | Captured fields |
| 13 | Has Usage? | **YES** — separate `/usage` page in left nav (not audited in detail) | Left nav snapshot |
| 14 | Has Cost Attribution? | **YES** — separate `/billing` page in left nav + per-run `Credits consumed: $X` footer in agent detail page + `$48.69` balance link in breadcrumb | Breadcrumb + §7.3.3 observation |

## Create API Client dialog fields (from screenshot phase4h_corti_12)

| Field | Type | Options / Default |
|---|---|---|
| Client display name | textbox | placeholder: "e.g. Production, Development, Testing" |
| Client ID | auto-generated (read-only) | prefix: `songluhua-` (username slug prefix) |
| How will this client be used? | radiogroup | **Direct API access** (default, checked) / Embedded Assistant |
| Authentication method | read-only display | "Client credentials" (auto-set based on use case selection) |
| Region | radiogroup | US Region / **EU Region** (default, checked) |

Plus descriptive text: "The selected region determines where your data is processed and stored. Choose the region closest to your users or aligned with your data residency requirements for optimal performance and compliance."

## iCoDer parity check

| Dimension | Corti | iCoDer (Phase 4-G) | Parity |
|---|---|---|---|
| API Client page exists | `/api-clients` | `/api-clients` (or equivalent) | MATCH |
| Two default client types | Client credentials + ROPC | Two types (backend-service + ROPC embedded) per CLAUDE.md | MATCH |
| Region selection | US / EU | EU / US / CN (iCoDer has CN region per CLAUDE.md) | **iCoDer ADVANTAGE** (CN region) |
| Client ID slug format | `username-clientname` | (per iCoDer impl) | TBD |
| Secret masking | first 4 chars + dots | (per iCoDer impl — likely matches) | TBD |
| Regenerate secret | YES | TBD | GAP if not implemented |
| Show secret on-demand | YES | TBD | GAP if not implemented |
| Copy all as .env | YES | TBD | GAP if not implemented |
| Per-Client scope | NO | NO | MATCH (both lack) |
| Per-Client rate limit | NO | NO | MATCH (both lack) |
| Per-Client Agent RBAC | NO | NO | MATCH (both lack) |
| Usage page | `/usage` | (per Phase 4-G memory: Cost counter + RunHistory) | **iCoDer ADVANTAGE (RunHistory)** |
| Billing page | `/billing` | (iCoDer has Cost counter in TopBar) | MATCH |
| Tenant/Env/Region model | Environment → Tenant → API Client | Environment (EU/US/CN) → Tenant (医院) → API Client | MATCH (per CLAUDE.md cloud architecture) |

## iCoDer Phase 5 recommendations

1. **P0_INTEGRATION — Verify iCoDer has Secret masking + Regenerate + Show-on-demand.** Match Corti's 4 action buttons (Copy ID / Regenerate / Show / Copy secret / Copy env ID / Copy tenant / Copy all as .env).
2. **P1_DEVELOPER — Add "Copy all as .env variables" button.** Convenience for backend-service integration.
3. **DO_NOT_COPY — Do NOT add per-Client scope / rate limit / Agent RBAC.** Corti doesn't have these either; both lack.
