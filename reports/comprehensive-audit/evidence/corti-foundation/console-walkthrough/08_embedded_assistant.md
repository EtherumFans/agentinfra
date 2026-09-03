# Corti Embedded Assistant — Authoritative SDK Signature (Verified)

> Source: `https://console.corti.app/project/4c4193c7-.../ai-studio/embedded-assistant` → Code tab → HTML (web component)
> Access date: 2026-07-16. Evidence: `08_embedded_assistant.png` + `08b_embedded_html_generator.txt`.

## Package: `@corti/embedded-web`

3 code generators: **HTML (web component)** | **React** | **JSON Config**

## Verified HTML web component snippet

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
      corti-embedded { width: 100%; height: 100vh; }
    </style>
  </head>
  <body>
    <corti-embedded id="corti-assistant" baseURL="https://assistant.eu.corti.app"></corti-embedded>

    <script type="module">
      import '@corti/embedded-web';

      const TENANT = "base";
      const ENVIRONMENT = "eu";

      const assistant = document.getElementById('corti-assistant');

      assistant.addEventListener('ready', async () => {
        try {
          // Replace with your authentication logic.
          await assistant.auth({
            access_token: 'YOUR_ACCESS_TOKEN',
            refresh_token: 'YOUR_REFRESH_TOKEN',
            token_type: 'bearer',
            mode: 'stateless',
          });
          await assistant.configureSession({
            defaultLanguage: "en",
            defaultMode: "in-person",
            defaultOutputLanguage: "en",
            defaultTemplateKey: "corti-patient-summary-legacy",
          });
          await assistant.configure({
            features: {
              aiChat: true,
              documentFeedback: true,
              interactionTitle: true,
              navigation: false,
              syncDocumentAction: false,
              templateEditor: true,
              virtualMode: true,
            },
            locale: {
              dictationLanguage: "en",
              interfaceLanguage: "auto",
            },
          });
          await assistant.show();
        } catch (error) {
          console.log('Initialization error:', error);
        }
      });

      assistant.addEventListener('embedded-event', (e) => {
        const { name, payload } = e.detail;
        switch (name) {
          case 'account.creditsConsumed':
            console.log('Credits consumed:', payload);
            break;
          case 'error.triggered':
            console.log('Error:', payload);
            break;
          default:
            console.log(name, payload);
        }
      });
    </script>
  </body>
</html>
```

## Authoritative API surface (derived from code generator)

### Custom element
- Tag: `<corti-embedded>`
- Required attribute: `baseURL` (e.g., `https://assistant.eu.corti.app`)
- Optional attribute: `id`

### Lifecycle methods (await-able)
| Method | Purpose | Required |
|--------|---------|----------|
| `assistant.auth({access_token, refresh_token, token_type, mode})` | Inject auth tokens | YES |
| `assistant.configureSession({defaultLanguage, defaultMode, defaultOutputLanguage, defaultTemplateKey})` | Per-session config | YES |
| `assistant.configure({features, locale})` | UI feature toggles | YES |
| `assistant.show()` | Render the widget | YES |

### Auth shape
```ts
{
  access_token: string,
  refresh_token: string,
  token_type: 'bearer',
  mode: 'stateless',  // or 'stateful'?
}
```

Note: Corti uses `access_token` + `refresh_token` (snake_case) — differs from typical JS conventions.

### Session config
- `defaultLanguage` — primary spoken language (e.g., "en")
- `defaultMode` — "in-person" | "virtual"
- `defaultOutputLanguage` — output document language
- `defaultTemplateKey` — initial document template (e.g., "corti-patient-summary-legacy")

### Features (7 toggles)
- `aiChat` — Enable AI chat panel
- `documentFeedback` — Show document feedback
- `interactionTitle` — Show interaction title
- `navigation` — Show navigation
- `syncDocumentAction` — Show sync-document action
- `templateEditor` — Enable template editor
- `virtualMode` — Allow virtual mode

### Locale config
- `dictationLanguage` — speech-to-text language
- `interfaceLanguage` — UI language ("auto" = browser default)

