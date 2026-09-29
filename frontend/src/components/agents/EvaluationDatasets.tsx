import CodingDifference from './CodingDifference';
import {useEffect,useRef,useState} from 'react';
import api from '../../services/api';
import {downloadEvaluation} from './EvaluationImport';
const splits:Record<string,string>={training:'训练集',validation:'验证集',acceptance:'验收集'};
const statuses:Record<string,string>={pending:'待审核',approved:'已审核',rejected:'已拒绝',active:'运行中',completed:'已结束',cancelled:'已取消',blocked:'已阻断',queued:'排队中',running:'执行中',failed:'执行失败',interrupted:'执行中断'};
function message(e:any){const d=e?.response?.data?.detail;return typeof d==='string'?d:d?.message||(e?.response?'操作未完成，请检查权限、数据格式与当前版本后重试。':e?.message||'操作未完成，请重试。');}

export default function EvaluationDatasets({agentId,suite,onLoad}:{agentId:string;suite:string;onLoad:(v:string)=>void}){
 const [rows,setRows]=useState<any[]>([]),[selected,setSelected]=useState<any>(null),[name,setName]=useState(''),[split,setSplit]=useState('validation'),[note,setNote]=useState('');
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[page,setPage]=useState(0),[more,setMore]=useState(false),[revision,setRevision]=useState(0),[batches,setBatches]=useState<any[]>([]),[batch,setBatch]=useState('');
 const ticket=useRef(crypto.randomUUID()),alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{const c=new AbortController();api.get('/evaluation-datasets',{params:{offset:page*20},signal:c.signal}).then(r=>{if(!c.signal.aborted){setRows(r.data.items||[]);setMore(r.data.has_more);}}).catch(()=>{if(!c.signal.aborted)setError('评测集读取失败。');});return ()=>c.abort();},[page,revision]);
 useEffect(()=>{const c=new AbortController();setBatch('');setBatches([]);ticket.current=crypto.randomUUID();if(selected)api.get(`/evaluation-datasets/${selected.id}/batches`,{signal:c.signal}).then(r=>{if(!c.signal.aborted){setBatches(r.data);if(r.data[0])setBatch(r.data[0].id);}}).catch(()=>{if(!c.signal.aborted)setError('批次读取失败。');});return ()=>c.abort();},[selected?.id,revision]);
 async function perform(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();}catch(e){if(alive.current)setError(message(e));}finally{if(alive.current)setBusy(false);}}
 async function save(append=false){await perform(async()=>{const cases=JSON.parse(suite);const r=await api.post('/evaluation-datasets',{name,split,cases,...(append&&selected?{dataset_id:selected.dataset_id,expected_version:selected.version,append:true}:{})});if(alive.current){setSelected(r.data);setPage(0);setRevision(v=>v+1);}});}
 async function importAll(file?:File){if(!file)return;await perform(async()=>{
  if(file.size>10*1024*1024)throw new Error('文件超过 10 MB');
  let r;if(file.name.toLowerCase().endsWith('.xlsx')){const body=new FormData();body.append('file',file);body.append('name',name);body.append('split',split);r=await api.post('/evaluation-datasets/import-xlsx',body,{timeout:120000});}
  else {const raw=JSON.parse((await file.text()).replace(/^\uFEFF/,''));r=await api.post('/evaluation-datasets',{name,split,cases:Array.isArray(raw)?raw:raw.cases});}
  if(alive.current){setSelected(r.data);setPage(0);setRevision(v=>v+1);}
 });}
 async function review(decision:string){await perform(async()=>{const r=await api.post(`/evaluation-datasets/${selected.id}/review`,{decision,note,expected_reviews:selected.reviews.length});if(alive.current){setSelected(r.data);setNote('');setRevision(v=>v+1);}});}
 async function start(){await perform(async()=>{const r=await api.post(`/evaluation-datasets/${selected.id}/batches`,{agent_id:agentId,request_id:ticket.current});if(alive.current){setBatch(r.data.id);setBatches(v=>[{id:r.data.id,state:'active'},...v.filter(b=>b.id!==r.data.id)]);ticket.current=crypto.randomUUID();}});}
 return <section className="inspector-card space-y-3" aria-label="已保存评测集"><h2 className="font-semibold">评测集</h2>
 <p className="text-sm">保存样例，审核后批量运行。每个版本最多 2000 条。</p>
 {error&&<p role="alert">{error}</p>}
 <details className="evaluation-disclosure"><summary>新建或追加样例</summary><div className="flex flex-wrap gap-3"><label>评测集名称<input aria-label="评测集名称" className="border rounded-lg p-2" value={name} maxLength={120} onChange={e=>setName(e.target.value)}/></label><label>数据用途<select aria-label="数据用途" value={split} onChange={e=>setSplit(e.target.value)}>{Object.entries(splits).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label></div>
 <div className="flex flex-wrap gap-3"><button disabled={busy||!name.trim()} onClick={()=>void save()}>将编辑中的样例保存为新评测集</button><button disabled={busy||!name.trim()||!selected} onClick={()=>void save(true)}>追加到所选集的新版本</button><label>导入完整文件并保存<input aria-label="保存完整评测集文件" type="file" accept=".xlsx,.json" disabled={busy||!name.trim()} onChange={e=>{void importAll(e.target.files?.[0]);e.target.value='';}}/></label></div>
 <p className="text-xs text-muted-foreground">导入文件不调用模型。请先确认脱敏情况；训练、验证和验收数据分别保存。追加时标识必须唯一。批量运行只评测当前已保存草稿，不会自动发布。</p>
 </details><div className="flex flex-wrap gap-2"><button disabled={page===0||busy} onClick={()=>setPage(v=>v-1)}>评测集上一页</button><span>第 {page+1} 页</span><button disabled={!more||busy} onClick={()=>setPage(v=>v+1)}>评测集下一页</button><button onClick={()=>setRevision(v=>v+1)}>刷新评测集</button></div>
 {!rows.length&&<div className="evaluation-empty"><h3>从第一组样例开始</h3><p>展开“新建或追加样例”，导入文件或保存编辑中的样例。</p></div>}<ul className="space-y-2">{rows.map(d=><li key={d.id}><button className={`w-full text-left border rounded-xl p-3 ${selected?.id===d.id?'border-primary bg-blue-50':''}`} onClick={()=>{setSelected(d);setName(d.name);setSplit(d.split);setNote('');}}>{d.name} · v{d.version} · {splits[d.split]} · {d.case_count} 条 · {statuses[d.review_status]}</button></li>)}</ul>
 {selected&&<div className="border rounded-xl p-3 space-y-3"><h3>{selected.name} · v{selected.version} · {selected.case_count} 条 · {statuses[selected.review_status]}</h3>
 <div className="flex gap-3"><button onClick={()=>void perform(async()=>{const r=await api.get(`/evaluation-datasets/${selected.id}`,{params:{limit:2000}});downloadEvaluation(r.data.cases,`dataset-v${selected.version}.json`);})}>下载此版本全部样例</button><button onClick={()=>void perform(async()=>{const r=await api.get(`/evaluation-datasets/${selected.id}`,{params:{limit:10}});if(alive.current)onLoad(JSON.stringify(r.data.cases,null,2));})}>复制前 10 条到编辑区</button></div>
 <details className="evaluation-disclosure" key={selected.id+selected.review_status} open={selected.review_status==='pending'}><summary>版本审核 · {statuses[selected.review_status]}</summary><p className="text-sm">管理员审核：请核对样例与预期答案。接受只确认此评测集版本，不代表模型通过业务验收。</p>
 {selected.reviews.map((r:any,i:number)=><p key={i} className="text-xs">{statuses[r.decision]} · {r.note} · {new Date(r.at).toLocaleString()}</p>)}
 <textarea aria-label="评测集审核意见" className="border rounded-lg p-2 w-full" maxLength={2000} value={note} onChange={e=>setNote(e.target.value)} placeholder="填写核对范围与审核意见，请勿填写患者身份信息"/>
 <button disabled={busy||!note.trim()} onClick={()=>void review('approved')}>接受此评测集版本</button> · <button disabled={busy||!note.trim()} onClick={()=>void review('rejected')}>拒绝此评测集版本</button></details>
 <p className="text-sm">开始后会逐条调用模型，最多 {selected.case_count} 次任务，可能产生 API 费用。取消停止未开始的样例；正在执行的样例会收尾。</p>
 <button className="rounded-full bg-primary text-primary-foreground px-4 py-2 disabled:opacity-40" disabled={busy||selected.review_status!=='approved'} onClick={()=>void start()}>开始后台批量评测</button>
 <label className="block">历史批次<select aria-label="历史批次" value={batch} onChange={e=>setBatch(e.target.value)}><option value="">选择批次</option>{batches.map(b=><option key={b.id} value={b.id}>{b.id} · {statuses[b.state]||b.state}</option>)}</select></label>
 {batch&&<BatchProgress key={selected.id+batch} rid={selected.id} bid={batch}/>}</div>}
 </section>;
}

