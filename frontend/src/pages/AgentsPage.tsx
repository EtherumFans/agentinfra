// iCoDer Agents — iCoDer Console 1:1 with My Agents / Prebuilt tabs + Agent detail chat
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useT, useLocaleStore } from '../i18n';
import {
  Bot, Search, BookOpen, Plus, Clock, User, ChevronRight,
  ChevronDown, Loader2, X, Sparkles,
  Copy, Check, Wrench, Trash2, Send,
} from 'lucide-react';
import { billingApi, expertsApi, agentsApi, oauthApi } from '../services/api';

// Fallback prebuilt agents — used only when API is unavailable
const PREBUILT_AGENTS: { key: string; name: string; desc: string; useCase: string }[] = [
  { key: 'icd10-navigator', name: 'ICD-10 索引导航', desc: '从临床术语遍历ICD-10字母索引，为编码员审核提供候选编码', useCase: '编码' },
  { key: 'rule-explainer', name: '规则解释', desc: '解释特定ICD-10-CN、ICD-9-CM-3或医保编码被选中的原因及编码规则依据', useCase: '编码' },
  { key: 'compliance-guardrail', name: '合规护栏', desc: '在提交医保结算清单前，按配置的医保或医院规则集评估编码集的合规性', useCase: '医保' },
  { key: 'code-validation', name: '编码校验', desc: '按官方编码规则验证编码集，发现错误、冲突和合规风险', useCase: '编码' },
  { key: 'procedure-extractor', name: '手术提取', desc: '从手术记录中提取手术操作并分配ICD-9-CM-3编码', useCase: '编码' },
  { key: 'diagnosis-extractor', name: '诊断提取', desc: '从病历中提取诊断并分配ICD-10-CN编码', useCase: '编码' },
  { key: 'surgical-registry', name: '外科质控登记', desc: '从手术记录/日志自动提取数据填入外科质量登记数据库', useCase: '质控' },
  { key: 'icu-summary', name: 'ICU入院摘要', desc: '综合EHR数据自动生成ICU入院结构化临床摘要', useCase: '文书' },
  { key: 'triage', name: '急诊分诊', desc: '使用验证过的风险评分和循证紧急度分级，辅助急诊分诊决策', useCase: '急诊' },
  { key: 'note-completeness', name: '病历完整性', desc: '实时检查病历完整性、准确性和合规性', useCase: '质控' },
  { key: 'med-reconciliation', name: '用药重整', desc: '入院/转科/出院环节提供准确的用药重整', useCase: '药学' },
  { key: 'denial-appeals', name: '拒付申诉', desc: '生成有循证依据的申诉回复', useCase: '医保' },
  { key: 'discharge-edu', name: '出院宣教', desc: '生成个性化的清晰出院指导', useCase: '护理' },
  { key: 'nursing-handoff', name: '护理交班', desc: '结构化护理交班报告', useCase: '护理' },
  { key: 'prior-auth', name: '预授权', desc: '自动生成符合指南的预授权文件', useCase: '医保' },
  { key: 'referral-gen', name: '转诊生成', desc: '生成结构化转诊信', useCase: '文书' },
  { key: 'clinical-edu', name: '临床教育', desc: '为医护人员提供循证医学教育支持', useCase: '教育' },
  { key: 'clinical-guidelines', name: '临床指南', desc: '检索最新临床指南和诊疗路径', useCase: '教育' },
  { key: 'cdi', name: '临床文书改进', desc: '审查临床文书质量，识别缺口', useCase: '质控' },
  { key: 'medical-coding', name: '医学编码', desc: '将临床文本转化为ICD-10-CN/ICD-9-CM-3编码', useCase: '编码' },
];

const USE_CASE_KEYS = ['全部', '编码', '医保', '质控', '文书', '急诊', '护理', '药学'];
const USE_CASES = USE_CASE_KEYS;

// Agent key → Expert name mapping moved to AgentDetailPage

// Agent expert configuration moved to AgentDetailPage

