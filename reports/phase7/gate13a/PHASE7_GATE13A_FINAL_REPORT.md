# Phase 7 Gate 13A — Embedded Preview Security Hardening (FINAL)

**Verdict**: `PASS_GATE13A_EMBEDDED_PREVIEW_SECURITY_HARDENED`
**Date**: 2026-07-15
**Gates**: 13A-0 through 13A-10 (all 11 closed)
**Hardening Checkpoints**: A, B, C, D, E, F (all 6 closed)
**Tests**: 48 new + 78 Phase 7 regression = 126 PASS
**Browser E2E**: real DeepSeek session via Runtime Token ✓

---

## What Gate 13A closes

Phase 7 Gate 13 shipped a Corti-parity Embedded Assistant Console page, but
the iframe URL still leaked the JWT and patient PHI:

```
/api/embedded/preview.html?token=eyJ...&patientName=%E5%BC%A0%E4%B8%89&patientId=P-2026-001&...
```

That URL hit four attack surfaces enumerated in the threat model:

- **T1 — browser history**: JWT readable from `history.state` / back button
- **T2 — HAR file**: DevTools "Save all as HAR" leaked JWT + patient name
- **T3 — backend access logs**: SIEM aggregation persisted URL-decoded PHI
- **T4 — Referer on sub-resource requests**: widget `fetch()` sent full
  URL (incl. JWT + PHI) as `Referer` to the backend
- **T5 — postMessage wildcard**: `postMessage(..., '*')` both directions
  let any frame forge events
- **T6 — code generator copy**: CS engineer copy-pasted real patient
  PHI into Slack when sharing the snippet

Gate 13A replaces all of this with a **short-lived HMAC-signed Bootstrap
Ticket + MessageChannel handshake**.

---

## Architecture

```
┌─────────────────────────┐         ┌─────────────────────────┐
│  Console Parent (React) │         │  iCoDer Backend (FastAPI)│
│  EmbeddedAssistantPage  │         │                          │
│                         │  POST   │                          │
│  1. create session ─────┼────────►│  /api/embedded/preview-  │
│      (with Console JWT) │         │  sessions                │
│                         │  ◄──────┼  ← ticket (60s, signed)  │
│  2. set iframe.src =    │         │  ← preview_session_id    │
│     preview.html?psid=  │         │                          │
│     <opaque-id-only>    │         │                          │
│                         │         │                          │
│  3. iframe loads; opens │         │                          │
│     MessageChannel port │         │                          │
│     ─ open-port msg ───►│         │                          │
│                         │         │                          │
│  4. iframe sends        │         │                          │
│     ready-ping {psid}   │         │                          │
│     ◄───────────────────│         │                          │
│                         │         │                          │
│  5. parent verifies     │         │                          │
│     psid match, sends   │         │                          │
│     bootstrap {ticket,  │         │                          │
│     nonce, context} ───►│         │                          │
│                         │         │                          │
│                         │         │                          │
│  ┌───────────────────┐  │         │                          │
│  │ iframe:           │  │         │                          │
│  │  6. POST ticket ──┼──────────►│  /api/embedded/preview-  │
│  │     to exchange   │  │         │  sessions/exchange       │
│  │                   │◄─┼─────────│  → verify HMAC + exp +   │
│  │  7. widget.auth() │  │         │    origin + nonce match  │
│  │     configureSes- │  │         │  → return Runtime Token  │
│  │     sion(ctx)     │  │         │  → mark ticket USED      │
│  │     configure()   │  │         │                          │
│  │     show()        │  │         │                          │
│  │                   │  │         │                          │
│  │  8. embedded-event│  │         │                          │
│  │     back via port │  │         │                          │
│  └───────────────────┘  │         │                          │
└─────────────────────────┘         └──────────────────────────┘
```

Key design decisions:

1. **Ticket TTL = 60 seconds, single-use.** Console creates on page mount;
   iframe exchanges within 60s; replay after exchange → `TICKET_ALREADY_USED`.
2. **Runtime Token TTL = 10 minutes.** Scoped to `agents:run runs:read
   traces:read contexts:write`. Lives in iframe JS memory only.
