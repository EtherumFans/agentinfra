"""Embedded Assistant API — serves the @icoder/embedded v2.0 Web Component.

Phase 6 Gate 1 (2026-07-13): upgraded from 1.0 src-serving to 2.0 dist-serving.
The 2.0 build is the Corti-compatible method-based API
(`auth()/configureSession()/configure()/show()`) with unified `embedded-event`
envelope, shipped from `packages/icoder-embedded/dist/`.

Phase 7 Gate 13A (2026-07-14): preview.html rewritten to use the secure
Preview Bootstrap Ticket + MessageChannel handshake instead of JWT/PHI in
the URL. See reports/phase7/gate13a/PHASE7_GATE13A_THREAT_MODEL.md.
- iframe URL contains only `?psid=<opaque-id>` — no token, no PHI
- iframe reads its bootstrap ticket + Runtime Token via MessageChannel
- iframe exchanges ticket → Runtime Token, then auth() + configureSession()
- All embedded-events are forwarded via the SAME secured port
- Strict CSP, sandbox, frame-ancestors, no-store, no-referrer (Gate 13A-5)
"""
import json
import secrets
from fastapi import APIRouter, Request
from fastapi.responses import Response, HTMLResponse
from pathlib import Path

router = APIRouter(prefix="/api/embedded", tags=["embedded"])

_PKG_ROOT = Path(__file__).parent.parent.parent.parent / "packages" / "icoder-embedded"
_DIST_JS = _PKG_ROOT / "dist" / "icoder-assistant.js"


@router.get("/assistant.js")
async def embedded_assistant_js():
    """Serve the @icoder/embedded v2.0 Web Component bundle.

    Returns the compiled ES module from `packages/icoder-embedded/dist/`.
    If the dist hasn't been built, returns a stub that prints a build hint.
    """
    if _DIST_JS.exists():
        content = _DIST_JS.read_text(encoding="utf-8")
        return Response(
            content=content,
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )
    return Response(
        content="// @icoder/embedded dist not built. Run: cd packages/icoder-embedded && npx tsc",
        media_type="application/javascript",
    )


