/** ToolSelector - browse + select tools for Agent composition.

Displays available tools grouped by category, with Tier 1/Tier 2 badges,
contract info (requires/guarantees), and accuracy tags.
Used in AgentDetailPage's "Tools" tab.
*/

import { useState, useEffect } from 'react';
import {
  Search, Shield, ChevronDown,
  ChevronRight, Info,
} from 'lucide-react';

import { useT } from '../../i18n';

interface ToolDef {
  id: string;
  name: string;
  description: string;
  tier: number;
  category: string;
  icon: string;
  requires: string[];
  guarantees: Record<string, string>;
  accuracy_tags: string[];
  is_injectable: boolean;
  has_input_schema: boolean;
}

const CATEGORY_ORDER = ['safety', 'extraction', 'coding', 'verification', 'analysis', 'report'];

interface Props {
  enabledTools: string[];
  onChange: (enabled: string[]) => void;
  tier1Enforce: boolean;
  onTier1EnforceChange: (v: boolean) => void;
}

export default function ToolSelector({ enabledTools, onChange, tier1Enforce, onTier1EnforceChange }: Props) {
  const t = useT();
  const [tools, setTools] = useState<ToolDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [toolDetail, setToolDetail] = useState<string | null>(null);

  const CATEGORY_NAMES: Record<string, string> = {
    safety: t.toolSelectorCategorySafety,
    extraction: t.toolSelectorCategoryExtraction,
    coding: t.toolSelectorCategoryCoding,
    verification: t.toolSelectorCategoryVerification,
    analysis: t.toolSelectorCategoryAnalysis,
    report: t.toolSelectorCategoryReport,
  };

  useEffect(() => {
    fetch('/api/tools')
      .then(r => r.json())
      .then(data => {
        setTools(data.tools || []);
        // Auto-expand all categories
        const exp: Record<string, boolean> = {};
        CATEGORY_ORDER.forEach(c => { exp[c] = true; });
        setExpanded(exp);
      })
      .catch(() => {
        // Fallback: empty tools list
        setTools([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const toggle = (toolId: string) => {
    if (enabledTools.includes(toolId)) {
      onChange(enabledTools.filter(t => t !== toolId));
    } else {
      onChange([...enabledTools, toolId]);
    }
  };

  const filtered = tools.filter(t => {
    if (!search) return true;
    const q = search.toLowerCase();
    return t.id.includes(q) || t.name.includes(q) || t.description.includes(q) || t.category.includes(q);
  });

  const grouped: Record<string, ToolDef[]> = {};
  for (const cat of CATEGORY_ORDER) {
    grouped[cat] = filtered.filter(t => t.category === cat);
  }

  if (loading) {
    return (
      <div className="p-6 text-center text-gray-500">
        <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-2" />
        {t.toolSelectorLoading}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            {t.toolSelectorAvailableTools} ({filtered.length})
          </h3>
        </div>

        {/* Search */}
        <div className="relative mb-3">
          <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t.toolSelectorSearchPlaceholder}
            className="w-full pl-8 pr-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600
                       rounded bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300
                       focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Tier 1 enforce toggle */}
        <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={tier1Enforce}
            onChange={e => onTier1EnforceChange(e.target.checked)}
            className="rounded"
          />
          <Shield className="w-3.5 h-3.5 text-green-600" />
          {t.toolSelectorTier1Toggle}
        </label>
      </div>

      {/* Tool list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {CATEGORY_ORDER.map(cat => {
          const catTools = grouped[cat];
          if (!catTools || catTools.length === 0) return null;

          return (
            <div key={cat}>
              <button
                onClick={() => setExpanded(prev => ({ ...prev, [cat]: !prev[cat] }))}
                className="flex items-center gap-1.5 w-full text-left mb-2"
              >
                {expanded[cat] ? (
                  <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-gray-500" />
                )}
                <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  {CATEGORY_NAMES[cat] || cat}
                </span>
                <span className="text-xs text-gray-400">({catTools.length})</span>
              </button>

              {expanded[cat] && (
                <div className="space-y-1.5">
                  {catTools.map(tool => {
                    const isEnabled = enabledTools.includes(tool.id);
                    const isTier1 = tool.tier === 1;
                    return (
                      <div key={tool.id}>
                        <button
                          onClick={() => toggle(tool.id)}
                          className={`w-full flex items-start gap-2 p-2 rounded text-left text-xs transition-colors
                            ${isEnabled
                              ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800'
                              : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:border-gray-300'
                            }`}
                        >
                          {/* Checkbox */}
                          <input
                            type="checkbox"
                            checked={isEnabled}
                            onChange={() => toggle(tool.id)}
                            className="mt-0.5 rounded"
                          />

                          {/* Info */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className="font-medium text-gray-800 dark:text-gray-200 truncate">
                                {tool.name}
                              </span>
                              <span className={`px-1 py-0.5 rounded text-[10px] font-semibold ${
                                isTier1
                                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                  : 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
                              }`}>
                                T{tool.tier}
                              </span>
                              {tool.is_injectable && (
                                <span className="px-1 py-0.5 rounded text-[10px] bg-yellow-100 text-yellow-700">
                                  {t.toolSelectorAuto}
                                </span>
                              )}
                            </div>
                            <p className="text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-1">
                              {tool.description}
                            </p>

                            {/* Accuracy tags */}
                            {tool.accuracy_tags.length > 0 && (
                              <div className="flex gap-1 mt-1 flex-wrap">
                                {tool.accuracy_tags.map(tag => (
                                  <span key={tag} className="px-1 py-0.5 rounded text-[9px] bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>

                          {/* Info button */}
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              setToolDetail(toolDetail === tool.id ? null : tool.id);
                            }}
                            className="p-0.5 text-gray-400 hover:text-gray-600 flex-shrink-0"
                          >
                            <Info className="w-3 h-3" />
                          </button>
                        </button>

                        {/* Expanded detail */}
                        {toolDetail === tool.id && (
                          <div className="ml-8 mt-1 p-2 bg-gray-50 dark:bg-gray-800/50 rounded border border-gray-200 dark:border-gray-700 text-xs">
                            <div className="mb-1">
                              <span className="font-semibold">{t.toolSelectorId}:</span> {tool.id}
                            </div>
                            {tool.requires.length > 0 && (
                              <div className="mb-1">
                                <span className="font-semibold text-amber-600">{t.toolSelectorPreconditions}:</span>
                                <ul className="list-disc list-inside text-gray-600 dark:text-gray-400">
                                  {tool.requires.map(r => <li key={r}>{r}</li>)}
                                </ul>
                              </div>
                            )}
                            {Object.keys(tool.guarantees).length > 0 && (
                              <div>
                                <span className="font-semibold text-green-600">{t.toolSelectorPostconditions}:</span>
                                <ul className="list-disc list-inside text-gray-600 dark:text-gray-400">
                                  {Object.entries(tool.guarantees).map(([k, v]) => (
                                    <li key={k}>{k}: {v}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="text-center text-gray-400 text-xs pt-8">
            {t.toolSelectorNoMatch} "{search}"
          </div>
        )}
      </div>

      {/* Footer summary */}
      <div className="p-3 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500">
        {enabledTools.length} {t.toolSelectorSelected}
        ({tools.filter(t => enabledTools.includes(t.id) && t.tier === 1).length} {t.toolSelectorTier1},
        {tools.filter(t => enabledTools.includes(t.id) && t.tier === 2).length} {t.toolSelectorTier2})
      </div>
    </div>
  );
}

