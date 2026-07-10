// Phase 3-B2 Loop 2 - Chat with a cloned (project-scoped) Agent.
//
// Route: /agents/:project_agent_id/chat?preset={agent_ref}
//
// Loop 2 (Gap 2.2) - Click-to-Chat UX:
//   - Hub CTA "Chat / Use Agent" calls clone endpoint (Loop 1), then
//     navigates here with the returned project_agent_id.
//   - This page fetches the agent by ID (route guard: 404 → redirect to
//     /ai-studio/agents so the user re-clones).
//   - Submits input via A2A mainline (POST /api/icoder/agents/{agent_id}/v1/message:send).
//   - Renders result in a Tab-switched Output Panel (Rendered / JSON):
//     • Rendered: markdown rendered as HTML tables (Loop 3, Gap 4.3).
//     • JSON: pretty-printed v2 8-field structured output.
//
// The `?preset={agent_ref}` query param is informational - it lets the
// chat page pre-fill a greeting or context hint based on the source
// agent's use case (e.g. medical-coding → "请为以下病历进行 ICD 编码").
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom';
import {
  Bot, Send, Loader2, AlertCircle, CheckCircle2, Activity,
  ChevronRight, Paperclip, X, User, Copy, Clipboard,
} from 'lucide-react';
import { agentsApi, oauthApi } from '../services/api';
import { runtimeAgentApi } from '../services/runtimeApi';
import { useToastStore } from '../store';
import type { RuntimeRunResult } from '../types/runtime';
import {
  generateFallbackMarkdown,
  RenderedMarkdown,
} from '../utils/medicalCodingMarkdown';
import { useT } from '../i18n';
import AgentConfigSidebar from '../components/agents/AgentConfigSidebar';

const PRESET_GREETINGS_BY_REF: Record<string, string> = {
  'icoder/medical-coding-agent@2.0.0': 'medicalCoding',
};

type OutputTab = 'rendered' | 'json';

type ChatMessage = {
  id: string;
  role: 'user' | 'agent';
  text: string;
  result?: RuntimeRunResult | any | null;
  error?: string | null;
  attachedFiles?: string[];
  ts: number;
};

let _msgCounter = 0;
const newMsgId = () => `msg-${++_msgCounter}-${Date.now()}`;

