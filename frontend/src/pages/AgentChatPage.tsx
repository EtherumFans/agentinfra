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
  ChevronRight, Paperclip, X, User,
} from 'lucide-react';
import { agentsApi } from '../services/api';
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

  // Derive the runtime agent_id (short form) from agent.config.agent_ref
  // or fall back to the source_agent_ref if present. Used for the A2A path.
  const runtimeAgentId = (() => {
    const cfg = agent?.config || {};
    const ref = cfg.source_agent_ref || cfg.agent_ref || '';
    if (!ref) return '';
    const tail = ref.split('/').pop() || '';
    return tail.split('@')[0];
  })();

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
      // Build extra parts: JSON files → DataPart.
      const extraParts = filesForRun.map(f => ({
        kind: 'data',
        data: f.content,
        metadata: { filename: f.name, source: 'add-context' },
      }));
      const data = await runtimeAgentApi.runAgentViaA2A(runtimeAgentId, userText, extraParts);
      setMessages(prev => [...prev, {
        id: newMsgId(),
        role: 'agent',
        text: data?.markdown ? '' : (data?.structured ? '' : (data?.output || '')),
        result: data,
        ts: Date.now(),
      }]);
      toast(t.agentChatRunComplete, 'success');
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
  }, [input, loading, runtimeAgentId, attachedFiles, toast, t]);

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
              {result.processing_time_ms ? (
                <span className="text-[10px] text-muted-foreground ml-auto tabular-nums">
                  {t.agentChatDuration} {result.processing_time_ms}ms
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

