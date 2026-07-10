// Phase 4-D - Corti-style agent config sidebar (right pane).
// Mirrors console.corti.app/ai-studio/agents/{id} right sidebar:
//   Settings/Code radio toggle (SettingsCodeTab).
//   Settings slot: Name input (21/50) + System prompt textarea + Experts list
//                  + Browse Expert Library + Add expert + Pinned message parts.
//   Code slot: JavaScript (SDK) / .NET (SDK) / JSON Config tabs + Copy button.
import { useState, useMemo, useCallback } from 'react';
import {
  Plus, Search, Pin, ChevronDown,
} from 'lucide-react';
import { useT } from '../../i18n';
import { agentsApi } from '../../services/api';
import { useToastStore } from '../../store';
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
  const initialName = agent?.name || '';
  const initialSystemPrompt = agent?.system_prompt || agent?.config?.system_prompt || '';
  const expertIds: string[] = agent?.expert_ids || agent?.config?.expert_ids || [];

  const [name, setName] = useState(initialName);
  const [systemPrompt, setSystemPrompt] = useState(initialSystemPrompt);
  const [savingName, setSavingName] = useState(false);
  const [savingPrompt, setSavingPrompt] = useState(false);
  const [showExpertLibrary, setShowExpertLibrary] = useState(false);
  const [showAddExpert, setShowAddExpert] = useState(false);

  // Sync local state when agent prop changes (e.g., after initial load)
  const agentKey = agentId + '|' + initialName + '|' + initialSystemPrompt;
  const [lastAgentKey, setLastAgentKey] = useState(agentKey);
  if (agentKey !== lastAgentKey) {
    setLastAgentKey(agentKey);
    setName(initialName);
    setSystemPrompt(initialSystemPrompt);
  }

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
      {/* Name input (Corti: 21/50 char counter) */}
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
            disabled
            title={t.agentChatExpertLibraryStub || 'Expert library - coming soon (Phase 5)'}
            className="text-[10px] text-primary/50 flex items-center gap-1 cursor-not-allowed"
          >
            <Search size={10} /> {t.agentChatBrowseExpertLibrary}
          </button>
        </div>
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
                <span className="text-[11px] font-mono text-foreground truncate">{eid}</span>
              </div>
            ))
          )}
        </div>
        {/* Custom experts sub-section + Add expert */}
        <div className="mt-2 pt-2 border-t border-border/30">
          <p className="text-[10px] text-muted-foreground mb-1">{t.agentChatCustomExperts}</p>
          <button
            onClick={() => setShowAddExpert(true)}
            disabled
            title={t.agentChatAddExpertStub || 'Add expert - coming soon (Phase 5)'}
            className="text-[10px] text-primary/50 flex items-center gap-1 cursor-not-allowed"
          >
            <Plus size={10} /> {t.agentChatAddExpert}
          </button>
        </div>
      </div>

      {/* Pinned message parts (stub - empty state) */}
      <div>
        <div className="flex items-center gap-1.5 mb-1.5">
          <Pin size={11} className="text-muted-foreground" />
          <label className="text-[11px] font-semibold text-foreground">
            {t.agentChatPinnedMessageParts}
          </label>
        </div>
        <p className="text-[10px] text-muted-foreground italic">
          {t.agentChatNoPinnedParts || 'No pinned message parts'}
        </p>
      </div>
    </div>
  );

  // ── Code slot - SDK tabs (JS / Python / curl / JSON Config) per prompt §7.4 ──
  const sdkCode = useMemo(() => {
    const ref = agentRef || `icoder/${agentId}`;
    const a2aEndpoint = `/api/icoder/agents/${agentId}/v1/message:send`;
    const unifiedEndpoint = `/api/v1/agents/${agentId}/run`;
    return {
      javascript: `import { iCoDerClient } from "@icoder/sdk";

const client = new iCoDerClient({ apiKey: process.env.ICODER_API_KEY });

// Send a message to the agent via the unified run endpoint
const result = await client.agents.run("${ref}", {
  input: { text: "Your input here" },
  include_trace: true,
  include_evidence: true,
});

console.log(result.run_id, result.runtime_mode, result.latency_ms);
console.log(result.result);`,
      python: `from icoder import iCoDerClient
import os

client = iCoDerClient(
    api_key=os.environ["ICODER_API_KEY"],
)

# Send a message to the agent via the unified run endpoint
result = client.agents.run(
    "${ref}",
    input={"text": "Your input here"},
    include_trace=True,
    include_evidence=True,
)

print(result.run_id, result.runtime_mode, result.latency_ms)
print(result.result)`,
      curl: `curl -X POST "${window.location.origin}${unifiedEndpoint}" \\
  -H "Authorization: Bearer $ICODER_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "input": {"text": "Your input here"},
    "include_trace": true,
    "include_evidence": true
  }'`,
      json: JSON.stringify({
        agent_ref: ref,
        a2a_endpoint: a2aEndpoint,
        unified_run_endpoint: unifiedEndpoint,
        protocol: "A2A/0.3",
        method: "message/send",
        envelope: {
          jsonrpc: "2.0",
          method: "message/send",
          params: {
            message: {
              role: "user",
              parts: [{ kind: "text", text: "Your input here" }],
            },
          },
        },
      }, null, 2),
    };
  }, [agentRef, agentId]);

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

      {/* Expert Library modal stub */}
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
              <p className="text-xs text-muted-foreground">
                {t.agentChatExpertLibraryStub || 'Expert library - coming soon (Phase 5)'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Add expert dropdown stub */}
      {showAddExpert && (
        <div className="fixed inset-0 z-50" onClick={() => setShowAddExpert(false)}>
          <div className="absolute" style={{}} onClick={(e) => e.stopPropagation()}>
            <div className="bg-background border border-border rounded-lg shadow-lg w-64 p-3">
              <p className="text-xs text-muted-foreground">
                {t.agentChatAddExpertStub || 'Add expert - coming soon (Phase 5)'}
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

