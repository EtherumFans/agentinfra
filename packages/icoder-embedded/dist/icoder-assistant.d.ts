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
 *         default: console.log(name, payload);
 *       }
 *     });
 *   </script>
 *
 * iCoDer ADVANTAGE methods kept (Corti does not have these):
 *   - setPatientContext({ patientId, name, encounterId })
 *   - ask(question)
 * See memory `feedback_corti_alignment.md` ("勿为像 Corti 删 iCoDer 差异化能力").
 *
 * Migration guide: see packages/icoder-embedded/MIGRATION-2.0.md.
 */
export interface AuthOptions {
    access_token: string;
    refresh_token?: string;
    token_type?: string;
    mode?: string;
}
export interface SessionConfig {
    defaultTemplateKey?: string;
    defaultLanguage?: string;
    defaultMode?: string;
    defaultOutputLanguage?: string;
    patientId?: string;
    name?: string;
    encounterId?: string;
}
export interface ConfigureOptions {
    features?: Record<string, boolean>;
    locale?: {
        dictationLanguage?: string;
        interfaceLanguage?: string;
    };
}
export interface EmbeddedEvent {
    name: string;
    payload: any;
}
declare class iCoDerEmbedded extends HTMLElement {
    private _auth;
    private _sessionConfig;
    private _config;
    private _patientContext;
    private _baseUrl;
    private _visible;
    private _shadow;
    static get observedAttributes(): string[];
    constructor();
    connectedCallback(): void;
    attributeChangedCallback(name: string, _old: string, _new: string): void;
    /**
     * Set auth credentials. Must be called before show() if not using
     * the deprecated access-token attribute.
     */
    auth(opts: AuthOptions): Promise<void>;
    /**
     * Configure session-level defaults (agent + patient context).
     * iCoDer ADVANTAGE: patientId/name/encounterId as explicit fields
     * (Corti uses defaultTemplateKey only).
     */
    configureSession(opts: SessionConfig): Promise<void>;
    /**
     * Configure feature flags + locale (interface language).
     */
    configure(opts: ConfigureOptions): Promise<void>;
    /**
     * Show the widget. Should be called after auth() + configureSession() +
     * configure(). If auth() was not called, prints a warning and the widget
     * will render but API calls will fail with 401.
     */
    show(): Promise<void>;
    /**
     * Set patient context explicitly. iCoDer-specific — Corti uses
     * configureSession({defaultTemplateKey}) instead.
     */
    setPatientContext(ctx: {
        patientId?: string;
        name?: string;
        encounterId?: string;
    }): void;
    /**
     * Send a question to the agent. Shortcut for the user typing into the
     * input box. Returns the agent's response.
     */
    ask(question: string): Promise<any>;
    private _readyEmitted;
    private _emitEmbeddedEvent;
    private _emitReady;
    private _setupUIHandlers;
    private _renderBadge;
    private _renderPatientBar;
    private _applyInterfaceLanguage;
    private _applyFeatures;
    private _addMessage;
    private _callAgent;
    private _send;
}
export { iCoDerEmbedded };
export default iCoDerEmbedded;
