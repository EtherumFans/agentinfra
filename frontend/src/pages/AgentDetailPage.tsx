// Agent Detail Page - standalone page for /ai-studio/agents/:agentId
// Chat area (left) + SettingsCodeTab (right) with Settings/Code tabs
import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useT } from '../i18n';
import {
  Bot, Send, Loader2, Home, ChevronRight, Plus, Settings, Code,
  X, Paperclip, FileText, Braces, Trash2, Wrench, Pencil,
  Search, Check, Sparkles, BookOpen, Copy, User, Clock,
} from 'lucide-react';
import { agentsApi, billingApi, oauthApi } from '../services/api';
import { agentHubApi } from '../services/agentHubApi';
import { runtimeAgentApi } from '../services/runtimeApi';
import { useToastStore } from '../store';
import type { RuntimeRunResult } from '../types/runtime';
import SettingsCodeTab from '../components/common/SettingsCodeTab';
import ToolSelector from '../components/agents/ToolSelector';
import CodeSnippet from '../components/common/CodeSnippet';
import EditSystemPromptModal from '../components/EditSystemPromptModal';
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
  // Phase 4-G #4: fork button state (clones iCoDer built agent into user's namespace)
  const [forkLoading, setForkLoading] = useState(false);
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
    agentsApi.get(agentId).then(r2 => {
      if (!isActive()) return;
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
      // Fallback: try Hub (prebuilt agents like icoder/medical-coding-agent@2.0.0)
      try {
        const hubRes = await agentHubApi.list();
        if (!isActive()) return;
        const card = (hubRes.data?.agents || []).find(c => c.agent_ref === agentId || c.agent_id === agentId);
        if (card) {
          setAgent({
            id: card.agent_ref,
            name: card.name,
            description: card.description,
            version: card.version,
            category: card.category,
            system_prompt: '',
            expert_ids: [],
            config: { default_runtime_mode: card.default_runtime_mode },
            is_prebuilt: true,
            red_lines: card.red_lines,
            workflow: card.workflow,
            badge: card.badge,
            maturity: card.maturity,
            production_ready: card.production_ready,
            human_review: card.human_review,
          } as any);
          setAgentName(card.name); setAgentRef(card.agent_ref);
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

    const assistantIdx = chatMessages.length + 1;
    setChatMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    try {
      const token = localStorage.getItem('access_token') || '';
      void token; // auth handled by axios interceptor in runtimeApi

      // Phase 4-F (2026-07-09): use unified Agent Run API
      // POST /api/v1/agents/{id}/run — uniform 13-field envelope across
      // all iCoDer built agents. Routes internally to CodingRuntimeDispatcher
      // (medical-coding) or ProviderRegistry (others).
      const { runtimeAgentApi } = await import('../services/runtimeApi');
      const resp = await runtimeAgentApi.agentRun(agentId || '', content, {
        runtime_mode: agent?.default_runtime_mode || undefined,
      });

      if (!isActive()) return;

      if (resp.error) {
        setChatMessages(prev => prev.map((m, i) =>
          i === assistantIdx
            ? { ...m, content: `错误：${resp.summary || resp.error_reason || 'agent run failed'}` }
            : m
        ));
      } else {
        // Format response: summary + result preview
        const parts: string[] = [];
        if (resp.summary) parts.push(resp.summary);
        if (resp.result && Object.keys(resp.result).length > 0) {
          parts.push('```json\n' + JSON.stringify(resp.result, null, 2) + '\n```');
        }
        if (resp.warnings?.length) {
          parts.push('⚠️ ' + resp.warnings.join('; '));
        }
        if (resp.manual_review_required) {
          parts.push('🔍 人工复核提示：本次运行结果需经编码员人工确认。');
        }
        const assistantContent = parts.join('\n\n') || '(no output)';
        setChatMessages(prev => prev.map((m, i) =>
          i === assistantIdx ? { ...m, content: assistantContent } : m
        ));
        // Stash raw JSON for Copy JSON button.
        setJsonData(JSON.stringify(resp, null, 2));
      }
      setChatLoading(false);
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      if (isActive()) {
        const msg = err?.response?.data?.detail || err.message || 'agent run failed';
        setChatMessages(prev => prev.map((m, i) =>
          i === assistantIdx ? { ...m, content: m.content || `错误：${msg}` } : m
        ));
        setChatLoading(false);
      }
    }
  };

  // Quick actions
  const handleWhatCanYouDo = () => {
    handleSend(t.agentDetailCapabilityQuestion);
  };


  const [editingAttachment, setEditingAttachment] = useState<string | null>(null);

  const handleSuggestPrompt = () => {
    const caseItem = { caseLabel: t.agentDetailTestCaseLabel, caseText: t.agentDetailTestCaseText };

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
    // /api/agents/{id}/evaluation-history was deleted in Phase 2.1-A.
    // TODO: re-implement via A2A run history (/api/runtime/runs) filtered by agent_ref.
    try {
      const ref = agentRef || (agent?.name?.toLowerCase()?.replace(/\s+/g,'-')||'') + '-' + (agent?.version||'1.0.0');
      // eslint-disable-next-line no-unused-vars
      const _ = ref; // (kept for future A2A history call)
      setEvalHistory([]);
    } catch {}
  };
  const runEvaluation = async () => {
    // /api/agents/{id}/evaluate was deleted in Phase 2.1-A.
    // TODO: re-implement via A2A message:send + evaluation agent.
    setEvalLoading(true);
    try {
      throw new Error('Agent evaluation endpoint removed in Phase 2.1-A. Use A2A message:send with an evaluation agent.');
    } catch (e: any) {
      // Surface the migration error
      console.warn(e.message);
    } finally { setEvalLoading(false); }
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
          <div className="bg-background rounded-xl shadow-sm text-center py-16">
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
              toast(t.agentDetailInstalledToast, 'success');
            } catch (e: any) {
              const msg = e?.response?.data?.detail || e?.message || t.agentDetailInstallFailed;
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
            {/* Phase 4-G #4: Fork iCoDer built agent into user's editable namespace */}
            {agent?.is_prebuilt && (
              <button
                onClick={async () => {
                  if (forkLoading || !agentId) return;
                  setForkLoading(true);
                  try {
                    const res = await agentHubApi.clone(agentId);
                    const data = res.data;
                    const forkedId = data.project_agent_id || agentId;
                    if (data.cloned) {
                      toast(t.agentClonedToDraftToast || '已复制到我的智能体', 'success');
                    } else {
                      toast(t.agentExistingCloneToast || '已有副本,正在打开', 'warning');
                    }
                    navigate(`/ai-studio/agents/${encodeURIComponent(forkedId)}`);
                  } catch (e: any) {
                    const status = e?.response?.status;
                    if (status === 401) {
                      toast(t.agentLoginRequiredToast || '请先登录', 'error');
                      navigate('/login');
                    } else {
                      toast(e?.response?.data?.detail || e?.message || t.agentCloneFailedToast || '复制失败', 'error');
                    }
                  } finally { setForkLoading(false); }
                }}
                disabled={forkLoading}
                className="px-2 py-0.5 rounded text-[11px] bg-primary/10 text-primary hover:bg-primary/20 disabled:opacity-50 flex items-center gap-1 transition-colors"
                title="Clone this iCoDer built agent into your editable namespace"
              >
                {forkLoading ? 'Forking...' : '自定义'}
              </button>
            )}
            <button onClick={() => setShowTestPanel(!showTestPanel)}
              className="px-2 py-0.5 rounded text-[11px] bg-blue-50 text-blue-600 hover:bg-blue-100">
              {t.agentDetailTestTitle}
            </button>
            <button onClick={() => { setShowEval(!showEval); if (!showEval && !evalHistory.length) fetchEvalHistory(); }}
              className="px-2 py-0.5 rounded text-[11px] bg-green-50 text-green-600 hover:bg-green-100">
              {t.agentDetailEvalTitle}
            </button>
            <button onClick={async () => {
              try {
                const newAction = runtimeStatus === 'enabled' ? 'disable' : 'enable';
                await runtimeAgentApi.agentLifecycle(agentRef, newAction);
                setRuntimeStatus(runtimeStatus === 'enabled' ? 'disabled' : 'enabled');
                toast(newAction === 'enable' ? t.agentEnabledToast : t.agentDisabledToast, 'success');
              } catch { toast(t.agentDetailOperationFailed, 'error'); }
            }}
              className="px-2 py-0.5 rounded text-[11px] bg-gray-100 hover:bg-gray-200">
              {runtimeStatus === 'enabled' ? t.agentDisable : t.agentEnable}
            </button>
          </div>
        )}
      </div>

      {/* Agent Test Panel */}
      {showTestPanel && (
        <div className="px-6 py-3 bg-blue-50/50 border-b border-blue-100">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-foreground">{t.agentDetailTestTitle}</h4>
            <button onClick={() => { setShowTestPanel(false); setTestResult(null); setTestInput(''); }}
              className="p-0.5 rounded hover:bg-accent"><X size={14} className="text-muted-foreground" /></button>
          </div>
          <div className="flex gap-2">
            <textarea value={testInput} onChange={e => setTestInput(e.target.value)}
              placeholder={t.agentDetailTestInputPlaceholder}
              rows={4} className="flex-1 text-xs border border-border rounded-lg px-3 py-2 bg-background resize-none focus:outline-none focus:ring-1 focus:ring-ring" />
            <button onClick={async () => {
              if (!testInput.trim() || testLoading) return;
              setTestLoading(true); setTestResult(null);
              try {
                const ref = agentRef || (agent?.name?.toLowerCase()?.replace(/\s+/g,'-')||'agent') + '-' + (agent?.version||'1.0.0');
                const data = await runtimeAgentApi.runAgent(ref, testInput);
                setTestResult(data);
              } catch (e: any) { setTestResult({ error: e?.message || t.agentDetailTestFailed }); }
              finally { setTestLoading(false); }
            }} disabled={testLoading || !testInput.trim()}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-40 shrink-0 self-end">
              {testLoading ? t.agentDetailRunning : t.agentDetailRunTest}
            </button>
          </div>
          {testResult && (
            <div className="mt-3 bg-background rounded-lg border border-border p-3 text-xs space-y-2">
              {testResult.error ? (
                <p className="text-red-600">{testResult.error}</p>
              ) : (
                <>
                  <div className="flex gap-4">
                    <span>{t.agentDetailStatus}: <b>{testResult.status || '-'}</b></span>
                    <span>{t.agentDetailDuration}: <b>{testResult.processing_time_ms || 0}ms</b></span>
                    <span>{t.agentDetailSafety}: <b>{testResult.safety ? t.agentDetailVerified : '-'}</b></span>
                  </div>
                  {testResult.primary_diagnosis?.code && (
                    <div>
                      <p className="text-muted-foreground">{t.agentDetailPrimaryDx}</p>
                      <p className="font-mono text-sm">{testResult.primary_diagnosis.code} - {testResult.primary_diagnosis.description || ''}</p>
                    </div>
                  )}
                  {testResult.secondary_diagnoses?.length > 0 && (
                    <div>
                      <p className="text-muted-foreground">{t.agentDetailSecondaryDx} ({testResult.secondary_diagnoses.length})</p>
                      <div className="flex flex-wrap gap-1">
                        {testResult.secondary_diagnoses.slice(0, 10).map((d: any, i: number) => (
                          <span key={i} className="px-1.5 py-0.5 bg-muted rounded font-mono text-[10px]">{d.code}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {testResult.procedures?.length > 0 && (
                    <div>
                      <p className="text-muted-foreground">{t.agentDetailProcedures} ({testResult.procedures.length})</p>
                      <div className="flex flex-wrap gap-1">
                        {testResult.procedures.map((p: any, i: number) => (
                          <span key={i} className="px-1.5 py-0.5 bg-muted rounded font-mono text-[10px]">{p.code}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {testResult.issues_found?.length > 0 && (
                    <div>
                      <p className="text-muted-foreground">{t.agentDetailIssues} ({testResult.issues_found.length})</p>
                      {testResult.issues_found.slice(0, 5).map((iss: any, i: number) => (
                        <p key={i} className="text-[10px] text-amber-700">[{iss.severity}] {iss.message}</p>
                      ))}
                    </div>
                  )}
                  {testResult.safety?.post_check?.rule_issues?.length > 0 && (
                    <div>
                      <p className="text-muted-foreground">{t.agentDetailRuleChecks}</p>
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
        {/* Left: Chat area - bg-muted/20 with card content */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0 bg-muted/20">
          <div className="flex-1 p-4 flex flex-col min-h-0">
            <div className="bg-background rounded-xl shadow-sm flex-1 flex flex-col min-h-0 overflow-y-auto">
            {chatMessages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-6">
                <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-6">
                  <Bot size={28} className="text-primary" />
                </div>
                <h3 className="text-lg font-brand text-foreground mb-2">{t.askTheAgentTitle}</h3>
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
              {/* Attached case document card - iCoDer-style, above input */}
              {attachedFile && (
                <div className="mb-2 bg-background rounded-xl shadow-sm overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-border/20 bg-muted/30">
                    <div className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded bg-primary/10 flex items-center justify-center">
                        <FileText size={11} className="text-primary" />
                      </div>
                      <span className="text-[11px] font-medium text-foreground">{attachedFile.name}</span>
                    </div>
                    <div className="flex items-center gap-0.5">
                      <button onClick={() => setEditingAttachment(attachedFile.content)} className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors" title={t.agentDetailEdit}>
                        <Pencil size={11} />
                      </button>
                      <button onClick={() => setAttachedFile(null)} className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors" title={t.agentDetailRemove}>
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
                <div className="mb-2 bg-background rounded-xl shadow-sm p-3">
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
                    className="w-full text-xs font-mono bg-muted/50 border border-border rounded-lg px-3 py-2 text-foreground placeholder:text-foreground/70 resize-none focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
              )}

              {/* Main input */}
              <div className="bg-background rounded-2xl shadow-sm focus-within:ring-primary/30 focus-within:shadow-md transition-all">
                <textarea
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); handleSend(); } }}
                  placeholder={t.askTheAgentPlaceholder}
                  rows={1}
                  className="w-full text-sm bg-transparent focus:outline-none placeholder:text-foreground/70 resize-none py-3 px-4 min-h-[40px] max-h-[120px]"
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

                  {/* Phase 4-F: API Client dropdown — Corti-style usage attribution selector */}
                  {apiClients.length > 0 && (
                    <select
                      value={selectedApiClient}
                      onChange={e => setSelectedApiClient(e.target.value)}
                      className="text-[10px] text-muted-foreground bg-transparent border border-border/40 rounded-md px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-ring max-w-[120px]"
                      title={t.apiClient || 'API Client'}
                    >
                      {apiClients.map((c: any) => (
                        <option key={c.client_id} value={c.client_id}>
                          {c.name || c.client_id}
                        </option>
                      ))}
                    </select>
                  )}

                  <button onClick={() => handleSend()}
                    disabled={(!chatInput.trim() && !jsonData.trim() && !attachedFile) || chatLoading}
                    className="w-9 h-9 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 active:scale-[0.98] disabled:opacity-30 transition-all shrink-0 flex items-center justify-center">
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
                <h4 className="text-xs font-semibold text-foreground">{t.agentDetailEvalTitle}</h4>
                <button onClick={() => setShowEval(false)} className="p-0.5 rounded hover:bg-accent"><X size={14} className="text-muted-foreground" /></button>
              </div>
              <button onClick={runEvaluation} disabled={evalLoading}
                className="w-full py-2 rounded-lg bg-green-600 text-white text-xs font-medium hover:bg-green-700 disabled:opacity-40">
                {evalLoading ? t.agentDetailEvaluating : t.agentDetailRunGoldStandard}
              </button>
              {evalResult && (
                <div className="bg-white rounded-lg border p-3 space-y-2 text-xs">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="text-center p-2 bg-muted/50 rounded"><p className="text-lg font-bold text-green-700">{evalResult.primary_dx_accuracy ? (evalResult.primary_dx_accuracy*100).toFixed(0)+'%' : '-'}</p><p className="text-[10px] text-muted-foreground">{t.agentDetailDxAccuracy}</p></div>
                    <div className="text-center p-2 bg-muted/50 rounded"><p className="text-lg font-bold text-blue-700">{evalResult.primary_proc_accuracy ? (evalResult.primary_proc_accuracy*100).toFixed(0)+'%' : '-'}</p><p className="text-[10px] text-muted-foreground">{t.agentDetailProcAccuracy}</p></div>
                  </div>
                  <p className="text-[10px] text-muted-foreground text-center">{evalResult.total_cases} cases in {evalResult.elapsed_seconds}s</p>
                  <button onClick={() => {
                    const rows = [['Case ID','Expected DX','Actual DX','Match','Expected PROC','Actual PROC','Match','Latency(ms)']];
                    (evalResult.per_case||[]).forEach((c:any) => rows.push([c.case_id,c.expected_dx,c.actual_dx,c.dx_match?'YES':'NO',c.expected_proc||'',c.actual_proc||'',c.proc_match?'YES':'NO',String(c.latency_ms||0)]));
                    const csv = rows.map(r => r.join(',')).join('\n');
                    const blob = new Blob(['﻿'+csv], {type:'text/csv;charset=utf-8'});
                    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `eval-${agentRef||'agent'}-${new Date().toISOString().slice(0,10)}.csv`; a.click();
                  }} className="w-full mt-2 py-1.5 rounded text-[10px] border border-border text-muted-foreground hover:text-foreground">{t.agentDetailExportCsv}</button>
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
                  <p className="font-medium mb-1">{t.agentDetailHistoryTrend}</p>
                  {evalHistory.slice(0,5).map((h: any, i: number) => (
                    <div key={i} className="flex justify-between py-0.5 text-[10px]">
                      <span className="text-muted-foreground">{h.evaluated_at?.slice(0,16)||''}</span>
                      <span className="font-mono text-green-700">{h.primary_dx_accuracy ? (h.primary_dx_accuracy*100).toFixed(0)+'%' : '-'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
          <SettingsCodeTab
            labels={{ settings: t.settingsCodeTabSettings, code: t.settingsCodeTabCode, tools: t.settingsCodeTabTools }}
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
                {/* Phase 4-G #4: Forked-from badge for clones (config.source_agent_ref) */}
                {agent?.config?.source_agent_ref && (
                  <div className="px-4 pt-3 pb-2 bg-primary/5 border-b border-primary/10">
                    <div className="flex items-center gap-1.5 text-[10px] text-primary">
                      <span className="px-1.5 py-0.5 rounded bg-primary/10 font-medium">Forked</span>
                      <span className="text-muted-foreground">from</span>
                      <code className="font-mono text-primary/80 break-all">{agent.config.source_agent_ref}</code>
                    </div>
                  </div>
                )}
                {/* Name */}
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs text-muted-foreground">{t.agentDetailBasicInfo}</h3>
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
                      className="w-full text-sm border border-border/60 rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-foreground/70/40 focus:outline-none focus:ring-2 focus:ring-ring/30 transition-all"
                    />
                  </div>
                </div>

                {/* System Prompt */}
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs text-muted-foreground">{t.systemPrompt}</h3>
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
                    <h3 className="font-medium text-xs text-muted-foreground">{t.experts}</h3>
                    {agentExperts.length > 0 && (
                      <span className="text-[10px] text-muted-foreground/50 ml-auto">{agentExperts.length} {t.agentDetailExpertCountSuffix}</span>
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
                            <span className="text-[9px] text-muted-foreground/40 w-4 shrink-0" title={t.agentDetailDragSort}>⠿</span>
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
                      <p className="text-[10px] text-muted-foreground/40 mt-1.5 text-center">⠿ {t.agentDetailDragHint}</p>
                    )}
                  </div>
                </div>

                {/* Orchestration Strategy */}
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs text-muted-foreground">{t.agentDetailOrchestrationStrategy}</h3>
                  </div>
                  <div className="px-4 pb-4 space-y-3">
                    <div>
                      <label className="text-[10px] text-muted-foreground">{t.agentDetailRoutingStrategy}</label>
                      <select value={routingStrategy} onChange={e => { setRoutingStrategy(e.target.value); setSettingsSaved(false); }}
                        className="w-full text-xs border border-border/60 rounded-lg px-2.5 py-2 bg-background text-foreground mt-0.5 focus:outline-none focus:ring-1 focus:ring-ring">
                        <option value="llm_plan">{t.agentDetailRoutingLlmPlan}</option>
                        <option value="tool_native">{t.agentDetailRoutingToolNative}</option>
                        <option value="fixed_order">{t.agentDetailRoutingFixedOrder}</option>
                        <option value="parallel">{t.agentDetailRoutingParallel}</option>
                        <option value="single_expert">{t.agentDetailRoutingSingleExpert}</option>
                      </select>
                      <p className="text-[9px] text-muted-foreground/50 mt-0.5">
                        {routingStrategy === 'llm_plan' && t.agentDetailRoutingLlmPlanDesc}
                        {routingStrategy === 'tool_native' && t.agentDetailRoutingToolNativeDesc}
                        {routingStrategy === 'fixed_order' && t.agentDetailRoutingFixedOrderDesc}
                        {routingStrategy === 'parallel' && t.agentDetailRoutingParallelDesc}
                        {routingStrategy === 'single_expert' && t.agentDetailRoutingSingleExpertDesc}
                      </p>
                    </div>

                    {/* Permission Preset */}
                    <div>
                      <label className="text-[10px] text-muted-foreground">{t.agentDetailPermissionPreset}</label>
                      <select value={permissionPreset} onChange={e => { setPermissionPreset(e.target.value); setSettingsSaved(false); }}
                        className="w-full text-xs border border-border/60 rounded-lg px-2.5 py-2 bg-background text-foreground mt-0.5 focus:outline-none focus:ring-1 focus:ring-ring">
                        <option value="medical_coding">{t.agentDetailPermissionMedicalCoding}</option>
                        <option value="cdi_audit">{t.agentDetailPermissionCdiAudit}</option>
                        <option value="drg_analysis">{t.agentDetailPermissionDrgAnalysis}</option>
                        <option value="restrictive">{t.agentDetailPermissionRestrictive}</option>
                        <option value="full_access">{t.agentDetailPermissionFullAccess}</option>
                      </select>
                      <p className="text-[9px] text-muted-foreground/50 mt-0.5">
                        {permissionPreset === 'medical_coding' && t.agentDetailPermissionMedicalCodingDesc}
                        {permissionPreset === 'cdi_audit' && t.agentDetailPermissionCdiAuditDesc}
                        {permissionPreset === 'drg_analysis' && t.agentDetailPermissionDrgAnalysisDesc}
                        {permissionPreset === 'restrictive' && t.agentDetailPermissionRestrictiveDesc}
                        {permissionPreset === 'full_access' && t.agentDetailPermissionFullAccessDesc}
                      </p>
                    </div>
                    <div>
                      <label className="text-[10px] text-muted-foreground">{t.agentDetailMaxRetriesLabel.replace('{n}', String(maxRetries))}</label>
                      <input type="range" min="0" max="5" value={maxRetries} onChange={e => { setMaxRetries(Number(e.target.value)); setSettingsSaved(false); }}
                        className="w-full mt-0.5" />
                    </div>
                    <div>
                      <label className="text-[10px] text-muted-foreground">{t.agentDetailConfidenceThresholdLabel.replace('{n}', confidenceThreshold.toFixed(1))}</label>
                      <input type="range" min="0" max="1" step="0.1" value={confidenceThreshold} onChange={e => { setConfidenceThreshold(Number(e.target.value)); setSettingsSaved(false); }}
                        className="w-full mt-0.5" />
                      <div className="flex justify-between text-[9px] text-muted-foreground/40"><span>{t.agentDetailConfidenceLoose}</span><span>{t.agentDetailConfidenceStrict}</span></div>
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
                curl={`curl -X POST "${window.location.origin}/api/v1/agents/${encodeURIComponent(agentId || '')}/run" \\
  -H "Authorization: Bearer $ICODER_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "input": {"text": "patient case..."},
    "runtime_mode": "${agent?.default_runtime_mode || ''}",
    "include_trace": true,
    "include_evidence": true
  }'`}
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

      {/* Expert Library Modal removed - experts.py deleted in Phase 2.1-B Step 1 */}

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
          <div className="relative bg-background rounded-xl shadow-sm p-6 max-w-sm w-full mx-4" onClick={e => e.stopPropagation()}>
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
              <h3 className="text-sm font-semibold text-foreground">{t.agentDetailEditCase}</h3>
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
              <button onClick={() => setEditingAttachment(null)} className="text-xs px-4 py-2 rounded-lg hover:bg-accent transition-colors">{t.cancel}</button>
              <button onClick={() => {
                if (attachedFile && editingAttachment.trim()) {
                  setAttachedFile({ ...attachedFile, content: editingAttachment.trim() });
                }
                setEditingAttachment(null);
              }} className="text-xs px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">{t.save}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
