import { useState, useEffect } from 'react';
import { Loader2, Users } from 'lucide-react';
import { a2aApi } from '../services/api';

interface Props {
  currentAgentId: string;
}

export default function A2ACollaboration({ currentAgentId }: Props) {
  const [discoveredAgents, setDiscoveredAgents] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    a2aApi.discoverAgents().then(r => {
      const agents = r.data.agents || [];
      setDiscoveredAgents(agents.filter((a: any) => a.id !== currentAgentId));
    }).catch(() => {}).finally(() => setLoading(false));
  }, [currentAgentId]);

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
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {discoveredAgents.slice(0, 8).map((a: any) => (
              <div key={a.id || a.name}
                className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-accent">
                <Users size={10} />
                <span className="font-medium">{a.name}</span>
                <span className="text-[9px] text-muted-foreground ml-auto">v{a.version || '?'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
