import CodingDifference from '../components/agents/CodingDifference';
import './AgentEvaluationPage.css';
import AgentWorkflow from '../components/agents/AgentWorkflow';
import RemoteHistory from '../components/agents/RemoteHistory';
import TaskInputEditor, {validateTaskInput} from '../components/agents/TaskInputEditor';
import EvaluationImport from '../components/agents/EvaluationImport';
import EvaluationDatasets from '../components/agents/EvaluationDatasets';
import {useEffect,useRef,useState} from 'react';
import {Link,useParams} from 'react-router-dom';
import api from '../services/api';
import {useAuthStore} from '../store';

const checkLabels:Record<string,string>={execution:'执行成功',json_object:'有效 JSON 对象',json_field_equals:'字段匹配',no_extra_fields:'无额外字段',real_model:'真实模型证据',contains:'包含预期内容',excludes:'不含禁用内容',field_equals:'字段匹配'};
const reasonLabels:Record<string,string>={ok:'符合预期',invalid_json:'输出不是有效 JSON 对象',missing_field:'缺少必需字段',value_mismatch:'字段值与预期不一致',unexpected_fields:'包含不应新增的字段',real_model_evidence_missing:'缺少匹配配置的真实模型用量证据',execution_failed:'执行失败'};
const defaultSuite=JSON.stringify([{id:'missing-information',text:'合成软件测试资料：未提供诊断与检查结果。',contains:[],excludes:['测试禁用词'],expected_fields:{}}],null,2);
export default function AgentEvaluationPage(){
 const [view,setView]=useState('datasets');
 const {agentId}=useParams();const org=useAuthStore(s=>s.currentOrgId);
 const base=`/rest/v1/agent_definitions/${encodeURIComponent(agentId || '')}`;
 const [versions,setVersions]=useState<string[]>([]),[baseline,setBaseline]=useState(''),[candidate,setCandidate]=useState('draft');
 const [purpose,setPurpose]=useState('quality_improvement');
 const [suite,setSuite]=useState(defaultSuite);
 const [businessSuite,setBusinessSuite]=useState(''),[builtins,setBuiltins]=useState<any[]>([]),[reviewRevision,setReviewRevision]=useState(0);
 const [reports,setReports]=useState<any[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const controller=useRef<AbortController | null>(null);
 useEffect(()=>{const c=new AbortController();controller.current=c;setReports([]);setVersions([]);setSuite(defaultSuite);setBusinessSuite('');setBuiltins([]);setPurpose('quality_improvement');setError('');setBusy(false);
 api.get(`${base}/evaluation-suites`,{signal:c.signal}).then(r=>{if(!c.signal.aborted)setBuiltins(r.data.suites||[]);}).catch(()=>{});
 api.get(`${base}/releases`,{signal:c.signal}).then(r=>{
 if(c.signal.aborted)return;setVersions(r.data.releases.map((v:any)=>v.version));setBusinessSuite(r.data.evaluation_gate?.business_suite||'');setBaseline(r.data.evaluation_gate?.business_suite?'':r.data.active_version || '');setCandidate('draft');setReports([]);
 }).catch(()=>{if(!c.signal.aborted)setError('无法读取评测配置。');});return ()=>c.abort();},[base,org]);
 async function evaluate(){const c=controller.current;setError('');let cases;
 const validation=businessSuite?'':validateTaskInput(suite,'evaluation');if(validation){setError(validation);return;}
 try{cases=businessSuite?undefined:JSON.parse(suite);}catch{setError('样例 JSON 格式不正确。');return;}
 setBusy(true);try{const r=await api.post(`${base}/evaluations`,{baseline_version:baseline||null,candidate_version:candidate,purpose_of_use:purpose,...(businessSuite?{business_suite:businessSuite}:{cases})},{signal:c?.signal,timeout:3600000});
 if(!c?.signal.aborted)setReports(previous=>[r.data,...previous]);}catch{if(!c?.signal.aborted)setError('评测未完成：请检查样例规则、权限和运行状态；已执行的任务可在运行记录中查看。');}finally{if(!c?.signal.aborted)setBusy(false);}}
 function download(value:any,name:string){const url=URL.createObjectURL(new Blob([typeof value==='string'?value:JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);}
 return <div className="evaluation-workspace"><div className="evaluation-content">
 <Link className="text-primary" to={`/ai-studio/agents/${agentId}/releases`}>返回发布版本管理</Link>
 <header className="evaluation-header"><div><h1>质量评测</h1><p>用可靠的样例，验证智能体的每一次改进。</p></div><span className="evaluation-badge">发布前验证</span></header><details className="evaluation-disclosure"><summary>查看交付流程</summary>{agentId&&<AgentWorkflow agentId={agentId}/>}</details>
 <nav className="evaluation-segments" aria-label="评测视图">{[["datasets","评测集"],["single","单次评测"],["history","评测记录"]].map(([id,label])=><button key={id} aria-pressed={view===id} onClick={()=>setView(id)}>{label}</button>)}</nav>
 {error && <p role="alert">{error}</p>}
 <div hidden={view!=="datasets"}>
 {agentId&&<EvaluationDatasets key={'datasets:'+org+base} agentId={agentId} suite={businessSuite?JSON.stringify(builtins.find(s=>s.id===businessSuite)?.cases||[]):suite} onLoad={value=>{setView('single');setSuite(value);setBusinessSuite('');setBaseline('');}}/>}
</div>
 <div hidden={view!=="single"} className="evaluation-single">
 <details className="evaluation-disclosure"><summary>导入样例或下载模板</summary> <EvaluationImport key={'import:'+org+base} base={base} suites={builtins} disabled={busy} onApply={value=>{setSuite(value);setBusinessSuite('');setBaseline('');setError('');}}/></details>
 <section className="inspector-card space-y-3">
 <label>业务验收套件 <select aria-label="业务验收套件" disabled={busy} value={businessSuite} onChange={e=>{setBusinessSuite(e.target.value);setBaseline('');}}><option value="">自定义规则</option>{builtins.map(s=><option key={s.id} value={s.id}>{s.name} · {s.id}</option>)}</select></label>
 <p className="text-xs">业务套件使用固定合成资料、逐字段检查和真实模型用量证据。默认只评测候选，可另选基线；每个版本会执行 2 次模型任务并产生 API 费用。</p>
 <label>评测用途 <select aria-label="评测用途" disabled={busy} value={purpose} onChange={e=>setPurpose(e.target.value)}>{Object.entries({quality_improvement:'质量改进',research:'研究',treatment:'诊疗',payment:'支付',healthcare_operations:'医疗运营',public_health:'公共卫生'}).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
 <label>基线版本 <select aria-label="基线版本" disabled={busy} value={baseline} onChange={e=>setBaseline(e.target.value)}><option value="">无基线（仅检查候选）</option>{versions.map(v=><option key={v}>{v}</option>)}</select></label>
 <label>候选版本 <select aria-label="候选版本" disabled={busy} value={candidate} onChange={e=>setCandidate(e.target.value)}><option value="draft">已保存草稿</option>{versions.map(v=><option key={v}>{v}</option>)}</select></label>
 {!businessSuite&&<p className="text-sm">填写表单或导入已有样例，可下载后复用。最多 10 个样例，每个必须有明确检查；contains / excludes 检查结果内容，expected_fields 用点路径比较结果字段。请将默认演示规则替换为业务验收要求。</p>}
 {!businessSuite&&<TaskInputEditor key={org+base} kind="evaluation" value={suite} disabled={busy} hideImport onChange={value=>{setSuite(value);}}/>}
 {businessSuite&&<div className="rounded-lg bg-muted p-3 text-sm"><p>{builtins.find(s=>s.id===businessSuite)?.description}</p>{builtins.find(s=>s.id===businessSuite)?.cases.map((c:any)=><details key={c.id}><summary>{c.id}</summary><p>{c.text}</p><pre className="whitespace-pre-wrap">预期：{JSON.stringify(c.expected_json,null,2)}</pre></details>)}</div>}
 <div className="flex gap-3"><button disabled={busy || baseline===candidate} className="bg-primary text-primary-foreground px-4 py-2" onClick={evaluate}>{busy?'正在运行评测…':'运行新旧版本评测'}</button><button onClick={()=>download(businessSuite?builtins.find(s=>s.id===businessSuite):suite,'evaluation-suite.json')}>下载固定样例</button></div>
 </section>
 {reports[0]&&<p role="status">{!reports[0].consistent?"评测期间草稿发生变化，本次结论无效":reports[0].checks_passed?"本次评测已通过，报告已保存":"本次评测存在未通过项，报告已保存"}</p>}
 </div><div hidden={view!=="history"}><h2 className="evaluation-section-title">评测记录</h2>
 <RemoteHistory key={'history:'+org+base} url={`${base}/evaluations`} field="items" label="评测版本、报告标识或样例摘要" revision={reports.length+reviewRevision} render={r=><details className="inspector-card evaluation-report space-y-3" key={r.id}>
 <summary>{r.baseline_version || '无基线'} → {r.candidate_version} · 候选通过 {r.candidate_passed}/{r.case_count} · 退步 {r.regressions}</summary>
 {r.batch_context&&<p className="text-xs">批量任务的单例记录，不作为独立发布验收报告。</p>}
 <p>{!r.consistent?'评测期间配置发生变化，本次结论无效':r.checks_passed?'软件检查通过，人工验收状态见下方':'存在未通过项，请检查运行证据'}</p>
 <p className="text-xs break-all">{r.business_suite&&`业务套件：${r.business_suite} · `}样例摘要：{r.suite_digest}</p>
 {r.cases.map((c:any)=><div key={c.case_id} className="flex flex-wrap gap-3 text-sm"><strong>{c.case_id}</strong>{['baseline','candidate'].map(k=><div key={k}>{k==='baseline'?'基线':'候选'}：{c[k].skipped?'未设置':c[k].passed?'通过':'未通过'} {c[k].model_usage&&<small> · {c[k].model_usage.models?.map((m:any)=>m.model).join(' / ')} · {c[k].model_usage.input_tokens??'—'} 输入 / {c[k].model_usage.output_tokens??'—'} 输出 Token</small>}<CodingDifference checks={c[k].checks}/><details><summary>逐项检查</summary>{c[k].checks?.map((check:any,i:number)=><p key={i}>{check.passed?'通过':'未通过'} · {check.path||checkLabels[check.kind]||check.kind} · {reasonLabels[check.reason]||checkLabels[check.kind]||check.kind}</p>)}</details>{c[k].run_id && <Link className="text-primary underline" to={`/runs/${c[k].run_id}/trace`}>运行记录</Link>}</div>)}</div>)}
 <EvaluationReview key={org+base+r.id} base={base} report={r} onChanged={()=>setReviewRevision(v=>v+1)}/>
 <button className="text-primary underline" onClick={()=>download(r,`evaluation-${r.id}.json`)}>下载评测报告</button>
 </details>}/>

 </div><p className="evaluation-footnote">检查结果用于辅助质量判断，发布前仍需专业人员复核。</p></div></div>;
}

function EvaluationReview({base,report,onChanged}:{base:string;report:any;onChanged:()=>void}){
 const [note,setNote]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function review(decision:string){setBusy(true);setError('');try{await api.post(`${base}/evaluations/${report.id}/review`,{decision,note,expected_previous_review_id:report.review?.id||null});setNote('');onChanged();}catch{setError('复核未保存：请检查报告是否通过、配置是否变化及当前权限，刷新后重试。');}finally{setBusy(false);}}
 return <div className="rounded-lg border border-border p-3 space-y-2"><p>人工验收复核：{report.review?report.review.decision==='approved'?'已接受':'已拒绝':'待复核'}</p>{report.review&&<p className="text-sm">{report.review.note} · {new Date(report.review.created_at).toLocaleString()}</p>}{report.review_editable&&<><textarea aria-label={`复核意见 ${report.id}`} value={note} onChange={e=>setNote(e.target.value)} maxLength={2000} className="w-full rounded-lg border p-2 bg-background" placeholder="说明检查范围与验收意见，请勿填写患者身份信息。"/><p className="text-xs">接受表示认可本次验收证据，不代表已取得临床准入或专业资质审批。</p><button disabled={busy||!note.trim()||!report.checks_passed||!report.consistent} onClick={()=>void review('approved')}>接受评测</button> · <button disabled={busy||!note.trim()} onClick={()=>void review('rejected')}>拒绝评测</button></>}{error&&<p role="alert">{error}</p>}</div>;
}
