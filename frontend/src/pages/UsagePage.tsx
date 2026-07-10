// iCoDer Usage Page - connected to real backend
// Corti IA: header + period segmented control + 3 metric cards (with
// icons + prev-period comparison line) + activity history list
import { Activity, Loader2, ChevronDown, BarChart3, Zap, Clock } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import { useT } from '../i18n';
import { usageApi, oauthApi } from '../services/api';

const TIME_RANGES = [
  { key: 7, labelKey: 'last7DaysLabel' as const },
  { key: 30, labelKey: 'last30DaysLabel' as const },
  { key: 90, labelKey: 'last90DaysLabel' as const },
];

export default function UsagePage() {
  const t = useT();
  const [summary, setSummary] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [days, setDays] = useState(30);
  const [compareEnabled, setCompareEnabled] = useState(false);
  const [compareSummary, setCompareSummary] = useState<any>(null);
  const [apiClients, setApiClients] = useState<any[]>([]);
  const [apiClientFilter, setApiClientFilter] = useState('all');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    setCompareSummary(null);
    try {
      const [sumRes, histRes] = await Promise.all([
        usageApi.summary(days),
        usageApi.history(days),
      ]);
      setSummary(sumRes.data);
      setHistory(histRes.data.history || []);

      // Fetch comparison data for the previous period
      if (compareEnabled) {
        try {
          const compRes = await usageApi.summary(days * 2);
          const current = sumRes.data;
          const extended = compRes.data;
          const prev = {
            total_requests: Math.max(0, (extended.total_requests ?? 0) - (current.total_requests ?? 0)),
            credits_used: Math.max(0, (extended.credits_used ?? 0) - (current.credits_used ?? 0)),
            avg_response_time_ms: extended.avg_response_time_ms ?? 0,
          };
          setCompareSummary(prev);
        } catch {
          setCompareSummary(null);
        }
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || '加载用量数据失败');
    } finally {
      setLoading(false);
    }
  }, [days, compareEnabled]);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { oauthApi.list().then(r => setApiClients(r.data?.clients || [])).catch(() => {}); }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="animate-spin h-8 w-8 text-muted-foreground" />
    </div>
  );

  if (error) return (
    <div className="bg-muted/20 min-h-dvh p-6 text-center">
      <p className="text-destructive mb-4">{error}</p>
      <button onClick={fetchData} className="bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors">重试</button>
    </div>
  );

  return (
    <div className="bg-muted/20 min-h-dvh p-6">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-foreground mb-2">{t.usageTitle}</h2>
        <p className="text-sm text-muted-foreground">{t.usageDesc}</p>
      </div>

      {/* Period selector (segmented control) + API client filter + compare toggle */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <div className="inline-flex items-center rounded-lg border border-border/20 bg-background p-0.5">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                days === d
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
        {apiClients.length > 0 && (
          <div className="relative">
            <select
              value={apiClientFilter}
              onChange={e => setApiClientFilter(e.target.value)}
              className="appearance-none text-xs pl-2.5 pr-7 py-1.5 rounded-lg border border-border/20 bg-background text-foreground cursor-pointer hover:border-primary/30 focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="all">{t.allApiClients}</option>
              {apiClients.map((c: any) => (
                <option key={c.client_id} value={c.client_id}>{c.client_name || c.client_id}</option>
              ))}
            </select>
            <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          </div>
        )}
        <div className="flex items-center gap-1.5 ml-auto">
          <input
            type="checkbox"
            id="compare-period"
            checked={compareEnabled}
            onChange={e => setCompareEnabled(e.target.checked)}
            className="accent-primary w-3.5 h-3.5"
          />
          <label htmlFor="compare-period" className="text-xs text-muted-foreground cursor-pointer select-none hover:text-foreground transition-colors">
            对比周期
          </label>
        </div>
      </div>

      {/* Summary cards with comparison (Corti-style: icon + label + value + sub) */}
      <div className="grid grid-cols-3 gap-4 max-w-3xl mb-8">
        <div className="bg-background rounded-xl shadow-sm p-5">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-md bg-primary/10 text-primary flex items-center justify-center">
              <BarChart3 size={14} />
            </div>
            <p className="text-xs text-muted-foreground">{t.totalRequests}</p>
          </div>
          <p className="text-2xl font-bold font-mono text-foreground">{summary?.total_requests ?? 0}</p>
          <p className="text-xs text-muted-foreground mt-1">过去 {days} 天</p>
          {compareSummary && (
            <ComparisonLine
              label="上期"
              value={String(compareSummary.total_requests)}
              current={summary?.total_requests ?? 0}
              reverse={false}
            />
          )}
        </div>
        <div className="bg-background rounded-xl shadow-sm p-5">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-md bg-amber-500/10 text-amber-600 flex items-center justify-center">
              <Zap size={14} />
            </div>
            <p className="text-xs text-muted-foreground">{t.creditsUsed}</p>
          </div>
          <p className="text-2xl font-bold font-mono text-foreground">¥{summary?.credits_used?.toFixed(2) ?? '0.00'}</p>
          <p className="text-xs text-muted-foreground mt-1">过去 {days} 天</p>
          {compareSummary && (
            <ComparisonLine
              label="上期"
              value={`¥${compareSummary.credits_used.toFixed(2)}`}
              current={summary?.credits_used ?? 0}
              reverse={false}
            />
          )}
        </div>
        <div className="bg-background rounded-xl shadow-sm p-5">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-md bg-blue-500/10 text-blue-600 flex items-center justify-center">
              <Clock size={14} />
            </div>
            <p className="text-xs text-muted-foreground">{t.avgResponseTime}</p>
          </div>
          <p className="text-2xl font-bold font-mono text-foreground">
            {summary?.avg_response_time_ms ? `${summary.avg_response_time_ms.toFixed(0)}ms` : t.noData}
          </p>
          <p className="text-xs text-muted-foreground mt-1">过去 {days} 天</p>
          {compareSummary && (
            <ComparisonLine
              label="上期"
              value={`${compareSummary.avg_response_time_ms.toFixed(0)}ms`}
              current={summary?.avg_response_time_ms ?? 0}
              reverse={true}
            />
          )}
        </div>
      </div>

      {/* Activity history */}
      <div className="w-full">
        <h3 className="text-sm font-semibold text-foreground mb-3">{t.recentActivity}</h3>
        <div className="bg-background rounded-xl shadow-sm overflow-hidden">
          {history.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground text-sm">暂无活动</div>
          ) : (
            history.map((row: any, i: number) => (
              <div key={i} className="flex items-center justify-between p-4 border-b border-border/20 last:border-0 hover:bg-accent/50 transition-colors">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center">
                    <Activity size={14} className="text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground">{row.endpoint || row.action}</p>
                    <p className="text-xs text-muted-foreground">{row.date}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">{row.resource_type}</p>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${row.status === 'success' ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}>
                    {row.status}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

/** Inline comparison line showing previous period value and % change */
function ComparisonLine({ label, value, current, reverse }: {
  label: string; value: string; current: number; reverse: boolean;
}) {
  const prev = parseFloat(value.replace(/[^0-9.-]/g, ''));
  if (isNaN(prev) || prev === 0) return null;
  const pct = ((current - prev) / prev * 100);
  const isUp = pct > 0;
  const isDown = pct < 0;
  const color = reverse
    ? (isUp ? 'text-destructive' : isDown ? 'text-success' : 'text-muted-foreground')
    : (isUp ? 'text-success' : isDown ? 'text-destructive' : 'text-muted-foreground');
  return (
    <p className="text-[11px] mt-1.5 text-muted-foreground">
      {label}: {value}
      <span className={`ml-1 ${color}`}>
        {pct > 0 ? '↑' : pct < 0 ? '↓' : ''}{Math.abs(pct).toFixed(1)}%
      </span>
    </p>
  );
}
