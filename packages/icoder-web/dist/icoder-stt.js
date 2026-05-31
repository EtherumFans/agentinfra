/**
 * <icoder-stt> — Medical Speech-to-Text Web Component
 *
 * Usage:
 *   <icoder-stt
 *     language="zh-CN"
 *     placeholder="点击麦克风开始录音"
 *   ></icoder-stt>
 *
 *   const stt = document.querySelector('icoder-stt');
 *   stt.configure({ accessToken: '...', baseURL: 'http://localhost:8000' });
 *   stt.addEventListener('transcript', (e) => console.log(e.detail));
 *
 * Zero dependencies. Works in any HTML page.
 */
class iCoDerStt extends HTMLElement {
    constructor() {
        super();
        this.config = { language: 'zh-CN', interimResults: true, continuous: true };
        this.isListening = false;
        this.transcript = '';
        this.interim = '';
        this.mediaRecorder = null;
        this.ws = null;
        this.recognition = null;
        this.root = this.attachShadow({ mode: 'open' });
    }
    static get observedAttributes() {
        return ['language', 'placeholder'];
    }
    attributeChangedCallback(name, _old, value) {
        if (name === 'language')
            this.config.language = value;
        this.render();
    }
    connectedCallback() {
        this.config.language = this.getAttribute('language') || 'zh-CN';
        this.render();
    }
    /** Configure auth and connection settings */
    configure(config) {
        this.config = { ...this.config, ...config };
    }
    render() {
        const placeholder = this.getAttribute('placeholder') || '点击麦克风开始录音';
        const lang = this.config.language || 'zh-CN';
        this.root.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: 'Noto Sans SC', -apple-system, sans-serif;
          --icoder-primary: hsl(9, 68%, 48%);
          --icoder-bg: hsl(40, 14%, 98%);
          --icoder-border: hsl(40, 10%, 89%);
          --icoder-text: hsl(40, 6%, 9%);
          --icoder-muted: hsl(40, 4%, 43%);
        }
        .container {
          background: var(--icoder-bg);
          border: 1px solid var(--icoder-border);
          border-radius: 12px;
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          min-height: 200px;
        }
        .transcript-area {
          flex: 1;
          min-height: 80px;
          font-size: 15px;
          line-height: 1.6;
          color: var(--icoder-text);
          white-space: pre-wrap;
          overflow-y: auto;
          max-height: 300px;
        }
        .interim {
          color: hsl(40, 4%, 60%);
        }
        .placeholder {
          color: hsl(40, 4%, 75%);
          font-size: 15px;
        }
        .controls {
          display: flex;
          justify-content: center;
          align-items: center;
          gap: 8px;
          padding-top: 8px;
          border-top: 1px solid var(--icoder-border);
        }
        .mic-btn {
          width: 52px;
          height: 52px;
          border-radius: 50%;
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
          font-size: 20px;
        }
        .mic-btn.off {
          background: var(--icoder-primary);
          color: white;
          box-shadow: 0 2px 8px hsla(9, 68%, 48%, 0.3);
        }
        .mic-btn.off:hover { opacity: 0.9; transform: scale(1.05); }
        .mic-btn.on {
          background: hsl(0, 72%, 48%);
          color: white;
          box-shadow: 0 2px 12px hsla(0, 72%, 48%, 0.4);
          animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
          0%, 100% { box-shadow: 0 0 0 0 hsla(0, 72%, 48%, 0.4); }
          50% { box-shadow: 0 0 0 8px hsla(0, 72%, 48%, 0); }
        }
        .status {
          font-size: 12px;
          color: var(--icoder-muted);
        }
      </style>
      <div class="container">
        <div class="transcript-area" id="transcript">
          ${this.transcript
            ? `<span>${this.escapeHtml(this.transcript)}</span>${this.interim ? `<span class="interim"> ${this.escapeHtml(this.interim)}</span>` : ''}`
            : `<span class="placeholder">${placeholder}</span>`}
        </div>
        <div class="controls">
          <span class="status">${this.isListening ? '录音中...' : lang === 'zh-CN' ? '语音转录' : 'Speech To Text'}</span>
          <button class="mic-btn ${this.isListening ? 'on' : 'off'}" id="mic-btn" title="${this.isListening ? '停止' : '录音'}">
            ${this.isListening ? '⏹' : '🎤'}
          </button>
        </div>
      </div>
    `;
        const btn = this.root.getElementById('mic-btn');
        btn?.addEventListener('click', () => this.toggle());
    }
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    updateTranscript() {
        const el = this.root.getElementById('transcript');
        if (!el)
            return;
        const placeholder = this.getAttribute('placeholder') || '点击麦克风开始录音';
        el.innerHTML = this.transcript
            ? `<span>${this.escapeHtml(this.transcript)}</span>${this.interim ? `<span class="interim"> ${this.escapeHtml(this.interim)}</span>` : ''}`
            : `<span class="placeholder">${placeholder}</span>`;
    }
    async toggle() {
        if (this.isListening) {
            this.stop();
        }
        else {
            await this.start();
        }
    }
    async start() {
        if (this.isListening)
            return;
        // Try browser SpeechRecognition first (simpler, no server needed)
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SR && !this.config.baseURL) {
            const rec = new SR();
            rec.continuous = this.config.continuous ?? true;
            rec.interimResults = this.config.interimResults ?? true;
            rec.lang = this.config.language || 'zh-CN';
            rec.onresult = (event) => {
                let i = '', f = '';
                for (let j = event.resultIndex; j < event.results.length; j++) {
                    const r = event.results[j];
                    r.isFinal ? f += r[0].transcript : i += r[0].transcript;
                }
                if (f) {
                    this.transcript += f;
                    this.dispatchEvent(new CustomEvent('transcript', { detail: { text: f, isFinal: true } }));
                    this.interim = '';
                }
                else {
                    this.interim = i;
                    this.dispatchEvent(new CustomEvent('transcript', { detail: { text: i, isFinal: false } }));
                }
                this.updateTranscript();
            };
            rec.onerror = (event) => {
                if (event.error !== 'no-speech') {
                    this.dispatchEvent(new CustomEvent('error', { detail: { error: event.error } }));
                }
                this.stop();
            };
            rec.onend = () => { if (this.isListening)
                rec.start(); };
            try {
                rec.start();
                this.recognition = rec;
                this.isListening = true;
                this.render();
            }
            catch {
                this.dispatchEvent(new CustomEvent('error', { detail: { error: '浏览器不支持语音识别' } }));
            }
            return;
        }
        // Server mode: WebSocket streaming
        if (!this.config.baseURL || !this.config.accessToken) {
            this.dispatchEvent(new CustomEvent('error', { detail: { error: '请先调用 configure() 设置 baseURL 和 accessToken' } }));
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
            this.mediaRecorder = new MediaRecorder(stream, { mimeType: mime });
            const wsUrl = this.config.baseURL.replace(/^http/, 'ws') + '/ws/speech-to-text';
            this.ws = new WebSocket(wsUrl);
            this.ws.onopen = () => {
                this.ws.send(JSON.stringify({ type: 'start', mimeType: mime }));
                this.mediaRecorder.start(250);
                this.isListening = true;
                this.render();
            };
            this.ws.onmessage = (ev) => {
                const m = JSON.parse(ev.data);
                if (m.type === 'interim')
                    this.interim = m.text || '';
                else if (m.type === 'final') {
                    this.transcript += m.text || '';
                    this.interim = '';
                    this.dispatchEvent(new CustomEvent('transcript', { detail: { text: m.text, isFinal: true } }));
                }
                this.updateTranscript();
            };
            this.ws.onerror = () => { this.dispatchEvent(new CustomEvent('error', { detail: { error: 'WebSocket连接失败' } })); this.stop(); };
            this.ws.onclose = () => this.stop();
            // Timeout
            setTimeout(() => { if (this.ws && this.ws.readyState !== WebSocket.OPEN) {
                this.stop();
                this.dispatchEvent(new CustomEvent('error', { detail: { error: '连接超时' } }));
            } }, 5000);
        }
        catch (err) {
            this.dispatchEvent(new CustomEvent('error', { detail: { error: err.message || '无法启动录音' } }));
        }
    }
    stop() {
        this.isListening = false;
        try {
            this.recognition?.stop();
        }
        catch { }
        try {
            this.mediaRecorder?.stop();
        }
        catch { }
        try {
            this.ws?.close();
        }
        catch { }
        this.mediaRecorder = null;
        this.ws = null;
        this.recognition = null;
        this.interim = '';
        this.render();
    }
    /** Reset transcript */
    clear() { this.transcript = ''; this.interim = ''; this.render(); }
    /** Get current transcript */
    getTranscript() { return this.transcript; }
}
customElements.define('icoder-stt', iCoDerStt);
export { iCoDerStt };
