# `@icoder/embedded`

Embeddable AI coding assistant Web Component for HIS/EMR systems. Drop the `<icoder-embedded>` tag into any HTML page and your clinicians get in-context medical coding help powered by the iCoDer platform.

> **Phase 5 A4 (2026-07-10):** v2.0.0 ships a method-based API. Existing 1.0 attribute-based config still works through the 2.0.x deprecation window — see [MIGRATION-2.0.md](./MIGRATION-2.0.md).

## Install

```bash
npm install @icoder/embedded
# or
pnpm add @icoder/embedded
```

## Quick start

```html
<icoder-embedded id="icoder-assistant" baseURL="https://hospital.icoder.cloud"></icoder-embedded>

<script type="module">
  import '@icoder/embedded';

  const a = document.getElementById('icoder-assistant');

  a.addEventListener('ready', async () => {
    await a.auth({
      access_token: 'YOUR_ACCESS_TOKEN',
      token_type: 'bearer',
      mode: 'stateless',
    });
    await a.configureSession({
      defaultTemplateKey: 'icoder/medical-coding-agent',
      // iCoDer 增强: 显式 patient context (templateKey 之外还能传 patientId/name/encounterId)
      patientId: 'P001', name: '张三', encounterId: 'E2026071001',
    });
    await a.configure({
      features: { aiChat: true, documentFeedback: true, virtualMode: false },
      locale: { dictationLanguage: 'zh-CN', interfaceLanguage: 'auto' },
    });
    await a.show();
  });

  // Unified event envelope
  a.addEventListener('embedded-event', (e) => {
    const { name, payload } = e.detail;
    switch (name) {
      case 'account.creditsConsumed':
        console.log('Cost:', payload);  // {amount, currency, run_id}
        break;
      case 'run.completed':
        console.log('Run done:', payload);  // {run_id, agent_id, latency_ms, output, cost}
        break;
      case 'error.triggered':
        console.error('Error:', payload);  // {message}
        break;
    }
  });
</script>
```

## API reference

### Methods

| Method | Purpose |
|---|---|
| `auth({access_token, refresh_token?, token_type?, mode?})` | Set credentials. Required before any agent run. |
| `configureSession({defaultTemplateKey, defaultLanguage?, ..., patientId?, name?, encounterId?})` | Set agent + patient context. |
| `configure({features?, locale?})` | Feature flags + interface language. |
| `show()` | Reveal the widget (hidden until called). |

### Methods (iCoDer 增强)

| Method | Purpose |
|---|---|
| `setPatientContext({patientId?, name?, encounterId?})` | Update patient mid-session. |
| `ask(question): Promise<RunResponse>` | Programmatic message send (no UI click). |

### Events (unified `embedded-event` envelope `{name, payload}`)

| `name` | `payload` |
|---|---|
| `ready` | `{}` |
| `run.completed` | `{run_id, agent_id, latency_ms, output, cost}` |
| `account.creditsConsumed` | `{amount, currency, run_id}` |
| `error.triggered` | `{message}` |
| `message.received` | `{role, content}` |

Listen:

```js
a.addEventListener('embedded-event', (e) => {
  const { name, payload } = e.detail;
  // route by name
});
```

## Browser support

- Chrome/Edge 90+ (custom elements v1, Shadow DOM, ES modules)
- Safari 15.4+ (same)
- Firefox 93+ (same)
- IE 11 not supported

## Bundling

- ES module: `dist/icoder-assistant.js`
- TypeScript types: `dist/index.d.ts`
- No dependencies — vanilla Web Component.

## Pricing

Cost events use **CNY (¥)**, not USD. See `CLAUDE.md §货币约定` for the rationale.

## License

Apache-2.0

## Changelog

### 2.0.0 (2026-07-10) — Phase 5 A4

- **BREAKING**: refactored attribute-based config → method-based API (`auth()/configureSession()/configure()/show()`)
- **BREAKING**: tag renamed `<icoder-assistant>` → `<icoder-embedded>` (1.0 tag kept as deprecated alias)
- **BREAKING**: events unified into `embedded-event` envelope (1.0 `coding.completed` + `error` removed)
- **FIX**: endpoint updated to `POST /api/v1/agents/{id}/run` (1.0 used a removed endpoint that returned 410)
- See [MIGRATION-2.0.md](./MIGRATION-2.0.md)

### 1.0.0

- Initial release with attribute-based config
