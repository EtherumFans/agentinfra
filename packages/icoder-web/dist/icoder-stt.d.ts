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
interface SttConfig {
    accessToken?: string;
    refreshToken?: string;
    baseURL?: string;
    language?: string;
    interimResults?: boolean;
    continuous?: boolean;
}
declare class iCoDerStt extends HTMLElement {
    private config;
    private isListening;
    private transcript;
    private interim;
    private mediaRecorder;
    private ws;
    private recognition;
    private root;
    constructor();
    static get observedAttributes(): string[];
    attributeChangedCallback(name: string, _old: string, value: string): void;
    connectedCallback(): void;
    /** Configure auth and connection settings */
    configure(config: SttConfig): void;
    private render;
    private escapeHtml;
    private updateTranscript;
    toggle(): Promise<void>;
    private start;
    private stop;
    /** Reset transcript */
    clear(): void;
    /** Get current transcript */
    getTranscript(): string;
}
export { iCoDerStt };
