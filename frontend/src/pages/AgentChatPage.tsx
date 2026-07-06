// Phase 3-B2 Loop 2 — Chat with a cloned (project-scoped) Agent.
//
// Route: /agents/:project_agent_id/chat?preset={agent_ref}
//
// Loop 2 (Gap 2.2) — Click-to-Chat UX:
//   - Hub CTA "Chat / Use Agent" calls clone endpoint (Loop 1), then
//     navigates here with the returned project_agent_id.
//   - This page fetches the agent by ID (route guard: 404 → redirect to
//     /ai-studio/agents so the user re-clones).
//   - Submits input via A2A mainline (POST /api/icoder/agents/{agent_id}/v1/message:send).
//   - Renders result in a Tab-switched Output Panel (Rendered / JSON):
//     • Rendered: markdown rendered as HTML tables (Loop 3, Gap 4.3).
//     • JSON: pretty-printed v2 8-field structured output.
//
// The `?preset={agent_ref}` query param is informational — it lets the
// chat page pre-fill a greeting or context hint based on the source
// agent's use case (e.g. medical-coding → "请为以下病历进行 ICD 编码").
import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom';
import {
  Bot, ArrowLeft, Send, Loader2, AlertCircle, CheckCircle2,
} from 'lucide-react';
import { agentsApi } from '../services/api';
import { runtimeAgentApi } from '../services/runtimeApi';
import { useToastStore } from '../store';
import type { RuntimeRunResult } from '../types/runtime';
import {
  generateFallbackMarkdown,
  RenderedMarkdown,
} from '../utils/medicalCodingMarkdown';

const PRESET_GREETINGS: Record<string, string> = {
  'icoder/medical-coding-agent@2.0.0':
    '请为以下病历文本进行 ICD-10-CN 诊断编码与 ICD-9-CM-3 手术操作编码建议。',
};

type OutputTab = 'rendered' | 'json';

