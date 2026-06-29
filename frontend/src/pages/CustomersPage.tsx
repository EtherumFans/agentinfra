// iCoDer — Customers page (Corti parity for Embedded Assistant end-user mgmt)
//
// Corti IA replicated:
//   Header  Customers · "Manage your customers and end-users for Embedded Assistant"
//   CTA     Add customer (right-aligned)
//   Filters Search box (name / customer ID / region / tenant) + Clear Filters
//   Table   Name | NFR | Region | Customer ID | Created | Actions
//   Footer  Pagination (20 / page)
//   Modal   Display Name + Customer ID Suffix (with org slug prefix shown)
//           + Region radio (US / EU; iCoDer adds CN)
//
// iCoDer China-extension: a CN region option (CustomerRegion enum `cn`) is
// surfaced because Cloud SaaS serves 中国医院. NFR is the count of clinical
// notes ingested via Embedded Assistant — backend increments via hook.
import { useEffect, useState, useCallback } from 'react';
import {
  Loader2, Plus, Search, X, ChevronLeft, ChevronRight,
  Trash2, Users,
} from 'lucide-react';
import { customersApi } from '../services/api';
import { useT } from '../i18n';
import { useAuthStore } from '../store';

interface Customer {
  id: string;
  display_name: string;
  customer_id: string;
  region: 'us' | 'eu' | 'cn';
  nfr: number;
  created_at: string | null;
}

type RegionFilter = '' | 'us' | 'eu' | 'cn';

const PAGE_SIZE = 20;
const REGIONS: RegionFilter[] = ['us', 'eu', 'cn'];

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
  } catch {
    return iso.slice(0, 10);
  }
}

