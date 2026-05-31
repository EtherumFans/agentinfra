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
declare class iCoDerAssistant extends HTMLElement {
    private root;
    private messages;
    private input;
    private config;
    private aiChatOpen;
    constructor();
    static get observedAttributes(): string[];
    connectedCallback(): void;
    /** Configure authentication and settings */
    configure(config: {
        accessToken: string;
        baseURL: string;
        refreshToken?: string;
        mode?: string;
        language?: string;
    }): void;
    private render;
    private escapeHtml;
    private sendMessage;
}
export { iCoDerAssistant };
