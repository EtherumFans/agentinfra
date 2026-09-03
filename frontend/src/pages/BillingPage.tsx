// iCoDer Billing Page - honest local-ledger simulation until payment integration.
import { CreditCard, Plus, ArrowUpRight, Loader2, Shield, Building2, History, AlertTriangle, RefreshCw } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import { useT } from '../i18n';
import { billingApi } from '../services/api';

const BILLING_TABS = [
  { key: 'plan', label: '套餐计划', icon: Shield },
  { key: 'history', label: '账单历史', icon: History },
  { key: 'business', label: '企业信息', icon: Building2 },
];

export default function BillingPage() {
  const t = useT();
  const navigate = useNavigate();
  const [balance, setBalance] = useState<number | null>(null);
  const [available, setAvailable] = useState<number | null>(null);
  const [reserved, setReserved] = useState(0);
  const [simulation, setSimulation] = useState(false);
  const [consumed, setConsumed] = useState(0);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [settlements, setSettlements] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reconciling, setReconciling] = useState(false);
  const [reconcileMessage, setReconcileMessage] = useState('');

  // Tabs
  const [activeTab, setActiveTab] = useState('plan');

  // Low balance alerts
  const [lowBalanceAlerts, setLowBalanceAlerts] = useState(false);
  const [alertThreshold, setAlertThreshold] = useState('50');
  const [alertUpdated, setAlertUpdated] = useState(false);

  // Business info
  const [businessInfo, setBusinessInfo] = useState({
    companyName: '',
    billingEmail: '',
    taxId: '',
    address: '',
  });
  const [savingBusinessInfo, setSavingBusinessInfo] = useState(false);
  const [businessSaved, setBusinessSaved] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [balRes, txRes, settlementRes] = await Promise.all([
        billingApi.balance(),
        billingApi.transactions(20),
        billingApi.runSettlements(20),
      ]);
      setBalance(balRes.data.balance);
      setAvailable(balRes.data.available);
      setReserved(balRes.data.reserved);
      setSimulation(balRes.data.simulation);
      const txns = txRes.data.transactions || [];
      setTransactions(txns);
      setSettlements(settlementRes.data.items || []);
      const debits = txns.filter((t: any) => t.type === 'debit');
      setConsumed(Math.abs(debits.reduce((sum: number, t: any) => sum + parseFloat(t.amount), 0)));
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || '加载计费数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Load billing settings from localStorage
  useEffect(() => {
    try {
      const a = localStorage.getItem('icoder-billing-alerts');
      if (a) { const p = JSON.parse(a); setLowBalanceAlerts(p.enabled ?? false); setAlertThreshold(String(p.threshold ?? 50)); }
    } catch {}
  }, []);

  const handleAddCredits = async () => {
    try {
      const res = await billingApi.addCredits(50);
      setBalance(res.data.new_balance);
      fetchData(); // refresh transactions
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || '添加额度失败');
    }
  };

  const handleReconcileStale = async () => {
    if (!window.confirm('协调超过 1 小时且没有活跃 Run 的本地预授权；结算中记录只转为可重试，不免除成本。继续？')) return;
    setReconciling(true);
    setReconcileMessage('');
    try {
      const result = await billingApi.reconcileStaleRunSettlements(3600);
      setReconcileMessage(
        `已检查 ${result.data.inspected} 条，释放 ${result.data.released} 条，将 ${result.data.marked_retryable} 条结算转为可重试，跳过活跃 Run ${result.data.skipped_active} 条。`,
      );
      await fetchData();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setReconcileMessage(
        typeof detail === 'string' ? detail : detail?.code || err.message || '协调失败',
      );
    } finally {
      setReconciling(false);
    }
  };

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
    <>
    <div className="bg-muted/20 min-h-dvh p-6">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-foreground mb-2">{t.billingTitle}</h2>
        <p className="text-sm text-muted-foreground">{t.billingDesc}</p>
      </div>

      {simulation && (
        <div className="max-w-2xl mb-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 flex items-start gap-2 text-amber-900">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <p className="text-xs leading-relaxed">
            当前为本地开发账本模拟，不连接支付机构、不生成正式发票，也不会自动扣款。Agent Run 预授权与结算仅用于开发环境验证。
          </p>
        </div>
      )}

      {/* Balance cards */}
      <div className="grid grid-cols-2 gap-6 max-w-2xl mb-8">
        <div className="bg-background rounded-xl shadow-sm p-6">
          <p className="text-xs text-muted-foreground mb-1">{t.availableCredits}</p>
          <p className="text-3xl font-bold font-mono text-foreground">
            ¥{available !== null ? available.toFixed(2) : '--'}
          </p>
          <p className="text-[11px] text-muted-foreground mt-2 font-mono">
            账本 ¥{balance?.toFixed(2) ?? '--'} · 预授权占用 ¥{reserved.toFixed(2)}
          </p>
          <button onClick={handleAddCredits} className="bg-primary text-primary-foreground rounded-lg flex items-center gap-2 mt-4 px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors">
            <Plus size={16} /> {t.addCredits}
          </button>
        </div>
        <div className="bg-background rounded-xl shadow-sm p-6">
          <p className="text-xs text-muted-foreground mb-1">{t.creditsConsumed} ({t.last30DaysLabel})</p>
          <p className="text-3xl font-bold font-mono text-foreground">¥{consumed.toFixed(2)}</p>
          <button
            onClick={() => navigate('/usage')}
            className="text-sm text-foreground hover:underline mt-4 flex items-center gap-1"
          >
            {t.viewUsage} <ArrowUpRight size={14} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="w-full">
        <div className="flex items-center gap-1 border-b border-border/20 mb-6">
          {BILLING_TABS.map(tab => (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}>
              <tab.icon size={14} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Plan tab */}
        {activeTab === 'plan' && (
          <div className="space-y-6 w-full">
            {/* Low balance alerts */}
            <div className="bg-background rounded-xl shadow-sm p-5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-semibold text-foreground">余额不足提醒</h4>
                  {alertUpdated && <span className="text-xs text-success/80 transition-opacity duration-500">已保存</span>}
                </div>
                <button onClick={() => {
                  const next = !lowBalanceAlerts;
                  setLowBalanceAlerts(next);
                  localStorage.setItem('icoder-billing-alerts', JSON.stringify({ enabled: next, threshold: parseInt(alertThreshold) || 50 }));
                  setAlertUpdated(true); setTimeout(() => setAlertUpdated(false), 2000);
                }}
                  className={`relative w-9 h-5 rounded-full transition-colors shrink-0 ${lowBalanceAlerts ? 'bg-primary' : 'bg-muted border border-border/20'}`}>
                  <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-all ${lowBalanceAlerts ? 'left-[18px]' : 'left-0.5'}`} />
                </button>
              </div>
              <p className="text-xs text-muted-foreground mb-3">当余额低于阈值时发送邮件通知。</p>
              {lowBalanceAlerts && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground whitespace-nowrap">余额低于</span>
                  <div className="relative">
                    <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">¥</span>
                    <input type="number" value={alertThreshold} onChange={e => setAlertThreshold(e.target.value)}
                      className="w-20 pl-5 pr-2 py-1.5 text-xs border border-border/20 rounded-lg bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
                  </div>
                  <button onClick={() => {
                    localStorage.setItem('icoder-billing-alerts', JSON.stringify({ enabled: lowBalanceAlerts, threshold: parseInt(alertThreshold) || 50 }));
                    setAlertUpdated(true); setTimeout(() => setAlertUpdated(false), 2000);
                  }}
                    className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">
                    更新
                  </button>
                </div>
              )}
            </div>

            {/* Auto top-up */}
            <div className="bg-background rounded-xl shadow-sm p-5">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h4 className="text-sm font-semibold text-foreground">自动充值</h4>
                  <p className="text-xs text-muted-foreground mt-0.5">当余额不足时自动添加额度</p>
                </div>
                <button disabled title="尚未接入支付机构"
                  className="relative w-9 h-5 rounded-full shrink-0 bg-muted border border-border/20 opacity-50 cursor-not-allowed">
                  <div className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm" />
                </button>
              </div>
              <p className="text-xs text-amber-700">尚未接入真实支付机构；此功能不可用。</p>
            </div>

            {/* Payment methods */}
            <div className="bg-background rounded-xl shadow-sm p-5">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-foreground">支付方式</h4>
                <button disabled title="尚未接入支付机构"
                  className="text-xs px-3 py-1.5 rounded-lg border border-border/20 flex items-center gap-1 opacity-50 cursor-not-allowed">
                  <Plus size={12} /> 添加支付方式
                </button>
              </div>
              <p className="text-xs text-muted-foreground py-4 text-center">尚未接入支付方式管理。</p>
            </div>
          </div>
        )}

        {/* Billing History tab */}
        {activeTab === 'history' && (
          <div className="w-full">
            <h3 className="text-sm font-semibold text-foreground mb-3">{t.transactionHistory}</h3>
            <div className="bg-background rounded-xl shadow-sm overflow-hidden">
              {transactions.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground text-sm">暂无交易记录</div>
              ) : (
                transactions.map((tx: any) => (
                  <div key={tx.id} className="flex items-center justify-between p-4 border-b border-border/20 last:border-0 hover:bg-accent/50 transition-colors">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center ${tx.type === 'credit' ? 'bg-success/10' : 'bg-accent'}`}>
                        <CreditCard size={14} className={tx.type === 'credit' ? 'text-success' : 'text-muted-foreground'} />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-foreground">{tx.description}</p>
                        <p className="text-xs text-muted-foreground">{tx.date}</p>
                      </div>
                    </div>
                    <span className={`text-sm font-mono font-medium ${tx.type === 'credit' ? 'text-success' : 'text-foreground'}`}>
                      {tx.amount}
                    </span>
                  </div>
                ))
              )}
            </div>
            <div className="mt-6 mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Agent Run 预授权与结算</h3>
                {reconcileMessage && <p className="text-[11px] text-muted-foreground mt-1">{reconcileMessage}</p>}
              </div>
              {simulation && (
                <button
                  onClick={handleReconcileStale}
                  disabled={reconciling}
                  className="text-xs px-3 py-1.5 rounded-lg border border-border/20 flex items-center gap-1.5 hover:bg-accent disabled:opacity-50"
                  title="跳过仍处于活跃生命周期的 Run"
                >
                  <RefreshCw size={12} className={reconciling ? 'animate-spin' : ''} />
                  协调陈旧预授权
                </button>
              )}
            </div>
            <div className="bg-background rounded-xl shadow-sm overflow-hidden">
              {settlements.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground text-sm">暂无结算记录</div>
              ) : settlements.map((item: any) => (
                <div key={item.run_id} className="p-4 border-b border-border/20 last:border-0 flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-xs font-mono text-foreground truncate">{item.run_id}</p>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      预授权 ¥{Number(item.reserved_amount).toFixed(6)} · 结算 ¥{Number(item.settled_amount).toFixed(6)}
                    </p>
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded font-mono ${
                    item.status === 'SETTLED'
                      ? 'bg-green-100 text-green-700'
                      : item.status === 'RELEASED'
                      ? 'bg-slate-100 text-slate-700'
                      : item.status === 'SETTLEMENT_FAILED'
                      ? 'bg-red-100 text-red-700'
                      : 'bg-amber-100 text-amber-700'
                  }`}>
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Business info tab */}
        {activeTab === 'business' && (
          <div className="w-full">
            <div className="bg-background rounded-xl shadow-sm p-5">
              <h4 className="text-sm font-semibold text-foreground mb-4">企业信息</h4>
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-foreground block mb-1">公司名称</label>
                  <input value={businessInfo.companyName} onChange={e => setBusinessInfo(p => ({...p, companyName: e.target.value}))}
                    placeholder="您的公司名称" className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
                </div>
                <div>
                  <label className="text-xs font-medium text-foreground block mb-1">账单邮箱</label>
                  <input value={businessInfo.billingEmail} onChange={e => setBusinessInfo(p => ({...p, billingEmail: e.target.value}))}
                    type="email" placeholder="billing@company.com" className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
                </div>
                <div>
                  <label className="text-xs font-medium text-foreground block mb-1">税号</label>
                  <input value={businessInfo.taxId} onChange={e => setBusinessInfo(p => ({...p, taxId: e.target.value}))}
                    placeholder="税号 / VAT 号" className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
                </div>
                <div>
                  <label className="text-xs font-medium text-foreground block mb-1">地址</label>
                  <textarea value={businessInfo.address} onChange={e => setBusinessInfo(p => ({...p, address: e.target.value}))}
                    placeholder="街道、城市、邮编、国家" rows={3}
                    className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring resize-none" />
                </div>
                <div className="pt-2">
                  <button onClick={() => {
                    setSavingBusinessInfo(true);
                    setTimeout(() => {
                      setSavingBusinessInfo(false);
                      setBusinessSaved(true);
                      setTimeout(() => setBusinessSaved(false), 3000);
                    }, 800);
                  }} disabled={savingBusinessInfo}
                    className="bg-primary text-primary-foreground rounded-lg text-sm px-4 py-2 font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                    {savingBusinessInfo ? <Loader2 size={14} className="animate-spin" /> : null}
                    {businessSaved ? '已保存！' : '保存企业信息'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

    </div>
    </>
  );
}
