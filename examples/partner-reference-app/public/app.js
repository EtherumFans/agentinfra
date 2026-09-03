// Phase 7 Gate 12 — partner reference app frontend.
//
// Bootstraps the iCoDer embedded widget using a token obtained from the
// partner's own backend (server-side client_credentials exchange).
// Demonstrates: token exchange, widget init, patient context switching,
// unified event handling, trace_url capture.

// Load server-generated config first
try {
  await import('/config.js');
} catch (e) {
  console.warn('[partner-ref-app] /config.js load failed; using defaults', e);
}

const cfg = window.icoderPartnerConfig || {
  baseUrl: window.location.origin,
  agentRef: 'medical-coding-agent',
  needsTokenFromServer: true,
};

document.getElementById('baseUrl').value = cfg.baseUrl;
document.getElementById('agentRef').value = cfg.agentRef;

// Stamp baseURL on widget element before importing the bundle
const widget = document.getElementById('assistant');
widget.setAttribute('baseURL', cfg.baseUrl);

// Load iCoDer embedded bundle from iCoDer backend (not this partner server)
await import(`${cfg.baseUrl}/api/embedded/assistant.js`);

// ─── event log helpers ─────────────────────────────────────────────────
const logEl = document.getElementById('log');
function append(line, cls = '') {
  const div = document.createElement('div');
  div.className = 'line';
  div.innerHTML = `<span class="${cls}">${line}</span>`;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

const verified = new Set();
function markVerified(item) {
  verified.add(item);
  document.getElementById('verifiedList').innerHTML =
    `<strong style="color:#30d158;">已验证 (${verified.size}):</strong><br>` +
    [...verified].map(v => `✓ ${v}`).join('<br>');
}

// ─── unified event listener (Phase 6 envelope) ─────────────────────────
widget.addEventListener('embedded-event', (e) => {
  const { name, payload, meta } = e.detail;
  const ts = new Date().toLocaleTimeString();
  const metaSuffix = meta ? ` <span class="meta">eid=${(meta.eventId || '').slice(0, 8)} sid=${(meta.sessionId || '').slice(0, 8)} ctx=${meta.contextId || '∅'}</span>` : '';

  if (name === 'run.completed') {
    const trace = payload.trace_url
      ? ` <a href="${payload.trace_url}" target="_blank" rel="noopener" style="color:#64d2ff;">trace ↗</a>`
      : '';
    append(`${ts} <span class="name">${name}</span> agent=${payload.agent_id} latency=${payload.latency_ms}ms${trace}${metaSuffix}`, 'ok');
    markVerified('run.completed with agent_id + latency_ms');
    if (payload.trace_url) markVerified('signed trace_url (Gate 7)');
  } else if (name === 'account.creditsConsumed') {
    append(`${ts} <span class="name">${name}</span> ${payload.currency} ${payload.amount}${metaSuffix}`, 'cost');
    markVerified('account.creditsConsumed with CNY amount');
  } else if (name === 'error.triggered') {
    append(`${ts} <span class="name">${name}</span> ${payload.message}${metaSuffix}`, 'err');
  } else if (name === 'patient.context.cleared') {
    append(`${ts} <span class="name">${name}</span> reason=${payload.reason}${metaSuffix}`, 'ok');
    markVerified('patient.context.cleared emitted (Gate 11)');
  } else if (name === 'session.cleared') {
    append(`${ts} <span class="name">${name}</span> reason=${payload.reason}${metaSuffix}`, 'ok');
    markVerified('session.cleared emitted (Gate 11)');
  } else {
    append(`${ts} <span class="name">${name}</span>${metaSuffix}`, '');
  }
});

widget.addEventListener('ready', () => {
  append('widget ready');
  markVerified('widget ready event');
});

// ─── init: server-side token exchange ─────────────────────────────────
async function exchangeToken() {
  append('requesting token from partner server /token …');
  const resp = await fetch('/token');
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(`/token failed (${resp.status}): ${body.message || 'unknown'}`);
  }
  const { access_token, token_type, expires_in } = await resp.json();
  append(`token received (expires_in=${expires_in}s)`, 'ok');
  markVerified('server-side client_credentials exchange');
  return access_token;
}

document.getElementById('init').addEventListener('click', async () => {
  const btn = document.getElementById('init');
  btn.disabled = true;
  btn.textContent = '运行中…';
  try {
    // Step 1: server-side token exchange
    let token;
    try {
      token = await exchangeToken();
    } catch (e) {
      append(`token exchange failed — falling back to Console JWT mode. ${e.message}`, 'err');
      // Fallback: ask user to paste a Console JWT directly
      token = prompt('Paste a Console JWT (dev fallback):');
      if (!token) throw new Error('no token available');
    }

    // Step 2: widget auth + configure
    await widget.auth({ access_token: token, token_type: 'bearer', mode: 'stateless' });
    markVerified('widget.auth() accepts token');

    await widget.configureSession({
      defaultTemplateKey: document.getElementById('agentRef').value,
      defaultLanguage: 'zh-CN',
      defaultOutputLanguage: 'zh-CN',
      patientId: document.getElementById('patientId').value,
      name: document.getElementById('patientName').value,
      encounterId: document.getElementById('encounterId').value,
    });
    markVerified('configureSession sets patient context');

    await widget.configure({
      features: { aiChat: true, documentFeedback: true, virtualMode: false },
      locale: { dictationLanguage: 'zh-CN', interfaceLanguage: 'zh-CN' },
    });
    widget.baseURL = cfg.baseUrl;
    await widget.show();

    append('widget initialized — try the buttons below', 'ok');
    document.getElementById('switchPatient').disabled = false;
    document.getElementById('clearSession').disabled = false;
  } catch (e) {
    append(`init failed: ${e.message}`, 'err');
    btn.disabled = false;
    btn.textContent = '重试';
  }
});

// ─── patient switch (with clearPatientContext first) ──────────────────
let switchCount = 0;
document.getElementById('switchPatient').addEventListener('click', async () => {
  switchCount += 1;
  append(`── switching patient (iteration ${switchCount}) ──`, 'name');

  // CRITICAL: clear before re-configuring, otherwise cross-patient warn fires
  widget.clearPatientContext();

  // Rotate to the next patient in a small fixture list
  const patients = [
    { patientId: 'P-2026-001', name: '张三', encounterId: 'E-20260713-001' },
    { patientId: 'P-2026-002', name: '李四', encounterId: 'E-20260713-002' },
    { patientId: 'P-2026-003', name: '王五', encounterId: 'E-20260713-003' },
  ];
  const next = patients[switchCount % patients.length];

  document.getElementById('patientId').value = next.patientId;
  document.getElementById('patientName').value = next.name;
  document.getElementById('encounterId').value = next.encounterId;

  await widget.configureSession({
    defaultTemplateKey: document.getElementById('agentRef').value,
    defaultLanguage: 'zh-CN',
    defaultOutputLanguage: 'zh-CN',
    patientId: next.patientId,
    name: next.name,
    encounterId: next.encounterId,
  });
  append(`patient switched cleanly → ${next.name} (${next.patientId})`, 'ok');
});

// ─── clear session ────────────────────────────────────────────────────
document.getElementById('clearSession').addEventListener('click', () => {
  widget.clearSession();
  append('session cleared — auth + patient context + messages all flushed', 'ok');
  document.getElementById('switchPatient').disabled = true;
  document.getElementById('clearSession').disabled = true;
  document.getElementById('init').disabled = false;
  document.getElementById('init').textContent = '重新初始化';
});
