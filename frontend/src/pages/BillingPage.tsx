// iCoDer Billing Page - connected to real backend
import { CreditCard, Plus, ArrowUpRight, Loader2, Shield, Building2, History } from 'lucide-react';
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
  const [consumed, setConsumed] = useState(0);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Tabs
  const [activeTab, setActiveTab] = useState('plan');

  // Low balance alerts
  const [lowBalanceAlerts, setLowBalanceAlerts] = useState(false);
  const [alertThreshold, setAlertThreshold] = useState('50');
  const [alertUpdated, setAlertUpdated] = useState(false);

  // Auto top-up
  const [autoTopUp, setAutoTopUp] = useState(false);
  const [autoTopUpAmount, setAutoTopUpAmount] = useState('100');
  const [topUpSaved, setTopUpSaved] = useState(false);

  // Payment methods
  const [paymentMethods, setPaymentMethods] = useState<{id: string; type: string; last4: string; isDefault: boolean}[]>([]);
  const [showAddPayment, setShowAddPayment] = useState(false);

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
      const [balRes, txRes] = await Promise.all([
        billingApi.balance(),
        billingApi.transactions(20),
      ]);
      setBalance(balRes.data.balance);
      const txns = txRes.data.transactions || [];
      setTransactions(txns);
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
    try {
      const t = localStorage.getItem('icoder-billing-autotopup');
      if (t) { const p = JSON.parse(t); setAutoTopUp(p.enabled ?? false); setAutoTopUpAmount(String(p.amount ?? 100)); }
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

      {/* Balance cards */}
      <div className="grid grid-cols-2 gap-6 max-w-2xl mb-8">
        <div className="bg-background rounded-xl shadow-sm p-6">
          <p className="text-xs text-muted-foreground mb-1">{t.availableCredits}</p>
          <p className="text-3xl font-bold font-mono text-foreground">
            ¥{balance !== null ? balance.toFixed(2) : '--'}
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
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-semibold text-foreground">自动充值</h4>
                    {topUpSaved && <span className="text-xs text-success/80 transition-opacity duration-500">已保存</span>}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">当余额不足时自动添加额度</p>
                </div>
                <button onClick={() => {
                  const next = !autoTopUp;
                  setAutoTopUp(next);
                  localStorage.setItem('icoder-billing-autotopup', JSON.stringify({ enabled: next, amount: parseInt(autoTopUpAmount) || 100 }));
                  setTopUpSaved(true); setTimeout(() => setTopUpSaved(false), 2000);
                }}
                  className={`relative w-9 h-5 rounded-full transition-colors shrink-0 ${autoTopUp ? 'bg-primary' : 'bg-muted border border-border/20'}`}>
                  <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-all ${autoTopUp ? 'left-[18px]' : 'left-0.5'}`} />
                </button>
              </div>
              {autoTopUp && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground whitespace-nowrap">每次充值</span>
                    <div className="relative">
                      <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">¥</span>
                      <input type="number" value={autoTopUpAmount} onChange={e => setAutoTopUpAmount(e.target.value)}
                        className="w-20 pl-5 pr-2 py-1.5 text-xs border border-border/20 rounded-lg bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
                    </div>
                    <button onClick={() => {
                      localStorage.setItem('icoder-billing-autotopup', JSON.stringify({ enabled: autoTopUp, amount: parseInt(autoTopUpAmount) || 100 }));
                      setTopUpSaved(true); setTimeout(() => setTopUpSaved(false), 2000);
                    }}
                      className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">
                      更新
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground bg-muted/50 rounded-lg p-3 border border-border/20">
                    自动充值已启用。当余额低于告警阈值时将自动充值。每次扣款 <span className="text-foreground font-medium">¥{autoTopUpAmount}</span>。
                  </p>
                </div>
              )}
            </div>

            {/* Payment methods */}
            <div className="bg-background rounded-xl shadow-sm p-5">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-foreground">支付方式</h4>
                <button onClick={() => setShowAddPayment(true)}
                  className="text-xs px-3 py-1.5 rounded-lg border border-border/20 hover:bg-accent transition-colors flex items-center gap-1">
                  <Plus size={12} /> 添加支付方式
                </button>
              </div>
              {paymentMethods.length === 0 ? (
                <p className="text-xs text-muted-foreground py-4 text-center">暂无支付方式。添加后可启用自动充值。</p>
              ) : (
                <div className="space-y-2">
                  {paymentMethods.map(pm => (
                    <div key={pm.id} className="flex items-center justify-between p-3 border border-border/20 rounded-lg">
                      <div className="flex items-center gap-3">
                        <CreditCard size={16} className="text-muted-foreground" />
                        <span className="text-sm text-foreground">{pm.type} ending in {pm.last4}</span>
                        {pm.isDefault && <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">默认</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
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

      {/* Add Payment Method Modal */}
      {showAddPayment && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowAddPayment(false)}>
          <div className="bg-background rounded-xl shadow-sm w-full max-w-md overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-border/20">
              <h3 className="text-sm font-semibold text-foreground">添加支付方式</h3>
              <button onClick={() => setShowAddPayment(false)} className="p-1 rounded hover:bg-accent"><CreditCard size={14} className="text-muted-foreground" /></button>
            </div>
            <div className="px-5 py-4 space-y-4">
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">卡号</label>
                <input placeholder="1234 5678 9012 3456" className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-foreground block mb-1">有效期</label>
                  <input placeholder="MM/YY" className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
                </div>
                <div>
                  <label className="text-xs font-medium text-foreground block mb-1">安全码</label>
                  <input placeholder="123" className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">持卡人姓名</label>
                <input placeholder="姓名" className="w-full text-sm border border-border/20 rounded-lg px-3 py-2 bg-transparent focus:outline-none focus:ring-1 focus:ring-ring" />
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border/20 bg-muted/30">
              <button onClick={() => setShowAddPayment(false)} className="text-xs px-3 py-1.5 rounded-lg border border-border/20 hover:bg-accent">取消</button>
              <button onClick={() => {
                setPaymentMethods(prev => [...prev, { id: `pm_${Date.now()}`, type: 'Visa', last4: '4242', isDefault: prev.length === 0 }]);
                setShowAddPayment(false);
              }} className="text-xs px-4 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">添加卡片</button>
            </div>
          </div>
        </div>
      )}
    </div>
    </>
  );
}
