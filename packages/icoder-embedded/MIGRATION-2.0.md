# Migrating to `@icoder/embedded` 2.0

Phase 5 A4 (2026-07-10) — GAP-11-01: refactor Web Component API from
attribute-based config to Corti-compatible method-based API.

This guide shows the 1.0 → 2.0 diff for hospital HIS/EMR integrators.

## TL;DR

| Aspect | 1.0 (attribute-based) | 2.0 (method-based, Corti-compatible) |
|---|---|---|
| Tag name | `<icoder-assistant>` | `<icoder-embedded>` (1.0 alias kept, deprecated) |
| Auth | `access-token="..."` attr | `await assistant.auth({access_token, token_type, mode})` |
| Agent | `agent-ref="..."` attr | `await assistant.configureSession({defaultTemplateKey})` |
| Patient | `setPatientContext({...})` (method, kept) | `configureSession({... patient fields})` or `setPatientContext` (kept) |
| Features | none | `await assistant.configure({features, locale})` |
| Visibility | always visible after connect | hidden until `await assistant.show()` |
| Events | `coding.completed`, `error` | unified `embedded-event` w/ `{name, payload}` |

## Why the change

Phase 4-H §11 audit (`reports/phase4h/CORTI_THIRD_PARTY_INTEGRATION_AUDIT.md`)
found iCoDer's Web Component surface diverged from Corti's `<corti-embedded>`
in 7 ways:

1. Attribute-based config vs Corti's method-based `auth()/configureSession()/configure()/show()`
2. Split events (`coding.completed` + `error`) vs unified `embedded-event` envelope
3. No `configureSession({defaultTemplateKey})` analog
4. Patient context was a separate method rather than folded into `configureSession`
5. Widget auto-visible on connect vs Corti's "hidden until `show()`"
6. No `configure({features, locale})` analog
7. Event payload shape didn't match Corti's `{name, payload}` envelope

2.0 closes all 7 gaps while keeping iCoDer ADVANTAGE methods (`setPatientContext`,
`ask`) per memory `feedback_corti_alignment.md` ("勿为像 Corti 删 iCoDer 差异化能力").

## Before (1.0)

```html
<icoder-assistant
  base-url="https://hospital.icoder.cloud"
  access-token="eyJhbGciOiJIUzI1NiIs..."
  agent-ref="icoder/medical-coding-agent"
  theme="light"
  locale="zh-CN"
></icoder-assistant>
<script type="module">
  import '@icoder/embedded';
  const a = document.querySelector('icoder-assistant');
  a.setPatientContext({ patientId: 'P001', name: '张三' });
  a.addEventListener('coding.completed', (e) => console.log('done', e.detail));
  a.addEventListener('error', (e) => console.error('err', e.detail));
</script>
```

## After (2.0)

```html
<icoder-embedded id="icoder-assistant" baseURL="https://hospital.icoder.cloud"></icoder-embedded>
<script type="module">
  import '@icoder/embedded';
  const a = document.getElementById('icoder-assistant');
  a.addEventListener('ready', async () => {
    await a.auth({
      access_token: 'eyJhbGciOiJIUzI1NiIs...',
      token_type: 'bearer',
      mode: 'stateless',
    });
    await a.configureSession({
      defaultTemplateKey: 'icoder/medical-coding-agent',
      defaultLanguage: 'zh-CN',
      defaultOutputLanguage: 'zh-CN',
      // iCoDer ADVANTAGE: explicit patient context (Corti uses templateKey only)
      patientId: 'P001',
      name: '张三',
      encounterId: 'E2026071001',
    });
    await a.configure({
      features: { aiChat: true, documentFeedback: true, virtualMode: false },
      locale: { dictationLanguage: 'zh-CN', interfaceLanguage: 'auto' },
    });
    await a.show();
  });
  a.addEventListener('embedded-event', (e) => {
    const { name, payload } = e.detail;
    switch (name) {
      case 'account.creditsConsumed':
        console.log('Cost:', payload);  // {amount, currency, run_id}
        break;
      case 'run.completed':
        console.log('Run done:', payload);  // iCoDer-specific — {run_id, agent_id, latency_ms, output, cost}
        break;
      case 'error.triggered':
        console.error('Error:', payload);  // {message}
        break;
      case 'message.received':
        console.log('Msg:', payload);  // {role, content}
        break;
    }
  });
</script>
```

## Method reference

### `auth(opts: AuthOptions): Promise<void>`

