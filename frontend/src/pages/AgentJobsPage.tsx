import AgentWorkflow from '../components/agents/AgentWorkflow';
import TaskInputEditor, {validateTaskInput} from '../components/agents/TaskInputEditor';
import {useEffect,useRef,useState} from 'react';
import {Link,useParams,useSearchParams} from 'react-router-dom';
import api from '../services/api';
import {useAuthStore} from '../store';
const notificationLabels:Record<string,string>={none:'未启用',pending:'等待发送',delivered:'已送达',failed:'发送失败'};
const labels:Record<string,string>={queued:'排队中',running:'执行中',completed:'已返回结果',failed:'执行失败',interrupted:'执行中断，需核对结果',cancelled:'已取消'};
export default function AgentJobsPage(){
 const {agentId}=useParams();const [params]=useSearchParams();const version=params.get('version');const org=useAuthStore(s=>s.currentOrgId);
 const [manifest,setManifest]=useState<any>(null),[jobs,setJobs]=useState<any[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [inputs,setInputs]=useState(JSON.stringify([{text:'合成软件测试文书，无真实患者。请标注缺失资料。'}],null,2)),[callback,setCallback]=useState(''),[result,setResult]=useState<any>(null);
 const [page,setPage]=useState(0),[search,setSearch]=useState(''),[query,setQuery]=useState(''),[state,setState]=useState(''),[more,setMore]=useState(false);
 const queryIdentity=`${org}:${agentId}:${page}:${query}:${state}`;const latestQuery=useRef(queryIdentity);latestQuery.current=queryIdentity;const listSequence=useRef(0);
 const pendingKey=useRef<string | null>(null),controller=useRef<AbortController | null>(null);
 async function refresh(c=controller.current){const identity=queryIdentity;const sequence=++listSequence.current;try{const r=await api.get('/v1/agent-jobs',{params:{agent_id:agentId,limit:20,offset:page*20,q:query,state:state||undefined},signal:c?.signal});if(!c?.signal.aborted&&identity===latestQuery.current&&sequence===listSequence.current){setJobs(r.data.jobs);setMore(!!r.data.has_more);}}catch{if(!c?.signal.aborted&&identity===latestQuery.current&&sequence===listSequence.current)setError('无法读取任务状态。');}}
 useEffect(()=>{const c=new AbortController();controller.current=c;setManifest(null);setJobs([]);setPage(0);setQuery('');setSearch('');setState('');setError('');setResult(null);setCallback('');setInputs(JSON.stringify([{text:'合成软件测试文书，无真实患者。请标注缺失资料。'}],null,2));pendingKey.current=null;
 api.get(`/rest/v1/agent_definitions/${agentId}/integration`,{params:version?{version}:undefined,signal:c.signal}).then(r=>{if(!c.signal.aborted)setManifest(r.data);}).catch(()=>{if(!c.signal.aborted)setError('请先发布智能体。');});refresh(c);return ()=>c.abort();},[agentId,org,version]);
 useEffect(()=>{const c=new AbortController();setJobs([]);void refresh(c);return ()=>c.abort();},[page,query,state,agentId,org]);
 useEffect(()=>{if(!jobs.some(j=>['queued','running'].includes(j.state)||j.notification_state==='pending'))return;const timer=setInterval(()=>refresh(),3000);return ()=>clearInterval(timer);},[jobs,agentId,page,query,state]);
 async function submit(){const c=controller.current;if(!manifest)return;const validation=validateTaskInput(inputs,'jobs');if(validation){setError(validation);return;}let parsed;try{parsed=JSON.parse(inputs);if(!Array.isArray(parsed)||!parsed.length)throw Error();}catch{setError('请输入文书对象组成的 JSON 数组。');return;}
 setBusy(true);setError('');pendingKey.current ||= crypto.randomUUID();try{await api.post(`/v1/agents/${agentId}/jobs`,{inputs:parsed,purpose_of_use:'quality_improvement',expected_agent_version:manifest.version,expected_configuration_digest:manifest.configuration_digest,callback_url:callback||null},{headers:{'Idempotency-Key':pendingKey.current},signal:c?.signal});if(c?.signal.aborted)return;pendingKey.current=null;await refresh(c);}catch{if(!c?.signal.aborted)setError('提交未确认。可重试同一批资料；若更改资料，将使用新的提交标识。请检查发布版本、队列容量及回调注册配置。');}finally{if(!c?.signal.aborted)setBusy(false);}}
 async function action(id:string,kind:string){const c=controller.current;setError('');try{if(kind==='result'){const r=await api.get(`/v1/agent-jobs/${id}`,{signal:c?.signal});if(!c?.signal.aborted)setResult(r.data);}else{await api.post(`/v1/agent-jobs/${id}/${kind}`,null,{signal:c?.signal});await refresh(c);}}catch{if(!c?.signal.aborted)setError('操作未完成，请刷新任务状态。');}}
 return <div className="p-5 max-w-5xl mx-auto h-full overflow-auto space-y-4"><Link className="text-primary" to={`/ai-studio/agents/${agentId}/integration`}>返回集成向导</Link><h1 className="text-xl font-semibold">异步与批量任务</h1>{agentId&&<AgentWorkflow agentId={agentId}/>}
 <p>提交后可关闭页面，服务端继续处理。每批最多 20 份文书，创建时固定发布版本。结果需人工复核；执行中断时先核对运行记录。</p>{error&&<p role="alert">{error}</p>}
 <section className="inspector-card space-y-3"><p>发布版本：{manifest?.version || '读取中'}</p><TaskInputEditor key={org+String(agentId)} kind="jobs" value={inputs} disabled={busy} onChange={value=>{setInputs(value);pendingKey.current=null;}}/>
 <label className="block">结果通知地址（可选）<input aria-label="结果通知地址" disabled={busy} className="w-full border rounded-md bg-background p-2" value={callback} onChange={e=>{setCallback(e.target.value);pendingKey.current=null;}}/></label><p className="text-xs">地址须由部署管理员为当前组织注册为 HTTPS 回调。通知带签名，仅包含任务标识和状态，结果通过授权接口读取。</p>
 <button disabled={busy||!manifest} className="bg-primary text-primary-foreground px-4 py-2" onClick={submit}>{busy?'提交中…':'提交异步任务'}</button></section>
 <div className="flex justify-between"><h2 className="font-semibold">我的任务</h2><button onClick={()=>refresh()}>刷新状态</button></div>
 <form className="flex flex-wrap gap-2" onSubmit={e=>{e.preventDefault();setPage(0);setQuery(search);}}><input aria-label="任务搜索" placeholder="任务标识或版本" className="border rounded-md p-2 bg-background" value={search} onChange={e=>setSearch(e.target.value)}/><select aria-label="任务状态筛选" value={state} onChange={e=>{setState(e.target.value);setPage(0);}}><option value="">全部状态</option>{Object.entries(labels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select><button>搜索</button></form>
 {!jobs.length&&<p>暂无匹配任务。</p>}
 {jobs.map(j=><section key={j.id} className="inspector-card space-y-2"><p>{labels[j.state] || j.state} · 版本 {j.version}</p><p className="text-xs break-all">{j.id} · 批次 {j.batch_id} · 第 {j.item_index+1} 份</p><p>通知：{notificationLabels[j.notification_state] || j.notification_state} · 尝试 {j.notification_attempts} 次</p>{j.error_code&&<p>{j.error_code}</p>}<div className="flex flex-wrap gap-3"><button className="text-primary" onClick={()=>action(j.id,'result')}>查看结果</button>{j.run_id&&<Link className="text-primary" to={`/runs/${j.run_id}/trace`}>运行记录</Link>}{j.state==='queued'&&<button onClick={()=>action(j.id,'cancel')}>取消排队</button>}{j.notification_state==='failed'&&<button onClick={()=>action(j.id,'retry-notification')}>重试结果通知</button>}</div></section>)}
 <div className="flex gap-3"><button disabled={page===0} onClick={()=>setPage(p=>p-1)}>上一页</button><span>第 {page+1} 页</span><button disabled={!more} onClick={()=>setPage(p=>p+1)}>下一页</button></div>
 {result&&<section className="inspector-card"><h2>任务结果</h2><pre className="text-xs whitespace-pre-wrap break-all max-h-80 overflow-auto">{JSON.stringify(result,null,2)}</pre></section>}
 </div>;
}
