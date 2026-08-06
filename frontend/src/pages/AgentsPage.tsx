// iCoDer Agents - iCoDer Console 1:1 with My Agents / Prebuilt tabs + Agent detail chat
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bot, Search, Plus, User,
  ChevronDown, Loader2,
  Wrench, Trash2, Send,
  Layers,
} from 'lucide-react';

import { useT, useLocaleStore } from '../i18n';
import { billingApi, agentsApi, oauthApi } from '../services/api';
import { runtimeAgentApi } from '../services/runtimeApi';
import { agentHubApi, type HubCard } from '../services/agentHubApi';
import { useToastStore } from '../store';
import type { InstalledAgent } from '../types/runtime';

// Phase 3-B2 Loop 4 - use_case filter dropdown (backend-driven).
// Maps 5 use_case enum values to display labels (now i18n'd - Phase 3-E+).
// The Hub endpoint filters server-side via ?use_case=<key>. Empty key = no filter.
const USE_CASE_FILTER_KEYS: Array<{ key: string; labelKey: 'useCaseCodingRevenueCycle' | 'useCaseClinicalEvidenceResearch' | 'useCasePointOfCare' | 'useCaseCareCoordination' | 'useCaseChinaMedicalCompliance' }> = [
  { key: 'coding_revenue_cycle', labelKey: 'useCaseCodingRevenueCycle' },
  { key: 'clinical_evidence_research', labelKey: 'useCaseClinicalEvidenceResearch' },
  { key: 'point_of_care', labelKey: 'useCasePointOfCare' },
  { key: 'care_coordination', labelKey: 'useCaseCareCoordination' },
  { key: 'china_medical_compliance', labelKey: 'useCaseChinaMedicalCompliance' },
];

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
  // Phase 3-B2 Loop 4: useCase now stores the use_case key (e.g.
  // 'coding_revenue_cycle'), not a Chinese label. Empty string = no filter.
  const [useCase, setUseCase] = useState('');
  const [balance, setBalance] = useState<number | null>(null);
  const [cost, setCost] = useState('0.000000');
  const [createdByFilter, setCreatedByFilter] = useState('');
  const [showCreatedByFilter, setShowCreatedByFilter] = useState(false);
  const [showUseCaseFilter, setShowUseCaseFilter] = useState(false);

  // Expert name → ID lookup (for clone/creation flow)
  const [expertNameToId, setExpertNameToId] = useState<Record<string, string>>({});
  const [showClonePicker, setShowClonePicker] = useState(false);
  // Agents from new Runtime API (per tab)
  const [myAgents, setMyAgents] = useState<InstalledAgent[]>([]);
  const [hubCards, setHubCards] = useState<HubCard[]>([]);
  const [myAgentsLoading, setMyAgentsLoading] = useState(true);
  const [certifiedLoading, setCertifiedLoading] = useState(true);
  // API Client selector (iCoDer-style project/workspace switcher)
  const [apiClients, setApiClients] = useState<any[]>([]);
  const [selectedApiClient, setSelectedApiClient] = useState<string>('');
  // Delete confirmation modal state
  const [deleteConfirmAgent, setDeleteConfirmAgent] = useState<any>(null);
  // DB agents (for clone picker and create flow only)
  const [dbAgents, setDbAgents] = useState<any[]>([]);
  // Phase 3-B2 Loop 2 - track which Hub card is currently being cloned
  // (so we can show a spinner on the "Chat / Use Agent" CTA per card).
  const [cloningAgentId, setCloningAgentId] = useState<string | null>(null);

  useEffect(() => {
    billingApi.balance().then(r => setBalance(r.data.balance)).catch(() => {});
    // Fetch OAuth clients
    oauthApi.list().then(r => {
      const clients = r.data?.clients || [];
      setApiClients(clients);
      if (clients.length > 0) setSelectedApiClient(clients[0].client_id);
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
  const loadCertifiedAgents = (useCaseKey: string = '') => {
    setCertifiedLoading(true);
    // Phase 3-B1 Section F + Phase 3-B2 Loop 4: Prebuilt tab reads from
    // Hub endpoint with optional ?use_case=<key> filter
    // (pack-mastered, no auth, returns 11 visible packs by default: 10
    // metadata-only Coming Soon + Medical Coding Agent MVP). Backend
    // excludes expert-stubs and internal_engine automatically.
    agentHubApi.list(useCaseKey || undefined)
      .then((res: { data?: { agents?: HubCard[] } }) => setHubCards(res.data?.agents || []))
      .catch(() => setHubCards([]))
      .finally(() => setCertifiedLoading(false));
  };
  useEffect(() => { if (activeTab === 'my') loadMyAgents(); }, [activeTab]);
  useEffect(() => { if (activeTab === 'prebuilt') loadCertifiedAgents(useCase); }, [activeTab, useCase]);

  // Load memory context when entering agent detail chat - moved to AgentDetailPage

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
  const filteredCertifiedAgents = hubCards.filter(a => {
    const matchSearch = !searchQuery || (a.name || '').includes(searchQuery) || (a.description || '').includes(searchQuery);
    // Phase 3-B2 Loop 4: use_case filter now happens server-side via
    // ?use_case=<key> on agentHubApi.list. We only filter by search here.
    return matchSearch;
  });

  // Refresh Runtime agents list.
  const refreshRuntimeAgents = () => {
    runtimeAgentApi.listAgents().catch(() => {});
  };

  const handleBumpVersion = async (agentId: string) => {
    try {
      await agentsApi.version(agentId);
      refreshRuntimeAgents();
      toast(t.agentVersionBumpedToast, 'success');
    } catch { toast(t.agentVersionBumpFailedToast, 'error'); }
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

  // Clone from existing agent - uses backend POST /api/agents/{id}/clone
  const cloneAgent = async (agent: any) => {
    setShowClonePicker(false);
    try {
      const res = await agentsApi.clone(agent.id || agent.key, agent.name);
      const cloned = res.data;
      toast(t.agentClonedToDraftToast, 'success');
      navigate('/ai-studio/agents/' + (cloned.id || cloned.agent_id));
    } catch { toast(t.agentCloneFailedToast, 'error'); }
  };

  // Phase 3-B2 Loop 2 (Gap 2.2) - Click-to-Chat CTA on Hub cards.
  // Calls Loop 1 clone endpoint (idempotent), then navigates to the
  // Chat URL /ai-studio/agents/:agentId/chat?preset={agent_ref}.
  // On 401, redirects to login (the clone endpoint requires a valid Bearer token).
  const chatWithHubCard = async (card: HubCard) => {
    if (!card.runnable || !card.agent_id || cloningAgentId) return;
    setCloningAgentId(card.agent_id);
    try {
      const res = await agentHubApi.clone(card.agent_id);
      const data = res.data;
      // Phase 4-D: chat URL /ai-studio/agents/{id}/chat.
      // data.chat_url may be legacy /agents/{id}/chat; normalize to new pattern
      // using the cloned project_agent_id from the response.
      const clonedId = data.project_agent_id || card.agent_ref || card.agent_id;
      const url = `/ai-studio/agents/${encodeURIComponent(clonedId)}/chat?preset=${encodeURIComponent(card.agent_ref)}`;
      if (data.cloned) {
        toast(t.agentClonedEnterChatToast, 'success');
      } else {
        toast(t.agentExistingCloneToast, 'warning');
      }
      navigate(url);
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 401) {
        toast(t.agentLoginRequiredToast, 'error');
        navigate('/login');
      } else if (status === 404) {
        toast(t.agentNotFoundToast, 'error');
      } else {
        toast(`${t.agentCloneFailedToast}: ${err?.message || 'unknown'}`, 'error');
      }
    } finally {
      setCloningAgentId(null);
    }
  };

  // Agent列表视图
  return (
    <div className="flex-1 flex flex-col min-h-0 bg-muted/20">
      <div className="flex-1 p-6 overflow-y-auto mx-auto w-full max-w-5xl">
        <div className="bg-background rounded-xl">
          {/* Section header with accent bar ("Create an agent" + subtitle + + New Agent) */}
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

      {/* Use case 过滤器 (single dropdown ▾) - Phase 3-B2 Loop 4
          backend-driven via ?use_case=<key>. Dropdown shows i18n label,
          stores use_case key (e.g. 'coding_revenue_cycle'). Empty
          key = 全部 (no filter, all visible packs returned). */}
      {activeTab === 'prebuilt' && (
        <div className="relative flex items-center gap-2 px-6 pb-2">
          <button
            onClick={() => setShowUseCaseFilter(v => !v)}
            className="flex items-center gap-1.5 text-sm h-8 px-3 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            <span>{t.useCaseFilter}</span>
            <span className="text-foreground font-medium">
              {useCase === '' ? t.all : (USE_CASE_FILTER_KEYS.find(uc => uc.key === useCase) ? t[USE_CASE_FILTER_KEYS.find(uc => uc.key === useCase)!.labelKey] : t.all)}
            </span>
            <ChevronDown size={12} />
          </button>
          {showUseCaseFilter && (
            <div className="absolute left-6 top-full mt-1 bg-popover border border-border rounded-lg shadow-lg p-1 min-w-[160px] z-10">
              <button
                key=""
                onClick={() => { setUseCase(''); setShowUseCaseFilter(false); }}
                className={`w-full text-left px-3 py-1.5 text-xs rounded-md transition-colors ${useCase === '' ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'}`}
              >
                {t.all}
              </button>
              {USE_CASE_FILTER_KEYS.map(uc => (
                <button
                  key={uc.key}
                  onClick={() => { setUseCase(uc.key); setShowUseCaseFilter(false); }}
                  className={`w-full text-left px-3 py-1.5 text-xs rounded-md transition-colors ${useCase === uc.key ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'}`}
                >
                  {t[uc.labelKey]}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Agent列表 */}
      <div className="px-6 pb-6">

        {/* Tab: 我的智能体 - Runtime community agents */}
        {activeTab === 'my' && (
          myAgentsLoading ? (
            <div className="text-center py-12"><Loader2 className="animate-spin h-6 w-6 mx-auto text-muted-foreground" /></div>
          ) : filteredMyAgents.length === 0 ? (
            <div className="flex items-center justify-between px-6 py-8 rounded-xl bg-background">
              <div>
                <p className="text-sm font-medium text-foreground">{t.noMyAgents}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{t.noMyAgentsHint}</p>
              </div>
              <button onClick={() => setActiveTab('prebuilt')} className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-accent transition-colors">
                {t.browsePrebuilt}
              </button>
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
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-xs ${
                      agent.status === 'enabled' ? 'bg-green-100 text-green-700' :
                      agent.status === 'disabled' ? 'bg-red-100 text-red-700' :
                      'bg-muted text-muted-foreground'
                    }`}>{agent.status}</span>
                    <span className="text-[10px] font-mono text-muted-foreground">v{agent.version}</span>
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{agent.description}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-xs font-medium ${
                      agent.tier >= 3 ? 'bg-red-100 text-red-700' :
                      agent.tier >= 2 ? 'bg-amber-100 text-amber-700' :
                      'bg-green-100 text-green-700'
                    }`}>T{agent.tier}</span>
                    {agent.expert_count > 0 && <span className="text-[9px] text-muted-foreground tabular-nums">{agent.expert_count} {t.agentCardExpertsSuffix}</span>}
                    {agent.tool_count > 0 && <span className="text-[9px] text-muted-foreground tabular-nums">{agent.tool_count} {t.agentCardToolsSuffix}</span>}
                    <span className="text-[9px] text-muted-foreground">{agent.agent_type}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {agent.status === 'disabled' || agent.status === 'installed' ? (
                    <button onClick={async (e) => { e.stopPropagation(); await runtimeAgentApi.agentLifecycle(agent.agent_ref, 'enable'); loadMyAgents(); toast(t.agentEnabledToast, 'success'); }}
                      className="px-2 py-1 rounded text-[11px] bg-green-100 text-green-700 hover:bg-green-200">{t.agentEnable}</button>
                  ) : (
                    <button onClick={async (e) => { e.stopPropagation(); await runtimeAgentApi.agentLifecycle(agent.agent_ref, 'disable'); loadMyAgents(); toast(t.agentDisabledToast, 'success'); }}
                      className="px-2 py-1 rounded text-[11px] bg-amber-50 text-amber-700 hover:bg-amber-100">{t.agentDisable}</button>
                  )}
                  <button onClick={async (e) => { e.stopPropagation(); if (!confirm(t.agentConfirmUninstall)) return;
                    try { await runtimeAgentApi.agentLifecycle(agent.agent_ref, 'uninstall'); loadMyAgents(); toast(t.agentUninstalledToast, 'success'); } catch { toast(t.agentUninstallFailedToast, 'error'); }
                  }} className="px-2 py-1 rounded text-[11px] bg-red-50 text-red-600 hover:bg-red-100"><Trash2 size={11} />{t.agentUninstall}</button>
                </div>
              </div>
            ))
          )
        )}

        {/* Tab: 预置AI智能体 - Hub cards (pack-mastered) */}
        {activeTab === 'prebuilt' && (
          certifiedLoading ? (
            <div className="text-center py-12"><Loader2 className="animate-spin h-6 w-6 mx-auto text-muted-foreground" /></div>
          ) : filteredCertifiedAgents.length === 0 ? (
            <div className="text-center py-16 bg-background rounded-xl">
              <div className="w-16 h-16 mx-auto mb-4 rounded-xl bg-muted flex items-center justify-center">
                <Search size={32} className="text-muted-foreground" />
              </div>
              <h3 className="text-base font-semibold text-foreground mb-2">{t.noMatchingAgents}</h3>
              <p className="text-sm text-muted-foreground mb-4">{t.noMatchingAgentsHint}</p>
              <button onClick={() => { setSearchQuery(''); setUseCase(''); }} className="px-4 py-2 rounded-lg border border-border text-sm text-foreground hover:bg-accent transition-colors">{t.clearFilter}</button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
              {filteredCertifiedAgents.map(card => {
                // Phase 5 Track D P0 Gate 1 (2026-07-11): card uses unified
                // display_status + display_badges (≤2). PDF §B3 max badges.
                // Internal fields (maturity/production_ready/human_review)
                // remain accessible for engineering dashboards but are NOT
                // rendered on user-facing cards.
                const isComingSoon = card.display_status === 'coming_soon';
                const isDeprecated = card.display_status === 'deprecated';
                const dimCard = isComingSoon || isDeprecated;
                const isCloningThis = cloningAgentId === card.agent_id;
                const displayBadgeClass = (b: typeof card.display_badges[number]): string => {
                  switch (b.type) {
                    case 'preview':
                      return 'bg-amber-100 text-amber-700';
                    case 'available':
                      return 'bg-green-100 text-green-700';
                    case 'controlled_use':
                      return 'bg-blue-100 text-blue-700';
                    case 'coming_soon':
                      return 'bg-muted text-muted-foreground';
                    case 'deprecated':
                    case 'internal_only':
                      return 'bg-gray-200 text-gray-700';
                    case 'approval_required':
                      return 'bg-orange-50 text-orange-700';
                    case 'anomaly_confirmation_required':
                      return 'bg-yellow-50 text-yellow-700';
                    case 'clinical_decision_confirmation_required':
                      return 'bg-purple-50 text-purple-700';
                    default:
                      return 'bg-muted text-muted-foreground';
                  }
                };
                const displayBadgeLabel = (b: typeof card.display_badges[number]): string => {
                  // Use the user-locale label that the backend already attaches.
                  // Backend ``label_zh`` / ``label_en`` is authoritative — no
                  // client-side catalog drift.
                  return (locale === 'zh-CN' ? b.label_zh : b.label_en) || b.label_en;
                };
                return (
                  <div key={card.agent_ref}
                    className={`bg-background rounded-xl p-4 transition-all group ${
                      dimCard
                        ? 'opacity-80'
                        : 'hover:ring-1 hover:ring-primary/30 hover:shadow-md'
                    }`}>
                    <div className="flex items-start gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors ${
                        dimCard ? 'bg-muted' : 'bg-primary/10 group-hover:bg-primary/20'
                      }`}>
                        <Bot size={15} className={dimCard ? 'text-muted-foreground' : 'text-primary'} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className={`text-sm font-medium transition-colors ${
                            dimCard ? 'text-muted-foreground' : 'text-foreground group-hover:text-primary'
                          }`}>{card.name}</p>
                          {/* Phase 5 Track D P0 Gate 1: display_status + ≤2 badges.
                              PDF §B3 forbids rendering raw maturity/production_ready. */}
                          {card.display_badges?.map((b, i) => (
                            <span key={`${card.agent_ref}-badge-${i}`}
                              className={`text-[9px] px-1.5 py-0.5 rounded-xs font-medium ${displayBadgeClass(b)}`}
                              title={displayBadgeLabel(b)}>
                              {displayBadgeLabel(b)}
                            </span>
                          ))}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1 leading-relaxed line-clamp-2">{card.description}</p>
                        {/* Phase 4-D (D-6): card metadata (DD-Mon-YYYY · Creator) */}
                        {(card.created_at || card.creator) && (
                          <p className="text-[10px] text-muted-foreground/80 mt-1.5">
                            {card.created_at && <span>{card.created_at}</span>}
                            {card.created_at && card.creator && <span> · </span>}
                            {card.creator && <span>{card.creator}</span>}
                          </p>
                        )}
                        <div className="flex items-center gap-2 mt-2 flex-wrap">
                          {card.category && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{card.category}</span>
                          )}
                          <span className="text-[10px] font-mono text-muted-foreground">v{card.version}</span>
                          {card.default_runtime_mode && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-xs bg-primary/10 text-primary font-mono" title="Default runtime mode">
                              {card.default_runtime_mode}
                            </span>
                          )}
                        </div>
                        {/* Red lines (4 rules) - only show for runnable cards */}
                        {card.runnable && (card.red_lines?.no_upcoding || card.red_lines?.evidence_required) && (
                          <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                            {card.red_lines?.no_upcoding && (
                              <span className="text-[9px] px-1 py-0.5 rounded-xs bg-red-50 text-red-700" title="No upcoding">no_upcoding</span>
                            )}
                            {card.red_lines?.evidence_required && (
                              <span className="text-[9px] px-1 py-0.5 rounded-xs bg-orange-50 text-orange-700" title="Evidence required">evidence_required</span>
                            )}
                            {card.red_lines?.production_writeback_blocked && (
                              <span className="text-[9px] px-1 py-0.5 rounded-xs bg-gray-100 text-gray-700" title="Does not write back to EMR/HIS">no_writeback</span>
                            )}
                          </div>
                        )}
                        {/* Workflow (7-step / pipeline stages) */}
                        {card.runnable && card.workflow && (
                          <p className="text-[10px] text-muted-foreground mt-1.5 line-clamp-2">{card.workflow}</p>
                        )}
                        {/* Phase 3-B2 Loop 2 - Click-to-Chat CTAs.
                            Primary = Chat / Use Agent (clone + navigate).
                            Secondary = Customize (placeholder link to detail page). */}
                        {card.runnable && (
                          <div className="flex items-center gap-2 mt-3">
                            <button
                              onClick={(e) => { e.stopPropagation(); chatWithHubCard(card); }}
                              disabled={isCloningThis}
                              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-foreground text-background hover:opacity-90 disabled:opacity-50 transition-opacity duration-200 active:scale-[0.98] font-medium"
                            >
                              {isCloningThis ? (
                                <><Loader2 size={12} className="animate-spin" /> {t.agentCardCloning}</>
                              ) : (
                                <><Send size={12} /> {t.agentChatUseAgent}</>
                              )}
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); navigate(`/ai-studio/agents/${card.agent_ref}`); }}
                              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors duration-200 active:scale-[0.98]"
                              title={t.agentChatCustomize}
                            >
                              <Wrench size={12} /> {t.agentChatCustomize}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )
        )}

      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirmAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => setDeleteConfirmAgent(null)}>
          <div className="absolute inset-0 bg-black/40" />
          <div className="relative bg-background rounded-xl shadow-xl p-6 max-w-sm w-full mx-4" onClick={e => e.stopPropagation()}>
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

