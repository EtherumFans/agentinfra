// Phase 4-D - agent config sidebar (right pane).
// Mirrors /ai-studio/agents/{id} right sidebar:
//   Settings/Code radio toggle (SettingsCodeTab).
//   Settings slot: Name input (21/50) + System prompt textarea + Experts list
//                  + Browse Expert Library + Add expert + Pinned message parts.
//   Code slot: JavaScript (SDK) / .NET (SDK) / JSON Config tabs + Copy button.
import { useState, useMemo, useCallback, useEffect } from 'react';
import {
  Plus, Search, ChevronDown, X, LockKeyhole,
} from 'lucide-react';

import { useT } from '../../i18n';
import { agentsApi, expertsApi } from '../../services/api';
import { useToastStore } from '../../store';
import { buildAgentRunSnippets } from '../../utils/agentSdkCode';
import SettingsCodeTab from '../common/SettingsCodeTab';
import CodeSnippet from '../common/CodeSnippet';

interface AgentConfigSidebarProps {
  agent: any;
  onAgentUpdated?: (updated: any) => void;
}

export default function AgentConfigSidebar({ agent, onAgentUpdated }: AgentConfigSidebarProps) {
  const t = useT();
  const toast = useToastStore((s) => s.addToast);

  const agentId = agent?.id || agent?.agent_id || '';
  const agentRef = agent?.config?.source_agent_ref || agent?.config?.agent_ref || '';
  const runtimeCustomization = agent?.runtime_customization || {};
  const isDedicatedClone = runtimeCustomization?.expert_binding_mode === 'additive_policy';
  const fixedSourceExpertIds: string[] = isDedicatedClone
    ? (runtimeCustomization?.source_expert_ids || [])
    : [];
  const initialName = agent?.name || '';
  const initialSystemPrompt = agent?.system_prompt || agent?.config?.system_prompt || '';
  const initialExpertIds: string[] = isDedicatedClone
    ? (runtimeCustomization?.project_expert_ids || [])
    : (agent?.expert_ids || agent?.config?.expert_ids || []);

  const [name, setName] = useState(initialName);
  const [systemPrompt, setSystemPrompt] = useState(initialSystemPrompt);
  const [savingName, setSavingName] = useState(false);
  const [savingPrompt, setSavingPrompt] = useState(false);
  const [showExpertLibrary, setShowExpertLibrary] = useState(false);
  const [expertIds, setExpertIds] = useState<string[]>(initialExpertIds);
  const [availableExperts, setAvailableExperts] = useState<any[]>([]);
  const [expertsLoading, setExpertsLoading] = useState(false);
  const [expertSearch, setExpertSearch] = useState('');
  const [savingExperts, setSavingExperts] = useState(false);

  // Sync local state when agent prop changes (e.g., after initial load)
  const agentKey = agentId + '|' + initialName + '|' + initialSystemPrompt
    + '|' + initialExpertIds.join(',') + '|' + fixedSourceExpertIds.join(',');
  const [lastAgentKey, setLastAgentKey] = useState(agentKey);
  if (agentKey !== lastAgentKey) {
    setLastAgentKey(agentKey);
    setName(initialName);
    setSystemPrompt(initialSystemPrompt);
    setExpertIds(initialExpertIds);
  }

  useEffect(() => {
    if (!showExpertLibrary) return;
    setExpertsLoading(true);
    expertsApi.list()
      .then((response) => setAvailableExperts(response.data?.experts || []))
      .catch((err: any) => {
        setAvailableExperts([]);
        toast(`${t.agentChatLoadFailed || 'Load failed'}: ${err?.message || ''}`, 'error');
      })
      .finally(() => setExpertsLoading(false));
  }, [showExpertLibrary, toast, t]);

  const saveExpertIds = useCallback(async (nextIds: string[]) => {
    if (!agentId || savingExperts) return;
    setSavingExperts(true);
    try {
      const persistedIds = isDedicatedClone && nextIds.length === 0
        ? fixedSourceExpertIds
        : nextIds;
      const response = await agentsApi.update(agentId, { expert_ids: persistedIds });
      const savedIds = isDedicatedClone
        ? (response.data?.runtime_customization?.project_expert_ids || [])
        : (response.data?.expert_ids || nextIds);
      setExpertIds(savedIds);
      onAgentUpdated?.(response.data);
      toast(t.agentChatSaved || 'Saved', 'success');
    } catch (err: any) {
      setExpertIds(initialExpertIds);
      toast(`${t.agentChatSaveFailed || 'Save failed'}: ${err?.message || ''}`, 'error');
    } finally {
      setSavingExperts(false);
    }
  }, [agentId, savingExperts, isDedicatedClone, fixedSourceExpertIds, initialExpertIds, onAgentUpdated, toast, t]);

  const toggleExpert = useCallback((expertId: string) => {
    const nextIds = expertIds.includes(expertId)
      ? expertIds.filter((id) => id !== expertId)
      : [...expertIds, expertId];
    setExpertIds(nextIds);
    void saveExpertIds(nextIds);
  }, [expertIds, saveExpertIds]);

  const filteredExperts = useMemo(() => {
    const query = expertSearch.trim().toLowerCase();
    if (!query) return availableExperts;
    return availableExperts.filter((expert) =>
      [expert.name, expert.description, expert.category, expert.canonical_key]
        .some((value) => String(value || '').toLowerCase().includes(query)),
    );
  }, [availableExperts, expertSearch]);

  const expertNameById = useMemo(() => Object.fromEntries(
    availableExperts.map((expert) => [expert.id, expert.name]),
  ), [availableExperts]);

  const saveName = useCallback(async () => {
    if (!agentId || name === initialName) return;
    setSavingName(true);
    try {
      const r = await agentsApi.update(agentId, { name });
      toast(t.agentChatSaved || 'Saved', 'success');
      onAgentUpdated?.(r.data);
    } catch (err: any) {
      toast(`${t.agentChatSaveFailed || 'Save failed'}: ${err?.message || ''}`, 'error');
      setName(initialName); // revert
    } finally {
      setSavingName(false);
    }
  }, [agentId, name, initialName, toast, t, onAgentUpdated]);

  const saveSystemPrompt = useCallback(async () => {
    if (!agentId || systemPrompt === initialSystemPrompt) return;
    setSavingPrompt(true);
    try {
      const r = await agentsApi.update(agentId, { system_prompt: systemPrompt });
      toast(t.agentChatSaved || 'Saved', 'success');
      onAgentUpdated?.(r.data);
    } catch (err: any) {
      toast(`${t.agentChatSaveFailed || 'Save failed'}: ${err?.message || ''}`, 'error');
      setSystemPrompt(initialSystemPrompt); // revert
    } finally {
      setSavingPrompt(false);
    }
  }, [agentId, systemPrompt, initialSystemPrompt, toast, t, onAgentUpdated]);

  // ── Settings slot ──
  const settingsSlot = (
    <div className="flex flex-col gap-5 p-4">
      {/* Name input (21/50 char counter) */}
      <div>
        <label className="text-[11px] font-semibold text-foreground block mb-1.5">
          {t.agentChatNameLabel}
        </label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value.slice(0, 50))}
          onBlur={saveName}
          disabled={savingName}
          maxLength={50}
          className="w-full text-xs border border-border rounded-lg px-2.5 py-1.5 bg-transparent focus:outline-none focus:ring-2 focus:ring-ring/40 disabled:opacity-50"
          placeholder={t.agentChatNameLabel}
        />
        <div className="text-[10px] text-muted-foreground text-right mt-0.5 tabular-nums">
          {name.length}/50
        </div>
      </div>

      {/* System prompt textarea (editable, auto-save on blur) */}
      <div>
        <label className="text-[11px] font-semibold text-foreground block mb-1.5">
          {t.agentChatSystemPrompt}
        </label>
        {isDedicatedClone && (
          <p className="text-[10px] text-muted-foreground mb-2 leading-relaxed">
            {t.agentChatDedicatedPolicyHint}
          </p>
        )}
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          onBlur={saveSystemPrompt}
          disabled={savingPrompt}
          rows={10}
          className="w-full text-[11px] font-mono border border-border rounded-lg px-2.5 py-2 bg-transparent resize-y focus:outline-none focus:ring-2 focus:ring-ring/40 disabled:opacity-50 leading-relaxed"
          placeholder={t.agentChatSystemPrompt}
        />
        {savingPrompt && (
          <p className="text-[10px] text-muted-foreground mt-0.5">{t.agentChatSaving || 'Saving…'}</p>
        )}
      </div>

      {/* Experts section */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-[11px] font-semibold text-foreground">
            {t.agentChatExperts}
          </label>
          <button
            onClick={() => setShowExpertLibrary(true)}
            disabled={!agentId || savingExperts}
            className="text-[10px] text-primary flex items-center gap-1 disabled:opacity-50"
          >
            <Search size={10} /> {t.agentChatBrowseExpertLibrary}
          </button>
        </div>
        {isDedicatedClone && fixedSourceExpertIds.length > 0 && (
          <div className="mb-3 rounded-lg border border-border/60 bg-muted/20 p-2">
            <p className="text-[10px] font-medium text-muted-foreground mb-1.5">
              {t.agentChatFixedSourceExperts}
            </p>
            <div className="space-y-1">
              {fixedSourceExpertIds.map((eid) => (
                <div key={eid} className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-muted/40">
                  <LockKeyhole size={11} className="text-muted-foreground shrink-0" />
                  <span className="text-[11px] text-foreground truncate flex-1">
                    {expertNameById[eid] || eid}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        {isDedicatedClone && (
          <p className="text-[10px] font-medium text-muted-foreground mb-1.5">
            {t.agentChatProjectExperts}
          </p>
        )}
        {/* Experts list */}
        <div className="space-y-1 mb-2">
          {expertIds.length === 0 ? (
            <p className="text-[10px] text-muted-foreground italic">
              {t.agentChatNoExperts || 'No experts configured'}
            </p>
          ) : (
            expertIds.map((eid) => (
              <div key={eid} className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-muted/40">
                <div className="w-5 h-5 rounded bg-primary/10 flex items-center justify-center shrink-0">
                  <span className="text-[9px] font-mono text-primary">{eid.slice(0, 2).toUpperCase()}</span>
                </div>
                <span className="text-[11px] text-foreground truncate flex-1">
                  {expertNameById[eid] || eid}
                </span>
                <button
                  type="button"
                  disabled={savingExperts}
                  onClick={() => toggleExpert(eid)}
                  aria-label={`Remove ${expertNameById[eid] || eid}`}
                  className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                >
                  <X size={11} />
                </button>
              </div>
            ))
          )}
        </div>
        {/* Custom experts sub-section + Add expert */}
        <div className="mt-2 pt-2 border-t border-border/30">
          <p className="text-[10px] text-muted-foreground mb-1">{t.agentChatCustomExperts}</p>
          <button
            onClick={() => setShowExpertLibrary(true)}
            disabled={!agentId || savingExperts}
            className="text-[10px] text-primary flex items-center gap-1 disabled:opacity-50"
          >
            <Plus size={10} /> {t.agentChatAddExpert}
          </button>
        </div>
      </div>

    </div>
  );

  // ── Code slot - SDK tabs (JS / Python / curl / JSON Config) per prompt §7.4 ──
  const sdkCode = useMemo(() => buildAgentRunSnippets({
    agentId,
    agentRef,
    baseURL: window.location.origin,
    runtimeMode: agent?.default_runtime_mode || agent?.config?.default_runtime_mode || '',
  }), [agentRef, agentId, agent?.default_runtime_mode, agent?.config?.default_runtime_mode]);

  const codeSlot = (
    <CodeSnippet
      javascript={sdkCode.javascript}
      python={sdkCode.python}
      curl={sdkCode.curl}
      json={sdkCode.json}
    />
  );;

  return (
    <>
      <aside className="w-[400px] shrink-0 border-l border-border bg-background flex flex-col min-h-0">
        <SettingsCodeTab settings={settingsSlot} code={codeSlot} defaultTab="settings" />
      </aside>

      {/* Tenant-scoped Expert Library */}
      {showExpertLibrary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowExpertLibrary(false)}>
          <div className="bg-background rounded-xl shadow-xl w-[480px] max-w-[90vw] max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold">{t.agentChatBrowseExpertLibrary}</h3>
              <button onClick={() => setShowExpertLibrary(false)} className="text-muted-foreground hover:text-foreground">
                <ChevronDown size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <div className="relative mb-3">
                <Search size={13} className="absolute left-2.5 top-2.5 text-muted-foreground" />
                <input
                  value={expertSearch}
                  onChange={(event) => setExpertSearch(event.target.value)}
                  placeholder={t.toolSelectorSearchPlaceholder || 'Search experts...'}
                  className="w-full border border-border rounded-lg bg-transparent pl-8 pr-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-ring/40"
                />
              </div>
              {expertsLoading ? (
                <p className="text-xs text-muted-foreground">{t.loading || 'Loading...'}</p>
              ) : filteredExperts.length === 0 ? (
                <p className="text-xs text-muted-foreground">{t.agentChatNoExperts || 'No experts configured'}</p>
              ) : (
                <div className="space-y-2">
                  {filteredExperts.map((expert) => {
                    const selected = expertIds.includes(expert.id);
                    return (
                      <button
                        type="button"
                        key={expert.id}
                        disabled={savingExperts}
                        onClick={() => toggleExpert(expert.id)}
                        className={`w-full text-left rounded-lg border px-3 py-2 disabled:opacity-50 ${
                          selected ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/40'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium">{expert.name}</span>
                          <span className="text-[10px] text-primary">
                            {selected ? '✓' : '+'}
                          </span>
                        </div>
                        <p className="text-[10px] text-muted-foreground mt-1 line-clamp-2">
                          {expert.description || expert.category}
                        </p>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
