# Phase 7 Gate 13A — Threat Model + Architecture

## Threat model (6 attack surfaces)

| # | Surface | Threat | Current (Gate 13) | After Gate 13A |
|---|---------|--------|-------------------|----------------|
| T1 | iframe URL → Browser history | Attacker with browser access reads JWT from history | JWT in `?token=` | No token in URL |
| T2 | iframe URL → HAR file | DevTools "Save all as HAR" leaks JWT + patient | Full URL in HAR | Only opaque `preview_session_id` |
| T3 | iframe URL → Backend access logs | SIEM aggregation persists patient name decoded | `patientName=%E5%BC%A0%E4%B8%89` in logs | No PHI in URL |
| T4 | iframe URL → Referer on sub-resource requests | Widget's fetch() sends full URL as Referer | JWT + patient in Referer | `Referrer-Policy: no-referrer` |
| T5 | postMessage wildcard | Malicious parent/iframe forges or sniffs events | `postMessage(..., '*')` both directions | `postMessage(..., expectedOrigin)` + origin/source/nonce verification |
| T6 | Code generator copy | CS engineer pastes snippet into Slack w/ real PHI | Real patient name in copied code | Placeholders only |

## Architecture: Preview Bootstrap Ticket + MessageChannel handshake

### Why a Ticket (not "just remove the token")

Removing the JWT from the URL leaves the iframe unable to authenticate. The widget must call `/api/v1/agents/{id}/run` etc., which require a bearer token. Three options:

1. **Cookie auth** — set a `HttpOnly; SameSite=Strict` session cookie on the parent domain, rely on browser sending it with iframe requests. **Reject**: the iframe is same-origin with the backend (served from `/api/embedded/preview.html`), but Console users and partner tenants may have different cookie scopes in cloud deploy. Also, this conflates Console session with iframe session.
2. **In-memory JWT passed via `postMessage`** — parent sends JWT to iframe via MessageChannel after handshake. **Reject**: the JWT has full Console scope (admin/api-clients/billing). A ticket with narrow scope (`agents:run` + `runs:read` + `traces:read` + `contexts:write`) is safer; if the iframe is ever compromised, the attacker gets run-only scope.
3. **Short-lived signed Ticket → exchanged for scoped Runtime Token via authenticated POST** — **Accept**. The ticket is single-use, 60s TTL, bound to (org, user, parent_origin, iframe_origin, nonce, agent_allowlist, scope). The iframe POSTs the ticket to `/api/embedded/preview-sessions/exchange` and receives a Runtime Token. The Runtime Token has the narrow scope and lives only in iframe JS memory.

### Data flow

```
┌─────────────────────────┐         ┌─────────────────────────┐
│  Console Parent (React) │         │  iCoDer Backend (FastAPI)│
│  EmbeddedAssistantPage  │         │                          │
│                         │  POST   │                          │
│  1. create session ─────┼────────►│  /api/embedded/preview-  │
│      (with Console JWT) │         │  sessions                │
│                         │  ◄──────┼  ← ticket (60s, signed)  │
│  2. set iframe.src =    │         │                          │
│     preview.html?psid=  │         │                          │
│     <opaque-id-only>    │         │                          │
│                         │         │                          │
│  3. wait for iframe     │         │                          │
│     ready event         │         │                          │
│                         │         │                          │
│  ┌───────────────────┐  │         │                          │
│  │ iframe (preview.  │  │         │                          │
│  │  html — served    │  │         │                          │
│  │  with strict CSP, │  │         │                          │
│  │  sandbox, no-store│  │         │                          │
│  │                   │  │         │                          │
│  │ 4. on load, send  │  │         │                          │
│  │    preview.ready  │  │         │                          │
│  │    via Message-   │  │         │                          │
│  │    Channel port   │  │         │                          │
│  └─────────┬─────────┘  │         │                          │
│            │            │         │                          │
│  5. verify origin/      │         │                          │
│     source/nonce,       │         │                          │
│     send ticket + nonce │         │                          │
│     + patient ctx via   │         │                          │
│     MessageChannel      │         │                          │
│            │            │         │                          │
│            ▼            │         │                          │
│  ┌───────────────────┐  │         │                          │
│  │ iframe:           │  │         │                          │
│  │  6. POST ticket   │──┼────────►│  /api/embedded/preview-  │
│  │     to exchange   │  │         │  sessions/exchange       │
│  │     for Runtime   │  │         │  → verify sig + exp +    │
│  │     Token         │◄─┼─────────│  nonce + origin match    │
│  │                   │  │         │  → return Runtime Token   │
│  │  7. widget.auth() │  │         │  → mark ticket USED      │
│  │     configureSes- │  │         │                          │
│  │     sion(ctx)     │  │         │                          │
│  │     configure()   │  │         │                          │
│  │     show()        │  │         │                          │
│  │                   │  │         │                          │
│  │  8. embedded-event│  │         │                          │
│  │     back via port │  │         │                          │
│  └───────────────────┘  │         │                          │
└─────────────────────────┘         └──────────────────────────┘
```

