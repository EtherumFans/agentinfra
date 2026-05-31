/**
 * <icoder-assistant> — Embedded AI Assistant Web Component
 *
 * Usage:
 *   <icoder-assistant
 *     language="zh-CN"
 *     mode="ambient"
 *     specialty="orthopedics"
 *   ></icoder-assistant>
 *
 *   const widget = document.querySelector('icoder-assistant');
 *   widget.configure({ accessToken: '...', baseURL: 'http://localhost:8000' });
 *
 * Zero dependencies. Embeddable in any HTML page or EHR system.
 */
class iCoDerAssistant extends HTMLElement {
    constructor() {
        super();
        this.messages = [];
        this.input = '';
        this.config = {};
        this.aiChatOpen = false;
        this.root = this.attachShadow({ mode: 'open' });
    }
    static get observedAttributes() { return ['language', 'mode']; }
    connectedCallback() { this.render(); }
    /** Configure authentication and settings */
    configure(config) {
        this.config = { ...this.config, ...config };
    }
    render() {
        const lang = this.getAttribute('language') || 'zh-CN';
        const isZh = lang === 'zh-CN';
        this.root.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: 'Noto Sans SC', -apple-system, sans-serif;
          --icoder-primary: hsl(9, 68%, 48%);
          --icoder-bg: hsl(40, 14%, 98%);
          --icoder-card: hsl(0, 0%, 100%);
          --icoder-border: hsl(40, 10%, 89%);
          --icoder-text: hsl(40, 6%, 9%);
          --icoder-muted: hsl(40, 4%, 43%);
        }
        .widget {
          background: var(--icoder-card);
          border-radius: 12px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06);
          border: 1px solid var(--icoder-border);
          overflow: hidden;
          min-height: 400px;
          display: flex;
          flex-direction: column;
          max-width: 400px;
        }
        .header {
          padding: 12px 16px;
          border-bottom: 1px solid var(--icoder-border);
          font-size: 14px;
          font-weight: 600;
          color: var(--icoder-text);
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .header-dot {
          width: 8px; height: 8px;
          border-radius: 50%;
          background: var(--icoder-primary);
        }
        .content {
          flex: 1;
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          overflow-y: auto;
          max-height: 300px;
        }
        .placeholder-text {
          color: hsl(40, 4%, 65%);
          font-size: 14px;
          text-align: center;
          margin-top: 40px;
        }
        .msg {
          padding: 8px 12px;
          border-radius: 8px;
          font-size: 13px;
          line-height: 1.4;
          max-width: 85%;
        }
        .msg.user {
          align-self: flex-end;
          background: var(--icoder-primary);
          color: white;
        }
        .msg.assistant {
          align-self: flex-start;
          background: hsl(40, 10%, 95%);
          color: var(--icoder-text);
        }
        .input-area {
          display: flex;
          padding: 8px 12px;
          border-top: 1px solid var(--icoder-border);
          gap: 8px;
        }
        .input-area input {
          flex: 1;
          border: 1px solid var(--icoder-border);
          border-radius: 8px;
          padding: 8px 12px;
          font-size: 13px;
          font-family: inherit;
          outline: none;
        }
        .input-area input:focus { border-color: var(--icoder-primary); }
        .send-btn {
          background: var(--icoder-primary);
          color: white;
          border: none;
          border-radius: 8px;
          padding: 8px 16px;
          font-size: 13px;
          cursor: pointer;
          font-family: inherit;
        }
        .send-btn:hover { opacity: 0.9; }
      </style>
      <div class="widget">
        <div class="header">
          <span class="header-dot"></span>
          ${isZh ? 'AI 助手' : 'AI Assistant'}
        </div>
        <div class="content" id="msg-list">
          ${this.messages.length === 0
            ? `<div class="placeholder-text">${isZh ? '开始对话...' : 'Start a conversation...'}</div>`
            : this.messages.map(m => `<div class="msg ${m.role}">${this.escapeHtml(m.text)}</div>`).join('')}
        </div>
        <div class="input-area">
          <input id="msg-input" type="text" placeholder="${isZh ? '输入问题...' : 'Ask something...'}" />
          <button class="send-btn" id="send-btn">${isZh ? '发送' : 'Send'}</button>
        </div>
      </div>
    `;
        const sendBtn = this.root.getElementById('send-btn');
        const input = this.root.getElementById('msg-input');
        sendBtn?.addEventListener('click', () => this.sendMessage(input));
        input?.addEventListener('keydown', (e) => { if (e.key === 'Enter')
            this.sendMessage(input); });
    }
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    async sendMessage(input) {
        const text = input.value.trim();
        if (!text)
            return;
        input.value = '';
        this.messages.push({ role: 'user', text });
        this.render();
        if (!this.config.baseURL || !this.config.accessToken) {
            this.messages.push({ role: 'assistant', text: '请先调用 configure() 设置 API 凭据' });
            this.render();
            return;
        }
        try {
            const response = await fetch(`${this.config.baseURL}/api/experts/call/Medical%20Coding%20Expert?input=${encodeURIComponent(text)}`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${this.config.accessToken}` },
            });
            if (!response.ok)
                throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            const output = data.output || JSON.stringify(data);
            this.messages.push({ role: 'assistant', text: output });
        }
        catch (err) {
            this.messages.push({ role: 'assistant', text: `错误: ${err.message}` });
        }
        this.render();
    }
}
customElements.define('icoder-assistant', iCoDerAssistant);
export { iCoDerAssistant };
