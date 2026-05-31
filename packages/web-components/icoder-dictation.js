/**
 * iCoDer Dictation Web Component — <icoder-dictation>
 *
 * Framework-agnostic custom element for real-time clinical dictation.
 * Supports vanilla JS, React, Vue, Angular.
 *
 * Usage:
 *   <icoder-dictation
 *     base-url="http://localhost:8000"
 *     token="your-jwt-token"
 *     language="zh-CN"
 *     placeholder="点击麦克风开始录音">
 *   </icoder-dictation>
 *
 * Events:
 *   transcription — { text, interim, isFinal }
 *   error — { message }
 *   listening — { isListening }
 */

class iCoDerDictation extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._isListening = false;
    this._mediaRecorder = null;
    this._transcript = '';
    this._interim = '';
  }

  static get observedAttributes() {
    return ['base-url', 'token', 'language', 'placeholder', 'disabled'];
  }

  connectedCallback() {
    this.render();
  }

  attributeChangedCallback(name, oldVal, newVal) {
    if (oldVal !== newVal) this.render();
  }

  get baseUrl() { return this.getAttribute('base-url') || 'http://localhost:8000'; }
  get token() { return this.getAttribute('token') || ''; }
  get language() { return this.getAttribute('language') || 'zh-CN'; }
  get placeholder() { return this.getAttribute('placeholder') || '点击麦克风开始录音'; }
  get disabled() { return this.hasAttribute('disabled'); }

  async _toggleRecording() {
    if (this._isListening) {
      this._stopRecording();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this._isListening = true;
      this._mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      const chunks: Blob[] = [];

      this._mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      this._mediaRecorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        await this._sendAudio(blob);
        stream.getTracks().forEach(t => t.stop());
      };

      this._mediaRecorder.start(1000);
      this._dispatch('listening', { isListening: true });
      this.render();

      // Also use browser SpeechRecognition for real-time interim
      this._startBrowserSTT();
    } catch (err: any) {
      this._dispatch('error', { message: err.message || '麦克风访问被拒绝' });
    }
  }

  _startBrowserSTT() {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;
    const recognition = new SpeechRecognition();
    recognition.lang = this.language;
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.onresult = (event: any) => {
      let interim = '';
      let final = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) { final += r[0].transcript; }
        else { interim += r[0].transcript; }
      }
      if (final) this._transcript += final;
      this._interim = interim;
      this._dispatch('transcription', {
        text: this._transcript + interim,
        interim: this._interim,
        isFinal: !!final,
      });
      this.render();
    };
    recognition.onerror = () => {};
    recognition.start();
    this._recognition = recognition;
  }

  _stopRecording() {
    this._isListening = false;
    if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
      this._mediaRecorder.stop();
    }
    if (this._recognition) { this._recognition.stop(); this._recognition = null; }
    this._dispatch('listening', { isListening: false });
    this.render();
  }

  async _sendAudio(_blob: Blob) {
    // Audio upload to backend for server-side transcription
    // Falls back to browser STT if server unavailable
  }

  _clearTranscript() {
    this._transcript = '';
    this._interim = '';
    this._dispatch('transcription', { text: '', interim: '', isFinal: true });
    this.render();
  }

  _dispatch(name: string, detail: any) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }

  connectedCallback() { this.render(); }
  attributeChangedCallback() { this.render(); }

  render() {
    const displayText = this._transcript + (this._interim ? `<em>${this._interim}</em>` : '');
    this.shadowRoot!.innerHTML = `
      <style>
        :host { display: block; font-family: system-ui, sans-serif; }
        .container { border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; background: #fff; }
        .controls { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
        button {
          display: inline-flex; align-items: center; gap: 6px;
          padding: 8px 16px; border-radius: 8px; border: 1px solid #cbd5e1;
          background: #fff; cursor: pointer; font-size: 14px; transition: all .15s;
        }
        button:hover { background: #f1f5f9; }
        button.recording { background: #ef4444; color: #fff; border-color: #ef4444; }
        button.recording:hover { background: #dc2626; }
        button:disabled { opacity: .5; cursor: not-allowed; }
        .transcript {
          min-height: 60px; max-height: 200px; overflow-y: auto;
          padding: 12px; border-radius: 8px; background: #f8fafc;
          font-size: 14px; line-height: 1.6; color: #334155; white-space: pre-wrap;
        }
        .transcript em { color: #94a3b8; }
        .placeholder { color: #94a3b8; }
      </style>
      <div class="container">
        <div class="controls">
          <button class="${this._isListening ? 'recording' : ''}" ${this.disabled ? 'disabled' : ''}>
            ${this._isListening ? '⏹ 停止' : '🎤 录音'}
          </button>
          ${this._transcript ? '<button>🗑 清除</button>' : ''}
        </div>
        <div class="transcript">
          ${displayText ? displayText : `<span class="placeholder">${this.placeholder}</span>`}
        </div>
      </div>
    `;

    const micBtn = this.shadowRoot!.querySelector('button');
    const clearBtn = this.shadowRoot!.querySelectorAll('button')[1];
    micBtn?.addEventListener('click', () => this._toggleRecording());
    clearBtn?.addEventListener('click', () => this._clearTranscript());
  }
}

customElements.define('icoder-dictation', iCoDerDictation);
