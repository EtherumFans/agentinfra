// Event Inspector - iCoDer-style collapsible event log per page
import { useState } from 'react';
import { useT } from '../../i18n';

interface EventEntry {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
  credits?: number;
}

interface EventInspectorProps {
  events: EventEntry[];
  creditsConsumed: number;
}

export default function EventInspector({ events, creditsConsumed }: EventInspectorProps) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-t border-border bg-muted/20">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-2 flex items-center justify-between text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <span>{t.eventInspectorTitle}</span>
        <div className="flex items-center gap-3">
          <span>{t.eventInspectorCreditsConsumed}: {creditsConsumed > 0 ? `¥${creditsConsumed.toFixed(6)}` : 'N/A'}</span>
          <span className={`transition-transform ${expanded ? 'rotate-180' : ''}`}>▾</span>
        </div>
      </button>
      {expanded && (
        <div className="px-4 pb-3 max-h-48 overflow-y-auto space-y-1.5">
          {events.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">{t.eventInspectorNoEvents}</p>
          ) : (
            events.map((ev, i) => (
              <div key={i} className="flex items-start gap-2 text-[11px]">
                <span className="text-muted-foreground shrink-0 w-16 font-mono">{ev.timestamp}</span>
                <span className="font-medium text-foreground shrink-0 w-20">{ev.type}</span>
                <code className="text-muted-foreground truncate flex-1">
                  {JSON.stringify(ev.data).slice(0, 120)}
                </code>
                {ev.credits !== undefined && (
                  <span className="text-muted-foreground font-mono shrink-0">¥{ev.credits.toFixed(6)}</span>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

