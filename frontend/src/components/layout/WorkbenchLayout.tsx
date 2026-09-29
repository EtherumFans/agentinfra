// Shared document workspace: outline, paper canvas, and editable inspector.
import { ReactNode, useRef, useState } from 'react';
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
  const inputRef = useRef<HTMLDivElement>(null);
  const outputRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState('output');
  return (
    <div className="workspace-shell">
      <div className="workspace-heading">
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="document-workspace">
        <nav className="workspace-outline" aria-label="工作区目录">
          <h2>{title}</h2>
          <p className="text-[11px] text-muted-foreground mb-4">{description}</p>
          <button className="workspace-thumbnail" aria-current={selected === 'output'} onClick={() => {
            setSelected('output'); outputRef.current?.scrollIntoView({block:'nearest'});
          }}><PanelRight size={16} className="mb-3" />{outputLabel || t.workbenchLayoutOutput}</button>
          <button className="workspace-thumbnail" aria-current={selected === 'input'} onClick={() => {
            setSelected('input'); inputRef.current?.scrollIntoView({block:'nearest'});
          }}><PanelLeft size={16} className="mb-3" />{inputLabel || t.workbenchLayoutInput}</button>
        </nav>
        <section className="document-desk" aria-label={outputLabel || t.workbenchLayoutOutput}>
          <div ref={outputRef} className="document-paper flex flex-col">
            <h2 className="text-sm font-semibold mb-4">{outputLabel || t.workbenchLayoutOutput}</h2>
            <div className="flex-1 min-h-[400px]">{output}</div>
          </div>
        </section>
        <aside className="workspace-inspector" aria-label="输入与辅助信息">
          <section ref={inputRef} className="inspector-card">
            <h2>{inputLabel || t.workbenchLayoutInput}</h2>
            <div className="inspector-input flex flex-col">{input}</div>
          </section>
          {settings && <section className="inspector-card">
            <h2 className="flex items-center gap-2"><Settings size={14}/>{t.workbenchLayoutSettings}</h2>{settings}
          </section>}
          {eventInspector && <section className="inspector-card">
            <h2 className="flex items-center gap-2"><Terminal size={14}/>{t.workbenchLayoutEventInspector}</h2>{eventInspector}
          </section>}
        </aside>
      </div>
    </div>
  );
}
