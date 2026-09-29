import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api from '../services/api';
import AgentWorkflow from '../components/agents/AgentWorkflow';
import { useAuthStore } from '../store';

export default function AgentReleasesPage() {
  const {agentId} = useParams();
  const org = useAuthStore(s => s.currentOrgId);
  const base = `/rest/v1/agent_definitions/${encodeURIComponent(agentId || '')}`;
  const [purpose,setPurpose]=useState('quality_improvement');
  const [agent,setAgent] = useState<any>(null);
  const [releases,setReleases] = useState<any>(null);
  const [prompt,setPrompt] = useState('');
  const [input,setInput] = useState('合成测试文书：请整理已提供的事实，不补造缺失内容。');
  const [result,setResult] = useState<any>(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => {
    const c = new AbortController(); abort.current = c;
    setAgent(null); setReleases(null); setResult(null); setError(''); setBusy(false);
    Promise.all([api.get(base,{signal:c.signal}),api.get(`${base}/releases`,{signal:c.signal,params:{purpose}})])
      .then(([a,r]) => { if (!c.signal.aborted) {setAgent(a.data);setPrompt(a.data.system_prompt || '');setReleases(r.data);} })
      .catch(()=>{if(!c.signal.aborted)setError('无法读取当前组织的智能体版本。');});
    return ()=>c.abort();
  },[base,org,purpose]);
  async function action(kind:'save'|'publish'|'preview'|'activate'|'policy'|'business',version?:string) {
    if (busy) return;
    const c=abort.current;
    setBusy(true);setError('');
    try {
      if (kind==='business') {
        const r=await api.put(base,{config:{...agent.config,release_business_suite:version||null}},{signal:c?.signal});
        if(!c?.signal.aborted)setAgent(r.data);
      } else if (kind==='policy') {
        const r=await api.put(base,{config:{...agent.config,release_evaluation_required_for:releases.evaluation_gate?.required?(agent.config?.release_evaluation_required_for||[]).filter((p:string)=>p!==purpose&&p!=='*'):[...new Set([...(agent.config?.release_evaluation_required_for||[]),purpose])]}},{signal:c?.signal});
        if(!c?.signal.aborted)setAgent(r.data);
      } else if (kind==='save') {
        const r=await api.put(base,{system_prompt:prompt},{signal:c?.signal});
        if(!c?.signal.aborted){setAgent(r.data);setResult(null);}
      } else if (kind==='publish') await api.post(`${base}/publish`,null,{signal:c?.signal,params:{purpose}});
      else if(kind==='activate') await api.post(`${base}/releases/${encodeURIComponent(version || '')}/activate`,null,{signal:c?.signal});
      else {
        const r=await api.post(`/v1/agents/${encodeURIComponent(agentId || '')}/run`,
          {input:{text:input},preview_draft:true,purpose_of_use:'quality_improvement'},
          {signal:c?.signal,timeout:180000});
        if(!c?.signal.aborted)setResult(r.data);
      }
      if(c?.signal.aborted)return;
      const r=await api.get(`${base}/releases`,{signal:c?.signal,params:{purpose}});
      if(!c?.signal.aborted)setReleases(r.data);
    } catch(e:any) {
      if(!c?.signal.aborted) {
        const d=e.response?.data?.detail ?? e.response?.data;
        setError(typeof d==='string'?d:d?.message || d?.error || '操作失败，请检查权限与运行配置。');
      }
    } finally {if(!c?.signal.aborted)setBusy(false);}
  }
  const unsaved=agent && prompt!==(agent.system_prompt || '');
  return <div className="p-4 sm:p-6 w-full min-w-0 max-w-5xl mx-auto space-y-5 overflow-y-auto h-full">
    <AgentWorkflow agentId={agentId || ''} />
    <Link to={`/ai-studio/agents/${agentId}`} className="text-primary">返回智能体</Link>
    <h1 className="text-xl font-semibold">发布版本管理</h1>
    <Link className="text-primary underline" to={`/ai-studio/agents/${agentId}/evaluations`}>发布前质量评测</Link>
    <Link className="text-primary underline ml-4" to={`/ai-studio/agents/${agentId}/dependencies`}>外部依赖版本</Link>
    <p className="text-sm text-muted-foreground">保存只更新草稿。发布保存独立快照；指定旧版本的集成继续使用原快照。</p>
    <label>发布用途 <select aria-label="发布用途" disabled={busy || !!(agent && prompt!==(agent.system_prompt||''))} value={purpose} onChange={e=>setPurpose(e.target.value)}>{Object.entries({quality_improvement:'质量改进',research:'研究',treatment:'诊疗',payment:'支付',healthcare_operations:'医疗运营',public_health:'公共卫生'}).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
    {error && <p role="alert" className="text-red-700 bg-red-50 p-3 rounded-lg">{error}</p>}
    {agent && releases && <>
      <section className="inspector-card space-y-3"><h2 className="font-semibold">草稿 · {agent.name}</h2>
        <p>默认发布版本：{releases.active_version || '尚未发布'} · {unsaved?'有未保存编辑':releases.draft_changed?'有未发布修改':'草稿与默认版本一致'}</p>
        <div className="p-3 rounded-lg bg-muted space-y-2"><p>发布评测：{releases.evaluation_gate?.passed?'当前草稿已有有效通过报告':'当前草稿尚无有效通过报告，修改配置或依赖后需重新评测'}</p>
        <label className="flex gap-2"><input type="checkbox" aria-label="强制发布评测" checked={!!releases.evaluation_gate?.required} disabled={busy || !!unsaved || !!agent.config?.release_business_suite} onChange={()=>action('policy')}/>当前用途发布前必须通过评测</label>
        <label className="block">业务发布门禁 <select aria-label="业务发布门禁" disabled={busy||!!unsaved} value={agent.config?.release_business_suite||''} onChange={e=>void action('business',e.target.value)}><option value="">不指定业务套件</option><option value="documentation-v1">文书处理</option><option value="coding-v1">医学编码</option><option value="quality-v1">质量审核</option></select></label>
        {releases.evaluation_gate?.review_required&&<p className="text-sm">需通过指定业务套件的真实模型评测，并由管理员接受评测后才能发布。复核：{releases.evaluation_gate.review?.decision==='approved'?'已接受':releases.evaluation_gate.review?.decision==='rejected'?'已拒绝':'待复核'}。更改模型、草稿或依赖后须重新评测。</p>}
        <p className="text-xs">未启用时仅提示；启用后由服务端阻止缺少有效评测的发布。规则通过仍需专业复核。</p></div>
        <label className="block">系统提示词<textarea aria-label="草稿系统提示词" className="block w-full min-h-48 p-3 bg-background border border-border rounded-md" value={prompt} onChange={e=>setPrompt(e.target.value)}/></label>
        <p className="text-xs text-muted-foreground">专家、工具等配置可在智能体详情中编辑。发布快照保存已解析的运行配置；外部模型服务和工具程序仍需独立管理。</p>
        <div className="flex flex-wrap gap-3">
          <button disabled={busy || !unsaved || releases.status==='archived'} onClick={()=>action('save')} className="px-4 py-2 border border-border rounded-md disabled:opacity-40">保存草稿</button>
          <button disabled={busy || unsaved || !releases.draft_changed || releases.evaluation_gate?.can_publish===false || releases.status==='archived'} onClick={()=>action('publish')} className="px-4 py-2 bg-primary text-primary-foreground disabled:opacity-40">发布草稿</button>
        </div>
      </section>
      <section className="inspector-card space-y-3"><h2 className="font-semibold">调试已保存草稿</h2>
        <p className="text-sm text-muted-foreground">仅当前组织登录用户可调试，不影响线上版本。结果供人工复核。</p>
        <textarea aria-label="草稿测试资料" className="w-full min-h-28 p-3 bg-background border border-border rounded-md" maxLength={32000} value={input} onChange={e=>setInput(e.target.value)}/>
        <button disabled={busy || unsaved || !input.trim() || releases.status==='archived'} onClick={()=>action('preview')} className="px-4 py-2 border border-border rounded-md disabled:opacity-40">调试草稿</button>
        {result && <><p role="status">{result.error?'调试未完成':'草稿调用已返回，请复核结果'}</p><pre className="text-xs max-h-72 overflow-auto whitespace-pre-wrap">{JSON.stringify(result,null,2)}</pre></>}
      </section>
      <section className="inspector-card space-y-3"><h2 className="font-semibold">发布历史与默认版本</h2>
        <p className="text-sm text-muted-foreground">切换默认版本影响未指定版本的新调用；旧版本集成和当前草稿保持不变。</p>
        {!releases.releases.length && <p>尚无发布版本。</p>}
        {releases.releases.map((r:any)=><div key={r.version} className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
          <strong>{r.version}</strong>{r.evaluation_evidence?.evaluation_id && <span className="text-xs">关联评测：{r.evaluation_evidence.evaluation_id}</span>}<span className="text-xs text-muted-foreground">{new Date(r.created_at).toLocaleString()}</span>
          {r.active?<span className="text-primary">当前默认</span>:<button disabled={busy || releases.status!=='published'} className="text-primary underline disabled:opacity-40" onClick={()=>action('activate',r.version)}>设为默认／回滚</button>}
          <Link className="text-primary underline" to={`/ai-studio/agents/${agentId}/integration?version=${encodeURIComponent(r.version)}`}>集成此版本</Link>
        </div>)}
      </section>
    </>}
  </div>;
}