### Key design decisions

1. **Ticket TTL = 60 seconds, single-use**. The Console creates the session on page mount; the iframe exchanges within 60s. After exchange, the ticket is marked USED in the DB and cannot be replayed.
2. **Runtime Token TTL = 10 minutes, refreshable**. Scoped to `agents:run runs:read traces:read contexts:write`. Lives in iframe JS memory only — never written to storage.
3. **MessageChannel, not window.postMessage** — MessageChannel gives a private port between parent and iframe that can't be intercepted by other frames. The handshake establishes a port with a known nonce; subsequent messages use the port directly with `targetOrigin` set to the agreed value.
4. **Strict origin verification on every message** — both parent and iframe enforce `event.origin === EXPECTED_ORIGIN` AND `event.source === iframeRef.current?.contentWindow` (parent) or `event.source === window.parent` (iframe).
5. **preview_session_id in URL is opaque** — it's a random UUID, not the JWT. The DB row maps it to org/user but the URL itself reveals nothing.
6. **Patient context flows via MessageChannel, never URL** — the parent sends `{previewSessionId, nonce, context: {patientId, patientName, encounterId}}` via the secured port. The iframe verifies the nonce before accepting.

### Scope: what Gate 13A does NOT change

- The widget Web Component itself (`packages/icoder-embedded/src/icoder-assistant.ts`) — its public API (`auth/configureSession/configure/show`) is unchanged. Gate 13A only changes how the **Preview Console page** bootstraps the widget.
- Partner reference app at `examples/partner-reference-app/` — partners use `client_credentials` directly, no preview ticket needed.
- The 3 demos at `/examples/{medical-coding,cdi,drg-dip}/` — they're for partner evaluation and already use server-side token exchange.
- Phase 7 Gates 1-12 — all backend infrastructure (Idempotency, RunHistory, TraceToken, etc.) is reused as-is.

## Hardening checklist (mapped to Checkpoints A-F)

| Checkpoint | What | How |
|------------|------|-----|
| A — No sensitive URL | Remove token/PHI from iframe URL | Ticket + MessageChannel |
| B — Strict origin messaging | Replace `'*'` with handshake | MessageChannel + origin verify |
| C — One-time ticket | Single-use signed ticket + DB row | HMAC + DB unique constraint |
| D — Injection & embedding | CSP + sandbox + frame-ancestors + no-store + no-referrer | Response headers + iframe attrs |
| E — Patient A/B isolation | DOM/state/network/storage audit per switch | clearPatientContext + PostMessage ack |
| F — No functional regression | Gate 13 still works | Re-run Gate 13 walkthrough + Phase 7 |

## Verdict target

`PASS_GATE13A_EMBEDDED_PREVIEW_SECURITY_HARDENED` — all 6 checkpoints closed, no regression, no token/PHI in URL/HAR/Referer/logs.

Forbidden verdicts (per PDF §1.4): `PRODUCTION_READY`, `HOSPITAL_DEPLOYMENT_READY`, `PARTNER_PRODUCTION_READY`, `CORTI_FULL_PARITY`, `SECURITY_CERTIFIED`.
