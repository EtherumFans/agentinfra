// Phase 7 Gate 13A — Corti-style Embedded Assistant Console page.
//
// SECURE bootstrap (replaces Gate 13's URL-embedded JWT):
//   1. On mount (or Restart), POST /api/embedded/preview-sessions with the
//      Console's JWT → receive {preview_session_id, ticket, nonce}.
//   2. Set iframe.src = /api/embedded/preview.html?psid=<preview_session_id>.
//      NO token, NO PHI in URL (Gate 13A Checkpoint A).
//   3. iframe loads, opens MessageChannel, posts ready-ping on its port.
//   4. Console verifies (event.source === iframe.contentWindow) AND
//      event.origin === backend origin AND data.psid === current psid.
//      Responds with the bootstrap message: {ticket, nonce, context}.
//   5. iframe exchanges ticket → Runtime Token (scoped, 10min), then
//      auth/configureSession/configure/show.
//   6. iframe forwards every embedded-event back via the SAME port.
//      Console verifies the port's origin on every message (Checkpoint B).
//
// The patient context (agent/patientId/name/encounterId/features/locale)
// flows ONLY over the MessageChannel — never in the URL.

import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { Monitor, Smartphone, Copy, Check, RefreshCw, Power } from 'lucide-react';

import { useToastStore, useAuthStore } from '../store';
import { agentsApi } from '../services/api';
import { useT } from '../i18n';
import EventInspector from '../components/common/EventInspector';

interface EmbeddedConfig {
  agentRef: string;
  patientId: string;
  patientName: string;
  encounterId: string;
  primaryColor: string;
  features: {
    aiChat: boolean;
    documentFeedback: boolean;
    virtualMode: boolean;
    showNavigation: boolean;
  };
  locale: {
    dictationLanguage: string;
    interfaceLanguage: string;
  };
}

const DEFAULT_CONFIG: EmbeddedConfig = {
  agentRef: 'medical-coding-agent',
  patientId: 'P-2026-001',
  patientName: '张三',
  encounterId: 'E-20260713-001',
  primaryColor: '#007aff',
  features: {
    aiChat: true,
    documentFeedback: true,
    virtualMode: false,
    showNavigation: false,
  },
  locale: {
    dictationLanguage: 'zh-CN',
    interfaceLanguage: 'zh-CN',
  },
};

// Backend origin — same-origin with the iframe URL because the iframe
// src is /api/embedded/preview.html (served by the backend). In dev, the
// Vite dev server proxies /api → http://localhost:8000, so the iframe
// is technically cross-origin from the Console (localhost:5173) but
// same-origin with the backend (localhost:8000). We compute it from
// window.location so it works in both dev and cloud.
const BACKEND_ORIGIN = typeof window !== 'undefined'
  ? window.location.origin
  : 'http://localhost:8000';

// The iframe origin is the backend's origin (it serves preview.html).
// In dev, this differs from the Console origin (5173 vs 8000).
const IFRAME_ORIGIN = BACKEND_ORIGIN;

type PreviewDevice = 'desktop' | 'mobile';
type ConfigTab = 'settings' | 'code';
type CodeTab = 'html' | 'react' | 'json';

// Shape of the bootstrap response from POST /api/embedded/preview-sessions
interface PreviewSessionBootstrap {
  preview_session_id: string;
  ticket: string;
  nonce: string;
  expires_at: string;
  iframe_url: string;
}

