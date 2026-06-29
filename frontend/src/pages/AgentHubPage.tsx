// Agent Hub — discoverable surface for installed agents (P1.0-B)
// Hits /api/icoder/agents/* and shows: name, tier, status, health, requirements.

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bot, Layers, ChevronRight, CheckCircle2, AlertTriangle, ShieldAlert,
  Loader2, Search, RefreshCcw,
} from 'lucide-react';
import { agentHubApi, type AgentHubSummary, type AgentHealth, type AgentRequirements } from '../services/agentHubApi';

type Tab = 'overview' | 'health' | 'requirements';

export default function AgentHubPage() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentHubSummary[]>([]);
  const [registryStatus, setRegistryStatus] = useState<string>('unknown');
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('overview');
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<AgentHealth | null>(null);
  const [reqs, setReqs] = useState<AgentRequirements | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!selected) {
      setHealth(null);
      setReqs(null);
      return;
    }
    setDetailLoading(true);
    Promise.all([
      agentHubApi.getHealth(selected).catch(() => null),
      agentHubApi.getRequirements(selected).catch(() => null),
    ]).then(([h, r]) => {
      setHealth(h);
      setReqs(r);
      setDetailLoading(false);
    });
  }, [selected]);

  const refresh = () => {
    setLoading(true);
    agentHubApi.list()
      .then((d) => {
        setAgents(d.agents);
        setRegistryStatus(d.registry_status);
        if (!selected && d.agents.length > 0) {
          setSelected(d.agents[0].agent_ref);
        }
      })
      .catch(() => setAgents([]))
      .finally(() => setLoading(false));
  };

  const filtered = agents.filter((a) =>
    !search || a.name?.toLowerCase().includes(search.toLowerCase()) ||
    a.description?.toLowerCase().includes(search.toLowerCase()),
  );

  const overallIcon = (overall?: string) => {
    switch (overall) {
      case 'ready': return <CheckCircle2 size={14} className="text-emerald-600" />;
      case 'degraded': return <AlertTriangle size={14} className="text-amber-600" />;
      case 'blocked': return <ShieldAlert size={14} className="text-rose-600" />;
      default: return <Loader2 size={14} className="text-slate-400" />;
    }
  };

  return (
    <div className="flex h-full bg-muted/20">
      {/* Left rail — agent list */}
      <aside className="w-80 border-r bg-background flex flex-col">
        <div className="px-4 py-3 border-b">
          <div className="flex items-center gap-2 mb-2">
            <Layers size={18} className="text-primary" />
            <h2 className="text-sm font-semibold">Agent Hub</h2>
            <span className="ml-auto text-xs text-muted-foreground">{agents.length} agent{agents.length === 1 ? '' : 's'}</span>
          </div>
          <div className="relative">
            <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search agents…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-7 pr-2 py-1.5 text-xs border rounded-md bg-muted/40"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="p-4 text-center text-xs text-muted-foreground">
              <Loader2 size={16} className="inline animate-spin mr-1" /> Loading…
            </div>
          )}
          {!loading && filtered.length === 0 && (
            <div className="p-6 text-center text-xs text-muted-foreground">
              {registryStatus === 'not_initialized'
                ? 'Runtime registry not initialized. Boot the server first.'
                : 'No agents match this filter.'}
            </div>
          )}
          {filtered.map((a) => (
            <button
              key={a.agent_ref}
              onClick={() => setSelected(a.agent_ref)}
              className={`w-full px-4 py-3 text-left border-b hover:bg-muted/40 transition-colors ${
                selected === a.agent_ref ? 'bg-primary/5 border-l-2 border-l-primary' : ''
              }`}
            >
              <div className="flex items-start gap-2">
                <Bot size={16} className="text-primary shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{a.name}</span>
                    {a.experimental && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">
                        experimental
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate mt-0.5">
                    v{a.version ?? '?'} · {a.tier_label ?? `Tier ${a.tier ?? '?'}`}
                  </div>
                </div>
                <ChevronRight size={14} className="text-muted-foreground shrink-0 mt-0.5" />
              </div>
            </button>
          ))}
        </div>

        <div className="px-4 py-2 border-t flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground">registry: {registryStatus}</span>
          <button
            onClick={refresh}
            className="text-xs text-primary hover:underline flex items-center gap-1"
            aria-label="Refresh"
          >
            <RefreshCcw size={12} /> refresh
          </button>
        </div>
      </aside>

      {/* Right pane — detail */}
      <main className="flex-1 overflow-y-auto">
        {!selected ? (
          <div className="p-12 text-center text-muted-foreground">
            Select an agent to view details.
          </div>
        ) : (
          <div className="max-w-5xl mx-auto p-6">
            <header className="mb-4">
              <div className="flex items-center gap-3">
                <Bot size={24} className="text-primary" />
                <div>
                  <h1 className="text-xl font-semibold">{selected}</h1>
                  <p className="text-xs text-muted-foreground">{agents.find((a) => a.agent_ref === selected)?.description ?? ''}</p>
                </div>
                <div className="ml-auto flex items-center gap-1">
                  {overallIcon(health?.overall)}
                  <span className="text-xs">{health?.overall ?? 'loading…'}</span>
                </div>
              </div>
            </header>

            <nav className="flex border-b mb-4">
              {(['overview', 'health', 'requirements'] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-4 py-2 text-sm border-b-2 -mb-px transition-colors ${
                    tab === t ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {t === 'overview' ? 'Overview' : t === 'health' ? 'Health' : 'Requirements'}
                </button>
              ))}
            </nav>

            {detailLoading && (
              <div className="p-8 text-center text-xs text-muted-foreground">
                <Loader2 size={16} className="inline animate-spin mr-1" /> Loading…
              </div>
            )}

            {!detailLoading && tab === 'overview' && (
              <Overview summary={agents.find((a) => a.agent_ref === selected)!} health={health} reqs={reqs} />
            )}
            {!detailLoading && tab === 'health' && <HealthPane health={health} />}
            {!detailLoading && tab === 'requirements' && <RequirementsPane reqs={reqs} />}
          </div>
        )}
      </main>
    </div>
  );
}

