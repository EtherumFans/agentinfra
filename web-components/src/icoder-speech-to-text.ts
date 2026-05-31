/**
 * <icoder-speech-to-text> — Real-time medical dictation web component
 *
 * Usage:
 *   <icoder-speech-to-text
 *     language="zh-CN"
 *     punctuation="auto"
 *     interim-results="true"
 *     placeholder="开始录音..."
 *   ></icoder-speech-to-text>
 *
 * Events:
 *   transcript — fired when final transcript is available
 *   interim   — fired with interim (non-final) transcript
 *   status    — fired when recording status changes
 *
 * Uses browser Web Speech API. No backend required for recognition.
 * Chrome recommended — best medical term accuracy.
 */
import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}
interface SpeechRecognitionError extends Event {
  error: string;
}
interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((e: SpeechRecognitionEvent) => void) | null;
  onerror: ((e: SpeechRecognitionError) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}
declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
}

const PUNCTUATION_MAP: Record<string, string> = {
  'comma': ',', 'period': '.', 'question mark': '?',
  'exclamation mark': '!', 'new line': '\n', 'new paragraph': '\n\n',
  '逗号': ',', '句号': '。', '问号': '？', '感叹号': '！',
  '换行': '\n', '下一段': '\n\n',
};

export class iCoDerSpeechToText extends LitElement {
  static styles = css`
    :host {
      display: block;
      font-family: 'Noto Sans SC', -apple-system, sans-serif;
      background: hsl(0, 0%, 100%);
      border: 1px solid hsl(40, 10%, 89%);
      border-radius: 12px;
      overflow: hidden;
      max-width: 600px;
    }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px 16px;
      border-bottom: 1px solid hsl(40, 10%, 89%);
      background: hsl(40, 10%, 96%);
    }
    .lang-select {
      border: 1px solid hsl(40, 10%, 89%);
      border-radius: 6px;
      padding: 4px 8px;
      font-size: 12px;
      font-family: inherit;
      background: white;
    }
    .record-btn {
      width: 40px; height: 40px;
      border-radius: 50%;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 150ms;
      margin-left: auto;
    }
    .record-btn.off {
      background: hsl(9, 68%, 48%);
      color: white;
    }
    .record-btn.on {
      background: #ef4444;
      color: white;
      animation: pulse 1.5s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
      50% { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
    }
    .transcript-area {
      padding: 16px;
      min-height: 120px;
      max-height: 300px;
      overflow-y: auto;
      font-size: 14px;
      line-height: 1.6;
      color: hsl(40, 6%, 9%);
      white-space: pre-wrap;
    }
    .interim {
      color: hsl(40, 4%, 60%);
      font-style: italic;
    }
    .placeholder {
      color: hsl(40, 4%, 60%);
      text-align: center;
      padding: 40px 0;
    }
    .commands-bar {
      padding: 8px 16px;
      border-top: 1px solid hsl(40, 10%, 89%);
      background: hsl(40, 10%, 96%);
      font-size: 11px;
      color: hsl(40, 4%, 43%);
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    .cmd { opacity: 0.7; }
    .controls {
      padding: 8px 16px;
      border-top: 1px solid hsl(40, 10%, 89%);
      display: flex;
      gap: 8px;
    }
    .controls button {
      border: 1px solid hsl(40, 10%, 89%);
      border-radius: 6px;
      padding: 4px 12px;
      font-size: 12px;
      font-family: inherit;
      background: white;
      cursor: pointer;
    }
    .controls button:hover { background: hsl(40, 10%, 95%); }
    label { font-size: 12px; display: flex; align-items: center; gap: 4px; }
    input[type="checkbox"] { accent-color: hsl(9, 68%, 48%); }
  `;

  @property({ type: String }) language = 'zh-CN';
  @property({ type: String, attribute: 'punctuation' }) punctuation = 'auto';
  @property({ type: Boolean, attribute: 'interim-results' }) interimResults = true;
  @property({ type: String }) placeholder = '点击麦克风开始录音...';

