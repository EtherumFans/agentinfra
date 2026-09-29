import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { agentHubApi } from '../../services/agentHubApi';
import { useAuthStore } from '../../store';

export function useRuntimeReadiness(agentId: string) {
  const org = useAuthStore(s => s.currentOrgId);
  const [state, setState] = useState({ org, enabled: false, reason: '正在检查当前组织的运行配置…' });
  const [revision, refresh] = useState(0);
  useEffect(() => {
    let active = true;
    setState({ org, enabled: false, reason: '正在检查当前组织的运行配置…' });
    agentHubApi.listWithTenantReadiness().then(response => {
      if (!active) return;
      const readiness = response.data.agents.find(item => item.agent_id === agentId)?.runtime_readiness;
      setState({ org, enabled: readiness?.run_action_enabled === true,
        reason: readiness?.reason || 'tenant_runtime_readiness_unavailable' });
    }).catch(() => { if (active) setState({ org, enabled: false, reason: '无法读取运行配置，请重试或联系管理员。' }); });
    return () => { active = false; };
  }, [org, agentId, revision]);
  return { ...state, enabled: state.org === org && state.enabled, refresh: () => refresh(value => value + 1) };
}

export default function RuntimeReadinessNotice({ state }: { state: ReturnType<typeof useRuntimeReadiness> }) {
  if (state.enabled) return null;
  return <div role="status" className="rounded-lg border border-border bg-muted p-3 text-sm text-foreground">
    <p>当前组织暂不能运行此分析。请管理员检查模型配置、凭据与连接状态；配置完成后重新检查。</p>
    <p className="mt-1 text-xs text-muted-foreground">原因：{state.reason}</p>
    <div className="mt-2 flex gap-4"><Link to="/models" className="text-primary underline">查看模型配置</Link>
      <button type="button" onClick={state.refresh} className="text-primary underline">重新检查</button></div>
  </div>;
}
