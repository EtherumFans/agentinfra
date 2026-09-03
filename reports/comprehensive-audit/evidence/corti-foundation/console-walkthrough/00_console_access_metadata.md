# Corti Console Walkthrough — Access Metadata

| Field | Value |
|-------|-------|
| Access date | 2026-07-16 |
| Access scope | Full Console (authenticated) |
| Tenant user | Luhua Song <songluhua@gmail.com> |
| Username slug | songluhua-7ff972 |
| Project ID | `4c4193c7-c6bb-4a71-a275-0ed6c53172d0` |
| Project URL | `https://console.corti.app/project/4c4193c7-c6bb-4a71-a275-0ed6c53172d0` |
| Console host | `console.corti.app` |
| Credits at access | $37.52 available / $6.84 consumed |
| Region (inferred) | EU (Corti Models banner: "hosted by Corti on European infrastructure") |
| Auth provider | Keycloak (per prior memory: `sessionStorage["access-token:PROJECT:CLIENT.data"]`) |
| Login mechanism | Email + password (Corti ID) — user completed login manually before session |

## Promotion impact

Before this Console walkthrough, the following evidence items in `26A_CORTI_OFFICIAL_EVIDENCE_CATALOG.md` were marked `NOT_VERIFIED` per spec §4.3. With Console access granted, they are eligible for promotion to `VERIFIED_CONSOLE`:

- Agent CRUD operations (create / read / update / delete)
- Agent Card live schema
- Orchestrator runtime behavior (during agent run)
- Context and Memory live view
- A2A Client management
- Authentication flow (API Client credentials)
- SDK runtime introspection (via Console network calls)
- Speech to Text / Text Generation / Fact Extraction / Medical Coding live surfaces
- Usage metering granularity
- Billing "Add credits" actual payment processor

## Capture plan (in order)

1. Home / Overview — topology, navigation, IA
2. Agents list — registry, default agents, CRUD UI
3. Agent detail — Card schema, capabilities, expert binding, runs, traces
4. Medical Coding — ICD-10 variant verification
5. Embedded Assistant — widget bootstrap, code generators
6. API Clients — auth model, client_secret surface
7. Usage — metering dimensions
8. Billing — Add credits payment processor verification

Each capture saves: snapshot YAML, screenshot PNG, key network requests, and a per-page markdown evidence summary.
