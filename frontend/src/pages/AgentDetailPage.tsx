// Agent Detail Page — standalone page for /ai-studio/agents/:agentId
// Chat area (left) + SettingsCodeTab (right) with Settings/Code tabs
import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useT } from '../i18n';
import {
  Bot, Send, Loader2, Home, ChevronRight, Plus, Settings, Code,
  X, Paperclip, FileText, Braces, Trash2, Wrench, Pencil,
  Search, Check, Sparkles, BookOpen, Copy, User, Clock,
} from 'lucide-react';
import { agentsApi, expertsApi, memoryApi, billingApi, oauthApi } from '../services/api';
import { runtimeAgentApi } from '../services/runtimeApi';
import { useToastStore } from '../store';
import type { RuntimeRunResult } from '../types/runtime';
import SettingsCodeTab from '../components/common/SettingsCodeTab';
import ToolSelector from '../components/agents/ToolSelector';
import CodeSnippet from '../components/common/CodeSnippet';
import EditSystemPromptModal from '../components/EditSystemPromptModal';
import ExpertLibraryModal from '../components/ExpertLibraryModal';
import A2ACollaboration from '../components/A2ACollaboration';

export default function AgentDetailPage() {
  const t = useT();
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();

  // Agent data
  const [agent, setAgent] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Runtime state
  const [agentRef, setAgentRef] = useState('');
  const [runtimeInstalled, setRuntimeInstalled] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState('');
  const [runtimeTier, setRuntimeTier] = useState<number | null>(null);
  const [useRuntime, setUseRuntime] = useState(() => localStorage.getItem('icoder-agent-runtime-mode') !== 'legacy');
  const [installLoading, setInstallLoading] = useState(false);
  const toast = useToastStore((s) => s.addToast);

  // Agent Test Panel
  const [showTestPanel, setShowTestPanel] = useState(false);
  const [testInput, setTestInput] = useState('');
  const [testResult, setTestResult] = useState<any>(null);
  const [testLoading, setTestLoading] = useState(false);

  // Agent Evaluation
  const [showEval, setShowEval] = useState(false);
  const [evalResult, setEvalResult] = useState<any>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalHistory, setEvalHistory] = useState<any[]>([]);

  // Chat state
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<{ role: string; content: string }[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionId, setSessionId] = useState(() => `sess-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);
  const [memoryLoaded, setMemoryLoaded] = useState(false);

  // Expert bindings
  const [agentExperts, setAgentExperts] = useState<any[]>([]);
  const [expertNameToId, setExpertNameToId] = useState<Record<string, string>>({});
  const [expertDbId, setExpertDbId] = useState<string>('');

  // Settings state
  const [agentName, setAgentName] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [showEditPrompt, setShowEditPrompt] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);

  // Orchestration config
  const [routingStrategy, setRoutingStrategy] = useState<string>('llm_plan');
  const [maxRetries, setMaxRetries] = useState(2);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.6);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [tier1Enforce, setTier1Enforce] = useState(true);
  const [permissionPreset, setPermissionPreset] = useState<string>('medical_coding');

  // Drag-and-drop state
  const [dragIdx, setDragIdx] = useState<number | null>(null);

  // Expert browser
  const [showExpertBrowser, setShowExpertBrowser] = useState(false);

  // Input format
  const [inputFormat, setInputFormat] = useState<'text' | 'file' | 'json'>('text');
  const [jsonData, setJsonData] = useState('');
  const [attachedFile, setAttachedFile] = useState<{ name: string; content: string } | null>(null);
  const [showFormatMenu, setShowFormatMenu] = useState(false);

  // API client / balance
  const [balance, setBalance] = useState<number | null>(null);
  const [apiClients, setApiClients] = useState<any[]>([]);
  const [selectedApiClient, setSelectedApiClient] = useState<string>('');
  const [copied, setCopied] = useState('');
  // Delete confirmation modal state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Track the currently active agentId to discard stale responses
  const activeAgentIdRef = useRef(agentId);
  const activeStreamRef = useRef<AbortController | null>(null);
  useEffect(() => {
    activeAgentIdRef.current = agentId;
    // Abort any in-flight stream from previous agent
    if (activeStreamRef.current) {
      activeStreamRef.current.abort();
      activeStreamRef.current = null;
    }
  }, [agentId]);

  // Load agent data
  useEffect(() => {
    if (!agentId) return;

    const isActive = () => activeAgentIdRef.current === agentId;

    setError('');
    setLoading(true);
    setChatMessages([]);
    setMemoryLoaded(false);
    setSessionId(`sess-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);

    billingApi.balance().then(r => { if (isActive()) setBalance(r.data.balance); }).catch(() => {});
    oauthApi.list().then(r => {
      if (!isActive()) return;
      const clients = r.data?.clients || [];
      setApiClients(clients);
      if (clients.length > 0) setSelectedApiClient(clients[0].client_id);
    }).catch(() => {});

    let idToExpert: Record<string, any> = {};
    expertsApi.list('', '', 'all').then(r => {
      if (!isActive()) return;
      const expertsLoaded = r.data?.experts || [];
      const nameMap: Record<string, string> = {};
      for (const e of expertsLoaded) {
        nameMap[e.name] = e.id;
        idToExpert[e.id] = e;
      }
      if (!isActive()) return;
      setExpertNameToId(nameMap);
      const codingExperts = expertsLoaded.filter((e: any) => e.category === 'coding');
      if (codingExperts.length > 0) setExpertDbId(codingExperts[0].id);
      return agentsApi.get(agentId);
    }).then(r2 => {
      if (!isActive() || !r2) return;
      const a = r2.data;
      setAgent(a);
      setAgentName(a.name || '');
      // Check Runtime status for this agent
      const cleanName = (a.name || 'agent').toLowerCase().replace(/\s+/g, '-').replace(/\(copy\)/g, '').replace(/-+$/g, '');
      const ref = cleanName + '-' + (a.version || '1.0.0');
      setAgentRef(ref);
      runtimeAgentApi.listAgents().then(({ agents: installed }) => {
        const found = installed.find((inst: { agent_ref: string }) =>
          inst.agent_ref.includes(cleanName) || inst.agent_ref === ref
        );
        if (found) {
          setRuntimeInstalled(true);
          setRuntimeStatus(found.status);
          setRuntimeTier((found as any).tier ?? null);
        }
      }).catch(() => {});
      setSystemPrompt(a.system_prompt || '');
      const cfg = a.config || {};
      setRoutingStrategy(cfg.routing_strategy || 'llm_plan');
      setMaxRetries(cfg.max_retries ?? 2);
      setConfidenceThreshold(cfg.confidence_threshold ?? 0.6);
      const toolsCfg = cfg.tools || {};
      setEnabledTools(toolsCfg.enabled || []);
      setTier1Enforce(toolsCfg.tier1_enforce ?? true);
      setPermissionPreset(cfg.permission_preset || 'medical_coding');
      if (a.expert_ids?.length) {
        const resolved: any[] = a.expert_ids.map((eid: string) => {
          const e = idToExpert[eid];
          return e ? { id: e.id, name: e.name, icon: e.icon || 'Bot' } : { id: eid, name: eid, icon: 'Bot' };
        });
        setAgentExperts(resolved);
      }
    }).catch(async () => {
      if (!isActive()) return;
      // Fallback: try Runtime API
      try {
        const { agents: installed } = await runtimeAgentApi.listAgents();
        const found = installed.find((a: any) => a.agent_ref === agentId);
        if (found) {
          setAgent({ id: found.agent_ref, name: found.name, description: found.description, version: found.version, category: found.category, system_prompt: '', expert_ids: [], config: {}, is_prebuilt: found.agent_type === 'certified' });
          setAgentName(found.name); setAgentRef(found.agent_ref);
          setRuntimeInstalled(true); setRuntimeStatus(found.status); setRuntimeTier(found.tier ?? null);
          return;
        }
      } catch {}
      // Fallback: try templates
      try {
        const templatesRes = await agentsApi.templates();
        if (!isActive()) return;
        const templates = templatesRes.data?.templates || [];
        const tpl = templates.find((t: any) => t.id === agentId);
        if (tpl) {
          setAgent(tpl);
          setAgentName(tpl.title || '');
          setSystemPrompt(tpl.system_prompt || '');
        } else {
          setError(t.agentNotFound);
        }
      } catch {
        if (isActive()) setError(t.agentNotFound);
      }
    }).finally(() => {
      if (isActive()) setLoading(false);
    });
  }, [agentId]);

  // Load memory context
  useEffect(() => {
    if (agent && !memoryLoaded) {
      const isActive = () => activeAgentIdRef.current === agentId;
      memoryApi.context(sessionId).then(r => {
        if (!isActive()) return;
        const ctx = r.data?.context;
        if (ctx) {
          setChatMessages([{ role: 'assistant', content: `${t.sessionContextRestored}\n${ctx}` }]);
        }
      }).catch(() => {});
      setMemoryLoaded(true);
    }
    if (!agent) setMemoryLoaded(false);
  }, [agent, sessionId, memoryLoaded]);

  // Build message content
  const buildMessageContent = (): string => {
    const parts: string[] = [];
    if (chatInput.trim()) parts.push(chatInput.trim());
    if (jsonData.trim()) parts.push('```json\n' + jsonData.trim() + '\n```');
    if (attachedFile) parts.push(`[附件：${attachedFile.name}]\n${attachedFile.content}`);
    return parts.join('\n\n');
  };

  // Send chat message
  const handleSend = async (overrideContent?: string) => {
    const content = overrideContent || buildMessageContent();
    if (!content.trim() || !agent) return;

    // Abort any in-flight stream
    if (activeStreamRef.current) {
      activeStreamRef.current.abort();
    }
    const abortController = new AbortController();
    activeStreamRef.current = abortController;
    const isActive = () => activeAgentIdRef.current === agentId;

    const userMsg = { role: 'user', content };
    const history = chatMessages.map(m => ({ role: m.role, content: m.content }));
    setChatMessages(prev => [...prev, userMsg]);
    if (!overrideContent) {
      setChatInput('');
      setJsonData('');
      setAttachedFile(null);
      setInputFormat('text');
    }
    setChatLoading(true);

    memoryApi.save(sessionId, 'user', content, expertDbId, agent?.id).catch(() => {});

    const assistantIdx = chatMessages.length + 1;
    setChatMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    try {
      const token = localStorage.getItem('access_token') || '';
      const resp = await fetch(`/api/agents/${agent.id || agentId}/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ input: content, conversation_history: history }),
        signal: abortController.signal,
      });

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader = resp.body?.getReader();
      if (!reader) throw new Error('Cannot read response stream');

      const decoder = new TextDecoder();
      let buffer = '';
      let accumulated = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!isActive()) { reader.cancel(); break; }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') { if (isActive()) setChatLoading(false); continue; }
            try {
              const parsed = JSON.parse(data);
              if (parsed.type === 'token' && parsed.text) {
                accumulated += parsed.text;
                if (isActive()) setChatMessages(prev => prev.map((m, i) =>
                  i === assistantIdx ? { ...m, content: accumulated } : m
                ));
              } else if (parsed.type === 'done') {
                if (isActive()) setChatLoading(false);
              } else if (parsed.type === 'error') {
                if (isActive()) {
                  setChatMessages(prev => prev.map((m, i) =>
                    i === assistantIdx ? { ...m, content: `错误：${parsed.message}` } : m
                  ));
                  setChatLoading(false);
                }
              }
            } catch {
              accumulated += data;
              if (isActive()) setChatMessages(prev => prev.map((m, i) =>
                i === assistantIdx ? { ...m, content: accumulated } : m
              ));
            }
          }
        }
      }
      if (accumulated && isActive()) {
        memoryApi.save(sessionId, 'assistant', accumulated, expertDbId, agent?.id).catch(() => {});
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      if (isActive()) {
        setChatMessages(prev => prev.map((m, i) =>
          i === assistantIdx ? { ...m, content: m.content || `错误：${err.message}` } : m
        ));
        setChatLoading(false);
      }
    }
  };

  // Quick actions
  const handleWhatCanYouDo = () => {
    const msg = "你能做什么？请描述你的能力、专长以及如何在医疗编码、临床文档及相关医疗任务中提供帮助。";
    handleSend(msg);
  };


  const [editingAttachment, setEditingAttachment] = useState<string | null>(null);

  const handleSuggestPrompt = () => {
    const caseItem = { caseLabel: '腰椎间盘突出症', caseText: '患者，女，65岁。因腰痛伴左下肢放射痛3月就诊。腰椎MRI示L4/5椎间盘突出，压迫左侧神经根。入院诊断：腰椎间盘突出症。建议行PLIF手术。' };

    setAttachedFile({ name: caseItem.caseLabel, content: caseItem.caseText });

    // iCoDer-style: generate task instruction based on agent capability
    const desc = (agent?.description || '').toLowerCase();
    let instruction = '';
    if (desc.includes('索引') || desc.includes('索引导航') || desc.includes('navigator')) {
      instruction = `请遍历ICD-10字母索引，为"${caseItem.caseLabel}"提供主要候选编码及相关子术语。`;
    } else if (desc.includes('提取') || desc.includes('诊断') || desc.includes('extract')) {
      instruction = `请从以下病例中提取所有诊断并分配ICD-10-CN编码，提供证据引用。`;
    } else if (desc.includes('校验') || desc.includes('验证') || desc.includes('validate')) {
      instruction = `请验证以下病例编码的准确性，检查是否存在编码规则违反或冲突。`;
    } else if (desc.includes('合规') || desc.includes('护栏') || desc.includes('compliance')) {
      instruction = `请评估以下病例编码组合的合规性，按医保结算清单规范逐项检查。`;
    } else if (desc.includes('规则') || desc.includes('解释') || desc.includes('explain')) {
      instruction = `请解释以下病例中选用的ICD编码依据，并评估是否存在更合适的编码方案。`;
    } else {
      instruction = `请分析以下病例并提供ICD-10-CN编码建议，说明编码依据和证据支持。`;
    }
    setChatInput(instruction);
  };

  // Agent Evaluation
  const fetchEvalHistory = async () => {
    try {
      const ref = agentRef || (agent?.name?.toLowerCase()?.replace(/\s+/g,'-')||'') + '-' + (agent?.version||'1.0.0');
      const resp = await fetch(`/api/agents/${encodeURIComponent(ref)}/evaluation-history`);
      if (resp.ok) { const d = await resp.json(); setEvalHistory(d.evaluations||[]); }
    } catch {}
  };
  const runEvaluation = async () => {
    setEvalLoading(true);
    try {
      const ref = agentRef || (agent?.name?.toLowerCase()?.replace(/\s+/g,'-')||'') + '-' + (agent?.version||'1.0.0');
      const token = localStorage.getItem('access_token') || '';
      const resp = await fetch(`/api/agents/${encodeURIComponent(ref)}/evaluate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      });
      if (resp.ok) {
        const d = await resp.json(); setEvalResult(d);
        setEvalHistory(prev => [{ evaluated_at: d.evaluated_at, primary_dx_accuracy: d.primary_dx_accuracy }, ...prev].slice(0,10));
      }
    } catch {} finally { setEvalLoading(false); }
  };

  // Save settings
  const handleSaveSettings = async () => {
    if (!agent?.id) return;
    setSavingSettings(true);
    try {
      await agentsApi.update(agent.id, {
        name: agentName,
        system_prompt: systemPrompt,
        expert_ids: agentExperts.map(e => e.id),
        config: {
          routing_strategy: routingStrategy,
          max_retries: maxRetries,
          confidence_threshold: confidenceThreshold,
          permission_preset: permissionPreset,
          tools: {
            enabled: enabledTools,
            tier1_enforce: tier1Enforce,
          },
        },
      });
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2000);
    } catch { /* silently fail */ }
    setSavingSettings(false);
  };

  // Delete agent
  const handleDeleteAgent = () => {
    if (!agent?.id) return;
    setShowDeleteConfirm(true);
  };

  const confirmDeleteAgent = async () => {
    if (!agent?.id) return;
    try {
      await agentsApi.delete(agent.id);
      setShowDeleteConfirm(false);
      navigate('/ai-studio/agents');
    } catch { /* silently fail */ }
  };

  // Browse expert library
  const openExpertBrowser = () => {
    setShowExpertBrowser(true);
  };

  const addExpertToAgent = (expert: any) => {
    if (agentExperts.find(e => e.id === expert.id)) return;
    setAgentExperts(prev => [...prev, { id: expert.id, name: expert.name, icon: expert.icon || 'Bot' }]);
  };

  const removeExpertFromAgent = (id: string) => {
    setAgentExperts(prev => prev.filter(e => e.id !== id));
  };

  const handleCopy = (key: string) => {
    const code = `import { iCoDerClient } from "@icoder/sdk";\n\nconst client = new iCoDerClient({ apiKey: "YOUR_API_KEY" });\nconst agent = client.agent("${agent?.id || agentId}");\nconst response = await agent.chat("patient case...");`;
    navigator.clipboard.writeText(code);
    setCopied(key);
    setTimeout(() => setCopied(''), 2000);
  };

  // Only show spinner on very first load (no agent data at all)
  if (!agent && loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin h-8 w-8 text-muted-foreground" />
      </div>
    );
  }

  // Only show error when loading is finished and there's a real error
  if (!loading && error) {
    return (
      <div className="flex-1 flex flex-col bg-muted/20">
        <div className="flex-1 p-6 overflow-y-auto">
          <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 text-center py-16">
          <Bot size={48} className="mx-auto mb-3 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">{error || t.agentNotFound}</p>
          <Link to="/ai-studio/agents" className="inline-block mt-4 text-xs px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">
            {t.backToAgentList}
          </Link>
          </div>
        </div>
      </div>
    );
  }

  const agentTitle = agentName || agent.name || agent.title || '智能体';

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Runtime status bar */}
      <div className="flex items-center gap-4 px-6 py-2 bg-muted/30 border-b text-xs">
        <span className="text-muted-foreground">Runtime:</span>
        <span className="text-[11px] font-mono text-muted-foreground ml-auto">¥0.000000</span>
        {runtimeInstalled ? (
          <>
            <span className={`px-1.5 py-0.5 rounded-full font-medium ${
              runtimeStatus === 'enabled' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
            }`}>{runtimeStatus || 'installed'}</span>
            <span className="text-muted-foreground font-mono text-[11px]">{agentRef}</span>
            {/* Tier badge */}
            {runtimeTier != null && (
              <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${
                runtimeTier >= 3 ? 'bg-red-100 text-red-700' :
                runtimeTier >= 2 ? 'bg-amber-100 text-amber-700' :
                'bg-green-100 text-green-700'
              }`} title={`Security Tier ${runtimeTier}: ${
                runtimeTier === 0 ? 'Pure Prompt' : runtimeTier === 1 ? 'Read-only Tools' :
                runtimeTier === 2 ? 'Sandbox Code' : runtimeTier === 3 ? 'Network Access' : 'System Write-back'
              }`}>
                Tier {runtimeTier}
                {runtimeTier >= 3 ? ' (Approval Required)' : runtimeTier >= 2 ? ' (Default Disabled)' : ''}
              </span>
            )}
          </>
        ) : (
          <button onClick={async () => {
            setInstallLoading(true);
            try {
              const data = await runtimeAgentApi.installAgent(
                agent.name,
                agent.version || '1.0.0',
                agent.is_prebuilt ? 'certified' : 'community'
              );
              setAgentRef(data.agent_ref || agentRef);
              setRuntimeInstalled(true);
              setRuntimeStatus(data.status || 'enabled');
              toast('Agent 已安装到 Runtime', 'success');
            } catch (e: any) {
              const msg = e?.response?.data?.detail || e?.message || '安装失败';
              toast(msg, 'error');
            }
            finally { setInstallLoading(false); }
          }}
            disabled={installLoading}
            className="px-2 py-0.5 rounded text-[11px] bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            {installLoading ? 'Installing...' : 'Install to Runtime'}
          </button>
        )}
        {runtimeInstalled && (
          <div className="flex gap-1 ml-auto">
            <button onClick={() => setShowTestPanel(!showTestPanel)}
              className="px-2 py-0.5 rounded text-[11px] bg-blue-50 text-blue-600 hover:bg-blue-100">
              测试
            </button>
            <button onClick={() => { setShowEval(!showEval); if (!showEval && !evalHistory.length) fetchEvalHistory(); }}
              className="px-2 py-0.5 rounded text-[11px] bg-green-50 text-green-600 hover:bg-green-100">
              评估
            </button>
            <button onClick={async () => {
              try {
                const newAction = runtimeStatus === 'enabled' ? 'disable' : 'enable';
                await runtimeAgentApi.agentLifecycle(agentRef, newAction);
                setRuntimeStatus(runtimeStatus === 'enabled' ? 'disabled' : 'enabled');
                toast(`Agent ${newAction === 'enable' ? '已启用' : '已禁用'}`, 'success');
              } catch { toast('操作失败，请检查权限', 'error'); }
            }}
              className="px-2 py-0.5 rounded text-[11px] bg-gray-100 hover:bg-gray-200">
              {runtimeStatus === 'enabled' ? 'Disable' : 'Enable'}
            </button>
          </div>
        )}
      </div>

      {/* Agent Test Panel */}
      {showTestPanel && (
        <div className="px-6 py-3 bg-blue-50/50 border-b border-blue-100">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-foreground">Agent 测试</h4>
            <button onClick={() => { setShowTestPanel(false); setTestResult(null); setTestInput(''); }}
              className="p-0.5 rounded hover:bg-accent"><X size={14} className="text-muted-foreground" /></button>
          </div>
          <div className="flex gap-2">
            <textarea value={testInput} onChange={e => setTestInput(e.target.value)}
              placeholder="输入测试病历，验证 Agent 编码结果..."
              rows={4} className="flex-1 text-xs border border-border rounded-lg px-3 py-2 bg-background resize-none focus:outline-none focus:ring-1 focus:ring-ring" />
            <button onClick={async () => {
              if (!testInput.trim() || testLoading) return;
              setTestLoading(true); setTestResult(null);
              try {
                const ref = agentRef || (agent?.name?.toLowerCase()?.replace(/\s+/g,'-')||'agent') + '-' + (agent?.version||'1.0.0');
                const data = await runtimeAgentApi.runAgent(ref, testInput);
                setTestResult(data);
              } catch (e: any) { setTestResult({ error: e?.message || '测试失败' }); }
              finally { setTestLoading(false); }
            }} disabled={testLoading || !testInput.trim()}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-40 shrink-0 self-end">
              {testLoading ? '运行中...' : '运行测试'}
            </button>
          </div>
          {testResult && (
            <div className="mt-3 bg-background rounded-lg border border-border p-3 text-xs space-y-2">
              {testResult.error ? (
                <p className="text-red-600">{testResult.error}</p>
              ) : (
                <>
                  <div className="flex gap-4">
                    <span>状态: <b>{testResult.status || '—'}</b></span>
                    <span>耗时: <b>{testResult.processing_time_ms || 0}ms</b></span>
                    <span>安全: <b>{testResult.safety ? '已校验' : '—'}</b></span>
                  </div>
                  {testResult.primary_diagnosis?.code && (
                    <div>
                      <p className="text-muted-foreground">主诊断</p>
                      <p className="font-mono text-sm">{testResult.primary_diagnosis.code} — {testResult.primary_diagnosis.description || ''}</p>
                    </div>
                  )}
                  {testResult.secondary_diagnoses?.length > 0 && (
                    <div>
                      <p className="text-muted-foreground">次要诊断 ({testResult.secondary_diagnoses.length})</p>
                      <div className="flex flex-wrap gap-1">
                        {testResult.secondary_diagnoses.slice(0, 10).map((d: any, i: number) => (
                          <span key={i} className="px-1.5 py-0.5 bg-muted rounded font-mono text-[10px]">{d.code}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {testResult.procedures?.length > 0 && (
                    <div>
                      <p className="text-muted-foreground">手术 ({testResult.procedures.length})</p>
                      <div className="flex flex-wrap gap-1">
                        {testResult.procedures.map((p: any, i: number) => (
                          <span key={i} className="px-1.5 py-0.5 bg-muted rounded font-mono text-[10px]">{p.code}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {testResult.issues_found?.length > 0 && (
                    <div>
                      <p className="text-muted-foreground">问题 ({testResult.issues_found.length})</p>
                      {testResult.issues_found.slice(0, 5).map((iss: any, i: number) => (
                        <p key={i} className="text-[10px] text-amber-700">[{iss.severity}] {iss.message}</p>
                      ))}
                    </div>
                  )}
                  {testResult.safety?.post_check?.rule_issues?.length > 0 && (
                    <div>
                      <p className="text-muted-foreground">规则检查</p>
                      {testResult.safety.post_check.rule_issues.map((r: any, i: number) => (
                        <p key={i} className="text-[10px] text-red-600">[{r.severity}] {r.message}</p>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
      {/* Main: chat (left) + panel (right) */}
      <div className="flex-1 flex min-h-0">
        {/* Left: Chat area — bg-muted/20 with card content */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0 bg-muted/20">
          <div className="flex-1 p-4 flex flex-col min-h-0">
            <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 flex-1 flex flex-col min-h-0 overflow-y-auto">
            {chatMessages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-6">
                <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-6">
                  <Bot size={28} className="text-primary" />
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">{t.askTheAgentTitle}</h3>
                <p className="text-sm text-muted-foreground">{t.askTheAgentDesc}</p>
              </div>
            ) : (
              <div className="py-6">
                {chatMessages.map((msg, i) => (
                  <div key={i} className="px-6 mb-6">
                    <div className={`max-w-3xl mx-auto flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[75%] rounded-2xl px-5 py-3 text-sm ${
                        msg.role === 'user'
                          ? 'rounded-br-md bg-primary/5 border border-primary/10 text-foreground'
                          : 'text-foreground'
                      }`}>
                        {msg.role === 'assistant' && (
                          <p className="text-xs font-medium text-muted-foreground mb-1">{agentTitle}</p>
                        )}
                        <p className="whitespace-pre-wrap break-words leading-relaxed">{msg.content}</p>
                      </div>
                    </div>
                  </div>
                ))}
                {chatLoading && chatMessages[chatMessages.length - 1]?.role === 'assistant' && !chatMessages[chatMessages.length - 1]?.content && (
                  <div className="px-6 mb-6">
                    <div className="max-w-3xl mx-auto">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <div className="flex gap-1">
                          <span className="w-2 h-2 rounded-full bg-primary/40 animate-bounce" style={{ animationDelay: '0ms' }} />
                          <span className="w-2 h-2 rounded-full bg-primary/40 animate-bounce" style={{ animationDelay: '150ms' }} />
                          <span className="w-2 h-2 rounded-full bg-primary/40 animate-bounce" style={{ animationDelay: '300ms' }} />
                        </div>
                        <span>{t.thinking}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
            </div>
          </div>

          {/* Bottom input */}
          <div className="shrink-0">
            <div className="max-w-3xl mx-auto">
              {/* Attached case document card — iCoDer-style, above input */}
              {attachedFile && (
                <div className="mb-2 bg-background rounded-xl shadow-sm ring-1 ring-border/20 overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-border/20 bg-muted/30">
                    <div className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded bg-primary/10 flex items-center justify-center">
                        <FileText size={11} className="text-primary" />
                      </div>
                      <span className="text-[11px] font-medium text-foreground">{attachedFile.name}</span>
                    </div>
                    <div className="flex items-center gap-0.5">
                      <button onClick={() => setEditingAttachment(attachedFile.content)} className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors" title="编辑">
                        <Pencil size={11} />
                      </button>
                      <button onClick={() => setAttachedFile(null)} className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors" title="移除">
                        <X size={12} />
                      </button>
                    </div>
                  </div>
                  <div className="px-3 py-2 max-h-[120px] overflow-y-auto">
                    <p className="text-[11px] text-foreground/70 leading-relaxed whitespace-pre-wrap">{attachedFile.content.slice(0, 500)}{attachedFile.content.length > 500 ? '...' : ''}</p>
                  </div>
                </div>
              )}

              {/* JSON data input */}
              {inputFormat === 'json' && (
                <div className="mb-2 bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-foreground flex items-center gap-1.5">
                      <Braces size={12} /> {t.jsonData}
                    </span>
                    <button onClick={() => { setJsonData(''); setInputFormat('text'); }} className="text-muted-foreground hover:text-foreground">
                      <X size={14} />
                    </button>
                  </div>
                  <textarea
                    value={jsonData}
                    onChange={e => setJsonData(e.target.value)}
                    placeholder='{"key": "value"}'
                    rows={3}
                    className="w-full text-xs font-mono bg-muted/50 border border-border rounded-lg px-3 py-2 text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
              )}

              {/* Main input */}
              <div className="bg-background rounded-2xl shadow-sm ring-1 ring-border/20 focus-within:ring-primary/30 focus-within:shadow-md transition-all">
                <textarea
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                  placeholder={t.askTheAgentPlaceholder}
                  rows={1}
                  className="w-full text-sm bg-transparent focus:outline-none placeholder:text-muted-foreground resize-none py-3 px-4 min-h-[40px] max-h-[120px]"
                  onInput={(e) => { const el = e.target as HTMLTextAreaElement; el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 120) + 'px'; }}
                />

                {/* Toolbar */}
                <div className="flex items-center gap-1.5 px-2 pb-2">
                  {/* Add context button */}
                  <div className="relative">
                    <button
                      onClick={() => setShowFormatMenu(!showFormatMenu)}
                      className="flex items-center justify-center w-7 h-7 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                      title={t.addContext}
                    >
                      <Plus size={16} />
                    </button>
                    {showFormatMenu && (
                      <div className="absolute bottom-full left-0 mb-1.5 bg-popover border border-border rounded-xl shadow-lg p-1.5 min-w-[180px] z-10">
                        <button onClick={() => { setInputFormat('text'); setShowFormatMenu(false); }}
                          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-foreground hover:bg-accent transition-colors">
                          <FileText size={14} className="text-muted-foreground" />
                          <span>{t.addText}</span>
                        </button>
                        <button onClick={() => { setInputFormat('json'); setShowFormatMenu(false); }}
                          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-foreground hover:bg-accent transition-colors">
                          <Braces size={14} className="text-muted-foreground" />
                          <span>{t.addJson}</span>
                        </button>
                        <button onClick={() => { document.getElementById('detail-file-upload')?.click(); setShowFormatMenu(false); }}
                          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-foreground hover:bg-accent transition-colors">
                          <Paperclip size={14} className="text-muted-foreground" />
                          <span>{t.addFile}</span>
                        </button>
                      </div>
                    )}
                  </div>

                  <div className="flex-1" />

                  <button onClick={() => handleSend()}
                    disabled={(!chatInput.trim() && !jsonData.trim() && !attachedFile) || chatLoading}
                    className="w-9 h-9 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-30 transition-all shrink-0 flex items-center justify-center">
                    {chatLoading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                  </button>
                </div>

                <input id="detail-file-upload" type="file" className="hidden" accept=".txt,.csv,.json,.md,.xml,.hl7"
                  onChange={e => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    const reader = new FileReader();
                    reader.onload = () => setAttachedFile({ name: file.name, content: reader.result as string });
                    reader.readAsText(file);
                    e.target.value = '';
                  }}
                />
              </div>

              <div className="flex flex-col items-center gap-2 mt-2">
                <div className="flex items-center justify-center gap-3">
                  <button
                    onClick={handleWhatCanYouDo}
                    className="text-xs text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5 rounded-lg border border-border hover:bg-accent"
                  >
                    {t.whatCanYouDo}
                  </button>
                  <div className="relative">
                    <button
                      onClick={handleSuggestPrompt}
                      className="text-xs text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5 rounded-lg border border-border hover:bg-accent"
                    >
                      {t.suggestPrompt}
                    </button>
                  </div>
                </div>
              </div>

              <p className="text-xs text-muted-foreground text-center mt-2">{t.askTheAgentDesc}</p>
            </div>
          </div>
        </div>

        {/* Separator */}
        <div className="h-full w-px bg-border/40 shrink-0" />

        {/* Right: SettingsCodeTab panel or Eval panel */}
        <div className="w-80 bg-muted/10 shrink-0 overflow-y-auto">
          {showEval ? (
            <div className="p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold text-foreground">Agent 评估</h4>
                <button onClick={() => setShowEval(false)} className="p-0.5 rounded hover:bg-accent"><X size={14} className="text-muted-foreground" /></button>
              </div>
              <button onClick={runEvaluation} disabled={evalLoading}
                className="w-full py-2 rounded-lg bg-green-600 text-white text-xs font-medium hover:bg-green-700 disabled:opacity-40">
                {evalLoading ? '评估中...' : '运行金标准评估'}
              </button>
              {evalResult && (
                <div className="bg-white rounded-lg border p-3 space-y-2 text-xs">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="text-center p-2 bg-muted/50 rounded"><p className="text-lg font-bold text-green-700">{evalResult.primary_dx_accuracy ? (evalResult.primary_dx_accuracy*100).toFixed(0)+'%' : '—'}</p><p className="text-[10px] text-muted-foreground">诊断准确率</p></div>
                    <div className="text-center p-2 bg-muted/50 rounded"><p className="text-lg font-bold text-blue-700">{evalResult.primary_proc_accuracy ? (evalResult.primary_proc_accuracy*100).toFixed(0)+'%' : '—'}</p><p className="text-[10px] text-muted-foreground">手术准确率</p></div>
                  </div>
                  <p className="text-[10px] text-muted-foreground text-center">{evalResult.total_cases} cases in {evalResult.elapsed_seconds}s</p>
                  <button onClick={() => {
                    const rows = [['Case ID','Expected DX','Actual DX','Match','Expected PROC','Actual PROC','Match','Latency(ms)']];
                    (evalResult.per_case||[]).forEach((c:any) => rows.push([c.case_id,c.expected_dx,c.actual_dx,c.dx_match?'YES':'NO',c.expected_proc||'',c.actual_proc||'',c.proc_match?'YES':'NO',String(c.latency_ms||0)]));
                    const csv = rows.map(r => r.join(',')).join('\n');
                    const blob = new Blob(['﻿'+csv], {type:'text/csv;charset=utf-8'});
                    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `eval-${agentRef||'agent'}-${new Date().toISOString().slice(0,10)}.csv`; a.click();
                  }} className="w-full mt-2 py-1.5 rounded text-[10px] border border-border text-muted-foreground hover:text-foreground">导出 CSV</button>
                  <div className="max-h-48 overflow-y-auto space-y-1">
                    {evalResult.per_case?.map((c: any, i: number) => (
                      <div key={i} className="flex items-center gap-2 py-1 border-b border-muted">
                        <span className="text-[10px] font-mono">{c.case_id}</span>
                        <span className="text-[10px] font-mono">{c.expected_dx}</span>
                        <span className="ml-auto">{c.dx_match ? '✅' : '❌'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {evalHistory.length > 0 && (
                <div className="bg-white rounded-lg border p-3 text-xs">
                  <p className="font-medium mb-1">历史趋势</p>
                  {evalHistory.slice(0,5).map((h: any, i: number) => (
                    <div key={i} className="flex justify-between py-0.5 text-[10px]">
                      <span className="text-muted-foreground">{h.evaluated_at?.slice(0,16)||''}</span>
                      <span className="font-mono text-green-700">{h.primary_dx_accuracy ? (h.primary_dx_accuracy*100).toFixed(0)+'%' : '—'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
          <SettingsCodeTab
            labels={{ settings: '设置', code: '代码', tools: '工具' }}
            tools={
              <ToolSelector
                enabledTools={enabledTools}
                onChange={setEnabledTools}
                tier1Enforce={tier1Enforce}
                onTier1EnforceChange={setTier1Enforce}
              />
            }
            settings={
              <div className="flex flex-col">
                {/* Name */}
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">基本信息</h3>
                  </div>
                  <div className="px-4 pb-4">
                    <label className="text-xs text-foreground/70 block mb-1.5">
                      {t.agentDetailName} <span className="text-muted-foreground/50 font-normal">({agentName.length}/50)</span>
                    </label>
                    <input
                      value={agentName}
                      onChange={e => { setAgentName(e.target.value.slice(0, 50)); setSettingsSaved(false); }}
                      placeholder={t.agentNamePlaceholder}
                      maxLength={50}
                      className="w-full text-sm border border-border/60 rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-ring/30 transition-all"
                    />
                  </div>
                </div>

                {/* System Prompt */}
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">{t.systemPrompt}</h3>
                  </div>
                  <div className="px-4 pb-4">
                    <div
                      onClick={() => setShowEditPrompt(true)}
                      className="w-full text-left border border-border/60 rounded-lg p-3 text-xs text-muted-foreground bg-muted/20 hover:border-primary/40 hover:bg-muted/30 transition-all min-h-[80px] max-h-[200px] overflow-y-auto cursor-text leading-relaxed font-mono whitespace-pre-wrap"
                    >
                      {systemPrompt ? (
                        <span className="text-foreground/80">{systemPrompt}</span>
                      ) : (
                        <span className="italic text-muted-foreground/40">{t.clickToDefinePrompt}</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Experts */}
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">{t.experts}</h3>
                    {agentExperts.length > 0 && (
                      <span className="text-[10px] text-muted-foreground/50 ml-auto">{agentExperts.length} 个</span>
                    )}
                  </div>
                  <div className="px-4 pb-4">
                    {agentExperts.length === 0 ? (
                      <div className="text-center py-4 border border-dashed border-border/40 rounded-lg">
                        <Wrench size={16} className="mx-auto mb-1 text-muted-foreground/25" />
                        <p className="text-[11px] text-muted-foreground/40">{t.noExpertsBound}</p>
                      </div>
                    ) : (
                      <div className="space-y-0.5 mb-3">
                        {agentExperts.map((expert, idx) => (
                          <div key={expert.id}
                            draggable
                            onDragStart={() => { setDragIdx(idx); }}
                            onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('ring-2', 'ring-primary/30'); }}
                            onDragLeave={(e) => { e.currentTarget.classList.remove('ring-2', 'ring-primary/30'); }}
                            onDrop={(e) => {
                              e.currentTarget.classList.remove('ring-2', 'ring-primary/30');
                              if (dragIdx !== null && dragIdx !== idx) {
                                const a = [...agentExperts];
                                const [moved] = a.splice(dragIdx, 1);
                                a.splice(idx, 0, moved);
                                setAgentExperts(a);
                                setSettingsSaved(false);
                              }
                              setDragIdx(null);
                            }}
                            onDragEnd={() => { setDragIdx(null); }}
                            className={`flex items-center py-2 px-2.5 rounded-lg hover:bg-accent/40 transition-all group border border-transparent hover:border-border/30 cursor-grab active:cursor-grabbing ${dragIdx === idx ? 'opacity-50' : ''}`}>
                            <span className="text-[9px] text-muted-foreground/40 w-4 shrink-0" title="拖拽排序">⠿</span>
                            <div className="flex items-center gap-2.5 min-w-0 flex-1">
                              <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center shrink-0">
                                <Wrench size={12} className="text-primary" />
                              </div>
                              <span className="text-xs text-foreground/80 truncate">{expert.name}</span>
                            </div>
                            <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button onClick={() => removeExpertFromAgent(expert.id)}
                                className="p-0.5 rounded text-muted-foreground/30 hover:text-destructive"><X size={12} /></button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <button
                      onClick={openExpertBrowser}
                      className="w-full text-xs text-primary/70 hover:text-primary transition-colors flex items-center justify-center gap-1.5 py-2 rounded-lg hover:bg-primary/5 border border-dashed border-border/30 hover:border-primary/30"
                    >
                      <Plus size={12} /> {t.addExpert}
                    </button>
                    {agentExperts.length > 1 && (
                      <p className="text-[10px] text-muted-foreground/40 mt-1.5 text-center">⠿ 拖拽专家调整调用优先级</p>
                    )}
                  </div>
                </div>

                {/* Orchestration Strategy */}
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">编排策略</h3>
                  </div>
                  <div className="px-4 pb-4 space-y-3">
                    <div>
                      <label className="text-[10px] text-muted-foreground">路由策略</label>
                      <select value={routingStrategy} onChange={e => { setRoutingStrategy(e.target.value); setSettingsSaved(false); }}
                        className="w-full text-xs border border-border/60 rounded-lg px-2.5 py-2 bg-background text-foreground mt-0.5 focus:outline-none focus:ring-1 focus:ring-ring">
                        <option value="llm_plan">LLM 动态规划（推荐）</option>
                        <option value="tool_native">Tool-Native 合同强制（新）</option>
                        <option value="fixed_order">固定顺序执行</option>
                        <option value="parallel">并行调用</option>
                        <option value="single_expert">单专家直连</option>
                      </select>
                      <p className="text-[9px] text-muted-foreground/50 mt-0.5">
                        {routingStrategy === 'llm_plan' && '由 AI 分析任务后动态选择专家及调用顺序'}
                        {routingStrategy === 'tool_native' && 'LLM 自主选择工具，Harness 以合同强制验证每次调用'}
                        {routingStrategy === 'fixed_order' && '按列表顺序逐个调用绑定的专家'}
                        {routingStrategy === 'parallel' && '同时调用所有专家，聚合结果'}
                        {routingStrategy === 'single_expert' && '仅调用默认专家，忽略其他绑定'}
                      </p>
                    </div>

                    {/* Permission Preset */}
                    <div>
                      <label className="text-[10px] text-muted-foreground">权限策略 (Deny-First)</label>
                      <select value={permissionPreset} onChange={e => { setPermissionPreset(e.target.value); setSettingsSaved(false); }}
                        className="w-full text-xs border border-border/60 rounded-lg px-2.5 py-2 bg-background text-foreground mt-0.5 focus:outline-none focus:ring-1 focus:ring-ring">
                        <option value="medical_coding">医学编码（推荐）</option>
                        <option value="cdi_audit">临床文档审核（只读）</option>
                        <option value="drg_analysis">DRG/DIP 支付分析</option>
                        <option value="restrictive">严格模式（仅确定性工具）</option>
                        <option value="full_access">全量访问（开发/管理）</option>
                      </select>
                      <p className="text-[9px] text-muted-foreground/50 mt-0.5">
                        {permissionPreset === 'medical_coding' && '标准编码管道——确定性工具+LLM工具有限使用'}
                        {permissionPreset === 'cdi_audit' && '只读分析工具——不允许编码分配'}
                        {permissionPreset === 'drg_analysis' && '编码+DRG分析——适合医保审核'}
                        {permissionPreset === 'restrictive' && '仅确定性工具（ICD索引/证据排名等），最大安全性'}
                        {permissionPreset === 'full_access' && '全部工具可用——仅开发和管理使用'}
                      </p>
                    </div>
                    <div>
                      <label className="text-[10px] text-muted-foreground">最大重试次数: {maxRetries}</label>
                      <input type="range" min="0" max="5" value={maxRetries} onChange={e => { setMaxRetries(Number(e.target.value)); setSettingsSaved(false); }}
                        className="w-full mt-0.5" />
                    </div>
                    <div>
                      <label className="text-[10px] text-muted-foreground">置信度阈值: {confidenceThreshold.toFixed(1)}</label>
                      <input type="range" min="0" max="1" step="0.1" value={confidenceThreshold} onChange={e => { setConfidenceThreshold(Number(e.target.value)); setSettingsSaved(false); }}
                        className="w-full mt-0.5" />
                      <div className="flex justify-between text-[9px] text-muted-foreground/40"><span>0.0 (宽松)</span><span>1.0 (严格)</span></div>
                    </div>
                  </div>
                </div>

                {/* A2A Collaboration */}
                <A2ACollaboration currentAgentId={agentId || ''} />

                {/* Actions */}
                <div className="px-4 py-3 flex items-center justify-between">
                  <button
                    onClick={handleDeleteAgent}
                    className="text-xs px-3 py-1.5 rounded-lg text-muted-foreground/50 hover:text-destructive hover:bg-destructive/5 transition-colors flex items-center gap-1.5"
                  >
                    <Trash2 size={12} /> {t.delete}
                  </button>
                  <button
                    onClick={handleSaveSettings}
                    disabled={savingSettings}
                    className="text-xs px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-all shadow-sm shadow-primary/20"
                  >
                    {savingSettings ? t.savingAgent : settingsSaved ? t.savedAgent : t.save}
                  </button>
                </div>
              </div>
            }
            code={
              <CodeSnippet
                javascript={`import { iCoDerClient } from "@icoder/sdk";

const client = new iCoDerClient({
  apiKey: "YOUR_API_KEY",
});

// Create and configure the agent
const agent = await client.agents.create({
  name: "${agentTitle}",
  description: ${JSON.stringify(agent?.description || '')},
  experts: [
${agentExperts.map(e => `    { name: "${e.name}", type: "reference" },`).join('\n')}
  ],
  systemPrompt: ${JSON.stringify(systemPrompt || '')},
});

const agentId = agent.id;

// Send a message to the agent
const result = await client.agents.messageSend(agentId, {
  message: {
    role: "user",
    parts: [
      {
        text: "patient case...",
        kind: "text",
      },
    ],
    messageId: crypto.randomUUID(),
    kind: "message",
  },
});

console.log("Agent response:", result);`}
                python={`from icoder import iCoDerClient
import uuid

client = iCoDerClient(
    api_key="YOUR_API_KEY"
)

# Create and configure the agent
agent = client.agents.create(
    name="${agentTitle}",
    description=${JSON.stringify(agent?.description || '')},
    experts=[
${agentExperts.map(e => `        {"name": "${e.name}", "type": "reference"},`).join('\n')}
    ],
    system_prompt=${JSON.stringify(systemPrompt || '')},
)

agent_id = agent["id"]

# Send a message to the agent
result = client.agents.message_send(
    agent_id=agent_id,
    message={
        "role": "user",
        "parts": [
            {
                "text": "patient case...",
                "kind": "text",
            },
        ],
        "message_id": str(uuid.uuid4()),
        "kind": "message",
    },
)

print("Agent response:", result)`}
                csharp={`using iCoDer;
using iCoDer.Agents;

var client = new iCoDerClient("YOUR_API_KEY");

// Create and configure the agent
var createRequest = new AgentCreateRequest
{
    Name = "${agentTitle}",
    Description = ${JSON.stringify(agent?.description || '')},
    Experts = new List<AgentExpertRef>
    {
${agentExperts.map(e => `        new AgentExpertRef { Name = "${e.name}", Type = "reference" },`).join('\n')}
    },
    SystemPrompt = @${JSON.stringify(systemPrompt || '')},
};

var agent = await client.Agents.CreateAsync(createRequest);
var agentId = agent.Id;

// Send a message to the agent
var message = new AgentMessage
{
    Role = "user",
    Parts = new List<MessagePart>
    {
        new MessagePart { Text = "patient case...", Kind = "text" },
    },
    MessageId = Guid.NewGuid().ToString(),
    Kind = "message",
};

var result = await client.Agents.MessageSendAsync(agentId, message);

Console.WriteLine($"Agent response: {result}");`}
                json={JSON.stringify({
                  name: agentTitle,
                  description: agent?.description || '',
                  system_prompt: systemPrompt || '',
                  experts: agentExperts.map(e => ({ name: e.name, type: 'reference' })),
                  config: agent?.config || {},
                }, null, 2)}
              />
            }
          />
        )}
        </div>
      </div>

      {/* Expert Library Modal (iCoDer-style) */}
      <ExpertLibraryModal
        open={showExpertBrowser}
        onClose={() => setShowExpertBrowser(false)}
        onDone={(experts) => {
          setAgentExperts(experts.map(e => ({ id: e.id, name: e.name, icon: e.icon || 'Bot' })));
        }}
        preSelected={agentExperts}
      />

      {/* System Prompt Editor Modal */}
      {showEditPrompt && (
        <EditSystemPromptModal
          value={systemPrompt}
          onSave={(val) => { setSystemPrompt(val); setShowEditPrompt(false); setSettingsSaved(false); }}
          onCancel={() => setShowEditPrompt(false)}
          agentName={agentName}
          agentDesc={agent?.description || agent?.desc || ''}
          agentCategory={agent?.category || agent?.useCase || 'general'}
        />
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => setShowDeleteConfirm(false)}>
          <div className="absolute inset-0 bg-black/40" />
          <div className="relative bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-6 max-w-sm w-full mx-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-foreground mb-1">{t.deleteConfirmTitle}</h3>
            <p className="text-xs text-muted-foreground mb-4">{t.deleteConfirmDesc}</p>
            <p className="text-sm text-foreground mb-6">
              {t.deleteConfirmMessage.split('{name}')[0]}<span className="font-medium">{agentTitle}</span>{t.deleteConfirmMessage.split('{name}')[1]}
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="text-sm px-4 py-2 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              >
                {t.cancel}
              </button>
              <button
                onClick={confirmDeleteAgent}
                className="text-sm px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                {t.confirmDelete}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Attachment Modal */}
      {editingAttachment !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setEditingAttachment(null)}>
          <div className="bg-card rounded-xl border border-border shadow-xl w-full max-w-lg mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-border">
              <h3 className="text-sm font-semibold text-foreground">编辑病例内容</h3>
              <button onClick={() => setEditingAttachment(null)} className="p-1 rounded hover:bg-accent"><X size={14} className="text-muted-foreground" /></button>
            </div>
            <div className="p-5">
              <textarea
                value={editingAttachment}
                onChange={e => setEditingAttachment(e.target.value)}
                rows={12}
                className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent text-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none leading-relaxed"
                autoFocus
              />
            </div>
            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border bg-muted/20">
              <button onClick={() => setEditingAttachment(null)} className="text-xs px-4 py-2 rounded-lg hover:bg-accent transition-colors">取消</button>
              <button onClick={() => {
                if (attachedFile && editingAttachment.trim()) {
                  setAttachedFile({ ...attachedFile, content: editingAttachment.trim() });
                }
                setEditingAttachment(null);
              }} className="text-xs px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
