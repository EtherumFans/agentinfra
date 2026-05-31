/**
 * <icoder-assistant> — Embedded AI coding assistant widget
 *
 * Usage:
 *   <icoder-assistant
 *     api-key="ics_xxx"
 *     base-url="http://localhost:8000"
 *     mode="ambient"
 *     specialty="orthopedics"
 *     language="zh-CN"
 *   ></icoder-assistant>
 *
 * Uses Lit for reactive Web Components. Embeddable in any HTML page,
 * EHR system, or web application without framework dependencies.
 */
import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';

export class iCoDerAssistant extends LitElement {
  static styles = css`
    :host {
      display: block;
      font-family: 'Noto Sans SC', -apple-system, sans-serif;
      background: hsl(40, 14%, 98%);
      border: 1px solid hsl(40, 10%, 89%);
      border-radius: 12px;
      overflow: hidden;
      max-width: 400px;
      min-height: 300px;
    }
    .header {
      padding: 12px 16px;
      background: hsl(9, 68%, 48%);
      color: white;
      font-size: 14px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .messages {
      padding: 16px;
      max-height: 300px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 8px;
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
      background: hsl(9, 68%, 48%);
      color: white;
    }
    .msg.assistant {
      align-self: flex-start;
      background: hsl(40, 10%, 95%);
      color: hsl(40, 6%, 9%);
    }
    .input-area {
      display: flex;
      padding: 8px 12px;
      border-top: 1px solid hsl(40, 10%, 89%);
      gap: 8px;
    }
    input {
      flex: 1;
      border: 1px solid hsl(40, 10%, 89%);
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 13px;
      font-family: inherit;
      outline: none;
    }
    input:focus { border-color: hsl(9, 68%, 48%); }
    button {
      background: hsl(9, 68%, 48%);
      color: white;
      border: none;
      border-radius: 8px;
      padding: 8px 16px;
      font-size: 13px;
      cursor: pointer;
    }
    button:hover { filter: brightness(0.9); }
    .empty {
      text-align: center;
      padding: 40px 20px;
      color: hsl(40, 4%, 43%);
      font-size: 13px;
    }
  `;

  @property({ type: String, attribute: 'api-key' }) apiKey = '';
  @property({ type: String, attribute: 'base-url' }) baseUrl = 'http://localhost:8000';
  @property({ type: String }) mode = 'ambient';
  @property({ type: String }) specialty = 'general';
  @property({ type: String }) language = 'zh-CN';

  @state() private messages: { role: string; content: string }[] = [];
  @state() private input = '';
  @state() private loading = false;

  render() {
    return html`
      <div class="header">iCoDer 助手</div>
      <div class="messages">
        ${this.messages.length === 0
          ? html`<div class="empty">输入编码问题以开始使用</div>`
          : this.messages.map(m => html`
              <div class="msg ${m.role}">${m.content}</div>
            `)}
        ${this.loading ? html`<div class="msg assistant">思考中...</div>` : ''}
      </div>
      <div class="input-area">
        <input
          .value=${this.input}
          @input=${(e: InputEvent) => this.input = (e.target as HTMLInputElement).value}
          @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') this.send(); }}
          placeholder="输入问题..."
        />
        <button @click=${this.send} ?disabled=${this.loading}>发送</button>
      </div>
    `;
  }

  private async send() {
    if (!this.input.trim() || this.loading) return;
    const text = this.input;
    this.messages = [...this.messages, { role: 'user', content: text }];
    this.input = '';
    this.loading = true;

    try {
      const resp = await fetch(`${this.baseUrl}/api/experts/call/Medical%20Coding`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.apiKey}` },
        body: JSON.stringify({ input: text }),
      });
      const data = await resp.json();
      this.messages = [...this.messages, { role: 'assistant', content: data.output?.slice(0, 500) || 'No response' }];
    } catch (e: any) {
      this.messages = [...this.messages, { role: 'assistant', content: `Error: ${e.message}` }];
    } finally {
      this.loading = false;
      this.requestUpdate();
    }
  }
}

customElements.define('icoder-assistant', iCoDerAssistant);