3. **MessageChannel, not `postMessage('*')`.** Private port between parent
   and iframe that can't be intercepted by other frames.
4. **`preview_session_id` in URL is opaque** (32-char random), not the JWT.
5. **Patient context flows via MessageChannel**, never URL.
6. **HMAC-SHA256 domain-separated key** — preview_ticket's key has
   `b"icoder-preview-ticket|"` prefix so it can't cross-use with trace_token.

---

## Gate-by-gate status

| Gate | Description | Status | Evidence |
|------|-------------|--------|----------|
| 13A-0 | Baseline re-audit | ✓ | `PHASE7_GATE13A_BASELINE.md` |
| 13A | Threat model | ✓ | `PHASE7_GATE13A_THREAT_MODEL.md` |
| 13A-1 | Preview Session/Ticket API | ✓ | 4 endpoints, alembic 015, 32 tests |
| 13A-2/3 | iframe Bootstrap + MessageChannel | ✓ | preview.html rewritten, 9 tests |
| 13A-4 | Frontend Console handshake | ✓ | `EmbeddedAssistantPage.tsx` rewritten, tsc clean |
| 13A-5 | CSP/sandbox/cache headers | ✓ | nonce'd CSP + sandbox + no-store + no-referrer |
| 13A-6 | XSS hardening | ✓ | psid alphanumeric-only; 9 tests |
| 13A-7 | Code generator credential safety | ✓ | all 3 generators use placeholders |
| 13A-8 | Audit log + PHI leak audit | ✓ | 7 tests; no PHI in URL/body/DB/audit |
| 13A-9 | Browser E2E + negative tests | ✓ | Playwright MCP — widget reaches "interactive" |
| 13A-10 | Regression | ✓ | 48 new + 78 Phase 7 = 126 PASS; tsc clean |

---

## Hardening checklist (Checkpoints A-F)

| Checkpoint | What | How | Verified |
|------------|------|-----|----------|
| **A — No sensitive URL** | Remove token/PHI from iframe URL | Ticket + MessageChannel | `test_preview_html_only_reads_psid`; iframe URL `?psid=` only |
| **B — Strict origin messaging** | Replace `'*'` with handshake | MessageChannel + source check | `test_preview_html_no_wildcard_postmessage`; iframe `ev.source !== window.parent` |
| **C — One-time ticket** | Single-use signed ticket + DB row | HMAC + DB unique constraint + atomic PENDING→EXCHANGED | `test_replay_after_exchange_returns_410` |
| **D — Injection & embedding** | CSP + sandbox + frame-ancestors + no-store + no-referrer | Response headers + iframe attrs | `test_preview_html_has_csp_header`, `test_preview_html_has_sandbox_header`, `test_preview_html_has_no_store_header`, `test_preview_html_has_no_referrer_header` |
| **E — Patient A/B isolation** | PHI never in URL/DB, only in iframe memory | No `patient_*` columns on preview_sessions | `test_db_row_does_not_contain_phi` |
| **F — No functional regression** | Gate 13 still works | Phase 7 regression suite | 78/78 PASS |

---

## Forbidden verdicts (per PDF §1.4)

The following verdicts are explicitly forbidden and NOT claimed:

- `PRODUCTION_READY`
- `HOSPITAL_DEPLOYMENT_READY`
- `PARTNER_PRODUCTION_READY`
- `CORTI_FULL_PARITY`
- `SECURITY_CERTIFIED`

The allowed final verdict for this gate is **`PASS_GATE13A_EMBEDDED_PREVIEW_SECURITY_HARDENED`**.

---

## Files changed

### Backend (new)
- `app/models/preview_session.py` — PreviewSession ORM model
- `app/api/preview_sessions.py` — 4 endpoints (create/exchange/status/revoke)
- `app/services/preview_ticket.py` — HMAC ticket + Runtime Token service
- `alembic/versions/015_preview_sessions.py` — schema migration
- `tests/unit/app/services/test_phase7_gate13a_preview_ticket.py` — 18 tests
- `tests/unit/app/api/test_phase7_gate13a_preview_sessions.py` — 14 tests
- `tests/unit/app/api/test_phase7_gate13a_preview_html.py` — 9 tests
- `tests/unit/app/api/test_phase7_gate13a_audit.py` — 7 tests