export default function AgentChatPage() {
  const { project_agent_id: projectAgentId } = useParams<{ project_agent_id: string }>();
  const [searchParams] = useSearchParams();
  const preset = searchParams.get('preset') || '';
  const navigate = useNavigate();
  const toast = useToastStore((s) => s.addToast);

  const [agent, setAgent] = useState<any | null>(null);
  const [agentLoading, setAgentLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RuntimeRunResult | any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outputTab, setOutputTab] = useState<OutputTab>('rendered');

  // Route guard: fetch the cloned agent. If 404, redirect to Hub so the
  // user re-clones (Loop 2 acceptance: "未 Clone 的 Agent 不能直接进入 Chat").
  useEffect(() => {
    if (!projectAgentId) {
      setNotFound(true);
      setAgentLoading(false);
      return;
    }
    setAgentLoading(true);
    agentsApi
      .get(projectAgentId)
      .then((r) => {
        setAgent(r.data);
        setNotFound(false);
      })
      .catch((err) => {
        const status = err?.response?.status;
        if (status === 404) {
          setNotFound(true);
          toast('未找到 Agent — 请先从 Hub 克隆', 'error');
          // Redirect after a short delay so the toast is visible.
          setTimeout(() => navigate('/ai-studio/agents', { replace: true }), 800);
        } else {
          toast(`加载 Agent 失败: ${err?.message || 'unknown'}`, 'error');
        }
      })
      .finally(() => setAgentLoading(false));
  }, [projectAgentId, navigate, toast]);

  // Derive the runtime agent_id (short form) from agent.config.agent_ref
  // or fall back to the source_agent_ref if present. Used for the A2A path.
  const runtimeAgentId = (() => {
    const cfg = agent?.config || {};
    const ref = cfg.source_agent_ref || cfg.agent_ref || '';
    if (!ref) return '';
    const tail = ref.split('/').pop() || '';
    return tail.split('@')[0];
  })();

  const greeting = preset && PRESET_GREETINGS[preset]
    ? PRESET_GREETINGS[preset]
    : agent?.description
      ? `Agent: ${agent.description}`
      : '请输入您的请求。';

  const onSubmit = useCallback(async () => {
    if (!input.trim() || loading || !runtimeAgentId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await runtimeAgentApi.runAgentViaA2A(runtimeAgentId, input);
      setResult(data);
      toast('运行完成', 'success');
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '运行失败';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      toast('运行失败', 'error');
    } finally {
      setLoading(false);
    }
  }, [input, loading, runtimeAgentId, toast]);

  // Loading state — agent metadata fetch
  if (agentLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-muted/20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Not found — route guard kicked in, redirect already dispatched.
  if (notFound) {
    return (
      <div className="flex-1 flex items-center justify-center bg-muted/20 p-6">
        <div className="text-center">
          <AlertCircle className="h-10 w-10 mx-auto mb-3 text-amber-500" />
          <p className="text-sm font-medium text-foreground">Agent 未克隆</p>
          <p className="text-xs text-muted-foreground mt-1">
            正在跳转到 Agent Hub，请从那里克隆后再进入对话。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-muted/20">
      {/* Header — agent identity + back link */}
      <div className="px-6 py-4 border-b border-border/40 bg-background flex items-center gap-3">
        <Link
          to="/ai-studio/agents"
          className="p-1.5 rounded-lg hover:bg-accent transition-colors text-muted-foreground"
          title="返回 Agent Hub"
        >
          <ArrowLeft size={16} />
        </Link>
        <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
          <Bot size={15} className="text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-foreground truncate">
              {agent?.name || 'Agent'}
            </p>
            <span className="text-[10px] font-mono text-muted-foreground">
              v{agent?.version || '1.0.0'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground truncate">
            {agent?.description || greeting}
          </p>
        </div>
        {agent?.config?.source_agent_ref && (
          <span className="text-[10px] px-2 py-0.5 rounded bg-muted text-muted-foreground font-mono">
            source: {agent.config.source_agent_ref}
          </span>
        )}
      </div>

      {/* Body — input + result */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {/* Greeting / preset hint */}
        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-4">
          <p className="text-xs text-muted-foreground">{greeting}</p>
        </div>

        {/* Input */}
        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-4">
          <label className="text-xs font-semibold text-foreground block mb-2">
            输入
          </label>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="在此粘贴病历文本或输入您的请求…"
            rows={6}
            className="w-full text-sm bg-transparent border border-border rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-ring/50 leading-relaxed"
            disabled={loading}
          />
          <div className="flex items-center justify-between mt-3">
            <span className="text-[10px] text-muted-foreground">
              {input.length} 字符
            </span>
            <button
              onClick={onSubmit}
              disabled={!input.trim() || loading || !runtimeAgentId}
              className="inline-flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors font-medium"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" /> 运行中…
                </>
              ) : (
                <>
                  <Send size={14} /> 运行
                </>
              )}
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-2">
            <AlertCircle size={16} className="text-red-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-red-700">运行失败</p>
              <p className="text-xs text-red-600 mt-1 break-all">{error}</p>
            </div>
          </div>
        )}

        {/* Result — Tab-switched Output Panel (Loop 3, Gap 4.3).
            • Rendered: markdown rendered as HTML tables (default).
            • JSON: pretty-printed v2 8-field structured output.
            If the backend didn't pre-render markdown, auto-generate a
            minimal one from the v2 JSON (Loop 3 §3 降级处理). */}
        {result && (
          <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-4">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle2 size={14} className="text-green-600" />
              <p className="text-sm font-semibold text-foreground">运行结果</p>
              {result.processing_time_ms && (
                <span className="text-[10px] text-muted-foreground ml-auto">
                  耗时 {result.processing_time_ms}ms
                </span>
              )}
            </div>

            {/* Tab switcher */}
            <div className="flex items-center rounded-lg border border-border p-0.5 mb-3 w-fit">
              {([
                { id: 'rendered' as OutputTab, label: 'Rendered' },
                { id: 'json' as OutputTab, label: 'JSON' },
              ]).map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setOutputTab(tab.id)}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                    outputTab === tab.id
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Rendered tab — markdown → HTML.
                Uses dangerouslySetInnerHTML with a minimal markdown table
                parser. react-markdown isn't installed yet; this keeps the
                bundle small and avoids adding a dep for one page. The
                parser handles headings + tables (the only constructs the
                backend generator emits). */}
            {outputTab === 'rendered' && (
              <RenderedMarkdown
                markdown={
                  result.markdown ||
                  generateFallbackMarkdown(result.structured || result)
                }
              />
            )}

            {/* JSON tab */}
            {outputTab === 'json' && (
              <pre className="text-[11px] bg-muted/30 rounded-lg p-3 overflow-x-auto max-h-96 font-mono leading-relaxed">
                {JSON.stringify(result.structured || result, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