function BatchProgress({rid,bid}:{rid:string;bid:string}){
 const [data,setData]=useState<any>(null),[error,setError]=useState(''),[offset,setOffset]=useState(0),[failed,setFailed]=useState(false),[revision,setRevision]=useState(0);
 const base=`/evaluation-datasets/${rid}/batches/${bid}`;
 useEffect(()=>{const c=new AbortController();let timer:ReturnType<typeof setTimeout>;async function poll(){try{const r=await api.get(base,{params:{offset,failed_only:failed},signal:c.signal});if(!c.signal.aborted){setData(r.data);setError('');if(r.data.state==='active'||r.data.states.running)timer=setTimeout(poll,3000);}}catch{if(!c.signal.aborted)setError('进度读取失败，请刷新重试。');}}void poll();return()=>{c.abort();clearTimeout(timer);};},[base,offset,failed,revision]);
 async function action(kind:string){try{await api.post(`${base}/${kind}`);setRevision(v=>v+1);}catch(e){setError(message(e));}}
 return <div className="space-y-3">{error&&<p role="alert">{error}</p>}<button onClick={()=>setRevision(v=>v+1)}>刷新批次</button>{data&&<><p>状态：{statuses[data.state]} · 已执行 {data.states.completed+data.states.failed+data.states.interrupted}/{data.total} · 检查通过 {data.passed} · 排队 {data.states.queued} · 执行中 {data.states.running} · 已取消 {data.states.cancelled}</p><div className="flex gap-3"><button disabled={data.state!=='active'} onClick={()=>void action('cancel')}>取消未开始样例</button><button disabled={data.state==='cancelled'||!(data.states.failed+data.states.interrupted)} onClick={()=>void action('retry')}>重试执行失败或中断项</button></div><p className="text-xs">重试可能再次产生费用；检查结果不符合预期的样例不会被此按钮重跑。配置变化需新建批次。结果匹配率仅反映指定样例，不是总体临床准确率。</p>
 <details className="evaluation-disclosure"><summary>字段匹配详情</summary><div className="text-sm">{Object.entries(data.field_matches).map(([k,v]:[string,any])=><p key={k}>{({primary_diagnosis_code:'主要诊断',other_diagnosis_codes:'其他诊断',primary_procedure_code:'主要手术',other_procedure_codes:'其他手术'} as Record<string,string>)[k]||k}：{v.matched}/{v.checked} 匹配</p>)}</div></details>
 <label><input type="checkbox" checked={failed} onChange={e=>{setFailed(e.target.checked);setOffset(0);}}/>仅看未通过样例</label>
 {data.items.map((i:any)=><details key={i.id}><summary>{i.case_id} · {statuses[i.state]} {i.state==='completed'?(i.result?.checks_passed?'· 检查通过':'· 检查未通过'):''}</summary>{i.error_code&&<p>{i.error_code}</p>}<p>历史尝试记录：{i.attempts.length}</p>{i.result?.cases?.map((c:any)=><div key={c.case_id}>{c.candidate.run_id&&<a className="text-primary" href={`/runs/${c.candidate.run_id}/trace`}>查看运行证据</a>}<CodingDifference checks={c.candidate.checks}/><details><summary>全部检查</summary><pre className="whitespace-pre-wrap text-xs">{JSON.stringify(c.candidate.checks,null,2)}</pre></details><p>{c.candidate.model_usage?.models?.map((m:any)=>m.model).join(' / ')||'未记录真实模型用量'}</p></div>)}</details>)}
 <div className="flex gap-3"><button disabled={!offset} onClick={()=>setOffset(v=>v-20)}>结果上一页</button><button disabled={!data.has_more} onClick={()=>setOffset(v=>v+20)}>结果下一页</button></div></>}</div>;
}
