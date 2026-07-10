// iCoDer - Tickets Portal page (Corti parity)
//
// Corti /tickets IA: external Zendesk-style portal with org selector + All/
// Created by me + Search + Filter + table + empty state. iCoDer implements
// the same conceptual workflow in-app (no external help-desk infra needed).
//
// IA replicated:
//   Header  Tickets · subtitle
//   Toggle  All / Created by me
//   Filters Search + Status select + Priority select
//   Table   Subject / Status / Priority / Updated / Actions
//   CTA     New ticket (opens builder modal: subject + description + priority)
//   Status  open / in_progress / resolved / closed
//   Priority low / medium / high
import { useEffect, useState, useCallback } from 'react';
import {
  Loader2, Plus, Search, X, Trash2, MessageSquare, ChevronDown,
  AlertCircle,
} from 'lucide-react';
import { ticketsApi } from '../services/api';
import { useT } from '../i18n';

interface Ticket {
  id: string;
  subject: string;
  description: string;
  status: 'open' | 'in_progress' | 'resolved' | 'closed';
  priority: 'low' | 'medium' | 'high';
  created_by_id: string;
  created_at: string | null;
  updated_at: string | null;
}

type Scope = 'all' | 'mine';
type StatusFilter = '' | 'open' | 'in_progress' | 'resolved' | 'closed';
type PriorityFilter = '' | 'low' | 'medium' | 'high';

const STATUS_KEY: Record<string, string> = {
  open: 'ticketsStatusOpen',
  in_progress: 'ticketsStatusInProgress',
  resolved: 'ticketsStatusResolved',
  closed: 'ticketsStatusClosed',
};

const PRIORITY_KEY: Record<string, string> = {
  low: 'ticketsPriorityLow',
  medium: 'ticketsPriorityMedium',
  high: 'ticketsPriorityHigh',
};

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso.slice(0, 16).replace('T', ' ');
  }
}

function StatusBadge({ status }: { status: Ticket['status'] }) {
  const map: Record<string, string> = {
    open: 'bg-blue-500/10 text-blue-600 dark:text-blue-300 ring-1 ring-blue-500/20',
    in_progress: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 ring-1 ring-amber-500/20',
    resolved: 'bg-success/10 text-success ring-1 ring-success/20',
    closed: 'bg-muted text-muted-foreground ring-1 ring-border',
  };
  return (
    <span className={`inline-flex items-center text-[10px] font-semibold uppercase tracking-wider rounded px-1.5 py-0.5 ${map[status] || map.closed}`}>
      {status.replace('_', ' ')}
    </span>
  );
}

function PriorityBadge({ priority }: { priority: Ticket['priority'] }) {
  const map: Record<string, string> = {
    low: 'text-muted-foreground',
    medium: 'text-foreground',
    high: 'text-destructive font-semibold',
  };
  return (
    <span className={`inline-flex items-center text-xs ${map[priority] || ''}`}>
      {priority}
    </span>
  );
}

