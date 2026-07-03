import { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Clock } from 'lucide-react';
import { useT } from '../../i18n';
import { runtimeStatusApi } from '../../services/api';

interface Props {
  caseId: string;
  refreshTrigger?: number;
}

export default function AuditTrailViewer({ caseId, refreshTrigger }: Props) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    if (!caseId || !open) return;
    setLoading(true);
    runtimeStatusApi.audit(caseId, 100).then(r => {
      setEvents(r.data.events || []);
      setTotal(r.data.total || 0);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [caseId, open, refreshTrigger]);

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-accent/50 transition-colors"
      >
        {open ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
        <Clock size={14} className="text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">{t.orchestrationAuditTrail}</span>
        {total > 0 && <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded-full">{total}</span>}
      </button>
      {open && (
        <div className="px-4 pb-3 max-h-64 overflow-y-auto">
          {loading ? (
            <p className="text-xs text-muted-foreground py-4 text-center">Loading...</p>
          ) : events.length === 0 ? (
            <p className="text-xs text-muted-foreground py-4 text-center">{t.orchestrationNoAuditEvents}</p>
          ) : (
            <div className="space-y-px">
              {events.map((evt: any, i: number) => (
                <div key={i} className="flex items-start gap-3 py-1.5 text-xs">
                  <span className="text-[10px] text-muted-foreground font-mono shrink-0 w-16">
                    {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : ''}
                  </span>
                  <span className="text-[10px] font-medium text-foreground shrink-0 w-24 truncate">
                    {evt.event_type || evt.type || 'event'}
                  </span>
                  <span className="text-[10px] text-muted-foreground shrink-0 w-16 truncate">
                    {evt.actor || ''}
                  </span>
                  <span className="text-[10px] text-muted-foreground truncate">
                    {evt.payload ? JSON.stringify(evt.payload).slice(0, 80) : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
