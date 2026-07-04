// iCoDer Agents — iCoDer Console 1:1 with My Agents / Prebuilt tabs + Agent detail chat
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useT, useLocaleStore } from '../i18n';
import {
  Bot, Search, BookOpen, Plus, Clock, User, ChevronRight,
  ChevronDown, Loader2, X, Sparkles,
  Copy, Check, Wrench, Trash2, Send, Globe, Share2, Rocket,
  Layers,
} from 'lucide-react';
import { billingApi, agentsApi, oauthApi } from '../services/api';
import { runtimeAgentApi } from '../services/runtimeApi';
import { useToastStore } from '../store';
import type { InstalledAgent } from '../types/runtime';

const USE_CASE_KEYS = ['全部', '编码', '医保', '质控', '文书', '急诊', '护理', '药学'];
const USE_CASES = USE_CASE_KEYS;

// Agent key → Expert name mapping moved to AgentDetailPage

// Agent expert configuration moved to AgentDetailPage

type TabType = 'my' | 'prebuilt';

export default function AgentsPage() {
  const t = useT();
  const locale = useLocaleStore((s) => s.locale);
  const navigate = useNavigate();
  const toast = useToastStore((s) => s.addToast);
  const [activeTab, setActiveTab] = useState<TabType>('my');
  const [searchQuery, setSearchQuery] = useState('');
  const [useCase, setUseCase] = useState('全部');
  const [balance, setBalance] = useState<number | null>(null);
  const [cost, setCost] = useState('0.000000');
  const [createdByFilter, setCreatedByFilter] = useState('');
  const [showCreatedByFilter, setShowCreatedByFilter] = useState(false);
  const [showUseCaseFilter, setShowUseCaseFilter] = useState(false);

  // Expert name → ID lookup (for clone/creation flow)
  const [expertNameToId, setExpertNameToId] = useState<Record<string, string>>({});
  // New agent creation modal
  const [showNewAgentModal, setShowNewAgentModal] = useState(false);
  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentDesc, setNewAgentDesc] = useState('');
  const [newAgentCategory, setNewAgentCategory] = useState('编码');
  const [newAgentPrompt, setNewAgentPrompt] = useState('');
  const [creatingAgent, setCreatingAgent] = useState(false);
  const [newAgentExperts, setNewAgentExperts] = useState<any[]>([]);
  const [generatingPrompt, setGeneratingPrompt] = useState(false);
  const [showClonePicker, setShowClonePicker] = useState(false);
  // Agents from new Runtime API (per tab)
  const [myAgents, setMyAgents] = useState<InstalledAgent[]>([]);
  const [certifiedAgents, setCertifiedAgents] = useState<InstalledAgent[]>([]);
  const [myAgentsLoading, setMyAgentsLoading] = useState(true);
  const [certifiedLoading, setCertifiedLoading] = useState(true);
  // Agent templates (from backend)
  const [agentTemplates, setAgentTemplates] = useState<any[]>([]);
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [templateSearch, setTemplateSearch] = useState<string>('');
  // API Client selector (iCoDer-style project/workspace switcher)
  const [apiClients, setApiClients] = useState<any[]>([]);
  const [selectedApiClient, setSelectedApiClient] = useState<string>('');
  // Delete confirmation modal state
  const [deleteConfirmAgent, setDeleteConfirmAgent] = useState<any>(null);
  // DB agents (for clone picker and create flow only)
  const [dbAgents, setDbAgents] = useState<any[]>([]);

  useEffect(() => {
    billingApi.balance().then(r => setBalance(r.data.balance)).catch(() => {});
    // Fetch OAuth clients
    oauthApi.list().then(r => {
      const clients = r.data?.clients || [];
      setApiClients(clients);
      if (clients.length > 0) setSelectedApiClient(clients[0].client_id);
    }).catch(() => {});
    // Fetch agent templates
    agentsApi.templates().then(r => {
      setAgentTemplates(r.data?.templates || []);
    }).catch(() => {});
    // Fetch DB agents for clone picker
    agentsApi.list('', '', 'all').then(r => {
      setDbAgents(r.data?.agents || []);
    }).catch(() => setDbAgents([]));
  }, []);

  // ── Tab data loading ──
  const loadMyAgents = () => {
    setMyAgentsLoading(true);
    runtimeAgentApi.listAgents('community')
      .then(data => setMyAgents(data.agents || []))
      .catch(() => setMyAgents([]))
      .finally(() => setMyAgentsLoading(false));
  };
  const loadCertifiedAgents = () => {
    setCertifiedLoading(true);
    runtimeAgentApi.listAgents('certified')
      .then(data => setCertifiedAgents(data.agents || []))
      .catch(() => setCertifiedAgents([]))
      .finally(() => setCertifiedLoading(false));
  };
  useEffect(() => { if (activeTab === 'my') loadMyAgents(); }, [activeTab]);
  useEffect(() => { if (activeTab === 'prebuilt') loadCertifiedAgents(); }, [activeTab]);

  // Load memory context when entering agent detail chat — moved to AgentDetailPage

  // Unique creators for filter dropdown (from community agents)
  const uniqueCreators = [...new Set(
    myAgents.map(a => a.publisher_name || '').filter(Boolean)
  )];

  // Filtered agents for each tab
  const filteredMyAgents = myAgents.filter(a => {
    const matchSearch = !searchQuery || a.name.includes(searchQuery) || a.description.includes(searchQuery);
    const matchCreator = !createdByFilter || (a.publisher_name || '') === createdByFilter;
    return matchSearch && matchCreator;
  });
  const filteredCertifiedAgents = certifiedAgents.filter(a => {
    const matchSearch = !searchQuery || a.name.includes(searchQuery) || a.description.includes(searchQuery);
    const matchUseCase = useCase === '全部' || a.category === useCase;
    return matchSearch && matchUseCase;
  });

  // Refresh Runtime agents list.
  const refreshRuntimeAgents = () => {
    runtimeAgentApi.listAgents().catch(() => {});
  };

  const handleBumpVersion = async (agentId: string) => {
    try {
      await agentsApi.version(agentId);
      refreshRuntimeAgents();
      toast('版本号已更新', 'success');
    } catch { toast('版本更新失败', 'error'); }
  };

  // Normalize agent display data (works with both API and static objects)
  const agentDisplay = (a: any) => ({
    key: a.key || a.id,
    name: a.name,
    desc: a.desc || a.description || '',
    useCase: a.useCase || a.category || 'general',
    createdAt: a.createdAt || (a.created_at ? new Date(a.created_at).toLocaleDateString(locale) : ''),
    createdBy: a.createdBy || a.created_by || '',
    defaultExpertId: a.default_expert_id || '',
    expertIds: a.expert_ids || [],
  });

  // Agent chat and expert management moved to AgentDetailPage (/ai-studio/agents/:agentId)

  // Agent detail view moved to AgentDetailPage (/ai-studio/agents/:agentId)

  // Clone from existing agent — uses backend POST /api/agents/{id}/clone
  const cloneAgent = async (agent: any) => {
    setShowClonePicker(false);
    try {
      const res = await agentsApi.clone(agent.id || agent.key, agent.name + ' (副本)');
      const cloned = res.data;
      toast('已克隆为草稿', 'success');
      navigate('/ai-studio/agents/' + (cloned.id || cloned.agent_id));
    } catch { toast('克隆失败', 'error'); }
  };

  // AI-assisted system prompt generation
  const generatePrompt = async () => {
    // /api/text-gen/generate deleted in Phase 2.1-B Step 4 (text_gen.py removed)
    // Auto-generation disabled; user must write the system prompt manually.
    if (!newAgentName.trim() || generatingPrompt) return;
    setGeneratingPrompt(false);
  };

  // Auto-generate prompt when template is selected (Corti-style AI assist)
  const generatePromptForTemplate = async (name: string, desc: string, category: string) => {
    // /api/text-gen/generate deleted in Phase 2.1-B Step 4 (text_gen.py removed)
    if (!name || generatingPrompt) return;
    setGeneratingPrompt(false);
  };

  // New Agent Creation
  const handleCreateAgent = async () => {
    if (!newAgentName.trim() || creatingAgent) return;
    setCreatingAgent(true);
    try {
      const res = await agentsApi.create({
        name: newAgentName.trim(),
        description: newAgentDesc.trim(),
        system_prompt: newAgentPrompt.trim(),
        category: newAgentCategory,
        expert_ids: newAgentExperts.map(e => e.id),
        default_expert_id: newAgentExperts[0]?.id || '',
      });
      setShowNewAgentModal(false);
      setNewAgentName(''); setNewAgentDesc(''); setNewAgentPrompt(''); setNewAgentExperts([]);
      // Refresh and switch to My Agents tab
      agentsApi.list('', '', 'all').then(r => setDbAgents(r.data?.agents || [])).catch(() => {});
      loadMyAgents();
      setActiveTab('my');
      // Navigate to the newly created agent
      navigate('/ai-studio/agents/' + res.data?.id);
    } catch { /* silently fail */ }
    setCreatingAgent(false);
  };

  // Agent列表视图
  return (
    <div className="flex-1 flex flex-col min-h-0 bg-muted/20">
      <div className="flex-1 p-6 overflow-y-auto">
        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20">
          {/* Section header with accent bar (Corti: "Create an agent" + subtitle + + New Agent) */}
          <div className="flex items-start gap-3 px-6 pt-5 pb-3 border-b border-border/40">
            <Layers size={18} className="text-muted-foreground shrink-0 mt-0.5" />
            <div className="min-w-0 flex-1">
              <h2 className="text-base font-semibold text-foreground tracking-tight">{t.createAgent}</h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">{t.createAgentSubtitle}</p>
            </div>
            <button
              onClick={() => navigate('/ai-studio/agents/new')}
              className="shrink-0 inline-flex items-center gap-1.5 text-xs px-3 py-2 bg-foreground text-background rounded-lg hover:opacity-90 transition-opacity font-medium"
            >
              <Plus size={14} /> {t.newAgent}
            </button>
          </div>

      {/* 标签切换 */}
      <div className="flex items-center gap-3 px-6 pt-4 pb-2">
        <div className="flex items-center rounded-lg border border-border p-0.5">
          {([
            { id: 'my' as TabType, label: t.myAgents },
            { id: 'prebuilt' as TabType, label: t.prebuiltAgents },
          ]).map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
                activeTab === tab.id
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {/* 搜索 */}
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder={t.searchAgents}
            className="pl-7 pr-3 py-1.5 text-sm border border-border rounded-md bg-transparent focus:outline-none focus:ring-1 focus:ring-ring w-52"
          />
        </div>

        {/* Created by filter（仅在"我的AI智能体"标签时显示） */}
        {activeTab === 'my' && (
          <div className="relative">
            <button
              onClick={() => setShowCreatedByFilter(!showCreatedByFilter)}
              className="flex items-center gap-1 text-sm h-8 px-3 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              <User size={14} />
              <span>{createdByFilter || t.allCreators}</span>
              <ChevronDown size={10} />
            </button>
            {showCreatedByFilter && (
              <div className="absolute right-0 top-full mt-1 bg-popover border border-border rounded-lg shadow-lg p-1 min-w-[160px] z-10">
                <button
                  onClick={() => { setCreatedByFilter(''); setShowCreatedByFilter(false); }}
                  className={`w-full text-left px-3 py-1.5 text-xs rounded-md transition-colors ${!createdByFilter ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'}`}
                >
                  {t.allCreators}
                </button>
                {uniqueCreators.map(creator => (
                  <button
                    key={creator}
                    onClick={() => { setCreatedByFilter(creator); setShowCreatedByFilter(false); }}
                    className={`w-full text-left px-3 py-1.5 text-xs rounded-md transition-colors ${createdByFilter === creator ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'}`}
                  >
                    {creator}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Use case 过滤器 (Corti: 单 dropdown ▾) */}
      {activeTab === 'prebuilt' && (
        <div className="relative flex items-center gap-2 px-6 pb-2">
          <button
            onClick={() => setShowUseCaseFilter(v => !v)}
            className="flex items-center gap-1.5 text-sm h-8 px-3 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            <span>{t.useCaseFilter}</span>
            <span className="text-foreground font-medium">{useCase === '全部' ? t.all : useCase}</span>
            <ChevronDown size={12} />
          </button>
          {showUseCaseFilter && (
            <div className="absolute left-6 top-full mt-1 bg-popover border border-border rounded-lg shadow-lg p-1 min-w-[160px] z-10">
              {USE_CASES.map(uc => (
                <button
                  key={uc}
                  onClick={() => { setUseCase(uc); setShowUseCaseFilter(false); }}
                  className={`w-full text-left px-3 py-1.5 text-xs rounded-md transition-colors ${useCase === uc ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'}`}
                >
                  {uc === '全部' ? t.all : uc}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Agent列表 */}
      <div className="px-6 pb-6">

        {/* Tab: 我的智能体 — Runtime community agents */}
        {activeTab === 'my' && (
          myAgentsLoading ? (
            <div className="text-center py-12"><Loader2 className="animate-spin h-6 w-6 mx-auto text-muted-foreground" /></div>
          ) : filteredMyAgents.length === 0 ? (
            <div className="flex items-center justify-between px-6 py-8 rounded-xl bg-background shadow-sm ring-1 ring-border/20">
              <div>
                <p className="text-sm font-medium text-foreground">{t.noMyAgents}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{t.noMyAgentsHint}</p>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => setActiveTab('prebuilt')} className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-accent transition-colors">
                  {t.browsePrebuilt}
                </button>
                <button onClick={() => setShowNewAgentModal(true)} className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors flex items-center gap-1">
                  <Plus size={14} /> {t.newAgent}
                </button>
              </div>
            </div>
          ) : (
            filteredMyAgents.map(agent => (
              <div key={agent.agent_ref} className="flex items-center gap-4 w-full px-4 py-3 border-b border-border hover:bg-accent transition-colors group">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20 transition-colors">
                  <Bot size={16} className="text-primary" />
                </div>
                <div className="flex-1 min-w-0 cursor-pointer" onClick={() => navigate('/ai-studio/agents/' + agent.agent_ref)}>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">{agent.name}</p>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                      agent.status === 'enabled' ? 'bg-green-100 text-green-700' :
                      agent.status === 'disabled' ? 'bg-red-100 text-red-700' :
                      'bg-muted text-muted-foreground'
                    }`}>{agent.status}</span>
                    <span className="text-[10px] font-mono text-muted-foreground">v{agent.version}</span>
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{agent.description}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${
                      agent.tier >= 3 ? 'bg-red-100 text-red-700' :
                      agent.tier >= 2 ? 'bg-amber-100 text-amber-700' :
                      'bg-green-100 text-green-700'
                    }`}>T{agent.tier}</span>
                    {agent.expert_count > 0 && <span className="text-[9px] text-muted-foreground">{agent.expert_count} experts</span>}
                    {agent.tool_count > 0 && <span className="text-[9px] text-muted-foreground">{agent.tool_count} tools</span>}
                    <span className="text-[9px] text-muted-foreground">{agent.agent_type}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {agent.status === 'disabled' || agent.status === 'installed' ? (
                    <button onClick={async (e) => { e.stopPropagation(); await runtimeAgentApi.agentLifecycle(agent.agent_ref, 'enable'); loadMyAgents(); toast('已启用', 'success'); }}
                      className="px-2 py-1 rounded text-[11px] bg-green-100 text-green-700 hover:bg-green-200">启用</button>
                  ) : (
                    <button onClick={async (e) => { e.stopPropagation(); await runtimeAgentApi.agentLifecycle(agent.agent_ref, 'disable'); loadMyAgents(); toast('已禁用', 'success'); }}
                      className="px-2 py-1 rounded text-[11px] bg-amber-50 text-amber-700 hover:bg-amber-100">禁用</button>
                  )}
                  <button onClick={async (e) => { e.stopPropagation(); if (!confirm('确定要卸载吗？')) return;
                    try { await runtimeAgentApi.agentLifecycle(agent.agent_ref, 'uninstall'); loadMyAgents(); toast('已卸载', 'success'); } catch { toast('卸载失败', 'error'); }
                  }} className="px-2 py-1 rounded text-[11px] bg-red-50 text-red-600 hover:bg-red-100"><Trash2 size={11} />卸载</button>
                </div>
              </div>
            ))
          )
        )}

        {/* Tab: 预置AI智能体 — Runtime certified agents */}
        {activeTab === 'prebuilt' && (
          certifiedLoading ? (
            <div className="text-center py-12"><Loader2 className="animate-spin h-6 w-6 mx-auto text-muted-foreground" /></div>
          ) : filteredCertifiedAgents.length === 0 ? (
            <div className="text-center py-16 bg-background rounded-xl shadow-sm ring-1 ring-border/20">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-muted flex items-center justify-center">
                <Search size={32} className="text-muted-foreground" />
              </div>
              <h3 className="text-base font-semibold text-foreground mb-2">{t.noMatchingAgents}</h3>
              <p className="text-sm text-muted-foreground mb-4">{t.noMatchingAgentsHint}</p>
              <button onClick={() => { setSearchQuery(''); setUseCase('全部'); }} className="px-4 py-2 rounded-lg border border-border text-sm text-foreground hover:bg-accent transition-colors">{t.clearFilter}</button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
              {filteredCertifiedAgents.map(agent => (
              <div key={agent.agent_ref} className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-4 hover:ring-primary/30 hover:shadow-md transition-all cursor-pointer group"
                onClick={() => navigate('/ai-studio/agents/' + agent.agent_ref)}>
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20 transition-colors">
                    <Bot size={15} className="text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">{agent.name}</p>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${agent.status === 'enabled' ? 'bg-green-100 text-green-700' : 'bg-muted text-muted-foreground'}`}>{agent.status}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed line-clamp-2">{agent.description}</p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{agent.category}</span>
                      <span className={`text-[9px] px-1 py-0.5 rounded-full font-medium ${agent.tier >= 3 ? 'bg-red-100 text-red-700' : agent.tier >= 2 ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'}`}>T{agent.tier}</span>
                      <span className="text-[10px] font-mono text-muted-foreground">v{agent.version}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      {agent.expert_count > 0 && <span className="text-[9px] text-muted-foreground">{agent.expert_count} experts</span>}
                      {agent.tool_count > 0 && <span className="text-[9px] text-muted-foreground">{agent.tool_count} tools</span>}
                    </div>
                  </div>
                </div>
              </div>
              ))}
            </div>
          )
        )}

      </div>

      {/* New Agent Creation Panel (slide-over, iCoDer-style) */}
      {showNewAgentModal && (
        <div className="fixed inset-0 z-50 flex" onClick={() => setShowNewAgentModal(false)}>
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/40" />
          {/* Slide-over panel */}
          <div
            className="relative ml-auto w-full max-w-lg bg-background border-l border-border shadow-2xl flex flex-col h-full animate-slide-in"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
              <div>
                <h2 className="text-base font-semibold text-foreground">{t.newAgent}</h2>
                <p className="text-xs text-muted-foreground mt-0.5">{t.newAgentModalDesc}</p>
              </div>
              <button onClick={() => setShowNewAgentModal(false)} className="p-1.5 rounded-lg hover:bg-accent transition-colors">
                <X size={16} className="text-muted-foreground" />
              </button>
            </div>

            {/* Form body */}
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
              <div>
                <label className="text-xs font-semibold text-foreground block mb-2">选择模板</label>
                <div className="relative mb-2">
                  <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input value={templateSearch} onChange={e => setTemplateSearch(e.target.value)}
                    placeholder="搜索模板..."
                    className="w-full pl-6 pr-2 py-1.5 text-xs bg-transparent border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-ring" />
                </div>
                <div className="max-h-56 overflow-y-auto space-y-1">
                  {agentTemplates.length > 0
                    ? agentTemplates.filter((t: any) => !templateSearch || (t.title||t.name||'').toLowerCase().includes(templateSearch.toLowerCase())).map((tpl: any) => (
                      <label key={tpl.id} className={'flex items-start gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors ' + (selectedTemplate === tpl.id ? 'bg-primary/10 border border-primary/20' : 'hover:bg-accent border border-transparent')}>
                        <input type="radio" name="agent-template" className="mt-0.5 accent-primary shrink-0"
                          checked={selectedTemplate === tpl.id}
                          onChange={() => { setSelectedTemplate(tpl.id); setNewAgentName(tpl.title||tpl.name||''); setNewAgentDesc(tpl.description||''); setNewAgentCategory((tpl as any).category||'编码'); generatePromptForTemplate(tpl.title||tpl.name||'', tpl.description||'', (tpl as any).category||'编码'); }} />
                        <div className="min-w-0"><p className="text-xs font-medium text-foreground">{tpl.title||tpl.name}</p><p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">{tpl.description}</p></div>
                      </label>
                    ))
                    : (dbAgents.filter(a => a.is_prebuilt).slice(0, 8)||[]).map((a: any) => (
                      <label key={a.id||a.key} className={'flex items-start gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors ' + (selectedTemplate===(a.id||a.key) ? 'bg-primary/10 border border-primary/20' : 'hover:bg-accent border border-transparent')}>
                        <input type="radio" name="agent-template" className="mt-0.5 accent-primary shrink-0"
                          checked={selectedTemplate===(a.id||a.key)}
                          onChange={() => { setSelectedTemplate(a.id||a.key); setNewAgentName(a.name||''); setNewAgentDesc(a.desc||a.description||''); setNewAgentCategory(a.category||'编码'); generatePromptForTemplate(a.name||'', a.desc||a.description||'', a.category||'编码'); }} />
                        <div className="min-w-0"><p className="text-xs font-medium text-foreground">{a.name}</p><p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">{a.desc||a.description||''}</p></div>
                      </label>
                    ))
                  }
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1.5">Agent 名称 <span className="text-muted-foreground">*</span></label>
                <input value={newAgentName} onChange={e => setNewAgentName(e.target.value)} placeholder="例如：我的合规审核助手"
                  className="w-full text-sm border border-border rounded-lg px-3 py-2.5 bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50" autoFocus />
              </div>
              <div className="border border-border rounded-lg overflow-hidden">
                <button onClick={() => setShowTemplatePicker(!showTemplatePicker)} className="w-full flex items-center justify-between px-3 py-2 hover:bg-accent/30 transition-colors text-left">
                  <span className="text-xs font-medium text-muted-foreground">高级设置</span>
                  <ChevronRight size={14} className={'text-muted-foreground transition-transform ' + (showTemplatePicker ? 'rotate-90' : '')} />
                </button>
                {showTemplatePicker && (
                  <div className="border-t border-border px-3 py-3 bg-muted/20 space-y-3">
                    <div><label className="text-[10px] font-semibold text-foreground block mb-1">描述</label><input value={newAgentDesc} onChange={e => setNewAgentDesc(e.target.value)} placeholder="Agent 的功能描述" className="w-full text-xs border border-border rounded-lg px-2 py-1.5 bg-transparent" /></div>
                    <div><label className="text-[10px] font-semibold text-foreground block mb-1">分类</label><div className="flex flex-wrap gap-1">{USE_CASES.filter(c => c !== '全部').map(c => (<button key={c} onClick={() => setNewAgentCategory(c)} className={'text-[10px] px-2 py-1 rounded-full border transition-colors ' + (newAgentCategory===c ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground hover:bg-accent')}>{c}</button>))}</div></div>
                    <div><label className="text-[10px] font-semibold text-foreground block mb-1">系统提示词</label><div className="border border-border rounded-lg overflow-hidden"><div className="bg-muted/50 px-2 py-1 border-b border-border flex items-center justify-between"><span className="text-[10px] font-mono text-muted-foreground">&lt;role&gt;</span><button onClick={generatePrompt} disabled={!newAgentName.trim()||generatingPrompt} className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border border-border/50 hover:bg-accent disabled:opacity-40">{generatingPrompt ? <><Loader2 size={10} className="animate-spin" /></> : <><Sparkles size={10} /> AI 生成</>}</button></div><textarea value={newAgentPrompt} onChange={e => setNewAgentPrompt(e.target.value)} placeholder="系统提示词..." rows={4} className="w-full text-xs bg-transparent px-2 py-1.5 resize-none focus:outline-none leading-relaxed" /></div></div>
                  </div>
                )}
              </div>
            </div>
{/* Footer */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-muted/30 shrink-0">
              <button
                onClick={() => { setShowNewAgentModal(false); setNewAgentExperts([]); }}
                className="text-sm px-4 py-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              >
                {t.cancel}
              </button>
              <button
                onClick={handleCreateAgent}
                disabled={!newAgentName.trim() || creatingAgent}
                className="text-sm px-6 py-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-all flex items-center gap-1.5 font-medium"
              >
                {creatingAgent ? (
                  <><Loader2 size={14} className="animate-spin" /> {t.creatingAgent}</>
                ) : (
                  <>{t.createAgent}</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirmAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => setDeleteConfirmAgent(null)}>
          <div className="absolute inset-0 bg-black/40" />
          <div className="relative bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-6 max-w-sm w-full mx-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-foreground mb-1">{t.confirmDelete}</h3>
            <p className="text-xs text-muted-foreground mb-4">{t.deleteIrreversible}</p>
            <p className="text-sm text-foreground mb-6">
              {t.confirmDeleteAgent.replace('{name}', deleteConfirmAgent.name)}
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setDeleteConfirmAgent(null)}
                className="text-sm px-4 py-2 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              >
                {t.cancel}
              </button>
              <button
                onClick={async () => {
                  try {
                    await agentsApi.delete(deleteConfirmAgent.id || deleteConfirmAgent.key);
                    setDbAgents(prev => prev.filter(a => (a.id || a.key) !== (deleteConfirmAgent.id || deleteConfirmAgent.key)));
                    loadMyAgents();
                    setDeleteConfirmAgent(null);
                  } catch { /* silently fail */ }
                }}
                className="text-sm px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                {t.confirmDeleteBtn}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
          </div>
        </div>
  );
}

// Inline expert picker for Agent creation panel
function CreateExpertPicker({ selectedIds, onAdd, onRemove }: {
  selectedIds: string[];
  onAdd: (expert: any) => void;
  onRemove: (id: string) => void;
}) {
  const t = useT();
  const [experts, setExperts] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!loaded) {
      setLoading(true);
      // experts endpoint deleted in Phase 2.1-B Step 1; expert picker is now empty
      setExperts([]);
      setLoaded(true);
      setLoading(false);
    }
  }, [loaded]);

  const filtered = experts.filter(e => {
    if (search && !e.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-muted/30 border-b border-border">
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t.searchExperts}
            className="pl-6 pr-2 py-1 text-xs bg-transparent w-full focus:outline-none"
          />
        </div>
      </div>
      <div className="max-h-48 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 size={14} className="animate-spin text-muted-foreground" />
          </div>
        ) : filtered.length === 0 ? (
          <p className="text-[10px] text-muted-foreground text-center py-4">{t.noMatchingExperts}</p>
        ) : (
          filtered.map(expert => {
            const isSelected = selectedIds.includes(expert.id);
            return (
              <div
                key={expert.id}
                className={`flex items-center gap-2 px-3 py-2 text-xs border-b border-border/30 last:border-0 transition-colors ${
                  isSelected ? 'bg-primary/5' : 'hover:bg-accent/50'
                }`}
              >
                <span className="flex-1 truncate">{expert.name}</span>
                <span className="text-[9px] text-muted-foreground">{expert.category}</span>
                <button
                  onClick={() => isSelected ? onRemove(expert.id) : onAdd({ id: expert.id, name: expert.name, icon: expert.icon })}
                  className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] transition-colors ${
                    isSelected
                      ? 'bg-primary text-primary-foreground'
                      : 'border border-border text-muted-foreground hover:border-primary hover:text-primary'
                  }`}
                >
                  {isSelected ? <Check size={10} /> : <Plus size={10} />}
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