export default function AgentChatPage() {
  // Phase 4-D: support both new /ai-studio/agents/:agentId/chat and legacy
  // /agents/:project_agent_id/chat routes.
  const { agentId, project_agent_id: projectAgentId } = useParams<{ agentId?: string; project_agent_id?: string }>();
  const effectiveAgentId = agentId || projectAgentId || '';
  const [searchParams] = useSearchParams();
  const preset = searchParams.get('preset') || '';
  const navigate = useNavigate();
  const toast = useToastStore((s) => s.addToast);
  const t = useT();

  const [agent, setAgent] = useState<any | null>(null);
  const [agentLoading, setAgentLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [attachedFiles, setAttachedFiles] = useState<{ name: string; content: any }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [outputTab, setOutputTab] = useState<OutputTab>('rendered');
  // Phase 4-F3 §5.3: API Client dropdown (placeholder — selection is not
  // yet wired into the run request; per prompt §10.3 a non-functional
  // dropdown is acceptable for F3).
  const [apiClients, setApiClients] = useState<any[]>([]);
  const [selectedApiClient, setSelectedApiClient] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const historyEndRef = useRef<HTMLDivElement>(null);

  // Route guard: fetch the cloned agent. If 404, redirect to Hub so the
  // user re-clones (Loop 2 acceptance: "未 Clone 的 Agent 不能直接进入 Chat").
  useEffect(() => {
    if (!effectiveAgentId) {
      setNotFound(true);
      setAgentLoading(false);
      return;
    }
    setAgentLoading(true);
    agentsApi
      .get(effectiveAgentId)
      .then((r) => {
        setAgent(r.data);
        setNotFound(false);
      })
      .catch((err) => {
        const status = err?.response?.status;
        if (status === 404) {
          setNotFound(true);
          toast(t.agentChatNotFoundToast, 'error');
          // Redirect after a short delay so the toast is visible.
          setTimeout(() => navigate('/ai-studio/agents', { replace: true }), 800);
        } else {
          toast(`${t.agentChatLoadFailed}: ${err?.message || 'unknown'}`, 'error');
        }
      })
      .finally(() => setAgentLoading(false));
  }, [effectiveAgentId, navigate, toast, t]);

  // Phase 4-F3 §5.3: load API clients for the dropdown (best-effort).
  useEffect(() => {
    oauthApi.list().then(r => {
      const list = r.data?.clients || [];
      setApiClients(list);
      if (list.length > 0) setSelectedApiClient(list[0].client_id);
    }).catch(() => {});
  }, []);

  // Phase 4-G #3: hydrate RunHistory dropdown on page load + refresh after
  // each run completes so the user sees their recent runs without a page refresh.
  // Defined after `runtimeAgentId` (below) — keep ordering intact.
  const [runHistory, setRunHistory] = useState<any[]>([]);

  // Derive the runtime agent_id (short form) from agent.config.agent_ref
  // or fall back to the source_agent_ref if present. Used for the A2A path.
  const runtimeAgentId = (() => {
    const cfg = agent?.config || {};
    const ref = cfg.source_agent_ref || cfg.agent_ref || '';
    if (!ref) return '';
    const tail = ref.split('/').pop() || '';
    return tail.split('@')[0];
  })();

  // Phase 4-G #3: hydrate RunHistory dropdown on page load + refresh after
  // each run completes so the user sees their recent runs without a page refresh.
  const refreshRunHistory = useCallback(() => {
    if (!runtimeAgentId) {
      setRunHistory([]);
      return;
    }
    runtimeAgentApi.getRunHistory(runtimeAgentId, 20).then(r => {
      setRunHistory(r?.items || []);
    }).catch(() => {});
  }, [runtimeAgentId]);

  useEffect(() => { refreshRunHistory(); }, [refreshRunHistory]);

  const greeting = useMemo(() => {
    if (preset && PRESET_GREETINGS_BY_REF[preset] === 'medicalCoding') {
      return t.agentChatGreetingMedicalCoding;
    }
    return agent?.description
      ? t.agentChatAgentDescriptionPrefix.replace('{desc}', agent.description)
      : t.agentChatDefaultGreeting;
  }, [preset, agent, t]);

  const onSubmit = useCallback(async () => {
    if (!input.trim() || loading || !runtimeAgentId) return;
    const userText = input.trim();
    const userMsg: ChatMessage = {
      id: newMsgId(),
      role: 'user',
      text: userText,
      attachedFiles: attachedFiles.map(f => f.name),
      ts: Date.now(),
    };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    const filesForRun = [...attachedFiles];
    setAttachedFiles([]);
    setLoading(true);
    setError(null);
    try {
      // Phase 4-F1 (2026-07-10): Medical Coding Agent uses the unified
      // Agent Run API (POST /api/v1/agents/{id}/run) with the G001
      // `corti_like_fast` fast path (~9-10s on T12). The A2A message:send
      // path routes to MedCodER 5-stage pipeline and 60s-timeouts.
      const isMedicalCoding =
        runtimeAgentId === 'medical-coding-agent' ||
        (agent?.config?.source_agent_ref || '').includes('medical-coding-agent');
      let data: RuntimeRunResult | any;
      if (isMedicalCoding) {
        // Unified path — agentRun returns AgentRunResponse; runAgentUnified
        // maps it to RuntimeRunResult for MessageBubble compatibility.
        // Attached JSON files go through `extra` since the unified
        // endpoint takes a single `input.text` (not A2A parts).
        const extra: Record<string, unknown> = {};
        if (filesForRun.length === 1) {
          extra.context_file = filesForRun[0];
        } else if (filesForRun.length > 1) {
          extra.context_files = filesForRun;
        }
        data = await runtimeAgentApi.runAgentUnified(runtimeAgentId, userText, {
          runtime_mode: 'corti_like_fast',
          include_trace: true,
          include_evidence: true,
          extra,
          api_client_id: selectedApiClient || undefined,
        });
      } else {
        // Phase 4-F3 §2.1: non-Medical-Coding agents also use the unified
        // Agent Run API. The unified endpoint routes through
        // ProviderRegistry → PureLLMProvider for these agents.
        // (Previously this used A2A message:send which doesn't persist
        // trace_events to RunTraceStore.)
        const extra: Record<string, unknown> = {};
        if (filesForRun.length === 1) {
          extra.context_file = filesForRun[0];
        } else if (filesForRun.length > 1) {
          extra.context_files = filesForRun;
        }
        data = await runtimeAgentApi.runAgentUnified(runtimeAgentId, userText, {
          include_trace: true,
          include_evidence: true,
          extra,
          api_client_id: selectedApiClient || undefined,
        });
      }
      setMessages(prev => [...prev, {
        id: newMsgId(),
        role: 'agent',
        text: data?.markdown ? '' : (data?.structured ? '' : (data?.output || data?.summary || '')),
        result: data,
        ts: Date.now(),
      }]);
      toast(t.agentChatRunComplete, 'success');
      // Phase 4-G #3: refresh history dropdown so the just-completed run appears.
      refreshRunHistory();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || t.agentChatRunFailed;
      const errMsg = typeof msg === 'string' ? msg : JSON.stringify(msg);
      setError(errMsg);
      setMessages(prev => [...prev, {
        id: newMsgId(),
        role: 'agent',
        text: '',
        error: errMsg,
        ts: Date.now(),
      }]);
      toast(t.agentChatRunFailed, 'error');
    } finally {
      setLoading(false);
    }
  }, [input, loading, runtimeAgentId, agent, attachedFiles, toast, t]);

  // Corti-style: Ctrl+Enter to submit, plain Enter = newline.
  const onTextareaKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      onSubmit();
    }
  }, [onSubmit]);

  // Add context - JSON file picker (Corti "Add context" button).
  const onAddContextClick = useCallback(() => {
    fileInputRef.current?.click();
  }, [fileInputRef]);

  const onFileSelected = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const content = JSON.parse(String(reader.result));
          setAttachedFiles(prev => [...prev, { name: file.name, content }]);
        } catch {
          toast(`${t.agentChatBadJson || 'Invalid JSON'}: ${file.name}`, 'error');
        }
      };
      reader.readAsText(file);
    });
    // Clear input so same file can be re-selected.
    e.target.value = '';
  }, [toast, t]);

  const removeAttachedFile = useCallback((name: string) => {
    setAttachedFiles(prev => prev.filter(f => f.name !== name));
  }, []);

  // Auto-scroll to bottom on new message.
  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, loading]);

  // Loading state - agent metadata fetch
  if (agentLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-muted/20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Not found - route guard kicked in, redirect already dispatched.
  if (notFound) {
    return (
      <div className="flex-1 flex items-center justify-center bg-muted/20 p-6">
        <div className="text-center">
          <AlertCircle className="h-10 w-10 mx-auto mb-3 text-amber-500" />
          <p className="text-sm font-medium text-foreground">{t.agentChatNotCloned}</p>
          <p className="text-xs text-muted-foreground mt-1">
            {t.agentChatRedirecting}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-muted/20">
      {/* Phase 4-D - Corti-style breadcrumb: Agents > {agent_name} */}
      <div className="px-6 py-3 border-b border-border/40 bg-background flex items-center gap-2 text-sm">
        <Link
          to="/ai-studio/agents"
          className="text-muted-foreground hover:text-foreground transition-colors duration-200 flex items-center gap-1"
        >
          <Bot size={14} />
          <span>{t.agentChatBreadcrumbAgents}</span>
        </Link>
        <ChevronRight size={14} className="text-muted-foreground/60" />
        <span className="text-foreground font-medium truncate">
          {agent?.name || t.agentChatAgentFallback}
        </span>
        {agent?.config?.source_agent_ref && (
          <span className="text-[10px] px-2 py-0.5 rounded bg-muted text-muted-foreground font-mono ml-auto">
            {t.agentChatSourceRef.replace('{ref}', agent.config.source_agent_ref)}
          </span>
        )}
      </div>
      {/* Header - agent identity + version */}
      <div className="px-6 py-4 border-b border-border/40 bg-background flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
          <Bot size={15} className="text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-base font-brand font-bold text-foreground truncate tracking-tight">
              {agent?.name || t.agentChatAgentFallback}
            </p>
            <span className="text-[10px] font-mono text-muted-foreground">
              v{agent?.version || '1.0.0'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground truncate">
            {agent?.description || greeting}
          </p>
        </div>
      </div>

      {/* Phase 4-D - 2-pane layout: left chat (flex-1) + right AgentConfigSidebar (w-400) */}
      <div className="flex-1 flex min-h-0">
      {/* Left chat pane - Corti-style: scrollable message history + bottom input bar */}
      <div className="flex-1 flex flex-col min-h-0">
        {/* Message history (scrollable) */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* Greeting / preset hint - shown only when no messages yet */}
          {messages.length === 0 && (
            <div className="bg-background rounded-xl p-4 max-w-2xl mx-auto">
              <p className="text-xs text-muted-foreground">{greeting}</p>
            </div>
          )}

          {messages.map(m => (
            <MessageBubble key={m.id} message={m} t={t} outputTab={outputTab} setOutputTab={setOutputTab} />
          ))}

          {loading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground pl-2">
              <Loader2 size={12} className="animate-spin" />
              <span>{t.agentChatRunning}</span>
            </div>
          )}

          {/* Generic error banner (kept for parity; per-message error renders inline) */}
          {error && messages.length === 0 && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-2">
              <AlertCircle size={16} className="text-red-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-medium text-red-700">{t.agentChatRunFailedTitle}</p>
                <p className="text-xs text-red-600 mt-1 break-all">{error}</p>
              </div>
            </div>
          )}
          <div ref={historyEndRef} />
        </div>

        {/* Bottom input bar - Corti-style: Add context + textarea + helper text. Ctrl+Enter to submit. */}
        <div className="border-t border-border/40 bg-background px-6 py-3">
          {/* Phase 4-G #3: RunHistory dropdown — recent runs for this agent */}
          {runHistory.length > 0 && (
            <div className="flex items-center gap-2 mb-2">
              <Activity size={11} className="text-muted-foreground shrink-0" />
              <select
                value=""
                onChange={e => {
                  const runId = e.target.value;
                  if (runId) navigate(`/ai-studio/runs/${encodeURIComponent(runId)}/trace`);
                }}
                className="text-[10px] text-muted-foreground bg-transparent border border-border rounded-md px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-ring max-w-[280px] truncate"
                title={t.agentChatRunHistory || 'Recent runs'}
                disabled={loading}
              >
                <option value="">{t.agentChatRunHistory || 'Recent runs'} ({runHistory.length})</option>
                {runHistory.map((r: any) => (
                  <option key={r.run_id} value={r.run_id}>
                    {new Date(r.created_at).toLocaleString()} · {r.latency_ms}ms · ${typeof r.cost_usd === 'number' ? r.cost_usd.toFixed(6) : '0.000000'}
                    {r.error ? ' · error' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}
          {/* Attached files chips */}
          {attachedFiles.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {attachedFiles.map(f => (
                <span
                  key={f.name}
                  className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md bg-primary/10 text-primary"
                >
                  <Paperclip size={10} />
                  <span className="font-mono truncate max-w-[200px]">{f.name}</span>
                  <button
                    onClick={() => removeAttachedFile(f.name)}
                    className="hover:bg-primary/20 rounded p-0.5"
                    aria-label={t.agentChatRemoveAttachment || 'Remove'}
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2">
            {/* Add context button */}
            <button
              onClick={onAddContextClick}
              disabled={loading}
              className="shrink-0 inline-flex items-center gap-1 text-[11px] px-2.5 py-2 rounded-md border border-border text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-40 transition-colors duration-200 active:scale-[0.98]"
              title={t.agentChatAddContext}
            >
              <Paperclip size={12} />
              <span>{t.agentChatAddContext}</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/json,.json"
              multiple
              onChange={onFileSelected}
              className="hidden"
            />
            {/* Phase 4-F3 §5.3: API Client dropdown — placeholder selector */}
            {apiClients.length > 0 && (
              <select
                value={selectedApiClient}
                onChange={e => setSelectedApiClient(e.target.value)}
                className="shrink-0 text-[10px] text-muted-foreground bg-transparent border border-border rounded-md px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-ring max-w-[120px]"
                title={t.agentChatApiClient || 'API Client'}
                disabled={loading}
              >
                {apiClients.map((c: any) => (
                  <option key={c.client_id} value={c.client_id}>
                    {c.name || c.client_id}
                  </option>
                ))}
              </select>
            )}
            {/* Textarea - Corti placeholder + Ctrl+Enter submit */}
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onTextareaKeyDown}
              placeholder={t.agentChatTextareaPlaceholder}
              rows={2}
              className="flex-1 text-sm bg-transparent border border-border rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-ring/40 leading-relaxed disabled:opacity-50"
              disabled={loading}
            />
          </div>
          {/* Helper text - Corti "Messaging an agent consumes credits" + Ctrl+Enter hint */}
          <div className="flex items-center justify-between mt-1.5">
            <span className="text-[10px] text-muted-foreground">
              {t.agentChatConsumesCredits}
            </span>
            <span className="text-[10px] text-muted-foreground/70 tabular-nums">
              {input.length} {t.agentChatCharCount} · ⌘+↵
            </span>
          </div>
        </div>
      </div>
      {/* Right sidebar - Corti-style Settings/Code dual panel */}
      {agent && (
        <AgentConfigSidebar agent={agent} onAgentUpdated={(updated) => setAgent(updated)} />
      )}
      </div>
    </div>
  );
}

// ── Message bubble - Corti-style chat turn ──
function MessageBubble({
  message, t, outputTab, setOutputTab,
}: {
  message: ChatMessage;
  t: any;
  outputTab: OutputTab;
  setOutputTab: (tab: OutputTab) => void;
}) {
  const isUser = message.role === 'user';
  const result = message.result;
  const isAgentError = !isUser && message.error;

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${
        isUser ? 'bg-primary/15' : isAgentError ? 'bg-red-100' : 'bg-muted'
      }`}>
        {isUser ? (
          <User size={13} className="text-primary" />
        ) : isAgentError ? (
          <AlertCircle size={13} className="text-red-600" />
        ) : (
          <Bot size={13} className="text-foreground" />
        )}
      </div>
      {/* Bubble body */}
      <div className={`flex-1 min-w-0 max-w-[85%] ${isUser ? 'items-end' : ''}`}>
        {/* User text + attached file chips */}
        {isUser && (
          <div className="bg-primary/10 rounded-lg px-3 py-2 inline-block">
            {message.text && <p className="text-sm text-foreground whitespace-pre-wrap">{message.text}</p>}
            {message.attachedFiles && message.attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {message.attachedFiles.map(name => (
                  <span key={name} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-background/60 text-foreground/80">
                    <Paperclip size={9} />
                    <span className="font-mono truncate max-w-[150px]">{name}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
        {/* Agent error */}
        {isAgentError && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            <p className="text-xs font-medium text-red-700">{t.agentChatRunFailedTitle}</p>
            <p className="text-[11px] text-red-600 mt-1 break-all">{message.error}</p>
          </div>
        )}
        {/* Agent result */}
        {!isUser && result && (
          <div className="bg-background rounded-xl px-3 py-2">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle2 size={12} className="text-green-600" />
              <p className="text-xs font-semibold text-foreground">{t.agentChatResult}</p>
              {result.runtime_mode && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                  {result.runtime_mode}
                </span>
              )}
              {result.processing_time_ms ? (
                <span className="text-[10px] text-muted-foreground ml-auto tabular-nums">
                  {t.agentChatDuration} {result.processing_time_ms}ms
                </span>
              ) : result.latency_ms ? (
                <span className="text-[10px] text-muted-foreground ml-auto tabular-nums">
                  {t.agentChatDuration} {result.latency_ms}ms
                </span>
              ) : null}
              {result.run_id && (
                <Link
                  to={`/runs/${encodeURIComponent(result.run_id)}/trace`}
                  className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md border border-border hover:bg-accent transition-colors duration-200 active:scale-[0.98] text-muted-foreground hover:text-foreground"
                  title={t.agentChatViewRunTraceHint}
                >
                  <Activity size={11} />
                  {t.agentChatViewRunTrace}
                </Link>
              )}
            </div>
            {result.summary && (
              <p className="text-xs text-foreground mb-2 leading-relaxed">{result.summary}</p>
            )}
            {result.manual_review_required && (
              <div className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mb-2">
                🔍 {t.agentChatManualReviewRequired || '人工复核提示：本次运行结果需经编码员人工确认。'}
              </div>
            )}
            {Array.isArray(result.issues_found) && result.issues_found.length > 0 && (
              <div className="text-[10px] text-amber-700 mb-2">
                ⚠️ {result.issues_found.join('; ')}
              </div>
            )}
            <div className="flex items-center rounded-md border border-border p-0.5 mb-2 w-fit">
              {([
                { id: 'rendered' as OutputTab, label: t.agentChatRenderedTab },
                { id: 'json' as OutputTab, label: t.agentChatJsonTab },
              ]).map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setOutputTab(tab.id)}
                  className={`px-2.5 py-0.5 text-[11px] font-medium rounded transition-colors duration-200 active:scale-[0.98] ${
                    outputTab === tab.id
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            {/* Phase 4-F: Copy JSON / Copy Markdown buttons (Corti-style §5.3) */}
            <div className="flex items-center gap-2 mb-2">
              <button
                onClick={() => navigator.clipboard?.writeText(
                  JSON.stringify(result.trace_events && result.trace_events.length
                    ? { ...result.structured, trace_id: result.trace_id, runtime_mode: result.runtime_mode, latency_ms: result.latency_ms, trace_events: result.trace_events, cost: result.cost }
                    : (result.structured || result), null, 2),
                )}
                className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md border border-border hover:bg-accent transition-colors duration-200 active:scale-[0.98] text-muted-foreground hover:text-foreground"
                title="Copy JSON output"
              >
                <Copy size={10} /> Copy JSON
              </button>
              <button
                onClick={() => navigator.clipboard?.writeText(
                  `# Agent Run Result\n\nRun ID: ${result.run_id || ''} | Trace ID: ${result.trace_id || ''} | Runtime: ${result.runtime_mode || 'a2a'} | Latency: ${result.latency_ms || result.processing_time_ms || 0}ms\n\n${result.summary ? `**Summary:** ${result.summary}\n\n` : ''}${result.markdown || generateFallbackMarkdown(result.structured || result)}`,
                )}
                className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md border border-border hover:bg-accent transition-colors duration-200 active:scale-[0.98] text-muted-foreground hover:text-foreground"
                title="Copy Markdown output"
              >
                <Clipboard size={10} /> Copy Markdown
              </button>
            </div>
            {/* Phase 4-F1: inline trace_events viewer (Event Inspector) —
             * unified endpoint returns trace_events inline; dedicated
             * /runs/{id}/trace viewer doesn't see them because the unified
             * facade doesn't persist to runtime runs storage (known gap). */}
            {Array.isArray(result.trace_events) && result.trace_events.length > 0 && (
              <details className="mb-2 border border-border/40 rounded-md">
                <summary className="text-[10px] font-medium text-muted-foreground px-2 py-1 cursor-pointer hover:bg-accent/40 transition-colors">
                  📋 Trace Events ({result.trace_events.length})
                </summary>
                <div className="px-2 pb-2 space-y-1">
                  {result.trace_events.map((ev: any, i: number) => (
                    <div key={i} className="text-[10px] font-mono leading-relaxed flex gap-2">
                      <span className="text-muted-foreground tabular-nums shrink-0">
                        [{i + 1}]
                      </span>
                      <span className="text-foreground font-medium">
                        {ev.step || ev.event || ev.name || '?'}
                      </span>
                      {ev.status && (
                        <span className={`px-1 rounded ${
                          ev.status === 'ok' ? 'bg-green-100 text-green-700'
                          : ev.status === 'error' ? 'bg-red-100 text-red-700'
                          : 'bg-muted text-muted-foreground'
                        }`}>
                          {ev.status}
                        </span>
                      )}
                      {typeof ev.duration_ms === 'number' && (
                        <span className="text-muted-foreground tabular-nums">
                          {ev.duration_ms}ms
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </details>
            )}
            {outputTab === 'rendered' ? (
              <RenderedMarkdown
                markdown={
                  result.markdown ||
                  generateFallbackMarkdown(result.structured || result)
                }
              />
            ) : (
              <pre className="text-[10px] bg-muted/30 rounded-md p-2 overflow-x-auto max-h-80 font-mono leading-relaxed">
                {JSON.stringify(result.structured || result, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