function RegionBadge({ region }: { region: 'us' | 'eu' | 'cn' }) {
  const map: Record<string, { label: string; cls: string }> = {
    us: { label: 'US', cls: 'bg-blue-500/10 text-blue-600 dark:text-blue-300 ring-1 ring-blue-500/20' },
    eu: { label: 'EU', cls: 'bg-purple-500/10 text-purple-600 dark:text-purple-300 ring-1 ring-purple-500/20' },
    cn: { label: 'CN', cls: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 ring-1 ring-amber-500/20' },
  };
  const meta = map[region] ?? { label: region, cls: 'bg-muted text-muted-foreground ring-1 ring-border' };
  return (
    <span className={`inline-flex items-center text-[10px] font-semibold rounded px-1.5 py-0.5 ${meta.cls}`}>
      {meta.label}
    </span>
  );
}

export default function CustomersPage() {
  const t = useT();
  const { user, organizations, currentOrgId } = useAuthStore();

  // Compute org slug prefix the same way the backend resolves it.
  // We surface it inside the Customer ID Suffix field as a hint.
  const orgSlugHint = (() => {
    const current = organizations?.find((o: any) => o.id === currentOrgId);
    if (current?.slug) return current.slug;
    if (user?.email && user.email.includes('@')) {
      return user.email.split('@', 1)[0].replace(/\./g, '-');
    }
    return user?.id ? `u-${user.id}` : 'unknown';
  })();
  const [items, setItems] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [region, setRegion] = useState<RegionFilter>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await customersApi.list({
        search: search.trim(),
        region,
        page,
        page_size: PAGE_SIZE,
      });
      setItems(res.data.customers || []);
      setTotal(res.data.total || 0);
    } catch (err: any) {
      setError(err?.response?.data?.detail?.message || err?.message || '加载客户列表失败');
    } finally {
      setLoading(false);
    }
  }, [search, region, page]);

  useEffect(() => { fetchList(); }, [fetchList]);

  // Reset to page 1 when filters change.
  useEffect(() => { setPage(1); }, [search, region]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasFilters = search.trim() !== '' || region !== '';

  function clearFilters() {
    setSearch('');
    setRegion('');
  }

  return (
    <div className="bg-muted/20 min-h-screen p-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold text-foreground mb-2">{t.customersTitle}</h2>
          <p className="text-sm text-muted-foreground max-w-2xl">{t.customersDesc}</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors shadow-sm"
        >
          <Plus size={14} />
          {t.addCustomer}
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative flex-1 max-w-md">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t.searchCustomerPlaceholder}
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-border/20 bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <select
          value={region}
          onChange={e => setRegion(e.target.value as RegionFilter)}
          className="appearance-none text-sm pl-3 pr-8 py-2 rounded-lg border border-border/20 bg-background text-foreground cursor-pointer hover:border-primary/30 focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="">{t.customerColRegion}: —</option>
          {REGIONS.map(r => (
            <option key={r} value={r}>
              {r === 'us' ? t.customerRegionUs : r === 'eu' ? t.customerRegionEu : t.customerRegionCn}
            </option>
          ))}
        </select>
        {hasFilters && (
          <button
            onClick={clearFilters}
            className="inline-flex items-center gap-1 px-3 py-2 text-xs rounded-lg border border-border/20 text-muted-foreground hover:bg-accent transition-colors"
          >
            <X size={12} /> {t.clearFilters}
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="animate-spin h-8 w-8 text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="text-center py-12 text-sm">
            <p className="text-destructive mb-4">{error}</p>
            <button onClick={fetchList} className="bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors">重试</button>
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <Users size={32} className="mx-auto mb-3 opacity-40" />
            <p className="text-sm">{t.customerNoData}</p>
            {!hasFilters && (
              <button
                onClick={() => setShowModal(true)}
                className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
              >
                <Plus size={14} /> {t.addCustomer}
              </button>
            )}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border/20 bg-muted/30">
                <th className="px-4 py-3 font-medium">{t.customerColName}</th>
                <th className="px-4 py-3 font-medium">{t.customerColNfr}</th>
                <th className="px-4 py-3 font-medium">{t.customerColRegion}</th>
                <th className="px-4 py-3 font-medium">{t.customerColCustomerId}</th>
                <th className="px-4 py-3 font-medium">{t.customerColCreated}</th>
                <th className="px-4 py-3 font-medium text-right">{t.customerColActions}</th>
              </tr>
            </thead>
            <tbody>
              {items.map(c => (
                <CustomerRow
                  key={c.id}
                  customer={c}
                  onDeleted={fetchList}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {!loading && !error && total > 0 && (
        <div className="flex items-center justify-between mt-4 text-xs text-muted-foreground">
          <p>{(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} / {total}</p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-1.5 rounded-md hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              aria-label="Previous page"
            >
              <ChevronLeft size={14} />
            </button>
            <span className="px-2">{page} / {totalPages}</span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="p-1.5 rounded-md hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              aria-label="Next page"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}

      {showModal && (
        <AddCustomerModal
          orgSlugHint={orgSlugHint}
          onClose={() => setShowModal(false)}
          onCreated={() => { setShowModal(false); fetchList(); }}
        />
      )}
    </div>
  );
}

function CustomerRow({ customer, onDeleted }: {
  customer: Customer;
  onDeleted: () => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);

  async function handleDelete() {
    if (!confirm(t.customerDeleteConfirm)) return;
    setBusy(true);
    try {
      await customersApi.delete(customer.customer_id);
      onDeleted();
    } catch {
      // global axios interceptor surfaces a toast
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className="border-b border-border/10 last:border-0 hover:bg-accent/30 transition-colors">
      <td className="px-4 py-3">
        <p className="text-sm font-medium text-foreground">{customer.display_name}</p>
      </td>
      <td className="px-4 py-3 text-sm font-mono text-muted-foreground">{customer.nfr}</td>
      <td className="px-4 py-3"><RegionBadge region={customer.region} /></td>
      <td className="px-4 py-3 text-xs font-mono text-muted-foreground">{customer.customer_id}</td>
      <td className="px-4 py-3 text-xs text-muted-foreground">{formatDate(customer.created_at)}</td>
      <td className="px-4 py-3 text-right">
        <button
          onClick={handleDelete}
          disabled={busy}
          className="p-1.5 rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors disabled:opacity-40"
          title={t.customerColActions}
          aria-label="Delete customer"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
        </button>
      </td>
    </tr>
  );
}

function AddCustomerModal({ orgSlugHint, onClose, onCreated }: {
  orgSlugHint: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const t = useT();
  const [displayName, setDisplayName] = useState('');
  const [suffix, setSuffix] = useState('');
  const [region, setRegion] = useState<'us' | 'eu' | 'cn'>('cn');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  async function submit() {
    if (!displayName.trim() || !suffix.trim()) {
      setFormError('请填写完整');
      return;
    }
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(suffix.trim())) {
      setFormError(t.customerIdSuffixHelp);
      return;
    }
    setSubmitting(true);
    setFormError('');
    try {
      await customersApi.create({
        display_name: displayName.trim(),
        customer_id_suffix: suffix.trim(),
        region,
      });
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
      <div
        className="bg-background rounded-xl shadow-2xl ring-1 ring-border/20 w-full max-w-md overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-border/20 flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">{t.addCustomer}</h3>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-accent text-muted-foreground">
            <X size={16} />
          </button>
        </div>
        <div className="p-5 space-y-4">
          {/* Display Name */}
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">Display Name</label>
            <input
              value={displayName}
              onChange={e => setDisplayName(e.target.value)}
              placeholder="Clinic A"
              autoFocus
              className="w-full px-3 py-2 text-sm rounded-lg border border-border/20 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Customer ID Suffix */}
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">
              {t.customerIdSuffix}
            </label>
            <div className="flex items-center rounded-lg border border-border/20 bg-muted/30 overflow-hidden focus-within:ring-1 focus-within:ring-ring">
              <span className="px-3 py-2 text-sm text-muted-foreground font-mono border-r border-border/20 bg-background">
                {orgSlugHint}/
              </span>
              <input
                value={suffix}
                onChange={e => setSuffix(e.target.value)}
                placeholder="clinic-a"
                className="flex-1 px-3 py-2 text-sm bg-background text-foreground focus:outline-none font-mono"
              />
            </div>
            <p className="text-[11px] text-muted-foreground mt-1.5">{t.customerIdSuffixHelp}</p>
          </div>

          {/* Region radio */}
          <div>
            <label className="block text-xs font-medium text-foreground mb-2">Region</label>
            <div className="grid grid-cols-3 gap-2">
              {(['us', 'eu', 'cn'] as const).map(r => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRegion(r)}
                  className={`px-3 py-2 text-sm rounded-lg border transition-colors ${
                    region === r
                      ? 'border-primary bg-primary/10 text-primary font-medium'
                      : 'border-border/20 text-muted-foreground hover:bg-accent'
                  }`}
                >
                  {r === 'us' ? t.customerRegionUs : r === 'eu' ? t.customerRegionEu : t.customerRegionCn}
                </button>
              ))}
            </div>
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
            {t.addCustomer}
          </button>
        </div>
      </div>
    </div>
  );
}