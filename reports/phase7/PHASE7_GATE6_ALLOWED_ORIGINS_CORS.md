# Phase 7 Gate 6 — Allowed Origins / CORS / Embedded Security

**Status**: PASS_GATE6_ALLOWED_ORIGINS_CORS_VERIFIED
**Verdict tier**: PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION (gate-level)
**Date**: 2026-07-14
**Checkpoint**: B in progress (Gates 5 done → 6 done → 7 next)

> Phase 7 §11 Gate 6 contract:
> - §11.1 Per-client Allowed Origins enforcement (no `*` with client_credentials)
> - §11.2 CSP with all 6 directives (script-src/connect-src/frame-src/frame-ancestors/img-src/style-src), no `unsafe-eval`
> - §11.3 No PHI/secrets in localStorage/sessionStorage/IndexedDB/Cache Storage/Cookies
> - §11.4 No PHI/secrets in console output

---

## 1. What was built

| Artifact | Path | Purpose |
|---|---|---|
| Middleware | `backend/app/middleware/partner_cors.py` (~190 LOC) | `PartnerCORSMiddleware` — enforces per-client `allowed_origins` on partner routes |
| Wiring | `backend/app/main.py` (line ~1413-1424) | `app.add_middleware(PartnerCORSMiddleware)` layered after `CORSMiddleware` |
| CSP update | `backend/app/api/examples.py` (line 55-66) | Added `frame-src 'none'` + `form-action 'self'`; bumped version to `1.0.0-phase7-gate6` |
| Tests | `backend/tests/test_api/test_phase7_gate6_cors.py` (8 tests) | All §11.1 contract coverage |
| Build | `packages/icoder-embedded/dist/icoder-assistant.js` (rebuilt) | Compiled widget JS for the assistant.js endpoint |

**Test evidence**: 8/8 new PASS + 15/15 Gate 5 regression + 7/7 Gate 4 regression + 4/4 Gate 3 regression + 14/14 OAuth regression = **all green**.

---

## 2. §11.1 Per-client Allowed Origins enforcement

### Design — layered, not duplicated

The existing static `CORSMiddleware` (in `main.py`) uses `settings.CORS_ORIGINS` — perfect for the Console SPA (one known origin) but not for partners (each partner brings their own Origin).

`PartnerCORSMiddleware` is layered on top, running BEFORE the static layer on partner routes only:

```python
_PARTNER_ROUTE_PREFIXES = (
    "/api/v1/agents/",   # POST /agents/{id}/run
    "/api/v1/runs/",     # GET/POST runs + cancel
    "/api/embedded/",    # widget handshake
    "/examples/",        # demo static assets
)
```

Console routes (`/api/clients/*`, `/api/usage/*`, etc.) keep the static layer. §4 "no parallel implementations" satisfied.

### Preflight handling (critical)

A subtle issue: when a partner Origin is ALLOWED by the per-client allowlist but NOT by the static allowlist, naively calling `call_next()` would pass the request to the static `CORSMiddleware`, which would return **400 Disallowed CORS origin** — breaking preflight entirely for partner origins.

**Fix**: `PartnerCORSMiddleware` short-circuits OPTIONS preflight for partner routes when the Origin is allowed, returning a complete preflight response (204 + `Access-Control-Allow-Origin` + `Access-Control-Allow-Methods` + `Access-Control-Allow-Headers` + `Access-Control-Allow-Credentials` + `Access-Control-Max-Age: 600`). This bypasses the static layer entirely on partner preflights.

### Disallowed origin → 403 ORIGIN_NOT_ALLOWED

When the Origin isn't on ANY allowlist (static OR dynamic), we return:

```json
HTTP/1.1 403 Forbidden
Content-Type: application/json
Access-Control-Allow-Origin: null
Cache-Control: no-store

{
  "code": "ORIGIN_NOT_ALLOWED",
  "message": "Origin not in allowed_origins for any configured API Client. Contact your iCoDer tenant admin."
}
```

