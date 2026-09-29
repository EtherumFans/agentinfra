import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import api from '../../services/api';
import {useAuthStore} from '../../store';
export default function AgentWorkflow({agentId}:{agentId:string}){
 const org=useAuthStore(s=>s.currentOrgId),[state,setState]=useState<any>(null),[error,setError]=useState(false);
 useEffect(()=>{const c=new AbortController();setState(null);setError(false);api.get(`/rest/v1/agent_definitions/${agentId}/releases`,{signal:c.signal}).then(r=>{if(!c.signal.aborted)setState(r.data);}).catch(()=>{if(!c.signal.aborted)setError(true);});return ()=>c.abort();},[agentId,org]);
 const base=`/ai-studio/agents/${agentId}`;
 const steps=[['创建',base,'已创建'],['调试',base+'/releases','调试已保存草稿'],['评测',base+'/evaluations',state?state.evaluation_gate?.passed?'当前草稿已通过':'待有效评测':'读取中'],['发布',base+'/releases',state?.active_version?`默认 ${state.active_version}`:state?'尚未发布':'读取中'],['接入',base+'/integration',state?.active_version?'打开接入向导':'先完成发布'],['运行运营',`/operations?agent_id=${encodeURIComponent(agentId)}`,'统计、任务与执行证据']];
 return <nav aria-label="智能体交付流程" className="m-3 p-3 border rounded-xl bg-background"><ol className="flex flex-wrap gap-3">{steps.map(([name,url,detail],i)=><li key={name}><Link className="text-primary text-sm" to={url}>{i+1}. {name}</Link><p className="text-xs text-muted-foreground">{detail}</p></li>)}</ol>{error&&<p className="text-xs">发布状态暂不可用，请在版本管理中重试。</p>}{state?.draft_changed&&<p className="text-xs mt-2">存在未发布修改；接入调用仍使用已发布版本。</p>}</nav>;
}
