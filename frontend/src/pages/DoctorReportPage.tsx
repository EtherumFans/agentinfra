// Doctor Report page (P1.0-F)
// Renders the JSON from GET /api/icoder/doctor in a readable table.
// Verdict-driven styling: OK=green, WARN=amber, FAIL=rose, SKIP=slate.

import { useEffect, useState } from 'react';
import {
  Stethoscope, RefreshCcw, Loader2, CheckCircle2, AlertTriangle,
  ShieldAlert, Minus, ChevronRight, Server,
} from 'lucide-react';

interface DoctorCheck {
  id: string;
  title: string;
  status: 'OK' | 'WARN' | 'FAIL' | 'SKIP';
  message: string;
  detail: Record<string, unknown>;
}

interface DoctorReport {
  verdict: 'OK' | 'WARN' | 'FAIL';
  summary: { passed: number; warned: number; failed: number; skipped: number; total: number };
  checks: DoctorCheck[];
  backend_root: string;
}

const STATUS_ICON: Record<DoctorCheck['status'], JSX.Element> = {
  OK: <CheckCircle2 size={14} className="text-emerald-600" />,
  WARN: <AlertTriangle size={14} className="text-amber-600" />,
  FAIL: <ShieldAlert size={14} className="text-rose-600" />,
  SKIP: <Minus size={14} className="text-slate-400" />,
};

const VERDICT_COLOR: Record<DoctorReport['verdict'], string> = {
  OK: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  WARN: 'bg-amber-50 text-amber-700 border-amber-200',
  FAIL: 'bg-rose-50 text-rose-700 border-rose-200',
};

export default function DoctorReportPage() {
  const [report, setReport] = useState<DoctorReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    fetch('/api/icoder/doctor')
      .then((r) => r.json())
      .then((d: DoctorReport) => setReport(d))
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  if (loading && !report) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        <Loader2 size={16} className="inline animate-spin mr-1" /> Loading doctor report…
      </div>
    );
  }
  if (!report) {
    return (
      <div className="p-8 text-center text-rose-700">
        Failed to load doctor report.
        <button onClick={refresh} className="ml-2 text-primary hover:underline">
          retry
        </button>
      </div>
    );
  }

  const selected = selectedId ? report.checks.find((c) => c.id === selectedId) : null;

  return (
    <div className="flex h-full bg-muted/20">
      {/* Left rail — check list */}
      <aside className="w-96 border-r bg-background flex flex-col">
        <div className="px-4 py-3 border-b">
          <div className="flex items-center gap-2">
            <Stethoscope size={18} className="text-primary" />
            <h2 className="text-sm font-semibold">Doctor Report</h2>
            <span className="ml-auto text-xs text-muted-foreground">
              {report.summary.total} checks
            </span>
          </div>
          <div className="mt-2 flex items-center gap-2 text-xs">
            <span className={`px-2 py-0.5 rounded border ${VERDICT_COLOR[report.verdict]}`}>
              {report.verdict}
            </span>
            <span className="text-muted-foreground">
              {report.summary.passed} OK · {report.summary.warned} WARN ·{' '}
              {report.summary.failed} FAIL · {report.summary.skipped} SKIP
            </span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {report.checks.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelectedId(c.id)}
              className={`w-full px-4 py-2.5 text-left border-b hover:bg-muted/40 transition-colors ${
                selectedId === c.id ? 'bg-primary/5 border-l-2 border-l-primary' : ''
              }`}
            >
              <div className="flex items-start gap-2">
                <div className="shrink-0 mt-0.5">{STATUS_ICON[c.status]}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-mono text-muted-foreground">{c.id}</div>
                  <div className="text-sm truncate">{c.title}</div>
                  {c.message && (
                    <div className="text-[11px] text-muted-foreground truncate mt-0.5">
                      {c.message}
                    </div>
                  )}
                </div>
                <ChevronRight size={12} className="text-muted-foreground shrink-0 mt-1" />
              </div>
            </button>
          ))}
        </div>

        <div className="px-4 py-2 border-t flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground truncate">
            {report.backend_root}
          </span>
          <button
            onClick={refresh}
            className="text-xs text-primary hover:underline flex items-center gap-1"
          >
            <RefreshCcw size={12} /> refresh
          </button>
        </div>
      </aside>

      {/* Right pane — detail */}
      <main className="flex-1 overflow-y-auto">
        {!selected ? (
          <div className="p-12 text-center text-muted-foreground">
            Select a check on the left to see its detail payload.
          </div>
        ) : (
          <div className="max-w-3xl mx-auto p-6 space-y-4">
            <header className="border-b pb-3">
              <div className="flex items-center gap-3">
                <Server size={22} className="text-primary" />
                <div className="flex-1 min-w-0">
                  <h1 className="text-lg font-semibold">{selected.title}</h1>
                  <p className="text-xs font-mono text-muted-foreground">{selected.id}</p>
                </div>
                <div className="flex items-center gap-1 text-xs">
                  {STATUS_ICON[selected.status]}
                  <span>{selected.status}</span>
                </div>
              </div>
              {selected.message && (
                <p className="text-sm text-muted-foreground mt-2">{selected.message}</p>
              )}
            </header>

            <section>
              <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">
                Detail payload
              </h3>
              <pre className="text-xs bg-background border rounded-md p-3 overflow-auto max-h-[60vh]">
                {JSON.stringify(selected.detail, null, 2)}
              </pre>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}