export default function EmbeddedAssistantPage() {
  const toast = useToastStore((s) => s.addToast);
  const t = useT();
  const [config, setConfig] = useState<EmbeddedConfig>(DEFAULT_CONFIG);
  const [device, setDevice] = useState<PreviewDevice>('desktop');
  const [configTab, setConfigTab] = useState<ConfigTab>('settings');
  const [codeTab, setCodeTab] = useState<CodeTab>('html');
  const [copied, setCopied] = useState(false);
  const [agents, setAgents] = useState<string[]>([]);
  const [previewKey, setPreviewKey] = useState(0);
  const [events, setEvents] = useState<{ type: string; data: Record<string, unknown>; timestamp: string; credits?: number }[]>([]);
  const [creditsConsumed, setCreditsConsumed] = useState(0);

  // Gate 13A-1 — preview session state (ticket lives in parent JS memory only)
  const [session, setSession] = useState<PreviewSessionBootstrap | null>(null);
  const [bootstrapping, setBootstrapping] = useState(false);

  // Console JWT — used to mint the ticket (sent in Authorization header).
  const accessToken = useAuthStore((s) => s.accessToken);

  // Refs for the MessageChannel handshake
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const channelRef = useRef<MessageChannel | null>(null);
  const portRef = useRef<MessagePort | null>(null);
  // The context to send on the next bootstrap (kept in a ref so the
  // iframe's port.onmessage handler always sees the latest value).
  const pendingContextRef = useRef<EmbeddedConfig>(config);
  const pendingTicketRef = useRef<PreviewSessionBootstrap | null>(null);

  // ─── load agent list ───────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const resp = await agentsApi.list();
        const data = (resp as any)?.data || resp;
        const refs = (data?.agents || []).map((a: any) => a?.agent_ref || a?.id).filter(Boolean);
        if (refs.length) setAgents(refs);
      } catch { /* keep default */ }
    })();
  }, []);

  // ─── create preview session on mount or Restart ────────────────────
  // Gate 13A-1 — Console mints a 60s single-use ticket. The ticket is
  // stored in parent JS memory only (no localStorage, no URL).
  const createSession = useCallback(async () => {
    if (!accessToken) {
      toast('Console JWT not available — please sign in', 'error');
      return;
    }
    setBootstrapping(true);
    try {
      const resp = await fetch(`${BACKEND_ORIGIN}/api/embedded/preview-sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
        credentials: 'include',
        body: JSON.stringify({ expected_parent_origin: window.location.origin }),
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
      }
      const data = await resp.json() as PreviewSessionBootstrap;
      pendingTicketRef.current = data;
      setSession(data);
      // Bump previewKey to remount the iframe so it re-handshakes.
      setPreviewKey((k) => k + 1);
    } catch (e) {
      toast(`Failed to create preview session: ${String(e)}`, 'error');
    } finally {
      setBootstrapping(false);
    }
  }, [accessToken, toast]);

  useEffect(() => {
    createSession();
    // Cleanup on unmount: revoke the active session.
    return () => {
      const s = pendingTicketRef.current;
      if (s) {
        fetch(`${BACKEND_ORIGIN}/api/embedded/preview-sessions/${s.preview_session_id}/revoke`, {
          method: 'POST',
          headers: accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {},
          credentials: 'include',
        }).catch(() => { /* fire-and-forget */ });
      }
      if (portRef.current) {
        try { portRef.current.close(); } catch { /* noop */ }
      }
      if (channelRef.current) {
        try { channelRef.current.port1.close(); } catch { /* noop */ }
      }
    };
  }, [createSession]);

  // Keep pendingContextRef in sync with config state.
  useEffect(() => {
    pendingContextRef.current = config;
  }, [config]);

  // ─── iframe URL — opaque psid ONLY ─────────────────────────────────
  // Gate 13A Checkpoint A — no token, no PHI in URL.
  const previewUrl = useMemo(() => {
    if (!session) return null;
    // The iframe is served by the backend; build the absolute URL.
    return `${IFRAME_ORIGIN}/api/embedded/preview.html?psid=${encodeURIComponent(session.preview_session_id)}`;
  }, [session]);

  // ─── MessageChannel handshake (parent side) ────────────────────────
  // Wait for iframe to load, then open a port and handshake.
  const onIframeLoad = useCallback(() => {
    if (!iframeRef.current || !session) return;
    // Tear down any previous channel.
    if (portRef.current) {
      try { portRef.current.close(); } catch { /* noop */ }
    }
    const channel = new MessageChannel();
    channelRef.current = channel;
    portRef.current = channel.port1;
    channel.port1.onmessage = (e: MessageEvent) => {
      // Per HTML spec, MessageChannel port-to-port messages carry
      // origin='' (no incumbent window). The port was transferred to
      // the iframe only after we verified ev.source === iframe.contentWindow
      // in the icoder:open-port handler, so we trust the port. The
      // psid check below is the binding guarantee.
      const msg = e.data || {};
      if (!msg || typeof msg !== 'object') return;
      if (msg.kind === 'icoder:ready-ping') {
        // Verify psid matches what we issued (defense-in-depth).
        if (msg.psid !== session.preview_session_id) return;
        // Respond with ack + bootstrap atomically.
        channel.port1.postMessage({ kind: 'icoder:ready-ack', psid: session.preview_session_id });
        // Send bootstrap with ticket + nonce + current context.
        const ctx = pendingContextRef.current;
        channel.port1.postMessage({
          kind: 'icoder:bootstrap',
          ticket: session.ticket,
          nonce: session.nonce,
          psid: session.preview_session_id,
          context: {
            agent: ctx.agentRef,
            patientId: ctx.patientId,
            name: ctx.patientName,
            encounterId: ctx.encounterId,
            features: ctx.features,
            locale: ctx.locale,
            primaryColor: ctx.primaryColor,
          },
        });
      } else if (msg.kind === 'icoder:event') {
        // Embedded widget event forwarded by the iframe.
        const ts = new Date().toLocaleTimeString();
        setEvents((prev) => [...prev, {
          type: msg.name || 'unknown',
          data: msg.payload || {},
          timestamp: ts,
          credits: msg.name === 'account.creditsConsumed' ? msg.payload?.amount : undefined,
        }]);
        if (msg.name === 'account.creditsConsumed' && msg.payload?.amount) {
          setCreditsConsumed((c) => c + (msg.payload.amount || 0));
        }
      } else if (msg.kind === 'icoder:ready') {
        // iframe finished init; nothing to do here.
      } else if (msg.kind === 'icoder:bootstrap-error') {
        toast(`Preview bootstrap failed: ${msg.error}`, 'error');
      }
    };
    // Transfer port2 to the iframe.
    const iframeWindow = iframeRef.current.contentWindow;
    if (!iframeWindow) return;
    iframeWindow.postMessage(
      { kind: 'icoder:open-port', psid: session.preview_session_id },
      IFRAME_ORIGIN,
      [channel.port2],
    );
  }, [session, toast]);

  // ─── Restart = tear down current session, mint a new one ───────────
  const restart = useCallback(() => {
    setEvents([]);
    setCreditsConsumed(0);
    // Revoke old session if any, then create a fresh one.
    const old = pendingTicketRef.current;
    if (old) {
      fetch(`${BACKEND_ORIGIN}/api/embedded/preview-sessions/${old.preview_session_id}/revoke`, {
        method: 'POST',
        headers: accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {},
        credentials: 'include',
      }).catch(() => { /* fire-and-forget */ });
    }
    pendingTicketRef.current = null;
    setSession(null);
    createSession();
  }, [accessToken, createSession]);

  // ─── code generators ────────────────────────────────────────────────
  const htmlCode = useMemo(() => generateHtml(config), [config]);
  const reactCode = useMemo(() => generateReact(config), [config]);
  const jsonCode = useMemo(() => JSON.stringify(config, null, 2), [config]);
  const codeForActiveTab = codeTab === 'html' ? htmlCode : codeTab === 'react' ? reactCode : jsonCode;

  const copyCode = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(codeForActiveTab);
      setCopied(true);
      toast(`${codeTab.toUpperCase()} ${t.embeddedCopySnippetCopied}`, 'success');
      setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      toast(`${t.embeddedCopyFailed}: ${String(e)}`, 'error');
    }
  }, [codeForActiveTab, codeTab, toast, t.embeddedCopySnippetCopied, t.embeddedCopyFailed]);

  const update = <K extends keyof EmbeddedConfig>(key: K, value: EmbeddedConfig[K]) =>
    setConfig((c) => ({ ...c, [key]: value }));

  const updateFeature = (key: keyof EmbeddedConfig['features'], value: boolean) =>
    setConfig((c) => ({ ...c, features: { ...c.features, [key]: value } }));

  const updateLocale = (key: keyof EmbeddedConfig['locale'], value: string) =>
    setConfig((c) => ({ ...c, locale: { ...c.locale, [key]: value } }));

  return (
    <div className="min-h-dvh bg-background">
      {/* Page-level header with live cost + reset */}
      <div className="border-b border-border/30 px-6 py-3 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">{t.embeddedAssistantTitle}</h1>
          <p className="text-xs text-muted-foreground mt-0.5">{t.embeddedPageSubtitle}</p>
        </div>
        <div className="flex items-center gap-3">
          {creditsConsumed > 0 && (
            <span className="text-xs font-mono text-muted-foreground tabular-nums">¥{creditsConsumed.toFixed(6)}</span>
          )}
          {session && (
            <span className="text-[10px] font-mono text-muted-foreground/70">
              psid={session.preview_session_id.slice(0, 8)}…
            </span>
          )}
          <button
            onClick={() => { setEvents([]); setCreditsConsumed(0); }}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs border border-border rounded-md hover:bg-muted/40 transition-colors"
            title={t.resetLiveCost ?? 'Reset live cost'}
          >
            <RefreshCw className="w-3 h-3" /> {t.resetLiveCost ?? 'Reset'}
          </button>
        </div>
      </div>

      <div className="px-6 py-4 space-y-3 max-w-7xl mx-auto">
        {/* ─── Preview pane ─── */}
        <section className="border border-border/40 rounded-lg overflow-hidden bg-card">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border/30 bg-muted/20">
            <span className="text-xs font-medium text-muted-foreground">{t.embeddedPreview}</span>
            <div className="flex items-center gap-2">
              <div className="flex border border-border rounded-md overflow-hidden">
                <button
                  onClick={() => setDevice('desktop')}
                  className={`px-2 py-1 flex items-center gap-1 text-[11px] transition-colors ${device === 'desktop' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted/40'}`}
                >
                  <Monitor className="w-3 h-3" /> {t.embeddedDesktop}
                </button>
                <button
                  onClick={() => setDevice('mobile')}
                  className={`px-2 py-1 flex items-center gap-1 text-[11px] transition-colors ${device === 'mobile' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted/40'}`}
                >
                  <Smartphone className="w-3 h-3" /> {t.embeddedMobile}
                </button>
              </div>
              <button
                onClick={restart}
                disabled={bootstrapping}
                className="px-2 py-1 flex items-center gap-1 text-[11px] border border-border rounded-md hover:bg-muted/40 disabled:opacity-50 disabled:cursor-wait"
                title={t.embeddedRestart}
              >
                <Power className="w-3 h-3" /> {t.embeddedRestart}
              </button>
            </div>
          </div>
          <div className="flex justify-center p-4 bg-muted/10">
            {previewUrl ? (
              <iframe
                key={previewKey}
                ref={iframeRef}
                src={previewUrl}
                onLoad={onIframeLoad}
                title="Embedded Preview"
                sandbox="allow-scripts allow-same-origin"
                // referrerpolicy=no-referrer strips iframe URL from widget fetch() Referer (T4)
                referrerPolicy="no-referrer"
                className="border border-border/40 rounded-md bg-white shadow-sm transition-all"
                style={{
                  width: device === 'mobile' ? '390px' : '100%',
                  maxWidth: device === 'mobile' ? '390px' : '640px',
                  height: '500px',
                }}
              />
            ) : (
              <div className="flex items-center justify-center w-full max-w-[640px] h-[500px] text-xs text-muted-foreground">
                {bootstrapping ? 'Minting preview ticket…' : 'No preview session'}
              </div>
            )}
          </div>
        </section>

        {/* ─── Event Inspector ─── */}
        <EventInspector events={events} creditsConsumed={creditsConsumed} />

        {/* ─── Configuration pane ─── */}
        <section className="border border-border/40 rounded-lg overflow-hidden bg-card">
          <div className="flex border-b border-border/30">
            <button
              onClick={() => setConfigTab('settings')}
              className={`flex-1 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors ${configTab === 'settings' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
            >
              {t.settings}
            </button>
            <button
              onClick={() => setConfigTab('code')}
              className={`flex-1 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors ${configTab === 'code' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
            >
              {t.code}
            </button>
          </div>

          {configTab === 'settings' && (
            <div className="p-4 grid grid-cols-2 gap-x-6 gap-y-4 text-xs">
              {/* Agent + Patient */}
              <div className="space-y-3 col-span-2 sm:col-span-1">
                <h3 className="text-xs font-semibold text-foreground">{t.embeddedSessionDefaults}</h3>
                <label className="block">
                  <span className="text-[11px] text-muted-foreground">{t.embeddedAgent}</span>
                  <select
                    value={config.agentRef}
                    onChange={(e) => update('agentRef', e.target.value)}
                    className="mt-1 w-full px-2 py-1 border border-border rounded text-xs bg-background"
                  >
                    {(agents.length ? agents : [config.agentRef]).map((ref) => (
                      <option key={ref} value={ref}>{ref}</option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="text-[11px] text-muted-foreground">{t.embeddedPatientId}</span>
                  <input value={config.patientId} onChange={(e) => update('patientId', e.target.value)} className="mt-1 w-full px-2 py-1 border border-border rounded text-xs bg-background" />
                </label>
                <label className="block">
                  <span className="text-[11px] text-muted-foreground">{t.embeddedPatientName}</span>
                  <input value={config.patientName} onChange={(e) => update('patientName', e.target.value)} className="mt-1 w-full px-2 py-1 border border-border rounded text-xs bg-background" />
                </label>
                <label className="block">
                  <span className="text-[11px] text-muted-foreground">{t.embeddedEncounterId}</span>
                  <input value={config.encounterId} onChange={(e) => update('encounterId', e.target.value)} className="mt-1 w-full px-2 py-1 border border-border rounded text-xs bg-background" />
                </label>
                <p className="text-[10px] text-muted-foreground/80 italic pt-1">
                  Patient context flows via secured MessageChannel — never in iframe URL.
                </p>
              </div>

              {/* Features + Locale */}
              <div className="space-y-3 col-span-2 sm:col-span-1">
                <h3 className="text-xs font-semibold text-foreground">{t.embeddedFeatures}</h3>
                {([
                  ['aiChat', t.embeddedFeatureAiChat],
                  ['documentFeedback', t.embeddedFeatureDocFeedback],
                  ['virtualMode', t.embeddedFeatureVirtualMode],
                  ['showNavigation', t.embeddedFeatureShowNav],
                ] as const).map(([key, label]) => (
                  <label key={key} className="flex items-center justify-between text-xs cursor-pointer">
                    <span>{label}</span>
                    <button
                      onClick={() => updateFeature(key, !config.features[key])}
                      className={`relative w-8 h-4 rounded-full transition-colors ${config.features[key] ? 'bg-primary' : 'bg-muted'}`}
                    >
                      <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${config.features[key] ? 'translate-x-4' : 'translate-x-0.5'}`} />
                    </button>
                  </label>
                ))}
                <label className="block pt-2">
                  <span className="text-[11px] text-muted-foreground">{t.embeddedInterfaceLanguage}</span>
                  <select
                    value={config.locale.interfaceLanguage}
                    onChange={(e) => updateLocale('interfaceLanguage', e.target.value)}
                    className="mt-1 w-full px-2 py-1 border border-border rounded text-xs bg-background"
                  >
                    <option value="zh-CN">{t.embeddedLangZhCN}</option>
                    <option value="en-US">{t.embeddedLangEnUS}</option>
                  </select>
                </label>
                <label className="block">
                  <span className="text-[11px] text-muted-foreground">{t.embeddedPrimaryColor}</span>
                  <input type="color" value={config.primaryColor} onChange={(e) => update('primaryColor', e.target.value)} className="mt-1 w-full h-6 border border-border rounded bg-background" />
                </label>
              </div>
            </div>
          )}

          {configTab === 'code' && (
            <div>
              <div className="flex items-center justify-between border-b border-border/30 px-2">
                <div className="flex">
                  {(['html', 'react', 'json'] as const).map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setCodeTab(tab)}
                      className={`px-3 py-1.5 text-[11px] font-mono uppercase border-b-2 -mb-px transition-colors ${codeTab === tab ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
                    >
                      {tab === 'html' ? t.embeddedHtmlTab : tab === 'react' ? t.embeddedReactTab : t.embeddedJsonConfigTab}
                    </button>
                  ))}
                </div>
                <button
                  onClick={copyCode}
                  className="flex items-center gap-1 px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
                >
                  {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                  {copied ? t.copied : t.copy}
                </button>
              </div>
              <pre className="text-[11px] font-mono p-3 overflow-x-auto bg-muted/10 max-h-96 overflow-y-auto">
                <code>{codeForActiveTab}</code>
              </pre>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

// ─── code generators ───────────────────────────────────────────────────
// Gate 13A-7 — patient context placeholders only (never leak real PHI).
function generateHtml(c: EmbeddedConfig): string {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>iCoDer Embedded — ${c.agentRef}</title>
</head>
<body>
  <icoder-embedded id="assistant"></icoder-embedded>

  <script type="module">
    // 1. Backend URL — replace with your iCoDer tenant
    const BASE_URL = window.location.origin.startsWith('http://localhost')
      ? 'http://localhost:8000'
      : 'https://YOUR_TENANT.icoder.cloud';

    // 2. Token — mint server-side via your backend's /token endpoint
    //    (client_credentials). NEVER ship a real token in copied code.
    const ACCESS_TOKEN = 'YOUR_SERVER_ISSUED_SESSION_TOKEN';

    document.getElementById('assistant').setAttribute('baseURL', BASE_URL);
    await import(BASE_URL + '/api/embedded/assistant.js');

    const a = document.getElementById('assistant');
    a.addEventListener('embedded-event', (e) => {
      const { name, payload } = e.detail;
      console.log(name, payload);
    });

    await a.auth({ access_token: ACCESS_TOKEN, token_type: 'bearer', mode: 'stateless' });
    await a.configureSession({
      defaultTemplateKey: ${JSON.stringify(c.agentRef)},
      defaultLanguage: ${JSON.stringify(c.locale.dictationLanguage)},
      defaultOutputLanguage: ${JSON.stringify(c.locale.interfaceLanguage)},
      // Replace with your real patient context (typically from your HIS/EMR)
      patientId: 'YOUR_PATIENT_ID',
      name: 'YOUR_PATIENT_NAME',
      encounterId: 'YOUR_ENCOUNTER_ID',
    });
    await a.configure({
      features: ${JSON.stringify(c.features, null, 6)},
      locale: { dictationLanguage: ${JSON.stringify(c.locale.dictationLanguage)}, interfaceLanguage: ${JSON.stringify(c.locale.interfaceLanguage)} },
    });
    await a.show();
  </script>
</body>
</html>`;
}

function generateReact(c: EmbeddedConfig): string {
  return `import { useEffect, useRef } from 'react';

export default function MyEmbeddedWidget({ accessToken }: { accessToken: string }) {
  const ref = useRef<any>(null);

  useEffect(() => {
    const BASE_URL = 'https://YOUR_TENANT.icoder.cloud';
    import(/* @vite-ignore */ BASE_URL + '/api/embedded/assistant.js');

    const a = ref.current;
    if (!a) return;

    const handler = (e: any) => {
      const { name, payload } = e.detail;
      console.log(name, payload);
    };
    a.addEventListener('embedded-event', handler);

    (async () => {
      await a.auth({ access_token: accessToken, token_type: 'bearer', mode: 'stateless' });
      await a.configureSession({
        defaultTemplateKey: ${JSON.stringify(c.agentRef)},
        defaultLanguage: ${JSON.stringify(c.locale.dictationLanguage)},
        defaultOutputLanguage: ${JSON.stringify(c.locale.interfaceLanguage)},
        // Replace with your real patient context
        patientId: 'YOUR_PATIENT_ID',
        name: 'YOUR_PATIENT_NAME',
        encounterId: 'YOUR_ENCOUNTER_ID',
      });
      await a.configure({
        features: ${JSON.stringify(c.features, null, 6)},
        locale: { dictationLanguage: ${JSON.stringify(c.locale.dictationLanguage)}, interfaceLanguage: ${JSON.stringify(c.locale.interfaceLanguage)} },
      });
      await a.show();
    })();

    return () => a.removeEventListener('embedded-event', handler);
  }, [accessToken]);

  return <icoder-embedded ref={ref} baseURL="https://YOUR_TENANT.icoder.cloud" />;
}`;
}