### Backend (modified)
- `app/api/embedded.py` — `/api/embedded/preview.html` rewritten with
  MessageChannel handshake, CSP nonce, sandbox, no-store, no-referrer
- `app/main.py` — wire `preview_sessions_router`

### Frontend (modified)
- `src/pages/EmbeddedAssistantPage.tsx` — fully rewritten Console side:
  - mint ticket via POST `/api/embedded/preview-sessions`
  - iframe URL is `?psid=<opaque>` only
  - MessageChannel handshake on iframe load
  - patient context flows via port, never URL
  - code generators use placeholders (no real patient)

### Docs
- `reports/phase7/gate13a/PHASE7_GATE13A_BASELINE.md`
- `reports/phase7/gate13a/PHASE7_GATE13A_THREAT_MODEL.md`
- `reports/phase7/gate13a/PHASE7_GATE13A_FINAL_REPORT.md` (this file)
- `docs/corti_parity/phase7_gate13a/e2e_widget_interactive.png` (browser screenshot)

---

## Browser E2E trace (Playwright MCP)

1. ✅ Console login → JWT in localStorage
2. ✅ Visit `/ai-studio/embedded-assistant`
3. ✅ Console POST `/api/embedded/preview-sessions` → 201 Created, ticket + psid returned
4. ✅ iframe loads `?psid=vQtaZBRGAuj4djIXyTja80BgUQBo5pUY` (no token, no PHI in URL)
5. ✅ Console opens MessageChannel, transfers port2 to iframe
6. ✅ iframe receives `open-port`, sends `ready-ping {psid}`
7. ✅ Console verifies psid, sends bootstrap `{ticket, nonce, context}`
8. ✅ iframe POST `/api/embedded/preview-sessions/exchange` → 200 OK, Runtime Token returned
9. ✅ iframe `auth(runtime_token)` → `configureSession(ctx)` → `configure()` → `show()`
10. ✅ Status: `widget ready — interactive`

Negative tests (curl):

- ✅ Cross-origin exchange from `https://evil.attacker.example` → 403 ORIGIN_NOT_ALLOWED
- ✅ Replay of consumed ticket → 410 TICKET_ALREADY_USED
- ✅ Revoke after exchange → idempotent 200 (status REVOKED)

---

## Test summary

```
tests/unit/app/services/test_phase7_gate13a_preview_ticket.py   18 passed
tests/unit/app/api/test_phase7_gate13a_preview_sessions.py      14 passed
tests/unit/app/api/test_phase7_gate13a_preview_html.py           9 passed
tests/unit/app/api/test_phase7_gate13a_audit.py                  7 passed
─────────────────────────────────────────────────────────────────────────
Phase 7 Gate 13A new tests                                        48 passed

tests/test_api/test_phase7_gate1_examples_mount.py                (part of)
tests/test_api/test_phase7_gate3_agent_run_idempotency.py         (part of)
tests/test_api/test_phase7_gate4_run_cancel.py                    (part of)
tests/test_api/test_phase7_gate5_api_clients.py                   (part of)
tests/test_api/test_phase7_gate6_cors.py                          (part of)
tests/test_api/test_phase7_gate7_trace_token.py                   (part of)
tests/test_api/test_phase7_gate8_usage_api_client.py              (part of)
tests/test_api/test_phase7_gate9_sse_run_events.py                (part of)
─────────────────────────────────────────────────────────────────────────
Phase 7 Gates 1-9 regression                                     78 passed

Total: 126 PASS, 0 FAIL, 0 regression
```

`tsc --noEmit` on frontend: clean.

---

## What Gate 13A does NOT change (scope statement)

- The widget Web Component itself (`packages/icoder-embedded/src/`) —
  public API unchanged.
- Partner reference app (`examples/partner-reference-app/`) — partners use
  `client_credentials` directly, no preview ticket.
- The 3 demos at `/examples/{medical-coding,cdi,drg-dip}/` — already
  server-side token exchange.
- Phase 7 Gates 1-12 — all backend infrastructure reused as-is.
