import AgentWorkflow from '../components/agents/AgentWorkflow';
import RemoteHistory from '../components/agents/RemoteHistory';
import {useEffect,useRef,useState} from 'react';
import {Link,useParams} from 'react-router-dom';
import api from '../services/api';
import {useAuthStore} from '../store';
const kinds:Record<string,string>={model:'模型',tool:'工具',knowledge:'知识库'};
export default function AgentDependenciesPage(){
 const {agentId}=useParams();const org=useAuthStore(s=>s.currentOrgId);const base=`/rest/v1/agent_definitions/${agentId}/dependencies`;
 const [data,setData]=useState<any>(null),[bindings,setBindings]=useState<any[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [impact,setImpact]=useState<any>(null),[candidates,setCandidates]=useState<any[]>([]);
 const [revision,setRevision]=useState(0);
 const [kind,setKind]=useState('model'),[name,setName]=useState(''),[version,setVersion]=useState(''),[digest,setDigest]=useState('');
 const impactKey=useRef('');impactKey.current=base+kind+name+org;
 const controller=useRef<AbortController | null>(null);
 async function load(c=controller.current){const r=await api.get(base,{signal:c?.signal});if(!c?.signal.aborted){setData(r.data);setBindings(r.data.bindings);}}
 useEffect(()=>{const c=new AbortController();controller.current=c;setData(null);setBindings([]);setImpact(null);setCandidates([]);api.get(base+'/candidates',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setCandidates(r.data.candidates||[]);}).catch(()=>{});setName('');setVersion('');setDigest('');setError('');setBusy(false);load(c).catch(()=>{if(!c.signal.aborted)setError('无法读取依赖版本。');});return ()=>c.abort();},[base,org]);
 async function previewImpact(){const key=impactKey.current;const c=controller.current;setError('');try{const r=await api.get(base+'/impact',{params:{kind,name},signal:c?.signal});if(!c?.signal.aborted&&key===impactKey.current)setImpact(r.data);}catch{if(!c?.signal.aborted)setError('无法读取依赖影响范围。');}}
 async function save(register=false){const c=controller.current;setError('');setBusy(true);try{if(register)await api.post(base+'/register',{kind,name,version,artifact_digest:digest||null},{signal:c?.signal});else await api.put(base+'/bindings',{bindings},{signal:c?.signal});if(!c?.signal.aborted){await load(c);setRevision(n=>n+1);}}catch{if(!c?.signal.aborted)setError('保存失败：请检查组织管理权限、版本标识及摘要。已有版本的摘要不可修改。');}finally{if(!c?.signal.aborted)setBusy(false);}}
 return <div className="p-5 max-w-5xl mx-auto h-full overflow-auto space-y-4"><Link className="text-primary" to={`/ai-studio/agents/${agentId}/releases`}>返回发布版本管理</Link><h1 className="text-xl font-semibold">外部依赖版本</h1>{agentId&&<AgentWorkflow agentId={agentId}/>}
 <p>按实际使用的模型、工具和知识库登记版本，由部署负责人核验。发布时锁定登记清单；登记版本变化后，旧发布调用会被阻止，需重新评测与发布。</p><p className="text-sm text-muted-foreground">登记不会部署或回滚外部服务，也不能检测供应方未披露的内部变化。未绑定的依赖不在本项检测范围内。</p>
 {error&&<p role="alert">{error}</p>}{data&&<>
 <section className="inspector-card space-y-3"><h2 className="font-semibold">当前发布锁定清单</h2>{!data.locked.length&&<p>尚未锁定外部依赖。</p>}{data.locked.map((d:any)=><p key={d.kind+d.name}>{kinds[d.kind]} · {d.name} · {d.version}</p>)}
 {data.drift.length>0?<p role="alert">检测到依赖版本变化：{data.drift.map((d:any)=>`${d.expected.name} ${d.expected.version} → ${d.current?.version || '未登记'}`).join('；')}。旧发布版本暂不可运行。</p>:<p>登记清单未发现变化；这不代表外部服务内容已被自动核验。</p>}</section>
 <section className="inspector-card space-y-3"><h2 className="font-semibold">草稿绑定</h2><p className="text-sm">选择当前智能体实际使用的依赖。保存后需发布才会进入锁定清单。</p>
 <RemoteHistory key={org+base+"bindings"} url={base} field="registry" label="按依赖名称或版本查找" currentOnly revision={revision} render={(d:any)=><label className="flex gap-2" key={d.kind+d.name}><input type="checkbox" disabled={busy} checked={bindings.some(b=>b.kind===d.kind&&b.name===d.name)} onChange={e=>setBindings(previous=>e.target.checked?[...previous,{kind:d.kind,name:d.name}]:previous.filter(b=>b.kind!==d.kind||b.name!==d.name))}/>{kinds[d.kind]} · {d.name} · {d.version}</label>}/><p className="text-sm break-all">已选 {bindings.length} 项：{bindings.map(b=>b.name).join("、") || "无"}（翻页保留选择）</p><button disabled={busy} className="bg-primary text-primary-foreground px-4 py-2" onClick={()=>save()}>保存草稿依赖</button></section>
 {data.can_register&&<section className="inspector-card space-y-3"><h2 className="font-semibold">登记当前外部版本（组织管理员）</h2><p>此操作更新组织共享登记，可能影响其他绑定该依赖的智能体。请先确认外部服务的真实版本。</p>
 <label className="block">从运行配置选择<select aria-label="配置中的依赖" defaultValue="" onChange={e=>{const selected=candidates[Number(e.target.value)];if(selected){setKind(selected.kind);setName(selected.name);setImpact(null);}}}><option value="">选择已有模型或工具</option>{candidates.map((c,i)=><option value={i} key={c.kind+c.name}>{kinds[c.kind]} · {c.name}</option>)}</select></label><p className="text-xs">仅预填名称；版本与制品摘要仍须核验后填写。</p>
 <select aria-label="依赖类型" value={kind} onChange={e=>{setKind(e.target.value);setImpact(null);}}>{Object.entries(kinds).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select>
 <input aria-label="依赖名称" placeholder="依赖名称，如 clinical-model" className="block w-full p-2 border rounded-md bg-background" value={name} onChange={e=>{setName(e.target.value);setImpact(null);}}/>
 <input aria-label="依赖版本" placeholder="供应方版本标识，如 2026.09.1" className="block w-full p-2 border rounded-md bg-background" value={version} onChange={e=>setVersion(e.target.value)}/>
 <input aria-label="依赖摘要" placeholder="可选：经核验的 SHA-256 摘要" className="block w-full p-2 border rounded-md bg-background" value={digest} onChange={e=>setDigest(e.target.value)}/>
 <button disabled={busy||!name} onClick={previewImpact}>查看变更影响</button>
 {impact&&<section className="border rounded-lg p-3 space-y-2"><h3>当前登记引用范围</h3><p className="text-xs">客户端仅表示有权调用，无法推断其是否固定使用某个版本；更新前请核对实际接入方。排队数包含该智能体所有版本。</p>{!impact.agents.length&&<p>未发现登记引用。</p>}{impact.agents.map((a:any)=><div key={a.agent_id}><Link className="text-primary" to={`/ai-studio/agents/${a.agent_id}/releases`}>{a.name}</Link> · {a.draft_bound?'草稿已绑定':'仅历史发布引用'} · 待完成任务 {a.pending_jobs}<p>发布版本：{a.releases.map((r:any)=>`${r.version}${r.active?'（默认）':''} / 依赖 ${r.dependency_version}`).join('；')||'无'}</p><p>授权客户端：{a.authorized_clients.map((c:any)=>c.name).join('、')||'无'}</p></div>)}</section>}
 <button disabled={busy||!name||!version} onClick={()=>save(true)}>登记当前版本</button></section>}
 <section className="inspector-card space-y-2"><h2 className="font-semibold">组织依赖历史</h2><RemoteHistory key={org+base+"history"} url={base} field="registry" label="依赖名称或版本历史" revision={revision} render={(d:any)=><p className="text-sm break-all" key={d.kind+d.name+d.version}>{kinds[d.kind]} · {d.name} · {d.version} {d.is_current?'（当前）':''}{d.artifact_digest?` · SHA-256 ${d.artifact_digest}`:' · 未提供制品摘要'}</p>}/></section>
 </>}
 </div>;
}
