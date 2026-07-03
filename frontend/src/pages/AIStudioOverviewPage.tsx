// iCoDer AI Studio Overview — dynamic dashboard
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, Stethoscope, ArrowRight, Layers, Asterisk, Search, Activity } from 'lucide-react';
import { runtimeAgentApi } from '../services/runtimeApi';

export default function AIStudioOverviewPage() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<any[]>([]);
  const [recentRuns, setRecentRuns] = useState<any[]>([]);

  useEffect(() => {
    runtimeAgentApi.listAgents().then(d => setAgents((d.agents||[]).slice(0, 5))).catch(() => {});
    runtimeAgentApi.listRuns('', 5).then(d => setRecentRuns(d.runs||[])).catch(() => {});
  }, []);

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-muted/20">
      <h2 className="text-lg font-semibold text-foreground mb-4">AI Studio</h2>

      {/* Quick actions */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <button onClick={() => navigate('/ai-studio/agents')}
          className="flex items-center gap-3 p-4 bg-background rounded-xl shadow-sm ring-1 ring-border/20 hover:ring-primary/30 transition-all text-left group">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20"><Layers size={20} className="text-primary" /></div>
          <div><p className="text-sm font-medium text-foreground">AI 智能体</p><p className="text-xs text-muted-foreground">管理、创建和市场发现 Agent</p></div>
          <ArrowRight size={16} className="ml-auto text-muted-foreground opacity-0 group-hover:opacity-100" />
        </button>
        <button onClick={() => navigate('/ai-studio/medical-coding')}
          className="flex items-center gap-3 p-4 bg-background rounded-xl shadow-sm ring-1 ring-border/20 hover:ring-primary/30 transition-all text-left group">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20"><Stethoscope size={20} className="text-primary" /></div>
          <div><p className="text-sm font-medium text-foreground">医学编码</p><p className="text-xs text-muted-foreground">ICD-10/ICD-9-CM-3 智能编码</p></div>
          <ArrowRight size={16} className="ml-auto text-muted-foreground opacity-0 group-hover:opacity-100" />
        </button>
      </div>

      {/* Recent Agents */}
      {agents.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2"><Bot size={14} /> 最近 Agent</h3>
            <button onClick={() => navigate('/ai-studio/agents')} className="text-xs text-primary hover:underline">全部</button>
          </div>
          <div className="space-y-1">
            {agents.map(a => (
              <div key={a.agent_ref} onClick={() => navigate('/ai-studio/agents/' + a.agent_ref)}
                className="flex items-center gap-3 px-3 py-2 bg-background rounded-lg shadow-sm ring-1 ring-border/20 hover:bg-accent cursor-pointer text-xs">
                <span className="font-medium text-foreground">{a.name}</span>
                <span className="text-muted-foreground font-mono text-[10px]">v{a.version}</span>
                <span className={`ml-auto px-1.5 py-0.5 rounded-full text-[9px] ${a.status === 'enabled' ? 'bg-green-100 text-green-700' : 'bg-muted text-muted-foreground'}`}>{a.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Runs */}
      {recentRuns.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2"><Activity size={14} /> 最近运行</h3>
          </div>
          <div className="space-y-1">
            {recentRuns.map((r: any, i) => (
              <div key={i} className="flex items-center gap-3 px-3 py-2 bg-background rounded-lg shadow-sm ring-1 ring-border/20 text-xs">
                <span className="font-mono text-[10px] text-muted-foreground">{r.run_id?.slice(0,12)||'—'}</span>
                <span className="text-foreground">{r.agent_ref||'—'}</span>
                <span className="ml-auto text-muted-foreground">{r.status||'—'}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