| Field | Type | Required | Notes |
|---|---|---|---|
| `access_token` | string | yes | JWT or opaque token from `/api/auth/login` |
| `refresh_token` | string | no | for `mode: 'session'` long-lived sessions |
| `token_type` | string | no | default `'bearer'` |
| `mode` | string | no | `'stateless'` (default) or `'session'` |

### `configureSession(opts: SessionConfig): Promise<void>`

| Field | Type | Notes |
|---|---|---|
| `defaultTemplateKey` | string | agent_id, e.g. `'icoder/medical-coding-agent'` |
| `defaultLanguage` | string | `'zh-CN'` / `'en-US'` |
| `defaultMode` | string | `'in-person'` / `'remote'` / `'telehealth'` |
| `defaultOutputLanguage` | string | |
| `patientId` | string | iCoDer ADVANTAGE — Corti does not have this |
| `name` | string | iCoDer ADVANTAGE |
| `encounterId` | string | iCoDer ADVANTAGE |

### `configure(opts: ConfigureOptions): Promise<void>`

| Field | Type | Notes |
|---|---|---|
| `features.aiChat` | boolean | show/hide input + quick actions |
| `features.documentFeedback` | boolean | reserved for future |
| `features.virtualMode` | boolean | reserved for future |
| `locale.dictationLanguage` | string | `'zh-CN'` / `'en-US'` |
| `locale.interfaceLanguage` | string | `'auto'` = follow browser |

### `show(): Promise<void>`

Make the widget visible. Should be called after `auth() + configureSession() + configure()`.
If `auth()` was skipped, prints a warning and renders but API calls will 401.

### `setPatientContext(ctx)` and `ask(question)` (iCoDer ADVANTAGE, kept)

Corti does not have these. They remain as iCoDer-specific extensions:

- `setPatientContext({ patientId, name, encounterId })` — set patient context after `show()`
- `ask(question): Promise<RunResponse>` — programmatic message send

## Event reference

All events use the unified `embedded-event` envelope with `{name, payload}` shape:

| `name` | `payload` | When |
|---|---|---|
| `ready` | (empty) | widget finished initializing; safe to call `auth()` etc. |
| `account.creditsConsumed` | `{amount, currency, run_id}` | run completed with non-zero cost |
| `run.completed` | `{run_id, agent_id, latency_ms, output, cost}` | iCoDer-specific; run returned 200 |
| `error.triggered` | `{message}` | run failed or thrown |
| `message.received` | `{role, content}` | user or agent message rendered |

Listener pattern:

```js
a.addEventListener('embedded-event', (e) => {
  const { name, payload } = e.detail;
  // route by name
});
```

## Deprecation window

- 1.0 attributes (`access-token`, `agent-ref`) still work in 2.0.x — they print a
  `console.warn` pointing to this guide.
- The old `<icoder-assistant>` tag still works in 2.0.x — registered as an alias
  for `<icoder-embedded>`.
- Old events (`coding.completed`, `error`) are **not** emitted in 2.0 — switch to
  the unified `embedded-event` listener.
- 1.0 attributes and the `<icoder-assistant>` alias will be **removed in 2.1**.

## Endpoint change (internal)

2.0 also fixes the backend endpoint the widget calls:

- 1.0: `POST /api/runtime/agents/{agentRef}/run` (removed in Phase 2.1-A, returned 410)
- 2.0: `POST /api/v1/agents/{agentId}/run` (unified Agent Run API, Phase 4-F2)

This was a 1.0 latent bug — the old endpoint returned 410 Gone, so the widget
silently broke. 2.0 wires to the live endpoint.

## TypeScript types

```ts
import type { AuthOptions, SessionConfig, ConfigureOptions, EmbeddedEvent } from '@icoder/embedded';
```

Full type declarations ship in `dist/index.d.ts`.

## Rollback / coexistence

If you can't migrate immediately:

- Stay on `@icoder/embedded@1.0.0` — it's still on npm (A5 will publish 2.0.0
  side-by-side, not replace).
- 1.0's `agent-ref` attribute still routes through the new endpoint internally
  in 2.0 — so you can upgrade the package without changing your HTML.

## Open issues

- A5 (npm publish) — `@icoder/embedded@2.0.0` not yet on the public registry.
  Until A5 ships, install from local path: `npm install file:./packages/icoder-embedded`.
- A6 (RunHistory Date filter + daily chart) — the daily chart on `/usage` uses
  `daily_breakdown` from the new A3 backend; visible after A6 lands.
