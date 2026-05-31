import { useState, useEffect } from 'react';
import { GitBranch, Play, Loader2, ArrowRight, Users, Zap } from 'lucide-react';
import { a2aApi, agentsApi } from '../services/api';

interface Props {
  currentAgentId: string;
}

export default function A2ACollaboration({ currentAgentId }: Props) {
  const [discoveredAgents, setDiscoveredAgents] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [chainInput, setChainInput] = useState('');
  const [chainResult, setChainResult] = useState<string | null>(null);
  const [chainRunning, setChainRunning] = useState(false);
  const [selectedChain, setSelectedChain] = useState<string[]>([]);
  const [coordinateResult, setCoordinateResult] = useState<any>(null);

  useEffect(() => {
    setLoading(true);
    a2aApi.discoverAgents().then(r => {
      const agents = r.data.agents || [];
      setDiscoveredAgents(agents.filter((a: any) => a.name !== currentAgentId));
    }).catch(() => {}).finally(() => setLoading(false));
  }, [currentAgentId]);

  const toggleChain = (name: string) => {
    setSelectedChain(prev => prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]);
  };

  const runChain = async () => {
    if (!chainInput.trim() || selectedChain.length === 0) return;
    setChainRunning(true); setChainResult(null);
    try {
      const r = await a2aApi.chain({ input: chainInput, agent_names: selectedChain });
      const data = r.data as any;
      setChainResult(data.output || data.result || JSON.stringify(data, null, 2));
    } catch (err: any) {
      setChainResult(`错误: ${err.message || '链式调用失败'}`);
    }
    setChainRunning(false);
  };

  const runCoordinate = async () => {
    if (!chainInput.trim()) return;
    setChainRunning(true); setCoordinateResult(null);
    try {
      const r = await a2aApi.coordinate({ input: chainInput });
      setCoordinateResult(r.data);
    } catch (err: any) {
      setCoordinateResult({ error: err.message });
    }
    setChainRunning(false);
  };

  return (
    <div className="border-t border-border/20">
      <div className="flex items-center gap-2 px-4 pt-4 pb-2">
        <div className="w-1 h-4 rounded-full bg-primary/40" />
        <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">A2A Agent 协作</h3>
        {discoveredAgents.length > 0 && (
          <span className="text-[10px] text-muted-foreground/50 ml-auto">{discoveredAgents.length} 个可用</span>
        )}
      </div>
      <div className="px-4 pb-4 space-y-3">
        {loading ? (
          <div className="text-center py-4"><Loader2 className="animate-spin h-4 w-4 mx-auto text-muted-foreground" /></div>
        ) : discoveredAgents.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40 text-center py-2">未发现其他 Agent（需启用 A2A）</p>
        ) : (
          <>
            {/* Discovered agents */}
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {discoveredAgents.slice(0, 8).map((a: any) => (
                <div key={a.name} onClick={() => toggleChain(a.name)}
                  className={`flex items-center gap-2 text-xs py-1 px-2 rounded cursor-pointer transition-colors ${selectedChain.includes(a.name) ? 'bg-primary/10 ring-1 ring-primary/20' : 'hover:bg-accent'}`}>
                  <input type="checkbox" checked={selectedChain.includes(a.name)} readOnly className="w-3 h-3" />
                  <span className="font-medium">{a.name}</span>
                  <span className="text-[9px] text-muted-foreground ml-auto">v{a.version || '?'}</span>
                </div>
              ))}
            </div>

            {/* Chain input */}
            <textarea value={chainInput} onChange={e => setChainInput(e.target.value)}
              placeholder="输入任务描述，将按顺序传递给选中的 Agent..."
              className="w-full h-16 text-xs border border-border/60 rounded-lg p-2 bg-background resize-none focus:outline-none focus:ring-1 focus:ring-ring"
            />

            {/* Chain and Coordinate buttons */}
            <div className="flex gap-2">
              <button onClick={runChain} disabled={chainRunning || selectedChain.length === 0 || !chainInput.trim()}
                className="flex-1 inline-flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors">
                <GitBranch size={12} /> 链式调用 ({selectedChain.length})
              </button>
              <button onClick={runCoordinate} disabled={chainRunning || !chainInput.trim()}
                className="flex-1 inline-flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium border border-border hover:bg-accent disabled:opacity-50 transition-colors">
                <Zap size={12} /> 并行协调
              </button>
            </div>

            {/* Chain visualization */}
            {selectedChain.length > 0 && (
              <div className="flex items-center gap-1 text-[9px] text-muted-foreground flex-wrap">
                <Users size={10} />{selectedChain.map((name, i) => (<span key={i}>{i > 0 && <ArrowRight size={8} className="inline mx-0.5" />}{name}</span>))}
              </div>
            )}

            {/* Chain result */}
            {chainResult && (
              <div className="bg-muted/50 rounded-lg p-2 text-[10px] font-mono text-foreground max-h-24 overflow-y-auto border border-border/20">
                <p className="text-[9px] text-muted-foreground mb-0.5">链式调用结果:</p>
                {chainResult}
              </div>
            )}
            {coordinateResult && (
              <div className="bg-muted/50 rounded-lg p-2 text-[10px] text-foreground max-h-24 overflow-y-auto border border-border/20">
                <p className="text-[9px] text-muted-foreground mb-0.5">并行协调结果:</p>
                {JSON.stringify(coordinateResult, null, 1)}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
