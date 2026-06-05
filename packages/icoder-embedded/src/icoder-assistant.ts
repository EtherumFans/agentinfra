/**
 * <icoder-assistant> — Embeddable AI coding assistant Web Component.
 *
 * Usage:
 *   <icoder-assistant
 *     base-url="http://icoder-server:8000"
 *     access-token="<jwt>"
 *     agent-ref="medical-coding-agent-1.0.0"
 *     theme="light"
 *     locale="zh-CN"
 *   ></icoder-assistant>
 *
 * Events:
 *   coding.completed → { codes, review_id }
 *   error → { message }
 *   ready → {}
 *
 * Methods:
 *   element.setPatientContext({ patientId, name, encounterId })
 *   element.ask("这个患者的编码有什么问题?")
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

class iCoDerAssistant extends HTMLElement {
  private _baseUrl = '';
  private _token = '';
  private _agentRef = 'medical-coding-agent-1.0.0';
  private _patientContext: Record<string, string> = {};
  private _shadow: ShadowRoot;

  static get observedAttributes() {
    return ['base-url', 'access-token', 'agent-ref', 'theme', 'locale'];
  }

  constructor() {
    super();
    this._shadow = this.attachShadow({ mode: 'open' });
    this._shadow.innerHTML = TEMPLATE;
  }

  connectedCallback() {
    this._baseUrl = this.getAttribute('base-url') || '';
    this._token = this.getAttribute('access-token') || '';
    this._agentRef = this.getAttribute('agent-ref') || 'medical-coding-agent-1.0.0';

    const badge = this._shadow.querySelector('[data-ref]')!;
    badge.textContent = this._agentRef;

    // Setup event handlers
    const input = this._shadow.querySelector('[data-input]') as HTMLTextAreaElement;
    const sendBtn = this._shadow.querySelector('[data-send]')!;
    const actions = this._shadow.querySelectorAll('[data-action]');

    sendBtn.addEventListener('click', () => this._send(input));
    input.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this._send(input); }
    });
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 80) + 'px';
    });

    actions.forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.getAttribute('data-action') || '';
        const prompts: Record<string, string> = {
          review: '请审核当前患者的编码，检查是否有错误、遗漏或合规风险。',
          gaps: '请检查当前患者的病历文档完整性，列出缺失的关键信息。',
          drg: '请分析当前患者的编码对 DRG 分组和医保支付的影响。',
        };
        const msg = prompts[action] || action;
        this._addMessage('user', msg);
        this._callAgent(msg);
      });
    });

    this.dispatchEvent(new CustomEvent('ready', { bubbles: true, composed: true }));
  }

  attributeChangedCallback(name: string, _old: string, _new: string) {
    if (name === 'access-token') this._token = _new;
    if (name === 'agent-ref') this._agentRef = _new;
    if (name === 'base-url') this._baseUrl = _new;
    if (name === 'theme') {
      this._shadow!.host.classList.toggle('dark', _new === 'dark');
    }
  }

  // ── Public API ──

  setPatientContext(ctx: { patientId?: string; name?: string; encounterId?: string }) {
    this._patientContext = ctx;
    const bar = this._shadow.querySelector('[data-patient-bar]')!;
    const nameEl = this._shadow.querySelector('[data-pt-name]')!;
    const idEl = this._shadow.querySelector('[data-pt-id]')!;
    if (ctx.name || ctx.patientId) {
      bar.classList.add('visible');
      nameEl.textContent = ctx.name || '';
      idEl.textContent = ctx.patientId ? `#${ctx.patientId}` : '';
    }
  }

  async ask(question: string) {
    this._addMessage('user', question);
    await this._callAgent(question);
  }

  // ── Private ──

  private _addMessage(role: 'user' | 'agent', content: string) {
    const container = this._shadow.querySelector('[data-messages]')!;
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.textContent = content;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  private async _callAgent(input: string) {
    const loading = this._shadow.querySelector('[data-loading]') as HTMLElement;
    const sendBtn = this._shadow.querySelector('[data-send]') as HTMLButtonElement;
    loading.style.display = 'flex';
    sendBtn.disabled = true;

    try {
      // Build patient-enriched input
      let enrichedInput = input;
      if (this._patientContext.name || this._patientContext.patientId) {
        enrichedInput = `[患者: ${this._patientContext.name||''} ID:${this._patientContext.patientId||''}]\n${input}`;
      }

      const resp = await fetch(`${this._baseUrl}/api/runtime/agents/${encodeURIComponent(this._agentRef)}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${this._token}` },
        body: JSON.stringify({ input: enrichedInput }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }

      const data = await resp.json();
      const output = data.output || JSON.stringify(data.primary_diagnosis || data, null, 2);
      this._addMessage('agent', output);

      this.dispatchEvent(new CustomEvent('coding.completed', {
        bubbles: true, composed: true,
        detail: { codes: data, review_id: data.review_id },
      }));
    } catch (e: any) {
      this._addMessage('agent', `错误: ${e.message}`);
      this.dispatchEvent(new CustomEvent('error', {
        bubbles: true, composed: true,
        detail: { message: e.message },
      }));
    } finally {
      loading.style.display = 'none';
      sendBtn.disabled = false;
    }
  }

  private _send(input: HTMLTextAreaElement) {
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.style.height = 'auto';
    this._addMessage('user', text);
    this._callAgent(text);
  }
}

customElements.define('icoder-assistant', iCoDerAssistant);
export { iCoDerAssistant };
