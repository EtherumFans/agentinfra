// iCoDer Console Home — Clinical AI Workbench
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, Stethoscope, Layers, BrainCircuit, Plus, Play, Upload, Code, ChevronDown, Loader2, TrendingUp } from 'lucide-react';
import { billingApi } from '../services/api';
import { runtimeApi } from '../services/runtimeApi';
import { useT } from '../i18n';

export default function HomePage() {
  const t = useT();
  const navigate = useNavigate();
  const [balance, setBalance] = useState<number | null>(null);
  const [agentCount, setAgentCount] = useState(0);
  const [certifiedCount, setCertifiedCount] = useState(0);
  const [recentAgents, setRecentAgents] = useState<any[]>([]);
  const [showUsage, setShowUsage] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      billingApi.balance().then(r => setBalance(r.data.balance)).catch(() => {}),
      runtimeApi.listAgents().then(d => {
        const all = d.agents || [];
        setAgentCount(all.length);
        setCertifiedCount(all.filter((a: any) => a.agent_type === 'certified').length);
        setRecentAgents(all.slice(0, 5));
      }).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  const formatCurrency = (v: number) => `¥${v.toFixed(2)}`;

  return (
    <div className="flex h-full bg-muted/20">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">

          {/* Hero */}
          <div className="text-center mb-2">
            <h1 className="text-2xl font-bold text-foreground tracking-tight">收入合规 AI 工作台</h1>
            <p className="text-sm text-muted-foreground mt-2">管理医学编码 Agent，追踪合规审核结果，连接 HIS/EMR 系统</p>
          </div>

          {/* Feature cards */}
          <div className="grid grid-cols-2 gap-4">
            <button onClick={() => navigate('/ai-studio/agents')}
              className="group flex items-start gap-4 p-5 bg-background rounded-xl shadow-sm ring-1 ring-border/20 hover:ring-primary/30 hover:shadow-md transition-all text-left">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20 transition-colors">
                <Layers size={20} className="text-primary" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">Agent 工作台</p>
                <p className="text-xs text-muted-foreground mt-1">{agentCount} 个 Agent 已安装 · 管理 · 评估 · 市场</p>
              </div>
            </button>
            <button onClick={() => navigate('/ai-studio/medical-coding')}
              className="group flex items-start gap-4 p-5 bg-background rounded-xl shadow-sm ring-1 ring-border/20 hover:ring-primary/30 hover:shadow-md transition-all text-left">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20 transition-colors">
                <Stethoscope size={20} className="text-primary" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">医学编码</p>
                <p className="text-xs text-muted-foreground mt-1">ICD-10/ICD-9-CM-3 · 真实 LLM 驱动 · 规则引擎校验</p>
              </div>
            </button>
          </div>

          {/* Agent overview stats */}
          {!loading && (
            <div className="grid grid-cols-4 gap-3">
              <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-4 text-center">
                <p className="text-2xl font-bold text-foreground">{agentCount}</p>
                <p className="text-[11px] text-muted-foreground mt-1">已安装 Agent</p>
              </div>
              <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-4 text-center">
                <p className="text-2xl font-bold text-foreground">{certifiedCount}</p>
                <p className="text-[11px] text-muted-foreground mt-1">iCoDer 认证</p>
              </div>
              <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-4 text-center">
                <p className="text-2xl font-bold text-foreground">{agentCount - certifiedCount}</p>
                <p className="text-[11px] text-muted-foreground mt-1">社区 Agent</p>
              </div>
              <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-4 text-center">
                <p className="text-2xl font-bold text-foreground">{balance !== null ? formatCurrency(balance) : '--'}</p>
                <p className="text-[11px] text-muted-foreground mt-1">可用额度</p>
              </div>
            </div>
          )}

          {/* Recent agents */}
          {recentAgents.length > 0 && (
            <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2"><Bot size={14} className="text-primary" /> Agent 列表</h3>
                <button onClick={() => navigate('/ai-studio/agents')} className="text-xs text-primary hover:underline">全部</button>
              </div>
              <div className="space-y-1">
                {recentAgents.map((a: any) => (
                  <div key={a.agent_ref} onClick={() => navigate('/ai-studio/agents/' + a.agent_ref)}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-accent cursor-pointer transition-colors group">
                    <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20">
                      <Bot size={14} className="text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{a.name}</p>
                      <p className="text-[10px] text-muted-foreground">{a.description?.slice(0, 60) || a.category}</p>
                    </div>
                    <span className="text-[10px] font-mono text-muted-foreground">v{a.version}</span>
                    <span className={`px-1.5 py-0.5 rounded-full text-[9px] ${a.status === 'enabled' ? 'bg-green-100 text-green-700' : 'bg-muted text-muted-foreground'}`}>
                      {a.status}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-medium ${a.tier >= 3 ? 'bg-red-100 text-red-700' : a.tier >= 2 ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'}`}>
                      T{a.tier}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Quick actions */}
          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={() => navigate('/ai-studio/agents/new')}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">
              <Plus size={14} /> 新建 Agent
            </button>
            <button onClick={() => navigate('/evaluation')}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border border-border hover:bg-accent transition-colors">
              <Play size={14} /> 运行评估
            </button>
            <button onClick={() => navigate('/developer-quickstart')}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border border-border hover:bg-accent transition-colors">
              <Code size={14} /> SDK 集成
            </button>
          </div>

          {/* Usage (collapsible) */}
          <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 overflow-hidden">
            <button onClick={() => setShowUsage(!showUsage)}
              className="w-full flex items-center justify-between px-5 py-3 hover:bg-accent/30 transition-colors">
              <span className="text-xs font-semibold text-foreground flex items-center gap-2">
                <TrendingUp size={14} className="text-muted-foreground" /> 用量概览
              </span>
              <ChevronDown size={14} className={`text-muted-foreground transition-transform ${showUsage ? 'rotate-180' : ''}`} />
            </button>
            {showUsage && (
              <div className="px-5 pb-4 grid grid-cols-3 gap-4 border-t border-border pt-4">
                <div>
                  <p className="text-[10px] text-muted-foreground">可用额度</p>
                  <p className="text-lg font-bold font-mono">{balance !== null ? formatCurrency(balance) : '--'}</p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground">已安装 Agent</p>
                  <p className="text-lg font-bold font-mono">{agentCount}</p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground">认证 Agent</p>
                  <p className="text-lg font-bold font-mono">{certifiedCount}</p>
                </div>
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
