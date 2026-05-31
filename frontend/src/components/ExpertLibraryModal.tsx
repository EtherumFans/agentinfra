// iCoDer Expert Library Modal — iCoDer Console 1:1
// Modal dialog with search, checkboxes, "Read more", Cancel/Done buttons
import { useState, useEffect } from 'react';
import {
  Search, X, ChevronLeft, Wrench, Check, BookOpen,
  Bot, Stethoscope, Pill, Globe, Calculator, Users,
  Microscope, Shield, FileText,
} from 'lucide-react';
import { expertsApi } from '../services/api';

const ICON_MAP: Record<string, React.ElementType> = {
  Bot, Stethoscope, Pill, Globe, Calculator, Users,
  Microscope, Shield, FileText, BookOpen, Wrench,
};

interface Expert {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  is_prebuilt: boolean;
  system_prompt: string;
  mcp_servers?: any[];
  usage_count?: number;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onDone: (selectedExperts: Expert[]) => void;
  preSelected: Expert[];  // experts already bound to the agent
}

export default function ExpertLibraryModal({ open, onClose, onDone, preSelected }: Props) {
  const [experts, setExperts] = useState<Expert[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    expertsApi.list('', '', 'all').then(r => {
      const list = r.data?.experts || [];
      setExperts(list);
      setSelectedIds(new Set(preSelected.map(e => e.id)));
    }).catch(() => {}).finally(() => setLoading(false));
  }, [open]);

  useEffect(() => {
    setSelectedIds(new Set(preSelected.map(e => e.id)));
  }, [preSelected]);

  const filtered = experts.filter(e => {
    if (!search) return true;
    const q = search.toLowerCase();
    return e.name.toLowerCase().includes(q)
      || (e.description || '').toLowerCase().includes(q)
      || (e.category || '').toLowerCase().includes(q);
  });

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const handleDone = () => {
    const selected = experts.filter(e => selectedIds.has(e.id));
    onDone(selected);
    onClose();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-card border border-border rounded-2xl shadow-2xl w-[520px] max-h-[600px] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border shrink-0">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <BookOpen size={16} className="text-muted-foreground" />
            Expert Library
          </h3>
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-accent transition-colors text-muted-foreground"
          >
            <X size={16} />
          </button>
        </div>

        {/* Search */}
        <div className="px-5 py-3 border-b border-border shrink-0">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search experts"
              className="w-full pl-9 pr-3 py-2 text-xs bg-muted/30 border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        </div>

        {/* Expert list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-16">
              {search ? 'No experts match your search' : 'No experts available'}
            </p>
          ) : (
            <div className="py-1">
              {filtered.map(expert => {
                const Icon = ICON_MAP[expert.icon] || Wrench;
                const isSelected = selectedIds.has(expert.id);
                const isExpanded = expandedId === expert.id;
                return (
                  <div key={expert.id} className={`px-5 py-3 border-b border-border/30 last:border-0 transition-colors ${isSelected ? 'bg-primary/5' : 'hover:bg-accent/30'}`}>
                    <div className="flex items-start gap-3">
                      {/* Checkbox */}
                      <button
                        onClick={() => toggleSelect(expert.id)}
                        className={`shrink-0 mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all ${
                          isSelected
                            ? 'bg-primary border-primary text-primary-foreground'
                            : 'border-muted-foreground/30 hover:border-primary/50'
                        }`}
                      >
                        {isSelected && <Check size={12} strokeWidth={3} />}
                      </button>

                      {/* Icon */}
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 bg-primary/10 text-primary">
                        <Icon size={16} />
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{expert.name}</p>
                          {expert.is_prebuilt && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">Prebuilt</span>
                          )}
                        </div>
                        <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed line-clamp-2">
                          {expert.description || 'No description'}
                        </p>

                        {/* Read more */}
                        <button
                          onClick={() => setExpandedId(isExpanded ? null : expert.id)}
                          className="text-[10px] text-primary hover:underline mt-1"
                        >
                          {isExpanded ? 'Show less' : 'Read more'}
                        </button>

                        {/* Expanded details */}
                        {isExpanded && (
                          <div className="mt-3 p-3 rounded-lg bg-muted/20 border border-border/50">
                            <div className="flex items-center gap-2 mb-2">
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{expert.category}</span>
                              {expert.mcp_servers && expert.mcp_servers.length > 0 && (
                                <span className="text-[9px] text-muted-foreground">{expert.mcp_servers.length} MCP server(s)</span>
                              )}
                            </div>
                            {expert.system_prompt && (
                              <div className="mt-2">
                                <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">System Prompt</p>
                                <pre className="text-[10px] text-muted-foreground whitespace-pre-wrap font-mono leading-relaxed bg-muted/30 rounded p-2 max-h-32 overflow-y-auto">
                                  {expert.system_prompt.slice(0, 400)}
                                  {expert.system_prompt.length > 400 ? '...' : ''}
                                </pre>
                              </div>
                            )}
                            {expert.mcp_servers && expert.mcp_servers.length > 0 && (
                              <div className="mt-2">
                                <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">MCP Servers</p>
                                {expert.mcp_servers.map((s: any, i: number) => (
                                  <div key={i} className="text-[10px] text-muted-foreground flex items-center gap-1.5">
                                    <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                                    {s.name} ({s.transport_type || 'http'})
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-border shrink-0 bg-muted/10">
          <p className="text-[10px] text-muted-foreground">
            <span className="font-medium text-foreground">{selectedIds.size}</span> expert{selectedIds.size !== 1 ? 's' : ''} selected
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="text-xs px-4 py-2 rounded-lg border border-border text-muted-foreground hover:bg-accent transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleDone}
              className="text-xs px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors font-medium"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
