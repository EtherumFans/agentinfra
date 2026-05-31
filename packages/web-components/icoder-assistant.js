/**
 * iCoDer Assistant Web Component — <icoder-assistant>
 *
 * Framework-agnostic embedded AI assistant with chat + transcription.
 *
 * Usage:
 *   <icoder-assistant
 *     base-url="http://localhost:8000"
 *     token="your-jwt-token"
 *     agent-id="your-agent-id"
 *     language="zh-CN">
 *   </icoder-assistant>
 */

class iCoDerAssistant extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._messages = [];
    this._input = '';
    this._loading = false;
    this._transcript = '';
    this._isRecording = false;
  }

  static get observedAttributes() { return ['base-url', 'token', 'agent-id', 'language', 'placeholder']; }

  get baseUrl() { return this.getAttribute('base-url') || 'http://localhost:8000'; }
  get token() { return this.getAttribute('token') || ''; }
  get agentId() { return this.getAttribute('agent-id') || ''; }
  get language() { return this.getAttribute('language') || 'zh-CN'; }

  async _sendMessage() {
    const text = this._input.trim();
    if (!text || this._loading) return;
    this._messages.push({ role: 'user', content: text });
    this._input = '';
    this._loading = true;
    this.render();

    const assistantIdx = this._messages.length;
    this._messages.push({ role: 'assistant', content: '' });

    try {
      const resp = await fetch(`${this.baseUrl}/api/agents/${this.agentId}/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${this.token}` },
        body: JSON.stringify({ input: text, conversation_history: this._messages.slice(0, -1) }),
      });
      const reader = resp.body?.getReader();
      if (!reader) throw new Error('No stream');
      const decoder = new TextDecoder();
      let buffer = '', accumulated = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') break;
            try {
              const p = JSON.parse(data);
              if (p.type === 'token' && p.text) {
                accumulated += p.text;
                this._messages[assistantIdx] = { role: 'assistant', content: accumulated };
                this.render();
              }
            } catch { accumulated += data; }
          }
        }
      }
    } catch (err: any) {
      this._messages[assistantIdx] = { role: 'assistant', content: 'Error: ' + err.message };
    }
    this._loading = false;
    this.render();
  }

  connectedCallback() { this.render(); }
  attributeChangedCallback() { this.render(); }

  render() {
    const placeholder = this.getAttribute('placeholder') || '输入临床问题...';
    this.shadowRoot!.innerHTML = `
      <style>
        :host { display: flex; flex-direction: column; height: 500px; max-height: 100vh; font-family: system-ui, sans-serif; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: #fff; }
        .header { padding: 12px 16px; border-bottom: 1px solid #e2e8f0; font-weight: 600; font-size: 14px; color: #1e293b; display: flex; align-items: center; gap: 8px; }
        .header .dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; }
        .messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
        .msg { max-width: 80%; padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
        .msg.user { align-self: flex-end; background: #3b82f6; color: #fff; border-bottom-right-radius: 4px; }
        .msg.assistant { align-self: flex-start; background: #f1f5f9; color: #334155; border-bottom-left-radius: 4px; }
        .input-area { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid #e2e8f0; }
        .input-area input { flex: 1; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; outline: none; }
        .input-area input:focus { border-color: #3b82f6; }
        .input-area button { padding: 8px 16px; border-radius: 8px; border: none; background: #3b82f6; color: #fff; cursor: pointer; font-size: 13px; }
        .input-area button:disabled { opacity: .5; cursor: not-allowed; }
        .loading { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; animation: pulse 1s infinite; }
        @keyframes pulse { 0%,100%{opacity:.3} 50%{opacity:1} }
      </style>
      <div class="header"><span class="dot"></span> iCoDer Assistant</div>
      <div class="messages" id="msg-list">
        ${this._messages.length === 0 ? '<div style="text-align:center;color:#94a3b8;padding:40px 0;font-size:13px">输入临床问题开始对话</div>' : ''}
        ${this._messages.map((m, i) => `<div class="msg ${m.role}">${m.content || (i === this._messages.length - 1 && this._loading ? '<span class="loading"></span>' : '')}</div>`).join('')}
      </div>
      <div class="input-area">
        <input type="text" value="${this._input}" placeholder="${placeholder}" onkeydown="if(event.key==='Enter')this.closest('icoder-assistant')._sendMessage()" />
        <button ${this._loading || !this._input.trim() ? 'disabled' : ''}>发送</button>
      </div>
    `;
    const input = this.shadowRoot!.querySelector('input');
    input?.addEventListener('input', (e) => { this._input = (e.target as HTMLInputElement).value; });
    const btn = this.shadowRoot!.querySelector('button');
    btn?.addEventListener('click', () => this._sendMessage());
  }
}

customElements.define('icoder-assistant', iCoDerAssistant);
