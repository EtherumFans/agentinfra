// WorkbenchLayout - shared shell for 5 AI Studio tool pages.
// P1.3 Stage 6 (2026-07-02): shell only, individual pages not migrated yet.
// Corti pattern: left Input / right Output 50/50 + right Settings panel + bottom Event Inspector.
// Pages adopt this shell in Phase 2; for now it's a contract skeleton.
import { ReactNode } from 'react';
import { Settings, Terminal, PanelLeft, PanelRight } from 'lucide-react';

import { useT } from '../../i18n';

export interface WorkbenchLayoutProps {
  title: string;
  description?: string;
  input: ReactNode;
  output: ReactNode;
  settings?: ReactNode;
  eventInspector?: ReactNode;
  inputLabel?: string;
  outputLabel?: string;
}

export default function WorkbenchLayout({
  title,
  description,
  input,
  output,
  settings,
  eventInspector,
  inputLabel,
  outputLabel,
}: WorkbenchLayoutProps) {
  const t = useT();
  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div>
          <h1 className="text-base font-semibold text-foreground">{title}</h1>
          {description && <p className="text-xs text-muted-foreground mt-0.5">{description}</p>}
        </div>
      </div>

      {/* Body: split (left input/output 50-50) + right settings */}
      <div className="flex flex-1 min-h-0">
        {/* Left: input + output 50/50 */}
        <div className="flex flex-1 min-w-0">
          <div className="flex-1 min-w-0 border-r border-border flex flex-col">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-muted/30">
              <PanelLeft size={12} className="text-muted-foreground" />
              <span className="text-xs font-medium text-foreground">{inputLabel || t.workbenchLayoutInput}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-3">{input}</div>
          </div>
          <div className="flex-1 min-w-0 flex flex-col">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-muted/30">
              <PanelRight size={12} className="text-muted-foreground" />
              <span className="text-xs font-medium text-foreground">{outputLabel || t.workbenchLayoutOutput}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-3">{output}</div>
          </div>
        </div>

        {/* Right: settings panel (collapsible) */}
        {settings && (
          <div className="w-64 shrink-0 border-l border-border flex flex-col">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-muted/30">
              <Settings size={12} className="text-muted-foreground" />
              <span className="text-xs font-medium text-foreground">{t.workbenchLayoutSettings}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-3">{settings}</div>
          </div>
        )}
      </div>

      {/* Bottom: event inspector */}
      {eventInspector && (
        <div className="border-t border-border shrink-0 max-h-48 overflow-y-auto">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-muted/30 sticky top-0">
            <Terminal size={12} className="text-muted-foreground" />
            <span className="text-xs font-medium text-foreground">{t.workbenchLayoutEventInspector}</span>
          </div>
          <div className="p-3">{eventInspector}</div>
        </div>
      )}
    </div>
  );
}