  @state() private transcript = '';
  @state() private interim = '';
  @state() private isListening = false;
  @state() private autoPunctuate = true;
  @state() private recognition: SpeechRecognition | null = null;

  disconnectedCallback() {
    super.disconnectedCallback();
    this.recognition?.stop();
  }

  render() {
    const micIcon = this.isListening
      ? html`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"/><path d="M17 16.95A7 7 0 0 1 5 13v-2m14 0v2a7 7 0 0 1-.11 1.23"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`
      : html`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`;

    return html`
      <div class="toolbar">
        <select class="lang-select" .value=${this.language} @change=${this.onLangChange}>
          <option value="zh-CN">简体中文</option>
          <option value="en-US">English (US)</option>
          <option value="en-GB">English (UK)</option>
        </select>
        <label><input type="checkbox" .checked=${this.autoPunctuate} @change=${this.togglePunctuation}>自动标点</label>
        <button class="record-btn ${this.isListening ? 'on' : 'off'}" @click=${this.toggleRecord} title=${this.isListening ? '停止' : '开始'}>
          ${micIcon}
        </button>
      </div>

      <div class="transcript-area">
        ${this.transcript || this.interim
          ? html`${this.transcript}<span class="interim">${this.interim ? ' ' + this.interim : ''}</span>`
          : html`<div class="placeholder">${this.isListening ? '正在听写...' : this.placeholder}</div>`}
      </div>

      <div class="controls">
        <button @click=${this.clear} ?disabled=${!this.transcript}>清除</button>
        <button @click=${this.copy} ?disabled=${!this.transcript}>复制</button>
      </div>

      <div class="commands-bar">
        <span class="cmd">语音指令：</span>
        <span class="cmd">"逗号/句号/问号" → 标点</span>
        <span class="cmd">"换行" → 新行</span>
        <span class="cmd">"删除上一条" → 撤销</span>
      </div>
    `;
  }

  private onLangChange(e: Event) {
    this.language = (e.target as HTMLSelectElement).value;
    if (this.isListening) {
      this.stop();
      setTimeout(() => this.start(), 100);
    }
  }

  private togglePunctuation(e: Event) {
    this.autoPunctuate = (e.target as HTMLInputElement).checked;
  }

  private toggleRecord() {
    this.isListening ? this.stop() : this.start();
  }

  private start() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      this.dispatch('error', 'Speech recognition not supported');
      return;
    }
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = this.interimResults;
    rec.lang = this.language;

    rec.onresult = (e: SpeechRecognitionEvent) => {
      let interimText = '', finalText = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) {
          let t = r[0].transcript;
          if (this.autoPunctuate) t = this.applyPunctuation(t);
          finalText += t;
        } else {
          interimText += r[0].transcript;
        }
      }
      if (finalText) {
        this.transcript += (this.transcript ? ' ' : '') + finalText;
        this.interim = '';
        this.dispatch('transcript', { text: this.transcript, latest: finalText });
      } else {
        this.interim = interimText;
        this.dispatch('interim', { text: interimText });
      }
    };

    rec.onerror = (e: SpeechRecognitionError) => {
      if (e.error !== 'no-speech') {
        this.dispatch('error', { error: e.error });
      }
      this.isListening = false;
    };

    rec.onend = () => { this.isListening = false; this.dispatch('status', { recording: false }); };

    try {
      rec.start();
      this.recognition = rec;
      this.isListening = true;
      this.dispatch('status', { recording: true });
    } catch (e: any) {
      this.dispatch('error', { error: e.message || 'Failed to start' });
    }
  }

  private stop() {
    this.recognition?.stop();
    this.isListening = false;
  }

  private clear() { this.transcript = ''; this.interim = ''; }

  private copy() { navigator.clipboard.writeText(this.transcript); }

  private applyPunctuation(text: string): string {
    let result = text;
    for (const [word, punct] of Object.entries(PUNCTUATION_MAP)) {
      result = result.replace(new RegExp(`\\s*${word}\\s*`, 'gi'), punct + ' ');
    }
    return result.trim();
  }

  private dispatch(name: string, detail: any) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }
}

customElements.define('icoder-speech-to-text', iCoDerSpeechToText);
