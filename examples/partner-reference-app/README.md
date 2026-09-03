# iCoDer Partner Reference App

> Phase 7 Gate 12 — minimal HIS/EMR integration example partners can clone,
> configure, and run in under 5 minutes.

This reference app shows the **canonical pattern** for embedding iCoDer into
a partner HIS/EMR system. It is deliberately tiny (~200 LOC server + ~150 LOC
HTML) so partners can read every line and understand what iCoDer expects from
their backend.

## What this app demonstrates

1. **Server-side secret holding** — `ICODER_API_CLIENT_SECRET` lives only in
   the partner's Node process. The browser never sees it.
2. **Server-side token exchange** — partner backend exchanges
   `client_credentials` for a short-lived access_token at the iCoDer token
   endpoint. Token is then passed to the browser widget.
3. **Embedded widget** — browser loads `<icoder-embedded>` from iCoDer's
   `/api/embedded/assistant.js` (CDN-hosted in production, served locally in
   dev), configures it with the token + patient context, and renders the chat.
4. **Patient context isolation** — switching patients calls
   `clearPatientContext()` first, so no PHI bleed (Phase 6 Gate 2 / Phase 7
   Gate 11).
5. **Unified event handling** — single `embedded-event` listener routes
   `run.completed`, `account.creditsConsumed`, `error.triggered`, etc.
6. **Trace URL access** — partner-side audit uses the signed trace_url from
   Gate 7 to deep-link into run details without requiring Console cookies.

## Quick start

```bash
# 1. Copy and edit env
cp .env.example .env
# fill in ICODER_API_CLIENT_ID + ICODER_API_CLIENT_SECRET (Gate 5 issues these)

# 2. Install + run
npm install
npm start

# 3. Open in browser
open http://localhost:4400
```

If you don't yet have API Client credentials, you can still run the app by
pasting a Console JWT into the access-token field — the widget falls through
to Console JWT mode (Phase 6 Gate 1 §6.2 backwards compatibility).

## Project structure

```
partner-reference-app/
├── .env.example         # ICODER_* env vars (copy to .env, fill in)
├── package.json         # express + node >= 18, no other deps
├── README.md            # this file
├── server/
│   └── index.mjs        # express app: /token (exchange), /* (static)
└── public/
    ├── index.html       # HIS/EMR shell + <icoder-embedded>
    └── app.js           # widget bootstrap, event handling, patient switching
```

## Why a server at all?

Per Phase 7 §6.3, the API client secret **MUST NOT** ship to the browser. The
only safe way to use `client_credentials` is for the partner to run a small
backend that holds the secret, exchanges it for short-lived tokens, and
passes the tokens down. This reference app shows the minimum viable backend.

For local dev against this repo's backend, you can skip the secret flow
entirely and use a Console JWT directly (the widget accepts either).

## Endpoints

| Route | Purpose |
|-------|---------|
| `GET  /`           | HIS/EMR shell with embedded widget |
| `GET  /token`      | Server-side `client_credentials` exchange → `{access_token, expires_in}` |
| `GET  /healthz`    | Liveness probe |

## Security checklist

- [x] Secret stays server-side (`ICODER_API_CLIENT_SECRET` never in browser)
- [x] Widget served from iCoDer's `/api/embedded/assistant.js` (CDN in prod)
- [x] CSP `default-src 'self'` allows only the partner origin + iCoDer origin
- [x] Patient PHI in-memory only; `clearPatientContext()` on patient switch
- [x] Trace URL signed (Gate 7 HMAC); partner doesn't need Console cookies
- [x] CORS allowlist on iCoDer side rejects unknown origins (Gate 6)

## What this app deliberately does NOT do

- No real HIS/EMR integration (it's a static shell — partners wire their own)
- No DB / persistence — every page load is fresh
- No production hardening (no rate limiting, logging, metrics) — partners add
  these per their org policy

## License

Apache-2.0 (same as `@icoder/embedded`)