type TabType = 'my' | 'prebuilt' | 'marketplace';

export default function AgentsPage() {
  const t = useT();
  const locale = useLocaleStore((s) => s.locale);
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabType>('my');
  const [searchQuery, setSearchQuery] = useState('');
  const [useCase, setUseCase] = useState('全部');
  const [balance, setBalance] = useState<number | null>(null);
  const [cost, setCost] = useState('0.000000');
  const [createdByFilter, setCreatedByFilter] = useState('');
  const [showCreatedByFilter, setShowCreatedByFilter] = useState(false);

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
  // Agents from API (backend Agent entities)
  const [apiAgents, setApiAgents] = useState<any[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
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

  useEffect(() => {
    billingApi.balance().then(r => setBalance(r.data.balance)).catch(() => {});
    // Fetch ALL experts and build name→id lookup for agent routing
    expertsApi.list('', '', 'all').then(r => {
      const experts = r.data?.experts || [];
      const nameMap: Record<string, string> = {};
      for (const e of experts) nameMap[e.name] = e.id;
      setExpertNameToId(nameMap);
    }).catch(() => {});
    // Fetch agents from backend API
    agentsApi.list('', '', 'all').then(r => {
      setApiAgents(r.data?.agents || []);
    }).catch(() => {
      // Fallback: use static data if API unavailable (backward compat)
      setApiAgents([]);
    }).finally(() => setAgentsLoading(false));
    // Fetch OAuth clients for API Client selector
    oauthApi.list().then(r => {
      const clients = r.data?.clients || [];
      setApiClients(clients);
      if (clients.length > 0) setSelectedApiClient(clients[0].client_id);
    }).catch(() => {});
    // Fetch agent templates
    agentsApi.templates().then(r => {
      setAgentTemplates(r.data?.templates || []);
    }).catch(() => {});
  }, []);

  // Load memory context when entering agent detail chat — moved to AgentDetailPage

  // Unique creators for filter dropdown (computed from base agents for the active tab)
  const uniqueCreators = [...new Set(
    (activeTab === 'my'
      ? apiAgents.filter((a: any) => !a.is_prebuilt)
      : []
    ).map((a: any) => a.createdBy || a.created_by || '').filter(Boolean)
  )];

  // 筛选Agent — 优先使用 API 数据，fallback 到静态数组
  const filteredAgents = (() => {
    const baseAgents = activeTab === 'my'
      ? (apiAgents.length > 0 ? apiAgents.filter(a => !a.is_prebuilt) : [])
      : (apiAgents.length > 0 ? apiAgents.filter(a => a.is_prebuilt) : PREBUILT_AGENTS);
    return baseAgents.filter(a => {
      const matchSearch = !searchQuery || a.name.includes(searchQuery) || (a.desc || a.description || '').includes(searchQuery);
      const matchUseCase = useCase === '全部' || (a as any).useCase === useCase || (a as any).category === useCase;
      const matchCreator = !createdByFilter || (a.createdBy || a.created_by || '') === createdByFilter;
      return matchSearch && matchUseCase && matchCreator;
    });
  })();

  // Marketplace agents
  const [marketAgents, setMarketAgents] = useState<any[]>([]);
  const [marketLoading, setMarketLoading] = useState(false);
  const [marketCategory, setMarketCategory] = useState('');
  const [marketSearch, setMarketSearch] = useState('');
  const [publishEnv, setPublishEnv] = useState('prod');
  const loadMarketplace = () => {
    setMarketLoading(true);
    agentsApi.marketplace(marketCategory, marketSearch).then(r => setMarketAgents(r.data.agents || [])).catch(() => {}).finally(() => setMarketLoading(false));
  };
  useEffect(() => { if (activeTab === 'marketplace') loadMarketplace(); }, [activeTab, marketCategory, marketSearch]);

  // Publish / Version handlers
  const handlePublish = async (agentId: string, env = 'prod') => {
    await agentsApi.publish(agentId, env);
    agentsApi.list().then(r => setApiAgents(r.data.agents || [])).catch(() => {});
  };
  const handleUnpublish = async (agentId: string) => {
    await agentsApi.unpublish(agentId);
    agentsApi.list().then(r => setApiAgents(r.data.agents || [])).catch(() => {});
  };
  const handleBumpVersion = async (agentId: string) => {
    await agentsApi.version(agentId);
    agentsApi.list().then(r => setApiAgents(r.data.agents || [])).catch(() => {});
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

  // Clone from existing agent
  const cloneAgent = (agent: any) => {
    setNewAgentName(agent.name + ' (副本)');
    setNewAgentDesc(agent.desc || agent.description || '');
    setNewAgentPrompt(agent.system_prompt || '');
    setNewAgentCategory(agent.useCase || agent.category || '编码');
    if (agent.expert_ids?.length) {
      // Resolve expert names from IDs for display
      const bound: any[] = [];
      for (const eid of agent.expert_ids) {
        const name = Object.entries(expertNameToId).find(([, id]) => id === eid)?.[0] || eid;
        bound.push({ id: eid, name, icon: 'Bot' });
      }
      setNewAgentExperts(bound);
    }
    setShowClonePicker(false);
  };

  // AI-assisted system prompt generation
  const generatePrompt = async () => {
    if (!newAgentName.trim() || generatingPrompt) return;
    setGeneratingPrompt(true);
    try {
      const token = localStorage.getItem('access_token') || '';
      if (!token) { console.warn('No auth token for prompt generation'); setGeneratingPrompt(false); return; }
      const resp = await fetch('/api/text-gen/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          template: 'system_prompt',
          language: 'zh-CN',
          context: {
            agent_name: newAgentName.trim(),
            description: newAgentDesc.trim(),
            category: newAgentCategory,
          },
        }),
      });
      if (!resp.ok) {
        console.error('Prompt generation failed:', resp.status, await resp.text());
      } else {
        const data = await resp.json();
        if (data.output) setNewAgentPrompt(data.output);
      }
    } catch (e) { console.error('Prompt generation error:', e); }
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
      const r = await agentsApi.list('', '', 'all');
      setApiAgents(r.data?.agents || []);
      setActiveTab('my');
      // Navigate to the newly created agent
      const created = r.data?.agents?.find((a: any) => a.id === res.data?.id);
      if (created) navigate('/ai-studio/agents/' + created.id);
    } catch { /* silently fail */ }
    setCreatingAgent(false);
  };

  // Agent列表视图
  return (
    <div className="flex-1 flex flex-col min-h-0 bg-muted/20">
      <div className="flex-1 p-6 overflow-y-auto">
        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20">
          {/* Section header with accent bar */}
          <div className="flex items-center gap-3 px-6 pt-5 pb-3 border-b border-border/40">
            <div className="w-1 h-4 rounded-full bg-primary/40" />
            <h2 className="text-lg font-semibold text-foreground">{t.agents}</h2>
            <div className="flex-1" />
            <button
              onClick={() => setShowNewAgentModal(true)}
              className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1"
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
            { id: 'marketplace' as TabType, label: 'Agent 市场' },
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

      {/* Use Case 筛选标签行 */}
      {activeTab === 'prebuilt' && (
        <div className="flex items-center gap-1.5 px-6 pb-2 flex-wrap">
          {USE_CASES.map(uc => (
            <button
              key={uc}
              onClick={() => setUseCase(uc)}
              className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                useCase === uc
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border text-muted-foreground hover:bg-accent'
              }`}
            >
              {uc === '全部' ? t.all : uc}
            </button>
          ))}
        </div>
      )}

      {/* Agent列表 */}
      <div className="px-6 pb-6">
        {activeTab === 'my' ? (
          // My Agents
          filteredAgents.length === 0 ? (
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
            filteredAgents.map(agent => {
              const d = agentDisplay(agent);
              return (
              <div
                key={d.key}
                className="flex items-center gap-4 w-full px-4 py-3 border-b border-border hover:bg-accent transition-colors group cursor-pointer"
                onClick={() => navigate('/ai-studio/agents/' + (agent.id || agent.key))}
              >
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20 transition-colors">
                  <Bot size={16} className="text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground">{d.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{d.desc}</p>
                </div>
                <div className="text-xs text-muted-foreground text-right shrink-0">
                  {agent.version && <div className="text-[10px] font-mono">v{agent.version}</div>}
                  {agent.status && (
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${agent.status === 'prod' ? 'bg-secondary/10 text-secondary' : agent.status === 'staging' ? 'bg-yellow-100 text-yellow-700' : agent.status === 'dev' ? 'bg-blue-100 text-blue-700' : 'bg-muted text-muted-foreground'}`}>
                      {agent.status === 'prod' ? 'prod' : agent.status === 'staging' ? 'staging' : agent.status === 'dev' ? 'dev' : '草稿'}
                    </span>
                  )}
                  {d.createdAt && <div className="flex items-center gap-1 justify-end"><Clock size={10} /> {d.createdAt}</div>}
                  {d.createdBy && <div className="flex items-center gap-1 justify-end mt-0.5"><User size={10} /> {d.createdBy}</div>}
                </div>
                <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-all">
                  {!agent.is_prebuilt && agent.status === 'draft' && (
                    <>
                      <select onClick={(e) => e.stopPropagation()} onChange={(e) => setPublishEnv(e.target.value)} value={publishEnv} className="text-[9px] border border-border rounded px-1 py-0.5 bg-card" title="发布环境">
                        <option value="dev">dev</option><option value="staging">staging</option><option value="prod">prod</option>
                      </select>
                      <button onClick={(e) => { e.stopPropagation(); handlePublish(agent.id, publishEnv); }} className="p-1 rounded text-secondary hover:bg-secondary/10" title="发布"><Send size={12} /></button>
                    </>
                  )}
                  {!agent.is_prebuilt && agent.status !== 'draft' && agent.status !== '' && (
                    <button onClick={(e) => { e.stopPropagation(); handleUnpublish(agent.id); }} className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent" title="撤回">{agent.status === 'prod' ? '🔴' : agent.status === 'staging' ? '🟡' : '🔵'}</button>
                  )}
                  {!agent.is_prebuilt && (
                    <button onClick={(e) => { e.stopPropagation(); handleBumpVersion(agent.id); }} className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent" title="版本+1"><Plus size={12} /></button>
                  )}
                  <button onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(window.location.origin + '/ai-studio/agents/' + agent.id); }} className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent" title="复制分享链接">📋</button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleteConfirmAgent(agent); }}
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent"
                    title="删除"
                  ><Trash2 size={14} /></button>
                </div>
              </div>
            )})
          )
        ) : (
          // Prebuilt Agents — 网格布局
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
            {filteredAgents.map(agent => {
              const d = agentDisplay(agent);
              return (
              <div
                key={d.key}
                className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-4 hover:ring-primary/30 hover:shadow-md transition-all cursor-pointer group"
                onClick={() => navigate('/ai-studio/agents/' + (agent.id || agent.key))}
              >
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20 transition-colors">
                    <Bot size={15} className="text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
                      {d.name}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed line-clamp-2">
                      {d.desc}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                        {d.useCase}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )})}
          </div>
        )}

        {activeTab === 'prebuilt' && filteredAgents.length === 0 && (
          <div className="text-center py-16 bg-background rounded-xl shadow-sm ring-1 ring-border/20">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-muted flex items-center justify-center">
              <Search size={32} className="text-muted-foreground" />
            </div>
            <h3 className="text-base font-semibold text-foreground mb-2">{t.noMatchingAgents}</h3>
            <p className="text-sm text-muted-foreground mb-4">{t.noMatchingAgentsHint}</p>
            <button onClick={() => { setSearchQuery(''); setUseCase('全部'); }} className="px-4 py-2 rounded-lg border border-border text-sm text-foreground hover:bg-accent transition-colors">{t.clearFilter}</button>
          </div>
        )}

        {activeTab === 'marketplace' && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input value={marketSearch} onChange={e => setMarketSearch(e.target.value)} placeholder="搜索 Agent..." className="w-full pl-9 pr-3 py-2 text-sm border border-border rounded-lg bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring" />
              </div>
              <select value={marketCategory} onChange={e => setMarketCategory(e.target.value)} className="text-xs border border-border rounded-lg px-2 py-2 bg-card text-foreground">
                <option value="">全部分类</option>
                <option value="coding">编码</option><option value="insurance">医保</option><option value="quality">质控</option>
                <option value="documentation">文书</option><option value="emergency">急诊</option><option value="nursing">护理</option>
                <option value="pharmacy">药学</option><option value="education">教育</option>
              </select>
            </div>
            {marketLoading ? (
              <div className="text-center py-12"><Loader2 className="animate-spin h-6 w-6 mx-auto text-muted-foreground" /></div>
            ) : marketAgents.length === 0 ? (
              <div className="text-center py-16 bg-background rounded-xl shadow-sm ring-1 ring-border/20">
                <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-muted flex items-center justify-center">
                  <Search size={32} className="text-muted-foreground" />
                </div>
                <h3 className="text-base font-semibold text-foreground mb-2">暂无已发布的 Agent</h3>
                <p className="text-sm text-muted-foreground mb-4">发布你的 Agent 后，它将出现在市场中供其他用户发现和使用</p>
                <button onClick={() => setActiveTab('my')} className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90">去发布我的 Agent</button>
              </div>
            ) : (
              <div className="space-y-1">
                {marketAgents.map((agent: any) => {
                  const d = agentDisplay(agent);
                  return (
                    <div key={agent.id} className="flex items-center gap-4 w-full px-4 py-3 border-b border-border hover:bg-accent transition-colors cursor-pointer rounded-lg bg-card" onClick={() => navigate('/ai-studio/agents/' + agent.id)}>
                      <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                        <Bot size={16} className="text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{d.name}</p>
                          <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${agent.status === 'prod' ? 'bg-secondary/10 text-secondary' : agent.status === 'staging' ? 'bg-yellow-100 text-yellow-700' : 'bg-blue-100 text-blue-700'}`}>
                            {agent.status === 'prod' ? 'prod' : agent.status === 'staging' ? 'staging' : agent.status === 'dev' ? 'dev' : '已发布'}
                          </span>
                          <span className="text-[10px] font-mono text-muted-foreground">v{agent.version || '1.0.0'}</span>
                        </div>
                        <p className="text-xs text-muted-foreground truncate">{d.desc}</p>
                      </div>
                      <div className="text-xs text-muted-foreground text-right shrink-0">
                        <div className="flex items-center gap-1 justify-end"><User size={10} /> {d.createdBy || 'admin'}</div>
                        <div className="flex items-center gap-1 justify-end mt-0.5">
                          <span>📊 {(agent.usage_count || 0)}次使用</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
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
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
              {/* Clone from existing */}
              <div className="border border-border rounded-lg overflow-hidden">
                <button
                  onClick={() => setShowClonePicker(!showClonePicker)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-accent/30 transition-colors text-left"
                >
                  <div className="flex items-center gap-2">
                    <Copy size={14} className="text-muted-foreground" />
                    <span className="text-sm font-medium text-foreground">{t.cloneFromExisting}</span>
                  </div>
                  <ChevronRight size={14} className={`text-muted-foreground transition-transform ${showClonePicker ? 'rotate-90' : ''}`} />
                </button>
                {showClonePicker && (
                  <div className="border-t border-border px-4 py-3 bg-muted/30 max-h-56 overflow-y-auto space-y-2">
                    <p className="text-[10px] text-muted-foreground">{t.cloneHint}</p>
                    <div className="grid gap-1.5">
                      {apiAgents.filter(a => a.is_prebuilt).slice(0, 8).map(agent => (
                        <button
                          key={agent.id}
                          onClick={() => cloneAgent(agent)}
                          className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-accent transition-colors text-left group"
                        >
                          <div className="w-7 h-7 rounded-md bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20 transition-colors">
                            <Bot size={13} className="text-primary" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-medium text-foreground truncate">{agent.name}</p>
                            <p className="text-[10px] text-muted-foreground truncate">{agent.category}</p>
                          </div>
                          <span className="text-[10px] text-primary opacity-0 group-hover:opacity-100 transition-opacity shrink-0">{t.cloneAction}</span>
                        </button>
                      ))}
                      {(!apiAgents || apiAgents.filter(a => a.is_prebuilt).length === 0) && (
                        <p className="text-[10px] text-muted-foreground text-center py-2">{t.noTemplatesAvailable}</p>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Use a template */}
              <div className="border border-border rounded-lg overflow-hidden">
                <button
                  onClick={() => setShowTemplatePicker(!showTemplatePicker)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-accent/30 transition-colors text-left"
                >
                  <div className="flex items-center gap-2">
                    <BookOpen size={14} className="text-muted-foreground" />
                    <span className="text-sm font-medium text-foreground">{t.useTemplate}</span>
                  </div>
                  <ChevronRight size={14} className={`text-muted-foreground transition-transform ${showTemplatePicker ? 'rotate-90' : ''}`} />
                </button>
                {showTemplatePicker && (
                  <div className="border-t border-border px-4 py-3 bg-muted/30 max-h-72 overflow-y-auto space-y-1.5">
                    <p className="text-[10px] text-muted-foreground mb-2">{t.useTemplateHint}</p>
                    {/* Template search */}
                    <div className="relative mb-2">
                      <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                      <input
                        value={templateSearch}
                        onChange={e => setTemplateSearch(e.target.value)}
                        placeholder={t.searchTemplates}
                        className="w-full pl-6 pr-2 py-1 text-xs bg-transparent border border-border rounded focus:outline-none focus:ring-1 focus:ring-ring"
                      />
                    </div>
                    {(agentTemplates.length === 0 && !templateSearch) ? (
                      <p className="text-[10px] text-muted-foreground text-center py-2">{t.loadingTemplates}</p>
                    ) : (
                      agentTemplates
                        .filter((tpl: any) => {
                          if (!templateSearch) return true;
                          const q = templateSearch.toLowerCase();
                          return (tpl.title || tpl.name || '').toLowerCase().includes(q);
                        })
                        .map((tpl: any) => (
                        <label
                          key={tpl.id}
                          className={`flex items-start gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                            selectedTemplate === tpl.id
                              ? 'bg-primary/10 border border-primary/20'
                              : 'hover:bg-accent border border-transparent'
                          }`}
                        >
                          <input
                            type="radio"
                            name="agent-template"
                            className="mt-0.5 accent-primary shrink-0"
                            checked={selectedTemplate === tpl.id}
                            onChange={() => {
                              if (selectedTemplate === tpl.id) {
                                setSelectedTemplate('');
                              } else {
                                setSelectedTemplate(tpl.id);
                                setNewAgentName(tpl.title || '');
                                setNewAgentDesc(tpl.description || '');
                                setNewAgentPrompt(tpl.system_prompt || '');
                              }
                            }}
                          />
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-medium text-foreground">{tpl.title}</p>
                            <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">{tpl.description}</p>
                          </div>
                        </label>
                      ))
                    )}
                  </div>
                )}
              </div>

              {/* Name */}
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1.5">{t.name} <span className="text-muted-foreground">*</span></label>
                <input
                  value={newAgentName}
                  onChange={e => setNewAgentName(e.target.value)}
                  placeholder={t.agentNamePlaceholder}
                  className="w-full text-sm border border-border rounded-lg px-3 py-2.5 bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
                  autoFocus
                />
              </div>

              {/* Description */}
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1.5">{t.description}</label>
                <input
                  value={newAgentDesc}
                  onChange={e => setNewAgentDesc(e.target.value)}
                  placeholder={t.agentDescPlaceholder}
                  className="w-full text-sm border border-border rounded-lg px-3 py-2.5 bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
                />
              </div>

              {/* Category */}
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1.5">{t.category}</label>
                <div className="flex flex-wrap gap-1.5">
                  {USE_CASES.filter(c => c !== '全部').map(c => (
                    <button
                      key={c}
                      onClick={() => setNewAgentCategory(c)}
                      className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                        newAgentCategory === c
                          ? 'bg-primary text-primary-foreground border-primary'
                          : 'border-border text-muted-foreground hover:bg-accent'
                      }`}
                    >
                      {c}
                    </button>
                  ))}
                </div>
              </div>

              {/* System Prompt */}
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1.5">
                  {t.systemPrompt}
                  <span className="text-muted-foreground font-normal ml-1">{t.optional}</span>
                </label>
                <div className="border border-border rounded-lg overflow-hidden">
                  <div className="bg-muted/50 px-3 py-1.5 border-b border-border flex items-center justify-between">
                    <span className="text-[10px] font-mono text-muted-foreground">&lt;role&gt;</span>
                    <button
                      onClick={generatePrompt}
                      disabled={!newAgentName.trim() || generatingPrompt}
                      className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded border border-border/50 hover:bg-accent hover:border-border disabled:opacity-40 transition-all text-muted-foreground hover:text-foreground"
                      title="AI 辅助生成系统提示词"
                    >
                      {generatingPrompt ? (
                        <><Loader2 size={10} className="animate-spin" /> {t.generating}</>
                      ) : (
                        <><Sparkles size={10} /> {t.aiGenerate}</>
                      )}
                    </button>
                  </div>
                  <textarea
                    value={newAgentPrompt}
                    onChange={e => setNewAgentPrompt(e.target.value)}
                    placeholder={t.systemPromptPlaceholder}
                    rows={6}
                    className="w-full text-xs bg-transparent px-3 py-2.5 text-foreground placeholder:text-muted-foreground resize-none focus:outline-none leading-relaxed"
                  />
                </div>
              </div>

              {/* Expert binding */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold text-foreground">{t.bindExperts}</label>
                  <span className="text-[10px] text-muted-foreground">{t.selectedCount.replace('{count}', String(newAgentExperts.length))}</span>
                </div>
                {/* Selected experts */}
                {newAgentExperts.length > 0 && (
                  <div className="space-y-1 mb-3">
                    {newAgentExperts.map(expert => (
                      <div key={expert.id} className="flex items-center gap-2 py-1.5 px-2.5 rounded-lg bg-accent/30 text-xs">
                        <Wrench size={12} className="text-muted-foreground shrink-0" />
                        <span className="flex-1 truncate">{expert.name}</span>
                        <button
                          onClick={() => setNewAgentExperts(prev => prev.filter(e => e.id !== expert.id))}
                          className="p-0.5 rounded hover:bg-accent text-muted-foreground hover:text-foreground"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {/* Inline expert picker */}
                <CreateExpertPicker
                  selectedIds={newAgentExperts.map(e => e.id)}
                  onAdd={(expert: any) => setNewAgentExperts(prev => [...prev, expert])}
                  onRemove={(id: string) => setNewAgentExperts(prev => prev.filter(e => e.id !== id))}
                />
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
                    setApiAgents(prev => prev.filter(a => (a.id || a.key) !== (deleteConfirmAgent.id || deleteConfirmAgent.key)));
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
      expertsApi.list('', '', 'all').then(r => {
        setExperts(r.data?.experts || []);
        setLoaded(true);
      }).catch(() => {}).finally(() => setLoading(false));
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

