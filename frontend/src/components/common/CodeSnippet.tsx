// Code snippet display — JS / Python / JSON three-format SDK code, auto-filled from page config
import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';

interface CodeSnippetProps {
  javascript: string;
  python?: string;
  json?: string;
  csharp?: string;
}

export default function CodeSnippet({ javascript, python, json, csharp }: CodeSnippetProps) {
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

  const tabs = [
    { key: 'javascript' as const, label: 'JavaScript (SDK)' },
    { key: 'python' as const, label: 'Python (SDK)' },
    { key: 'csharp' as const, label: 'C# (.NET SDK)' },
    { key: 'json' as const, label: 'JSON Config' },
  ];

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setFormat(t.key)}
              className={`text-[10px] px-2.5 py-1 rounded transition-colors ${
                format === t.key
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <button
          onClick={handleCopy}
          className="p-1 rounded hover:bg-accent transition-colors"
          title="Copy code"
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