function Overview({ summary, health, reqs }: { summary: AgentHubSummary; health: AgentHealth | null; reqs: AgentRequirements | null }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Card label="Tier" value={summary.tier_label ?? `Tier ${summary.tier ?? '?'}`} />
      <Card label="Status" value={summary.status ?? 'unknown'} />
      <Card label="Production-ready" value={summary.production_ready ? 'yes' : 'no'} />
      <Card label="Experimental" value={summary.experimental ? 'yes' : 'no'} />
      <Card label="Health" value={health?.overall ?? 'unknown'} />
      <Card label="MCP tools" value={reqs ? `${reqs.mcp_tools.filter((t) => t.registered).length}/${reqs.mcp_tools.length} registered` : 'loading…'} />
      <div className="col-span-2">
        <button
          onClick={() => window.location.assign(`/ai-studio/agents/${encodeURIComponent(summary.agent_ref)}`)}
          className="text-xs text-primary hover:underline"
        >
          Open in AI Studio →
        </button>
      </div>
    </div>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-4 bg-background rounded-lg border">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-sm font-medium mt-1">{value}</div>
    </div>
  );
}

function HealthPane({ health }: { health: AgentHealth | null }) {
  if (!health) return <div className="text-xs text-muted-foreground">No health data.</div>;
  return (
    <div className="space-y-3">
      <Row name="Registry" available={health.registry.available} />
      <Row name="LLM provider" available={!!health.llm_provider?.available} detail={health.llm_provider?.model} />
      <Row name="MCP tools" available={!!health.mcp_tools?.available} detail={health.mcp_tools ? `${health.mcp_tools.count} registered` : ''} />
      <Row name="Recorder (run_trace)" available={!!health.recorder?.available} detail={health.recorder?.kind} />
      {health.faiss_index?.applies_to && (
        <Row
          name="FAISS index"
          available={!!health.faiss_index.available}
          detail={health.faiss_index.error ?? (health.faiss_index.loading ? 'loading…' : 'ready')}
        />
      )}
      {health.blockers && health.blockers.length > 0 && (
        <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-md">
          <div className="text-xs font-medium text-amber-800">Blockers:</div>
          <ul className="text-xs text-amber-700 mt-1 list-disc pl-5">
            {health.blockers.map((b) => <li key={b}>{b}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function Row({ name, available, detail }: { name: string; available: boolean; detail?: string }) {
  return (
    <div className="flex items-center gap-2 p-3 bg-background rounded-md border">
      {available ? <CheckCircle2 size={14} className="text-emerald-600" /> : <AlertTriangle size={14} className="text-amber-600" />}
      <span className="text-sm flex-1">{name}</span>
      <span className="text-xs text-muted-foreground">{detail ?? (available ? 'available' : 'missing')}</span>
    </div>
  );
}

function RequirementsPane({ reqs }: { reqs: AgentRequirements | null }) {
  if (!reqs) return <div className="text-xs text-muted-foreground">No requirements data.</div>;
  return (
    <div className="space-y-4">
      <section>
        <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Filesystem assets</h3>
        <div className="space-y-1">
          {reqs.files.length === 0 && <div className="text-xs text-muted-foreground">No file assets required.</div>}
          {reqs.files.map((f, i) => (
            <div key={i} className="flex items-center gap-2 p-2 bg-background rounded border text-xs">
              {f.present ? <CheckCircle2 size={12} className="text-emerald-600" /> : <AlertTriangle size={12} className="text-rose-600" />}
              <span className="flex-1 truncate">{f.path}</span>
              <span className="text-muted-foreground">{f.description}</span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">MCP tools</h3>
        <div className="space-y-1">
          {reqs.mcp_tools.map((t, i) => (
            <div key={i} className="flex items-center gap-2 p-2 bg-background rounded border text-xs">
              {t.registered ? <CheckCircle2 size={12} className="text-emerald-600" /> : <AlertTriangle size={12} className="text-amber-600" />}
              <span className="font-mono">{t.name}</span>
              <span className="text-muted-foreground ml-auto">{t.stage}</span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Environment variables</h3>
        <div className="space-y-1">
          {reqs.env_vars.map((e) => (
            <div key={e.name} className="flex items-center gap-2 p-2 bg-background rounded border text-xs">
              {e.set ? <CheckCircle2 size={12} className="text-emerald-600" /> : <AlertTriangle size={12} className="text-amber-600" />}
              <span className="font-mono">{e.name}</span>
              <span className="text-muted-foreground ml-1">— {e.description}</span>
              <span className="ml-auto text-muted-foreground">{e.set ? e.value || '(empty)' : 'not set'}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}