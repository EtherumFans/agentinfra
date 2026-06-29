// Run Trace page (P1.0-E)
// Lists recent agent runs from /api/icoder/runs. NO fake data — if the
// recorder is inactive or history is empty, shows an honest empty state.

import { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  Activity, ChevronRight, Loader2, AlertTriangle,
  CheckCircle2, ShieldAlert, Search, RefreshCcw, Clock,
} from 'lucide-react';
import { runsApi, type RunHistoryEntry } from '../services/runsApi';

const STATUS_GLYPH: Record<string, JSX.Element> = {
  completed: <CheckCircle2 size={14} className="text-emerald-600" />,
  needs_review: <AlertTriangle size={14} className="text-amber-600" />,
  failed: <ShieldAlert size={14} className="text-rose-600" />,
};

export default function RunTracePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get('run_id');
  const filterAgentRef = searchParams.get('agent_ref') ?? '';
  const [runs, setRuns] = useState<RunHistoryEntry[]>([]);
  const [historyAvailable, setHistoryAvailable] = useState(true);
  const [selected, setSelected] = useState<RunHistoryEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [filter, setFilter] = useState(filterAgentRef);

  useEffect(() => {
    refresh();
  }, [filterAgentRef]);

  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }
    setDetailLoading(true);
    runsApi
      .get(selectedId)
      .then((r) => setSelected(r))
      .catch(() => setSelected(null))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  const refresh = () => {
    setLoading(true);
    runsApi
      .list(filterAgentRef || undefined)
      .then((d) => {
        setRuns(d.runs);
        setHistoryAvailable(d.history_available);
      })
      .catch(() => {
        setRuns([]);
        setHistoryAvailable(false);
      })
      .finally(() => setLoading(false));
  };

  const onSelectRun = (id: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('run_id', id);
    setSearchParams(next, { replace: true });
  };

  const filtered = filter
    ? runs.filter((r) =>
        r.agent_ref?.toLowerCase().includes(filter.toLowerCase()) ||
        r.primary_diagnosis_code?.toLowerCase().includes(filter.toLowerCase()) ||
        r.run_id?.toLowerCase().includes(filter.toLowerCase()),
      )
    : runs;

  return (
    <div className="flex h-full bg-muted/20">
      {/* Left rail */}
      <aside className="w-96 border-r bg-background flex flex-col">
        <div className="px-4 py-3 border-b">
          <div className="flex items-center gap-2 mb-2">
            <Activity size={18} className="text-primary" />
            <h2 className="text-sm font-semibold">Run Trace</h2>
            <span className="ml-auto text-xs text-muted-foreground">
              {runs.length} run{runs.length === 1 ? '' : 's'}
            </span>
          </div>
          <div className="relative">
            <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Filter by agent_ref / code / run_id…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
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
              {historyAvailable
                ? 'No runs recorded yet. Trigger a coding review from the Medical Coding page to populate this list.'
                : 'Run history store not initialized. Boot the server first.'}
            </div>
          )}
          {filtered.map((r) => (
            <button
              key={r.run_id}
              onClick={() => onSelectRun(r.run_id)}
              className={`w-full px-4 py-3 text-left border-b hover:bg-muted/40 transition-colors ${
                selectedId === r.run_id ? 'bg-primary/5 border-l-2 border-l-primary' : ''
              }`}
            >
              <div className="flex items-start gap-2">
                <div className="shrink-0 mt-0.5">
                  {STATUS_GLYPH[r.status] ?? <Clock size={14} className="text-slate-400" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-mono font-medium truncate">
                      {r.primary_diagnosis_code || r.run_id.slice(0, 12)}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate mt-0.5">
                    {r.primary_diagnosis_description || 'no diagnosis'}
                  </div>
                  <div className="text-[10px] text-muted-foreground truncate mt-0.5">
                    {new Date(r.timestamp).toLocaleString()} · {r.processing_time_ms}ms
                  </div>
                </div>
                <ChevronRight size={14} className="text-muted-foreground shrink-0 mt-0.5" />
              </div>
            </button>
          ))}
        </div>

        <div className="px-4 py-2 border-t flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground">
            history: {historyAvailable ? 'available' : 'unavailable'}
          </span>
          <button
            onClick={refresh}
            className="text-xs text-primary hover:underline flex items-center gap-1"
            aria-label="Refresh"
          >
            <RefreshCcw size={12} /> refresh
          </button>
        </div>
      </aside>

      {/* Right pane */}
      <main className="flex-1 overflow-y-auto">
        {!selectedId ? (
          <div className="p-12 text-center text-muted-foreground">
            Select a run to view its trace.
          </div>
        ) : detailLoading ? (
          <div className="p-8 text-center text-xs text-muted-foreground">
            <Loader2 size={16} className="inline animate-spin mr-1" /> Loading…
          </div>
        ) : !selected ? (
          <div className="p-12 text-center text-muted-foreground">
            Run <code className="font-mono">{selectedId}</code> not found.
          </div>
        ) : (
          <div className="max-w-4xl mx-auto p-6 space-y-4">
            <header className="border-b pb-3">
              <div className="flex items-center gap-3">
                <Activity size={22} className="text-primary" />
                <div className="flex-1 min-w-0">
                  <h1 className="text-lg font-semibold font-mono truncate">
                    {selected.run_id}
                  </h1>
                  <p className="text-xs text-muted-foreground truncate">
                    {selected.agent_ref}
                  </p>
                </div>
                <div className="flex items-center gap-1 text-xs">
                  {STATUS_GLYPH[selected.status] ?? <Clock size={14} />}
                  <span>{selected.status}</span>
                </div>
              </div>
            </header>

            <div className="grid grid-cols-3 gap-3">
              <Stat label="Processing time" value={`${selected.processing_time_ms}ms`} />
              <Stat label="Issues found" value={String(selected.issues_count)} />
              <Stat label="Errors" value={String(selected.errors?.length ?? 0)} />
            </div>

            <Card title="Primary diagnosis">
              <div className="font-mono text-sm">{selected.primary_diagnosis_code || '—'}</div>
              <div className="text-xs text-muted-foreground">
                {selected.primary_diagnosis_description || '(no description)'}
              </div>
            </Card>

            <Card title="Review conclusion">
              <div className="text-sm">{selected.review_conclusion || '(none)'}</div>
            </Card>

            {selected.errors && selected.errors.length > 0 && (
              <Card title="Errors">
                <ul className="text-xs text-rose-700 list-disc pl-5">
                  {selected.errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              </Card>
            )}

            {selected.input_preview && (
              <Card title="Input preview (first 500 chars)">
                <pre className="text-xs whitespace-pre-wrap text-muted-foreground">
                  {selected.input_preview}
                </pre>
              </Card>
            )}

            <div className="text-xs text-muted-foreground">
              <Link to="/agent-hub" className="text-primary hover:underline">← Back to Agent Hub</Link>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-3 bg-background rounded-lg border">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-sm font-medium mt-1">{value}</div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="p-4 bg-background rounded-lg border">
      <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">{title}</h3>
      {children}
    </section>
  );
}