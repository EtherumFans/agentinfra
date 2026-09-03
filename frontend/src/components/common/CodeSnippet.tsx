// Code snippet display - JS / Python / curl / JSON multi-format SDK code, auto-filled from page config
// Phase 4-F (2026-07-09): replaced C# with curl per prompt §7.4 (JS / Python / curl).
import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';

import { useT } from '../../i18n';

interface CodeSnippetProps {
  javascript: string;
  python?: string;
  json?: string;
  curl?: string;
  csharp?: string;  // Deprecated — back-compat only, prefer `curl`
  compact?: boolean;
}

type Format = 'javascript' | 'python' | 'curl' | 'json' | 'csharp';

export default function CodeSnippet({ javascript, python, json, curl, csharp, compact = false }: CodeSnippetProps) {
  const t = useT();
  const [format, setFormat] = useState<Format>('javascript');
  const [copied, setCopied] = useState(false);

  const code = format === 'javascript' ? javascript
    : format === 'python' ? (python || javascript)
    : format === 'curl' ? (curl || csharp || javascript)
    : format === 'csharp' ? (csharp || curl || javascript)
    : (json || JSON.stringify({ method: javascript.split('(')[0] }, null, 2));

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [code]);

  const tabs = compact
    ? [
        { key: 'javascript' as const, label: t.codeSnippetJavaScript },
        { key: 'json' as const, label: t.codeSnippetJSON },
      ]
    : [
        { key: 'javascript' as const, label: t.codeSnippetJavaScriptSDK },
        { key: 'python' as const, label: t.codeSnippetPythonSDK },
        { key: 'curl' as const, label: t.codeSnippetCurl },
        { key: 'json' as const, label: t.codeSnippetJSONConfig },
      ];

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setFormat(tab.key)}
              className={`text-[10px] px-2.5 py-1 rounded transition-colors ${
                format === tab.key
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <button
          onClick={handleCopy}
          className="p-1 rounded hover:bg-accent transition-colors"
          title={t.codeSnippetCopyCode}
        >
          {copied ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} className="text-muted-foreground" />}
        </button>
      </div>
      <pre className="flex-1 min-h-0 overflow-auto p-4 text-[11px] leading-relaxed font-mono text-muted-foreground bg-muted/10 whitespace-pre-wrap">
        <code>{code}</code>
      </pre>
    </div>
  );
}