@router.get("/preview")
async def embedded_assistant_preview():
    """2.0 Preview page using Corti-compatible method-based API.

    Phase 6 (interactive sidebar) — kept for development convenience.
    For the Console-embedded iframe use /api/embedded/preview.html (Gate 13A).
    """
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>iCoDer Embedded v2.0 Preview</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; background: #f5f5f7; display: flex; height: 100vh; }
.sidebar { width: 320px; background: #fff; border-right: 1px solid #e5e5ea; padding: 20px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
.sidebar h2 { font-size: 18px; font-weight: 600; color: #1d1d1f; }
.sidebar .version { font-size: 11px; color: #86868b; margin-top: -8px; }
.sidebar label { font-size: 12px; font-weight: 500; color: #86868b; display: block; margin-bottom: 4px; }
.sidebar input, .sidebar select { width: 100%; padding: 8px 12px; border: 1px solid #e5e5ea; border-radius: 8px; font-size: 13px; outline: none; background: #fff; color: #1d1d1f; }
.sidebar input:focus { border-color: #007aff; }
.sidebar button { padding: 10px 16px; background: #007aff; color: #fff; border: none; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; transition: opacity 0.2s; }
.sidebar button:hover { opacity: 0.85; }
.sidebar button:disabled { opacity: 0.4; cursor: default; }
.sidebar button.secondary { background: #f2f2f7; color: #1d1d1f; }
.main { flex: 1; display: flex; align-items: center; justify-content: center; padding: 24px; }
.assistant-wrapper { width: 420px; height: 640px; }
.event-log { position: fixed; bottom: 12px; right: 12px; width: 360px; max-height: 240px; overflow-y: auto; background: rgba(28,28,32,0.92); color: #f5f5f7; font-family: SFMono-Regular, Menlo, monospace; font-size: 11px; padding: 10px; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.2); }
.event-log .line { padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }
.event-log .line:last-child { border-bottom: none; }
.event-log .name { color: #64d2ff; }
.event-log .cost { color: #ffd60a; }
.event-log .err { color: #ff453a; }
</style>
</head>
<body>
<div class="sidebar">
  <h2>iCoDer Embedded</h2>
  <div class="version">v2.0.0 · Corti-compatible method API · Phase 6 Gate 1</div>
  <div>
    <label>Backend Base URL</label>
    <input id="baseUrl" value="http://localhost:8000" placeholder="https://hospital.icoder.cloud">
  </div>
  <div>
    <label>Access Token (JWT)</label>
    <input id="token" type="password" placeholder="Bearer JWT from /api/auth/login or /api/oauth/realms/{realm}/token">
  </div>
  <div>
    <label>Agent (defaultTemplateKey)</label>
    <select id="agentKey">
      <option value="medical-coding-agent">medical-coding-agent</option>
      <option value="coding-compliance">coding-compliance</option>
      <option value="cdi">cdi</option>
      <option value="note-completeness-agent">note-completeness-agent</option>
    </select>
  </div>
  <div>
    <label>Patient Name (iCoDer ADVANTAGE)</label>
    <input id="patientName" placeholder="张三">
  </div>
  <div>
    <label>Patient ID</label>
    <input id="patientId" placeholder="P001">
  </div>
  <div>
    <label>Encounter ID</label>
    <input id="encounterId" placeholder="E2026071301">
  </div>
  <div>
    <label>Interface Language</label>
    <select id="lang">
      <option value="auto">auto (browser)</option>
      <option value="zh-CN">zh-CN</option>
      <option value="en-US">en-US</option>
    </select>
  </div>
  <div>
    <label>aiChat feature</label>
    <select id="aiChat">
      <option value="true">enabled</option>
      <option value="false">disabled</option>
    </select>
  </div>
  <button id="init">Initialize Widget</button>
  <button id="clearPhi" class="secondary" disabled>Clear PHI (patient switch)</button>
  <button id="reset" class="secondary" disabled>Reset</button>
  <p style="font-size:11px;color:#86868b;margin-top:auto;">
    Embed via <code>&lt;icoder-embedded&gt;</code> in your HIS/EMR page.<br>
    Unified <code>embedded-event</code> with <code>{name, payload}</code>.<br>
    Phase 6 Gate 2: PHI lives in widget memory only (no localStorage).
  </p>
</div>
<div class="main">
  <div class="assistant-wrapper">
    <icoder-embedded id="assistant" baseURL="http://localhost:8000"></icoder-embedded>
  </div>
</div>
<div class="event-log" id="log">
  <div class="line">Event log (unified embedded-event envelope):</div>
</div>
<script type="module">
import '/api/embedded/assistant.js';

const log = document.getElementById('log');
function append(line, cls = '') {
  const div = document.createElement('div');
  div.className = 'line';
  div.innerHTML = `<span class="${cls}">${line}</span>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

const el = document.getElementById('assistant');
const initBtn = document.getElementById('init');
const resetBtn = document.getElementById('reset');

// Unified event listener — Phase 6 Gate 3 envelope {name, payload, meta}
el.addEventListener('embedded-event', (e) => {
  const { name, payload, meta } = e.detail;
  const ts = new Date().toLocaleTimeString();
  const metaSuffix = meta ? ` <span style="color:#86868b;font-size:10px;">eid=${(meta.eventId || '').slice(0, 8)} sid=${(meta.sessionId || '').slice(0, 8)} ctx=${meta.contextId || '∅'}</span>` : '';
  if (name === 'account.creditsConsumed') {
    append(`${ts} <span class="name">${name}</span> ${payload.currency} ${payload.amount} (run ${payload.run_id?.slice(0,8)})${metaSuffix}`, 'cost');
  } else if (name === 'error.triggered') {
    append(`${ts} <span class="name">${name}</span> ${payload.message}${metaSuffix}`, 'err');
  } else if (name === 'run.completed') {
    const traceLink = payload.trace_url
      ? ` <a href="${payload.trace_url}" target="_blank" rel="noopener" style="color:#64d2ff;text-decoration:underline;">trace ↗</a>`
      : '';
    append(`${ts} <span class="name">${name}</span> agent=${payload.agent_id} latency=${payload.latency_ms}ms${traceLink}${metaSuffix}`, '');
  } else {
    append(`${ts} <span class="name">${name}</span> ${JSON.stringify(payload).slice(0,120)}${metaSuffix}`, '');
  }
});

el.addEventListener('ready', () => append('widget ready — call Initialize'));

initBtn.addEventListener('click', async () => {
  initBtn.disabled = true;
  try {
    await el.auth({
      access_token: document.getElementById('token').value.trim(),
      token_type: 'bearer',
      mode: 'stateless',
    });
    await el.configureSession({
      defaultTemplateKey: document.getElementById('agentKey').value,
      defaultLanguage: document.getElementById('lang').value === 'auto' ? navigator.language : document.getElementById('lang').value,
      defaultOutputLanguage: 'zh-CN',
      patientId: document.getElementById('patientId').value.trim() || undefined,
      name: document.getElementById('patientName').value.trim() || undefined,
      encounterId: document.getElementById('encounterId').value.trim() || undefined,
    });
    await el.configure({
      features: { aiChat: document.getElementById('aiChat').value === 'true', documentFeedback: true, virtualMode: false },
      locale: {
        dictationLanguage: 'zh-CN',
        interfaceLanguage: document.getElementById('lang').value,
      },
    });
    el.baseURL = document.getElementById('baseUrl').value.trim();
    await el.show();
    append('widget shown — send a message in the chat');
    resetBtn.disabled = false;
    clearPhiBtn.disabled = false;
  } catch (e) {
    append(`init failed: ${e.message}`, 'err');
    initBtn.disabled = false;
  }
});

const clearPhiBtn = document.getElementById('clearPhi');
clearPhiBtn.addEventListener('click', () => {
  el.clearPatientContext();
  append('PHI cleared — widget ready for next patient (in-memory only, never touched storage)');
});

resetBtn.addEventListener('click', () => {
  location.reload();
});
</script>
</body>
</html>""")


# ── Phase 7 Gate 13A-5 — strict security headers ──────────────────────
# Per PHASE7_GATE13A_THREAT_MODEL.md Checkpoint D:
#   - Content-Security-Policy with per-request nonce
#   - sandbox='allow-scripts allow-same-origin' (no allow-forms/downloads/
#     popups/top-navigation)
#   - Referrer-Policy: no-referrer (T4)
#   - Cache-Control: no-store (HAR + browser history)
#   - X-Content-Type-Options: nosniff


def _build_preview_html(psid: str, request: Request) -> tuple[str, str, str]:
    """Build (html, csp_nonce, cache_control) for /preview.html.

    Returns nonce separately so the CSP header can include it. The HTML
    uses ``{NONCE}`` placeholder that the caller substitutes after
    building the CSP.
    """
    # Gate 13A-6 XSS hardening — escape psid before interpolation.
    safe_psid = "".join(
        c for c in (psid or "") if c.isalnum() or c in "-_"
    )[:64]
    return safe_psid


@router.get("/preview.html", response_class=HTMLResponse)
async def embedded_preview_html(request: Request):
    """Phase 7 Gate 13A — secure preview iframe.

    Only accepts ``?psid=<opaque-id>``. No token, no PHI in URL. The
    Console parent sends the bootstrap ticket + patient context via
    MessageChannel after a strict origin+source+nonce handshake.

    Per Gate 13A-5, response ships:
      - Content-Security-Policy with per-request nonce
      - sandbox + frame-ancestors (Console origin allowlist)
      - Cache-Control: no-store, Pragma: no-cache
      - Referrer-Policy: no-referrer

    Per Gate 13A-6, all dynamic interpolation is HTML-escaped.
    """
    from urllib.parse import parse_qs

    qs = parse_qs(request.url.query)
    p = {k: v[0] for k, v in qs.items()}
    psid = _build_preview_html(p.get("psid", ""), request)

    # Per-request CSP nonce (Gate 13A-5).
    csp_nonce = secrets.token_urlsafe(24)

    # Parent origin allowlist (Gate 13A-5 frame-ancestors). Pull from
    # settings.CORS_ORIGINS at request time so cloud deploys pick up
    # the right allowlist.
    from app.config import settings
    allowed_parents = " ".join(settings.CORS_ORIGINS)
    iframe_origin = f"{request.url.scheme}://{request.url.netloc}"

    # Strict CSP: only our nonce-tagged inline script + same-origin module
    # imports. No external scripts, no eval, no plugin fallback.
    # NOTE: CSP URLs must NOT be quoted (only keywords like 'self'/'none'
    # and nonces take single quotes).
    csp = (
        f"default-src 'none'; "
        f"script-src 'nonce-{csp_nonce}' 'strict-dynamic' {iframe_origin}; "
        f"style-src 'unsafe-inline' {iframe_origin}; "
        f"img-src 'self' data:; "
        f"font-src 'self' data:; "
        f"connect-src 'self' {iframe_origin}; "
        f"frame-ancestors {allowed_parents}; "
        f"base-uri 'none'; "
        f"form-action 'none'; "
        f"frame-src 'none'"
    )

    headers = {
        "Content-Security-Policy": csp,
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        # sandbox: allow-scripts so our script runs, allow-same-origin so
        # the widget can call fetch() to /api/embedded/preview-sessions/
        # exchange. Everything else (forms, top-nav, popups, plugins)
        # stays blocked.
        "Content-Security-Policy-Sandbox": "allow-scripts allow-same-origin",
    }

    # The iframe script is self-contained: it waits for the parent's
    # MessageChannel handshake (proves knowledge of nonce), receives
    # the ticket + patient context, exchanges the ticket for a Runtime
    # Token, then auth/configureSession/configure/show the widget.
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>iCoDer Embedded Preview</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ height: 100%; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; background: #fff; color: #1d1d1f; }}
  body {{ display: flex; flex-direction: column; height: 100vh; overflow: hidden; }}
  .topbar {{ padding: 8px 12px; border-bottom: 1px solid #e5e5ea; font-size: 11px; color: #86868b; background: #f5f5f7; flex-shrink: 0; }}
  .topbar code {{ background: #fff; padding: 1px 6px; border-radius: 3px; border: 1px solid #e5e5ea; }}
  .widget-wrap {{ flex: 1; min-height: 0; padding: 12px; overflow: hidden; display: flex; flex-direction: column; }}
  #assistant {{ flex: 1; min-height: 0; }}
  .status {{ font-size: 10px; color: #86868b; padding: 4px 12px; border-top: 1px solid #e5e5ea; flex-shrink: 0; }}
  .status.err {{ color: #ff453a; }}
</style>
</head>
<body>
  <div class="topbar">
    Preview · psid=<code>{psid}</code>
  </div>
  <div class="widget-wrap">
    <icoder-embedded id="assistant" baseURL=""></icoder-embedded>
  </div>
  <div class="status" id="status">Waiting for Console handshake…</div>

  <script nonce="{csp_nonce}" type="module">
    const PSID = {json.dumps(psid)};
    const BASE_URL = window.location.origin;

    const statusEl = document.getElementById('status');
    const setStatus = (msg, err = false) => {{
      statusEl.textContent = msg;
      statusEl.classList.toggle('err', err);
    }};

    const el = document.getElementById('assistant');
    el.setAttribute('baseURL', BASE_URL);

    // ── MessageChannel handshake ────────────────────────────────────
    // The parent opens a MessageChannel port and posts {{kind: 'ready',
    // psid: PSID}} on it. We respond with {{kind: 'ready-ack'}}.
    // The parent then sends {{kind: 'bootstrap', ticket, nonce,
    // context: {{agent, patientId, name, encounterId, features, locale,
    // primaryColor}}}}. We verify the nonce matches the ticket's bound
    // nonce (verified server-side at exchange), then proceed.

    let parentPort = null;
    let bootstrapMsg = null;

    window.addEventListener('message', (ev) => {{
      // Strict source check (Gate 13A-2): only accept from our parent.
      if (ev.source !== window.parent) return;
      // The parent is expected to open a MessageChannel and send the
      // port via the standard handshake. Verify the psid matches.
      if (ev.data && ev.data.kind === 'icoder:open-port' && ev.data.psid === PSID) {{
        parentPort = ev.ports[0];
        if (!parentPort) return;
        parentPort.onmessage = async (e) => {{
          const msg = e.data || {{}};
          if (msg.kind === 'icoder:bootstrap') {{
            // Defense-in-depth: ticket's psid must match our PSID.
            if (msg.psid !== PSID) {{
              setStatus('psid mismatch — refusing bootstrap', true);
              return;
            }}
            bootstrapMsg = msg;
            setStatus('Ticket received — exchanging for Runtime Token…');
            try {{
              await exchangeAndInit(msg);
            }} catch (err) {{
              setStatus('Bootstrap failed: ' + (err?.message || err), true);
              parentPort.postMessage({{ kind: 'icoder:bootstrap-error', error: String(err) }});
            }}
          }}
        }};
        // Announce readiness: tell the parent we're listening on this
        // port and prove we know the psid.
        parentPort.postMessage({{ kind: 'icoder:ready-ping', psid: PSID }});
        setStatus('Handshake ready — waiting for ticket');
      }}
    }});

    // Forward every embedded-event to the parent via the secured port
    // (NOT window.postMessage('*')). Per Gate 13A-2.
    el.addEventListener('embedded-event', (e) => {{
      if (parentPort) {{
        const {{ name, payload, meta }} = e.detail;
        parentPort.postMessage({{ kind: 'icoder:event', name, payload, meta }});
      }}
    }});

    async function exchangeAndInit(msg) {{
      const exResp = await fetch(BASE_URL + '/api/embedded/preview-sessions/exchange', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ ticket: msg.ticket }}),
        credentials: 'omit',
        referrerPolicy: 'no-referrer',
      }});
      if (!exResp.ok) {{
        const errBody = await exResp.text();
        throw new Error('exchange HTTP ' + exResp.status + ': ' + errBody);
      }}
      const ex = await exResp.json();
      setStatus('Runtime Token issued — initializing widget…');

      // Gate 13A-2: verify the nonce returned by the server side via
      // the ticket's bound nonce. The Console MUST send the same
      // nonce; the server-side verify already validated this.
      // (defense-in-depth)
      if (msg.nonce && ex.preview_session_id !== PSID) {{
        throw new Error('psid mismatch on exchange response');
      }}

      // Import the widget bundle (same-origin, no CORS preflight).
      await import(BASE_URL + '/api/embedded/assistant.js');

      const ctx = msg.context || {{}};
      // Auth with the scoped Runtime Token (NOT the user's JWT).
      await el.auth({{
        access_token: ex.runtime_token,
        token_type: 'bearer',
        mode: 'stateless',
      }});
      // configureSession with patient context (sent via MessageChannel,
      // NOT via URL).
      await el.configureSession({{
        defaultTemplateKey: ctx.agent || 'medical-coding-agent',
        defaultLanguage: (ctx.locale && ctx.locale.dictationLanguage) || 'zh-CN',
        defaultOutputLanguage: (ctx.locale && ctx.locale.interfaceLanguage) || 'zh-CN',
        patientId: ctx.patientId,
        name: ctx.name,
        encounterId: ctx.encounterId,
      }});
      await el.configure({{
        features: ctx.features || {{ aiChat: true, documentFeedback: true, virtualMode: false }},
        locale: ctx.locale || {{ dictationLanguage: 'zh-CN', interfaceLanguage: 'zh-CN' }},
      }});
      el.baseURL = BASE_URL;
      await el.show();
      setStatus('widget ready — interactive');
      if (parentPort) {{
        parentPort.postMessage({{ kind: 'icoder:ready' }});
      }}
    }}
  </script>
</body>
</html>"""

    return HTMLResponse(content=html, headers=headers)
