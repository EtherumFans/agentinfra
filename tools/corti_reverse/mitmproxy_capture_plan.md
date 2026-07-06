# Optional mitmproxy Capture Plan

**Tool**: #3 — Optional capture for WebSocket frames / SSE streams /
cross-origin responses that Chrome HAR truncates.

**Status**: Disabled by default. Enable only when Playwright HAR
proves insufficient for a specific Corti mechanism.

---

## When to Use mitmproxy

| Symptom | Cause | Use mitmproxy? |
|---|---|---|
| WebSocket frames truncated in HAR | Chrome HAR records WS metadata but not all frame payloads | ✅ Yes |
| SSE stream ends prematurely in HAR | Long-running SSE may be truncated | ✅ Yes |
| Cross-origin response body hidden | CORS blocks DevTools from reading body | ✅ Yes |
| Need full request/response headers | Chrome hides some headers (e.g., `cookie` on cross-origin) | ✅ Yes |
| Standard REST XHR | Full body visible in HAR | ❌ No — Playwright HAR is sufficient |
| Page load + initial API calls | Full sequence visible in HAR | ❌ No |

---

## Setup

### 1. Install mitmproxy

```bash
pip install mitmproxy
# or download from https://mitmproxy.org/
```

### 2. Start mitmproxy on port 8080

```bash
mitmweb --listen-port 8080 \
        --set save_stream_output=artifacts/corti_reverse/hars/<name>.flows \
        --set web_open_browser=false
```

### 3. Install mitmproxy CA cert in Chrome

- Start mitmproxy once with default config.
- Browse to `http://mitm.it` from Chrome.
- Download "mitmproxy CA cert" (PEM format).
- In Chrome: Settings → Privacy → Certificates → Authorities → Import → select PEM.
- Restart Chrome.

### 4. Launch Chrome with mitmproxy as proxy

```bash
# Windows (PowerShell)
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  -ArgumentList '--proxy-server=localhost:8080',
                '--user-data-dir=C:\Temp\corti-mitm-profile',
                'https://app.corti.ai/'

# macOS / Linux
google-chrome --proxy-server=localhost:8080 \
              --user-data-dir=/tmp/corti-mitm-profile \
              https://app.corti.ai/
```

Use a **separate Chrome profile** to avoid polluting the user's main
profile with the mitmproxy CA cert.

### 5. Perform Corti action under test

Navigate to Corti URL, perform the action. mitmproxy records all
flows to the `.flows` file.

### 6. Convert `.flows` to HAR

```bash
mitmdump -r artifacts/corti_reverse/hars/<name>.flows \
         --set hardump=artifacts/corti_reverse/hars/<name>.from-mitm.har
```

### 7. Redact

```bash
python tools/corti_reverse/har_analyzer/redact_har.py \
  --input artifacts/corti_reverse/hars/<name>.from-mitm.har \
  --output artifacts/corti_reverse/hars/<name>.redacted.har
```

### 8. Cleanup

- Stop mitmproxy (Ctrl+C).
- Delete the temporary Chrome profile.
- Optionally uninstall the mitmproxy CA cert from Chrome (to revert
  to baseline trust store).

---

## Risk Mitigation

- **CA cert exposure**: The mitmproxy CA cert, if leaked, allows
  MITM of any HTTPS site. Delete it after capture; never commit it.
- **Profile pollution**: Use a separate Chrome profile so the mitm
  CA cert does not persist in the user's main profile.
- **Credential leakage**: mitmproxy records all traffic including
  auth tokens. The `.flows` file MUST be redacted before commit
  (use `redact_har.py --flows-mode`).
- **Accidental capture of unrelated traffic**: Mitmproxy records
  ALL traffic through port 8080, not just Corti. Close other
  browser tabs during capture to minimize noise.

---

## Decision: Default Disabled

For Phase 3-B1.5 Sections B and C, **Playwright HAR is the default
capture mechanism**. mitmproxy is reserved for:

1. WebSocket frame body inspection (Corti's run streaming may use WS).
2. SSE chunk-level inspection (if Corti's run status uses SSE).
3. Cross-origin response body inspection (rare).

If Section B's manual exploration surfaces a need for mitmproxy,
enable it on a per-page basis and document the specific reason in
`CORTI_MANUAL_OBSERVATION_LOG.md`.
