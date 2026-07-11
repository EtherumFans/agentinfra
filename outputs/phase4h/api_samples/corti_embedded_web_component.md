# Corti Embedded Assistant — Web Component Code Sample

Source: Corti Console > AI Studio > Embedded Assistant > Code tab
URL: https://console.corti.app/project/b8f8129a-c31d-407f-b723-6ecc592d31e4/ai-studio/embedded-assistant

## Full HTML sample (verbatim from Corti Console)

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
      corti-embedded {
        width: 100%;
        height: 100vh;
      }
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
          // Use TENANT and ENVIRONMENT to configure your auth provider.
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

## Per §11.2 (Frontend embedding) verification

| # | Item | Corti status | Evidence |
|---|---|---|---|
| 1 | iframe | **NOT OBSERVED** — Corti does NOT use iframe embedding. Web Component is the canonical embed method. | Code sample uses `<corti-embedded>` custom element, no iframe |
| 2 | Web Component | **YES** — `<corti-embedded id="..." baseURL="...">` custom element (customElements tag) | Code sample |
| 3 | JavaScript SDK | **YES** — `import '@corti/embedded-web'` (npm package) | Code sample + Appearance tab |
| 4 | React Component | **NOT OBSERVED** — no React wrapper exposed. Web Component can be used from React via ref, but no first-party React binding. | Not in Console |
| 5 | Embedded Chat | **YES** — `features.aiChat: true` enables AI chat inside the embedded assistant | Code sample `features.aiChat` |
| 6 | Embedded Agent | **IMPLIED** — the Embedded Assistant can run Agents (per left nav "AI Studio > Embedded Assistant") | Page route |
| 7 | Theme | **YES** — Appearance tab: "Primary color #3C61DD" (color picker) | Appearance tab |
| 8 | Locale | **YES** — Locale tab: Interface language (Auto / browser default) + Dictation language (English US) | Locale tab |
| 9 | SSO | **YES** — `assistant.auth({access_token, refresh_token, token_type:'bearer', mode:'stateless'})` — token injection from parent app's auth provider | Code sample |
| 10 | Current Patient Context | **IMPLIED** — `configureSession({defaultTemplateKey: "corti-patient-summary-legacy"})` — template key suggests patient summary context, but no explicit `patient_id` field in the embed API. Patient context is passed via the Encounter API on the backend. | Code sample |
| 11 | Current User Context | **IMPLIED** — `mode: 'stateless'` + access_token carries user identity. No explicit `user_id` field. | Code sample |
| 12 | Callback | **YES** — `assistant.addEventListener('ready', ...)` and `assistant.addEventListener('embedded-event', ...)` are callback-style | Code sample |
| 13 | Event Listener | **YES** — `embedded-event` listener with `{name, payload}`. Specific event names: `account.creditsConsumed` (cost callback) + `error.triggered` (error callback) + others (default case) | Code sample |

## Per §11.3 (Event-driven integration) — client-side events

| # | Item | Corti status |
|---|---|---|
| Webhook | **NOT OBSERVED** in Console (no Webhooks page in left nav) |
| Background Run | **UNKNOWN** — not in Console UI |
| Async Job | **UNKNOWN** — not in Console UI |
| Callback URL | **NOT OBSERVED** in Console |
| Event Subscription | **PARTIAL** — client-side event listener (`embedded-event`), not server-side subscription |
| Run Completed Event | **PARTIAL** — `embedded-event` may emit run-completed, but not explicitly named in sample |
| Tool Call Event | **NOT OBSERVED** — no `tool.call` event in sample |
| Error Event | **YES (client-side)** — `error.triggered` event name in switch case |