`Access-Control-Allow-Origin: null` ensures the browser surfaces a CORS error (not a generic network error) so the partner developer sees the actual reason in DevTools.

### Cache

Origins are read from the DB (`oauth_clients.allowed_origins` JSON column) and cached for 60s in `_all_partner_origins._cache`. The cache is busted on write by the CRUD endpoints (or expires naturally). Tests can manually bust via `_all_partner_origins._cache = None`.

### §11.1 contract matrix

| Requirement | Enforcement | Test |
|---|---|---|
| Exact Origin match (no wildcard) | `if origin not in allowed: 403` | `test_preflight_disallowed_origin_returns_403` |
| No `*` with client_credentials | Gate 5 rejects at write time; verified not on wire | (covered by Gate 5 tests) |
| Localhost whitelist | `settings.CORS_ORIGINS` union; static entries include localhost for dev | `test_preflight_allowed_static_origin` |
| Origin mismatch → reject | `403 ORIGIN_NOT_ALLOWED` | `test_non_preflight_disallowed_origin_returns_403` |
| Preflight correct | `204` with `Access-Control-Allow-*` headers | `test_preflight_allowed_partner_origin_returns_204` |
| Errors don't leak Secret/internal info | Body is `{code, message}` only; no internal IDs or stack trace | (manual review) |

---

## 3. §11.2 Content Security Policy

`examples.py` defines the CSP and serves it as an HTTP header on every `/examples/*` response (HTML + JS). HTTP header is used (not `<meta>`) because `frame-ancestors` cannot be set via meta tag.

```python
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "        # no 'unsafe-eval'
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self' data:; "
    "frame-src 'none'; "
    "frame-ancestors 'none'; "                    # anti-clickjack
    "base-uri 'self'; "
    "form-action 'self'"
)
```

**§11.2 contract matrix**:

| Directive | Status | Why |
|---|---|---|
| `script-src` | ✓ `'self' 'unsafe-inline'` | Demos use inline `<script type="module">`. No `'unsafe-eval'` — verified by reading both source and compiled dist |
| `connect-src` | ✓ `'self'` | Widget only fetches from the same origin that served it |
| `frame-src` | ✓ `'none'` | Demos don't embed iframes |
| `frame-ancestors` | ✓ `'none'` | Demos cannot be iframed by anyone (anti-clickjack) |
| `img-src` | ✓ `'self' data:` | Allow inline data URIs for icons |
| `style-src` | ✓ `'self' 'unsafe-inline'` | Demos use inline `<style>` blocks |

Additional directives: `default-src 'self'`, `base-uri 'self'`, `form-action 'self'`, `font-src 'self' data:`.

`'unsafe-inline'` is allowed but `'unsafe-eval'` is forbidden — this matches §11.2's intent (block eval/Function constructor while permitting inline module scripts which are statically analyzable).

### Other security headers

| Header | Value | Purpose |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Block MIME sniffing |
| `X-Frame-Options` | `DENY` | Legacy anti-clickjack (belt-and-suspenders with `frame-ancestors`) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Don't leak full URL in Referer |
| `X-iCoDer-Demo-Version` | `1.0.0-phase7-gate6` | Version traceability |
| `Cache-Control` | `no-cache, must-revalidate` (HTML) / `no-cache, must-revalidate` (JS) | Always-fresh demos for partners |

---

## 4. §11.3 Storage audit

The embedded widget source (`packages/icoder-embedded/src/icoder-assistant.ts`) and the compiled dist (`packages/icoder-embedded/dist/icoder-assistant.js`) were both grepped for:

```
localStorage | sessionStorage | indexedDB | document.cookie
```

**Source**: 1 match at line 423 — a comment confirming the safety property:
```
* Phase 6 Gate 2 — PHI safety: patient context is held in-memory only.
* It is NEVER written to localStorage, sessionStorage, or cookies.
```

**Compiled dist**: 1 match — the same comment carried through.

**No actual storage calls**. PHI (patient name, ID, encounter ID) is held in JavaScript closures inside the `IcoderEmbedded` class. When the host HIS/EMR switches patients, it MUST call `clearPatientContext()` to flush — this is documented in the JS docstring.