export default function TicketsPage() {
  const t = useT();
  const [items, setItems] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [scope, setScope] = useState<Scope>('all');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<StatusFilter>('');
  const [priority, setPriority] = useState<PriorityFilter>('');
  const [page, setPage] = useState(1);
  const [showNew, setShowNew] = useState(false);

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await ticketsApi.list({
        search: search.trim(),
        status,
        priority,
        created_by_me: scope === 'mine',
        page,
        page_size: 20,
      });
      setItems(res.data.tickets || []);
      setTotal(res.data.total || 0);
    } catch (err: any) {
      setError(err?.response?.data?.detail?.message || err?.message || '加载工单失败');
    } finally {
      setLoading(false);
    }
  }, [search, status, priority, scope, page]);

  useEffect(() => { fetchList(); }, [fetchList]);
  useEffect(() => { setPage(1); }, [search, status, priority, scope]);

  return (
    <div className="bg-muted/20 min-h-dvh p-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold text-foreground mb-2">{t.ticketsTitle}</h2>
          <p className="text-sm text-muted-foreground max-w-2xl">{t.ticketsDesc}</p>
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors shadow-sm"
        >
          <Plus size={14} />
          {t.ticketsNewTicket}
        </button>
      </div>

      {/* Scope toggle + filters */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <div className="inline-flex items-center rounded-lg border border-border/20 bg-background p-0.5">
          {(['all', 'mine'] as Scope[]).map(s => (
            <button
              key={s}
              onClick={() => setScope(s)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                scope === s ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {s === 'all' ? t.ticketsAll : t.ticketsCreatedByMe}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <div className="relative w-full max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search..."
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-border/20 bg-background text-foreground placeholder:text-foreground/70 focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <select
          value={status}
          onChange={e => setStatus(e.target.value as StatusFilter)}
          className="appearance-none text-sm pl-3 pr-8 py-2 rounded-lg border border-border/20 bg-background text-foreground cursor-pointer hover:border-primary/30 focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="">All statuses</option>
          <option value="open">{t.ticketsStatusOpen}</option>
          <option value="in_progress">{t.ticketsStatusInProgress}</option>
          <option value="resolved">{t.ticketsStatusResolved}</option>
          <option value="closed">{t.ticketsStatusClosed}</option>
        </select>
        <select
          value={priority}
          onChange={e => setPriority(e.target.value as PriorityFilter)}
          className="appearance-none text-sm pl-3 pr-8 py-2 rounded-lg border border-border/20 bg-background text-foreground cursor-pointer hover:border-primary/30 focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="">All priorities</option>
          <option value="low">{t.ticketsPriorityLow}</option>
          <option value="medium">{t.ticketsPriorityMedium}</option>
          <option value="high">{t.ticketsPriorityHigh}</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-background rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="animate-spin h-8 w-8 text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="text-center py-12 text-sm">
            <AlertCircle size={28} className="mx-auto mb-3 text-destructive opacity-60" />
            <p className="text-destructive mb-4">{error}</p>
            <button onClick={fetchList} className="bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors">重试</button>
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <MessageSquare size={32} className="mx-auto mb-3 opacity-40" />
            <p className="text-sm">{t.ticketsNoData}</p>
            <button
              onClick={() => setShowNew(true)}
              className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <Plus size={14} /> {t.ticketsNewTicket}
            </button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border/20 bg-muted/30">
                <th className="px-4 py-3 font-medium">{t.ticketsColSubject}</th>
                <th className="px-4 py-3 font-medium">{t.ticketsColStatus}</th>
                <th className="px-4 py-3 font-medium">{t.ticketsColPriority}</th>
                <th className="px-4 py-3 font-medium">{t.ticketsColUpdated}</th>
                <th className="px-4 py-3 font-medium text-right">{t.ticketsColActions}</th>
              </tr>
            </thead>
            <tbody>
              {items.map(tk => (
                <TicketRow
                  key={tk.id}
                  ticket={tk}
                  statusLabel={(STATUS_KEY[tk.status] && (t[STATUS_KEY[tk.status] as keyof typeof t] as string)) || tk.status}
                  priorityLabel={(PRIORITY_KEY[tk.priority] && (t[PRIORITY_KEY[tk.priority] as keyof typeof t] as string)) || tk.priority}
                  onDeleted={fetchList}
                  onUpdated={fetchList}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {!loading && !error && items.length > 0 && (
        <p className="text-xs text-muted-foreground mt-3 text-right">{items.length} / {total}</p>
      )}

      {showNew && (
        <NewTicketModal
          onClose={() => setShowNew(false)}
          onCreated={() => { setShowNew(false); fetchList(); }}
        />
      )}
    </div>
  );
}

function TicketRow({ ticket, statusLabel, priorityLabel, onDeleted, onUpdated }: {
  ticket: Ticket;
  statusLabel: string;
  priorityLabel: string;
  onDeleted: () => void;
  onUpdated: () => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  async function handleDelete() {
    if (!confirm(t.ticketsDeleteConfirm)) return;
    setBusy(true);
    try { await ticketsApi.delete(ticket.id); onDeleted(); } catch {} finally { setBusy(false); }
  }

  async function updateStatus(newStatus: 'open' | 'in_progress' | 'resolved' | 'closed') {
    setBusy(true);
    try { await ticketsApi.update(ticket.id, { status: newStatus }); onUpdated(); } catch {} finally { setBusy(false); setOpen(false); }
  }

  return (
    <tr className="border-b border-border/10 last:border-0 hover:bg-accent/30 transition-colors">
      <td className="px-4 py-3">
        <p className="text-sm font-medium text-foreground">{ticket.subject}</p>
        {ticket.description && (
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{ticket.description}</p>
        )}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={ticket.status} />
        <span className="ml-2 text-xs text-muted-foreground">{statusLabel}</span>
      </td>
      <td className="px-4 py-3">
        <PriorityBadge priority={ticket.priority} />
        <span className="ml-2 text-xs text-muted-foreground">{priorityLabel}</span>
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground">{formatDate(ticket.updated_at)}</td>
      <td className="px-4 py-3 text-right">
        <div className="relative inline-block">
          <button
            onClick={() => setOpen(!open)}
            disabled={busy}
            className="p-1.5 rounded-md text-muted-foreground hover:bg-accent transition-colors disabled:opacity-40"
            aria-label="Actions"
          >
            <ChevronDown size={14} />
          </button>
          {open && (
            <div className="absolute right-0 top-full mt-1 w-44 bg-popover border border-border rounded-lg shadow-lg z-10 overflow-hidden text-left">
              <button onClick={() => updateStatus('in_progress')} className="w-full px-3 py-2 text-xs hover:bg-accent">→ In progress</button>
              <button onClick={() => updateStatus('resolved')} className="w-full px-3 py-2 text-xs hover:bg-accent">→ Resolved</button>
              <button onClick={() => updateStatus('closed')} className="w-full px-3 py-2 text-xs hover:bg-accent">→ Closed</button>
              <button onClick={() => updateStatus('open')} className="w-full px-3 py-2 text-xs hover:bg-accent">→ Open</button>
              <div className="border-t border-border/10" />
              <button
                onClick={handleDelete}
                className="w-full px-3 py-2 text-xs text-destructive hover:bg-destructive/10 flex items-center gap-2"
              >
                <Trash2 size={12} /> Delete
              </button>
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

function NewTicketModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void; }) {
  const t = useT();
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<'low' | 'medium' | 'high'>('medium');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  async function submit() {
    if (!subject.trim()) {
      setFormError('请填写主题');
      return;
    }
    setSubmitting(true);
    setFormError('');
    try {
      await ticketsApi.create({ subject: subject.trim(), description: description.trim(), priority });
      onCreated();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setFormError(typeof detail === 'string' ? detail : detail?.message || '创建失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-background rounded-xl shadow-2xl shadow-sm w-full max-w-md overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-border/20 flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">{t.ticketsNewTicket}</h3>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-accent text-muted-foreground">
            <X size={16} />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">{t.ticketsSubject}</label>
            <input
              value={subject}
              onChange={e => setSubject(e.target.value)}
              placeholder="简要描述问题或请求"
              autoFocus
              className="w-full px-3 py-2 text-sm rounded-lg border border-border/20 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">{t.ticketsDescription}</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="补充细节..."
              rows={4}
              className="w-full px-3 py-2 text-sm rounded-lg border border-border/20 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-y"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">{t.ticketsPriority}</label>
            <select
              value={priority}
              onChange={e => setPriority(e.target.value as 'low' | 'medium' | 'high')}
              className="w-full appearance-none text-sm pl-3 pr-8 py-2 rounded-lg border border-border/20 bg-background text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="low">{t.ticketsPriorityLow}</option>
              <option value="medium">{t.ticketsPriorityMedium}</option>
              <option value="high">{t.ticketsPriorityHigh}</option>
            </select>
          </div>
          {formError && (
            <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{formError}</p>
          )}
        </div>
        <div className="px-5 py-3 border-t border-border/20 bg-muted/30 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-border/20 text-foreground hover:bg-accent transition-colors"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {submitting && <Loader2 size={12} className="animate-spin" />}
            {t.ticketsNewTicket}
          </button>
        </div>
      </div>
    </div>
  );
}