// Settings/Code/Tools tab panel — iCoDer-style, used on all AI Studio pages
import { useState } from 'react';

interface TabConfig {
  settings: React.ReactNode;
  code: React.ReactNode;
  tools?: React.ReactNode;  // Optional tools tab
  defaultTab?: 'settings' | 'code' | 'tools';
  labels?: { settings?: string; code?: string; tools?: string };
}

type TabName = 'settings' | 'code' | 'tools';

export default function SettingsCodeTab({ settings, code, tools, defaultTab = 'settings', labels }: TabConfig) {
  const [tab, setTab] = useState<TabName>(defaultTab);

  const tabs: { key: TabName; label: string; content: React.ReactNode }[] = [
    { key: 'settings', label: labels?.settings || 'Settings', content: settings },
    { key: 'code', label: labels?.code || 'Code', content: code },
  ];

  if (tools) {
    tabs.push({ key: 'tools', label: labels?.tools || 'Tools', content: tools });
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center border-b border-border/30 shrink-0">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex-1 py-2.5 text-xs font-medium transition-colors border-b-2 -mb-px ${
              tab === key
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        {tabs.find(t => t.key === tab)?.content}
      </div>
    </div>
  );
}