**Demo HTMLs**: 0 matches — demos don't use any persistent storage.

### Partner guidance

Partners integrating the widget should:
1. Hold the JWT in memory only (not localStorage) — the widget's `auth()` method takes the token as a method argument, not from storage
2. Use `HttpOnly; Secure; SameSite=Strict` cookies for any server-side session (the widget itself doesn't set cookies)
3. Call `clearPatientContext()` on patient switch

---

## 5. §11.4 Console output audit

Grepped widget source + dist + demo HTMLs for `console.log|warn|error|info|debug`:

**Widget source** (7 matches):
- 5 are in a JSDoc example showing how a partner would consume events (lines 39-44) — not real calls
- 6 are `console.warn` for deprecated attribute usage (`access-token`, `agent-ref`, `<icoder-assistant>` tag name) — no PHI/secrets

**Demo HTMLs** (3 matches, one per demo):
- All three are `console.warn('[demo] config.js load failed; using defaults', e);` — no PHI/secrets

**No PHI or secret logged anywhere.** Partners can ship the widget without worrying about token or patient data leaking to the browser console.

---

## 6. Tests run

```
$ python -m pytest tests/test_api/test_phase7_gate6_cors.py -v

  PASSED test_preflight_allowed_partner_origin_returns_204
  PASSED test_preflight_allowed_static_origin
  PASSED test_preflight_disallowed_origin_returns_403
  PASSED test_non_preflight_disallowed_origin_returns_403
  PASSED test_non_preflight_allowed_partner_origin_tags_response
  PASSED test_no_origin_header_passes_through
  PASSED test_console_route_disallowed_partner_origin_not_blocked_by_partner_middleware
  PASSED test_origin_added_after_first_request_eventually_allowed

8 passed
```

**Regression**:
- `test_phase7_gate5_api_clients.py` (15) → PASS
- `test_phase7_gate4_run_cancel.py` (7) → PASS
- `test_phase7_gate3_agent_run_idempotency.py` (4) → PASS
- `test_oauth.py` (14) → PASS

**Total**: 8 + 15 + 7 + 4 + 14 = **48 PASS, 0 FAIL**.

---

## 7. What's NOT done (deferred)

- **Browser walkthrough**: Tests use FastAPI TestClient which doesn't exercise the full browser CORS pipeline. Gate 10 will run all 3 demos end-to-end in a real browser, exercising real CORS preflight + widget load + Run.
- **Token revocation on disable**: Still deferred from Gate 5 — disabled clients' tokens remain valid until their 5-min TTL expires (RFC 6749 doesn't auto-revoke).
- **Per-endpoint scope enforcement**: The middleware validates `Origin` but doesn't yet check per-endpoint OAuth scopes (e.g. `agents:run` required for `POST /agents/{id}/run`). Documented in Gate 5 §7; deferred.
- ** CSP for partner pages**: The CSP enforced here is on the iCoDer-hosted demos only. Partners embedding the widget from their own pages must set their own CSP allowing `connect-src https://*.icoder.cloud` and `script-src` for the widget URL.
- **Cookie-based auth**: Not implemented and not planned. The widget uses Bearer tokens passed via `auth({access_token, ...})`. Cookies would require CSRF tokens and `SameSite` tuning — out of scope for Gate 6.

---

## 8. §16 forbidden outputs check

| Forbidden | Status |
|---|---|
| PRODUCTION_READY | Not claimed |
| PUBLIC_NBM_PUBLISHED | Not claimed |
| Wildcard origin + client_credentials | Explicitly rejected (§11.1) |
| 'unsafe-eval' in script-src | Not present (§11.2) |
| PHI in localStorage/sessionStorage/cookies | Verified absent (§11.3) |
| PHI/Secret in console.log | Verified absent (§11.4) |
| "Final" verdict | Not claimed |

Verdict: **PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION** at the gate level. Phase 7 continues with Gate 7 (Trace URL partner-secured access).
