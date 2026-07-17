/**
 * <icoder-embedded> — Embeddable AI coding assistant Web Component.
 *
 * Phase 5 A4 (2026-07-10): refactored from attribute-based config to
 * Corti-compatible method-based API (`auth()/configureSession()/configure()/
 * show()/addEventListener('embedded-event')`). Tag renamed from
 * `<icoder-assistant>` to `<icoder-embedded>` to match Corti's
 * `<corti-embedded>` pattern. The old tag is kept as a deprecated alias
 * (prints a console warning) for the 2.0.x deprecation window.
 *
 * Usage (Corti-compatible):
 *   <icoder-embedded id="icoder-assistant" baseURL="http://localhost:8000"></icoder-embedded>
 *   <script type="module">
 *     import '@icoder/embedded';
 *     const assistant = document.getElementById('icoder-assistant');
 *     assistant.addEventListener('ready', async () => {
 *       await assistant.auth({
 *         access_token: 'YOUR_ACCESS_TOKEN',
 *         refresh_token: 'YOUR_REFRESH_TOKEN',  // optional
 *         token_type: 'bearer',
 *         mode: 'stateless',  // or 'session'
 *       });
 *       await assistant.configureSession({
 *         defaultTemplateKey: 'medical-coding-agent',  // agent_id
 *         defaultLanguage: 'zh-CN',
 *         defaultOutputLanguage: 'zh-CN',
 *         // iCoDer ADVANTAGE: explicit patient context (Corti uses template key only)
 *         patientId: 'P001', name: '张三', encounterId: 'E2026071001',
 *       });
 *       await assistant.configure({
 *         features: { aiChat: true, documentFeedback: true, virtualMode: false },
 *         locale: { dictationLanguage: 'zh-CN', interfaceLanguage: 'auto' },
 *       });
 *       await assistant.show();
 *     });
 *     assistant.addEventListener('embedded-event', (e) => {
 *       const { name, payload } = e.detail;
 *       switch (name) {
 *         case 'account.creditsConsumed': console.log('Cost:', payload); break;
 *         case 'run.completed': console.log('Run done:', payload); break;  // iCoDer-specific
 *         case 'error.triggered': console.error('Error:', payload); break;
 *         case 'patient.context.cleared': console.log('PHI flushed'); break;  // Phase 6 Gate 2
 *         case 'session.cleared': console.log('Full reset'); break;          // Phase 6 Gate 2
 *         default: console.log(name, payload);
 *       }
 *     });
 *   </script>
 *
 * iCoDer ADVANTAGE methods kept (Corti does not have these):
 *   - setPatientContext({ patientId, name, encounterId })
 *   - clearPatientContext()              // Phase 6 Gate 2 — flush PHI on patient switch
 *   - clearSession()                     // Phase 6 Gate 2 — full reset (auth + messages + PHI)
 *   - ask(question)
 * See memory `feedback_corti_alignment.md` ("勿为像 Corti 删 iCoDer 差异化能力").
 *
 * Migration guide: see packages/icoder-embedded/MIGRATION-2.0.md.
 */