### Event API
- Single listener: `embedded-event`
- Event detail shape: `{ name: string, payload: object }` (2 fields, FLAT)
- Verified event names: `account.creditsConsumed`, `error.triggered`
- Wildcard default branch (catches all other events)

## Parity comparison vs iCoDer Phase 6 Gate 3 unified envelope

| Dimension | Corti (verified) | iCoDer (Phase 6 Gate 3) |
|-----------|------------------|-------------------------|
| Event listener | Single `embedded-event` with name dispatch | Same — single listener |
| Event detail fields | `name`, `payload` (2 fields flat) | `name`, `payload`, `meta` (3 fields, meta has `version/eventId/timestamp/sessionId/contextId`) |
| Event naming convention | `account.creditsConsumed`, `error.triggered` (dot.noun.snake_case) | `message.received`, `run.completed`, `account.creditsConsumed`, `patient.context.cleared` (dot.noun.snake_case) |
| Auth shape | `{access_token, refresh_token, token_type, mode}` | `{accessToken, refreshToken, tokenType, mode}` (camelCase per iCoDer Gate 13A) |
| Lifecycle methods | `auth`, `configureSession`, `configure`, `show` | `auth`, `configureSession`, `configure`, `show` (1:1 match) |
| Package name | `@corti/embedded-web` | `@icoder/embedded` |
| Custom element | `<corti-embedded>` | `<icoder-assistant>` |
| baseURL pattern | `https://assistant.eu.corti.app` (region-qualified) | `https://assistant.{region}.icoder.cloud` (region-qualified) |
| Mode default | "stateless" | "stateless" |

### Parity verdict

- **Lifecycle API**: PARITY ✅ (1:1 method shape — validates Phase 6 Gate 3 design)
- **Event detail shape**: ICODER_ADVANTAGE ✅ (iCoDer adds `meta` with eventId/timestamp/sessionId/contextId; Corti has flat 2-field)
- **Event name coverage**: iCoDer surfaces `patient.context.cleared` + `session.cleared` — Corti does NOT have explicit patient-context-isolation events visible in this generator
- **Auth field naming**: DIFFERENT_BY_DESIGN (snake_case vs camelCase — both are valid; not a parity gap)
- **Custom element name**: DIFFERENT_BY_DESIGN (brand prefix)

## Settings tab — verified feature surface

The Settings tab reveals the same 7 features as the code generator plus:

- **Session defaults**:
  - Primary spoken language (English US default)
  - Default mode: In-person | Virtual (radio)
- **Appearance**:
  - Primary color (hex picker, default `#3C61DD` Corti blue)
  - Interface language (Auto / browser default)
  - Dictation language (English US)
- **Onboarding**: "New to Embedded Assistant? Take a tour" + Dismiss link

## iCoDer-side gaps vs Corti (for Pre-A0 Gate 7 Parity Matrix V2)

Features in Corti's configure() but NOT in iCoDer's @icoder/embedded:
- `documentFeedback` — Corti has document-level feedback UI
- `interactionTitle` — Corti shows encounter/interaction title
- `navigation` — Corti has in-widget navigation
- `syncDocumentAction` — Corti has explicit "sync document" action
- `templateEditor` — Corti has in-widget template editor
- `virtualMode` — Corti supports virtual (video call) encounters
- `defaultTemplateKey` — Corti has multiple built-in document templates (e.g., `corti-patient-summary-legacy`)

These are NOT current iCoDer features. They are partner-integration features Corti built for its ambient scribe product (Corti's primary use case is real-time dictation/summarization during patient encounters — iCoDer's primary use case is post-encounter coding compliance).

Classification per Pre-A0 decision matrix:
- All 7 features → `OUT_OF_CURRENT_SCOPE` (different product focus)
- Specifically: Corti = real-time in-encounter assistant; iCoDer = post-encounter coding/CDI compliance

This validates the Phase 6 final report's claim that iCoDer and Corti are "different-by-design" in product focus.
