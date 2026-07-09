// Code snippet display - JS / Python / JSON three-format SDK code, auto-filled from page config
import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';
import { useT } from '../../i18n';

interface CodeSnippetProps {
  javascript: string;
  python?: string;
  json?: string;
  csharp?: string;
  compact?: boolean;
}

export default function CodeSnippet({ javascript, python, json, csharp, compact = false }: CodeSnippetProps) {
  const t = useT();
  const [format, setFormat] = useState<'javascript' | 'python' | 'json' | 'csharp'>('javascript');
  const [copied, setCopied] = useState(false);

  const code = format === 'javascript' ? javascript
    : format === 'python' ? (python || javascript)
    : format === 'csharp' ? (csharp || javascript)
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
        { key: 'csharp' as const, label: t.codeSnippetCSharpSDK },
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

