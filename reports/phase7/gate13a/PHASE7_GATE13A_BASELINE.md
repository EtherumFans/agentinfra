# Phase 7 Gate 13A-0 — Baseline Re-audit

**Date**: 2026-07-14
**Git HEAD**: `c147d015455017bc1d8420cbdbd813b3b8ec23ce` (Track H Tier 2)
**Uncommitted**: Phase 7 FINAL + Gate 13 (Corti-style Embedded Assistant Console page) + Gate 13 i18n follow-up
**Audit scope**: Files touched by Gate 13 + their security-relevant neighbors

## Files audited

### Frontend
- `frontend/src/pages/EmbeddedAssistantPage.tsx` (~340 LOC) — Gate 13 Console page
- `frontend/src/components/layout/Layout.tsx` — sidebar entry
- `frontend/src/App.tsx` — routing

### Backend
- `backend/app/api/embedded.py` — `GET /api/embedded/assistant.js`, `GET /api/embedded/preview`, `GET /api/embedded/preview.html`
- `backend/app/services/trace_token.py` — Phase 7 Gate 7 HMAC token service (reusable pattern)
- `backend/app/models/__init__.py` — model registry

### Embedded package
- `packages/icoder-embedded/` — Web Component source + dist
- `packages/icoder-sdk/` — TypeScript SDK

## Three sensitive-data-in-URL vectors (Checkpoint A violations)

### Vector 1 — Access Token in iframe URL (CRITICAL)

`EmbeddedAssistantPage.tsx:108-125` builds the iframe `src` as:

```ts
const previewUrl = useMemo(() => {
  const params = new URLSearchParams({
    agent: config.agentRef,
    patientId: config.patientId,
    patientName: config.patientName,
    encounterId: config.encounterId,
    primaryColor: config.primaryColor,
    aiChat: String(config.features.aiChat),
    // ... more params
    token: accessToken,  // ← Console JWT in URL
  });
  return `/api/embedded/preview.html?${params.toString()}`;
}, [config, accessToken]);
```

The Console user's `accessToken` (a JWT with `sub`, `org_id`, `role`, `exp`, `type: "access"`) is embedded in the iframe URL. Every iframe load writes this JWT into:
- Browser history entries (the URL is `location.href` of the iframe)
- Network HAR / DevTools Network panel
- Any `Referer` header on sub-resource requests inside the iframe
- Backend FastAPI access logs (URL path + query string)
- Any caching proxy between client and backend (if Cache-Control allows)

### Vector 2 — PHI in iframe URL (CRITICAL)

Same URLSearchParams contains:
- `patientId` (e.g. `P-2026-001`)
- `patientName` (e.g. `张三` → URL-encoded `%E5%BC%A0%E4%B8%89`)
- `encounterId` (e.g. `E-20260713-001`)

All three are PHI under HIPAA-equivalent regulations. They leak via the same channels as Vector 1. Backend access logs (which often get aggregated to centralized logging/SIEM) would persist patient names in URL-decoded form.

### Vector 3 — `postMessage(..., '*')` wildcard target origin (CRITICAL)

`backend/app/api/embedded.py:320` (iframe → parent):
```js
window.parent.postMessage({source: 'icoder-embedded', name, payload, meta}, '*');
```

`frontend/src/pages/EmbeddedAssistantPage.tsx:90-105` (parent → listener):
```ts
const handler = (e: MessageEvent) => {
  const data = e.data || {};
  if (data.source !== 'icoder-embedded') return;  // ← source check only
  // No event.origin check
  // No event.source check (didn't verify it came from our iframe)
  // No previewSessionId / nonce check
  // No schema validation
  ...
};
```

Both directions use `'*'` or don't enforce origin. A malicious parent page that embeds the iframe (if CSP/frame-ancestors allows it) can receive the `{name, payload, meta}` envelope including `run.completed` payloads that contain agent responses (potentially including chart-summary text = PHI). Conversely, a malicious iframe (if an attacker could swap the iframe URL) could send forged events to the parent.

## Missing security headers (Checkpoint D violations)

`backend/app/api/embedded.py:46-231` (`embedded_assistant_preview` + `embedded_preview_html`):

- No `Content-Security-Policy` header on either endpoint. The default FastAPI response has no CSP.
- No `X-Frame-Options` or CSP `frame-ancestors`. Any site can iframe this URL.
- No `Referrer-Policy`. Default browser behavior leaks the full URL to Referer on sub-resource requests.
- No `Cache-Control: no-store`. Browsers and proxies may cache the page (and its query string) per their default heuristic.
- No `iframe sandbox` attribute set by the parent. The iframe runs with full same-origin privileges.

The Preview pane in `EmbeddedAssistantPage.tsx:204-216`:
```tsx
<iframe
  key={previewKey}
  src={previewUrl}
  title="Embedded Preview"
  className="border ..."
  style={{ ... }}
/>
```

No `sandbox` attribute. No `allowlist` of features.

## Code generator credential safety (Checkpoint G violation, partial)

`EmbeddedAssistantPage.tsx:342-388` (`generateHtml`) and `:390-431` (`generateReact`):

✅ Already safe: `ACCESS_TOKEN = 'PASTE_TOKEN_HERE'` (placeholder)

❌ Unsafe: HTML/React generators embed the **current patient context** as literal values:
```ts
await a.configureSession({
  defaultTemplateKey: "medical-coding-agent",
  defaultLanguage: "zh-CN",
  defaultOutputLanguage: "zh-CN",
  patientId: "P-2026-001",       // ← real patient ID
  name: "张三",                   // ← real patient name
  encounterId: "E-20260713-001", // ← real encounter ID
});
```

A customer success engineer who clicks "Copy" and pastes the snippet into Slack/email/Jira leaks real PHI.

## Existing security assets (reusable)

### `backend/app/services/trace_token.py` (Phase 7 Gate 7)
- HMAC-SHA256 signed tokens bound to `(run_id, org_id, api_client_id)`
- 24h TTL, constant-time signature comparison
- Pattern reusable for Preview Bootstrap Ticket (shorten TTL to 60s)

### `backend/app/middleware/auth.py`
- `get_current_user` — Console JWT auth
- `get_current_user_or_oauth_client` — hybrid (Phase 7 Gate 12)
- Both reusable for `POST /api/embedded/preview-sessions` endpoint

### `backend/app/models/idempotency_record.py` + alembic 012
- DB model + migration pattern for short-lived records with org/client scoping
- Reusable structure for `preview_sessions` table

### `backend/alembic/versions/`
- 14 migrations exist; next is 015

## Test posture inherited from Gate 13

- `npx tsc --noEmit` — 0 errors
- 88/88 Phase 7 backend regression PASS
- `vitest locales.test` 9/9 PASS
- Playwright MCP browser E2E — real DeepSeek run verified (S52.500x001)

## Gate 13A-0 verdict

**`GATE13A_0_BASELINE_AUDIT_COMPLETE`** — three URL-leak vectors confirmed, postMessage wildcard confirmed, missing security headers confirmed, code-generator PHI leak confirmed. Reusable security assets inventoried. Proceed to Gate 13A-1 (Preview Session/Ticket API).

## Files written by this gate

- `reports/phase7/gate13a/PHASE7_GATE13A_BASELINE.md` (this file)
