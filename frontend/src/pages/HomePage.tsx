// iCoDer Console Home — iCoDer-style Product Hub with i18n
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Loader2, Activity, ChevronDown,
} from 'lucide-react';
import { billingApi, usageApi, encountersApi, reviewsApi, oauthApi } from '../services/api';
import { useT, useLocaleStore } from '../i18n';

interface ChartPoint { label: string; value: number; }

const TIME_RANGES = [
  { key: 7, labelKey: 'last7DaysLabel' as const },
  { key: 30, labelKey: 'last30DaysLabel' as const },
  { key: 90, labelKey: 'last90DaysLabel' as const },
];

export default function HomePage() {
  const t = useT();
  const locale = useLocaleStore((s) => s.locale);
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'transcribe' | 'document' | 'chat' | 'code'>('transcribe');
  const [chartPeriod, setChartPeriod] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [comparePeriod, setComparePeriod] = useState(false);
  const [timeRange, setTimeRange] = useState(30);
  const [apiClients, setApiClients] = useState<any[]>([]);
  const [apiClientFilter, setApiClientFilter] = useState('all');
  const [balance, setBalance] = useState<number | null>(null);
  const [consumed, setConsumed] = useState(0);
  const [historyData, setHistoryData] = useState<{ date: string; credits: number }[]>([]);
  const [totalRequests, setTotalRequests] = useState(0);
  const [avgResponseTime, setAvgResponseTime] = useState(0);
  const [recentEncounters, setRecentEncounters] = useState<any[]>([]);
  const [recentReviews, setRecentReviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const PRODUCT_TABS = [
    { key: 'chat' as const, label: t.productHubChat, description: t.productHubChatDesc, cta: t.productHubChatCta, ctaLink: '/ai-studio/agents', secondaryLabel: t.productHubChatSecondary, secondaryLink: '/ai-studio/agents', buildLabel: t.productHubChatBuild, buildLink: '/developer-quickstart?useCase=chat' },
    { key: 'code' as const, label: t.productHubCode, labelSuffix: t.productHubNew, description: t.productHubCodeDesc, cta: t.productHubCodeCta, ctaLink: '/ai-studio/medical-coding', secondaryLabel: t.productHubCodeSecondary, secondaryLink: '/ai-studio/medical-coding', buildLabel: t.productHubCodeBuild, buildLink: '/developer-quickstart?useCase=coding' },
  ];

  const formatCurrency = (value: number, fractionDigits = 2) =>
    new Intl.NumberFormat(locale, { style: 'currency', currency: 'CNY', minimumFractionDigits: fractionDigits, maximumFractionDigits: fractionDigits }).format(value);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [balR, useR, histR, encR, revR] = await Promise.allSettled([billingApi.balance(), usageApi.summary(timeRange), usageApi.history(timeRange), encountersApi.list(1, 5), reviewsApi.list(1, 5)]);
      if (balR.status === 'fulfilled') setBalance(balR.value.data.balance);
      if (useR.status === 'fulfilled') { setConsumed(useR.value.data.credits_used || 0); setTotalRequests(useR.value.data.total_requests || 0); setAvgResponseTime(useR.value.data.avg_response_time_ms || 0); }
      if (histR.status === 'fulfilled') setHistoryData(histR.value.data?.items || histR.value.data || []);
      if (encR.status === 'fulfilled') setRecentEncounters(encR.value.data.items || []);
      if (revR.status === 'fulfilled') setRecentReviews(revR.value.data.items || []);
    } finally { setLoading(false); }
  }, [timeRange]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    oauthApi.list().then(r => setApiClients(r.data?.clients || [])).catch(() => {});
  }, []);

  // Real time-series chart data from history API
  const chartData: ChartPoint[] = (() => {
    if (historyData.length > 0) {
      // Bucket history items by date
      const buckets: Record<string, number> = {};
      historyData.forEach(item => {
        const date = (item as any).date || (item as any).timestamp?.slice(0, 10) || (item as any).created_at?.slice(0, 10);
        if (!date) return;
        const credits = (item as any).credits_consumed || (item as any).credits || 1;
        buckets[date] = (buckets[date] || 0) + credits;
      });
      const sorted = Object.entries(buckets).sort(([a], [b]) => a.localeCompare(b));
      return sorted.map(([date, value]) => ({
        label: date.slice(5),
        value,
      }));
    }
    // No history data — return empty chart
    return [];
  })();
  const compareData: ChartPoint[] = [];

  const activeProduct = PRODUCT_TABS.find(tab => tab.key === activeTab)!;

  return (
    <div className="flex h-full bg-muted/20">
      <div className="flex-1 overflow-y-auto">
        <section className="flex w-full flex-col items-center gap-6 px-4 py-8 relative overflow-hidden">
          <div className="absolute inset-0 pointer-events-none opacity-[0.12]" style={{ backgroundImage: 'radial-gradient(circle, hsl(var(--foreground)) 1px, transparent 1px)', backgroundSize: '16px 16px' }} />
          <div className="flex w-full justify-center" role="tablist">
            <div className="relative inline-flex max-w-full overflow-x-auto rounded-[10px] bg-muted p-0.5 gap-0.5">
              {PRODUCT_TABS.map(tab => (
                <button key={tab.key} role="tab" aria-selected={activeTab === tab.key} onClick={() => setActiveTab(tab.key)}
                  className={`relative flex cursor-pointer items-center justify-center rounded-lg px-1.5 py-1 text-base transition-colors ${activeTab === tab.key ? 'text-foreground bg-popover shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>
                  {tab.label}{tab.labelSuffix && <span className="ml-1 text-[11px] px-1 py-0.5 rounded font-semibold bg-primary/10 text-primary">{tab.labelSuffix}</span>}
                </button>
              ))}
            </div>
          </div>
          <div className="flex w-full flex-col items-center gap-8">
            <div className="relative min-h-[56px] w-[640px] max-w-full text-center flex items-center"><p className="text-base text-foreground leading-relaxed">{activeProduct.description}</p></div>
            <div className="flex w-full flex-col rounded-xl border border-border bg-popover p-4 shadow-sm md:w-auto md:flex-row md:items-center md:gap-4">
              <div className="flex items-center justify-between gap-4 py-2 md:py-0">
                <a href={activeProduct.ctaLink} onClick={(e) => { e.preventDefault(); navigate(activeProduct.ctaLink); }} className="text-sm font-medium text-foreground hover:underline">{activeProduct.cta}</a>
                <a href={activeProduct.secondaryLink} onClick={(e) => { e.preventDefault(); navigate(activeProduct.secondaryLink); }} className="inline-flex items-center px-3 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors">{activeProduct.secondaryLabel}</a>
              </div>
              <div className="h-px w-full bg-border md:h-8 md:w-px" />
              <div className="flex items-center justify-between gap-4 py-2 md:py-0">
                <a href={activeProduct.buildLink} onClick={(e) => { e.preventDefault(); navigate(activeProduct.buildLink); }} className="text-sm font-medium text-foreground hover:underline">{activeProduct.buildLabel}</a>
                <a href="/developer-quickstart" onClick={(e) => { e.preventDefault(); navigate('/developer-quickstart'); }} className="inline-flex items-center px-3 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors">{t.productHubDevQuickstart}</a>
              </div>
            </div>
          </div>
        </section>

        <div className="px-6 pb-6">
          {loading && <div className="flex justify-center py-2"><Loader2 className="animate-spin h-4 w-4 text-muted-foreground" /></div>}
          <div className="flex items-center gap-2 mb-4">
            <div className="w-1 h-4 rounded-full bg-primary/40" />
            <h3 className="text-sm font-semibold text-foreground">{t.overviewSection}</h3>
          </div>
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-5"><p className="text-xs text-muted-foreground mb-1">{t.availableCredits}</p><p className="text-2xl font-bold font-mono text-foreground">{balance !== null ? formatCurrency(balance) : '--'}</p><button onClick={() => navigate('/billing')} className="text-xs text-foreground hover:underline mt-3 inline-block">{t.addCredits}</button></div>
            <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-5"><p className="text-xs text-muted-foreground mb-1">{t.totalCreditsConsumed}</p><p className="text-2xl font-bold font-mono text-foreground">{formatCurrency(consumed)}</p><button onClick={() => navigate('/usage')} className="text-xs text-foreground hover:underline mt-3 inline-block">{t.viewUsage}</button></div>
            <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-5"><p className="text-xs text-muted-foreground mb-1">{t.apiRequests}</p><p className="text-2xl font-bold font-mono text-foreground">{totalRequests.toLocaleString()}</p><span className="text-xs text-muted-foreground mt-3 inline-block">{TIME_RANGES.find(tr => tr.key === timeRange) ? t[TIME_RANGES.find(tr => tr.key === timeRange)!.labelKey] : t.last30DaysLabel}</span></div>
            <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-5"><p className="text-xs text-muted-foreground mb-1">{t.avgResponseTimeMs}</p><p className="text-2xl font-bold font-mono text-foreground">{avgResponseTime > 0 ? `${avgResponseTime.toFixed(0)}ms` : '--'}</p><span className="text-xs text-muted-foreground mt-3 inline-block">{t.milliseconds}</span></div>
          </div>
          <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-5 mb-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className="w-1 h-4 rounded-full bg-primary/40" />
                <h4 className="text-sm font-semibold text-foreground">{t.creditsConsumed}</h4>
              </div>
              <div className="flex items-center gap-2">
                {/* Time range filter — iCoDer-style dropdown */}
                <div className="relative">
                  <select
                    value={timeRange}
                    onChange={e => setTimeRange(Number(e.target.value))}
                    className="appearance-none text-xs px-2.5 py-1.5 pr-7 rounded-lg border border-border bg-card text-foreground cursor-pointer hover:border-primary/30 focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    {TIME_RANGES.map(tr => (
                      <option key={tr.key} value={tr.key}>{t[tr.labelKey]}</option>
                    ))}
                  </select>
                  <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
                </div>
                {/* API client filter — iCoDer-style dropdown */}
                {apiClients.length > 0 && (
                  <div className="relative">
                    <select
                      value={apiClientFilter}
                      onChange={e => setApiClientFilter(e.target.value)}
                      className="appearance-none text-xs px-2.5 py-1.5 pr-7 rounded-lg border border-border bg-card text-foreground cursor-pointer hover:border-primary/30 focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      <option value="all">{t.allApiClients}</option>
                      {apiClients.map((c: any) => (
                        <option key={c.client_id} value={c.client_id}>{c.client_name || c.client_id}</option>
                      ))}
                    </select>
                    <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
                  </div>
                )}
                <label className="flex items-center gap-1.5 cursor-pointer text-xs text-muted-foreground hover:text-foreground transition-colors select-none"><input type="checkbox" checked={comparePeriod} onChange={e => setComparePeriod(e.target.checked)} className="w-3.5 h-3.5 rounded border-border accent-foreground cursor-pointer" />{t.comparePeriod}</label>
                <div className="flex items-center rounded-lg border border-border p-0.5">
                  {(['daily', 'weekly', 'monthly'] as const).map(p => (
                    <button key={p} onClick={() => setChartPeriod(p)} className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors capitalize ${chartPeriod === p ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>{p === 'daily' ? t.daily : p === 'weekly' ? t.weekly : t.monthly}</button>
                  ))}
                </div>
              </div>
            </div>
            <div className="relative h-32">
              <div className="absolute inset-0 flex items-end gap-0.5">{chartData.map((pt, i) => { const maxVal = Math.max(...chartData.map(d => d.value), 0.01); return <div key={i} className="flex-1 rounded-sm bg-foreground/85 hover:bg-foreground transition-colors" style={{ height: `${Math.max(4, (pt.value / maxVal) * 100)}%` }} title={`${pt.label}: ${formatCurrency(pt.value, 3)}`} />; })}</div>
              {comparePeriod && compareData.length > 0 && <svg className="absolute inset-0 w-full h-full pointer-events-none" preserveAspectRatio="none" viewBox={`0 0 ${compareData.length} 100`}><polyline fill="none" stroke="hsl(var(--primary))" strokeWidth="1.5" strokeDasharray="3 3" strokeLinecap="round" strokeLinejoin="round" opacity="0.6" points={compareData.map((pt, i) => { const maxVal = Math.max(...chartData.map(d => d.value), 0.01); return `${i},${100 - (pt.value / maxVal) * 100}`; }).join(' ')} /></svg>}
            </div>
            {chartData.length > 0 && <div className="flex justify-between mt-2 text-[10px] text-muted-foreground">{chartData.filter((_, i) => i % Math.max(1, Math.floor(chartData.length / 5)) === 0 || i === chartData.length - 1).map((pt, i) => <span key={i}>{pt.label}</span>)}</div>}
          </div>
          {(recentEncounters.length > 0 || recentReviews.length > 0) && (
            <div className="w-full max-w-3xl">
              <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-5">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-1 h-4 rounded-full bg-primary/40" />
                  <Activity size={14} className="text-muted-foreground" /><h4 className="text-sm font-semibold text-foreground">{t.recentActivity}</h4>
                </div>
                <div className="space-y-1.5">
                  {recentEncounters.slice(0, 3).map((enc: any) => (
                    <div key={enc.id} className="flex items-center justify-between text-xs cursor-pointer hover:bg-accent/50 rounded px-2 py-1 -mx-2" onClick={() => navigate('/ai-studio/medical-coding')}>
                      <div><span className="font-mono text-muted-foreground">{enc.encounter_id || enc.id}</span><span className="ml-2 text-foreground">{enc.department || '--'}</span></div>
                      <span className="text-[10px] text-muted-foreground">{enc.created_at ? new Date(enc.created_at).toLocaleDateString(locale) : ''}</span>
                    </div>
                  ))}
                  {recentReviews.slice(0, 3).map((rev: any) => (
                    <div key={rev.id} className="flex items-center justify-between text-xs cursor-pointer hover:bg-accent/50 rounded px-2 py-1 -mx-2" onClick={() => navigate('/ai-studio/medical-coding')}>
                      <div><span className="font-mono text-muted-foreground">{rev.review_id || rev.id}</span>{rev.primary_diagnosis_name && <span className="ml-2 text-foreground truncate max-w-60 inline-block">{rev.primary_diagnosis_name}</span>}</div>
                      <span className="text-[10px] text-muted-foreground">{rev.created_at ? new Date(rev.created_at).toLocaleDateString(locale) : ''}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
