import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Clock, User, ArrowRight, Hash, Activity } from 'lucide-react';
import { runtimeStatusApi } from '../../services/api';

interface TraceEvent {
  type: 'state_transition' | 'audit' | 'human_decision';
  from_state?: string;
  to_state?: string;
  event?: string;
  subject?: string;
  decision?: string;
  actor?: string;
  reviewer?: string;
  rationale?: string;
  payload?: Record<string, any>;
  content_hash?: string;
  timestamp: string;
}

interface TraceData {
  pipeline_id: string;
  current_state: string;
  total_events: number;
  events: TraceEvent[];
  summary: {
    state_transitions: number;
    audit_records: number;
    human_decisions: number;
  };
}

interface Props {
  pipelineId: string;
  compact?: boolean;
}

const STATE_COLORS: Record<string, string> = {
  INGESTED: 'bg-slate-100 text-slate-700',
  FACTS_EXTRACTED: 'bg-blue-50 text-blue-700',
  CANDIDATES_READY: 'bg-indigo-50 text-indigo-700',
  RULES_VALIDATED: 'bg-emerald-50 text-emerald-700',
  RISK_IDENTIFIED: 'bg-amber-50 text-amber-700',
  REVIEW_REQUIRED: 'bg-orange-50 text-orange-700',
  DECISION_CONFIRMED: 'bg-green-50 text-green-700',
  ARCHIVED: 'bg-slate-100 text-slate-500',
  FAILED: 'bg-red-50 text-red-700',
  ESCALATED: 'bg-red-100 text-red-800',
};

const EVENT_ICONS: Record<string, React.ReactNode> = {
  state_transition: <ArrowRight size={12} />,
  audit: <Activity size={12} />,
  human_decision: <User size={12} />,
};

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso.slice(11, 19);
  }
}

export default function AgentTraceViewer({ pipelineId, compact }: Props) {
  const [trace, setTrace] = useState<TraceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!pipelineId) return;
    setLoading(true);
    runtimeStatusApi
      .trace(pipelineId)
      .then((r) => setTrace(r.data))
      .catch(() => setError('Trace data unavailable'))
      .finally(() => setLoading(false));
  }, [pipelineId]);

  if (loading) return <div className="text-xs text-muted-foreground py-8 text-center">Loading trace...</div>;
  if (error) return <div className="text-xs text-muted-foreground py-4">{error}</div>;
  if (!trace || trace.events.length === 0) return <div className="text-xs text-muted-foreground py-4">No trace events recorded.</div>;

  if (compact) {
    return (
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
        <span>{trace.summary.state_transitions} transitions</span>
        <span>{trace.summary.audit_records} audits</span>
        <span>{trace.summary.human_decisions} decisions</span>
        <span className={`px-1.5 py-0.5 rounded font-medium ${STATE_COLORS[trace.current_state]?.split(' ')[0] || 'bg-slate-100'} ${STATE_COLORS[trace.current_state]?.split(' ').slice(1).join(' ') || 'text-slate-700'}`}>
          {trace.current_state}
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {/* Summary bar */}
      <div className="flex items-center gap-4 px-3 py-2 bg-muted/30 rounded-lg text-[10px] text-muted-foreground mb-2">
        <span className="flex items-center gap-1"><ArrowRight size={10} /> {trace.summary.state_transitions}</span>
        <span className="flex items-center gap-1"><Activity size={10} /> {trace.summary.audit_records}</span>
        <span className="flex items-center gap-1"><User size={10} /> {trace.summary.human_decisions}</span>
        <span className="ml-auto">State: <span className="font-medium text-foreground">{trace.current_state}</span></span>
      </div>

      {/* Timeline */}
      <div className="relative pl-6 border-l-2 border-border">
        {trace.events.map((ev, i) => (
          <div key={i} className="relative pb-3 last:pb-0">
            {/* Dot */}
            <div className={`absolute -left-[25px] top-1 w-3 h-3 rounded-full border-2 border-background ${
              ev.type === 'state_transition' ? 'bg-blue-400' :
              ev.type === 'human_decision' ? 'bg-amber-400' : 'bg-slate-400'
            }`} />

            {/* State transition */}
            {ev.type === 'state_transition' && (
              <div className="flex items-center gap-2 text-[11px]">
                <span className={STATE_COLORS[ev.from_state || ''] || 'bg-slate-50 text-slate-600'} style={{padding: '1px 4px', borderRadius: 3}}>
                  {ev.from_state}
                </span>
                <ArrowRight size={10} className="text-muted-foreground" />
                <span className={STATE_COLORS[ev.to_state || ''] || 'bg-slate-50 text-slate-600'} style={{padding: '1px 4px', borderRadius: 3}}>
                  {ev.to_state}
                </span>
                {ev.actor && <span className="text-muted-foreground ml-1">by {ev.actor}</span>}
                <span className="text-muted-foreground ml-auto">{formatTime(ev.timestamp)}</span>
              </div>
            )}

            {/* Audit event */}
            {ev.type === 'audit' && (
              <div className="text-[11px]">
                <div className="flex items-center gap-1.5">
                  <span className="font-medium text-foreground">{ev.event}</span>
                  {ev.actor && <span className="text-muted-foreground">— {ev.actor}</span>}
                  <span className="text-muted-foreground ml-auto">{formatTime(ev.timestamp)}</span>
                </div>
                {ev.payload && Object.keys(ev.payload).length > 0 && (
                  <div className="mt-0.5 text-[10px] text-muted-foreground bg-muted/30 rounded px-2 py-1 font-mono">
                    {Object.entries(ev.payload).slice(0, 3).map(([k, v]) => (
                      <span key={k} className="mr-2">{k}={JSON.stringify(v).slice(0, 40)}</span>
                    ))}
                  </div>
                )}
                {ev.content_hash && (
                  <div className="flex items-center gap-1 text-[10px] text-muted-foreground mt-0.5">
                    <Hash size={10} />
                    <span className="font-mono">{ev.content_hash}</span>
                  </div>
                )}
              </div>
            )}

            {/* Human decision */}
            {ev.type === 'human_decision' && (
              <div className="flex items-start gap-2 text-[11px] bg-amber-50/50 rounded px-2 py-1.5 border border-amber-100">
                <User size={12} className="text-amber-600 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium">{ev.subject || ev.decision}</span>
                    {ev.reviewer && <span className="text-muted-foreground">— {ev.reviewer}</span>}
                    <span className="ml-auto text-muted-foreground">{formatTime(ev.timestamp)}</span>
                  </div>
                  {ev.rationale && (
                    <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">{ev.rationale}</p>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