const TEMPLATE = `
<style>
:host {
  display: block;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
  --ic-primary: #007aff;
  --ic-bg: #ffffff;
  --ic-border: #e5e5ea;
  --ic-text: #1d1d1f;
  --ic-subtext: #86868b;
  --ic-bubble-user: #007aff;
  --ic-bubble-user-text: #ffffff;
  --ic-bubble-agent: #f2f2f7;
  --ic-bubble-agent-text: #1d1d1f;
  --ic-radius: 16px;
  --ic-radius-sm: 8px;
  --ic-shadow: 0 2px 12px rgba(0,0,0,0.08);
}
:host([theme="dark"]) {
  --ic-bg: #1c1c1e;
  --ic-border: #38383a;
  --ic-text: #f5f5f7;
  --ic-subtext: #98989d;
  --ic-bubble-agent: #2c2c2e;
  --ic-bubble-agent-text: #f5f5f7;
}

.container {
  display: flex; flex-direction: column; height: 100%;
  background: var(--ic-bg); border-radius: var(--ic-radius);
  box-shadow: var(--ic-shadow); overflow: hidden;
  font-size: 14px; color: var(--ic-text);
}
.header {
  padding: 12px 16px; border-bottom: 1px solid var(--ic-border);
  display: flex; align-items: center; gap: 8px;
}
.header .logo { width: 20px; height: 20px; border-radius: 6px; background: var(--ic-primary); display: flex; align-items: center; justify-content: center; color: #fff; font-size: 11px; font-weight: 600; }
.header .title { font-weight: 600; font-size: 13px; }
.header .badge { font-size: 10px; color: var(--ic-subtext); margin-left: auto; }
.patient-bar {
  padding: 8px 16px; background: #f9f9fb; border-bottom: 1px solid var(--ic-border);
  font-size: 12px; display: none; align-items: center; gap: 8px;
}
.patient-bar.visible { display: flex; }
.patient-bar .pt-name { font-weight: 500; }
.patient-bar .pt-id { color: var(--ic-subtext); font-family: monospace; }
.messages {
  flex: 1; overflow-y: auto; padding: 12px 16px;
  display: flex; flex-direction: column; gap: 8px;
}
.message {
  max-width: 85%; padding: 10px 14px; border-radius: var(--ic-radius-sm);
  font-size: 13px; line-height: 1.5; word-break: break-word;
}
.message.user {
  align-self: flex-end; background: var(--ic-bubble-user);
  color: var(--ic-bubble-user-text); border-bottom-right-radius: 4px;
}
.message.agent {
  align-self: flex-start; background: var(--ic-bubble-agent);
  color: var(--ic-bubble-agent-text); border-bottom-left-radius: 4px;
}
.message.agent pre { font-size: 11px; background: rgba(0,0,0,0.04); padding: 8px; border-radius: 6px; overflow-x: auto; margin: 4px 0 0; }
.input-area {
  padding: 8px 12px; border-top: 1px solid var(--ic-border);
  display: flex; gap: 8px; align-items: flex-end;
}
.input-area textarea {
  flex: 1; border: 1px solid var(--ic-border); border-radius: 20px;
  padding: 8px 14px; font-size: 13px; resize: none; outline: none;
  background: var(--ic-bg); color: var(--ic-text);
  font-family: inherit; max-height: 80px; line-height: 1.4;
}
.input-area textarea:focus { border-color: var(--ic-primary); }
.input-area button {
  width: 36px; height: 36px; border-radius: 50%; border: none;
  background: var(--ic-primary); color: #fff; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: opacity 0.2s;
}
.input-area button:disabled { opacity: 0.3; cursor: default; }
.input-area button svg { width: 16px; height: 16px; }
.quick-actions {
  display: flex; gap: 6px; padding: 8px 16px; flex-wrap: wrap;
  border-top: 1px solid var(--ic-border);
}
.quick-actions button {
  font-size: 11px; padding: 4px 10px; border-radius: 12px;
  border: 1px solid var(--ic-border); background: var(--ic-bg);
  color: var(--ic-primary); cursor: pointer; transition: all 0.15s;
}
.quick-actions button:hover { background: var(--ic-primary); color: #fff; border-color: var(--ic-primary); }
.loading { display: flex; gap: 4px; padding: 8px 16px; }
.loading span { width: 6px; height: 6px; border-radius: 50%; background: var(--ic-subtext); animation: bounce 1.4s infinite ease-in-out both; }
.loading span:nth-child(1) { animation-delay: -0.32s; }
.loading span:nth-child(2) { animation-delay: -0.16s; }
@keyframes bounce { 0%,80%,100% { transform: scale(0); } 40% { transform: scale(1); } }
</style>

<div class="container">
  <div class="header">
    <div class="logo">iC</div>
    <div class="title">iCoDer Assistant</div>
    <div class="badge" data-ref></div>
  </div>
  <div class="patient-bar" data-patient-bar>
    <span>👤</span>
    <span class="pt-name" data-pt-name></span>
    <span class="pt-id" data-pt-id></span>
  </div>
  <div class="messages" data-messages></div>
  <div class="loading" data-loading style="display:none"><span></span><span></span><span></span></div>
  <div class="quick-actions" data-actions>
    <button data-action="review">审核编码</button>
    <button data-action="gaps">检查文档缺口</button>
    <button data-action="drg">DRG 分析</button>
  </div>
  <div class="input-area">
    <textarea rows="1" placeholder="输入消息..." data-input></textarea>
    <button data-send>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
    </button>
  </div>
</div>
`;
// ── Web Component ───────────────────────────────────────────────────────
class iCoDerEmbedded extends HTMLElement {
    static get observedAttributes() {
        // baseURL is the only attribute in the new API (it's connection config,
        // not auth/session config — those go through methods). The legacy
        // attribute-based keys are still observed for the 2.0.x deprecation window.
        return ['baseURL', 'base-url', 'access-token', 'agent-ref', 'theme', 'locale'];
    }
    constructor() {
        super();
        // Auth + config state (Corti-compatible method-based API)
        this._auth = null;
        this._sessionConfig = {};
        this._config = {};
        // iCoDer ADVANTAGE: explicit patient context (kept; not in Corti API)
        this._patientContext = {};
        // Connection config
        this._baseUrl = '';
        this._contextId = '';
        // Visibility (hidden until show() is called, matching Corti pattern)
        this._visible = false;
        // ── Unified event emission (Corti-compatible) ──────────────────────────
        this._readyEmitted = false;
        this._shadow = this.attachShadow({ mode: 'open' });
        this._shadow.innerHTML = TEMPLATE;
        // Phase 6 Gate 3 — sessionId stable per widget instance. contextId
        // starts empty (no patient set yet) and is updated by
        // configureSession/setPatientContext/clearPatientContext/clearSession.
        this._sessionId = (typeof crypto !== 'undefined' && crypto.randomUUID)
            ? crypto.randomUUID()
            : `sid-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
        // Note: per custom element spec, constructor() must not set attributes
        // (including style). The initial visibility:hidden is set via
        // connectedCallback() instead.
    }
    connectedCallback() {
        // Initial hidden state — matches Corti pattern where the widget stays
        // invisible until configuration is complete. Set here (not in constructor)
        // because the custom element spec forbids setting attributes in constructor.
        if (!this._visible) {
            this.style.display = 'none';
        }
        // Legacy attribute-based config (deprecated in 2.0, removed in 2.1)
        const baseUrlAttr = this.getAttribute('base-url') || this.getAttribute('baseurl') || this.getAttribute('baseURL') || '';
        const tokenAttr = this.getAttribute('access-token') || '';
        const agentRefAttr = this.getAttribute('agent-ref') || '';
        const themeAttr = this.getAttribute('theme') || '';
        if (baseUrlAttr)
            this._baseUrl = baseUrlAttr;
        if (tokenAttr) {
            console.warn('[icoder-embedded] attribute "access-token" is deprecated; use assistant.auth({access_token, ...}) instead. ' +
                'See MIGRATION-2.0.md. Will be removed in 2.1.');
            this._auth = { access_token: tokenAttr, token_type: 'bearer', mode: 'stateless' };
        }
        if (agentRefAttr) {
            console.warn('[icoder-embedded] attribute "agent-ref" is deprecated; use assistant.configureSession({defaultTemplateKey: ...}) instead. ' +
                'See MIGRATION-2.0.md. Will be removed in 2.1.');
            this._sessionConfig.defaultTemplateKey = agentRefAttr;
        }
        if (themeAttr) {
            this._shadow.host.classList.toggle('dark', themeAttr === 'dark');
        }
        this._setupUIHandlers();
        this._renderBadge();
        // Auto-show if auth was provided via attribute (backward-compat).
        // For the new method-based API, the consumer must call show() explicitly.
        if (this._auth) {
            void this.show();
        }
        else {
            this._emitReady();
        }
    }
    attributeChangedCallback(name, _old, _new) {
        if (name === 'access-token' && _new) {
            // Legacy path — deprecation warning already printed in connectedCallback
            this._auth = { access_token: _new, token_type: 'bearer', mode: 'stateless' };
        }
        if (name === 'agent-ref' && _new) {
            this._sessionConfig.defaultTemplateKey = _new;
            this._renderBadge();
        }
        if (name === 'base-url' || name === 'baseurl' || name === 'baseURL') {
            this._baseUrl = _new;
        }
        if (name === 'theme') {
            this._shadow.host.classList.toggle('dark', _new === 'dark');
        }
    }
    // ── Corti-compatible method-based API ─────────────────────────────────
    /**
     * Set auth credentials. Must be called before show() if not using
     * the deprecated access-token attribute.
     */
    async auth(opts) {
        this._auth = opts;
    }
    /**
     * Configure session-level defaults (agent + patient context).
     * iCoDer ADVANTAGE: patientId/name/encounterId as explicit fields
     * (Corti uses defaultTemplateKey only).
     */
    async configureSession(opts) {
        this._sessionConfig = { ...this._sessionConfig, ...opts };
        if (opts.patientId || opts.name || opts.encounterId) {
            if (this._patientContext.patientId && opts.patientId && this._patientContext.patientId !== opts.patientId) {
                console.warn(`[icoder-embedded] configureSession() called with a different patientId ` +
                    `(${opts.patientId}) without first calling clearPatientContext(). ` +
                    `Cross-patient PHI bleed risk — call clearPatientContext() on patient switch.`);
            }
            this._patientContext = {
                patientId: opts.patientId,
                name: opts.name,
                encounterId: opts.encounterId,
            };
            // Phase 6 Gate 3 — contextId follows the current patient. Stable
            // within one patient session, changes on switch, cleared on clear().
            this._contextId = opts.encounterId || opts.patientId || '';
            this._renderPatientBar();
        }
        this._renderBadge();
    }
    /**
     * Configure feature flags + locale (interface language).
     */
    async configure(opts) {
        this._config = { ...this._config, ...opts };
        // Apply theme based on interfaceLanguage (zh-CN / en-US / auto)
        const lang = opts.locale?.interfaceLanguage;
        if (lang && lang !== 'auto') {
            // Update quick-action labels + textarea placeholder
            this._applyInterfaceLanguage(lang);
        }
        // Toggle features (e.g. aiChat, documentFeedback)
        if (opts.features) {
            this._applyFeatures(opts.features);
        }
    }
    /**
     * Show the widget. Should be called after auth() + configureSession() +
     * configure(). If auth() was not called, prints a warning and the widget
     * will render but API calls will fail with 401.
     */
    async show() {
        if (!this._auth) {
            console.warn('[icoder-embedded] show() called before auth() — widget will render but API calls will fail.');
        }
        if (!this._baseUrl) {
            console.warn('[icoder-embedded] baseURL attribute not set — API calls will use relative path.');
        }
        this._visible = true;
        this.style.display = 'block';
        if (!this._readyEmitted) {
            this._emitReady();
            this._readyEmitted = true;
        }
    }
    // ── iCoDer ADVANTAGE methods (Corti does not have these) ──────────────
    /**
     * Set patient context explicitly. iCoDer-specific — Corti uses
     * configureSession({defaultTemplateKey}) instead.
     *
     * Phase 6 Gate 2 — PHI safety: patient context is held in-memory only.
     * It is NEVER written to localStorage, sessionStorage, or cookies.
     * When the host HIS/EMR switches patients, it MUST call
     * ``clearPatientContext()`` to flush the in-memory PHI. Otherwise the
     * previous patient's name/ID will leak into the next run's enriched
     * input prefix.
     */
    setPatientContext(ctx) {
        if (this._patientContext.patientId && ctx.patientId && this._patientContext.patientId !== ctx.patientId) {
            console.warn(`[icoder-embedded] setPatientContext() called with a different patientId ` +
                `(${ctx.patientId}) without first calling clearPatientContext(). ` +
                `Previous context (${this._patientContext.patientId}) is being overwritten. ` +
                `HIS/EMR hosts should call clearPatientContext() on patient switch ` +
                `to prevent cross-patient PHI bleed.`);
        }
        this._patientContext = ctx;
        this._contextId = ctx.encounterId || ctx.patientId || '';
        this._renderPatientBar();
    }
    /**
     * Clear patient context (PHI). MUST be called by HIS/EMR hosts when:
     *
     * 1. The user navigates to a different patient chart.
     * 2. The user logs out.
     * 3. The widget is being torn down (e.g. via ``element.remove()``).
     *
     * After this call, the widget's in-memory PHI (``patientId``, ``name``,
     * ``encounterId``) is set to ``{}`` and the patient bar is hidden.
     * Messages history is preserved (per Corti pattern); call
     * ``clearSession()`` to also clear messages + auth.
     */
    clearPatientContext() {
        this._patientContext = { patientId: undefined, name: undefined, encounterId: undefined };
        this._contextId = '';
        this._renderPatientBar();
        this._emitEmbeddedEvent('patient.context.cleared', { reason: 'host_invoked_clear' });
    }
    /**
     * Clear the full session: patient context + auth + agent config + message
     * history. Use this on logout or when reusing the widget for a different
     * user/agent pair. After this call, the widget returns to the
     * pre-``auth()`` state and ``show()`` must be called again to use it.
     */
    clearSession() {
        this._patientContext = { patientId: undefined, name: undefined, encounterId: undefined };
        this._contextId = '';
        this._auth = null;
        this._sessionConfig = {};
        this._config = {};
        this._renderPatientBar();
        this._renderBadge();
        const messages = this._shadow.querySelector('[data-messages]');
        if (messages)
            messages.innerHTML = '';
        this._emitEmbeddedEvent('session.cleared', { reason: 'host_invoked_clear' });
    }
    /**
     * Send a question to the agent. Shortcut for the user typing into the
     * input box. Returns the agent's response.
     */
    async ask(question) {
        this._addMessage('user', question);
        return this._callAgent(question);
    }
    _emitEmbeddedEvent(name, payload) {
        // Phase 6 Gate 3 — unified envelope with meta. Embedders use:
        //   meta.eventId   — dedup (idempotency)
        //   meta.timestamp — ordering across multiple widgets
        //   meta.sessionId — correlate events from one widget instance
        //   meta.contextId — PHI-scoped correlation (current patient)
        //   meta.version   — envelope schema version (currently '1.0')
        const meta = {
            version: '1.0',
            eventId: (typeof crypto !== 'undefined' && crypto.randomUUID)
                ? crypto.randomUUID()
                : `evt-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
            timestamp: new Date().toISOString(),
            sessionId: this._sessionId,
            contextId: this._contextId,
        };
        this.dispatchEvent(new CustomEvent('embedded-event', {
            bubbles: true, composed: true,
            detail: { name, payload, meta },
        }));
    }
    _emitReady() {
        this.dispatchEvent(new CustomEvent('ready', { bubbles: true, composed: true }));
    }
    // ── UI setup ──────────────────────────────────────────────────────────
    _setupUIHandlers() {
        const input = this._shadow.querySelector('[data-input]');
        const sendBtn = this._shadow.querySelector('[data-send]');
        const actions = this._shadow.querySelectorAll('[data-action]');
        sendBtn.addEventListener('click', () => this._send(input));
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this._send(input);
            }
        });
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 80) + 'px';
        });
        actions.forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.getAttribute('data-action') || '';
                const prompts = {
                    review: '请审核当前患者的编码，检查是否有错误、遗漏或合规风险。',
                    gaps: '请检查当前患者的病历文档完整性，列出缺失的关键信息。',
                    drg: '请分析当前患者的编码对 DRG 分组和医保支付的影响。',
                };
                const msg = prompts[action] || action;
                this._addMessage('user', msg);
                void this._callAgent(msg);
            });
        });
    }
    _renderBadge() {
        const badge = this._shadow.querySelector('[data-ref]');
        badge.textContent = this._sessionConfig.defaultTemplateKey || 'medical-coding-agent';
    }
    _renderPatientBar() {
        const bar = this._shadow.querySelector('[data-patient-bar]');
        const nameEl = this._shadow.querySelector('[data-pt-name]');
        const idEl = this._shadow.querySelector('[data-pt-id]');
        if (this._patientContext.name || this._patientContext.patientId) {
            bar.classList.add('visible');
            nameEl.textContent = this._patientContext.name || '';
            idEl.textContent = this._patientContext.patientId ? `#${this._patientContext.patientId}` : '';
        }
        else {
            bar.classList.remove('visible');
        }
    }
    _applyInterfaceLanguage(lang) {
        const input = this._shadow.querySelector('[data-input]');
        const actions = this._shadow.querySelectorAll('[data-action]');
        const labels = {
            'zh-CN': { placeholder: '输入消息...', review: '审核编码', gaps: '检查文档缺口', drg: 'DRG 分析' },
            'en-US': { placeholder: 'Type a message...', review: 'Review Codes', gaps: 'Check Doc Gaps', drg: 'DRG Analysis' },
        };
        const set = labels[lang] || labels['zh-CN'];
        input.placeholder = set.placeholder;
        actions.forEach(btn => {
            const action = btn.getAttribute('data-action') || '';
            if (set[action])
                btn.textContent = set[action];
        });
    }
    _applyFeatures(features) {
        const actions = this._shadow.querySelector('[data-actions]');
        // If aiChat is false, hide the input area + quick actions
        const inputArea = this._shadow.querySelector('.input-area');
        if (typeof features.aiChat === 'boolean') {
            inputArea.style.display = features.aiChat ? 'flex' : 'none';
            actions.style.display = features.aiChat ? 'flex' : 'none';
        }
    }
    // ── Messaging ─────────────────────────────────────────────────────────
    _addMessage(role, content) {
        const container = this._shadow.querySelector('[data-messages]');
        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.textContent = content;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        // iCoDer-specific event: notify host app that a message was rendered
        this._emitEmbeddedEvent('message.received', { role, content });
    }
    async _callAgent(input) {
        const loading = this._shadow.querySelector('[data-loading]');
        const sendBtn = this._shadow.querySelector('[data-send]');
        loading.style.display = 'flex';
        sendBtn.disabled = true;
        // Phase 6 Gate 3 — per-call AbortController. Default timeout 90s
        // (backend medical-coding corti_like_fast ~9s, medcoder_deep 30-60s+).
        // Embedders may override by setting the `request-timeout-ms` attribute.
        const timeoutMs = parseInt(this.getAttribute('request-timeout-ms') || '90000', 10);
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        try {
            if (!this._auth) {
                throw new Error('Not authenticated — call assistant.auth({access_token, ...}) before sending messages.');
            }
            // Build patient-enriched input (iCoDer ADVANTAGE)
            let enrichedInput = input;
            if (this._patientContext.name || this._patientContext.patientId) {
                enrichedInput = `[患者: ${this._patientContext.name || ''} ID:${this._patientContext.patientId || ''}]\n${input}`;
            }
            // Phase 5 B-2 AUDIT_BLOCKER_FIX #3: normalize full agent_ref
            // (e.g. `icoder/medical-coding-agent@2.0.0`) to the short agent_id
            // (`medical-coding-agent`) the backend route expects. Backend's route
            // pattern /api/v1/agents/{agent_id}/run treats %2F as a path separator
            // and 404s on the full ref. Mirrors the frontend normalize in
            // frontend/src/services/runtimeApi.ts:agentRun().
            const rawAgentId = this._sessionConfig.defaultTemplateKey || 'medical-coding-agent';
            const agentId = rawAgentId.split('/').pop().split('@')[0];
            const url = `${this._baseUrl}/api/v1/agents/${encodeURIComponent(agentId)}/run`;
            // Phase 6 Gate 3 — idempotency-key + 1 retry on transient errors.
            // Embedders can use the idempotency-key to safely retry a request
            // without re-charging (server-side dedup is Phase 7).
            const idempotencyKey = (typeof crypto !== 'undefined' && crypto.randomUUID)
                ? crypto.randomUUID()
                : `idem-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
            const doFetch = async (attempt) => {
                return fetch(url, {
                    method: 'POST',
                    signal: controller.signal,
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `${this._auth.token_type || 'Bearer'} ${this._auth.access_token}`,
                        'Idempotency-Key': idempotencyKey,
                        'X-Attempt': String(attempt),
                    },
                    body: JSON.stringify({ input: { text: enrichedInput } }),
                });
            };
            let resp;
            try {
                resp = await doFetch(1);
            }
            catch (networkErr) {
                // Phase 6 Gate 3 — 1 automatic retry on network error (transient).
                // Only retried forAbortError-name!=='AbortError' (timeout) and
                // TypeError (most likely DNS/connection reset). 4xx/5xx HTTP responses
                // are NOT retried (they indicate server-side rejection that won't
                // change with a retry).
                if (controller.signal.aborted)
                    throw networkErr;
                try {
                    resp = await doFetch(2);
                }
                catch (retryErr) {
                    throw new Error(`Network error after retry: ${retryErr.message}`);
                }
            }
            clearTimeout(timeoutId);
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || err.error_reason || `HTTP ${resp.status}`);
            }
            const data = await resp.json();
            const output = data.summary || data.output || JSON.stringify(data.result || data, null, 2);
            this._addMessage('agent', output);
            // Emit unified embedded-event with run.completed + account.creditsConsumed
            // (Corti-compatible envelope: {name, payload})
            // Phase 6 Gate 5: include trace_id + trace_url so embedders can deep-link
            // to the iCoDer RunTrace viewer (frontend route, opened in a new tab).
            const traceUrl = data.trace_url
                ? `${this._baseUrl}${data.trace_url}`
                : '';
            this._emitEmbeddedEvent('run.completed', {
                run_id: data.run_id,
                agent_id: data.agent_id,
                trace_id: data.trace_id || '',
                trace_url: traceUrl,
                latency_ms: data.latency_ms,
                output,
                cost: data.cost,
            });
            if (data.cost && typeof data.cost.amount === 'number') {
                this._emitEmbeddedEvent('account.creditsConsumed', {
                    amount: data.cost.amount,
                    currency: data.cost.currency || 'CNY',
                    run_id: data.run_id,
                });
            }
            return data;
        }
        catch (e) {
            const isAbort = e.name === 'AbortError';
            const msg = isAbort
                ? `请求超时 (>${timeoutMs}ms)。请在 backend config 检查 agent runtime 模式或增加 request-timeout-ms 属性。`
                : e.message;
            this._addMessage('agent', `错误: ${msg}`);
            this._emitEmbeddedEvent('error.triggered', {
                message: msg,
                kind: isAbort ? 'timeout' : 'runtime',
                retriable: !isAbort,
            });
            throw e;
        }
        finally {
            clearTimeout(timeoutId);
            loading.style.display = 'none';
            sendBtn.disabled = false;
        }
    }
    _send(input) {
        const text = input.value.trim();
        if (!text)
            return;
        input.value = '';
        input.style.height = 'auto';
        this._addMessage('user', text);
        void this._callAgent(text);
    }
}
// Register the new primary tag. Also keep <icoder-assistant> as a deprecated
// alias so existing embeds keep working during the 2.0.x migration window.
//
// Chrome's CustomElementRegistry spec forbids using the same constructor for
// two different tag names ("this constructor has already been used with this
// registry"). So we create an anonymous subclass for the deprecated alias.
// See https://developer.mozilla.org/en-US/docs/Web/API/CustomElementRegistry/define
customElements.define('icoder-embedded', iCoDerEmbedded);
const _deprecatedAlias = customElements.get('icoder-assistant');
if (!_deprecatedAlias) {
    // Subclass so the registry sees a different constructor.
    class _iCoDerAssistantAlias extends iCoDerEmbedded {
    }
    customElements.define('icoder-assistant', _iCoDerAssistantAlias);
}
else if (typeof window !== 'undefined' && window.console && typeof window.console.warn === 'function') {
    console.warn('[icoder-embedded] <icoder-assistant> tag is a deprecated alias for <icoder-embedded>; please rename. Will be removed in 2.1.');
}
export { iCoDerEmbedded };
export default iCoDerEmbedded;
